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


def agenda_por_periodos():
    # Inicio fixo nao acompanha o adiamento/antecipacao do vencimento.
    regra = {"tipo": "dia_mes_seguinte", "inicio_dia": 1, "dia": 20, "sem_expediente": "adiar"}
    assert rv.validar_regra(regra) == regra
    ocorrencias = rv.calcular_ocorrencias("2026-10", regra, rv.feriados_nacionais(2026))
    assert ocorrencias == [{"ocorrencia": 1, "inicio": date(2026, 11, 1),
                           "vencimento": date(2026, 11, 23), "rotulo": ""}]
    antecipada = rv.calcular_ocorrencias("2026-03", dict(regra, dia=25, sem_expediente="antecipar"))
    assert antecipada[0]["inicio"] == date(2026, 4, 1)
    assert antecipada[0]["vencimento"] == date(2026, 4, 24)
    # Uma regra antiga continua sem inicio fixo, para o store conservar sua politica.
    assert rv.calcular_ocorrencias("2026-12", {"tipo": "dia_mes_seguinte", "dia": 30}) == [
        {"ocorrencia": 1, "inicio": None, "vencimento": date(2027, 1, 30), "rotulo": ""}]

    periodos = {"tipo": "periodos_mes_seguinte", "sem_expediente": "manter",
                "periodos": [{"inicio": 1, "fim": 10}, {"inicio": 11, "fim": 20}, {"inicio": 21, "fim": 30}]}
    esperado = [(1, date(2026, 2, 1), date(2026, 2, 10), "01–10"),
                (2, date(2026, 2, 11), date(2026, 2, 20), "11–20"),
                (3, date(2026, 2, 21), date(2026, 2, 28), "21–30")]
    recebido = rv.calcular_ocorrencias("2026-01", periodos)
    assert [(o["ocorrencia"], o["inicio"], o["vencimento"], o["rotulo"]) for o in recebido] == esperado
    assert rv.calcular_ocorrencias("2028-01", periodos)[2]["vencimento"] == date(2028, 2, 29)
    assert rv.calcular_ocorrencias("2026-02", periodos)[2]["vencimento"] == date(2026, 3, 30), "Nao estender ate o dia 31"
    assert rv.calcular_ocorrencias("2026-12", periodos)[0]["inicio"] == date(2027, 1, 1)
    quinzenas = {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 1, "fim": 15}, {"inicio": 16, "fim": 30}],
                 "sem_expediente": "antecipar"}
    recebidas = rv.calcular_ocorrencias("2026-01", quinzenas, rv.feriados_nacionais(2026))
    assert [o["ocorrencia"] for o in recebidas] == [1, 2]
    assert recebidas[0]["vencimento"] == date(2026, 2, 13)
    assert recebidas[1]["inicio"] == date(2026, 2, 16) and recebidas[1]["vencimento"] == date(2026, 2, 27)
    assert recebidas[1]["rotulo"] == "16–30", "Rotulo preserva periodo original, mesmo em fevereiro"
    # Calendario altera prazos, nunca os identificadores posicionais das ocorrencias.
    adiadas = rv.calcular_ocorrencias("2026-01", dict(quinzenas, sem_expediente="adiar"), rv.feriados_nacionais(2026))
    assert [o["ocorrencia"] for o in adiadas] == [1, 2]
    assert adiadas[0]["inicio"] == date(2026, 2, 1) and adiadas[0]["vencimento"] == date(2026, 2, 18)
    assert adiadas[1]["inicio"] == date(2026, 2, 16) and adiadas[1]["vencimento"] == date(2026, 3, 2)
    recusa(rv.calcular_vencimento, "2026-01", periodos)
    # Nunca entregar apenas parte da agenda quando um intervalo ficou impossivel.
    recusa(rv.calcular_ocorrencias, "2026-01", {"tipo": "dia_mes_seguinte", "inicio_dia": 8,
                                              "dia": 8, "sem_expediente": "antecipar"})
    recusa(rv.calcular_ocorrencias, "2026-01", {"tipo": "periodos_mes_seguinte", "sem_expediente": "antecipar",
                                              "periodos": [{"inicio": 1, "fim": 5}, {"inicio": 7, "fim": 8}]})
    sem = {"tipo": "sem_vencimento"}
    assert rv.validar_regra(sem) == sem
    assert rv.calcular_ocorrencias("2026-12", sem) == [
        {"ocorrencia": 1, "inicio": date(2027, 1, 1), "vencimento": None, "rotulo": ""}]
    recusa(rv.calcular_vencimento, "2026-12", sem)
    recusa(rv.calcular_ocorrencias, "9999-12", sem)
    for invalida in (
        {"tipo": "dia_mes_seguinte", "dia": 20, "inicio_dia": True},
        {"tipo": "dia_mes_seguinte", "dia": 20, "inicio_dia": 0},
        {"tipo": "dia_mes_seguinte", "dia": 20, "inicio_dia": 21},
        {"tipo": "dia_mes_seguinte", "dia": 20, "inicio_dia": None},
        {"tipo": "dia_mes_fixo", "dia": 20, "mes": 3, "inicio_dia": 1},
        {"tipo": "ultimo_dia_util_mes_seguinte", "inicio_dia": 1},
        {"tipo": "sem_vencimento", "dia": 20},
        {"tipo": "sem_vencimento", "sem_expediente": "manter"},
        {"tipo": "sem_vencimento", "inicio_dia": 1},
        {"tipo": []}, {"tipo": "periodos_mes_seguinte"},
        {"tipo": "periodos_mes_seguinte", "periodos": []},
        {"tipo": "periodos_mes_seguinte", "periodos": {"inicio": 1, "fim": 10}},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 1, "fim": 10, "extra": True}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 1}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": True, "fim": 10}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 0, "fim": 10}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 10, "fim": 5}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 21, "fim": 32}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 1, "fim": 10}, {"inicio": 10, "fim": 20}]},
        {"tipo": "periodos_mes_seguinte", "periodos": [{"inicio": 11, "fim": 20}, {"inicio": 1, "fim": 10}]},
    ):
        recusa(rv.validar_regra, invalida)


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
    agenda_por_periodos()
    print("OK - regras de vencimento, competencias, feriados, inicio fixo, periodos e ausencia de prazo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
