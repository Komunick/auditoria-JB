"""API de administracao: usuarios, permissoes e historico de acessos.

Tela pedida pelo dono (2026-07-17) para substituir a criacao de usuarios "na
mao" que o README-servidor descrevia como evolucao futura. Quem alcanca estas
rotas e quem tem `admin.usuarios` (gestao) ou `admin.historico` (trilha) —
na pratica os administradores, que tem o catalogo inteiro.

Toda rota daqui e auditada como qualquer outra: mexer em permissao de alguem
e, ele proprio, um evento do historico.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import auditoria, permissoes
from .auditoria import acesso
from .auth import Usuario
from . import auth

router = APIRouter(prefix="/api/admin", tags=["admin"])


class NovoUsuario(BaseModel):
    usuario: str
    nome: str = ""
    senha: str
    admin: bool = False
    permissoes: list[str] = []


class EdicaoUsuario(BaseModel):
    nome: str = ""
    admin: bool = False
    ativo: bool = True


class EdicaoPermissoes(BaseModel):
    permissoes: list[str] = []


class NovaSenha(BaseModel):
    senha: str


def _usuario_json(linha: dict) -> dict:
    return {**linha,
            "permissoes": permissoes.permissoes_do_usuario(
                linha["id"], linha["admin"]),
            "resumo": auditoria.resumo_por_usuario(linha["usuario"])}


def _obter(usuario_id: int) -> dict:
    alvo = auth.obter_usuario(usuario_id)
    if alvo is None:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    return alvo


# ----------------------------------------------------------------------
# Usuarios e permissoes


@router.get("/usuarios")
def listar(request: Request,
           usuario: Usuario = Depends(acesso("admin.usuarios_listados"))) -> dict:
    """Lista os usuarios com as permissoes e o catalogo que a tela desenha."""
    return {"catalogo": permissoes.catalogo_json(),
            "padrao_novo": list(permissoes.PADRAO_NOVO_USUARIO),
            "usuarios": [_usuario_json(u) for u in auth.listar_usuarios()]}


@router.post("/usuarios")
def criar(entrada: NovoUsuario, request: Request,
          usuario: Usuario = Depends(acesso("admin.usuario_criado"))) -> dict:
    try:
        pedidas = permissoes.validar(entrada.permissoes)
        novo_id = auth.criar_usuario(entrada.usuario, entrada.nome,
                                     entrada.senha, admin=entrada.admin)
        if not entrada.admin:
            permissoes.definir(novo_id, pedidas, por=usuario.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    auditoria.detalhar(request, (
        f"criou {entrada.usuario.strip().lower()}"
        f"{' (administrador)' if entrada.admin else ''}; permissoes: "
        f"{', '.join(pedidas) if pedidas and not entrada.admin else 'todas'}"))
    return _usuario_json(_obter(novo_id))


@router.put("/usuarios/{usuario_id}")
def editar(usuario_id: int, entrada: EdicaoUsuario, request: Request,
           usuario: Usuario = Depends(acesso("admin.usuario_editado"))) -> dict:
    alvo = _obter(usuario_id)
    # Ninguem tira o proprio acesso de administrador: alem de trancar a si
    # mesmo para fora (a chamada seguinte de permissoes ja viria 403), some
    # com a unica pessoa que poderia se reverter. Peca a outro administrador.
    if usuario_id == usuario.id and (not entrada.admin or not entrada.ativo):
        raise HTTPException(
            status_code=422,
            detail="Voce nao pode remover o proprio acesso de administrador. "
                   "Peca a outro administrador para fazer essa alteracao.")
    try:
        atualizado = auth.atualizar_usuario(usuario_id, entrada.nome,
                                            entrada.admin, entrada.ativo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    mudancas = []
    if alvo["nome"] != atualizado["nome"]:
        mudancas.append(f"nome: {alvo['nome']} -> {atualizado['nome']}")
    if alvo["admin"] != atualizado["admin"]:
        mudancas.append(
            "promovido a administrador" if atualizado["admin"]
            else "deixou de ser administrador")
    if alvo["ativo"] != atualizado["ativo"]:
        mudancas.append("reativado" if atualizado["ativo"] else "desativado")
    auditoria.detalhar(request, f"{alvo['usuario']}: "
                                f"{'; '.join(mudancas) or 'sem mudancas'}")
    return _usuario_json(atualizado)


@router.put("/usuarios/{usuario_id}/permissoes")
def definir_permissoes(usuario_id: int, entrada: EdicaoPermissoes,
                       request: Request,
                       usuario: Usuario = Depends(
                           acesso("admin.permissoes"))) -> dict:
    alvo = _obter(usuario_id)
    # Nomeia o alvo antes de qualquer recusa: uma tentativa negada tambem
    # precisa dizer sobre QUEM era, senao o historico fica cego.
    auditoria.detalhar(request, f"{alvo['usuario']}: tentativa")
    if alvo["admin"]:
        raise HTTPException(
            status_code=422,
            detail="Administrador tem todas as permissoes. Remova o perfil de "
                   "administrador antes de recortar o acesso.")
    antes = set(permissoes.permissoes_do_usuario(usuario_id, False))
    try:
        agora = permissoes.definir(usuario_id, entrada.permissoes,
                                   por=usuario.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    concedidas = sorted(set(agora) - antes)
    retiradas = sorted(antes - set(agora))
    partes = []
    if concedidas:
        partes.append(f"concedeu: {', '.join(concedidas)}")
    if retiradas:
        partes.append(f"retirou: {', '.join(retiradas)}")
    auditoria.detalhar(request, f"{alvo['usuario']}: "
                                f"{'; '.join(partes) or 'sem mudancas'}")
    return _usuario_json(_obter(usuario_id))


@router.put("/usuarios/{usuario_id}/senha")
def trocar_senha(usuario_id: int, entrada: NovaSenha, request: Request,
                 usuario: Usuario = Depends(acesso("admin.senha"))) -> dict:
    alvo = _obter(usuario_id)
    try:
        auth.trocar_senha(usuario_id, entrada.senha)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    auditoria.detalhar(
        request, f"trocou a senha de {alvo['usuario']} (sessoes encerradas)")
    return {"ok": True}


# ----------------------------------------------------------------------
# Historico


@router.get("/historico")
def historico(request: Request, usuario_filtro: str = "", categoria: str = "",
              acao: str = "", de: str = "", ate: str = "", texto: str = "",
              limite: int = 200, pagina: int = 1,
              usuario: Usuario = Depends(acesso("admin.historico"))) -> dict:
    resultado = auditoria.consultar(
        usuario=usuario_filtro, categoria=categoria, acao=acao, de=de, ate=ate,
        texto=texto, limite=limite, pagina=pagina)
    return {
        **resultado,
        "categorias": [{"valor": v, "rotulo": r}
                       for v, r in auditoria.ROTULO_CATEGORIA.items()],
        "acoes": [{"valor": a.slug, "rotulo": a.descricao}
                  for a in auditoria.ACOES.values()],
        "usuarios": auditoria.usuarios_no_historico(),
    }


@router.get("/historico/exportar")
def exportar_historico(
        request: Request, usuario_filtro: str = "", categoria: str = "",
        acao: str = "", de: str = "", ate: str = "", texto: str = "",
        usuario: Usuario = Depends(
            acesso("admin.historico_exportado"))) -> StreamingResponse:
    """CSV do historico filtrado (separador ';', utf-8-sig — abre no Excel).

    Percorre TODAS as paginas do filtro: o CSV que o dono leva para uma
    conversa ou para o Fisco nao pode cortar em 1000 linhas em silencio."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Data e hora", "Usuario", "Nome", "Categoria",
                       "Acao", "O que fez", "Detalhe", "Resultado", "IP"])
    total = 0
    pagina = 1
    while True:
        bloco = auditoria.consultar(
            usuario=usuario_filtro, categoria=categoria, acao=acao, de=de,
            ate=ate, texto=texto, limite=1000, pagina=pagina)
        for item in bloco["itens"]:
            escritor.writerow([
                item["data_hora"], item["usuario"], item["nome"],
                item["categoria_rotulo"], item["acao"], item["descricao"],
                item["detalhe"], item["resultado"], item["ip"]])
        total += len(bloco["itens"])
        if total >= bloco["total"] or not bloco["itens"]:
            break
        pagina += 1
    auditoria.detalhar(request, f"{total} linha(s)")
    conteudo = io.BytesIO(saida.getvalue().encode("utf-8-sig"))
    return StreamingResponse(
        conteudo, media_type="text/csv",
        headers={"content-disposition":
                 'attachment; filename="historico_acessos.csv"'})
