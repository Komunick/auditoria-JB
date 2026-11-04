"""Recorrencia e carteira em dois meses, com banco e relogio sinteticos."""
from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auditoria_fiscal.core.tarefas import ErroTarefas
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.web.agendador import Agendador, FUSO_SALVADOR


GESTOR = {"usuario_id": 1, "usuario_login": "gestor_sintetico"}
ANALISTA = {"usuario_id": 2, "usuario_login": "analista_sintetico"}


@contextmanager
def cenario():
    instante = [datetime(2026, 11, 1, 8, tzinfo=FUSO_SALVADOR)]
    with tempfile.TemporaryDirectory(prefix="recorrencia_sintetica_") as pasta:
        banco = str(Path(pasta) / "clientes.db")

        def factory():
            return TarefasStore(banco, usuario_ativo=lambda uid: uid in {1, 2, 3},
                                agora_fn=lambda: instante[0])

        # Nao consulta variaveis SMTP nem abre conexoes de rede.
        envios_falsos = []

        def enviar(store, usuarios, hoje):
            envios_falsos.append(hoje.isoformat())
            return {"simulado": True}

        s = factory()
        try:
            setor = s.salvar_setor({"nome": "Fiscal sintetico", "responsavel_usuario_id": 1}, **GESTOR)
            s.definir_membros(setor["id"], [1, 2, 3], **GESTOR)
            agendador = Agendador(factory, lambda: [], relogio=lambda: instante[0], enviar=enviar)
            yield s, setor["id"], instante, agendador, envios_falsos
        finally:
            s.fechar()


def obrigacao_mensal(s, sid):
    return s.salvar_obrigacao({
        "nome": "Obrigacao mensal sintetica", "setor_id": sid,
        "periodicidade": "mensal", "condicao": {}, "exige_conferencia": False,
        "regra_vencimento": {"tipo": "dia_mes_seguinte", "dia": 20},
    }, **GESTOR)


def confirmar_previa(s, sid, competencia):
    previa = s.previa_geracao(competencia, setor_id=sid)
    return s.gerar(competencia, setor_id=sid, previa_esperada=previa, **GESTOR)


def recorrencia_e_carteira():
    with cenario() as (s, sid, instante, agendador, envios):
        clientes = [s.criar_cliente({"nome": f"Empresa sintetica {n}"}, **GESTOR) for n in range(1, 4)]
        s.definir_carteira(clientes[0], sid, 2, **GESTOR)
        s.definir_carteira(clientes[1], sid, 3, **GESTOR)
        obrigacao = obrigacao_mensal(s, sid)
        avulsa = s.criar_avulsa({
            "cliente_id": clientes[0], "setor_id": sid, "titulo": "Pedido avulso sintetico",
            "responsavel_usuario_id": 2, "competencia": "2026-11",
            "inicio": "2026-11-01", "vencimento": "2026-11-20",
        }, **GESTOR)

        agendador.executar_ciclo()
        agendador.executar_ciclo()
        novembro = s.listar_tarefas({"competencia": "2026-11"}, todas=True)["itens"]
        recorrentes = {t["cliente_id"]: t for t in novembro if t["obrigacao_id"] == obrigacao["id"]}
        assert len(novembro) == 4 and len(recorrentes) == 3
        assert {t["vencimento"] for t in recorrentes.values()} == {"2026-12-20"}
        assert recorrentes[clientes[0]]["responsavel_usuario_id"] == 2
        assert recorrentes[clientes[1]]["responsavel_usuario_id"] == 3
        assert recorrentes[clientes[2]]["responsavel_usuario_id"] is None
        assert s.listar_tarefas(escopo_setores=[sid])["total"] == 4
        assert s.listar_tarefas(escopo_usuario_id=2)["total"] == 2
        assert s.listar_tarefas(escopo_usuario_id=3)["total"] == 1
        assert confirmar_previa(s, sid, "2026-11")["contagens"]["criadas"] == 0

        encerrada = recorrentes[clientes[0]]
        encerrada = s.mudar_situacao(encerrada["id"], "em_andamento", encerrada["revision"], **ANALISTA)
        encerrada = s.mudar_situacao(encerrada["id"], "concluida", encerrada["revision"], **ANALISTA)
        historico_encerrado = s.eventos(encerrada["id"])
        assert [e["para"] for e in historico_encerrado] == ["a_fazer", "em_andamento", "concluida"]
        assert historico_encerrado[-1]["usuario_id"] == 2

        # Trocar carteira redistribui abertas, inclusive a avulsa, sem copiar tarefas.
        s.definir_carteira(clientes[0], sid, 3, **GESTOR)
        s.definir_carteira(clientes[1], sid, 2, **GESTOR)
        s.definir_carteira(clientes[2], sid, 2, **GESTOR)
        assert s.listar_tarefas(todas=True)["total"] == 4
        assert s.obter_tarefa(encerrada["id"]) == encerrada
        assert s.eventos(encerrada["id"]) == historico_encerrado
        assert s.obter_tarefa(avulsa["id"])["responsavel_usuario_id"] == 3
        for cid in clientes[1:]:
            atualizada = s.obter_tarefa(recorrentes[cid]["id"])
            assert atualizada["responsavel_usuario_id"] == 2
            assert atualizada["revision"] == recorrentes[cid]["revision"] + 1
            assert s.eventos(atualizada["id"])[-1]["tipo"] == "responsavel"

        instante[0] = datetime(2026, 12, 1, 8, tzinfo=FUSO_SALVADOR)
        agendador.executar_ciclo()
        agendador.executar_ciclo()
        dezembro = s.listar_tarefas({"competencia": "2026-12"}, todas=True)["itens"]
        assert len(dezembro) == 3
        assert {t["cliente_id"] for t in dezembro} == set(clientes)
        assert {t["obrigacao_id"] for t in dezembro} == {obrigacao["id"]}
        assert {t["vencimento"] for t in dezembro} == {"2027-01-20"}
        assert {t["situacao"] for t in dezembro} == {"a_fazer"}
        assert {t["id"] for t in dezembro}.isdisjoint(t["id"] for t in novembro)
        assert {t["cliente_id"]: t["responsavel_usuario_id"] for t in dezembro} == {
            clientes[0]: 3, clientes[1]: 2, clientes[2]: 2,
        }
        assert confirmar_previa(s, sid, "2026-12")["contagens"]["criadas"] == 0
        assert s.listar_tarefas(todas=True)["total"] == 7
        assert len(s.listar_obrigacoes(sid)) == 1
        assert s.conn.execute("SELECT count(*) FROM tarefa WHERE obrigacao_id IS NULL").fetchone()[0] == 1
        assert s.conn.execute("SELECT count(*) FROM geracao WHERE disparo='automatico'").fetchone()[0] == 2
        assert s.eventos(encerrada["id"]) == historico_encerrado
        preservada = s.obter_tarefa(encerrada["id"])
        for campo in ("situacao", "responsavel_usuario_id", "concluida_por", "concluida_em", "origem", "revision"):
            assert preservada[campo] == encerrada[campo]
        assert envios == ["2026-11-01", "2026-11-01", "2026-12-01", "2026-12-01"]
        return {"obrigacoes": 1, "clientes": 3, "tarefas_recorrentes_novembro": 3,
                "tarefas_recorrentes_dezembro": 3, "tarefas_avulsas": 1,
                "tarefas_duplicadas": 0, "historico_encerrado_preservado": True}


