"""Perfil de emissao pela nota ja emitida (spec 009, Parte 2).

Le o XML de NFS-e que a escola ja emitiu e devolve sugestoes para o
formulario do perfil, cada uma com a fonte:

- Nota Salvador, leiaute ABRASF versao 1 (`InfNfse` em qualquer raiz, com ou
  sem namespace; aliquota em fracao, como no provedor de Salvador);
- NFS-e nacional (`NFSe/infNFSe/DPS/infDPS`), a que a escola emite a partir
  de 01/11/2026 e a que o ADN devolve.

Nucleo puro: sem FastAPI, sem banco, sem rede e nada gravado. CPF e nome do
tomador e o texto da discriminacao ficam so aqui dentro, para montar o modelo:
o resultado leva os campos do prestador, os codigos e o modelo ja sem nomes.
Regras e fontes: specs/009-nfse-perfil-pelo-certificado/spec.md (Parte 2).
"""

from __future__ import annotations

import io
import json
import os
import re
import unicodedata
import zipfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from lxml import etree

from . import documentos_br
from . import nfse as nf

MAX_ARQUIVO_BYTES = 5 * 1024 * 1024
MAX_XMLS_ZIP = 1000
MAX_DESCOMPACTADO = 20 * 1024 * 1024
MAX_NOTAS = 1000
MAX_TURMAS_SUGERIDAS = 20

NOTA_ILEGIVEL = "NOTA_ILEGIVEL"
NOTA_GRANDE_DEMAIS = "NOTA_GRANDE_DEMAIS"
NOTA_SEM_NFSE = "NOTA_SEM_NFSE"
NOTA_DE_OUTRO_CNPJ = "NOTA_DE_OUTRO_CNPJ"

LEIAUTE_ABRASF = "abrasf_v1"
LEIAUTE_NACIONAL = "nacional"
SALVADOR = "2927408"

OPT_ME_EPP = "me_epp"
OPT_MEI = "mei"
OPT_NAO = "nao_optante"

CODIGOS_TURMA = ("c_trib_nac", "c_nbs", "c_ind_op", "c_class_trib",
                 "ref_cnae", "ref_item_lista", "ref_ctiss")

# ABRASF v1 `RegimeEspecialTributacao` -> `regEspTrib` nacional. 5 (MEI) nao
# e' regime especial no nacional: vira aviso. Ausente com optante = nenhum.
_REGIME_ABRASF = {"1": 3, "2": 2, "3": 6, "4": 1, "6": 0}
_OP_SIMP_NAC = {"1": OPT_NAO, "2": OPT_MEI, "3": OPT_ME_EPP}

# Subitem com mais de um desdobro nacional e regra pelo CNAE. So o 08.01,
# pelas descricoes do Anexo B: 080101 "pre-escolar, fundamental e medio",
# 080102 "superior"; CNAE 85.1 e 85.2 x 85.3.
_DESDOBRO_POR_CNAE = {"0801": (("851", "080101"), ("852", "080101"),
                               ("853", "080102"))}

# Nomes provaveis das tags da reforma no XML municipal (o leiaute ABRASF v1
# nao tem); no nacional sao os do leiaute.
_NOMES_NBS = {"cNBS", "CodigoNbs", "CodigoNBS", "Nbs", "NBS", "CodigoNbsServico"}
_NOMES_IND_OP = {"cIndOp", "CodigoIndicadorOperacao", "IndicadorOperacao", "IndOp",
                 "CodigoIndOp"}
_NOMES_CLASS_TRIB = {"cClassTrib", "CClassTrib", "ClassTrib", "ClassificacaoTributaria",
                     "CodigoClassificacaoTributaria"}

_MANUAIS = (
    ("informar_im", "Se a inscrição municipal vai na DPS (registro no CNC, R5)"),
    ("reg_ap_trib_sn", "Regime de apuração no Simples (JB-8)"),
    ("tributos_aprox", "Tributos aproximados (JB-8)"),
    ("convenio_incidencia_ativo", "Convênio do município ativo (use o certificado, acima)"),
    ("endereco_tomador", "Endereço do tomador (JB-2)"),
    ("serie_dps", "Série da DPS"),
    ("turmas", "Nome e apelidos das turmas (JB-3)"),
)


def _erro(codigo: str, mensagem: str) -> nf.ErroNfse:
    return nf.ErroNfse(codigo, mensagem)


# ----------------------------------------------------------------------
# Nota lida (campos pessoais fora do repr, para nao vazar em mensagem)


