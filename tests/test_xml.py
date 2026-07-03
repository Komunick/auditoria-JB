"""Teste do leitor de XML da NF-e com um procNFe sintetico."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.nfe_xml import ler_xml_nfe  # noqa: E402

CHAVE = "35260399888777000166550010000010011123456780"

XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{CHAVE}" versao="4.00">
      <ide>
        <cUF>35</cUF><natOp>VENDA</natOp><mod>55</mod><serie>1</serie>
        <nNF>1001</nNF><dhEmi>2026-03-05T10:00:00-03:00</dhEmi>
        <tpNF>1</tpNF>
      </ide>
      <emit>
        <CNPJ>99888777000166</CNPJ><xNome>FORNECEDOR ALPHA LTDA</xNome>
        <IE>9990001</IE>
        <enderEmit><UF>SP</UF></enderEmit>
      </emit>
      <dest>
        <CNPJ>11222333000181</CNPJ><xNome>EMPRESA TESTE LTDA</xNome>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>P001</cProd><xProd>PARAFUSO SEXTAVADO M8</xProd>
          <NCM>73181500</NCM><CFOP>5102</CFOP><uCom>UN</uCom>
          <qCom>100.00</qCom><vUnCom>5.00</vUnCom><vProd>500.00</vProd>
        </prod>
        <imposto>
          <ICMS><ICMS00>
            <CST>00</CST><vBC>500.00</vBC><pICMS>18.00</pICMS><vICMS>90.00</vICMS>
          </ICMS00></ICMS>
          <PIS><PISAliq><CST>01</CST><vPIS>8.25</vPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><vCOFINS>38.00</vCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <det nItem="2">
        <prod>
          <cProd>P002</cProd><xProd>CHAPA DE ACO 2MM</xProd>
          <NCM>72104900</NCM><CFOP>5102</CFOP><uCom>KG</uCom>
          <qCom>20.00</qCom><vUnCom>20.00</vUnCom><vProd>400.00</vProd>
        </prod>
        <imposto>
          <ICMS><ICMS00>
            <CST>00</CST><vBC>400.00</vBC><pICMS>18.00</pICMS><vICMS>72.00</vICMS>
          </ICMS00></ICMS>
        </imposto>
      </det>
      <total>
        <ICMSTot>
          <vBC>900.00</vBC><vICMS>162.00</vICMS><vProd>900.00</vProd>
          <vNF>900.00</vNF><vPIS>8.25</vPIS><vCOFINS>38.00</vCOFINS>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
  <protNFe><infProt><cStat>100</cStat></infProt></protNFe>
</nfeProc>
"""


def main() -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(XML)
        caminho = fh.name
    try:
        nota = ler_xml_nfe(caminho)
    finally:
        os.unlink(caminho)

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    checar(nota is not None, "nota nao lida")
    if nota is None:
        print("FALHA: nota None")
        return 1

    checar(nota.chave == CHAVE, f"chave: {nota.chave}")
    checar(nota.numero == "1001", f"numero: {nota.numero}")
    checar(nota.modelo == "55", f"modelo: {nota.modelo}")
    checar(nota.ind_oper == "1", f"ind_oper (saida): {nota.ind_oper}")
    checar(nota.participante.nome == "FORNECEDOR ALPHA LTDA", f"emit: {nota.participante}")
    checar(nota.cnpj_emitente == "99888777000166", f"cnpj emit: {nota.cnpj_emitente}")
    checar(nota.valor_documento == Decimal("900.00"), f"vNF: {nota.valor_documento}")
    checar(nota.vl_icms == Decimal("162.00"), f"vICMS: {nota.vl_icms}")
    checar(str(nota.dt_emissao) == "2026-03-05", f"dt: {nota.dt_emissao}")
    checar(not nota.cancelada, "nao deveria estar cancelada (cStat 100)")

    checar(len(nota.itens) == 2, f"itens: {len(nota.itens)}")
    i1 = nota.itens[0]
    checar(i1.cod_item == "P001", f"cod: {i1.cod_item}")
    checar(i1.ncm == "73181500", f"ncm: {i1.ncm}")
    checar(i1.cfop == "5102", f"cfop: {i1.cfop}")
    checar(i1.cst_icms == "00", f"cst: {i1.cst_icms}")
    checar(i1.aliq_icms == Decimal("18.00"), f"aliq: {i1.aliq_icms}")
    checar(i1.vl_icms == Decimal("90.00"), f"vicms: {i1.vl_icms}")
    checar(i1.valor_item == Decimal("500.00"), f"vprod: {i1.valor_item}")

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - leitor de XML da NF-e passou.")
    print(f"  NF {nota.numero} | {nota.participante.nome} | R$ {nota.valor_documento} | "
          f"{len(nota.itens)} itens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
