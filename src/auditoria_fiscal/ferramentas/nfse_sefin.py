"""Cliente da Sefin Nacional para a Fase 2 da NFS-e (spec 008, research.md).

So a PRODUCAO RESTRITA (`tpAmb = 2`, hosts `*.producaorestrita.nfse.gov.br`)
— e loopback, que so os testes usam. Produção e' a Fase 3.

Transporte com a biblioteca padrao (`http.client` + `ssl`): o mTLS precisa
so de um `SSLContext` com o e-CNPJ. O `ssl` do Python carrega a chave de
arquivo; ela vai para um PEM cifrado com senha aleatoria, numa pasta
temporaria privada, e e' apagada logo depois de carregada (FR-202). O
servidor e' sempre verificado (FR-209).

O cliente so relata o que aconteceu; quem decide o que fazer com a DPS e' a
transmissao (`nfse_transmissao.py`). Sem FastAPI, sem banco.
"""

from __future__ import annotations

import base64
import gzip
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import tempfile
import zlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from lxml import etree

from ..core import nfse as nf
from ..core.nfse_certificado import CertificadoA1

URL_SEFIN_RESTRITA = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
URL_ADN_RESTRITA = "https://adn.producaorestrita.nfse.gov.br"
SUFIXO_RESTRITA = ".producaorestrita.nfse.gov.br"
TIMEOUT_PADRAO = 60.0
MAX_RESPOSTA = 10 * 1024 * 1024
MAX_XML = 5 * 1024 * 1024

DESTINO_PROIBIDO = "DESTINO_PROIBIDO"
AMBIENTE_PROIBIDO = "AMBIENTE_PROIBIDO"
ID_INVALIDO = "ID_INVALIDO"

# Resultados
AUTORIZADA = "autorizada"
REJEITADA = "rejeitada"
CERTIFICADO_RECUSADO = "certificado_recusado"
INCERTA = "incerta"            # pode ter sido processada: consultar antes de reenviar
SEM_CONEXAO = "sem_conexao"    # nada saiu daqui (TLS ou rede antes do envio)
EXISTE = "existe"
NAO_EXISTE = "nao_existe"


@dataclass
class RespostaEnvio:
    resultado: str
    http_status: int | None = None
    chave_acesso: str | None = None
    nfse_xml: bytes | None = None
    erros: list = field(default_factory=list)
    alertas: list = field(default_factory=list)
    mensagem: str = ""
    versao_aplicativo: str | None = None
    dh_processamento: str | None = None

    @property
    def duplicada(self) -> bool:
        """E0014: serie e numero ja usados numa NFS-e (research.md, R-6)."""
        return any(e.get("codigo") == "E0014" for e in self.erros)


@dataclass
class RespostaConsulta:
    resultado: str
    http_status: int | None = None
    chave_acesso: str | None = None
    xml: bytes | None = None
    mensagem: str = ""


class _SemConexao(Exception):
    pass


class _Incerto(Exception):
    pass


def _host_permitido(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    if host.endswith(SUFIXO_RESTRITA):
        return True
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def conferir_destino(url: str) -> str:
    partes = urlsplit(url or "")
    if partes.scheme != "https" or not _host_permitido(partes.hostname or ""):
        raise nf.ErroNfse(DESTINO_PROIBIDO,
                          "A Fase 2 só transmite para a produção restrita da Sefin "
                          f"Nacional (https://*{SUFIXO_RESTRITA}); destino recusado: "
                          f"{partes.scheme}://{partes.hostname}.")
    return partes.hostname


def _contexto_tls(certificado: CertificadoA1, ca_extra: str | None) -> ssl.SSLContext:
    contexto = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    if ca_extra:
        contexto.load_verify_locations(cafile=ca_extra)
    senha = secrets.token_urlsafe(32).encode("ascii")
    pasta = tempfile.mkdtemp(prefix="nfse_tls_")   # 0700 no Linux
    try:
        caminho_cert = os.path.join(pasta, "cert.pem")
        caminho_chave = os.path.join(pasta, "chave.pem")
        cadeia = [certificado.certificado, *certificado.cadeia]
        with open(caminho_cert, "wb") as arq:
            for c in cadeia:
                arq.write(c.public_bytes(serialization.Encoding.PEM))
        with open(caminho_chave, "wb") as arq:
            arq.write(certificado.chave.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(senha)))
        contexto.load_cert_chain(caminho_cert, caminho_chave, password=senha)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return contexto


def _descompactar_b64(texto: str) -> bytes:
    """Base64 + gzip, com teto (uma resposta nao vira bomba de memoria)."""
    bruto = base64.b64decode(texto or "", validate=False)
    descompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    dado = descompressor.decompress(bruto, MAX_XML + 1)
    if len(dado) > MAX_XML or descompressor.unconsumed_tail:
        raise ValueError("XML devolvido maior que o limite.")
    return dado