@dataclass
class NotaLida:
    leiaute: str
    numero: str = "?"
    competencia: str | None = None
    cnpj: str | None = None
    razao_social: str | None = None
    inscricao_municipal: str | None = None
    im_na_dps: bool | None = None
    municipio_ibge: str | None = None
    municipio_prestacao_ibge: str | None = None
    optante: str | None = None
    reg_ap_trib_sn: int | None = None
    reg_esp_trib: int | None = None
    iss_retido: bool | None = None
    aliquota: Decimal | None = None
    aliquota_aplicada: bool = False
    tributos_aprox: str | None = None
    p_tot: dict = field(default_factory=dict)
    servico: dict = field(default_factory=dict)
    opcoes_c_trib: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    ambiente: int | None = None
    discriminacao: str = field(default="", repr=False)
    tomador: str | None = field(default=None, repr=False)
    tomador_doc: str | None = field(default=None, repr=False)

    @property
    def rotulo(self) -> str:
        if self.leiaute == LEIAUTE_NACIONAL:
            return "NFS-e nacional"
        if self.municipio_ibge == SALVADOR:
            return "Nota Salvador"
        return "NFS-e municipal (ABRASF v1)"


# ----------------------------------------------------------------------
# Leitura do arquivo


def ler_arquivo(dados: bytes) -> list[NotaLida]:
    """XML (uma ou varias NFS-e) ou `.zip` de XMLs -> notas lidas."""
    if not dados:
        raise _erro(NOTA_ILEGIVEL, "O arquivo está vazio.")
    if len(dados) > MAX_ARQUIVO_BYTES:
        raise _erro(NOTA_GRANDE_DEMAIS, f"O arquivo passa de "
                                        f"{MAX_ARQUIVO_BYTES // (1024 * 1024)} MB.")
    if dados[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        xmls = _xmls_do_zip(dados)
    else:
        xmls = [("O arquivo", dados)]
    notas: list[NotaLida] = []
    for nome, xml in xmls:
        notas.extend(_notas_do_xml(xml, nome))
        if len(notas) > MAX_NOTAS:
            raise _erro(NOTA_GRANDE_DEMAIS, f"O arquivo tem mais de {MAX_NOTAS} notas; "
                                            "envie só algumas.")
    if not notas:
        raise _erro(NOTA_SEM_NFSE, "O arquivo não tem NFS-e: não achei a nota da Nota "
                                   "Salvador (InfNfse) nem a nacional (infNFSe).")
    return notas


def _xmls_do_zip(dados: bytes) -> list[tuple[str, bytes]]:
    """XMLs do zip, contados na LEITURA: o tamanho declarado no zip nao vale."""
    try:
        pacote = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError):
        raise _erro(NOTA_ILEGIVEL, "O arquivo .zip está corrompido.") from None
    saida = []
    with pacote:
        entradas = [e for e in pacote.infolist()
                    if not e.is_dir() and e.filename.lower().endswith(".xml")]
        if len(entradas) > MAX_XMLS_ZIP:
            raise _erro(NOTA_GRANDE_DEMAIS, f"O .zip tem mais de {MAX_XMLS_ZIP} XMLs.")
        restante = MAX_DESCOMPACTADO
        for n, entrada in enumerate(entradas, start=1):
            if entrada.flag_bits & 0x1:
                raise _erro(NOTA_ILEGIVEL, "O .zip tem senha; envie sem senha.")
            try:
                with pacote.open(entrada) as arq:
                    conteudo = arq.read(restante + 1)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError,
                    zlib.error, OSError):
                raise _erro(NOTA_ILEGIVEL, f"O XML {n} do .zip está corrompido.") from None
            if len(conteudo) > restante:
                raise _erro(NOTA_GRANDE_DEMAIS, "Descompactado, o .zip passa de "
                                                f"{MAX_DESCOMPACTADO // (1024 * 1024)} MB.")
            restante -= len(conteudo)
            saida.append((f"O XML {n} do .zip", conteudo))
    return saida


def _parser() -> etree.XMLParser:
    return etree.XMLParser(no_network=True, resolve_entities=False, load_dtd=False,
                           huge_tree=False, remove_comments=True, remove_pis=True)


def _notas_do_xml(xml: bytes, nome: str) -> list[NotaLida]:
    if not xml.strip():
        raise _erro(NOTA_ILEGIVEL, f"{nome} está vazio.")
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", xml, re.I):
        raise _erro(NOTA_ILEGIVEL, f"{nome}: XML com DOCTYPE não é aceito.")
    try:
        raiz = etree.fromstring(xml, _parser())
    except (etree.XMLSyntaxError, ValueError) as exc:
        motivo = getattr(exc, "msg", "") or "formato inválido"
        raise _erro(NOTA_ILEGIVEL, f"{nome} não é um XML válido ({motivo}).") from None
    if raiz.getroottree().docinfo.doctype:
        raise _erro(NOTA_ILEGIVEL, f"{nome}: XML com DOCTYPE não é aceito.")
    notas = []
    for elemento in raiz.iter():
        local = _local(elemento)
        if local == "InfNfse":
            notas.append(_ler_abrasf(elemento))
        elif local == "infNFSe":
            notas.append(_ler_nacional(elemento))
    return notas


