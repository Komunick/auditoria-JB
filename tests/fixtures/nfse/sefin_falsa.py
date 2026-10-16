"""Sefin Nacional FALSA para os testes da Fase 2 (spec 008).

Servidor HTTPS em 127.0.0.1 (porta efemera, so durante o teste) que EXIGE
certificado de cliente da AC de teste, como a Sefin exige o e-CNPJ no mTLS.
Implementa o que a transmissao usa:

    POST /SefinNacional/nfse            recebe {"dpsXmlGZipB64"}; confere a
                                        assinatura, o tpAmb, o CNPJ e a
                                        duplicidade (E0014)
    GET  /SefinNacional/dps/{id}        chave de acesso da DPS ja emitida
    GET  /SefinNacional/nfse/{chave}    XML da NFS-e
    GET  /danfse/{chave}                PDF (pode ser desligado)
    GET  /parametrizacao/...            parametros municipais do ADN (spec 009):
                                        convenio, aliquota e retencoes, nos
                                        formatos conferidos no servico real

`programar(...)` enfileira comportamentos para os proximos POST: "500",
"403", ("400", codigo, descricao), "emitir_e_500" (gera a nota e responde
500) e "emitir_e_demorar" (gera a nota e demora mais que o cliente espera).
"""

from __future__ import annotations

import base64
import gzip
import json
import re
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography import x509
from lxml import etree

from auditoria_fiscal.core import nfse as nf
from auditoria_fiscal.core import nfse_assinatura as na
from auditoria_fiscal.core import nfse_certificado as nc

NS = "{http://www.sped.fazenda.gov.br/nfse}"


class SefinFalsa:
    def __init__(self, kit, *, atraso: float = 3.0):
        self.kit = kit
        self.atraso = atraso
        self.programado: list = []
        self.posts: list[str] = []          # idDps de cada POST recebido
        self.emitidas: dict[str, str] = {}  # idDps -> chave
        self.nfse: dict[str, bytes] = {}    # chave -> XML
        self.cnpjs_conexao: list[str | None] = []
        self.danfse_disponivel = True
        self.consultas: list[str] = []
        # Parametrizacao (ADN). Municipio fora de `convenios` = sem convenio ativo.
        self.convenios: dict[str, dict] = {"2927408": {
            "aderenteAmbienteNacional": 1, "aderenteEmissorNacional": 1,
            "situacaoEmissaoPadraoContribuintesRFB": 1, "aderenteMAN": 0,
            "permiteAproveitametoDeCreditos": True}}
        self.aliquotas: dict[tuple[str, str], list[dict]] = {
            ("2927408", "08.01.01.000"): [
                {"Incidencia": "SIM", "Aliq": 2.00, "DtIni": "2020-01-01T00:00:00",
                 "DtFim": "2022-12-31T00:00:00"},
                {"Incidencia": "SIM", "Aliq": 5.00, "DtIni": "2023-01-01T00:00:00",
                 "DtFim": None}]}
        self.retencoes: dict[str, dict] = {"2927408": {
            "retencoesMunicipais": [{"descricao": "Retenção na fonte",
                                     "dataInicioVigencia": "2023-01-01T00:00:00",
                                     "tiposRetencao": [2],
                                     "servicos": [{"codigoCompleto": "07.02.01.000"}]}]}}
        self.parametros_fora_do_ar = False
        self.caminhos_parametros: list[str] = []
        self._contador = 0
        self._trava = threading.Lock()
        self._servidor = None

    # ------------------------------------------------------------------

    def programar(self, *comportamentos) -> None:
        self.programado.extend(comportamentos)

    def iniciar(self) -> str:
        sefin = self

        class Handler(_Handler):
            falsa = sefin

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.load_cert_chain(self.kit.servidor_pem, self.kit.servidor_chave)
        contexto.verify_mode = ssl.CERT_REQUIRED
        contexto.load_verify_locations(self.kit.ca_pem)
        servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
        self._servidor = servidor
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        return f"https://127.0.0.1:{servidor.server_address[1]}"

    def parar(self) -> None:
        if self._servidor:
            self._servidor.shutdown()
            self._servidor.server_close()

    # ------------------------------------------------------------------

    def _emitir(self, id_dps: str, xml_dps: bytes) -> str:
        with self._trava:
            self._contador += 1
            chave = f"{29274082}{id_dps[11:25]}{self._contador:026d}"[:50].ljust(50, "0")
            interno = etree.tostring(etree.fromstring(xml_dps))
            self.nfse[chave] = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
                f'<infNFSe Id="NFS{chave}"><nNFSe>{self._contador}</nNFSe>'
            ).encode() + interno + b"</infNFSe></NFSe>"
            self.emitidas[id_dps] = chave
            return chave


