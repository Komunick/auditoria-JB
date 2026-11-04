"""Spec 023: delegacao individual, contexto, concorrencia e trilha sinteticos."""
from __future__ import annotations

import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditoria_fiscal.core.tarefas import ErroTarefas
from auditoria_fiscal.ferramentas.clientes_store import ConcorrenciaError
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.web.agendador import FUSO_SALVADOR


def ator(uid):
    return {"usuario_id": uid, "usuario_login": f"pessoa_sintetica_{uid}"}


def recusa(tipo, funcao, *args, **kwargs):
    try:
        funcao(*args, **kwargs)
    except tipo:
        return
    raise AssertionError(f"{funcao.__name__} deveria recusar")


@contextmanager
def cenario():
    with tempfile.TemporaryDirectory(prefix="delegacao_sintetica_") as pasta:
        ativos = set(range(1, 8))
        executores = set(range(1, 7))
        instante = [datetime(2026, 11, 4, 12, tzinfo=FUSO_SALVADOR)]
        banco = str(Path(pasta) / "clientes.db")

        def factory():
            return TarefasStore(banco, usuario_ativo=lambda uid: uid in ativos,
                                usuario_pode_executar=lambda uid: uid in executores,
                                agora_fn=lambda: instante[0])

        s = factory()
        try:
            cid = s.criar_cliente({"nome": "Empresa sintetica da delegacao"}, **ator(1))
            sid = s.salvar_setor({"nome": "Fiscal sintetico", "responsavel_usuario_id": 1}, **ator(1))["id"]
            s.definir_membros(sid, [1, 2, 3, 5, 6, 7], **ator(1))
            s.salvar_setor({"nome": "Outro setor sintetico", "responsavel_usuario_id": 4}, **ator(1))
            s.definir_carteira(cid, sid, 2, **ator(1))
            t = s.criar_avulsa({"cliente_id": cid, "setor_id": sid, "titulo": "Tarefa sintetica",
                                "responsavel_usuario_id": 2, "competencia": "2026-11",
                                "inicio": "2026-11-04", "vencimento": "2026-11-20",
                                "exige_conferencia": True}, **ator(1))
            yield s, t, sid, cid, ativos, executores, instante, factory
        finally:
            s.fechar()


def autorizar(s, t, executor=3):
    atual = s.obter_tarefa(t["id"])
    return s.autorizar_execucao(t["id"], executor, atual["revision"], "Apoio sintetico", **ator(2))


def pedido_decisao_revogacao():
    with cenario() as (s, t, *_):
        pedido = s.solicitar_execucao(t["id"], t["revision"], "Posso apoiar", **ator(3))
        assert pedido["estado"] == "pendente" and pedido["solicitante_usuario_id"] == 3
        assert pedido["revision"] == t["revision"] + 1
        assert not s.pode_executar_delegado(t, 3) and s.tarefas_autorizadas(3) == []
        assert s.obter_tarefa(t["id"])["responsavel_usuario_id"] == 2
        recusa(ErroTarefas, s.solicitar_execucao, t["id"], pedido["revision"], "Repetido", **ator(3))
        recusa(PermissionError, s.decidir_execucao, t["id"], pedido["id"], "aprovar", pedido["revision"], "Gestor nao e dono", **ator(1))
        aprovada = s.decidir_execucao(t["id"], pedido["id"], "aprovar", pedido["revision"], "Pode apoiar", **ator(2))
        assert aprovada["estado"] == "autorizada" and aprovada["vigente"] and aprovada["decidido_por"] == 2
        assert aprovada["revision"] == pedido["revision"] + 1
        assert s.pode_executar_delegado(t, 3) and s.tarefas_autorizadas(3) == [t["id"]]
        recusa(ErroTarefas, s.autorizar_execucao, t["id"], 3, aprovada["revision"], "Duplicada", **ator(2))
        outra = autorizar(s, t, 5)
        assert s.pode_executar_delegado(t, 3) and s.pode_executar_delegado(t, 5)
        revogada = s.decidir_execucao(t["id"], aprovada["id"], "revogar", outra["revision"], "Apoio encerrado", **ator(2))
        assert revogada["estado"] == "revogada" and not revogada["vigente"]
        assert not s.pode_executar_delegado(t, 3) and s.tarefas_autorizadas(3) == []
        assert s.pode_executar_delegado(t, 5)
        assert len(s.autorizacoes_execucao(t["id"])) == 2
        eventos = s.eventos(t["id"])
        assert [e["usuario_id"] for e in eventos[1:]] == [3, 2, 2, 2]
        assert all(e["tipo"] == "execucao" for e in eventos[1:])
        assert s.obter_tarefa(t["id"])["responsavel_usuario_id"] == 2


