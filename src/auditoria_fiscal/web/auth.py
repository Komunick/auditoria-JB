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
import time
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
    # Dois primeiros acessos ao banco legado podem migrar ao mesmo tempo.
    # O lock precede a leitura do schema, para que o segundo veja a coluna
    # adicionada pelo primeiro em vez de repetir o ALTER TABLE.
    conn.execute('BEGIN IMMEDIATE')
    try:
        if 'email' not in {r['name'] for r in conn.execute('PRAGMA table_info(usuario)')}:
            conn.execute("ALTER TABLE usuario ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    # Limite de tentativas de login (ver autenticar). No banco, e nao em
    # memoria, para que reiniciar o servidor nao zere um bloqueio.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tentativa_login ("
        "  chave TEXT PRIMARY KEY,"      # 'conta:<usuario>' ou 'ip:<endereco>'
        "  falhas INTEGER NOT NULL DEFAULT 0,"
        "  primeira_em TEXT NOT NULL,"
        "  ultima_em TEXT NOT NULL,"
        "  bloqueado_ate TEXT"
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
                  admin: bool = False, email: str = '') -> int:
    """Cria e devolve o id (o chamador usa para gravar as permissoes)."""
    usuario = usuario.strip().lower()
    if not usuario:
        raise ValueError("Informe usuario e senha (minimo 6 caracteres).")
    _validar_senha(senha)
    email = _validar_email(email)
    salt = secrets.token_hex(16)
    with conexao() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO usuario(usuario, nome, senha_hash, salt, admin,"
                " ativo, criado_em, email) VALUES(?,?,?,?,?,1,?,?)",
                (usuario, nome.strip() or usuario, _hash_senha(senha, salt),
                 salt, 1 if admin else 0, agora_br(), email))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Usuario ja existe.") from exc
        return int(cursor.lastrowid)


# ----------------------------------------------------------------------
# Limite de tentativas de login (portado do clone do Cadastro JB, SEC-03 e
# R2-NEW-01 da auditoria de 23/08/2026)
#
# Dois niveis, para que errar a senha de alguem nao tire essa pessoa do
# sistema:
#   * BLOQUEIO por IP: 8 falhas em 15 minutos param de ser atendidas por 1
#     minuto; insistindo, 5 min, 15 min e 1 h. So aquele IP fica de fora.
#   * ATRASO na conta: a partir da 8a falha recente, cada login daquela
#     conta espera um pouco mais (ate 2 s), venha de onde vier. Nunca recusa:
#     quem tem a senha entra de outro lugar, mas o ataque espalhado em muitos
#     IPs fica caro.
# Login certo zera os contadores daquele IP e daquela conta.
MAX_FALHAS = 8
JANELA_FALHAS = timedelta(minutes=15)
BLOQUEIOS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15),
             timedelta(hours=1))
ATRASO_MAXIMO_CONTA = 2.0
# O usuario digitado vira chave do contador: sem teto, um nome gigante
# viraria uma linha gigante no banco.
_TAMANHO_CHAVE_USUARIO = 64


class LoginBloqueado(Exception):
    """Limite atingido; `segundos` diz quanto falta para liberar."""

    def __init__(self, segundos: float) -> None:
        super().__init__("Muitas tentativas seguidas.")
        self.segundos = max(1, int(segundos + 0.999))


def _chaves_limite(usuario: str, ip: str) -> list[str]:
    chaves = [f"conta:{usuario[:_TAMANHO_CHAVE_USUARIO]}"] if usuario else []
    if ip:
        chaves.append(f"ip:{ip}")
    return chaves


def _conferir_bloqueio(conn: sqlite3.Connection, chaves: list[str]) -> None:
    """Levanta LoginBloqueado se o IP estiver bloqueado (a conta nunca e)."""
    agora = datetime.now()
    for chave in chaves:
        if not chave.startswith("ip:"):
            continue
        linha = conn.execute(
            "SELECT bloqueado_ate FROM tentativa_login WHERE chave=?",
            (chave,)).fetchone()
        if linha and linha["bloqueado_ate"]:
            ate = datetime.fromisoformat(linha["bloqueado_ate"])
            if ate > agora:
                raise LoginBloqueado((ate - agora).total_seconds())


def _atraso_da_conta(conn: sqlite3.Connection, usuario: str) -> float:
    if not usuario:
        return 0.0
    linha = conn.execute(
        "SELECT falhas, primeira_em FROM tentativa_login WHERE chave=?",
        (_chaves_limite(usuario, "")[0],)).fetchone()
    if not linha or (datetime.now() - datetime.fromisoformat(
            linha["primeira_em"])) > JANELA_FALHAS:
        return 0.0
    excedente = max(0, int(linha["falhas"]) - MAX_FALHAS + 1)
    return min(0.25 * excedente, ATRASO_MAXIMO_CONTA)


