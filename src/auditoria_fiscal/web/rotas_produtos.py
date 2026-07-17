"""API da Auditoria de Produtos (paridade com a aba 5 do desktop).

O estado da sessao de trabalho espelha o do widget: BaseProdutos (df bruto,
layout e o CAMINHO do upload original - gerar_nova_base REABRE esse arquivo
do disco), resultados mutados in-place pelas correcoes e alteracoes
acumuladas na sessao. O navegador recebe apenas a previa (max. 5000 linhas)
com o indice ESTAVEL de cada produto (produto.indice). O historico
auditavel vai para dados_web/historico_produtos.csv (nunca o LOCALAPPDATA
do processo). Bases legais: dados_web/dados quando o servidor tiver as
suas, senao a pasta dados/ do repositorio - carregar_base_legal nunca
falha por ausencia (vira aviso).
"""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.base_legal import carregar_base_legal, localizar_pasta_dados
from ..core.cadastro_produtos import gerar_nova_base, ler_base_produtos
from ..ferramentas.auditoria_produtos import (
    ResultadoAuditoria, auditar_produtos, calcular_indicadores,
)
from ..ferramentas.correcao_produtos import (
    aplicar_correcoes, selecionar_alta_confianca,
)
from ..ferramentas.relatorio_produtos import exportar_relatorio_excel
from .auditoria import acesso, detalhar, exigir_aba
from .auth import Usuario
from .infra import caminho_historico_produtos, pasta_dados_web, raiz_projeto
from .sessoes import iniciar_job, obter_sessao, salvar_upload

router = APIRouter(prefix="/api/produtos", tags=["produtos"])

LIMITE_PREVIA = 5000   # linhas na previa; relatorio e nova base levam tudo

_FILTROS = ("todos", "inconsistentes", "alertas", "alta_confianca")

_MEDIA_XLSX = ("application/vnd.openxmlformats-officedocument."
               "spreadsheetml.sheet")
