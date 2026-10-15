"""Persistencia da Emissao de NFS-e: SQLite dedicado e trilha append-only.

Banco proprio (`dados_web/nfse.db`) pelo mesmo motivo dos outros dominios
fiscais: ciclo de vida, trilha e backup proprios. Ele guarda dados pessoais
(nomes de criancas, CPFs de responsaveis) e por isso nunca vai para o Git.

Sem FastAPI e sem sessao HTTP: caminho e identidade chegam por injecao, e a
identidade chega como SNAPSHOT primitivo (`usuario_id`, `usuario_login`).

Garantias que moram no SQL, nao so no Python (data-model.md):

- **Imutabilidade**: versoes de perfil, origens, linhas, correcoes, rodadas de
  conferencia, apontamentos, DPS e eventos recusam UPDATE e DELETE.
- **Duplicata**: indice unico parcial em `chave_aprovada` impede que duas
  aprovacoes simultaneas reservem a mesma nota.
- **Numeracao**: `numeracao_dps` so cresce e `dps` tem numero unico por
  perfil, ambiente e serie. Numero reservado nunca volta.
- **Aprovacao tudo ou nada**: chaves, numeros, DPS, estado do lote e eventos
  na mesma transacao `BEGIN IMMEDIATE`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict

from ..core import nfse as nf
from ..core import nfse_conferencia as nc
from ..core import nfse_dps as nd
from ..core import nfse_entrada as ne

VERSAO_SCHEMA = 1

PERFIL_NAO_ENCONTRADO = "PERFIL_NAO_ENCONTRADO"
PERFIL_DUPLICADO = "PERFIL_DUPLICADO"
CNPJ_DIFERENTE = "CNPJ_DIFERENTE"
LOTE_NAO_ENCONTRADO = "LOTE_NAO_ENCONTRADO"
LINHA_NAO_ENCONTRADA = "LINHA_NAO_ENCONTRADA"
DPS_NAO_ENCONTRADA = "DPS_NAO_ENCONTRADA"
ESTADO_INVALIDO = "ESTADO_INVALIDO"
CAMPO_NAO_CORRIGIVEL = "CAMPO_NAO_CORRIGIVEL"
MOTIVO_OBRIGATORIO = "MOTIVO_OBRIGATORIO"
VALOR_IGUAL = "VALOR_IGUAL"
PERFIL_DESATUALIZADO = "PERFIL_DESATUALIZADO"
LOTE_VAZIO = "LOTE_VAZIO"
LOTE_COM_BLOQUEIO = "LOTE_COM_BLOQUEIO"

EM_REVISAO = "em_revisao"
APROVADO = "aprovado"
DESCARTADO = "descartado"

CAMPOS_CORRIGIVEIS = ne.CAMPOS + ("excluida",)
MAX_MOTIVO = 500


class ConcorrenciaError(Exception):
    """O lote mudou desde que o cliente o leu."""

    def __init__(self, revision_atual: int):
        super().__init__("Lote desatualizado.")
        self.revision_atual = revision_atual


def agora_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


_TABELAS = """
CREATE TABLE IF NOT EXISTS perfil (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cnpj TEXT NOT NULL UNIQUE,
  criado_em TEXT NOT NULL,
  criado_por_id INTEGER NOT NULL DEFAULT 0,
  criado_por_login TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS perfil_versao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  perfil_id INTEGER NOT NULL REFERENCES perfil(id),
  versao INTEGER NOT NULL,
  razao_social TEXT NOT NULL,
  inscricao_municipal TEXT,
  informar_im INTEGER,
  municipio_ibge TEXT NOT NULL,
  municipio_prestacao_ibge TEXT NOT NULL,
  emissor TEXT NOT NULL CHECK (emissor = 'nacional'),
  op_simp_nac INTEGER NOT NULL CHECK (op_simp_nac = 3),
  reg_ap_trib_sn INTEGER,
  reg_esp_trib INTEGER,
  iss_retido INTEGER NOT NULL,
  convenio_incidencia_ativo INTEGER,
  aliquota_centesimos INTEGER,
  tributos_aprox TEXT,
  p_tot_trib_sn INTEGER,
  p_tot_trib_fed INTEGER,
  p_tot_trib_est INTEGER,
  p_tot_trib_mun INTEGER,
  endereco_tomador TEXT,
  serie_dps TEXT NOT NULL,
  ambiente INTEGER NOT NULL CHECK (ambiente = 2),
  modelo_discriminacao TEXT NOT NULL,
  motivo TEXT NOT NULL DEFAULT '',
  criado_em TEXT NOT NULL,
  criado_por_id INTEGER NOT NULL DEFAULT 0,
  criado_por_login TEXT NOT NULL,
  UNIQUE (perfil_id, versao)
);

CREATE TABLE IF NOT EXISTS perfil_turma (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  perfil_versao_id INTEGER NOT NULL REFERENCES perfil_versao(id),
  ordem INTEGER NOT NULL,
  nome TEXT NOT NULL,
  nome_normalizado TEXT NOT NULL,
  categoria TEXT,
  c_trib_nac TEXT,
  c_nbs TEXT,
  c_ind_op TEXT,
  c_class_trib TEXT,
  ref_cnae TEXT,
  ref_item_lista TEXT,
  ref_ctiss TEXT,
  UNIQUE (perfil_versao_id, nome_normalizado)
);

