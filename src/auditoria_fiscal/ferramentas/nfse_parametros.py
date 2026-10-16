"""Perfil de emissao pelo certificado (spec 009).

Junta o que da para saber sem perguntar a ninguem:

- do proprio e-CNPJ, sem rede: CNPJ e razao social;
- da parametrizacao do ADN, com o certificado no mTLS: se o convenio do
  municipio esta ativo e a aliquota de cada codigo de servico na competencia.
  Retencoes do municipio entram so como aviso.

O resto do perfil (IM/CNC, regime do Simples, tributos aproximados, endereco
do tomador, serie, modelo, turmas) nao tem consulta por CNPJ na API e fica
manual. Nada aqui grava: devolve sugestoes para a tela preencher o formulario.

Destino: so o ADN (`adn.nfse.gov.br` ou `adn.producaorestrita.nfse.gov.br`,
ou loopback nos testes) e so GET. Producao e' o padrao porque os dados da
producao restrita sao de teste — e consultar parametro publico nao emite nada.
Caminhos e formatos: specs/009-nfse-perfil-pelo-certificado/spec.md.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from ..core import nfse as nf
from ..core.nfse_certificado import CertificadoA1
from . import nfse_sefin as sf

URL_PARAMETROS_PRODUCAO = "https://adn.nfse.gov.br/parametrizacao"
URL_PARAMETROS_RESTRITA = "https://adn.producaorestrita.nfse.gov.br/parametrizacao"
_HOSTS_ADN = {"adn.nfse.gov.br", "adn.producaorestrita.nfse.gov.br"}
TIMEOUT_PADRAO = 20.0

CODIGO_SERVICO_INVALIDO = "CODIGO_SERVICO_INVALIDO"
MUNICIPIO_INVALIDO = "MUNICIPIO_INVALIDO"

OK = "ok"
NAO_ENCONTRADO = "nao_encontrado"
FALHA = "falha"

FONTE_CERTIFICADO = "certificado"

# O que o perfil precisa e nenhuma consulta responde (spec 009).
MANUAIS = (
    "Inscrição municipal e se ela vai na DPS (registro no CNC, R5)",
    "Regime de apuração no Simples e regime especial (JB-8)",
    "Tributos aproximados (JB-8)",
    "ISS retido pelo tomador",
    "Endereço do tomador (JB-2)",
    "Série da DPS e modelo da discriminação",
    "Turmas e códigos (JB-3)",
)


@dataclass
class Consulta:
    resultado: str
    dados: dict | None = None
    mensagem: str = ""
    http_status: int | None = None


def _host_adn(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    if host in _HOSTS_ADN or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def conferir_destino(url: str) -> str:
    partes = urlsplit(url or "")
    if partes.scheme != "https" or not _host_adn(partes.hostname or ""):
        raise nf.ErroNfse(sf.DESTINO_PROIBIDO,
                          "A consulta de parâmetros só vai ao ADN do Sistema Nacional "
                          "(adn.nfse.gov.br ou adn.producaorestrita.nfse.gov.br); "
                          f"destino recusado: {partes.scheme}://{partes.hostname}.")
    return partes.hostname


def codigo_servico(c_trib_nac: str, complemento: str = "000") -> str:
    """`080101` -> `08.01.01.000`: o ADN so aceita o codigo completo com pontos."""
    digitos = re.sub(r"\D", "", c_trib_nac or "")
    if len(digitos) != 6 or not re.fullmatch(r"\d{3}", complemento or ""):
        raise nf.ErroNfse(CODIGO_SERVICO_INVALIDO,
                          f"Código de tributação nacional inválido: {c_trib_nac!r}.")
    return f"{digitos[:2]}.{digitos[2:4]}.{digitos[4:6]}.{complemento}"


def municipio_valido(codigo: str) -> str:
    codigo = (codigo or "").strip()
    if not re.fullmatch(r"\d{7}", codigo):
        raise nf.ErroNfse(MUNICIPIO_INVALIDO,
                          f"Código IBGE do município inválido: {codigo!r} (7 dígitos).")
    return codigo


def _mensagem(corpo) -> str:
    if isinstance(corpo, dict):
        texto = corpo.get("mensagem") or corpo.get("title") or ""
        erros = corpo.get("errors")
        if isinstance(erros, dict):
            texto += " " + "; ".join(f"{k}: {', '.join(map(str, v))}"
                                     for k, v in erros.items() if isinstance(v, list))
        return str(texto).strip()[:500]
    return ""


class ClienteParametros:
    """GET na parametrizacao do ADN, com o mesmo mTLS da transmissao."""

    def __init__(self, certificado: CertificadoA1, *, url: str = URL_PARAMETROS_PRODUCAO,
                 ca_extra: str | None = None, timeout: float = TIMEOUT_PADRAO):
        self.destino = conferir_destino(url)
        self.url = url.rstrip("/")
        self.timeout = float(timeout)
        self._contexto = sf._contexto_tls(certificado, ca_extra)

    @classmethod
    def do_ambiente(cls, certificado: CertificadoA1) -> "ClienteParametros":
        try:
            timeout = float(os.environ.get("AUDITORIA_NFSE_TIMEOUT") or TIMEOUT_PADRAO)
        except ValueError:
            timeout = TIMEOUT_PADRAO
        return cls(certificado,
                   url=os.environ.get("AUDITORIA_NFSE_PARAMETROS_URL") or URL_PARAMETROS_PRODUCAO,
                   ca_extra=os.environ.get("AUDITORIA_NFSE_CA_EXTRA") or None,
                   timeout=max(1.0, min(timeout, 60.0)))

    @property
    def ambiente(self) -> str:
        if self.destino == "adn.nfse.gov.br":
            return "produção"
        if self.destino == "adn.producaorestrita.nfse.gov.br":
            return "produção restrita (dados de teste)"
        return "teste local"

    def _get(self, caminho: str) -> Consulta:
        url = f"{self.url}/{caminho}"
        for tentativa in range(2):
            try:
                status, dado, _ = sf.chamar_https(self._contexto, self.timeout, "GET", url,
                                                  servico="o ADN")
                break
            except sf.SemConexao as exc:
                # O ADN as vezes derruba o primeiro aperto de mao; GET pode repetir.
                if tentativa == 0:
                    continue
                return Consulta(FALHA, mensagem=str(exc))
            except sf.Incerto as exc:
                return Consulta(FALHA, mensagem=str(exc))
        try:
            corpo = json.loads(dado.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            corpo = None
        if status == 200 and isinstance(corpo, dict):
            return Consulta(OK, dados=corpo, mensagem=_mensagem(corpo), http_status=200)
        if status == 404:
            return Consulta(NAO_ENCONTRADO, mensagem=_mensagem(corpo) or "não encontrado",
                            http_status=404)
        return Consulta(FALHA, mensagem=_mensagem(corpo) or f"o ADN respondeu HTTP {status}",
                        http_status=status)

    def convenio(self, municipio: str) -> Consulta:
        c = self._get(f"{municipio_valido(municipio)}/convenio")
        if c.resultado == OK:
            dados = c.dados.get("parametrosConvenio")
            if not isinstance(dados, dict):
                return Consulta(FALHA, mensagem="convênio sem parametrosConvenio",
                                http_status=200)
            c.dados = dados
        return c

    def aliquota(self, municipio: str, c_trib_nac: str, competencia: dt.date) -> Consulta:
        codigo = codigo_servico(c_trib_nac)
        c = self._get(f"{municipio_valido(municipio)}/{codigo}/{competencia.isoformat()}/aliquota")
        if c.resultado != OK:
            c.dados = None
            return c
        lista = ((c.dados or {}).get("aliquotas") or {}).get(codigo) or []
        valor = _aliquota_vigente(lista, competencia)
        if valor is None:
            return Consulta(NAO_ENCONTRADO, mensagem="sem alíquota vigente na competência",
                            http_status=200)
        return Consulta(OK, dados={"codigo": codigo, "aliquota": valor}, http_status=200)

    def retencoes(self, municipio: str, competencia: dt.date) -> Consulta:
        return self._get(f"{municipio_valido(municipio)}/{competencia.isoformat()}/retencoes")


def _aliquota_vigente(lista: list, competencia: dt.date) -> Decimal | None:
    alvo = competencia.isoformat()
    for item in lista:
        if not isinstance(item, dict):
            continue
        inicio = str(item.get("DtIni") or "")[:10]
        fim = item.get("DtFim")
        if inicio and inicio > alvo:
            continue
        if fim and str(fim)[:10] < alvo:
            continue
        try:
            return Decimal(str(item.get("Aliq"))).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None
    return None


def _codigos_completos(valor) -> set[str]:
    """Todo `codigoCompleto` dentro da resposta de retencoes, onde estiver: o
    formato completo nao e' documentado, entao a busca nao depende dele."""
    achados: set[str] = set()
    if isinstance(valor, dict):
        for chave, item in valor.items():
            if chave == "codigoCompleto" and isinstance(item, str):
                achados.add(item)
            else:
                achados |= _codigos_completos(item)
    elif isinstance(valor, list):
        for item in valor:
            achados |= _codigos_completos(item)
    return achados


