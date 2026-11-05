"""Gestão da qualidade: escopo no servidor, autoria da sessão e revisões."""
from __future__ import annotations

from contextlib import contextmanager
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from ..core import qualidade as q, tarefas as t
from ..core.clientes import ErroClientes
from ..core.qualidade_indicadores import calcular_painel, intervalo_relatorio, classificar_qualidade
from ..ferramentas.clientes_store import ConcorrenciaError
from ..ferramentas.qualidade_store import QualidadeStore
from ..ferramentas import qualidade_anexos as anexos
from ..ferramentas.relatorio_qualidade import gerar_excel, gerar_pdf
from . import auth, permissoes
from .auth import Usuario
from .auditoria import acesso, exigir_permissao
from .infra import caminho_db_clientes

router = APIRouter(prefix='/api/qualidade', tags=['qualidade'])
MODELOS = [
    {'setor': 'Fiscal', 'atividades': ['Apuração de tributos e guias', 'Obrigações acessórias', 'Conferência de notas', 'Atendimento a intimações e malhas', 'Pendências de documentos']},
    {'setor': 'Contábil', 'atividades': ['Conciliação bancária', 'Classificação e lançamentos', 'Fechamento mensal', 'Balancete, balanço e DRE', 'Revisão contábil']},
    {'setor': 'Departamento Pessoal', 'atividades': ['Folha de pagamento', 'Admissões e rescisões', 'Férias e décimo terceiro', 'Obrigações trabalhistas e eSocial', 'Convenções e prazos']},
    {'setor': 'Legalização', 'atividades': ['Abertura, alteração e baixa', 'Processos em órgãos públicos', 'Alvarás e licenças', 'Inscrições e cadastros', 'Protocolos e exigências']},
    {'setor': 'Administrativo', 'atividades': ['Atendimento e solicitações', 'Organização de documentos', 'Demandas internas', 'Distribuição de atividades', 'Acompanhamento de qualidade']},
]


def criar_store():
    return QualidadeStore(caminho_db_clientes(), usuario_ativo=lambda uid: bool(
        (p := auth.obter_usuario(uid)) and p['ativo']))


@contextmanager
def _store(*, escrita=False):
    s = criar_store()
    try:
        s.conn.execute('BEGIN IMMEDIATE' if escrita else 'BEGIN')
        yield s
        if escrita:
            s.conn.commit()
    except ConcorrenciaError as exc:
        raise HTTPException(409, detail={'detail': 'O registro mudou. Recarregue antes de salvar.',
                                        'current_revision': exc.revision_atual}) from exc
    except (ErroClientes, t.ErroTarefas) as exc:
        raise HTTPException(422, detail=exc.mensagem) from exc
    except LookupError as exc:
        raise HTTPException(404, detail='Registro não encontrado.') from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    finally:
        if s.conn.in_transaction:
            s.conn.rollback()
        s.fechar()


def _tem(u, slug):
    return permissoes.tem_permissao(u, 'qualidade.' + slug)


def _exigir(u, slug):
    exigir_permissao(u, 'qualidade.' + slug, 'Você não tem permissão para esta ação.')


def _quem(u):
    return dict(usuario_id=u.id, usuario_login=u.usuario)


def _geridos(s, u):
    if u.admin or (_tem(u, 'todas') and (_tem(u, 'gerir') or _tem(u, 'validar'))):
        return {r['id'] for r in s.listar_setores()}
    return set(s.setores_responsavel(u.id, t.hoje_salvador())) if (_tem(u, 'gerir') or _tem(u, 'validar')) else set()


def _proprio(s, u, r, entidade=''):
    titular = r.get('responsavel_usuario_id')
    if entidade == 'horas':
        return titular == u.id
    return bool(titular and s.responsavel_efetivo(r['setor_id'], titular, t.hoje_salvador()) == u.id)


def _visivel(s, u, r, entidade=''):
    return _tem(u, 'todas') or r['setor_id'] in _geridos(s, u) or _proprio(s, u, r, entidade)


