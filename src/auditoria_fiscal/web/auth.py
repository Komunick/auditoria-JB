"""Autenticacao da versao web: usuarios + sessoes de login em SQLite.

Login simples por usuario/senha (decisao do dono, 2026-07-14): senha com
PBKDF2-HMAC-SHA256 + salt (stdlib), sessao por cookie HttpOnly com token
aleatorio. Sem usuario cadastrado, o endpoint de bootstrap cria o primeiro
administrador. O usuario logado assina conferencias/correcoes/sobrescritas
(substitui o getpass.getuser() do desktop).

Este modulo cuida de QUEM e o usuario; o que ele pode fazer esta em
permissoes.py e o que ele fez, em auditoria.py. Nenhum dos dois e importado
aqui no topo (auditoria.py importa este modulo) — a unica excecao e o import
tardio que registra a sessao expirada.
"""

from __future__ import annotations

import hashlib
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


def agora_br() -> str:
    """Carimbo legivel usado em todo o sistema (usuario, correcao, evento)."""
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def conexao() -> sqlite3.Connection:
    """Conexao com o banco de usuarios, com o schema garantido.

    Publica porque permissoes.py e auditoria.py guardam suas tabelas no MESMO
    banco (auditoria_web.db): usuario, permissao e historico contam a mesma
    historia e um backup unico leva tudo."""
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


def _validar_senha(senha: str) -> None:
    if not senha or len(senha) < 6:
        raise ValueError("A senha precisa de pelo menos 6 caracteres.")


def existe_usuario() -> bool:
    with conexao() as conn:
        return conn.execute("SELECT 1 FROM usuario LIMIT 1").fetchone() is not None


def criar_usuario(usuario: str, nome: str, senha: str,
                  admin: bool = False) -> int:
    """Cria e devolve o id (o chamador usa para gravar as permissoes)."""
    usuario = usuario.strip().lower()
    if not usuario:
        raise ValueError("Informe usuario e senha (minimo 6 caracteres).")
    _validar_senha(senha)
    salt = secrets.token_hex(16)
    with conexao() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO usuario(usuario, nome, senha_hash, salt, admin,"
                " ativo, criado_em) VALUES(?,?,?,?,?,1,?)",
                (usuario, nome.strip() or usuario, _hash_senha(senha, salt),
                 salt, 1 if admin else 0, agora_br()))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Usuario ja existe.") from exc
        return int(cursor.lastrowid)


def autenticar(usuario: str, senha: str) -> str | None:
    """Retorna um token de sessao ou None (mensagem generica no chamador)."""
    usuario = (usuario or "").strip().lower()
    with conexao() as conn:
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
    with conexao() as conn:
        conn.execute("DELETE FROM sessao_login WHERE token=?", (token,))


def encerrar_sessoes_do_usuario(usuario_id: int) -> None:
    """Desativar ou trocar a senha derruba quem ja estava logado."""
    with conexao() as conn:
        conn.execute("DELETE FROM sessao_login WHERE usuario_id=?",
                     (usuario_id,))


def usuario_do_token(token: str | None) -> Usuario | None:
    if not token:
        return None
    with conexao() as conn:
        row = conn.execute(
            "SELECT u.id, u.nome, u.usuario, u.admin, s.expira_em"
            " FROM sessao_login s JOIN usuario u ON u.id = s.usuario_id"
            " WHERE s.token=? AND u.ativo=1", (token,)).fetchone()
        if row is None:
            return None
        vencimento = datetime.fromisoformat(row["expira_em"])
        expirada = vencimento < datetime.now()
        if expirada:
            conn.execute("DELETE FROM sessao_login WHERE token=?", (token,))
    usuario = Usuario(id=row["id"], nome=row["nome"], usuario=row["usuario"],
                      admin=bool(row["admin"]))
    if expirada:
        # Import tardio: auditoria.py importa este modulo no topo. A sessao que
        # morre por tempo tambem e uma "saida"; carimba o momento REAL do
        # vencimento, nao o desta requisicao (que pode ser dias depois).
        from . import auditoria
        auditoria.registrar(
            "sessao.expirada", usuario,
            quando=(vencimento.isoformat(timespec="seconds"),
                    vencimento.strftime("%d/%m/%Y %H:%M")))
        return None
    return usuario


def exigir_usuario(request: Request) -> Usuario:
    """Dependency do FastAPI: 401 quando nao autenticado."""
    usuario = usuario_do_token(request.cookies.get(COOKIE_SESSAO))
    if usuario is None:
        raise HTTPException(status_code=401, detail="Faca login para continuar.")
    return usuario


# ----------------------------------------------------------------------
# Administracao de usuarios


def _linha_usuario(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "usuario": row["usuario"], "nome": row["nome"],
            "admin": bool(row["admin"]), "ativo": bool(row["ativo"]),
            "criado_em": row["criado_em"]}


def listar_usuarios() -> list[dict]:
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM usuario ORDER BY admin DESC, usuario").fetchall()
    return [_linha_usuario(linha) for linha in linhas]


def obter_usuario(usuario_id: int) -> dict | None:
    with conexao() as conn:
        row = conn.execute("SELECT * FROM usuario WHERE id=?",
                           (usuario_id,)).fetchone()
    return _linha_usuario(row) if row else None


def _total_admins_ativos(conn: sqlite3.Connection, exceto: int = 0) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM usuario WHERE admin=1 AND ativo=1"
        " AND id<>?", (exceto,)).fetchone()["n"]


def atualizar_usuario(usuario_id: int, nome: str, admin: bool,
                      ativo: bool) -> dict:
    """Guarda o sistema de ficar sem dono: o ULTIMO administrador ativo nao
    pode ser rebaixado nem desativado (ninguem mais criaria usuarios).

    BEGIN IMMEDIATE serializa a guarda: sem ele, dois rebaixamentos simultaneos
    (os dois administradores um contra o outro) leem "ainda sobra 1 admin" ao
    mesmo tempo e zeram os administradores. O lock de escrita forca a segunda
    a esperar e a ver o estado ja atualizado."""
    with conexao() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM usuario WHERE id=?",
                           (usuario_id,)).fetchone()
        if row is None:
            raise ValueError("Usuario nao encontrado.")
        perde_admin = bool(row["admin"]) and (not admin or not ativo)
        if perde_admin and _total_admins_ativos(conn, exceto=usuario_id) == 0:
            raise ValueError(
                "Este e o ultimo administrador ativo. Promova outro usuario a "
                "administrador antes de alterar este.")
        conn.execute(
            "UPDATE usuario SET nome=?, admin=?, ativo=? WHERE id=?",
            (nome.strip() or row["usuario"], 1 if admin else 0,
             1 if ativo else 0, usuario_id))
        if not ativo:
            conn.execute("DELETE FROM sessao_login WHERE usuario_id=?",
                         (usuario_id,))
        atualizado = conn.execute("SELECT * FROM usuario WHERE id=?",
                                  (usuario_id,)).fetchone()
    return _linha_usuario(atualizado)


def trocar_senha(usuario_id: int, senha: str) -> None:
    """Troca a senha e derruba as sessoes abertas daquele usuario."""
    _validar_senha(senha)
    salt = secrets.token_hex(16)
    with conexao() as conn:
        alterou = conn.execute(
            "UPDATE usuario SET senha_hash=?, salt=? WHERE id=?",
            (_hash_senha(senha, salt), salt, usuario_id)).rowcount
        if not alterou:
            raise ValueError("Usuario nao encontrado.")
        conn.execute("DELETE FROM sessao_login WHERE usuario_id=?",
                     (usuario_id,))
