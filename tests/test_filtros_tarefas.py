"""Filtros e opções da agenda: escopo real, igualdade literal e dados sintéticos."""
import io
import gc
import os
from pathlib import Path
import sys
import tempfile
from contextlib import ExitStack

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.core.tarefas import ErroTarefas
from test_painel_tarefas import montar, HOJE


def preparar(s, usuarios=None):
    f = montar(s, usuarios)
    literal = 'ISS %_ \\ literal'
    def inserir(conn):
        conn.execute('UPDATE tarefa SET titulo=? WHERE id=?', (literal, f['ids'][1]))
        # Mais que uma página: o catálogo não pode depender da página exibida.
        for _ in range(202):
            s._inserir_tarefa(dict(cliente_id=f['cliente'], setor_id=f['setor'],
                titulo='Duplicada sintética', inicio='2026-10-01', vencimento='2026-12-01',
                responsavel_usuario_id=f['usuarios']['pessoa'], exige_conferencia=False),
                0, 'fixture_sintetica')
        s._inserir_tarefa(dict(cliente_id=f['cliente'], setor_id=f['setor'],
            titulo='Última opção avulsa', inicio='2026-10-01', vencimento='2026-12-31',
            responsavel_usuario_id=f['usuarios']['pessoa'], exige_conferencia=False),
            0, 'fixture_sintetica')
    s._transacao(inserir)
    f['literal'] = literal
    return f


def verificar_store(s, f):
    escopo = dict(hoje=HOJE, escopo_setores=[f['setor']])
    # Falha na versão anterior: título exato ainda não era um filtro aceito.
    r = s.listar_tarefas({'titulo': f['literal']}, **escopo)
    assert [t['id'] for t in r['itens']] == [f['ids'][1]]
    assert s.listar_tarefas({'titulo': 'ISS'}, **escopo)['total'] == 0
    assert s.listar_tarefas({'texto': 'ISS'}, **escopo)['total'] == 1
    assert s.listar_tarefas({'titulo': 'Rotina restrita'}, **escopo)['total'] == 0
    for titulo in ('x' * 201, 12, ['ISS']):
        try:
            s.listar_tarefas({'titulo': titulo}, **escopo)
        except ErroTarefas as e:
            assert e.codigo == 'FILTRO_INVALIDO'
        else:
            raise AssertionError('Título inválido foi aceito')
    assert s.listar_tarefas({'titulo': ''}, **escopo)['total'] == 214
    combinados = dict(cliente_id=f['cliente'], setor_id=f['setor'],
        responsavel_usuario_id=f['usuarios']['pessoa'], competencia='2026-10',
        situacao='em_andamento', fila='pendentes', vencimento_de='2026-10-28',
        vencimento_ate='2026-10-28', abertas=True, titulo=f['literal'])
    assert s.listar_tarefas(combinados, **escopo)['total'] == 1
    assert s.listar_tarefas({**combinados, 'sem_responsavel': True}, **escopo)['total'] == 0
    assert s.listar_tarefas({'fila': 'sem_vencimento', 'vencimento_ate': '2099-01-01'}, **escopo)['total'] == 0
    for de, ate in [('2026-11-01', '2026-10-01'), ('invalida', '2026-10-01')]:
        try:
            s.listar_tarefas({'vencimento_de': de, 'vencimento_ate': ate}, **escopo)
        except ErroTarefas:
            pass
        else:
            raise AssertionError('Intervalo inválido foi aceito')
    opcoes = s.opcoes_filtros_tarefas(**escopo)
    assert opcoes['total_escopo'] == 214
    assert len(opcoes['titulos']) == len(set(opcoes['titulos'])) == 13
    assert 'Última opção avulsa' in opcoes['titulos']
    assert 'Rotina sintetica 08' in opcoes['titulos'], 'Encerradas também são opções'
    assert 'Rotina restrita' not in opcoes['titulos']
    assert s.opcoes_filtros_tarefas(hoje=HOJE) == {'titulos': [], 'total_escopo': 0}
    assert s.opcoes_filtros_tarefas(hoje=HOJE, todas=True)['total_escopo'] == 215
    assert not s.conn.in_transaction
    return combinados


