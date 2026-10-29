"""Aba 10: escopo conferido no servidor e prévias privadas de uso único."""
from __future__ import annotations

import io
import math
import os
import secrets
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..core import tarefas as regras
from ..core import planilha_carteira as planilha
from ..core.clientes import ErroClientes
from ..ferramentas.clientes_store import ClientesStore, ConcorrenciaError
from ..ferramentas.tarefas_store import TarefasStore
from ..ferramentas.alertas_email import ConfigSMTP
from ..ferramentas.relatorio_tarefas import gerar_relatorio
from . import auth, permissoes
from .auth import Usuario
from .auditoria import acesso, exigir_aba, exigir_permissao, detalhar
from .infra import caminho_db_clientes

router = APIRouter(prefix='/api/tarefas', tags=['tarefas'])
_trava = threading.Lock()
_previas = {}


def _hoje():
    return regras.hoje_salvador()


def _usuario_ativo(uid):
    u = auth.obter_usuario(uid)
    return bool(u and u['ativo'])


def criar_store():
    return TarefasStore(caminho_db_clientes(), usuario_ativo=_usuario_ativo)


@contextmanager
def _store(*, escrita=False, leitura=False):
    s = criar_store()
    try:
        # Escopo e mutação compartilham o lock: trocar o titular/carteira não
        # pode ocorrer entre a autorização da rota e a escrita no domínio.
        if escrita:
            s.conn.execute('BEGIN IMMEDIATE')
        elif leitura:
            s.conn.execute('BEGIN')
        yield s
        if escrita:
            s.conn.commit()
    except ConcorrenciaError as exc:
        raise HTTPException(409, detail={'detail': 'O registro mudou. Recarregue antes de salvar.',
                                        'current_revision': exc.revision_atual}) from exc
    except (ErroClientes, regras.ErroTarefas) as exc:
        status = 409 if exc.codigo == 'PREVIA_DESATUALIZADA' else 422
        raise HTTPException(status, detail={'detail': exc.mensagem, 'code': exc.codigo}) from exc
    except LookupError as exc:
        raise HTTPException(404, detail='Registro não encontrado.') from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    finally:
        if (escrita or leitura) and s.conn.in_transaction:
            s.conn.rollback()
        s.fechar()


def _quem(u):
    return dict(usuario_id=u.id, usuario_login=u.usuario)


def _tem(u, slug):
    return permissoes.tem_permissao(u, slug)


def _geridos(s, u, hoje=None):
    if u.admin:
        return [setor['id'] for setor in s.listar_setores()]
    return s.setores_responsavel(u.id, hoje if hoje is not None else _hoje()) if _tem(u, 'tarefas.setor') else []


def _exigir_setor(s, u, setor_id):
    if setor_id not in _geridos(s, u):
        raise HTTPException(403, detail='Você não responde por este setor nesta data.')


def _escopo(s, u, visao='cliente', setor_id=None, hoje=None):
    if visao not in ('minhas', 'setor', 'cliente'):
        raise ValueError('Visão desconhecida.')
    if visao == 'minhas':
        return dict(escopo_usuario_id=u.id)
    if _tem(u, 'tarefas.todas'):
        return dict(todas=True)
    geridos = _geridos(s, u, hoje)
    if visao == 'setor':
        if not geridos or (setor_id and setor_id not in geridos):
            raise HTTPException(403, detail='Você não responde por este setor nesta data.')
        return dict(escopo_setores=geridos)
    return dict(escopo_usuario_id=u.id, escopo_setores=geridos)


def _propria(s, u, t, hoje=None):
    titular = t.get('responsavel_usuario_id')
    return bool(titular and s.responsavel_efetivo(t['setor_id'], titular, hoje if hoje is not None else _hoje()) == u.id)


def _ver(s, u, t):
    if not (_tem(u, 'tarefas.todas') or t['setor_id'] in _geridos(s, u) or _propria(s, u, t)):
        raise HTTPException(403, detail='Esta tarefa não está no seu escopo.')