def _cnpj_formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def sugerir_perfil(cliente: ClienteParametros, certificado: CertificadoA1, *,
                   municipio: str, c_trib_nacs: list[str],
                   competencia: dt.date) -> dict:
    """Sugestoes para o formulario do perfil, cada uma com a fonte.

    Uma consulta que falha vira aviso; o que veio do certificado vale sempre."""
    municipio = municipio_valido(municipio)
    fonte_adn = f"ADN — parametrização ({cliente.ambiente})"
    campos: dict[str, dict] = {}
    avisos: list[str] = []
    consultas: list[dict] = []

    agora = dt.datetime.now(dt.timezone.utc)
    if agora > certificado.valido_ate:
        avisos.append(f"O certificado venceu em {certificado.valido_ate:%d/%m/%Y}: serve "
                      "para ler o CNPJ, mas o Sistema Nacional recusa a conexão.")
    if certificado.cnpj:
        campos["cnpj"] = {"valor": _cnpj_formatado(certificado.cnpj),
                          "fonte": FONTE_CERTIFICADO}
    if certificado.razao_social:
        campos["razao_social"] = {"valor": certificado.razao_social,
                                  "fonte": FONTE_CERTIFICADO}

    c = cliente.convenio(municipio)
    consultas.append({"o_que": f"Convênio do município {municipio}",
                      "resultado": c.resultado, "mensagem": c.mensagem})
    if c.resultado == OK:
        ativo = c.dados.get("aderenteAmbienteNacional") == 1
        campos["convenio_incidencia_ativo"] = {"valor": ativo, "fonte": fonte_adn}
        if not ativo:
            avisos.append(f"O município {municipio} aparece sem adesão ao ambiente "
                          "nacional no convênio.")
    elif c.resultado == NAO_ENCONTRADO:
        campos["convenio_incidencia_ativo"] = {"valor": False, "fonte": fonte_adn}
        avisos.append(f"Convênio: {c.mensagem}")
    else:
        avisos.append(f"Não foi possível consultar o convênio: {c.mensagem}")

    codigos = []
    for c_trib in c_trib_nacs or ["080101"]:
        try:
            codigos.append(codigo_servico(c_trib))
        except nf.ErroNfse:
            avisos.append(f"Código de serviço ignorado (inválido): {c_trib!r}.")
    codigos = sorted(set(codigos))
    aliquotas: dict[str, Decimal] = {}
    for codigo in codigos:
        a = cliente.aliquota(municipio, codigo.replace(".", "")[:6], competencia)
        consultas.append({"o_que": f"Alíquota {codigo} em {competencia:%m/%Y}",
                          "resultado": a.resultado, "mensagem": a.mensagem})
        if a.resultado == OK:
            aliquotas[codigo] = a.dados["aliquota"]
        else:
            avisos.append(f"Alíquota de {codigo}: {a.mensagem or a.resultado}.")
    if aliquotas and len(set(aliquotas.values())) == 1 and len(aliquotas) == len(codigos):
        valor = next(iter(aliquotas.values()))
        campos["aliquota"] = {"valor": f"{valor:.2f}".replace(".", ","),
                              "fonte": f"{fonte_adn} — {', '.join(codigos)} em "
                                       f"{competencia:%m/%Y}"}
    elif len(set(aliquotas.values())) > 1:
        avisos.append("Os códigos das turmas têm alíquotas diferentes no município ("
                      + "; ".join(f"{k}: {v:.2f}%" for k, v in sorted(aliquotas.items()))
                      + "); o perfil tem uma alíquota só — escolha à mão.")

    r = cliente.retencoes(municipio, competencia)
    consultas.append({"o_que": f"Retenções do município em {competencia:%m/%Y}",
                      "resultado": r.resultado, "mensagem": r.mensagem})
    if r.resultado == OK:
        com_retencao = sorted(_codigos_completos(r.dados) & set(codigos))
        for codigo in com_retencao:
            avisos.append(f"O município define retenção de ISS para {codigo}. Para "
                          "tomador pessoa física costuma não se aplicar; confira com o "
                          "contador o campo \"ISS retido\".")
    elif r.resultado == FALHA:
        avisos.append(f"Não foi possível consultar as retenções: {r.mensagem}")

    return {"certificado": certificado.resumo(), "campos": campos, "avisos": avisos,
            "consultas": consultas, "manuais": list(MANUAIS),
            "ambiente": cliente.ambiente, "municipio": municipio,
            "competencia": competencia.isoformat()}