def escopos_e_historico():
    with cenario() as (s, t, sid, cid, *_):
        autorizar(s, t)
        ids = s.tarefas_autorizadas(3)
        assert s.listar_tarefas(escopo_usuario_id=3)["total"] == 0
        assert s.listar_tarefas(escopo_usuario_id=3, escopo_tarefas=ids)["total"] == 1
        assert s.listar_tarefas({"cliente_id": cid + 1}, escopo_tarefas=ids)["total"] == 0
        assert s.listar_tarefas(escopo_setores=[sid], escopo_tarefas=ids)["total"] == 1
        assert s.opcoes_filtros_tarefas(escopo_usuario_id=3, escopo_tarefas=ids)["total_escopo"] == 1
        painel = s.painel_tarefas(escopo_usuario_id=3, escopo_tarefas=ids)
        assert painel["resumo"]["total"] == painel["fila"]["total"] == 1
        atual = s.obter_tarefa(t["id"])
        atual = s.mudar_situacao(t["id"], "em_andamento", atual["revision"], **ator(3))
        atual = s.mudar_situacao(t["id"], "concluida", atual["revision"], **ator(3))
        assert atual["concluida_por"] == 3 and atual["responsavel_usuario_id"] == 2
        assert s.tarefas_autorizadas(3) == [t["id"]]
        assert not s.pode_executar_delegado(t, 3), "Mesmo DTO antigo nao pode executar tarefa encerrada"
        assert s.eventos(t["id"])[-1]["usuario_id"] == 3
        s.mudar_situacao(t["id"], "devolvida", atual["revision"], "Revisar", True, **ator(1))
        assert not s.pode_executar_delegado(t, 3) and s.tarefas_autorizadas(3) == []
        nova = autorizar(s, t)
        assert nova["vigente"] and s.pode_executar_delegado(t, 3)
        atual = s.obter_tarefa(t["id"])
        atual = s.mudar_situacao(t["id"], "dispensada", atual["revision"], "Dispensa sintetica", True, **ator(1))
        s.mudar_situacao(t["id"], "a_fazer", atual["revision"], "Retomar", True, **ator(1))
        assert not s.pode_executar_delegado(t, 3)


def permissoes_e_alvos():
    with cenario() as (s, t, sid, cid, ativos, executores, *_):
        for uid in (1, 3, 4):
            recusa(PermissionError, s.autorizar_execucao, t["id"], 5, t["revision"], "Sem autoridade", **ator(uid))
        for alvo in (2, 4, 7):
            recusa(ErroTarefas, s.autorizar_execucao, t["id"], alvo, t["revision"], "Alvo invalido", **ator(2))
        for uid in (2, 4, 7):
            recusa((ErroTarefas, PermissionError), s.solicitar_execucao, t["id"], t["revision"], "Pedido invalido", **ator(uid))
        ativos.remove(5)
        recusa(ErroTarefas, s.autorizar_execucao, t["id"], 5, t["revision"], "Inativo", **ator(2))
        assert s.obter_tarefa(t["id"])["revision"] == t["revision"]
        assert len(s.eventos(t["id"])) == 1 and not s.autorizacoes_execucao(t["id"])
        autorizar(s, t)
        executores.remove(3)
        assert not s.pode_executar_delegado(t, 3) and s.tarefas_autorizadas(3) == []
        executores.add(3)
        ativos.remove(2)
        assert not s.pode_executar_delegado(t, 3)
        ativos.add(2)
        s.salvar_setor({"ativo": False}, id=sid, **ator(1))
        assert not s.pode_executar_delegado(t, 3)
        s.salvar_setor({"ativo": True}, id=sid, **ator(1))
        assert not s.pode_executar_delegado(t, 3), "Reativar setor nao renova concessao antiga"


