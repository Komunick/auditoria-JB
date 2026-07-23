"""Leitor de arquivos Firebird (.FDB) — capacidade compartilhada do site.

O ERP Symac (e vários outros do comércio) guardam os dados em bancos
Firebird. Este módulo abre um .FDB QUALQUER com o motor Firebird 2.5
"embedded" empacotado em `vendor/firebird25/` (sem instalar Firebird na
máquina), lista as tabelas e lê o conteúdo de uma tabela como texto — para
qualquer ferramenta do site consumir (a Auditoria de Produtos é a primeira).

## Isolamento em subprocesso (importante)

O motor Firebird 2.5 embedded é **EOL** e roda dentro do processo. Abrir um
.FDB não confiável (upload) direto no processo do servidor tem dois riscos:
um arquivo corrompido pode **derrubar o processo nativo** (levando junto o
site inteiro), e `fbembed.dll` **não é seguro para múltiplas threads** (o
FastAPI atende rotas síncronas numa threadpool). Por isso toda leitura roda
num **processo filho** dedicado (`sys.executable <este arquivo> ...`): um
crash mata só o filho (vira erro tratado no site), cada leitura tem seu
próprio processo (sem corrida entre threads) e a memória é devolvida ao fim.

## Descoberta de login

Nesses bancos o SYSDBA e o próprio dono às vezes COLIDEM com um `ROLE` de
mesmo nome, e o Firebird recusa o login ("-902 your login X is same as one of
the SQL role name"). No embedded a senha é ignorada, mas o PRIVILÉGIO de
SELECT continua valendo. Então tentamos SYSDBA direto (dono usual de bancos
normais) e, só se colidir com um role, caímos numa sonda que lê as tabelas de
sistema e escolhe um login utilizável: o dono (se não for role) ou um usuário
com GRANT de SELECT (ex.: no Symac é o `SYMAC`).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

# fdb é importado só dentro do processo filho (o resto do site não depende dele).

_USUARIO_SONDA = "AUDITORIAFB"
_ROLES_SEMPRE = {"SYSDBA", "RDB$ADMIN", "PUBLIC"}
_LIMITE_CONTAGEM = 1000          # conta exato até aqui; acima vira "1000+"
_TIMEOUT_SUBPROCESSO_S = 180


def _home_firebird() -> str:
    """Pasta do Firebird embedded empacotado (vendor/firebird25 na raiz)."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    raiz = os.path.abspath(os.path.join(aqui, "..", "..", ".."))
    return os.environ.get(
        "AUDITORIA_FB_HOME", os.path.join(raiz, "vendor", "firebird25"))


def _dll() -> str:
    return os.path.join(_home_firebird(), "fbembed.dll")


def _charset() -> str:
    # Symac e a maioria dos ERPs BR usam WIN1252/ISO8859_1 (single-byte, mapeia
    # todos os bytes — sem erro de transliteracao). Ajustavel por ambiente.
    return os.environ.get("AUDITORIA_FB_CHARSET", "WIN1252")


def _limite_padrao() -> int:
    """Teto de linhas lidas de uma tabela (evita OOM em base gigante)."""
    try:
        return max(1, int(os.environ.get("AUDITORIA_FB_MAX_LINHAS", "200000")))
    except ValueError:
        return 200000


def firebird_disponivel() -> tuple[bool, str]:
    """(disponivel, motivo) — para a UI avisar se o motor não está instalado.

    Roda no processo do site (só checa arquivo/import; sem abrir banco)."""
    home = _home_firebird()
    if not os.path.isfile(_dll()):
        return False, (f"Motor Firebird embedded não encontrado em {home}. "
                       "Baixe conforme o README (vendor/firebird25).")
    try:
        import fdb  # noqa: F401
    except ImportError:
        return False, ("Driver 'fdb' não instalado no ambiente do servidor "
                       "(pip install fdb).")
    return True, ""


