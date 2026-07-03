"""Utilitarios de conversao usados pelos leitores (SPED, XML, SEFAZ)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


def para_decimal(valor: Optional[str]) -> Decimal:
    """Converte texto no formato brasileiro/SPED para Decimal.

    Aceita "1.234,56" (com separador de milhar), "1234,56", "1234.56" e "".
    Campo vazio vira Decimal("0").
    """
    if valor is None:
        return Decimal("0")
    texto = valor.strip()
    if not texto:
        return Decimal("0")

    # Formato brasileiro: virgula = decimal, ponto = milhar.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def para_data(valor: Optional[str]) -> Optional[date]:
    """Converte data do SPED (ddmmaaaa) ou formatos comuns para date.

    Retorna None se vazio ou invalido.
    """
    if not valor:
        return None
    texto = valor.strip()
    if not texto:
        return None

    formatos = ("%d%m%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def ler_texto(caminho: str) -> str:
    """Le um arquivo texto tentando os encodings comuns de SPED.

    SPED e usualmente Latin-1 (ISO-8859-1 / cp1252), mas alguns sistemas
    exportam UTF-8. latin-1 nunca falha na decodificacao, servindo de fallback.
    """
    with open(caminho, "rb") as fh:
        bruto = fh.read()

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return bruto.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 acima ja garante sucesso, mas por seguranca:
    return bruto.decode("latin-1", errors="replace")