# ----------------------------------------------------------------------
# Navegacao pelo nome local (com ou sem namespace)


def _local(elemento) -> str:
    return etree.QName(elemento).localname if isinstance(elemento.tag, str) else ""


def _filho(elemento, nome: str):
    if elemento is None:
        return None
    for filho in elemento:
        if _local(filho) == nome:
            return filho
    return None


def _primeiro(elemento, *nomes):
    """O primeiro filho que existir entre `nomes`. (Elemento lxml sem filhos e'
    falso num `or`; por isso a comparacao com None.)"""
    for nome in nomes:
        if (filho := _filho(elemento, nome)) is not None:
            return filho
    return None


def _caminho(elemento, *nomes):
    for nome in nomes:
        elemento = _filho(elemento, nome)
        if elemento is None:
            return None
    return elemento


def _texto(elemento, *nomes) -> str | None:
    alvo = _caminho(elemento, *nomes)
    if alvo is None:
        return None
    texto, _ = nf.normalizar_texto(alvo.text)
    return texto or None


def _codigo_reforma(raiz, nomes: set[str], digitos: int) -> str | None:
    if raiz is None:
        return None
    for elemento in raiz.iter():
        if _local(elemento) in nomes:
            valor = re.sub(r"\D", "", elemento.text or "")
            if len(valor) == digitos:
                return valor
    return None


# ----------------------------------------------------------------------
# Campos


def _digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _cnpj(texto) -> str | None:
    try:
        return documentos_br.digitos_cnpj(texto) if texto else None
    except documentos_br.DocumentoInvalido:
        return None


def _ibge(texto) -> str | None:
    valor = _digitos(texto)
    return valor if len(valor) == 7 else None


def _im(texto) -> str | None:
    if not texto:
        return None
    if len(texto) > nf.MAX_INSC_MUNICIPAL:
        texto = _digitos(texto)
    return texto if 0 < len(texto) <= nf.MAX_INSC_MUNICIPAL else None


_RE_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})")
_RE_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})")


def _competencia(texto) -> str | None:
    texto = texto or ""
    if m := _RE_DATA_ISO.match(texto):
        ano, mes = m.groups()
    elif m := _RE_DATA_BR.match(texto):
        mes, ano = m.group(2), m.group(3)
    else:
        return None
    return f"{ano}-{mes}" if 1 <= int(mes) <= 12 else None


def _decimal(texto) -> Decimal | None:
    try:
        return Decimal(str(texto).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def _aliquota(texto, *, fracao: bool) -> tuple[Decimal | None, str | None]:
    """Aliquota em percentual. No ABRASF de Salvador vem em fracao (`0.05`);
    abaixo de 1 e' fracao, de 1 a 5 e' percentual. Acima de 5% (E0595), nao."""
    if texto is None:
        return None, None
    valor = _decimal(texto)
    if valor is None:
        return None, f"Alíquota ilegível na nota ({texto!r}); não preenchi."
    if valor <= 0:
        return None, "A nota tem alíquota zero; não preenchi a alíquota."
    if fracao and valor < 1:
        valor *= 100
    if valor > nf.ALIQUOTA_MAX / 100:
        return None, (f"Alíquota de {texto} na nota passa de 5% (E0595); "
                      "não preenchi.")
    return valor.quantize(Decimal("0.01")), None


def _percentual(valor: Decimal) -> str:
    return f"{valor:.2f}".replace(".", ",")


@lru_cache(maxsize=1)
def _lista_servico() -> dict:
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    caminho = os.path.join(raiz, "dados", "nfse", "lista_servico_nacional.json")
    with open(caminho, encoding="utf-8") as arq:
        return json.load(arq)["subitens"]


def codigo_nacional(item, cnae=None) -> tuple[str | None, list[list[str]]]:
    """Item da lista (LC 116) -> `cTribNac`, pela lista nacional do Anexo B.

    Devolve `(codigo, [])` quando da para decidir, `(None, opcoes)` quando o
    subitem tem mais de um desdobro e nenhuma regra decide, `(None, [])`
    quando o item nao existe na lista."""
    digitos = _digitos(item)
    tabela = _lista_servico()
    if len(digitos) == 6:
        existe = any(codigo == digitos for lista in tabela.values() for codigo, _ in lista)
        return (digitos, []) if existe else (None, [])
    if len(digitos) == 5 and digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) == 3:
        digitos = "0" + digitos
    opcoes = tabela.get(digitos) if len(digitos) == 4 else None
    if not opcoes:
        return None, []
    if len(opcoes) == 1:
        return opcoes[0][0], []
    cnae = _digitos(cnae)
    for prefixo, codigo in _DESDOBRO_POR_CNAE.get(digitos, ()):
        if cnae.startswith(prefixo):
            return codigo, []
    return None, [list(o) for o in opcoes]


