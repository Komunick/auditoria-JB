"""Teste do gerador de SPED corrigido (C170, C190 e contadores)."""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.composicao_fiscal import compor_nota  # noqa: E402
from auditoria_fiscal.core.correcoes import (  # noqa: E402
    Correcao, aplicar_correcoes,
)
from auditoria_fiscal.core.sped_parser import ler_sped  # noqa: E402
from auditoria_fiscal.ferramentas.sped_corrigido import (  # noqa: E402
    gerar_sped_corrigido,
)

CHAVE = "29260399888777000166550010000010011123456780"

# Nota com 2 itens de CFOPs 1102 e 1101 (mesmo CST/aliquota): a correcao
# 1102 -> 1101 deve mesclar os dois C190 num so.
LINHAS = [
    "|0000|017|0|01032026|31032026|EMPRESA TESTE LTDA|11222333000181||BA|123||A|1|",
    "|0001|0|",
    "|0150|F001|FORNECEDOR ALPHA||99888777000166||9990001|2927408||||",
    "|0990|4|",
    "|C001|0|",
    f"|C100|0|1|F001|55|00|1|1001|{CHAVE}|05032026|06032026|500,00|1|0,00||500,00|9|||500,00|90,00|||||0,00|0,00|",
    "|C170|1|P001|ITEM A|10,00|UN|200,00|0,00|0|000|1102||200,00|18,00|36,00|0,00|0,00|0,00|||0,00|||0,00|||0,00||0,00|||0,00||0,00|",
    "|C170|2|P002|ITEM B|20,00|UN|300,00|0,00|0|000|1101||300,00|18,00|54,00|0,00|0,00|0,00|||0,00|||0,00|||0,00||0,00|||0,00||0,00|",
    "|C190|000|1102|18,00|200,00|200,00|36,00|0,00|0,00|0,00|0,00||",
    "|C190|000|1101|18,00|300,00|300,00|54,00|0,00|0,00|0,00|0,00||",
    "|C990|7|",
    "|9001|0|",
    "|9900|0000|1|",
    "|9900|0001|1|",
    "|9900|0150|1|",
    "|9900|0990|1|",
    "|9900|C001|1|",
    "|9900|C100|1|",
    "|9900|C170|2|",
    "|9900|C190|2|",
    "|9900|C990|1|",
    "|9900|9001|1|",
    "|9900|9900|13|",
    "|9900|9990|1|",
    "|9900|9999|1|",
    "|9990|16|",
    "|9999|27|",
]


def _escrever_sped(caminho: str) -> None:
    with open(caminho, "w", encoding="latin-1", newline="") as fh:
        fh.write("\r\n".join(LINHAS) + "\r\n")


def _campos(linha: str) -> list[str]:
    return linha.split("|")


