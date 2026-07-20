"""Leitor de XML da NF-e (leiaute 4.00) / procNFe.

Produz os mesmos modelos (NotaFiscal / ItemNota / Participante) que o leitor de
SPED, de modo que as ferramentas nao precisam distinguir a origem.

A busca de elementos usa local-name() para ignorar o namespace
(http://www.portalfiscal.inf.br/nfe), tornando o parser tolerante a XMLs com ou
sem prefixo de namespace.
"""

from __future__ import annotations

import glob
import os
from decimal import Decimal
from typing import Optional

from lxml import etree

from .modelos import (
    ItemNota,
    NotaFiscal,
    Participante,
    ORIGEM_XML,
    so_digitos,
)
from .utils import para_data, para_decimal


def _texto(elemento, caminho_local: str) -> str:
    """Retorna o texto do primeiro descendente com o dado local-name."""
    if elemento is None:
        return ""
    achados = elemento.xpath(
        f".//*[local-name()=$n]", n=caminho_local
    )
    if achados and achados[0].text:
        return achados[0].text.strip()
    return ""


def _no(elemento, nome_local):
    """Retorna o primeiro descendente com o local-name informado (ou None)."""
    if elemento is None:
        return None
    achados = elemento.xpath(".//*[local-name()=$n]", n=nome_local)
    return achados[0] if achados else None


def _participante_de(no_part) -> Optional[Participante]:
    if no_part is None:
        return None
    return Participante(
        nome=_texto(no_part, "xNome"),
        cnpj=so_digitos(_texto(no_part, "CNPJ")),
        cpf=so_digitos(_texto(no_part, "CPF")),
        ie=_texto(no_part, "IE"),
        uf=_texto(no_part, "UF"),
    )


def _situacao_por_status(cstat: str) -> str:
    """Mapeia cStat do protocolo para o codigo de situacao do SPED.

    100 autorizado -> "00" (regular)
    101/151/135 cancelado -> "02"
    110/301/302/303 denegado -> "04"
    """
    if cstat in {"101", "151", "135", "155"}:
        return "02"
    if cstat in {"110", "301", "302", "303"}:
        return "04"
    return "00"


def _icms_item(no_imposto) -> dict:
    """Extrai CST/CSOSN e valores de ICMS do grupo (variantes ICMS00..ICMSSNxxx)."""
    resultado = {
        "cst": "", "vl_bc": Decimal("0"), "aliq": Decimal("0"),
        "vl": Decimal("0"), "vl_bc_st": Decimal("0"), "aliq_st": Decimal("0"),
        "vl_st": Decimal("0"),
    }
    grupo = _no(no_imposto, "ICMS")
    if grupo is None:
        return resultado
    # O grupo ICMS tem um unico filho (ICMS00, ICMS10, ICMSSN101, ...).
    filhos = list(grupo)
    alvo = filhos[0] if filhos else grupo
    cst = _texto(alvo, "CST") or _texto(alvo, "CSOSN")
    resultado.update(
        cst=cst,
        vl_bc=para_decimal(_texto(alvo, "vBC")),
        aliq=para_decimal(_texto(alvo, "pICMS")),
        vl=para_decimal(_texto(alvo, "vICMS")),
        vl_bc_st=para_decimal(_texto(alvo, "vBCST")),
        aliq_st=para_decimal(_texto(alvo, "pICMSST")),
        vl_st=para_decimal(_texto(alvo, "vICMSST")),
    )
    return resultado


def _imposto_simples(no_imposto, grupo_nome: str, campo_valor: str) -> tuple[str, Decimal]:
    """Extrai (CST, valor) de IPI/PIS/COFINS."""
    grupo = _no(no_imposto, grupo_nome)
    if grupo is None:
        return "", Decimal("0")
    cst = _texto(grupo, "CST")
    valor = para_decimal(_texto(grupo, campo_valor))
    return cst, valor