def contexto_nao_ressuscita():
    with cenario() as (s, t, sid, cid, *_):
        autorizar(s, t)
        s.definir_carteira(cid, sid, 5, **ator(1))
        s.definir_carteira(cid, sid, 2, **ator(1))
        assert not s.pode_executar_delegado(t, 3)
        autorizar(s, t)
        s.definir_membros(sid, [1, 2, 5, 6, 7], **ator(1))
        s.definir_membros(sid, [1, 2, 3, 5, 6, 7], **ator(1))
        assert not s.pode_executar_delegado(t, 3)
        autorizar(s, t)
        s.definir_carteira(cid, sid, 2, **ator(1))
        assert s.pode_executar_delegado(t, 3), "Salvar carteira sem troca nao invalida"


def substituicao_e_recusa():
    with cenario() as (s, t, sid, cid, ativos, executores, instante, _):
        antiga = autorizar(s, t)
        s.criar_substituicao({"titular_usuario_id": 2, "substituto_usuario_id": 6, "setor_id": sid,
                             "inicio": "2026-11-05", "fim": "2026-11-06", "motivo": "Ausencia sintetica"}, **ator(1))
        assert s.pode_executar_delegado(t, 3)
        instante[0] = instante[0].replace(day=5)
        assert not s.pode_executar_delegado(t, 3)
        atual = s.obter_tarefa(t["id"])
        recusa(PermissionError, s.autorizar_execucao, t["id"], 5, atual["revision"], "Titular ausente", **ator(2))
        nova = s.autorizar_execucao(t["id"], 3, atual["revision"], "Substituto autoriza", **ator(6))
        assert nova["vigente"] and s.eventos(t["id"])[-1]["substituindo_usuario_id"] == 2
        instante[0] = instante[0].replace(day=7)
        assert not s.pode_executar_delegado(t, 3)
        assert not s.autorizacoes_execucao(t["id"])[0]["vigente"]
        pedido = s.solicitar_execucao(t["id"], s.obter_tarefa(t["id"])["revision"], "Novo apoio", **ator(5))
        recusada = s.decidir_execucao(t["id"], pedido["id"], "recusar", pedido["revision"], "Nao necessario", **ator(2))
        assert recusada["estado"] == "recusada" and not recusada["vigente"]
        assert not s.pode_executar_delegado(t, 5)


def substituicoes_fora_da_ordem():
    with cenario() as (s, t, sid, cid, ativos, executores, instante, _):
        # O periodo futuro tem ID menor; o passado e cadastrado depois.
        for inicio, fim in (("2026-11-05", "2026-11-06"), ("2026-11-01", "2026-11-02")):
            s.criar_substituicao({"titular_usuario_id": 2, "substituto_usuario_id": 6, "setor_id": sid,
                                 "inicio": inicio, "fim": fim, "motivo": "Ausencia sintetica"}, **ator(1))
        autorizar(s, t)
        assert s.pode_executar_delegado(t, 3)
        # Nenhuma consulta ocorreu durante a ausencia; ainda assim nao renova.
        instante[0] = instante[0].replace(day=7)
        assert not s.pode_executar_delegado(t, 3)


