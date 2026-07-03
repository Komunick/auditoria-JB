"""Teste ponta-a-ponta: SPED x relacao SEFAZ -> resultado -> relatorio Excel."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from openpyxl import Workbook  # noqa: E402

from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.core.sefaz_relacao import ler_relacao_sefaz  # noqa: E402
from auditoria_fiscal.ferramentas.comparador_sped_sefaz import comparar  # noqa: E402
from auditoria_fiscal.ferramentas.relatorio_excel import gerar_relatorio  # noqa: E402


def chave(cnpj, nnf, cnf):
    ch = f"352603{cnpj}55001{nnf}1{cnf}0"
    assert len(ch) == 44, f"{len(ch)}: {ch}"
    return ch


CH_A = chave("99888777000166", "000001001", "11111111")  # ambos, ok
CH_B = chave("55666777000188", "000002002", "22222222")  # so SEFAZ -> faltante
CH_C = chave("44555666000177", "000003003", "33333333")  # cancelada SEFAZ, escriturada
CH_D = chave("33444555000199", "000004004", "44444444")  # divergencia de valor
CH_E = chave("22333444000155", "000005005", "55555555")  # so SPED, SAIDA (ignorada)
CH_F = chave("11222333000144", "000006006", "66666666")  # so SPED, entrada -> info


def linha(reg, campos):
    maxpos = max([1] + list(campos))
    vals = [""] * (maxpos + 1)
    vals[1] = reg
    for p, v in campos.items():
        vals[p] = v
    return "|" + "|".join(vals[1:]) + "|"


def montar_sped():
    def c100(cod_part, sit, num, chv, valor, ind_oper="0"):
        return linha("C100", {2: ind_oper, 3: "1", 4: cod_part, 5: "55", 6: sit,
                              7: "1", 8: num, 9: chv, 10: "05032026",
                              11: "05032026", 12: valor, 16: valor, 21: valor})
    linhas = [
        linha("0000", {4: "01032026", 5: "31032026", 6: "EMPRESA TESTE LTDA",
                       7: "11222333000181", 9: "SP"}),
        linha("0150", {2: "P_A", 3: "FORNECEDOR ALPHA LTDA", 5: "99888777000166"}),
        linha("0150", {2: "P_C", 3: "FORNECEDOR GAMA LTDA", 5: "44555666000177"}),
        linha("0150", {2: "P_D", 3: "FORNECEDOR DELTA LTDA", 5: "33444555000199"}),
        c100("P_A", "00", "1001", CH_A, "1000,00"),
        c100("P_C", "00", "3003", CH_C, "300,00"),        # regular no SPED
        c100("P_D", "00", "4004", CH_D, "850,00"),        # SPED 850 vs SEFAZ 800
        c100("", "00", "5005", CH_E, "700,00", ind_oper="1"),  # SAIDA - ignorada
        c100("", "00", "6006", CH_F, "600,00"),           # entrada, so SPED
    ]
    return "\r\n".join(linhas) + "\r\n"


def montar_sefaz_xlsx(caminho):
    wb = Workbook()
    ws = wb.active
    # Linha de titulo antes do cabecalho (para testar a deteccao).
    ws.append(["Relacao de NF-e emitidas contra o CNPJ 11.222.333/0001-81"])
    ws.append(["Chave de Acesso", "Numero", "Serie", "CNPJ Emitente",
               "Razao Social", "Data Emissao", "Valor Total", "Situacao"])
    ws.append([CH_A, "1001", "1", "99888777000166", "FORNECEDOR ALPHA LTDA",
               "05/03/2026", "1000,00", "Autorizada"])
    ws.append([CH_B, "2002", "1", "55666777000188", "FORNECEDOR BETA ME",
               "07/03/2026", "500,00", "Autorizada"])
    ws.append([CH_C, "3003", "1", "44555666000177", "FORNECEDOR GAMA LTDA",
               "08/03/2026", "300,00", "Cancelada"])
    ws.append([CH_D, "4004", "1", "33444555000199", "FORNECEDOR DELTA LTDA",
               "09/03/2026", "800,00", "Autorizada"])
    ws.append(["", "", "", "", "", "TOTAL", "2600,00", ""])  # rodape sem chave
    wb.save(caminho)


def main() -> int:
    tmp = tempfile.mkdtemp()
    caminho_sped = os.path.join(tmp, "sped.txt")
    caminho_sefaz = os.path.join(tmp, "sefaz.xlsx")
    caminho_rel = os.path.join(tmp, "relatorio.xlsx")

    with open(caminho_sped, "w", encoding="cp1252") as fh:
        fh.write(montar_sped())
    montar_sefaz_xlsx(caminho_sefaz)

    doc = ler_sped(caminho_sped)
    registros, diag = ler_relacao_sefaz(caminho_sefaz)
    resultado = comparar(doc, registros)

    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    # Diagnostico da leitura SEFAZ
    checar(diag["linha_cabecalho"] == 1, f"linha cabecalho: {diag['linha_cabecalho']}")
    checar("chave" in diag["mapa_colunas"], f"mapa: {diag['mapa_colunas']}")
    checar(len(registros) == 4, f"registros SEFAZ: {len(registros)} (esperado 4, rodape ignorado)")

    r = resultado.resumo()
    checar(r["notas_na_sefaz"] == 4, f"sefaz: {r}")
    checar(r["notas_no_sped"] == 4, f"sped entradas (A,C,D,F): {r}")
    checar(r["conciliadas"] == 3, f"conciliadas (A,C,D): {r}")
    checar(r["faltantes_no_sped"] == 1, f"faltantes: {r}")
    checar(r["canceladas_escrituradas"] == 1, f"canceladas: {r}")
    checar(r["divergencias_valor"] == 1, f"divergencias: {r}")
    checar(r["apenas_no_sped"] == 1, f"apenas sped (F): {r}")

    # Detalhes
    if resultado.faltantes_no_sped:
        checar(resultado.faltantes_no_sped[0].chave_normalizada == CH_B,
               f"faltante deveria ser B: {resultado.faltantes_no_sped[0].chave}")
    if resultado.divergencias_valor:
        d = resultado.divergencias_valor[0]
        checar(d.chave == CH_D, f"divergencia deveria ser D: {d.chave}")
        checar(d.diferenca == Decimal("50.00"), f"diferenca: {d.diferenca}")
    if resultado.canceladas_escrituradas:
        checar(resultado.canceladas_escrituradas[0].chave == CH_C,
               f"cancelada deveria ser C: {resultado.canceladas_escrituradas[0].chave}")

    # Gera o relatorio Excel
    gerar_relatorio(resultado, caminho_rel, nome_empresa=doc.empresa.nome)
    checar(os.path.exists(caminho_rel), "relatorio nao gerado")
    checar(os.path.getsize(caminho_rel) > 0, "relatorio vazio")

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        print("\nDiagnostico SEFAZ:", diag)
        return 1

    print("OK - comparador SPED x SEFAZ passou.")
    print("  Diagnostico SEFAZ:", diag["mapa_colunas"])
    print("  Resumo:", r)
    print("  Faltante no SPED:", resultado.faltantes_no_sped[0].numero,
          "-", resultado.faltantes_no_sped[0].emitente_nome)
    print("  Relatorio Excel gerado:", caminho_rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
