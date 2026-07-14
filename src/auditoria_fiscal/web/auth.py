"""Autenticacao da versao web: usuarios + sessoes de login em SQLite.

Login simples por usuario/senha (decisao do dono, 2026-07-14): senha com
PBKDF2-HMAC-SHA256 + salt (stdlib), sessao por cookie HttpOnly com token
aleatorio. Sem usuario cadastrado, o endpoint de bootstrap cria o primeiro
administrador. O usuario logado assina conferencias/correcoes/sobrescritas
(substitui o getpass.getuser() do desktop).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

from .infra import caminho_db_usuarios

_PBKDF2_ITERACOES = 200_000
_VALIDADE_SESSAO = timedelta(hours=12)
COOKIE_SESSAO = "auditoria_sessao"


@dataclass
class Usuario:
    id: int
    nome: str
    usuario: str
    admin: bool


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(caminho_db_usuarios())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS usuario ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  usuario TEXT NOT NULL UNIQUE,"
        "  nome TEXT NOT NULL,"
        "  senha_hash TEXT NOT NULL,"
        "  salt TEXT NOT NULL,"
        "  admin INTEGER NOT NULL DEFAULT 0,"
        "  ativo INTEGER NOT NULL DEFAULT 1,"
        "  criado_em TEXT NOT NULL"
        ")")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessao_login ("
        "  token TEXT PRIMARY KEY,"
        "  usuario_id INTEGER NOT NULL,"
        "  criada_em TEXT NOT NULL,"
        "  expira_em TEXT NOT NULL"
        ")")
    conn.commit()
    return conn


def _hash_senha(senha: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(salt),
        _PBKDF2_ITERACOES).hex()


def existe_usuario() -> bool:
    with _conn() as conn:
        return conn.execute("SELECT 1 FROM usuario LIMIT 1").fetchone() is not None


def criar_usuario(usuario: str, nome: str, senha: str,
                  admin: bool = False) -> None:
    usuario = usuario.strip().lower()
    if not usuario or not senha or len(senha) < 6:
        raise ValueError("Informe usuario e senha (minimo 6 caracteres).")
    salt = secrets.token_hex(16)
    with _conn() as conn:
        try:
            conn.execute(
                "INSERT INTO usuario(usuario, nome, senha_hash, salt, admin,"
                " ativo, criado_em) VALUES(?,?,?,?,?,1,?)",
                (usuario, nome.strip() or usuario, _hash_senha(senha, salt),
                 salt, 1 if admin else 0,
                 datetime.now().strftime("%d/%m/%Y %H:%M")))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Usuario ja existe.") from exc


def autenticar(usuario: str, senha: str) -> str | None:
    """Retorna um token de sessao ou None (mensagem generica no chamador)."""
    usuario = (usuario or "").strip().lower()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM usuario WHERE usuario=? AND ativo=1",
            (usuario,)).fetchone()
        if row is None:
            return None
        if not secrets.compare_digest(
                row["senha_hash"], _hash_senha(senha or "", row["salt"])):
            return None
        token = secrets.token_urlsafe(32)
        agora = datetime.now()
        conn.execute(
            "INSERT INTO sessao_login(token, usuario_id, criada_em, expira_em)"
            " VALUES(?,?,?,?)",
            (token, row["id"], agora.isoformat(),
             (agora + _VALIDADE_SESSAO).isoformat()))
        return token


def encerrar_sessao(token: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM sessao_login WHERE token=?", (token,))


def usuario_do_token(token: str | None) -> Usuario | None:
    if not token:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT u.id, u.nome, u.usuario, u.admin, s.expira_em"
            " FROM sessao_login s JOIN usuario u ON u.id = s.usuario_id"
            " WHERE s.token=? AND u.ativo=1", (token,)).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expira_em"]) < datetime.now():
            conn.execute("DELETE FROM sessao_login WHERE token=?", (token,))
            return None
        return Usuario(id=row["id"], nome=row["nome"],
                       usuario=row["usuario"], admin=bool(row["admin"]))


def exigir_usuario(request: Request) -> Usuario:
    """Dependency do FastAPI: 401 quando nao autenticado."""
    usuario = usuario_do_token(request.cookies.get(COOKIE_SESSAO))
    if usuario is None:
        raise HTTPException(status_code=401, detail="Faca login para continuar.")
    return usuario