def _ver(s, u, r, entidade=''):
    if not _visivel(s, u, r, entidade):
        raise HTTPException(403, detail='Este registro não está no seu escopo.')


def _editar(s, u, r, entidade=''):
    _ver(s, u, r, entidade)
    if not ((_tem(u, 'registrar') and _proprio(s, u, r, entidade)) or
            (_tem(u, 'gerir') and r['setor_id'] in _geridos(s, u))):
        raise HTTPException(403, detail='Você não pode alterar este registro.')


def _validar(s, u, r):
    _exigir(u, 'validar')
    if r['setor_id'] not in _geridos(s, u):
        raise HTTPException(403, detail='Você não responde por este setor nesta data.')


def _tarefas(s, u):
    itens, offset = [], 0
    escopo = {'todas': True} if _tem(u, 'todas') else {
        'escopo_usuario_id': u.id, 'escopo_setores': list(_geridos(s, u))}
    while True:
        p = s.listar_tarefas(hoje=t.hoje_salvador(), offset=offset, limite=500, **escopo)
        itens.extend(p['itens']); offset += len(p['itens'])
        if not p['itens'] or offset >= p['total']:
            return itens


def _pares(s, u):
    if _tem(u, 'todas'):
        return None
    pares = {(r['cliente_id'], r['setor_id']) for r in s.listar_carteiras()
             if r['setor_id'] in _geridos(s, u) or _proprio(s, u, r)}
    pares.update((r['cliente_id'], r['setor_id']) for r in _tarefas(s, u))
    for lista in (s.listar_ocorrencias(), s.listar_planos()):
        pares.update((r['cliente_id'], r['setor_id']) for r in lista if _visivel(s, u, r))
    return pares


def _vinculos(s, u, dados):
    cid, sid = q.identificador(dados.get('cliente_id')), q.identificador(dados.get('setor_id'))
    pares = _pares(s, u)
    # Visão global é leitura; gestão explícita autoriza cadastros em seus setores.
    gerencia = _tem(u, 'gerir') and sid in _geridos(s, u)
    if not gerencia and (pares is None or (cid, sid) not in pares):
        # Usuário global também pode registrar na própria carteira/tarefa.
        propria = any(r['cliente_id'] == cid and r['setor_id'] == sid and _proprio(s,u,r)
                      for r in s.listar_carteiras()+_tarefas(s,u)+s.listar_ocorrencias()+s.listar_planos())
        if not propria:
            raise HTTPException(403, detail='Cliente e setor fora do seu escopo de registro.')
    rid = q.identificador(dados.get('responsavel_usuario_id', u.id))
    if not gerencia and (not rid or s.responsavel_efetivo(sid, rid, t.hoje_salvador()) != u.id):
        raise HTTPException(403, detail='A atribuição a outra pessoa exige gestão do setor.')
    if dados.get('tarefa_id'):
        tarefa = s.obter_tarefa(q.identificador(dados['tarefa_id']))
        _ver(s, u, tarefa)
        if (tarefa['cliente_id'], tarefa['setor_id']) != (cid, sid):
            raise ValueError('A tarefa deve pertencer ao mesmo cliente e setor.')


def _limpar(valor, custos):
    if isinstance(valor, list):
        return [_limpar(v, custos) for v in valor]
    if isinstance(valor, dict):
        return {k: _limpar(v, custos) for k, v in valor.items()
                if k != 'chave_objeto' and (custos or k not in {'custo_hora', 'custo_total'})}
    return valor


