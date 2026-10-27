"""Tarefas e prazos: schema aditivo 2 no clientes.db, sem dependencia web.

Uma conexao por operacao/thread. Mutacoes e seus eventos usam BEGIN IMMEDIATE;
as identidades e a verificacao de escopo chegam da interface autenticada.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ..core import regras_vencimento as rv
from ..core import tarefas as regras
from ..core import clientes as cl
from .clientes_store import ClientesStore, ConcorrenciaError

VERSAO_SCHEMA = 2
ABERTAS = ("a_fazer", "em_andamento", "aguardando_cliente", "devolvida")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS setor (
 id INTEGER PRIMARY KEY, nome TEXT NOT NULL UNIQUE,
 responsavel_usuario_id INTEGER, ativo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS setor_membro (
 id INTEGER PRIMARY KEY, setor_id INTEGER NOT NULL REFERENCES setor(id),
 usuario_id INTEGER NOT NULL, desde TEXT NOT NULL, ate TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS idx_membro_atual ON setor_membro(setor_id,usuario_id) WHERE ate='';
CREATE TABLE IF NOT EXISTS substituicao (
 id INTEGER PRIMARY KEY, titular_usuario_id INTEGER NOT NULL, substituto_usuario_id INTEGER NOT NULL,
 setor_id INTEGER REFERENCES setor(id), inicio TEXT NOT NULL, fim TEXT NOT NULL,
 motivo TEXT NOT NULL, criada_por INTEGER NOT NULL, criada_em TEXT NOT NULL,
 CHECK(inicio<=fim), CHECK(titular_usuario_id<>substituto_usuario_id));
CREATE INDEX IF NOT EXISTS idx_substituicao_periodo ON substituicao(titular_usuario_id,inicio,fim);
CREATE TABLE IF NOT EXISTS caracteristica (
 id INTEGER PRIMARY KEY, grupo TEXT NOT NULL, nome TEXT NOT NULL,
 exclusiva_no_grupo INTEGER NOT NULL DEFAULT 0, ativa INTEGER NOT NULL DEFAULT 1,
 UNIQUE(grupo,nome));
CREATE TABLE IF NOT EXISTS cliente_caracteristica (
 cliente_id INTEGER NOT NULL REFERENCES cliente(id),
 caracteristica_id INTEGER NOT NULL REFERENCES caracteristica(id),
 desde TEXT NOT NULL, marcada_por INTEGER NOT NULL,
 PRIMARY KEY(cliente_id,caracteristica_id));
CREATE TABLE IF NOT EXISTS carteira (
 cliente_id INTEGER NOT NULL REFERENCES cliente(id), setor_id INTEGER NOT NULL REFERENCES setor(id),
 responsavel_usuario_id INTEGER, desde TEXT NOT NULL, atualizada_por INTEGER NOT NULL,
 PRIMARY KEY(cliente_id,setor_id));
CREATE TABLE IF NOT EXISTS obrigacao (
 id INTEGER PRIMARY KEY, setor_id INTEGER NOT NULL REFERENCES setor(id), nome TEXT NOT NULL,
 periodicidade TEXT NOT NULL, competencias TEXT NOT NULL, regra_vencimento TEXT NOT NULL,
 condicao TEXT NOT NULL, inicio_antecedencia_dias INTEGER, exige_conferencia INTEGER NOT NULL DEFAULT 0,
 ativa INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1,
 criada_em TEXT NOT NULL, atualizada_em TEXT NOT NULL, UNIQUE(setor_id,nome));
CREATE TABLE IF NOT EXISTS ajuste_cliente (
 id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES cliente(id),
 obrigacao_id INTEGER NOT NULL REFERENCES obrigacao(id), tipo TEXT NOT NULL,
 regra_vencimento TEXT NOT NULL DEFAULT '{}', valido_de TEXT NOT NULL DEFAULT '',
 valido_ate TEXT NOT NULL DEFAULT '', motivo TEXT NOT NULL,
 criado_por INTEGER NOT NULL, criado_em TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_ajuste_cliente ON ajuste_cliente(cliente_id,obrigacao_id);
CREATE TABLE IF NOT EXISTS feriado (
 data TEXT NOT NULL, descricao TEXT NOT NULL, abrangencia TEXT NOT NULL,
 origem TEXT NOT NULL, sem_expediente INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(data,abrangencia));
CREATE TABLE IF NOT EXISTS tarefa (
 id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES cliente(id),
 setor_id INTEGER NOT NULL REFERENCES setor(id), obrigacao_id INTEGER REFERENCES obrigacao(id),
 competencia TEXT NOT NULL DEFAULT '', titulo TEXT NOT NULL, responsavel_usuario_id INTEGER,
 inicio TEXT NOT NULL, vencimento TEXT NOT NULL, situacao TEXT NOT NULL DEFAULT 'a_fazer',
 exige_conferencia INTEGER NOT NULL DEFAULT 0, concluida_em TEXT NOT NULL DEFAULT '',
 concluida_por INTEGER, conferida_em TEXT NOT NULL DEFAULT '', conferida_por INTEGER,
 conferida_substituindo INTEGER, fora_do_prazo INTEGER NOT NULL DEFAULT 0,
 origem TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 criada_em TEXT NOT NULL, atualizada_em TEXT NOT NULL, situacao_em TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tarefa_competencia
 ON tarefa(cliente_id,obrigacao_id,competencia) WHERE obrigacao_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tarefa_setor ON tarefa(setor_id,situacao,vencimento);
CREATE INDEX IF NOT EXISTS idx_tarefa_responsavel ON tarefa(responsavel_usuario_id,situacao,vencimento);
CREATE INDEX IF NOT EXISTS idx_tarefa_cliente ON tarefa(cliente_id,competencia);
CREATE TABLE IF NOT EXISTS tarefa_evento (
 id INTEGER PRIMARY KEY, tarefa_id INTEGER NOT NULL REFERENCES tarefa(id), tipo TEXT NOT NULL,
 de TEXT NOT NULL DEFAULT '', para TEXT NOT NULL DEFAULT '', comentario TEXT NOT NULL DEFAULT '',
 usuario_id INTEGER NOT NULL, usuario_login TEXT NOT NULL, substituindo_usuario_id INTEGER,
 criado_em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tarefa_evento ON tarefa_evento(tarefa_id,id);
CREATE TRIGGER IF NOT EXISTS trg_tarefa_evento_sem_update BEFORE UPDATE ON tarefa_evento
 BEGIN SELECT RAISE(ABORT,'Evento de tarefa e imutavel.'); END;
CREATE TRIGGER IF NOT EXISTS trg_tarefa_evento_sem_delete BEFORE DELETE ON tarefa_evento
 BEGIN SELECT RAISE(ABORT,'Evento de tarefa e imutavel.'); END;
CREATE TABLE IF NOT EXISTS geracao (
 id INTEGER PRIMARY KEY, competencia TEXT NOT NULL, setor_id INTEGER NOT NULL REFERENCES setor(id),
 disparo TEXT NOT NULL, usuario_login TEXT NOT NULL, criada_em TEXT NOT NULL, contagens TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS idx_geracao_automatica
 ON geracao(competencia,setor_id) WHERE disparo='automatico';
CREATE TABLE IF NOT EXISTS envio_alerta (
 id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, dia TEXT NOT NULL,
 canal TEXT NOT NULL DEFAULT 'email', destino TEXT NOT NULL, quantidades TEXT NOT NULL,
 resultado TEXT NOT NULL, erro TEXT NOT NULL DEFAULT '', criado_em TEXT NOT NULL,
 UNIQUE(usuario_id,dia,canal));
"""


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