# ----------------------------------------------------------------------
# Leiautes


def _ler_abrasf(inf) -> NotaLida:
    nota = NotaLida(LEIAUTE_ABRASF, numero=_texto(inf, "Numero") or "?")
    servico = _filho(inf, "Servico")
    valores = _filho(servico, "Valores")
    prest = _primeiro(inf, "PrestadorServico", "Prestador")
    ident = _filho(prest, "IdentificacaoPrestador")
    toma = _primeiro(inf, "TomadorServico", "Tomador")

    nota.competencia = _competencia(_texto(inf, "Competencia")
                                    or _texto(inf, "DataEmissao"))
    nota.cnpj = _cnpj(_texto(ident, "Cnpj") or _texto(ident, "CpfCnpj", "Cnpj"))
    nota.razao_social = _texto(prest, "RazaoSocial")
    nota.inscricao_municipal = _im(_texto(ident, "InscricaoMunicipal"))
    nota.municipio_ibge = (_ibge(_texto(inf, "OrgaoGerador", "CodigoMunicipio"))
                           or _ibge(_texto(prest, "Endereco", "CodigoMunicipio")))
    nota.municipio_prestacao_ibge = _ibge(_texto(servico, "CodigoMunicipio"))

    optante = _texto(inf, "OptanteSimplesNacional")
    regime = _texto(inf, "RegimeEspecialTributacao")
    if regime == "5":
        nota.optante = OPT_MEI
    elif optante == "2":
        nota.optante = OPT_NAO
    else:
        nota.optante = OPT_ME_EPP if optante == "1" else None
        if regime is None:
            nota.reg_esp_trib = 0 if optante == "1" else None
        elif regime in _REGIME_ABRASF:
            nota.reg_esp_trib = _REGIME_ABRASF[regime]
        else:
            nota.avisos.append(f"Regime especial {regime!r} da nota não tem "
                               "correspondente no padrão nacional; não preenchi.")

    retido = (_texto(valores, "IssRetido") or "").lower()
    nota.iss_retido = {"1": True, "true": True, "sim": True,
                       "2": False, "0": False, "false": False}.get(retido)
    nota.aliquota, aviso = _aliquota(_texto(valores, "Aliquota"), fracao=True)
    if aviso:
        nota.avisos.append(aviso)

    item = _texto(servico, "ItemListaServico")
    cnae = _digitos(_texto(servico, "CodigoCnae")) or None
    codigo, opcoes = codigo_nacional(item, cnae) if item else (None, [])
    if opcoes:
        nota.opcoes_c_trib = opcoes
        nota.avisos.append(
            f"O item {item} da nota corresponde a mais de um código nacional ("
            + "; ".join(f"{c} — {d}" for c, d in opcoes)
            + "). Escolha o da turma.")
    elif item and not codigo:
        nota.avisos.append(f"O item {item} da nota não está na lista nacional; "
                           "informe o código nacional da turma à mão.")
    ctiss = _texto(servico, "CodigoTributacaoMunicipio")
    nota.servico = {
        "c_trib_nac": codigo,
        "c_nbs": _codigo_reforma(inf, _NOMES_NBS, 9),
        "c_ind_op": _codigo_reforma(inf, _NOMES_IND_OP, 6),
        "c_class_trib": _codigo_reforma(inf, _NOMES_CLASS_TRIB, 6),
        "ref_cnae": cnae,
        "ref_item_lista": item[:30] if item else None,
        "ref_ctiss": ctiss[:30] if ctiss else None,
    }
    nota.discriminacao = _texto(servico, "Discriminacao") or ""
    nota.tomador = _texto(toma, "RazaoSocial")
    ident_toma = _filho(toma, "IdentificacaoTomador")
    nota.tomador_doc = _digitos(_texto(ident_toma, "CpfCnpj", "Cpf")
                                or _texto(ident_toma, "CpfCnpj", "Cnpj")) or None
    return nota


