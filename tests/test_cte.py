"""Leitura de CT-e (modelo 57) mapeada para o modelo NotaFiscal.

Verifica: um CT-e vira uma NotaFiscal (mod 57) com um item sintetico de frete
(CFOP/CST/aliquota/valor); a pasta de XMLs mistura NF-e e CT-e sem perder
nenhum; e a extracao de itens gera a linha do servico. Dados sinteticos.
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.cte_xml import ler_xml_cte  # noqa: E402
from auditoria_fiscal.core.nfe_xml import (  # noqa: E402
    chave_do_xml,
    ler_pasta_xml,
)
from auditoria_fiscal.ferramentas.extracao_itens import extrair_itens  # noqa: E402
from test_xml import CHAVE, XML  # noqa: E402


CHAVE_CTE = "29260703571231000143570030003496881791035302"

CTE = f"""<?xml version="1.0" encoding="UTF-8"?>
<cteProc versao="4.00" xmlns="http://www.portalfiscal.inf.br/cte">
 <CTe xmlns="http://www.portalfiscal.inf.br/cte">
  <infCte versao="4.00" Id="CTe{CHAVE_CTE}">
   <ide>
    <cUF>29</cUF><CFOP>6932</CFOP>
    <natOp>Prestacao de servico de transporte</natOp>
    <mod>57</mod><serie>3</serie><nCT>349688</nCT>
    <dhEmi>2026-07-06T08:46:44-03:00</dhEmi>
    <UFIni>GO</UFIni><UFFim>TO</UFFim>
   </ide>
   <emit><CNPJ>03571231000143</CNPJ><IE>123456</IE>
    <xNome>BRAZIL TRANSPORTS LTDA</xNome><enderEmit><UF>BA</UF></enderEmit>
   </emit>
   <vPrest><vTPrest>150.00</vTPrest><vRec>150.00</vRec></vPrest>
   <imp><ICMS><ICMS00>
     <CST>00</CST><vBC>150.00</vBC><pICMS>12.00</pICMS><vICMS>18.00</vICMS>
   </ICMS00></ICMS></imp>
  </infCte>
 </CTe>
 <protCTe><infProt><cStat>100</cStat></infProt></protCTe>
</cteProc>
"""


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="cte_teste_")
    caminho_cte = os.path.join(tmp, "cte.xml")
    with open(caminho_cte, "w", encoding="utf-8") as saida:
        saida.write(CTE)

    # ------------------------------------------------------------------
    # Leitura direta do CT-e
    nota = ler_xml_cte(caminho_cte)
    checar(nota is not None, "CT-e deveria ser lido")
    checar(nota.modelo == "57", f"modelo deveria ser 57: {nota.modelo}")
    checar(nota.numero == "349688", f"numero: {nota.numero}")
    checar(nota.serie == "3", f"serie: {nota.serie}")
    checar(nota.chave_normalizada == CHAVE_CTE,
           f"chave: {nota.chave_normalizada}")
    checar(nota.cnpj_emitente == "03571231000143",
           f"cnpj emitente (da chave): {nota.cnpj_emitente}")
    checar(nota.uf_origem == "BA", f"uf (da chave): {nota.uf_origem}")
    checar(nota.participante and "BRAZIL TRANSPORTS" in nota.participante.nome,
           "fornecedor deveria ser a transportadora (emit)")
    checar(str(nota.valor_documento) == "150.00",
           f"valor do servico: {nota.valor_documento}")
    checar(str(nota.vl_icms) == "18.00", f"vl_icms: {nota.vl_icms}")

    # Item sintetico do frete
    checar(len(nota.itens) == 1, f"CT-e deveria ter 1 item: {len(nota.itens)}")
    item = nota.itens[0]
    checar(item.cfop == "6932", f"cfop do item: {item.cfop}")
    checar(item.cst_icms == "00", f"cst do item: {item.cst_icms}")
    checar(str(item.aliq_icms) == "12.00", f"aliquota: {item.aliq_icms}")
    checar(str(item.valor_item) == "150.00", f"valor do item: {item.valor_item}")
    checar("transporte" in item.descricao.lower(),
           f"descricao do item: {item.descricao!r}")

    # ------------------------------------------------------------------
    # Pasta mista: NF-e + CT-e no mesmo diretorio, nenhum perdido
    with open(os.path.join(tmp, "nfe.xml"), "w", encoding="utf-8") as saida:
        saida.write(XML if isinstance(XML, str) else XML.decode())
    notas = ler_pasta_xml(tmp)
    checar(len(notas) == 2, f"pasta mista deveria ter 2 notas: {len(notas)}")
    modelos = sorted(n.modelo for n in notas)
    checar(modelos == ["55", "57"],
           f"deveria ter uma NF-e (55) e um CT-e (57): {modelos}")

    # chave_do_xml reconhece os dois tipos
    checar(chave_do_xml(caminho_cte) == CHAVE_CTE, "chave_do_xml do CT-e")
    checar(chave_do_xml(os.path.join(tmp, "nfe.xml")) == CHAVE,
           "chave_do_xml da NF-e continua funcionando")

    # ------------------------------------------------------------------
    # Extracao de itens inclui a linha do CT-e
    linhas = extrair_itens(notas)
    checar(len(linhas) >= 2,
           f"extracao deveria ter itens da NF-e e do CT-e: {len(linhas)}")
    linha_cte = next((l for l in linhas if l["modelo"] == "57"), None)
    checar(linha_cte is not None, "extracao deveria ter a linha do CT-e")
    checar(linha_cte["cfop"] == "6932" and str(linha_cte["valor_item"]) == "150.00",
           f"linha do CT-e: {linha_cte['cfop']} / {linha_cte['valor_item']}")

    print("OK - leitura de CT-e (mod 57): nota + item sintetico de frete, "
          "pasta mista NF-e/CT-e, chave e extracao de itens passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
