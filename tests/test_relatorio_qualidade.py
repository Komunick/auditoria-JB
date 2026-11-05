"""Relatórios de qualidade: Excel e PDF completos, seguros e sintéticos."""
from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from openpyxl import load_workbook
from auditoria_fiscal.core.qualidade_indicadores import calcular_painel
from auditoria_fiscal.ferramentas.relatorio_qualidade import gerar_excel, gerar_pdf


def fontes():
    tarefa = dict(id=1, titulo='=HYPERLINK("https://invalid.example")', cliente_id=1,
        cliente_nome='+Empresa sintética', setor_id=1, setor_nome='Setor sintético',
        responsavel_usuario_id=2, responsavel_nome='Pessoa sintética', situacao='a_fazer',
        inicio='2026-10-01', vencimento='2026-10-29', criada_em='2026-10-01T12:00:00+00:00')
    ocorrencia = dict(id=2, data='2026-10-23', cliente_id=1, cliente_nome='+Empresa sintética',
        setor_id=1, setor_nome='Setor sintético', responsavel_usuario_id=2, tipo='erro',
        descricao='<img src="file:///arquivo-restrito"> & descrição sintética\x00 fim',
        criticidade='alta', situacao='aberta', prazo='2026-10-29',
        criado_em='2026-10-23T12:00:00+00:00')
    plano = dict(id=3, ocorrencia_id=2, cliente_id=1, setor_id=1, tipo='corretiva',
        descricao='Ação sintética ' * 700, causa='=CAUSA()', responsavel_usuario_id=2,
        situacao='aberto', prazo='2026-10-30', criado_em='2026-10-23T12:00:00+00:00')
    hora = dict(id=4, data='2026-10-29', cliente_id=1, setor_id=1, usuario_id=2,
        usuario_nome='Pessoa sintética', descricao='@apontamento sintético',
        minutos=90, custo_hora='10.01', custo_total='15.02', cancelado=False)
    return [tarefa], [ocorrencia], [plano], [hora]


def main():
    dados = fontes()
    antes = deepcopy(dados)
    painel = calcular_painel(*dados, hoje=date(2026, 10, 30), custos_permitidos=True)
    filtros = {'de': '2026-10-01', 'ate': '2026-10-31', 'cliente': '=externo()'}
    xlsx = gerar_excel(painel, *dados, filtros=filtros)
    wb = load_workbook(BytesIO(xlsx))
    assert wb.sheetnames == ['Indicadores', 'Setores', 'Colaboradores', 'Alertas', 'Tarefas',
                            'Ocorrências', 'Planos de ação', 'Apontamentos', 'Metodologia']
    for aba in wb:
        assert aba.freeze_panes == 'A2'
        assert all(c.data_type != 'f' for row in aba for c in row)
    assert any(c.value == "'+Empresa sintética" for row in wb['Tarefas'] for c in row)
    headers = {c.value: c.column for c in wb['Apontamentos'][1]}
    assert wb['Apontamentos'].cell(2, headers['Custo/hora']).value == 10.01
    assert wb['Apontamentos'].cell(2, headers['Custo registrado']).value == 15.02
    assert 'R$' in wb['Apontamentos'].cell(2, headers['Custo registrado']).number_format
    assert wb['Planos de ação'].cell(2, 6).value == dados[2][0]['descricao']
    assert any(c.value == 'Não conformidades identificadas' for row in wb['Indicadores'] for c in row)
    assert any('2026-10-31' in str(c.value) for row in wb['Metodologia'] for c in row)
    wb.close()
    pdf = gerar_pdf(painel, *dados, filtros=filtros)
    assert pdf.startswith(b'%PDF') and pdf.rstrip().endswith(b'%%EOF')
    assert len(re.findall(rb'/Type /Page\b', pdf)) >= 3, 'Descrição extensa deve paginar, não truncar'
    assert b'/URI' not in pdf and b'/JavaScript' not in pdf and b'/EmbeddedFile' not in pdf
    assert dados == antes, 'Exportadores não alteram os dados'

    # Defesa adicional: mesmo recebendo colunas privadas, export não as usa sem permissão.
    privado = calcular_painel(*dados, hoje='2026-10-30', custos_permitidos=False)
    wb = load_workbook(BytesIO(gerar_excel(privado, *dados)))
    assert not any('Custo' in str(c.value) for c in wb['Apontamentos'][1])
    assert not any(c.value == 15.02 for aba in wb for row in aba for c in row)
    wb.close()
    assert gerar_pdf(privado, *dados).startswith(b'%PDF')
    vazio = calcular_painel([], [], [], [], hoje='2026-10-30', custos_permitidos=True)
    wb = load_workbook(BytesIO(gerar_excel(vazio, [], [], [], [])))
    assert wb['Tarefas'].max_row == 1
    assert wb['Indicadores'].cell(2, 2).value is None, 'Denominador zero não vira 0%'
    wb.close()
    assert gerar_pdf(vazio, [], [], [], []).startswith(b'%PDF')
    # O DTO de horas usa responsável histórico, sem um alias usuario_nome.
    reais = fontes()
    reais[3][0].pop('usuario_nome')
    reais[3][0].pop('usuario_id')
    reais[3][0].update(responsavel_usuario_id=2, responsavel_nome='Autoria sintética histórica')
    wb = load_workbook(BytesIO(gerar_excel(painel, *reais)))
    cabecalho = {c.value:c.column for c in wb['Apontamentos'][1]}
    assert wb['Apontamentos'].cell(2,cabecalho['Colaborador']).value == 'Autoria sintética histórica'
    wb.close()
    print('OK - relatórios de qualidade: Excel/PDF, paginação, texto hostil e custos protegidos')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