def ler_xml_nfe(caminho: str) -> Optional[NotaFiscal]:
    """Le um arquivo XML de NF-e e retorna a NotaFiscal (ou None se invalido)."""
    try:
        arvore = etree.parse(caminho)
    except (etree.XMLSyntaxError, OSError):
        return None
    raiz = arvore.getroot()

    inf = _no(raiz, "infNFe")
    if inf is None:
        return None

    # Chave: atributo Id = "NFe" + 44 digitos.
    chave = so_digitos(inf.get("Id", ""))
    if len(chave) > 44:
        chave = chave[-44:]

    ide = _no(inf, "ide")
    tp_nf = _texto(ide, "tpNF")            # 0 entrada / 1 saida
    dh_emi = _texto(ide, "dhEmi") or _texto(ide, "dEmi")
    dh_saient = _texto(ide, "dhSaiEnt") or _texto(ide, "dSaiEnt")

    total = _no(_no(inf, "total"), "ICMSTot") if _no(inf, "total") is not None else None

    # Protocolo (status de autorizacao/cancelamento/denegacao).
    cstat = _texto(raiz, "cStat")
    situacao = _situacao_por_status(cstat)

    nota = NotaFiscal(
        origem=ORIGEM_XML,
        xml_path=os.path.abspath(caminho),
        chave=chave,
        modelo=_texto(ide, "mod"),
        serie=_texto(ide, "serie"),
        numero=_texto(ide, "nNF"),
        ind_oper="0" if tp_nf == "0" else "1",
        ind_emit="",
        situacao=situacao,
        participante=_participante_de(_no(inf, "emit")),
        dt_emissao=para_data(dh_emi[:10]),
        dt_entrada_saida=para_data(dh_saient[:10]) if dh_saient else None,
        valor_documento=para_decimal(_texto(total, "vNF")),
        valor_mercadoria=para_decimal(_texto(total, "vProd")),
        valor_desconto=para_decimal(_texto(total, "vDesc")),
        valor_frete=para_decimal(_texto(total, "vFrete")),
        vl_bc_icms=para_decimal(_texto(total, "vBC")),
        vl_icms=para_decimal(_texto(total, "vICMS")),
        vl_bc_icms_st=para_decimal(_texto(total, "vBCST")),
        vl_icms_st=para_decimal(_texto(total, "vST")),
        vl_ipi=para_decimal(_texto(total, "vIPI")),
        vl_pis=para_decimal(_texto(total, "vPIS")),
        vl_cofins=para_decimal(_texto(total, "vCOFINS")),
    )

    # Itens: cada <det nItem="..">
    for det in inf.xpath(".//*[local-name()='det']"):
        prod = _no(det, "prod")
        imposto = _no(det, "imposto")
        icms = _icms_item(imposto)
        cst_ipi, vl_ipi = _imposto_simples(imposto, "IPI", "vIPI")
        cst_pis, vl_pis = _imposto_simples(imposto, "PIS", "vPIS")
        cst_cofins, vl_cofins = _imposto_simples(imposto, "COFINS", "vCOFINS")

        item = ItemNota(
            num_item=det.get("nItem", ""),
            cod_item=_texto(prod, "cProd"),
            descricao=_texto(prod, "xProd"),
            ncm=_texto(prod, "NCM"),
            cest=_texto(prod, "CEST"),
            unidade=_texto(prod, "uCom"),
            quantidade=para_decimal(_texto(prod, "qCom")),
            valor_unitario=para_decimal(_texto(prod, "vUnCom")),
            valor_item=para_decimal(_texto(prod, "vProd")),
            valor_desconto=para_decimal(_texto(prod, "vDesc")),
            cfop=_texto(prod, "CFOP"),
            cst_icms=icms["cst"],
            vl_bc_icms=icms["vl_bc"],
            aliq_icms=icms["aliq"],
            vl_icms=icms["vl"],
            vl_bc_icms_st=icms["vl_bc_st"],
            aliq_st=icms["aliq_st"],
            vl_icms_st=icms["vl_st"],
            cst_ipi=cst_ipi,
            vl_ipi=vl_ipi,
            cst_pis=cst_pis,
            vl_pis=vl_pis,
            cst_cofins=cst_cofins,
            vl_cofins=vl_cofins,
        )
        nota.itens.append(item)

    return nota