def _ler_nacional(inf_nfse) -> NotaLida:
    nota = NotaLida(LEIAUTE_NACIONAL, numero=_texto(inf_nfse, "nNFSe") or "?")
    inf = next((e for e in inf_nfse.iter() if _local(e) == "infDPS"), None)
    if inf is None:
        raise _erro(NOTA_ILEGIVEL, f"A NFS-e nacional nº {nota.numero} não tem a DPS.")
    emit = _filho(inf_nfse, "emit")
    prest = _filho(inf, "prest")
    reg = _filho(prest, "regTrib")

    amb = _texto(inf, "tpAmb")
    nota.ambiente = int(amb) if amb in ("1", "2") else None
    nota.competencia = _competencia(_texto(inf, "dCompet"))
    nota.cnpj = _cnpj(_texto(emit, "CNPJ") or _texto(prest, "CNPJ"))
    nota.razao_social = _texto(emit, "xNome")
    nota.inscricao_municipal = _im(_texto(emit, "IM") or _texto(prest, "IM"))
    # RN #198 e #200: com registro no CNC a IM tem de ir na DPS, sem registro
    # nao pode ir. A nota saiu, entao o que a DPS fez estava certo.
    nota.im_na_dps = _filho(prest, "IM") is not None
    nota.municipio_ibge = _ibge(_texto(inf, "cLocEmi"))
    nota.municipio_prestacao_ibge = _ibge(_texto(inf, "serv", "locPrest", "cLocPrestacao"))

    nota.optante = _OP_SIMP_NAC.get(_texto(reg, "opSimpNac") or "")
    if nota.optante == OPT_ME_EPP:
        reg_ap = _texto(reg, "regApTribSN")
        reg_esp = _texto(reg, "regEspTrib")
        nota.reg_ap_trib_sn = int(reg_ap) if reg_ap in ("1", "2", "3") else None
        nota.reg_esp_trib = (int(reg_esp) if reg_esp and reg_esp.isdigit()
                             and int(reg_esp) in nf.REGIMES_ESPECIAIS else None)

    trib = _caminho(inf, "valores", "trib")
    mun = _filho(trib, "tribMun")
    tp_ret = _texto(mun, "tpRetISSQN")
    nota.iss_retido = {"1": False, "2": True}.get(tp_ret or "")
    if tp_ret == "3":
        nota.avisos.append("A nota tem ISS retido pelo intermediário, que o perfil não "
                           "cobre; não preenchi o ISS retido.")
    p_aliq = _texto(mun, "pAliq")
    if p_aliq is None:
        p_aliq = _texto(inf_nfse, "valores", "pAliqAplic")
        nota.aliquota_aplicada = p_aliq is not None
    nota.aliquota, aviso = _aliquota(p_aliq, fracao=False)
    if aviso:
        nota.avisos.append(aviso)

    tot = _filho(trib, "totTrib")
    if (sn := _texto(tot, "pTotTribSN")) is not None:
        nota.tributos_aprox = nf.TRIB_PTOTTRIBSN
        nota.p_tot = {"p_tot_trib_sn": _decimal(sn)}
    elif (grupo := _filho(tot, "pTotTrib")) is not None:
        nota.tributos_aprox = nf.TRIB_PTOTTRIB
        nota.p_tot = {campo: _decimal(_texto(grupo, tag)) for campo, tag in (
            ("p_tot_trib_fed", "pTotTribFed"), ("p_tot_trib_est", "pTotTribEst"),
            ("p_tot_trib_mun", "pTotTribMun"))}

    cserv = _caminho(inf, "serv", "cServ")
    c_trib = _digitos(_texto(cserv, "cTribNac"))
    nota.servico = {
        "c_trib_nac": c_trib if len(c_trib) == 6 else None,
        "c_nbs": _codigo_reforma(cserv, {"cNBS"}, 9),
        "c_ind_op": _codigo_reforma(inf, {"cIndOp"}, 6),
        "c_class_trib": _codigo_reforma(inf, {"cClassTrib"}, 6),
        "ref_cnae": None, "ref_item_lista": None, "ref_ctiss": None,
    }
    nota.discriminacao = _texto(cserv, "xDescServ") or ""
    toma = _filho(inf, "toma")
    nota.tomador = _texto(toma, "xNome")
    nota.tomador_doc = _digitos(_texto(toma, "CPF") or _texto(toma, "CNPJ")) or None
    return nota


# ----------------------------------------------------------------------
# Modelo da discriminacao


def _dobrar_letra(letra: str) -> str:
    base = unicodedata.normalize("NFD", letra)[:1] or letra
    return base.lower()[:1] or base


def _dobrar(texto: str) -> str:
    """Sem acento e em minusculas, com o MESMO comprimento (indices batem)."""
    return "".join(_dobrar_letra(c) for c in texto)


def _campo(nome: str, maiusculo: bool) -> str:
    return "{" + (nome.upper() if maiusculo else nome) + "}"


