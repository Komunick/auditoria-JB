"""Teste da vinculacao de XMLs a notas do SPED pela chave de acesso."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.modelos import (  # noqa: E402
    ItemNota, NotaFiscal, ORIGEM_SPED,
)
from auditoria_fiscal.core.nfe_xml import (  # noqa: E402
    associar_xmls, chave_do_xml, completar_itens_com_xmls, indexar_pasta_xml,
)

CHAVE_A = "35260399888777000166550010000010011123456780"
CHAVE_B = "29260311222333000181550010000020021765432109"
CHAVE_SEM_XML = "29260344555666000122550010000030031000000001"
CHAVE_FORA_SPED = "29260377888999000155550010000090091000000009"

MODELO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide><mod>55</mod><serie>1</serie><nNF>{numero}</nNF>
        <dhEmi>2026-03-05T10:00:00-03:00</dhEmi><tpNF>0</tpNF></ide>
      <emit><CNPJ>99888777000166</CNPJ><xNome>FORNECEDOR TESTE</xNome></emit>
      <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><cStat>100</cStat></infProt></protNFe>
</nfeProc>
"""

# XML com item detalhado e tpNF=1 (saida do EMITENTE): no fluxo combinado a
# nota do SPED que adotar estes itens NAO pode herdar o tpNF do fornecedor.
MODELO_XML_ITEM = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide><mod>55</mod><serie>1</serie><nNF>{numero}</nNF>
        <dhEmi>2026-03-05T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
      <emit><CNPJ>99888777000166</CNPJ><xNome>FORNECEDOR TESTE</xNome></emit>
      <det nItem="1">
        <prod><cProd>PX</cProd><xProd>PRODUTO DO XML</xProd><NCM>73181500</NCM>
          <CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.00</qCom><vUnCom>50.00</vUnCom>
          <vProd>100.00</vProd></prod>
        <imposto><ICMS><ICMS00><CST>00</CST><vBC>100.00</vBC><pICMS>18.00</pICMS>
          <vICMS>18.00</vICMS></ICMS00></ICMS></imposto>
      </det>
      <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><cStat>100</cStat></infProt></protNFe>
</nfeProc>
"""


def main() -> int:
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    pasta = tempfile.mkdtemp(prefix="xmls_")
    sub = os.path.join(pasta, "subpasta")
    os.makedirs(sub)
    try:
        arq_a = os.path.join(pasta, "nota_a.xml")
        arq_b = os.path.join(sub, "nota_b.xml")   # recursivo
        with open(arq_a, "w", encoding="utf-8") as fh:
            fh.write(MODELO_XML.format(chave=CHAVE_A, numero="1001"))
        with open(arq_b, "w", encoding="utf-8") as fh:
            fh.write(MODELO_XML.format(chave=CHAVE_B, numero="2002"))
        # Um XML que nao e NF-e deve ser ignorado sem erro.
        with open(os.path.join(pasta, "outro.xml"), "w", encoding="utf-8") as fh:
            fh.write("<raiz><nada/></raiz>")
        # Lixo nao-XML tambem nao pode derrubar a indexacao.
        with open(os.path.join(pasta, "quebrado.xml"), "w", encoding="utf-8") as fh:
            fh.write("isto nao e xml <<<")

        # chave_do_xml
        checar(chave_do_xml(arq_a) == CHAVE_A, f"chave A: {chave_do_xml(arq_a)}")
        checar(chave_do_xml(os.path.join(pasta, "outro.xml")) == "",
               "XML sem infNFe deveria dar chave vazia")

        # indexar_pasta_xml (inclui subpastas)
        indice = indexar_pasta_xml(pasta)
        checar(len(indice) == 2, f"indice deveria ter 2 chaves: {len(indice)}")
        checar(indice.get(CHAVE_B) == os.path.abspath(arq_b),
               f"caminho da chave B: {indice.get(CHAVE_B)}")

        # associar_xmls: notas vindas do SPED (sem xml_path)
        notas = [
            NotaFiscal(origem=ORIGEM_SPED, chave=CHAVE_A, numero="1001"),
            NotaFiscal(origem=ORIGEM_SPED, chave=CHAVE_B, numero="2002"),
            NotaFiscal(origem=ORIGEM_SPED, chave=CHAVE_SEM_XML, numero="3003"),
        ]
        associadas = associar_xmls(notas, pasta)
        checar(associadas == 2, f"associadas: {associadas} (esperado 2)")
        checar(notas[0].xml_path == os.path.abspath(arq_a),
               f"xml_path nota A: {notas[0].xml_path}")
        checar(notas[1].xml_path == os.path.abspath(arq_b),
               f"xml_path nota B: {notas[1].xml_path}")
        checar(notas[2].xml_path == "", "nota sem XML nao deveria ter xml_path")

        # Chamada repetida nao reassocia quem ja tem XML.
        checar(associar_xmls(notas, pasta) == 0, "reassociou indevidamente")
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    # ------------------------------------------------------------------
    # completar_itens_com_xmls (fluxo combinado): o SPED define as notas;
    # o XML preenche xml_path e da itens so a quem veio sem C170.
    pasta2 = tempfile.mkdtemp(prefix="xmls_comb_")
    try:
        for nome, chave, numero in [("a.xml", CHAVE_A, "1001"),
                                    ("b.xml", CHAVE_B, "2002"),
                                    ("fora.xml", CHAVE_FORA_SPED, "9009")]:
            with open(os.path.join(pasta2, nome), "w", encoding="utf-8") as fh:
                fh.write(MODELO_XML_ITEM.format(chave=chave, numero=numero))

        do_sped = [
            NotaFiscal(origem=ORIGEM_SPED, chave=CHAVE_A, numero="1001",
                       ind_oper="0",
                       itens=[ItemNota(cfop="1102", cst_icms="000")]),
            NotaFiscal(origem=ORIGEM_SPED, chave=CHAVE_B, numero="2002",
                       ind_oper="0"),
            NotaFiscal(origem=ORIGEM_SPED, chave=CHAVE_SEM_XML, numero="3003"),
        ]
        resumo = completar_itens_com_xmls(do_sped, pasta2)
        checar(resumo == {"com_xml": 2, "completadas": 1,
                          "sem_xml": 1, "ignorados": 1},
               f"contadores do combinado: {resumo}")

        nota_a, nota_b, nota_sem = do_sped
        # Nota COM C170: mantem os proprios itens (a declaracao e o que se
        # audita), mas ganha o xml_path para DANFE.
        checar(len(nota_a.itens) == 1 and nota_a.itens[0].cfop == "1102",
               f"itens do C170 nao deviam mudar: {nota_a.itens}")
        checar(nota_a.xml_path.endswith("a.xml"),
               f"xml_path nota A: {nota_a.xml_path}")
        # Nota SEM C170: adota os itens do XML, sem herdar o tpNF do emitente.
        checar(len(nota_b.itens) == 1 and nota_b.itens[0].cfop == "5102",
               f"itens do XML nao adotados: {nota_b.itens}")
        checar(nota_b.itens[0].descricao == "PRODUTO DO XML",
               f"descricao do item adotado: {nota_b.itens[0].descricao}")
        checar(nota_b.ind_oper == "0",
               f"ind_oper devia continuar o do SPED: {nota_b.ind_oper}")
        checar(nota_sem.xml_path == "" and not nota_sem.itens,
               "nota sem XML nao devia mudar")
    finally:
        shutil.rmtree(pasta2, ignore_errors=True)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - vinculacao de XMLs pela chave de acesso passou "
          "(associar_xmls e completar_itens_com_xmls).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
