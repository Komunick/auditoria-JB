"""Spec 013: integridade, migracao, concorrencia e rastreabilidade (dados sinteticos)."""
from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import ExitStack
from datetime import date, datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.ferramentas.clientes_store import ClientesStore, ConcorrenciaError
from auditoria_fiscal.ferramentas import clientes_store as legado
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.core.clientes import ErroClientes

U = {"usuario_id": 1, "usuario_login": "gestor_sintetico"}
HOJE = date(2026, 10, 27)


def recusa(tipo, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except tipo:
        return
    raise AssertionError(f"{fn.__name__} deveria recusar")


def main():
    with tempfile.TemporaryDirectory(prefix="tarefas_sintetico_") as pasta, ExitStack() as recursos:
        original = os.path.join(pasta, "schema1.db")
        with sqlite3.connect(original) as conn:
            conn.executescript(legado._TABELAS + legado._INDICES + legado._TRIGGERS)
            conn.execute("INSERT INTO cliente(nome,criado_em,atualizado_em) VALUES('Legado sintetico','2026-01-01','2026-01-01')")
            conn.execute("INSERT INTO certificado(cliente_id,fim,origem,criado_em,atualizado_em) VALUES(1,'2027-01-01','manual','2026-01-01','2026-01-01')")
            conn.execute("INSERT INTO segredo(cliente_id,campo,uid,cifra,nonce,chave_id,atualizado_em) VALUES(1,'sefaz','uid-sintetico',x'010203',x'040506','chave-sintetica','2026-01-01')")
            conn.execute("PRAGMA user_version=1")
            assert 'contato_email' not in {r[1] for r in conn.execute('PRAGMA table_info(cliente)')}
        conn.close()
        migrado = TarefasStore(original)
        recursos.callback(migrado.fechar)
        assert migrado.conn.execute('SELECT cifra FROM segredo').fetchone()[0] == bytes([1, 2, 3])
        assert migrado.conn.execute('SELECT fim FROM certificado').fetchone()[0] == '2027-01-01'
        assert migrado.conn.execute('SELECT contato_email FROM cliente').fetchone()[0] == ''
        assert migrado.conn.execute('PRAGMA user_version').fetchone()[0] == 2
        # Fixture descartavel de um banco schema 2 anterior ao campo revision.
        # Apenas a montagem desta fixture remove a coluna; a migracao e aditiva.
        migrado.conn.execute('ALTER TABLE ajuste_cliente DROP COLUMN revision')
        migrado.fechar()
        migrado = TarefasStore(original)
        recursos.callback(migrado.fechar)
        assert 'revision' in {r['name'] for r in migrado.conn.execute('PRAGMA table_info(ajuste_cliente)')}
        migrado.fechar()
        db = os.path.join(pasta, "clientes.db")
        # Banco da spec 012, com cliente e trilha a preservar na migracao.
        clientes = ClientesStore(db)
        recursos.callback(clientes.fechar)
        ids = [clientes.criar_cliente({"nome": f"Empresa sintetica {n}"}, **U)
               for n in range(1, 5)]
        clientes.mudar_situacao(ids[2], "inativo", "Fixture", **U)
        clientes.mudar_situacao(ids[3], "baixado", "Fixture", **U)
        antes = clientes.contar("alteracao")
        clientes._conn.execute("PRAGMA user_version=1")
        clientes.fechar()
        ativos = {1, 2, 3, 4}
        s = TarefasStore(db, usuario_ativo=lambda uid: uid in ativos,
                        agora_fn=lambda: datetime(2026, 10, 27, 12, tzinfo=timezone.utc))
        recursos.callback(s.fechar)
        assert s._conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert s._conn.execute("SELECT count(*) FROM cliente").fetchone()[0] == 4
        assert s._conn.execute("SELECT count(*) FROM alteracao").fetchone()[0] == antes
        c = ClientesStore(db)
        recursos.callback(c.fechar)
        assert c._conn.execute("PRAGMA user_version").fetchone()[0] == 2
        c.editar_cliente(ids[0], {**c.obter(ids[0]), "contato_nome": "Contato sintetico",
                                "contato_email": "teste@example.invalid"}, revision=1, **U)
        assert c.obter(ids[0])["contato_email"] == "teste@example.invalid"
        recusa(ErroClientes, c.editar_cliente, ids[0], {**c.obter(ids[0]), "contato_email": "a,b@example.invalid"}, **U)
        c.fechar()

        # A interface pode manter a trava entre autorizacao e mutacao.
        # O store nao confirma a transacao externa nem deixa efeitos parciais.
        trilha_antes = s.conn.execute("SELECT count(*) FROM alteracao").fetchone()[0]
        s.conn.execute("BEGIN IMMEDIATE")
        s.salvar_setor({"nome": "Setor transitorio", "responsavel_usuario_id": 1}, **U)
        assert s.conn.in_transaction
        recusa(ValueError, s.salvar_setor,
               {"nome": "Setor invalido", "responsavel_usuario_id": 1, "membros": [1, 999]}, **U)
        assert s.conn.in_transaction
        assert [x["nome"] for x in s.listar_setores()] == ["Setor transitorio"]
        s.conn.execute("ROLLBACK")
        assert not s.listar_setores()
        assert s.conn.execute("SELECT count(*) FROM alteracao").fetchone()[0] == trilha_antes

        setor = s.salvar_setor({"nome": "Fiscal sintetico", "responsavel_usuario_id": 1}, **U)
        sid = setor["id"]
        s.definir_membros(sid, [1, 2, 3], **U)
        assert len(s.listar_setores()[0]["membros"]) == 3
        s.criar_substituicao({"titular_usuario_id": 1, "substituto_usuario_id": 2,
                             "setor_id": sid, "inicio": "2026-10-20", "fim": "2026-10-30",
                             "motivo": "Ausencia sintetica"}, **U)
        for dia, esperado in [(19, 1), (20, 2), (30, 2), (31, 1)]:
            assert s.responsavel_efetivo(sid, 1, date(2026, 10, dia)) == esperado
        assert s.setores_responsavel(1, HOJE) == []
        assert s.setores_responsavel(2, HOJE) == [sid]
        recusa(ValueError, s.criar_substituicao,
               {"titular_usuario_id": 1, "substituto_usuario_id": 3,
                "inicio": "2026-10-25", "fim": "2026-11-01", "motivo": "Sobreposta"}, **U)
        regime1 = s.salvar_caracteristica({"grupo": "Regime", "nome": "Regime A",
                                          "exclusiva_no_grupo": True}, **U)["id"]
        regime2 = s.salvar_caracteristica({"grupo": "Regime", "nome": "Regime B",
                                          "exclusiva_no_grupo": True}, **U)["id"]
        s.definir_caracteristicas([ids[0]], [regime1], **U)
        s.definir_caracteristicas([ids[0]], [regime2], **U)
        assert [x["id"] for x in s.ficha_cliente(ids[0])["caracteristicas"]] == [regime2]
        recusa(ValueError, s.definir_caracteristicas, [ids[0]], [regime1, regime2], **U)
        s.definir_carteira(ids[0], sid, 1, **U)
        obrig = s.salvar_obrigacao({"nome": "Obrigacao sintetica", "setor_id": sid,
                                  "periodicidade": "mensal",
                                  "regra_vencimento": {"tipo": "dia_mes_seguinte", "dia": 20},
                                  "condicao": {}, "exige_conferencia": True}, **U)
        oid = obrig["id"]
        assert s.previa_geracao("2026-10", setor_id=sid, hoje=HOJE)["contagens"]["novas"] == 2
        geracao = s.gerar("2026-10", setor_id=sid, hoje=HOJE, **U)
        assert geracao["contagens"]["criadas"] == 2
        assert s.gerar("2026-10", setor_id=sid, hoje=HOJE, **U)["contagens"]["criadas"] == 0
        lista = s.listar_tarefas(todas=True, hoje=HOJE)
        assert lista["total"] == 2
        t = next(x for x in lista["itens"] if x["cliente_id"] == ids[0])
        fila = next(x for x in lista["itens"] if x["cliente_id"] == ids[1])
        assert fila["responsavel_usuario_id"] is None
        assert t["responsavel_usuario_id"] == 1 and t["responsavel_efetivo_id"] == 2
        assert s.listar_tarefas(escopo_usuario_id=1, hoje=HOJE)["total"] == 0
        assert s.listar_tarefas(escopo_usuario_id=2, hoje=HOJE)["total"] == 1
        assert s.listar_tarefas(escopo_setores=[sid], hoje=HOJE)["total"] == 2
        assert s.listar_tarefas(hoje=HOJE)["total"] == 0
        t = s.mudar_situacao(t["id"], "em_andamento", revision=t["revision"], **U)
        recusa(ConcorrenciaError, s.comentar, t["id"], "Desatualizado", revision=1, **U)
        t = s.mudar_situacao(t["id"], "concluida", revision=t["revision"], **U)
        assert t["concluida_por"] == 1 and not t["fora_do_prazo"]
        s.definir_carteira(ids[0], sid, 3, **U)
        assert s.obter_tarefa(t["id"])["responsavel_usuario_id"] == 1
        t = s.mudar_situacao(t["id"], "conferida", revision=t["revision"],
                             responsavel_setor=True, usuario_id=2, usuario_login="substituto_sintetico")
        assert t["conferida_por"] == 2 and t["conferida_substituindo"] == 1
        recusa(sqlite3.IntegrityError, s._conn.execute, "DELETE FROM tarefa_evento")
        recusa(sqlite3.IntegrityError, s._conn.execute, "UPDATE tarefa_evento SET comentario='x'")
        s.salvar_ajuste({"cliente_id": ids[2], "obrigacao_id": oid, "tipo": "incluir",
                        "valido_de": "2026-11-01", "valido_ate": "2026-11-30", "motivo": "Excecao"}, **U)
        s.salvar_ajuste({"cliente_id": ids[1], "obrigacao_id": oid, "tipo": "excluir",
                        "valido_de": "2026-11-01", "valido_ate": "2026-11-30", "motivo": "Excecao"}, **U)
        s.salvar_ajuste({"cliente_id": ids[0], "obrigacao_id": oid, "tipo": "vencimento",
                        "regra_vencimento": {"tipo": "dia_mes_seguinte", "dia": 10},
                        "valido_de": "2026-11-01", "valido_ate": "2026-11-30", "motivo": "Excecao"}, **U)
        p = s.previa_geracao("2026-11", setor_id=sid, hoje=HOJE)
        assert {x["cliente_id"] for x in p["tarefas"]} == {ids[0], ids[2]}
        assert next(x for x in p["tarefas"] if x["cliente_id"] == ids[0])["vencimento"] == "2026-12-10"
        assert s.previa_geracao("2026-12", setor_id=sid, hoje=HOJE)["contagens"]["novas"] == 2
        # Dois escritores simultaneos geram uma unica agenda.
        def gerar_concorrente(_):
            outro = TarefasStore(db)
            try:
                return outro.gerar("2027-01", setor_id=sid, hoje=HOJE, disparo="automatico", **U)
            finally:
                outro.fechar()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(gerar_concorrente, range(2)))
        assert sum(r["contagens"]["criadas"] for r in resultados) == 2
        assert s._conn.execute("SELECT count(*) FROM geracao WHERE competencia='2027-01' AND disparo='automatico'").fetchone()[0] == 1
        # Usuario desativado nao recebe novas distribuicoes, mas preserva historico.
        ativos.remove(3)
        s.gerar("2027-02", setor_id=sid, hoje=HOJE, **U)
        tt = s.listar_tarefas({"competencia": "2027-02", "cliente_id": ids[0]}, todas=True)["itens"][0]
        assert tt["responsavel_usuario_id"] is None
        recusa(ValueError, s.definir_carteira, ids[0], sid, 3, **U)
        ativos.add(3)
        # Alteracao de catalogo nao reescreve origem/vencimento de tarefas existentes.
        antigo = s.obter_tarefa(t["id"])
        s.salvar_obrigacao({**obrig, "nome": "Obrigacao revista"}, id=oid, revision=1, **U)
        assert s.obter_tarefa(t["id"])["origem"] == antigo["origem"]
        recusa(ConcorrenciaError, s.salvar_obrigacao, obrig, id=oid, revision=1, **U)
        # Importacao atomicamente confirma cliente, contato, caracteristicas e carteira.
        linha = {"cliente_id": ids[1], "contato_nome": "Contato teste",
                 "contato_email": "contato@example.invalid", "caracteristica_ids": [regime1],
                 "origem": {"aba": "Carteira", "linha": 3, "colunas": {"contato_email": "E3"}}}
        s.importar_carteira([linha], setor_id=sid, responsavel_usuario_id=2,
                           hash_arquivo="a" * 64, nome_arquivo="sintetica.xlsx", **U)
        assert s.ficha_cliente(ids[1])["contato_email"] == "contato@example.invalid"
        recusa(ValueError, s.importar_carteira, [{**linha, "contato_nome": "Nao gravar"},
                {**linha, "cliente_id": ids[0], "contato_email": "invalido"}], setor_id=sid,
                responsavel_usuario_id=2, hash_arquivo="b" * 64, nome_arquivo="sintetica.xlsx", **U)
        assert s.ficha_cliente(ids[1])["contato_nome"] == "Contato teste"
        assert s.reservar_envio(2, "2026-10-27", "teste@example.invalid", {"tarefas": 2})
        assert not s.reservar_envio(2, "2026-10-27", "teste@example.invalid", {"tarefas": 2})
        s.finalizar_envio(2, "2026-10-27", "ok")
        assert s.listar_envios()[0]["resultado"] == "ok"
        # Comentarios e redistribuicao nao reiniciam o relogio de espera do cliente.
        avulsa = s.criar_avulsa({"cliente_id": ids[0], "setor_id": sid, "titulo": "Avulsa sintetica",
                                 "vencimento": "2026-11-30", "responsavel_usuario_id": 3}, **U)
        avulsa = s.mudar_situacao(avulsa["id"], "aguardando_cliente", avulsa["revision"], **U)
        desde = avulsa["aguardando_desde"]
        s.agora_fn = lambda: datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        avulsa = s.comentar(avulsa["id"], "Cobranca registrada", avulsa["revision"], **U)
        assert avulsa["aguardando_desde"] == desde
        s.redistribuir([{"id": avulsa["id"], "revision": avulsa["revision"]}], 2, "Troca sintetica", **U)
        assert s.obter_tarefa(avulsa["id"])["aguardando_desde"] == desde
        # Uma alteracao apos a previa nao pode ampliar o que foi confirmado.
        previa = s.previa_geracao("2028-01", setor_id=sid, hoje=HOJE)
        obrig2 = s.salvar_obrigacao({"nome": "Outra obrigacao sintetica", "setor_id": sid,
                                  "periodicidade": "mensal", "regra_vencimento": {"tipo": "dia_mes_seguinte", "dia": 15}}, **U)
        recusa(ValueError, s.gerar, "2028-01", setor_id=sid, hoje=HOJE, previa_esperada=previa, **U)
        assert s.listar_tarefas({"competencia": "2028-01"}, todas=True)["total"] == 0
        # Lote inteiro reverte se uma revision estiver desatualizada.
        abertas = s.listar_tarefas({"competencia": "2027-01"}, todas=True)["itens"]
        revisions = [{"id": x["id"], "revision": x["revision"]} for x in abertas]
        recusa(ConcorrenciaError, s.redistribuir, [revisions[0], {**revisions[1], "revision": 999}], 2, "Redistribuicao", **U)
        assert s.obter_tarefa(abertas[0]["id"])["revision"] == abertas[0]["revision"]
        # Falha no evento reverte a mudanca; nao ha tarefa sem trilha.
        s._conn.execute("CREATE TRIGGER teste_evento_falha BEFORE INSERT ON tarefa_evento BEGIN SELECT RAISE(ABORT,'sintetico'); END")
        recusa(ValueError, s.mudar_situacao, abertas[0]["id"], "em_andamento", abertas[0]["revision"], **U)
        assert s.obter_tarefa(abertas[0]["id"])["situacao"] == "a_fazer"
        s._conn.execute("DROP TRIGGER teste_evento_falha")
        # Substituto desativado tambem sai de novas distribuicoes; a fila fica visivel.
        s.definir_carteira(ids[0], sid, 1, **U)
        ativos.remove(2)
        sem_sub = s.previa_geracao("2028-02", setor_id=sid, hoje=HOJE)
        assert all(x["responsavel_usuario_id"] is None for x in sem_sub["tarefas"] if x["cliente_id"] == ids[0])
        ativos.add(2)
        # Uma excecao permanente pode ser corrigida com revisao e historico.
        exclusao = s.salvar_ajuste({"cliente_id": ids[0], "obrigacao_id": oid,
                                    "tipo": "excluir", "motivo": "Configuracao sintetica inicial"}, **U)
        tarefa_anterior = s.obter_tarefa(t["id"])
        assert not any(x["cliente_id"] == ids[0] and x["obrigacao_id"] == oid
                       for x in s.previa_geracao("2028-03", setor_id=sid, hoje=HOJE)["tarefas"])
        revisado = s.salvar_ajuste({"tipo": "incluir", "motivo": "Correcao sintetica confirmada"},
                                  id=exclusao["id"], revision=1, **U)
        assert revisado["revision"] == 2 and revisado["tipo"] == "incluir"
        assert any(x["cliente_id"] == ids[0] and x["obrigacao_id"] == oid
                   for x in s.previa_geracao("2028-03", setor_id=sid, hoje=HOJE)["tarefas"])
        recusa(ConcorrenciaError, s.salvar_ajuste, {"tipo": "excluir", "motivo": "Versao velha"},
               id=exclusao["id"], revision=1, **U)
        recusa(ValueError, s.salvar_ajuste, {"cliente_id": ids[1], "motivo": "Troca indevida"},
               id=exclusao["id"], revision=2, **U)
        assert s.obter_tarefa(t["id"])["origem"] == tarefa_anterior["origem"]
        assert s.obter_tarefa(t["id"])["vencimento"] == tarefa_anterior["vencimento"]
        historico = s.conn.execute("SELECT antes,depois FROM alteracao WHERE entidade='cliente' AND entidade_id=? AND campo='ajuste' ORDER BY id DESC LIMIT 1", (ids[0],)).fetchone()
        assert json.loads(historico["antes"])["tipo"] == "excluir"
        assert json.loads(historico["depois"])["tipo"] == "incluir"
        s.gerar("2028-04", setor_id=sid, hoje=HOJE, **U)
        gerada = next(x for x in s.listar_tarefas({"competencia": "2028-04", "cliente_id": ids[0]}, todas=True)["itens"] if x["obrigacao_id"] == oid)
        s.salvar_ajuste({"tipo": "vencimento", "valido_de": "2028-01-01",
                         "regra_vencimento": {"tipo": "dia_mes_seguinte", "dia": 5},
                         "motivo": "Novo prazo sintetico"}, id=exclusao["id"], revision=2, **U)
        proxima = next(x for x in s.previa_geracao("2028-05", setor_id=sid, hoje=HOJE)["tarefas"]
                       if x["cliente_id"] == ids[0] and x["obrigacao_id"] == oid)
        assert proxima["vencimento"] == "2028-06-05"
        assert s.obter_tarefa(gerada["id"])["vencimento"] == gerada["vencimento"] == "2028-05-20"
        assert s.obter_tarefa(gerada["id"])["origem"] == gerada["origem"]
        # Um feriado calculado desmarcado permanece assim apos reabrir o banco.
        natal = next(f for f in s.feriados(2026) if f["data"] == "2026-12-25")
        s.salvar_feriado({**natal, "sem_expediente": False}, **U)
        s.fechar()
        s = TarefasStore(db)
        recursos.callback(s.fechar)
        assert not next(f for f in s.feriados(2026) if f["data"] == "2026-12-25")["sem_expediente"]
        s.fechar()
    print("OK - tarefas_store: migracao, escopos, regras, substituicoes, trilha, importacao e concorrencia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