def _achar(texto: str, alvo: str) -> list[tuple[int, int]]:
    """Ocorrencias de `alvo` como palavra inteira, sem caixa e sem acento."""
    dobrado, procurado = _dobrar(texto), _dobrar(" ".join(alvo.split()))
    achados, inicio = [], 0
    while procurado and (pos := dobrado.find(procurado, inicio)) >= 0:
        fim = pos + len(procurado)
        if ((pos == 0 or not dobrado[pos - 1].isalnum())
                and (fim == len(dobrado) or not dobrado[fim].isalnum())):
            achados.append((pos, fim))
            inicio = fim
        else:
            inicio = pos + 1
    return achados


def _trocar(texto: str, trechos, nome: str) -> str:
    for inicio, fim in sorted(trechos, reverse=True):
        texto = texto[:inicio] + _campo(nome, texto[inicio:fim].isupper()) + texto[fim:]
    return texto


_MESES_DOBRADOS = tuple(_dobrar(m) for m in nf.MESES_EXTENSO)
_MARCADOR = re.compile(r"\b(?:menor|alun[oa]|crianca|estudante|dependente)\b"
                       r"(?:\s*\(\s*a\s*\))?\s*[:\-–]?\s*")
_PALAVRA = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")
_PARADAS = {"no", "na", "nos", "nas", "em", "referente", "referentes", "ref", "periodo",
            "mes", "competencia", "turma", "serie", "ano", "mensalidade", "cpf",
            "responsavel", "valor", "matricula", "pelo", "pela", "pelos", "pelas",
            "durante", "relativo", "relativa", "conforme", *_MESES_DOBRADOS}
_CONECTIVOS = {"de", "da", "do", "das", "dos", "e", "d"}
_RE_DOCUMENTO = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")
_RE_DATA_SOBRANDO = re.compile(r"(?<!\d)\d{1,2}\s*/\s*\d{4}(?!\d)|\b(?:19|20)\d{2}\b")


def _nome_depois(texto: str, inicio: int) -> tuple[int, int] | None:
    """Nome proprio que comeca em `inicio`: palavras separadas por espaco ate
    uma pontuacao, um numero, um campo ja trocado ou uma palavra de parada."""
    palavras: list[tuple[int, int]] = []
    pos = inicio
    while (m := _PALAVRA.match(texto, pos)) is not None:
        if _dobrar(m.group()) in _PARADAS:
            break
        palavras.append((m.start(), m.end()))
        espacos = re.match(r" +", texto[m.end():])
        if not espacos:
            break
        pos = m.end() + espacos.end()
    while palavras and _dobrar(texto[slice(*palavras[-1])]) in _CONECTIVOS:
        palavras.pop()
    if len(palavras) < 2 or _dobrar(texto[slice(*palavras[0])]) in _CONECTIVOS:
        return None
    return palavras[0][0], palavras[-1][1]


def modelo_da_discriminacao(texto: str, *, tomador: str | None, competencia: str | None,
                            turmas) -> str | None:
    """Texto de uma nota -> modelo com `{ALUNO}`, `{TURMA}`, `{MES}`... ou
    `None` quando nao da para tirar todos os nomes e datas com seguranca."""
    texto, _ = nf.normalizar_texto(texto)
    if not texto or not competencia:
        return None
    maiusculo = texto.upper() == texto
    if tomador:
        texto = _trocar(texto, _achar(texto, tomador), "responsavel")

    ano, mes = competencia.split("-")
    nome_mes = _MESES_DOBRADOS[int(mes) - 1]
    padrao = re.compile(rf"\b{nome_mes}\b(\s*/\s*|\s+de\s+|\s+)({ano})\b")
    for m in reversed(list(padrao.finditer(_dobrar(texto)))):
        alto = texto[m.start():m.start() + len(nome_mes)].isupper()
        texto = (texto[:m.start()] + _campo("mes_extenso", alto) + texto[m.start(1):m.end(1)]
                 + _campo("ano", alto) + texto[m.end():])
    numerico = re.compile(rf"(?<![\d/])0?{int(mes)}\s*/\s*{ano}(?!\d)")
    texto = numerico.sub(_campo("mes", maiusculo) + "/" + _campo("ano", maiusculo), texto)
    texto = re.sub(rf"(?<![\d/]){ano}(?!\d)", _campo("ano", maiusculo), texto)

    for turma in sorted((t for t in turmas if t), key=len, reverse=True):
        texto = _trocar(texto, _achar(texto, turma), "turma")

    alunos = []
    for m in _MARCADOR.finditer(_dobrar(texto)):
        if (trecho := _nome_depois(texto, m.end())) is not None:
            alunos.append(trecho)
    if not alunos:
        return None
    texto = _trocar(texto, alunos, "aluno")

    # O que sobrar de nome do tomador, documento ou data fica de fora: o
    # modelo iria para todas as notas.
    for parte in (tomador or "").split():
        if len(parte) >= 3 and _dobrar(parte) not in _CONECTIVOS and _achar(texto, parte):
            return None
    if _RE_DOCUMENTO.search(texto) or _RE_DATA_SOBRANDO.search(texto):
        return None
    dobrado = _dobrar(texto)
    if any(re.search(rf"\b{m}\b", dobrado) for m in _MESES_DOBRADOS):
        return None
    try:
        nf.validar_modelo(texto)
    except nf.ErroNfse:
        return None
    return texto