def _dto(s, u, r, entidade):
    d = _limpar(r, _tem(u, 'custos'))
    gerir = _tem(u, 'gerir') and r['setor_id'] in _geridos(s, u)
    editar = gerir or (_tem(u, 'registrar') and _proprio(s, u, r, entidade))
    validar = _tem(u, 'validar') and r['setor_id'] in _geridos(s, u)
    p = auth.obter_usuario(r.get('responsavel_usuario_id')) if r.get('responsavel_usuario_id') else None
    d['responsavel_nome'] = p['nome'] if p else ''
    if entidade == 'horas':
        d['pode_cancelar'] = bool(editar and not r['cancelado'])
        return d
    d['cor'] = classificar_qualidade(r, t.hoje_salvador(), plano=entidade == 'plano')
    terminal = r['situacao'] in {'encerrada', 'validado'}
    transicoes = sorted(q.TRANSICOES[entidade].get(r['situacao'], set()))
    d.update(pode_editar=bool(editar and not terminal and r['situacao'] not in {'resolvida','aguardando_validacao'}),
             pode_comentar=bool(editar and not terminal), pode_validar=bool(validar and not terminal))
    d['transicoes_permitidas'] = [e for e in transicoes if
        (validar if e in {'encerrada','validado'} or (entidade == 'plano' and r['situacao'] == 'aguardando_validacao') else editar)]
    d['pode_transicionar'] = bool(d['transicoes_permitidas'])
    if 'planos' in d:
        d['planos'] = [_dto(s,u,p,'plano') for p in r['planos'] if _visivel(s,u,p)]
    return d


def _filtros(request, s, u, entidade=None):
    permitidos = {'cliente_id','setor_id','responsavel_usuario_id','de','ate','situacao'}
    if entidade == 'ocorrencia': permitidos |= {'tipo','criticidade'}
    if entidade == 'plano': permitidos |= {'tipo','ocorrencia_id'}
    if entidade is None: permitidos |= {'periodo','referencia'}
    f = {k:v for k,v in request.query_params.items() if v != ''}
    q.campos(f, permitidos)
    for k in list(f):
        if k.endswith('_id'):
            try: f[k] = q.identificador(int(f[k]))
            except (ValueError, TypeError): raise ValueError('Filtro de identificador inválido.') from None
        elif k in {'de','ate','referencia'}: f[k] = q.data(f[k])
    if f.get('periodo'):
        inicio,fim = intervalo_relatorio(f['periodo'], f.get('referencia') or t.hoje_salvador().isoformat())
        if not (f.get('de') and f.get('ate')): f['de'],f['ate'] = inicio,fim
    if f.get('de') and f.get('ate') and f['de'] > f['ate']:
        raise ValueError('Início do período deve anteceder o fim.')
    estados = set(q.SITUACOES_OCORRENCIA) | set(q.SITUACOES_PLANO) | set(t.SITUACOES)
    if f.get('situacao') and f['situacao'] not in estados: raise ValueError('Situação desconhecida.')
    if entidade == 'horas' and f.get('situacao'): raise ValueError('Horas não usam filtro de situação.')
    if f.get('tipo'): q.escolha(f['tipo'], q.TIPOS if entidade == 'ocorrencia' else q.TIPOS_PLANO, 'Tipo')
    if f.get('criticidade'): q.escolha(f['criticidade'], q.CRITICIDADES, 'Criticidade')
    if not _tem(u,'todas'):
        pares = _pares(s,u)
        setores = {r['id'] for r in s.listar_setores() if u.id in r['membros']} | _geridos(s,u) | {p[1] for p in pares}
        if f.get('setor_id') and f['setor_id'] not in setores:
            raise HTTPException(403, detail='Setor fora do seu escopo.')
        if f.get('cliente_id') and f['cliente_id'] not in {p[0] for p in pares}:
            raise HTTPException(403, detail='Cliente fora do seu escopo.')
    return f


def _filtrar(itens, f, entidade):
    resultado=[]
    for r in itens:
        dia = r.get('data') or r.get('vencimento') or r.get('inicio') or ''
        if f.get('de') and (not dia or dia < f['de']): continue
        if f.get('ate') and (not dia or dia > f['ate']): continue
        if any(r.get(k) != f[k] for k in ('cliente_id','setor_id','responsavel_usuario_id','situacao','tipo','criticidade','ocorrencia_id') if k in f): continue
        resultado.append(r)
    return resultado