def _registrar_falha(conn: sqlite3.Connection, chaves: list[str]) -> None:
    """Conta a falha numa UPSERT so (sem ler-e-escrever, que perderia falhas
    simultaneas) e, se for o caso, bloqueia o IP."""
    agora = datetime.now()
    agora_iso = agora.isoformat(timespec="seconds")
    limite = (agora - JANELA_FALHAS).isoformat(timespec="seconds")
    # Contadores fora da janela e sem bloqueio vigente nao servem mais para
    # nada; apagar aqui mantem a tabela do tamanho dos ultimos 15 minutos.
    conn.execute(
        "DELETE FROM tentativa_login WHERE primeira_em < ? AND"
        " (bloqueado_ate IS NULL OR bloqueado_ate < ?)", (limite, agora_iso))
    for chave in chaves:
        conn.execute(
            "INSERT INTO tentativa_login(chave, falhas, primeira_em, ultima_em)"
            " VALUES(?, 1, ?, ?)"
            " ON CONFLICT(chave) DO UPDATE SET"
            "  falhas = CASE WHEN primeira_em < ? THEN 1 ELSE falhas + 1 END,"
            "  primeira_em = CASE WHEN primeira_em < ?"
            "    THEN excluded.primeira_em ELSE primeira_em END,"
            "  ultima_em = excluded.ultima_em",
            (chave, agora_iso, agora_iso, limite, limite))
        if not chave.startswith("ip:"):
            continue
        falhas = conn.execute(
            "SELECT falhas FROM tentativa_login WHERE chave=?",
            (chave,)).fetchone()["falhas"]
        if falhas >= MAX_FALHAS:
            passo = min((falhas - MAX_FALHAS) // 4, len(BLOQUEIOS) - 1)
            conn.execute(
                "UPDATE tentativa_login SET bloqueado_ate=? WHERE chave=?",
                ((agora + BLOQUEIOS[passo]).isoformat(timespec="seconds"),
                 chave))


def autenticar(usuario: str, senha: str, ip: str = "") -> str | None:
    """Retorna um token de sessao ou None (mensagem generica no chamador).

    `ip` vem de seguranca.ip_do_cliente; vazio = so o atraso da conta vale.
    Levanta LoginBloqueado quando aquele IP passou do limite — antes de
    calcular a senha, para o bloqueado nao custar PBKDF2 ao servidor."""
    usuario = (usuario or "").strip().lower()
    chaves = _chaves_limite(usuario, ip)
    with conexao() as conn:
        _conferir_bloqueio(conn, chaves)
        atraso = _atraso_da_conta(conn, usuario)
    if atraso:
        time.sleep(atraso)
    with conexao() as conn:
        row = conn.execute(
            "SELECT * FROM usuario WHERE usuario=? AND ativo=1",
            (usuario,)).fetchone()
        if row is None or not secrets.compare_digest(
                row["senha_hash"], _hash_senha(senha or "", row["salt"])):
            _registrar_falha(conn, chaves)
            return None
        for chave in chaves:
            conn.execute("DELETE FROM tentativa_login WHERE chave=?", (chave,))
        token = secrets.token_urlsafe(32)
        agora = datetime.now()
        conn.execute(
            "INSERT INTO sessao_login(token, usuario_id, criada_em, expira_em)"
            " VALUES(?,?,?,?)",
            (token, row["id"], agora.isoformat(),
             (agora + _VALIDADE_SESSAO).isoformat()))
        return token


def conferir_senha(usuario_id: int, senha: str) -> bool:
    """Confere a senha de quem ja esta logado, sem abrir sessao nova.

    Usado antes de revelar senha de cliente (spec 012): a sessao aberta num
    computador esquecido nao basta para abrir o cofre."""
    with conexao() as conn:
        row = conn.execute(
            "SELECT senha_hash, salt FROM usuario WHERE id=? AND ativo=1",
            (usuario_id,)).fetchone()
    if row is None:
        return False
    return secrets.compare_digest(row["senha_hash"],
                                  _hash_senha(senha or "", row["salt"]))


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
            "criado_em": row["criado_em"], "email": row["email"]}


def _validar_email(email: str) -> str:
    from ..ferramentas.alertas_email import email_valido
    email = email.strip()
    if email and not email_valido(email):
        raise ValueError('Informe um e-mail válido para os alertas.')
    return email


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
                      ativo: bool, email: str | None = None) -> dict:
    """Guarda o sistema de ficar sem dono: o ULTIMO administrador ativo nao
    pode ser rebaixado nem desativado (ninguem mais criaria usuarios).

    BEGIN IMMEDIATE serializa a guarda: sem ele, dois rebaixamentos simultaneos
    (os dois administradores um contra o outro) leem "ainda sobra 1 admin" ao
    mesmo tempo e zeram os administradores. O lock de escrita forca a segunda
    a esperar e a ver o estado ja atualizado."""
    if email is not None:
        email = _validar_email(email)
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
            "UPDATE usuario SET nome=?, admin=?, ativo=?, email=? WHERE id=?",
            (nome.strip() or row["usuario"], 1 if admin else 0,
             1 if ativo else 0, row['email'] if email is None else email, usuario_id))
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
