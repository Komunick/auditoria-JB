"""Regras do cadastro de clientes da contabilidade (spec 012).

Puro: sem FastAPI, sem SQLite. Tres assuntos:

- **Documento.** A planilha antiga guarda o CNPJ como NUMERO, e o Excel come
  o zero da frente. Recuperar o zero so e' seguro quando o digito verificador
  confere — senao seria inventar um documento.
- **Valor x situacao.** Na planilha, a mesma coluna guarda ora a inscricao,
  ora "NAO TEM", ora "PENDENTE", com variacoes de grafia. O sistema separa as
  duas coisas: um campo tem um valor OU uma situacao, nunca os dois num texto
  livre. A lista de grafias e' explicita (nada de "parecido com"): texto que
  nao esta nela e' valor.
- **Faixas de vencimento** do certificado digital, com "hoje" injetado.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from .documentos_br import DocumentoInvalido, digitos_cnpj, digitos_cpf

DOCUMENTO_INVALIDO = "DOCUMENTO_INVALIDO"
CAMPO_OBRIGATORIO = "CAMPO_OBRIGATORIO"
VALOR_INVALIDO = "VALOR_INVALIDO"
FAIXAS_INVALIDAS = "FAIXAS_INVALIDAS"


class ErroClientes(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem


# ----------------------------------------------------------------------
# Situacao do cliente

SITUACAO_ATIVO = "ativo"
SITUACAO_INATIVO = "inativo"
SITUACAO_BAIXADO = "baixado"
SITUACAO_NAO_CLIENTE = "nao_cliente"

SITUACOES_CLIENTE = {
    SITUACAO_ATIVO: "Ativo",
    SITUACAO_INATIVO: "Inativo",
    SITUACAO_BAIXADO: "Baixado",
    SITUACAO_NAO_CLIENTE: "Não é mais cliente",
}

# ----------------------------------------------------------------------
# Situacao de um campo (inscricao, senha, licenca)

CAMPO_NAO_TEM = "nao_tem"
CAMPO_PENDENTE = "pendente"
CAMPO_AGUARDANDO_CERTIFICADO = "aguardando_certificado"
CAMPO_BAIXADA = "baixada"
CAMPO_NAO_SE_APLICA = "nao_se_aplica"
CAMPO_DEFINITIVO = "definitivo"
CAMPO_VENCIDO = "vencido"
CAMPO_OK = "ok"
CAMPO_RENOVANDO = "renovando"
CAMPO_DATA_INVALIDA = "data_invalida"

SITUACOES_CAMPO = {
    CAMPO_NAO_TEM: "Não tem",
    CAMPO_PENDENTE: "Pendente",
    CAMPO_AGUARDANDO_CERTIFICADO: "Aguardando certificado",
    CAMPO_BAIXADA: "Baixada",
    CAMPO_NAO_SE_APLICA: "Não se aplica",
    CAMPO_DEFINITIVO: "Definitivo",
    CAMPO_VENCIDO: "Vencido",
    CAMPO_OK: "Em dia",
    CAMPO_RENOVANDO: "Renovando",
    CAMPO_DATA_INVALIDA: "Data inválida — revisar",
}

# Grafias vistas na planilha da JB (estrutura lida em 22/10/2026), inclusive
# os erros de digitacao. Chave sem acento e em caixa alta.
_GRAFIAS = {
    "NAO TEM": CAMPO_NAO_TEM, "N": CAMPO_NAO_TEM, "NAO": CAMPO_NAO_TEM,
    "SEM INSCRICAO": CAMPO_NAO_TEM, "SEM IM": CAMPO_NAO_TEM,
    "NAO TEM IE": CAMPO_NAO_TEM,
    "PENDENTE": CAMPO_PENDENTE, "PENTENDE": CAMPO_PENDENTE,
    "P": CAMPO_PENDENTE, "IM PENDENTE": CAMPO_PENDENTE,
    "CD PENDENTE": CAMPO_PENDENTE, "ALVARA PENDENTE": CAMPO_PENDENTE,
    "SOCIO COM PENDENCIA": CAMPO_PENDENTE, "NAO FEZ AINDA": CAMPO_PENDENTE,
    "VERIFICAR": CAMPO_PENDENTE,
    "AGUARDANDO CERTIFICADO": CAMPO_AGUARDANDO_CERTIFICADO,
    "CERTIFICADO PENDENTE": CAMPO_AGUARDANDO_CERTIFICADO,
    "NAO TEM CERTIFICADO": CAMPO_AGUARDANDO_CERTIFICADO,
    "BAIXADA": CAMPO_BAIXADA,
    "NAO SE ENQUADRA": CAMPO_NAO_SE_APLICA,
    "NAO SE ENQUEDRA": CAMPO_NAO_SE_APLICA,
    "DEFINITIVO": CAMPO_DEFINITIVO, "DEFFINITIVO": CAMPO_DEFINITIVO,
    "VENCIDO": CAMPO_VENCIDO, "OK": CAMPO_OK, "RENOVANDO": CAMPO_RENOVANDO,
}


def chave_texto(valor) -> str:
    """Sem acento, caixa alta e espacos colapsados — so para comparar."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def texto_celula(valor, *, preservar: bool = False) -> str:
    """Celula -> texto. Inteiro gravado como float sai sem '.0'."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "SIM" if valor else "NAO"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor)
    return texto if preservar else texto.strip()


def classificar_campo(valor, *, preservar: bool = False) -> tuple[str, str]:
    """(valor, situacao): exatamente um dos dois vem preenchido (ou nenhum).

    `preservar` mantem espacos do valor — uma senha com espaco no fim e'
    outra senha."""
    texto = texto_celula(valor, preservar=preservar)
    if not texto.strip():
        return "", ""
    situacao = _GRAFIAS.get(chave_texto(texto))
    if situacao:
        return "", situacao
    return texto, ""


# ----------------------------------------------------------------------
# Documento


def normalizar_documento(valor) -> str:
    """CNPJ (14) ou CPF (11), so digitos, com DV conferido.

    Numero de celula perde zeros a esquerda. Completar com zeros so vale
    quando o DV confere no tamanho completado; se servir como CPF e como CNPJ
    ao mesmo tempo, e' ambiguo e fica recusado."""
    if isinstance(valor, bool) or valor is None:
        raise ErroClientes(DOCUMENTO_INVALIDO, "Informe o CNPJ ou o CPF.")
    numerico = isinstance(valor, (int, float))
    digitos = re.sub(r"\D", "", texto_celula(valor))
    if not digitos:
        raise ErroClientes(DOCUMENTO_INVALIDO, "Informe o CNPJ ou o CPF.")

    candidatos: list[str] = []
    if numerico and len(digitos) < 14:
        tentativas = [digitos.zfill(11), digitos.zfill(14)] if len(digitos) <= 11 \
            else [digitos.zfill(14)]
    else:
        tentativas = [digitos]
    for tentativa in tentativas:
        try:
            if len(tentativa) == 14:
                candidatos.append(digitos_cnpj(tentativa))
            elif len(tentativa) == 11:
                candidatos.append(digitos_cpf(tentativa))
        except DocumentoInvalido:
            continue
    if len(candidatos) == 1:
        return candidatos[0]
    if len(candidatos) > 1:
        raise ErroClientes(DOCUMENTO_INVALIDO,
                           f"'{digitos}' serve como CPF e como CNPJ: informe "
                           "o documento com os zeros da frente.")
    raise ErroClientes(DOCUMENTO_INVALIDO,
                       f"'{texto_celula(valor)}' não é CNPJ nem CPF válido.")


