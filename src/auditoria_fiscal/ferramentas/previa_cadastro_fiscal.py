"""Snapshot mínimo do cadastro para a prévia Fiscal, sem abrir stores migratórios.

A conexão só lê o banco existente. Não usa ``immutable``: os registros ainda no
WAL precisam participar da mesma fotografia que os lotes seguintes. SQLite pode
manter o índice compartilhado ``-shm`` durante uma leitura; isso não é gravação
cadastral nem motivo para ignorar o WAL.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import stat

from ..core.documentos_br import DocumentoInvalido, digitos_cnpj

_TAMANHO_LOTE = 400
_CAMPOS = "id, nome, documento, contato_nome, situacao, revision"


class CadastroIndisponivel(RuntimeError):
    """Banco existente indisponível ou incompatível; nunca equivale a vazio."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _documentos_validos(documentos) -> list[str]:
    validos = set()
    for documento in documentos:
        # O chamador entrega CNPJs efetivos normalizados. Não recuperar zeros,
        # aceitar CPF ou normalizar texto livre nesta consulta ao cadastro.
        if not isinstance(documento, str) or not re.fullmatch(r"[0-9]{14}", documento):
            continue
        try:
            validos.add(digitos_cnpj(documento))
        except DocumentoInvalido:
            continue
    return sorted(validos)


def consultar_cadastro(caminho, documentos) -> dict:
    """Lê somente os CNPJs solicitados, sem criar banco, diretório ou schema.

    Ausência do arquivo é informada explicitamente. Erros de acesso, corrupção e
    schema incompatível interrompem a prévia, inclusive quando não há CNPJ válido.
    A transação única mantém consistência entre todos os lotes parametrizados.
    """
    documentos = _documentos_validos(documentos)
    conn = None
    try:
        arquivo = Path(caminho).resolve()
        try:
            metadados = arquivo.stat()
        except FileNotFoundError:
            return {"disponivel": False, "consultado_em": _agora(), "clientes": []}
        if not stat.S_ISREG(metadados.st_mode):
            raise CadastroIndisponivel("O cadastro está indisponível para consulta. Tente novamente após verificar sua disponibilidade.")

        # as_uri codifica '#', '?', '%' e espaços antes de acrescentar opções.
        # mode=ro também impede criação se o arquivo desaparecer após o stat.
        conn = sqlite3.connect(arquivo.as_uri() + "?mode=ro", uri=True,
                               timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        # Valida o schema mesmo sem documentos, sem buscar todos os clientes.
        conn.execute(f"SELECT {_CAMPOS} FROM cliente WHERE 0").fetchall()
        consultado_em = _agora()
        clientes = []
        for inicio in range(0, len(documentos), _TAMANHO_LOTE):
            lote = documentos[inicio:inicio + _TAMANHO_LOTE]
            marcadores = ",".join("?" for _ in lote)
            consulta = f"SELECT {_CAMPOS} FROM cliente WHERE documento IN ({marcadores}) ORDER BY documento,id"
            clientes.extend(dict(linha) for linha in conn.execute(consulta, lote).fetchall())
        return {"disponivel": True, "consultado_em": consultado_em, "clientes": clientes}
    except (OSError, sqlite3.Error) as exc:
        raise CadastroIndisponivel(
            "Não foi possível consultar o cadastro. Verifique sua disponibilidade e compatibilidade antes de gerar a prévia."
        ) from exc
    finally:
        if conn is not None:
            conn.close()
