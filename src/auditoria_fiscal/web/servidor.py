"""Aplicacao FastAPI da Auditoria Fiscal Web.

Sobe a API (/api/**) e serve o frontend estatico de webui/. Iniciar com
`python servidor.py` (raiz do projeto) ou pelo servidor.ps1.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth
from .auth import Usuario, exigir_usuario
from .infra import raiz_projeto
from .sessoes import criar_sessao, descartar_sessao, obter_job, obter_sessao
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


class NovoUsuarioEntrada(BaseModel):
    usuario: str
    nome: str = ""
    senha: str
    admin: bool = False


class SessaoEntrada(BaseModel):
    ferramenta: str


def criar_app() -> FastAPI:
    app = FastAPI(title="Auditoria Fiscal Web", docs_url=None, redoc_url=None)

    # ------------------------------------------------------------------
    # Autenticacao

    @app.get("/api/estado")
    def estado(request: Request) -> dict:
        """Estado inicial para o front: precisa de bootstrap? esta logado?"""
        usuario = auth.usuario_do_token(
            request.cookies.get(auth.COOKIE_SESSAO))
        return {
            "precisa_bootstrap": not auth.existe_usuario(),
            "logado": usuario is not None,
            "usuario": ({"usuario": usuario.usuario, "nome": usuario.nome,
                         "admin": usuario.admin} if usuario else None),
        }

    @app.post("/api/bootstrap")
    def bootstrap(entrada: BootstrapEntrada, response: Response) -> dict:
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
        return {"ok": True}

    @app.post("/api/login")
    def login(entrada: LoginEntrada, response: Response) -> dict:
        token = auth.autenticar(entrada.usuario, entrada.senha)
        if token is None:
            # Mensagem generica: nao revela se o usuario existe.
            raise HTTPException(status_code=401,
                                detail="Usuario ou senha invalidos.")
        response.set_cookie(auth.COOKIE_SESSAO, token, httponly=True,
                            samesite="lax")
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response) -> dict:
        token = request.cookies.get(auth.COOKIE_SESSAO)
        if token:
            auth.encerrar_sessao(token)
        response.delete_cookie(auth.COOKIE_SESSAO)
        return {"ok": True}

    @app.post("/api/usuarios")
    def criar_usuario(entrada: NovoUsuarioEntrada,
                      usuario: Usuario = Depends(exigir_usuario)) -> dict:
        if not usuario.admin:
            raise HTTPException(status_code=403,
                                detail="Somente administradores criam usuarios.")
        try:
            auth.criar_usuario(entrada.usuario, entrada.nome, entrada.senha,
                               admin=entrada.admin)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True}

    # ------------------------------------------------------------------
    # Sessoes de trabalho + jobs

    @app.post("/api/sessoes")
    def nova_sessao(entrada: SessaoEntrada,
                    usuario: Usuario = Depends(exigir_usuario)) -> dict:
        sessao = criar_sessao(entrada.ferramenta, usuario.usuario)
        return {"sessao_id": sessao.id}

    @app.delete("/api/sessoes/{sessao_id}")
    def remover_sessao(sessao_id: str,
                       usuario: Usuario = Depends(exigir_usuario)) -> dict:
        obter_sessao(sessao_id)
        descartar_sessao(sessao_id)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, usuario: Usuario = Depends(exigir_usuario)) -> dict:
        j = obter_job(job_id)
        return {"status": j.status, "erro": j.erro,
                "resultado": j.resultado, "descricao": j.descricao}

    # ------------------------------------------------------------------
    # Ferramentas + frontend

    app.include_router(rotas_conferencia)
    app.include_router(rotas_comparador)
    app.include_router(rotas_diff)
    app.include_router(rotas_extracao)
    app.include_router(rotas_produtos)

    webui = os.path.join(raiz_projeto(), "webui")
    app.mount("/", StaticFiles(directory=webui, html=True), name="webui")
    return app
