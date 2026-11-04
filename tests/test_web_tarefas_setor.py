"""Consulta compartilhada: dados sintéticos, sem ampliar gestão nem execução."""
import io
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ['AUDITORIA_WEB_DADOS'] = tempfile.mkdtemp(prefix='tarefas_setor_web_')
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from auditoria_fiscal.web import rotas_tarefas as rt, permissoes
from auditoria_fiscal.web.servidor import criar_app

API = '/api/tarefas'
CONSULTA = 'tarefas.consultar_setor'
BASE = ['aba.tarefas', 'tarefas.executar']


def ok(response, status=200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json() if status == 200 else None


class Ambiente:
    def __init__(self):
        rt._hoje = lambda: date(2026, 11, 4)
        self.app = criar_app()
        self.adm = TestClient(self.app)
        ok(self.adm.post('/api/bootstrap', json=dict(usuario='admin_teste', nome='Admin sintético', senha='sintetica-123')))
        self.pessoas = {}
        for nome, slugs in [('dono', BASE), ('colega', BASE + [CONSULTA]),
                            ('sem_consulta', BASE), ('observador', ['aba.tarefas', CONSULTA]),
                            ('fora', BASE + [CONSULTA]),
                            ('gestor', BASE + ['tarefas.setor', 'tarefas.configurar'])]:
            user = ok(self.adm.post('/api/admin/usuarios', json=dict(usuario=nome, nome='Pessoa ' + nome,
                senha='sintetica-123', permissoes=slugs)))
            client = TestClient(self.app)
            ok(client.post('/api/login', json=dict(usuario=nome, senha='sintetica-123')))
            self.pessoas[nome] = (user['id'], client)
        self.membros = [self.uid(n) for n in ('dono', 'colega', 'sem_consulta', 'observador', 'gestor')]
        self.setor = ok(self.adm.post(API + '/setores', json=self.dados_setor()))['id']
        self.outro = ok(self.adm.post(API + '/setores', json=dict(nome='Outro setor', membros=[self.uid('fora')],
            responsavel_usuario_id=self.uid('fora'))))['id']
        self.cliente = ok(self.adm.post('/api/clientes', json=dict(nome='Empresa fictícia compartilhada')))['id']
        self.cliente_fora = ok(self.adm.post('/api/clientes', json=dict(nome='Empresa fictícia restrita')))['id']
        ok(self.adm.put(f'{API}/clientes/{self.cliente}/carteira', json=dict(setor_id=self.setor, responsavel_usuario_id=self.uid('dono'))))
        ok(self.adm.put(f'{API}/clientes/{self.cliente}/carteira', json=dict(setor_id=self.outro, responsavel_usuario_id=self.uid('fora'))))
        self.tarefa = self.nova('Tarefa do titular')
        self.sem_dono = self.nova('Tarefa sem responsável', dono=None)
        self.propria = self.nova('Tarefa do colega', dono='colega')
        self.restrita = self.nova('Tarefa de outro setor', dono='fora', setor=self.outro, cliente=self.cliente_fora)

    def uid(self, nome):
        return self.pessoas[nome][0]

    def client(self, nome):
        return self.pessoas[nome][1]

    def dados_setor(self, **kwargs):
        return dict(dict(nome='Fiscal sintético', responsavel_usuario_id=self.uid('gestor'), membros=self.membros), **kwargs)

    def nova(self, titulo, dono='dono', setor=None, cliente=None):
        return ok(self.adm.post(API + '/avulsas', json=dict(cliente_id=cliente or self.cliente,
            setor_id=setor or self.setor, titulo=titulo, competencia='2026-11', inicio='2026-11-01',
            vencimento='2026-12-10', responsavel_usuario_id=self.uid(dono) if dono else None)))

    def permissoes(self, nome, slugs):
        ok(self.adm.put(f'/api/admin/usuarios/{self.uid(nome)}/permissoes', json={'permissoes': slugs}))


def main():
    assert CONSULTA in permissoes.SLUGS
    assert CONSULTA not in permissoes.PADRAO_NOVO_USUARIO
    a = Ambiente()
    c = a.client('colega')
    catalogo = ok(c.get(API + '/catalogo'))
    assert catalogo['setores_consultaveis'] == [a.setor] and catalogo['setores_geridos'] == []
    assert {x['id'] for x in catalogo['clientes']} == {a.cliente}
    lista = ok(c.get(API, params={'visao': 'setor'}))
    assert {x['id'] for x in lista['itens']} == {a.tarefa['id'], a.sem_dono['id'], a.propria['id']}
    assert ok(c.get(API))['total'] == 1
    assert ok(c.get(API + '/opcoes-filtros', params={'visao': 'setor'}))['total_escopo'] == 3
    assert ok(c.get(API + '/painel', params={'visao': 'setor'}))['fila']['total'] == 3
    assert ok(c.get(API, params={'visao': 'cliente'}))['total'] == 3
    detalhe = ok(c.get(f"{API}/{a.tarefa['id']}"))
    assert not detalhe['pode_executar'] and not detalhe['pode_gerir']
    assert detalhe['eventos']
    ficha = ok(c.get(f'{API}/clientes/{a.cliente}'))
    assert {x['setor_id'] for x in ficha['carteira']} == {a.setor}
    ok(c.get(f'{API}/clientes/{a.cliente_fora}'), 403)
    ok(c.get(f"{API}/{a.restrita['id']}"), 403)
    ok(c.get(API, params={'visao': 'setor', 'setor_id': a.outro}), 403)
    ok(a.client('sem_consulta').get(API, params={'visao': 'setor'}), 403)
    ok(c.get('/api/clientes'), 403)
    ok(c.get('/api/qualidade/catalogo'), 403)
    for destino in ('em_andamento', 'concluida', 'dispensada', 'a_fazer'):
        ok(c.post(f"{API}/{a.tarefa['id']}/situacao", json=dict(situacao=destino, revision=1)), 403)
    ok(c.post(f"{API}/{a.tarefa['id']}/comentarios", json=dict(comentario='Não autorizado', revision=1)), 403)
    ok(c.post(f"{API}/{a.tarefa['id']}/vencimento", json=dict(vencimento='2026-12-11', motivo='Teste', revision=1)), 403)
    ok(c.post(API + '/geracao/previa', json=dict(setor_id=a.setor, competencia='2026-12')), 403)
    ok(c.get(API + '/exportar', params={'visao': 'setor'}), 403)
    a.permissoes('colega', BASE + [CONSULTA, 'tarefas.exportar'])
    arquivo = c.get(API + '/exportar', params={'visao': 'setor'})
    assert arquivo.status_code == 200
    assert load_workbook(io.BytesIO(arquivo.content)).active.max_row == 4
    # Revogações são verificadas em cada requisição, inclusive acesso direto.
    a.permissoes('colega', BASE)
    ok(c.get(API, params={'visao': 'setor'}), 403)
    ok(c.get(f"{API}/{a.tarefa['id']}"), 403)
    a.permissoes('colega', BASE + [CONSULTA])
    ok(a.adm.put(f'{API}/setores/{a.setor}', json=a.dados_setor(ativo=False)))
    ok(c.get(API, params={'visao': 'setor'}), 403)
    ok(a.adm.put(f'{API}/setores/{a.setor}', json=a.dados_setor(membros=[x for x in a.membros if x != a.uid('colega')])))
    ok(c.get(API, params={'visao': 'setor'}), 403)
    ok(c.get(f"{API}/{a.tarefa['id']}"), 403)
    print('OK - consulta do setor: escopo, leitura, revogações, exportação e isolamento')


if __name__ == '__main__':
    main()
