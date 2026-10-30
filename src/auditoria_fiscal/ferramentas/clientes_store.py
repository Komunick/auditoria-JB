"""Persistencia do cadastro de clientes (spec 012): `dados_web/clientes.db`.

Banco proprio, como `patrimonio.db` e `nfse.db`: ciclo de vida, trilha e
backup proprios. E' o banco mais sensivel do sistema — guarda as senhas dos
portais dos clientes —, por isso:

- **Senha so entra cifrada.** O store recebe o texto, cifra com o `Cofre`
  injetado e grava cifra + nonce + impressao da chave. Sem cofre, le o
  cadastro mas recusa tocar em senha (CofreIndisponivel).
- **Revelar e' uma operacao com trilha.** A linha em `acesso_cofre` e a
  leitura acontecem na mesma transacao; o limite por hora e' contado nessa
  mesma tabela, que nenhum UPDATE/DELETE alcanca (trigger).
- **Toda alteracao do cadastro** vira linha em `alteracao`, tambem imutavel,
  na mesma transacao da mudanca. Valor de senha nunca entra la.

Sem FastAPI: caminho, cofre e identidade chegam por injecao.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..core import clientes as cl
from ..core.cofre import Cifrado, CofreIndisponivel

VERSAO_SCHEMA = 1

DOCUMENTO_DUPLICADO = "DOCUMENTO_DUPLICADO"
SEM_VALOR = "SEM_VALOR"
DECISAO_INVALIDA = "DECISAO_INVALIDA"
COLETA_INVALIDA = "COLETA_INVALIDA"
SERIE_DUPLICADA = "SERIE_DUPLICADA"

CAMPOS_SEGREDO = {
    "sefaz": "Senha SEFAZ estadual",
    "prefeitura": "Senha Prefeitura",
    "codigo_acesso": "Código de acesso",
    "outro": "Outro portal",
}
SITUACOES_SEGREDO = (cl.CAMPO_PENDENTE, cl.CAMPO_AGUARDANDO_CERTIFICADO,
                     cl.CAMPO_NAO_TEM, cl.CAMPO_NAO_SE_APLICA)

TIPOS_LICENCA = ("tvl", "alvara", "alvara_saude", "publicidade")
TIPOS_CERTIFICADO = ("A1", "A3", "outro")

CERT_VIGENTE = "vigente"
CERT_SUBSTITUIDO = "substituido"
CERT_NAO_RENOVAR = "nao_renovar"
SITUACOES_CERTIFICADO = {
    CERT_VIGENTE: "Vigente", CERT_SUBSTITUIDO: "Substituído",
    CERT_NAO_RENOVAR: "Não renovar",
}
ORIGEM_MANUAL = "manual"
ORIGEM_ARQUIVO = "arquivo"
ORIGEM_COLETA = "coleta"

LIMITE_REVELACOES_HORA = 30

# Situacoes de cliente que saem do painel e do aviso de vencimento.
_FORA_DO_PAINEL = (cl.SITUACAO_BAIXADO, cl.SITUACAO_NAO_CLIENTE)


class ConcorrenciaError(Exception):
    def __init__(self, revision_atual: int):
        super().__init__("Registro desatualizado.")
        self.revision_atual = revision_atual


class LimiteExcedido(Exception):
    """Revelacoes demais na ultima hora."""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_TABELAS = """
