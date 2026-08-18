"""Persistencia da Conciliacao Fiscal: SQLite dedicado e imutavel.

Banco proprio (`dados_web/conciliacao.db`) porque o dominio fiscal versionado
tem ciclo de vida, trilha e backup proprios; misturar com autenticacao ou
conferencia acoplaria coisas que evoluem em ritmos diferentes.

Sem FastAPI, sem sessao HTTP, sem `request`: caminhos e identidade chegam por
injecao, e a identidade chega como SNAPSHOT primitivo (`usuario_id`,
`usuario_login`) — nunca um objeto de autenticacao. Assim a regra fiscal e'
testavel sem servidor e o ator de uma mutacao nao pode ser forjado pelo corpo
de uma requisicao.

Tres invariantes que o schema garante no proprio SQL, nao so no Python:

- fonte, movimento, fato, revisao e evento recusam UPDATE e DELETE;
- de uma versao so o `estado` muda — valor financeiro, CNPJ, competencia e
  proveniencia sao imutaveis;
- `UNIQUE(cnpj, competencia)` e `UNIQUE(sha256)` transformam corrida em
  resultado idempotente, nao em dado duplicado.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from ..core import conciliacao_sefaz as cs

VERSAO_SCHEMA = 1

ESTADO_EM_REVISAO = "em_revisao"
ESTADO_APROVADA = "aprovada"
ESTADO_REJEITADA = "rejeitada"

VERSAO_VIGENTE = "vigente"
VERSAO_CANDIDATA = "candidata"
VERSAO_SUBSTITUIDA = "substituida"
VERSAO_DESCARTADA = "descartada"

RESULTADO_PROCESSADO = "processado"
RESULTADO_DUPLICADO = "duplicado"
RESULTADO_CONFLITANTE = "conflitante"
RESULTADO_REJEITADO = "rejeitado"

CAMPOS_FINANCEIROS = (
    "receita_declarada", "declarada_com_st", "declarada_sem_st",
    "receita_calculada", "calculada_com_st", "calculada_sem_st",
    "diferenca_receita", "diferenca_com_st", "diferenca_sem_st",
    "total_pix", "total_nao_pix",
)


class ConcorrenciaError(Exception):
    """A conciliacao mudou desde que o cliente a leu.

    Carrega a revision ATUAL para o cliente recarregar e decidir de novo em
    cima do estado real, em vez de sobrescrever a decisao de outra pessoa.
    """

    def __init__(self, revision_atual: int):
        super().__init__("Registro desatualizado.")
        self.revision_atual = revision_atual


class TransicaoInvalida(Exception):
    """A mudanca pedida nao e' permitida a partir do estado atual."""

    def __init__(self, mensagem: str, codigo: str = "TRANSICAO_INVALIDA"):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


@dataclass
class ItemImportado:
    """Resultado de UM arquivo dentro de um lote."""

    nome_recebido: str
    resultado: str
    mensagem: str
    ordem: int
    sha256: str = ""
    codigo_erro: str = ""
    conciliacao_id: int | None = None
    versao_id: int | None = None
    fonte_id: int | None = None


def agora() -> str:
    """UTC ISO-8601. A apresentacao converte; o banco nao guarda fuso local."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# Schema

_TABELAS = """
CREATE TABLE IF NOT EXISTS lote_importacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sessao_id TEXT NOT NULL DEFAULT '',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'recebido',
  total_arquivos INTEGER NOT NULL DEFAULT 0,
  processados INTEGER NOT NULL DEFAULT 0,
  duplicados INTEGER NOT NULL DEFAULT 0,
  conflitantes INTEGER NOT NULL DEFAULT 0,
  rejeitados INTEGER NOT NULL DEFAULT 0,
  criado_em TEXT NOT NULL,
  iniciado_em TEXT NOT NULL DEFAULT '',
  concluido_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fonte_fiscal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sha256 TEXT NOT NULL UNIQUE,
  nome_original TEXT NOT NULL,
  caminho_relativo TEXT NOT NULL UNIQUE,
  tamanho_bytes INTEGER NOT NULL,
  layout TEXT NOT NULL DEFAULT '',
  versao_parser TEXT NOT NULL,
  resultado TEXT NOT NULL DEFAULT 'processada',
  mensagem TEXT NOT NULL DEFAULT '',
  enviada_por_id INTEGER NOT NULL DEFAULT 0,
  enviada_por_login TEXT NOT NULL,
  recebida_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_lote (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lote_id INTEGER NOT NULL REFERENCES lote_importacao(id),
  fonte_id INTEGER REFERENCES fonte_fiscal(id),
  nome_recebido TEXT NOT NULL,
  sha256_tentativa TEXT NOT NULL DEFAULT '',
  tamanho_bytes INTEGER NOT NULL DEFAULT 0,
  versao_parser TEXT NOT NULL,
  codigo_erro TEXT NOT NULL DEFAULT '',
  ordem INTEGER NOT NULL,
  resultado TEXT NOT NULL,
  mensagem TEXT NOT NULL,
  criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conciliacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cnpj TEXT NOT NULL,
  competencia TEXT NOT NULL,
  razao_social TEXT NOT NULL DEFAULT '',
  versao_vigente_id INTEGER,
  estado TEXT NOT NULL DEFAULT 'em_revisao',
  revision INTEGER NOT NULL DEFAULT 1,
  criada_em TEXT NOT NULL,
  atualizada_em TEXT NOT NULL,
  UNIQUE (cnpj, competencia)
);

CREATE TABLE IF NOT EXISTS versao_conciliacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conciliacao_id INTEGER NOT NULL REFERENCES conciliacao(id),
  fonte_id INTEGER NOT NULL UNIQUE REFERENCES fonte_fiscal(id),
  numero INTEGER NOT NULL,
  estado TEXT NOT NULL,
  layout TEXT NOT NULL,
  razao_social TEXT NOT NULL DEFAULT '',
  receita_declarada INTEGER NOT NULL,
  declarada_com_st INTEGER NOT NULL,
  declarada_sem_st INTEGER NOT NULL,
  receita_calculada INTEGER NOT NULL,
  calculada_com_st INTEGER NOT NULL,
  calculada_sem_st INTEGER NOT NULL,
  diferenca_receita INTEGER NOT NULL,
  diferenca_com_st INTEGER NOT NULL,
  diferenca_sem_st INTEGER NOT NULL,
  total_pix INTEGER,
  total_nao_pix INTEGER,
  aba_origem TEXT NOT NULL,
  linha_resumo INTEGER NOT NULL,
  versao_parser TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  UNIQUE (conciliacao_id, numero)
);

