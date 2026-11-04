"""Execução autorizada por tarefa: identidade, escopo, estados e concorrência HTTP."""
from test_web_tarefas_setor import Ambiente, API, BASE, CONSULTA, ok
import threading
from auditoria_fiscal.web import rotas_tarefas as rt
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore


def concorrencia_revogacao(a):
    tarefa = a.nova('Disputa sintética entre iniciar e revogar')
    p = f"{API}/{tarefa['id']}"
    autorizada = ok(a.client('dono').post(p + '/execucao/autorizar', json=dict(
        usuario_id=a.uid('sem_consulta'), revision=1, motivo='Apoio concorrente.')))
    aid = autorizada['execucao']['registros'][0]['id']
    disparar, tentando, terminou = threading.Event(), threading.Event(), threading.Event()
    erros = []
    original = TarefasStore.mudar_situacao

    def revogar():
        try:
            assert disparar.wait(10)
            tentando.set()
            with rt._store(escrita=True) as store:
                atual = store.obter_tarefa(tarefa['id'])
                store.decidir_execucao(tarefa['id'], aid, 'revogar', atual['revision'], 'Revogação concorrente.',
                    usuario_id=a.uid('dono'), usuario_login='dono', hoje=rt._hoje())
        except Exception as exc:
            erros.append(exc)
        finally:
            terminou.set()

    def mudar(store, *args, **kwargs):
        disparar.set()
        assert tentando.wait(5)
        assert not terminou.wait(.2), 'A autorização mudou entre a checagem de escopo e a mutação'
        return original(store, *args, **kwargs)

    worker = threading.Thread(target=revogar, daemon=True)
    worker.start()
    try:
        TarefasStore.mudar_situacao = mudar
        iniciada = ok(a.client('sem_consulta').post(p + '/situacao', json=dict(
            situacao='em_andamento', revision=autorizada['revision'])))
    finally:
        TarefasStore.mudar_situacao = original
        disparar.set()
        worker.join(10)
    assert not worker.is_alive() and not erros, erros
    ok(a.client('sem_consulta').get(p), 403)
    ok(a.client('sem_consulta').post(p + '/situacao', json=dict(
        situacao='concluida', revision=iniciada['revision'])), 403)


def disponibilidade_titular(a):
    tarefa = a.nova('Disponibilidade do titular original')
    p = f"{API}/{tarefa['id']}"
    ok(a.adm.post(API + '/substituicoes', json=dict(titular_usuario_id=a.uid('dono'),
        substituto_usuario_id=a.uid('gestor'), setor_id=a.setor, inicio='2026-11-04', fim='2026-11-05',
        motivo='Substituição sintética.')))
    assert ok(a.client('gestor').get(p))['execucao']['pode_autorizar']
    ok(a.adm.put(f'{API}/setores/{a.setor}', json=a.dados_setor(
        membros=[x for x in a.membros if x != a.uid('dono')])))
    for client in (a.client('gestor'), a.client('colega')):
        execucao = ok(client.get(p))['execucao']
        assert not execucao['pode_autorizar'] and not execucao['pode_solicitar']
    ok(a.client('gestor').post(p + '/execucao/autorizar', json=dict(
        usuario_id=a.uid('colega'), revision=1, motivo='Titular sem vínculo')), 403)
    ok(a.adm.put(f'{API}/setores/{a.setor}', json=a.dados_setor()))
    assert ok(a.client('gestor').get(p))['execucao']['pode_autorizar']
    ok(a.adm.put(f"/api/admin/usuarios/{a.uid('dono')}", json=dict(nome='Pessoa dono', ativo=False)))
    assert not ok(a.client('gestor').get(p))['execucao']['pode_autorizar']
    assert not ok(a.client('colega').get(p))['execucao']['pode_solicitar']


