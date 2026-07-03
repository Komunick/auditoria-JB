"""Inspeciona os arquivos reais para validar/ajustar os leitores."""

from __future__ import annotations

import os
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

import pandas as pd  # noqa: E402

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.core.sefaz_relacao import ler_relacao_sefaz  # noqa: E402

SPED = r"C:\Users\brazil\Downloads\JB\052026E0001_I.txt"
SEFAZ = r"C:\Users\brazil\Downloads\JB\PLANILHA AUDITORIA SEFAZ.xlsx"


def inspecionar_sped():
    print("=" * 70)
    print("SPED:", SPED)
    doc = ler_sped(SPED)
    e = doc.empresa
    print(f"Empresa: {e.nome} | CNPJ {e.cnpj} | {e.uf} | {e.dt_inicial} a {e.dt_final}")
    print(f"Total de notas (C100): {len(doc.notas)}")

    com_chave = [n for n in doc.notas if len(n.chave_normalizada) == 44]
    print(f"  com chave de 44 digitos: {len(com_chave)}")
    print("  por ind_oper:", dict(Counter(n.ind_oper for n in doc.notas)))
    print("  por modelo:", dict(Counter(n.modelo for n in doc.notas)))
    print("  por situacao:", dict(Counter(n.situacao for n in doc.notas)))
    total_itens = sum(len(n.itens) for n in doc.notas)
    print(f"  total de itens (C170): {total_itens}")

    entradas = [n for n in doc.notas if n.ind_oper == "0" and len(n.chave_normalizada) == 44]
    print(f"  entradas com chave: {len(entradas)}")
    print("  --- 3 primeiras entradas ---")
    for n in entradas[:3]:
        forn = n.participante.nome if n.participante else "(sem part.)"
        print(f"    NF {n.numero} serie {n.serie} | {n.dt_emissao} | R$ {n.valor_documento}"
              f" | {forn} | {len(n.itens)} itens | chave {n.chave[:10]}...")
    return doc


def inspecionar_sefaz():
    print("=" * 70)
    print("SEFAZ:", SEFAZ)
    # Visao crua das primeiras linhas
    bruto = pd.read_excel(SEFAZ, header=None, dtype=str)
    print("Dimensoes (linhas x colunas):", bruto.shape)
    print("--- primeiras 12 linhas (cruas) ---")
    for i in range(min(12, len(bruto))):
        celulas = [("" if c is None else str(c)) for c in bruto.iloc[i].tolist()]
        print(f"  [{i}]", " | ".join(celulas))

    print("--- leitura pelo leitor flexivel ---")
    registros, diag = ler_relacao_sefaz(SEFAZ)
    print("Linha de cabecalho detectada:", diag["linha_cabecalho"])
    print("Mapa de colunas:", diag["mapa_colunas"])
    print("Registros validos (com chave 44):", diag["registros_validos"],
          "de", diag["total_linhas_dados"], "linhas de dados")
    print("Situacoes encontradas:", dict(Counter(r.situacao for r in registros)))
    print("--- 3 primeiros registros ---")
    for r in registros[:3]:
        print(f"    NF {r.numero} | {r.dt_emissao} | R$ {r.valor} | {r.situacao}"
              f" | {r.emitente_nome} | chave {r.chave[:10]}...")
    return registros, diag


if __name__ == "__main__":
    try:
        inspecionar_sped()
    except Exception as exc:  # noqa: BLE001
        print("ERRO no SPED:", type(exc).__name__, exc)
    try:
        inspecionar_sefaz()
    except Exception as exc:  # noqa: BLE001
        print("ERRO na SEFAZ:", type(exc).__name__, exc)
