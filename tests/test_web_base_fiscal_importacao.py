"""Propostas Fiscal: rota sem carga, dois uploads, snapshot e autorização."""
from pathlib import Path
import gc
import hashlib
import io
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
_DADOS = tempfile.TemporaryDirectory(prefix='web_importacao_fiscal_sintetica_')
os.environ['AUDITORIA_WEB_DADOS'] = _DADOS.name

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from auditoria_fiscal.core.documentos_br import dv_cnpj
from auditoria_fiscal.core.planilha_empresas import ler_planilha_empresas
from auditoria_fiscal.ferramentas.relatorio_base_fiscal import gerar_relatorio_base_fiscal
from auditoria_fiscal.web.servidor import criar_app
from auditoria_fiscal.web import rotas_clientes as rc


def fonte_relatorio():
    livro = Workbook()
    aba = livro.active
    aba.title = 'Fiscal sintético'
    aba.append([None, 'RESPONSAVEL', 'EMPRESAS', 'RESPONSAVEL', 'CNPJ', 'REGIME DA EMPRESA'])
    cnpj = '019876540001' + dv_cnpj('019876540001')
    aba.append([None, 'Equipe sintética', 'Empresa sintética HTTP', 'Contato sintético', cnpj, 'Lucro Real'])
    saida = io.BytesIO()
    livro.save(saida)
    livro.close()
    fonte = saida.getvalue()
    with tempfile.TemporaryDirectory() as pasta:
        p = Path(pasta) / 'fonte.xlsx'
        p.write_bytes(fonte)
        relatorio = gerar_relatorio_base_fiscal(ler_planilha_empresas(p), nome_arquivo='fonte.xlsx')
    return fonte, relatorio, cnpj


def editar(conteudo, aba, celula, valor):
    livro = load_workbook(io.BytesIO(conteudo))
    livro[aba][celula] = valor
    saida = io.BytesIO()
    livro.save(saida)
    livro.close()
    return saida.getvalue()