def main():
    a = Ambiente()
    dono, colega = a.client('dono'), a.client('colega')
    sem_consulta, gestor = a.client('sem_consulta'), a.client('gestor')
    tid = a.tarefa['id']
    caminho = f'{API}/{tid}'
    detalhe = ok(dono.get(caminho))
    assert detalhe['execucao']['pode_autorizar']
    assert {x['id'] for x in detalhe['execucao']['candidatos']} == {
        a.uid(n) for n in ('colega', 'sem_consulta', 'gestor')}
    assert ok(colega.get(caminho))['execucao']['pode_solicitar']
    # Consulta não permite executar nem autorizar outro colega.
    ok(colega.post(caminho + '/execucao/autorizar', json=dict(usuario_id=a.uid('gestor'), revision=1, motivo='Teste')), 403)
    ok(gestor.post(caminho + '/execucao/autorizar', json=dict(usuario_id=a.uid('colega'), revision=1, motivo='Teste')), 403)
    ok(a.client('fora').post(caminho + '/execucao/solicitar', json=dict(revision=1, motivo='Teste')), 403)
    ok(a.client('observador').post(caminho + '/execucao/solicitar', json=dict(revision=1, motivo='Teste')), 403)
    ok(sem_consulta.post(caminho + '/execucao/solicitar', json=dict(revision=1, motivo='Teste')), 403)
    ok(colega.post(caminho + '/execucao/solicitar', json=dict(revision=1, motivo='Teste', usuario_id=a.uid('dono'))), 422)
    pedido = ok(colega.post(caminho + '/execucao/solicitar', json=dict(revision=1, motivo='Posso apoiar esta tarefa.')))
    assert pedido['revision'] == 2 and not pedido['pode_executar']
    registro = pedido['execucao']['registros'][0]
    aid = registro['id']
    assert registro['estado'] == 'pendente' and registro['solicitante_usuario_id'] == a.uid('colega')
    assert not registro['pode_aprovar'] and not registro['pode_revogar']
    assert tid not in {x['id'] for x in ok(colega.get(API))['itens']}
    ok(colega.post(caminho + '/situacao', json=dict(situacao='em_andamento', revision=2)), 403)
    ok(colega.post(caminho + '/execucao/solicitar', json=dict(revision=2, motivo='Duplicado')), 422)
    decidir = caminho + f'/execucao/{aid}/decidir'
    ok(colega.post(decidir, json=dict(acao='aprovar', revision=2, motivo='Autoaprovação')), 403)
    ok(dono.post(decidir, json=dict(acao='aprovar', revision=1, motivo='Desatualizado')), 409)
    recusada = ok(dono.post(decidir, json=dict(acao='recusar', revision=2, motivo='Sem necessidade no momento.')))
    assert recusada['execucao']['registros'][0]['estado'] == 'recusada'
    pedido = ok(colega.post(caminho + '/execucao/solicitar', json=dict(revision=recusada['revision'], motivo='Apoio novamente necessário.')))
    aid = next(x['id'] for x in pedido['execucao']['registros'] if x['estado'] == 'pendente')
    autorizado = ok(dono.post(caminho + f'/execucao/{aid}/decidir', json=dict(acao='aprovar', revision=pedido['revision'], motivo='Apoio aprovado.')))
    detalhe = ok(colega.get(caminho))
    assert detalhe['pode_executar'] and detalhe['execucao_delegada'] and not detalhe['pode_gerir']
    assert detalhe['responsavel_usuario_id'] == a.uid('dono')
    assert tid in {x['id'] for x in ok(colega.get(API))['itens']}
    assert ok(colega.get(API + '/opcoes-filtros'))['total_escopo'] == 2
    comentada = ok(colega.post(caminho + '/comentarios', json=dict(revision=detalhe['revision'], comentario='Apoio iniciado.')))
    iniciada = ok(colega.post(caminho + '/situacao', json=dict(situacao='em_andamento', revision=comentada['revision'])))
    concluida = ok(colega.post(caminho + '/situacao', json=dict(situacao='concluida', revision=iniciada['revision'])))
    assert concluida['concluida_por'] == a.uid('colega') and concluida['responsavel_usuario_id'] == a.uid('dono')
    assert tid in {x['id'] for x in ok(colega.get(API))['itens']}
    historico = ok(colega.get(caminho))['eventos']
    assert any(x['usuario_id'] == a.uid('colega') and x['tipo'] == 'situacao' and x['para'] == 'concluida' for x in historico)
    ok(colega.post(caminho + '/vencimento', json=dict(revision=concluida['revision'], vencimento='2026-12-15', motivo='Teste')), 403)
    # Autorização direta dispensa consulta ampla, mantendo leitura específica.
    tarefa = a.nova('Execução específica sem consulta geral')
    p = f"{API}/{tarefa['id']}"
    ok(dono.post(p + '/execucao/autorizar', json=dict(usuario_id=a.uid('fora'), revision=1, motivo='Fora do setor')), 422)
    ok(dono.post(p + '/execucao/autorizar', json=dict(usuario_id=a.uid('observador'), revision=1, motivo='Sem execução')), 422)
    autorizada = ok(dono.post(p + '/execucao/autorizar', json=dict(usuario_id=a.uid('sem_consulta'), revision=1, motivo='Apoio pontual.')))
    reg = autorizada['execucao']['registros'][0]
    assert ok(sem_consulta.get(p))['pode_executar']
    assert {x['id'] for x in ok(sem_consulta.get(API))['itens']} == {tarefa['id']}
    ok(sem_consulta.get(API, params={'visao': 'setor'}), 403)
    ok(sem_consulta.get(caminho), 403)
    # Autorização de outra tarefa, identidade forjada e estado inválido não passam.
    ok(dono.post(p + f'/execucao/{aid}/decidir', json=dict(acao='revogar', revision=autorizada['revision'], motivo='Registro de outra tarefa')), 404)
    ok(dono.post(p + f"/execucao/{reg['id']}/decidir", json=dict(acao='inventada', revision=autorizada['revision'], motivo='Teste')), 422)
    a.permissoes('sem_consulta', ['aba.tarefas'])
    ok(sem_consulta.get(p), 403)
    ok(sem_consulta.post(p + '/situacao', json=dict(situacao='em_andamento', revision=autorizada['revision'])), 403)
    a.permissoes('sem_consulta', BASE)
    revogada = ok(dono.post(p + f"/execucao/{reg['id']}/decidir", json=dict(acao='revogar', revision=autorizada['revision'], motivo='Apoio encerrado.')))
    assert revogada['execucao']['registros'][0]['estado'] == 'revogada'
    ok(sem_consulta.get(p), 403)
    ok(sem_consulta.post(p + '/situacao', json=dict(situacao='em_andamento', revision=revogada['revision'])), 403)
    assert ok(sem_consulta.get(API))['total'] == 0
    assert not ok(a.client('colega').get(f"{API}/{a.sem_dono['id']}"))['execucao']['pode_solicitar']
    concorrencia_revogacao(a)
    disponibilidade_titular(a)
    print('OK - execução autorizada HTTP: solicitação, decisão, autoria, revogação e isolamento')


if __name__ == '__main__':
    main()
