"""Rotas do Patrimonio (setima ferramenta).

Mesma divisao que a conciliacao provou: leitura com `exigir_aba` (nao entope o
historico), mutacao e download com `acesso(<slug>)`, que autentica, confere
aba + slug e marca a linha da trilha — inclusive quando a tentativa e negada.

Este modulo e a UNICA camada que conhece FastAPI nesta feature:
`core/patrimonio.py` e `ferramentas/patrimonio_store.py` continuam puros.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..core import patrimonio as pt
from ..ferramentas.patrimonio_store import ConcorrenciaError, PatrimonioStore
from ..ferramentas.relatorio_patrimonio import gerar_relacao, gerar_termo
from .auditoria import acesso, detalhar, exigir_aba
from .auth import Usuario
from .infra import caminho_db_patrimonio

router = APIRouter(prefix="/api/patrimonio", tags=["patrimonio"])

MIME_XLSX = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")


def _store() -> PatrimonioStore:
    """Conexao por operacao: SQLite nao atravessa thread com seguranca."""
    return PatrimonioStore(db_path=caminho_db_patrimonio())


def erro(status: int, detalhe: str, codigo: str = "", **extras) -> HTTPException:
    corpo: dict = {"detail": detalhe}
    if codigo:
        corpo["code"] = codigo
    corpo.update(extras)
    return HTTPException(status_code=status, detail=corpo)


def _traduzir(exc: Exception) -> HTTPException:
    """Excecoes do dominio -> contrato HTTP, sem vazar detalhe interno."""
    if isinstance(exc, ConcorrenciaError):
        return erro(409,
                    "Este bem mudou enquanto você editava. Recarregue e "
                    "confira o estado atual antes de confirmar.",
                    "REVISION_DESATUALIZADA",
                    current_revision=exc.revision_atual)
    if isinstance(exc, pt.ErroPatrimonio):
        # Regra de negocio violada e' 409 (conflito com o estado), exceto
        # campo mal preenchido, que e' 422 (entrada invalida).
        status = 422 if exc.codigo in (
            pt.CAMPO_OBRIGATORIO, pt.VALOR_INVALIDO, pt.CPF_INVALIDO,
            pt.ETIQUETA_INVALIDA) else 409
        return erro(status, exc.mensagem, exc.codigo)
    if isinstance(exc, LookupError):
        return erro(404, str(exc) or "Registro não encontrado.")
    if isinstance(exc, ValueError):
        return erro(422, str(exc), "FILTRO_INVALIDO")
    raise exc


def _executar(operacao, request: Request | None = None, detalhe: str = ""):
    store = _store()
    try:
        resultado = operacao(store)
    except (ConcorrenciaError, pt.ErroPatrimonio, LookupError,
            ValueError) as exc:
        raise _traduzir(exc) from exc
    finally:
        store.fechar()
    if request is not None and detalhe:
        detalhar(request, detalhe)
    return resultado


def dinheiro(centavos: int | None) -> dict | None:
    """Centavos -> {centavos, texto}. `None` continua None."""
    if centavos is None:
        return None
    from ..core.utils import formatar_moeda
    from decimal import Decimal
    return {"centavos": int(centavos),
            "texto": formatar_moeda(Decimal(centavos) / 100, True)}


def _bem_json(linha: dict, *, completo: bool = False) -> dict:
    corpo = {
        "id": linha["id"], "etiqueta": linha["etiqueta"],
        "tipo": linha["tipo"], "descricao": linha["descricao"],
        "marca": linha["marca"], "modelo": linha["modelo"],
        "numero_serie": linha["numero_serie"] or "",
        "conservacao": linha["conservacao"],
        "conservacao_rotulo": pt.CONSERVACOES.get(linha["conservacao"], ""),
        "situacao": linha["situacao"],
        "situacao_rotulo": pt.SITUACOES.get(linha["situacao"], ""),
        "valor_aquisicao": dinheiro(linha["valor_aquisicao"]),
        "data_aquisicao": linha["data_aquisicao"],
        "local_id": linha["local_id"],
        "local_nome": linha.get("local_nome") or "",
        "pai_id": linha["pai_id"],
        "revision": linha["revision"],
        "responsavel_nome": linha.get("responsavel_nome") or "",
        "responsavel_id": linha.get("responsavel_id"),
    }
    if not completo:
        return corpo
    corpo.update({
        "nota_fiscal": linha["nota_fiscal"], "observacao": linha["observacao"],
        "criado_em": linha["criado_em"], "atualizado_em": linha["atualizado_em"],
    })
    return corpo


# ----------------------------------------------------------------------
# Catalogo e leitura

@router.get("/catalogo")
def catalogo(usuario: Usuario = Depends(exigir_aba("patrimonio"))) -> dict:
    """Tipos, conservacoes, situacoes e movimentos que a tela desenha."""
    return {
        "tipos": list(pt.TIPOS),
        "conservacoes": [{"chave": k, "rotulo": v}
                         for k, v in pt.CONSERVACOES.items()],
        "situacoes": [{"chave": k, "rotulo": v}
                      for k, v in pt.SITUACOES.items()],
        "movimentos": [{"chave": k, "rotulo": v}
                       for k, v in pt.MOVIMENTOS.items()
                       if k != pt.MOV_AQUISICAO],
    }


@router.get("/resumo")
def resumo(texto: str = "", tipo: str = "", situacao: str = "",
           local_id: int = 0, pessoa_id: int = 0,
           incluir_baixados: bool = False,
           usuario: Usuario = Depends(exigir_aba("patrimonio"))) -> dict:
    dados = _executar(lambda store: store.resumo(
        **_filtros(texto, tipo, situacao, local_id, pessoa_id,
                   incluir_baixados)))
    return {**{k: dados[k] for k in ("total", "disponiveis", "em_uso",
                                     "manutencao", "emprestados", "baixados")},
            "valor_total": dinheiro(dados["valor_total"])}


def _filtros(texto: str, tipo: str, situacao: str, local_id: int,
             pessoa_id: int, incluir_baixados: bool) -> dict:
    bruto = {"texto": texto, "tipo": tipo, "situacao": situacao,
             "local_id": local_id or None, "pessoa_id": pessoa_id or None,
             "incluir_baixados": incluir_baixados or None}
    return {k: v for k, v in bruto.items() if v}


@router.get("/bens")
def listar(texto: str = "", tipo: str = "", situacao: str = "",
           local_id: int = 0, pessoa_id: int = 0,
           incluir_baixados: bool = False, pagina: int = 1, limite: int = 50,
           usuario: Usuario = Depends(exigir_aba("patrimonio"))) -> dict:
    dados = _executar(lambda store: store.listar(
        pagina=pagina, limite=limite,
        **_filtros(texto, tipo, situacao, local_id, pessoa_id,
                   incluir_baixados)))
    return {"itens": [_bem_json(i) for i in dados["itens"]],
            "total": dados["total"], "pagina": dados["pagina"],
            "limite": dados["limite"], "paginas": dados["paginas"]}


@router.get("/bens/{bem_id}")
def detalhar_bem(bem_id: int,
                 usuario: Usuario = Depends(exigir_aba("patrimonio"))) -> dict:
    d = _executar(lambda store: store.detalhar(bem_id))
    return {
        **_bem_json(d, completo=True),
        "responsavel": ({"pessoa_id": d["responsavel"]["pessoa_id"],
                         "nome": d["responsavel"]["nome"],
                         "setor": d["responsavel"]["setor"],
                         "desde": d["responsavel"]["iniciada_em"]}
                        if d["responsavel"] else None),
        "responsabilidades": [{
            "id": r["id"], "pessoa_nome": r["pessoa_nome"],
            "iniciada_em": r["iniciada_em"],
            "encerrada_em": r["encerrada_em"] or "",
            "observacao_inicio": r["observacao_inicio"],
            "observacao_fim": r["observacao_fim"],
            "registrada_por": r["registrada_por_login"],
        } for r in d["responsabilidades"]],
        "movimentacoes": [{
            "id": m["id"], "tipo": m["tipo"],
            "tipo_rotulo": pt.MOVIMENTOS.get(m["tipo"], m["tipo"]),
            "situacao_anterior": m["situacao_anterior"],
            "situacao_nova": m["situacao_nova"],
            "pessoa_nome": m["pessoa_nome"] or "",
            "observacao": m["observacao"], "usuario": m["usuario_login"],
            "criada_em": m["criada_em"],
        } for m in d["movimentacoes"]],
        "perifericos": d["perifericos"],
    }


@router.get("/etiqueta/{etiqueta}")
def por_etiqueta(etiqueta: str,
                 usuario: Usuario = Depends(exigir_aba("patrimonio"))) -> dict:
    """Leitura pela etiqueta colada no equipamento (QR/codigo de barras)."""
    bem = _executar(lambda store: store.obter_por_etiqueta(etiqueta))
    return {"id": bem["id"], "etiqueta": bem["etiqueta"]}


@router.get("/pessoas")
def listar_pessoas(apenas_ativas: bool = False,
                   usuario: Usuario = Depends(
                       exigir_aba("patrimonio"))) -> dict:
    pessoas = _executar(
        lambda store: store.listar_pessoas(apenas_ativas=apenas_ativas))
    return {"itens": [{"id": p["id"], "nome": p["nome"],
                       "setor": p["setor"], "email": p["email"],
                       "ativo": bool(p["ativo"]),
                       "bens_ativos": p["bens_ativos"]} for p in pessoas]}


@router.get("/locais")
def listar_locais(usuario: Usuario = Depends(
        exigir_aba("patrimonio"))) -> dict:
    locais = _executar(lambda store: store.listar_locais())
    return {"itens": [{"id": l["id"], "nome": l["nome"],
                       "descricao": l["descricao"], "bens": l["bens"]}
                      for l in locais]}


# ----------------------------------------------------------------------
# Cadastro

class BemEntrada(BaseModel):
    descricao: str
    tipo: str
    conservacao: str = "bom"
    marca: str = ""
    modelo: str = ""
    numero_serie: str = ""
    valor_aquisicao: str = ""
    data_aquisicao: str = ""
    nota_fiscal: str = ""
    observacao: str = ""
    local_id: int | None = None
    pai_id: int | None = None
    revision: int | None = None


class PessoaEntrada(BaseModel):
    nome: str
    cpf: str = ""
    setor: str = ""
    email: str = ""


class LocalEntrada(BaseModel):
    nome: str
    descricao: str = ""


@router.post("/bens")
def criar_bem(entrada: BemEntrada, request: Request,
              usuario: Usuario = Depends(
                  acesso("patrimonio.cadastrar"))) -> dict:
    resultado = _executar(
        lambda store: store.criar_bem(
            entrada.model_dump(exclude={"revision"}),
            usuario_id=usuario.id, usuario_login=usuario.usuario),
        request, f"cadastrou {entrada.tipo}: {entrada.descricao[:60]}")
    return resultado


@router.put("/bens/{bem_id}")
def editar_bem(bem_id: int, entrada: BemEntrada, request: Request,
               usuario: Usuario = Depends(
                   acesso("patrimonio.cadastrar"))) -> dict:
    return _executar(
        lambda store: store.editar_bem(
            bem_id, entrada.model_dump(exclude={"revision", "pai_id"}),
            revision=entrada.revision, usuario_login=usuario.usuario),
        request, f"editou o bem {bem_id}")


@router.post("/pessoas")
def criar_pessoa(entrada: PessoaEntrada, request: Request,
                 usuario: Usuario = Depends(
                     acesso("patrimonio.cadastrar"))) -> dict:
    pessoa_id = _executar(
        lambda store: store.criar_pessoa(
            entrada.nome, cpf=entrada.cpf, setor=entrada.setor,
            email=entrada.email),
        request, f"cadastrou a pessoa {entrada.nome[:60]}")
    return {"id": pessoa_id}


@router.delete("/pessoas/{pessoa_id}")
def desativar_pessoa(pessoa_id: int, request: Request,
                     usuario: Usuario = Depends(
                         acesso("patrimonio.cadastrar"))) -> dict:
    """Desliga o colaborador. NAO encerra responsabilidades.

    Quem esta com um equipamento continua respondendo por ele ate a devolucao
    ser registrada — a resposta devolve a lista do que ficou pendente.
    """
    return _executar(lambda store: store.desativar_pessoa(pessoa_id),
                     request, f"desativou a pessoa {pessoa_id}")


@router.post("/locais")
def criar_local(entrada: LocalEntrada, request: Request,
                usuario: Usuario = Depends(
                    acesso("patrimonio.cadastrar"))) -> dict:
    local_id = _executar(
        lambda store: store.criar_local(entrada.nome, entrada.descricao),
        request, f"cadastrou o local {entrada.nome[:60]}")
    return {"id": local_id}


# ----------------------------------------------------------------------
# Movimentacao

class MovimentoEntrada(BaseModel):
    tipo: str
    pessoa_id: int | None = None
    local_id: int | None = None
    observacao: str = ""
    revision: int | None = None


@router.post("/bens/{bem_id}/movimentar")
def movimentar(bem_id: int, entrada: MovimentoEntrada, request: Request,
               usuario: Usuario = Depends(exigir_aba("patrimonio"))) -> dict:
    """Aplica uma movimentacao.

    A BAIXA exige `patrimonio.baixar`, separado de `patrimonio.movimentar`:
    quem move um equipamento de sala nao deveria, pelo mesmo direito, encerrar
    a vida dele. A checagem acontece aqui porque so o corpo revela o tipo.
    """
    from . import auditoria as trilha
    slug = ("patrimonio.baixar" if entrada.tipo == pt.MOV_BAIXA
            else "patrimonio.movimentar")
    # Marca a acao ANTES de checar, para a tentativa negada tambem ser
    # registrada na trilha.
    request.state.auditoria_acao = (
        "patrimonio.baixar" if entrada.tipo == pt.MOV_BAIXA
        else "patrimonio.movimentar")
    request.state.auditoria_usuario = usuario
    trilha.exigir_permissao(
        usuario, slug,
        "Voce nao tem permissao para esta acao. Fale com o administrador.")

    movimento = _executar(
        lambda store: store.movimentar(
            bem_id, entrada.tipo, pessoa_id=entrada.pessoa_id,
            local_id=entrada.local_id, observacao=entrada.observacao,
            revision=entrada.revision, usuario_id=usuario.id,
            usuario_login=usuario.usuario),
        request,
        f"bem {bem_id}: {pt.MOVIMENTOS.get(entrada.tipo, entrada.tipo)}")
    return {"bem_id": movimento.bem_id, "tipo": movimento.tipo,
            "situacao_anterior": movimento.situacao_anterior,
            "situacao_nova": movimento.situacao_nova,
            "revision": movimento.revision}


# ----------------------------------------------------------------------
# Inventario

class InventarioEntrada(BaseModel):
    observacao: str = ""


class ConferenciaEntrada(BaseModel):
    bem_id: int
    resultado: str
    observacao: str = ""


@router.get("/inventario")
def inventario_atual(usuario: Usuario = Depends(
        exigir_aba("patrimonio"))) -> dict:
    def _consulta(store):
        aberto = store.inventario_aberto()
        if aberto is None:
            return {"aberto": None}
        return {"aberto": store.resumo_inventario(aberto["id"])}
    return _executar(_consulta)


@router.post("/inventario")
def abrir_inventario(entrada: InventarioEntrada, request: Request,
                     usuario: Usuario = Depends(
                         acesso("patrimonio.inventariar"))) -> dict:
    inventario_id = _executar(
        lambda store: store.abrir_inventario(
            usuario_login=usuario.usuario, observacao=entrada.observacao),
        request, "abriu inventario")
    return {"id": inventario_id}


@router.post("/inventario/{inventario_id}/conferir")
def conferir(inventario_id: int, entrada: ConferenciaEntrada, request: Request,
             usuario: Usuario = Depends(
                 acesso("patrimonio.inventariar"))) -> dict:
    return _executar(
        lambda store: store.conferir(
            inventario_id, entrada.bem_id, entrada.resultado,
            observacao=entrada.observacao, usuario_login=usuario.usuario),
        request, f"conferiu o bem {entrada.bem_id}: {entrada.resultado}")


@router.post("/inventario/{inventario_id}/fechar")
def fechar_inventario(inventario_id: int, request: Request,
                      usuario: Usuario = Depends(
                          acesso("patrimonio.inventariar"))) -> dict:
    resumo_final = _executar(
        lambda store: store.fechar_inventario(
            inventario_id, usuario_login=usuario.usuario),
        request, f"fechou o inventario {inventario_id}")
    return {"id": resumo_final["id"], "estado": resumo_final["estado"],
            "total": resumo_final["total"],
            "contagens": resumo_final["contagens"]}


# ----------------------------------------------------------------------
# Saidas

def _limpar(pasta: str):
    def _tarefa() -> None:
        shutil.rmtree(pasta, ignore_errors=True)
    return _tarefa


@router.post("/exportar")
def exportar(texto: str = "", tipo: str = "", situacao: str = "",
             local_id: int = 0, pessoa_id: int = 0,
             incluir_baixados: bool = False, request: Request = None,
             usuario: Usuario = Depends(
                 acesso("patrimonio.exportar"))) -> FileResponse:
    filtros = _filtros(texto, tipo, situacao, local_id, pessoa_id,
                       incluir_baixados)

    def _consulta(store):
        pagina = store.listar(limite=200, pagina=1, **filtros)
        itens = list(pagina["itens"])
        for numero in range(2, pagina["paginas"] + 1):
            itens += store.listar(limite=200, pagina=numero,
                                  **filtros)["itens"]
        return itens

    itens = _executar(_consulta)
    pasta = tempfile.mkdtemp(prefix="patrimonio_saida_")
    nome = f"patrimonio_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    destino = os.path.join(pasta, nome)
    try:
        gerar_relacao(destino, bens=itens, gerado_por=usuario.usuario,
                      filtros=filtros)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    detalhar(request, f"{len(itens)} bem(ns); filtros: {filtros or 'nenhum'}")
    return FileResponse(destino, media_type=MIME_XLSX, filename=nome,
                        background=BackgroundTask(_limpar(pasta)))


@router.post("/bens/{bem_id}/termo")
def termo(bem_id: int, request: Request,
          usuario: Usuario = Depends(
              acesso("patrimonio.termo"))) -> FileResponse:
    """Termo de responsabilidade do bem, para o colaborador assinar."""
    dados = _executar(lambda store: store.detalhar(bem_id))
    if not dados.get("responsavel"):
        raise erro(409,
                   "Este bem não está sob responsabilidade de ninguém. "
                   "Atribua antes de emitir o termo.", "SEM_RESPONSAVEL")

    pasta = tempfile.mkdtemp(prefix="patrimonio_termo_")
    nome = f"termo_{dados['etiqueta']}.pdf"
    destino = os.path.join(pasta, nome)
    try:
        gerar_termo(destino, bem=dados, responsavel=dados["responsavel"],
                    emitido_por=usuario.usuario)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    detalhar(request, f"termo do bem {dados['etiqueta']} para "
                      f"{dados['responsavel']['nome'][:40]}")
    return FileResponse(destino, media_type="application/pdf", filename=nome,
                        background=BackgroundTask(_limpar(pasta)))