def _b64gz(dado: bytes) -> str:
    return base64.b64encode(gzip.compress(dado)).decode("ascii")


class _Handler(BaseHTTPRequestHandler):
    falsa: SefinFalsa
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _responder(self, status: int, corpo=None, tipo="application/json") -> None:
        dado = b""
        if corpo is not None:
            dado = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dado)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(dado)

    def _cnpj_conexao(self) -> str | None:
        der = self.connection.getpeercert(binary_form=True)
        return nc.cnpj_do_certificado(x509.load_der_x509_certificate(der)) if der else None

    def _erro(self, status: int, codigo: str, descricao: str) -> None:
        self._responder(status, {"erros": [{"codigo": codigo, "descricao": descricao,
                                             "complemento": ""}]})

    def _sucesso(self, id_dps: str, chave: str) -> None:
        self._responder(201, {
            "tipoAmbiente": 2, "versaoAplicativo": "SefinFalsa-1",
            "dataHoraProcessamento": time.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
            "idDps": id_dps, "chaveAcesso": chave,
            "nfseXmlGZipB64": _b64gz(self.falsa.nfse[chave]), "alertas": []})

    def do_POST(self):
        falsa = self.falsa
        falsa.cnpjs_conexao.append(self._cnpj_conexao())
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho)
        if self.path != "/SefinNacional/nfse":
            return self._responder(404, {"erro": "rota"})
        try:
            pedido = json.loads(corpo)
            xml = gzip.decompress(base64.b64decode(pedido["dpsXmlGZipB64"]))
            raiz = etree.fromstring(xml)
            inf = raiz.find(f"{NS}infDPS")
            id_dps = inf.get("Id")
        except Exception:  # noqa: BLE001
            return self._erro(400, "E1235", "Falha no esquema XML da DPS.")
        falsa.posts.append(id_dps)

        programado = falsa.programado.pop(0) if falsa.programado else None
        if programado == "500":
            return self._responder(500, {"erro": "falha interna"})
        if programado == "403":
            return self._responder(403, {"erro": "certificado"})
        if isinstance(programado, tuple) and programado[0] == "400":
            return self._erro(400, programado[1], programado[2])

        try:
            info = na.conferir_assinatura(xml)
        except nf.ErroNfse:
            return self._erro(400, "E0714", "Arquivo enviado com erro na assinatura.")
        cnpj_prest = inf.findtext(f"{NS}prest/{NS}CNPJ")
        if info["cnpj"] != cnpj_prest:
            return self._erro(400, "E0718", "A assinatura deve ser feita com o "
                                            "certificado digital do emitente da DPS.")
        if inf.findtext(f"{NS}tpAmb") != "2":
            return self._erro(400, "E0003", "Ambiente diferente de produção restrita.")
        if id_dps in falsa.emitidas:
            return self._erro(400, "E0014", "Conjunto de Série, Número, Código do "
                                            "Município Emissor e CNPJ/CPF já existe.")
        chave = falsa._emitir(id_dps, xml)
        if programado == "emitir_e_500":
            return self._responder(500, {"erro": "falha depois de gerar"})
        if programado == "emitir_e_demorar":
            time.sleep(falsa.atraso)
        return self._sucesso(id_dps, chave)

    def _parametrizacao(self) -> None:
        falsa = self.falsa
        falsa.caminhos_parametros.append(self.path)
        if falsa.parametros_fora_do_ar:
            return self._responder(500, {"mensagem": "falha interna"})
        partes = self.path.split("/")[2:]          # depois de /parametrizacao/
        if len(partes) == 2 and partes[1] == "convenio":
            dados = falsa.convenios.get(partes[0])
            if dados is None:
                return self._responder(404, {
                    "parametrosConvenio": None,
                    "mensagem": f"O convênio do município <{partes[0]}> ainda não "
                                "está ativo no Sistema Nacional NFS-e."})
            return self._responder(200, {"parametrosConvenio": dados, "mensagem":
                                         "Parâmetros do convênio recuperados com sucesso."})
        if len(partes) == 4 and partes[3] == "aliquota":
            municipio, codigo, competencia = partes[:3]
            if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{3}", codigo):
                return self._responder(400, {
                    "aliquotas": None, "mensagem": "Chamada mal formada. O código do "
                                                  "serviço deve ser composto por nove dígitos."})
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", competencia):
                return self._responder(400, {
                    "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
                    "title": "One or more validation errors occurred.", "status": 400,
                    "errors": {"competencia": [f"The value '{competencia}' is not valid."]}})
            lista = falsa.aliquotas.get((municipio, codigo))
            if not lista:
                return self._responder(404, {"aliquotas": None,
                                             "mensagem": "Alíquota não encontrada."})
            vigentes = [a for a in lista if a["DtIni"][:10] <= competencia
                        and (a["DtFim"] is None or a["DtFim"][:10] >= competencia)]
            return self._responder(200, {"aliquotas": {codigo: vigentes},
                                         "mensagem": "Alíquotas recuperadas com sucesso."})
        if len(partes) == 3 and partes[2] == "retencoes":
            dados = falsa.retencoes.get(partes[0])
            if dados is None:
                return self._responder(404, {"retencoes": None,
                                             "mensagem": "Sem retenções parametrizadas."})
            return self._responder(200, {"retencoes": dados,
                                         "mensagem": "Retenções recuperadas com sucesso."})
        return self._responder(404, {"mensagem": "rota"})

    def do_GET(self):
        falsa = self.falsa
        falsa.cnpjs_conexao.append(self._cnpj_conexao())
        if self.path.startswith("/parametrizacao/"):
            return self._parametrizacao()
        achado = re.fullmatch(r"/SefinNacional/dps/(DPS\d{42})", self.path)
        if achado:
            falsa.consultas.append(achado.group(1))
            chave = falsa.emitidas.get(achado.group(1))
            if not chave:
                return self._responder(404, {"erro": "DPS não encontrada"})
            return self._responder(200, {"tipoAmbiente": 2, "idDps": achado.group(1),
                                         "chaveAcesso": chave})
        achado = re.fullmatch(r"/SefinNacional/nfse/(\d{50})", self.path)
        if achado:
            xml = falsa.nfse.get(achado.group(1))
            if xml is None:
                return self._responder(404, {"erro": "NFS-e não encontrada"})
            return self._responder(200, {"chaveAcesso": achado.group(1),
                                         "nfseXmlGZipB64": _b64gz(xml)})
        achado = re.fullmatch(r"/danfse/(\d{50})", self.path)
        if achado:
            if not falsa.danfse_disponivel or achado.group(1) not in falsa.nfse:
                return self._responder(501, {"erro": "indisponível"})
            return self._responder(200, b"%PDF-1.4\n% DANFSe falso\n", "application/pdf")
        return self._responder(404, {"erro": "rota"})

    do_HEAD = do_GET
