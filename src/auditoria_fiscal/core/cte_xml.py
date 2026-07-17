"""Leitor de XML do CT-e (Conhecimento de Transporte Eletronico, modelo 57).

O CT-e documenta uma PRESTACAO DE SERVICO DE TRANSPORTE, nao mercadorias: nao
tem itens de produto (<det>). Para que as ferramentas (Livro de Conferencia e
Extracao de Itens) tratem o CT-e sem precisar distinguir a origem, ele e
mapeado para o MESMO modelo NotaFiscal da NF-e, com UM item sintetico que
representa o frete (CFOP/CST/aliquota/valor do servico). O emitente do CT-e (a
transportadora) vira o participante/fornecedor.

Reaproveita os helpers do leitor de NF-e (busca por local-name, ignorando o
namespace http://www.portalfiscal.inf.br/cte). O despacho entre NF-e e CT-e
fica em nfe_xml.ler_pasta_xml, que tenta um e depois o outro.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from lxml import etree

from .modelos import ItemNota, NotaFiscal, ORIGEM_XML, so_digitos
from .nfe_xml import (
    _icms_item,
    _no,
    _participante_de,
    _situacao_por_status,
    _texto,
)
from .utils import para_data, para_decimal

MODELO_CTE = "57"


def _chave_cte(inf) -> str:
    """Chave de acesso (44 digitos) do atributo Id = 'CTe' + 44 digitos."""
    chave = so_digitos(inf.get("Id", ""))
    return chave[-44:] if len(chave) > 44 else chave


def ler_xml_cte(caminho: str) -> Optional[NotaFiscal]:
    """Le um XML de CT-e e retorna a NotaFiscal (ou None se nao for CT-e)."""
    try:
        arvore = etree.parse(caminho)
    except (etree.XMLSyntaxError, OSError):
        return None
    raiz = arvore.getroot()

    inf = _no(raiz, "infCte")
    if inf is None:
        return None

    ide = _no(inf, "ide")
    dh_emi = _texto(ide, "dhEmi") or _texto(ide, "dEmi")
    cfop = _texto(ide, "CFOP")
    nat_op = _texto(ide, "natOp")

    # Valor do servico de transporte (o "valor contabil" do CT-e).
    vprest = _no(inf, "vPrest")
    valor_serv = (para_decimal(_texto(vprest, "vTPrest"))
                  or para_decimal(_texto(vprest, "vRec")))

    # ICMS do frete: grupo <imp><ICMS><ICMSxx>.  O helper de NF-e ja pega
    # CST/vBC/pICMS/vICMS do primeiro filho do grupo ICMS.
    icms = _icms_item(_no(inf, "imp"))

    situacao = _situacao_por_status(_texto(raiz, "cStat"))

    nota = NotaFiscal(
        origem=ORIGEM_XML,
        xml_path=os.path.abspath(caminho),
        chave=_chave_cte(inf),
        modelo=_texto(ide, "mod") or MODELO_CTE,
        serie=_texto(ide, "serie"),
        numero=_texto(ide, "nCT"),
        ind_oper="",               # CT-e nao traz entrada/saida (depende do tomador)
        ind_emit="",
        situacao=situacao,
        participante=_participante_de(_no(inf, "emit")),
        dt_emissao=para_data(dh_emi[:10]) if dh_emi else None,
        valor_documento=valor_serv,
        valor_frete=valor_serv,
        vl_bc_icms=icms["vl_bc"],
        vl_icms=icms["vl"],
        vl_bc_icms_st=icms["vl_bc_st"],
        vl_icms_st=icms["vl_st"],
    )

    # Item sintetico: a propria prestacao de servico de transporte, para que a
    # composicao fiscal e a extracao de itens tenham CFOP/CST/aliquota/valor.
    nota.itens.append(ItemNota(
        num_item="1",
        descricao=nat_op or "Prestacao de servico de transporte (CT-e)",
        unidade="SERV",
        quantidade=Decimal("1"),
        valor_unitario=valor_serv,
        valor_item=valor_serv,
        cfop=cfop,
        cst_icms=icms["cst"],
        vl_bc_icms=icms["vl_bc"],
        aliq_icms=icms["aliq"],
        vl_icms=icms["vl"],
        vl_bc_icms_st=icms["vl_bc_st"],
        aliq_st=icms["aliq_st"],
        vl_icms_st=icms["vl_st"],
    ))

    return nota


def chave_do_cte(caminho: str) -> str:
    """Extrai a chave de acesso (44 digitos) de um XML de CT-e, ou ''."""
    try:
        arvore = etree.parse(caminho)
    except (etree.XMLSyntaxError, OSError):
        return ""
    inf = _no(arvore.getroot(), "infCte")
    if inf is None:
        return ""
    chave = _chave_cte(inf)
    return chave if len(chave) == 44 else ""
