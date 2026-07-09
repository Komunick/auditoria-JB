"""Teste da vinculacao de XMLs a notas do SPED pela chave de acesso."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.modelos import NotaFiscal, ORIGEM_SPED  # noqa: E402
from auditoria_fiscal.core.nfe_xml import (  # noqa: E402
    associar_xmls, chave_do_xml, indexar_pasta_xml,
)

CHAVE_A = "35260399888777000166550010000010011123456780"
CHAVE_B = "29260311222333000181550010000020021765432109"
CHAVE_SEM_XML = "29260344555666000122550010000030031000000001"

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

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - vinculacao de XMLs pela chave de acesso passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
