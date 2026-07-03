"""Extrai os itens do SPED real e gera a planilha de auditoria (demo)."""

from __future__ import annotations

import os
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.ferramentas.extracao_itens import (  # noqa: E402
    exportar_itens_excel, extrair_itens,
)

SPED = r"C:\Users\brazil\Downloads\JB\052026E0001_I.txt"
SAIDA = os.path.join(RAIZ, "amostras", "exemplo_itens_auditoria.xlsx")

doc = ler_sped(SPED)
linhas = extrair_itens(doc.notas)
print(f"Empresa: {doc.empresa.nome}")
print(f"Notas: {len(doc.notas)} | Itens extraidos (C170): {len(linhas)}")

# Distribuicoes uteis para auditoria
print("Top CFOP:", Counter(l["cfop"] for l in linhas).most_common(5))
print("Top CST/CSOSN:", Counter(l["cst_icms"] for l in linhas).most_common(5))
print("Top NCM:", Counter(l["ncm"] for l in linhas).most_common(5))

print("--- 3 primeiros itens ---")
for l in linhas[:3]:
    print(f"  NF {l['numero']} | {l['descricao'][:30]:30} | NCM {l['ncm']} | "
          f"CFOP {l['cfop']} | CST {l['cst_icms']} | qtd {l['quantidade']} | "
          f"R$ {l['valor_item']}")

os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
exportar_itens_excel(linhas, SAIDA)
print("Planilha de auditoria gerada:", SAIDA)
