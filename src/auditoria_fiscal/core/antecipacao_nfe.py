"""Leitor do XML da NF-e para a Antecipacao/DIFAL da Bahia (spec 027).

O leitor geral (`nfe_xml.py`) alimenta o Livro de Conferencia e nao traz o que
esta conta precisa: destinatario, origem da mercadoria, frete/seguro/outras
por item, FCP, CRT do emitente e o credito do Simples. Este modulo le so isso,
a partir dos BYTES recebidos no upload (arquivo de terceiro: parser sem
entidades externas, sem rede e sem arvore gigante).

Campo ausente continua ausente (None): quem decide o que fazer com a falta e'
`antecipacao_ba.avaliar_item`, que a transforma em pendencia.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from .antecipacao_ba import ItemEntrada, NotaEntrada, so_digitos

MAX_XML_BYTES = 5 * 1024 * 1024
MAX_ITENS = 990          # limite do leiaute da NF-e


class NFeInvalida(ValueError):
    """O arquivo nao e' um XML de NF-e que de para ler."""


def _nome(elemento) -> str:
    return etree.QName(elemento).localname if isinstance(elemento.tag, str) else ""


def _filho(elemento, nome: str):
    if elemento is None:
        return None
    for filho in elemento:
        if _nome(filho) == nome:
            return filho
    return None


def _caminho(elemento, *nomes: str):
    for nome in nomes:
        elemento = _filho(elemento, nome)
        if elemento is None:
            return None
    return elemento


def _texto(elemento, *nomes: str) -> str:
    alvo = _caminho(elemento, *nomes)
    return (alvo.text or "").strip() if alvo is not None else ""


def _decimal(elemento, *nomes: str) -> Decimal | None:
    texto = _texto(elemento, *nomes)
    if not texto:
        return None
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def _ou_zero(valor: Decimal | None) -> Decimal:
    """So para parcelas OPCIONAIS do leiaute (desconto, frete...): a tag
    ausente significa mesmo "nao ha"."""
    return valor if valor is not None else Decimal("0")


def _data(texto: str) -> date | None:
    try:
        return date.fromisoformat(texto[:10])
    except (ValueError, TypeError):
        return None


def _primeiro(raiz, nome: str):
    """Primeiro elemento com o local-name, em qualquer profundidade."""
    if _nome(raiz) == nome:
        return raiz
    for elemento in raiz.iter():
        if _nome(elemento) == nome:
            return elemento
    return None


def _item(det) -> ItemEntrada:
    prod = _filho(det, "prod")
    imposto = _filho(det, "imposto")
    grupo = _filho(imposto, "ICMS")
    icms = grupo[0] if grupo is not None and len(grupo) else None
    fcp = _ou_zero(_decimal(icms, "vFCP")) + _ou_zero(_decimal(icms, "vFCPST"))
    return ItemEntrada(
        num_item=det.get("nItem", ""),
        descricao=_texto(prod, "xProd")[:300],
        ncm=so_digitos(_texto(prod, "NCM")),
        cest=so_digitos(_texto(prod, "CEST")),
        cfop=so_digitos(_texto(prod, "CFOP")),
        cst=_texto(icms, "CST") or _texto(icms, "CSOSN"),
        origem_mercadoria=_texto(icms, "orig"),
        v_prod=_decimal(prod, "vProd"),
        v_desc=_ou_zero(_decimal(prod, "vDesc")),
        v_frete=_ou_zero(_decimal(prod, "vFrete")),
        v_seg=_ou_zero(_decimal(prod, "vSeg")),
        v_outro=_ou_zero(_decimal(prod, "vOutro")),
        v_ipi=_ou_zero(_decimal(imposto, "IPI", "IPITrib", "vIPI")),
        aliq_icms=_decimal(icms, "pICMS"),
        v_icms=_decimal(icms, "vICMS"),
        v_bc_st=_ou_zero(_decimal(icms, "vBCST")),
        v_st=_ou_zero(_decimal(icms, "vICMSST")),
        v_fcp=fcp,
        v_cred_sn=_ou_zero(_decimal(icms, "vCredICMSSN")),
    )


def ler_nfe(conteudo: bytes) -> NotaEntrada:
    """Bytes de um XML de NF-e (NFe ou nfeProc) -> NotaEntrada."""
    if not conteudo:
        raise NFeInvalida("Arquivo vazio.")
    if len(conteudo) > MAX_XML_BYTES:
        raise NFeInvalida(
            f"XML maior que {MAX_XML_BYTES // (1024 * 1024)} MB.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True,
                             load_dtd=False, dtd_validation=False,
                             huge_tree=False, remove_comments=True,
                             remove_pis=True)
    try:
        raiz = etree.fromstring(conteudo, parser)
    except etree.XMLSyntaxError as exc:
        raise NFeInvalida("O arquivo não é um XML válido.") from exc

    inf = _primeiro(raiz, "infNFe")
    if inf is None:
        raise NFeInvalida("O XML não é de NF-e (falta o grupo infNFe).")

    chave = so_digitos(inf.get("Id", ""))[-44:]
    ide = _filho(inf, "ide")
    emit = _filho(inf, "emit")
    dest = _filho(inf, "dest")
    prot = _primeiro(raiz, "infProt")

    itens = [_item(det) for det in inf if _nome(det) == "det"]
    if len(itens) > MAX_ITENS:
        raise NFeInvalida("A nota tem mais itens que o leiaute permite.")

    return NotaEntrada(
        chave=chave,
        modelo=_texto(ide, "mod"),
        numero=_texto(ide, "nNF"),
        serie=_texto(ide, "serie"),
        dt_emissao=_data(_texto(ide, "dhEmi") or _texto(ide, "dEmi")),
        tp_nf=_texto(ide, "tpNF"),
        fin_nfe=_texto(ide, "finNFe"),
        situacao=_texto(prot, "cStat"),
        uf_origem=_texto(emit, "enderEmit", "UF").upper(),
        uf_destino=_texto(dest, "enderDest", "UF").upper(),
        cnpj_emit=so_digitos(_texto(emit, "CNPJ")),
        nome_emit=_texto(emit, "xNome")[:200],
        crt_emit=_texto(emit, "CRT"),
        cnpj_dest=so_digitos(_texto(dest, "CNPJ")),
        nome_dest=_texto(dest, "xNome")[:200],
        valor_total=_decimal(inf, "total", "ICMSTot", "vNF"),
        itens=itens,
    )