@dataclass
class TabelaInfo:
    nome: str
    linhas: int          # contagem exata até _LIMITE_CONTAGEM
    mais: bool = False   # True quando há mais linhas do que `linhas`


# ======================================================================
# API pública — cada chamada roda ISOLADA num processo filho.
# ======================================================================


def listar_tabelas(caminho: str) -> list[TabelaInfo]:
    """Tabelas de dados do .FDB (nome + contagem limitada de linhas)."""
    dados = _rodar_isolado({"op": "listar", "caminho": caminho})
    return [TabelaInfo(t["nome"], t["linhas"], t["mais"]) for t in dados]


def colunas_tabela(caminho: str, tabela: str) -> list[str]:
    """Nomes das colunas de uma tabela (barato: só metadados, sem ler dados).

    Usado para mapear os campos ANTES de ler, e então trazer só as colunas
    necessárias — tabelas de ERP têm dezenas/centenas de colunas."""
    return _rodar_isolado({"op": "colunas", "caminho": caminho,
                           "tabela": tabela})


def ler_tabela(caminho: str, tabela: str, colunas: list[str] | None = None,
               limite: int | None = None
               ) -> tuple[list[str], list[list[str]], bool]:
    """Lê uma tabela como texto: devolve (colunas, linhas, truncado).

    `colunas` restringe a leitura a essas colunas (grande ganho em tabelas
    largas); None lê todas. `truncado` é True quando a tabela tem mais linhas
    que o teto. `tabela` e cada nome de coluna são validados dentro do filho
    contra os nomes reais (barreira contra injeção de SQL)."""
    dados = _rodar_isolado({
        "op": "ler", "caminho": caminho, "tabela": tabela,
        "colunas": colunas,
        "limite": _limite_padrao() if limite is None else limite})
    return dados["colunas"], dados["linhas"], dados["truncado"]


def _rodar_isolado(req: dict):
    """Roda uma operação de leitura num processo filho e devolve o resultado.

    A requisição vai por arquivo JSON (aceita lista de colunas sem estourar a
    linha de comando). Crash do filho (arquivo corrompido) vira ValueError
    tratável — o processo do site sobrevive."""
    ok, motivo = firebird_disponivel()
    if not ok:
        raise ValueError(motivo)
    if not os.path.isfile(req["caminho"]):
        raise ValueError("Arquivo .FDB não encontrado.")

    fd_r, entrada = tempfile.mkstemp(prefix="fdb_req_", suffix=".json")
    with os.fdopen(fd_r, "w", encoding="utf-8") as fh:
        json.dump(req, fh, ensure_ascii=False)
    fd_o, saida = tempfile.mkstemp(prefix="fdb_out_", suffix=".json")
    os.close(fd_o)
    args = [sys.executable, os.path.abspath(__file__), entrada, saida]
    try:
        proc = subprocess.run(args, capture_output=True,
                              timeout=_TIMEOUT_SUBPROCESSO_S)
        if proc.returncode != 0 or not os.path.getsize(saida):
            # Sem JSON de erro tratado => o motor caiu de fato (nativo).
            detalhe = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise ValueError(
                "Não foi possível ler o .FDB — o motor Firebird encerrou "
                "inesperadamente (arquivo possivelmente corrompido ou "
                "incompatível)." + (f" [{detalhe[-200:]}]" if detalhe else ""))
        with open(saida, encoding="utf-8") as fh:
            dados = json.load(fh)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Leitura do .FDB excedeu o tempo limite.") from exc
    finally:
        for tmp in (entrada, saida):
            with contextlib.suppress(OSError):
                os.remove(tmp)
    if "erro" in dados:
        raise ValueError(dados["erro"])
    return dados["resultado"]


# ======================================================================
# Implementação in-process — SÓ roda dentro do processo filho (__main__).
# ======================================================================


def _preparar_ambiente() -> None:
    home = _home_firebird()
    os.environ.setdefault("FIREBIRD", home)
    if hasattr(os, "add_dll_directory") and os.path.isdir(home):
        with contextlib.suppress(OSError):
            os.add_dll_directory(home)


