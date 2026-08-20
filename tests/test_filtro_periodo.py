"""Testes do filtro por periodo (data de escrituracao / emissao).

Cobre a escolha da base de data, os limites inclusivos, o tratamento de notas
sem a data escolhida e o conjunto de chaves no periodo (usado para restringir
as correcoes do SPED corrigido).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core.filtro_periodo import (  # noqa: E402
    BASE_EMISSAO, BASE_ESCRITURACAO, chaves_no_periodo, data_base,
    filtrar_por_periodo, no_periodo, normalizar_base, para_data, tem_periodo,
)
from auditoria_fiscal.core.modelos import ItemNota, NotaFiscal  # noqa: E402


def chave(sufixo: str) -> str:
    ch = ("35260399888777000166550010000010011111111" + sufixo)[:44]
    return ch.ljust(44, "0")


def nota(emissao=None, escrituracao=None, sufixo="1") -> NotaFiscal:
    n = NotaFiscal(chave=chave(sufixo), numero=sufixo,
                   dt_emissao=emissao, dt_entrada_saida=escrituracao,
                   valor_documento=Decimal("100"))
    n.itens.append(ItemNota(num_item="1", cfop="1102",
                            valor_item=Decimal("100")))
    return n


def test_para_data() -> None:
    assert para_data("2026-07-21") == date(2026, 7, 21)
    assert para_data(date(2026, 7, 21)) == date(2026, 7, 21)
    assert para_data("") is None
    assert para_data(None) is None
    assert para_data("31/07/2026") is None    # so ISO dos <input type=date>
    print("OK para_data (ISO, date, vazio)")


def test_base_e_normalizacao() -> None:
    n = nota(emissao=date(2026, 7, 3), escrituracao=date(2026, 7, 21))
    assert data_base(n, BASE_EMISSAO) == date(2026, 7, 3)
    assert data_base(n, BASE_ESCRITURACAO) == date(2026, 7, 21)
    # Base invalida cai no padrao (escrituracao).
    assert normalizar_base("qualquer") == BASE_ESCRITURACAO
    assert data_base(n, "xxx") == date(2026, 7, 21)
    print("OK base de data + normalizacao para escrituracao")


def test_sem_periodo_mantem_tudo() -> None:
    notas = [nota(sufixo="1"), nota(sufixo="2")]
    assert tem_periodo(None, None) is False
    assert tem_periodo("2026-07-01", None) is True
    saida = filtrar_por_periodo(notas, None, None)
    assert [n.chave for n in saida] == [n.chave for n in notas]
    assert saida is not notas             # copia, nao a mesma lista
    assert chaves_no_periodo(notas, None, None) is None
    print("OK sem periodo devolve tudo (copia) e chaves None")


def test_escrituracao_o_cenario_do_usuario() -> None:
    # Importa o SPED do mes; escritura em datas diferentes da emissao.
    notas = [
        nota(emissao=date(2026, 6, 28), escrituracao=date(2026, 7, 2), sufixo="1"),
        nota(emissao=date(2026, 6, 30), escrituracao=date(2026, 7, 21), sufixo="2"),
        nota(emissao=date(2026, 7, 1), escrituracao=date(2026, 7, 31), sufixo="3"),
        nota(emissao=date(2026, 7, 5), escrituracao=date(2026, 8, 1), sufixo="4"),
    ]
    # "do dia 21 ao 31" por ESCRITURACAO: pega as notas 2 e 3.
    saida = filtrar_por_periodo(notas, "2026-07-21", "2026-07-31",
                                BASE_ESCRITURACAO)
    assert [n.numero for n in saida] == ["2", "3"]
    # O mesmo intervalo por EMISSAO nao pega nenhuma (emissoes em jun/inicio jul).
    por_emissao = filtrar_por_periodo(notas, "2026-07-21", "2026-07-31",
                                      BASE_EMISSAO)
    assert por_emissao == []
    print("OK periodo por escrituracao (cenario 21..31) x emissao")


def test_limites_inclusivos_e_abertos() -> None:
    notas = [nota(escrituracao=date(2026, 7, d), sufixo=str(d)) for d in (20, 21, 31)]
    # Limites inclusivos nas duas pontas.
    assert [n.numero for n in filtrar_por_periodo(
        notas, "2026-07-21", "2026-07-31", BASE_ESCRITURACAO)] == ["21", "31"]
    # So inicio (sem fim): tudo a partir de 21.
    assert [n.numero for n in filtrar_por_periodo(
        notas, "2026-07-21", None, BASE_ESCRITURACAO)] == ["21", "31"]
    # So fim (sem inicio): tudo ate 21.
    assert [n.numero for n in filtrar_por_periodo(
        notas, None, "2026-07-21", BASE_ESCRITURACAO)] == ["20", "21"]
    print("OK limites inclusivos e periodos abertos de um lado")


def test_nota_sem_data_fica_fora() -> None:
    com = nota(escrituracao=date(2026, 7, 25), sufixo="1")
    sem = nota(escrituracao=None, sufixo="2")     # DT_E_S ausente
    saida = filtrar_por_periodo([com, sem], "2026-07-21", "2026-07-31",
                                BASE_ESCRITURACAO)
    assert [n.numero for n in saida] == ["1"]
    assert no_periodo(sem, "2026-07-21", "2026-07-31", BASE_ESCRITURACAO) is False
    # Sem periodo, a nota sem data continua aparecendo (nada a comparar).
    assert no_periodo(sem, None, None, BASE_ESCRITURACAO) is True
    print("OK nota sem a data escolhida fica fora quando ha limite")


def test_chaves_no_periodo() -> None:
    notas = [
        nota(escrituracao=date(2026, 7, 10), sufixo="1"),
        nota(escrituracao=date(2026, 7, 25), sufixo="2"),
    ]
    chaves = chaves_no_periodo(notas, "2026-07-21", "2026-07-31",
                               BASE_ESCRITURACAO)
    assert chaves == {notas[1].chave_normalizada}
    print("OK chaves_no_periodo (restringe correcoes do SPED corrigido)")


if __name__ == "__main__":
    test_para_data()
    test_base_e_normalizacao()
    test_sem_periodo_mantem_tudo()
    test_escrituracao_o_cenario_do_usuario()
    test_limites_inclusivos_e_abertos()
    test_nota_sem_data_fica_fora()
    test_chaves_no_periodo()
    print("\nTodos os testes do filtro por periodo passaram.")