def decisoes_e_limites():
    with cenario() as (s, t, sid, cid, ativos, executores, instante, factory):
        recusa(ErroTarefas, s.solicitar_execucao, t["id"], t["revision"], "x" * 4001, **ator(3))
        pedido = s.solicitar_execucao(t["id"], t["revision"], "x" * 4000, **ator(3))
        assert len(pedido["motivo"]) == 4000
        segunda = s.criar_avulsa({"cliente_id": cid, "setor_id": sid, "titulo": "Outra tarefa sintetica",
                                 "responsavel_usuario_id": 2, "inicio": "2026-11-04", "vencimento": "2026-11-20"}, **ator(1))
        recusa(LookupError, s.decidir_execucao, segunda["id"], pedido["id"], "aprovar", segunda["revision"], "Outra tarefa", **ator(2))
        s.definir_membros(sid, [1, 2, 5, 6, 7], **ator(1))
        s.definir_membros(sid, [1, 2, 3, 5, 6, 7], **ator(1))
        recusa(ErroTarefas, s.decidir_execucao, t["id"], pedido["id"], "aprovar", pedido["revision"], "Contexto mudou", **ator(2))
        recusada = s.decidir_execucao(t["id"], pedido["id"], "recusar", pedido["revision"], "x" * 4000, **ator(2))
        assert len(recusada["decisao_motivo"]) == 4000
        concedida = autorizar(s, t)
        atual = s.obter_tarefa(t["id"])
        atual = s.mudar_situacao(t["id"], "em_andamento", atual["revision"], **ator(3))
        atual = s.mudar_situacao(t["id"], "concluida", atual["revision"], **ator(3))
        assert s.tarefas_autorizadas(3) == [t["id"]]
        revogada = s.decidir_execucao(t["id"], concedida["id"], "revogar", atual["revision"], "Encerrar acesso", **ator(2))
        assert revogada["estado"] == "revogada" and s.tarefas_autorizadas(3) == []
        # Consultas nao alteram dados, e ausencia de integracao falha fechada.
        mudancas = s.conn.total_changes
        s.autorizacoes_execucao(t["id"])
        s.tarefas_autorizadas(3)
        assert s.conn.total_changes == mudancas
        banco = s.conn.execute("PRAGMA database_list").fetchone()[2]
        sem_permissao = TarefasStore(banco, agora_fn=lambda: instante[0])
        try:
            recusa(PermissionError, sem_permissao.autorizar_execucao, segunda["id"], 3,
                   segunda["revision"], "Sem callback", **ator(2))
        finally:
            sem_permissao.fechar()


def atomicidade_concorrencia_migracao():
    with cenario() as (s, t, sid, cid, ativos, executores, instante, factory):
        # Falha ao gravar evento reverte autorizacao e revision.
        s.conn.execute("CREATE TRIGGER falha_sintetica BEFORE INSERT ON tarefa_evento BEGIN SELECT RAISE(ABORT,'falha sintetica'); END")
        recusa(ErroTarefas, autorizar, s, t)
        assert s.obter_tarefa(t["id"])["revision"] == t["revision"]
        assert not s.autorizacoes_execucao(t["id"])
        s.conn.execute("DROP TRIGGER falha_sintetica")

        def concorrer(executor):
            outro = factory()
            try:
                outro.autorizar_execucao(t["id"], executor, t["revision"], "Concorrencia sintetica", **ator(2))
                return "ok"
            except ConcorrenciaError:
                return "conflito"
            finally:
                outro.fechar()

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(concorrer, [3, 5])) == ["conflito", "ok"]
        assert len(s.autorizacoes_execucao(t["id"])) == 1
        assert len(s.eventos(t["id"])) == 2
        recusa(ConcorrenciaError, s.mudar_situacao, t["id"], "em_andamento", t["revision"], **ator(2))
        # Reabrir o store aplica migracao idempotente e nao reduz schema superior.
        s.conn.execute("PRAGMA user_version=99")
        outro = factory()
        try:
            assert outro.conn.execute("PRAGMA user_version").fetchone()[0] == 99
            assert outro.obter_tarefa(t["id"])["responsavel_usuario_id"] == 2
            assert outro.eventos(t["id"]) == s.eventos(t["id"])
            assert outro.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not outro.conn.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            outro.fechar()


def main():
    cenarios = [pedido_decisao_revogacao, escopos_e_historico, permissoes_e_alvos,
                contexto_nao_ressuscita, substituicao_e_recusa, substituicoes_fora_da_ordem,
                decisoes_e_limites, atomicidade_concorrencia_migracao]
    for teste in cenarios:
        teste()
    print(json.dumps({"resultado": "ok", "cenarios": [t.__name__ for t in cenarios],
                      "dados": "sinteticos"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
