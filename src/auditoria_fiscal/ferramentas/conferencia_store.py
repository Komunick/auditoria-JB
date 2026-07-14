"""Persistencia do estado de conferencia (Item 3).

Guarda, por chave de acesso, se a nota foi conferida, a observacao registrada e
a data da conferencia. Usa SQLite (modulo padrao do Python) para que o estado
persista entre sessoes. Chaveado pela chave de acesso, o estado acompanha a nota
independentemente da origem (SPED ou XML).

Tambem persiste as CORRECOES de campos fiscais (tabela `correcao`), com a
trilha completa de auditoria: valor original, valor corrigido, campo, usuario,
data/hora, tipo (manual/automatica), motivo, status e a inconsistencia que a
originou. Registrar aqui e o UNICO caminho de gravacao — a interface nunca
aplica correcao sem persistir.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..core.correcoes import (
    Correcao, STATUS_APLICADA, STATUS_REVERTIDA, TIPO_MANUAL,
    normalizar_valor, validar_correcao,
)


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


@dataclass
class OverrideComposicao:
    """Texto digitado pelo usuario sobre uma celula da composicao fiscal.

    Diferente da correcao (que altera itens e recalcula), a sobrescrita
    substitui o TEXTO exibido de uma celula calculada — na tela e no Livro
    Fiscal (PDF). O valor calculado original fica preservado para auditoria.
    """

    chave: str
    grupo: str      # chave_grupo(g) ou GRUPO_TOTAL
    coluna: int     # indice da coluna na tabela da composicao (0-7)
    valor: str
    valor_original: str = ""
    usuario: str = ""
    data_hora: str = ""


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
        # Migracao aditiva: bancos existentes ganham a tabela sem perder nada.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS correcao ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  chave TEXT NOT NULL,"
            "  campo TEXT NOT NULL,"
            "  valor_original TEXT NOT NULL,"
            "  valor_corrigido TEXT NOT NULL,"
            "  usuario TEXT NOT NULL,"
            "  data_hora TEXT NOT NULL,"
            "  tipo TEXT NOT NULL DEFAULT 'manual',"
            "  motivo TEXT NOT NULL DEFAULT '',"
            "  status TEXT NOT NULL DEFAULT 'aplicada',"
            "  inconsistencia TEXT NOT NULL DEFAULT ''"
            ")")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_correcao_chave"
            " ON correcao(chave)")
        # Migracao aditiva: sobrescritas manuais da composicao fiscal.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS composicao_override ("
            "  chave TEXT NOT NULL,"
            "  grupo TEXT NOT NULL,"
            "  coluna INTEGER NOT NULL,"
            "  valor TEXT NOT NULL,"
            "  valor_original TEXT NOT NULL DEFAULT '',"
            "  usuario TEXT NOT NULL DEFAULT '',"
            "  data_hora TEXT NOT NULL DEFAULT '',"
            "  PRIMARY KEY (chave, grupo, coluna)"
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

    # ------------------------------------------------------------------
    # Correcoes de campos fiscais (auditoria completa)

    def registrar_correcao(self, chave: str, campo: str, valor_original,
                           valor_corrigido, usuario: str,
                           tipo: str = TIPO_MANUAL, motivo: str = "",
                           inconsistencia: str = "") -> Correcao:
        """Valida e persiste uma correcao. Levanta ValueError se invalida."""
        validar_correcao(campo, valor_original, valor_corrigido, usuario)
        correcao = Correcao(
            chave=chave, campo=campo,
            valor_original=normalizar_valor(campo, valor_original),
            valor_corrigido=normalizar_valor(campo, valor_corrigido),
            usuario=str(usuario).strip(),
            data_hora=datetime.now().strftime("%d/%m/%Y %H:%M"),
            tipo=tipo, motivo=motivo.strip(),
            status=STATUS_APLICADA, inconsistencia=inconsistencia.strip())
        cur = self._conn.execute(
            "INSERT INTO correcao(chave, campo, valor_original,"
            " valor_corrigido, usuario, data_hora, tipo, motivo, status,"
            " inconsistencia) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (correcao.chave, correcao.campo, correcao.valor_original,
             correcao.valor_corrigido, correcao.usuario, correcao.data_hora,
             correcao.tipo, correcao.motivo, correcao.status,
             correcao.inconsistencia))
        self._conn.commit()
        correcao.id = cur.lastrowid
        return correcao

    def reverter_correcao(self, id_correcao: int, usuario: str) -> None:
        """Marca a correcao como revertida (o registro e preservado)."""
        if not str(usuario or "").strip():
            raise ValueError("Informe o usuario responsavel pela reversao.")
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        self._conn.execute(
            "UPDATE correcao SET status=?, motivo=motivo || ?"
            " WHERE id=?",
            (STATUS_REVERTIDA,
             f" [revertida por {usuario.strip()} em {agora}]", id_correcao))
        self._conn.commit()

    def _correcao_de_row(self, row) -> Correcao:
        return Correcao(
            id=row["id"], chave=row["chave"], campo=row["campo"],
            valor_original=row["valor_original"],
            valor_corrigido=row["valor_corrigido"], usuario=row["usuario"],
            data_hora=row["data_hora"], tipo=row["tipo"],
            motivo=row["motivo"], status=row["status"],
            inconsistencia=row["inconsistencia"])

    def correcoes_da_chave(self, chave: str) -> list[Correcao]:
        cur = self._conn.execute(
            "SELECT * FROM correcao WHERE chave=? ORDER BY id", (chave,))
        return [self._correcao_de_row(r) for r in cur.fetchall()]

    def todas_correcoes(self) -> dict[str, list[Correcao]]:
        """Mapa chave -> correcoes (na ordem em que foram registradas)."""
        cur = self._conn.execute("SELECT * FROM correcao ORDER BY id")
        mapa: dict[str, list[Correcao]] = {}
        for row in cur.fetchall():
            mapa.setdefault(row["chave"], []).append(self._correcao_de_row(row))
        return mapa

    # ------------------------------------------------------------------
    # Sobrescritas manuais da composicao fiscal (texto por celula)

    def salvar_override(self, chave: str, grupo: str, coluna: int,
                        valor: str, valor_original: str,
                        usuario: str) -> None:
        """Grava a sobrescrita; valor vazio REMOVE (volta ao calculado)."""
        if not str(valor).strip():
            self._conn.execute(
                "DELETE FROM composicao_override"
                " WHERE chave=? AND grupo=? AND coluna=?",
                (chave, grupo, coluna))
        else:
            agora = datetime.now().strftime("%d/%m/%Y %H:%M")
            self._conn.execute(
                "INSERT INTO composicao_override(chave, grupo, coluna,"
                " valor, valor_original, usuario, data_hora)"
                " VALUES(?,?,?,?,?,?,?)"
                " ON CONFLICT(chave, grupo, coluna) DO UPDATE SET"
                "  valor=excluded.valor,"
                "  usuario=excluded.usuario,"
                "  data_hora=excluded.data_hora",
                (chave, grupo, coluna, str(valor).strip(),
                 str(valor_original), str(usuario).strip(), agora))
        self._conn.commit()

    def _override_de_row(self, row) -> OverrideComposicao:
        return OverrideComposicao(
            chave=row["chave"], grupo=row["grupo"], coluna=row["coluna"],
            valor=row["valor"], valor_original=row["valor_original"],
            usuario=row["usuario"], data_hora=row["data_hora"])

    def overrides_da_chave(
            self, chave: str) -> dict[tuple[str, int], OverrideComposicao]:
        cur = self._conn.execute(
            "SELECT * FROM composicao_override WHERE chave=?", (chave,))
        return {(r["grupo"], r["coluna"]): self._override_de_row(r)
                for r in cur.fetchall()}

    def todas_overrides(
            self) -> dict[str, dict[tuple[str, int], OverrideComposicao]]:
        """Mapa chave -> {(grupo, coluna) -> sobrescrita}."""
        cur = self._conn.execute("SELECT * FROM composicao_override")
        mapa: dict[str, dict[tuple[str, int], OverrideComposicao]] = {}
        for row in cur.fetchall():
            mapa.setdefault(row["chave"], {})[
                (row["grupo"], row["coluna"])] = self._override_de_row(row)
        return mapa

    def fechar(self) -> None:
        self._conn.close()
