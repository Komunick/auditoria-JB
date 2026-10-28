"""Previa Fiscal: autorizacao, limpeza do upload e nenhuma escrita cadastral."""
from pathlib import Path
import io
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ['AUDITORIA_WEB_DADOS'] = tempfile.mkdtemp(prefix='web_base_fiscal_sintetica_')

from fastapi.testclient import TestClient
from openpyxl import Workbook
from auditoria_fiscal.core.documentos_br import dv_cnpj
from auditoria_fiscal.web.servidor import criar_app
from auditoria_fiscal.web import rotas_clientes as rc


def arquivo_sintetico():
    livro = Workbook()
    aba = livro.active
    aba.title = 'Carteira'
    aba.append(['Base sintetica'])
    aba.append([None, 'RESPONSAVEL', 'EMPRESAS', 'RESPONSAVEL', 'ZERADAS', 'REGIME DA EMPRESA'])
    documento = '519876540001' + dv_cnpj('519876540001')
    aba.append([None, 'Pessoa de teste', '<b>Empresa de teste</b>', 'Contato de teste', documento, 'Simples Nacional'])
    zeradas = livro.create_sheet('ZERADAS')
    zeradas.append(['Base sintetica'])
    zeradas.append([None, 'EMPRESA', 'CNPJ'])
    zeradas.append([None, 'Outra ocorrencia sintetica', documento])
    saida = io.BytesIO()
    livro.save(saida)
    livro.close()
    return saida.getvalue()


def main():
    app = criar_app()
    adm = TestClient(app)
    assert adm.post('/api/bootstrap', json=dict(usuario='dono_fiscal', nome='Dono sintetico', senha='teste-fiscal-017')).status_code == 200
    caminho = '/api/clientes/base-fiscal/previa'
    conteudo = arquivo_sintetico()
    arquivos = {'arquivo': ('base-sintetica.xlsx', conteudo, 'application/octet-stream')}
    ler_original = rc.pe.ler_planilha_empresas
    chamadas_parser = []
    def ler_registrando(*args, **kwargs):
        chamadas_parser.append(True)
        return ler_original(*args, **kwargs)
    rc.pe.ler_planilha_empresas = ler_registrando
    assert TestClient(app).post(caminho, files=arquivos).status_code == 401
    clientes = {}
    for nome, permissoes in [('consulta', ['aba.clientes']), ('sem_aba', ['clientes.importar']),
                            ('importador', ['aba.clientes', 'clientes.importar'])]:
        r = adm.post('/api/admin/usuarios', json=dict(usuario=nome+'_fiscal', nome='Perfil sintetico',
                     senha='teste-fiscal-017', permissoes=permissoes))
        assert r.status_code == 200, r.text
        clientes[nome] = TestClient(app)
        assert clientes[nome].post('/api/login', json=dict(usuario=nome+'_fiscal', senha='teste-fiscal-017')).status_code == 200
    for nome in ('consulta', 'sem_aba'):
        assert clientes[nome].post(caminho, files=arquivos).status_code == 403
    assert not chamadas_parser, 'Nao analisar upload sem as duas permissoes'

    destinos, uploads = [], []
    receber = rc._receber
    store = rc._store
    def nao_abrir_store(*args, **kwargs):
        raise AssertionError('Previa de origem nao deve abrir nem inicializar banco de clientes')
    async def registrar_upload(arquivo, destino, limite):
        destinos.append(Path(destino))
        uploads.append(arquivo)
        return await receber(arquivo, destino, limite)
    rc._store = nao_abrir_store
    rc._receber = registrar_upload
    previas = dict(rc._previas)
    try:
        r = clientes['importador'].post(caminho, files=arquivos)
        assert r.status_code == 200, r.text
        dados = r.json()
        assert len(chamadas_parser) == 1
        assert dados['somente_leitura'] is True and 'token' not in dados
        assert 'no-store' in r.headers.get('cache-control', '')
        assert dados['contagens']['linhas'] == 2
        assert dados['contagens']['cnpjs_distintos'] == 1
        assert dados['contagens']['grupos_duplicados'] == 1
        assert dados['contagens']['sem_movimento'] == 1
        assert dados['linhas'][0]['sem_movimento'] is None
        assert len({l['id'] for l in dados['linhas']}) == 2
        assert dados['linhas'][0]['nome'] == '<b>Empresa de teste</b>'
        assert not any(p.exists() or p.parent.exists() for p in destinos)
        assert all(a.file.closed for a in uploads)
        assert rc._previas == previas
        # Tipo, pacote e limite rejeitados sem arquivo residual ou token.
        for nome, corpo, esperado in [('base.xls', conteudo, 422), ('base.xlsx', b'invalido', 422)]:
            r = adm.post(caminho, files={'arquivo': (nome, corpo)})
            assert r.status_code == esperado, r.text
        from auditoria_fiscal.core import planilha_empresas as pe
        limite = pe.MAX_PLANILHA_BYTES
        pe.MAX_PLANILHA_BYTES = 32
        try:
            r = adm.post(caminho, files=arquivos)
            assert r.status_code == 413, r.text
        finally:
            pe.MAX_PLANILHA_BYTES = limite
        # Falha inesperada tambem deve fechar e remover o upload.
        def falhar(*args, **kwargs):
            raise RuntimeError('Falha sintetica do parser')
        pe.ler_planilha_empresas = falhar
        try:
            falha = TestClient(app, raise_server_exceptions=False)
            falha.cookies.update(adm.cookies)
            assert falha.post(caminho, files=arquivos).status_code == 500
        finally:
            pe.ler_planilha_empresas = ler_registrando
        assert not any(p.exists() or p.parent.exists() for p in destinos)
        assert all(a.file.closed for a in uploads)
        assert rc._previas == previas
    finally:
        rc._receber = receber
        rc._store = store
        rc.pe.ler_planilha_empresas = ler_original

    eventos = adm.get('/api/admin/historico', params={'limite': 500}).json()['itens']
    relevantes = [e for e in eventos if e['acao'] == 'clientes.importar']
    assert relevantes, 'A previa deve registrar a acao na trilha geral'
    assert any(e['detalhe'] == 'previa base fiscal: 2 linha(s)' and e['http_status'] == 200 for e in relevantes)
    assert {200, 403, 413, 422, 500}.issubset({e['http_status'] for e in relevantes})
    for texto in ('Empresa de teste', 'Contato de teste', 'Pessoa de teste', '519876540001', 'base-sintetica.xlsx'):
        assert texto not in str(relevantes), 'Conteudo do upload vazou para auditoria'
    print('OK - previa Fiscal HTTP: acesso, leitura sem banco, upload removido, cache e auditoria minima')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