def tipo_documento(documento: str) -> str:
    return {14: "cnpj", 11: "cpf"}.get(len(documento or ""), "")


def formatar_documento(documento: str) -> str:
    d = documento or ""
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d


def texto_obrigatorio(valor, rotulo: str, *, maximo: int) -> str:
    texto = re.sub(r"\s+", " ", str(valor or "")).strip()
    if not texto:
        raise ErroClientes(CAMPO_OBRIGATORIO, f"{rotulo} é obrigatório.")
    if len(texto) > maximo:
        raise ErroClientes(VALOR_INVALIDO,
                           f"{rotulo} passa de {maximo} caracteres.")
    return texto


# ----------------------------------------------------------------------
# Datas e vencimentos

ANO_MINIMO = 1990
ANO_MAXIMO = 2100


_DATA_BR = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_ERROS_EXCEL = {"#REF!", "#N/A", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!",
                "#NULL!", "#SPILL!", "#CALC!"}


def erro_do_excel(valor) -> bool:
    """Celula que guarda erro de formula ('#REF!'), nao um dado."""
    return isinstance(valor, str) and valor.strip().upper() in _ERROS_EXCEL


def data_plausivel(valor) -> date | None:
    """Data de celula, ISO ou dd/mm/aaaa; ano absurdo (2878) e texto viram
    None."""
    if isinstance(valor, datetime):
        valor = valor.date()
    elif isinstance(valor, str):
        texto = valor.strip()
        brasileira = _DATA_BR.fullmatch(texto)
        try:
            if brasileira:
                dia, mes, ano = (int(g) for g in brasileira.groups())
                valor = date(ano, mes, dia)
            else:
                valor = date.fromisoformat(texto)
        except ValueError:
            return None
    if not isinstance(valor, date):
        return None
    if not ANO_MINIMO <= valor.year <= ANO_MAXIMO:
        return None
    return valor


FAIXAS_PADRAO = (15, 20, 30)
FAIXA_VENCIDO = "vencido"
FAIXA_EM_DIA = "em_dia"
FAIXA_SEM_DATA = "sem_data"


def validar_faixas(faixas) -> tuple[int, ...]:
    """1 a 5 prazos em dias, entre 1 e 365, ordenados e sem repeticao."""
    try:
        numeros = sorted({int(f) for f in faixas})
    except (TypeError, ValueError) as exc:
        raise ErroClientes(FAIXAS_INVALIDAS,
                           "Os prazos de aviso devem ser números de dias.") from exc
    if not 1 <= len(numeros) <= 5 or not all(1 <= n <= 365 for n in numeros):
        raise ErroClientes(FAIXAS_INVALIDAS,
                           "Informe de 1 a 5 prazos, cada um entre 1 e 365 dias.")
    return tuple(numeros)


def rotulo_faixa(faixa: str) -> str:
    if faixa == FAIXA_VENCIDO:
        return "Vencido"
    if faixa == FAIXA_EM_DIA:
        return "Em dia"
    if faixa == FAIXA_SEM_DATA:
        return "Sem data"
    return f"Vence em até {faixa.split('_')[1]} dias"


def classificar_vencimento(fim, hoje: date,
                           faixas=FAIXAS_PADRAO) -> tuple[str, int | None]:
    """(faixa, dias restantes). Vence hoje = 0 dias, ainda na faixa curta."""
    if isinstance(fim, datetime):
        fim = fim.date()
    if isinstance(fim, str):
        fim = data_plausivel(fim)
    if fim is None:
        return FAIXA_SEM_DATA, None
    dias = (fim - hoje).days
    if dias < 0:
        return FAIXA_VENCIDO, dias
    for limite in validar_faixas(faixas):
        if dias <= limite:
            return f"ate_{limite}", dias
    return FAIXA_EM_DIA, dias