def _conectar(caminho: str, usuario: str):
    import fdb
    return fdb.connect(database=caminho, user=usuario, password="x",
                       fb_library_name=_dll(), charset=_charset())


def _colisao_role(exc: Exception) -> bool:
    return "same as one of the sql role" in str(exc).lower()


def _amigavel(exc: Exception) -> str:
    linhas = [ln.strip() for ln in str(exc).splitlines() if ln.strip()]
    detalhe = linhas[-1] if linhas else exc.__class__.__name__
    baixo = detalhe.lower()
    if "not a valid database" in baixo or "unknown ods" in baixo:
        return "O arquivo não parece ser um banco Firebird (.FDB) válido."
    if "encrypt" in baixo:
        return "Banco Firebird protegido/criptografado — não foi possível abrir."
    if "transliterate" in baixo:
        return ("O banco usa um conjunto de caracteres incompatível. Defina "
                "AUDITORIA_FB_CHARSET (ex.: ISO8859_1, UTF8) e tente de novo.")
    return f"Não foi possível abrir o .FDB: {detalhe}"


@contextlib.contextmanager
def _abrir_local(caminho: str):
    """Conexão de leitura (dentro do filho). Fecha tudo no fim, sem vazar."""
    import fdb

    _preparar_ambiente()
    abertas: list = []
    try:
        # 1) SYSDBA direto: dono usual de bancos "normais".
        try:
            con = _conectar(caminho, "SYSDBA")
            abertas.append(con)
            yield con
            return
        except fdb.DatabaseError as exc:
            if not _colisao_role(exc):
                raise ValueError(_amigavel(exc)) from exc

        # 2) SYSDBA colide com um role: sonda + descoberta do login certo.
        sonda = _conectar(caminho, _USUARIO_SONDA)
        abertas.append(sonda)
        login = None
        with contextlib.suppress(Exception):
            login = _descobrir_login(sonda)
        if login is None:
            yield sonda            # sonda já lê tudo (PUBLIC) ou falhará claro
            return
        con = _conectar(caminho, login)
        abertas.append(con)
        yield con
    finally:
        for c in abertas:
            with contextlib.suppress(Exception):
                c.close()


def _descobrir_login(con_sonda) -> str | None:
    cur = con_sonda.cursor()
    cur.execute("SELECT TRIM(RDB$ROLE_NAME) FROM RDB$ROLES")
    roles = {r[0] for r in cur.fetchall()} | _ROLES_SEMPRE
    cur.execute(
        "SELECT TRIM(RDB$OWNER_NAME), COUNT(*) FROM RDB$RELATIONS "
        "WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL "
        "GROUP BY 1 ORDER BY 2 DESC")
    for dono, _n in cur.fetchall():
        if dono and dono not in roles:
            return dono
    cur.execute(
        "SELECT TRIM(p.RDB$USER), COUNT(*) FROM RDB$USER_PRIVILEGES p "
        "JOIN RDB$RELATIONS r ON r.RDB$RELATION_NAME = p.RDB$RELATION_NAME "
        "WHERE p.RDB$PRIVILEGE = 'S' AND p.RDB$OBJECT_TYPE = 0 "
        "  AND r.RDB$SYSTEM_FLAG = 0 AND r.RDB$VIEW_BLR IS NULL "
        "GROUP BY 1 ORDER BY 2 DESC")
    for usuario, _n in cur.fetchall():
        if usuario and usuario not in roles and usuario != _USUARIO_SONDA:
            return usuario
    return None


def _nomes_tabelas(con) -> list[str]:
    cur = con.cursor()
    cur.execute("SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS "
                "WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL "
                "ORDER BY 1")
    return [linha[0] for linha in cur.fetchall()]


