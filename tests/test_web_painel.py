"""Central HTTP: nenhuma metrica ou nome fora do escopo autorizado."""
import io
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ['AUDITORIA_WEB_DADOS'] = tempfile.mkdtemp(prefix='web_painel_sintetico_')
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from auditoria_fiscal.web import rotas_tarefas as rt
from auditoria_fiscal.web.servidor import criar_app
from test_painel_tarefas import montar, HOJE


def ok(r, status=200):
    assert r.status_code == status, (r.status_code, r.text)
    return r.json() if status == 200 else None


def main():
    rt._hoje=lambda:HOJE
    app=criar_app(); adm=TestClient(app); api='/api/tarefas'
    ok(adm.post('/api/bootstrap',json=dict(usuario='admin_painel',nome='Admin sintetico',senha='sintetica-123')))
    ok(TestClient(app).get(api+'/painel'),401)
    usuarios={}; clientes={}
    for nome,permissoes in (
        ('pessoa',['aba.tarefas','tarefas.executar']), ('outra',['aba.tarefas']),
        ('chefe',['aba.tarefas','tarefas.setor','tarefas.exportar']),
        ('externo',['aba.tarefas']), ('substituto',['aba.tarefas','tarefas.executar']),
        ('diretoria',['aba.tarefas','tarefas.todas']), ('bloqueado',[])):
        usuarios[nome]=ok(adm.post('/api/admin/usuarios',json=dict(usuario=nome+'_painel',
            nome='Pessoa sintetica '+nome,senha='sintetica-123',permissoes=permissoes)))['id']
        clientes[nome]=TestClient(app)
        ok(clientes[nome].post('/api/login',json=dict(usuario=nome+'_painel',senha='sintetica-123')))
    s=rt.criar_store()
    try: fixture=montar(s,usuarios)
    finally: s.fechar()
    ok(clientes['bloqueado'].get(api+'/painel'),403)
    pessoa=clientes['pessoa']; chefe=clientes['chefe']; global_=clientes['diretoria']
    p=ok(pessoa.get(api+'/painel',params={'limite':1}))
    assert p['hoje']==HOJE.isoformat() and p['fuso']=='America/Bahia' and p['alerta_dias']==3
    assert p['resumo']['total']==5 and p['fila']['total']==5 and len(p['fila']['itens'])==1
    assert p['filtros']['visao']=='cliente'
    assert {r['id'] for r in p['por_responsavel']}=={usuarios['pessoa']}
    assert p['fila']['itens'][0]['pode_executar'] and not p['fila']['itens'][0]['pode_gerir']
    assert 'Pessoa sintetica externo' not in str(p) and 'Rotina restrita' not in str(p)
    ok(pessoa.get(api+'/painel',params={'visao':'setor','setor_id':fixture['setor']}),403)
    assert ok(pessoa.get(api+'/painel',params={'setor_id':fixture['separado']}))['resumo']['total']==0
    assert ok(pessoa.get(api+'/painel',params={'responsavel_usuario_id':usuarios['externo']}))['por_responsavel']==[]
    assert ok(chefe.get(api+'/painel'))['resumo']['total']==11
    assert ok(global_.get(api+'/painel'))['resumo']['total']==12
    ok(pessoa.get(f"{api}/{fixture['secreto']}"),403)
    for fila in ('todas','pendentes','atrasadas','hoje','proximas','aguardando_cliente','conferencia','sem_vencimento','sem_responsavel'):
        filtros=dict(visao='setor',setor_id=fixture['setor'],fila=fila,limite=200)
        painel=ok(chefe.get(api+'/painel',params=filtros))
        lista=ok(chefe.get(api,params=filtros))
        assert painel['resumo']['total']==11
        assert {t['id'] for t in painel['fila']['itens']}=={t['id'] for t in lista['itens']}
        r=chefe.get(api+'/exportar',params=filtros)
        assert r.status_code==200,r.text
        wb=load_workbook(io.BytesIO(r.content))
        assert {int(linha[0]) for linha in list(wb.active.values)[1:]}=={t['id'] for t in lista['itens']}
        wb.close()
    for filtros,total in (({'texto':'01'},1),({'abertas':True},8),({'pendente_conferencia':True},2),
                          ({'competencia':'2026-09'},1),({'vencimento_de':'2000-01-01'},8)):
        parametros=dict(visao='setor',setor_id=fixture['setor'],fila='todas',**filtros)
        assert ok(chefe.get(api,params=parametros))['total']==total
        assert ok(chefe.get(api+'/painel',params=parametros))['resumo']['total']==total
    for caminho in ('','/painel','/exportar'):
        for parametros in ({'fila':'inexistente'}, {'texto':'x'*201}):
            ok(chefe.get(api+caminho,params=parametros),422)
    for parametros in ({'pagina':0},{'limite':201},{'visao':'invalida'}):
        ok(chefe.get(api+'/painel',params=parametros),422)
    # Escopo, classificacao e DTO compartilham exatamente a data desta consulta.
    chamadas=[]
    def hoje_unico():
        chamadas.append(True)
        assert len(chamadas)==1,'Mais de uma captura de hoje durante o painel'
        return HOJE
    rt._hoje=hoje_unico
    ok(chefe.get(api+'/painel'))
    assert len(chamadas)==1
    rt._hoje=lambda:HOJE
    print('OK - painel HTTP: autorizacao, filtros, nomes, filas/exportacao e data unica')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
