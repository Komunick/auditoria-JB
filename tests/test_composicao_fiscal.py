"""Teste do agrupamento fiscal por CFOP -> CST -> aliquota (Decimal)."""

from __future__ import annotations

import os
import sys
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.composicao_fiscal import compor_nota  # noqa: E402
from auditoria_fiscal.core.modelos import ItemNota, NotaFiscal  # noqa: E402
from auditoria_fiscal.core.utils import (  # noqa: E402
    formatar_cfop, formatar_moeda, formatar_percentual,
)

D = Decimal


def _item(cfop, cst, aliq, valor, bc=None, icms=None, **kw):
    return ItemNota(cfop=cfop, cst_icms=cst, aliq_icms=D(aliq),
                    valor_item=D(valor),
                    vl_bc_icms=D(bc) if bc is not None else D("0"),
                    vl_icms=D(icms) if icms is not None else D("0"), **kw)


def main() -> int:
    falhas = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    # ---- Formatadores (padrao brasileiro) ----
    checar(formatar_moeda(D("1234.56"), True) == "R$ 1.234,56",
           f"moeda: {formatar_moeda(D('1234.56'), True)}")
    checar(formatar_percentual(D("20.5")) == "20,50%",
           f"percentual: {formatar_percentual(D('20.5'))}")
    checar(formatar_cfop("1102") == "1.102", f"cfop: {formatar_cfop('1102')}")

    # ---- Cenario 1: uma unica combinacao CFOP/CST/aliquota ----
    nota1 = NotaFiscal(chave="1" * 44, valor_documento=D("200.00"),
                       valor_mercadoria=D("200.00"),
                       itens=[_item("1102", "000", "20.50", "200.00",
                                    "200.00", "41.00")])
    c1 = compor_nota(nota1)
    checar(len(c1.grupos) == 1, f"cenario1 grupos: {len(c1.grupos)}")
    g = c1.grupos[0]
    checar(g.valor_contabil == D("200.00") and g.vl_bc_icms == D("200.00")
           and g.aliquota == D("20.50") and g.vl_icms == D("41.00"),
           f"cenario1 valores: {g}")
    checar(not c1.alertas, f"cenario1 nao deveria alertar: {c1.alertas}")

    # ---- Cenario 2: duas combinacoes de CFOP e CST (nota de 500) ----
    nota2 = NotaFiscal(chave="2" * 44, valor_documento=D("500.00"),
                       valor_mercadoria=D("500.00"),
                       itens=[
                           _item("1403", "060", "0", "300.00"),
                           _item("1102", "000", "20.50", "200.00",
                                 "200.00", "41.00"),
                       ])
    c2 = compor_nota(nota2)
    checar(len(c2.grupos) == 2, f"cenario2 grupos: {len(c2.grupos)}")
    checar(c2.grupos[0].cfop == "1102" and c2.grupos[1].cfop == "1403",
           "cenario2 ordenacao por CFOP")
    checar(not c2.grupos[1].tem_icms, "1403/060 nao deveria ter ICMS")
    checar(c2.soma_valor_contabil == D("500.00"),
           f"cenario2 soma: {c2.soma_valor_contabil}")
    checar(not c2.alertas, f"cenario2 alertas: {c2.alertas}")

    # ---- Cenario 3: mesmo CFOP/CST com aliquotas diferentes ----
    nota3 = NotaFiscal(chave="3" * 44, valor_documento=D("300.00"),
                       valor_mercadoria=D("300.00"),
                       itens=[
                           _item("1102", "000", "20.50", "100.00",
                                 "100.00", "20.50"),
                           _item("1102", "000", "27.00", "200.00",
                                 "200.00", "54.00"),
                       ])
    c3 = compor_nota(nota3)
    checar(len(c3.grupos) == 2,
           f"cenario3: aliquotas diferentes nao podem somar ({len(c3.grupos)})")
    checar(c3.grupos[0].aliquota == D("20.50")
           and c3.grupos[1].aliquota == D("27.00"), "cenario3 ordenacao")

    # ---- Itens com mesmo CFOP, CST e aliquota somam num grupo so ----
    nota4 = NotaFiscal(chave="4" * 44, valor_documento=D("30.00"),
                       valor_mercadoria=D("30.00"),
                       itens=[
                           _item("1102", "000", "18", "10.00", "10.00", "1.80"),
                           _item("1102", "000", "18.00", "20.00", "20.00",
                                 "3.60"),
                       ])
    c4 = compor_nota(nota4)
    checar(len(c4.grupos) == 1 and c4.grupos[0].qtd_itens == 2,
           f"mesma combinacao deveria somar: {len(c4.grupos)}")
    checar(c4.grupos[0].valor_contabil == D("30.00"), "soma do grupo")

    # ---- ICMS incompativel com base x aliquota -> alerta (nao erro) ----
    nota5 = NotaFiscal(chave="5" * 44, valor_documento=D("100.00"),
                       valor_mercadoria=D("100.00"),
                       itens=[_item("1102", "020", "18", "100.00", "100.00",
                                    "9.00")])   # esperado 18,00 (reducao?)
    c5 = compor_nota(nota5)
    checar(any("reducao de base" in a for a in c5.alertas),
           f"divergencia deveria alertar reducao/diferimento: {c5.alertas}")

    # ---- CST sem destaque (40) com ICMS informado -> alerta ----
    nota6 = NotaFiscal(chave="6" * 44, valor_documento=D("50.00"),
                       valor_mercadoria=D("50.00"),
                       itens=[_item("1102", "040", "0", "50.00", "0", "5.00")])
    c6 = compor_nota(nota6)
    checar(any("sem destaque" in a for a in c6.alertas),
           f"CST 40 com ICMS deveria alertar: {c6.alertas}")

    # ---- Nota sem itens (C100 sem C170): capa + alerta ----
    nota7 = NotaFiscal(chave="7" * 44, valor_documento=D("80.00"),
                       vl_bc_icms=D("80.00"), vl_icms=D("14.40"))
    c7 = compor_nota(nota7)
    checar(c7.sem_itens and len(c7.grupos) == 1, "sem itens: capa da nota")
    checar(c7.grupos[0].valor_contabil == D("80.00"), "capa valor")
    checar(any("sem detalhe de itens" in a for a in c7.alertas),
           "sem itens deveria alertar")

    # ---- Total da nota maior que a soma (frete/IPI/ST conhecidos) ----
    nota8 = NotaFiscal(chave="8" * 44, valor_documento=D("115.00"),
                       valor_mercadoria=D("100.00"), valor_frete=D("10.00"),
                       vl_ipi=D("5.00"),
                       itens=[_item("1102", "000", "18", "100.00", "100.00",
                                    "18.00")])
    c8 = compor_nota(nota8)
    checar(not any("reconstruido" in a for a in c8.alertas),
           f"frete+IPI conhecidos nao deveriam alertar: {c8.alertas}")

    # ---- Divergencia inexplicada no total -> alerta descritivo ----
    nota9 = NotaFiscal(chave="9" * 44, valor_documento=D("150.00"),
                       valor_mercadoria=D("100.00"),
                       itens=[_item("1102", "000", "18", "100.00", "100.00",
                                    "18.00")])
    c9 = compor_nota(nota9)
    checar(any("difere do total da nota" in a for a in c9.alertas),
           f"divergencia de total deveria alertar: {c9.alertas}")

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - composicao fiscal (CFOP -> CST -> aliquota) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