def ler_pasta_xml(pasta: str) -> list[NotaFiscal]:
    """Le todos os XMLs de NF-e e CT-e de uma pasta (recursivamente).

    Cada arquivo e tentado como NF-e; se nao for (ex.: um CT-e), tenta como
    CT-e. Import tardio de cte_xml para evitar ciclo (cte_xml usa helpers deste
    modulo)."""
    from .cte_xml import ler_xml_cte

    notas: list[NotaFiscal] = []
    padrao = os.path.join(pasta, "**", "*.xml")
    for caminho in glob.glob(padrao, recursive=True):
        nota = ler_xml_nfe(caminho) or ler_xml_cte(caminho)
        if nota is not None:
            notas.append(nota)
    return notas


def chave_do_xml(caminho: str) -> str:
    """Extrai a chave de acesso (44 digitos) de um XML de NF-e ou CT-e, ou ""."""
    try:
        arvore = etree.parse(caminho)
    except (etree.XMLSyntaxError, OSError):
        return ""
    inf = _no(arvore.getroot(), "infNFe")
    if inf is None:
        from .cte_xml import chave_do_cte
        return chave_do_cte(caminho)
    chave = so_digitos(inf.get("Id", ""))
    if len(chave) > 44:
        chave = chave[-44:]
    return chave if len(chave) == 44 else ""


def indexar_pasta_xml(pasta: str) -> dict[str, str]:
    """Mapeia chave de acesso -> caminho do XML (busca recursiva na pasta)."""
    indice: dict[str, str] = {}
    padrao = os.path.join(pasta, "**", "*.xml")
    for caminho in glob.glob(padrao, recursive=True):
        chave = chave_do_xml(caminho)
        if chave and chave not in indice:
            indice[chave] = os.path.abspath(caminho)
    return indice


def associar_xmls(notas: list[NotaFiscal], pasta: str) -> int:
    """Preenche xml_path das notas localizando o XML pela chave de acesso.

    Usado quando as notas vieram do SPED (que nao traz o XML): com o XML
    associado, o DANFE passa a poder ser gerado tambem para essas notas.
    Retorna quantas notas ganharam XML nesta chamada.
    """
    indice = indexar_pasta_xml(pasta)
    associadas = 0
    for nota in notas:
        if nota.xml_path:
            continue
        caminho = indice.get(nota.chave_normalizada)
        if caminho:
            nota.xml_path = caminho
            associadas += 1
    return associadas


def completar_itens_com_xmls(notas: list[NotaFiscal], pasta: str) -> dict:
    """Le os XMLs correspondentes as notas (vindas do SPED) e completa itens.

    Fluxo combinado SPED + XMLs: o SPED define QUAIS notas entram; desta
    pasta, so os XMLs cuja chave de acesso consta nas notas recebidas sao
    lidos por inteiro — os demais ficam de fora (contados em "ignorados").

    O SPED continua sendo a autoridade sobre o que foi declarado: a
    classificacao entrada/saida (IND_OPER), a situacao e os totais nao
    mudam, e notas COM itens do C170 mantem os proprios itens (e a
    declaracao que se audita). O XML entra como complemento: preenche
    xml_path (DANFE) e da itens as notas que o SPED nao detalhou (C100 sem
    C170) — sem herdar o tpNF do emitente, que inverteria o filtro de
    operacao nas compras.

    Retorna contadores para a interface: com_xml (notas com XML na pasta),
    completadas (notas que ganharam itens do XML), sem_xml (notas sem XML
    correspondente) e ignorados (XMLs da pasta fora do SPED).
    """
    from .cte_xml import ler_xml_cte

    indice = indexar_pasta_xml(pasta)
    usadas: set[str] = set()
    com_xml = completadas = 0
    for nota in notas:
        caminho = indice.get(nota.chave_normalizada)
        if not caminho:
            continue
        usadas.add(nota.chave_normalizada)
        com_xml += 1
        if not nota.xml_path:
            nota.xml_path = caminho
        if not nota.itens:
            do_xml = ler_xml_nfe(caminho) or ler_xml_cte(caminho)
            if do_xml is not None and do_xml.itens:
                nota.itens = do_xml.itens
                completadas += 1
    return {
        "com_xml": com_xml,
        "completadas": completadas,
        "sem_xml": len(notas) - com_xml,
        "ignorados": len(indice) - len(usadas),
    }
