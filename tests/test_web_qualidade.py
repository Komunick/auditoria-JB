"""Qualidade HTTP: escopo, autoria, revisão, validação e arquivos sintéticos."""
import io
import gc
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
_dados = tempfile.TemporaryDirectory(prefix='qualidade_http_')
for chave in list(os.environ):
    if chave.startswith('AUDITORIA_'):
        del os.environ[chave]
os.environ['AUDITORIA_WEB_DADOS'] = _dados.name
os.environ['AUDITORIA_QUALIDADE_ANEXOS_LOCAL'] = '1'
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from auditoria_fiscal.web.servidor import criar_app


def ok(resposta, status=200):
    assert resposta.status_code == status, (resposta.status_code, resposta.text[:800])
    if 'json' in resposta.headers.get('content-type', ''):
        return resposta.json()
    return resposta


def main():
    app = criar_app()
    adm = TestClient(app)
    ok(adm.post('/api/bootstrap', json={'usuario': 'admin_qa', 'nome': 'Gestão sintética', 'senha': 'teste-qualidade-022'}))
    api = '/api/qualidade'
    ok(TestClient(app).get(api+'/catalogo'), 401)
    from auditoria_fiscal.web import permissoes
    assert not any(p.startswith('qualidade.') or p == 'aba.qualidade' for p in permissoes.PADRAO_NOVO_USUARIO)
    pessoas = {}
    comum = ['aba.qualidade', 'qualidade.registrar', 'aba.tarefas', 'tarefas.executar']
    for nome, slugs in [('pessoa_a', comum), ('pessoa_b', comum),
                        ('lider', comum+['qualidade.gerir','qualidade.validar','qualidade.exportar']),
                        ('diretoria', ['aba.qualidade','qualidade.todas','qualidade.exportar']), ('negado', [])]:
        dados = ok(adm.post('/api/admin/usuarios', json={'usuario':nome, 'nome':nome,
                   'senha':'teste-qualidade-022','permissoes':slugs}))
        c = TestClient(app)
        ok(c.post('/api/login', json={'usuario':nome,'senha':'teste-qualidade-022'}))
        pessoas[nome] = (dados['id'], c)
    uid, a = pessoas['pessoa_a']; bid, b = pessoas['pessoa_b']; lid, lider = pessoas['lider']
    ok(pessoas['negado'][1].get(api+'/painel'),403)
    sid = ok(adm.post('/api/tarefas/setores', json={'nome':'Fiscal sintético','responsavel_usuario_id':lid,'membros':[lid,uid,bid]}))['id']
    sid2 = ok(adm.post('/api/tarefas/setores', json={'nome':'Outro setor','responsavel_usuario_id':bid,'membros':[bid]}))['id']
    cid = ok(adm.post('/api/clientes', json={'nome':'Cliente sintético permitido'}))['id']
    cid2 = ok(adm.post('/api/clientes', json={'nome':'Cliente sintético reservado'}))['id']
    ok(adm.put(f'/api/tarefas/clientes/{cid}/carteira', json={'setor_id':sid,'responsavel_usuario_id':uid}))
    ok(adm.put(f'/api/tarefas/clientes/{cid2}/carteira', json={'setor_id':sid2,'responsavel_usuario_id':bid}))
    tarefa = ok(adm.post('/api/tarefas/avulsas', json={'cliente_id':cid,'setor_id':sid,'titulo':'Serviço sintético',
                 'inicio':'2026-10-01','vencimento':'2026-12-01','responsavel_usuario_id':uid}))
    hoje = date.today().isoformat()
    entrada = dict(data=hoje, cliente_id=cid, setor_id=sid, responsavel_usuario_id=uid,
                   tipo='nao_conformidade', descricao='Evidência sintética restrita', criticidade='alta', prazo='2027-01-01', tarefa_id=tarefa['id'])
    oc = ok(a.post(api+'/ocorrencias', json=entrada))
    oid = oc['id']; assert oc['revision'] == 1
    ok(b.get(f'{api}/ocorrencias/{oid}'),403)
    assert ok(b.get(api+'/ocorrencias'))['total'] == 0
    assert ok(lider.get(api+'/ocorrencias'))['total'] == 1
    assert ok(pessoas['diretoria'][1].get(api+'/ocorrencias'))['total'] == 1
    ok(a.post(api+'/ocorrencias', json=dict(entrada,cliente_id=cid2,setor_id=sid2,tarefa_id=None)),403)
    ok(a.post(api+'/ocorrencias', json=dict(entrada,responsavel_usuario_id=bid)),403)
    ok(a.post(api+'/ocorrencias', json=dict(entrada,usuario_id=bid)),422)
    ok(a.patch(f'{api}/ocorrencias/{oid}', json={'descricao':'Outra descrição','revision':0}),422)
    oc = ok(a.post(f'{api}/ocorrencias/{oid}/comentarios',json={'comentario':'Comentário sintético','revision':oc['revision']}))
    ok(a.patch(f'{api}/ocorrencias/{oid}', json={'descricao':'Revisão antiga','revision':1}),409)
    plano = ok(a.post(api+'/planos', json={'ocorrencia_id':oid,'causa':'Causa identificada',
                 'descricao':'Conferir e corrigir','tipo':'corretiva','responsavel_usuario_id':uid,'prazo':'2027-01-02'}))
    pid = plano['id']
    for estado in ('em_andamento','aguardando_validacao'):
        plano = ok(a.post(f'{api}/planos/{pid}/transicao', json={'situacao':estado,'revision':plano['revision'],'comentario':'Etapa registrada'}))
    ok(a.post(f'{api}/planos/{pid}/transicao', json={'situacao':'validado','revision':plano['revision'],'comentario':'Autoaprovação'}),403)
    plano = ok(lider.post(f'{api}/planos/{pid}/transicao', json={'situacao':'validado','revision':plano['revision'],'comentario':'Solução conferida'}))
    assert plano['situacao'] == 'validado'
    oc = ok(a.get(f'{api}/ocorrencias/{oid}'))
    for estado in ('em_tratamento','resolvida'):
        oc = ok(a.post(f'{api}/ocorrencias/{oid}/transicao',json={'situacao':estado,'revision':oc['revision'],'comentario':'Tratamento registrado'}))
    ok(a.post(f'{api}/ocorrencias/{oid}/transicao',json={'situacao':'encerrada','revision':oc['revision'],'comentario':'Encerrar'}),403)
    oc = ok(lider.post(f'{api}/ocorrencias/{oid}/transicao',json={'situacao':'encerrada','revision':oc['revision'],'comentario':'Conferência da gestão'}))
    assert len(oc['historico']) >= 5
    hora = dict(cliente_id=cid,setor_id=sid,tarefa_id=tarefa['id'],data=hoje,minutos=90,descricao='Tempo sintético')
    ok(a.post(api+'/horas',json=dict(hora,custo_hora='120.00')),403)
    h = ok(a.post(api+'/horas',json=hora))
    assert h['responsavel_usuario_id'] == uid and 'custo_total' not in h
    assert ok(b.get(api+'/horas'))['total'] == 0
    ok(b.post(f"{api}/horas/{h['id']}/cancelar",json={'motivo':'Alheio','revision':h['revision']}),403)
    h = ok(a.post(f"{api}/horas/{h['id']}/cancelar",json={'motivo':'Apontamento incorreto','revision':h['revision']}))
    assert h['cancelado']
    cat = ok(a.get(api+'/catalogo'))
    assert cid in {c['id'] for c in cat['clientes']} and cid2 not in {c['id'] for c in cat['clientes']}
    assert not cat['permissoes']['custos']
    p = ok(pessoas['diretoria'][1].get(api+'/painel'))
    assert p['formato'] == 'qualidade_painel_v1' and p['custos']['permitido'] is False
    ok(a.get(api+'/relatorio.xlsx'),403)
    r = ok(lider.get(api+'/relatorio.xlsx',params={'periodo':'mensal','referencia':hoje}))
    assert r.headers['cache-control'] == 'no-store'
    wb = load_workbook(io.BytesIO(r.content)); assert len(wb.sheetnames) >= 4; wb.close()
    pdf = ok(lider.get(api+'/relatorio.pdf')); assert pdf.content.startswith(b'%PDF')
    ok(adm.get(api+'/painel',params={'de':'2027-01-02','ate':'2027-01-01'}),422)
    ok(adm.get(api+'/painel',params={'situacao':'invalida'}),422)
    # Reabrir outra ocorrência para testar anexo privado sem mutar a encerrada.
    aberta = ok(a.post(api+'/ocorrencias',json=dict(entrada,descricao='Anexo sintético')))
    eml = b'From: qa@example.test\r\nTo: teste@example.test\r\nSubject: QA\r\nDate: Fri, 30 Oct 2026 12:00:00 -0300\r\n\r\nEvidencia sintetica.'
    anexo = ok(a.post(f"{api}/ocorrencias/{aberta['id']}/anexos", files={'arquivo':('evidencia.eml',eml,'message/rfc822')}))
    ok(b.get(f"{api}/anexos/{anexo['id']}/download"),403)
    d = ok(a.get(f"{api}/anexos/{anexo['id']}/download"))
    assert d.content == eml and 'attachment' in d.headers['content-disposition']
    assert d.headers['cache-control']=='no-store'
    assert 'chave_objeto' not in anexo
    ok(a.post(f"{api}/ocorrencias/{aberta['id']}/anexos", files={'arquivo':('falso.pdf',b'<script>bad</script>','application/pdf')}),422)
    ok(a.get(api+'/ocorrencias',params={'setor_id':sid2}),403)
    trilha = ok(adm.get('/api/admin/historico',params={'limite':500}))['itens']
    eventos = [e for e in trilha if e.get('acao','').startswith('qualidade.')]
    assert eventos and not any('Evidência sintética restrita' in str(e) for e in eventos)
    print('OK - qualidade HTTP: permissões, escopo, revisão, validação, horas, anexos e exportações sintéticas')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        gc.collect()
        _dados.cleanup()
