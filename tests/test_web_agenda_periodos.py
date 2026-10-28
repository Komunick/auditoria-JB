"""Regressão HTTP sintética da agenda com múltiplas ocorrências e sem prazo."""
import io
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ['AUDITORIA_WEB_DADOS'] = tempfile.mkdtemp(prefix='web_agenda_periodos_')
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from auditoria_fiscal.web import rotas_tarefas as rt
from auditoria_fiscal.web.servidor import criar_app


def ok(resposta, status=200):
    assert resposta.status_code == status, (resposta.status_code, resposta.text)
    return resposta.json() if status == 200 else None


def main():
    rt._hoje = lambda: date(2026, 10, 27)
    app = criar_app()
    adm = TestClient(app)
    ok(adm.post('/api/bootstrap', json=dict(usuario='admin_periodos', nome='Admin sintético', senha='sintetica-123')))
    api = '/api/tarefas'
    executor = ok(adm.post('/api/admin/usuarios', json=dict(usuario='executor_periodos', nome='Executor sintético',
        senha='sintetica-123', permissoes=['aba.tarefas', 'tarefas.executar'])))
    pessoa = TestClient(app)
    ok(pessoa.post('/api/login', json=dict(usuario='executor_periodos', senha='sintetica-123')))
    setor = ok(adm.post(api + '/setores', json=dict(nome='Setor sintético', responsavel_usuario_id=executor['id'],
        membros=[executor['id']])))['id']
    cliente = ok(adm.post('/api/clientes', json=dict(nome='Empresa sintética de períodos')))['id']
    ok(adm.put(f'{api}/clientes/{cliente}/carteira', json=dict(setor_id=setor, responsavel_usuario_id=executor['id'])))
    serie = dict(setor_id=setor, nome='Rotina fracionada sintética', regra_vencimento=dict(
        tipo='periodos_mes_seguinte', periodos=[dict(inicio=1, fim=10), dict(inicio=11, fim=20)], sem_expediente='manter'))
    obrigacao = ok(adm.post(api + '/obrigacoes', json=serie))
    ok(pessoa.post(api + '/obrigacoes', json=serie), 403)
    sem_prazo = ok(adm.post(api + '/obrigacoes', json=dict(setor_id=setor, nome='Rotina mensal sintética',
        regra_vencimento=dict(tipo='sem_vencimento'))))
    ok(adm.post(api + '/obrigacoes', json=dict(setor_id=setor, nome='Rotina fixa sintética',
        regra_vencimento=dict(tipo='dia_mes_seguinte', inicio_dia=1, dia=15, sem_expediente='antecipar'))))
    entrada = dict(competencia='2026-10', setor_id=setor)
    previa = ok(adm.post(api + '/geracao/previa', json=entrada))
    assert previa['total'] == 4, previa
    ocorrencias = [t for t in previa['itens'] if t['obrigacao_id'] == obrigacao['id']]
    assert [(t['ocorrencia'], t['inicio'], t['vencimento']) for t in ocorrencias] == [
        (1, '2026-11-01', '2026-11-10'), (2, '2026-11-11', '2026-11-20')]
    assert [t['origem']['intervalo'] for t in ocorrencias] == ['01–10', '11–20']
    assert next(t for t in previa['itens'] if t['obrigacao_id'] == sem_prazo['id'])['vencimento'] == ''
    ok(TestClient(app).post(api + '/geracao/confirmar', json=dict(token=previa['token'])), 401)
    ok(pessoa.post(api + '/geracao/confirmar', json=dict(token=previa['token'])), 403)
    ok(adm.post(api + '/geracao/confirmar', json=dict(token=previa['token'])))
    ok(adm.post(api + '/geracao/confirmar', json=dict(token=previa['token'])), 404)
    assert ok(adm.post(api + '/geracao/previa', json=entrada))['total'] == 0
    tarefas = ok(pessoa.get(api))['itens']
    assert len(tarefas) == 4
    avisos = ok(pessoa.get(api + '/avisos'))
    assert avisos['email_ativo'] is False
    assert avisos['vencendo'] == avisos['atrasadas'] == 0
    antiga = next(t for t in tarefas if t['obrigacao_id'] == obrigacao['id'] and t['ocorrencia'] == 1)
    detalhe_antes = ok(pessoa.get(f"{api}/{antiga['id']}"))
    # A série cresce, mas tarefas e eventos históricos não são recalculados.
    desatualizada = ok(adm.post(api + '/geracao/previa', json=entrada))
    serie['regra_vencimento']['periodos'].append(dict(inicio=21, fim=30))
    ok(adm.put(f"{api}/obrigacoes/{obrigacao['id']}", json=dict(serie, revision=obrigacao['revision'])))
    ok(adm.post(api + '/geracao/confirmar', json=dict(token=desatualizada['token'])), 409)
    nova = ok(adm.post(api + '/geracao/previa', json=entrada))
    assert nova['total'] == 1 and nova['itens'][0]['ocorrencia'] == 3, nova
    ok(adm.post(api + '/geracao/confirmar', json=dict(token=nova['token'])))
    assert ok(pessoa.get(f"{api}/{antiga['id']}")) == detalhe_antes
    tarefa = next(t for t in tarefas if t['obrigacao_id'] == sem_prazo['id'])
    for situacao in ('em_andamento', 'concluida'):
        tarefa = ok(pessoa.post(f"{api}/{tarefa['id']}/situacao", json=dict(situacao=situacao, revision=tarefa['revision'])))
    assert tarefa['vencimento'] == '' and not tarefa['fora_do_prazo']
    exportacao = adm.get(api + '/exportar', params=dict(visao='setor', setor_id=setor))
    assert exportacao.status_code == 200, exportacao.text
    linhas = list(load_workbook(io.BytesIO(exportacao.content)).active.values)
    assert any('Sem vencimento' in linha for linha in linhas)
    assert any('21–30' in linha for linha in linhas)
    print('OK - agenda HTTP: ocorrências, prévia vinculada, histórico, conclusão sem prazo e exportação')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