@router.get('/catalogo')
def catalogo(u: Usuario = Depends(acesso('qualidade.consultar'))):
    with _store() as s:
        pares = _pares(s,u)
        setores = [r for r in s.listar_setores() if _tem(u,'todas') or r['id'] in _geridos(s,u)
                   or u.id in r['membros'] or any(p[1] == r['id'] for p in pares)]
        clientes=[]; pagina=1
        while True:
            p=s.listar(pagina=pagina,limite=200)
            clientes.extend({'id':r['id'],'nome':r['nome']} for r in p['itens'] if pares is None or any(x[0]==r['id'] for x in pares))
            if pagina >= p['paginas']: break
            pagina+=1
        usuarios=[{'id':p['id'],'nome':p['nome'],'setor_ids':[r['id'] for r in setores if p['id'] in r['membros']]}
                  for p in auth.listar_usuarios() if p['ativo'] and (p['id']==u.id or any(p['id'] in r['membros'] for r in setores))]
        return dict(clientes=clientes,setores=[{'id':r['id'],'nome':r['nome']} for r in setores],usuarios=usuarios,
                    tipos=[{'valor':v,'rotulo':r} for v,r in q.TIPOS.items()],
                    criticidades=[{'valor':v,'rotulo':r} for v,r in q.CRITICIDADES.items()],modelos=MODELOS,
                    permissoes={k:_tem(u,k) for k in ('registrar','gerir','validar','exportar','custos')},
                    anexos={'disponivel':anexos.disponivel(),'limite_bytes':anexos.LIMITE_BYTES})


def _conjunto(s,u,f):
    tarefas=_filtrar(_tarefas(s,u),f,'tarefa')
    listas=[tarefas]
    for entidade,metodo in [('ocorrencia',s.listar_ocorrencias),('plano',s.listar_planos),('horas',s.listar_horas)]:
        # Filtro de status aplica-se a todas as entidades; horas têm apenas data/autoria.
        ff={k:v for k,v in f.items() if k!='situacao'} if entidade=='horas' else f
        listas.append([_dto(s,u,r,entidade) for r in _filtrar(metodo(),ff,entidade) if _visivel(s,u,r,entidade)])
    cfg=s.configuracao()
    painel=calcular_painel(*listas,hoje=t.hoje_salvador(),
        usuarios={p['id']:p['nome'] for p in auth.listar_usuarios()},
        setores={r['id']:r['nome'] for r in s.listar_setores()},custos_permitidos=_tem(u,'custos'),
        proximos_dias=cfg.get('tarefas_alerta_dias',3))
    return painel,listas


@router.get('/painel')
def painel(request:Request,u:Usuario=Depends(acesso('qualidade.consultar'))):
    with _store() as s:
        return _conjunto(s,u,_filtros(request,s,u))[0]


def _lista(entidade,request,u):
    with _store() as s:
        f=_filtros(request,s,u,entidade)
        nome={'ocorrencia':'ocorrencias','plano':'planos','horas':'horas'}[entidade]
        itens=[_dto(s,u,r,entidade) for r in _filtrar(getattr(s,'listar_'+nome)(),f,entidade) if _visivel(s,u,r,entidade)]
        return {'itens':itens,'total':len(itens)}


@router.get('/ocorrencias')
def ocorrencias(request:Request,u:Usuario=Depends(acesso('qualidade.consultar'))): return _lista('ocorrencia',request,u)
@router.get('/planos')
def planos(request:Request,u:Usuario=Depends(acesso('qualidade.consultar'))): return _lista('plano',request,u)
@router.get('/horas')
def horas(request:Request,u:Usuario=Depends(acesso('qualidade.consultar'))): return _lista('horas',request,u)


