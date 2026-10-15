"""Geracao da DPS do padrao nacional, leiaute v1.01, SEM envio (spec 006).

Monta o XML de uma Declaracao de Prestacao de Servico a partir da versao do
perfil e de uma linha conferida, e valida contra o XSD oficial versionado em
`dados/nfse/xsd/v1.01`. Nao assina, nao le certificado e nao abre conexao: a
transmissao e' da Fase 2.

Decisoes (specs/006-emissao-nfse/research.md):

- Ambiente sempre 2 (producao restrita) na Fase 1.
- O XML sai deterministico: o gerador nao le relogio; `dh_emi` entra como
  parametro e fica gravado. Mesma entrada, mesmos bytes.
- O XSD oficial nao e' editado. O padrao de `TSSerieDPS` usa `^` e `$`, que
  no XML Schema sao caracteres comuns, e o libxml2 recusaria toda serie
  valida; o validador troca so esse padrao, em memoria.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import threading
from dataclasses import dataclass

from lxml import etree

from . import nfse as nf

VERSAO_LEIAUTE = "1.01"
VERSAO_GERADOR = "1"
VER_APLIC = "auditoriaJB-nfse-1"
NS = "http://www.sped.fazenda.gov.br/nfse"
AMBIENTE_PRODUCAO_RESTRITA = 2
TIPO_INSCRICAO_CNPJ = "2"
FUSO_SALVADOR = dt.timezone(dt.timedelta(hours=-3))

DPS_INVALIDA = "DPS_INVALIDA"
LINHA_COM_BLOQUEIO = "LINHA_COM_BLOQUEIO"
NUMERO_INVALIDO = "NUMERO_INVALIDO"
DATA_SEM_FUSO = "DATA_SEM_FUSO"

PADRAO_SERIE_OFICIAL = r"^0{0,4}\d{1,5}$"
PADRAO_SERIE_CORRIGIDO = r"0{0,4}\d{1,5}"
_ARQUIVO_TIPOS_SIMPLES = "tiposSimples_v1.01.xsd"


def pasta_xsd() -> str:
    """`dados/nfse/xsd/v1.01` na raiz do projeto (ou `AUDITORIA_NFSE_XSD`)."""
    pasta = os.environ.get("AUDITORIA_NFSE_XSD")
    if pasta:
        return pasta
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.path.join(raiz, "dados", "nfse", "xsd", "v1.01")


# ----------------------------------------------------------------------
# Dados de uma nota


@dataclass(frozen=True)
class DadosNota:
    cpf: str
    nome: str
    endereco: dict | None
    turma: nf.Turma
    discriminacao: str
    valor_centavos: int
    competencia: str


@dataclass(frozen=True)
class DpsGerada:
    id_dps: str
    serie: str
    numero: int
    dh_emi: str
    d_compet: str
    xml: bytes
    sha256: str
    versao_leiaute: str = VERSAO_LEIAUTE
    versao_gerador: str = VERSAO_GERADOR


def dados_da_linha(linha) -> DadosNota:
    """Linha conferida -> dados da nota. Linha com bloqueio nao vira DPS."""
    if linha.excluida or linha.situacao == "bloqueio" or any(
            a.nivel == nf.BLOQUEIO for a in linha.apontamentos):
        raise nf.ErroNfse(LINHA_COM_BLOQUEIO,
                          f"A linha {linha.ref} tem bloqueio ou foi excluída.")
    faltando = [nome for nome, valor in (
        ("CPF", linha.cpf), ("nome do responsável", linha.responsavel),
        ("turma", linha.turma), ("discriminação", linha.discriminacao),
        ("valor", linha.valor_centavos), ("competência", linha.competencia))
        if not valor]
    if faltando:
        raise nf.ErroNfse(LINHA_COM_BLOQUEIO,
                          f"A linha {linha.ref} não tem: {', '.join(faltando)}.")
    return DadosNota(cpf=linha.cpf, nome=linha.responsavel, endereco=linha.endereco,
                     turma=linha.turma, discriminacao=linha.discriminacao,
                     valor_centavos=linha.valor_centavos,
                     competencia=linha.competencia)


# ----------------------------------------------------------------------
# Montagem


def _sub(pai, nome: str, texto: str | None = None):
    elemento = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        elemento.text = texto
    return elemento


def montar_dps(perfil: nf.PerfilVersao, nota: DadosNota, *, numero: int,
               dh_emi: dt.datetime) -> DpsGerada:
    """Monta e valida a DPS. Qualquer problema levanta `ErroNfse`; nunca
    devolve XML invalido."""
    pendencias = nf.pendencias_do_perfil(perfil)
    if pendencias:
        raise nf.ErroNfse(nf.PERFIL_COM_PENDENCIA,
                          "O perfil tem pendências: " + "; ".join(
                              f"{p.campo} ({p.origem})" for p in pendencias))
    if nf.turma_pendente(nota.turma):
        raise nf.ErroNfse(nf.TURMA_PENDENTE,
                          f"A turma {nota.turma.nome!r} está sem código.")
    if not isinstance(numero, int) or not 1 <= numero < 10 ** 15:
        raise nf.ErroNfse(NUMERO_INVALIDO, f"Número de DPS inválido: {numero!r}.")
    if dh_emi.tzinfo is None:
        raise nf.ErroNfse(DATA_SEM_FUSO, "A data de emissão precisa de fuso.")
    local = dh_emi.astimezone(FUSO_SALVADOR)
    d_compet = nf.primeiro_dia(nota.competencia)
    if d_compet > local.date():
        raise nf.ErroNfse(nf.COMPETENCIA_FUTURA,
                          "A competência não pode ser posterior à data de "
                          "emissão (E0015).")
    regra = nf.regra_aliquota(perfil)
    serie = perfil.serie_dps
    id_dps = (f"DPS{perfil.municipio_ibge}{TIPO_INSCRICAO_CNPJ}{perfil.cnpj}"
              f"{int(serie):05d}{numero:015d}")
    dh_texto = local.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"

    dps = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS})
    dps.set("versao", VERSAO_LEIAUTE)
    inf = _sub(dps, "infDPS")
    inf.set("Id", id_dps)
    _sub(inf, "tpAmb", str(AMBIENTE_PRODUCAO_RESTRITA))
    _sub(inf, "dhEmi", dh_texto)
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "serie", serie)
    _sub(inf, "nDPS", str(numero))
    _sub(inf, "dCompet", d_compet.isoformat())
    _sub(inf, "tpEmit", "1")
    _sub(inf, "cLocEmi", perfil.municipio_ibge)

    prest = _sub(inf, "prest")
    _sub(prest, "CNPJ", perfil.cnpj)
    if perfil.informar_im:
        _sub(prest, "IM", perfil.inscricao_municipal)
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", str(perfil.op_simp_nac))
    _sub(reg, "regApTribSN", str(perfil.reg_ap_trib_sn))
    _sub(reg, "regEspTrib", str(perfil.reg_esp_trib))

    toma = _sub(inf, "toma")
    _sub(toma, "CPF", nota.cpf)
    _sub(toma, "xNome", nota.nome)
    if nota.endereco:
        end = _sub(toma, "end")
        nac = _sub(end, "endNac")
        _sub(nac, "cMun", nota.endereco["cMun"])
        _sub(nac, "CEP", nota.endereco["CEP"])
        _sub(end, "xLgr", nota.endereco["xLgr"])
        _sub(end, "nro", nota.endereco["nro"])
        if nota.endereco.get("xCpl"):
            _sub(end, "xCpl", nota.endereco["xCpl"])
        _sub(end, "xBairro", nota.endereco["xBairro"])

    serv = _sub(inf, "serv")
    _sub(_sub(serv, "locPrest"), "cLocPrestacao", perfil.municipio_prestacao_ibge)
    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", nota.turma.c_trib_nac)
    _sub(cserv, "xDescServ", nota.discriminacao)
    _sub(cserv, "cNBS", nota.turma.c_nbs)

    valores = _sub(inf, "valores")
    _sub(_sub(valores, "vServPrest"), "vServ", nf.centavos_em_texto(nota.valor_centavos))
    trib = _sub(valores, "trib")
    mun = _sub(trib, "tribMun")
    _sub(mun, "tribISSQN", "1")
    _sub(mun, "tpRetISSQN", "2" if perfil.iss_retido else "1")
    if regra == nf.ALIQ_INFORMAR:
        _sub(mun, "pAliq", nf.centavos_em_texto(perfil.aliquota_centesimos))
    tot = _sub(trib, "totTrib")
    if perfil.tributos_aprox == nf.TRIB_PTOTTRIBSN:
        _sub(tot, "pTotTribSN", nf.centavos_em_texto(perfil.p_tot_trib_sn))
    else:
        grupo = _sub(tot, "pTotTrib")
        _sub(grupo, "pTotTribFed", nf.centavos_em_texto(perfil.p_tot_trib_fed))
        _sub(grupo, "pTotTribEst", nf.centavos_em_texto(perfil.p_tot_trib_est))
        _sub(grupo, "pTotTribMun", nf.centavos_em_texto(perfil.p_tot_trib_mun))

    xml = etree.tostring(dps, xml_declaration=True, encoding="UTF-8")
    garantir_valida(xml)
    return DpsGerada(id_dps=id_dps, serie=serie, numero=numero, dh_emi=dh_texto,
                     d_compet=d_compet.isoformat(), xml=xml,
                     sha256=hashlib.sha256(xml).hexdigest())


# ----------------------------------------------------------------------
# Validacao no XSD oficial

_esquema = None
_trava = threading.Lock()


def padrao_serie_no_xsd_oficial() -> str | None:
    """O padrao de `TSSerieDPS` como esta no arquivo oficial (para o teste
    que avisa quando o governo corrigir o XSD)."""
    arvore = etree.parse(os.path.join(pasta_xsd(), _ARQUIVO_TIPOS_SIMPLES),
                         etree.XMLParser(no_network=True, resolve_entities=False))
    xs = "{http://www.w3.org/2001/XMLSchema}"
    for tipo in arvore.getroot().iter(f"{xs}simpleType"):
        if tipo.get("name") == "TSSerieDPS":
            padrao = tipo.find(f".//{xs}pattern")
            return padrao.get("value") if padrao is not None else None
    return None


class _Resolvedor(etree.Resolver):
    """So arquivos da pasta do XSD; o de tipos simples com a serie corrigida."""

    def __init__(self, pasta: str):
        super().__init__()
        self.pasta = pasta

    def resolve(self, url, pubid, context):
        nome = os.path.basename(url or "")
        caminho = os.path.join(self.pasta, nome)
        if not os.path.isfile(caminho):
            return None
        if nome == _ARQUIVO_TIPOS_SIMPLES:
            with open(caminho, "rb") as arq:
                dado = arq.read()
            velho = f'value="{PADRAO_SERIE_OFICIAL}"'.encode()
            dado = dado.replace(velho, f'value="{PADRAO_SERIE_CORRIGIDO}"'.encode(), 1)
            return self.resolve_string(dado, context, base_url=caminho)
        return self.resolve_filename(caminho, context)


def _carregar_esquema():
    global _esquema
    with _trava:
        if _esquema is None:
            pasta = pasta_xsd()
            parser = etree.XMLParser(no_network=True, resolve_entities=False)
            parser.resolvers.add(_Resolvedor(pasta))
            principal = os.path.join(pasta, "DPS_v1.01.xsd")
            with open(principal, "rb") as arq:
                documento = etree.parse(arq, parser, base_url=principal)
            _esquema = etree.XMLSchema(documento)
        return _esquema


def validar_xsd(xml: bytes) -> list[str]:
    """Erros de validacao no XSD oficial; lista vazia = valida."""
    esquema = _carregar_esquema()
    try:
        documento = etree.fromstring(
            xml, etree.XMLParser(no_network=True, resolve_entities=False))
    except etree.XMLSyntaxError as exc:
        return [f"XML malformado: {exc}"]
    with _trava:
        if esquema.validate(documento):
            return []
        return [f"linha {e.line}: {e.message}" for e in esquema.error_log]


def garantir_valida(xml: bytes) -> None:
    erros = validar_xsd(xml)
    if erros:
        raise nf.ErroNfse(DPS_INVALIDA,
                          "A DPS não passou no XSD oficial: " + "; ".join(erros[:5]))
