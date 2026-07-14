"""Infraestrutura da versao web: pastas de dados e serializacao JSON.

Os dados do servidor vivem em `dados_web/` na raiz do projeto (gitignored):
banco de usuarios, banco de conferencia compartilhado, uploads por sessao de
trabalho e historico de produtos. O caminho pode ser trocado pela variavel de
ambiente AUDITORIA_WEB_DADOS (util nos testes).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

from ..core.utils import formatar_moeda


def raiz_projeto() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))


def pasta_dados_web() -> str:
    pasta = os.environ.get("AUDITORIA_WEB_DADOS") or os.path.join(
        raiz_projeto(), "dados_web")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def caminho_db_usuarios() -> str:
    return os.path.join(pasta_dados_web(), "auditoria_web.db")


def caminho_db_conferencia() -> str:
    return os.path.join(pasta_dados_web(), "conferencia.db")


def caminho_historico_produtos() -> str:
    return os.path.join(pasta_dados_web(), "historico_produtos.csv")


def pasta_sessoes() -> str:
    pasta = os.path.join(pasta_dados_web(), "sessoes")
    os.makedirs(pasta, exist_ok=True)
    return pasta


# ----------------------------------------------------------------------
# Serializacao JSON (Decimal e datas nao serializam nativamente)

def texto_moeda(valor) -> str:
    """Decimal/None -> 'R$ 1.234,56' (ou '')."""
    if valor in (None, ""):
        return ""
    return formatar_moeda(valor, True)


def texto_data(valor) -> str:
    """date/datetime/None -> 'dd/mm/aaaa' (ou '')."""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    return str(valor or "")


def json_seguro(valor):
    """Converte recursivamente Decimal/date para tipos JSON."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return texto_data(valor)
    if isinstance(valor, dict):
        return {k: json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [json_seguro(v) for v in valor]
    return valor
