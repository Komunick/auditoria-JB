"""Revisão independente HTTP: revogação, substituições, custo e estados finais."""
import gc
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from test_web_qualidade import TestClient, criar_app, ok, _dados
from auditoria_fiscal.core.tarefas import hoje_salvador
from auditoria_fiscal.web import auth, permissoes, rotas_qualidade
from openpyxl import load_workbook


def sem_custo(valor):
    if isinstance(valor, dict):
        assert not {'custo_hora', 'custo_total'} & valor.keys(), valor.keys()
        for item in valor.values():
            sem_custo(item)
    elif isinstance(valor, list):
        for item in valor:
            sem_custo(item)


def main():
    achados = []
    app = criar_app()
    adm = TestClient(app)
    ok(adm.post('/api/bootstrap', json={'usuario':'admin_seguranca', 'nome':'Gestão sintética',
                                       'senha':'teste-seguranca-022'}))
    api = '/api/qualidade'
    base = ['aba.qualidade', 'qualidade.registrar', 'qualidade.exportar', 'aba.tarefas', 'tarefas.executar']
    pessoas = {}
    for nome, flags in [('titular', base+['qualidade.custos']), ('substituto', base),
                        ('lider', base+['qualidade.gerir', 'qualidade.validar']),
                        ('outro', base), ('leitor', ['aba.qualidade','qualidade.todas','qualidade.exportar'])]:
        uid = ok(adm.post('/api/admin/usuarios', json={'usuario':nome, 'nome':nome,
            'senha':'teste-seguranca-022', 'permissoes':flags}))['id']
        c = TestClient(app)
        ok(c.post('/api/login',json={'usuario':nome,'senha':'teste-seguranca-022'}))
        pessoas[nome] = (uid, c)
    aid, a = pessoas['titular']; bid, b = pessoas['substituto']
    lid, lider = pessoas['lider']; oid, outro = pessoas['outro']
    sid = ok(adm.post('/api/tarefas/setores',json={'nome':'Setor sintético 1',
        'responsavel_usuario_id':lid,'membros':[aid,bid,lid]}))['id']
    sid2 = ok(adm.post('/api/tarefas/setores',json={'nome':'Setor sintético 2',
        'responsavel_usuario_id':oid,'membros':[oid]}))['id']
    cid = ok(adm.post('/api/clientes',json={'nome':'Cliente do titular'}))['id']
    cid2 = ok(adm.post('/api/clientes',json={'nome':'Cliente de outro setor'}))['id']
    for cliente,setor,pessoa in [(cid,sid,aid),(cid2,sid2,oid)]:
        ok(adm.put(f'/api/tarefas/clientes/{cliente}/carteira', json={
            'setor_id':setor,'responsavel_usuario_id':pessoa}))
    hoje = hoje_salvador().isoformat()
    entrada = dict(data=hoje,cliente_id=cid,setor_id=sid,responsavel_usuario_id=aid,
        tipo='nao_conformidade',descricao='Ocorrência sintética restrita',criticidade='alta',prazo=hoje)
    oc = ok(a.post(api+'/ocorrencias',json=entrada))
    for invalido in ([], {}, True, False):
        ok(a.post(f"{api}/ocorrencias/{oc['id']}/transicao",json={
            'situacao':invalido,'revision':oc['revision'],'comentario':'Teste de tipo'}),422)
        ok(a.post(api+'/ocorrencias',json=dict(entrada,responsavel_usuario_id=invalido)),422)
        ok(a.post(api+'/ocorrencias',json=dict(entrada,data=invalido)),422)
        ok(a.patch(f"{api}/ocorrencias/{oc['id']}",json={'revision':invalido,'descricao':'Tipo recusado'}),422)
    for filtro in ({'de':'2026-02-30'}, {'de':'[]'}, {'referencia':'false'},
                   {'responsavel_usuario_id':'true'}, {'cliente_id':'[]'}, {'periodo':'{}'}):
        ok(a.get(api+'/painel',params=filtro),422)
    hora = ok(a.post(api+'/horas',json=dict(cliente_id=cid,setor_id=sid,data=hoje,
        descricao='Tempo sintético reservado',minutos=61,custo_hora='987.65')))
    assert hora['custo_total'] == '1004.11'
    # Permissões são consultadas novamente sem exigir outro login; histórico também é limpo.
    ok(adm.put(f'/api/admin/usuarios/{aid}/permissoes',json={'permissoes':base}))
    sem_custo(ok(a.get(api+'/horas')))
    h = ok(a.post(f"{api}/horas/{hora['id']}/cancelar",json={'motivo':'Correção sintética','revision':hora['revision']}))
    sem_custo(h)
    assert h['historico'] and h['cancelado']
    wb = load_workbook(BytesIO(ok(a.get(api+'/relatorio.xlsx')).content))
    assert not any(c.value in (987.65,1004.11,'987.65','1004.11') for aba in wb for row in aba for c in row)
    wb.close()
    ok(a.post(api+'/horas',json=dict(cliente_id=cid,setor_id=sid,data=hoje,
        descricao='Sem autorização monetária',minutos=30,custo_hora='1.00')),403)
    for rota in ('/painel','/ocorrencias','/planos','/horas','/relatorio.xlsx'):
        ok(a.get(api+rota,params={'cliente_id':cid2}),403)
        ok(a.get(api+rota,params={'setor_id':sid2}),403)
    # Troca de responsável efetivo tira o titular e dá o mesmo escopo ao substituto.
    ok(adm.post('/api/tarefas/substituicoes',json={'titular_usuario_id':aid,
        'substituto_usuario_id':bid,'setor_id':sid,'inicio':hoje,'fim':hoje,'motivo':'Ausência sintética'}))
    ok(a.get(f"{api}/ocorrencias/{oc['id']}"),403)
    oc = ok(b.get(f"{api}/ocorrencias/{oc['id']}"))
    assert ok(b.get(api+'/ocorrencias'))['total'] == 1
    assert ok(b.get(api+'/horas'))['total'] == 0, 'Autoria do tempo é histórica; não muda com substituição'
    ok(outro.get(f"{api}/ocorrencias/{oc['id']}"),403)
    oc = ok(b.post(f"{api}/ocorrencias/{oc['id']}/comentarios",json={
        'comentario':'Substituto autorizado','revision':oc['revision']}))
    ok(b.post(f"{api}/ocorrencias/{oc['id']}/comentarios",json={
        'comentario':'Conflito sintético','revision':1}),409)
    # Upload revogado depois da gravação do objeto: registro recusado e objeto removido.
    salvar = rotas_qualidade.anexos.salvar
    objeto = []
    def salvar_revogando(*args, **kwargs):
        meta = salvar(*args, **kwargs)
        objeto.append(meta['chave_objeto'])
        permissoes.definir(bid, [], por='revisao_sintetica')
        return meta
    eml = b'From: qa@example.test\r\nTo: x@example.test\r\nSubject: Sintetico\r\nDate: Fri, 30 Oct 2026 12:00:00 -0300\r\n\r\nEvidencia.'
    with patch.object(rotas_qualidade.anexos,'salvar',salvar_revogando):
        ok(b.post(f"{api}/ocorrencias/{oc['id']}/anexos",files={'arquivo':('seguro.eml',eml,'message/rfc822')}),403)
    assert objeto and not (Path(_dados.name)/'qualidade'/'anexos'/objeto[0].split('/')[-1]).exists()
    ok(b.get(api+'/catalogo'),403)
    ok(adm.put(f'/api/admin/usuarios/{bid}/permissoes',json={'permissoes':base}))
    oc = ok(b.get(f"{api}/ocorrencias/{oc['id']}"))
    assert not oc['anexos']
    def salvar_encerrando_sessao(*args, **kwargs):
        meta = salvar(*args, **kwargs)
        objeto.append(meta['chave_objeto'])
        auth.encerrar_sessoes_do_usuario(bid)
        return meta
    with patch.object(rotas_qualidade.anexos,'salvar',salvar_encerrando_sessao):
        resultado = b.post(f"{api}/ocorrencias/{oc['id']}/anexos",files={'arquivo':('sessao.eml',eml,'message/rfc822')})
    if resultado.status_code == 200:
        achados.append('Upload aceita sessão encerrada durante a gravação do objeto.')
    else:
        ok(resultado,401)
        assert not (Path(_dados.name)/'qualidade'/'anexos'/objeto[-1].split('/')[-1]).exists()
    ok(b.post('/api/login',json={'usuario':'substituto','senha':'teste-seguranca-022'}))
    # Rebaixamento de administrador mantém a sessão, mas deve revogar o poder no request em curso.
    demovido_id = ok(adm.post('/api/admin/usuarios',json={'usuario':'admin_temporario',
        'nome':'Admin sintético temporário','senha':'teste-seguranca-022','admin':True,'permissoes':[]}))['id']
    demovido = TestClient(app)
    ok(demovido.post('/api/login',json={'usuario':'admin_temporario','senha':'teste-seguranca-022'}))
    def salvar_desativando_admin(*args, **kwargs):
        meta = salvar(*args, **kwargs)
        objeto.append(meta['chave_objeto'])
        auth.atualizar_usuario(demovido_id,'Admin sintético temporário',False,True)
        return meta
    with patch.object(rotas_qualidade.anexos,'salvar',salvar_desativando_admin):
        resultado = demovido.post(f"{api}/ocorrencias/{oc['id']}/anexos",files={'arquivo':('admin.eml',eml,'message/rfc822')})
    if resultado.status_code == 200:
        achados.append('Upload conserva u.admin=True depois de despromover o administrador durante a gravação do objeto.')
    else:
        ok(resultado,403)
        assert not (Path(_dados.name)/'qualidade'/'anexos'/objeto[-1].split('/')[-1]).exists()
    oc = ok(b.get(f"{api}/ocorrencias/{oc['id']}"))
    plano = ok(b.post(api+'/planos',json={'ocorrencia_id':oc['id'], 'causa':'Causa sintética',
        'descricao':'Ação sintética','tipo':'corretiva','responsavel_usuario_id':bid,'prazo':hoje}))
    for estado in ('em_andamento','aguardando_validacao'):
        plano = ok(b.post(f"{api}/planos/{plano['id']}/transicao",json={
            'situacao':estado,'revision':plano['revision'],
            'comentario':None if estado=='em_andamento' else 'Etapa sintética'}))
    if plano['pode_editar']:
        achados.append('Plano em validação anuncia pode_editar=true, embora o store recuse a edição.')
    ok(b.patch(f"{api}/planos/{plano['id']}",json={'revision':plano['revision'],'descricao':'Não deve editar em validação'}),422)
    plano = ok(lider.post(f"{api}/planos/{plano['id']}/transicao",json={
        'situacao':'validado','revision':plano['revision'],'comentario':'Validado pela chefia'}))
    assert plano['pode_comentar'] is False
    resultado = b.post(f"{api}/planos/{plano['id']}/comentarios",json={
        'comentario':'Comentário após validação','revision':plano['revision']})
    if resultado.status_code == 200:
        achados.append('Plano validado aceita comentário e altera revision, apesar de pode_comentar=false.')
    else:
        ok(resultado,422)
    for estado in ('em_tratamento','resolvida'):
        oc = ok(b.post(f"{api}/ocorrencias/{oc['id']}/transicao",json={
            'situacao':estado,'revision':oc['revision'],
            'comentario':None if estado=='em_tratamento' else 'Tratamento sintético'}))
    oc = ok(lider.post(f"{api}/ocorrencias/{oc['id']}/transicao",json={
        'situacao':'encerrada','revision':oc['revision'],'comentario':'Encerramento definitivo'}))
    assert oc['pode_comentar'] is False
    resultado = b.post(f"{api}/ocorrencias/{oc['id']}/comentarios",json={
        'comentario':'Comentário após encerramento','revision':oc['revision']})
    if resultado.status_code == 200:
        achados.append('Ocorrência encerrada aceita comentário e altera revision, apesar de pode_comentar=false.')
    else:
        ok(resultado,422)
    # Conceder leitura global não pode tirar o direito de registrar na tarefa própria.
    global_id = ok(adm.post('/api/admin/usuarios',json={'usuario':'global_registrador',
        'nome':'Global sintético','senha':'teste-seguranca-022','permissoes':base+['qualidade.todas']}))['id']
    global_c = TestClient(app)
    ok(global_c.post('/api/login',json={'usuario':'global_registrador','senha':'teste-seguranca-022'}))
    global_sid = ok(adm.post('/api/tarefas/setores',json={'nome':'Setor global sintético',
        'responsavel_usuario_id':global_id,'membros':[global_id]}))['id']
    global_cid = ok(adm.post('/api/clientes',json={'nome':'Cliente da tarefa sem carteira'}))['id']
    global_tarefa = ok(adm.post('/api/tarefas/avulsas',json={'cliente_id':global_cid,
        'setor_id':global_sid,'titulo':'Tarefa própria sem carteira','inicio':hoje,
        'vencimento':hoje,'responsavel_usuario_id':global_id}))
    resultado = global_c.post(api+'/ocorrencias',json=dict(entrada,cliente_id=global_cid,
        setor_id=global_sid,responsavel_usuario_id=global_id,tarefa_id=global_tarefa['id']))
    if resultado.status_code == 403:
        achados.append('Leitura global impede registro em tarefa própria sem carteira; a mesma pessoa sem qualidade.todas consegue registrar.')
        ok(adm.put(f'/api/admin/usuarios/{global_id}/permissoes',json={'permissoes':base}))
        ok(global_c.post(api+'/ocorrencias',json=dict(entrada,cliente_id=global_cid,
            setor_id=global_sid,responsavel_usuario_id=global_id,tarefa_id=global_tarefa['id'])))
    else:
        ok(resultado)
    assert not achados, '\n'.join(achados)
    print('OK - qualidade segurança: revogação, custos recursivos, escopo, substituição, upload e estados terminais')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        gc.collect()
        _dados.cleanup()