def _data(valor, *, opcional=False):
    if opcional and valor in (None, ""):
        return ""
    if isinstance(valor, datetime):
        valor = regras.data_salvador(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    try:
        texto = str(valor)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
            raise ValueError()
        return date.fromisoformat(texto).isoformat()
    except (TypeError, ValueError) as exc:
        raise regras.ErroTarefas("DATA_INVALIDA", "Informe uma data no formato AAAA-MM-DD.") from exc


def _texto(valor, rotulo="Nome", maximo=160):
    texto = " ".join(str(valor or "").split())
    if not texto or len(texto) > maximo:
        raise regras.ErroTarefas("VALOR_INVALIDO", f"{rotulo} é obrigatório (até {maximo} caracteres).")
    return texto


def _id(valor, *, opcional=False):
    if opcional and valor in (None, ""):
        return None
    if isinstance(valor, bool):
        raise regras.ErroTarefas("VALOR_INVALIDO", "Identificador inválido.")
    try:
        numero = int(valor)
        if numero < 1 or str(numero) != str(valor):
            raise ValueError()
        return numero
    except (TypeError, ValueError) as exc:
        raise regras.ErroTarefas("VALOR_INVALIDO", "Identificador inválido.") from exc


def _bool(valor):
    if valor not in (True, False, 0, 1):
        raise regras.ErroTarefas("VALOR_INVALIDO", "Informe verdadeiro ou falso.")
    return int(bool(valor))


class TarefasStore(ClientesStore):
    def __init__(self, db_path, *, usuario_ativo=None, agora_fn=None):
        self.usuario_ativo = usuario_ativo or (lambda uid: True)
        self.agora_fn = agora_fn or (lambda: datetime.now(timezone.utc))
        super().__init__(db_path)

    def _migrar(self):
        super()._migrar()
        self._conn.executescript(_SCHEMA)
        def completar(conn):
            # Bancos schema 2 criados antes da edicao de ajustes tambem evoluem
            # aditivamente, sem recriar a tabela nem tocar em tarefas geradas.
            colunas = {r["name"] for r in conn.execute("PRAGMA table_info(ajuste_cliente)")}
            if "revision" not in colunas:
                conn.execute("ALTER TABLE ajuste_cliente ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
            versao = conn.execute("PRAGMA user_version").fetchone()[0]
            if versao < VERSAO_SCHEMA:
                conn.execute(f"PRAGMA user_version={VERSAO_SCHEMA}")
        self._transacao(completar)

    close = ClientesStore.fechar

    def _transacao(self, operacao):
        try:
            if self._conn.in_transaction:
                # A interface pode adquirir BEGIN IMMEDIATE antes de conferir
                # o escopo. O savepoint protege esta operacao sem liberar a
                # trava nem confirmar a transacao que pertence ao chamador.
                self._savepoint_contador = getattr(self, "_savepoint_contador", 0) + 1
                nome = f"tarefa_operacao_{self._savepoint_contador}"
                self._conn.execute(f"SAVEPOINT {nome}")
                try:
                    resultado = operacao(self._conn)
                except Exception:
                    self._conn.execute(f"ROLLBACK TO SAVEPOINT {nome}")
                    self._conn.execute(f"RELEASE SAVEPOINT {nome}")
                    raise
                self._conn.execute(f"RELEASE SAVEPOINT {nome}")
                return resultado
            return super()._transacao(operacao)
        except sqlite3.IntegrityError as exc:
            raise regras.ErroTarefas("INTEGRIDADE_INVALIDA", "A operação conflita com um registro existente ou uma regra de integridade.") from exc

    @property
    def conn(self):
        """Conexao local da operacao; apenas integracoes internas do mesmo processo."""
        return self._conn

    def listar_carteiras(self):
        return [dict(r) for r in self._conn.execute("SELECT * FROM carteira ORDER BY setor_id,cliente_id")]

    def _agora(self):
        valor = self.agora_fn()
        if valor.tzinfo is None:
            raise ValueError("Relogio deve informar fuso horario.")
        return valor.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _hoje(self, hoje=None):
        return date.fromisoformat(_data(hoje)) if hoje is not None else regras.data_salvador(self.agora_fn())

    def _um(self, tabela, id):
        if tabela not in {"cliente", "setor", "caracteristica", "obrigacao", "tarefa", "ajuste_cliente"}:
            raise ValueError("Tabela inválida.")
        r = self._conn.execute(f"SELECT * FROM {tabela} WHERE id=?", (_id(id),)).fetchone()
        if r is None:
            raise LookupError("Registro não encontrado.")
        return dict(r)

    def _usuario(self, uid, *, opcional=False):
        uid = _id(uid, opcional=opcional)
        if uid is not None and not self.usuario_ativo(uid):
            raise regras.ErroTarefas("USUARIO_INATIVO", "Selecione um usuário ativo do sistema.")
        return uid

    def _membro(self, setor_id, uid):
        uid = self._usuario(uid, opcional=True)
        if uid is not None and not self._conn.execute(
                "SELECT 1 FROM setor_membro WHERE setor_id=? AND usuario_id=? AND ate=''",
                (setor_id, uid)).fetchone():
            raise regras.ErroTarefas("MEMBRO_INVALIDO", "O responsável deve ser membro do setor.")
        return uid

    def _auditar(self, entidade, id, campo, antes, depois, usuario_id, usuario_login):
        self._conn.execute("INSERT INTO alteracao(entidade,entidade_id,campo,antes,depois,usuario_id,usuario_login,criada_em) VALUES(?,?,?,?,?,?,?,?)",
                           (entidade, id, campo, _json(antes), _json(depois), usuario_id, usuario_login, self._agora()))

    def _evento(self, tarefa, tipo, de, para, comentario, usuario_id, usuario_login, substituindo=None):
        if substituindo is None and tarefa.get("responsavel_usuario_id") != usuario_id:
            titular = tarefa.get("responsavel_usuario_id")
            if titular and self.responsavel_efetivo(tarefa["setor_id"], titular, self._hoje()) == usuario_id:
                substituindo = titular
        self._conn.execute("INSERT INTO tarefa_evento(tarefa_id,tipo,de,para,comentario,usuario_id,usuario_login,substituindo_usuario_id,criado_em) VALUES(?,?,?,?,?,?,?,?,?)",
                           (tarefa["id"], tipo, str(de or ""), str(para or ""), comentario,
                            usuario_id, usuario_login, substituindo, self._agora()))

    # Setores e substituicoes --------------------------------------------
    def listar_setores(self):
        setores = [dict(r) for r in self._conn.execute("SELECT * FROM setor ORDER BY nome")]
        for setor in setores:
            setor["membros"] = [r[0] for r in self._conn.execute(
                "SELECT usuario_id FROM setor_membro WHERE setor_id=? AND ate='' ORDER BY usuario_id", (setor["id"],))]
        return setores

    def salvar_setor(self, dados, id=None, *, usuario_id=0, usuario_login=""):
        def gravar(conn):
            antigo = self._um("setor", id) if id else {}
            novo = {**antigo, **dados}
            nome = _texto(novo.get("nome"))
            responsavel = self._usuario(novo.get("responsavel_usuario_id"), opcional=True)
            ativo = _bool(novo.get("ativo", True))
            if id:
                conn.execute("UPDATE setor SET nome=?,responsavel_usuario_id=?,ativo=? WHERE id=?", (nome, responsavel, ativo, id))
                sid = id
            else:
                sid = conn.execute("INSERT INTO setor(nome,responsavel_usuario_id,ativo) VALUES(?,?,?)", (nome, responsavel, ativo)).lastrowid
            # Lider e membro do setor; os demais entram pela lista explicita.
            if responsavel:
                conn.execute("INSERT OR IGNORE INTO setor_membro(setor_id,usuario_id,desde) VALUES(?,?,?)", (sid, responsavel, self._agora()))
            if "membros" in dados:
                self._membros_sql(sid, dados["membros"], usuario_id, usuario_login)
            self._auditar("setor", sid, "cadastro", antigo, self._um("setor", sid), usuario_id, usuario_login)
            return next(s for s in self.listar_setores() if s["id"] == sid)
        return self._transacao(gravar)

    def _membros_sql(self, setor_id, usuario_ids, usuario_id, usuario_login):
        setor = self._um("setor", setor_id)
        if not isinstance(usuario_ids, list):
            raise regras.ErroTarefas("MEMBRO_INVALIDO", "Informe uma lista de membros do setor.")
        novos = sorted({self._usuario(uid) for uid in usuario_ids})
        if setor["responsavel_usuario_id"] and setor["responsavel_usuario_id"] not in novos:
            raise regras.ErroTarefas("MEMBRO_INVALIDO", "O responsável deve permanecer entre os membros.")
        antes = [r[0] for r in self._conn.execute("SELECT usuario_id FROM setor_membro WHERE setor_id=? AND ate=''", (setor_id,))]
        for uid in set(antes) - set(novos):
            self._conn.execute("UPDATE setor_membro SET ate=? WHERE setor_id=? AND usuario_id=? AND ate=''", (self._agora(), setor_id, uid))
        for uid in set(novos) - set(antes):
            self._conn.execute("INSERT INTO setor_membro(setor_id,usuario_id,desde) VALUES(?,?,?)", (setor_id, uid, self._agora()))
        self._auditar("setor", setor_id, "membros", antes, novos, usuario_id, usuario_login)
        return novos

    def definir_membros(self, setor_id, usuario_ids, *, usuario_id=0, usuario_login=""):
        return self._transacao(lambda conn: self._membros_sql(setor_id, usuario_ids, usuario_id, usuario_login))

    def criar_substituicao(self, dados, *, usuario_id=0, usuario_login=""):
        def gravar(conn):
            titular = self._usuario(dados.get("titular_usuario_id"))
            substituto = self._usuario(dados.get("substituto_usuario_id"))
            sid = _id(dados.get("setor_id"), opcional=True)
            inicio, fim = _data(dados.get("inicio")), _data(dados.get("fim"))
            motivo = _texto(dados.get("motivo"), "Motivo", 1000)
            if titular == substituto or inicio > fim:
                raise regras.ErroTarefas("SUBSTITUICAO_INVALIDA", "Confira as pessoas e o período da substituição.")
            if sid:
                self._um("setor", sid)
                self._membro(sid, titular)
                self._membro(sid, substituto)
            # Global conflita com qualquer setor; dois setores distintos podem coexistir.
            anteriores = conn.execute("SELECT * FROM substituicao WHERE inicio<=? AND fim>=? AND (? IS NULL OR setor_id IS NULL OR setor_id=?)", (fim, inicio, sid, sid)).fetchall()
            if any(r["titular_usuario_id"] == titular for r in anteriores):
                raise regras.ErroTarefas("SUBSTITUICAO_SOBREPOSTA", "Já existe substituição do titular neste período.")
            if any(r["titular_usuario_id"] == substituto or r["substituto_usuario_id"] == titular for r in anteriores):
                raise regras.ErroTarefas("SUBSTITUICAO_ENCADEADA", "Substituições encadeadas no mesmo período não são permitidas.")
            rid = conn.execute("INSERT INTO substituicao(titular_usuario_id,substituto_usuario_id,setor_id,inicio,fim,motivo,criada_por,criada_em) VALUES(?,?,?,?,?,?,?,?)", (titular, substituto, sid, inicio, fim, motivo, usuario_id, self._agora())).lastrowid
            nova = dict(conn.execute("SELECT * FROM substituicao WHERE id=?", (rid,)).fetchone())
            self._auditar("substituicao", rid, "criada", None, nova, usuario_id, usuario_login)
            return nova
        return self._transacao(gravar)

    def listar_substituicoes(self):
        return [dict(r) for r in self._conn.execute("SELECT * FROM substituicao ORDER BY inicio DESC,id DESC")]

    def responsavel_efetivo(self, setor_id, titular_id, hoje=None):
        if titular_id is None:
            return None
        hoje = self._hoje(hoje).isoformat()
        r = self._conn.execute("SELECT substituto_usuario_id FROM substituicao WHERE titular_usuario_id=? AND (setor_id=? OR setor_id IS NULL) AND inicio<=? AND fim>=? ORDER BY id DESC LIMIT 1", (titular_id, setor_id, hoje, hoje)).fetchone()
        return int(r[0]) if r else titular_id

    def setores_responsavel(self, usuario_id, hoje=None):
        if not self.usuario_ativo(usuario_id):
            return []
        return [s["id"] for s in self.listar_setores() if s["ativo"] and
                self.responsavel_efetivo(s["id"], s["responsavel_usuario_id"], hoje) == usuario_id]

    # Caracteristicas e carteira -----------------------------------------
    def listar_caracteristicas(self):
        return [dict(r) for r in self._conn.execute("SELECT * FROM caracteristica ORDER BY grupo,nome")]

    def salvar_caracteristica(self, dados, id=None, *, usuario_id=0, usuario_login=""):
        def gravar(conn):
            antes = self._um("caracteristica", id) if id else {}
            novo = {**antes, **dados}
            grupo, nome = _texto(novo.get("grupo"), "Grupo", 80), _texto(novo.get("nome"))
            exclusiva, ativa = _bool(novo.get("exclusiva_no_grupo", False)), _bool(novo.get("ativa", True))
            if conn.execute("SELECT 1 FROM caracteristica WHERE grupo=? AND exclusiva_no_grupo<>? AND id<>?", (grupo, exclusiva, id or 0)).fetchone():
                raise regras.ErroTarefas("GRUPO_INVALIDO", "Todas as características do grupo devem usar a mesma exclusividade.")
            if id and antes["grupo"] != grupo and conn.execute("SELECT 1 FROM cliente_caracteristica WHERE caracteristica_id=?", (id,)).fetchone():
                raise regras.ErroTarefas("GRUPO_EM_USO", "Desmarque a característica dos clientes antes de mudar seu grupo.")
            if id:
                conn.execute("UPDATE caracteristica SET grupo=?,nome=?,exclusiva_no_grupo=?,ativa=? WHERE id=?", (grupo, nome, exclusiva, ativa, id))
                rid = id
            else:
                rid = conn.execute("INSERT INTO caracteristica(grupo,nome,exclusiva_no_grupo,ativa) VALUES(?,?,?,?)", (grupo, nome, exclusiva, ativa)).lastrowid
            nova = self._um("caracteristica", rid)
            self._auditar("caracteristica", rid, "cadastro", antes, nova, usuario_id, usuario_login)
            return nova
        return self._transacao(gravar)

    def _caracteristicas_sql(self, cliente_id, ids, usuario_id, usuario_login):
        self._um("cliente", cliente_id)
        novas = [self._um("caracteristica", cid) for cid in sorted({_id(i) for i in ids})]
        exclusivos = set()
        for c in novas:
            if not c["ativa"]:
                raise regras.ErroTarefas("CARACTERISTICA_INATIVA", "Não é possível atribuir característica inativa.")
            if c["exclusiva_no_grupo"]:
                if c["grupo"] in exclusivos:
                    raise regras.ErroTarefas("GRUPO_EXCLUSIVO", "Escolha apenas uma característica de cada grupo exclusivo.")
                exclusivos.add(c["grupo"])
        antes = [r[0] for r in self._conn.execute("SELECT caracteristica_id FROM cliente_caracteristica WHERE cliente_id=? ORDER BY caracteristica_id", (cliente_id,))]
        novos_ids = [c["id"] for c in novas]
        if antes != novos_ids:
            self._conn.execute("DELETE FROM cliente_caracteristica WHERE cliente_id=?", (cliente_id,))
            for cid in novos_ids:
                self._conn.execute("INSERT INTO cliente_caracteristica VALUES(?,?,?,?)", (cliente_id, cid, self._agora(), usuario_id))
            self._auditar("cliente", cliente_id, "caracteristicas", antes, novos_ids, usuario_id, usuario_login)
            self._conn.execute("UPDATE cliente SET revision=revision+1,atualizado_em=? WHERE id=?", (self._agora(), cliente_id))
        return novos_ids

    def definir_caracteristicas(self, cliente_ids, ids, *, usuario_id=0, usuario_login=""):
        if not cliente_ids or len(cliente_ids) > 2000:
            raise regras.ErroTarefas("LOTE_INVALIDO", "Selecione entre 1 e 2000 clientes.")
        return self._transacao(lambda conn: [self._caracteristicas_sql(cid, ids, usuario_id, usuario_login) for cid in sorted({_id(i) for i in cliente_ids})])

    def ficha_cliente(self, cliente_id):
        c = self._um("cliente", cliente_id)
        c["caracteristicas"] = [dict(r) for r in self._conn.execute("SELECT k.* FROM caracteristica k JOIN cliente_caracteristica cc ON cc.caracteristica_id=k.id WHERE cc.cliente_id=? ORDER BY k.grupo,k.nome", (cliente_id,))]
        c["carteira"] = [dict(r) for r in self._conn.execute("SELECT c.*,s.nome AS setor_nome FROM carteira c JOIN setor s ON s.id=c.setor_id WHERE cliente_id=? ORDER BY s.nome", (cliente_id,))]
        c["ajustes"] = self.listar_ajustes(cliente_id)
        return c

    def _carteira_sql(self, cliente_id, setor_id, responsavel_id, usuario_id, usuario_login):
        self._um("cliente", cliente_id)
        self._um("setor", setor_id)
        responsavel_id = self._membro(setor_id, responsavel_id)
        anterior = self._conn.execute("SELECT responsavel_usuario_id FROM carteira WHERE cliente_id=? AND setor_id=?", (cliente_id, setor_id)).fetchone()
        antes = anterior[0] if anterior else None
        self._conn.execute("INSERT INTO carteira VALUES(?,?,?,?,?) ON CONFLICT(cliente_id,setor_id) DO UPDATE SET responsavel_usuario_id=excluded.responsavel_usuario_id,desde=excluded.desde,atualizada_por=excluded.atualizada_por", (cliente_id, setor_id, responsavel_id, self._agora(), usuario_id))
        if anterior is None or antes != responsavel_id:
            self._auditar("cliente", cliente_id, f"carteira:{setor_id}", antes, responsavel_id, usuario_id, usuario_login)
            for r in self._conn.execute("SELECT * FROM tarefa WHERE cliente_id=? AND setor_id=? AND situacao IN ('a_fazer','em_andamento','aguardando_cliente','devolvida')", (cliente_id, setor_id)).fetchall():
                if r["responsavel_usuario_id"] != responsavel_id:
                    self._conn.execute("UPDATE tarefa SET responsavel_usuario_id=?,revision=revision+1,atualizada_em=? WHERE id=?", (responsavel_id, self._agora(), r["id"]))
                    self._evento(dict(r), "responsavel", r["responsavel_usuario_id"], responsavel_id, "Mudança de carteira", usuario_id, usuario_login)
        return {"cliente_id": cliente_id, "setor_id": setor_id, "responsavel_usuario_id": responsavel_id}

    def definir_carteira(self, cliente_id, setor_id, responsavel_id, *, usuario_id=0, usuario_login=""):
        return self._transacao(lambda conn: self._carteira_sql(cliente_id, setor_id, responsavel_id, usuario_id, usuario_login))

    # Catalogo e calendario ----------------------------------------------
    @staticmethod
    def _obrigacao_dict(r):
        item = dict(r)
        for campo in ("competencias", "regra_vencimento", "condicao"):
            if isinstance(item[campo], str):
                item[campo] = json.loads(item[campo])
        return item

    def listar_obrigacoes(self, setor_id=None):
        sql = "SELECT * FROM obrigacao"
        parametros = ()
        if setor_id is not None:
            sql += " WHERE setor_id=?"
            parametros = (setor_id,)
        return [self._obrigacao_dict(r) for r in self._conn.execute(sql + " ORDER BY nome", parametros)]

    def salvar_obrigacao(self, dados, id=None, revision=None, *, usuario_id=0, usuario_login=""):
        def gravar(conn):
            antes = self._obrigacao_dict(self._um("obrigacao", id)) if id else {}
            if id and (revision is None or revision != antes["revision"]):
                raise ConcorrenciaError(antes["revision"])
            novo = {**antes, **dados}
            sid = _id(novo.get("setor_id"))
            self._um("setor", sid)
            if id and sid != antes["setor_id"]:
                raise regras.ErroTarefas("SETOR_INVALIDO", "O setor da obrigação não pode ser alterado.")
            nome = _texto(novo.get("nome"))
            periodicidade = novo.get("periodicidade", "mensal")
            competencias = rv.validar_periodicidade(periodicidade, novo.get("competencias"))
            regra = rv.validar_regra(novo.get("regra_vencimento"))
            condicao = regras.validar_condicao(novo.get("condicao") or {})
            for cid in set(sum(condicao.values(), [])):
                self._um("caracteristica", cid)
            antecedencia = novo.get("inicio_antecedencia_dias")
            if antecedencia is not None and (isinstance(antecedencia, bool) or not isinstance(antecedencia, int) or not 0 <= antecedencia <= 366):
                raise regras.ErroTarefas("VALOR_INVALIDO", "Antecedência deve ser um número entre 0 e 366 dias.")
            valores = (sid, nome, periodicidade, _json(competencias), _json(regra), _json(condicao), antecedencia,
                       _bool(novo.get("exige_conferencia", False)), _bool(novo.get("ativa", True)))
            if id:
                conn.execute("UPDATE obrigacao SET setor_id=?,nome=?,periodicidade=?,competencias=?,regra_vencimento=?,condicao=?,inicio_antecedencia_dias=?,exige_conferencia=?,ativa=?,revision=revision+1,atualizada_em=? WHERE id=?", (*valores, self._agora(), id))
                rid = id
            else:
                rid = conn.execute("INSERT INTO obrigacao(setor_id,nome,periodicidade,competencias,regra_vencimento,condicao,inicio_antecedencia_dias,exige_conferencia,ativa,criada_em,atualizada_em) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (*valores, self._agora(), self._agora())).lastrowid
            resultado = self._obrigacao_dict(self._um("obrigacao", rid))
            self._auditar("obrigacao", rid, "cadastro", antes, resultado, usuario_id, usuario_login)
            return resultado
        return self._transacao(gravar)

    def salvar_ajuste(self, dados, id=None, revision=None, *, usuario_id=0, usuario_login=""):
        def gravar(conn):
            antes = self._um("ajuste_cliente", id) if id is not None else {}
            if antes:
                self._revision(antes, revision)
                antes["regra_vencimento"] = json.loads(antes["regra_vencimento"])
            novo = {**antes, **dados}
            cid, oid = _id(novo.get("cliente_id")), _id(novo.get("obrigacao_id"))
            if antes and (cid != antes["cliente_id"] or oid != antes["obrigacao_id"]):
                raise regras.ErroTarefas("AJUSTE_INVALIDO", "Cliente e obrigação do ajuste não podem ser alterados.")
            self._um("cliente", cid)
            self._um("obrigacao", oid)
            tipo = novo.get("tipo")
            if tipo not in ("incluir", "excluir", "vencimento"):
                raise regras.ErroTarefas("AJUSTE_INVALIDO", "Tipo de ajuste inválido.")
            regra = rv.validar_regra(novo.get("regra_vencimento")) if tipo == "vencimento" else {}
            inicio, fim = _data(novo.get("valido_de"), opcional=True), _data(novo.get("valido_ate"), opcional=True)
            if inicio and fim and inicio > fim:
                raise regras.ErroTarefas("AJUSTE_INVALIDO", "A validade inicial deve preceder a final.")
            motivo = _texto(novo.get("motivo"), "Motivo", 1000)
            # Nao escolher silenciosamente entre duas excecoes contraditorias.
            familia = ("vencimento",) if tipo == "vencimento" else ("incluir", "excluir")
            for anterior in conn.execute("SELECT * FROM ajuste_cliente WHERE cliente_id=? AND obrigacao_id=? AND id<>?", (cid, oid, id or 0)):
                if anterior["tipo"] in familia and (anterior["valido_de"] or "0001-01-01") <= (fim or "9999-12-31") and (anterior["valido_ate"] or "9999-12-31") >= (inicio or "0001-01-01"):
                    raise regras.ErroTarefas("AJUSTE_SOBREPOSTO", "Já existe ajuste desta aplicação no período.")
            if antes:
                rid = id
                conn.execute("UPDATE ajuste_cliente SET tipo=?,regra_vencimento=?,valido_de=?,valido_ate=?,motivo=?,revision=revision+1 WHERE id=?",
                             (tipo, _json(regra), inicio, fim, motivo, rid))
            else:
                rid = conn.execute("INSERT INTO ajuste_cliente(cliente_id,obrigacao_id,tipo,regra_vencimento,valido_de,valido_ate,motivo,criado_por,criado_em) VALUES(?,?,?,?,?,?,?,?,?)", (cid, oid, tipo, _json(regra), inicio, fim, motivo, usuario_id, self._agora())).lastrowid
            resultado = self._um("ajuste_cliente", rid)
            resultado["regra_vencimento"] = regra
            self._auditar("cliente", cid, "ajuste", antes or None, resultado, usuario_id, usuario_login)
            return resultado
        return self._transacao(gravar)

    def listar_ajustes(self, cliente_id=None):
        sql = "SELECT a.*,o.nome AS obrigacao_nome,o.setor_id FROM ajuste_cliente a JOIN obrigacao o ON o.id=a.obrigacao_id"
        parametros = ()
        if cliente_id is not None:
            sql += " WHERE a.cliente_id=?"
            parametros = (cliente_id,)
        resultado = []
        for r in self._conn.execute(sql + " ORDER BY a.id DESC", parametros):
            item = dict(r)
            item["regra_vencimento"] = json.loads(item["regra_vencimento"])
            resultado.append(item)
        return resultado

    def feriados(self, ano):
        ano = int(ano)
        base = {(f["data"], f["abrangencia"]): f for f in rv.feriados_nacionais(ano)}
        for r in self._conn.execute("SELECT * FROM feriado WHERE data>=? AND data<=?", (f"{ano:04}-01-01", f"{ano:04}-12-31")):
            base[(r["data"], r["abrangencia"])] = dict(r)
        return sorted(base.values(), key=lambda f: (f["data"], f["abrangencia"]))

    def salvar_feriado(self, dados, *, usuario_id=0, usuario_login=""):
        dia = _data(dados.get("data"))
        abrangencia = dados.get("abrangencia", "municipal")
        if abrangencia not in ("nacional", "estadual", "municipal"):
            raise regras.ErroTarefas("FERIADO_INVALIDO", "Abrangência inválida.")
        descricao = _texto(dados.get("descricao"), "Descrição")
        sem = _bool(dados.get("sem_expediente", True))
        def gravar(conn):
            antes = next((f for f in self.feriados(int(dia[:4])) if f["data"] == dia and f["abrangencia"] == abrangencia), None)
            origem = antes["origem"] if antes else "manual"
            conn.execute("INSERT INTO feriado VALUES(?,?,?,?,?) ON CONFLICT(data,abrangencia) DO UPDATE SET descricao=excluded.descricao,sem_expediente=excluded.sem_expediente", (dia, descricao, abrangencia, origem, sem))
            novo = {"data": dia, "descricao": descricao, "abrangencia": abrangencia, "origem": origem, "sem_expediente": sem}
            self._auditar("feriado", int(dia.replace("-", "")), abrangencia, antes, novo, usuario_id, usuario_login)
            return novo
        return self._transacao(gravar)

    # Geracao: mesma selecao na previa e dentro da transacao de gravacao ---
    def _candidatas(self, competencia, setor_id, cliente_id, hoje):
        ano, mes = rv.validar_competencia(competencia)
        referencia = f"{competencia}-01"
        feriados = [f for a in (ano, ano + 1) for f in self.feriados(a) if f["sem_expediente"]]
        setores = {s["id"]: s for s in self.listar_setores() if s["ativo"]}
        if setor_id is not None:
            setor_id = _id(setor_id)
            self._um("setor", setor_id)
            setores = {k: v for k, v in setores.items() if k == setor_id}
        if cliente_id is not None:
            clientes = [self._um("cliente", cliente_id)]
        else:
            clientes = [dict(r) for r in self._conn.execute("SELECT * FROM cliente WHERE situacao NOT IN ('baixado','nao_cliente') ORDER BY id")]
        caracteristicas = {}
        for r in self._conn.execute("SELECT cc.cliente_id,cc.caracteristica_id FROM cliente_caracteristica cc JOIN caracteristica k ON k.id=cc.caracteristica_id WHERE k.ativa=1"):
            caracteristicas.setdefault(r[0], set()).add(r[1])
        carteira = {(r["cliente_id"], r["setor_id"]): r["responsavel_usuario_id"] for r in self._conn.execute("SELECT * FROM carteira")}
        membros = {(s["id"], uid) for s in setores.values() for uid in s["membros"]}
        ajustes = {}
        for a in self.listar_ajustes(cliente_id):
            if (not a["valido_de"] or a["valido_de"] <= referencia) and (not a["valido_ate"] or a["valido_ate"] >= referencia):
                ajustes.setdefault((a["cliente_id"], a["obrigacao_id"]), []).append(a)
        existentes = {(r[0], r[1]) for r in self._conn.execute("SELECT cliente_id,obrigacao_id FROM tarefa WHERE competencia=?", (competencia,))}
        candidatas, repetidas = [], 0
        for o in self.listar_obrigacoes(setor_id):
            if o["setor_id"] not in setores or not o["ativa"] or not rv.competencia_aplicavel(competencia, o["periodicidade"], o["competencias"]):
                continue
            for c in clientes:
                if c["situacao"] in ("baixado", "nao_cliente"):
                    continue
                ajustes_c = ajustes.get((c["id"], o["id"]), [])
                incluido = any(a["tipo"] == "incluir" for a in ajustes_c)
                excluido = any(a["tipo"] == "excluir" for a in ajustes_c)
                if excluido or (c["situacao"] == "inativo" and not incluido):
                    continue
                if not incluido and not regras.aplica(o["condicao"], caracteristicas.get(c["id"], set())):
                    continue
                if (c["id"], o["id"]) in existentes:
                    repetidas += 1
                    continue
                regra = next((a["regra_vencimento"] for a in ajustes_c if a["tipo"] == "vencimento"), o["regra_vencimento"])
                vencimento = rv.calcular_vencimento(competencia, regra, feriados)
                antecedencia = o["inicio_antecedencia_dias"]
                inicio = hoje if antecedencia is None else vencimento - timedelta(days=antecedencia)
                titular = carteira.get((c["id"], o["setor_id"]))
                if titular and (not self.usuario_ativo(titular) or (o["setor_id"], titular) not in membros):
                    titular = None
                efetivo = self.responsavel_efetivo(o["setor_id"], titular, hoje)
                if efetivo and not self.usuario_ativo(efetivo):
                    # O titular continua na carteira/historico; a distribuicao
                    # nova vai para a fila se seu substituto foi desativado.
                    titular, efetivo = None, None
                candidatas.append({"cliente_id": c["id"], "cliente_nome": c["nome"], "setor_id": o["setor_id"],
                                   "obrigacao_id": o["id"], "competencia": competencia, "titulo": o["nome"],
                                   "responsavel_usuario_id": titular,
                                   "responsavel_efetivo_id": efetivo,
                                   "inicio": inicio.isoformat(), "vencimento": vencimento.isoformat(),
                                   "exige_conferencia": o["exige_conferencia"],
                                   "origem": {"regra": regra, "obrigacao_revision": o["revision"], "condicao": o["condicao"],
                                              "caracteristicas": sorted(caracteristicas.get(c["id"], set())),
                                              "ajustes": ajustes_c}})
        return candidatas, repetidas, list(setores)

    def previa_geracao(self, competencia, setor_id=None, cliente_id=None, hoje=None):
        tarefas, existentes, _ = self._candidatas(competencia, setor_id, cliente_id, self._hoje(hoje))
        return {"tarefas": tarefas, "contagens": {"novas": len(tarefas), "existentes": existentes,
                "criadas": 0, "sem_responsavel": sum(t["responsavel_usuario_id"] is None for t in tarefas)}}

    def _inserir_tarefa(self, dados, usuario_id, usuario_login):
        agora = self._agora()
        rid = self._conn.execute("INSERT INTO tarefa(cliente_id,setor_id,obrigacao_id,competencia,titulo,responsavel_usuario_id,inicio,vencimento,exige_conferencia,origem,criada_em,atualizada_em,situacao_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (dados["cliente_id"], dados["setor_id"], dados.get("obrigacao_id"), dados.get("competencia", ""),
                                 dados["titulo"], dados.get("responsavel_usuario_id"), dados["inicio"], dados["vencimento"],
                                 dados.get("exige_conferencia", 0), _json(dados.get("origem", {})), agora, agora, agora)).lastrowid
        tarefa = self._um("tarefa", rid)
        self._evento(tarefa, "criada", "", "a_fazer", "", usuario_id, usuario_login)
        return rid

    def gerar(self, competencia, setor_id=None, cliente_id=None, hoje=None, *, disparo="manual", usuario_id=0, usuario_login="", previa_esperada=None):
        if disparo not in ("manual", "automatico") or (disparo == "automatico" and cliente_id is not None):
            raise regras.ErroTarefas("GERACAO_INVALIDA", "Disparo de geração inválido.")
        def gravar(conn):
            candidatas, existentes, setores = self._candidatas(competencia, setor_id, cliente_id, self._hoje(hoje))
            if previa_esperada is not None and candidatas != previa_esperada.get("tarefas"):
                raise regras.ErroTarefas("PREVIA_DESATUALIZADA", "A agenda mudou desde a prévia. Revise uma nova prévia antes de gerar.")
            total = {"novas": len(candidatas), "existentes": existentes, "criadas": 0, "sem_responsavel": 0}
            geracoes, criadas = [], []
            for sid in setores:
                if disparo == "automatico" and conn.execute("SELECT 1 FROM geracao WHERE competencia=? AND setor_id=? AND disparo='automatico'", (competencia, sid)).fetchone():
                    continue
                gid = conn.execute("INSERT INTO geracao(competencia,setor_id,disparo,usuario_login,criada_em,contagens) VALUES(?,?,?,?,?,?)", (competencia, sid, disparo, usuario_login, self._agora(), "{}")).lastrowid
                geracoes.append(gid)
                contagem = {"criadas": 0, "sem_responsavel": 0}
                for candidata in (c for c in candidatas if c["setor_id"] == sid):
                    candidata["origem"]["geracao_id"] = gid
                    rid = self._inserir_tarefa(candidata, usuario_id, usuario_login)
                    criadas.append({**candidata, "id": rid})
                    contagem["criadas"] += 1
                    contagem["sem_responsavel"] += int(candidata["responsavel_usuario_id"] is None)
                conn.execute("UPDATE geracao SET contagens=? WHERE id=?", (_json(contagem), gid))
                total["criadas"] += contagem["criadas"]
                total["sem_responsavel"] += contagem["sem_responsavel"]
            return {"tarefas": criadas, "contagens": total, "geracao_ids": geracoes}
        return self._transacao(gravar)

    # Consultas e ciclo de vida ------------------------------------------
    def _tarefa_dict(self, r, hoje=None):
        item = dict(r)
        hoje = self._hoje(hoje)
        item["origem"] = json.loads(item["origem"])
        item["responsavel_efetivo_id"] = self.responsavel_efetivo(item["setor_id"], item["responsavel_usuario_id"], hoje)
        item.update(regras.classificar(item, hoje, self.configuracao()["tarefas_alerta_dias"]))
        item["aguardando_desde"] = item["situacao_em"] if item["situacao"] == "aguardando_cliente" else ""
        item["pendente_conferencia"] = bool(item["situacao"] == "concluida" and item["exige_conferencia"])
        item["nao_se_aplica_mais"] = False
        if item["obrigacao_id"] and item["situacao"] in ABERTAS:
            obrigacao = self._obrigacao_dict(self._um("obrigacao", item["obrigacao_id"]))
            cids = [r[0] for r in self._conn.execute("SELECT cc.caracteristica_id FROM cliente_caracteristica cc JOIN caracteristica c ON c.id=cc.caracteristica_id WHERE cc.cliente_id=? AND c.ativa=1", (item["cliente_id"],))]
            aplica = bool(obrigacao["ativa"]) and regras.aplica(obrigacao["condicao"], cids)
            referencia = item["competencia"] + "-01"
            for ajuste in self.listar_ajustes(item["cliente_id"]):
                if ajuste["obrigacao_id"] != item["obrigacao_id"]:
                    continue
                if (not ajuste["valido_de"] or ajuste["valido_de"] <= referencia) and (not ajuste["valido_ate"] or ajuste["valido_ate"] >= referencia):
                    if ajuste["tipo"] == "incluir":
                        aplica = True
                    elif ajuste["tipo"] == "excluir":
                        aplica = False
            item["nao_se_aplica_mais"] = not aplica
        return item

    def obter_tarefa(self, id, hoje=None):
        r = self._conn.execute("SELECT t.*,c.nome AS cliente_nome,s.nome AS setor_nome FROM tarefa t JOIN cliente c ON c.id=t.cliente_id JOIN setor s ON s.id=t.setor_id WHERE t.id=?", (_id(id),)).fetchone()
        if r is None:
            raise LookupError("Tarefa não encontrada.")
        return self._tarefa_dict(r, hoje)

    def listar_tarefas(self, filtros=None, hoje=None, offset=0, limite=100,
                      escopo_usuario_id=None, escopo_setores=None, todas=False):
        filtros = filtros or {}
        validos = {"cliente_id", "setor_id", "responsavel_usuario_id", "competencia", "situacao",
                   "vencimento_de", "vencimento_ate", "sem_responsavel", "abertas", "texto", "pendente_conferencia"}
        if set(filtros) - validos:
            raise regras.ErroTarefas("FILTRO_INVALIDO", "Filtro de tarefas desconhecido.")
        hoje = self._hoje(hoje)
        onde, valores = [], []
        efetivo = "COALESCE((SELECT sub.substituto_usuario_id FROM substituicao sub WHERE sub.titular_usuario_id=t.responsavel_usuario_id AND (sub.setor_id=t.setor_id OR sub.setor_id IS NULL) AND sub.inicio<=? AND sub.fim>=? ORDER BY sub.id DESC LIMIT 1),t.responsavel_usuario_id)"
        if not todas:
            escopos = []
            if escopo_usuario_id is not None:
                escopos.append(efetivo + "=?")
                valores.extend((hoje.isoformat(), hoje.isoformat(), _id(escopo_usuario_id)))
            if escopo_setores:
                setores = sorted({_id(i) for i in escopo_setores})
                escopos.append("t.setor_id IN (" + ",".join("?" for _ in setores) + ")")
                valores.extend(setores)
            onde.append("(" + " OR ".join(escopos) + ")" if escopos else "0=1")
        for campo in ("cliente_id", "setor_id"):
            if filtros.get(campo) not in (None, ""):
                onde.append(f"t.{campo}=?")
                valores.append(_id(filtros[campo]))
        if filtros.get("responsavel_usuario_id") not in (None, ""):
            onde.append(efetivo + "=?")
            valores.extend((hoje.isoformat(), hoje.isoformat(), _id(filtros["responsavel_usuario_id"])))
        if filtros.get("competencia"):
            rv.validar_competencia(filtros["competencia"])
            onde.append("t.competencia=?")
            valores.append(filtros["competencia"])
        if filtros.get("situacao"):
            situacao = filtros["situacao"]
            if situacao not in (*ABERTAS, "concluida", "conferida", "dispensada"):
                raise regras.ErroTarefas("FILTRO_INVALIDO", "Situação desconhecida.")
            onde.append("t.situacao=?")
            valores.append(situacao)
        for campo, operador in (("vencimento_de", ">="), ("vencimento_ate", "<=")):
            if filtros.get(campo):
                onde.append(f"t.vencimento{operador}?")
                valores.append(_data(filtros[campo]))
        if filtros.get("sem_responsavel"):
            onde.append("t.responsavel_usuario_id IS NULL")
        if filtros.get("abertas"):
            onde.append("(t.situacao IN ('a_fazer','em_andamento','aguardando_cliente','devolvida') OR (t.situacao='concluida' AND t.exige_conferencia=1))")
        if filtros.get("pendente_conferencia"):
            onde.append("t.situacao='concluida' AND t.exige_conferencia=1")
        if filtros.get("texto"):
            termo = str(filtros["texto"]).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            onde.append("(t.titulo LIKE ? ESCAPE '\\' OR c.nome LIKE ? ESCAPE '\\')")
            valores.extend(("%" + termo + "%", "%" + termo + "%"))
        consulta = " FROM tarefa t JOIN cliente c ON c.id=t.cliente_id JOIN setor s ON s.id=t.setor_id"
        if onde:
            consulta += " WHERE " + " AND ".join(onde)
        total = self._conn.execute("SELECT COUNT(*)" + consulta, valores).fetchone()[0]
        limite, offset = max(1, min(2000, int(limite))), max(0, int(offset))
        itens = [self._tarefa_dict(r, hoje) for r in self._conn.execute(
            "SELECT t.*,c.nome AS cliente_nome,s.nome AS setor_nome" + consulta + " ORDER BY t.vencimento,c.nome,t.id LIMIT ? OFFSET ?", (*valores, limite, offset))]
        return {"itens": itens, "total": total, "offset": offset, "limite": limite}

    def criar_avulsa(self, dados, *, usuario_id=0, usuario_login=""):
        def gravar(conn):
            cid, sid = _id(dados.get("cliente_id")), _id(dados.get("setor_id"))
            self._um("cliente", cid)
            self._um("setor", sid)
            responsavel = self._membro(sid, dados.get("responsavel_usuario_id"))
            competencia = dados.get("competencia") or ""
            if competencia:
                rv.validar_competencia(competencia)
            vencimento = _data(dados.get("vencimento"))
            inicio = _data(dados.get("inicio") or self._hoje())
            if inicio > vencimento:
                raise regras.ErroTarefas("DATA_INVALIDA", "O início não pode ser posterior ao vencimento.")
            nova = {"cliente_id": cid, "setor_id": sid, "responsavel_usuario_id": responsavel,
                    "competencia": competencia, "titulo": _texto(dados.get("titulo"), "Título", 200),
                    "inicio": inicio, "vencimento": vencimento,
                    "exige_conferencia": _bool(dados.get("exige_conferencia", False)),
                    "origem": {"tipo": "avulsa"}}
            rid = self._inserir_tarefa(nova, usuario_id, usuario_login)
            return self.obter_tarefa(rid)
        return self._transacao(gravar)

    def _revision(self, tarefa, revision):
        if isinstance(revision, bool) or not isinstance(revision, int) or revision != tarefa["revision"]:
            raise ConcorrenciaError(tarefa["revision"])

    def _mudar_sql(self, id, situacao, revision, motivo, responsavel_setor, usuario_id, usuario_login, hoje=None):
        tarefa = self._um("tarefa", id)
        self._revision(tarefa, revision)
        motivo = str(motivo or "").strip()
        if len(motivo) > 4000:
            raise regras.ErroTarefas("VALOR_INVALIDO", "Comentário deve ter até 4000 caracteres.")
        nova = regras.validar_transicao(tarefa["situacao"], situacao, bool(tarefa["exige_conferencia"]), motivo, responsavel_setor)
        agora = self._agora()
        campos = {"situacao": nova, "situacao_em": agora, "atualizada_em": agora, "revision": tarefa["revision"] + 1}
        substituindo = None
        if nova == "concluida":
            campos.update(concluida_em=agora, concluida_por=usuario_id,
                          fora_do_prazo=int(bool(tarefa["fora_do_prazo"]) or self._hoje(hoje).isoformat() > tarefa["vencimento"]))
        if nova == "conferida":
            setor = self._um("setor", tarefa["setor_id"])
            titular = setor["responsavel_usuario_id"]
            if titular != usuario_id and self.responsavel_efetivo(tarefa["setor_id"], titular, hoje) == usuario_id:
                substituindo = titular
            campos.update(conferida_em=agora, conferida_por=usuario_id, conferida_substituindo=substituindo)
        if nova == "devolvida":
            # A primeira conclusao segue no evento, mas a tarefa aguarda nova entrega.
            campos.update(concluida_em="", concluida_por=None, conferida_em="", conferida_por=None, conferida_substituindo=None)
        self._conn.execute("UPDATE tarefa SET " + ",".join(f"{c}=?" for c in campos) + " WHERE id=?", (*campos.values(), id))
        self._evento(tarefa, "situacao", tarefa["situacao"], nova, motivo, usuario_id, usuario_login, substituindo)
        return self.obter_tarefa(id, hoje)

    def mudar_situacao(self, id, situacao, revision, motivo="", responsavel_setor=False, *, usuario_id=0, usuario_login="", hoje=None):
        return self._transacao(lambda conn: self._mudar_sql(id, situacao, revision, motivo, responsavel_setor, usuario_id, usuario_login, hoje))

    def comentar(self, id, comentario, revision, *, usuario_id=0, usuario_login="", hoje=None):
        comentario = str(comentario or "").strip()
        if not comentario or len(comentario) > 4000:
            raise regras.ErroTarefas("VALOR_INVALIDO", "Comentário é obrigatório (até 4000 caracteres).")
        def gravar(conn):
            tarefa = self._um("tarefa", id)
            self._revision(tarefa, revision)
            self._evento(tarefa, "comentario", "", "", comentario, usuario_id, usuario_login)
            conn.execute("UPDATE tarefa SET revision=revision+1,atualizada_em=? WHERE id=?", (self._agora(), id))
            return self.obter_tarefa(id, hoje)
        return self._transacao(gravar)

    def _lote(self, tarefas):
        if not isinstance(tarefas, list) or not 1 <= len(tarefas) <= 1000:
            raise regras.ErroTarefas("LOTE_INVALIDO", "Selecione entre 1 e 1000 tarefas.")
        validadas, ids = [], set()
        for item in tarefas:
            tarefa = self._um("tarefa", item.get("id"))
            if tarefa["id"] in ids:
                raise regras.ErroTarefas("LOTE_INVALIDO", "Uma tarefa aparece mais de uma vez no lote.")
            ids.add(tarefa["id"])
            self._revision(tarefa, item.get("revision"))
            validadas.append(tarefa)
        return validadas

    def redistribuir(self, tarefas, responsavel_id, motivo, *, usuario_id=0, usuario_login="", hoje=None):
        motivo = _texto(motivo, "Motivo", 1000)
        def gravar(conn):
            lote = self._lote(tarefas)
            for tarefa in lote:
                self._membro(tarefa["setor_id"], responsavel_id)
                if tarefa["situacao"] not in ABERTAS:
                    raise regras.ErroTarefas("TAREFA_FECHADA", "Só tarefas abertas podem ser redistribuídas.")
            for tarefa in lote:
                conn.execute("UPDATE tarefa SET responsavel_usuario_id=?,revision=revision+1,atualizada_em=? WHERE id=?", (responsavel_id, self._agora(), tarefa["id"]))
                self._evento(tarefa, "responsavel", tarefa["responsavel_usuario_id"], responsavel_id, motivo, usuario_id, usuario_login)
            return [self.obter_tarefa(t["id"], hoje) for t in lote]
        return self._transacao(gravar)

    def dispensar_lote(self, tarefas, motivo, *, usuario_id=0, usuario_login="", hoje=None):
        motivo = _texto(motivo, "Motivo", 1000)
        def gravar(conn):
            lote = self._lote(tarefas)
            return [self._mudar_sql(t["id"], "dispensada", t["revision"], motivo, True, usuario_id, usuario_login, hoje) for t in lote]
        return self._transacao(gravar)

    def eventos(self, tarefa_id):
        self._um("tarefa", tarefa_id)
        return [dict(r) for r in self._conn.execute("SELECT * FROM tarefa_evento WHERE tarefa_id=? ORDER BY id", (tarefa_id,))]

    # Importacao confirmada; nenhuma criacao de cliente por suposicao ------
    def importar_carteira(self, linhas, setor_id, responsavel_usuario_id, hash_arquivo, nome_arquivo,
                         *, usuario_id=0, usuario_login=""):
        if not isinstance(linhas, list) or not 1 <= len(linhas) <= 20000:
            raise regras.ErroTarefas("IMPORTACAO_INVALIDA", "Confirme pelo menos uma linha da planilha.")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", hash_arquivo):
            raise regras.ErroTarefas("IMPORTACAO_INVALIDA", "Hash de origem inválido.")
        def gravar(conn):
            self._um("setor", setor_id)
            self._membro(setor_id, responsavel_usuario_id)
            vistos = set()
            for linha in linhas:
                cid = _id(linha.get("cliente_id"))
                if cid in vistos:
                    raise regras.ErroTarefas("IMPORTACAO_DUPLICADA", "Confirme apenas uma linha por cliente.")
                vistos.add(cid)
                atual = self._um("cliente", cid)
                contato = " ".join(str(linha.get("contato_nome") or "").split())[:160]
                try:
                    email = cl.validar_email(linha.get("contato_email"))
                except cl.ErroClientes as exc:
                    raise regras.ErroTarefas("EMAIL_INVALIDO", exc.mensagem) from exc
                # Campos vazios da planilha nao apagam contatos existentes.
                dados = {"contato_nome": contato or atual["contato_nome"], "contato_email": email or atual["contato_email"]}
                for campo, valor in dados.items():
                    if valor != atual[campo]:
                        conn.execute(f"UPDATE cliente SET {campo}=?,revision=revision+1,atualizado_em=? WHERE id=?", (valor, self._agora(), cid))
                        self._auditar("cliente", cid, campo, atual[campo], valor, usuario_id, usuario_login)
                ids = linha.get("caracteristica_ids", [])
                if ids:
                    existentes = {r[0] for r in conn.execute("SELECT caracteristica_id FROM cliente_caracteristica WHERE cliente_id=?", (cid,))}
                    for kid in ids:
                        nova = self._um("caracteristica", kid)
                        if nova["exclusiva_no_grupo"]:
                            existentes -= {c["id"] for c in self.listar_caracteristicas() if c["grupo"] == nova["grupo"]}
                    self._caracteristicas_sql(cid, list(existentes | set(ids)), usuario_id, usuario_login)
                self._carteira_sql(cid, setor_id, responsavel_usuario_id, usuario_id, usuario_login)
                origem = {"hash_arquivo": hash_arquivo, "nome_arquivo": str(nome_arquivo)[:200],
                          "aba": str((linha.get("origem") or {}).get("aba", ""))[:80],
                          "linha": (linha.get("origem") or {}).get("linha"),
                          "colunas": (linha.get("origem") or {}).get("celulas", (linha.get("origem") or {}).get("colunas", {}))}
                self._auditar("cliente", cid, "importacao_carteira", None, origem, usuario_id, usuario_login)
            contagens = {"clientes": len(vistos), "carteiras": len(vistos)}
            conn.execute("INSERT INTO importacao(tipo,hash_arquivo,nome_arquivo,usuario_login,criada_em,contagens) VALUES('carteira',?,?,?,?,?)", (hash_arquivo, str(nome_arquivo)[:200], usuario_login, self._agora(), _json(contagens)))
            return contagens
        return self._transacao(gravar)

    # Configuracao e exclusao mutua dos resumos diarios -------------------
    def configuracao(self):
        resultado = {"tarefas_alerta_dias": 3, "tarefas_resumo_hora": "07:00", "tarefas_aguardando_cliente_dias": 5}
        for r in self._conn.execute("SELECT chave,valor FROM configuracao WHERE chave LIKE 'tarefas_%'"):
            if r["chave"] in resultado:
                resultado[r["chave"]] = json.loads(r["valor"])
        return resultado

    def definir_configuracao(self, dados, *, usuario_id=0, usuario_login=""):
        atual = self.configuracao()
        if set(dados) - set(atual):
            raise regras.ErroTarefas("CONFIGURACAO_INVALIDA", "Configuração desconhecida.")
        novo = {**atual, **dados}
        for campo in ("tarefas_alerta_dias", "tarefas_aguardando_cliente_dias"):
            if isinstance(novo[campo], bool) or not isinstance(novo[campo], int) or not 0 <= novo[campo] <= 365:
                raise regras.ErroTarefas("CONFIGURACAO_INVALIDA", "Informe dias entre 0 e 365.")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(novo["tarefas_resumo_hora"])):
            raise regras.ErroTarefas("CONFIGURACAO_INVALIDA", "Horário deve estar em HH:MM.")
        def gravar(conn):
            for campo, valor in dados.items():
                conn.execute("INSERT INTO configuracao VALUES(?,?,?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,atualizado_por_login=excluded.atualizado_por_login,atualizado_em=excluded.atualizado_em", (campo, _json(valor), usuario_login, self._agora()))
            self._auditar("tarefas_configuracao", 0, "configuracao", atual, novo, usuario_id, usuario_login)
            return novo
        return self._transacao(gravar)

    def reservar_envio(self, usuario_id, dia, destino, quantidades):
        dia = _data(dia)
        destino = regras.validar_email(destino)
        return self._transacao(lambda conn: conn.execute("INSERT OR IGNORE INTO envio_alerta(usuario_id,dia,destino,quantidades,resultado,criado_em) VALUES(?,?,?,?,'em_envio',?)", (_id(usuario_id), dia, destino, _json(quantidades), self._agora())).rowcount == 1)

    def finalizar_envio(self, usuario_id, dia, resultado, erro=""):
        if resultado not in ("ok", "falha", "desligado"):
            raise ValueError("Resultado de envio inválido.")
        # Chamador fornece apenas categoria sanitizada; texto SMTP pode conter credencial.
        erro = str(erro or "")[:200]
        return self._transacao(lambda conn: conn.execute("UPDATE envio_alerta SET resultado=?,erro=? WHERE usuario_id=? AND dia=? AND canal='email' AND resultado='em_envio'", (resultado, erro, usuario_id, _data(dia))).rowcount == 1)

    def listar_envios(self, dia=None):
        sql, valores = "SELECT * FROM envio_alerta", ()
        if dia is not None:
            sql += " WHERE dia=?"
            valores = (_data(dia),)
        resultado = []
        for r in self._conn.execute(sql + " ORDER BY id DESC", valores):
            item = dict(r)
            item["quantidades"] = json.loads(item["quantidades"])
            resultado.append(item)
        return resultado
