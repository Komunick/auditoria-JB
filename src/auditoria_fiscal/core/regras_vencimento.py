"""Competencias, regras fechadas de vencimento e calendario da spec 013.

Nenhum prazo de obrigacao fiscal e' definido aqui. O escritorio cadastra a regra;
o calendario calculado pode ser complementado/alterado na tabela de feriados.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .tarefas import ErroTarefas, data_salvador


def validar_competencia(competencia: str) -> tuple[int, int]:
    if not isinstance(competencia, str) or not re.fullmatch(r"\d{4}-\d{2}", competencia):
        raise ErroTarefas("COMPETENCIA_INVALIDA", "Informe a competência no formato AAAA-MM.")
    ano, mes = map(int, competencia.split("-"))
    try:
        date(ano, mes, 1)
    except ValueError as exc:
        raise ErroTarefas("COMPETENCIA_INVALIDA", "Ano ou mês da competência inválido.") from exc
    return ano, mes


def validar_periodicidade(periodicidade: str, competencias: list | None = None) -> list[int]:
    padroes = {"mensal": list(range(1, 13)), "trimestral": [3, 6, 9, 12], "anual": [12], "demanda": []}
    if periodicidade not in padroes:
        raise ErroTarefas("PERIODICIDADE_INVALIDA", "Escolha mensal, trimestral, anual ou por demanda.")
    if competencias is None or competencias == []:
        return list(padroes[periodicidade])
    if (not isinstance(competencias, list)
            or any(type(m) is not int or not 1 <= m <= 12 for m in competencias)
            or len(competencias) != len(set(competencias))):
        raise ErroTarefas("COMPETENCIAS_INVALIDAS", "Informe meses válidos, sem repetição.")
    meses = sorted(competencias)
    if len(meses) != len(padroes[periodicidade]):
        raise ErroTarefas("COMPETENCIAS_INVALIDAS", "A quantidade de meses não corresponde à periodicidade.")
    return meses


def competencia_aplicavel(competencia: str, periodicidade: str,
                        competencias: list | None = None) -> bool:
    _, mes = validar_competencia(competencia)
    return mes in validar_periodicidade(periodicidade, competencias)


def validar_regra(regra: dict) -> dict:
    campos = {
        "dia_mes_seguinte": {"tipo", "dia", "inicio_dia", "sem_expediente"},
        "ultimo_dia_util_mes_seguinte": {"tipo", "sem_expediente"},
        "dia_mes_fixo": {"tipo", "dia", "mes", "sem_expediente"},
        "periodos_mes_seguinte": {"tipo", "periodos", "sem_expediente"},
        "sem_vencimento": {"tipo"},
    }
    if (not isinstance(regra, dict) or not isinstance(regra.get("tipo"), str)
            or regra["tipo"] not in campos):
        raise ErroTarefas("REGRA_INVALIDA", "Tipo de regra de vencimento desconhecido.")
    tipo = regra["tipo"]
    if set(regra) - campos[tipo]:
        raise ErroTarefas("REGRA_INVALIDA", "A regra contém campos não reconhecidos.")
    if tipo == "sem_vencimento":
        return {"tipo": tipo}
    resultado = {"tipo": tipo, "sem_expediente": regra.get("sem_expediente", "manter")}
    if resultado["sem_expediente"] not in ("antecipar", "adiar", "manter"):
        raise ErroTarefas("REGRA_INVALIDA", "Escolha antecipar, adiar ou manter o dia sem expediente.")
    for campo, limite in (("dia", 31), ("mes", 12)):
        if campo in campos[tipo]:
            valor = regra.get(campo)
            if type(valor) is not int or not 1 <= valor <= limite:
                raise ErroTarefas("REGRA_INVALIDA", f"O campo {campo} deve estar entre 1 e {limite}.")
            resultado[campo] = valor
    if "inicio_dia" in regra:
        inicio = regra["inicio_dia"]
        if type(inicio) is not int or not 1 <= inicio <= resultado["dia"]:
            raise ErroTarefas("REGRA_INVALIDA", "O início deve ser um dia entre 1 e o dia do vencimento.")
        resultado["inicio_dia"] = inicio
    if tipo == "periodos_mes_seguinte":
        periodos = regra.get("periodos")
        if not isinstance(periodos, list) or not 1 <= len(periodos) <= 31:
            raise ErroTarefas("REGRA_INVALIDA", "Informe uma lista de períodos do mês.")
        anteriores = 0
        resultado["periodos"] = []
        for periodo in periodos:
            if not isinstance(periodo, dict) or set(periodo) != {"inicio", "fim"}:
                raise ErroTarefas("REGRA_INVALIDA", "Cada período deve informar somente início e fim.")
            inicio, fim = periodo["inicio"], periodo["fim"]
            if (type(inicio) is not int or type(fim) is not int
                    or not 1 <= inicio <= fim <= 31):
                raise ErroTarefas("REGRA_INVALIDA", "Os períodos exigem dias de 1 a 31, com início anterior ou igual ao fim.")
            if inicio <= anteriores:
                raise ErroTarefas("REGRA_INVALIDA", "Informe os períodos em ordem cronológica, sem sobreposição.")
            anteriores = fim
            resultado["periodos"].append({"inicio": inicio, "fim": fim})
    return resultado


def _datas_sem_expediente(feriados) -> set[date]:
    datas = set()
    for feriado in feriados:
        if isinstance(feriado, dict):
            if not feriado.get("sem_expediente", True):
                continue
            feriado = feriado.get("data")
        datas.add(data_salvador(feriado))
    return datas


def dia_util(dia: date | str, feriados=()) -> bool:
    data = data_salvador(dia)
    return data.weekday() < 5 and data not in _datas_sem_expediente(feriados)


def _mes_vencimento(competencia: str, regra: dict) -> tuple[int, int]:
    ano, mes = validar_competencia(competencia)
    if regra["tipo"] == "dia_mes_fixo":
        ano += regra["mes"] < mes
        mes = regra["mes"]
    else:
        ano += mes == 12
        mes = mes % 12 + 1
    if ano > 9999:
        raise ErroTarefas("REGRA_INVALIDA", "Vencimento ultrapassa o calendário suportado.")
    return ano, mes


def _ajustar_expediente(vencimento: date, politica: str, sem_expediente: set[date]) -> date:
    if politica == "manter":
        return vencimento
    passo = timedelta(days=-1 if politica == "antecipar" else 1)
    try:
        while vencimento.weekday() >= 5 or vencimento in sem_expediente:
            vencimento += passo
    except OverflowError as exc:
        raise ErroTarefas("REGRA_INVALIDA", "Vencimento ultrapassa o calendário suportado.") from exc
    return vencimento


def calcular_ocorrencias(competencia: str, regra: dict, feriados=()) -> list[dict]:
    """Agenda completa, com identidade posicional e sem datas ficticias.

    Os intervalos originais definem ordem e identidade. Somente o fim acompanha
    a politica de expediente; inicio fixo e rotulo preservam a regra cadastrada.
    """
    regra = validar_regra(regra)
    ano, mes = _mes_vencimento(competencia, regra)
    if regra["tipo"] == "sem_vencimento":
        return [{"ocorrencia": 1, "inicio": date(ano, mes, 1), "vencimento": None, "rotulo": ""}]
    sem_expediente = _datas_sem_expediente(feriados)
    ultimo = calendar.monthrange(ano, mes)[1]
    if regra["tipo"] == "periodos_mes_seguinte":
        ocorrencias = []
        for numero, periodo in enumerate(regra["periodos"], 1):
            inicio = date(ano, mes, min(periodo["inicio"], ultimo))
            vencimento = _ajustar_expediente(date(ano, mes, min(periodo["fim"], ultimo)),
                                             regra["sem_expediente"], sem_expediente)
            if inicio > vencimento:
                raise ErroTarefas("REGRA_INVALIDA", f"O período {numero} começa depois do vencimento ajustado; revise a regra.")
            ocorrencias.append({"ocorrencia": numero, "inicio": inicio, "vencimento": vencimento,
                                "rotulo": f"{periodo['inicio']:02d}–{periodo['fim']:02d}"})
        return ocorrencias
    dia = ultimo if regra["tipo"] == "ultimo_dia_util_mes_seguinte" else min(regra["dia"], ultimo)
    politica = "antecipar" if regra["tipo"] == "ultimo_dia_util_mes_seguinte" else regra["sem_expediente"]
    vencimento = _ajustar_expediente(date(ano, mes, dia), politica, sem_expediente)
    inicio = date(ano, mes, min(regra["inicio_dia"], ultimo)) if "inicio_dia" in regra else None
    if inicio is not None and inicio > vencimento:
        raise ErroTarefas("REGRA_INVALIDA", "O início fixo é posterior ao vencimento ajustado; revise a regra.")
    return [{"ocorrencia": 1, "inicio": inicio, "vencimento": vencimento, "rotulo": ""}]


def calcular_vencimento(competencia: str, regra: dict, feriados=()) -> date:
    """Contrato legado: uma data. Novas agendas nunca sao reduzidas silenciosamente."""
    ocorrencias = calcular_ocorrencias(competencia, regra, feriados)
    if len(ocorrencias) != 1:
        raise ErroTarefas("MULTIPLAS_OCORRENCIAS", "Esta regra produz mais de um vencimento; consulte a agenda completa.")
    if ocorrencias[0]["vencimento"] is None:
        raise ErroTarefas("SEM_VENCIMENTO", "Esta regra não define vencimento.")
    return ocorrencias[0]["vencimento"]


def pascoa(ano: int) -> date:
    """Computus gregoriano (Meeus/Jones/Butcher), deterministico e sem rede."""
    if type(ano) is not int or not 1 <= ano <= 9999:
        raise ErroTarefas("ANO_INVALIDO", "Informe um ano válido.")
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, resto = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, resto + 1)


def feriados_nacionais(ano: int) -> list[dict]:
    """Inclui os pontos facultativos solicitados, identificados na descricao.

    O store insere somente datas ausentes, preservando a escolha de expediente
    feita pelo escritorio para Carnaval e Corpus Christi.
    """
    domingo = pascoa(ano)
    fixos = {
        (1, 1): "Confraternização Universal", (4, 21): "Tiradentes",
        (5, 1): "Dia do Trabalho", (9, 7): "Independência do Brasil",
        (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados",
        (11, 15): "Proclamação da República", (11, 20): "Consciência Negra",
        (12, 25): "Natal",
    }
    datas = {date(ano, mes, dia): nome for (mes, dia), nome in fixos.items()}
    for deslocamento, nome in ((-48, "Carnaval — segunda-feira (ponto facultativo)"),
                              (-47, "Carnaval — terça-feira (ponto facultativo)"),
                              (-2, "Sexta-feira Santa"),
                              (60, "Corpus Christi (ponto facultativo)")):
        datas[domingo + timedelta(days=deslocamento)] = nome
    return [{"data": dia.isoformat(), "descricao": descricao,
             "abrangencia": "nacional", "origem": "calculado", "sem_expediente": 1}
            for dia, descricao in sorted(datas.items())]