CREATE TABLE IF NOT EXISTS perfil_turma_apelido (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turma_id INTEGER NOT NULL REFERENCES perfil_turma(id),
  apelido TEXT NOT NULL,
  apelido_normalizado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS origem (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL CHECK (tipo IN ('planilha', 'texto')),
  sha256 TEXT NOT NULL UNIQUE,
  nome_arquivo TEXT,
  tamanho_bytes INTEGER NOT NULL,
  arquivo_relativo TEXT,
  texto TEXT,
  importado_em TEXT NOT NULL,
  importado_por_id INTEGER NOT NULL DEFAULT 0,
  importado_por_login TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lote (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  perfil_id INTEGER NOT NULL REFERENCES perfil(id),
  origem_id INTEGER NOT NULL REFERENCES origem(id),
  conferencia_atual_id INTEGER,
  estado TEXT NOT NULL CHECK (estado IN ('em_revisao', 'aprovado', 'descartado')),
  revision INTEGER NOT NULL DEFAULT 1,
  avisos_importacao TEXT NOT NULL DEFAULT '[]',
  linhas_ignoradas INTEGER NOT NULL DEFAULT 0,
  criado_em TEXT NOT NULL,
  criado_por_id INTEGER NOT NULL DEFAULT 0,
  criado_por_login TEXT NOT NULL,
  aprovado_em TEXT,
  aprovado_por_id INTEGER,
  aprovado_por_login TEXT,
  hash_aprovacao TEXT,
  descartado_em TEXT,
  descartado_por_id INTEGER,
  descartado_por_login TEXT,
  motivo_descarte TEXT
);

CREATE TABLE IF NOT EXISTS linha (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lote_id INTEGER NOT NULL REFERENCES lote(id),
  ordem INTEGER NOT NULL,
  aba TEXT,
  linha_planilha INTEGER,
  bloco INTEGER,
  texto_linha_ini INTEGER,
  texto_linha_fim INTEGER,
  responsavel_nome TEXT,
  responsavel_cpf TEXT,
  responsavel_celular TEXT,
  responsavel_email TEXT,
  endereco_texto TEXT,
  cep TEXT,
  logradouro TEXT,
  numero TEXT,
  complemento TEXT,
  bairro TEXT,
  municipio TEXT,
  uf TEXT,
  municipio_ibge TEXT,
  aluno_nome TEXT,
  turma TEXT,
  competencia TEXT,
  valor TEXT,
  nao_reconhecido TEXT NOT NULL DEFAULT '[]',
  rotulos_repetidos TEXT NOT NULL DEFAULT '[]',
  proveniencia TEXT NOT NULL DEFAULT '{}',
  UNIQUE (lote_id, ordem)
);

CREATE TABLE IF NOT EXISTS correcao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  linha_id INTEGER NOT NULL REFERENCES linha(id),
  campo TEXT NOT NULL,
  valor_anterior TEXT,
  valor_novo TEXT,
  motivo TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  criada_por_id INTEGER NOT NULL DEFAULT 0,
  criada_por_login TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conferencia (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lote_id INTEGER NOT NULL REFERENCES lote(id),
  perfil_versao_id INTEGER NOT NULL REFERENCES perfil_versao(id),
  versao_regras TEXT NOT NULL,
  motivo TEXT NOT NULL,
  hoje TEXT NOT NULL,
  competencia_predominante TEXT,
  executada_em TEXT NOT NULL,
  executada_por_id INTEGER NOT NULL DEFAULT 0,
  executada_por_login TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conferencia_linha (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conferencia_id INTEGER NOT NULL REFERENCES conferencia(id),
  linha_id INTEGER NOT NULL REFERENCES linha(id),
  excluida INTEGER NOT NULL DEFAULT 0,
  cpf TEXT,
  competencia TEXT,
  valor_centavos INTEGER,
  turma_id INTEGER REFERENCES perfil_turma(id),
  responsavel TEXT,
  aluno TEXT,
  endereco TEXT,
  chave_duplicata TEXT,
  discriminacao TEXT,
  situacao TEXT NOT NULL,
  UNIQUE (conferencia_id, linha_id)
);

CREATE TABLE IF NOT EXISTS apontamento (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conferencia_linha_id INTEGER NOT NULL REFERENCES conferencia_linha(id),
  codigo TEXT NOT NULL,
  nivel TEXT NOT NULL CHECK (nivel IN ('aviso', 'bloqueio')),
  campo TEXT,
  mensagem TEXT NOT NULL,
  referencia TEXT
);

CREATE TABLE IF NOT EXISTS chave_aprovada (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  perfil_id INTEGER NOT NULL REFERENCES perfil(id),
  chave TEXT NOT NULL,
  lote_id INTEGER NOT NULL REFERENCES lote(id),
  linha_id INTEGER NOT NULL REFERENCES linha(id),
  reservada_em TEXT NOT NULL,
  liberada_em TEXT
);

CREATE TABLE IF NOT EXISTS numeracao_dps (
  perfil_id INTEGER NOT NULL REFERENCES perfil(id),
  ambiente INTEGER NOT NULL,
  serie TEXT NOT NULL,
  ultimo_numero INTEGER NOT NULL,
  PRIMARY KEY (perfil_id, ambiente, serie)
);

CREATE TABLE IF NOT EXISTS dps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lote_id INTEGER NOT NULL REFERENCES lote(id),
  linha_id INTEGER NOT NULL UNIQUE REFERENCES linha(id),
  conferencia_linha_id INTEGER NOT NULL REFERENCES conferencia_linha(id),
  perfil_id INTEGER NOT NULL REFERENCES perfil(id),
  perfil_versao_id INTEGER NOT NULL REFERENCES perfil_versao(id),
  ambiente INTEGER NOT NULL,
  serie TEXT NOT NULL,
  numero INTEGER NOT NULL,
  id_dps TEXT NOT NULL UNIQUE,
  dh_emi TEXT NOT NULL,
  d_compet TEXT NOT NULL,
  versao_leiaute TEXT NOT NULL,
  versao_gerador TEXT NOT NULL,
  xml BLOB NOT NULL,
  sha256 TEXT NOT NULL,
  gerada_em TEXT NOT NULL,
  gerada_por_id INTEGER NOT NULL DEFAULT 0,
  gerada_por_login TEXT NOT NULL,
  UNIQUE (perfil_id, ambiente, serie, numero)
);

CREATE TABLE IF NOT EXISTS evento (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL,
  perfil_id INTEGER,
  lote_id INTEGER,
  linha_id INTEGER,
  dps_id INTEGER,
  detalhe TEXT NOT NULL DEFAULT '{}',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  criado_em TEXT NOT NULL
);
"""

_INDICES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_lote_origem_vivo
  ON lote(perfil_id, origem_id) WHERE estado <> 'descartado';
CREATE INDEX IF NOT EXISTS idx_lote_perfil ON lote(perfil_id, estado, criado_em);
CREATE INDEX IF NOT EXISTS idx_correcao_linha ON correcao(linha_id, campo, id);
CREATE INDEX IF NOT EXISTS idx_conferencia_lote ON conferencia(lote_id, id);
CREATE INDEX IF NOT EXISTS idx_apontamento_cl ON apontamento(conferencia_linha_id);
CREATE INDEX IF NOT EXISTS idx_turma_apelido ON perfil_turma_apelido(turma_id);

-- A mesma nota (CPF + aluno + competencia) nao e' aprovada duas vezes, nem
-- por duas aprovacoes simultaneas: a garantia e' do banco.
CREATE UNIQUE INDEX IF NOT EXISTS idx_chave_viva
  ON chave_aprovada(perfil_id, chave) WHERE liberada_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_chave_lote ON chave_aprovada(lote_id);

CREATE INDEX IF NOT EXISTS idx_dps_lote ON dps(lote_id);
CREATE INDEX IF NOT EXISTS idx_evento_lote ON evento(lote_id, id);
CREATE INDEX IF NOT EXISTS idx_evento_perfil ON evento(perfil_id, id);
"""


def _imutavel(tabela: str, nome: str) -> str:
    return f"""
CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_update
BEFORE UPDATE ON {tabela} BEGIN
  SELECT RAISE(ABORT, '{nome} e imutavel: UPDATE nao e permitido.');
END;
CREATE TRIGGER IF NOT EXISTS trg_{tabela}_sem_delete
BEFORE DELETE ON {tabela} BEGIN
  SELECT RAISE(ABORT, '{nome} e imutavel: DELETE nao e permitido.');
END;
"""


_TRIGGERS = "".join(_imutavel(t, n) for t, n in (
    ("perfil_versao", "Versao de perfil"), ("perfil_turma", "Turma do perfil"),
    ("perfil_turma_apelido", "Apelido de turma"), ("origem", "Origem"),
    ("linha", "Linha bruta"), ("correcao", "Correcao"),
    ("conferencia", "Rodada de conferencia"),
    ("conferencia_linha", "Linha conferida"), ("apontamento", "Apontamento"),
    ("dps", "DPS"), ("evento", "Evento"),
)) + """
CREATE TRIGGER IF NOT EXISTS trg_perfil_cnpj_imutavel
BEFORE UPDATE ON perfil BEGIN
  SELECT RAISE(ABORT, 'O CNPJ do perfil e imutavel.');
END;
CREATE TRIGGER IF NOT EXISTS trg_perfil_sem_delete
BEFORE DELETE ON perfil BEGIN
  SELECT RAISE(ABORT, 'Perfil nao e excluido.');
END;

CREATE TRIGGER IF NOT EXISTS trg_lote_sem_delete
BEFORE DELETE ON lote BEGIN
  SELECT RAISE(ABORT, 'Lote nao e excluido: descarte com motivo.');
END;
CREATE TRIGGER IF NOT EXISTS trg_lote_descartado_terminal
BEFORE UPDATE ON lote WHEN OLD.estado = 'descartado' BEGIN
  SELECT RAISE(ABORT, 'Lote descartado e terminal.');
END;
CREATE TRIGGER IF NOT EXISTS trg_lote_aprovado_congelado
BEFORE UPDATE ON lote WHEN OLD.estado = 'aprovado' AND NEW.estado <> 'descartado'
BEGIN
  SELECT RAISE(ABORT, 'Lote aprovado nao muda; so pode ser descartado.');
END;

CREATE TRIGGER IF NOT EXISTS trg_chave_sem_delete
BEFORE DELETE ON chave_aprovada BEGIN
  SELECT RAISE(ABORT, 'Reserva de nota nao e excluida; e liberada.');
END;
CREATE TRIGGER IF NOT EXISTS trg_chave_so_libera
BEFORE UPDATE ON chave_aprovada
WHEN OLD.liberada_em IS NOT NULL OR NEW.liberada_em IS NULL
     OR NEW.chave IS NOT OLD.chave OR NEW.perfil_id IS NOT OLD.perfil_id
     OR NEW.lote_id IS NOT OLD.lote_id OR NEW.linha_id IS NOT OLD.linha_id
BEGIN
  SELECT RAISE(ABORT, 'Reserva de nota: so e permitido liberar uma vez.');
END;

CREATE TRIGGER IF NOT EXISTS trg_numeracao_so_cresce
BEFORE UPDATE ON numeracao_dps WHEN NEW.ultimo_numero <= OLD.ultimo_numero BEGIN
  SELECT RAISE(ABORT, 'Numero de DPS nunca volta.');
END;
CREATE TRIGGER IF NOT EXISTS trg_numeracao_sem_delete
BEFORE DELETE ON numeracao_dps BEGIN
  SELECT RAISE(ABORT, 'Numero de DPS nunca volta.');
END;
"""

_CONTAVEIS = {"perfil", "perfil_versao", "perfil_turma", "origem", "lote", "linha",
              "correcao", "conferencia", "conferencia_linha", "apontamento",
              "chave_aprovada", "numeracao_dps", "dps", "evento"}

_COLUNAS_VERSAO = (
    "razao_social", "inscricao_municipal", "informar_im", "municipio_ibge",
    "municipio_prestacao_ibge", "emissor", "op_simp_nac", "reg_ap_trib_sn",
    "reg_esp_trib", "iss_retido", "convenio_incidencia_ativo",
    "aliquota_centesimos", "tributos_aprox", "p_tot_trib_sn", "p_tot_trib_fed",
    "p_tot_trib_est", "p_tot_trib_mun", "endereco_tomador", "serie_dps",
    "ambiente", "modelo_discriminacao")
_BOOLEANOS = ("informar_im", "iss_retido", "convenio_incidencia_ativo")


class NfseStore:
    """Uma instancia por thread: conexao SQLite nao atravessa thread."""

    def __init__(self, db_path: str, pasta_origens: str):
        self.db_path = db_path
        self.pasta_origens = pasta_origens
        pasta = os.path.dirname(os.path.abspath(db_path))
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        os.makedirs(pasta_origens, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._migrar()

    def _migrar(self) -> None:
        conn = self._conn
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.executescript(_TABELAS)
        conn.executescript(_INDICES)
        conn.executescript(_TRIGGERS)
        conn.execute(f"PRAGMA user_version={VERSAO_SCHEMA}")

    def fechar(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def contar(self, tabela: str) -> int:
        if tabela not in _CONTAVEIS:
            raise ValueError(f"Tabela desconhecida: {tabela}")
        return self._conn.execute(f"SELECT COUNT(*) AS n FROM {tabela}").fetchone()["n"]

    # ------------------------------------------------------------------
    # Transacao e trilha

    def _transacao(self):
        conn = self._conn

        class _Ctx:
            def __enter__(self_inner):
                conn.execute("BEGIN IMMEDIATE")
                return conn

            def __exit__(self_inner, tipo, valor, rastro):
                if tipo is None:
                    conn.execute("COMMIT")
                else:
                    conn.execute("ROLLBACK")
                return False

        return _Ctx()

    @staticmethod
    def _evento(conn, tipo: str, *, usuario_id: int, usuario_login: str,
                perfil_id=None, lote_id=None, linha_id=None, dps_id=None,
                detalhe: dict | None = None) -> None:
        conn.execute(
            "INSERT INTO evento(tipo, perfil_id, lote_id, linha_id, dps_id, detalhe,"
            " usuario_id, usuario_login, criado_em) VALUES(?,?,?,?,?,?,?,?,?)",
            (tipo, perfil_id, lote_id, linha_id, dps_id, _json(detalhe or {}),
             usuario_id, usuario_login, agora_iso()))

    # ------------------------------------------------------------------
    # Perfis

    def criar_perfil(self, dados: dict, *, usuario_id: int, usuario_login: str,
                     motivo: str = "") -> dict:
        perfil = nf.validar_perfil(dados)
        with self._transacao() as conn:
            if conn.execute("SELECT 1 FROM perfil WHERE cnpj=?",
                            (perfil.cnpj,)).fetchone():
                raise nf.ErroNfse(PERFIL_DUPLICADO,
                                  "Já existe um perfil para este CNPJ; crie uma "
                                  "versão nova dele.")
            cur = conn.execute(
                "INSERT INTO perfil(cnpj, criado_em, criado_por_id, criado_por_login)"
                " VALUES(?,?,?,?)", (perfil.cnpj, agora_iso(), usuario_id, usuario_login))
            perfil_id = int(cur.lastrowid)
            versao_id = self._inserir_versao(conn, perfil_id, 1, perfil, motivo,
                                             usuario_id, usuario_login)
            self._evento(conn, "perfil_criado", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=perfil_id,
                         detalhe={"versao": 1})
        return {"perfil_id": perfil_id, "versao_id": versao_id, "versao": 1}

    def criar_versao(self, perfil_id: int, dados: dict, *, usuario_id: int,
                     usuario_login: str, motivo: str = "") -> dict:
        perfil = nf.validar_perfil(dados)
        with self._transacao() as conn:
            linha = conn.execute("SELECT cnpj FROM perfil WHERE id=?",
                                 (perfil_id,)).fetchone()
            if linha is None:
                raise nf.ErroNfse(PERFIL_NAO_ENCONTRADO, "Perfil não encontrado.")
            if linha["cnpj"] != perfil.cnpj:
                raise nf.ErroNfse(CNPJ_DIFERENTE,
                                  "O CNPJ de um perfil não muda; cadastre outro perfil.")
            versao = int(conn.execute(
                "SELECT COALESCE(MAX(versao), 0) + 1 AS v FROM perfil_versao"
                " WHERE perfil_id=?", (perfil_id,)).fetchone()["v"])
            versao_id = self._inserir_versao(conn, perfil_id, versao, perfil, motivo,
                                             usuario_id, usuario_login)
            self._evento(conn, "perfil_versionado", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=perfil_id,
                         detalhe={"versao": versao})
        return {"perfil_id": perfil_id, "versao_id": versao_id, "versao": versao}

    @staticmethod
    def _inserir_versao(conn, perfil_id, versao, perfil: nf.PerfilVersao, motivo,
                        usuario_id, usuario_login) -> int:
        valores = []
        for coluna in _COLUNAS_VERSAO:
            valor = getattr(perfil, coluna)
            if coluna in _BOOLEANOS and valor is not None:
                valor = int(valor)
            valores.append(valor)
        cur = conn.execute(
            f"INSERT INTO perfil_versao(perfil_id, versao, {', '.join(_COLUNAS_VERSAO)},"
            " motivo, criado_em, criado_por_id, criado_por_login)"
            f" VALUES(?,?,{','.join('?' * len(_COLUNAS_VERSAO))},?,?,?,?)",
            (perfil_id, versao, *valores, (motivo or "").strip()[:MAX_MOTIVO],
             agora_iso(), usuario_id, usuario_login))
        versao_id = int(cur.lastrowid)
        for ordem, turma in enumerate(perfil.turmas, start=1):
            cur = conn.execute(
                "INSERT INTO perfil_turma(perfil_versao_id, ordem, nome,"
                " nome_normalizado, categoria, c_trib_nac, c_nbs, c_ind_op,"
                " c_class_trib, ref_cnae, ref_item_lista, ref_ctiss)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (versao_id, ordem, turma.nome, nf.chave_comparacao(turma.nome),
                 turma.categoria, turma.c_trib_nac, turma.c_nbs, turma.c_ind_op,
                 turma.c_class_trib, turma.ref_cnae, turma.ref_item_lista,
                 turma.ref_ctiss))
            for apelido in turma.apelidos:
                conn.execute(
                    "INSERT INTO perfil_turma_apelido(turma_id, apelido,"
                    " apelido_normalizado) VALUES(?,?,?)",
                    (cur.lastrowid, apelido, nf.chave_comparacao(apelido)))
        return versao_id

    def _turmas_da_versao(self, versao_id: int) -> list[tuple[int, nf.Turma]]:
        turmas = []
        for t in self._conn.execute(
                "SELECT * FROM perfil_turma WHERE perfil_versao_id=? ORDER BY ordem",
                (versao_id,)):
            apelidos = tuple(a["apelido"] for a in self._conn.execute(
                "SELECT apelido FROM perfil_turma_apelido WHERE turma_id=? ORDER BY id",
                (t["id"],)))
            turmas.append((t["id"], nf.Turma(
                nome=t["nome"], apelidos=apelidos, categoria=t["categoria"],
                c_trib_nac=t["c_trib_nac"], c_nbs=t["c_nbs"], c_ind_op=t["c_ind_op"],
                c_class_trib=t["c_class_trib"], ref_cnae=t["ref_cnae"],
                ref_item_lista=t["ref_item_lista"], ref_ctiss=t["ref_ctiss"])))
        return turmas

    def carregar_versao(self, versao_id: int) -> nf.PerfilVersao:
        v = self._conn.execute(
            "SELECT pv.*, p.cnpj FROM perfil_versao pv JOIN perfil p ON p.id=pv.perfil_id"
            " WHERE pv.id=?", (versao_id,)).fetchone()
        if v is None:
            raise nf.ErroNfse(PERFIL_NAO_ENCONTRADO, "Versão de perfil não encontrada.")
        campos = {}
        for coluna in _COLUNAS_VERSAO:
            valor = v[coluna]
            if coluna in _BOOLEANOS and valor is not None:
                valor = bool(valor)
            campos[coluna] = valor
        return nf.PerfilVersao(cnpj=v["cnpj"], turmas=tuple(
            t for _, t in self._turmas_da_versao(versao_id)), **campos)

    def versao_atual(self, perfil_id: int) -> tuple[int, int]:
        """(versao_id, numero da versao) da versao vigente."""
        v = self._conn.execute(
            "SELECT id, versao FROM perfil_versao WHERE perfil_id=?"
            " ORDER BY versao DESC LIMIT 1", (perfil_id,)).fetchone()
        if v is None:
            raise nf.ErroNfse(PERFIL_NAO_ENCONTRADO, "Perfil não encontrado.")
        return int(v["id"]), int(v["versao"])

    def _versao_dict(self, versao_id: int) -> dict:
        p = self.carregar_versao(versao_id)
        dados = asdict(p)
        dados["turmas"] = [dict(asdict(t), apelidos=list(t.apelidos),
                                pendente=nf.turma_pendente(t)) for t in p.turmas]
        dados["regra_aliquota"] = nf.regra_aliquota(p)
        return dados

    def perfil(self, perfil_id: int) -> dict:
        p = self._conn.execute("SELECT * FROM perfil WHERE id=?", (perfil_id,)).fetchone()
        if p is None:
            raise nf.ErroNfse(PERFIL_NAO_ENCONTRADO, "Perfil não encontrado.")
        versao_id, numero = self.versao_atual(perfil_id)
        versoes = [dict(v) for v in self._conn.execute(
            "SELECT id, versao, motivo, criado_em, criado_por_login FROM perfil_versao"
            " WHERE perfil_id=? ORDER BY versao", (perfil_id,))]
        atual = self.carregar_versao(versao_id)
        return {"perfil_id": perfil_id, "cnpj": p["cnpj"], "versao_id": versao_id,
                "versao": numero, "atual": self._versao_dict(versao_id),
                "versoes": versoes,
                "pendencias": [asdict(x) for x in nf.pendencias_do_perfil(atual)]}

    def listar_perfis(self) -> list[dict]:
        saida = []
        for p in self._conn.execute("SELECT id, cnpj FROM perfil ORDER BY id"):
            versao_id, numero = self.versao_atual(p["id"])
            atual = self.carregar_versao(versao_id)
            saida.append({"perfil_id": p["id"], "cnpj": p["cnpj"],
                          "razao_social": atual.razao_social, "versao": numero,
                          "pendencias": len(nf.pendencias_do_perfil(atual))})
        return saida

    # ------------------------------------------------------------------
    # Importacao

    def importar_planilha(self, perfil_id: int, caminho: str, nome_arquivo: str, *,
                          hoje: dt.date, usuario_id: int, usuario_login: str) -> dict:
        self.versao_atual(perfil_id)
        with open(caminho, "rb") as arq:
            conteudo = arq.read()
        sha = hashlib.sha256(conteudo).hexdigest()
        existente = self._lote_vivo(perfil_id, sha)
        if existente is not None:
            return self._reaproveitado(perfil_id, existente, usuario_id, usuario_login)
        resultado = ne.ler_planilha(caminho)
        relativo = f"origens/{sha}.xlsx"
        destino = os.path.join(self.pasta_origens, f"{sha}.xlsx")
        if not os.path.isfile(destino):
            # Gravado pelo hash ANTES do COMMIT: se a transacao falhar, sobra no
            # maximo um arquivo identico ao da proxima tentativa.
            fd, parcial = tempfile.mkstemp(dir=self.pasta_origens, suffix=".parcial")
            with os.fdopen(fd, "wb") as saida:
                saida.write(conteudo)
            os.replace(parcial, destino)
        origem = {"tipo": "planilha", "sha256": sha,
                  "nome_arquivo": os.path.basename(nome_arquivo or "")[:200] or None,
                  "tamanho_bytes": len(conteudo), "arquivo_relativo": relativo,
                  "texto": None}
        return self._importar(perfil_id, origem, resultado, hoje, usuario_id,
                              usuario_login)

    def importar_texto(self, perfil_id: int, texto: str, *, hoje: dt.date,
                       usuario_id: int, usuario_login: str) -> dict:
        versao_id, _ = self.versao_atual(perfil_id)
        bruto = texto or ""
        sha = hashlib.sha256(bruto.encode("utf-8")).hexdigest()
        existente = self._lote_vivo(perfil_id, sha)
        if existente is not None:
            return self._reaproveitado(perfil_id, existente, usuario_id, usuario_login)
        turmas = self.carregar_versao(versao_id).turmas
        resultado = ne.ler_texto(bruto, turmas)
        origem = {"tipo": "texto", "sha256": sha, "nome_arquivo": None,
                  "tamanho_bytes": len(bruto.encode("utf-8")),
                  "arquivo_relativo": None, "texto": bruto}
        return self._importar(perfil_id, origem, resultado, hoje, usuario_id,
                              usuario_login)

    def _lote_vivo(self, perfil_id: int, sha: str) -> int | None:
        achado = self._conn.execute(
            "SELECT l.id FROM lote l JOIN origem o ON o.id=l.origem_id"
            " WHERE l.perfil_id=? AND o.sha256=? AND l.estado <> 'descartado'",
            (perfil_id, sha)).fetchone()
        return int(achado["id"]) if achado else None

    def _reaproveitado(self, perfil_id, lote_id, usuario_id, usuario_login) -> dict:
        with self._transacao() as conn:
            self._evento(conn, "origem_reaproveitada", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=perfil_id,
                         lote_id=lote_id)
        return {"lote_id": lote_id, "reaproveitado": True}

    def _importar(self, perfil_id, origem: dict, resultado: ne.ResultadoEntrada,
                  hoje, usuario_id, usuario_login) -> dict:
        with self._transacao() as conn:
            achada = conn.execute("SELECT id FROM origem WHERE sha256=?",
                                  (origem["sha256"],)).fetchone()
            if achada:
                origem_id = int(achada["id"])
            else:
                origem_id = int(conn.execute(
                    "INSERT INTO origem(tipo, sha256, nome_arquivo, tamanho_bytes,"
                    " arquivo_relativo, texto, importado_em, importado_por_id,"
                    " importado_por_login) VALUES(?,?,?,?,?,?,?,?,?)",
                    (origem["tipo"], origem["sha256"], origem["nome_arquivo"],
                     origem["tamanho_bytes"], origem["arquivo_relativo"],
                     origem["texto"], agora_iso(), usuario_id,
                     usuario_login)).lastrowid)
            lote_id = int(conn.execute(
                "INSERT INTO lote(perfil_id, origem_id, estado, revision,"
                " avisos_importacao, linhas_ignoradas, criado_em, criado_por_id,"
                " criado_por_login) VALUES(?,?,?,?,?,?,?,?,?)",
                (perfil_id, origem_id, EM_REVISAO, 1, _json(resultado.avisos),
                 resultado.ignoradas, agora_iso(), usuario_id,
                 usuario_login)).lastrowid)
            for bruta in resultado.linhas:
                prov = dict(bruta.proveniencia)
                for campo, tipo in bruta.tipos.items():
                    prov.setdefault(campo, {})["tipo_celula"] = tipo
                colunas = list(ne.CAMPOS)
                conn.execute(
                    "INSERT INTO linha(lote_id, ordem, aba, linha_planilha, bloco,"
                    " texto_linha_ini, texto_linha_fim, nao_reconhecido,"
                    f" rotulos_repetidos, proveniencia, {', '.join(colunas)})"
                    f" VALUES(?,?,?,?,?,?,?,?,?,?,{','.join('?' * len(colunas))})",
                    (lote_id, bruta.ordem, bruta.aba, bruta.linha_planilha, bruta.bloco,
                     bruta.texto_linha_ini, bruta.texto_linha_fim,
                     _json(list(bruta.nao_reconhecido)),
                     _json(list(bruta.rotulos_repetidos)), _json(prov),
                     *[bruta.campos.get(c) for c in colunas]))
            self._conferir(conn, lote_id, perfil_id, "importacao", hoje,
                           usuario_id, usuario_login)
            self._evento(conn, "lote_importado", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=perfil_id,
                         lote_id=lote_id,
                         detalhe={"tipo": origem["tipo"], "sha256": origem["sha256"],
                                  "linhas": len(resultado.linhas),
                                  "ignoradas": resultado.ignoradas})
        return {"lote_id": lote_id, "reaproveitado": False}

    # ------------------------------------------------------------------
    # Conferencia

    @staticmethod
    def _efetivas(conn, lote_id: int) -> list[nf.LinhaEfetiva]:
        efetivas = []
        for l in conn.execute("SELECT * FROM linha WHERE lote_id=? ORDER BY ordem",
                              (lote_id,)):
            campos = {c: l[c] for c in ne.CAMPOS}
            prov = json.loads(l["proveniencia"])
            tipos = {c: info.get("tipo_celula", "texto") for c, info in prov.items()}
            excluida = False
            for c in conn.execute(
                    "SELECT campo, valor_novo FROM correcao WHERE linha_id=? ORDER BY id",
                    (l["id"],)):
                if c["campo"] == "excluida":
                    excluida = c["valor_novo"] == "1"
                else:
                    campos[c["campo"]] = c["valor_novo"]
                    tipos.pop(c["campo"], None)
            efetivas.append(nf.LinhaEfetiva(
                ref=int(l["id"]), campos=campos, tipos=tipos, excluida=excluida,
                nao_reconhecido=tuple(json.loads(l["nao_reconhecido"])),
                rotulos_repetidos=tuple(json.loads(l["rotulos_repetidos"]))))
        return efetivas

    @staticmethod
    def _chaves_aprovadas(conn, perfil_id: int, lote_id: int) -> dict[str, int]:
        return {c["chave"]: int(c["lote_id"]) for c in conn.execute(
            "SELECT chave, lote_id FROM chave_aprovada WHERE perfil_id=?"
            " AND liberada_em IS NULL AND lote_id <> ?", (perfil_id, lote_id))}

    def _conferir(self, conn, lote_id, perfil_id, motivo, hoje, usuario_id,
                  usuario_login) -> int:
        versao_id, _ = self.versao_atual(perfil_id)
        perfil = self.carregar_versao(versao_id)
        ids_turma = {t.nome: tid for tid, t in self._turmas_da_versao(versao_id)}
        efetivas = self._efetivas(conn, lote_id)
        resultado = nc.conferir(perfil, efetivas,
                                chaves_aprovadas=self._chaves_aprovadas(
                                    conn, perfil_id, lote_id),
                                hoje=hoje)
        conferencia_id = int(conn.execute(
            "INSERT INTO conferencia(lote_id, perfil_versao_id, versao_regras, motivo,"
            " hoje, competencia_predominante, executada_em, executada_por_id,"
            " executada_por_login) VALUES(?,?,?,?,?,?,?,?,?)",
            (lote_id, versao_id, nc.VERSAO_REGRAS, motivo, hoje.isoformat(),
             resultado.competencia_predominante, agora_iso(), usuario_id,
             usuario_login)).lastrowid)
        for linha in resultado.linhas:
            cl_id = int(conn.execute(
                "INSERT INTO conferencia_linha(conferencia_id, linha_id, excluida, cpf,"
                " competencia, valor_centavos, turma_id, responsavel, aluno, endereco,"
                " chave_duplicata, discriminacao, situacao)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (conferencia_id, linha.ref, int(linha.excluida), linha.cpf,
                 linha.competencia, linha.valor_centavos,
                 ids_turma.get(linha.turma.nome) if linha.turma else None,
                 linha.responsavel, linha.aluno,
                 _json(linha.endereco) if linha.endereco else None,
                 linha.chave_duplicata, linha.discriminacao,
                 linha.situacao)).lastrowid)
            for a in linha.apontamentos:
                conn.execute(
                    "INSERT INTO apontamento(conferencia_linha_id, codigo, nivel, campo,"
                    " mensagem, referencia) VALUES(?,?,?,?,?,?)",
                    (cl_id, a.codigo, a.nivel, a.campo, a.mensagem,
                     _json(a.referencia) if a.referencia else None))
        conn.execute("UPDATE lote SET conferencia_atual_id=? WHERE id=?",
                     (conferencia_id, lote_id))
        return conferencia_id

    def _lote_para_mudar(self, conn, lote_id: int, revision: int | None) -> sqlite3.Row:
        lote = conn.execute("SELECT * FROM lote WHERE id=?", (lote_id,)).fetchone()
        if lote is None:
            raise nf.ErroNfse(LOTE_NAO_ENCONTRADO, "Lote não encontrado.")
        if revision is not None and int(revision) != int(lote["revision"]):
            raise ConcorrenciaError(int(lote["revision"]))
        return lote

    def corrigir(self, lote_id: int, linha_id: int, campo: str, valor_novo,
                 motivo: str, *, revision: int, hoje: dt.date, usuario_id: int,
                 usuario_login: str) -> dict:
        if campo not in CAMPOS_CORRIGIVEIS:
            raise nf.ErroNfse(CAMPO_NAO_CORRIGIVEL, f"O campo {campo!r} não é corrigível.")
        motivo = " ".join(str(motivo or "").split())
        if not motivo:
            raise nf.ErroNfse(MOTIVO_OBRIGATORIO, "Informe o motivo da correção.")
        if campo == "excluida":
            valor_novo = "1" if str(valor_novo) in ("1", "true", "True") else "0"
        else:
            valor_novo = None if valor_novo is None or not str(valor_novo).strip() \
                else str(valor_novo)
        with self._transacao() as conn:
            lote = self._lote_para_mudar(conn, lote_id, revision)
            if lote["estado"] != EM_REVISAO:
                raise nf.ErroNfse(ESTADO_INVALIDO, "Só lote em revisão aceita correção.")
            existe = conn.execute("SELECT 1 FROM linha WHERE id=? AND lote_id=?",
                                  (linha_id, lote_id)).fetchone()
            if not existe:
                raise nf.ErroNfse(LINHA_NAO_ENCONTRADA, "Linha não encontrada no lote.")
            atual = next(e for e in self._efetivas(conn, lote_id) if e.ref == linha_id)
            anterior = ("1" if atual.excluida else "0") if campo == "excluida" \
                else atual.campos.get(campo)
            if anterior == valor_novo:
                raise nf.ErroNfse(VALOR_IGUAL, "O valor novo é igual ao atual.")
            conn.execute(
                "INSERT INTO correcao(linha_id, campo, valor_anterior, valor_novo, motivo,"
                " criada_em, criada_por_id, criada_por_login) VALUES(?,?,?,?,?,?,?,?)",
                (linha_id, campo, anterior, valor_novo, motivo[:MAX_MOTIVO], agora_iso(),
                 usuario_id, usuario_login))
            nova = int(lote["revision"]) + 1
            conn.execute("UPDATE lote SET revision=? WHERE id=?", (nova, lote_id))
            self._conferir(conn, lote_id, lote["perfil_id"], "correcao", hoje,
                           usuario_id, usuario_login)
            tipo = "linha_corrigida"
            if campo == "excluida":
                tipo = "linha_excluida" if valor_novo == "1" else "linha_reincluida"
            self._evento(conn, tipo, usuario_id=usuario_id, usuario_login=usuario_login,
                         perfil_id=lote["perfil_id"], lote_id=lote_id, linha_id=linha_id,
                         detalhe={"campo": campo, "motivo": motivo[:MAX_MOTIVO]})
        return {"lote_id": lote_id, "revision": nova}

    def reconferir(self, lote_id: int, *, revision: int, hoje: dt.date,
                   usuario_id: int, usuario_login: str) -> dict:
        with self._transacao() as conn:
            lote = self._lote_para_mudar(conn, lote_id, revision)
            if lote["estado"] != EM_REVISAO:
                raise nf.ErroNfse(ESTADO_INVALIDO, "Só lote em revisão é reconferido.")
            nova = int(lote["revision"]) + 1
            conn.execute("UPDATE lote SET revision=? WHERE id=?", (nova, lote_id))
            self._conferir(conn, lote_id, lote["perfil_id"], "reconferencia", hoje,
                           usuario_id, usuario_login)
            self._evento(conn, "lote_reconferido", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=lote["perfil_id"],
                         lote_id=lote_id)
        return {"lote_id": lote_id, "revision": nova}

    # ------------------------------------------------------------------
    # Aprovacao e descarte

    def aprovar(self, lote_id: int, *, revision: int, agora: dt.datetime,
                usuario_id: int, usuario_login: str) -> dict:
        """Aprova e gera as DPS, tudo na mesma transacao (tudo ou nada)."""
        with self._transacao() as conn:
            lote = self._lote_para_mudar(conn, lote_id, revision)
            if lote["estado"] != EM_REVISAO:
                raise nf.ErroNfse(ESTADO_INVALIDO, "Só lote em revisão pode ser aprovado.")
            perfil_id = int(lote["perfil_id"])
            rodada = conn.execute("SELECT * FROM conferencia WHERE id=?",
                                  (lote["conferencia_atual_id"],)).fetchone()
            versao_id, _ = self.versao_atual(perfil_id)
            if int(rodada["perfil_versao_id"]) != versao_id:
                raise nf.ErroNfse(PERFIL_DESATUALIZADO,
                                  "O perfil mudou depois da última conferência; "
                                  "reconfira o lote antes de aprovar.")
            perfil = self.carregar_versao(versao_id)
            pendencias = nf.pendencias_do_perfil(perfil)
            if pendencias:
                raise nf.ErroNfse(nf.PERFIL_COM_PENDENCIA,
                                  "O perfil tem pendências: " + "; ".join(
                                      f"{p.campo} ({p.origem})" for p in pendencias))
            linhas = [dict(l) for l in conn.execute(
                "SELECT * FROM conferencia_linha WHERE conferencia_id=? ORDER BY linha_id",
                (rodada["id"],))]
            ativas = [l for l in linhas if not l["excluida"]]
            if not ativas:
                raise nf.ErroNfse(LOTE_VAZIO, "Todas as linhas foram excluídas.")
            com_bloqueio = [l for l in ativas if l["situacao"] == nc.SITUACAO_BLOQUEIO]
            if com_bloqueio:
                raise nf.ErroNfse(LOTE_COM_BLOQUEIO,
                                  f"{len(com_bloqueio)} linha(s) com bloqueio.")

            reservada_em = agora_iso()
            for l in ativas:
                try:
                    conn.execute(
                        "INSERT INTO chave_aprovada(perfil_id, chave, lote_id, linha_id,"
                        " reservada_em) VALUES(?,?,?,?,?)",
                        (perfil_id, l["chave_duplicata"], lote_id, l["linha_id"],
                         reservada_em))
                except sqlite3.IntegrityError as exc:
                    raise nf.ErroNfse(nf.DUPLICATA_APROVADA,
                                      "Outra aprovação já reservou uma destas notas; "
                                      "reconfira o lote.") from exc

            turmas = {tid: t for tid, t in self._turmas_da_versao(versao_id)}
            serie = perfil.serie_dps
            atual = conn.execute(
                "SELECT ultimo_numero FROM numeracao_dps WHERE perfil_id=? AND ambiente=?"
                " AND serie=?", (perfil_id, nd.AMBIENTE_PRODUCAO_RESTRITA, serie)).fetchone()
            ultimo = int(atual["ultimo_numero"]) if atual else 0
            geradas = []
            for posicao, l in enumerate(ativas, start=1):
                nota = nd.DadosNota(
                    cpf=l["cpf"], nome=l["responsavel"],
                    endereco=json.loads(l["endereco"]) if l["endereco"] else None,
                    turma=turmas[l["turma_id"]], discriminacao=l["discriminacao"],
                    valor_centavos=l["valor_centavos"], competencia=l["competencia"])
                dps = nd.montar_dps(perfil, nota, numero=ultimo + posicao, dh_emi=agora)
                dps_id = int(conn.execute(
                    "INSERT INTO dps(lote_id, linha_id, conferencia_linha_id, perfil_id,"
                    " perfil_versao_id, ambiente, serie, numero, id_dps, dh_emi, d_compet,"
                    " versao_leiaute, versao_gerador, xml, sha256, gerada_em,"
                    " gerada_por_id, gerada_por_login)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (lote_id, l["linha_id"], l["id"], perfil_id, versao_id,
                     nd.AMBIENTE_PRODUCAO_RESTRITA, dps.serie, dps.numero, dps.id_dps,
                     dps.dh_emi, dps.d_compet, dps.versao_leiaute, dps.versao_gerador,
                     dps.xml, dps.sha256, agora_iso(), usuario_id,
                     usuario_login)).lastrowid)
                geradas.append((dps_id, dps))
            novo_ultimo = ultimo + len(ativas)
            if atual:
                conn.execute(
                    "UPDATE numeracao_dps SET ultimo_numero=? WHERE perfil_id=? AND"
                    " ambiente=? AND serie=?",
                    (novo_ultimo, perfil_id, nd.AMBIENTE_PRODUCAO_RESTRITA, serie))
            else:
                conn.execute(
                    "INSERT INTO numeracao_dps(perfil_id, ambiente, serie, ultimo_numero)"
                    " VALUES(?,?,?,?)",
                    (perfil_id, nd.AMBIENTE_PRODUCAO_RESTRITA, serie, novo_ultimo))

            conteudo = {"conferencia_id": int(rodada["id"]), "perfil_versao_id": versao_id,
                        "linhas": [{k: l[k] for k in (
                            "linha_id", "cpf", "competencia", "valor_centavos",
                            "turma_id", "responsavel", "aluno", "endereco",
                            "discriminacao")} for l in ativas]}
            hash_aprovacao = hashlib.sha256(_json(conteudo).encode("utf-8")).hexdigest()
            nova = int(lote["revision"]) + 1
            conn.execute(
                "UPDATE lote SET estado=?, revision=?, aprovado_em=?, aprovado_por_id=?,"
                " aprovado_por_login=?, hash_aprovacao=? WHERE id=?",
                (APROVADO, nova, agora_iso(), usuario_id, usuario_login,
                 hash_aprovacao, lote_id))
            self._evento(conn, "lote_aprovado", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=perfil_id,
                         lote_id=lote_id,
                         detalhe={"hash": hash_aprovacao, "dps": len(geradas),
                                  "conferencia_id": int(rodada["id"])})
            for dps_id, dps in geradas:
                self._evento(conn, "dps_gerada", usuario_id=usuario_id,
                             usuario_login=usuario_login, perfil_id=perfil_id,
                             lote_id=lote_id, dps_id=dps_id,
                             detalhe={"id_dps": dps.id_dps, "numero": dps.numero,
                                      "sha256": dps.sha256})
        return {"lote_id": lote_id, "revision": nova, "dps": len(geradas),
                "hash_aprovacao": hash_aprovacao}

    def descartar(self, lote_id: int, *, revision: int, motivo: str, usuario_id: int,
                  usuario_login: str) -> dict:
        motivo = " ".join(str(motivo or "").split())
        if not motivo:
            raise nf.ErroNfse(MOTIVO_OBRIGATORIO, "Informe o motivo do descarte.")
        with self._transacao() as conn:
            lote = self._lote_para_mudar(conn, lote_id, revision)
            if lote["estado"] == DESCARTADO:
                raise nf.ErroNfse(ESTADO_INVALIDO, "O lote já foi descartado.")
            estado_anterior = lote["estado"]
            if estado_anterior == APROVADO:
                conn.execute("UPDATE chave_aprovada SET liberada_em=? WHERE lote_id=?"
                             " AND liberada_em IS NULL", (agora_iso(), lote_id))
            nova = int(lote["revision"]) + 1
            conn.execute(
                "UPDATE lote SET estado=?, revision=?, descartado_em=?,"
                " descartado_por_id=?, descartado_por_login=?, motivo_descarte=?"
                " WHERE id=?",
                (DESCARTADO, nova, agora_iso(), usuario_id, usuario_login,
                 motivo[:MAX_MOTIVO], lote_id))
            self._evento(conn, "lote_descartado", usuario_id=usuario_id,
                         usuario_login=usuario_login, perfil_id=lote["perfil_id"],
                         lote_id=lote_id,
                         detalhe={"estado_anterior": estado_anterior,
                                  "motivo": motivo[:MAX_MOTIVO]})
        return {"lote_id": lote_id, "revision": nova, "estado_anterior": estado_anterior}

    def registrar_exportacao(self, lote_id: int, formato: str, *, usuario_id: int,
                             usuario_login: str, dps_id: int | None = None) -> None:
        lote = self._conn.execute("SELECT perfil_id FROM lote WHERE id=?",
                                  (lote_id,)).fetchone()
        with self._transacao() as conn:
            self._evento(conn, "exportacao", usuario_id=usuario_id,
                         usuario_login=usuario_login,
                         perfil_id=lote["perfil_id"] if lote else None,
                         lote_id=lote_id, dps_id=dps_id, detalhe={"formato": formato})

    # ------------------------------------------------------------------
    # Consultas

    def estado_do_lote(self, lote_id: int) -> str:
        lote = self._conn.execute("SELECT estado FROM lote WHERE id=?",
                                  (lote_id,)).fetchone()
        if lote is None:
            raise nf.ErroNfse(LOTE_NAO_ENCONTRADO, "Lote não encontrado.")
        return lote["estado"]

    def listar_lotes(self, *, perfil_id: int | None = None, estado: str | None = None,
                     limite: int = 50, deslocamento: int = 0) -> dict:
        filtros, valores = [], []
        if perfil_id is not None:
            filtros.append("l.perfil_id=?")
            valores.append(int(perfil_id))
        if estado is not None:
            if estado not in (EM_REVISAO, APROVADO, DESCARTADO):
                raise nf.ErroNfse(ESTADO_INVALIDO, f"Estado desconhecido: {estado!r}.")
            filtros.append("l.estado=?")
            valores.append(estado)
        onde = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        limite = max(1, min(int(limite), 200))
        deslocamento = max(0, int(deslocamento))
        total = self._conn.execute(f"SELECT COUNT(*) AS n FROM lote l{onde}",
                                   valores).fetchone()["n"]
        itens = []
        for l in self._conn.execute(
                "SELECT l.id, l.perfil_id, l.estado, l.revision, l.criado_em,"
                " l.criado_por_login, l.aprovado_em, l.aprovado_por_login, o.tipo,"
                " o.nome_arquivo, p.cnpj FROM lote l JOIN origem o ON o.id=l.origem_id"
                f" JOIN perfil p ON p.id=l.perfil_id{onde}"
                " ORDER BY l.id DESC LIMIT ? OFFSET ?", (*valores, limite, deslocamento)):
            item = dict(l)
            item["totais"] = self._totais(int(l["id"]))
            itens.append(item)
        return {"total": total, "itens": itens}

    def _totais(self, lote_id: int) -> dict:
        rodada = self._conn.execute("SELECT conferencia_atual_id AS c FROM lote WHERE id=?",
                                    (lote_id,)).fetchone()["c"]
        linhas = list(self._conn.execute(
            "SELECT excluida, situacao, valor_centavos FROM conferencia_linha"
            " WHERE conferencia_id=?", (rodada,)))
        ativas = [l for l in linhas if not l["excluida"]]
        return {"linhas": len(linhas), "ativas": len(ativas),
                "excluidas": len(linhas) - len(ativas),
                "bloqueio": sum(1 for l in ativas if l["situacao"] == "bloqueio"),
                "aviso": sum(1 for l in ativas if l["situacao"] == "aviso"),
                "ok": sum(1 for l in ativas if l["situacao"] == "ok"),
                "soma_centavos": sum(l["valor_centavos"] or 0 for l in ativas)}

    def lote(self, lote_id: int) -> dict:
        conn = self._conn
        lote = conn.execute("SELECT * FROM lote WHERE id=?", (lote_id,)).fetchone()
        if lote is None:
            raise nf.ErroNfse(LOTE_NAO_ENCONTRADO, "Lote não encontrado.")
        origem = conn.execute(
            "SELECT tipo, sha256, nome_arquivo, tamanho_bytes, importado_em,"
            " importado_por_login FROM origem WHERE id=?", (lote["origem_id"],)).fetchone()
        rodada = conn.execute("SELECT * FROM conferencia WHERE id=?",
                              (lote["conferencia_atual_id"],)).fetchone()
        versao_id, numero = self.versao_atual(lote["perfil_id"])
        perfil_atual = self.carregar_versao(versao_id)
        turmas = {tid: t for tid, t in self._turmas_da_versao(rodada["perfil_versao_id"])}
        efetivas = {e.ref: e for e in self._efetivas(conn, lote_id)}
        corrigidos: dict[int, list[str]] = {}
        for c in conn.execute(
                "SELECT c.linha_id, c.campo FROM correcao c JOIN linha l ON l.id=c.linha_id"
                " WHERE l.lote_id=? ORDER BY c.id", (lote_id,)):
            lista = corrigidos.setdefault(int(c["linha_id"]), [])
            if c["campo"] != "excluida" and c["campo"] not in lista:
                lista.append(c["campo"])

        linhas = []
        for l in conn.execute(
                "SELECT l.*, cl.id AS cl_id, cl.excluida AS cl_excluida, cl.cpf AS cl_cpf,"
                " cl.competencia AS cl_competencia, cl.valor_centavos, cl.turma_id,"
                " cl.responsavel AS cl_responsavel, cl.aluno AS cl_aluno,"
                " cl.endereco AS cl_endereco, cl.discriminacao, cl.situacao"
                " FROM linha l JOIN conferencia_linha cl ON cl.linha_id=l.id"
                " AND cl.conferencia_id=? WHERE l.lote_id=? ORDER BY l.ordem",
                (rodada["id"], lote_id)):
            turma = turmas.get(l["turma_id"])
            apontamentos = [{"codigo": a["codigo"], "nivel": a["nivel"],
                             "campo": a["campo"], "mensagem": a["mensagem"],
                             "referencia": json.loads(a["referencia"])
                             if a["referencia"] else None}
                            for a in conn.execute(
                                "SELECT * FROM apontamento WHERE conferencia_linha_id=?"
                                " ORDER BY id", (l["cl_id"],))]
            linhas.append({
                "id": l["id"], "ordem": l["ordem"],
                "origem": {"aba": l["aba"], "linha_planilha": l["linha_planilha"],
                           "bloco": l["bloco"], "texto_linha_ini": l["texto_linha_ini"],
                           "texto_linha_fim": l["texto_linha_fim"]},
                "brutos": {c: l[c] for c in ne.CAMPOS},
                "efetivos": efetivas[l["id"]].campos,
                "corrigidos": corrigidos.get(int(l["id"]), []),
                "proveniencia": json.loads(l["proveniencia"]),
                "excluida": bool(l["cl_excluida"]),
                "situacao": l["situacao"],
                "cpf": l["cl_cpf"], "competencia": l["cl_competencia"],
                "valor_centavos": l["valor_centavos"],
                "turma": turma.nome if turma else None,
                "codigos": {"cTribNac": turma.c_trib_nac, "cNBS": turma.c_nbs}
                if turma else None,
                "responsavel": l["cl_responsavel"], "aluno": l["cl_aluno"],
                "endereco": json.loads(l["cl_endereco"]) if l["cl_endereco"] else None,
                "discriminacao": l["discriminacao"],
                "apontamentos": apontamentos,
            })

        desatualizado = int(rodada["perfil_versao_id"]) != versao_id
        pendencias = nf.pendencias_do_perfil(perfil_atual)
        apontamentos_lote = []
        if lote["estado"] == EM_REVISAO:
            if pendencias:
                apontamentos_lote.append({
                    "codigo": nf.PERFIL_COM_PENDENCIA, "nivel": "bloqueio",
                    "mensagem": "O perfil tem pendências: " + "; ".join(
                        f"{p.descricao} ({p.origem})" for p in pendencias)})
            if desatualizado:
                apontamentos_lote.append({
                    "codigo": PERFIL_DESATUALIZADO, "nivel": "bloqueio",
                    "mensagem": "O perfil mudou depois da última conferência; "
                                "use Reconferir."})
            if linhas and all(x["excluida"] for x in linhas):
                apontamentos_lote.append({
                    "codigo": LOTE_VAZIO, "nivel": "bloqueio",
                    "mensagem": "Todas as linhas foram excluídas."})
        for aviso in json.loads(lote["avisos_importacao"]):
            apontamentos_lote.append({"codigo": "AVISO_IMPORTACAO", "nivel": "aviso",
                                      "mensagem": aviso})
        dps = [{"id": d["id"], "linha_id": d["linha_id"], "serie": d["serie"],
                "numero": d["numero"], "id_dps": d["id_dps"], "sha256": d["sha256"],
                "dh_emi": d["dh_emi"]}
               for d in conn.execute("SELECT id, linha_id, serie, numero, id_dps, sha256,"
                                     " dh_emi FROM dps WHERE lote_id=? ORDER BY numero",
                                     (lote_id,))]
        dados_lote = {k: lote[k] for k in (
            "id", "perfil_id", "estado", "revision", "criado_em", "criado_por_login",
            "aprovado_em", "aprovado_por_login", "hash_aprovacao", "descartado_em",
            "descartado_por_login", "motivo_descarte", "linhas_ignoradas")}
        dados_lote["origem"] = dict(origem)
        return {
            "lote": dados_lote,
            "perfil": {"perfil_id": lote["perfil_id"], "cnpj": perfil_atual.cnpj,
                       "razao_social": perfil_atual.razao_social,
                       "versao_conferida_id": int(rodada["perfil_versao_id"]),
                       "versao_atual_id": versao_id, "versao_atual": numero,
                       "desatualizado": desatualizado,
                       "pendencias": [asdict(p) for p in pendencias]},
            "conferencia": {"id": rodada["id"], "executada_em": rodada["executada_em"],
                            "executada_por_login": rodada["executada_por_login"],
                            "hoje": rodada["hoje"], "motivo": rodada["motivo"],
                            "competencia_predominante": rodada["competencia_predominante"],
                            "totais": self._totais(lote_id)},
            "apontamentos_lote": apontamentos_lote,
            "linhas": linhas,
            "dps": dps,
        }

    def correcoes(self, linha_id: int) -> list[dict]:
        return [dict(c) for c in self._conn.execute(
            "SELECT id, campo, valor_anterior, valor_novo, motivo, criada_em,"
            " criada_por_login FROM correcao WHERE linha_id=? ORDER BY id", (linha_id,))]

    def eventos(self, lote_id: int) -> list[dict]:
        return [dict(e, detalhe=json.loads(e["detalhe"])) for e in self._conn.execute(
            "SELECT id, tipo, perfil_id, lote_id, linha_id, dps_id, detalhe,"
            " usuario_login, criado_em FROM evento WHERE lote_id=? ORDER BY id",
            (lote_id,))]

    def dps_do_lote(self, lote_id: int) -> list[dict]:
        return [dict(d) for d in self._conn.execute(
            "SELECT d.*, l.ordem FROM dps d JOIN linha l ON l.id=d.linha_id"
            " WHERE d.lote_id=? ORDER BY d.numero", (lote_id,))]

    def dps(self, dps_id: int) -> dict:
        d = self._conn.execute("SELECT * FROM dps WHERE id=?", (dps_id,)).fetchone()
        if d is None:
            raise nf.ErroNfse(DPS_NAO_ENCONTRADA, "DPS não encontrada.")
        return dict(d)

    def caminho_origem(self, lote_id: int) -> str | None:
        o = self._conn.execute(
            "SELECT o.arquivo_relativo FROM lote l JOIN origem o ON o.id=l.origem_id"
            " WHERE l.id=?", (lote_id,)).fetchone()
        if o is None or not o["arquivo_relativo"]:
            return None
        return os.path.join(self.pasta_origens, os.path.basename(o["arquivo_relativo"]))