def _dto(s, u, t, usuarios=None, hoje=None):
    hoje = hoje if hoje is not None else _hoje()
    usuarios = usuarios or {p['id']: p for p in auth.listar_usuarios()}
    def nome(uid):
        return usuarios.get(uid, {}).get('nome', '')
    efetivo = s.responsavel_efetivo(t['setor_id'], t['responsavel_usuario_id'], hoje) if t.get('responsavel_usuario_id') else None
    return dict(t, responsavel_efetivo_id=efetivo,
                responsavel_nome=nome(t.get('responsavel_usuario_id')),
                responsavel_efetivo_nome=nome(efetivo), concluida_nome=nome(t.get('concluida_por')),
                conferida_nome=nome(t.get('conferida_por')),
                 pode_executar=bool(_tem(u, 'tarefas.executar') and _propria(s, u, t, hoje)),
                 pode_gerir=t['setor_id'] in _geridos(s, u, hoje))


def _clientes(s, u):
    cs = ClientesStore(caminho_db_clientes())
    try:
        # Configuradores precisam escolher os clientes ainda sem carteira.
        acesso_global = _tem(u, 'tarefas.todas') or (_tem(u, 'tarefas.configurar') and bool(_geridos(s, u)))
        permitidos = None
        if not acesso_global:
            permitidos = set()
            for c in s.listar_carteiras():
                if c['setor_id'] in _geridos(s, u) or (c['responsavel_usuario_id'] and
                        s.responsavel_efetivo(c['setor_id'],c['responsavel_usuario_id'],_hoje()) == u.id):
                    permitidos.add(c['cliente_id'])
            offset = 0
            while True:
                p = s.listar_tarefas(hoje=_hoje(), offset=offset, limite=500, **_escopo(s,u))
                permitidos.update(t['cliente_id'] for t in p['itens'])
                offset += len(p['itens'])
                if not p['itens'] or offset >= p['total']:
                    break
        resultado=[]
        pagina=1
        while True:
            p=cs.listar(pagina=pagina,limite=200)
            resultado.extend({k:c[k] for k in ('id','nome','documento')} for c in p['itens']
                             if permitidos is None or c['id'] in permitidos)
            if pagina >= p['paginas']:
                break
            pagina += 1
        return resultado
    finally:
        cs.fechar()


def _guardar(tipo, u, dados):
    with _trava:
        agora=time.monotonic()
        for chave in list(_previas):
            if agora-_previas[chave]['criada'] > 1800:
                _previas.pop(chave)
        minhas=sorted((p['criada'],t) for t,p in _previas.items() if p['usuario_id']==u.id)
        for _,token in minhas[:-2]:
            _previas.pop(token,None)
        token=secrets.token_urlsafe(24)
        _previas[token]=dict(tipo=tipo,usuario_id=u.id,criada=agora,dados=dados)
        return token


def _consumir(token,tipo,u):
    with _trava:
        p=_previas.get(token)
        if not p or p['usuario_id']!=u.id or p['tipo']!=tipo or time.monotonic()-p['criada']>1800:
            raise HTTPException(404,detail='A prévia expirou ou não pertence a você. Gere uma nova prévia.')
        return _previas.pop(token)['dados']


class Entrada(BaseModel):
    model_config=ConfigDict(extra='forbid')


class SetorEntrada(Entrada):
    nome: str
    responsavel_usuario_id: int | None = None
    ativo: bool = True
    membros: list[int] = Field(default_factory=list)


class SubstituicaoEntrada(Entrada):
    titular_usuario_id: int
    substituto_usuario_id: int
    setor_id: int | None = None
    inicio: str
    fim: str
    motivo: str


class CaracteristicaEntrada(Entrada):
    grupo: str
    nome: str
    exclusiva_no_grupo: bool = False
    ativa: bool = True


