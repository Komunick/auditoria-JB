"""Aplicacao FastAPI da Auditoria Fiscal Web.

Sobe a API (/api/**) e serve o frontend estatico de webui/. Iniciar com
`python servidor.py` (raiz do projeto) ou pelo servidor.ps1.

Todo o /api/** passa pelo middleware do historico (auditoria.py): as rotas
declaram a acao com `Depends(acesso("<slug>"))` e o middleware grava a linha
depois da resposta, com o status real.
"""

from __future__ import annotations

import os
import logging
from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auditoria, auth, permissoes, seguranca
from .auditoria import acesso
from .auth import Usuario, exigir_usuario
from .infra import raiz_projeto
from .sessoes import criar_sessao, descartar_sessao, obter_job, obter_sessao
from .rotas_admin import router as rotas_admin
from .rotas_clientes import router as rotas_clientes
from .rotas_conciliacao import router as rotas_conciliacao
from .rotas_conferencia import router as rotas_conferencia
from .rotas_comparador import router as rotas_comparador
from .rotas_diff import router as rotas_diff
from .rotas_patrimonio import router as rotas_patrimonio
from .rotas_nfse import router as rotas_nfse
from .rotas_extracao import router as rotas_extracao
from .rotas_produtos import router as rotas_produtos
from .rotas_tarefas import router as rotas_tarefas, criar_store as criar_store_tarefas
from .agendador import Agendador
from .versao import identificar_versao

logger = logging.getLogger('uvicorn.error.aplicacao')


def _versao_indisponivel():
    return dict(sha=None, origem='indisponivel', arvore='desconhecida', iniciado_em=None)


def _usuarios_alertas():
    resultado=[]
    for pessoa in auth.listar_usuarios():
        if not pessoa['ativo']:
            continue
        usuario=Usuario(pessoa['id'],pessoa['nome'],pessoa['usuario'],pessoa['admin'])
        if not permissoes.tem_permissao(usuario,'aba.tarefas'):
            continue
        resultado.append(dict(pessoa,pode_setor=permissoes.tem_permissao(usuario,'tarefas.setor')))
    return resultado


@asynccontextmanager
async def _ciclo_de_vida(app):
    # Snapshot do checkout na inicialização; não muda se o disco mudar depois.
    app.state.versao_execucao = dict(identificar_versao(raiz_projeto()),
                                    iniciado_em=datetime.now(timezone.utc).isoformat())
    # Migração antes de atender; a thread tem suas próprias conexões SQLite.
    store=criar_store_tarefas()
    store.fechar()
    agendador=Agendador(criar_store_tarefas,_usuarios_alertas)
    app.state.tarefas_agendador=agendador
    versao=app.state.versao_execucao
    logger.info('aplicacao_inicio sha=%s origem=%s arvore=%s iniciado_em=%s',
                versao['sha'] or 'indisponivel', versao['origem'], versao['arvore'], versao['iniciado_em'])
    agendador.iniciar()
    try:
        yield
    finally:
        agendador.parar()


# Modelos no nivel do modulo: com `from __future__ import annotations`, o
# FastAPI nao resolve classes Pydantic locais (viram string) e trataria o
# corpo como query param.
class LoginEntrada(BaseModel):
    usuario: str
    senha: str


class BootstrapEntrada(BaseModel):
    usuario: str
    nome: str = ""
    senha: str


class SessaoEntrada(BaseModel):
    ferramenta: str


class AbaEntrada(BaseModel):
    aba: str


class WebuiSemCache(StaticFiles):
    """Frontend que o navegador SEMPRE revalida antes de reusar.

    Sem isto, o Starlette manda os arquivos so com ETag/Last-Modified e o
    navegador aplica cache heuristico: depois de um `git pull` + reinicio, a
    pessoa podia ficar com o app.js novo e o conferencia.js velho — telas
    quebradas e, pior, controles de permissao antigos. "Atualizar o sistema =
    atualizar o servidor uma unica vez" (SC-002 da spec) so vale se o
    navegador conferir a cada carga. Na rede interna o custo e um 304."""

    def file_response(self, *args, **kwargs) -> Response:
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["cache-control"] = "no-cache, must-revalidate"
        return resposta


