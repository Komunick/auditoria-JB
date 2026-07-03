"""Testa a geracao de DANFE (PDF) a partir de um XML de NF-e completo."""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

CHAVE = "35260399888777000166550010000010011123456780"

XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{CHAVE}" versao="4.00">
      <ide>
        <cUF>35</cUF><cNF>12345678</cNF><natOp>VENDA</natOp><mod>55</mod>
        <serie>1</serie><nNF>1001</nNF><dhEmi>2026-05-05T10:00:00-03:00</dhEmi>
        <tpNF>1</tpNF><idDest>2</idDest><cMunFG>3550308</cMunFG>
        <tpImp>1</tpImp><tpEmis>1</tpEmis><cDV>0</cDV><tpAmb>1</tpAmb>
        <finNFe>1</finNFe><indFinal>1</indFinal><indPres>1</indPres>
        <procEmi>0</procEmi><verProc>1.0</verProc>
      </ide>
      <emit>
        <CNPJ>99888777000166</CNPJ><xNome>FORNECEDOR ALPHA LTDA</xNome>
        <xFant>ALPHA</xFant>
        <enderEmit>
          <xLgr>RUA DAS FLORES</xLgr><nro>100</nro><xBairro>CENTRO</xBairro>
          <cMun>3550308</cMun><xMun>SAO PAULO</xMun><UF>SP</UF><CEP>01000000</CEP>
          <cPais>1058</cPais><xPais>BRASIL</xPais><fone>1130000000</fone>
        </enderEmit>
        <IE>111111111111</IE><CRT>3</CRT>
      </emit>
      <dest>
        <CNPJ>11222333000181</CNPJ><xNome>EMPRESA TESTE LTDA</xNome>
        <enderDest>
          <xLgr>AV BRASIL</xLgr><nro>200</nro><xBairro>JARDIM</xBairro>
          <cMun>2927408</cMun><xMun>SALVADOR</xMun><UF>BA</UF><CEP>40000000</CEP>
          <cPais>1058</cPais><xPais>BRASIL</xPais>
        </enderDest>
        <indIEDest>1</indIEDest><IE>222222222222</IE>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>P001</cProd><cEAN>SEM GTIN</cEAN><xProd>PARAFUSO SEXTAVADO M8</xProd>
          <NCM>73181500</NCM><CFOP>5102</CFOP><uCom>UN</uCom>
          <qCom>100.0000</qCom><vUnCom>5.0000000000</vUnCom><vProd>500.00</vProd>
          <cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib><qTrib>100.0000</qTrib>
          <vUnTrib>5.0000000000</vUnTrib><indTot>1</indTot>
        </prod>
        <imposto>
          <ICMS><ICMS00>
            <orig>0</orig><CST>00</CST><modBC>3</modBC>
            <vBC>500.00</vBC><pICMS>18.00</pICMS><vICMS>90.00</vICMS>
          </ICMS00></ICMS>
          <PIS><PISAliq><CST>01</CST><vBC>500.00</vBC><pPIS>1.65</pPIS><vPIS>8.25</vPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><vBC>500.00</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>38.00</vCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <total>
        <ICMSTot>
          <vBC>500.00</vBC><vICMS>90.00</vICMS><vICMSDeson>0.00</vICMSDeson>
          <vFCP>0.00</vFCP><vBCST>0.00</vBCST><vST>0.00</vST>
          <vFCPST>0.00</vFCPST><vFCPSTRet>0.00</vFCPSTRet>
          <vProd>500.00</vProd><vFrete>0.00</vFrete><vSeg>0.00</vSeg>
          <vDesc>0.00</vDesc><vII>0.00</vII><vIPI>0.00</vIPI><vIPIDevol>0.00</vIPIDevol>
          <vPIS>8.25</vPIS><vCOFINS>38.00</vCOFINS><vOutro>0.00</vOutro><vNF>500.00</vNF>
        </ICMSTot>
      </total>
      <transp><modFrete>9</modFrete></transp>
      <pag><detPag><tPag>01</tPag><vPag>500.00</vPag></detPag></pag>
    </infNFe>
  </NFe>
  <protNFe versao="4.00"><infProt>
    <tpAmb>1</tpAmb><verAplic>SP_NFE</verAplic>
    <chNFe>{CHAVE}</chNFe>
    <dhRecbto>2026-05-05T10:05:00-03:00</dhRecbto><nProt>135260000000001</nProt>
    <digVal>YWJjZA==</digVal><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>
  </infProt></protNFe>
</nfeProc>
"""


def main() -> int:
    from auditoria_fiscal.ferramentas.danfe import gerar_danfe_pdf

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(XML)
        caminho_xml = fh.name
    pdf = os.path.join(tempfile.gettempdir(), "danfe_teste.pdf")

    try:
        gerar_danfe_pdf(caminho_xml, pdf)
    except Exception as exc:  # noqa: BLE001
        print("FALHA ao gerar DANFE:", type(exc).__name__, exc)
        return 1
    finally:
        os.unlink(caminho_xml)

    ok = os.path.exists(pdf) and os.path.getsize(pdf) > 1000
    tam = os.path.getsize(pdf) if os.path.exists(pdf) else 0
    if os.path.exists(pdf):
        os.unlink(pdf)
    if not ok:
        print(f"FALHA: PDF nao gerado corretamente (tamanho={tam})")
        return 1
    print(f"OK - DANFE gerado a partir do XML ({tam} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
