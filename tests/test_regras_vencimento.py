"""Spec 013: regras de datas puras, com calendario e relogio fixos."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
from auditoria_fiscal.core import regras_vencimento as rv
from auditoria_fiscal.core.tarefas import ErroTarefas


def recusa(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except ErroTarefas:
        return
    raise AssertionError(f"Entrada invalida aceita: {func.__name__}{args}")


def main():
    assert rv.validar_competencia("2026-01") == (2026, 1)
    for valor in ("2026-1", "2026-13", "0000-01", "2026-01-01", None):
        recusa(rv.validar_competencia, valor)
    assert rv.competencia_aplicavel("2026-01", "mensal")
    assert rv.competencia_aplicavel("2026-03", "trimestral")
    assert not rv.competencia_aplicavel("2026-01", "trimestral")
    assert rv.competencia_aplicavel("2026-02", "trimestral", [2, 5, 8, 11])
    assert rv.competencia_aplicavel("2026-12", "anual")
    assert rv.competencia_aplicavel("2026-04", "anual", [4])
    assert not rv.competencia_aplicavel("2026-12", "demanda")
    for periodo, meses in (("semanal", None), ("anual", [2, 3]), ("trimestral", [0]),
                           ("anual", [True]), ("mensal", [1]), ("trimestral", [1, 1, 1, 1])):
        recusa(rv.validar_periodicidade, periodo, meses)

    dia = {"tipo": "dia_mes_seguinte", "dia": 30}
    assert rv.calcular_vencimento("2026-01", dia) == date(2026, 2, 28)
    assert rv.calcular_vencimento("2028-01", dia) == date(2028, 2, 29)
    assert rv.calcular_vencimento("2026-12", dia) == date(2027, 1, 30)
    assert rv.calcular_vencimento("2026-12", {"tipo": "dia_mes_fixo", "dia": 30, "mes": 4}) == date(2027, 4, 30)
    assert rv.calcular_vencimento("2026-04", {"tipo": "dia_mes_fixo", "dia": 30, "mes": 4}) == date(2026, 4, 30)
    sabado = {"tipo": "dia_mes_seguinte", "dia": 7}
    domingo = {"tipo": "dia_mes_seguinte", "dia": 8}
    for regra in (sabado, domingo):
        assert rv.calcular_vencimento("2026-01", dict(regra, sem_expediente="antecipar")) == date(2026, 2, 6)
        assert rv.calcular_vencimento("2026-01", dict(regra, sem_expediente="adiar")) == date(2026, 2, 9)
        assert rv.calcular_vencimento("2026-01", dict(regra, sem_expediente="manter")).day == regra["dia"]
    feriados = [{"data": "2026-02-09", "sem_expediente": 1}, {"data": "2026-02-10", "sem_expediente": 0}]
    assert rv.calcular_vencimento("2026-01", dict(domingo, sem_expediente="adiar"), feriados) == date(2026, 2, 10)
    assert rv.calcular_vencimento("2026-01", {"tipo": "dia_mes_seguinte", "dia": 9, "sem_expediente": "antecipar"}, feriados) == date(2026, 2, 6)
    ultimo = {"tipo": "ultimo_dia_util_mes_seguinte", "sem_expediente": "adiar"}
    assert rv.calcular_vencimento("2026-01", ultimo) == date(2026, 2, 27)
    assert rv.calcular_vencimento("2026-01", ultimo, [date(2026, 2, 27)]) == date(2026, 2, 26)

    # Datas de Pascoa e dos quatro moveis conhecidas, sem derivar o esperado do algoritmo.
    calendario = {
        2026: ("04-05", "02-16", "02-17", "04-03", "06-04"),
        2027: ("03-28", "02-08", "02-09", "03-26", "05-27"),
        2028: ("04-16", "02-28", "02-29", "04-14", "06-15"),
        2029: ("04-01", "02-12", "02-13", "03-30", "05-31"),
        2030: ("04-21", "03-04", "03-05", "04-19", "06-20"),
    }
    for ano, datas in calendario.items():
        assert rv.pascoa(ano).isoformat() == f"{ano}-{datas[0]}"
        gerados = rv.feriados_nacionais(ano)
        assert len(gerados) == 13
        assert all(f["origem"] == "calculado" and f["abrangencia"] == "nacional" and f["sem_expediente"] == 1 for f in gerados)
        indices = {f["data"] for f in gerados}
        assert all(f"{ano}-{d}" in indices for d in datas[1:])
        assert f"{ano}-11-20" in indices
    for regra in ({}, {"tipo": "script"}, {"tipo": "dia_mes_seguinte", "dia": 0},
                  {"tipo": "dia_mes_seguinte", "dia": True}, {"tipo": "dia_mes_fixo", "dia": 20, "mes": 13},
                  {"tipo": "dia_mes_seguinte", "dia": 20, "codigo": "x"},
                  {"tipo": "dia_mes_seguinte", "dia": 20, "sem_expediente": "ignorar"}):
        recusa(rv.validar_regra, regra)
    print("OK - regras de vencimento, competencias, feriados 2026-2030 e validacao")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