CREATE TABLE IF NOT EXISTS cliente (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  documento TEXT,
  documento_informado TEXT NOT NULL DEFAULT '',
  ie TEXT NOT NULL DEFAULT '', ie_situacao TEXT NOT NULL DEFAULT '',
  im TEXT NOT NULL DEFAULT '', im_situacao TEXT NOT NULL DEFAULT '',
  iptu TEXT NOT NULL DEFAULT '', iptu_situacao TEXT NOT NULL DEFAULT '',
  municipio TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT 'ativo',
  observacao TEXT NOT NULL DEFAULT '',
  pendencias TEXT NOT NULL DEFAULT '[]',
  origem TEXT NOT NULL DEFAULT '{}',
  revision INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS licenca (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL REFERENCES cliente(id),
  tipo TEXT NOT NULL,
  numero TEXT NOT NULL DEFAULT '',
  vencimento TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT '',
  texto_original TEXT NOT NULL DEFAULT '',
  atualizado_em TEXT NOT NULL,
  UNIQUE (cliente_id, tipo)
);

CREATE TABLE IF NOT EXISTS segredo (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL REFERENCES cliente(id),
  campo TEXT NOT NULL,
  portal TEXT NOT NULL DEFAULT '',
  usuario_portal TEXT NOT NULL DEFAULT '',
  uid TEXT NOT NULL UNIQUE,
  cifra BLOB, nonce BLOB, chave_id TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT '',
  atualizado_por_login TEXT NOT NULL DEFAULT '',
  atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS acesso_cofre (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  cliente_id INTEGER,
  segredo_id INTEGER,
  campo TEXT NOT NULL DEFAULT '',
  acao TEXT NOT NULL,
  resultado TEXT NOT NULL,
  ip TEXT NOT NULL DEFAULT '',
  criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certificado (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL REFERENCES cliente(id),
  tipo TEXT NOT NULL DEFAULT '',
  titular_nome TEXT NOT NULL DEFAULT '',
  titular_documento TEXT NOT NULL DEFAULT '',
  emissor TEXT NOT NULL DEFAULT '',
  inicio TEXT NOT NULL DEFAULT '',
  fim TEXT NOT NULL,
  serie TEXT NOT NULL DEFAULT '',
  local_guarda TEXT NOT NULL DEFAULT '',
  origem TEXT NOT NULL,
  hash_arquivo TEXT NOT NULL DEFAULT '',
  coletado_em TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT 'vigente',
  substituido_por_id INTEGER REFERENCES certificado(id),
  renovacao_em_andamento INTEGER NOT NULL DEFAULT 0,
  renovacao_por_login TEXT NOT NULL DEFAULT '',
  renovacao_em TEXT NOT NULL DEFAULT '',
  observacao TEXT NOT NULL DEFAULT '',
  revision INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alteracao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidade TEXT NOT NULL,
  entidade_id INTEGER NOT NULL,
  campo TEXT NOT NULL,
  antes TEXT NOT NULL DEFAULT '',
  depois TEXT NOT NULL DEFAULT '',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  criada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS importacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL,
  hash_arquivo TEXT NOT NULL,
  nome_arquivo TEXT NOT NULL DEFAULT '',
  usuario_login TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  contagens TEXT NOT NULL DEFAULT '{}',
  ignoradas TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS importacao_base_fiscal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash_arquivo TEXT NOT NULL,
  hash_correcoes TEXT NOT NULL,
  nome_arquivo TEXT NOT NULL,
  nome_correcoes TEXT NOT NULL,
  usuario_id INTEGER NOT NULL,
  usuario_login TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  resultado TEXT NOT NULL,
  proveniencia TEXT NOT NULL,
  UNIQUE (hash_arquivo, hash_correcoes)
);

CREATE TABLE IF NOT EXISTS configuracao (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL,
  atualizado_por_login TEXT NOT NULL DEFAULT '',
  atualizado_em TEXT NOT NULL
);
"""

_INDICES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_cliente_documento
  ON cliente(documento) WHERE documento IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cliente_situacao ON cliente(situacao, nome);
-- Um segredo por campo fixo; "outro" (portal livre) pode repetir.
CREATE UNIQUE INDEX IF NOT EXISTS idx_segredo_campo
  ON segredo(cliente_id, campo) WHERE campo <> 'outro';
CREATE INDEX IF NOT EXISTS idx_acesso_usuario
  ON acesso_cofre(usuario_id, acao, resultado, criado_em);
CREATE INDEX IF NOT EXISTS idx_acesso_cliente ON acesso_cofre(cliente_id, id);
CREATE INDEX IF NOT EXISTS idx_cert_cliente ON certificado(cliente_id, situacao);
CREATE INDEX IF NOT EXISTS idx_cert_fim ON certificado(situacao, fim);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cert_serie
  ON certificado(emissor, serie) WHERE serie <> '';
CREATE INDEX IF NOT EXISTS idx_alteracao ON alteracao(entidade, entidade_id, id);
"""

_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_acesso_sem_update
BEFORE UPDATE ON acesso_cofre BEGIN
  SELECT RAISE(ABORT, 'Acesso ao cofre e imutavel.');
END;
CREATE TRIGGER IF NOT EXISTS trg_acesso_sem_delete
BEFORE DELETE ON acesso_cofre BEGIN
  SELECT RAISE(ABORT, 'Acesso ao cofre e imutavel.');
END;
CREATE TRIGGER IF NOT EXISTS trg_alteracao_sem_update
BEFORE UPDATE ON alteracao BEGIN
  SELECT RAISE(ABORT, 'Alteracao e imutavel.');
END;
CREATE TRIGGER IF NOT EXISTS trg_alteracao_sem_delete
BEFORE DELETE ON alteracao BEGIN
  SELECT RAISE(ABORT, 'Alteracao e imutavel.');
END;
-- Cliente nao e' excluido: muda de situacao, e o historico fica.
CREATE TRIGGER IF NOT EXISTS trg_cliente_sem_delete
BEFORE DELETE ON cliente BEGIN
  SELECT RAISE(ABORT, 'Cliente nao e excluido: mude a situacao.');
END;
CREATE TRIGGER IF NOT EXISTS trg_importacao_base_fiscal_sem_update
BEFORE UPDATE ON importacao_base_fiscal BEGIN
  SELECT RAISE(ABORT, 'Recibo da Base Fiscal e imutavel.');
END;
CREATE TRIGGER IF NOT EXISTS trg_importacao_base_fiscal_sem_delete
BEFORE DELETE ON importacao_base_fiscal BEGIN
  SELECT RAISE(ABORT, 'Recibo da Base Fiscal e imutavel.');
END;
"""

_CAMPOS_EDITAVEIS = ("nome", "documento", "ie", "ie_situacao", "im",
                     "im_situacao", "iptu", "iptu_situacao", "municipio",
                     "observacao", "contato_nome", "contato_email")


def _aad(cliente_id: int, campo: str, uid: str) -> str:
    return f"{cliente_id}:{campo}:{uid}"


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


class ClientesStore:
    """Uma instancia por operacao: conexao SQLite nao atravessa thread."""

    def __init__(self, db_path: str, *, cofre=None):
        self.db_path = db_path
        self.cofre = cofre
        pasta = os.path.dirname(os.path.abspath(db_path))
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=15, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        try:
            self._migrar()
        except Exception:
            # O chamador ainda não recebeu a instância e não pode fechá-la
            # quando abertura/migração falha (banco inválido, trava, permissões).
            self._conn.close()
            raise

    def _migrar(self) -> None:
        conn = self._conn
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_TABELAS)
        conn.executescript(_INDICES)
        conn.executescript(_TRIGGERS)
        # Contatos sao aditivos; a spec 013 compartilha este banco. Nunca
        # rebaixar a versao ao abrir o cadastro depois do modulo de tarefas.
        conn.execute("BEGIN IMMEDIATE")
        try:
            colunas = {r["name"] for r in conn.execute("PRAGMA table_info(cliente)")}
            for campo in ("contato_nome", "contato_email"):
                if campo not in colunas:
                    conn.execute(f"ALTER TABLE cliente ADD COLUMN {campo} TEXT NOT NULL DEFAULT ''")
            versao = conn.execute("PRAGMA user_version").fetchone()[0]
            if versao < VERSAO_SCHEMA:
                conn.execute(f"PRAGMA user_version={VERSAO_SCHEMA}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def fechar(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def contar(self, tabela: str) -> int:
        if tabela not in {"cliente", "licenca", "segredo", "acesso_cofre",
                          "certificado", "alteracao", "importacao"}:
            raise ValueError(f"Tabela desconhecida: {tabela}")
        return int(self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {tabela}").fetchone()["n"])

    def _transacao(self, operacao):
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            resultado = operacao(conn)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return resultado

    def _exigir_cofre(self):
        if self.cofre is None:
            raise CofreIndisponivel(
                "Cofre de senhas desligado: falta a chave no servidor.")
        return self.cofre

    # ------------------------------------------------------------------
    # Cadastro

    def _validar_cliente(self, dados: dict) -> dict:
        limpo: dict = {"nome": cl.texto_obrigatorio(dados.get("nome"),
                                                    "Nome do cliente",
                                                    maximo=160)}
        bruto = dados.get("documento")
        if bruto not in (None, "") and cl.texto_celula(bruto):
            limpo["documento"] = cl.normalizar_documento(bruto)
        else:
            limpo["documento"] = None
        for campo in ("ie", "im", "iptu"):
            situacao_dada = str(dados.get(f"{campo}_situacao") or "").strip()
            valor, situacao = cl.classificar_campo(dados.get(campo))
            if situacao_dada:
                if situacao_dada not in cl.SITUACOES_CAMPO:
                    raise cl.ErroClientes(cl.VALOR_INVALIDO,
                                          f"Situação desconhecida: {situacao_dada}.")
                valor, situacao = "", situacao_dada
            limpo[campo] = valor[:40]
            limpo[f"{campo}_situacao"] = situacao
        limpo["municipio"] = " ".join(str(dados.get("municipio") or "").split())[:80]
        limpo["observacao"] = str(dados.get("observacao") or "").strip()[:2000]
        limpo["contato_nome"] = " ".join(str(dados.get("contato_nome") or "").split())[:160]
        limpo["contato_email"] = cl.validar_email(dados.get("contato_email"))
        return limpo

    def _registrar(self, conn, entidade: str, entidade_id: int, campo: str,
                   antes, depois, usuario_id: int, usuario_login: str) -> None:
        conn.execute(
            "INSERT INTO alteracao(entidade, entidade_id, campo, antes, depois,"
            " usuario_id, usuario_login, criada_em) VALUES(?,?,?,?,?,?,?,?)",
            (entidade, entidade_id, campo, "" if antes is None else str(antes),
             "" if depois is None else str(depois), usuario_id, usuario_login,
             agora()))

    def _inserir_cliente(self, conn, limpo: dict, *, situacao: str,
                         documento_informado: str = "", pendencias=(),
                         origem: dict | None = None, usuario_id: int,
                         usuario_login: str) -> int:
        try:
            cur = conn.execute(
                "INSERT INTO cliente(nome, documento, documento_informado, ie,"
                " ie_situacao, im, im_situacao, iptu, iptu_situacao, municipio,"
                " situacao, observacao, pendencias, origem, criado_em,"
                " atualizado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (limpo["nome"], limpo["documento"], documento_informado,
                 limpo["ie"], limpo["ie_situacao"], limpo["im"],
                 limpo["im_situacao"], limpo["iptu"], limpo["iptu_situacao"],
                 limpo["municipio"], situacao, limpo["observacao"],
                 _json(list(pendencias)), _json(origem or {}), agora(), agora()))
        except sqlite3.IntegrityError as exc:
            raise cl.ErroClientes(
                DOCUMENTO_DUPLICADO,
                "Já existe um cliente com este CNPJ/CPF.") from exc
        cliente_id = int(cur.lastrowid)
        conn.execute("UPDATE cliente SET contato_nome=?, contato_email=? WHERE id=?",
                     (limpo.get("contato_nome", ""), limpo.get("contato_email", ""), cliente_id))
        self._registrar(conn, "cliente", cliente_id, "criado", "",
                        limpo["nome"], usuario_id, usuario_login)
        return cliente_id

    def criar_cliente(self, dados: dict, *, usuario_id: int = 0,
                      usuario_login: str = "") -> int:
        limpo = self._validar_cliente(dados)
        return self._transacao(lambda conn: self._inserir_cliente(
            conn, limpo, situacao=cl.SITUACAO_ATIVO,
            usuario_id=usuario_id, usuario_login=usuario_login))

    def _aplicar_edicao(self, conn, atual, limpo: dict, *, usuario_id: int,
                        usuario_login: str) -> int:
        limpo = {**dict(atual), **limpo}
        mudou = [c for c in _CAMPOS_EDITAVEIS
                 if (atual[c] if atual[c] is not None else None) != limpo[c]]
        if not mudou:
            return int(atual["revision"])
        try:
            conn.execute(
                "UPDATE cliente SET " + ", ".join(f"{c}=?" for c in mudou) +
                ", revision=revision+1, atualizado_em=? WHERE id=?",
                [limpo[c] for c in mudou] + [agora(), atual["id"]])
        except sqlite3.IntegrityError as exc:
            raise cl.ErroClientes(
                DOCUMENTO_DUPLICADO,
                "Já existe outro cliente com este CNPJ/CPF.") from exc
        for campo in mudou:
            self._registrar(conn, "cliente", atual["id"], campo, atual[campo],
                            limpo[campo], usuario_id, usuario_login)
        return int(atual["revision"]) + 1

    def editar_cliente(self, cliente_id: int, dados: dict, *,
                       revision: int | None = None, usuario_id: int = 0,
                       usuario_login: str = "") -> dict:
        def _editar(conn):
            atual = conn.execute("SELECT * FROM cliente WHERE id=?",
                                 (cliente_id,)).fetchone()
            if atual is None:
                raise LookupError("Cliente não encontrado.")
            if revision is not None and int(revision) != int(atual["revision"]):
                raise ConcorrenciaError(int(atual["revision"]))
            # Clientes antigos da interface nao enviam os campos novos.
            # Campos de contato omitidos mantem seu valor, inclusive importado.
            # A semantica anterior de valor/situacao de IE/IM/IPTU e preservada.
            contatos = {c: atual[c] for c in ("contato_nome", "contato_email")}
            limpo = self._validar_cliente({**contatos, **dados})
            return self._aplicar_edicao(conn, atual, limpo,
                                        usuario_id=usuario_id,
                                        usuario_login=usuario_login)

        return {"id": cliente_id, "revision": self._transacao(_editar)}

    def mudar_situacao(self, cliente_id: int, situacao: str, motivo: str, *,
                       usuario_id: int = 0, usuario_login: str = "") -> dict:
        if situacao not in cl.SITUACOES_CLIENTE:
            raise cl.ErroClientes(cl.VALOR_INVALIDO,
                                  f"Situação desconhecida: {situacao}.")
        motivo = cl.texto_obrigatorio(motivo, "Motivo da mudança", maximo=500)

        def _mudar(conn):
            atual = conn.execute("SELECT situacao, revision FROM cliente"
                                 " WHERE id=?", (cliente_id,)).fetchone()
            if atual is None:
                raise LookupError("Cliente não encontrado.")
            conn.execute("UPDATE cliente SET situacao=?, revision=revision+1,"
                         " atualizado_em=? WHERE id=?",
                         (situacao, agora(), cliente_id))
            self._registrar(conn, "cliente", cliente_id, "situacao",
                            atual["situacao"], f"{situacao} — {motivo}",
                            usuario_id, usuario_login)
            return int(atual["revision"]) + 1

        return {"id": cliente_id, "revision": self._transacao(_mudar)}

    def obter(self, cliente_id: int) -> dict:
        linha = self._conn.execute("SELECT * FROM cliente WHERE id=?",
                                   (cliente_id,)).fetchone()
        if linha is None:
            raise LookupError("Cliente não encontrado.")
        return dict(linha)

    def detalhar(self, cliente_id: int) -> dict:
        cliente = self.obter(cliente_id)
        cliente["pendencias"] = json.loads(cliente["pendencias"] or "[]")
        cliente["origem"] = json.loads(cliente["origem"] or "{}")
        cliente["licencas"] = {l["tipo"]: dict(l) for l in self._conn.execute(
            "SELECT tipo, numero, vencimento, situacao, texto_original"
            " FROM licenca WHERE cliente_id=? ORDER BY tipo", (cliente_id,))}
        cliente["segredos"] = [{
            "id": s["id"], "campo": s["campo"], "portal": s["portal"],
            "usuario_portal": s["usuario_portal"], "situacao": s["situacao"],
            "presente": s["cifra"] is not None,
            "atualizado_em": s["atualizado_em"],
            "atualizado_por": s["atualizado_por_login"],
        } for s in self._conn.execute(
            "SELECT * FROM segredo WHERE cliente_id=? ORDER BY"
            " CASE campo WHEN 'sefaz' THEN 1 WHEN 'prefeitura' THEN 2"
            " WHEN 'codigo_acesso' THEN 3 ELSE 4 END, portal, id",
            (cliente_id,))]
        cliente["certificados"] = [dict(c) for c in self._conn.execute(
            "SELECT * FROM certificado WHERE cliente_id=?"
            " ORDER BY situacao='vigente' DESC, fim DESC", (cliente_id,))]
        cliente["alteracoes"] = [dict(a) for a in self._conn.execute(
            "SELECT campo, antes, depois, usuario_login, criada_em FROM alteracao"
            " WHERE entidade='cliente' AND entidade_id=? ORDER BY id DESC"
            " LIMIT 100", (cliente_id,))]
        return cliente

    _FILTROS = ("texto", "situacao", "municipio", "com_pendencia")

    def listar(self, *, pagina: int = 1, limite: int = 50, **filtros) -> dict:
        desconhecidos = sorted(set(filtros) - set(self._FILTROS))
        if desconhecidos:
            raise ValueError("Filtro desconhecido: " + ", ".join(desconhecidos))
        onde, valores = [], []
        texto = str(filtros.get("texto") or "").strip()
        if texto:
            padrao = "%" + (texto.replace("\\", "\\\\").replace("%", "\\%")
                            .replace("_", "\\_").upper()) + "%"
            digitos = "".join(ch for ch in texto if ch.isdigit())
            condicao = ("(UPPER(nome) LIKE ? ESCAPE '\\'"
                        " OR UPPER(ie) LIKE ? ESCAPE '\\'"
                        " OR UPPER(im) LIKE ? ESCAPE '\\'")
            valores.extend([padrao] * 3)
            if digitos:
                condicao += " OR documento LIKE ?"
                valores.append(f"%{digitos}%")
            onde.append(condicao + ")")
        situacao = str(filtros.get("situacao") or "").strip()
        if situacao:
            if situacao not in cl.SITUACOES_CLIENTE:
                raise ValueError(f"Situação desconhecida: {situacao}.")
            onde.append("situacao = ?")
            valores.append(situacao)
        municipio = str(filtros.get("municipio") or "").strip()
        if municipio:
            onde.append("municipio = ?")
            valores.append(municipio)
        if filtros.get("com_pendencia"):
            onde.append("pendencias <> '[]'")
        sql_onde = (" WHERE " + " AND ".join(onde)) if onde else ""

        limite = max(1, min(int(limite or 50), 200))
        total = int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM cliente" + sql_onde, valores
        ).fetchone()["n"])
        paginas = max(1, -(-total // limite))
        pagina = min(max(1, int(pagina or 1)), paginas)
        linhas = self._conn.execute(
            "SELECT c.*, (SELECT MIN(fim) FROM certificado k WHERE"
            " k.cliente_id=c.id AND k.situacao='vigente') AS certificado_fim"
            " FROM (SELECT * FROM cliente" + sql_onde + ") c"
            " ORDER BY c.nome COLLATE NOCASE LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite]).fetchall()
        itens = []
        for linha in linhas:
            item = dict(linha)
            item["pendencias"] = json.loads(item["pendencias"] or "[]")
            item.pop("origem", None)
            itens.append(item)
        return {"itens": itens, "total": total, "pagina": pagina,
                "limite": limite, "paginas": paginas}

    def municipios(self) -> list[str]:
        return [l["municipio"] for l in self._conn.execute(
            "SELECT DISTINCT municipio FROM cliente WHERE municipio <> ''"
            " ORDER BY municipio")]

    def resumo(self) -> dict:
        contagens = {l["situacao"]: l["n"] for l in self._conn.execute(
            "SELECT situacao, COUNT(*) AS n FROM cliente GROUP BY situacao")}
        pendentes = int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM cliente WHERE pendencias <> '[]'"
        ).fetchone()["n"])
        return {"total": sum(contagens.values()),
                "por_situacao": {k: contagens.get(k, 0)
                                 for k in cl.SITUACOES_CLIENTE},
                "com_pendencia": pendentes}

    # ------------------------------------------------------------------
    # Cofre

    def _gravar_segredo_sql(self, conn, cliente_id: int, campo: str,
                            valor: str, *, situacao: str, portal: str,
                            usuario_portal: str, segredo_id: int | None,
                            usuario_id: int, usuario_login: str) -> int:
        cofre = self._exigir_cofre()
        if segredo_id is not None:
            atual = conn.execute("SELECT * FROM segredo WHERE id=?",
                                 (segredo_id,)).fetchone()
            if atual is None or atual["cliente_id"] != cliente_id:
                raise LookupError("Senha não encontrada.")
        elif campo != "outro":
            atual = conn.execute(
                "SELECT * FROM segredo WHERE cliente_id=? AND campo=?",
                (cliente_id, campo)).fetchone()
        else:
            atual = None
        uid = atual["uid"] if atual else secrets.token_hex(8)
        if valor:
            cifrado = cofre.cifrar(valor, _aad(cliente_id, campo, uid))
            cifra, nonce, chave_id = cifrado.cifra, cifrado.nonce, cifrado.chave_id
            nova_situacao = ""
        else:
            cifra = nonce = None
            chave_id = ""
            nova_situacao = situacao
        if atual is None:
            cur = conn.execute(
                "INSERT INTO segredo(cliente_id, campo, portal, usuario_portal,"
                " uid, cifra, nonce, chave_id, situacao, atualizado_por_login,"
                " atualizado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cliente_id, campo, portal, usuario_portal, uid, cifra, nonce,
                 chave_id, nova_situacao, usuario_login, agora()))
            segredo_id = int(cur.lastrowid)
            antes = ""
        else:
            segredo_id = int(atual["id"])
            antes = "definida" if atual["cifra"] is not None else atual["situacao"]
            conn.execute(
                "UPDATE segredo SET portal=?, usuario_portal=?, cifra=?, nonce=?,"
                " chave_id=?, situacao=?, atualizado_por_login=?, atualizado_em=?"
                " WHERE id=?",
                (portal, usuario_portal, cifra, nonce, chave_id, nova_situacao,
                 usuario_login, agora(), segredo_id))
        depois = "definida" if valor else nova_situacao
        rotulo = f"segredo:{campo}" + (f":{portal}" if portal else "")
        self._registrar(conn, "cliente", cliente_id, rotulo,
                        antes, ("trocada" if antes == "definida" and valor
                                else depois), usuario_id, usuario_login)
        conn.execute(
            "INSERT INTO acesso_cofre(usuario_id, usuario_login, cliente_id,"
            " segredo_id, campo, acao, resultado, criado_em)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (usuario_id, usuario_login, cliente_id, segredo_id, campo, "gravar",
             "ok", agora()))
        return segredo_id

    def _validar_segredo(self, campo: str, valor, situacao: str, portal: str):
        if campo not in CAMPOS_SEGREDO:
            raise cl.ErroClientes(cl.VALOR_INVALIDO,
                                  f"Campo de senha desconhecido: {campo}.")
        if campo == "outro":
            portal = cl.texto_obrigatorio(portal, "Nome do portal", maximo=80)
        else:
            portal = ""
        valor = "" if valor is None else str(valor)
        if len(valor) > 500:
            raise cl.ErroClientes(cl.VALOR_INVALIDO, "Senha longa demais.")
        if not valor:
            if situacao not in SITUACOES_SEGREDO:
                raise cl.ErroClientes(
                    cl.CAMPO_OBRIGATORIO,
                    "Informe a senha ou a situação (pendente, aguardando "
                    "certificado, não tem).")
        return valor, portal

    def gravar_segredo(self, cliente_id: int, campo: str, valor, *,
                       situacao: str = "", portal: str = "",
                       usuario_portal: str = "", segredo_id: int | None = None,
                       usuario_id: int = 0, usuario_login: str = "") -> int:
        valor, portal = self._validar_segredo(campo, valor, situacao, portal)
        self._exigir_cofre()
        usuario_portal = str(usuario_portal or "").strip()[:120]

        def _gravar(conn):
            if conn.execute("SELECT 1 FROM cliente WHERE id=?",
                            (cliente_id,)).fetchone() is None:
                raise LookupError("Cliente não encontrado.")
            return self._gravar_segredo_sql(
                conn, cliente_id, campo, valor, situacao=situacao,
                portal=portal, usuario_portal=usuario_portal,
                segredo_id=segredo_id, usuario_id=usuario_id,
                usuario_login=usuario_login)

        return self._transacao(_gravar)

    def remover_segredo(self, segredo_id: int, *, usuario_id: int = 0,
                        usuario_login: str = "") -> dict:
        """So 'outro portal' some; campo fixo volta a 'nao tem'."""
        def _remover(conn):
            atual = conn.execute("SELECT * FROM segredo WHERE id=?",
                                 (segredo_id,)).fetchone()
            if atual is None:
                raise LookupError("Senha não encontrada.")
            conn.execute(
                "UPDATE segredo SET cifra=NULL, nonce=NULL, chave_id='',"
                " situacao=?, atualizado_por_login=?, atualizado_em=?"
                " WHERE id=?", (cl.CAMPO_NAO_TEM, usuario_login, agora(),
                                segredo_id))
            self._registrar(conn, "cliente", atual["cliente_id"],
                            f"segredo:{atual['campo']}"
                            + (f":{atual['portal']}" if atual["portal"] else ""),
                            "definida" if atual["cifra"] is not None
                            else atual["situacao"], "removida",
                            usuario_id, usuario_login)
            conn.execute(
                "INSERT INTO acesso_cofre(usuario_id, usuario_login, cliente_id,"
                " segredo_id, campo, acao, resultado, criado_em)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (usuario_id, usuario_login, atual["cliente_id"], segredo_id,
                 atual["campo"], "remover", "ok", agora()))
            return {"id": segredo_id, "cliente_id": atual["cliente_id"]}

        return self._transacao(_remover)

    def revelar(self, segredo_id: int, *, ip: str = "", usuario_id: int = 0,
                usuario_login: str = "",
                limite_hora: int = LIMITE_REVELACOES_HORA) -> dict:
        """Decifra UMA senha e grava o acesso na mesma transacao.

        O limite conta as revelacoes 'ok' da ultima hora nesta mesma tabela
        imutavel: nao ha contador separado para alguem zerar."""
        cofre = self._exigir_cofre()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            segredo = conn.execute("SELECT * FROM segredo WHERE id=?",
                                   (segredo_id,)).fetchone()
            if segredo is None:
                raise LookupError("Senha não encontrada.")
            desde = (datetime.now(timezone.utc) - timedelta(hours=1)
                     ).isoformat(timespec="seconds")
            usadas = int(conn.execute(
                "SELECT COUNT(*) AS n FROM acesso_cofre WHERE usuario_id=?"
                " AND usuario_login=? AND acao='revelar' AND resultado='ok'"
                " AND criado_em >= ?", (usuario_id, usuario_login, desde)
            ).fetchone()["n"])
            registro = ("INSERT INTO acesso_cofre(usuario_id, usuario_login,"
                        " cliente_id, segredo_id, campo, acao, resultado, ip,"
                        " criado_em) VALUES(?,?,?,?,?,'revelar',?,?,?)")
            base = (usuario_id, usuario_login, segredo["cliente_id"],
                    segredo_id, segredo["campo"])
            if usadas >= limite_hora:
                conn.execute(registro, (*base, "limite", ip, agora()))
                conn.execute("COMMIT")
                raise LimiteExcedido(
                    f"Limite de {limite_hora} senhas por hora atingido. "
                    "Tente mais tarde ou fale com o administrador.")
            if segredo["cifra"] is None:
                raise cl.ErroClientes(
                    SEM_VALOR, "Esta senha não está cadastrada "
                    f"({cl.SITUACOES_CAMPO.get(segredo['situacao'], 'vazia')}).")
            valor = cofre.decifrar(
                Cifrado(cifra=segredo["cifra"], nonce=segredo["nonce"],
                        chave_id=segredo["chave_id"]),
                _aad(segredo["cliente_id"], segredo["campo"], segredo["uid"]))
            conn.execute(registro, (*base, "ok", ip, agora()))
            conn.execute("COMMIT")
        except LimiteExcedido:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"id": segredo_id, "cliente_id": segredo["cliente_id"],
                "campo": segredo["campo"], "portal": segredo["portal"],
                "usuario_portal": segredo["usuario_portal"], "valor": valor}

    def registrar_negado(self, cliente_id: int | None, segredo_id: int | None,
                         *, ip: str = "", usuario_id: int = 0,
                         usuario_login: str = "") -> None:
        self._conn.execute(
            "INSERT INTO acesso_cofre(usuario_id, usuario_login, cliente_id,"
            " segredo_id, acao, resultado, ip, criado_em)"
            " VALUES(?,?,?,?,'revelar','negado',?,?)",
            (usuario_id, usuario_login, cliente_id, segredo_id, ip, agora()))

    def segredo(self, segredo_id: int) -> dict:
        linha = self._conn.execute(
            "SELECT id, cliente_id, campo FROM segredo WHERE id=?",
            (segredo_id,)).fetchone()
        if linha is None:
            raise LookupError("Senha não encontrada.")
        return dict(linha)

    def acessos(self, *, usuario: str = "", cliente_id: int = 0, de: str = "",
                ate: str = "", pagina: int = 1, limite: int = 100) -> dict:
        onde, valores = [], []
        if usuario:
            onde.append("a.usuario_login = ?")
            valores.append(usuario.strip().lower())
        if cliente_id:
            onde.append("a.cliente_id = ?")
            valores.append(int(cliente_id))
        if de:
            onde.append("a.criado_em >= ?")
            valores.append(f"{de}T00:00:00")
        if ate:
            # `ate` cobre o dia inteiro: compara com o comeco do dia seguinte.
            onde.append("a.criado_em < ?")
            valores.append((date.fromisoformat(ate) + timedelta(days=1))
                           .isoformat() + "T00:00:00")
        sql_onde = (" WHERE " + " AND ".join(onde)) if onde else ""
        limite = max(1, min(int(limite or 100), 500))
        total = int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM acesso_cofre a" + sql_onde, valores
        ).fetchone()["n"])
        paginas = max(1, -(-total // limite))
        pagina = min(max(1, int(pagina or 1)), paginas)
        itens = [dict(l) for l in self._conn.execute(
            "SELECT a.*, c.nome AS cliente_nome, s.portal FROM acesso_cofre a"
            " LEFT JOIN cliente c ON c.id = a.cliente_id"
            " LEFT JOIN segredo s ON s.id = a.segredo_id" + sql_onde +
            " ORDER BY a.id DESC LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite])]
        return {"itens": itens, "total": total, "pagina": pagina,
                "paginas": paginas}

    def senhas_presentes(self) -> dict[int, list[str]]:
        """cliente_id -> campos com senha cadastrada (nunca o valor)."""
        presentes: dict[int, list[str]] = {}
        for linha in self._conn.execute(
                "SELECT cliente_id, campo FROM segredo WHERE cifra IS NOT NULL"
                " ORDER BY cliente_id, id"):
            campos = presentes.setdefault(int(linha["cliente_id"]), [])
            if linha["campo"] not in campos:
                campos.append(linha["campo"])
        return presentes

    def pendentes_de_recifrar(self) -> int:
        cofre = self._exigir_cofre()
        return int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM segredo WHERE cifra IS NOT NULL"
            " AND chave_id <> ?", (cofre.chave_id,)).fetchone()["n"])

    # ------------------------------------------------------------------
    # Importacao da planilha

    def _existente(self, conn, documento: str, nome: str):
        if documento:
            return conn.execute("SELECT * FROM cliente WHERE documento=?",
                                (documento,)).fetchone()
        return conn.execute(
            "SELECT * FROM cliente WHERE documento IS NULL AND nome=?",
            (nome,)).fetchone()

    def situacao_importacao(self, leitura, decisoes: dict | None = None
                            ) -> dict[int, str]:
        """linha -> 'novo' | 'atualiza' | 'ignorar', com as decisoes."""
        resultado = {}
        for linha in leitura.linhas:
            acao = (decisoes or {}).get(linha.linha, linha.acao)
            if acao != "incluir" or not linha.nome:
                resultado[linha.linha] = "ignorar"
                continue
            existe = self._existente(self._conn, linha.documento, linha.nome)
            resultado[linha.linha] = "atualiza" if existe else "novo"
        return resultado

    def importar_planilha(self, leitura, *, decisoes: dict, nome_arquivo: str,
                          segredos: dict | None = None, usuario_id: int = 0,
                          usuario_login: str = "") -> dict:
        """Grava a planilha conferida numa transacao so.

        `segredos` (linha -> {campo: (valor, situacao)}) substitui
        `linha.segredos` quando a rota guardou a previa cifrada e decifra so
        aqui, na hora de gravar. `decisoes` (linha -> 'incluir'|'ignorar')
        vence a sugestao da previa."""
        escolhidas = []
        documentos: dict[str, int] = {}
        for linha in leitura.linhas:
            acao = decisoes.get(linha.linha, linha.acao)
            if acao not in ("incluir", "ignorar"):
                raise cl.ErroClientes(DECISAO_INVALIDA,
                                      f"Decisão desconhecida na linha {linha.linha}.")
            if acao != "incluir":
                continue
            if not linha.nome:
                raise cl.ErroClientes(
                    DECISAO_INVALIDA,
                    f"A linha {linha.linha} não tem nome e não pode entrar.")
            if linha.documento:
                if linha.documento in documentos:
                    raise cl.ErroClientes(
                        DECISAO_INVALIDA,
                        f"As linhas {documentos[linha.documento]} e "
                        f"{linha.linha} têm o mesmo CNPJ/CPF: escolha uma.")
                documentos[linha.documento] = linha.linha
            escolhidas.append(linha)
        if any(linha.segredos for linha in escolhidas) or segredos:
            self._exigir_cofre()

        def _importar(conn):
            contagem = {"criados": 0, "atualizados": 0,
                        "ignorados": len(leitura.linhas) - len(escolhidas)}
            for linha in escolhidas:
                limpo = {
                    "nome": linha.nome, "documento": linha.documento or None,
                    "ie": linha.ie, "ie_situacao": linha.ie_situacao,
                    "im": linha.im, "im_situacao": linha.im_situacao,
                    "iptu": linha.iptu, "iptu_situacao": linha.iptu_situacao,
                    "municipio": linha.municipio, "observacao": "",
                }
                origem = {"arquivo": leitura.hash_arquivo, "linha": linha.linha,
                          "nome_arquivo": nome_arquivo[:200]}
                atual = self._existente(conn, linha.documento, linha.nome)
                if atual is None:
                    cliente_id = self._inserir_cliente(
                        conn, limpo, situacao=linha.situacao,
                        documento_informado=linha.documento_informado,
                        pendencias=linha.pendencias, origem=origem,
                        usuario_id=usuario_id, usuario_login=usuario_login)
                    contagem["criados"] += 1
                else:
                    cliente_id = int(atual["id"])
                    limpo["observacao"] = atual["observacao"]
                    limpo["municipio"] = linha.municipio or atual["municipio"]
                    self._aplicar_edicao(conn, atual, limpo,
                                         usuario_id=usuario_id,
                                         usuario_login=usuario_login)
                    if atual["situacao"] != linha.situacao:
                        conn.execute("UPDATE cliente SET situacao=?,"
                                     " revision=revision+1 WHERE id=?",
                                     (linha.situacao, cliente_id))
                        self._registrar(conn, "cliente", cliente_id, "situacao",
                                        atual["situacao"],
                                        f"{linha.situacao} — importação",
                                        usuario_id, usuario_login)
                    conn.execute("UPDATE cliente SET pendencias=?, origem=?"
                                 " WHERE id=?", (_json(linha.pendencias),
                                                 _json(origem), cliente_id))
                    contagem["atualizados"] += 1
                for tipo, reg in linha.licencas.items():
                    conn.execute(
                        "INSERT INTO licenca(cliente_id, tipo, numero, vencimento,"
                        " situacao, texto_original, atualizado_em)"
                        " VALUES(?,?,?,?,?,?,?) ON CONFLICT(cliente_id, tipo)"
                        " DO UPDATE SET numero=excluded.numero,"
                        " vencimento=excluded.vencimento,"
                        " situacao=excluded.situacao,"
                        " texto_original=excluded.texto_original,"
                        " atualizado_em=excluded.atualizado_em",
                        (cliente_id, tipo, reg["numero"], reg["vencimento"],
                         reg["situacao"], reg["texto_original"][:200], agora()))
                linha_segredos = (segredos or {}).get(linha.linha, linha.segredos)
                for campo, (valor, situacao) in linha_segredos.items():
                    self._gravar_segredo_sql(
                        conn, cliente_id, campo, valor,
                        situacao=situacao or cl.CAMPO_PENDENTE, portal="",
                        usuario_portal="", segredo_id=None,
                        usuario_id=usuario_id, usuario_login=usuario_login)
            ignoradas = [{"linha": l.linha, "motivo": l.motivo or "decisão"}
                         for l in leitura.linhas if l not in escolhidas]
            conn.execute(
                "INSERT INTO importacao(tipo, hash_arquivo, nome_arquivo,"
                " usuario_login, criada_em, contagens, ignoradas)"
                " VALUES('planilha',?,?,?,?,?,?)",
                (leitura.hash_arquivo, nome_arquivo[:200], usuario_login,
                 agora(), _json(contagem), _json(ignoradas)))
            return contagem

        return self._transacao(_importar)

    # ------------------------------------------------------------------
    # Certificados

    def _validar_certificado(self, dados: dict) -> dict:
        fim = cl.data_plausivel(str(dados.get("fim") or ""))
        if fim is None:
            raise cl.ErroClientes(cl.CAMPO_OBRIGATORIO,
                                  "Informe a validade (fim) do certificado.")
        inicio = cl.data_plausivel(str(dados.get("inicio") or ""))
        tipo = str(dados.get("tipo") or "").strip()
        if tipo and tipo not in TIPOS_CERTIFICADO:
            raise cl.ErroClientes(cl.VALOR_INVALIDO,
                                  f"Tipo de certificado desconhecido: {tipo}.")
        documento = str(dados.get("titular_documento") or "").strip()
        if documento:
            documento = cl.normalizar_documento(documento)
        return {
            "tipo": tipo,
            "titular_nome": str(dados.get("titular_nome") or "").strip()[:160],
            "titular_documento": documento,
            "emissor": str(dados.get("emissor") or "").strip()[:160],
            "inicio": inicio.isoformat() if inicio else "",
            "fim": fim.isoformat(),
            "serie": str(dados.get("serie") or "").strip().upper()[:80],
            "local_guarda": str(dados.get("local_guarda") or "").strip()[:300],
            "hash_arquivo": str(dados.get("hash_arquivo") or "")[:64],
            "observacao": str(dados.get("observacao") or "").strip()[:1000],
        }

    def _substituir_antigos(self, conn, cliente_id: int, novo_id: int,
                            titular: str, fim: str) -> None:
        """Certificado mais novo do mesmo titular aposenta os mais velhos."""
        vigentes = conn.execute(
            "SELECT id, fim FROM certificado WHERE cliente_id=? AND id<>?"
            " AND situacao='vigente' AND titular_documento=?",
            (cliente_id, novo_id, titular)).fetchall()
        for antigo in vigentes:
            if antigo["fim"] <= fim:
                conn.execute(
                    "UPDATE certificado SET situacao=?, substituido_por_id=?,"
                    " renovacao_em_andamento=0, atualizado_em=? WHERE id=?",
                    (CERT_SUBSTITUIDO, novo_id, agora(), antigo["id"]))
            else:
                conn.execute(
                    "UPDATE certificado SET situacao=?, substituido_por_id=?,"
                    " atualizado_em=? WHERE id=?",
                    (CERT_SUBSTITUIDO, antigo["id"], agora(), novo_id))

    def _inserir_certificado(self, conn, cliente_id: int, limpo: dict, *,
                             origem: str, coletado_em: str = "",
                             usuario_id: int, usuario_login: str) -> int:
        try:
            cur = conn.execute(
                "INSERT INTO certificado(cliente_id, tipo, titular_nome,"
                " titular_documento, emissor, inicio, fim, serie, local_guarda,"
                " origem, hash_arquivo, coletado_em, observacao, criado_em,"
                " atualizado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cliente_id, limpo["tipo"], limpo["titular_nome"],
                 limpo["titular_documento"], limpo["emissor"], limpo["inicio"],
                 limpo["fim"], limpo["serie"], limpo["local_guarda"], origem,
                 limpo["hash_arquivo"], coletado_em, limpo["observacao"],
                 agora(), agora()))
        except sqlite3.IntegrityError as exc:
            raise cl.ErroClientes(
                SERIE_DUPLICADA,
                "Este certificado (emissor + série) já está cadastrado.") from exc
        cert_id = int(cur.lastrowid)
        self._substituir_antigos(conn, cliente_id, cert_id,
                                 limpo["titular_documento"], limpo["fim"])
        self._registrar(conn, "cliente", cliente_id, "certificado", "",
                        f"{limpo['tipo'] or 'certificado'} até {limpo['fim']}"
                        f" ({origem})", usuario_id, usuario_login)
        return cert_id

    def adicionar_certificado(self, cliente_id: int, dados: dict, *,
                              origem: str = ORIGEM_MANUAL, usuario_id: int = 0,
                              usuario_login: str = "") -> int:
        if origem not in (ORIGEM_MANUAL, ORIGEM_ARQUIVO):
            raise ValueError("Origem desconhecida.")
        limpo = self._validar_certificado(dados)

        def _adicionar(conn):
            if conn.execute("SELECT 1 FROM cliente WHERE id=?",
                            (cliente_id,)).fetchone() is None:
                raise LookupError("Cliente não encontrado.")
            return self._inserir_certificado(conn, cliente_id, limpo,
                                             origem=origem,
                                             usuario_id=usuario_id,
                                             usuario_login=usuario_login)

        return self._transacao(_adicionar)

    def editar_certificado(self, cert_id: int, dados: dict, *,
                           usuario_id: int = 0, usuario_login: str = "") -> dict:
        """So o que e' do escritorio: tipo, onde esta guardado, observacao e
        'nao renovar'. Validade e titular vem do certificado."""
        def _editar(conn):
            atual = conn.execute("SELECT * FROM certificado WHERE id=?",
                                 (cert_id,)).fetchone()
            if atual is None:
                raise LookupError("Certificado não encontrado.")
            novo = {
                "tipo": str(dados.get("tipo", atual["tipo"]) or "").strip(),
                "local_guarda": str(dados.get("local_guarda",
                                              atual["local_guarda"]) or "")
                .strip()[:300],
                "observacao": str(dados.get("observacao", atual["observacao"])
                                  or "").strip()[:1000],
                "situacao": str(dados.get("situacao", atual["situacao"])),
            }
            if novo["tipo"] and novo["tipo"] not in TIPOS_CERTIFICADO:
                raise cl.ErroClientes(cl.VALOR_INVALIDO, "Tipo desconhecido.")
            if novo["situacao"] not in (CERT_VIGENTE, CERT_NAO_RENOVAR) and \
                    novo["situacao"] != atual["situacao"]:
                raise cl.ErroClientes(cl.VALOR_INVALIDO,
                                      "Situação de certificado inválida.")
            mudou = [c for c in novo if novo[c] != atual[c]]
            if mudou:
                conn.execute(
                    "UPDATE certificado SET " +
                    ", ".join(f"{c}=?" for c in mudou) +
                    ", revision=revision+1, atualizado_em=? WHERE id=?",
                    [novo[c] for c in mudou] + [agora(), cert_id])
                for campo in mudou:
                    self._registrar(conn, "cliente", atual["cliente_id"],
                                    f"certificado:{campo}", atual[campo],
                                    novo[campo], usuario_id, usuario_login)
            return {"id": cert_id, "cliente_id": atual["cliente_id"]}

        return self._transacao(_editar)

    def marcar_renovacao(self, cert_id: int, em_andamento: bool, *,
                         usuario_id: int = 0, usuario_login: str = "") -> dict:
        def _marcar(conn):
            atual = conn.execute("SELECT * FROM certificado WHERE id=?",
                                 (cert_id,)).fetchone()
            if atual is None:
                raise LookupError("Certificado não encontrado.")
            conn.execute(
                "UPDATE certificado SET renovacao_em_andamento=?,"
                " renovacao_por_login=?, renovacao_em=?, atualizado_em=?"
                " WHERE id=?", (1 if em_andamento else 0, usuario_login,
                                agora(), agora(), cert_id))
            self._registrar(conn, "cliente", atual["cliente_id"],
                            "certificado:renovacao",
                            "em andamento" if atual["renovacao_em_andamento"]
                            else "", "em andamento" if em_andamento else "",
                            usuario_id, usuario_login)
            return {"id": cert_id, "cliente_id": atual["cliente_id"]}

        return self._transacao(_marcar)

    # ------------------------------------------------------------------
    # Coleta da pasta de certificados

    @staticmethod
    def validar_coleta(coleta) -> list[dict]:
        if not isinstance(coleta, dict) or \
                coleta.get("formato") != "auditoria-jb/coleta-certificados":
            raise cl.ErroClientes(
                COLETA_INVALIDA,
                "Este arquivo não é uma coleta do coletar-certificados.py.")
        if coleta.get("versao") != 1 or not isinstance(coleta.get("itens"), list):
            raise cl.ErroClientes(COLETA_INVALIDA,
                                  "Versão da coleta não suportada.")
        if len(coleta["itens"]) > 20000:
            raise cl.ErroClientes(COLETA_INVALIDA, "Coleta grande demais.")
        itens = []
        for item in coleta["itens"]:
            if not isinstance(item, dict):
                raise cl.ErroClientes(COLETA_INVALIDA, "Item de coleta inválido.")
            # A coleta nunca traz senha. Se trouxer (arquivo editado a mao),
            # o campo e' descartado aqui e nao segue para lugar nenhum.
            item = {k: v for k, v in item.items() if "senha" not in k.lower()}
            if isinstance(item.get("info"), dict):
                item["info"] = {k: v for k, v in item["info"].items()
                                if "senha" not in k.lower()}
            itens.append(item)
        return itens

    def previa_coleta(self, coleta: dict) -> list[dict]:
        resultado = []
        for item in self.validar_coleta(coleta):
            base = {"pasta": str(item.get("pasta") or "")[:200],
                    "arquivo": str(item.get("arquivo") or "")[:200],
                    "titular_nome": str(item.get("titular_nome") or "")[:160],
                    "titular_documento": str(item.get("titular_documento") or ""),
                    "fim": str(item.get("fim") or ""),
                    "problemas": [str(p) for p in item.get("problemas") or []],
                    "cliente_id": None, "cliente_nome": ""}
            if not base["fim"]:
                base["resultado"] = "nao_lido"
            else:
                cliente = None
                if base["titular_documento"]:
                    cliente = self._conn.execute(
                        "SELECT id, nome FROM cliente WHERE documento=?",
                        (base["titular_documento"],)).fetchone()
                if cliente is None:
                    base["resultado"] = "sem_cliente"
                else:
                    base.update(resultado="casou", cliente_id=cliente["id"],
                                cliente_nome=cliente["nome"])
            resultado.append(base)
        return resultado

    def importar_coleta(self, coleta: dict, *, nome_arquivo: str,
                        hash_arquivo: str, usuario_id: int = 0,
                        usuario_login: str = "") -> dict:
        itens = self.validar_coleta(coleta)
        pasta_raiz = str(coleta.get("pasta") or "")[:120]
        gerada_em = str(coleta.get("gerada_em") or "")[:32]

        def _importar(conn):
            contagem = {"novos": 0, "atualizados": 0, "sem_cliente": 0,
                        "nao_lidos": 0}
            for item in itens:
                if not item.get("fim"):
                    contagem["nao_lidos"] += 1
                    continue
                documento = str(item.get("titular_documento") or "")
                cliente = conn.execute(
                    "SELECT id FROM cliente WHERE documento=?",
                    (documento,)).fetchone() if documento else None
                if cliente is None:
                    contagem["sem_cliente"] += 1
                    continue
                local = "\\".join(p for p in (pasta_raiz,
                                              str(item.get("pasta") or ""),
                                              str(item.get("arquivo") or "")) if p)
                limpo = self._validar_certificado({**item, "local_guarda": local})
                existente = conn.execute(
                    "SELECT id FROM certificado WHERE emissor=? AND serie=?"
                    " AND serie<>''", (limpo["emissor"], limpo["serie"])
                ).fetchone()
                if existente is not None:
                    conn.execute(
                        "UPDATE certificado SET local_guarda=?, hash_arquivo=?,"
                        " coletado_em=?, atualizado_em=? WHERE id=?",
                        (limpo["local_guarda"], limpo["hash_arquivo"], gerada_em,
                         agora(), existente["id"]))
                    contagem["atualizados"] += 1
                    continue
                self._inserir_certificado(conn, int(cliente["id"]), limpo,
                                          origem=ORIGEM_COLETA,
                                          coletado_em=gerada_em,
                                          usuario_id=usuario_id,
                                          usuario_login=usuario_login)
                contagem["novos"] += 1
            conn.execute(
                "INSERT INTO importacao(tipo, hash_arquivo, nome_arquivo,"
                " usuario_login, criada_em, contagens) VALUES('coleta',?,?,?,?,?)",
                (hash_arquivo[:64], nome_arquivo[:200], usuario_login, agora(),
                 _json(contagem)))
            return contagem

        return self._transacao(_importar)

    # ------------------------------------------------------------------
    # Vencimentos

    def faixas(self) -> tuple[int, ...]:
        linha = self._conn.execute(
            "SELECT valor FROM configuracao WHERE chave='faixas_vencimento'"
        ).fetchone()
        if linha is None:
            return cl.FAIXAS_PADRAO
        try:
            return cl.validar_faixas(json.loads(linha["valor"]))
        except (cl.ErroClientes, ValueError):
            return cl.FAIXAS_PADRAO

    def definir_faixas(self, faixas, *, usuario_id: int = 0,
                       usuario_login: str = "") -> tuple[int, ...]:
        validas = cl.validar_faixas(faixas)
        self._conn.execute(
            "INSERT INTO configuracao(chave, valor, atualizado_por_login,"
            " atualizado_em) VALUES('faixas_vencimento',?,?,?)"
            " ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,"
            " atualizado_por_login=excluded.atualizado_por_login,"
            " atualizado_em=excluded.atualizado_em",
            (json.dumps(list(validas)), usuario_login, agora()))
        return validas

    def vencimentos(self, hoje: date, *, faixa: str | None = None,
                    texto: str = "") -> list[dict]:
        faixas = self.faixas()
        marcadores = ",".join("?" * len(_FORA_DO_PAINEL))
        linhas = self._conn.execute(
            "SELECT k.*, c.nome AS cliente_nome, c.documento AS cliente_documento,"
            " c.situacao AS cliente_situacao FROM certificado k"
            " JOIN cliente c ON c.id = k.cliente_id"
            f" WHERE k.situacao='vigente' AND c.situacao NOT IN ({marcadores})"
            " ORDER BY k.fim, c.nome", _FORA_DO_PAINEL).fetchall()
        termo = cl.chave_texto(texto)
        resultado = []
        for linha in linhas:
            item = dict(linha)
            item["faixa"], item["dias"] = cl.classificar_vencimento(
                item["fim"], hoje, faixas)
            if faixa and item["faixa"] != faixa:
                continue
            if termo and termo not in cl.chave_texto(item["cliente_nome"]):
                continue
            resultado.append(item)
        return resultado

    def resumo_vencimentos(self, hoje: date) -> dict:
        faixas = self.faixas()
        contagem = {cl.FAIXA_VENCIDO: 0, **{f"ate_{f}": 0 for f in faixas},
                    cl.FAIXA_EM_DIA: 0}
        aviso = 0
        curta = f"ate_{faixas[0]}"
        for item in self.vencimentos(hoje):
            contagem[item["faixa"]] = contagem.get(item["faixa"], 0) + 1
            if item["faixa"] in (cl.FAIXA_VENCIDO, curta) and \
                    not item["renovacao_em_andamento"]:
                aviso += 1
        return {"faixas": list(faixas), "contagem": contagem, "aviso": aviso,
                "faixa_curta": faixas[0]}
