"""Persistencia do Patrimonio: SQLite dedicado, trilha append-only.

Banco proprio (`dados_web/patrimonio.db`) pelo mesmo motivo do
`conciliacao.db`: ciclo de vida, trilha e backup proprios. Patrimonio e
conciliacao fiscal nao tem relacao entre si — juntar num banco so acoplaria
dominios que evoluem em ritmos diferentes.

Sem FastAPI, sem sessao HTTP: caminho e identidade chegam por injecao, e a
identidade chega como SNAPSHOT primitivo (`usuario_id`, `usuario_login`).

Tres garantias moram no SQL, nao apenas no Python:

- **Um responsavel ativo por bem**, por indice parcial unico. Conferir em
  Python e inserir depois deixaria janela para duas atribuicoes simultaneas
  criarem dois donos — e aí ninguem sabe com quem esta o equipamento.
- **Movimentacao append-only** e **etiqueta imutavel**, por trigger. A
  etiqueta esta colada no equipamento: renumerar quebra o vinculo com o mundo
  fisico.
- **Um inventario aberto por vez**, tambem por indice parcial unico.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from ..core import patrimonio as pt

VERSAO_SCHEMA = 1


class ConcorrenciaError(Exception):
    """O bem mudou desde que o cliente o leu."""

    def __init__(self, revision_atual: int):
        super().__init__("Registro desatualizado.")
        self.revision_atual = revision_atual


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Movimento:
    """Resultado de uma movimentacao aplicada."""

    bem_id: int
    tipo: str
    situacao_anterior: str
    situacao_nova: str
    movimentacao_id: int
    revision: int


_TABELAS = """
CREATE TABLE IF NOT EXISTS local (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  descricao TEXT NOT NULL DEFAULT '',
  ativo INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pessoa (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cpf TEXT,
  setor TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  ativo INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bem (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  etiqueta TEXT NOT NULL UNIQUE,
  numero_etiqueta INTEGER NOT NULL,
  pai_id INTEGER REFERENCES bem(id),
  tipo TEXT NOT NULL,
  descricao TEXT NOT NULL,
  marca TEXT NOT NULL DEFAULT '',
  modelo TEXT NOT NULL DEFAULT '',
  numero_serie TEXT,
  valor_aquisicao INTEGER,
  data_aquisicao TEXT NOT NULL DEFAULT '',
  nota_fiscal TEXT NOT NULL DEFAULT '',
  conservacao TEXT NOT NULL DEFAULT 'bom',
  situacao TEXT NOT NULL DEFAULT 'disponivel',
  local_id INTEGER REFERENCES local(id),
  observacao TEXT NOT NULL DEFAULT '',
  revision INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS responsabilidade (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bem_id INTEGER NOT NULL REFERENCES bem(id),
  pessoa_id INTEGER NOT NULL REFERENCES pessoa(id),
  iniciada_em TEXT NOT NULL,
  encerrada_em TEXT,
  observacao_inicio TEXT NOT NULL DEFAULT '',
  observacao_fim TEXT NOT NULL DEFAULT '',
  registrada_por_id INTEGER NOT NULL DEFAULT 0,
  registrada_por_login TEXT NOT NULL,
  encerrada_por_id INTEGER NOT NULL DEFAULT 0,
  encerrada_por_login TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS movimentacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bem_id INTEGER NOT NULL REFERENCES bem(id),
  tipo TEXT NOT NULL,
  situacao_anterior TEXT NOT NULL DEFAULT '',
  situacao_nova TEXT NOT NULL DEFAULT '',
  pessoa_id INTEGER REFERENCES pessoa(id),
  local_id INTEGER REFERENCES local(id),
  observacao TEXT NOT NULL DEFAULT '',
  usuario_id INTEGER NOT NULL DEFAULT 0,
  usuario_login TEXT NOT NULL,
  criada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventario (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  estado TEXT NOT NULL DEFAULT 'aberto',
  aberto_em TEXT NOT NULL,
  fechado_em TEXT NOT NULL DEFAULT '',
  aberto_por_login TEXT NOT NULL,
  fechado_por_login TEXT NOT NULL DEFAULT '',
  observacao TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS inventario_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inventario_id INTEGER NOT NULL REFERENCES inventario(id),
  bem_id INTEGER NOT NULL REFERENCES bem(id),
  situacao_esperada TEXT NOT NULL,
  local_esperado_id INTEGER REFERENCES local(id),
  resultado TEXT NOT NULL DEFAULT 'pendente',
  observacao TEXT NOT NULL DEFAULT '',
  conferido_em TEXT NOT NULL DEFAULT '',
  conferido_por_login TEXT NOT NULL DEFAULT '',
  UNIQUE (inventario_id, bem_id)
);
"""

_INDICES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_bem_etiqueta ON bem(etiqueta);
CREATE INDEX IF NOT EXISTS idx_bem_situacao ON bem(situacao, tipo);
CREATE INDEX IF NOT EXISTS idx_bem_pai ON bem(pai_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bem_serie
  ON bem(numero_serie) WHERE numero_serie IS NOT NULL AND numero_serie <> '';

-- A garantia de UM responsavel ativo por bem mora aqui, no banco. Conferir em
-- Python e inserir depois deixaria janela para duas atribuicoes simultaneas
-- criarem dois donos do mesmo equipamento.
CREATE UNIQUE INDEX IF NOT EXISTS idx_resp_ativa
  ON responsabilidade(bem_id) WHERE encerrada_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_resp_pessoa
  ON responsabilidade(pessoa_id, encerrada_em);

CREATE INDEX IF NOT EXISTS idx_mov_bem ON movimentacao(bem_id, id);
CREATE INDEX IF NOT EXISTS idx_mov_tipo ON movimentacao(tipo, criada_em);

-- Um inventario aberto por vez, pelo mesmo motivo.
CREATE UNIQUE INDEX IF NOT EXISTS idx_inv_aberto
  ON inventario(estado) WHERE estado = 'aberto';
CREATE INDEX IF NOT EXISTS idx_inv_item
  ON inventario_item(inventario_id, resultado);
"""

_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_mov_sem_update
BEFORE UPDATE ON movimentacao BEGIN
  SELECT RAISE(ABORT, 'Movimentacao e imutavel: UPDATE nao e permitido.');
END;
CREATE TRIGGER IF NOT EXISTS trg_mov_sem_delete
BEFORE DELETE ON movimentacao BEGIN
  SELECT RAISE(ABORT, 'Movimentacao e imutavel: DELETE nao e permitido.');
END;

-- A etiqueta esta colada no equipamento. Trocar a etiqueta de um bem faria
-- alguem ler o adesivo na mesa e encontrar outro item no sistema.
CREATE TRIGGER IF NOT EXISTS trg_bem_etiqueta_imutavel
BEFORE UPDATE ON bem
WHEN NEW.etiqueta IS NOT OLD.etiqueta
     OR NEW.numero_etiqueta IS NOT OLD.numero_etiqueta BEGIN
  SELECT RAISE(ABORT, 'Etiqueta e imutavel: ela esta colada no equipamento.');
END;
CREATE TRIGGER IF NOT EXISTS trg_bem_sem_delete
BEFORE DELETE ON bem BEGIN
  SELECT RAISE(ABORT,
    'Bem nao e excluido: registre a BAIXA, que preserva o historico.');
END;

-- Hierarquia de dois niveis: o pai nao pode ser um periferico.
CREATE TRIGGER IF NOT EXISTS trg_bem_dois_niveis
BEFORE INSERT ON bem
WHEN NEW.pai_id IS NOT NULL
     AND (SELECT pai_id FROM bem WHERE id = NEW.pai_id) IS NOT NULL BEGIN
  SELECT RAISE(ABORT, 'Periferico nao pode ter periferico: dois niveis.');
END;

-- Sessao de inventario fechada nao volta atras.
CREATE TRIGGER IF NOT EXISTS trg_inv_fechado_imutavel
BEFORE UPDATE ON inventario
WHEN OLD.estado = 'fechado' BEGIN
  SELECT RAISE(ABORT, 'Inventario fechado e imutavel.');
END;
"""


class PatrimonioStore:
    """Uma instancia por thread: conexao SQLite nao atravessa thread."""

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

    def fechar(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def contar(self, tabela: str) -> int:
        if tabela not in {"local", "pessoa", "bem", "responsabilidade",
                          "movimentacao", "inventario", "inventario_item"}:
            raise ValueError(f"Tabela desconhecida: {tabela}")
        return self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {tabela}").fetchone()["n"]

    # ------------------------------------------------------------------
    # Cadastros de apoio

    def criar_local(self, nome: str, descricao: str = "") -> int:
        nome = pt.texto_obrigatorio(nome, "Nome do local", maximo=80)
        try:
            cur = self._conn.execute(
                "INSERT INTO local(nome, descricao, criado_em)"
                " VALUES(?,?,?)", (nome, descricao.strip()[:300], agora()))
        except sqlite3.IntegrityError as exc:
            raise pt.ErroPatrimonio(
                "LOCAL_DUPLICADO", f"Já existe um local chamado '{nome}'."
            ) from exc
        return int(cur.lastrowid)

    def criar_pessoa(self, nome: str, *, cpf: str = "", setor: str = "",
                     email: str = "") -> int:
        nome = pt.texto_obrigatorio(nome, "Nome", maximo=120)
        documento = pt.normalizar_cpf(cpf)
        try:
            cur = self._conn.execute(
                "INSERT INTO pessoa(nome, cpf, setor, email, criado_em)"
                " VALUES(?,?,?,?,?)",
                (nome, documento or None, setor.strip()[:80],
                 email.strip()[:120], agora()))
        except sqlite3.IntegrityError as exc:
            raise pt.ErroPatrimonio(
                "CPF_DUPLICADO",
                "Já existe uma pessoa cadastrada com este CPF.") from exc
        return int(cur.lastrowid)

    def desativar_pessoa(self, pessoa_id: int) -> dict:
        """Desliga o colaborador SEM encerrar responsabilidades.

        Quem esta com um equipamento continua respondendo por ele ate a
        devolucao ser registrada — encerrar sozinho faria o bem sumir do
        controle sem ninguem ter devolvido nada.
        """
        self._conn.execute("UPDATE pessoa SET ativo=0 WHERE id=?", (pessoa_id,))
        pendentes = [dict(l) for l in self._conn.execute(
            "SELECT b.id, b.etiqueta, b.descricao FROM responsabilidade r"
            " JOIN bem b ON b.id = r.bem_id"
            " WHERE r.pessoa_id=? AND r.encerrada_em IS NULL", (pessoa_id,))]
        return {"pessoa_id": pessoa_id, "bens_pendentes": pendentes}

    # ------------------------------------------------------------------
    # Bens

    def criar_bem(self, dados: dict, *, usuario_id: int = 0,
                  usuario_login: str = "") -> dict:
        validado = pt.validar_bem(dados)
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            periferico = validado.pai_id is not None
            if periferico:
                pai = conn.execute("SELECT id, pai_id, situacao FROM bem"
                                   " WHERE id=?",
                                   (validado.pai_id,)).fetchone()
                if pai is None:
                    raise pt.ErroPatrimonio(
                        pt.HIERARQUIA_INVALIDA, "Bem pai não encontrado.")
                pt.validar_hierarquia(pai["pai_id"] is not None)

            prefixo = pt.PREFIXO_PERIFERICO if periferico else pt.PREFIXO_BEM
            proximo = int(conn.execute(
                "SELECT COALESCE(MAX(numero_etiqueta), 0) + 1 AS n FROM bem"
                " WHERE etiqueta LIKE ?", (f"{prefixo}-%",)).fetchone()["n"])
            etiqueta = pt.formatar_etiqueta(proximo, periferico=periferico)

            cur = conn.execute(
                "INSERT INTO bem(etiqueta, numero_etiqueta, pai_id, tipo,"
                " descricao, marca, modelo, numero_serie, valor_aquisicao,"
                " data_aquisicao, nota_fiscal, conservacao, situacao,"
                " local_id, observacao, revision, criado_em, atualizado_em)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (etiqueta, proximo, validado.pai_id, validado.tipo,
                 validado.descricao, validado.marca, validado.modelo,
                 validado.numero_serie or None, validado.valor_aquisicao,
                 validado.data_aquisicao, validado.nota_fiscal,
                 validado.conservacao, pt.SITUACAO_DISPONIVEL,
                 validado.local_id, validado.observacao, 1, agora(), agora()))
            bem_id = int(cur.lastrowid)

            self._movimentar_sql(
                conn, bem_id, pt.MOV_AQUISICAO, "", pt.SITUACAO_DISPONIVEL,
                local_id=validado.local_id, observacao="Cadastro inicial.",
                usuario_id=usuario_id, usuario_login=usuario_login)
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "numero_serie" in str(exc):
                raise pt.ErroPatrimonio(
                    "SERIE_DUPLICADA",
                    "Já existe um bem com este número de série.") from exc
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"id": bem_id, "etiqueta": etiqueta}

    def obter_bem(self, bem_id: int) -> dict:
        linha = self._conn.execute("SELECT * FROM bem WHERE id=?",
                                   (bem_id,)).fetchone()
        if linha is None:
            raise LookupError("Bem não encontrado.")
        return dict(linha)

    def obter_por_etiqueta(self, etiqueta: str) -> dict:
        normalizada = pt.normalizar_etiqueta(etiqueta)
        linha = self._conn.execute("SELECT * FROM bem WHERE etiqueta=?",
                                   (normalizada,)).fetchone()
        if linha is None:
            raise LookupError("Etiqueta não encontrada.")
        return dict(linha)

    def editar_bem(self, bem_id: int, dados: dict, *, revision: int | None = None,
                   usuario_login: str = "") -> dict:
        """Edita os campos descritivos. Etiqueta e situacao NAO entram aqui.

        Situacao so muda por movimentacao, para nunca existir mudanca de estado
        sem a linha correspondente na trilha.
        """
        validado = pt.validar_bem(dados)
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            atual = conn.execute("SELECT * FROM bem WHERE id=?",
                                 (bem_id,)).fetchone()
            if atual is None:
                raise LookupError("Bem não encontrado.")
            if revision is not None and int(revision) != int(atual["revision"]):
                raise ConcorrenciaError(int(atual["revision"]))
            if atual["situacao"] == pt.SITUACAO_BAIXADO:
                raise pt.ErroPatrimonio(
                    pt.BEM_BAIXADO, "Bem baixado não é editado.")
            conn.execute(
                "UPDATE bem SET tipo=?, descricao=?, marca=?, modelo=?,"
                " numero_serie=?, valor_aquisicao=?, data_aquisicao=?,"
                " nota_fiscal=?, conservacao=?, observacao=?,"
                " revision=revision+1, atualizado_em=? WHERE id=?",
                (validado.tipo, validado.descricao, validado.marca,
                 validado.modelo, validado.numero_serie or None,
                 validado.valor_aquisicao, validado.data_aquisicao,
                 validado.nota_fiscal, validado.conservacao,
                 validado.observacao, agora(), bem_id))
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise pt.ErroPatrimonio(
                "SERIE_DUPLICADA",
                "Já existe um bem com este número de série.") from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"id": bem_id, "revision": int(atual["revision"]) + 1}

    # ------------------------------------------------------------------
    # Movimentacoes

    def _movimentar_sql(self, conn, bem_id: int, tipo: str, anterior: str,
                        nova: str, *, pessoa_id: int | None = None,
                        local_id: int | None = None, observacao: str = "",
                        usuario_id: int = 0, usuario_login: str = "") -> int:
        cur = conn.execute(
            "INSERT INTO movimentacao(bem_id, tipo, situacao_anterior,"
            " situacao_nova, pessoa_id, local_id, observacao, usuario_id,"
            " usuario_login, criada_em) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (bem_id, tipo, anterior, nova, pessoa_id, local_id,
             observacao.strip()[:1000], usuario_id, usuario_login, agora()))
        return int(cur.lastrowid)

    def movimentar(self, bem_id: int, tipo: str, *, pessoa_id: int | None = None,
                   local_id: int | None = None, observacao: str = "",
                   revision: int | None = None, usuario_id: int = 0,
                   usuario_login: str = "") -> Movimento:
        """Aplica uma movimentacao: situacao, responsabilidade e trilha juntas.

        Tudo numa transacao so. Gravar a situacao e depois a trilha deixaria
        janela para um bem mudar de estado sem ninguem saber quem mandou.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            bem = conn.execute("SELECT * FROM bem WHERE id=?",
                               (bem_id,)).fetchone()
            if bem is None:
                raise LookupError("Bem não encontrado.")
            if revision is not None and int(revision) != int(bem["revision"]):
                raise ConcorrenciaError(int(bem["revision"]))

            transicao = pt.validar_transicao(tipo, bem["situacao"])
            if transicao.exige_pessoa and not pessoa_id:
                raise pt.ErroPatrimonio(
                    pt.CAMPO_OBRIGATORIO,
                    f"'{pt.MOVIMENTOS[tipo]}' exige informar a pessoa.")
            if transicao.exige_justificativa and not observacao.strip():
                raise pt.ErroPatrimonio(
                    pt.JUSTIFICATIVA_OBRIGATORIA,
                    "A baixa exige justificativa: ela é definitiva.")

            if tipo == pt.MOV_ATRIBUICAO:
                self._abrir_responsabilidade(conn, bem_id, pessoa_id,
                                             observacao, usuario_id,
                                             usuario_login)
            elif tipo in (pt.MOV_DEVOLUCAO, pt.MOV_BAIXA):
                self._encerrar_responsabilidade(conn, bem_id, observacao,
                                                usuario_id, usuario_login)

            destino_local = local_id if local_id is not None else bem["local_id"]
            conn.execute(
                "UPDATE bem SET situacao=?, local_id=?, revision=revision+1,"
                " atualizado_em=? WHERE id=?",
                (transicao.situacao_nova, destino_local, agora(), bem_id))
            movimentacao_id = self._movimentar_sql(
                conn, bem_id, tipo, transicao.situacao_anterior,
                transicao.situacao_nova, pessoa_id=pessoa_id,
                local_id=local_id, observacao=observacao,
                usuario_id=usuario_id, usuario_login=usuario_login)
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "idx_resp_ativa" in str(exc):
                raise pt.ErroPatrimonio(
                    "JA_TEM_RESPONSAVEL",
                    "Este bem já está sob responsabilidade de alguém. "
                    "Registre a devolução antes de atribuir a outra pessoa."
                ) from exc
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise

        return Movimento(bem_id=bem_id, tipo=tipo,
                         situacao_anterior=transicao.situacao_anterior,
                         situacao_nova=transicao.situacao_nova,
                         movimentacao_id=movimentacao_id,
                         revision=int(bem["revision"]) + 1)

    def _abrir_responsabilidade(self, conn, bem_id: int, pessoa_id: int,
                                observacao: str, usuario_id: int,
                                usuario_login: str) -> None:
        pessoa = conn.execute("SELECT id, ativo FROM pessoa WHERE id=?",
                              (pessoa_id,)).fetchone()
        if pessoa is None:
            raise pt.ErroPatrimonio(pt.CAMPO_OBRIGATORIO,
                                    "Pessoa não encontrada.")
        if not pessoa["ativo"]:
            raise pt.ErroPatrimonio(
                "PESSOA_INATIVA",
                "Colaborador desligado não recebe novo bem.")
        conn.execute(
            "INSERT INTO responsabilidade(bem_id, pessoa_id, iniciada_em,"
            " observacao_inicio, registrada_por_id, registrada_por_login)"
            " VALUES(?,?,?,?,?,?)",
            (bem_id, pessoa_id, agora(), observacao.strip()[:500],
             usuario_id, usuario_login))

    def _encerrar_responsabilidade(self, conn, bem_id: int, observacao: str,
                                   usuario_id: int, usuario_login: str) -> None:
        conn.execute(
            "UPDATE responsabilidade SET encerrada_em=?, observacao_fim=?,"
            " encerrada_por_id=?, encerrada_por_login=?"
            " WHERE bem_id=? AND encerrada_em IS NULL",
            (agora(), observacao.strip()[:500], usuario_id, usuario_login,
             bem_id))

    def responsavel_atual(self, bem_id: int) -> dict | None:
        linha = self._conn.execute(
            "SELECT r.*, p.nome, p.setor FROM responsabilidade r"
            " JOIN pessoa p ON p.id = r.pessoa_id"
            " WHERE r.bem_id=? AND r.encerrada_em IS NULL", (bem_id,)
        ).fetchone()
        return dict(linha) if linha else None

    # ------------------------------------------------------------------
    # Inventario

    def abrir_inventario(self, *, usuario_login: str = "",
                         observacao: str = "") -> int:
        """Abre a sessao CONGELANDO o universo de bens ativos.

        Bem cadastrado depois nao entra: senao a taxa de localizacao mudaria
        sozinha no meio da conferencia.
        """
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT INTO inventario(estado, aberto_em, aberto_por_login,"
                " observacao) VALUES('aberto',?,?,?)",
                (agora(), usuario_login, observacao.strip()[:500]))
            inventario_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO inventario_item(inventario_id, bem_id,"
                " situacao_esperada, local_esperado_id)"
                " SELECT ?, id, situacao, local_id FROM bem WHERE situacao<>?",
                (inventario_id, pt.SITUACAO_BAIXADO))
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise pt.ErroPatrimonio(
                "INVENTARIO_ABERTO",
                "Já existe um inventário aberto. Feche-o antes de abrir "
                "outro.") from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return inventario_id

    def conferir(self, inventario_id: int, bem_id: int, resultado: str, *,
                 observacao: str = "", usuario_login: str = "") -> dict:
        if resultado not in ("localizado", "nao_localizado", "divergente"):
            raise pt.ErroPatrimonio("RESULTADO_INVALIDO",
                                    f"Resultado desconhecido: {resultado}.")
        sessao = self._conn.execute("SELECT estado FROM inventario WHERE id=?",
                                    (inventario_id,)).fetchone()
        if sessao is None:
            raise LookupError("Inventário não encontrado.")
        if sessao["estado"] != "aberto":
            raise pt.ErroPatrimonio("INVENTARIO_FECHADO",
                                    "Este inventário já foi fechado.")
        cur = self._conn.execute(
            "UPDATE inventario_item SET resultado=?, observacao=?,"
            " conferido_em=?, conferido_por_login=?"
            " WHERE inventario_id=? AND bem_id=?",
            (resultado, observacao.strip()[:500], agora(), usuario_login,
             inventario_id, bem_id))
        if cur.rowcount == 0:
            raise LookupError(
                "Este bem não faz parte do inventário aberto (foi cadastrado "
                "depois da abertura).")
        return {"inventario_id": inventario_id, "bem_id": bem_id,
                "resultado": resultado}

    def fechar_inventario(self, inventario_id: int, *,
                          usuario_login: str = "") -> dict:
        self._conn.execute(
            "UPDATE inventario SET estado='fechado', fechado_em=?,"
            " fechado_por_login=? WHERE id=? AND estado='aberto'",
            (agora(), usuario_login, inventario_id))
        return self.resumo_inventario(inventario_id)

    def resumo_inventario(self, inventario_id: int) -> dict:
        sessao = self._conn.execute("SELECT * FROM inventario WHERE id=?",
                                    (inventario_id,)).fetchone()
        if sessao is None:
            raise LookupError("Inventário não encontrado.")
        contagens = {l["resultado"]: l["n"] for l in self._conn.execute(
            "SELECT resultado, COUNT(*) AS n FROM inventario_item"
            " WHERE inventario_id=? GROUP BY resultado", (inventario_id,))}
        return {**dict(sessao), "contagens": contagens,
                "total": sum(contagens.values())}

    def inventario_aberto(self) -> dict | None:
        linha = self._conn.execute(
            "SELECT * FROM inventario WHERE estado='aberto'").fetchone()
        return dict(linha) if linha else None

    # ------------------------------------------------------------------
    # Consultas

    _FILTROS = ("texto", "tipo", "situacao", "local_id", "pessoa_id",
                "incluir_baixados")

    def _condicoes(self, filtros: dict) -> tuple[str, list]:
        desconhecidos = sorted(set(filtros) - set(self._FILTROS))
        if desconhecidos:
            raise ValueError(
                "Filtro desconhecido: " + ", ".join(desconhecidos) + ".")
        onde: list[str] = []
        valores: list = []

        texto = str(filtros.get("texto") or "").strip()
        if texto:
            padrao = "%" + (texto.replace("\\", "\\\\").replace("%", "\\%")
                            .replace("_", "\\_").upper()) + "%"
            onde.append("(UPPER(b.descricao) LIKE ? ESCAPE '\\'"
                        " OR UPPER(b.etiqueta) LIKE ? ESCAPE '\\'"
                        " OR UPPER(COALESCE(b.numero_serie,'')) LIKE ? ESCAPE '\\'"
                        " OR UPPER(b.marca) LIKE ? ESCAPE '\\')")
            valores.extend([padrao] * 4)

        tipo = str(filtros.get("tipo") or "").strip()
        if tipo:
            onde.append("b.tipo = ?")
            valores.append(tipo)

        situacao = str(filtros.get("situacao") or "").strip()
        if situacao:
            if situacao not in pt.SITUACOES:
                raise ValueError(f"Situação desconhecida: {situacao}.")
            onde.append("b.situacao = ?")
            valores.append(situacao)

        if filtros.get("local_id"):
            onde.append("b.local_id = ?")
            valores.append(int(filtros["local_id"]))

        if filtros.get("pessoa_id"):
            onde.append(
                "EXISTS (SELECT 1 FROM responsabilidade r"
                " WHERE r.bem_id = b.id AND r.encerrada_em IS NULL"
                " AND r.pessoa_id = ?)")
            valores.append(int(filtros["pessoa_id"]))

        # Baixados somem por padrao: eles poluem a lista operacional, mas
        # continuam consultaveis quando pedidos.
        if not filtros.get("incluir_baixados"):
            onde.append("b.situacao <> ?")
            valores.append(pt.SITUACAO_BAIXADO)

        return ((" WHERE " + " AND ".join(onde)) if onde else "", valores)

    def listar(self, *, pagina: int = 1, limite: int = 50, **filtros) -> dict:
        onde, valores = self._condicoes(filtros)
        limite = max(1, min(int(limite or 50), 200))
        pagina = max(1, int(pagina or 1))
        total = int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM bem b" + onde,
            valores).fetchone()["n"])
        paginas = max(1, -(-total // limite))
        pagina = min(pagina, paginas)
        linhas = self._conn.execute(
            "SELECT b.*, l.nome AS local_nome,"
            " (SELECT p.nome FROM responsabilidade r JOIN pessoa p"
            "   ON p.id = r.pessoa_id"
            "  WHERE r.bem_id = b.id AND r.encerrada_em IS NULL)"
            "  AS responsavel_nome,"
            " (SELECT r.pessoa_id FROM responsabilidade r"
            "  WHERE r.bem_id = b.id AND r.encerrada_em IS NULL)"
            "  AS responsavel_id"
            " FROM bem b LEFT JOIN local l ON l.id = b.local_id" + onde +
            " ORDER BY b.numero_etiqueta LIMIT ? OFFSET ?",
            [*valores, limite, (pagina - 1) * limite]).fetchall()
        return {"itens": [dict(l) for l in linhas], "total": total,
                "pagina": pagina, "limite": limite, "paginas": paginas}

    def resumo(self, **filtros) -> dict:
        onde, valores = self._condicoes(filtros)
        linha = self._conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(b.situacao='disponivel') AS disponiveis,"
            " SUM(b.situacao='em_uso') AS em_uso,"
            " SUM(b.situacao='manutencao') AS manutencao,"
            " SUM(b.situacao='emprestado') AS emprestados,"
            " COALESCE(SUM(b.valor_aquisicao), 0) AS valor_total"
            " FROM bem b" + onde, valores).fetchone()
        baixados = int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM bem WHERE situacao='baixado'"
        ).fetchone()["n"])
        return {chave: int(linha[chave] or 0) for chave in (
            "total", "disponiveis", "em_uso", "manutencao", "emprestados",
            "valor_total")} | {"baixados": baixados}

    def detalhar(self, bem_id: int) -> dict:
        bem = self.obter_bem(bem_id)
        bem["local_nome"] = ""
        if bem["local_id"]:
            local = self._conn.execute("SELECT nome FROM local WHERE id=?",
                                       (bem["local_id"],)).fetchone()
            bem["local_nome"] = local["nome"] if local else ""
        bem["responsavel"] = self.responsavel_atual(bem_id)
        bem["responsabilidades"] = [dict(l) for l in self._conn.execute(
            "SELECT r.*, p.nome AS pessoa_nome FROM responsabilidade r"
            " JOIN pessoa p ON p.id = r.pessoa_id"
            " WHERE r.bem_id=? ORDER BY r.id DESC", (bem_id,))]
        bem["movimentacoes"] = [dict(l) for l in self._conn.execute(
            "SELECT m.*, p.nome AS pessoa_nome FROM movimentacao m"
            " LEFT JOIN pessoa p ON p.id = m.pessoa_id"
            " WHERE m.bem_id=? ORDER BY m.id DESC", (bem_id,))]
        bem["perifericos"] = [dict(l) for l in self._conn.execute(
            "SELECT id, etiqueta, descricao, situacao FROM bem"
            " WHERE pai_id=? ORDER BY numero_etiqueta", (bem_id,))]
        return bem

    def listar_pessoas(self, *, apenas_ativas: bool = False) -> list[dict]:
        sql = ("SELECT p.*, (SELECT COUNT(*) FROM responsabilidade r"
               " WHERE r.pessoa_id = p.id AND r.encerrada_em IS NULL)"
               " AS bens_ativos FROM pessoa p")
        if apenas_ativas:
            sql += " WHERE p.ativo=1"
        return [dict(l) for l in self._conn.execute(sql + " ORDER BY p.nome")]

    def listar_locais(self) -> list[dict]:
        return [dict(l) for l in self._conn.execute(
            "SELECT l.*, (SELECT COUNT(*) FROM bem b WHERE b.local_id = l.id"
            "  AND b.situacao <> 'baixado') AS bens"
            " FROM local l ORDER BY l.nome")]