class ObrigacaoEntrada(Entrada):
    setor_id: int
    nome: str
    periodicidade: str = 'mensal'
    competencias: list[int] = Field(default_factory=list)
    regra_vencimento: dict
    condicao: dict = Field(default_factory=dict)
    inicio_antecedencia_dias: int | None = None
    exige_conferencia: bool = False
    ativa: bool = True
    revision: int | None = None


class AjusteEntrada(Entrada):
    cliente_id: int
    obrigacao_id: int
    tipo: str
    regra_vencimento: dict | None = None
    valido_de: str = ''
    valido_ate: str = ''
    motivo: str
    revision: int | None = None


class FeriadoEntrada(Entrada):
    data: str
    descricao: str
    abrangencia: str = 'municipal'
    sem_expediente: bool = True


class CarteiraEntrada(Entrada):
    setor_id: int
    responsavel_usuario_id: int | None = None


class CaracteristicasCliente(Entrada):
    caracteristica_ids: list[int] = Field(default_factory=list)


class CaracteristicasLote(CaracteristicasCliente):
    cliente_ids: list[int]


class GeracaoEntrada(Entrada):
    competencia: str
    setor_id: int
    cliente_id: int | None = None


class TokenEntrada(Entrada):
    token: str


class AvulsaEntrada(Entrada):
    cliente_id: int
    setor_id: int
    titulo: str
    vencimento: str
    inicio: str = ''
    competencia: str = ''
    responsavel_usuario_id: int | None = None
    exige_conferencia: bool = False


class SituacaoEntrada(Entrada):
    situacao: str
    revision: int
    comentario: str = ''
    motivo: str = ''


class ComentarioEntrada(Entrada):
    comentario: str
    revision: int


class ReferenciaTarefa(Entrada):
    id: int
    revision: int


class LoteEntrada(Entrada):
    acao: str
    tarefas: list[ReferenciaTarefa] = Field(min_length=1,max_length=500)
    responsavel_usuario_id: int | None = None
    motivo: str


class DecisaoImportacao(Entrada):
    linha: int
    cliente_id: int | None = None
    caracteristica_ids: list[int] = Field(default_factory=list)
    contato_nome: str | None = None
    contato_email: str | None = None


class ImportacaoEntrada(TokenEntrada):
    decisoes: list[DecisaoImportacao]


class ConfiguracaoEntrada(Entrada):
    tarefas_alerta_dias: int = Field(default=3,ge=0,le=365)
    tarefas_resumo_hora: str = '07:00'
    tarefas_aguardando_cliente_dias: int = Field(default=5,ge=0,le=365)


@router.get('/catalogo')
def catalogo(usuario: Usuario=Depends(exigir_aba('tarefas'))):
    with _store() as s:
        geridos=_geridos(s,usuario)
        setores=s.listar_setores()
        todos=_tem(usuario,'tarefas.todas') or _tem(usuario,'setores.administrar')
        visiveis={x['id'] for x in setores if todos or x['id'] in geridos or usuario.id in x.get('membros',[])}
        setores=[x for x in setores if x['id'] in visiveis]
        us=auth.listar_usuarios()
        return dict(setores=setores, usuarios=[{k:u[k] for k in ('id','nome','usuario','ativo')} for u in us],
                    clientes=_clientes(s,usuario), caracteristicas=s.listar_caracteristicas(),
                    obrigacoes=[o for o in s.listar_obrigacoes() if o['setor_id'] in visiveis],
                    ajustes=[a for a in s.listar_ajustes() if a['obrigacao_id'] in
                             {o['id'] for o in s.listar_obrigacoes() if _tem(usuario,'tarefas.todas') or o['setor_id'] in geridos}]
                             if geridos or todos else [],
                    substituicoes=[p for p in s.listar_substituicoes() if todos or p.get('setor_id') in visiveis or p['substituto_usuario_id']==usuario.id],
                    feriados=s.feriados(_hoje().year),configuracao=s.configuracao(),
                    email_ativo=ConfigSMTP.de_ambiente().ativo,setores_geridos=geridos,
                    pode_configurar=_tem(usuario,'tarefas.configurar'),
                    situacoes=[dict(chave=k,rotulo=v) for k,v in regras.SITUACOES.items()])


