"""Sobrescritas manuais da composicao fiscal (tela + Livro Fiscal).

Verifica que: (1) o store grava, atualiza e remove sobrescritas; (2) o
montar_blocos do Livro Fiscal aplica o texto editado no grupo certo e no
total da nota; (3) celulas sem sobrescrita continuam com o valor calculado.
"""

from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.composicao_fiscal import (  # noqa: E402
    GRUPO_TOTAL, chave_grupo, compor_nota,
)
from auditoria_fiscal.core.modelos import ItemNota, NotaFiscal  # noqa: E402
from auditoria_fiscal.ferramentas.conferencia_store import (  # noqa: E402
    ConferenciaStore,
)
from auditoria_fiscal.ferramentas.livro_fiscal import montar_blocos  # noqa: E402


def _nota() -> NotaFiscal:
    nota = NotaFiscal(numero="123", serie="1",
                      chave="1" * 44, valor_documento=Decimal("1000"))
    nota.itens.append(ItemNota(
        cfop="1102", cst_icms="000", aliq_icms=Decimal("18"),
        valor_item=Decimal("1000"), vl_bc_icms=Decimal("1000"),
        vl_icms=Decimal("180")))
    return nota


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def main() -> int:
    nota = _nota()
    comp = compor_nota(nota)
    grupo = chave_grupo(comp.grupos[0])
    chave = nota.chave_normalizada

    with tempfile.TemporaryDirectory() as pasta:
        store = ConferenciaStore(os.path.join(pasta, "conf.db"))

        # 1) grava, atualiza e le
        store.salvar_override(chave, grupo, 3, "R$ 999,99",
                              "R$ 1.000,00", "tester")
        store.salvar_override(chave, GRUPO_TOTAL, 3, "R$ 888,88",
                              "R$ 1.000,00", "tester")
        ovs = store.overrides_da_chave(chave)
        checar((grupo, 3) in ovs and ovs[(grupo, 3)].valor == "R$ 999,99",
               "override do grupo nao gravado")
        store.salvar_override(chave, grupo, 3, "R$ 777,77",
                              "R$ 1.000,00", "tester")
        checar(store.overrides_da_chave(chave)[(grupo, 3)].valor
               == "R$ 777,77", "override nao atualizado")

        # 2) Livro Fiscal com os textos editados
        blocos = montar_blocos([nota], {}, None, store.todas_overrides())
        linhas = [ln for g in blocos[0]["grupos"] for ln in g]
        checar(any("Valor Contabil: R$ 777,77" in ln for ln in linhas),
               f"PDF sem o texto editado do grupo: {linhas}")
        checar("Valor total da nota: R$ 888,88" == blocos[0]["total"],
               f"PDF sem o total editado: {blocos[0]['total']}")
        # Base de calculo segue calculada (sem override na coluna 4)
        checar(any("Base de Calculo: " in ln and "777" not in ln
                   for ln in linhas), "base de calculo deveria ser calculada")

        # 3) valor vazio remove (volta ao calculado)
        store.salvar_override(chave, grupo, 3, "", "", "tester")
        store.salvar_override(chave, GRUPO_TOTAL, 3, "", "", "tester")
        checar(store.overrides_da_chave(chave) == {},
               "override vazio deveria remover")
        blocos = montar_blocos([nota], {}, None, store.todas_overrides())
        checar("Valor total da nota: R$ 1.000,00" == blocos[0]["total"],
               "total deveria voltar ao calculado")

        # 4) persistencia entre sessoes (reabre o banco)
        store.salvar_override(chave, grupo, 5, "R$ 111,11",
                              "R$ 180,00", "tester")
        store.fechar()
        store2 = ConferenciaStore(os.path.join(pasta, "conf.db"))
        checar(store2.overrides_da_chave(chave)[(grupo, 5)].valor
               == "R$ 111,11", "override nao persistiu entre sessoes")
        store2.fechar()

    print("OK - sobrescritas da composicao (store + Livro Fiscal) passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