CREATE TABLE IF NOT EXISTS movimento_dimp (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  versao_id INTEGER NOT NULL REFERENCES versao_conciliacao(id),
  instituicao TEXT NOT NULL,
  linha_origem INTEGER NOT NULL,
  debito INTEGER NOT NULL,
  credito INTEGER NOT NULL,
  transferencia INTEGER NOT NULL,
  pix INTEGER NOT NULL,
  voucher INTEGER NOT NULL,
  outras INTEGER NOT NULL,
  total_dimp INTEGER NOT NULL,
  total_nao_pix INTEGER NOT NULL,
  aba TEXT NOT NULL DEFAULT '',
  celula_total TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fato_extraido (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  versao_id INTEGER NOT NULL REFERENCES versao_conciliacao(id),
  metrica TEXT NOT NULL,
  valor_numerico INTEGER,
  valor_texto TEXT,
  tipo_origem TEXT NOT NULL,
  aba TEXT,
  celula TEXT,
  rotulo TEXT NOT NULL DEFAULT '',
  regra_parser TEXT NOT NULL,
  formula TEXT,
  fatos_origem_json TEXT NOT NULL DEFAULT '[]',
  versao_parser TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS excecao_conciliacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conciliacao_id INTEGER NOT NULL REFERENCES conciliacao(id),
  versao_id INTEGER NOT NULL REFERENCES versao_conciliacao(id),
  codigo TEXT NOT NULL,
  severidade TEXT NOT NULL,
  mensagem TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'aberta',
  resolucao TEXT NOT NULL DEFAULT '',
  resolvida_por_id INTEGER NOT NULL DEFAULT 0,
  resolvida_por_login TEXT NOT NULL DEFAULT '',
  criada_em TEXT NOT NULL,
  resolvida_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conflito_importacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conciliacao_id INTEGER NOT NULL REFERENCES conciliacao(id),
  versao_vigente_id INTEGER NOT NULL REFERENCES versao_conciliacao(id),
  versao_candidata_id INTEGER NOT NULL UNIQUE REFERENCES versao_conciliacao(id),
  estado TEXT NOT NULL DEFAULT 'aberto',
  justificativa TEXT NOT NULL DEFAULT '',
  resolvido_por_id INTEGER NOT NULL DEFAULT 0,
  resolvido_por_login TEXT NOT NULL DEFAULT '',
  criado_em TEXT NOT NULL,
  resolvido_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS revisao_conciliacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conciliacao_id INTEGER NOT NULL REFERENCES conciliacao(id),
  versao_id INTEGER REFERENCES versao_conciliacao(id),
  revision_anterior INTEGER NOT NULL,
  estado_anterior TEXT NOT NULL,
  estado_novo TEXT NOT NULL,
  justificativa TEXT NOT NULL DEFAULT '',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  criada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evento_fiscal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conciliacao_id INTEGER REFERENCES conciliacao(id),
  versao_id INTEGER REFERENCES versao_conciliacao(id),
  fonte_id INTEGER REFERENCES fonte_fiscal(id),
  acao TEXT NOT NULL,
  detalhes_json TEXT NOT NULL DEFAULT '{}',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  criada_em TEXT NOT NULL
);
"""

_INDICES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_conc_chave
  ON conciliacao(cnpj, competencia);
CREATE INDEX IF NOT EXISTS idx_conc_estado
  ON conciliacao(estado, competencia);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fonte_sha ON fonte_fiscal(sha256);
CREATE INDEX IF NOT EXISTS idx_versao_estado
  ON versao_conciliacao(conciliacao_id, estado);
CREATE INDEX IF NOT EXISTS idx_excecao_estado
  ON excecao_conciliacao(estado, severidade);
-- Indice que sustenta SC-011. Resumo e filtro de excecao perguntam, para
-- CADA conciliacao, "existe excecao aberta desta severidade na versao
-- vigente?". Sem uma chave que cubra os quatro campos da pergunta, cada
-- linha vira uma varredura da tabela de excecoes: medido em 3,2 s no resumo
-- e 7,9 s no filtro com 10 mil conciliacoes, contra 2 s de meta. Com o
-- indice, os dois caem para a casa dos milissegundos.
CREATE INDEX IF NOT EXISTS idx_excecao_por_versao
  ON excecao_conciliacao(conciliacao_id, versao_id, estado, severidade);
CREATE INDEX IF NOT EXISTS idx_mov_versao
  ON movimento_dimp(versao_id, instituicao);
CREATE INDEX IF NOT EXISTS idx_evento_conc
  ON evento_fiscal(conciliacao_id, id);
CREATE INDEX IF NOT EXISTS idx_lote_usuario
  ON lote_importacao(usuario_login, criado_em);
CREATE INDEX IF NOT EXISTS idx_item_lote ON item_lote(lote_id, ordem);
CREATE INDEX IF NOT EXISTS idx_conflito_estado
  ON conflito_importacao(conciliacao_id, estado);
"""


def _sql_append_only(tabela: str, rotulo: str) -> str:
    """Bloqueia UPDATE e DELETE na propria base.

    A garantia mora no SQL, e nao apenas no Python, porque a evidencia fiscal
    precisa sobreviver a um script de manutencao distraido ou a um `sqlite3`
    aberto na mao.
    """
    return f"""
CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_update
BEFORE UPDATE ON {tabela} BEGIN
  SELECT RAISE(ABORT, '{rotulo} e imutavel: UPDATE nao e permitido.');
END;
CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_delete
BEFORE DELETE ON {tabela} BEGIN
  SELECT RAISE(ABORT, '{rotulo} e imutavel: DELETE nao e permitido.');
END;
"""


_TRIGGERS = "".join([
    _sql_append_only("fonte_fiscal", "Fonte fiscal"),
    _sql_append_only("movimento_dimp", "Movimento DIMP"),
    _sql_append_only("fato_extraido", "Fato extraido"),
    _sql_append_only("revisao_conciliacao", "Revisao"),
    _sql_append_only("evento_fiscal", "Evento fiscal"),
    # Da versao, so o estado muda. Sem isto, um UPDATE em massa poderia
    # reescrever receita sem deixar rastro nenhum.
    f"""
CREATE TRIGGER IF NOT EXISTS trg_versao_sem_delete
BEFORE DELETE ON versao_conciliacao BEGIN
  SELECT RAISE(ABORT, 'Versao e imutavel: DELETE nao e permitido.');
END;
CREATE TRIGGER IF NOT EXISTS trg_versao_so_estado
BEFORE UPDATE ON versao_conciliacao
WHEN {" OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in CAMPOS_FINANCEIROS)}
     OR NEW.conciliacao_id IS NOT OLD.conciliacao_id
     OR NEW.fonte_id IS NOT OLD.fonte_id
     OR NEW.numero IS NOT OLD.numero
     OR NEW.layout IS NOT OLD.layout
     OR NEW.aba_origem IS NOT OLD.aba_origem
     OR NEW.linha_resumo IS NOT OLD.linha_resumo
BEGIN
  SELECT RAISE(ABORT,
    'Somente o estado de uma versao pode mudar; valores sao imutaveis.');
END;
""",
])


class ConciliacaoStore:
    """Uma instancia por thread. Conexao SQLite nao atravessa thread."""

    def __init__(self, db_path: str, origens_path: str):
        self.db_path = db_path
        self.origens_path = origens_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        os.makedirs(origens_path, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=15,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._trava = threading.Lock()
        self._migrar()
        self._recuperar_lotes_abandonados()

    # ------------------------------------------------------------------
    # Ciclo de vida

    def _migrar(self) -> None:
        conn = self._conn
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(_TABELAS)
        conn.executescript(_INDICES)
        conn.executescript(_TRIGGERS)
        conn.execute(f"PRAGMA user_version={VERSAO_SCHEMA}")

    def _recuperar_lotes_abandonados(self) -> None:
        """Lote em 'processando' na abertura so pode ser sobra de queda.

        Jobs vivem em memoria: se o processo caiu no meio, ninguem mais vai
        concluir aquele lote. Deixa-lo eternamente 'processando' esconderia a
        falha e travaria a leitura do resultado (FR-015).
        """
        self._conn.execute(
            "UPDATE lote_importacao SET estado='interrompido',"
            " concluido_em=? WHERE estado='processando'", (agora(),))

    def fechar(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------------
    # Utilitarios

    def contar(self, tabela: str) -> int:
        if tabela not in {
            "lote_importacao", "fonte_fiscal", "item_lote", "conciliacao",
            "versao_conciliacao", "movimento_dimp", "fato_extraido",
            "excecao_conciliacao", "conflito_importacao",
            "revisao_conciliacao", "evento_fiscal"}:
            raise ValueError(f"Tabela desconhecida: {tabela}")
        return self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {tabela}").fetchone()["n"]

    @staticmethod
    def sha256_do_arquivo(caminho: str) -> str:
        digest = hashlib.sha256()
        with open(caminho, "rb") as arq:
            for bloco in iter(lambda: arq.read(1024 * 1024), b""):
                digest.update(bloco)
        return digest.hexdigest()

    def _evento(self, conn, acao: str, *, usuario_id: int, usuario_login: str,
                conciliacao_id: int | None = None, versao_id: int | None = None,
                fonte_id: int | None = None, detalhes: dict | None = None) -> None:
        conn.execute(
            "INSERT INTO evento_fiscal(conciliacao_id, versao_id, fonte_id,"
            " acao, detalhes_json, usuario_id, usuario_login, criada_em)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (conciliacao_id, versao_id, fonte_id, acao,
             json.dumps(detalhes or {}, ensure_ascii=False, sort_keys=True),
             usuario_id, usuario_login, agora()))

    def _revisao(self, conn, conciliacao_id: int, *, versao_id: int | None,
                 revision_anterior: int, estado_anterior: str,
                 estado_novo: str, justificativa: str, usuario_id: int,
                 usuario_login: str) -> None:
        conn.execute(
            "INSERT INTO revisao_conciliacao(conciliacao_id, versao_id,"
            " revision_anterior, estado_anterior, estado_novo, justificativa,"
            " usuario_id, usuario_login, criada_em) VALUES(?,?,?,?,?,?,?,?,?)",
            (conciliacao_id, versao_id, revision_anterior, estado_anterior,
             estado_novo, justificativa, usuario_id, usuario_login, agora()))

    # ------------------------------------------------------------------
    # Lotes

    def abrir_lote(self, *, sessao_id: str, usuario_id: int,
                   usuario_login: str, total_arquivos: int) -> int:
        cur = self._conn.execute(
            "INSERT INTO lote_importacao(sessao_id, usuario_id, usuario_login,"
            " estado, total_arquivos, criado_em) VALUES(?,?,?,?,?,?)",
            (sessao_id, usuario_id, usuario_login, "recebido",
             int(total_arquivos), agora()))
        return int(cur.lastrowid)

    def marcar_processando(self, lote_id: int) -> None:
        self._conn.execute(
            "UPDATE lote_importacao SET estado='processando', iniciado_em=?"
            " WHERE id=?", (agora(), lote_id))

    def obter_lote(self, lote_id: int, usuario_login: str = "") -> dict:
        linha = self._conn.execute(
            "SELECT * FROM lote_importacao WHERE id=?", (lote_id,)).fetchone()
        if linha is None or (usuario_login
                             and linha["usuario_login"] != usuario_login):
            # Lote alheio responde como inexistente: nao confirmamos o ID.
            raise LookupError("Lote nao encontrado.")
        lote = dict(linha)
        lote["itens"] = [dict(i) for i in self._conn.execute(
            "SELECT * FROM item_lote WHERE lote_id=? ORDER BY ordem, id",
            (lote_id,))]
        return lote

    def concluir_lote(self, lote_id: int) -> dict:
        contagens = self._conn.execute(
            "SELECT resultado, COUNT(*) AS n FROM item_lote WHERE lote_id=?"
            " GROUP BY resultado", (lote_id,)).fetchall()
        mapa = {l["resultado"]: l["n"] for l in contagens}
        self._conn.execute(
            "UPDATE lote_importacao SET estado='concluido', concluido_em=?,"
            " processados=?, duplicados=?, conflitantes=?, rejeitados=?"
            " WHERE id=?",
            (agora(), mapa.get(RESULTADO_PROCESSADO, 0),
             mapa.get(RESULTADO_DUPLICADO, 0),
             mapa.get(RESULTADO_CONFLITANTE, 0),
             mapa.get(RESULTADO_REJEITADO, 0), lote_id))
        return {"lote_id": lote_id,
                "processados": mapa.get(RESULTADO_PROCESSADO, 0),
                "duplicados": mapa.get(RESULTADO_DUPLICADO, 0),
                "conflitantes": mapa.get(RESULTADO_CONFLITANTE, 0),
                "rejeitados": mapa.get(RESULTADO_REJEITADO, 0)}

    # ------------------------------------------------------------------
    # Importacao

    def importar_arquivo(self, lote_id: int, *, caminho_staging: str,
                         nome_recebido: str, ordem: int, usuario_id: int,
                         usuario_login: str,
                         max_bytes: int | None = None) -> ItemImportado:
        """Le, valida, preserva e persiste UM arquivo.

        O parse acontece FORA da transacao: ler XLSX e' a parte lenta, e
        segurar a escrita do banco durante ela transformaria um lote grande
        num bloqueio para todo mundo (SC-013).
        """
        try:
            sha = self.sha256_do_arquivo(caminho_staging)
        except OSError as exc:
            return self._registrar_item(
                lote_id, nome_recebido, ordem, RESULTADO_REJEITADO,
                f"Nao foi possivel ler o arquivo enviado: {exc}",
                codigo_erro=cs.XLSX_INVALIDO)

        existente = self._conn.execute(
            "SELECT f.id AS fonte_id, v.id AS versao_id,"
            " v.conciliacao_id AS conciliacao_id FROM fonte_fiscal f"
            " LEFT JOIN versao_conciliacao v ON v.fonte_id = f.id"
            " WHERE f.sha256=?", (sha,)).fetchone()
        if existente is not None:
            return self._registrar_item(
                lote_id, nome_recebido, ordem, RESULTADO_DUPLICADO,
                "Arquivo ja importado anteriormente (mesmo conteudo).",
                sha256=sha, fonte_id=existente["fonte_id"],
                versao_id=existente["versao_id"],
                conciliacao_id=existente["conciliacao_id"],
                tamanho=os.path.getsize(caminho_staging))

        try:
            relatorio = cs.ler_relatorio(
                caminho_staging, sha256=sha, nome_original=nome_recebido,
                max_bytes=max_bytes)
        except cs.ErroConciliacao as exc:
            return self._registrar_item(
                lote_id, nome_recebido, ordem, RESULTADO_REJEITADO,
                exc.mensagem, codigo_erro=exc.codigo, sha256=sha,
                tamanho=os.path.getsize(caminho_staging))

        # Promocao ATOMICA da fonte antes de o banco apontar para ela: o
        # inverso deixaria uma linha referenciando arquivo que pode nao
        # existir se o processo cair no meio.
        destino = os.path.join(self.origens_path, f"{sha}.xlsx")
        if not os.path.exists(destino):
            temporario = f"{destino}.parcial-{os.getpid()}-{threading.get_ident()}"
            shutil.copyfile(caminho_staging, temporario)
            try:
                os.replace(temporario, destino)
            except OSError:
                if os.path.exists(temporario):
                    os.remove(temporario)
                if not os.path.exists(destino):
                    raise

        try:
            return self._persistir(lote_id, relatorio, sha, nome_recebido,
                                   ordem, usuario_id, usuario_login,
                                   os.path.getsize(caminho_staging))
        except sqlite3.IntegrityError:
            # Corrida: outra operacao gravou a mesma fonte entre a consulta e
            # o INSERT. `UNIQUE(sha256)` transforma isso em resultado
            # idempotente, nao em erro 500. O ROLLBACK ja aconteceu dentro de
            # `_persistir`; repeti-lo aqui estouraria "no transaction active".
            achado = self._conn.execute(
                "SELECT f.id AS fonte_id, v.id AS versao_id,"
                " v.conciliacao_id AS conciliacao_id FROM fonte_fiscal f"
                " LEFT JOIN versao_conciliacao v ON v.fonte_id = f.id"
                " WHERE f.sha256=?", (sha,)).fetchone()
            return self._registrar_item(
                lote_id, nome_recebido, ordem, RESULTADO_DUPLICADO,
                "Arquivo importado simultaneamente por outra operacao.",
                sha256=sha,
                fonte_id=achado["fonte_id"] if achado else None,
                versao_id=achado["versao_id"] if achado else None,
                conciliacao_id=achado["conciliacao_id"] if achado else None,
                tamanho=os.path.getsize(caminho_staging))

    def _persistir(self, lote_id: int, rel: cs.RelatorioConciliacao, sha: str,
                   nome_recebido: str, ordem: int, usuario_id: int,
                   usuario_login: str, tamanho: int) -> ItemImportado:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT INTO fonte_fiscal(sha256, nome_original,"
                " caminho_relativo, tamanho_bytes, layout, versao_parser,"
                " resultado, mensagem, enviada_por_id, enviada_por_login,"
                " recebida_em) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (sha, nome_recebido, f"conciliacao/origens/{sha}.xlsx",
                 tamanho, rel.layout, rel.versao_parser, "processada", "",
                 usuario_id, usuario_login, agora()))
            fonte_id = int(cur.lastrowid)

            conciliacao = conn.execute(
                "SELECT * FROM conciliacao WHERE cnpj=? AND competencia=?",
                (rel.cnpj, rel.competencia)).fetchone()

            if conciliacao is None:
                cur = conn.execute(
                    "INSERT INTO conciliacao(cnpj, competencia, razao_social,"
                    " estado, revision, criada_em, atualizada_em)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (rel.cnpj, rel.competencia, rel.razao_social,
                     ESTADO_EM_REVISAO, 1, agora(), agora()))
                conciliacao_id = int(cur.lastrowid)
                numero, estado_versao = 1, VERSAO_VIGENTE
                conflito = False
            else:
                conciliacao_id = int(conciliacao["id"])
                numero = int(conn.execute(
                    "SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM"
                    " versao_conciliacao WHERE conciliacao_id=?",
                    (conciliacao_id,)).fetchone()["n"])
                estado_versao, conflito = VERSAO_CANDIDATA, True

            versao_id = self._inserir_versao(conn, conciliacao_id, fonte_id,
                                             numero, estado_versao, rel)

            if conciliacao is None:
                conn.execute(
                    "UPDATE conciliacao SET versao_vigente_id=?,"
                    " atualizada_em=? WHERE id=?",
                    (versao_id, agora(), conciliacao_id))
                self._revisao(conn, conciliacao_id, versao_id=versao_id,
                              revision_anterior=0,
                              estado_anterior="", estado_novo=ESTADO_EM_REVISAO,
                              justificativa="Primeira importacao.",
                              usuario_id=usuario_id,
                              usuario_login=usuario_login)
            else:
                self._chegou_candidata(conn, conciliacao, versao_id,
                                       usuario_id, usuario_login)

            self._evento(conn, "importacao", usuario_id=usuario_id,
                         usuario_login=usuario_login,
                         conciliacao_id=conciliacao_id, versao_id=versao_id,
                         fonte_id=fonte_id,
                         detalhes={"sha256": sha, "layout": rel.layout,
                                   "competencia": rel.competencia,
                                   "cnpj": rel.cnpj})
            if conflito:
                self._evento(conn, "conflito_aberto", usuario_id=usuario_id,
                             usuario_login=usuario_login,
                             conciliacao_id=conciliacao_id,
                             versao_id=versao_id, fonte_id=fonte_id,
                             detalhes={"sha256": sha})

            resultado = (RESULTADO_CONFLITANTE if conflito
                         else RESULTADO_PROCESSADO)
            mensagem = ("Retificacao recebida como versao candidata; a versao "
                        "vigente foi preservada."
                        if conflito else "Importado com sucesso.")
            self._inserir_item(conn, lote_id, nome_recebido, ordem, resultado,
                               mensagem, sha256=sha, fonte_id=fonte_id,
                               tamanho=tamanho)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        return ItemImportado(
            nome_recebido=nome_recebido, resultado=resultado,
            mensagem=mensagem, ordem=ordem, sha256=sha,
            conciliacao_id=conciliacao_id, versao_id=versao_id,
            fonte_id=fonte_id)

    def _inserir_versao(self, conn, conciliacao_id: int, fonte_id: int,
                        numero: int, estado: str,
                        rel: cs.RelatorioConciliacao) -> int:
        cur = conn.execute(
            "INSERT INTO versao_conciliacao(conciliacao_id, fonte_id, numero,"
            " estado, layout, razao_social, receita_declarada,"
            " declarada_com_st, declarada_sem_st, receita_calculada,"
            " calculada_com_st, calculada_sem_st, diferenca_receita,"
            " diferenca_com_st, diferenca_sem_st, total_pix, total_nao_pix,"
            " aba_origem, linha_resumo, versao_parser, criada_em)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (conciliacao_id, fonte_id, numero, estado, rel.layout,
             rel.razao_social,
             cs.centavos(rel.receita_declarada),
             cs.centavos(rel.declarada_com_st),
             cs.centavos(rel.declarada_sem_st),
             cs.centavos(rel.receita_calculada),
             cs.centavos(rel.calculada_com_st),
             cs.centavos(rel.calculada_sem_st),
             cs.centavos(rel.diferenca_receita),
             cs.centavos(rel.diferenca_com_st),
             cs.centavos(rel.diferenca_sem_st),
             cs.centavos(rel.total_pix),          # None continua None
             cs.centavos(rel.total_nao_pix),
             rel.aba_origem, rel.linha_resumo, rel.versao_parser, agora()))
        versao_id = int(cur.lastrowid)

        for mov in rel.movimentos:
            conn.execute(
                "INSERT INTO movimento_dimp(versao_id, instituicao,"
                " linha_origem, debito, credito, transferencia, pix, voucher,"
                " outras, total_dimp, total_nao_pix, aba, celula_total)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (versao_id, mov.instituicao, mov.linha_origem,
                 cs.centavos(mov.debito), cs.centavos(mov.credito),
                 cs.centavos(mov.transferencia), cs.centavos(mov.pix),
                 cs.centavos(mov.voucher), cs.centavos(mov.outras),
                 cs.centavos(mov.total_dimp), cs.centavos(mov.total_nao_pix),
                 mov.aba, mov.celula_total))

        for f in rel.fatos:
            conn.execute(
                "INSERT INTO fato_extraido(versao_id, metrica, valor_numerico,"
                " valor_texto, tipo_origem, aba, celula, rotulo, regra_parser,"
                " formula, fatos_origem_json, versao_parser)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (versao_id, f.metrica, cs.centavos(f.valor), None,
                 f.tipo_origem, f.aba, f.celula, f.rotulo, f.regra_parser,
                 f.formula, json.dumps(list(f.fatos_origem)), f.versao_parser))

        for exc in rel.excecoes:
            conn.execute(
                "INSERT INTO excecao_conciliacao(conciliacao_id, versao_id,"
                " codigo, severidade, mensagem, estado, criada_em)"
                " VALUES(?,?,?,?,?,?,?)",
                (conciliacao_id, versao_id, exc.codigo, exc.severidade,
                 exc.mensagem, "aberta", agora()))

        return versao_id

    def _chegou_candidata(self, conn, conciliacao, versao_id: int,
                          usuario_id: int, usuario_login: str) -> None:
        """Candidata nova devolve a conciliacao a Em revisao (FR-051).

        Uma competencia aprovada que recebe retificacao nao pode continuar
        aprovada: a decisao anterior foi tomada sobre outros numeros.
        """
        conciliacao_id = int(conciliacao["id"])
        estado_anterior = conciliacao["estado"]
        revision_anterior = int(conciliacao["revision"])

        conn.execute(
            "INSERT INTO conflito_importacao(conciliacao_id,"
            " versao_vigente_id, versao_candidata_id, estado, criado_em)"
            " VALUES(?,?,?,?,?)",
            (conciliacao_id, conciliacao["versao_vigente_id"], versao_id,
             "aberto", agora()))

        conn.execute(
            "UPDATE conciliacao SET estado=?, revision=revision+1,"
            " atualizada_em=? WHERE id=?",
            (ESTADO_EM_REVISAO, agora(), conciliacao_id))
        self._revisao(
            conn, conciliacao_id, versao_id=versao_id,
            revision_anterior=revision_anterior,
            estado_anterior=estado_anterior, estado_novo=ESTADO_EM_REVISAO,
            justificativa="Nova versao candidata recebida por importacao.",
            usuario_id=usuario_id, usuario_login=usuario_login)

    def _inserir_item(self, conn, lote_id: int, nome: str, ordem: int,
                      resultado: str, mensagem: str, *, sha256: str = "",
                      codigo_erro: str = "", fonte_id: int | None = None,
                      tamanho: int = 0) -> None:
        conn.execute(
            "INSERT INTO item_lote(lote_id, fonte_id, nome_recebido,"
            " sha256_tentativa, tamanho_bytes, versao_parser, codigo_erro,"
            " ordem, resultado, mensagem, criado_em)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (lote_id, fonte_id, nome, sha256, tamanho, cs.VERSAO_PARSER,
             codigo_erro, ordem, resultado, mensagem, agora()))

    def _registrar_item(self, lote_id: int, nome: str, ordem: int,
                        resultado: str, mensagem: str, *, sha256: str = "",
                        codigo_erro: str = "", fonte_id: int | None = None,
                        versao_id: int | None = None,
                        conciliacao_id: int | None = None,
                        tamanho: int = 0) -> ItemImportado:
        self._inserir_item(self._conn, lote_id, nome, ordem, resultado,
                           mensagem, sha256=sha256, codigo_erro=codigo_erro,
                           fonte_id=fonte_id, tamanho=tamanho)
        return ItemImportado(
            nome_recebido=nome, resultado=resultado, mensagem=mensagem,
            ordem=ordem, sha256=sha256, codigo_erro=codigo_erro,
            fonte_id=fonte_id, versao_id=versao_id,
            conciliacao_id=conciliacao_id)

    # ------------------------------------------------------------------
    # Leitura

    def detalhar(self, conciliacao_id: int) -> dict:
        linha = self._conn.execute(
            "SELECT * FROM conciliacao WHERE id=?",
            (conciliacao_id,)).fetchone()
        if linha is None:
            raise LookupError("Conciliacao nao encontrada.")
        detalhe = dict(linha)

        versoes = [dict(v) for v in self._conn.execute(
            "SELECT * FROM versao_conciliacao WHERE conciliacao_id=?"
            " ORDER BY numero", (conciliacao_id,))]
        detalhe["versoes"] = versoes
        vigente = next((v for v in versoes
                        if v["id"] == linha["versao_vigente_id"]), None)
        detalhe["versao_vigente"] = vigente

        alvo = vigente["id"] if vigente else -1
        detalhe["movimentos"] = [dict(m) for m in self._conn.execute(
            "SELECT * FROM movimento_dimp WHERE versao_id=? ORDER BY id",
            (alvo,))]
        detalhe["fatos"] = [dict(f) for f in self._conn.execute(
            "SELECT * FROM fato_extraido WHERE versao_id=? ORDER BY id",
            (alvo,))]
        detalhe["excecoes"] = [dict(e) for e in self._conn.execute(
            "SELECT * FROM excecao_conciliacao WHERE conciliacao_id=?"
            " ORDER BY id", (conciliacao_id,))]
        detalhe["conflitos"] = [dict(c) for c in self._conn.execute(
            "SELECT * FROM conflito_importacao WHERE conciliacao_id=?"
            " ORDER BY id", (conciliacao_id,))]
        detalhe["revisoes"] = [dict(r) for r in self._conn.execute(
            "SELECT * FROM revisao_conciliacao WHERE conciliacao_id=?"
            " ORDER BY id", (conciliacao_id,))]

        # Fatos derivados guardam os fatos de origem como JSON; a leitura
        # devolve lista, para o cliente nao ter de desserializar de novo.
        for fato in detalhe["fatos"]:
            try:
                fato["fatos_origem"] = json.loads(
                    fato.pop("fatos_origem_json", "[]") or "[]")
            except (TypeError, ValueError):
                fato["fatos_origem"] = []

        # A fonte da versao vigente: e' dela que saem arquivo, hash e versao
        # do parser exibidos ao lado de cada valor.
        detalhe["fonte"] = None
        if vigente is not None:
            fonte = self._conn.execute(
                "SELECT * FROM fonte_fiscal WHERE id=?",
                (vigente["fonte_id"],)).fetchone()
            if fonte is not None:
                detalhe["fonte"] = dict(fonte)

        # Contadores coerentes com os da listagem.
        detalhe.update(self._contagens_excecao(
            conciliacao_id, linha["versao_vigente_id"]))
        return detalhe

    def eventos(self, conciliacao_id: int) -> list[dict]:
        return [dict(e) for e in self._conn.execute(
            "SELECT * FROM evento_fiscal WHERE conciliacao_id=? ORDER BY id",
            (conciliacao_id,))]

    # ------------------------------------------------------------------
    # Decisoes: revisao, aprovacao, excecoes e conflitos
    #
    # Toda mutacao daqui grava, NA MESMA TRANSACAO, o novo estado, a revisao
    # (append-only) e o evento fiscal. A trilha geral de `auditoria_web.db` e'
    # fail-open por desenho — nunca derruba a rota — entao ela nao serve de
    # prova de uma mutacao fiscal. A prova mora aqui, junto do dado.
    #
    # A identidade chega sempre como snapshot primitivo vindo da sessao
    # autenticada. Nenhum metodo aceita "ator" de corpo de requisicao.

    def _travar_conciliacao(self, conn, conciliacao_id: int, revision: int | None):
        """Le a conciliacao e confere a revision otimista."""
        linha = conn.execute("SELECT * FROM conciliacao WHERE id=?",
                             (conciliacao_id,)).fetchone()
        if linha is None:
            raise LookupError("Conciliacao nao encontrada.")
        if revision is not None and int(revision) != int(linha["revision"]):
            raise ConcorrenciaError(int(linha["revision"]))
        return linha

    def _bloqueios_abertos(self, conn, conciliacao_id: int, versao_id) -> int:
        return int(conn.execute(
            "SELECT COUNT(*) AS n FROM excecao_conciliacao"
            " WHERE conciliacao_id=? AND versao_id=? AND estado='aberta'"
            " AND severidade='bloqueio'",
            (conciliacao_id, versao_id)).fetchone()["n"])

    def _conflitos_abertos(self, conn, conciliacao_id: int) -> int:
        return int(conn.execute(
            "SELECT COUNT(*) AS n FROM conflito_importacao"
            " WHERE conciliacao_id=? AND estado='aberto'",
            (conciliacao_id,)).fetchone()["n"])

    def _mudar_estado(self, conn, linha, *, estado_novo: str,
                      justificativa: str, usuario_id: int, usuario_login: str,
                      acao: str, detalhes: dict | None = None) -> dict:
        conciliacao_id = int(linha["id"])
        anterior = linha["estado"]
        revision_anterior = int(linha["revision"])
        conn.execute(
            "UPDATE conciliacao SET estado=?, revision=revision+1,"
            " atualizada_em=? WHERE id=?",
            (estado_novo, agora(), conciliacao_id))
        self._revisao(conn, conciliacao_id, versao_id=linha["versao_vigente_id"],
                      revision_anterior=revision_anterior,
                      estado_anterior=anterior, estado_novo=estado_novo,
                      justificativa=justificativa, usuario_id=usuario_id,
                      usuario_login=usuario_login)
        self._evento(conn, acao, usuario_id=usuario_id,
                     usuario_login=usuario_login,
                     conciliacao_id=conciliacao_id,
                     versao_id=linha["versao_vigente_id"],
                     detalhes={"de": anterior, "para": estado_novo,
                               **(detalhes or {})})
        return {"id": conciliacao_id, "estado": estado_novo,
                "revision": revision_anterior + 1}

    def revisar(self, conciliacao_id: int, *, estado_novo: str,
                justificativa: str, revision: int | None = None,
                usuario_id: int = 0, usuario_login: str = "") -> dict:
        """Rejeita uma competencia ou a devolve para Em revisao.

        Aprovar tem porta propria (`aprovar`), com permissao propria: rejeitar
        e aprovar sao decisoes de peso diferente.
        """
        if estado_novo not in (ESTADO_EM_REVISAO, ESTADO_REJEITADA):
            raise TransicaoInvalida(
                "A revisao so pode rejeitar ou devolver para Em revisao.")
        if not justificativa.strip():
            raise TransicaoInvalida(
                "Justificativa e' obrigatoria em qualquer decisao fiscal.",
                "JUSTIFICATIVA_OBRIGATORIA")

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            linha = self._travar_conciliacao(conn, conciliacao_id, revision)
            if linha["estado"] == estado_novo:
                raise TransicaoInvalida(
                    f"A competencia ja esta em '{estado_novo}'.")
            resultado = self._mudar_estado(
                conn, linha, estado_novo=estado_novo,
                justificativa=justificativa, usuario_id=usuario_id,
                usuario_login=usuario_login,
                acao="rejeicao" if estado_novo == ESTADO_REJEITADA
                else "devolucao_revisao")
            conn.execute("COMMIT")
            return resultado
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def aprovar(self, conciliacao_id: int, *, justificativa: str = "",
                revision: int | None = None, usuario_id: int = 0,
                usuario_login: str = "") -> dict:
        """Aprova a versao vigente.

        Bloqueio aberto da vigente ou conflito aberto IMPEDEM a aprovacao, e a
        checagem acontece dentro da transacao: conferir antes e gravar depois
        deixaria espaco para uma candidata chegar no meio e a aprovacao valer
        sobre outros numeros.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            linha = self._travar_conciliacao(conn, conciliacao_id, revision)
            if linha["estado"] != ESTADO_EM_REVISAO:
                raise TransicaoInvalida(
                    "So e' possivel aprovar a partir de Em revisao. Devolva a "
                    "competencia para revisao antes de decidir de novo.")
            if linha["versao_vigente_id"] is None:
                raise TransicaoInvalida("A competencia nao tem versao vigente.")

            bloqueios = self._bloqueios_abertos(conn, conciliacao_id,
                                                linha["versao_vigente_id"])
            conflitos = self._conflitos_abertos(conn, conciliacao_id)
            if bloqueios or conflitos:
                raise TransicaoInvalida(
                    f"Aprovacao impedida: {bloqueios} bloqueio(s) e "
                    f"{conflitos} conflito(s) em aberto. Resolva antes de "
                    f"aprovar.", "APROVACAO_IMPEDIDA")

            resultado = self._mudar_estado(
                conn, linha, estado_novo=ESTADO_APROVADA,
                justificativa=justificativa, usuario_id=usuario_id,
                usuario_login=usuario_login, acao="aprovacao")
            conn.execute("COMMIT")
            return resultado
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def resolver_excecao(self, excecao_id: int, *, resolucao: str,
                         usuario_id: int = 0, usuario_login: str = "") -> dict:
        """Encerra um aviso ou bloqueio, com justificativa obrigatoria."""
        if not resolucao.strip():
            raise TransicaoInvalida(
                "A resolucao precisa dizer POR QUE a excecao foi encerrada.",
                "JUSTIFICATIVA_OBRIGATORIA")

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            excecao = conn.execute(
                "SELECT * FROM excecao_conciliacao WHERE id=?",
                (excecao_id,)).fetchone()
            if excecao is None:
                raise LookupError("Excecao nao encontrada.")
            if excecao["estado"] != "aberta":
                raise TransicaoInvalida("Esta excecao ja foi resolvida.")

            conn.execute(
                "UPDATE excecao_conciliacao SET estado='resolvida',"
                " resolucao=?, resolvida_por_id=?, resolvida_por_login=?,"
                " resolvida_em=? WHERE id=?",
                (resolucao, usuario_id, usuario_login, agora(), excecao_id))
            conn.execute(
                "UPDATE conciliacao SET revision=revision+1, atualizada_em=?"
                " WHERE id=?", (agora(), excecao["conciliacao_id"]))
            self._evento(conn, "excecao_resolvida", usuario_id=usuario_id,
                         usuario_login=usuario_login,
                         conciliacao_id=excecao["conciliacao_id"],
                         versao_id=excecao["versao_id"],
                         detalhes={"excecao_id": excecao_id,
                                   "codigo": excecao["codigo"],
                                   "severidade": excecao["severidade"]})
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"id": excecao_id, "estado": "resolvida"}

    # ------------------------------------------------------------------
    # Conflitos de versao

    def comparar_versoes(self, vigente_id: int, candidata_id: int) -> list[dict]:
        """Diferenca campo a campo entre a vigente e a candidata."""
        vigente = self._conn.execute(
            "SELECT * FROM versao_conciliacao WHERE id=?",
            (vigente_id,)).fetchone()
        candidata = self._conn.execute(
            "SELECT * FROM versao_conciliacao WHERE id=?",
            (candidata_id,)).fetchone()
        if vigente is None or candidata is None:
            raise LookupError("Versao nao encontrada.")
        diferencas = []
        for campo in CAMPOS_FINANCEIROS:
            de, para = vigente[campo], candidata[campo]
            diferencas.append({
                "campo": campo, "vigente": de, "candidata": para,
                "mudou": de != para,
                # None em um lado e numero no outro NAO e' "delta": e' a
                # troca de um layout sem DIMP por um com DIMP, ou o inverso.
                "delta": (para - de) if (de is not None and para is not None)
                else None,
            })
        return diferencas

    def listar_conflitos(self, *, estado: str = "aberto", pagina: int = 1,
                         limite: int = 50) -> dict:
        onde, valores = "", []
        if estado:
            if estado not in ("aberto", "mantida_vigente", "promovida_candidata"):
                raise ValueError("Estado de conflito desconhecido: " + estado)
            onde, valores = " WHERE k.estado = ?", [estado]
        de_para = (" FROM conflito_importacao k"
                   " JOIN conciliacao c ON c.id = k.conciliacao_id")
        limite = max(1, min(int(limite or 50), 200))
        pagina = max(1, int(pagina or 1))
        total = int(self._conn.execute(
            "SELECT COUNT(*) AS n" + de_para + onde,
            valores).fetchone()["n"])
        paginas = max(1, -(-total // limite))
        pagina = min(pagina, paginas)
        linhas = self._conn.execute(
            "SELECT k.*, c.cnpj, c.competencia, c.razao_social, c.revision"
            + de_para + onde
            + " ORDER BY k.id DESC LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite]).fetchall()
        return {"itens": [dict(l) for l in linhas], "total": total,
                "pagina": pagina, "limite": limite, "paginas": paginas}

    def resolver_conflito(self, conflito_id: int, *, decisao: str,
                          justificativa: str, revision: int | None = None,
                          usuario_id: int = 0,
                          usuario_login: str = "") -> dict:
        """Mantem a vigente ou promove a candidata, preservando o historico.

        Promover NAO apaga nada: a vigente anterior vira `substituida` e
        continua consultavel com seus movimentos, fatos e proveniencia. A
        conciliacao volta para Em revisao, porque a decisao anterior (se
        houve) foi tomada sobre outros numeros.

        A vigente do instante em que o conflito nasceu e' comparada com a
        vigente ATUAL: se mudou, ninguem promove uma candidata contra uma base
        diferente sem reanalisar.
        """
        if decisao not in ("manter_vigente", "promover_candidata"):
            raise TransicaoInvalida("Decisao desconhecida: " + str(decisao))
        if not justificativa.strip():
            raise TransicaoInvalida(
                "Justificativa e' obrigatoria para resolver um conflito.",
                "JUSTIFICATIVA_OBRIGATORIA")

        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conflito = conn.execute(
                "SELECT * FROM conflito_importacao WHERE id=?",
                (conflito_id,)).fetchone()
            if conflito is None:
                raise LookupError("Conflito nao encontrado.")
            if conflito["estado"] != "aberto":
                raise TransicaoInvalida("Este conflito ja foi resolvido.")

            linha = self._travar_conciliacao(
                conn, int(conflito["conciliacao_id"]), revision)
            if linha["versao_vigente_id"] != conflito["versao_vigente_id"]:
                raise TransicaoInvalida(
                    "A versao vigente mudou desde que este conflito foi "
                    "aberto. Recarregue e compare de novo antes de decidir.",
                    "VIGENTE_ALTERADA")

            candidata_id = int(conflito["versao_candidata_id"])
            if decisao == "manter_vigente":
                conn.execute(
                    "UPDATE versao_conciliacao SET estado=? WHERE id=?",
                    (VERSAO_DESCARTADA, candidata_id))
                novo_vigente = linha["versao_vigente_id"]
            else:
                conn.execute(
                    "UPDATE versao_conciliacao SET estado=? WHERE id=?",
                    (VERSAO_SUBSTITUIDA, linha["versao_vigente_id"]))
                conn.execute(
                    "UPDATE versao_conciliacao SET estado=? WHERE id=?",
                    (VERSAO_VIGENTE, candidata_id))
                novo_vigente = candidata_id

            conn.execute(
                "UPDATE conflito_importacao SET estado=?, justificativa=?,"
                " resolvido_por_id=?, resolvido_por_login=?, resolvido_em=?"
                " WHERE id=?",
                ("mantida_vigente" if decisao == "manter_vigente"
                 else "promovida_candidata", justificativa, usuario_id,
                 usuario_login, agora(), conflito_id))

            revision_anterior = int(linha["revision"])
            estado_anterior = linha["estado"]
            conn.execute(
                "UPDATE conciliacao SET versao_vigente_id=?, estado=?,"
                " revision=revision+1, atualizada_em=? WHERE id=?",
                (novo_vigente, ESTADO_EM_REVISAO, agora(), linha["id"]))
            if decisao == "promover_candidata":
                # A razao social passa a ser a da versao promovida.
                nova = conn.execute(
                    "SELECT razao_social FROM versao_conciliacao WHERE id=?",
                    (candidata_id,)).fetchone()
                if nova is not None and nova["razao_social"]:
                    conn.execute(
                        "UPDATE conciliacao SET razao_social=? WHERE id=?",
                        (nova["razao_social"], linha["id"]))

            self._revisao(
                conn, int(linha["id"]), versao_id=novo_vigente,
                revision_anterior=revision_anterior,
                estado_anterior=estado_anterior, estado_novo=ESTADO_EM_REVISAO,
                justificativa=justificativa, usuario_id=usuario_id,
                usuario_login=usuario_login)
            self._evento(
                conn, "conflito_resolvido", usuario_id=usuario_id,
                usuario_login=usuario_login, conciliacao_id=int(linha["id"]),
                versao_id=novo_vigente,
                detalhes={"conflito_id": conflito_id, "decisao": decisao})
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"id": conflito_id, "decisao": decisao,
                "versao_vigente_id": novo_vigente,
                "estado": ESTADO_EM_REVISAO,
                "revision": revision_anterior + 1}

    # ------------------------------------------------------------------
    # Consultas: resumo, listagem, excecoes e fonte
    #
    # Todo filtro passa por ALLOWLIST. Nome de campo jamais viaja do cliente
    # para dentro do SQL e valor de enum e' conferido contra o conjunto
    # conhecido, entao a listagem aceita combinacao livre sem abrir espaco
    # para injecao.

    ORDENACOES = {
        "competencia_desc": "c.competencia DESC, c.cnpj ASC",
        "competencia_asc": "c.competencia ASC, c.cnpj ASC",
        "empresa_asc": "c.razao_social ASC, c.competencia DESC",
        "diferenca_desc": "ABS(COALESCE(v.diferenca_receita, 0)) DESC",
    }

    _ESTADOS = (ESTADO_EM_REVISAO, ESTADO_APROVADA, ESTADO_REJEITADA)
    _LAYOUTS = (cs.LAYOUT_50_5, cs.LAYOUT_50_3)
    _EXCECOES = ("aviso", "bloqueio", "conflito")
    _FILTROS = ("cnpj", "texto", "competencia_de", "competencia_ate",
                "estado", "layout", "excecao")

    _DE_PARA = (" FROM conciliacao c"
                " LEFT JOIN versao_conciliacao v ON v.id = c.versao_vigente_id")

    def _condicoes(self, filtros: dict) -> tuple[str, list]:
        """WHERE compartilhado por resumo e listagem.

        Os dois PRECISAM usar o mesmo filtro: indicador contando um universo
        e tabela mostrando outro e' o jeito mais rapido de alguem decidir
        sobre um numero que nao existe.
        """
        desconhecidos = sorted(set(filtros) - set(self._FILTROS))
        if desconhecidos:
            raise ValueError(
                "Filtro desconhecido: " + ", ".join(desconhecidos) + ".")

        onde: list[str] = []
        valores: list = []

        cnpj = "".join(c for c in str(filtros.get("cnpj") or "") if c.isdigit())
        if cnpj:
            onde.append("c.cnpj = ?")
            valores.append(cnpj)

        texto = str(filtros.get("texto") or "").strip()
        if texto:
            # ESCAPE: '%' e '_' digitados sao texto, nao curinga.
            padrao = "%" + (texto.replace("\\", "\\\\")
                            .replace("%", "\\%")
                            .replace("_", "\\_").upper()) + "%"
            onde.append("(UPPER(c.razao_social) LIKE ? ESCAPE '\\'"
                        " OR c.cnpj LIKE ? ESCAPE '\\')")
            valores.extend([padrao, padrao])

        for chave, operador in (("competencia_de", ">="),
                                ("competencia_ate", "<=")):
            bruto = str(filtros.get(chave) or "").strip()
            if bruto:
                onde.append("c.competencia " + operador + " ?")
                valores.append(cs.normalizar_competencia(bruto))

        estado = str(filtros.get("estado") or "").strip()
        if estado:
            if estado not in self._ESTADOS:
                raise ValueError("Estado desconhecido: " + estado + ".")
            onde.append("c.estado = ?")
            valores.append(estado)

        layout = str(filtros.get("layout") or "").strip()
        if layout:
            if layout not in self._LAYOUTS:
                raise ValueError("Layout desconhecido: " + layout + ".")
            onde.append("v.layout = ?")
            valores.append(layout)

        excecao = str(filtros.get("excecao") or "").strip()
        if excecao:
            if excecao not in self._EXCECOES:
                raise ValueError("Tipo de excecao desconhecido: " + excecao + ".")
            if excecao == "conflito":
                onde.append(
                    "EXISTS (SELECT 1 FROM conflito_importacao k"
                    " WHERE k.conciliacao_id = c.id AND k.estado = 'aberto')")
            else:
                # So excecoes da versao VIGENTE contam para o estado corrente;
                # as de versoes substituidas permanecem no historico.
                onde.append(
                    "EXISTS (SELECT 1 FROM excecao_conciliacao e"
                    " WHERE e.conciliacao_id = c.id"
                    " AND e.versao_id = c.versao_vigente_id"
                    " AND e.estado = 'aberta' AND e.severidade = ?)")
                valores.append(excecao)

        return ((" WHERE " + " AND ".join(onde)) if onde else "", valores)

    def resumo(self, **filtros) -> dict:
        """Indicadores do painel, com os MESMOS filtros da listagem."""
        onde, valores = self._condicoes(filtros)
        linha = self._conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(c.estado = 'em_revisao') AS em_revisao,"
            " SUM(c.estado = 'aprovada') AS aprovadas,"
            " SUM(c.estado = 'rejeitada') AS rejeitadas,"
            " COALESCE(SUM(v.diferenca_receita), 0) AS diferenca_total,"
            " SUM(EXISTS (SELECT 1 FROM excecao_conciliacao e"
            "  WHERE e.conciliacao_id = c.id"
            "  AND e.versao_id = c.versao_vigente_id"
            "  AND e.estado = 'aberta' AND e.severidade = 'aviso')) AS avisos,"
            " SUM(EXISTS (SELECT 1 FROM excecao_conciliacao e"
            "  WHERE e.conciliacao_id = c.id"
            "  AND e.versao_id = c.versao_vigente_id"
            "  AND e.estado = 'aberta'"
            "  AND e.severidade = 'bloqueio')) AS bloqueios,"
            " SUM(EXISTS (SELECT 1 FROM conflito_importacao k"
            "  WHERE k.conciliacao_id = c.id"
            "  AND k.estado = 'aberto')) AS conflitos"
            + self._DE_PARA + onde, valores).fetchone()
        return {chave: int(linha[chave] or 0) for chave in (
            "total", "em_revisao", "aprovadas", "rejeitadas", "avisos",
            "bloqueios", "conflitos", "diferenca_total")}

    def listar(self, *, pagina: int = 1, limite: int = 50,
               ordenar: str = "competencia_desc", **filtros) -> dict:
        onde, valores = self._condicoes(filtros)
        if ordenar not in self.ORDENACOES:
            raise ValueError("Ordenacao desconhecida: " + str(ordenar) + ".")

        limite = max(1, min(int(limite or 50), 200))
        pagina = max(1, int(pagina or 1))
        total = int(self._conn.execute(
            "SELECT COUNT(*) AS n" + self._DE_PARA + onde,
            valores).fetchone()["n"])
        paginas = max(1, -(-total // limite))
        # Prende a pagina ao numero real: OFFSET gigante estouraria o inteiro
        # do SQLite em vez de devolver uma pagina vazia sensata.
        pagina = min(pagina, paginas)

        linhas = self._conn.execute(
            "SELECT c.id, c.cnpj, c.razao_social, c.competencia, c.estado,"
            " c.revision, v.id AS versao_id, v.numero,"
            " v.estado AS versao_estado, v.layout, v.receita_declarada,"
            " v.receita_calculada, v.diferenca_receita, v.total_pix,"
            " v.total_nao_pix"
            + self._DE_PARA + onde
            + " ORDER BY " + self.ORDENACOES[ordenar]
            + ", c.id DESC LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite]).fetchall()

        return {"itens": [self._linha_lista(l) for l in linhas],
                "total": total, "pagina": pagina, "limite": limite,
                "paginas": paginas}

    def _contagens_excecao(self, conciliacao_id: int, vigente_id) -> dict:
        linha = self._conn.execute(
            "SELECT"
            " (SELECT COUNT(*) FROM excecao_conciliacao e"
            "  WHERE e.conciliacao_id=? AND e.versao_id=?"
            "  AND e.estado='aberta' AND e.severidade='aviso') AS avisos,"
            " (SELECT COUNT(*) FROM excecao_conciliacao e"
            "  WHERE e.conciliacao_id=? AND e.versao_id=?"
            "  AND e.estado='aberta' AND e.severidade='bloqueio') AS bloqueios,"
            " (SELECT COUNT(*) FROM conflito_importacao k"
            "  WHERE k.conciliacao_id=? AND k.estado='aberto') AS conflitos",
            (conciliacao_id, vigente_id, conciliacao_id, vigente_id,
             conciliacao_id)).fetchone()
        return {"avisos_abertos": int(linha["avisos"]),
                "bloqueios_abertos": int(linha["bloqueios"]),
                "conflitos_abertos": int(linha["conflitos"])}

    def _linha_lista(self, l) -> dict:
        return {
            "id": l["id"], "cnpj": l["cnpj"],
            "razao_social": l["razao_social"],
            "competencia": l["competencia"], "estado": l["estado"],
            "revision": l["revision"],
            "versao": {
                "id": l["versao_id"], "numero": l["numero"],
                "estado": l["versao_estado"], "layout": l["layout"],
                "receita_declarada": l["receita_declarada"],
                "receita_calculada": l["receita_calculada"],
                "diferenca_receita": l["diferenca_receita"],
                "total_pix": l["total_pix"],
                "total_nao_pix": l["total_nao_pix"],
            },
            **self._contagens_excecao(l["id"], l["versao_id"]),
        }

    def instituicoes(self, versao_id: int) -> list[dict]:
        """Agregado por instituicao, para leitura.

        `linhas` diz quantos movimentos originais foram somados: agregar nao
        pode dar a impressao de que a fonte trazia um lancamento so. As linhas
        e a proveniencia continuam intactas em `movimento_dimp`.
        """
        return [dict(l) for l in self._conn.execute(
            "SELECT instituicao, COUNT(*) AS linhas, SUM(debito) AS debito,"
            " SUM(credito) AS credito, SUM(transferencia) AS transferencia,"
            " SUM(pix) AS pix, SUM(voucher) AS voucher, SUM(outras) AS outras,"
            " SUM(total_dimp) AS total_dimp,"
            " SUM(total_nao_pix) AS total_nao_pix"
            " FROM movimento_dimp WHERE versao_id=?"
            " GROUP BY instituicao ORDER BY instituicao", (versao_id,))]

    def obter_fonte(self, fonte_id: int) -> dict:
        linha = self._conn.execute(
            "SELECT * FROM fonte_fiscal WHERE id=?", (fonte_id,)).fetchone()
        if linha is None:
            raise LookupError("Fonte nao encontrada.")
        return dict(linha)

    def listar_excecoes(self, *, estado: str = "aberta", severidade: str = "",
                        cnpj: str = "", pagina: int = 1,
                        limite: int = 50) -> dict:
        """Fila de excecoes, ja localizando a competencia de cada uma."""
        onde = ["e.versao_id = c.versao_vigente_id"]
        valores: list = []
        if estado:
            if estado not in ("aberta", "resolvida"):
                raise ValueError("Estado de excecao desconhecido: " + estado)
            onde.append("e.estado = ?")
            valores.append(estado)
        if severidade:
            if severidade not in ("aviso", "bloqueio"):
                raise ValueError("Severidade desconhecida: " + severidade)
            onde.append("e.severidade = ?")
            valores.append(severidade)
        digitos = "".join(c for c in str(cnpj or "") if c.isdigit())
        if digitos:
            onde.append("c.cnpj = ?")
            valores.append(digitos)

        de_para = (" FROM excecao_conciliacao e"
                   " JOIN conciliacao c ON c.id = e.conciliacao_id")
        clausula = " WHERE " + " AND ".join(onde)
        limite = max(1, min(int(limite or 50), 200))
        pagina = max(1, int(pagina or 1))
        total = int(self._conn.execute(
            "SELECT COUNT(*) AS n" + de_para + clausula,
            valores).fetchone()["n"])
        paginas = max(1, -(-total // limite))
        pagina = min(pagina, paginas)
        linhas = self._conn.execute(
            "SELECT e.*, c.cnpj, c.competencia, c.razao_social"
            + de_para + clausula
            + " ORDER BY e.severidade DESC, e.id DESC LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite]).fetchall()
        return {"itens": [dict(l) for l in linhas], "total": total,
                "pagina": pagina, "limite": limite, "paginas": paginas}