def main() -> int:
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    base = tempfile.mkdtemp(prefix="sped_")
    original = os.path.join(base, "original.txt")
    corrigido = os.path.join(base, "corrigido.txt")
    _escrever_sped(original)

    correcao = Correcao(id=1, chave=CHAVE, campo="cfop",
                        valor_original="1102", valor_corrigido="1101",
                        usuario="ana", data_hora="09/07/2026 10:00")

    # ---- Sem correcoes: arquivo identico ----
    resumo0 = gerar_sped_corrigido(original, corrigido, {})
    with open(original, "rb") as fh:
        bruto_orig = fh.read()
    with open(corrigido, "rb") as fh:
        bruto_igual = fh.read()
    checar(bruto_orig == bruto_igual,
           "sem correcoes o arquivo deveria ser identico")
    checar(resumo0.itens_c170_alterados == 0, "resumo0 sem alteracoes")

    # ---- Correcao de CFOP: C170 + C190 mesclado + contadores ----
    resumo = gerar_sped_corrigido(original, corrigido, {CHAVE: [correcao]})
    checar(resumo.itens_c170_alterados == 1,
           f"C170 alterados: {resumo.itens_c170_alterados}")
    checar(resumo.c190_mesclados == 1,
           f"C190 mesclados: {resumo.c190_mesclados}")
    checar(resumo.notas_alteradas == 1, "notas alteradas")

    with open(corrigido, encoding="latin-1") as fh:
        linhas = fh.read().splitlines()

    c170 = [l for l in linhas if l.startswith("|C170|")]
    checar(all(_campos(l)[11] == "1101" for l in c170),
           f"CFOP dos C170: {[_campos(l)[11] for l in c170]}")

    c190 = [l for l in linhas if l.startswith("|C190|")]
    checar(len(c190) == 1, f"C190 deveria mesclar em 1 (veio {len(c190)})")
    if len(c190) == 1:
        c = _campos(c190[0])
        checar(c[3] == "1101", f"CFOP do C190: {c[3]}")
        checar(c[5] == "500,00" and c[6] == "500,00" and c[7] == "90,00",
               f"somas do C190: opr={c[5]} bc={c[6]} icms={c[7]}")

    # Sem duplicidade de registros: chaves de grupo unicas
    grupos = [tuple(_campos(l)[2:5]) for l in c190]
    checar(len(grupos) == len(set(grupos)), "grupos C190 duplicados")

    # Contadores recalculados
    total = len(linhas)
    c990 = next(l for l in linhas if l.startswith("|C990|"))
    checar(_campos(c990)[2] == str(
        sum(1 for l in linhas if _campos(l)[1].startswith("C"))),
        f"C990: {c990}")
    l9900_c190 = next(l for l in linhas if l.startswith("|9900|C190|"))
    checar(_campos(l9900_c190)[3] == "1", f"9900 C190: {l9900_c190}")
    l9999 = next(l for l in linhas if l.startswith("|9999|"))
    checar(_campos(l9999)[2] == str(total), f"9999: {l9999} (total {total})")

    # ---- Cenario 7: consistencia entre SPED, tela e PDFs ----
    # O SPED corrigido relido pelo parser produz a MESMA composicao da nota
    # corrigida em memoria (que alimenta a tela e os PDFs).
    doc = ler_sped(corrigido)
    nota_sped = doc.notas[0]
    doc_orig = ler_sped(original)
    nota_memoria = aplicar_correcoes(doc_orig.notas[0], [correcao])
    comp_sped = compor_nota(nota_sped)
    comp_mem = compor_nota(nota_memoria)
    grupos_sped = [(g.cfop, g.cst, g.aliquota, g.valor_contabil, g.vl_icms)
                   for g in comp_sped.grupos]
    grupos_mem = [(g.cfop, g.cst, g.aliquota, g.valor_contabil, g.vl_icms)
                  for g in comp_mem.grupos]
    checar(grupos_sped == grupos_mem,
           f"composicao divergente:\n  SPED: {grupos_sped}\n  mem:  {grupos_mem}")
    checar(grupos_sped and grupos_sped[0][0] == "1101"
           and grupos_sped[0][3] == Decimal("500.00"),
           f"grupo esperado 1101/500,00: {grupos_sped}")

    # ---- Correcao de aliquota nao vai ao SPED (ignorada com aviso) ----
    corr_aliq = Correcao(id=2, chave=CHAVE, campo="aliq_icms",
                         valor_original="18", valor_corrigido="20,50",
                         usuario="ana", data_hora="x")
    resumo2 = gerar_sped_corrigido(original, corrigido, {CHAVE: [corr_aliq]})
    checar(len(resumo2.ignoradas) == 1 and resumo2.itens_c170_alterados == 0,
           f"aliquota deveria ser ignorada: {resumo2.ignoradas}")
    with open(corrigido, "rb") as fh:
        checar(fh.read() == bruto_orig,
               "aliquota ignorada: arquivo deveria ficar identico")

    # ---- Correcao revertida nao e aplicada ----
    correcao.status = "revertida"
    resumo3 = gerar_sped_corrigido(original, corrigido, {CHAVE: [correcao]})
    checar(resumo3.itens_c170_alterados == 0, "revertida nao pode aplicar")

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - SPED corrigido (C170, C190 mesclado, contadores, consistencia).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
