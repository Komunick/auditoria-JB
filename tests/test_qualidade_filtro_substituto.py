"""Filtro HTTP por responsável efetivo e catálogo sintético da qualidade."""
import io
import gc
from datetime import date
from unittest.mock import patch
from test_web_qualidade import TestClient, criar_app, ok, _dados
from openpyxl import load_workbook

MODELOS_ESPERADOS = {
    'Fiscal': ['Apuração de impostos e emissão de guias', 'Entrega das obrigações acessórias', 'Conferência de notas fiscais', 'Acompanhamento de notificações e malhas fiscais', 'Controle de pendências fiscais dos clientes', 'Monitoramento de prazos e vencimentos'],
    'Contábil': ['Conciliações bancárias', 'Classificação e lançamentos contábeis', 'Fechamento mensal', 'Elaboração de balancetes, balanços e DRE', 'Controle de documentos pendentes', 'Conferência e validação dos serviços executados'],
    'Departamento Pessoal': ['Processamento da folha de pagamento', 'Controle de admissões e rescisões', 'Férias e décimo terceiro salário', 'Obrigações trabalhistas e previdenciárias', 'Conferência das informações enviadas ao eSocial', 'Acompanhamento de atualização de convenção coletiva', 'Controle de prazos e pendências'],
    'Legalização': ['Abertura, alteração e baixa de empresas', 'Acompanhamento de processos nos órgãos públicos', 'Controle de alvarás, inscrições e licenças', 'Regularização cadastral', 'Monitoramento de protocolos e exigências', 'Acompanhamento dos prazos de conclusão'],
    'Administrativo': ['Atendimento e solicitações dos clientes', 'Controle de documentos recebidos e pendentes', 'Acompanhamento das demandas internas', 'Distribuição de atividades', 'Monitoramento da produtividade e qualidade do atendimento'],
}


def conferir_catalogo(cliente):
    modelos = ok(cliente.get('/api/qualidade/catalogo'))['modelos']
    assert len(modelos) == len(MODELOS_ESPERADOS)
    assert {m['setor']: m['atividades'] for m in modelos} == MODELOS_ESPERADOS
    assert all(len(m['atividades']) == len(set(m['atividades'])) for m in modelos)


def main():
    from auditoria_fiscal.web import rotas_qualidade as rotas
    app = criar_app()
    adm = TestClient(app)
    senha = 'teste-qualidade-022'
    ok(adm.post('/api/bootstrap', json=dict(usuario='admin_qa', nome='Gestão sintética', senha=senha)))
    pessoas = []
    for nome in ('titular', 'substituto'):
        uid = ok(adm.post('/api/admin/usuarios', json=dict(usuario=nome, nome=nome, senha=senha,
            permissoes=['aba.qualidade', 'qualidade.registrar', 'qualidade.exportar', 'aba.tarefas', 'tarefas.executar'])))['id']
        cliente = TestClient(app)
        ok(cliente.post('/api/login', json=dict(usuario=nome, senha=senha)))
        pessoas.append((uid, cliente))
    (aid, a), (bid, b) = pessoas
    sid = ok(adm.post('/api/tarefas/setores', json=dict(nome='Setor sintético',
        responsavel_usuario_id=1, membros=[1, aid, bid])))['id']
    cid = ok(adm.post('/api/clientes', json={'nome': 'Cliente sintético'}))['id']
    ok(adm.put(f'/api/tarefas/clientes/{cid}/carteira', json=dict(setor_id=sid, responsavel_usuario_id=aid)))
    api = '/api/qualidade'
    with patch.object(rotas.t, 'hoje_salvador', return_value=date(2026, 11, 9)):
        tarefa = ok(adm.post('/api/tarefas/avulsas', json=dict(cliente_id=cid, setor_id=sid,
            titulo='Tarefa sintética', inicio='2026-11-01', vencimento='2026-11-30', responsavel_usuario_id=aid)))
        oc = ok(a.post(api+'/ocorrencias', json=dict(data='2026-11-09', cliente_id=cid, setor_id=sid,
            responsavel_usuario_id=aid, tipo='erro', descricao='Ocorrência sintética', criticidade='baixa', prazo='2026-11-30')))
        plano = ok(a.post(api+'/planos', json=dict(ocorrencia_id=oc['id'], causa='Causa sintética',
            descricao='Plano sintético', tipo='corretiva', responsavel_usuario_id=aid, prazo='2026-11-30')))
        hora = dict(cliente_id=cid, setor_id=sid, data='2026-11-09', minutos=30, descricao='Tempo sintético')
        ha = ok(a.post(api+'/horas', json=hora))
        ok(adm.post('/api/tarefas/substituicoes', json=dict(titular_usuario_id=aid,
            substituto_usuario_id=bid, setor_id=sid, inicio='2026-11-09', fim='2026-11-09', motivo='Ausência sintética')))
        hb = ok(b.post(api+'/horas', json=hora))
        filtro = {'responsavel_usuario_id': bid}
        assert ok(b.get(api+'/ocorrencias'))['total'] == 1, 'Substituto deve ter escopo antes de filtrar'
        assert [r['id'] for r in ok(b.get(api+'/ocorrencias', params=filtro))['itens']] == [oc['id']], 'Filtro por substituto perdeu a ocorrência do titular'
        assert [r['id'] for r in ok(b.get(api+'/planos', params=filtro))['itens']] == [plano['id']]
        painel = ok(b.get(api+'/painel', params=filtro))
        assert painel['totais']['tarefas'] == 1 and painel['totais']['ocorrencias'] == 1
        assert painel['totais']['planos'] == 1
        livro = load_workbook(io.BytesIO(ok(b.get(api+'/relatorio.xlsx', params=filtro)).content))
        try:
            assert tarefa['id'] in [r[0] for r in livro['Tarefas'].iter_rows(min_row=2, values_only=True)]
        finally:
            livro.close()
        assert [r['id'] for r in ok(b.get(api+'/horas', params=filtro))['itens']] == [hb['id']]
        assert ok(b.get(api+'/horas', params={'responsavel_usuario_id': aid}))['total'] == 0
        assert [r['id'] for r in ok(adm.get(api+'/horas', params={'responsavel_usuario_id': aid}))['itens']] == [ha['id']]
        with patch.object(rotas.t, 'hoje_salvador', return_value=date(2026, 11, 10)):
            for entidade in ('ocorrencias', 'planos'):
                assert ok(b.get(api+'/'+entidade, params=filtro))['total'] == 0
            assert ok(b.get(api+'/painel', params=filtro))['totais']['tarefas'] == 0
            # Gestão mantém visibilidade: a vigência também deve afetar o filtro em si.
            totais = ok(adm.get(api+'/painel', params=filtro))['totais']
            assert totais['tarefas'] == totais['ocorrencias'] == totais['planos'] == 0
        conferir_catalogo(b)
    print('OK - qualidade: filtro efetivo, vigência, planos, Excel, horas pessoais e catálogo completo')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        gc.collect()
        _dados.cleanup()
