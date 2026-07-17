"""Aplicacao FastAPI da Auditoria Fiscal Web.

Sobe a API (/api/**) e serve o frontend estatico de webui/. Iniciar com
`python servidor.py` (raiz do projeto) ou pelo servidor.ps1.

Todo o /api/** passa pelo middleware do historico (auditoria.py): as rotas
declaram a acao com `Depends(acesso("<slug>"))` e o middleware grava a linha
depois da resposta, com o status real.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auditoria, auth, permissoes
from .auditoria import acesso
from .auth import Usuario, exigir_usuario
from .infra import raiz_projeto
from .sessoes import criar_sessao, descartar_sessao, obter_job, obter_sessao
from .rotas_admin import router as rotas_admin
from .rotas_conferencia import router as rotas_conferencia
from .rotas_comparador import router as rotas_comparador
from .rotas_diff import router as rotas_diff
from .rotas_extracao import router as rotas_extracao
from .rotas_produtos import router as rotas_produtos


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


def criar_app() -> FastAPI:
    app = FastAPI(title="Auditoria Fiscal Web", docs_url=None, redoc_url=None)
    app.middleware("http")(auditoria.middleware_historico)

    # ------------------------------------------------------------------
    # Autenticacao

    @app.get("/api/estado")
    def estado(request: Request) -> dict:
        """Estado inicial para o front: precisa de bootstrap? esta logado?

        Devolve tambem as permissoes: o navegador so DESENHA o que o usuario
        alcanca — quem manda de verdade e o 403 do servidor."""
        usuario = auth.usuario_do_token(
            request.cookies.get(auth.COOKIE_SESSAO))
        return {
            "precisa_bootstrap": not auth.existe_usuario(),
            "logado": usuario is not None,
            "usuario": ({"usuario": usuario.usuario, "nome": usuario.nome,
                         "admin": usuario.admin,
                         "permissoes": permissoes.permissoes_do_usuario(
                             usuario.id, usuario.admin)}
                        if usuario else None),
        }

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
        token = auth.autenticar(entrada.usuario, entrada.senha)
        response.set_cookie(auth.COOKIE_SESSAO, token or "", httponly=True,
                            samesite="lax")
        criado = auth.usuario_do_token(token)
        auditoria.registrar("admin.usuario_criado", criado, request=request,
                            detalhe="primeiro administrador (bootstrap)")
        auditoria.registrar_login(request, criado)
        return {"ok": True}

    @app.post("/api/login")
    def login(entrada: LoginEntrada, request: Request,
              response: Response) -> dict:
        token = auth.autenticar(entrada.usuario, entrada.senha)
        if token is None:
            auditoria.registrar_login(request, None, tentado=entrada.usuario)
            # Mensagem generica: nao revela se o usuario existe.
            raise HTTPException(status_code=401,
                                detail="Usuario ou senha invalidos.")
        response.set_cookie(auth.COOKIE_SESSAO, token, httponly=True,
                            samesite="lax")
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
        response.delete_cookie(auth.COOKIE_SESSAO)
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
        sessao = obter_sessao(sessao_id)
        auditoria.detalhar(request, f"ferramenta: {sessao.ferramenta}")
        descartar_sessao(sessao_id)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, usuario: Usuario = Depends(exigir_usuario)) -> dict:
        """Fora do historico de proposito: o front consulta a cada 700 ms."""
        j = obter_job(job_id)
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

    webui = os.path.join(raiz_projeto(), "webui")
    app.mount("/", WebuiSemCache(directory=webui, html=True), name="webui")
    return app
