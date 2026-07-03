"""Teste do comparador de dois SPEDs (dados sinteticos, autocontido)."""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.ferramentas.comparador_sped_sped import comparar_speds  # noqa: E402
from auditoria_fiscal.ferramentas.relatorio_diff_excel import gerar_relatorio_diff  # noqa: E402


def ch(cnpj, nnf, cnf):
    c = f"352603{cnpj}55001{nnf}1{cnf}0"
    assert len(c) == 44
    return c


CH1 = ch("99888777000166", "000001001", "11111111")  # identica
CH2 = ch("99888777000166", "000002002", "22222222")  # divergente
CH3 = ch("99888777000166", "000003003", "33333333")  # so em A
CH4 = ch("99888777000166", "000004004", "44444444")  # so em B


def linha(reg, campos):
    maxpos = max([1] + list(campos))
    vals = [""] * (maxpos + 1)
    vals[1] = reg
    for p, v in campos.items():
        vals[p] = v
    return "|" + "|".join(vals[1:]) + "|"


def cab():
    return [
        linha("0000", {4: "01032026", 5: "31032026", 6: "EMPRESA TESTE LTDA",
                       7: "11222333000181", 9: "SP"}),
        linha("0150", {2: "F001", 3: "FORNECEDOR ALPHA LTDA", 5: "99888777000166"}),
        linha("0200", {2: "P001", 3: "PRODUTO UM", 8: "73181500"}),
        linha("0200", {2: "P002", 3: "PRODUTO DOIS", 8: "72104900"}),
    ]


def c100(num, chave, valor):
    return linha("C100", {2: "0", 3: "1", 4: "F001", 5: "55", 6: "00", 7: "1",
                          8: num, 9: chave, 10: "05032026", 11: "05032026",
                          12: valor, 16: "200,00"})


def item(numit, cod, cfop, cst, aliq, vicms, vitem="200,00"):
    return linha("C170", {2: numit, 3: cod, 4: cod, 5: "10,00", 6: "UN",
                          7: vitem, 10: cst, 11: cfop, 13: "200,00",
                          14: aliq, 15: vicms})


def sped_a():
    linhas = cab() + [
        c100("1001", CH1, "100,00"),
        item("1", "P001", "1102", "000", "18,00", "18,00", "100,00"),
        c100("2002", CH2, "200,00"),                       # valor 200
        item("1", "P001", "1102", "000", "18,00", "36,00"),  # sera alterado em B
        item("2", "P002", "1102", "000", "18,00", "9,00"),   # sera removido em B
        c100("3003", CH3, "300,00"),                       # so em A
    ]
    return "\r\n".join(linhas) + "\r\n"


def sped_b():
    linhas = cab() + [
        c100("1001", CH1, "100,00"),
        item("1", "P001", "1102", "000", "18,00", "18,00", "100,00"),
        c100("2002", CH2, "250,00"),                       # valor 250 (diverge)
        item("1", "P001", "5102", "020", "12,00", "30,00"),  # cfop/cst/aliq/icms
        # item 2 removido
        c100("4004", CH4, "400,00"),                       # so em B
    ]
    return "\r\n".join(linhas) + "\r\n"


def escrever(conteudo):
    fh = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="cp1252")
    fh.write(conteudo)
    fh.close()
    return fh.name


def main() -> int:
    ca = escrever(sped_a())
    cb = escrever(sped_b())
    try:
        doc_a = ler_sped(ca)
        doc_b = ler_sped(cb)
    finally:
        os.unlink(ca)
        os.unlink(cb)

    res = comparar_speds(doc_a, doc_b, "Contabilidade", "Cliente")
    r = res.resumo()

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    checar(r["total_a"] == 3, f"total_a: {r['total_a']}")
    checar(r["total_b"] == 3, f"total_b: {r['total_b']}")
    checar(r["conciliadas"] == 2, f"conciliadas: {r['conciliadas']}")
    checar(r["iguais"] == 1, f"iguais: {r['iguais']}")
    checar(r["divergentes"] == 1, f"divergentes: {r['divergentes']}")
    checar(r["apenas_em_a"] == 1, f"apenas_a: {r['apenas_em_a']}")
    checar(r["apenas_em_b"] == 1, f"apenas_b: {r['apenas_em_b']}")

    if res.divergentes:
        nota = res.divergentes[0]
        checar(nota.chave == CH2, f"chave divergente: {nota.chave}")
        campos = {(d.nivel, d.campo, d.num_item): (d.valor_a, d.valor_b)
                  for d in nota.diferencas}
        checar(("nota", "Valor contabil", "") in campos,
               "faltou diferenca de Valor contabil")
        checar(campos.get(("nota", "Valor contabil", "")) == ("200.00", "250.00"),
               f"valores contabil: {campos.get(('nota', 'Valor contabil', ''))}")
        checar(campos.get(("item", "CFOP", "1")) == ("1102", "5102"),
               f"cfop item: {campos.get(('item', 'CFOP', '1'))}")
        checar(campos.get(("item", "CST/CSOSN", "1")) == ("000", "020"),
               f"cst item: {campos.get(('item', 'CST/CSOSN', '1'))}")
        checar(("item", "Aliquota ICMS", "1") in campos, "faltou diferenca de aliquota")
        checar(("item", "Item so no arquivo A", "2") in campos,
               "faltou item removido (so em A)")

    # Exportacao
    fh = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    saida = fh.name
    fh.close()
    try:
        gerar_relatorio_diff(res, saida)
        checar(os.path.exists(saida) and os.path.getsize(saida) > 0, "excel vazio")
    finally:
        if os.path.exists(saida):
            os.unlink(saida)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1

    print("OK - comparador de SPEDs passou.")
    print("  Resumo:", r)
    print(f"  Nota divergente {res.divergentes[0].numero}: "
          f"{len(res.divergentes[0].diferencas)} campos divergentes")
    for d in res.divergentes[0].diferencas:
        alvo = f"item {d.num_item}" if d.nivel == "item" else "nota"
        print(f"    [{alvo}] {d.campo}: '{d.valor_a}' -> '{d.valor_b}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