def _filtros(setor_id=None,cliente_id=None,responsavel_usuario_id=None,competencia='',situacao='',vencimento_de='',vencimento_ate='',sem_responsavel=False,
             texto='',fila='',abertas=False,pendente_conferencia=False):
    return TarefasStore._normalizar_filtros_tarefas(
        {k:v for k,v in locals().items() if v is not None and v != '' and v is not False})


def _listar(s,u,visao, pagina,limite, filtros, hoje=None):
    if pagina<1 or not 1<=limite<=200:
        raise ValueError('Paginação inválida.')
    hoje = hoje if hoje is not None else _hoje()
    dados=s.listar_tarefas(filtros=filtros,hoje=hoje,offset=(pagina-1)*limite,limite=limite,
                          **_escopo(s,u,visao,filtros.get('setor_id'),hoje))
    us={p['id']:p for p in auth.listar_usuarios()}
    return dict(dados,itens=[_dto(s,u,t,us,hoje) for t in dados['itens']],pagina=pagina,limite=limite,
                paginas=max(1,math.ceil(dados['total']/limite)))


@router.get('')
def listar(visao:str='minhas',setor_id:int|None=None,cliente_id:int|None=None,
           responsavel_usuario_id:int|None=None,competencia:str='',situacao:str='',
           vencimento_de:str='',vencimento_ate:str='',sem_responsavel:bool=False,
            texto:str='',fila:str='',abertas:bool=False,pendente_conferencia:bool=False,
           pagina:int=1,limite:int=50,usuario:Usuario=Depends(exigir_aba('tarefas'))):
    with _store() as s:
        return _listar(s,usuario,visao,pagina,limite,_filtros(setor_id,cliente_id,responsavel_usuario_id,
                      competencia,situacao,vencimento_de,vencimento_ate,sem_responsavel,
                      texto,fila,abertas,pendente_conferencia))


@router.get('/painel')
def painel(visao:str='cliente',setor_id:int|None=None,cliente_id:int|None=None,
           responsavel_usuario_id:int|None=None,competencia:str='',situacao:str='',
           vencimento_de:str='',vencimento_ate:str='',sem_responsavel:bool=False,
           texto:str='',fila:str='pendentes',abertas:bool=False,pendente_conferencia:bool=False,
           pagina:int=1,limite:int=10,usuario:Usuario=Depends(exigir_aba('tarefas'))):
    # Escopo, totais, substituicoes e pagina observam a mesma versao do banco.
    with _store(leitura=True) as s:
        hoje = _hoje()
        filtros = _filtros(setor_id,cliente_id,responsavel_usuario_id,competencia,situacao,
                           vencimento_de,vencimento_ate,sem_responsavel,texto,
                           abertas=abertas,pendente_conferencia=pendente_conferencia)
        dados = s.painel_tarefas(filtros,hoje,pagina,limite,fila,
                                 **_escopo(s,usuario,visao,setor_id,hoje))
        usuarios = {p['id']:p for p in auth.listar_usuarios()}
        for grupo in dados['por_responsavel']:
            grupo['nome'] = usuarios.get(grupo['id'],{}).get('nome','') if grupo['id'] is not None else 'Sem responsável'
        dados['fila']['itens'] = [_dto(s,usuario,t,usuarios,hoje) for t in dados['fila']['itens']]
        dados['filtros'] = dict(dados['filtros'],visao=visao)
        return dados