def _listar_local(con) -> list[dict]:
    cur = con.cursor()
    infos: list[dict] = []
    for nome in _nomes_tabelas(con):
        try:
            # Contagem LIMITADA: a subquery com FIRST lê no máximo 1001 linhas,
            # então nem tabela de milhões faz full scan (Firebird 2.5 não tem
            # COUNT barato). Acima do teto marca "mais".
            cur.execute(f'SELECT COUNT(*) FROM (SELECT FIRST {_LIMITE_CONTAGEM + 1}'
                        f' 1 AS X FROM "{nome}")')
            n = cur.fetchone()[0]
            infos.append({"nome": nome, "linhas": min(n, _LIMITE_CONTAGEM),
                          "mais": n > _LIMITE_CONTAGEM})
        except Exception:  # noqa: BLE001 — tabela sem SELECT: -1 (sem acesso)
            infos.append({"nome": nome, "linhas": -1, "mais": False})
    return infos


def _texto_celula(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        for enc in ("cp1252", "latin-1", "utf-8"):
            with contextlib.suppress(UnicodeDecodeError):
                return valor.decode(enc).strip()
        return valor.decode("latin-1", "replace").strip()
    return str(valor).strip()


def _colunas_local(con, tabela: str) -> list[str]:
    if tabela not in set(_nomes_tabelas(con)):
        raise ValueError(f"Tabela {tabela!r} não existe neste .FDB.")
    cur = con.cursor()
    cur.execute("SELECT TRIM(RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS "
                "WHERE RDB$RELATION_NAME = ? ORDER BY RDB$FIELD_POSITION",
                (tabela,))
    return [linha[0] for linha in cur.fetchall()]


def _ler_local(con, tabela: str, limite: int,
               colunas: list[str] | None) -> dict:
    todas = _colunas_local(con, tabela)
    if colunas:
        # Cada nome pedido tem de existir de fato: validacao contra a lista
        # real E a barreira contra injecao (os nomes vao entre aspas no SELECT).
        validas = set(todas)
        alvo = [c for c in colunas if c in validas]
        if not alvo:
            raise ValueError("Nenhuma das colunas pedidas existe na tabela.")
    else:
        alvo = todas
    lista_sql = ", ".join(f'"{c}"' for c in alvo)
    cur = con.cursor()
    # Lê teto+1 para saber se truncou, sem carregar a tabela inteira.
    cur.execute(f'SELECT FIRST {int(limite) + 1} {lista_sql} FROM "{tabela}"')
    brutas = cur.fetchall()
    truncado = len(brutas) > limite
    if truncado:
        brutas = brutas[:limite]
    linhas = [[_texto_celula(v) for v in registro] for registro in brutas]
    return {"colunas": alvo, "linhas": linhas, "truncado": truncado}


def _main(argv: list[str]) -> int:
    """Ponto de entrada do PROCESSO FILHO: lê a requisição JSON, escreve o
    resultado JSON no arquivo de saída.

    Erros tratados viram {"erro": msg} (returncode 0); um crash nativo do
    Firebird não chega aqui — o pai detecta pelo returncode/arquivo vazio."""
    entrada, saida = argv[1], argv[2]
    try:
        with open(entrada, encoding="utf-8") as fh:
            req = json.load(fh)
        op, caminho = req["op"], req["caminho"]
        with _abrir_local(caminho) as con:
            if op == "listar":
                resultado = _listar_local(con)
            elif op == "colunas":
                resultado = _colunas_local(con, req["tabela"])
            elif op == "ler":
                resultado = _ler_local(con, req["tabela"], int(req["limite"]),
                                       req.get("colunas"))
            else:
                raise ValueError(f"operação desconhecida: {op}")
        conteudo = {"resultado": resultado}
    except ValueError as exc:
        conteudo = {"erro": str(exc)}
    except Exception as exc:  # noqa: BLE001 — vira mensagem amigável no site
        conteudo = {"erro": _amigavel(exc)}
    with open(saida, "w", encoding="utf-8") as fh:
        json.dump(conteudo, fh, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
