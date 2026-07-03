"""Sanidade do diff em escala real: SPED x ele mesmo e x copia alterada."""

from __future__ import annotations

import os
import sys
import time
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.ferramentas.comparador_sped_sped import comparar_speds  # noqa: E402

SPED = r"C:\Users\brazil\Downloads\JB\052026E0001_I.txt"

t0 = time.perf_counter()
doc_a = ler_sped(SPED)
doc_b = ler_sped(SPED)
t1 = time.perf_counter()

# 1) SPED x ele mesmo -> zero divergencias
res = comparar_speds(doc_a, doc_b, "Original", "Original")
t2 = time.perf_counter()
r = res.resumo()
print("SPED x ele mesmo:", r)
assert r["divergentes"] == 0, "deveria ser 0 divergencias"
assert r["iguais"] == r["conciliadas"], "todas deveriam ser identicas"
assert r["apenas_em_a"] == 0 and r["apenas_em_b"] == 0

# 2) Altera 1 nota com itens na copia B e compara
alvo = next((n for n in doc_b.notas if n.itens), None)
assert alvo is not None, "nenhuma nota com itens"
cfop_orig = alvo.itens[0].cfop
alvo.valor_documento = alvo.valor_documento + Decimal("10.00")
alvo.itens[0].cfop = "9999"

res2 = comparar_speds(doc_a, doc_b, "Original", "Alterado")
r2 = res2.resumo()
print("SPED x copia alterada:", r2)
assert r2["divergentes"] == 1, f"esperado 1 divergente, obtido {r2['divergentes']}"
nota = res2.divergentes[0]
campos = {(d.nivel, d.campo): (d.valor_a, d.valor_b) for d in nota.diferencas}
assert ("nota", "Valor contabil") in campos, "faltou valor contabil"
assert campos.get(("item", "CFOP")) == (cfop_orig, "9999"), \
    f"cfop diff inesperado: {campos.get(('item', 'CFOP'))}"

print(f"\nOK - diff valido em escala real ({len(doc_a.notas)} notas).")
print(f"  Leitura de 2 SPEDs: {t1 - t0:.2f}s | comparacao: {t2 - t1:.2f}s")
print(f"  Nota alterada {nota.numero}: "
      + "; ".join(f"{d.campo} '{d.valor_a}'->'{d.valor_b}'" for d in nota.diferencas))
