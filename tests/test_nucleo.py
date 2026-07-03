"""Testes do nucleo com um SPED sintetico (sem depender de amostra real).

Executar:  python -m tests.test_nucleo   (a partir da raiz do projeto)
ou via pytest, se instalado.
"""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

# Permite rodar sem instalar o pacote: adiciona src/ ao path.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402


def _linha(reg: str, campos: dict[int, str]) -> str:
    """Monta uma linha de SPED colocando cada valor na posicao do layout.

    campos: {posicao_layout: valor}. Posicao 1 = REG. Preenche vazios no meio.
    """
    maxpos = max([1] + list(campos.keys()))
    valores = [""] * (maxpos + 1)
    valores[1] = reg
    for pos, val in campos.items():
        valores[pos] = val
    # Junta com pipe nas bordas: |campo1|campo2|...|
    return "|" + "|".join(valores[1:]) + "|"


def _chave(cuf, aamm, cnpj, mod, serie, nnf, tpemis, cnf, dv) -> str:
    ch = f"{cuf}{aamm}{cnpj}{mod}{serie}{nnf}{tpemis}{cnf}{dv}"
    assert len(ch) == 44, f"chave com {len(ch)} digitos: {ch}"
    return ch


def construir_sped() -> str:
    chave1 = _chave("35", "2603", "99888777000166", "55", "001",
                    "000001001", "1", "12345678", "0")
    chave2 = _chave("35", "2603", "55666777000188", "55", "002",
                    "000002002", "1", "87654321", "0")

    linhas = [
        _linha("0000", {4: "01032026", 5: "31032026", 6: "EMPRESA TESTE LTDA",
                        7: "11222333000181", 9: "SP", 10: "111222333"}),
        _linha("0150", {2: "F001", 3: "FORNECEDOR ALPHA LTDA",
                        5: "99888777000166", 7: "9990001"}),
        _linha("0150", {2: "F002", 3: "FORNECEDOR BETA ME",
                        5: "55666777000188", 7: "8880002"}),
        _linha("0200", {2: "P001", 3: "PARAFUSO SEXTAVADO M8", 8: "73181500"}),
        _linha("0200", {2: "P002", 3: "CHAPA DE ACO 2MM", 8: "72104900"}),
        # Nota 1 - entrada de terceiros, regular
        _linha("C100", {2: "0", 3: "1", 4: "F001", 5: "55", 6: "00", 7: "1",
                        8: "1001", 9: chave1, 10: "05032026", 11: "06032026",
                        12: "1000,00", 14: "0,00", 16: "900,00", 18: "0,00",
                        21: "900,00", 22: "162,00", 25: "0,00",
                        26: "14,85", 27: "68,40"}),
        _linha("C170", {2: "1", 3: "P001", 4: "PARAFUSO SEXTAVADO M8",
                        5: "100,00", 6: "UN", 7: "500,00", 8: "0,00", 9: "0",
                        10: "000", 11: "1102", 13: "500,00", 14: "18,00",
                        15: "90,00", 25: "50", 30: "8,25", 31: "50",
                        36: "38,00"}),
        _linha("C170", {2: "2", 3: "P002", 4: "CHAPA DE ACO 2MM",
                        5: "20,00", 6: "KG", 7: "400,00", 8: "0,00", 9: "0",
                        10: "000", 11: "1102", 13: "400,00", 14: "18,00",
                        15: "72,00", 25: "50", 30: "6,60", 31: "50",
                        36: "30,40"}),
        # Nota 2 - entrada de terceiros, CANCELADA (situacao 02)
        _linha("C100", {2: "0", 3: "1", 4: "F002", 5: "55", 6: "02", 7: "2",
                        8: "2002", 9: chave2, 10: "10032026", 11: "10032026",
                        12: "500,00", 16: "500,00", 21: "500,00",
                        22: "90,00"}),
    ]
    return "\r\n".join(linhas) + "\r\n"


def main() -> int:
    conteudo = construir_sped()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="cp1252") as fh:
        fh.write(conteudo)
        caminho = fh.name

    try:
        doc = ler_sped(caminho)
    finally:
        os.unlink(caminho)

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    # Empresa
    checar(doc.empresa.cnpj == "11222333000181", f"CNPJ empresa: {doc.empresa.cnpj}")
    checar(doc.empresa.nome == "EMPRESA TESTE LTDA", f"nome: {doc.empresa.nome}")
    checar(doc.empresa.uf == "SP", f"UF: {doc.empresa.uf}")
    checar(str(doc.empresa.dt_inicial) == "2026-03-01", f"dt_ini: {doc.empresa.dt_inicial}")

    # Notas
    checar(len(doc.notas) == 2, f"qtd notas: {len(doc.notas)}")
    n1 = doc.notas[0]
    checar(len(n1.chave) == 44, f"chave n1 len: {len(n1.chave)}")
    checar(n1.numero == "1001", f"numero n1: {n1.numero}")
    checar(n1.valor_documento == Decimal("1000.00"), f"valor n1: {n1.valor_documento}")
    checar(n1.vl_icms == Decimal("162.00"), f"icms n1: {n1.vl_icms}")
    checar(n1.participante is not None and n1.participante.nome == "FORNECEDOR ALPHA LTDA",
           f"forn n1: {n1.participante}")
    checar(n1.cnpj_emitente == "99888777000166", f"emit n1: {n1.cnpj_emitente}")
    checar(not n1.cancelada, "n1 nao deveria estar cancelada")

    # Itens da nota 1
    checar(len(n1.itens) == 2, f"itens n1: {len(n1.itens)}")
    i1 = n1.itens[0]
    checar(i1.cod_item == "P001", f"cod_item i1: {i1.cod_item}")
    checar(i1.ncm == "73181500", f"ncm i1: {i1.ncm}")
    checar(i1.cfop == "1102", f"cfop i1: {i1.cfop}")
    checar(i1.cst_icms == "000", f"cst i1: {i1.cst_icms}")
    checar(i1.quantidade == Decimal("100.00"), f"qtd i1: {i1.quantidade}")
    checar(i1.valor_item == Decimal("500.00"), f"vl_item i1: {i1.valor_item}")
    checar(i1.valor_unitario == Decimal("5.00"), f"vl_unit i1: {i1.valor_unitario}")
    checar(i1.aliq_icms == Decimal("18.00"), f"aliq i1: {i1.aliq_icms}")

    # Nota 2 cancelada
    n2 = doc.notas[1]
    checar(n2.cancelada, "n2 deveria estar cancelada (situacao 02)")

    # Indice por chave
    idx = doc.por_chave()
    checar(len(idx) == 2, f"indice: {len(idx)}")

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - todos os testes do nucleo passaram.")
    print(f"  Empresa: {doc.empresa.nome} ({doc.empresa.cnpj}) - {doc.empresa.uf}")
    print(f"  Notas lidas: {len(doc.notas)}")
    for n in doc.notas:
        estado = "CANCELADA" if n.cancelada else "regular"
        print(f"    NF {n.numero} | chave {n.chave} | R$ {n.valor_documento} | "
              f"{len(n.itens)} itens | {estado}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