@router.get('/avisos')
def avisos(request:Request,usuario:Usuario=Depends(exigir_aba('tarefas'))):
    with _store() as s:
        contagem=dict(vencendo=0,atrasadas=0)
        offset=0
        while True:
            p=s.listar_tarefas(hoje=_hoje(),offset=offset,limite=500,**_escopo(s,usuario))
            for t in p['itens']:
                c=regras.classificar(t,_hoje(),int(s.configuracao()['tarefas_alerta_dias']))
                contagem['atrasadas']+=int(bool(c['atrasada']))
                if (t.get('vencimento') and t['situacao'] in regras.ABERTAS
                        and 0 <= (date.fromisoformat(t['vencimento'])-_hoje()).days <= int(s.configuracao()['tarefas_alerta_dias'])):
                    contagem['vencendo']+=1
            offset+=len(p['itens'])
            if not p['itens'] or offset>=p['total']:
                break
        agendador=getattr(request.app.state,'tarefas_agendador',None)
        return dict(contagem,email_ativo=ConfigSMTP.de_ambiente().ativo,
                    alerta_dias=int(s.configuracao()['tarefas_alerta_dias']),
                    agendador=agendador.ultimo_resultado if agendador else {'estado':'aguardando'})


@router.get('/exportar')
def exportar(request:Request,visao:str='minhas',setor_id:int|None=None,cliente_id:int|None=None,
             responsavel_usuario_id:int|None=None,competencia:str='',situacao:str='',
             vencimento_de:str='',vencimento_ate:str='',sem_responsavel:bool=False,
              texto:str='',fila:str='',abertas:bool=False,pendente_conferencia:bool=False,
             usuario:Usuario=Depends(acesso('tarefas.exportar'))):
    with _store() as s:
        filtros=_filtros(setor_id,cliente_id,responsavel_usuario_id,competencia,situacao,vencimento_de,vencimento_ate,sem_responsavel,
                         texto,fila,abertas,pendente_conferencia)
        hoje = _hoje()
        itens=[];pagina=1
        while True:
            p=_listar(s,usuario,visao,pagina,200,filtros,hoje);itens.extend(p['itens'])
            if pagina>=p['paginas']:break
            pagina+=1
        dados=gerar_relatorio(itens)
        detalhar(request,f'{len(itens)} tarefa(s) exportada(s)')
        return StreamingResponse(io.BytesIO(dados),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                 headers={'Content-Disposition':'attachment; filename="tarefas.xlsx"','Cache-Control':'no-store'})


@router.post('/setores')
@router.put('/setores/{setor_id}')
def salvar_setor(entrada:SetorEntrada,request:Request,setor_id:int|None=None,
                 usuario:Usuario=Depends(acesso('setores.administrar'))):
    with _store(escrita=True) as s:
        resultado=s.salvar_setor(entrada.model_dump(),id=setor_id,**_quem(usuario))
        detalhar(request,f"setor {resultado['id']}")
        return resultado


@router.post('/substituicoes')
def substituir(entrada:SubstituicaoEntrada,request:Request,usuario:Usuario=Depends(acesso('setores.administrar'))):
    with _store(escrita=True) as s:
        resultado=s.criar_substituicao(entrada.model_dump(),**_quem(usuario))
        detalhar(request,f"substituição {resultado['id']}")
        return resultado


