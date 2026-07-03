"""Teste do motor de extracao de itens (dados sinteticos, autocontido)."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.ferramentas.extracao_itens import (  # noqa: E402
    CAMPOS, TITULOS, exportar_itens_excel, extrair_itens,
)


def linha(reg, campos):
    maxpos = max([1] + list(campos))
    vals = [""] * (maxpos + 1)
    vals[1] = reg
    for p, v in campos.items():
        vals[p] = v
    return "|" + "|".join(vals[1:]) + "|"


CHV = "35260399888777000166550010000010011123456780"


def montar_sped():
    linhas = [
        linha("0000", {4: "01032026", 5: "31032026", 6: "EMPRESA TESTE LTDA",
                       7: "11222333000181", 9: "SP"}),
        linha("0150", {2: "F001", 3: "FORNECEDOR ALPHA LTDA", 5: "99888777000166"}),
        linha("0200", {2: "P001", 3: "PARAFUSO SEXTAVADO M8", 8: "73181500"}),
        linha("0200", {2: "P002", 3: "CHAPA DE ACO 2MM", 8: "72104900"}),
        linha("C100", {2: "0", 3: "1", 4: "F001", 5: "55", 6: "00", 7: "1",
                       8: "1001", 9: CHV, 10: "05032026", 11: "05032026",
                       12: "900,00", 16: "900,00", 21: "900,00", 22: "162,00"}),
        linha("C170", {2: "1", 3: "P001", 4: "PARAFUSO SEXTAVADO M8", 5: "100,00",
                       6: "UN", 7: "500,00", 10: "000", 11: "1102", 13: "500,00",
                       14: "18,00", 15: "90,00", 25: "50", 30: "8,25", 31: "50",
                       36: "38,00"}),
        linha("C170", {2: "2", 3: "P002", 4: "CHAPA DE ACO 2MM", 5: "20,00",
                       6: "KG", 7: "400,00", 10: "000", 11: "1102", 13: "400,00",
                       14: "18,00", 15: "72,00"}),
    ]
    return "\r\n".join(linhas) + "\r\n"


def main() -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="cp1252") as fh:
        fh.write(montar_sped())
        caminho = fh.name
    try:
        doc = ler_sped(caminho)
    finally:
        os.unlink(caminho)

    linhas = extrair_itens(doc.notas)

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    checar(len(linhas) == 2, f"linhas: {len(linhas)} (esperado 2)")
    checar(len(CAMPOS) == len(TITULOS), "CAMPOS/TITULOS desalinhados")

    l1 = linhas[0]
    checar(l1["chave"] == CHV, f"chave: {l1['chave']}")
    checar(l1["numero"] == "1001", f"numero: {l1['numero']}")
    checar(l1["forn_nome"] == "FORNECEDOR ALPHA LTDA", f"forn: {l1['forn_nome']}")
    checar(l1["forn_cnpj"] == "99888777000166", f"cnpj: {l1['forn_cnpj']}")
    checar(l1["cod_item"] == "P001", f"cod: {l1['cod_item']}")
    checar(l1["ncm"] == "73181500", f"ncm: {l1['ncm']}")
    checar(l1["cfop"] == "1102", f"cfop: {l1['cfop']}")
    checar(l1["cst_icms"] == "000", f"cst: {l1['cst_icms']}")
    checar(l1["quantidade"] == Decimal("100.00"), f"qtd: {l1['quantidade']}")
    checar(l1["valor_unitario"] == Decimal("5.00"), f"unit: {l1['valor_unitario']}")
    checar(l1["operacao"] == "Entrada", f"oper: {l1['operacao']}")

    # Filtro por operacao
    entradas = extrair_itens(doc.notas, somente_operacao="0")
    saidas = extrair_itens(doc.notas, somente_operacao="1")
    checar(len(entradas) == 2, f"entradas: {len(entradas)}")
    checar(len(saidas) == 0, f"saidas: {len(saidas)}")

    # Exportacao
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
        saida = fh.name
    try:
        exportar_itens_excel(linhas, saida)
        checar(os.path.exists(saida) and os.path.getsize(saida) > 0, "excel vazio")
    finally:
        if os.path.exists(saida):
            os.unlink(saida)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - extracao de itens passou.")
    print(f"  {len(linhas)} itens | {len(TITULOS)} colunas")
    print(f"  Ex.: {l1['descricao']} | NCM {l1['ncm']} | CFOP {l1['cfop']} | "
          f"CST {l1['cst_icms']} | R$ {l1['valor_item']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
