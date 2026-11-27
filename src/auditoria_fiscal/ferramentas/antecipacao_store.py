"""Persistencia da Antecipacao/DIFAL do ICMS-BA (spec 027).

Banco proprio (`dados_web/antecipacao.db`), pelo mesmo motivo dos outros
dominios fiscais: ciclo de vida, trilha e backup proprios. Sem FastAPI: caminho
e identidade chegam por injecao (`usuario_id`, `usuario_login`).

Garantias que moram no SQL:

- **Uma nota por chave de acesso** (UNIQUE): a segunda importacao da mesma
  chave nao sobrescreve nada, volta como "duplicada".
- **Trilha append-only** (triggers): toda mudanca de parametro, decisao,
  aprovacao, reabertura e exclusao grava o evento NA MESMA transacao.
- **Aliquota nao muda de valor**: uma linha nova (nova vigencia) substitui a
  anterior; a antiga so ganha data de fim. A memoria de cada item guarda a
  aliquota usada, entao o que ja foi aprovado nao muda com a tabela.

Dinheiro: centavos inteiros no banco, Decimal no nucleo.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from ..core import antecipacao_ba as ab

VERSAO_SCHEMA = 1

ESTADO_REVISAO = "em_revisao"
ESTADO_APROVADA = "aprovada"
ESTADOS = {ESTADO_REVISAO: "Em revisão", ESTADO_APROVADA: "Aprovada"}

ORIGEM_AUTOMATICA = "automatica"
ORIGEM_REVISOR = "revisor"

CONFIG_PADRAO = {
    "metodo_padrao": ab.METODO_POR_DENTRO,
    "componentes": dict(ab.COMPONENTES_PADRAO),
    "reducao_percentual": "20",
    "dia_vencimento": 25,
}

MAX_MOTIVO = 500


class ConcorrenciaError(Exception):
    """A nota mudou desde que o cliente a leu."""

    def __init__(self, revision_atual: int):
        super().__init__("Registro desatualizado.")
        self.revision_atual = revision_atual


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_TABELAS = """
CREATE TABLE IF NOT EXISTS aliquota (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL,
  uf TEXT NOT NULL,
  ncm TEXT NOT NULL DEFAULT '',
  percentual TEXT NOT NULL,
  vigencia_inicio TEXT NOT NULL,
  vigencia_fim TEXT NOT NULL DEFAULT '',
  base_legal TEXT NOT NULL,
  origem TEXT NOT NULL DEFAULT 'usuario',
  criada_por_login TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  encerrada_por_login TEXT NOT NULL DEFAULT '',
  encerrada_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS configuracao (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL,
  atualizado_por_login TEXT NOT NULL DEFAULT '',
  atualizado_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS empresa (
  cnpj TEXT PRIMARY KEY,
  nome TEXT NOT NULL DEFAULT '',
  regime TEXT NOT NULL DEFAULT '',
  atualizado_por_login TEXT NOT NULL DEFAULT '',
  atualizado_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS nota (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chave TEXT NOT NULL UNIQUE,
  sha256 TEXT NOT NULL DEFAULT '',
  cnpj_dest TEXT NOT NULL REFERENCES empresa(cnpj),
  nome_dest TEXT NOT NULL DEFAULT '',
  cnpj_emit TEXT NOT NULL DEFAULT '',
  nome_emit TEXT NOT NULL DEFAULT '',
  crt_emit TEXT NOT NULL DEFAULT '',
  uf_origem TEXT NOT NULL,
  uf_destino TEXT NOT NULL,
  numero TEXT NOT NULL DEFAULT '',
  serie TEXT NOT NULL DEFAULT '',
  fin_nfe TEXT NOT NULL DEFAULT '',
  dt_emissao TEXT NOT NULL,
  competencia TEXT NOT NULL,
  valor_total INTEGER,
  metodo TEXT NOT NULL,
  presuncao INTEGER NOT NULL DEFAULT 0,
  componentes TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'em_revisao',
  a_recolher INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 1,
  importada_por_login TEXT NOT NULL,
  importada_em TEXT NOT NULL,
  aprovada_por_login TEXT NOT NULL DEFAULT '',
  aprovada_em TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nota_id INTEGER NOT NULL REFERENCES nota(id) ON DELETE CASCADE,
  ordem INTEGER NOT NULL,
  num_item TEXT NOT NULL DEFAULT '',
  descricao TEXT NOT NULL DEFAULT '',
  ncm TEXT NOT NULL DEFAULT '',
  cest TEXT NOT NULL DEFAULT '',
  cfop TEXT NOT NULL DEFAULT '',
  cst TEXT NOT NULL DEFAULT '',
  origem_mercadoria TEXT NOT NULL DEFAULT '',
  v_prod INTEGER,
  v_desc INTEGER NOT NULL DEFAULT 0,
  v_frete INTEGER NOT NULL DEFAULT 0,
  v_seg INTEGER NOT NULL DEFAULT 0,
  v_outro INTEGER NOT NULL DEFAULT 0,
  v_ipi INTEGER NOT NULL DEFAULT 0,
  aliq_icms TEXT,
  v_icms INTEGER,
  v_bc_st INTEGER NOT NULL DEFAULT 0,
  v_st INTEGER NOT NULL DEFAULT 0,
  v_fcp INTEGER NOT NULL DEFAULT 0,
  v_cred_sn INTEGER NOT NULL DEFAULT 0,
  finalidade TEXT NOT NULL DEFAULT '',
  decisao TEXT NOT NULL DEFAULT '',
  decisao_origem TEXT NOT NULL DEFAULT '',
  decisao_motivo TEXT NOT NULL DEFAULT '',
  decisao_por_login TEXT NOT NULL DEFAULT '',
  decisao_em TEXT NOT NULL DEFAULT '',
  pendencias TEXT NOT NULL DEFAULT '[]',
  memoria TEXT NOT NULL DEFAULT '{}',
  tipo_credito TEXT NOT NULL DEFAULT '',
  aliquota_credito TEXT NOT NULL DEFAULT '',
  a_recolher INTEGER,
  UNIQUE (nota_id, ordem)
);

CREATE TABLE IF NOT EXISTS evento (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nota_id INTEGER,
  chave TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL,
  detalhe TEXT NOT NULL DEFAULT '',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  criado_em TEXT NOT NULL
);
"""

_INDICES = """
CREATE INDEX IF NOT EXISTS idx_aliquota_busca ON aliquota(tipo, uf, ncm);
CREATE INDEX IF NOT EXISTS idx_nota_empresa ON nota(cnpj_dest, competencia);
CREATE INDEX IF NOT EXISTS idx_nota_estado ON nota(estado, competencia);
CREATE INDEX IF NOT EXISTS idx_item_nota ON item(nota_id, ordem);
CREATE INDEX IF NOT EXISTS idx_evento_nota ON evento(nota_id, id);
"""

_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_evento_sem_update
BEFORE UPDATE ON evento BEGIN
  SELECT RAISE(ABORT, 'Evento e imutavel: UPDATE nao e permitido.');
END;
CREATE TRIGGER IF NOT EXISTS trg_evento_sem_delete
BEFORE DELETE ON evento BEGIN
  SELECT RAISE(ABORT, 'Evento e imutavel: DELETE nao e permitido.');
END;

-- O percentual de uma linha da tabela nunca muda: muda-se a vigencia.
CREATE TRIGGER IF NOT EXISTS trg_aliquota_valor_imutavel
BEFORE UPDATE ON aliquota
WHEN NEW.percentual IS NOT OLD.percentual OR NEW.tipo IS NOT OLD.tipo
     OR NEW.uf IS NOT OLD.uf OR NEW.ncm IS NOT OLD.ncm
     OR NEW.vigencia_inicio IS NOT OLD.vigencia_inicio BEGIN
  SELECT RAISE(ABORT, 'Aliquota e imutavel: cadastre uma nova vigencia.');
END;
CREATE TRIGGER IF NOT EXISTS trg_aliquota_sem_delete
BEFORE DELETE ON aliquota BEGIN
  SELECT RAISE(ABORT, 'Aliquota nao e excluida: encerre a vigencia.');
END;

-- Nota aprovada so muda pelo caminho de reabrir (estado volta a em_revisao).
CREATE TRIGGER IF NOT EXISTS trg_nota_aprovada_sem_delete
BEFORE DELETE ON nota WHEN OLD.estado = 'aprovada' BEGIN
  SELECT RAISE(ABORT, 'Nota aprovada nao e excluida: reabra antes.');
END;
CREATE TRIGGER IF NOT EXISTS trg_item_de_nota_aprovada
BEFORE UPDATE ON item
WHEN (SELECT estado FROM nota WHERE id = OLD.nota_id) = 'aprovada' BEGIN
  SELECT RAISE(ABORT, 'Item de nota aprovada e imutavel: reabra a nota.');
END;
"""


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True)


def _motivo(texto, obrigatorio: bool, para: str) -> str:
    limpo = " ".join(str(texto or "").split())[:MAX_MOTIVO]
    if obrigatorio and len(limpo) < 5:
        raise ab.ErroAntecipacao(
            "MOTIVO_OBRIGATORIO",
            f"Escreva o motivo ({para}): ele fica na trilha da nota.")
    return limpo


class AntecipacaoStore:
    """Uma instancia por operacao/thread: conexao SQLite nao atravessa thread."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        pasta = os.path.dirname(os.path.abspath(db_path))
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=15, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._migrar()

    def _migrar(self) -> None:
        conn = self._conn
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_TABELAS)
        conn.executescript(_INDICES)
        conn.executescript(_TRIGGERS)
        conn.execute(f"PRAGMA user_version={VERSAO_SCHEMA}")
        # A leitura vem antes para nao pedir trava de escrita a cada conexao.
        if not conn.execute("SELECT 1 FROM aliquota LIMIT 1").fetchone():
            self._transacao(self._semear)

    @staticmethod
    def _semear(conn) -> None:
        """Carga inicial idempotente: so quando a tabela esta vazia."""
        if conn.execute("SELECT 1 FROM aliquota LIMIT 1").fetchone():
            return
        momento = agora()
        for linha in ab.aliquotas_iniciais():
            conn.execute(
                "INSERT INTO aliquota(tipo, uf, ncm, percentual,"
                " vigencia_inicio, base_legal, origem, criada_por_login,"
                " criada_em) VALUES(?,?,?,?,?,?,?,?,?)",
                (linha["tipo"], linha["uf"], linha["ncm"], linha["percentual"],
                 linha["vigencia_inicio"], linha["base_legal"], "semente",
                 "sistema", momento))

    def fechar(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def contar(self, tabela: str) -> int:
        if tabela not in {"aliquota", "configuracao", "empresa", "nota",
                          "item", "evento"}:
            raise ValueError(f"Tabela desconhecida: {tabela}")
        return self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {tabela}").fetchone()["n"]

    def _transacao(self, operacao):
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            resultado = operacao(conn)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        return resultado

    @staticmethod
    def _evento(conn, tipo: str, detalhe: str, *, nota_id: int | None = None,
                chave: str = "", usuario_id: int = 0,
                usuario_login: str = "") -> None:
        conn.execute(
            "INSERT INTO evento(nota_id, chave, tipo, detalhe, usuario_id,"
            " usuario_login, criado_em) VALUES(?,?,?,?,?,?,?)",
            (nota_id, chave, tipo, detalhe[:1000], int(usuario_id or 0),
             usuario_login or "?", agora()))

    # ------------------------------------------------------------------
    # Configuracao

    def configuracao(self) -> dict:
        valores = {k: (dict(v) if isinstance(v, dict) else v)
                   for k, v in CONFIG_PADRAO.items()}
        for linha in self._conn.execute("SELECT chave, valor FROM configuracao"):
            if linha["chave"] in valores:
                valores[linha["chave"]] = json.loads(linha["valor"])
        return valores

    def definir_configuracao(self, dados: dict, *, usuario_id: int = 0,
                             usuario_login: str = "") -> dict:
        atual = self.configuracao()
        novo = dict(atual)
        if "metodo_padrao" in dados:
            if dados["metodo_padrao"] not in ab.METODOS:
                raise ab.ErroAntecipacao("METODO_INVALIDO", "Método desconhecido.")
            novo["metodo_padrao"] = dados["metodo_padrao"]
        if "componentes" in dados:
            novo["componentes"] = ab.validar_parametros(
                novo["metodo_padrao"], False, dados["componentes"]).componentes
        if "reducao_percentual" in dados:
            percentual = ab.para_decimal(dados["reducao_percentual"])
            if percentual is None or not 0 <= percentual <= 100:
                raise ab.ErroAntecipacao(
                    "PERCENTUAL_INVALIDO", "Redução: informe de 0 a 100.")
            novo["reducao_percentual"] = ab.texto_percentual(percentual)
        if "dia_vencimento" in dados:
            try:
                dia = int(dados["dia_vencimento"])
            except (TypeError, ValueError):
                dia = 0
            if not 1 <= dia <= 28:
                raise ab.ErroAntecipacao(
                    "DIA_INVALIDO", "Dia de vencimento: informe de 1 a 28.")
            novo["dia_vencimento"] = dia
        mudou = {k: v for k, v in novo.items() if v != atual[k]}
        if not mudou:
            return atual

        def _gravar(conn):
            momento = agora()
            for chave, valor in mudou.items():
                conn.execute(
                    "INSERT INTO configuracao(chave, valor,"
                    " atualizado_por_login, atualizado_em) VALUES(?,?,?,?)"
                    " ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,"
                    " atualizado_por_login=excluded.atualizado_por_login,"
                    " atualizado_em=excluded.atualizado_em",
                    (chave, _json(valor), usuario_login, momento))
            self._evento(
                conn, "configuracao_alterada",
                "; ".join(f"{k}: {_json(atual[k])} -> {_json(v)}"
                          for k, v in sorted(mudou.items())),
                usuario_id=usuario_id, usuario_login=usuario_login)
        self._transacao(_gravar)
        return self.configuracao()

    # ------------------------------------------------------------------
    # Aliquotas por vigencia

    def aliquotas(self) -> list[dict]:
        return [dict(l) for l in self._conn.execute(
            "SELECT * FROM aliquota ORDER BY tipo, uf, ncm, vigencia_inicio DESC")]

    def tabela(self) -> ab.TabelaAliquotas:
        return ab.TabelaAliquotas(self.aliquotas())

    def criar_aliquota(self, dados: dict, *, usuario_id: int = 0,
                       usuario_login: str = "") -> int:
        nova = ab.validar_aliquota(dados)

        def _criar(conn):
            momento = agora()
            existentes = conn.execute(
                "SELECT * FROM aliquota WHERE tipo=? AND uf=? AND ncm=?",
                (nova["tipo"], nova["uf"], nova["ncm"])).fetchall()
            for linha in existentes:
                inicio, fim = linha["vigencia_inicio"], linha["vigencia_fim"]
                novo_fim = nova["vigencia_fim"]
                sobrepoe = (inicio <= (novo_fim or "9999-12-31")
                            and nova["vigencia_inicio"] <= (fim or "9999-12-31"))
                if not sobrepoe:
                    continue
                if not fim and inicio < nova["vigencia_inicio"] and not novo_fim:
                    # A vigencia aberta termina na vespera da nova.
                    vespera = (date.fromisoformat(nova["vigencia_inicio"])
                               - timedelta(days=1)).isoformat()
                    conn.execute(
                        "UPDATE aliquota SET vigencia_fim=?,"
                        " encerrada_por_login=?, encerrada_em=? WHERE id=?",
                        (vespera, usuario_login, momento, linha["id"]))
                    continue
                raise ab.ErroAntecipacao(
                    "VIGENCIA_SOBREPOSTA",
                    "Já existe alíquota para o mesmo alcance nesse período "
                    f"({linha['percentual']}% desde {inicio}). Encerre a "
                    "vigência anterior ou ajuste as datas.")
            cur = conn.execute(
                "INSERT INTO aliquota(tipo, uf, ncm, percentual,"
                " vigencia_inicio, vigencia_fim, base_legal, origem,"
                " criada_por_login, criada_em) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (nova["tipo"], nova["uf"], nova["ncm"], nova["percentual"],
                 nova["vigencia_inicio"], nova["vigencia_fim"],
                 nova["base_legal"], "usuario", usuario_login, momento))
            self._evento(
                conn, "aliquota_criada",
                f"{nova['tipo']} {nova['uf']} ncm={nova['ncm'] or 'geral'}: "
                f"{nova['percentual']}% a partir de {nova['vigencia_inicio']}"
                f" ({nova['base_legal']})",
                usuario_id=usuario_id, usuario_login=usuario_login)
            return cur.lastrowid
        return self._transacao(_criar)

    def encerrar_aliquota(self, aliquota_id: int, fim, *, usuario_id: int = 0,
                          usuario_login: str = "") -> dict:
        fim_iso = ab.data_iso(fim)
        if not fim_iso:
            raise ab.ErroAntecipacao(
                "VIGENCIA_INVALIDA", "Informe a data de fim (dd/mm/aaaa).")

        def _encerrar(conn):
            linha = conn.execute("SELECT * FROM aliquota WHERE id=?",
                                 (aliquota_id,)).fetchone()
            if linha is None:
                raise LookupError("Alíquota não encontrada.")
            if linha["vigencia_fim"]:
                raise ab.ErroAntecipacao(
                    "JA_ENCERRADA", "Esta vigência já está encerrada.")
            if fim_iso < linha["vigencia_inicio"]:
                raise ab.ErroAntecipacao(
                    "VIGENCIA_INVALIDA",
                    "O fim não pode ser antes do início da vigência.")
            conn.execute(
                "UPDATE aliquota SET vigencia_fim=?, encerrada_por_login=?,"
                " encerrada_em=? WHERE id=?",
                (fim_iso, usuario_login, agora(), aliquota_id))
            self._evento(
                conn, "aliquota_encerrada",
                f"{linha['tipo']} {linha['uf']} ncm={linha['ncm'] or 'geral'}"
                f" {linha['percentual']}%: fim em {fim_iso}",
                usuario_id=usuario_id, usuario_login=usuario_login)
        self._transacao(_encerrar)
        return dict(self._conn.execute(
            "SELECT * FROM aliquota WHERE id=?", (aliquota_id,)).fetchone())

    # ------------------------------------------------------------------
    # Empresas (destinatarias)

    def empresas(self) -> list[dict]:
        return [dict(l) for l in self._conn.execute(
            "SELECT e.*, (SELECT COUNT(*) FROM nota n WHERE n.cnpj_dest=e.cnpj)"
            " AS notas FROM empresa e ORDER BY e.nome, e.cnpj")]

    def definir_regime(self, cnpj: str, regime: str, *, usuario_id: int = 0,
                       usuario_login: str = "") -> dict:
        cnpj = ab.so_digitos(cnpj)
        if regime not in ab.REGIMES:
            raise ab.ErroAntecipacao("REGIME_INVALIDO", "Regime desconhecido.")

        def _definir(conn):
            linha = conn.execute("SELECT * FROM empresa WHERE cnpj=?",
                                 (cnpj,)).fetchone()
            if linha is None:
                raise LookupError("Empresa não encontrada.")
            if linha["regime"] == regime:
                return
            conn.execute(
                "UPDATE empresa SET regime=?, atualizado_por_login=?,"
                " atualizado_em=? WHERE cnpj=?",
                (regime, usuario_login, agora(), cnpj))
            self._evento(
                conn, "regime_definido",
                f"empresa {cnpj}: {linha['regime'] or 'não informado'} -> {regime}",
                usuario_id=usuario_id, usuario_login=usuario_login)
        self._transacao(_definir)
        return dict(self._conn.execute(
            "SELECT * FROM empresa WHERE cnpj=?", (cnpj,)).fetchone())

    # ------------------------------------------------------------------
    # Avaliacao (ponte entre as linhas do banco e o nucleo)

    @staticmethod
    def _entrada_item(linha) -> ab.ItemEntrada:
        def dinheiro(nome):
            return ab.de_centavos(linha[nome])
        return ab.ItemEntrada(
            num_item=linha["num_item"], descricao=linha["descricao"],
            ncm=linha["ncm"], cest=linha["cest"], cfop=linha["cfop"],
            cst=linha["cst"], origem_mercadoria=linha["origem_mercadoria"],
            v_prod=dinheiro("v_prod"), v_desc=dinheiro("v_desc"),
            v_frete=dinheiro("v_frete"), v_seg=dinheiro("v_seg"),
            v_outro=dinheiro("v_outro"), v_ipi=dinheiro("v_ipi"),
            aliq_icms=(Decimal(linha["aliq_icms"])
                       if linha["aliq_icms"] else None),
            v_icms=dinheiro("v_icms"), v_bc_st=dinheiro("v_bc_st"),
            v_st=dinheiro("v_st"), v_fcp=dinheiro("v_fcp"),
            v_cred_sn=dinheiro("v_cred_sn"))

    @staticmethod
    def _entrada_nota(linha) -> ab.NotaEntrada:
        return ab.NotaEntrada(
            chave=linha["chave"], uf_origem=linha["uf_origem"],
            uf_destino=linha["uf_destino"], crt_emit=linha["crt_emit"],
            fin_nfe=linha["fin_nfe"],
            dt_emissao=date.fromisoformat(linha["dt_emissao"]))

    @staticmethod
    def _parametros(linha) -> ab.Parametros:
        return ab.validar_parametros(linha["metodo"], bool(linha["presuncao"]),
                                     json.loads(linha["componentes"]))

    def _recalcular(self, conn, nota_id: int) -> int:
        """Refaz a memoria de todos os itens da nota e a soma dela.

        Decisao de revisor e' preservada; so cai quando deixou de ser possivel
        (mandou calcular e o item passou a ter impedimento)."""
        nota = conn.execute("SELECT * FROM nota WHERE id=?",
                            (nota_id,)).fetchone()
        entrada_nota = self._entrada_nota(nota)
        parametros = self._parametros(nota)
        tabela = ab.TabelaAliquotas([dict(l) for l in conn.execute(
            "SELECT * FROM aliquota")])
        soma = 0
        for linha in conn.execute(
                "SELECT * FROM item WHERE nota_id=? ORDER BY ordem",
                (nota_id,)).fetchall():
            r = ab.avaliar_item(self._entrada_item(linha), entrada_nota,
                                parametros, tabela, linha["finalidade"])
            decisao, origem = linha["decisao"], linha["decisao_origem"]
            motivo, por, em = (linha["decisao_motivo"],
                               linha["decisao_por_login"], linha["decisao_em"])
            possivel = (r["a_recolher"] is not None
                        and not ab.impede_calculo(r["pendencias"]))
            if origem == ORIGEM_REVISOR:
                if decisao == ab.DECISAO_CALCULAR and not possivel:
                    decisao = origem = motivo = por = em = ""
            else:
                decisao = ab.decisao_automatica(r["pendencias"], r["a_recolher"])
                origem = ORIGEM_AUTOMATICA if decisao else ""
                motivo = por = em = ""
            valor = ab.centavos(r["a_recolher"])
            if decisao == ab.DECISAO_CALCULAR:
                soma += valor
            conn.execute(
                "UPDATE item SET pendencias=?, memoria=?, tipo_credito=?,"
                " aliquota_credito=?, a_recolher=?, decisao=?,"
                " decisao_origem=?, decisao_motivo=?, decisao_por_login=?,"
                " decisao_em=? WHERE id=?",
                (_json(r["pendencias"]), _json(r["memoria"]),
                 r["memoria"]["tipo_credito"] or "",
                 r["aliquota_credito"] or "", valor, decisao, origem, motivo,
                 por, em, linha["id"]))
        conn.execute("UPDATE nota SET a_recolher=? WHERE id=?", (soma, nota_id))
        return soma

    # ------------------------------------------------------------------
    # Importacao

    def chaves_existentes(self, chaves: list[str]) -> dict[str, dict]:
        achadas: dict[str, dict] = {}
        for chave in set(chaves):
            linha = self._conn.execute(
                "SELECT id, estado FROM nota WHERE chave=?", (chave,)).fetchone()
            if linha:
                achadas[chave] = {"nota_id": linha["id"],
                                  "estado": linha["estado"]}
        return achadas

    def importar(self, nota: ab.NotaEntrada, *, sha256: str,
                 parametros: ab.Parametros, finalidade: str = "",
                 usuario_id: int = 0, usuario_login: str = "") -> dict:
        """Grava a nota em revisao. Devolve a situacao: importada, duplicada
        ou recusada (fora do escopo) — nunca sobrescreve uma chave existente."""
        if finalidade and finalidade not in ab.FINALIDADES:
            raise ab.ErroAntecipacao("FINALIDADE_INVALIDA",
                                     "Finalidade desconhecida.")
        recusa = ab.recusa_da_nota(nota)
        if recusa:
            return {"situacao": "recusada", "chave": nota.chave,
                    "codigo": recusa[0], "mensagem": recusa[1]}

        def _importar(conn):
            existente = conn.execute(
                "SELECT id, estado FROM nota WHERE chave=?",
                (nota.chave,)).fetchone()
            if existente:
                return {"situacao": "duplicada", "chave": nota.chave,
                        "nota_id": existente["id"],
                        "estado": existente["estado"]}
            momento = agora()
            conn.execute(
                "INSERT INTO empresa(cnpj, nome) VALUES(?,?)"
                " ON CONFLICT(cnpj) DO NOTHING",
                (nota.cnpj_dest, nota.nome_dest))
            cur = conn.execute(
                "INSERT INTO nota(chave, sha256, cnpj_dest, nome_dest,"
                " cnpj_emit, nome_emit, crt_emit, uf_origem, uf_destino,"
                " numero, serie, fin_nfe, dt_emissao, competencia,"
                " valor_total, metodo, presuncao, componentes,"
                " importada_por_login, importada_em)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (nota.chave, sha256, nota.cnpj_dest, nota.nome_dest,
                 nota.cnpj_emit, nota.nome_emit, nota.crt_emit,
                 nota.uf_origem, nota.uf_destino, nota.numero, nota.serie,
                 nota.fin_nfe, nota.dt_emissao.isoformat(),
                 ab.competencia_de(nota.dt_emissao),
                 ab.centavos(nota.valor_total), parametros.metodo,
                 int(parametros.presuncao), _json(parametros.componentes),
                 usuario_login, momento))
            nota_id = cur.lastrowid
            for ordem, it in enumerate(nota.itens, start=1):
                conn.execute(
                    "INSERT INTO item(nota_id, ordem, num_item, descricao,"
                    " ncm, cest, cfop, cst, origem_mercadoria, v_prod,"
                    " v_desc, v_frete, v_seg, v_outro, v_ipi, aliq_icms,"
                    " v_icms, v_bc_st, v_st, v_fcp, v_cred_sn, finalidade)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (nota_id, ordem, it.num_item, it.descricao, it.ncm,
                     it.cest, it.cfop, it.cst, it.origem_mercadoria,
                     ab.centavos(it.v_prod), ab.centavos(it.v_desc),
                     ab.centavos(it.v_frete), ab.centavos(it.v_seg),
                     ab.centavos(it.v_outro), ab.centavos(it.v_ipi),
                     ab.texto_percentual(it.aliq_icms)
                     if it.aliq_icms is not None else None,
                     ab.centavos(it.v_icms), ab.centavos(it.v_bc_st),
                     ab.centavos(it.v_st), ab.centavos(it.v_fcp),
                     ab.centavos(it.v_cred_sn), finalidade))
            soma = self._recalcular(conn, nota_id)
            pendentes = conn.execute(
                "SELECT COUNT(*) AS n FROM item WHERE nota_id=? AND decisao=''",
                (nota_id,)).fetchone()["n"]
            self._evento(
                conn, "nota_importada",
                f"{len(nota.itens)} item(ns); método {parametros.metodo}; "
                f"presunção {'autorizada' if parametros.presuncao else 'não autorizada'}; "
                f"finalidade {finalidade or 'a definir'}; "
                f"{pendentes} item(ns) aguardando decisão; sha256 {sha256[:12]}",
                nota_id=nota_id, chave=nota.chave, usuario_id=usuario_id,
                usuario_login=usuario_login)
            return {"situacao": "importada", "chave": nota.chave,
                    "nota_id": nota_id, "itens": len(nota.itens),
                    "pendentes": pendentes, "a_recolher": soma}
        return self._transacao(_importar)

    # ------------------------------------------------------------------
    # Revisao

    @staticmethod
    def _nota_para_mudar(conn, nota_id: int, revision: int | None,
                         estado: str):
        nota = conn.execute("SELECT * FROM nota WHERE id=?",
                            (nota_id,)).fetchone()
        if nota is None:
            raise LookupError("Nota não encontrada.")
        if revision is None or int(revision) != nota["revision"]:
            raise ConcorrenciaError(nota["revision"])
        if nota["estado"] != estado:
            if estado == ESTADO_REVISAO:
                raise ab.ErroAntecipacao(
                    "NOTA_APROVADA",
                    "A nota já foi aprovada. Reabra antes de alterar.")
            raise ab.ErroAntecipacao(
                "NOTA_EM_REVISAO", "A nota ainda está em revisão.")
        return nota

    @staticmethod
    def _avancar(conn, nota_id: int) -> int:
        conn.execute("UPDATE nota SET revision=revision+1 WHERE id=?",
                     (nota_id,))
        return conn.execute("SELECT revision FROM nota WHERE id=?",
                            (nota_id,)).fetchone()["revision"]

    def alterar_nota(self, nota_id: int, dados: dict, *, revision: int | None,
                     usuario_id: int = 0, usuario_login: str = "") -> dict:
        """Muda metodo, presuncao ou competencia e refaz a conta da nota."""
        def _alterar(conn):
            nota = self._nota_para_mudar(conn, nota_id, revision,
                                         ESTADO_REVISAO)
            mudancas = []
            metodo, presuncao = nota["metodo"], bool(nota["presuncao"])
            competencia = nota["competencia"]
            if dados.get("metodo") is not None and dados["metodo"] != metodo:
                ab.validar_parametros(dados["metodo"])
                mudancas.append(f"método: {metodo} -> {dados['metodo']}")
                metodo = dados["metodo"]
            if (dados.get("presuncao") is not None
                    and bool(dados["presuncao"]) != presuncao):
                presuncao = bool(dados["presuncao"])
                mudancas.append("presunção: "
                                + ("autorizada" if presuncao else "retirada"))
            if dados.get("competencia") is not None:
                nova = ab.validar_competencia(dados["competencia"])
                if nova != competencia:
                    mudancas.append(f"competência: {competencia} -> {nova}")
                    competencia = nova
            if not mudancas:
                return nota["revision"]
            conn.execute(
                "UPDATE nota SET metodo=?, presuncao=?, competencia=?"
                " WHERE id=?", (metodo, int(presuncao), competencia, nota_id))
            self._recalcular(conn, nota_id)
            self._evento(conn, "nota_alterada", "; ".join(mudancas),
                         nota_id=nota_id, chave=nota["chave"],
                         usuario_id=usuario_id, usuario_login=usuario_login)
            return self._avancar(conn, nota_id)
        self._transacao(_alterar)
        return self.detalhar(nota_id)

    def alterar_itens(self, nota_id: int, item_ids: list[int], *,
                      finalidade: str | None = None,
                      decisao: str | None = None, motivo: str = "",
                      revision: int | None, usuario_id: int = 0,
                      usuario_login: str = "") -> dict:
        """Aplica finalidade e/ou decisao a um ou varios itens (um grupo).

        `decisao=""` devolve o item a regra automatica. Mandar CALCULAR um
        item com excecao exige motivo; mandar EXCLUIR, sempre."""
        if finalidade is not None and finalidade not in ab.FINALIDADES:
            raise ab.ErroAntecipacao("FINALIDADE_INVALIDA",
                                     "Finalidade desconhecida.")
        if decisao is not None and decisao not in (*ab.DECISOES, ""):
            raise ab.ErroAntecipacao("DECISAO_INVALIDA", "Decisão desconhecida.")
        if finalidade is None and decisao is None:
            raise ab.ErroAntecipacao("NADA_A_ALTERAR", "Nada a alterar.")
        ids = sorted({int(i) for i in item_ids or ()})
        if not ids:
            raise ab.ErroAntecipacao("SEM_ITENS", "Escolha ao menos um item.")

        def _alterar(conn):
            nota = self._nota_para_mudar(conn, nota_id, revision,
                                         ESTADO_REVISAO)
            marcas = ",".join("?" * len(ids))
            achados = conn.execute(
                f"SELECT id FROM item WHERE nota_id=? AND id IN ({marcas})",
                (nota_id, *ids)).fetchall()
            if len(achados) != len(ids):
                raise LookupError("Item não pertence a esta nota.")
            if finalidade is not None:
                conn.execute(
                    f"UPDATE item SET finalidade=? WHERE id IN ({marcas})",
                    (finalidade, *ids))
                self._recalcular(conn, nota_id)
            if decisao is not None:
                momento = agora()
                for linha in conn.execute(
                        f"SELECT * FROM item WHERE id IN ({marcas})",
                        ids).fetchall():
                    pendencias = json.loads(linha["pendencias"])
                    if decisao == "":
                        conn.execute(
                            "UPDATE item SET decisao='', decisao_origem='',"
                            " decisao_motivo='', decisao_por_login='',"
                            " decisao_em='' WHERE id=?", (linha["id"],))
                        continue
                    if decisao == ab.DECISAO_CALCULAR:
                        if (linha["a_recolher"] is None
                                or ab.impede_calculo(pendencias)):
                            raise ab.ErroAntecipacao(
                                "ITEM_SEM_CALCULO",
                                f"O item {linha['num_item'] or linha['ordem']} "
                                "não tem como ser calculado: resolva o que "
                                "impede (finalidade, crédito, alíquota ou dado "
                                "faltante) ou deixe-o fora do cálculo.")
                        texto = _motivo(motivo, ab.pede_decisao(pendencias),
                                        "calcular um item com exceção")
                    else:
                        texto = _motivo(motivo, True, "deixar fora do cálculo")
                    conn.execute(
                        "UPDATE item SET decisao=?, decisao_origem=?,"
                        " decisao_motivo=?, decisao_por_login=?, decisao_em=?"
                        " WHERE id=?",
                        (decisao, ORIGEM_REVISOR, texto, usuario_login,
                         momento, linha["id"]))
                self._recalcular(conn, nota_id)
            partes = []
            if finalidade is not None:
                partes.append(f"finalidade={finalidade}")
            if decisao is not None:
                partes.append(f"decisão={decisao or 'automática'}")
            limpo = " ".join(str(motivo or "").split())[:MAX_MOTIVO]
            self._evento(
                conn, "itens_alterados",
                f"{len(ids)} item(ns): " + ", ".join(partes)
                + (f" — {limpo}" if limpo else ""),
                nota_id=nota_id, chave=nota["chave"], usuario_id=usuario_id,
                usuario_login=usuario_login)
            return self._avancar(conn, nota_id)
        self._transacao(_alterar)
        return self.detalhar(nota_id)

    def aprovar(self, nota_id: int, *, revision: int | None,
                usuario_id: int = 0, usuario_login: str = "") -> dict:
        def _aprovar(conn):
            nota = self._nota_para_mudar(conn, nota_id, revision,
                                         ESTADO_REVISAO)
            empresa = conn.execute("SELECT regime FROM empresa WHERE cnpj=?",
                                   (nota["cnpj_dest"],)).fetchone()
            if not empresa or not empresa["regime"]:
                raise ab.ErroAntecipacao(
                    "REGIME_NAO_INFORMADO",
                    "Informe o regime tributário da empresa destinatária "
                    "antes de aprovar (a nota não traz esse dado).")
            # Reconfere com a tabela de agora: o que se aprova e' o que se ve.
            self._recalcular(conn, nota_id)
            pendentes = conn.execute(
                "SELECT COUNT(*) AS n FROM item WHERE nota_id=? AND decisao=''",
                (nota_id,)).fetchone()["n"]
            if pendentes:
                raise ab.ErroAntecipacao(
                    "ITENS_SEM_DECISAO",
                    f"{pendentes} item(ns) ainda aguardam decisão. Nada é "
                    "liberado automaticamente.")
            soma = conn.execute("SELECT a_recolher FROM nota WHERE id=?",
                                (nota_id,)).fetchone()["a_recolher"]
            conn.execute(
                "UPDATE nota SET estado=?, aprovada_por_login=?,"
                " aprovada_em=? WHERE id=?",
                (ESTADO_APROVADA, usuario_login, agora(), nota_id))
            self._evento(
                conn, "nota_aprovada",
                f"a recolher: {soma} centavo(s); método {nota['metodo']}",
                nota_id=nota_id, chave=nota["chave"], usuario_id=usuario_id,
                usuario_login=usuario_login)
            return self._avancar(conn, nota_id)
        self._transacao(_aprovar)
        return self.detalhar(nota_id)

    def reabrir(self, nota_id: int, motivo: str, *, revision: int | None,
                usuario_id: int = 0, usuario_login: str = "") -> dict:
        texto = _motivo(motivo, True, "reabrir a nota")

        def _reabrir(conn):
            nota = self._nota_para_mudar(conn, nota_id, revision,
                                         ESTADO_APROVADA)
            conn.execute(
                "UPDATE nota SET estado=?, aprovada_por_login='',"
                " aprovada_em='' WHERE id=?", (ESTADO_REVISAO, nota_id))
            self._evento(conn, "nota_reaberta", texto, nota_id=nota_id,
                         chave=nota["chave"], usuario_id=usuario_id,
                         usuario_login=usuario_login)
            return self._avancar(conn, nota_id)
        self._transacao(_reabrir)
        return self.detalhar(nota_id)

    def excluir_nota(self, nota_id: int, motivo: str, *, revision: int | None,
                     usuario_id: int = 0, usuario_login: str = "") -> dict:
        """Descarta uma nota EM REVISAO (importacao errada). O evento fica."""
        texto = _motivo(motivo, True, "excluir a nota")

        def _excluir(conn):
            nota = self._nota_para_mudar(conn, nota_id, revision,
                                         ESTADO_REVISAO)
            conn.execute("DELETE FROM item WHERE nota_id=?", (nota_id,))
            conn.execute("DELETE FROM nota WHERE id=?", (nota_id,))
            self._evento(conn, "nota_excluida", texto, nota_id=nota_id,
                         chave=nota["chave"], usuario_id=usuario_id,
                         usuario_login=usuario_login)
            return {"chave": nota["chave"], "sha256": nota["sha256"]}
        return self._transacao(_excluir)

    # ------------------------------------------------------------------
    # Leitura

    @staticmethod
    def _filtros(cnpj: str = "", competencia: str = "", estado: str = "",
                 texto: str = "") -> tuple[str, list]:
        onde, valores = [], []
        if cnpj:
            onde.append("n.cnpj_dest=?")
            valores.append(ab.so_digitos(cnpj))
        if competencia:
            onde.append("n.competencia=?")
            valores.append(ab.validar_competencia(competencia))
        if estado:
            if estado not in ESTADOS:
                raise ValueError("Estado desconhecido.")
            onde.append("n.estado=?")
            valores.append(estado)
        if texto:
            trecho = f"%{texto.strip()[:80]}%"
            onde.append("(n.chave LIKE ? OR n.numero LIKE ? OR n.nome_emit"
                        " LIKE ? OR n.nome_dest LIKE ?)")
            valores += [trecho] * 4
        return (" WHERE " + " AND ".join(onde)) if onde else "", valores

    def listar_notas(self, *, pagina: int = 1, limite: int = 50,
                     **filtros) -> dict:
        limite = max(1, min(int(limite or 50), 200))
        pagina = max(1, int(pagina or 1))
        onde, valores = self._filtros(**filtros)
        total = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM nota n{onde}", valores).fetchone()["n"]
        linhas = self._conn.execute(
            "SELECT n.*, e.regime,"
            " (SELECT COUNT(*) FROM item i WHERE i.nota_id=n.id) AS itens,"
            " (SELECT COUNT(*) FROM item i WHERE i.nota_id=n.id"
            "   AND i.decisao='') AS pendentes"
            f" FROM nota n JOIN empresa e ON e.cnpj=n.cnpj_dest{onde}"
            " ORDER BY n.dt_emissao DESC, n.id DESC LIMIT ? OFFSET ?",
            (*valores, limite, (pagina - 1) * limite)).fetchall()
        return {"itens": [dict(l) for l in linhas], "total": total,
                "pagina": pagina, "limite": limite,
                "paginas": max(1, -(-total // limite))}

    @staticmethod
    def _item_dict(linha) -> dict:
        item = dict(linha)
        item["pendencias"] = json.loads(item["pendencias"])
        item["memoria"] = json.loads(item["memoria"])
        return item

    def detalhar(self, nota_id: int) -> dict:
        nota = self._conn.execute(
            "SELECT n.*, e.regime FROM nota n JOIN empresa e"
            " ON e.cnpj=n.cnpj_dest WHERE n.id=?", (nota_id,)).fetchone()
        if nota is None:
            raise LookupError("Nota não encontrada.")
        itens = [self._item_dict(l) for l in self._conn.execute(
            "SELECT * FROM item WHERE nota_id=? ORDER BY ordem", (nota_id,))]
        eventos = [dict(l) for l in self._conn.execute(
            "SELECT tipo, detalhe, usuario_login, criado_em FROM evento"
            " WHERE nota_id=? ORDER BY id", (nota_id,))]
        dados = dict(nota)
        dados["componentes"] = json.loads(dados["componentes"])
        dados["itens"] = itens
        dados["grupos"] = agrupar(itens)
        dados["eventos"] = eventos
        dados["pendentes"] = sum(1 for i in itens if not i["decisao"])
        return dados

    def resumo(self, *, cnpj: str = "", competencia: str = "") -> list[dict]:
        """Totais por empresa e competencia. So nota APROVADA entra no valor
        a recolher; o que esta em revisao aparece a parte."""
        onde, valores = self._filtros(cnpj=cnpj, competencia=competencia)
        config = self.configuracao()
        percentual = Decimal(config["reducao_percentual"])
        linhas = self._conn.execute(
            "SELECT n.cnpj_dest, e.nome, e.regime, n.competencia,"
            " COUNT(DISTINCT n.id) AS notas,"
            " COUNT(DISTINCT CASE WHEN n.estado='aprovada' THEN n.id END)"
            "   AS aprovadas,"
            " COALESCE(SUM(CASE WHEN n.estado='aprovada'"
            "   AND i.decisao='calcular' THEN i.a_recolher END), 0)"
            "   AS aprovado,"
            " COALESCE(SUM(CASE WHEN n.estado='em_revisao'"
            "   AND i.decisao='calcular' THEN i.a_recolher END), 0)"
            "   AS em_revisao,"
            " COALESCE(SUM(CASE WHEN n.estado='aprovada'"
            "   AND i.decisao='calcular' AND i.finalidade='revenda'"
            "   THEN i.a_recolher END), 0) AS aprovado_revenda,"
            " COUNT(CASE WHEN i.decisao='' THEN 1 END) AS itens_pendentes,"
            " COUNT(CASE WHEN i.decisao='excluir' THEN 1 END) AS itens_fora"
            f" FROM nota n JOIN empresa e ON e.cnpj=n.cnpj_dest"
            f" LEFT JOIN item i ON i.nota_id=n.id{onde}"
            " GROUP BY n.cnpj_dest, n.competencia"
            " ORDER BY n.competencia DESC, e.nome", valores).fetchall()
        saida = []
        for linha in linhas:
            dados = dict(linha)
            dados["vencimento_referencia"] = ab.vencimento_de_referencia(
                linha["competencia"], config["dia_vencimento"]).isoformat()
            dados["reducao_percentual"] = config["reducao_percentual"]
            # Simulacao: so para Simples Nacional e so sobre compras para
            # revenda (antecipacao parcial). Elegibilidade e pagamento no
            # prazo NAO sao verificados aqui (pendencia P-04).
            if linha["regime"] == ab.REGIME_SIMPLES and linha["aprovado_revenda"]:
                reducao = ab.centavos(ab.reducao_simulada(
                    ab.de_centavos(linha["aprovado_revenda"]), percentual))
                dados["reducao_simulada"] = reducao
                dados["aprovado_com_reducao"] = linha["aprovado"] - reducao
            else:
                dados["reducao_simulada"] = None
                dados["aprovado_com_reducao"] = None
            saida.append(dados)
        return saida

    def itens_para_exportar(self, *, cnpj: str = "", competencia: str = "",
                            estado: str = "") -> list[dict]:
        onde, valores = self._filtros(cnpj=cnpj, competencia=competencia,
                                      estado=estado)
        linhas = self._conn.execute(
            "SELECT n.chave, n.numero, n.serie, n.dt_emissao, n.competencia,"
            " n.cnpj_dest, n.nome_dest, n.cnpj_emit, n.nome_emit,"
            " n.uf_origem, n.metodo, n.presuncao, n.estado,"
            " n.aprovada_por_login, n.aprovada_em, e.regime, i.*"
            f" FROM nota n JOIN empresa e ON e.cnpj=n.cnpj_dest"
            f" JOIN item i ON i.nota_id=n.id{onde}"
            " ORDER BY n.competencia, n.nome_dest, n.dt_emissao, n.id,"
            " i.ordem", valores).fetchall()
        return [self._item_dict(l) for l in linhas]

    def eventos_gerais(self, limite: int = 100) -> list[dict]:
        """Eventos sem nota (tabela, configuracao, regime) e exclusoes."""
        return [dict(l) for l in self._conn.execute(
            "SELECT tipo, detalhe, chave, usuario_login, criado_em FROM evento"
            " WHERE tipo NOT IN ('nota_importada','nota_alterada',"
            " 'itens_alterados','nota_aprovada','nota_reaberta')"
            " ORDER BY id DESC LIMIT ?", (max(1, min(int(limite), 500)),))]


def agrupar(itens: list[dict]) -> list[dict]:
    """Itens da nota por CFOP e aliquota do credito (o pedido original:
    "lista com produtos CFOP x com aliquota y"). A soma e' a dos itens, em
    centavos — nao uma conta refeita sobre a base agrupada."""
    grupos: dict[tuple, dict] = {}
    for item in itens:
        chave = (item["cfop"], item["aliquota_credito"], item["tipo_credito"])
        grupo = grupos.setdefault(chave, {
            "cfop": item["cfop"], "aliquota": item["aliquota_credito"],
            "tipo_credito": item["tipo_credito"], "itens": 0, "item_ids": [],
            "valor_operacao": 0, "a_recolher": 0, "pendentes": 0, "fora": 0})
        grupo["itens"] += 1
        grupo["item_ids"].append(item["id"])
        valor = ab.para_decimal(item["memoria"].get("valor_operacao"))
        if valor is not None:
            grupo["valor_operacao"] += ab.centavos(valor)
        if item["decisao"] == ab.DECISAO_CALCULAR:
            grupo["a_recolher"] += item["a_recolher"] or 0
        elif item["decisao"] == ab.DECISAO_EXCLUIR:
            grupo["fora"] += 1
        else:
            grupo["pendentes"] += 1
    return sorted(grupos.values(),
                  key=lambda g: (g["cfop"], g["aliquota"], g["tipo_credito"]))
