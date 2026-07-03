"""Persistencia do estado de conferencia (Item 3).

Guarda, por chave de acesso, se a nota foi conferida, a observacao registrada e
a data da conferencia. Usa SQLite (modulo padrao do Python) para que o estado
persista entre sessoes. Chaveado pela chave de acesso, o estado acompanha a nota
independentemente da origem (SPED ou XML).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime


def pasta_dados() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    pasta = os.path.join(base, "AuditoriaFiscal")
    os.makedirs(pasta, exist_ok=True)
    return pasta


@dataclass
class EstadoConferencia:
    chave: str
    conferida: bool = False
    observacao: str = ""
    data_conferencia: str = ""


class ConferenciaStore:
    """Armazenamento SQLite do estado de conferencia por chave."""

    def __init__(self, caminho_db: str | None = None):
        if caminho_db is None:
            caminho_db = os.path.join(pasta_dados(), "conferencia.db")
        self.caminho_db = caminho_db
        self._conn = sqlite3.connect(caminho_db)
        self._conn.row_factory = sqlite3.Row
        self._criar()

    def _criar(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS conferencia ("
            "  chave TEXT PRIMARY KEY,"
            "  conferida INTEGER NOT NULL DEFAULT 0,"
            "  observacao TEXT NOT NULL DEFAULT '',"
            "  data_conferencia TEXT NOT NULL DEFAULT ''"
            ")")
        self._conn.commit()

    def obter(self, chave: str) -> EstadoConferencia:
        cur = self._conn.execute(
            "SELECT chave, conferida, observacao, data_conferencia"
            " FROM conferencia WHERE chave = ?", (chave,))
        row = cur.fetchone()
        if row is None:
            return EstadoConferencia(chave)
        return EstadoConferencia(row["chave"], bool(row["conferida"]),
                                 row["observacao"], row["data_conferencia"])

    def carregar(self) -> dict[str, EstadoConferencia]:
        cur = self._conn.execute(
            "SELECT chave, conferida, observacao, data_conferencia FROM conferencia")
        return {
            row["chave"]: EstadoConferencia(row["chave"], bool(row["conferida"]),
                                            row["observacao"], row["data_conferencia"])
            for row in cur.fetchall()
        }

    def salvar(self, chave: str, conferida: bool, observacao: str) -> EstadoConferencia:
        # Preserva a data original se ja estava conferida; grava nova ao conferir.
        anterior = self.obter(chave)
        if conferida:
            data = anterior.data_conferencia or datetime.now().strftime("%d/%m/%Y %H:%M")
        else:
            data = ""
        self._conn.execute(
            "INSERT INTO conferencia(chave, conferida, observacao, data_conferencia)"
            " VALUES(?,?,?,?)"
            " ON CONFLICT(chave) DO UPDATE SET"
            "  conferida=excluded.conferida,"
            "  observacao=excluded.observacao,"
            "  data_conferencia=excluded.data_conferencia",
            (chave, 1 if conferida else 0, observacao, data))
        self._conn.commit()
        return EstadoConferencia(chave, conferida, observacao, data)

    def fechar(self) -> None:
        self._conn.close()
