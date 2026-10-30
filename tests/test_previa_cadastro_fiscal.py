"""Spec 020: consulta cadastral mínima, sem criação, migração ou escrita."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditoria_fiscal.core.documentos_br import dv_cnpj
from auditoria_fiscal.ferramentas import previa_cadastro_fiscal as previa


def documento(numero):
    base = f"{numero:08d}0001"
    return base + dv_cnpj(base)


def criar_banco(caminho, quantidade=1, *, wal=False):
    conn = sqlite3.connect(caminho, isolation_level=None)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.executescript("""
        CREATE TABLE cliente (
          id INTEGER PRIMARY KEY, nome TEXT NOT NULL, documento TEXT,
          contato_nome TEXT NOT NULL, situacao TEXT NOT NULL, revision INTEGER,
          observacao TEXT NOT NULL DEFAULT 'Não expor');
        CREATE TABLE segredo (cifra BLOB);
        INSERT INTO segredo VALUES(X'010203');
        PRAGMA user_version=3;
    """)
    conn.executemany("INSERT INTO cliente(id,nome,documento,contato_nome,situacao,revision) VALUES(?,?,?,?,?,?)",
                     [(i, f"Empresa sintética {i}", documento(i), "Contato sintético", "ativo", 1)
                      for i in range(1, quantidade + 1)])
    return conn


def falha_cadastro(caminho, documentos):
    try:
        previa.consultar_cadastro(caminho, documentos)
    except previa.CadastroIndisponivel as exc:
        assert "cadastro" in str(exc).lower()
        assert str(caminho) not in str(exc), "Não revelar caminho interno"
    else:
        raise AssertionError("Cadastro existente incompatível foi tratado como vazio")


def test_ausente_e_incompativel(pasta):
    caminho = pasta / "diretorio-nao-criado" / "clientes.db"
    resposta = previa.consultar_cadastro(caminho, [documento(1)])
    assert resposta["disponivel"] is False and resposta["clientes"] == []
    assert not caminho.parent.exists(), "Consulta criou pasta ou banco"
    assert datetime.fromisoformat(resposta["consultado_em"]).utcoffset() == timedelta(0)

    corrompido = pasta / "corrompido.db"
    corrompido.write_bytes(b"conteudo sintetico invalido")
    antes = corrompido.read_bytes()
    falha_cadastro(corrompido, [])
    assert corrompido.read_bytes() == antes
    incompat = pasta / "incompativel.db"
    conn = sqlite3.connect(incompat)
    conn.execute("CREATE TABLE cliente(id INTEGER, nome TEXT, documento TEXT)")
    conn.commit()
    conn.close()
    antes = incompat.read_bytes()
    falha_cadastro(incompat, [documento(1)])
    assert incompat.read_bytes() == antes


def test_minimo_parametrizado_e_sem_escrita(pasta):
    # Espaços e sinais reservados provam que o caminho vira uma URI codificada.
    caminho = pasta / "cadastro # revisão %.db"
    writer = criar_banco(caminho, 3)
    writer.execute("INSERT INTO cliente(id,nome,documento,contato_nome,situacao,revision) VALUES(99,'Inválido','00000000000000','','ativo',1)")
    writer.close()
    antes = caminho.read_bytes()
    original = sqlite3.connect
    chamadas, consultas, acessos = [], [], []

    class Observada(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            consultas.append((sql, tuple(parameters)))
            return super().execute(sql, parameters)

    def autorizar(acao, arg1, arg2, banco, origem):
        acessos.append((acao, arg1, arg2))
        if acao in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                    sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_ALTER_TABLE,
                    sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_ATTACH}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conexoes = []
    def conectar(*args, **kwargs):
        chamadas.append((args, dict(kwargs)))
        kwargs["factory"] = Observada
        conn = original(*args, **kwargs)
        conn.set_authorizer(autorizar)
        conexoes.append(conn)
        return conn

    with patch.object(previa.sqlite3, "connect", side_effect=conectar):
        resposta = previa.consultar_cadastro(caminho, [documento(2), documento(2), "00000000000000", "123", "' OR 1=1 --", None, 123, documento(1)])
    assert resposta["disponivel"] is True
    assert {c["id"] for c in resposta["clientes"]} == {1, 2}
    campos = {"id", "nome", "documento", "contato_nome", "situacao", "revision"}
    assert all(set(c) == campos for c in resposta["clientes"])
    assert caminho.read_bytes() == antes, "Leitura modificou o banco cadastral"
    assert len(chamadas) == 1 and chamadas[0][1]["uri"] is True
    uri = chamadas[0][0][0]
    assert "mode=ro" in uri and "immutable" not in uri
    assert "%23" in uri and "%25" in uri and "%20" in uri
    assert not any(a[0] == sqlite3.SQLITE_READ and a[1] == "segredo" for a in acessos)
    assert not any(a[0] == sqlite3.SQLITE_READ and a[1] == "cliente" and a[2] == "observacao" for a in acessos)
    parametros = [v for _, values in consultas for v in values]
    assert set(parametros) == {documento(1), documento(2)} and len(parametros) == 2
    for conn in conexoes:
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            pass
        else:
            raise AssertionError("Conexão de leitura ficou aberta")


def test_snapshot_wal_e_lotes(pasta):
    caminho = pasta / "cadastro-wal.db"
    writer = criar_banco(caminho, 501, wal=True)
    try:
        assert Path(str(caminho) + "-wal").exists()
        # Registro novo vive no WAL ainda não checkpointado e deve ser visto.
        writer.execute("INSERT INTO cliente(id,nome,documento,contato_nome,situacao,revision) VALUES(502,'Somente WAL',?,'','ativo',1)", (documento(502),))
        original = sqlite3.connect
        lotes = []
        class Concorrente(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if parameters:
                    lotes.append(tuple(parameters))
                    if len(lotes) == 2:
                        writer.execute("UPDATE cliente SET nome='Nome após snapshot',revision=2 WHERE id=502")
                return super().execute(sql, parameters)

        def conectar(*args, **kwargs):
            kwargs["factory"] = Concorrente
            return original(*args, **kwargs)
        with patch.object(previa.sqlite3, "connect", side_effect=conectar):
            resposta = previa.consultar_cadastro(caminho, [documento(i) for i in range(1, 503)])
        assert len(resposta["clientes"]) == 502
        assert len(lotes) >= 2 and all(len(lote) <= 400 for lote in lotes)
        antigo = next(c for c in resposta["clientes"] if c["id"] == 502)
        assert antigo["nome"] == "Somente WAL" and antigo["revision"] == 1, "Lotes misturaram revisões de snapshots distintos"
        assert writer.execute("SELECT nome FROM cliente WHERE id=502").fetchone()[0] == "Nome após snapshot"
        assert writer.execute("PRAGMA user_version").fetchone()[0] == 3
        assert writer.execute("SELECT count(*) FROM cliente").fetchone()[0] == 502
    finally:
        writer.close()


def main():
    with tempfile.TemporaryDirectory(prefix="previa_cadastro_020_") as temporario:
        pasta = Path(temporario)
        test_ausente_e_incompativel(pasta)
        test_minimo_parametrizado_e_sem_escrita(pasta)
        test_snapshot_wal_e_lotes(pasta)
    print("OK - previa cadastral: leitura mínima, URI segura, ausente/incompatível, snapshot WAL e lotes sem escrita")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