def _campo(item: dict, *nomes):
    for nome in nomes:
        for chave, valor in item.items():
            if chave.lower() == nome:
                return valor
    return None


def _erros(corpo) -> list[dict]:
    """Lista de erros da Sefin, tolerante a variacoes de nome (research, R-6)."""
    if not isinstance(corpo, dict):
        return []
    lista = _campo(corpo, "erros", "erro")
    if isinstance(lista, dict):
        lista = [lista]
    if not isinstance(lista, list):
        return []
    saida = []
    for item in lista:
        if isinstance(item, dict):
            saida.append({"codigo": str(_campo(item, "codigo") or ""),
                          "descricao": str(_campo(item, "descricao") or "")[:1000],
                          "complemento": str(_campo(item, "complemento") or "")[:1000]})
        else:
            saida.append({"codigo": "", "descricao": str(item)[:1000], "complemento": ""})
    return saida


class ClienteSefin:
    def __init__(self, certificado: CertificadoA1, *, url_sefin: str = URL_SEFIN_RESTRITA,
                 url_adn: str = URL_ADN_RESTRITA, ca_extra: str | None = None,
                 timeout: float = TIMEOUT_PADRAO):
        self.destino = conferir_destino(url_sefin)
        conferir_destino(url_adn)
        self.url_sefin = url_sefin.rstrip("/")
        self.url_adn = url_adn.rstrip("/")
        self.timeout = float(timeout)
        self._contexto = _contexto_tls(certificado, ca_extra)

    @classmethod
    def do_ambiente(cls, certificado: CertificadoA1) -> "ClienteSefin":
        """Endereços e CA extra pelas variaveis AUDITORIA_NFSE_*; o padrao e'
        a producao restrita oficial."""
        try:
            timeout = float(os.environ.get("AUDITORIA_NFSE_TIMEOUT") or TIMEOUT_PADRAO)
        except ValueError:
            timeout = TIMEOUT_PADRAO
        return cls(certificado,
                   url_sefin=os.environ.get("AUDITORIA_NFSE_SEFIN_URL") or URL_SEFIN_RESTRITA,
                   url_adn=os.environ.get("AUDITORIA_NFSE_ADN_URL") or URL_ADN_RESTRITA,
                   ca_extra=os.environ.get("AUDITORIA_NFSE_CA_EXTRA") or None,
                   timeout=max(1.0, min(timeout, 300.0)))

    # ------------------------------------------------------------------

    def _chamar(self, metodo: str, url: str, corpo: bytes | None = None
                ) -> tuple[int, bytes, str]:
        partes = urlsplit(url)
        conexao = http.client.HTTPSConnection(partes.hostname, partes.port or 443,
                                              context=self._contexto,
                                              timeout=self.timeout)
        try:
            try:
                conexao.connect()
            except (OSError, ssl.SSLError) as exc:
                raise _SemConexao(f"sem conexão segura com a Sefin: "
                                  f"{type(exc).__name__}") from None
            cabecalhos = {"Accept": "application/json"}
            if corpo is not None:
                cabecalhos["Content-Type"] = "application/json"
            try:
                conexao.request(metodo, partes.path or "/", body=corpo, headers=cabecalhos)
                resposta = conexao.getresponse()
                dado = resposta.read(MAX_RESPOSTA + 1)
            except (socket.timeout, TimeoutError):
                raise _Incerto("tempo esgotado esperando a Sefin") from None
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                raise _Incerto(f"conexão interrompida: {type(exc).__name__}") from None
            if len(dado) > MAX_RESPOSTA:
                raise _Incerto("resposta maior que o limite")
            return resposta.status, dado, resposta.getheader("Content-Type", "")
        finally:
            conexao.close()

    @staticmethod
    def _json(dado: bytes):
        try:
            return json.loads(dado.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None

    def enviar(self, xml_assinado: bytes) -> RespostaEnvio:
        try:
            raiz = etree.fromstring(xml_assinado, etree.XMLParser(
                no_network=True, resolve_entities=False, load_dtd=False))
        except etree.XMLSyntaxError as exc:
            raise nf.ErroNfse("XML_INVALIDO", f"XML malformado: {exc}") from None
        tp_amb = raiz.findtext("{http://www.sped.fazenda.gov.br/nfse}infDPS/"
                               "{http://www.sped.fazenda.gov.br/nfse}tpAmb")
        if tp_amb != "2":
            raise nf.ErroNfse(AMBIENTE_PROIBIDO,
                              "Só DPS de produção restrita (tpAmb 2) são transmitidas "
                              "nesta fase.")
        corpo = json.dumps({"dpsXmlGZipB64": base64.b64encode(
            gzip.compress(xml_assinado)).decode("ascii")}).encode("utf-8")
        try:
            status, dado, _ = self._chamar("POST", f"{self.url_sefin}/nfse", corpo)
        except _SemConexao as exc:
            return RespostaEnvio(SEM_CONEXAO, mensagem=str(exc))
        except _Incerto as exc:
            return RespostaEnvio(INCERTA, mensagem=str(exc))

        resposta = self._json(dado)
        if status == 201 and isinstance(resposta, dict):
            chave = str(_campo(resposta, "chaveacesso") or "")
            try:
                xml = _descompactar_b64(_campo(resposta, "nfsexmlgzipb64") or "")
            except (ValueError, zlib.error, EOFError):
                xml = b""
            if not re.fullmatch(r"\d{50}", chave) or not xml:
                return RespostaEnvio(INCERTA, http_status=201,
                                     mensagem="a Sefin respondeu 201 sem chave ou sem "
                                              "XML legíveis; consultar antes de reenviar")
            alertas = _campo(resposta, "alertas")
            return RespostaEnvio(
                AUTORIZADA, http_status=201, chave_acesso=chave, nfse_xml=xml,
                alertas=alertas if isinstance(alertas, list) else [],
                versao_aplicativo=_campo(resposta, "versaoaplicativo"),
                dh_processamento=_campo(resposta, "datahoraprocessamento"))
        if status == 400:
            erros = _erros(resposta) or [{"codigo": "", "complemento": "",
                                          "descricao": dado.decode("utf-8", "replace")[:1000]}]
            return RespostaEnvio(REJEITADA, http_status=400, erros=erros,
                                 mensagem="; ".join(f"{e['codigo']} {e['descricao']}".strip()
                                                    for e in erros)[:1000])
        if status == 403:
            return RespostaEnvio(CERTIFICADO_RECUSADO, http_status=403,
                                 mensagem="a Sefin recusou o certificado da transmissão")
        return RespostaEnvio(INCERTA, http_status=status,
                             mensagem=f"a Sefin respondeu HTTP {status}")

    def consultar_dps(self, id_dps: str) -> RespostaConsulta:
        if not re.fullmatch(r"DPS\d{42}", id_dps or ""):
            raise nf.ErroNfse(ID_INVALIDO, "Identificador de DPS fora do formato.")
        return self._consultar(f"{self.url_sefin}/dps/{id_dps}")

    def baixar_nfse(self, chave: str) -> RespostaConsulta:
        if not re.fullmatch(r"\d{50}", chave or ""):
            raise nf.ErroNfse(ID_INVALIDO, "Chave de acesso fora do formato.")
        return self._consultar(f"{self.url_sefin}/nfse/{chave}", com_xml=True)

    def _consultar(self, url: str, *, com_xml: bool = False) -> RespostaConsulta:
        try:
            status, dado, _ = self._chamar("GET", url)
        except _SemConexao as exc:
            return RespostaConsulta(SEM_CONEXAO, mensagem=str(exc))
        except _Incerto as exc:
            return RespostaConsulta(INCERTA, mensagem=str(exc))
        if status == 404:
            return RespostaConsulta(NAO_EXISTE, http_status=404)
        if status == 403:
            return RespostaConsulta(CERTIFICADO_RECUSADO, http_status=403,
                                    mensagem="a Sefin recusou o certificado da consulta")
        resposta = self._json(dado)
        if status != 200 or not isinstance(resposta, dict):
            return RespostaConsulta(INCERTA, http_status=status,
                                    mensagem=f"a Sefin respondeu HTTP {status}")
        chave = str(_campo(resposta, "chaveacesso") or "") or None
        if chave and not re.fullmatch(r"\d{50}", chave):
            chave = None
        xml = None
        if com_xml:
            try:
                xml = _descompactar_b64(_campo(resposta, "nfsexmlgzipb64") or "") or None
            except (ValueError, zlib.error, EOFError):
                xml = None
            if xml is None:
                return RespostaConsulta(INCERTA, http_status=200,
                                        mensagem="NFS-e sem XML legível na resposta")
        elif not chave:
            return RespostaConsulta(INCERTA, http_status=200,
                                    mensagem="consulta sem chave de acesso legível")
        return RespostaConsulta(EXISTE, http_status=200, chave_acesso=chave, xml=xml)

    def baixar_danfse(self, chave: str) -> bytes | None:
        """PDF da NFS-e. Tentativa: qualquer falha devolve None (research, R-5)."""
        if not re.fullmatch(r"\d{50}", chave or ""):
            return None
        try:
            status, dado, tipo = self._chamar("GET", f"{self.url_adn}/danfse/{chave}")
        except (_SemConexao, _Incerto):
            return None
        if status != 200 or not dado.startswith(b"%PDF"):
            return None
        return dado