def _turma_no_texto(texto: str, turmas) -> str | None:
    for turma in sorted((t for t in turmas if t), key=len, reverse=True):
        if _achar(texto, turma):
            return turma
    return None


# ----------------------------------------------------------------------
# Sugestao para o formulario


def _turmas_sugeridas(notas: list[NotaLida], turmas, fonte: str,
                      avisos: list[str]) -> list[dict]:
    """Uma sugestao por combinacao de codigos. A mesma turma vinda de leiautes
    diferentes (a Nota Salvador traz CNAE e item, a nacional traz o NBS) vira
    uma so quando os codigos nao conflitam; conflito fica separado, com aviso."""
    grupos: Counter = Counter()
    for nota in notas:
        nome = _turma_no_texto(nota.discriminacao, turmas)
        grupos[(nome, tuple(nota.servico.get(c) for c in CODIGOS_TURMA))] += 1
    sugeridas: list[dict] = []
    for (nome, codigos), vezes in grupos.most_common():
        atual = dict(zip(CODIGOS_TURMA, codigos))
        par = next((s for s in sugeridas if nome and s["nome"] == nome and all(
            s[c] is None or atual[c] is None or s[c] == atual[c] for c in CODIGOS_TURMA)),
            None)
        if par is None:
            sugeridas.append({"nome": nome, **atual, "notas": vezes, "fonte": fonte})
            continue
        for c in CODIGOS_TURMA:
            par[c] = par[c] or atual[c]
        par["notas"] += vezes
    for nome in sorted({s["nome"] for s in sugeridas if s["nome"]}):
        if sum(s["nome"] == nome for s in sugeridas) > 1:
            avisos.append(f"A turma {nome} aparece com códigos diferentes nas notas; "
                          "confira os códigos dela.")
    return sugeridas[:MAX_TURMAS_SUGERIDAS]


def _cnpj_formatado(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _fonte(notas: list[NotaLida]) -> str:
    if len(notas) == 1:
        return f"{notas[0].rotulo} nº {notas[0].numero}"
    rotulos = sorted({n.rotulo for n in notas})
    return f"{len(notas)} notas da {' e da '.join(rotulos)}"


def _mostrar(valor) -> str:
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, Decimal):
        return _percentual(valor) + "%"
    return str(valor)