@router.post('/ocorrencias')
def criar_ocorrencia(dados:dict,u:Usuario=Depends(acesso('qualidade.registrar'))):
    with _store(escrita=True) as s:
        _vinculos(s,u,dados)
        return _dto(s,u,s.criar_ocorrencia(dados,**_quem(u)),'ocorrencia')


@router.post('/planos')
def criar_plano(dados:dict,u:Usuario=Depends(acesso('qualidade.registrar'))):
    with _store(escrita=True) as s:
        oc=s.obter_ocorrencia(q.identificador(dados.get('ocorrencia_id')))
        _editar(s,u,oc)
        _vinculos(s,u,dict(dados,cliente_id=oc['cliente_id'],setor_id=oc['setor_id']))
        return _dto(s,u,s.criar_plano(dados,**_quem(u)),'plano')


@router.post('/horas')
def registrar_horas(dados:dict,u:Usuario=Depends(acesso('qualidade.registrar'))):
    with _store(escrita=True) as s:
        if dados.get('custo_hora') is not None: _exigir(u,'custos')
        _vinculos(s,u,dados)
        if dados.get('ocorrencia_id'): _ver(s,u,s.obter_ocorrencia(q.identificador(dados['ocorrencia_id'])))
        return _dto(s,u,s.registrar_horas(dados,**_quem(u)),'horas')


def _detalhe(entidade,id,u):
    with _store() as s:
        r=getattr(s,'obter_'+entidade)(id); _ver(s,u,r,entidade)
        return _dto(s,u,r,entidade)

@router.get('/ocorrencias/{id}')
def ocorrencia(id:int,u:Usuario=Depends(acesso('qualidade.consultar'))): return _detalhe('ocorrencia',id,u)
@router.get('/planos/{id}')
def plano(id:int,u:Usuario=Depends(acesso('qualidade.consultar'))): return _detalhe('plano',id,u)


def _mutar(entidade,id,dados,u,acao):
    with _store(escrita=True) as s:
        r=getattr(s,'obter_'+entidade)(id)
        _ver(s,u,r,entidade)
        revision=q.identificador(dados.get('revision'))
        if acao=='transicionar':
            q.escolha(dados.get('situacao'), q.SITUACOES_OCORRENCIA if entidade=='ocorrencia' else q.SITUACOES_PLANO, 'Situação')
        if acao=='transicionar' and (dados.get('situacao') in {'encerrada','validado'} or
            (entidade=='plano' and r['situacao']=='aguardando_validacao')):
            _validar(s,u,r)
        else: _editar(s,u,r,entidade)
        if acao=='editar':
            d={k:v for k,v in dados.items() if k!='revision'}
            _vinculos(s,u,dict(r,**d))
            novo=getattr(s,'editar_'+entidade)(id,d,revision,**_quem(u))
        elif acao=='transicionar':
            q.campos(dados,{'situacao','comentario','revision'})
            novo=getattr(s,'transicionar_'+entidade)(id,dados.get('situacao'),dados.get('comentario',''),revision,**_quem(u))
        else:
            q.campos(dados,{'comentario','revision'})
            novo=getattr(s,'comentar_'+entidade)(id,dados.get('comentario'),revision,**_quem(u))
        return _dto(s,u,novo,entidade)

@router.patch('/ocorrencias/{id}')
def editar_ocorrencia(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))): return _mutar('ocorrencia',id,dados,u,'editar')
@router.patch('/planos/{id}')
def editar_plano(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))): return _mutar('plano',id,dados,u,'editar')
@router.post('/ocorrencias/{id}/transicao')
def transicao_ocorrencia(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))): return _mutar('ocorrencia',id,dados,u,'transicionar')
@router.post('/planos/{id}/transicao')
def transicao_plano(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))): return _mutar('plano',id,dados,u,'transicionar')
@router.post('/ocorrencias/{id}/comentarios')
def comentario_ocorrencia(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))): return _mutar('ocorrencia',id,dados,u,'comentar')
@router.post('/planos/{id}/comentarios')
def comentario_plano(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))): return _mutar('plano',id,dados,u,'comentar')


