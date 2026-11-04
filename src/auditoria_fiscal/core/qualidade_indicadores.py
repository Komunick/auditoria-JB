"""Indicadores operacionais explicáveis sobre um conjunto já autorizado.

Sem banco, interface ou atribuição automática de notas a pessoas. Datas de
negócio usam Salvador; dinheiro usa Decimal e nunca transforma ausência em zero.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .tarefas import ABERTAS, classificar, data_salvador

CONCLUIDAS = frozenset(('concluida', 'conferida'))
SOLUCIONADAS = frozenset(('resolvida', 'encerrada'))
CENTAVO = Decimal('0.01')


def _decimal(valor):
    if isinstance(valor, (bool, float)):
        raise ValueError('Valor monetário deve ser decimal exato.')
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Valor monetário inválido.') from exc
    if not numero.is_finite() or numero < 0:
        raise ValueError('Valor monetário inválido.')
    return numero


def _numero(valor):
    return str(Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP))


def _percentual(numerador, denominador):
    return _numero(Decimal(numerador) * 100 / denominador) if denominador else None


def _dia(valor):
    return data_salvador(valor) if valor not in ('', None) else None


def _instante(valor):
    if not valor:
        return None
    try:
        instante = valor if isinstance(valor, datetime) else datetime.fromisoformat(valor)
        return instante if instante.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _nome(catalogo, id_, sem_nome):
    if id_ is None:
        return sem_nome
    valor = (catalogo or {}).get(id_, (catalogo or {}).get(str(id_)))
    if isinstance(valor, dict):
        return valor.get('nome') or f'ID {id_}'
    return str(valor) if valor else f'ID {id_}'


def _pendente(tarefa):
    return tarefa.get('situacao') in ABERTAS or (
        tarefa.get('situacao') == 'concluida' and bool(tarefa.get('exige_conferencia')))


def _no_prazo(tarefa):
    prazo = _dia(tarefa.get('vencimento'))
    concluida = _dia(tarefa.get('concluida_em'))
    return bool(prazo and concluida and concluida <= prazo and not tarefa.get('fora_do_prazo'))


def classificar_qualidade(registro, hoje, *, plano=False):
    """Semáforo único de ocorrências e planos, com datas no fuso de Salvador."""
    hoje = data_salvador(hoje)
    prazo = _dia(registro.get('prazo'))
    encerrado = registro.get('situacao') == 'validado' if plano else registro.get('situacao') in SOLUCIONADAS
    if encerrado:
        encerrada_em = _dia(registro.get('validado_em') if plano else registro.get('resolvida_em'))
        if not prazo or not encerrada_em:
            return 'neutro'
        return 'verde' if encerrada_em <= prazo else 'vermelho'
    if prazo and prazo < hoje or not plano and (
            registro.get('criticidade') == 'critica' or registro.get('tipo') == 'nao_conformidade'):
        return 'vermelho'
    return 'amarelo'


def _resumo_custos(lancamentos, permitido):
    minutos = 0
    valores = []
    sem_custo = 0
    for registro in lancamentos:
        valor = registro.get('minutos', 0)
        if type(valor) is not int or valor < 0:
            raise ValueError('Minutos devem ser inteiros não negativos.')
        minutos += valor
        if not permitido:
            continue
        custo_hora = registro.get('custo_hora')
        if custo_hora in (None, ''):
            sem_custo += 1
        else:
            custo = (_decimal(custo_hora) * valor / 60).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            valores.append(custo)
    informado = _numero(sum(valores, Decimal(0))) if valores else None
    return dict(permitido=bool(permitido), minutos=minutos, horas=_numero(Decimal(minutos) / 60),
        custo_total=informado if permitido and not sem_custo else None,
        custo_informado=informado, lancamentos_sem_custo=sem_custo if permitido else None,
        lancamentos=len(lancamentos),
        formula='Soma de minutos / 60 × custo/hora de cada lançamento ativo, arredondado em centavos. '
                'Custo total indisponível se faltar custo/hora; custo informado soma só os valores conhecidos.')


def intervalo_relatorio(periodo, referencia):
    """Intervalos inclusivos; semana civil de segunda a domingo."""
    ref = data_salvador(referencia)
    if periodo == 'diario':
        inicio = fim = ref
    elif periodo == 'semanal':
        inicio = ref - timedelta(days=ref.weekday())
        fim = inicio + timedelta(days=6)
    elif periodo == 'mensal':
        inicio = ref.replace(day=1)
        fim = ref.replace(day=calendar.monthrange(ref.year, ref.month)[1])
    else:
        raise ValueError('Período deve ser diario, semanal ou mensal.')
    return inicio.isoformat(), fim.isoformat()


def calcular_painel(tarefas, ocorrencias, planos, horas, hoje, usuarios=None, setores=None,
                    custos_permitidos=False, proximos_dias=3, dias_sem_movimento=7):
    """Sem filtros ocultos: todas as contagens usam integralmente as listas recebidas."""
    if type(proximos_dias) is not int or not 0 <= proximos_dias <= 365:
        raise ValueError('Antecedência deve estar entre 0 e 365 dias.')
    if type(dias_sem_movimento) is not int or not 1 <= dias_sem_movimento <= 365:
        raise ValueError('Inatividade deve estar entre 1 e 365 dias.')
    hoje = data_salvador(hoje)
    tarefas, ocorrencias, planos = list(tarefas), list(ocorrencias), list(planos)
    horas = [h for h in horas if not h.get('cancelado')]
    concluidas = [t for t in tarefas if t.get('situacao') in CONCLUIDAS]
    com_prazo = [t for t in concluidas if t.get('vencimento')]
    pendentes = [t for t in tarefas if _pendente(t)]
    atrasadas = [t for t in tarefas if t.get('situacao') in ABERTAS and
                 _dia(t.get('vencimento')) and _dia(t['vencimento']) < hoje]
    vencidas = [t for t in tarefas if t.get('situacao') != 'dispensada' and
                _dia(t.get('vencimento')) and _dia(t['vencimento']) <= hoje]
    em_dia = sum(_no_prazo(t) for t in com_prazo)
    cumpridas = sum(t.get('situacao') in CONCLUIDAS and _no_prazo(t) for t in vencidas)
    abertas = [o for o in ocorrencias if o.get('situacao') not in SOLUCIONADAS]
    nc_abertas = [o for o in abertas if o.get('tipo') == 'nao_conformidade']
    nc_solucionadas = [o for o in ocorrencias if o.get('tipo') == 'nao_conformidade'
                      and o.get('situacao') in SOLUCIONADAS]
    duracoes = []
    for ocorrencia in ocorrencias:
        if ocorrencia.get('situacao') not in SOLUCIONADAS:
            continue
        inicio = _instante(ocorrencia.get('criado_em'))
        fim = _instante(ocorrencia.get('resolvida_em'))
        if inicio and fim and fim >= inicio:
            delta = fim - inicio
            duracoes.append(Decimal(delta.days) + Decimal(delta.seconds) / 86400
                            + Decimal(delta.microseconds) / 86400000000)
    tempo_medio = _numero(sum(duracoes) / len(duracoes)) if duracoes else None
    def kpi(chave, rotulo, valor, unidade, formula, numerador=None, denominador=None):
        return dict(chave=chave, rotulo=rotulo, valor=valor, unidade=unidade,
                    formula=formula, numerador=numerador, denominador=denominador)
    kpis = [
        kpi('entregues_no_prazo', 'Entregas no prazo', _percentual(em_dia, len(com_prazo)), 'percentual',
            'Execuções concluídas no prazo / execuções concluídas com vencimento × 100. '
            'Considera concluída ou conferida; sem vencimento e dispensadas ficam fora.', em_dia, len(com_prazo)),
        kpi('tarefas_concluidas', 'Tarefas executadas', len(concluidas), 'numero',
            'Tarefas em concluída ou conferida; autoria atribuída à pessoa registrada na execução.'),
        kpi('atividades_pendentes', 'Atividades pendentes', len(pendentes), 'numero',
            'Tarefas abertas e execuções concluídas que ainda exigem conferência.'),
        kpi('erros_retrabalho', 'Erros e retrabalhos', sum(o.get('tipo') in ('erro', 'retrabalho') for o in ocorrencias), 'numero',
            'Ocorrências dos tipos erro e retrabalho, em todas as situações do conjunto filtrado.'),
        kpi('cumprimento_prazos', 'Cumprimento dos prazos vencidos', _percentual(cumpridas, len(vencidas)), 'percentual',
            'Execuções no prazo / tarefas com vencimento até a referência × 100; abertas vencidas '
            'permanecem no denominador, dispensadas ficam fora.', cumpridas, len(vencidas)),
        kpi('reclamacoes', 'Reclamações', sum(o.get('tipo') == 'reclamacao' for o in ocorrencias), 'numero',
            'Ocorrências do tipo reclamação no conjunto filtrado.'),
        kpi('tempo_medio_resolucao_dias', 'Tempo médio de resolução', tempo_medio, 'dias',
            'Média da data de resolução menos a data de registro nas ocorrências resolvidas/encerradas com '
            'carimbos válidos; mede dias corridos desde o registro.', None, len(duracoes)),
        kpi('nao_conformidades_abertas', 'Não conformidades abertas', len(nc_abertas), 'numero',
            'Não conformidades que ainda não estão resolvidas nem encerradas.'),
        kpi('nao_conformidades_solucionadas', 'Não conformidades solucionadas', len(nc_solucionadas), 'numero',
            'Não conformidades em resolvida ou encerrada.'),
    ]
    semaforo = dict(verde=0, amarelo=0, vermelho=0, neutro=0)
    for tarefa in tarefas:
        cor = classificar(dict(tarefa, vencimento=tarefa.get('vencimento') or ''), hoje)['cor']
        if cor == 'verde' and _pendente(tarefa):
            cor = 'amarelo'
        semaforo[cor] += 1
    for ocorrencia in ocorrencias:
        semaforo[classificar_qualidade(ocorrencia, hoje)] += 1
    for plano in planos:
        semaforo[classificar_qualidade(plano, hoje, plano=True)] += 1

    colaboradores = {}
    def colaborador(uid):
        if uid not in colaboradores:
            colaboradores[uid] = dict(usuario_id=uid, nome=_nome(usuarios, uid, 'Autoria ou responsável não informado'),
                tarefas_concluidas=0, tarefas_pendentes=0, minutos=0, horas='0.00', custo_total=None)
        return colaboradores[uid]
    for tarefa in concluidas:
        colaborador(tarefa.get('concluida_por'))['tarefas_concluidas'] += 1
    for tarefa in pendentes:
        colaborador(tarefa.get('responsavel_efetivo_id', tarefa.get('responsavel_usuario_id')))['tarefas_pendentes'] += 1
    for registro in horas:
        colaborador(registro.get('usuario_id', registro.get('responsavel_usuario_id')))
    for uid, item in colaboradores.items():
        custos = _resumo_custos([h for h in horas if h.get('usuario_id', h.get('responsavel_usuario_id')) == uid], custos_permitidos)
        item.update({chave: custos[chave] for chave in ('minutos', 'horas', 'custo_total')})
    setores_ids = {r.get('setor_id') for r in tarefas + ocorrencias + planos + horas}
    por_setor = []
    for sid in setores_ids:
        ts = [t for t in tarefas if t.get('setor_id') == sid]
        os = [o for o in ocorrencias if o.get('setor_id') == sid]
        por_setor.append(dict(setor_id=sid, nome=_nome(setores, sid, 'Setor não informado'), tarefas=len(ts),
            concluidas=sum(t.get('situacao') in CONCLUIDAS for t in ts), pendentes=sum(_pendente(t) for t in ts),
            atrasadas=sum(t.get('setor_id') == sid for t in atrasadas), ocorrencias=len(os),
            nao_conformidades_abertas=sum(o.get('setor_id') == sid for o in nc_abertas)))

    def resumir(entidade, registro):
        return dict(entidade=entidade, id=registro.get('id'),
            titulo=registro.get('titulo') or registro.get('descricao') or 'Registro sem descrição',
            cliente_id=registro.get('cliente_id'), setor_id=registro.get('setor_id'),
            responsavel_usuario_id=registro.get('responsavel_efetivo_id', registro.get('responsavel_usuario_id')),
            prazo=registro.get('vencimento') if entidade == 'tarefa' else registro.get('prazo'))
    def alerta(tipo, rotulo, cor, registros):
        itens = sorted((resumir(e, r) for e, r in registros), key=lambda r: (r['prazo'] or '9999', r['id'] or 0))
        return dict(tipo=tipo, rotulo=rotulo, cor=cor, quantidade=len(itens), itens=itens[:20], truncado=len(itens) > 20)
    def sem_movimento(registro):
        ultimo = _dia(registro.get('atualizado_em') or registro.get('atualizada_em') or registro.get('criado_em') or registro.get('criada_em'))
        return bool(ultimo and (hoje - ultimo).days >= dias_sem_movimento)
    paradas = [('tarefa', t) for t in pendentes if sem_movimento(t)]
    paradas += [('ocorrencia', o) for o in abertas if sem_movimento(o)]
    paradas += [('plano', p) for p in planos if p.get('situacao') != 'validado' and sem_movimento(p)]
    alertas = [
        alerta('proximos_vencimentos', f'Obrigações e tarefas nos próximos {proximos_dias} dias', 'amarelo',
            [('tarefa', t) for t in pendentes if _dia(t.get('vencimento')) and hoje <= _dia(t['vencimento']) <= hoje + timedelta(days=proximos_dias)]),
        alerta('tarefas_atrasadas', 'Tarefas em atraso', 'vermelho', [('tarefa', t) for t in atrasadas]),
        alerta('sem_movimentacao', f'Pendências sem movimento há {dias_sem_movimento} dias', 'amarelo', paradas),
        alerta('documentos_pendentes', 'Documentos ou informações aguardando cliente', 'amarelo',
            [('tarefa', t) for t in tarefas if t.get('situacao') == 'aguardando_cliente']),
        alerta('aguardando_conferencia', 'Atividades aguardando conferência', 'amarelo',
            [('tarefa', t) for t in tarefas if t.get('situacao') == 'concluida' and t.get('exige_conferencia')]),
        alerta('nao_conformidades', 'Não conformidades sem solução', 'vermelho', [('ocorrencia', o) for o in nc_abertas]),
        alerta('planos_vencidos', 'Planos de ação vencidos', 'vermelho',
            [('plano', p) for p in planos if p.get('situacao') != 'validado' and _dia(p.get('prazo')) and _dia(p['prazo']) < hoje]),
    ]
    finalizadas = [t for t in concluidas if not _pendente(t)]
    base_progresso = [t for t in tarefas if t.get('situacao') != 'dispensada']
    return dict(formato='qualidade_painel_v1', referencia=hoje.isoformat(), kpis=kpis,
        totais=dict(tarefas=len(tarefas), concluidas=len(concluidas), pendentes=len(pendentes), atrasadas=len(atrasadas),
            ocorrencias=len(ocorrencias), ocorrencias_abertas=len(abertas), planos=len(planos),
            planos_pendentes=sum(p.get('situacao') != 'validado' for p in planos)),
        semaforo=semaforo,
        por_colaborador=sorted(colaboradores.values(), key=lambda r: (r['nome'].casefold(), r['usuario_id'] or 0)),
        por_setor=sorted(por_setor, key=lambda r: (r['nome'].casefold(), r['setor_id'] or 0)), alertas=alertas,
        custos=_resumo_custos(horas, custos_permitidos),
        dimensoes=dict(operacao=dict(total=len(tarefas), pendentes=len(pendentes)),
            risco=dict(ocorrencias_criticas=sum(o.get('criticidade') == 'critica' for o in abertas), nao_conformidades_abertas=len(nc_abertas)),
            engajamento=dict(aguardando_cliente=sum(t.get('situacao') == 'aguardando_cliente' for t in tarefas), sem_movimento=len(paradas)),
            progresso=dict(concluidas=len(finalizadas), total=len(base_progresso), percentual=_percentual(len(finalizadas), len(base_progresso)))),
        metodologia=[
            'Todos os indicadores usam apenas o conjunto autorizado e filtrado; não há nota ou ranking automático de pessoas.',
            'Semáforo conta registros de tarefas, ocorrências e planos. Um cliente pode aparecer em vários registros; não são clientes únicos.',
            'Verde: finalizado dentro do prazo; amarelo: andamento ou conferência; vermelho: atraso, devolução, criticidade crítica ou não conformidade aberta. Neutro: dispensado ou sem comprovação de pontualidade.',
            'Engajamento mostra espera por cliente e registros sem movimento, não uma avaliação pessoal.',
            'Progresso conta tarefas finalizadas após a conferência exigida; dispensadas ficam fora do denominador.',
            'Conclusões por pessoa usam autoria histórica; pendências usam o responsável efetivo atual. Não são medidas equivalentes.',
            'A lista de exemplos de cada alerta limita-se a 20 registros, mas sua quantidade inclui todo o conjunto filtrado.',
            'Datas são avaliadas no horário de Salvador; durações usam carimbos com fuso. Campos sem dados não viram zero.',
        ])