def sugerir_perfil(notas: list[NotaLida], *, cnpj_perfil: str | None = None,
                   turmas=()) -> dict:
    """Sugestoes para o formulario do perfil, cada uma com a fonte.

    Um campo so e' preenchido quando todas as notas usadas concordam. Nada de
    CPF, nome do tomador ou do aluno e texto original no resultado."""
    if not notas:
        raise _erro(NOTA_SEM_NFSE, "Nenhuma NFS-e para ler.")
    turmas = [t for t in (nf.normalizar_texto(x)[0] for x in turmas or ()) if t][:50]
    avisos: list[str] = []

    if cnpj_perfil:
        alvo = _digitos(cnpj_perfil)
        usadas = [n for n in notas if n.cnpj == alvo]
        if not usadas:
            achados = sorted({_cnpj_formatado(n.cnpj) for n in notas if n.cnpj})
            raise _erro(NOTA_DE_OUTRO_CNPJ,
                        "As notas do arquivo são de outro prestador ("
                        + (", ".join(achados) or "CNPJ não identificado")
                        + "), não do CNPJ deste perfil.")
    else:
        alvo = Counter(n.cnpj for n in notas).most_common(1)[0][0]
        usadas = [n for n in notas if n.cnpj == alvo]
    if len(usadas) < len(notas):
        avisos.append(f"{len(notas) - len(usadas)} nota(s) de outro prestador ficaram "
                      "de fora.")
    fonte = _fonte(usadas)
    campos: dict[str, dict] = {}

    def consenso(campo: str, rotulo: str, valores, formatar=lambda v: v, sufixo=""):
        conhecidos = [v for v in valores if v is not None]
        if not conhecidos:
            return
        distintos = sorted({_mostrar(v) for v in conhecidos})
        if len(distintos) > 1:
            avisos.append(f"As notas divergem em {rotulo} ({', '.join(distintos)}); "
                          "não preenchi.")
            return
        campos[campo] = {"valor": formatar(conhecidos[0]), "fonte": fonte + sufixo}

    if alvo:
        campos["cnpj"] = {"valor": _cnpj_formatado(alvo), "fonte": fonte}
    consenso("razao_social", "razão social", [n.razao_social for n in usadas])
    consenso("inscricao_municipal", "inscrição municipal",
             [n.inscricao_municipal for n in usadas])
    consenso("informar_im", "IM na DPS", [n.im_na_dps for n in usadas],
             sufixo=": a nota saiu com a IM na DPS" if all(
                 n.im_na_dps for n in usadas if n.im_na_dps is not None)
             else ": a nota saiu sem a IM na DPS")
    consenso("municipio_ibge", "município emissor", [n.municipio_ibge for n in usadas])
    consenso("municipio_prestacao_ibge", "local da prestação",
             [n.municipio_prestacao_ibge for n in usadas])
    consenso("iss_retido", "ISS retido", [n.iss_retido for n in usadas])
    consenso("aliquota", "alíquota", [n.aliquota for n in usadas], _percentual,
             sufixo=" (alíquota aplicada pela Sefin)" if any(
                 n.aliquota_aplicada for n in usadas) else "")

    optantes = {n.optante for n in usadas}
    if OPT_MEI in optantes:
        avisos.append("A nota é de MEI. Este perfil só serve para ME/EPP do Simples "
                      "Nacional; o regime não foi sugerido.")
    if OPT_NAO in optantes:
        avisos.append("A nota é de prestador não optante do Simples. Este perfil só serve "
                      "para ME/EPP do Simples Nacional; o regime não foi sugerido.")
    regulares = [n for n in usadas if n.optante in (OPT_ME_EPP, None)]
    if regulares and not optantes & {OPT_MEI, OPT_NAO}:
        consenso("reg_ap_trib_sn", "regime de apuração no Simples",
                 [n.reg_ap_trib_sn for n in regulares])
        consenso("reg_esp_trib", "regime especial", [n.reg_esp_trib for n in regulares])
        consenso("tributos_aprox", "forma dos tributos aproximados",
                 [n.tributos_aprox for n in regulares])
        if campos.get("tributos_aprox"):
            for campo in ("p_tot_trib_sn", "p_tot_trib_fed", "p_tot_trib_est",
                          "p_tot_trib_mun"):
                consenso(campo, f"percentual de tributos ({campo})",
                         [n.p_tot.get(campo) for n in regulares], _percentual)
            if "p_tot_trib_sn" in campos:
                avisos.append("O percentual do Simples (pTotTribSN) muda com a faixa de "
                              "faturamento; confira com a JB o do mês.")

    if any(n.ambiente == 2 for n in usadas):
        avisos.append("Há nota da produção restrita (tpAmb = 2): os dados são de teste; "
                      "confira antes de usar.")
    for nota in usadas:
        for aviso in nota.avisos:
            if aviso not in avisos:
                avisos.append(aviso)

    # Modelo da discriminacao: o mais comum entre as notas.
    modelos = Counter(m for m in (
        modelo_da_discriminacao(n.discriminacao, tomador=n.tomador,
                                competencia=n.competencia, turmas=turmas)
        for n in usadas) if m)
    if modelos:
        modelo, vezes = modelos.most_common(1)[0]
        campos["modelo_discriminacao"] = {"valor": modelo, "fonte": fonte}
        if len(modelos) > 1:
            avisos.append(f"As notas têm textos diferentes; usei o mais comum ({vezes} de "
                          f"{len(usadas)}).")
    else:
        avisos.append("Não montei o modelo da discriminação: não achei o nome do aluno "
                      "depois de \"menor\", \"aluno(a)\", \"criança\", \"estudante\" ou "
                      "\"dependente\", ou sobrou data, CPF ou nome que não deu para trocar. "
                      "Monte o modelo à mão.")
    if not turmas:
        avisos.append("Cadastre as turmas antes de ler a nota para o nome da turma virar "
                      "{TURMA} no modelo e os códigos irem para a turma certa.")

    sugeridas = _turmas_sugeridas(usadas, turmas, fonte, avisos)

    manuais = [texto for campo, texto in _MANUAIS if campo not in campos]
    return {
        "campos": campos,
        "turmas": sugeridas,
        "avisos": avisos,
        "manuais": manuais,
        "notas": {"lidas": len(notas), "usadas": len(usadas),
                  "leiautes": sorted({n.rotulo for n in usadas}),
                  "numeros": [n.numero for n in usadas][:10],
                  "competencias": sorted({n.competencia for n in usadas
                                          if n.competencia})},
    }