def verificar_web(pasta):
    from fastapi.testclient import TestClient
    from openpyxl import load_workbook
    from auditoria_fiscal.web import rotas_tarefas as rt
    from auditoria_fiscal.web.servidor import criar_app
    app = criar_app()
    hoje_original = rt._hoje
    rt._hoje = lambda: HOJE
    def ok(r, esperado=200):
        assert r.status_code == esperado, (r.status_code, r.text)
        return r.json() if esperado == 200 else None
    try:
        with ExitStack() as stack:
            adm, anon = TestClient(app), TestClient(app)
            stack.callback(adm.close)
            stack.callback(anon.close)
            ok(adm.post('/api/bootstrap', json=dict(usuario='admin_filtros',
                nome='Admin Sintético', senha='somente-sintetica-123')))
            usuarios, clientes = {}, {}
            for nome, permissoes in [
                ('pessoa', ['aba.tarefas']), ('outra', ['aba.tarefas']),
                ('chefe', ['aba.tarefas', 'tarefas.setor', 'tarefas.exportar']),
                ('externo', ['aba.tarefas']), ('substituto', ['aba.tarefas', 'tarefas.setor']),
                ('bloqueado', []), ('vazio', ['aba.tarefas'])]:
                u = ok(adm.post('/api/admin/usuarios', json=dict(usuario=nome,
                    nome='Sintético '+nome, senha='somente-sintetica-123', permissoes=permissoes)))
                usuarios[nome] = u['id']
                clientes[nome] = TestClient(app)
                stack.callback(clientes[nome].close)
                ok(clientes[nome].post('/api/login', json=dict(usuario=nome, senha='somente-sintetica-123')))
            s = rt.criar_store()
            try:
                f = preparar(s, usuarios)
                combinados = verificar_store(s, f)
            finally:
                s.fechar()
            rota = '/api/tarefas/opcoes-filtros'
            ok(anon.get(rota), 401)
            ok(clientes['bloqueado'].get(rota), 403)
            ok(clientes['pessoa'].get(rota, params={'visao': 'setor'}), 403)
            ok(adm.get(rota, params={'visao': 'inventada'}), 422)
            assert ok(clientes['vazio'].get(rota)) == {'titulos': [], 'total_escopo': 0}
            chefe = clientes['chefe']
            esperado = ok(chefe.get(rota, params={'visao': 'setor'}))
            assert esperado['total_escopo'] == 214
            assert 'Rotina restrita' not in esperado['titulos']
            # Outros parâmetros não recortam as opções, mesmo quando a lista seria vazia.
            assert ok(chefe.get(rota, params={'visao': 'setor', 'titulo': 'inexistente',
                'pagina': 999, 'cliente_id': f['cliente']})) == esperado
            assert ok(clientes['pessoa'].get(rota))['total_escopo'] == 208
            assert ok(clientes['externo'].get(rota))['titulos'] == ['Rotina restrita']
            params = {'visao': 'setor', **combinados}
            lista = ok(chefe.get('/api/tarefas', params=params))
            assert lista['total'] == 1
            painel = ok(chefe.get('/api/tarefas/painel', params=params))
            assert painel['resumo']['total'] == painel['fila']['total'] == 1
            assert painel['fila']['itens'][0]['id'] == lista['itens'][0]['id']
            exportado = chefe.get('/api/tarefas/exportar', params=params)
            assert exportado.status_code == 200, exportado.text
            wb = load_workbook(io.BytesIO(exportado.content), read_only=True)
            try:
                linhas = list(wb.active.values)
                assert len(linhas) == 2 and str(linhas[1][0]) == str(f['ids'][1])
                assert linhas[1][3] == f['literal']
            finally:
                wb.close()
            for caminho in ['/api/tarefas', '/api/tarefas/painel', '/api/tarefas/exportar']:
                for erro in [{'titulo': 'a'*201}, {'vencimento_de': '2026-11-01', 'vencimento_ate': '2026-10-01'}]:
                    r = chefe.get(caminho, params={'visao': 'setor', **erro})
                    ok(r, 422)
                    if 'vencimento_de' in erro:
                        assert 'posterior' in r.text
            # A substituição deve transferir opções e total, tal como transfere a listagem.
            s = rt.criar_store()
            try:
                s.criar_substituicao(dict(titular_usuario_id=usuarios['pessoa'],
                    substituto_usuario_id=usuarios['substituto'], setor_id=f['setor'],
                    inicio=HOJE.isoformat(), fim=HOJE.isoformat(), motivo='Ausência sintética'))
            finally:
                s.fechar()
            assert ok(clientes['pessoa'].get(rota)) == {'titulos': [], 'total_escopo': 0}
            assert ok(clientes['substituto'].get(rota))['total_escopo'] == 208
            assert 'Rotina restrita' not in ok(clientes['substituto'].get(rota))['titulos']
    finally:
        rt._hoje = hoje_original
        gc.collect()  # SQLite context managers commit but rely on GC to close connections.


def main():
    anterior = os.environ.get('AUDITORIA_WEB_DADOS')
    try:
        with tempfile.TemporaryDirectory(prefix='filtros_tarefas_sinteticos_') as pasta:
            os.environ['AUDITORIA_WEB_DADOS'] = pasta
            verificar_web(pasta)
    finally:
        if anterior is None:
            os.environ.pop('AUDITORIA_WEB_DADOS', None)
        else:
            os.environ['AUDITORIA_WEB_DADOS'] = anterior
    print('OK - filtros tarefas: opções completas autorizadas, título literal, combinação, datas, exportação e substituição')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
