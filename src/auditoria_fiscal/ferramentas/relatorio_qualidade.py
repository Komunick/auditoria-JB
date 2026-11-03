"""Relatórios completos do conjunto autorizado, sem leitura de bancos ou rede."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
import json
import re

from openpyxl import Workbook

from ..core.planilha_segura import escrever_cabecalho, escrever_moeda, escrever_texto

_CONTROLES = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

TAREFAS = [('id', 'ID'), ('cliente_nome', 'Cliente'), ('setor_nome', 'Setor'),
    ('titulo', 'Atividade'), ('competencia', 'Competência'), ('inicio', 'Início'),
    ('vencimento', 'Prazo'), ('situacao', 'Situação'), ('responsavel_nome', 'Responsável titular'),
    ('responsavel_efetivo_nome', 'Responsável atual'), ('concluida_em', 'Executada em'),
    ('concluida_nome', 'Executada por'), ('conferida_em', 'Conferida em'),
    ('conferida_nome', 'Conferida por'), ('fora_do_prazo', 'Fora do prazo')]
OCORRENCIAS = [('id', 'ID'), ('data', 'Data'), ('cliente_nome', 'Cliente'), ('setor_nome', 'Setor'),
    ('tipo', 'Tipo'), ('descricao', 'Descrição'), ('criticidade', 'Criticidade'),
    ('responsavel_nome', 'Responsável'), ('prazo', 'Prazo'), ('situacao', 'Situação'),
    ('criado_em', 'Registrada em'), ('resolvida_em', 'Resolvida em'), ('encerrada_em', 'Encerrada em')]
PLANOS = [('id', 'ID'), ('ocorrencia_id', 'Ocorrência'), ('cliente_nome', 'Cliente'), ('setor_nome', 'Setor'),
    ('tipo', 'Tipo'), ('descricao', 'Ação'), ('causa', 'Causa identificada'),
    ('responsavel_nome', 'Responsável'), ('prazo', 'Prazo'), ('situacao', 'Situação'),
    ('criado_em', 'Registrado em'), ('validado_em', 'Validado em'), ('validado_por', 'Validado por')]
HORAS = [('id', 'ID'), ('data', 'Data'), ('cliente_nome', 'Cliente'), ('setor_nome', 'Setor'),
    ('usuario_nome', 'Colaborador'), ('tarefa_id', 'Tarefa'), ('ocorrencia_id', 'Ocorrência'),
    ('descricao', 'Descrição'), ('minutos', 'Minutos'), ('cancelado', 'Cancelado'),
    ('motivo_cancelamento', 'Motivo do cancelamento')]
COLABORADORES = [('usuario_id', 'Usuário'), ('nome', 'Colaborador'),
    ('tarefas_concluidas', 'Execuções concluídas'), ('tarefas_pendentes', 'Pendências atuais'),
    ('minutos', 'Minutos ativos'), ('horas', 'Horas ativas')]
SETORES = [('setor_id', 'ID'), ('nome', 'Setor'), ('tarefas', 'Tarefas'), ('concluidas', 'Executadas'),
    ('pendentes', 'Pendentes'), ('atrasadas', 'Atrasadas'), ('ocorrencias', 'Ocorrências'),
    ('nao_conformidades_abertas', 'Não conformidades abertas')]
ROTULOS = {
    'a_fazer': 'A fazer', 'em_andamento': 'Em andamento', 'aguardando_cliente': 'Aguardando cliente',
    'concluida': 'Concluída', 'conferida': 'Conferida', 'devolvida': 'Devolvida', 'dispensada': 'Dispensada',
    'aberta': 'Aberta', 'em_tratamento': 'Em tratamento', 'resolvida': 'Resolvida', 'encerrada': 'Encerrada',
    'aberto': 'Aberto', 'aguardando_validacao': 'Aguardando validação', 'validado': 'Validado',
    'erro': 'Erro', 'atraso': 'Atraso', 'comunicacao': 'Comunicação', 'reclamacao': 'Reclamação',
    'retrabalho': 'Retrabalho', 'pendencia': 'Pendência', 'procedimento': 'Procedimento',
    'nao_conformidade': 'Não conformidade', 'corretiva': 'Corretiva', 'preventiva': 'Preventiva',
    'baixa': 'Baixa', 'media': 'Média', 'alta': 'Alta', 'critica': 'Crítica',
}


def _texto(valor):
    """Torna controles inválidos do XML visíveis, preservando sua representação."""
    return _CONTROLES.sub(lambda m: f'\\x{ord(m[0]):02x}', str(valor))


def _campo(registro, chave):
    valor = registro.get(chave)
    if chave == 'usuario_nome' and valor in ('', None):
        valor = registro.get('responsavel_nome')
        if valor in ('', None) and registro.get('responsavel_usuario_id'):
            valor = f"ID {registro['responsavel_usuario_id']}"
    if chave == 'fora_do_prazo':
        return ('Sim' if valor else 'Não') if registro.get('vencimento') else 'Não se aplica'
    if chave == 'cancelado':
        return 'Sim' if valor else 'Não'
    if chave in ('situacao', 'tipo', 'criticidade'):
        return ROTULOS.get(valor, valor or '')
    if valor in ('', None) and chave.endswith('_nome'):
        base = chave[:-5]
        uid = registro.get(base + '_id') or registro.get(base + '_usuario_id') or registro.get(base + '_por')
        return f'ID {uid}' if uid else ''
    return valor


def _dinheiro(aba, linha, coluna, valor):
    escrever_moeda(aba, linha, coluna, None if valor in ('', None) else int(Decimal(str(valor)) * 100))


def _aba(livro, nome, campos, registros, monetarios=()):
    aba = livro.create_sheet(nome)
    escrever_cabecalho(aba, [titulo for _, titulo in campos])
    for linha, registro in enumerate(registros, 2):
        for coluna, (chave, _) in enumerate(campos, 1):
            valor = _campo(registro, chave)
            if chave in monetarios:
                _dinheiro(aba, linha, coluna, valor)
            elif valor is None:
                aba.cell(linha, coluna).value = None
            elif isinstance(valor, (int, Decimal)) and not isinstance(valor, bool):
                aba.cell(linha, coluna).value = valor
            else:
                escrever_texto(aba, linha, coluna, _texto(valor))
    aba.auto_filter.ref = aba.dimensions
    return aba


def _metodologia(painel, filtros):
    linhas = [('Referência', painel.get('referencia', ''))]
    linhas.extend((f'Filtro: {k}', json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))
                  for k, v in (filtros or {}).items() if v not in ('', None))
    linhas.extend((f'Método {i}', texto) for i, texto in enumerate(painel.get('metodologia', []), 1))
    linhas.extend((k['rotulo'], k['formula']) for k in painel.get('kpis', []))
    linhas.append(('Tempo e custo', painel.get('custos', {}).get('formula', '')))
    linhas.append(('Apontamentos cancelados', 'Constam no detalhe para rastreabilidade, mas não entram nos totais ou indicadores.'))
    linhas.append(('Detalhes', 'Tarefas, ocorrências, planos e apontamentos são reproduzidos integralmente no conjunto autorizado recebido.'))
    return linhas


def gerar_excel(painel, tarefas, ocorrencias, planos, horas, filtros=None):
    """Retorna XLSX em memória. Campos monetários requerem permissão no painel."""
    livro = Workbook()
    livro.remove(livro.active)
    indicadores = [dict(k, valor=Decimal(k['valor']) if isinstance(k.get('valor'), str) else k.get('valor'))
                   for k in painel.get('kpis', [])]
    _aba(livro, 'Indicadores', [('rotulo', 'Indicador'), ('valor', 'Valor'), ('unidade', 'Unidade'),
        ('numerador', 'Numerador'), ('denominador', 'Denominador'), ('formula', 'Fórmula')], indicadores)
    _aba(livro, 'Setores', SETORES, painel.get('por_setor', []))
    permitido = painel.get('custos', {}).get('permitido') is True
    campos_colaboradores = COLABORADORES + ([('custo_total', 'Custo total')] if permitido else [])
    _aba(livro, 'Colaboradores', campos_colaboradores, painel.get('por_colaborador', []), ('custo_total',))
    _aba(livro, 'Alertas', [('rotulo', 'Alerta'), ('quantidade', 'Quantidade'), ('cor', 'Semáforo')], painel.get('alertas', []))
    _aba(livro, 'Tarefas', TAREFAS, tarefas)
    _aba(livro, 'Ocorrências', OCORRENCIAS, ocorrencias)
    _aba(livro, 'Planos de ação', PLANOS, planos)
    campos_horas = HORAS + ([('custo_hora', 'Custo/hora'), ('custo_total', 'Custo registrado')] if permitido else [])
    _aba(livro, 'Apontamentos', campos_horas, horas, ('custo_hora', 'custo_total'))
    metodologia = _metodologia(painel, filtros)
    custos = painel.get('custos', {})
    metodologia.extend([('Minutos ativos', custos.get('minutos', 0)), ('Horas ativas', custos.get('horas', '0.00'))])
    _aba(livro, 'Metodologia', [('parametro', 'Parâmetro'), ('valor', 'Informação')],
         [dict(parametro=k, valor=v) for k, v in metodologia])
    if permitido:
        aba = livro['Metodologia']
        for rotulo, chave in [('Custo total (somente com cobertura completa)', 'custo_total'),
                             ('Custo informado (pode ser parcial)', 'custo_informado')]:
            linha = aba.max_row + 1
            escrever_texto(aba, linha, 1, rotulo)
            _dinheiro(aba, linha, 2, custos.get(chave))
        aba.append(['Lançamentos ativos sem custo informado', custos.get('lancamentos_sem_custo')])
    saida = BytesIO()
    try:
        livro.save(saida)
        return saida.getvalue()
    finally:
        livro.close()


def _pdf_texto(valor):
    texto = _texto(valor if valor not in (None, '') else 'Não informado')
    # Fonte core já usada nos PDFs do projeto; aspas/travessões viram equivalentes.
    texto = texto.translate(str.maketrans({'—': '-', '–': '-', '×': 'x', '→': '->',
                                         '“': '"', '”': '"', '’': "'", '\t': '    '}))
    return texto.encode('latin-1', 'replace').decode('latin-1')


def gerar_pdf(painel, tarefas, ocorrencias, planos, horas, filtros=None):
    """PDF com todas as linhas e descrições, paginação automática e texto literal."""
    from fpdf import FPDF

    class Relatorio(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 10)
            self.set_text_color(24, 57, 63)
            self.cell(0, 6, 'JB FRAGA | QUALIDADE E OPERACAO', new_x='LMARGIN', new_y='NEXT')
            self.set_draw_color(37, 145, 132)
            self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
            self.ln(5)

        def footer(self):
            self.set_y(-13)
            self.set_font('Helvetica', '', 8)
            self.set_text_color(90, 105, 110)
            self.cell(0, 5, f'Conjunto autorizado | Pagina {self.page_no()}/{{nb}}', align='R')

    pdf = Relatorio(orientation='P', unit='mm', format='A4')
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.alias_nb_pages()
    pdf.set_title('Relatório de qualidade e acompanhamento operacional')
    pdf.set_author('JB Fraga Contabilidade')
    pdf.add_page()
    def texto(valor, *, negrito=False, tamanho=9, altura=4.6):
        pdf.set_font('Helvetica', 'B' if negrito else '', tamanho)
        pdf.set_text_color(35, 48, 54)
        pdf.multi_cell(0, altura, _pdf_texto(valor), new_x='LMARGIN', new_y='NEXT', wrapmode='WORD')
    def secao(titulo):
        if pdf.get_y() > pdf.h - pdf.b_margin - 22:
            pdf.add_page()
        pdf.ln(4)
        pdf.set_fill_color(232, 244, 241)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_text_color(23, 85, 77)
        pdf.multi_cell(0, 8, _pdf_texto(titulo), fill=True, new_x='LMARGIN', new_y='NEXT')
        pdf.ln(2)
    def exibir_valor(kpi):
        valor = kpi.get('valor')
        if valor is None:
            return 'Sem dados para calcular'
        sufixo = {'percentual': '%', 'dias': ' dias', 'horas': ' h'}.get(kpi.get('unidade'), '')
        return f'{valor}{sufixo}'
    texto('Relatório de acompanhamento', negrito=True, tamanho=18, altura=9)
    texto(f'Referência: {painel.get("referencia", "")} | Horário de Salvador', tamanho=10)
    for chave, valor in (filtros or {}).items():
        if valor not in ('', None):
            texto(f'{chave}: {valor}')
    texto('Dados limitados ao acesso do solicitante e aos filtros informados. Não é uma avaliação automática de pessoas.', tamanho=8)
    secao('Indicadores de desempenho e qualidade')
    for kpi in painel.get('kpis', []):
        texto(f'{kpi["rotulo"]}: {exibir_valor(kpi)}', negrito=True)
        if kpi.get('denominador') is not None:
            texto(f'Base: {kpi.get("numerador") if kpi.get("numerador") is not None else "média"} / {kpi["denominador"]}', tamanho=8)
        texto(kpi['formula'], tamanho=8)
        pdf.ln(1)
    secao('Semáforo operacional')
    texto(' | '.join(f'{cor.capitalize()}: {painel.get("semaforo", {}).get(cor, 0)}'
                     for cor in ('verde', 'amarelo', 'vermelho', 'neutro')), negrito=True)
    texto('Contagem de registros de tarefas, ocorrências e planos; não representa clientes únicos.', tamanho=8)
    secao('Alertas e pendências')
    for alerta in painel.get('alertas', []):
        texto(f'{alerta["rotulo"]}: {alerta["quantidade"]}')
    custos = painel.get('custos', {})
    permitido = custos.get('permitido') is True
    secao('Tempo e custo da operação')
    texto(f'Horas ativas registradas: {custos.get("horas", "0.00")} ({custos.get("minutos", 0)} minutos)')
    if permitido:
        total, informado = custos.get('custo_total'), custos.get('custo_informado')
        texto(f'Custo total: R$ {total}' if total is not None else 'Custo total: indisponível (sem lançamentos ou cobertura incompleta)')
        texto(f'Custo informado: R$ {informado}' if informado is not None else 'Custo informado: indisponível')
        texto(f'Lançamentos ativos sem custo/hora: {custos.get("lancamentos_sem_custo", 0)}')
    else:
        texto('Valores de custo não incluídos neste acesso.')
    texto(custos.get('formula', ''), tamanho=8)

    def registros(titulo, campos, itens):
        secao(titulo)
        if not itens:
            texto('Nenhum registro no conjunto filtrado.')
            return
        for indice, registro in enumerate(itens, 1):
            texto(f'Registro {indice} - ID {registro.get("id", registro.get("usuario_id", registro.get("setor_id", "-")))}', negrito=True)
            for chave, rotulo in campos:
                valor = _campo(registro, chave)
                texto(f'{rotulo}: {valor if valor not in (None, "") else "Não informado"}')
            pdf.ln(3)
    registros('Desempenho por setor', SETORES, painel.get('por_setor', []))
    registros('Execuções e pendências por colaborador',
        COLABORADORES + ([('custo_total', 'Custo total (R$)')] if permitido else []), painel.get('por_colaborador', []))
    registros('Serviços executados e atividades pendentes', TAREFAS, list(tarefas))
    registros('Ocorrências, falhas e não conformidades', OCORRENCIAS, list(ocorrencias))
    registros('Medidas corretivas e preventivas', PLANOS, list(planos))
    registros('Apontamentos de trabalho', HORAS + ([('custo_hora', 'Custo/hora (R$)'),
        ('custo_total', 'Custo registrado (R$)')] if permitido else []), list(horas))
    secao('Metodologia e rastreabilidade')
    for chave, valor in _metodologia(painel, filtros):
        texto(f'{chave}: {valor}', tamanho=8)
    texto('O PDF usa a mesma fonte core dos demais relatórios do sistema. Caracteres fora do conjunto Latin-1 podem aparecer como ?. O Excel preserva o texto Unicode completo.', tamanho=8)
    return bytes(pdf.output())