_MEDIA_POR_EXTENSAO = {
    ".xlsx": _MEDIA_XLSX,
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def _pasta_dados_legais() -> str | None:
    """Pasta das bases legais: dados_web/dados > dados/ do repo > desktop."""
    do_servidor = os.path.join(pasta_dados_web(), "dados")
    if os.path.isdir(do_servidor):
        return do_servidor
    do_repo = os.path.join(raiz_projeto(), "dados")
    if os.path.isdir(do_repo):
        return do_repo
    return localizar_pasta_dados()


def _texto_aliquota(aliquota) -> str:
    if aliquota is None:
        return ""
    return str(aliquota).replace(".", ",")


def _texto_correcao(resultado: ResultadoAuditoria) -> str:
    """Texto legivel das correcoes sugeridas (mesma regra do desktop)."""
    partes: list[str] = []
    correcoes = resultado.correcoes
    if "cst" in correcoes:
        atual = resultado.produto.cst or "-"
        partes.append(f"CST {atual} -> {correcoes['cst']}")
    for de, para in resultado.cfop_map.items():
        partes.append(f"CFOP {de} -> {para}")
    if "cest" in correcoes:
        partes.append(f"CEST -> {correcoes['cest']}")
    if "aliquota" in correcoes:
        partes.append(f"Aliquota -> {correcoes['aliquota']}")
    return "; ".join(partes)


def _linha_resultado(resultado: ResultadoAuditoria) -> dict:
    produto = resultado.produto
    return {
        "indice": produto.indice,
        "codigo": produto.codigo,
        "descricao": produto.descricao,
        "ncm": produto.ncm,
        "cest": produto.cest,
        "cfop": ", ".join(produto.cfops),
        "cst": produto.cst,
        "aliquota": _texto_aliquota(produto.aliquota),
        "trib_atual": resultado.tributacao_atual,
        "trib_sugerida": resultado.tributacao_sugerida,
        "confianca": resultado.confianca,
        "situacao": resultado.situacao,
        "inconsistencias": resultado.tipos,
        "correcao": _texto_correcao(resultado),
        "status": resultado.status_correcao,
        "tem_correcao": resultado.tem_correcao,
    }


def _filtrar(resultados: list[ResultadoAuditoria],
             filtro: str) -> list[ResultadoAuditoria]:
    if filtro == "inconsistentes":
        return [r for r in resultados if r.situacao == "INCONSISTENTE"]
    if filtro == "alertas":
        return [r for r in resultados if r.situacao == "ALERTA"]
    if filtro == "alta_confianca":
        return list(selecionar_alta_confianca(resultados))
    return list(resultados)


def _pendentes_alta_confianca(
        resultados: list[ResultadoAuditoria]) -> list[ResultadoAuditoria]:
    """Candidatos de "Corrigir alta confianca" (regra do desktop).

    Serve tanto a previa (que mostra a contagem antes de confirmar) quanto a
    correcao em lote, para o numero prometido ao usuario ser exatamente o que
    a rota vai aplicar.
    """
    return [r for r in selecionar_alta_confianca(resultados)
            if r.status_correcao != "Corrigido"]


def _exigir_auditoria(sessao) -> list[ResultadoAuditoria]:
    resultados = sessao.estado.get("resultados")
    if resultados is None:
        raise HTTPException(status_code=422,
                            detail="Importe e audite o cadastro antes.")
    return resultados


# ----------------------------------------------------------------------
# Bases legais


@router.get("/bases-legais")
def bases_legais(usuario: Usuario = Depends(
        exigir_aba("produtos"))) -> dict:
    """Pasta das bases legais em uso; None quando nenhuma foi encontrada.

    O desktop mostra isso ANTES de auditar, para o usuario saber que sem a
    pasta as validacoes legais ficam limitadas.
    """
    return {"pasta": _pasta_dados_legais()}


# ----------------------------------------------------------------------
# Upload + auditoria


@router.post("/upload")
async def upload(sessao_id: str, arquivo: UploadFile, request: Request,
                 usuario: Usuario = Depends(
                     acesso("produtos.upload"))) -> dict:
    """Recebe a planilha do cadastro e guarda o CAMINHO na sessao.

    gerar_nova_base reabre o arquivo ORIGINAL do disco, entao o upload
    precisa continuar existindo na pasta da sessao ate o fim do trabalho.
    """
    sessao = obter_sessao(sessao_id)
    caminho = await salvar_upload(sessao, arquivo)
    with sessao.trava:
        sessao.estado["caminho_base"] = caminho
    detalhar(request, f"arquivo: {os.path.basename(caminho)}")
    return {"ok": True, "arquivo": os.path.basename(caminho)}


class AuditarEntrada(BaseModel):
    sessao_id: str


@router.post("/auditar")
def auditar(entrada: AuditarEntrada,
            usuario: Usuario = Depends(acesso("produtos.auditar"))) -> dict:
    sessao = obter_sessao(entrada.sessao_id)
    caminho = sessao.estado.get("caminho_base", "")

    def _executar() -> dict:
        if not caminho or not os.path.isfile(caminho):
            raise ValueError("Envie a planilha do cadastro antes de auditar.")
        base = ler_base_produtos(caminho)
        base_legal = carregar_base_legal(_pasta_dados_legais())
        resultados = auditar_produtos(base.produtos, base_legal)
        indicadores = calcular_indicadores(resultados)
        with sessao.trava:
            sessao.estado.update({
                "base": base, "resultados": resultados,
                "indicadores": indicadores, "alteracoes": {},
            })
        return {
            "total": indicadores["total"],
            "indicadores": indicadores,
            "mapa_colunas": base.diagnostico["mapa_colunas"],
            "avisos": list(base.diagnostico["avisos"]) + list(base_legal.avisos),
        }

    job = iniciar_job(sessao, "Importando e auditando produtos", _executar)
    return {"job_id": job.id}


@router.get("/resultados")
def resultados(sessao_id: str, filtro: str = "todos",
               usuario: Usuario = Depends(exigir_aba("produtos"))) -> dict:
    if filtro not in _FILTROS:
        raise HTTPException(
            status_code=422,
            detail=f"Filtro invalido (use: {', '.join(_FILTROS)}).")
    sessao = obter_sessao(sessao_id)
    todos = _exigir_auditoria(sessao)
    filtrados = _filtrar(todos, filtro)
    return {
        "indicadores": sessao.estado.get("indicadores", {}),
        "total_filtrado": len(filtrados),
        "itens": [_linha_resultado(r) for r in filtrados[:LIMITE_PREVIA]],
        "contexto": os.path.basename(sessao.estado.get("caminho_base", "")),
        "alteracoes_acumuladas": len(sessao.estado.get("alteracoes", {})),
        # Apurado sobre TODOS os resultados (nao sobre o filtro nem sobre a
        # previa): o botao "Corrigir alta confianca" tambem ignora os dois.
        "alta_confianca_pendentes": len(_pendentes_alta_confianca(todos)),
    }


# ----------------------------------------------------------------------
# Correcoes


class CorrigirEntrada(BaseModel):
    sessao_id: str
    indices: list[int] | None = None    # produto.indice dos selecionados
    alta_confianca: bool = False        # ou todos os auto-corrigiveis


@router.post("/corrigir")
def corrigir(entrada: CorrigirEntrada, request: Request,
             usuario: Usuario = Depends(acesso("produtos.corrigir"))) -> dict:
    sessao = obter_sessao(entrada.sessao_id)
    todos = _exigir_auditoria(sessao)
    base = sessao.estado.get("base")

    if entrada.alta_confianca:
        selecionados = _pendentes_alta_confianca(todos)
        if not selecionados:
            raise HTTPException(
                status_code=422,
                detail="Nenhuma correcao de alta confianca pendente.")
    else:
        indices = set(entrada.indices or [])
        selecionados = [r for r in todos
                        if r.produto.indice in indices and r.tem_correcao
                        and r.status_correcao != "Corrigido"]
        if not selecionados:
            raise HTTPException(
                status_code=422,
                detail="Selecione produtos com correcao sugerida pendente.")

    with sessao.trava:
        novas = aplicar_correcoes(
            selecionados, base.caminho,
            caminho_historico=caminho_historico_produtos())
        # Mescla nas alteracoes acumuladas da sessao (cfop_map por update,
        # como o _mesclar_alteracoes do desktop).
        alteracoes = sessao.estado.setdefault("alteracoes", {})
        for indice, campos in novas.items():
            atual = alteracoes.setdefault(indice, {})
            for chave, valor in campos.items():
                if chave == "cfop_map" and isinstance(atual.get(chave), dict) \
                        and isinstance(valor, dict):
                    atual[chave].update(valor)
                else:
                    atual[chave] = valor
        indicadores = calcular_indicadores(todos)
        sessao.estado["indicadores"] = indicadores

    modo = ("alta confianca" if entrada.alta_confianca
            else "selecao individual")
    detalhar(request, f"{len(novas)} produto(s) corrigido(s): {modo}")
    return {
        "corrigidos_agora": len(novas),
        "acumuladas": len(alteracoes),
        "indicadores": indicadores,
        "mensagem": (f"{len(novas)} produto(s) corrigido(s) agora; "
                     f"{len(alteracoes)} produto(s) com correcao acumulada "
                     "na sessao (use Gerar nova base para gravar)."),
    }


# ----------------------------------------------------------------------
# Saidas (downloads)


@router.post("/relatorio")
def relatorio(sessao_id: str, request: Request,
              usuario: Usuario = Depends(acesso(
                  "produtos.relatorio"))) -> FileResponse:
    sessao = obter_sessao(sessao_id)
    todos = _exigir_auditoria(sessao)
    base = sessao.estado.get("base")
    detalhar(request, f"{len(todos)} produto(s) no relatorio")
    destino = tempfile.mktemp(prefix="auditoria_produtos_", suffix=".xlsx")
    exportar_relatorio_excel(todos, destino,
                             sessao.estado.get("indicadores"),
                             contexto=base.caminho)
    return FileResponse(destino, media_type=_MEDIA_XLSX,
                        filename="auditoria_produtos.xlsx")


@router.post("/nova-base")
def nova_base(sessao_id: str, request: Request,
              usuario: Usuario = Depends(acesso(
                  "produtos.nova_base"))) -> FileResponse:
    """Nova base corrigida no MESMO formato do arquivo enviado."""
    sessao = obter_sessao(sessao_id)
    _exigir_auditoria(sessao)
    base = sessao.estado.get("base")
    alteracoes = sessao.estado.get("alteracoes") or {}
    if not alteracoes:
        raise HTTPException(
            status_code=422,
            detail="Nenhuma correcao aplicada ainda. Use Corrigir "
                   "selecionados ou Corrigir alta confianca antes de gerar "
                   "a nova base.")
    detalhar(request, f"{len(alteracoes)} produto(s) corrigido(s) na base")
    raiz_nome, ext = os.path.splitext(base.caminho)
    destino = tempfile.mktemp(prefix="nova_base_", suffix=ext or ".csv")
    with sessao.trava:
        gerar_nova_base(base, destino, alteracoes)
    return FileResponse(
        destino,
        media_type=_MEDIA_POR_EXTENSAO.get(ext.lower(),
                                           "application/octet-stream"),
        filename=f"{os.path.basename(raiz_nome)}_corrigida{ext}")
