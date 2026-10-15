"""Validadores brasileiros compartilhados: CPF, CNPJ e decimal monetario.

Extraidos de `core/patrimonio.py` (CPF) e `core/conciliacao_sefaz.py` (CNPJ e
decimal) quando a Emissao de NFS-e passou a precisar dos tres (spec 006,
plan.md, "Validadores compartilhados"). Importar de outra ferramenta acoplaria
dominios; copiar duplicaria um controle que alguem um dia corrige de um lado
so.

O erro aqui e' neutro: cada modulo que usa estas funcoes traduz para a sua
propria excecao e mensagem, e assim o comportamento visto por fora nao muda.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

CPF_INVALIDO = "CPF_INVALIDO"
CNPJ_INVALIDO = "CNPJ_INVALIDO"
VALOR_INVALIDO = "VALOR_INVALIDO"
VALOR_VAZIO = "VALOR_VAZIO"
FORMULA_SEM_VALOR = "FORMULA_SEM_VALOR"

CENTAVO = Decimal("0.01")


class DocumentoInvalido(ValueError):
    """`codigo` diz o campo; `motivo` diz o porque (`tamanho`, `repetidos`,
    `dv`) para quem precisa montar a propria mensagem."""

    def __init__(self, codigo: str, mensagem: str, *, motivo: str = ""):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.motivo = motivo


# ----------------------------------------------------------------------
# CPF e CNPJ


def digitos_cpf(valor) -> str:
    """CPF com 11 digitos e DV conferido. Vazio e' erro (`tamanho`): quem
    aceita CPF opcional decide isso antes de chamar."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) != 11:
        raise DocumentoInvalido(CPF_INVALIDO, "CPF deve ter 11 dígitos.",
                                motivo="tamanho")
    if digitos == digitos[0] * 11:
        raise DocumentoInvalido(CPF_INVALIDO, "CPF com dígitos repetidos.",
                                motivo="repetidos")
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(digitos[tamanho]):
            raise DocumentoInvalido(CPF_INVALIDO,
                                    "Dígito verificador do CPF não confere.",
                                    motivo="dv")
    return digitos


def dv_cnpj(base12: str) -> str:
    def _dv(numero: str) -> str:
        pesos = [p if p <= 9 else p - 8
                 for p in range(len(numero) + 1, 1, -1)]
        soma = sum(int(d) * p for d, p in zip(numero, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = _dv(base12)
    return d1 + _dv(base12 + d1)


def digitos_cnpj(valor) -> str:
    """CNPJ com 14 digitos e DV conferido."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) != 14:
        raise DocumentoInvalido(CNPJ_INVALIDO, "CNPJ deve ter 14 digitos.",
                                motivo="tamanho")
    if digitos == digitos[0] * 14:
        # 00.000.000/0000-00 e afins passam no calculo mas nao existem.
        raise DocumentoInvalido(CNPJ_INVALIDO, "CNPJ com digitos repetidos.",
                                motivo="repetidos")
    if dv_cnpj(digitos[:12]) != digitos[12:]:
        raise DocumentoInvalido(CNPJ_INVALIDO,
                                "Digito verificador do CNPJ nao confere.",
                                motivo="dv")
    return digitos


# ----------------------------------------------------------------------
# Decimal monetario


def _grupos_de_milhar_ok(inteiro: str, separador: str) -> bool:
    partes = inteiro.split(separador)
    if len(partes) == 1:
        return True
    if not 1 <= len(partes[0]) <= 3:
        return False
    return all(len(p) == 3 for p in partes[1:])


def _quantizar(numero: Decimal, original) -> Decimal:
    """Numero de celula ja e' exato; sub-centavo e' recusado, nao arredondado."""
    if numero != numero.quantize(CENTAVO):
        raise DocumentoInvalido(
            VALOR_INVALIDO,
            f"{original!r} tem fracao de centavo em campo monetario.")
    return numero.quantize(CENTAVO)


def decimal_monetario(valor) -> Decimal:
    """Numero monetario exato. Formato ambiguo e' RECUSADO, nunca chutado.

    `1.234` pode ser mil duzentos e trinta e quatro (milhar brasileiro) ou um
    virgula dois tres quatro (decimal americano). Escolher errado erra por
    1000x num numero fiscal, entao o parser exige que o separador decimal
    seja inequivoco.
    """
    if isinstance(valor, bool):           # bool e' int em Python; aqui nao serve
        raise DocumentoInvalido(VALOR_INVALIDO,
                                "Valor booleano em campo numerico.")
    if isinstance(valor, (int, float, Decimal)):
        try:
            numero = Decimal(str(valor))
        except InvalidOperation as exc:
            raise DocumentoInvalido(VALOR_INVALIDO,
                                    f"Numero invalido: {valor!r}") from exc
        return _quantizar(numero, valor)

    bruto = str(valor or "").strip()
    if not bruto:
        raise DocumentoInvalido(VALOR_VAZIO, "Valor vazio.")
    if bruto.startswith("="):
        # data_only=True devolveu a formula: o cache de valor nao existe.
        raise DocumentoInvalido(FORMULA_SEM_VALOR,
                                "Formula sem valor calculado armazenado.")
    if not re.fullmatch(r"[+-]?[\d.,\s]+", bruto):
        raise DocumentoInvalido(
            VALOR_INVALIDO,
            f"'{bruto}' nao e' numero (simbolo de moeda ou texto).")

    sinal = -1 if bruto.startswith("-") else 1
    corpo = bruto.lstrip("+-").replace(" ", "")
    tem_ponto, tem_virgula = "." in corpo, "," in corpo

    if tem_ponto and tem_virgula:
        # O ultimo separador a aparecer e' o decimal.
        decimal_sep = "." if corpo.rfind(".") > corpo.rfind(",") else ","
        milhar_sep = "," if decimal_sep == "." else "."
        inteiro, _, fracao = corpo.rpartition(decimal_sep)
        if not _grupos_de_milhar_ok(inteiro, milhar_sep):
            raise DocumentoInvalido(VALOR_INVALIDO,
                                    f"Separadores inconsistentes em '{bruto}'.")
        inteiro = inteiro.replace(milhar_sep, "")
    elif tem_ponto or tem_virgula:
        sep = "." if tem_ponto else ","
        if corpo.count(sep) > 1:
            # Varios separadores iguais so podem ser milhar.
            if not _grupos_de_milhar_ok(corpo, sep):
                raise DocumentoInvalido(
                    VALOR_INVALIDO, f"Grupos de milhar invalidos em '{bruto}'.")
            inteiro, fracao = corpo.replace(sep, ""), ""
        else:
            inteiro, _, fracao = corpo.partition(sep)
            if len(fracao) == 3:
                raise DocumentoInvalido(
                    VALOR_INVALIDO,
                    f"'{bruto}' e' ambiguo: '{sep}' pode ser milhar ou decimal.")
            if not fracao or not fracao.isdigit():
                raise DocumentoInvalido(VALOR_INVALIDO,
                                        f"Parte decimal invalida em '{bruto}'.")
    else:
        inteiro, fracao = corpo, ""

    if not inteiro.isdigit() or (fracao and not fracao.isdigit()):
        raise DocumentoInvalido(VALOR_INVALIDO, f"Numero invalido: '{bruto}'.")
    if len(fracao) > 2:
        raise DocumentoInvalido(
            VALOR_INVALIDO,
            f"'{bruto}' tem fracao de centavo; valor monetario para em 2 casas.")

    texto = inteiro + ("." + fracao if fracao else "")
    return (Decimal(texto) * sinal).quantize(CENTAVO)