def completar_mes_ja_processado():
    with cenario() as (s, sid, instante, agendador, _):
        cid = s.criar_cliente({"nome": "Empresa sintetica cadastrada antes da obrigacao"}, **GESTOR)
        s.definir_carteira(cid, sid, 2, **GESTOR)
        agendador.executar_ciclo()
        registro_vazio = dict(s.conn.execute("SELECT * FROM geracao").fetchone())
        assert json.loads(registro_vazio["contagens"])["criadas"] == 0

        obrigacao_mensal(s, sid)
        agendador.executar_ciclo()
        assert s.listar_tarefas(todas=True)["total"] == 0
        previa = s.previa_geracao("2026-11", setor_id=sid)
        assert previa["contagens"]["novas"] == 1
        assert s.listar_tarefas(todas=True)["total"] == 0, "A previa nao grava tarefas"

        # Uma carteira alterada depois da previa exige nova revisao antes de confirmar.
        s.definir_carteira(cid, sid, 3, **GESTOR)
        try:
            s.gerar("2026-11", setor_id=sid, previa_esperada=previa, **GESTOR)
        except ErroTarefas as erro:
            assert erro.codigo == "PREVIA_DESATUALIZADA"
        else:
            raise AssertionError("Confirmacao com previa desatualizada deveria ser recusada")
        assert s.listar_tarefas(todas=True)["total"] == 0
        resultado = confirmar_previa(s, sid, "2026-11")
        assert resultado["contagens"]["criadas"] == 1
        assert resultado["tarefas"][0]["responsavel_usuario_id"] == 3
        assert confirmar_previa(s, sid, "2026-11")["contagens"]["criadas"] == 0
        agendador.executar_ciclo()
        assert s.listar_tarefas(todas=True)["total"] == 1
        assert dict(s.conn.execute("SELECT * FROM geracao WHERE id=?", (registro_vazio["id"],)).fetchone()) == registro_vazio

        instante[0] = datetime(2026, 12, 1, 8, tzinfo=FUSO_SALVADOR)
        agendador.executar_ciclo()
        agendador.executar_ciclo()
        assert s.listar_tarefas({"competencia": "2026-12"}, todas=True)["total"] == 1
        assert s.listar_tarefas(todas=True)["total"] == 2
        return {"automatica_vazia_preservada": True, "previa_desatualizada_recusada": True,
                "complementacao_manual_novembro": 1, "automatica_dezembro": 1}


def main():
    resultado = {"recorrencia_e_carteira": recorrencia_e_carteira(),
                 "mes_ja_processado": completar_mes_ja_processado(),
                 "resultado": "ok", "dados": "sinteticos", "smtp": "enviador falso"}
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