@router.post('/caracteristicas')
@router.put('/caracteristicas/{caracteristica_id}')
def salvar_caracteristica(entrada:CaracteristicaEntrada,request:Request,caracteristica_id:int|None=None,
                          usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        return s.salvar_caracteristica(entrada.model_dump(),id=caracteristica_id,**_quem(usuario))


@router.post('/obrigacoes')
@router.put('/obrigacoes/{obrigacao_id}')
def salvar_obrigacao(entrada:ObrigacaoEntrada,request:Request,obrigacao_id:int|None=None,
                     usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        _exigir_setor(s,usuario,entrada.setor_id)
        if obrigacao_id:
            antiga=next((o for o in s.listar_obrigacoes() if o['id']==obrigacao_id),None)
            if not antiga:raise LookupError()
            _exigir_setor(s,usuario,antiga['setor_id'])
            if entrada.revision is None:raise ValueError('Informe a revisão da obrigação.')
        return s.salvar_obrigacao(entrada.model_dump(exclude={'revision'}),id=obrigacao_id,
                                 revision=entrada.revision,**_quem(usuario))


@router.post('/ajustes')
@router.put('/ajustes/{ajuste_id}')
def salvar_ajuste(entrada:AjusteEntrada,request:Request,ajuste_id:int|None=None,
                  usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        obrigacao=next((o for o in s.listar_obrigacoes() if o['id']==entrada.obrigacao_id),None)
        if not obrigacao:raise LookupError()
        _exigir_setor(s,usuario,obrigacao['setor_id'])
        if ajuste_id:
            antigo=next((a for a in s.listar_ajustes() if a['id']==ajuste_id),None)
            if not antigo:raise LookupError()
            if antigo['cliente_id']!=entrada.cliente_id or antigo['obrigacao_id']!=entrada.obrigacao_id:
                raise ValueError('Mantenha o cliente e a obrigação do ajuste existente.')
            if entrada.revision is None:raise ValueError('Informe a revisão do ajuste.')
        return s.salvar_ajuste(entrada.model_dump(exclude={'revision'}),id=ajuste_id,
                              revision=entrada.revision,**_quem(usuario))


@router.post('/feriados')
def salvar_feriado(entrada:FeriadoEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        return s.salvar_feriado(entrada.model_dump(),**_quem(usuario))


@router.put('/configuracao')
def configuracao(entrada:ConfiguracaoEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    exigir_permissao(usuario,'setores.administrar','A configuração geral exige administrar setores.')
    with _store(escrita=True) as s:
        return s.definir_configuracao(entrada.model_dump(),**_quem(usuario))


@router.get('/clientes/{cliente_id}')
def ficha_cliente(cliente_id:int,usuario:Usuario=Depends(exigir_aba('tarefas'))):
    with _store() as s:
        if cliente_id not in {c['id'] for c in _clientes(s,usuario)}:
            raise HTTPException(403,detail='Cliente fora da sua carteira.')
        ficha=s.ficha_cliente(cliente_id)
        if not _tem(usuario,'tarefas.todas'):
            geridos=_geridos(s,usuario)
            ficha['carteira']=[c for c in ficha['carteira'] if c['setor_id'] in geridos or
                              (c['responsavel_usuario_id'] and s.responsavel_efetivo(c['setor_id'],c['responsavel_usuario_id'],_hoje())==usuario.id)]
            ids={o['id'] for o in s.listar_obrigacoes() if o['setor_id'] in geridos or o['setor_id'] in {c['setor_id'] for c in ficha['carteira']}}
            ficha['ajustes']=[a for a in ficha.get('ajustes',[]) if a['obrigacao_id'] in ids]
        return ficha


@router.put('/clientes/{cliente_id}/carteira')
def carteira(cliente_id:int,entrada:CarteiraEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        _exigir_setor(s,usuario,entrada.setor_id)
        return s.definir_carteira(cliente_id,entrada.setor_id,entrada.responsavel_usuario_id,**_quem(usuario))


def _marcar_caracteristicas(s,u,cliente_ids,ids):
    if not u.admin and not _geridos(s,u):
        raise HTTPException(403,detail='Atribuir características exige responsabilidade por um setor.')
    return s.definir_caracteristicas(cliente_ids,ids,**_quem(u))


@router.put('/clientes/{cliente_id}/caracteristicas')
def caracteristicas_cliente(cliente_id:int,entrada:CaracteristicasCliente,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        return _marcar_caracteristicas(s,usuario,[cliente_id],entrada.caracteristica_ids)


@router.post('/caracteristicas/lote')
def caracteristicas_lote(entrada:CaracteristicasLote,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        return _marcar_caracteristicas(s,usuario,entrada.cliente_ids,entrada.caracteristica_ids)


@router.post('/geracao/previa')
def previa_geracao(entrada:GeracaoEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store() as s:
        _exigir_setor(s,usuario,entrada.setor_id)
        dados=entrada.model_dump()
        previa=s.previa_geracao(**dados,hoje=_hoje())
        token=_guardar('geracao',usuario,dict(entrada=dados,previa=previa))
        return dict(previa,token=token,itens=previa['tarefas'],total=previa['contagens']['novas'])


@router.post('/geracao/confirmar')
def confirmar_geracao(entrada:TokenEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        p=_consumir(entrada.token,'geracao',usuario)
        _exigir_setor(s,usuario,p['entrada']['setor_id'])
        atual=s.previa_geracao(**p['entrada'],hoje=_hoje())
        if atual != p['previa']:
            raise HTTPException(409,detail='A agenda mudou desde a prévia. Gere uma nova prévia.')
        return s.gerar(**p['entrada'],hoje=_hoje(),disparo='manual',previa_esperada=p['previa'],**_quem(usuario))


@router.post('/avulsas')
def avulsa(entrada:AvulsaEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        _exigir_setor(s,usuario,entrada.setor_id)
        return _dto(s,usuario,s.criar_avulsa(entrada.model_dump(),**_quem(usuario)))


@router.post('/lote')
def lote(entrada:LoteEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.gerir'))):
    with _store(escrita=True) as s:
        for ref in entrada.tarefas:
            _exigir_setor(s,usuario,s.obter_tarefa(ref.id,hoje=_hoje())['setor_id'])
        refs=[t.model_dump() for t in entrada.tarefas]
        if entrada.acao=='redistribuir':
            return s.redistribuir(refs,entrada.responsavel_usuario_id,entrada.motivo,**_quem(usuario))
        if entrada.acao=='dispensar':
            return s.dispensar_lote(refs,entrada.motivo,**_quem(usuario))
        raise ValueError('Ação de lote desconhecida.')


@router.post('/importacao/previa')
async def previa_importacao(request:Request,arquivo:UploadFile=File(...),setor_id:int=Form(...),
                            responsavel_usuario_id:int=Form(...),usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store() as s:
        _exigir_setor(s,usuario,setor_id)
        setor=next(x for x in s.listar_setores() if x['id']==setor_id)
        if responsavel_usuario_id not in setor['membros'] or not _usuario_ativo(responsavel_usuario_id):
            raise ValueError('Escolha um membro ativo do setor.')
        extensao=os.path.splitext(arquivo.filename or '')[1].lower()
        if extensao not in ('.xls','.xlsx'):raise HTTPException(422,detail='Envie uma planilha .xls ou .xlsx.')
        with tempfile.TemporaryDirectory(prefix='carteira_previa_') as pasta:
            caminho=os.path.join(pasta,'carteira'+extensao); tamanho=0
            with open(caminho,'wb') as saida:
                while pedaco:=await arquivo.read(1024*1024):
                    tamanho+=len(pedaco)
                    if tamanho>20*1024*1024:raise HTTPException(413,detail='A planilha excede 20 MB.')
                    saida.write(pedaco)
            leitura=planilha.ler_planilha_carteira(caminho)
        clientes=_clientes(s,usuario);caracteristicas=s.listar_caracteristicas();linhas=[]
        from ..core.clientes import chave_texto
        for linha in leitura.linhas:
            resumo=linha.resumo()
            sugestoes=planilha.sugerir_clientes(linha,clientes)
            resumo['sugestoes']=[dict(x,id=x['cliente_id']) for x in sugestoes]
            resumo['caracteristicas_sugeridas']=[c['id'] for c in caracteristicas if
                chave_texto(c['nome']) in {chave_texto(n) for n in resumo.get('sugestoes_caracteristicas',[])}]
            linhas.append(resumo)
        token=_guardar('importacao',usuario,dict(linhas=linhas,setor_id=setor_id,
                responsavel_usuario_id=responsavel_usuario_id,hash_arquivo=leitura.hash_arquivo,
                nome_arquivo=os.path.basename(arquivo.filename or 'carteira')))
        return dict(token=token,linhas=linhas,colunas_ignoradas=leitura.colunas_ignoradas)


@router.post('/importacao/confirmar')
def confirmar_importacao(entrada:ImportacaoEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.configurar'))):
    with _store(escrita=True) as s:
        p=_consumir(entrada.token,'importacao',usuario)
        _exigir_setor(s,usuario,p['setor_id'])
        por_linha={r['linha']:r for r in p['linhas']}; vistos=set();linhas=[]
        for decisao in entrada.decisoes:
            if decisao.linha not in por_linha or decisao.linha in vistos:
                raise ValueError('A decisão não corresponde às linhas da prévia.')
            vistos.add(decisao.linha)
            if decisao.cliente_id is None:continue
            linha=dict(por_linha[decisao.linha],cliente_id=decisao.cliente_id,caracteristica_ids=decisao.caracteristica_ids)
            if linha.get('contato_email_informado') and not linha.get('contato_email') and decisao.contato_email is None:
                raise ValueError('Corrija o e-mail inválido ou confirme o campo vazio na prévia.')
            for campo in ('contato_nome','contato_email'):
                if getattr(decisao,campo) is not None:linha[campo]=getattr(decisao,campo)
            linhas.append(linha)
        return s.importar_carteira(linhas,setor_id=p['setor_id'],responsavel_usuario_id=p['responsavel_usuario_id'],
                                  hash_arquivo=p['hash_arquivo'],nome_arquivo=p['nome_arquivo'],**_quem(usuario))


@router.get('/{tarefa_id}')
def detalhe(tarefa_id:int,usuario:Usuario=Depends(exigir_aba('tarefas'))):
    with _store() as s:
        t=s.obter_tarefa(tarefa_id,hoje=_hoje());_ver(s,usuario,t)
        return dict(_dto(s,usuario,t),eventos=s.eventos(tarefa_id))


@router.post('/{tarefa_id}/situacao')
def situacao(tarefa_id:int,entrada:SituacaoEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.executar'))):
    with _store(escrita=True) as s:
        t=s.obter_tarefa(tarefa_id,hoje=_hoje())
        gestor=t['setor_id'] in _geridos(s,usuario)
        if entrada.situacao in ('conferida','devolvida','dispensada'):
            _exigir_setor(s,usuario,t['setor_id'])
        elif not (_tem(usuario,'tarefas.executar') and _propria(s,usuario,t)):
            raise HTTPException(403,detail='Você só pode executar as próprias tarefas.')
        resultado=s.mudar_situacao(tarefa_id,entrada.situacao,entrada.revision,
                motivo=entrada.motivo or entrada.comentario,responsavel_setor=gestor,hoje=_hoje(),**_quem(usuario))
        detalhar(request,f'tarefa {tarefa_id}: {entrada.situacao}')
        return _dto(s,usuario,resultado)


@router.post('/{tarefa_id}/comentarios')
def comentar(tarefa_id:int,entrada:ComentarioEntrada,request:Request,usuario:Usuario=Depends(acesso('tarefas.executar'))):
    with _store(escrita=True) as s:
        t=s.obter_tarefa(tarefa_id,hoje=_hoje())
        if not ((_tem(usuario,'tarefas.executar') and _propria(s,usuario,t)) or t['setor_id'] in _geridos(s,usuario)):
            raise HTTPException(403,detail='Você não pode comentar esta tarefa.')
        resultado=s.comentar(tarefa_id,entrada.comentario,entrada.revision,**_quem(usuario))
        detalhar(request,f'comentário na tarefa {tarefa_id}')
        return _dto(s,usuario,resultado)