def main():
    app = criar_app()
    adm = TestClient(app)
    assert adm.post('/api/bootstrap', json=dict(usuario='dono_previa', nome='Perfil sintético',
                    senha='teste-previa-020')).status_code == 200
    rota = '/api/clientes/base-fiscal/importacao/previa'
    fonte, relatorio, cnpj = fonte_relatorio()
    hash_fonte = hashlib.sha256(fonte).hexdigest()
    dados = {'hash_esperado': hash_fonte}
    def arquivos(revisado=relatorio):
        return {'arquivo': ('fonte-sintetica.xlsx', fonte), 'correcoes': ('revisao-sintetica.xlsx', revisado)}
    # RED: a rota ainda não existe.
    assert TestClient(app).post(rota, files=arquivos(), data=dados).status_code == 401
    perfis = []
    for i, permissoes in enumerate([['aba.clientes'], ['clientes.importar'], ['aba.clientes', 'clientes.importar']]):
        login = f'revisor_previa_{i}'
        r = adm.post('/api/admin/usuarios', json=dict(usuario=login, nome='Perfil sintético',
                     senha='teste-previa-020', permissoes=permissoes))
        assert r.status_code == 200, r.text
        cliente = TestClient(app)
        assert cliente.post('/api/login', json=dict(usuario=login, senha='teste-previa-020')).status_code == 200
        perfis.append(cliente)

    originais = rc.pe.ler_planilha_empresas, rc._receber, rc._store
    chamadas, caminhos, uploads = [], [], []
    def ler(*args, **kwargs):
        chamadas.append(True)
        return originais[0](*args, **kwargs)
    async def receber(arquivo, destino, limite):
        caminhos.append(Path(destino))
        uploads.append(arquivo)
        return await originais[1](arquivo, destino, limite)
    def store_proibido(*args, **kwargs):
        raise AssertionError('A prévia não pode inicializar nem migrar o store cadastral')
    rc.pe.ler_planilha_empresas, rc._receber, rc._store = ler, receber, store_proibido
    previas = dict(rc._previas)
    banco = Path(_DADOS.name) / 'clientes.db'
    try:
        for cliente in perfis[:2]:
            assert cliente.post(rota, files=arquivos(), data=dados).status_code == 403
        assert not chamadas and not caminhos
        for cliente in (perfis[2], adm):
            r = cliente.post(rota, files=arquivos(), data=dados)
            assert r.status_code == 200, r.text
            p = r.json()
            assert p['somente_leitura'] is True and 'token' not in p
            assert p['formato'] == 'base_fiscal_importacao_v1'
            assert p['contagens']['incluir'] == 1
            assert p['hash_arquivo'] == hash_fonte
            assert p['hash_correcoes'] == hashlib.sha256(relatorio).hexdigest()
            assert p['cadastro_disponivel'] is False and p['cadastro_consultado_em']
            assert r.headers['cache-control'] == 'no-store'
        assert not banco.exists(), 'Consulta a base vazia não deve criar banco'

        # Apenas fixture local: cadastro divergente e schema anterior não podem ser migrados.
        conn = sqlite3.connect(banco)
        conn.execute('CREATE TABLE cliente(id INTEGER PRIMARY KEY, nome TEXT, documento TEXT, contato_nome TEXT, situacao TEXT, revision INTEGER)')
        conn.execute('INSERT INTO cliente VALUES(1,?,?,?,?,3)', ('Nome cadastrado sintético', cnpj, 'Contato sintético', 'ativo'))
        conn.execute('PRAGMA user_version=1')
        conn.commit()
        antes = list(conn.iterdump())
        r = adm.post(rota, files=arquivos(), data=dados)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p['cadastro_disponivel'] is True
        assert p['contagens']['conflito'] == 1 and p['linhas'][0]['cadastro']['revision'] == 3
        proposta = editar(relatorio, 'Correções', 'H2', 'Nome cadastrado sintético')
        r = adm.post(rota, files=arquivos(proposta), data=dados)
        assert r.status_code == 200, r.text
        assert r.json()['contagens']['existente'] == 1
        assert list(conn.iterdump()) == antes
        conn.close()

        # Origem ou identidade divergentes não podem produzir prévia parcial.
        assert adm.post(rota, files=arquivos(), data={'hash_esperado': '0'*64}).status_code == 409
        alterado = editar(relatorio, 'Resumo', 'B4', '0'*64)
        assert adm.post(rota, files=arquivos(alterado), data=dados).status_code == 409
        for aba, celula, valor in [('Correções', 'A2', 'id-inventado'), ('Correções', 'D2', 'Origem alterada'),
                                   ('Correções', 'H2', '=1+1')]:
            r = adm.post(rota, files=arquivos(editar(relatorio, aba, celula, valor)), data=dados)
            assert r.status_code == 422, r.text
        r = adm.post(rota, files=arquivos(editar(relatorio, 'Correções', 'K2', 'x'*161)), data=dados)
        assert r.status_code == 200, r.text
        assert r.json()['contagens']['pendente'] == 1

        n = len(chamadas)
        for invalido in ({}, {'hash_esperado': 'g'*64}, {'hash_esperado': 'a'}):
            assert adm.post(rota, files=arquivos(), data=invalido).status_code == 422
        assert len(chamadas) == n
        assert adm.post(rota, files={'arquivo': ('fonte.xlsx', fonte)}, data=dados).status_code == 422
        for campo in ('arquivo', 'correcoes'):
            for nome, conteudo in [('base.xls', fonte), ('base.xlsx', b'invalido')]:
                fs = arquivos()
                fs[campo] = (nome, conteudo)
                assert adm.post(rota, files=fs, data=dados).status_code == 422
        limite = rc.pe.MAX_PLANILHA_BYTES
        rc.pe.MAX_PLANILHA_BYTES = 32
        try:
            assert adm.post(rota, files=arquivos(), data=dados).status_code == 413
        finally:
            rc.pe.MAX_PLANILHA_BYTES = limite

        # Banco existe, mas está inválido: nunca fingir que todos os clientes são novos.
        banco.write_bytes(b'banco invalido sintetico')
        assert adm.post(rota, files=arquivos(), data=dados).status_code == 503
        def falhar(*args, **kwargs):
            raise RuntimeError('Falha sintética de leitura')
        rc.pe.ler_planilha_empresas = falhar
        falha = TestClient(app, raise_server_exceptions=False)
        falha.cookies.update(adm.cookies)
        assert falha.post(rota, files=arquivos(), data=dados).status_code == 500
        falha.close()
        assert all(a.file.closed for a in uploads)
        assert not any(p.exists() or p.parent.exists() for p in caminhos)
        assert rc._previas == previas
    finally:
        rc.pe.ler_planilha_empresas, rc._receber, rc._store = originais

    eventos = adm.get('/api/admin/historico', params={'limite':500}).json()['itens']
    relevantes = [e for e in eventos if e['acao'] == 'clientes.importar']
    assert any(e['detalhe'] == 'previa importacao base fiscal: 1 linha(s)' for e in relevantes)
    assert {200,403,409,413,422,500,503}.issubset({e['http_status'] for e in relevantes})
    for privado in (cnpj,hash_fonte,'Empresa sintética HTTP','Equipe sintética','revisao-sintetica.xlsx'):
        assert privado not in str(relevantes), 'Dados de empresa não pertencem à trilha geral'
    for c in [adm,*perfis]:
        c.close()
    gc.collect()
    _DADOS.cleanup()
    print('OK - importacao Fiscal HTTP: duas permissoes, dois arquivos, snapshot, erros e nenhuma carga')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
