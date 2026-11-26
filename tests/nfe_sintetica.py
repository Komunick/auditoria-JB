"""Fabrica de XML de NF-e SINTETICO para os testes da spec 027.

Nao e' teste (o nome nao comeca por test_): os testes da Antecipacao importam
daqui. CNPJs, nomes e chaves sao ficticios; nenhum dado real entra no Git.
"""

from __future__ import annotations

CNPJ_DEST = "11222333000181"
CNPJ_EMIT = "99888777000166"

_COD_UF = {"SP": "35", "GO": "52", "BA": "29", "PE": "26", "MG": "31",
           "RJ": "33", "SC": "42", "ES": "32"}


def _dv(base43: str) -> str:
    soma, peso = 0, 2
    for digito in reversed(base43):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def chave(uf: str = "SP", numero: int = 1, *, aamm: str = "2610",
          cnpj: str = CNPJ_EMIT, modelo: str = "55") -> str:
    base = (f"{_COD_UF[uf]}{aamm}{cnpj}{modelo}001{numero:09d}1"
            f"{numero:08d}")
    return base + _dv(base)


def item(v_prod: str = "1000.00", *, grupo: str = "ICMS00", cst: str = "00",
         orig: str = "0", p_icms: str = "", v_icms: str = "", ncm: str = "39241000",
         cfop: str = "6102", descricao: str = "PRODUTO DE TESTE", extras: str = "",
         prod_extras: str = "", ipi: str = "") -> dict:
    return {"v_prod": v_prod, "grupo": grupo, "cst": cst, "orig": orig,
            "p_icms": p_icms, "v_icms": v_icms, "ncm": ncm, "cfop": cfop,
            "descricao": descricao, "extras": extras,
            "prod_extras": prod_extras, "ipi": ipi}


def _det(numero: int, it: dict) -> str:
    tag_cst = "CSOSN" if len(it["cst"]) == 3 else "CST"
    icms = f"<orig>{it['orig']}</orig>" if it["orig"] != "" else ""
    if it["cst"]:
        icms += f"<{tag_cst}>{it['cst']}</{tag_cst}>"
    if it["p_icms"]:
        icms += f"<vBC>{it['v_prod']}</vBC><pICMS>{it['p_icms']}</pICMS>"
    if it["v_icms"]:
        icms += f"<vICMS>{it['v_icms']}</vICMS>"
    icms += it["extras"]
    ipi = (f"<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vIPI>{it['ipi']}</vIPI>"
           f"</IPITrib></IPI>") if it["ipi"] else ""
    ncm = f"<NCM>{it['ncm']}</NCM>" if it["ncm"] else ""
    return f"""
      <det nItem="{numero}">
        <prod>
          <cProd>P{numero:03d}</cProd><xProd>{it['descricao']}</xProd>
          {ncm}<CFOP>{it['cfop']}</CFOP><uCom>UN</uCom>
          <qCom>1.0000</qCom><vUnCom>{it['v_prod']}</vUnCom>
          <vProd>{it['v_prod']}</vProd>{it['prod_extras']}
        </prod>
        <imposto>
          <ICMS><{it['grupo']}>{icms}</{it['grupo']}></ICMS>{ipi}
        </imposto>
      </det>"""


def xml_nfe(itens: list[dict], *, uf: str = "SP", numero: int = 1,
            uf_dest: str = "BA", cnpj_dest: str = CNPJ_DEST,
            data: str = "2026-10-05", crt: str = "3", fin: str = "1",
            tp_nf: str = "1", cstat: str = "100", modelo: str = "55",
            nome_dest: str = "COMERCIO FICTICIO LTDA",
            nome_emit: str = "FORNECEDOR FICTICIO SA") -> bytes:
    aamm = data[2:4] + data[5:7]
    ch = chave(uf, numero, aamm=aamm, modelo=modelo)
    dets = "".join(_det(i, it) for i, it in enumerate(itens, start=1))
    total = sum(float(it["v_prod"]) for it in itens)
    dest_doc = (f"<CNPJ>{cnpj_dest}</CNPJ>" if len(cnpj_dest) == 14
                else f"<CPF>{cnpj_dest}</CPF>")
    texto = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{ch}" versao="4.00">
      <ide>
        <cUF>{_COD_UF[uf]}</cUF><natOp>VENDA</natOp><mod>{modelo}</mod>
        <serie>1</serie><nNF>{numero}</nNF>
        <dhEmi>{data}T10:00:00-03:00</dhEmi><tpNF>{tp_nf}</tpNF>
        <idDest>2</idDest><finNFe>{fin}</finNFe>
      </ide>
      <emit>
        <CNPJ>{CNPJ_EMIT}</CNPJ><xNome>{nome_emit}</xNome>
        <enderEmit><xMun>CIDADE</xMun><UF>{uf}</UF></enderEmit>
        <IE>123456789</IE><CRT>{crt}</CRT>
      </emit>
      <dest>
        {dest_doc}<xNome>{nome_dest}</xNome>
        <enderDest><xMun>SALVADOR</xMun><UF>{uf_dest}</UF></enderDest>
      </dest>{dets}
      <total><ICMSTot><vProd>{total:.2f}</vProd><vNF>{total:.2f}</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><cStat>{cstat}</cStat></infProt></protNFe>
</nfeProc>
"""
    return texto.encode("utf-8")


def nota_sp_com_destaque(numero: int = 1, **kw) -> bytes:
    """Exemplo 1 da especificacao: SP, R$ 1.000,00, ICMS destacado R$ 70,00."""
    return xml_nfe([item(p_icms="7.00", v_icms="70.00")], uf="SP",
                   numero=numero, **kw)


def nota_go_sem_destaque(numero: int = 2, **kw) -> bytes:
    """Exemplo 2: GO, R$ 1.000,00, sem destaque (fornecedor do Simples)."""
    return xml_nfe([item(grupo="ICMSSN102", cst="102")], uf="GO",
                   numero=numero, crt="1", **kw)


def nota_importado_sem_destaque(numero: int = 3, **kw) -> bytes:
    """Exemplo 3: mercadoria importada (orig 1), sem destaque."""
    return xml_nfe([item(grupo="ICMSSN102", cst="102", orig="1")], uf="SP",
                   numero=numero, crt="1", **kw)