@router.post('/horas/{id}/cancelar')
def cancelar_horas(id:int,dados:dict,u:Usuario=Depends(acesso('qualidade.alterar'))):
    with _store(escrita=True) as s:
        q.campos(dados,{'motivo','revision'})
        r=s.obter_horas(id); _editar(s,u,r,'horas')
        return _dto(s,u,s.cancelar_horas(id,dados.get('motivo'),q.identificador(dados.get('revision')),**_quem(u)),'horas')


async def _anexar(entidade,id,arquivo,u,request):
    with _store() as s:
        _editar(s,u,getattr(s,'obter_'+entidade)(id),entidade)
    conteudo=await arquivo.read(anexos.LIMITE_BYTES+1)
    meta=None
    try:
        meta=await run_in_threadpool(anexos.salvar,arquivo.filename or '',conteudo)
        u=auth.exigir_usuario(request)
        with _store(escrita=True) as s:
            # Permissões e escopo podem mudar durante o upload.
            exigir_permissao(u,'aba.qualidade','Acesso revogado.')
            _editar(s,u,getattr(s,'obter_'+entidade)(id),entidade)
            return _limpar(s.registrar_anexo(entidade,id,meta,**_quem(u)),False)
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except (HTTPException, LookupError):
        if meta: await _compensar(meta)
        raise
    except Exception as exc:
        if meta: await _compensar(meta)
        raise HTTPException(503,detail='Não foi possível armazenar a evidência. Tente novamente.') from exc
    finally:
        await arquivo.close()


async def _compensar(meta):
    try:
        await run_in_threadpool(anexos.excluir,meta['chave_objeto'])
    except Exception:
        logging.getLogger(__name__).error('QUALIDADE_ANEXO_COMPENSACAO_PENDENTE')


@router.post('/ocorrencias/{id}/anexos')
async def anexo_ocorrencia(id:int,request:Request,arquivo:UploadFile=File(...),u:Usuario=Depends(acesso('qualidade.anexar'))): return await _anexar('ocorrencia',id,arquivo,u,request)
@router.post('/planos/{id}/anexos')
async def anexo_plano(id:int,request:Request,arquivo:UploadFile=File(...),u:Usuario=Depends(acesso('qualidade.anexar'))): return await _anexar('plano',id,arquivo,u,request)


@router.get('/anexos/{id}/download')
def download_anexo(id:int,u:Usuario=Depends(acesso('qualidade.download'))):
    with _store() as s:
        a=s.obter_anexo(id)
        _ver(s,u,getattr(s,'obter_'+a['entidade'])(a['entidade_id']),a['entidade'])
        try: conteudo=anexos.ler(a)
        except Exception as exc: raise HTTPException(503,detail='Evidência indisponível. Contate a gestão.') from exc
        return Response(conteudo,media_type=a['mime'],headers={'Cache-Control':'no-store',
            'Content-Disposition':"attachment; filename*=UTF-8''"+quote(a['nome']), 'X-Content-Type-Options':'nosniff'})


def _relatorio(formato,request,u):
    with _store() as s:
        filtros=_filtros(request,s,u)
        painel,listas=_conjunto(s,u,filtros)
        conteudo=(gerar_excel if formato=='xlsx' else gerar_pdf)(painel,*listas,filtros=filtros)
    tipo='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if formato=='xlsx' else 'application/pdf'
    return Response(conteudo,media_type=tipo,headers={'Cache-Control':'no-store',
        'Content-Disposition':f'attachment; filename="qualidade.{formato}"'})

@router.get('/relatorio.xlsx')
def excel(request:Request,u:Usuario=Depends(acesso('qualidade.exportar'))): return _relatorio('xlsx',request,u)
@router.get('/relatorio.pdf')
def pdf(request:Request,u:Usuario=Depends(acesso('qualidade.exportar'))): return _relatorio('pdf',request,u)
