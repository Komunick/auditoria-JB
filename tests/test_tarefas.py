"""Spec 013: aplicabilidade, transicoes, cores e datas de Salvador."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
from auditoria_fiscal.core import tarefas as t


def recusa(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except t.ErroTarefas:
        return
    raise AssertionError(f"Entrada invalida aceita: {func.__name__}{args}")


def main():
    assert t.aplica({}, [])
    condicao = {"todas": [1, 2], "alguma": [3, 4], "nenhuma": [5]}
    assert t.aplica(condicao, [1, 2, 4])
    assert not t.aplica(condicao, [1, 2])
    assert not t.aplica(condicao, [1, 2, 3, 5])
    assert not t.aplica(condicao, [1, 3])
    for valor in ({"ou": [1]}, {"todas": [True]}, {"alguma": "1"}, {"nenhuma": [-1]}, []):
        recusa(t.validar_condicao, valor)
    assert t.validar_transicao("a_fazer", "em_andamento") == "em_andamento"
    assert t.validar_transicao("em_andamento", "aguardando_cliente") == "aguardando_cliente"
    assert t.validar_transicao("aguardando_cliente", "em_andamento") == "em_andamento"
    assert t.validar_transicao("em_andamento", "concluida") == "concluida"
    assert t.validar_transicao("concluida", "conferida", True, "", True) == "conferida"
    assert t.validar_transicao("concluida", "devolvida", True, "Corrigir documento", True) == "devolvida"
    assert t.validar_transicao("devolvida", "em_andamento") == "em_andamento"
    assert t.validar_transicao("a_fazer", "dispensada", False, "Sem fato gerador", True) == "dispensada"
    for args in (("a_fazer", "conferida", True, "", True),
                 ("concluida", "conferida", True, "", False),
                 ("concluida", "conferida", False, "", True),
                 ("concluida", "devolvida", True, "", True),
                 ("a_fazer", "dispensada", False, "", True),
                 ("a_fazer", "dispensada", False, "Motivo", False),
                 ("conferida", "em_andamento"), ("dispensada", "em_andamento"),
                 ("inexistente", "concluida")):
        recusa(t.validar_transicao, *args)
    hoje = date(2026, 10, 27)
    base = {"situacao": "a_fazer", "vencimento": "2026-10-30", "fora_do_prazo": 0}
    assert t.classificar(base, hoje)["cor"] == "amarelo"
    assert t.classificar(dict(base, vencimento="2026-11-03"), hoje)["cor"] == "neutro"
    assert t.classificar(dict(base, vencimento="2026-10-26"), hoje)["atrasada"]
    assert t.classificar(dict(base, vencimento="2026-10-27"), hoje)["atrasada"] is False
    for situacao in ("em_andamento", "aguardando_cliente"):
        assert t.classificar(dict(base, situacao=situacao, vencimento="2026-11-30"), hoje)["cor"] == "amarelo"
        assert t.classificar(dict(base, situacao=situacao, vencimento="2026-10-01"), hoje)["cor"] == "vermelho"
    assert t.classificar(dict(base, situacao="devolvida", vencimento="2026-11-30"), hoje)["cor"] == "vermelho"
    for situacao in ("concluida", "conferida"):
        assert t.classificar(dict(base, situacao=situacao, vencimento="2026-10-01"), hoje)["cor"] == "verde"
        late = t.classificar(dict(base, situacao=situacao, fora_do_prazo=1), date(2030, 1, 1))
        assert late == {"cor": "vermelho", "atrasada": False, "fora_do_prazo": True}
    assert t.classificar(dict(base, situacao="dispensada", vencimento="2026-10-01"), hoje)["cor"] == "neutro"
    # 02h UTC ainda e' a data anterior em Salvador; nunca use date() direto no timestamp UTC.
    assert t.data_salvador("2026-10-28T02:59:59+00:00") == hoje
    assert t.data_salvador("2026-10-28T03:00:00+00:00") == date(2026, 10, 28)
    assert t.validar_email("  equipe@example.test  ") == "equipe@example.test"
    assert t.validar_email("") == ""
    for email in ("sem-arroba", "a@", "a@host", "a\r\nBcc: x@example.test", "a b@example.test"):
        recusa(t.validar_email, email)
    print("OK - aplicabilidade, transicoes, cores, atraso permanente, email e Salvador")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
