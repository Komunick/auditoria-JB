"""Indicadores explicáveis de qualidade, somente dados sintéticos."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.core.qualidade_indicadores import calcular_painel, intervalo_relatorio


def dados():
    tarefas = []
    for i, (situacao, prazo, autor, exige, fora) in enumerate([
        ('concluida', '2026-10-29', 2, False, False),
        ('conferida', '2026-10-28', 3, True, True),
        ('a_fazer', '2026-10-29', None, False, False),
        ('em_andamento', '2026-11-01', None, False, False),
        ('aguardando_cliente', '', None, False, False),
        ('concluida', '2026-10-30', 2, True, False),
        ('dispensada', '2026-10-20', None, False, False),
        ('concluida', '', None, False, False),
    ], 1):
        tarefas.append(dict(id=i, titulo=f'Rotina sintética {i}', cliente_id=1,
            setor_id=1, responsavel_usuario_id=7, concluida_por=autor,
            situacao=situacao, vencimento=prazo, exige_conferencia=exige,
            fora_do_prazo=fora, concluida_em='2026-10-29T13:00:00+00:00' if autor else '',
            atualizada_em='2026-10-10T12:00:00+00:00', criada_em='2026-10-01T12:00:00+00:00'))
    ocorrencias = [dict(id=i, cliente_id=1, setor_id=1, responsavel_usuario_id=2,
        tipo=tipo, criticidade=crit, situacao=sit, descricao=f'Ocorrência sintética {i}',
        prazo=prazo, criado_em=criado, atualizado_em=criado, resolvida_em=resolvida)
        for i, tipo, crit, sit, prazo, criado, resolvida in [
            (11, 'erro', 'critica', 'aberta', '2026-10-31', '2026-10-20T12:00:00+00:00', ''),
            (12, 'retrabalho', 'alta', 'resolvida', '2026-10-27', '2026-10-23T12:00:00+00:00', '2026-10-25T12:00:00+00:00'),
            (13, 'reclamacao', 'media', 'em_tratamento', '2026-10-28', '2026-10-29T12:00:00+00:00', ''),
            (14, 'nao_conformidade', 'alta', 'aberta', '', '2026-10-20T12:00:00+00:00', ''),
            (15, 'nao_conformidade', 'baixa', 'encerrada', '', '2026-10-27T09:00:00+00:00', '2026-10-28T09:00:00+00:00'),
        ]]
    planos = [dict(id=21, ocorrencia_id=11, cliente_id=1, setor_id=1,
        responsavel_usuario_id=2, descricao='Ação sintética', causa='Causa sintética',
        tipo='corretiva', situacao='em_andamento', prazo='2026-10-29',
        criado_em='2026-10-20T12:00:00+00:00', atualizado_em='2026-10-29T12:00:00+00:00')]
    horas = [dict(id=31, usuario_id=2, cliente_id=1, setor_id=1, data='2026-10-29',
        minutos=90, custo_hora='10.01', custo_total='15.02', cancelado=False),
        dict(id=32, usuario_id=3, cliente_id=1, setor_id=1, data='2026-10-29',
        minutos=30, custo_hora=None, custo_total=None, cancelado=False),
        dict(id=33, usuario_id=2, cliente_id=1, setor_id=1, data='2026-10-29',
        minutos=60, custo_hora='999.00', custo_total='999.00', cancelado=True)]
    return tarefas, ocorrencias, planos, horas


def main():
    fonte = dados()
    antes = deepcopy(fonte)
    p = calcular_painel(*fonte, hoje=date(2026, 10, 30),
        usuarios={2: {'nome': 'Pessoa sintética A'}, 3: {'nome': 'Pessoa sintética B'}},
        setores={1: {'nome': 'Setor sintético'}}, custos_permitidos=True)
    assert fonte == antes, 'Indicadores não alteram fontes'
    k = {item['chave']: item for item in p['kpis']}
    assert k['entregues_no_prazo']['valor'] == '66.67'
    assert k['entregues_no_prazo']['numerador'] == 2 and k['entregues_no_prazo']['denominador'] == 3
    assert k['cumprimento_prazos']['valor'] == '50.00'
    assert k['cumprimento_prazos']['denominador'] == 4, 'Dispensada e sem vencimento não compõem índice'
    assert k['tarefas_concluidas']['valor'] == 4
    assert k['atividades_pendentes']['valor'] == 4, 'Conclusão aguardando conferência segue pendente'
    assert k['erros_retrabalho']['valor'] == 2 and k['reclamacoes']['valor'] == 1
    assert k['tempo_medio_resolucao_dias']['valor'] == '1.50'
    assert k['nao_conformidades_abertas']['valor'] == 1
    assert k['nao_conformidades_solucionadas']['valor'] == 1
    assert p['dimensoes']['progresso'] == {'concluidas': 3, 'total': 7, 'percentual': '42.86'}
    por = {i['usuario_id']: i for i in p['por_colaborador']}
    assert por[2]['tarefas_concluidas'] == 2 and por[3]['tarefas_concluidas'] == 1
    assert por[7]['tarefas_concluidas'] == 0, 'Responsável atual não recebe autoria histórica'
    assert por[None]['tarefas_concluidas'] == 1, 'Ausência de autor permanece explícita'
    assert p['custos']['minutos'] == 120 and p['custos']['horas'] == '2.00'
    assert p['custos']['custo_informado'] == '15.02' and p['custos']['custo_total'] is None
    assert p['custos']['lancamentos_sem_custo'] == 1
    assert por[2]['custo_total'] == '15.02' and por[3]['custo_total'] is None
    alertas = {a['tipo']: a for a in p['alertas']}
    for tipo in ('proximos_vencimentos', 'tarefas_atrasadas', 'sem_movimentacao',
                 'documentos_pendentes', 'aguardando_conferencia', 'nao_conformidades', 'planos_vencidos'):
        assert alertas[tipo]['quantidade'] > 0, tipo
    assert p['por_setor'][0]['ocorrencias'] == 5
    assert sum(p['semaforo'].values()) == 14, 'Semáforo cobre registros, não clientes únicos'
    assert all(item['formula'] for item in p['kpis'])

    sem_custo = calcular_painel(*fonte, hoje='2026-10-30')
    assert sem_custo['custos']['permitido'] is False
    assert sem_custo['custos']['custo_total'] is None and sem_custo['custos']['custo_informado'] is None
    assert all(i['custo_total'] is None for i in sem_custo['por_colaborador'])
    assert '15.02' not in str(sem_custo), 'Dinheiro não vaza no painel sem permissão'
    vazio = calcular_painel([], [], [], [], hoje='2026-10-30', custos_permitidos=True)
    kv = {i['chave']: i for i in vazio['kpis']}
    assert kv['entregues_no_prazo']['valor'] is None and kv['cumprimento_prazos']['valor'] is None
    assert kv['tempo_medio_resolucao_dias']['valor'] is None
    assert vazio['custos']['custo_total'] is None and vazio['custos']['horas'] == '0.00'

    # UTC de madrugada ainda é o dia anterior em Salvador.
    fronteira = dict(fonte[0][0], vencimento='2026-10-29', concluida_em='2026-10-30T01:00:00+00:00')
    pb = calcular_painel([fronteira], [], [], [], hoje='2026-10-30')
    assert {i['chave']: i['valor'] for i in pb['kpis']}['entregues_no_prazo'] == '100.00'
    futuro = dict(fronteira, situacao='a_fazer', vencimento='2026-11-05')
    assert calcular_painel([futuro], [], [], [], hoje='2026-10-30', proximos_dias=8)['alertas'][0]['quantidade'] == 1
    # Contagem completa mesmo quando a lista de exemplos do alerta é limitada.
    muitos = [dict(fonte[0][2], id=i) for i in range(70)]
    am = {a['tipo']: a for a in calcular_painel(muitos, [], [], [], hoje='2026-10-30')['alertas']}
    assert am['tarefas_atrasadas']['quantidade'] == 70
    assert len(am['tarefas_atrasadas']['itens']) == 20 and am['tarefas_atrasadas']['truncado'] is True
    assert intervalo_relatorio('diario', '2026-10-30') == ('2026-10-30', '2026-10-30')
    assert intervalo_relatorio('semanal', '2026-11-01') == ('2026-10-26', '2026-11-01')
    assert intervalo_relatorio('mensal', '2028-02-13') == ('2028-02-01', '2028-02-29')
    for kwargs in ({'proximos_dias': -1}, {'dias_sem_movimento': 0}):
        try:
            calcular_painel([], [], [], [], hoje='2026-10-30', **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError('Limite inválido deve ser recusado')
    print('OK - indicadores de qualidade: bases, autoria, prazos, alertas, moeda e ausência de dados')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
