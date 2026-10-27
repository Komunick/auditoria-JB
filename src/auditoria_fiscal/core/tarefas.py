"""Regras puras de tarefas (spec 013), sem banco, interface ou permissao implicita."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

SALVADOR = timezone(timedelta(hours=-3), "America/Bahia")
SITUACOES = {
    "a_fazer": "A fazer", "em_andamento": "Em andamento",
    "aguardando_cliente": "Aguardando cliente", "concluida": "Concluída",
    "conferida": "Conferida", "devolvida": "Devolvida", "dispensada": "Dispensada",
}
ABERTAS = frozenset(("a_fazer", "em_andamento", "aguardando_cliente", "devolvida"))
ENCERRADAS = frozenset(("concluida", "conferida", "dispensada"))


class ErroTarefas(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem


def data_salvador(valor: str | date | datetime) -> date:
    """Carimbo UTC vira dia local. Datas sem hora ja representam o dia de negocio."""
    try:
        if isinstance(valor, datetime):
            instante = valor
        elif isinstance(valor, date):
            return valor
        elif isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
            return date.fromisoformat(valor)
        else:
            instante = datetime.fromisoformat(valor)
        if instante.tzinfo is None:
            raise ValueError("Timestamp sem fuso")
        return instante.astimezone(SALVADOR).date()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ErroTarefas("DATA_INVALIDA", "Informe uma data ISO ou um carimbo com fuso horário.") from exc


def hoje_salvador() -> date:
    return datetime.now(SALVADOR).date()


def validar_email(valor: str | None) -> str:
    if valor is None:
        return ""
    if not isinstance(valor, str) or any(c in valor for c in "\r\n\x00"):
        raise ErroTarefas("EMAIL_INVALIDO", "Informe um endereço de e-mail válido.")
    email = valor.strip()
    if not email:
        return ""
    if len(email) > 254 or not re.fullmatch(r"[^\s@<>;,]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", email):
        raise ErroTarefas("EMAIL_INVALIDO", "Informe um endereço de e-mail válido.")
    local, dominio = email.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in email or any(
            not rotulo or len(rotulo) > 63 or rotulo.startswith("-") or rotulo.endswith("-")
            for rotulo in dominio.split(".")):
        raise ErroTarefas("EMAIL_INVALIDO", "Informe um endereço de e-mail válido.")
    return email


def validar_condicao(condicao: dict | None) -> dict:
    if condicao is None:
        condicao = {}
    if not isinstance(condicao, dict) or set(condicao) - {"todas", "alguma", "nenhuma"}:
        raise ErroTarefas("CONDICAO_INVALIDA", "A condição aceita somente todas, alguma e nenhuma.")
    normalizada = {}
    for chave in ("todas", "alguma", "nenhuma"):
        ids = condicao.get(chave, [])
        if not isinstance(ids, list) or any(type(i) is not int or i <= 0 for i in ids):
            raise ErroTarefas("CONDICAO_INVALIDA", "Características devem ser uma lista de identificadores positivos.")
        normalizada[chave] = sorted(set(ids))
    return normalizada


def aplica(condicao: dict | None, caracteristicas) -> bool:
    regra = validar_condicao(condicao)
    ids = set(caracteristicas)
    return (set(regra["todas"]).issubset(ids)
            and (not regra["alguma"] or bool(ids.intersection(regra["alguma"])))
            and not ids.intersection(regra["nenhuma"]))


def validar_transicao(atual: str, nova: str, exige_conferencia: bool = False,
                      motivo: str = "", responsavel_setor: bool = False) -> str:
    """O chamador comprova escopo/permissao; aqui o papel nao pode ser elevado."""
    if atual not in SITUACOES or nova not in SITUACOES:
        raise ErroTarefas("SITUACAO_INVALIDA", "Situação de tarefa desconhecida.")
    if nova == "dispensada":
        if atual not in ABERTAS or not responsavel_setor or not str(motivo or "").strip():
            raise ErroTarefas("TRANSICAO_INVALIDA", "Só o responsável do setor pode dispensar uma tarefa aberta, com motivo.")
        return nova
    if nova in ("conferida", "devolvida"):
        if atual != "concluida" or not exige_conferencia or not responsavel_setor:
            raise ErroTarefas("TRANSICAO_INVALIDA", "A conferência exige conclusão anterior e responsável do setor.")
        if nova == "devolvida" and not str(motivo or "").strip():
            raise ErroTarefas("MOTIVO_OBRIGATORIO", "Informe o motivo da devolução.")
        return nova
    permitidas = {
        "a_fazer": {"em_andamento", "aguardando_cliente"},
        "em_andamento": {"aguardando_cliente", "concluida"},
        "aguardando_cliente": {"em_andamento", "concluida"},
        # Devolvida representa trabalho reaberto e continua vermelha ate ser retomado.
        "devolvida": {"em_andamento", "aguardando_cliente", "concluida"},
    }
    if nova not in permitidas.get(atual, set()):
        raise ErroTarefas("TRANSICAO_INVALIDA", "Essa mudança não é permitida para a situação atual.")
    return nova


def classificar(tarefa: dict, hoje: date | str | datetime, dias: int = 3) -> dict:
    """Cor e atraso calculados no servidor; conclusao tardia permanece registrada."""
    if type(dias) is not int or not 0 <= dias <= 365:
        raise ErroTarefas("ALERTA_INVALIDO", "A antecedência deve estar entre 0 e 365 dias.")
    situacao = tarefa.get("situacao")
    if situacao not in SITUACOES:
        raise ErroTarefas("SITUACAO_INVALIDA", "Situação de tarefa desconhecida.")
    vencimento = data_salvador(tarefa["vencimento"])
    distancia = (vencimento - data_salvador(hoje)).days
    fora = bool(tarefa.get("fora_do_prazo"))
    atrasada = situacao in ABERTAS and distancia < 0
    if situacao == "dispensada":
        cor = "neutro"
    elif atrasada or situacao == "devolvida" or fora:
        cor = "vermelho"
    elif situacao in ("concluida", "conferida"):
        cor = "verde"
    elif situacao in ("em_andamento", "aguardando_cliente") or distancia <= dias:
        cor = "amarelo"
    else:
        cor = "neutro"
    return {"cor": cor, "atrasada": atrasada, "fora_do_prazo": fora}