def _gravar_cookie_sessao(response: Response, request: Request,
                          token: str) -> None:
    """Cookie de sessao: HttpOnly e SameSite=lax como sempre, mais Secure
    quando a requisicao chegou por HTTPS (direto ou pelo proxy declarado)
    ou quando o operador forca (AUDITORIA_COOKIES_SEGUROS=1). Na LAN em HTTP
    puro o Secure faria o navegador descartar o cookie."""
    response.set_cookie(auth.COOKIE_SESSAO, token, httponly=True,
                        samesite="lax",
                        secure=seguranca.cookie_seguro(request))


def criar_app() -> FastAPI:
    app = FastAPI(title="Auditoria Fiscal Web", docs_url=None, redoc_url=None, lifespan=_ciclo_de_vida)
    app.state.versao_execucao = _versao_indisponivel()
    app.middleware("http")(auditoria.middleware_historico)
    # Registrado por ultimo = a camada mais externa: Host e Origin sao
    # conferidos antes de qualquer rota (requisicao recusada nao vira linha
    # do historico nem tentativa de login) e toda resposta da API, inclusive
    # as de erro, sai com nosniff e CSP.
    app.add_middleware(seguranca.SegurancaMiddleware)

    # ------------------------------------------------------------------
    # Autenticacao

    @app.get("/api/estado")
    def estado(request: Request) -> dict:
        """Estado inicial para o front: precisa de bootstrap? esta logado?

        Devolve tambem as permissoes: o navegador so DESENHA o que o usuario
        alcanca — quem manda de verdade e o 403 do servidor."""
        usuario = auth.usuario_do_token(
            request.cookies.get(auth.COOKIE_SESSAO))
        resultado = {
            "precisa_bootstrap": not auth.existe_usuario(),
            "logado": usuario is not None,
            "usuario": ({"usuario": usuario.usuario, "nome": usuario.nome,
                         "admin": usuario.admin,
                         "permissoes": permissoes.permissoes_do_usuario(
                             usuario.id, usuario.admin)}
                        if usuario else None),
        }
        if usuario and usuario.admin:
            agendador = getattr(request.app.state, 'tarefas_agendador', None)
            resultado['operacao'] = {
                'versao': dict(request.app.state.versao_execucao),
                'agendador': deepcopy(agendador.diagnostico) if agendador else {'estado': 'aguardando'},
            }
        return resultado

    @app.post("/api/bootstrap")
    def bootstrap(entrada: BootstrapEntrada, request: Request,
                  response: Response) -> dict:
        """Cria o PRIMEIRO administrador (somente quando nao ha usuarios)."""
        if auth.existe_usuario():
            raise HTTPException(status_code=403,
                                detail="Ja existe usuario cadastrado.")
        try:
            auth.criar_usuario(entrada.usuario, entrada.nome, entrada.senha,
                               admin=True)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # Sem IP de proposito: o primeiro administrador acabou de nascer e
        # nao pode ficar de fora por falhas de antes da instalacao.
        token = auth.autenticar(entrada.usuario, entrada.senha)
        _gravar_cookie_sessao(response, request, token or "")
        criado = auth.usuario_do_token(token)
        auditoria.registrar("admin.usuario_criado", criado, request=request,
                            detalhe="primeiro administrador (bootstrap)")
        auditoria.registrar_login(request, criado)
        return {"ok": True}

    @app.post("/api/login")
    def login(entrada: LoginEntrada, request: Request,
              response: Response) -> dict:
        try:
            token = auth.autenticar(entrada.usuario, entrada.senha,
                                    ip=seguranca.ip_do_cliente(request))
        except auth.LoginBloqueado as bloqueio:
            # 429 com Retry-After: a tela mostra quanto falta, e o bloqueio
            # fica na trilha como as outras tentativas negadas.
            auditoria.registrar_login(request, None, tentado=entrada.usuario,
                                      http_status=429)
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas seguidas. Aguarde "
                       f"{bloqueio.segundos} segundo(s) e tente de novo.",
                headers={"Retry-After": str(bloqueio.segundos)}) from None
        if token is None:
            auditoria.registrar_login(request, None, tentado=entrada.usuario)
            # Mensagem generica: nao revela se o usuario existe.
            raise HTTPException(status_code=401,
                                detail="Usuario ou senha invalidos.")
        _gravar_cookie_sessao(response, request, token)
        auditoria.registrar_login(request, auth.usuario_do_token(token))
        # Cada login fecha as sessoes vencidas e registra a saida por tempo de
        # quem nao voltou — assim "quando saiu" nao fica em aberto para sempre.
        auditoria.varrer_sessoes_expiradas()
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response) -> dict:
        token = request.cookies.get(auth.COOKIE_SESSAO)
        usuario = auth.usuario_do_token(token)
        if token:
            auth.encerrar_sessao(token)
        if usuario is not None:
            auditoria.registrar("sessao.logout", usuario, request=request)
        response.delete_cookie(auth.COOKIE_SESSAO, httponly=True,
                               samesite="lax",
                               secure=seguranca.cookie_seguro(request))
        return {"ok": True}

    # ------------------------------------------------------------------
    # Navegacao (o "o que acessou" do historico)

    @app.post("/api/eventos/aba")
    def evento_aba(entrada: AbaEntrada, request: Request,
                   usuario: Usuario = Depends(acesso("navegacao.aba"))) -> dict:
        """O front avisa qual aba o usuario abriu."""
        aba = (entrada.aba or "").strip()
        if f"aba.{aba}" not in permissoes.SLUGS:
            raise HTTPException(status_code=422, detail="Aba desconhecida.")
        auditoria.exigir_permissao(
            usuario, f"aba.{aba}",
            "Voce nao tem acesso a esta ferramenta. Fale com o administrador.")
        auditoria.detalhar(request, f"aba: {aba}")
        return {"ok": True}

    # ------------------------------------------------------------------
    # Sessoes de trabalho + jobs

    @app.post("/api/sessoes")
    def nova_sessao(entrada: SessaoEntrada, request: Request,
                    usuario: Usuario = Depends(
                        acesso("sessao.trabalho_nova"))) -> dict:
        ferramenta = (entrada.ferramenta or "").strip()
        if f"aba.{ferramenta}" not in permissoes.SLUGS:
            raise HTTPException(status_code=422,
                                detail="Ferramenta desconhecida.")
        auditoria.exigir_permissao(
            usuario, f"aba.{ferramenta}",
            "Voce nao tem acesso a esta ferramenta. Fale com o administrador.")
        sessao = criar_sessao(ferramenta, usuario.usuario)
        auditoria.detalhar(request, f"ferramenta: {ferramenta}")
        return {"sessao_id": sessao.id}

    @app.delete("/api/sessoes/{sessao_id}")
    def remover_sessao(sessao_id: str, request: Request,
                       usuario: Usuario = Depends(
                           acesso("sessao.trabalho_descartada"))) -> dict:
        sessao = obter_sessao(sessao_id, usuario)
        auditoria.detalhar(request, f"ferramenta: {sessao.ferramenta}")
        descartar_sessao(sessao_id, usuario)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, ferramenta: str,
            usuario: Usuario = Depends(exigir_usuario)) -> dict:
        """Fora do historico de proposito: o front consulta a cada 700 ms.

        Rota COMPARTILHADA pelas seis ferramentas, por isso `ferramenta` e
        obrigatoria: alem do dono, o cliente declara qual aba espera, e um
        job_id de outra aba responde como inexistente. Ferramenta
        desconhecida cai no mesmo 404 — a rota nunca diz se o problema foi o
        ID, o dono ou a aba."""
        j = obter_job(job_id, usuario, ferramenta)
        return {"status": j.status, "erro": j.erro,
                "resultado": j.resultado, "descricao": j.descricao}

    # ------------------------------------------------------------------
    # Ferramentas + frontend

    app.include_router(rotas_admin)
    app.include_router(rotas_conferencia)
    app.include_router(rotas_comparador)
    app.include_router(rotas_diff)
    app.include_router(rotas_extracao)
    app.include_router(rotas_produtos)
    app.include_router(rotas_conciliacao)
    app.include_router(rotas_patrimonio)
    app.include_router(rotas_nfse)
    app.include_router(rotas_clientes)
    app.include_router(rotas_tarefas)

    # O mount estatico e' curinga em "/": tem de ser o ULTIMO. Registrado
    # antes, engoliria /api/conciliacao/** e a ferramenta responderia 404 do
    # frontend em vez da API.
    webui = os.path.join(raiz_projeto(), "webui")
    app.mount("/", WebuiSemCache(directory=webui, html=True), name="webui")
    return app
