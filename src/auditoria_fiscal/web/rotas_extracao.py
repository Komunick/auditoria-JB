"""API da Extracao de Itens (paridade com a aba 4 do desktop).

O estado da sessao de trabalho espelha o do widget: TODAS as linhas
extraidas ficam em memoria no servidor (a exportacao Excel usa a lista
completa, como o self._linhas do desktop); o navegador recebe apenas uma
previa formatada em pt-BR (max. 2000 linhas), com o mesmo aviso de filtro
de entradas (MSG_SEM_ENTRADAS) da tela original.
"""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.filtro_sped import MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS
from ..core.nfe_xml import ler_pasta_xml
from ..core.sped_parser import ler_sped
from ..ferramentas.extracao_itens import (
    CAMPOS, TITULOS, exportar_itens_excel, extrair_itens, valor_para_texto,
)
from .auditoria import acesso, detalhar
from .auth import Usuario
from .sessoes import iniciar_job, obter_sessao, salvar_upload

router = APIRouter(prefix="/api/extracao", tags=["extracao"])

LIMITE_PREVIA = 2000   # linhas na previa do navegador; a exportacao leva tudo

_MEDIA_XLSX = ("application/vnd.openxmlformats-officedocument."
               "spreadsheetml.sheet")

# Mesmos valores do combo do desktop, com o rotulo que vai ao historico.
_OPERACOES = {"": "todas as operacoes", "0": "apenas entradas",
              "1": "apenas saidas"}


@router.post("/upload")
async def upload(sessao_id: str, arquivo: UploadFile, request: Request,
                 usuario: Usuario = Depends(
                     acesso("extracao.upload"))) -> dict:
    """Recebe SPED (.txt) na raiz da sessao e XMLs/zips em xml/."""
    sessao = obter_sessao(sessao_id)
    nome = (arquivo.filename or "").lower()
    subpasta = "" if nome.endswith(".txt") else "xml"
    caminho = await salvar_upload(sessao, arquivo, subpasta)
    detalhar(request, f"arquivo: {os.path.basename(caminho)}")
    return {"ok": True, "arquivo": os.path.basename(caminho)}


# Modelos no nivel do modulo: com `from __future__ import annotations`,
# classes Pydantic locais nao resolvem e virariam query param.
class ExtracaoEntrada(BaseModel):
    sessao_id: str
    fonte: str                    # "xml" | "sped"
    operacao: str = ""            # "" todas | "0" entradas | "1" saidas


def _linha_previa(linha: dict) -> list[str]:
    """Uma linha da previa: textos ja formatados (data e numeros pt-BR)."""
    return [valor_para_texto(chave, tipo, linha.get(chave))
            for chave, _, tipo in CAMPOS]


@router.post("/extrair")
def extrair(entrada: ExtracaoEntrada, request: Request,
            usuario: Usuario = Depends(acesso("extracao.extrair"))) -> dict:
    if entrada.operacao not in _OPERACOES:
        raise HTTPException(status_code=422,
                            detail="Operacao invalida (use '', '0' ou '1').")
    fonte = "XML" if entrada.fonte == "xml" else "SPED"
    detalhar(request, f"fonte: {fonte}, {_OPERACOES[entrada.operacao]}")
    sessao = obter_sessao(entrada.sessao_id)
    pasta_xml = os.path.join(sessao.pasta, "xml")
    operacao = entrada.operacao or None
    # O aviso/rotulo de filtro so vale para SPED + apenas entradas (desktop).
    filtro_entradas = entrada.fonte == "sped" and entrada.operacao == "0"

    def _executar() -> dict:
        if entrada.fonte == "xml":
            if not os.path.isdir(pasta_xml):
                raise ValueError("Envie os XMLs (.xml ou .zip) antes de extrair.")
            notas, vistas = [], set()
            for nota in ler_pasta_xml(pasta_xml):
                chave = nota.chave_normalizada
                if len(chave) == 44:
                    if chave in vistas:
                        continue
                    vistas.add(chave)
                notas.append(nota)
            contexto = f"{len(notas)} XML(s)"
        else:
            speds = [f for f in os.listdir(sessao.pasta)
                     if f.lower().endswith(".txt")]
            if not speds:
                raise ValueError("Envie o arquivo SPED (.txt) antes de extrair.")
            doc = ler_sped(os.path.join(sessao.pasta, sorted(speds)[-1]))
            notas = doc.notas
            contexto = doc.empresa.nome or "SPED"

        linhas = extrair_itens(notas, somente_operacao=operacao)
        with sessao.trava:
            sessao.estado.update({
                "linhas": linhas, "contexto": contexto,
                "filtro_entradas": filtro_entradas,
            })
        return {
            "total": len(linhas),
            "contexto": contexto,
            "titulos": TITULOS,
            "previa": [_linha_previa(ln) for ln in linhas[:LIMITE_PREVIA]],
            "filtro": ROTULO_FILTRO_ENTRADAS if filtro_entradas else "",
            "aviso": MSG_SEM_ENTRADAS if filtro_entradas and not linhas else "",
        }

    job = iniciar_job(sessao, "Extraindo itens", _executar)
    return {"job_id": job.id}


@router.post("/exportar")
def exportar(sessao_id: str, request: Request,
             usuario: Usuario = Depends(
                 acesso("extracao.exportar"))) -> FileResponse:
    """Excel com TODAS as linhas extraidas (a previa e so da tela)."""
    sessao = obter_sessao(sessao_id)
    linhas = sessao.estado.get("linhas")
    if not linhas:
        raise HTTPException(status_code=422,
                            detail="Extraia os itens antes de exportar.")
    filtro = (ROTULO_FILTRO_ENTRADAS
              if sessao.estado.get("filtro_entradas") else "")
    detalhar(request, f"{len(linhas)} linha(s) exportada(s)")
    destino = tempfile.mktemp(prefix="itens_auditoria_", suffix=".xlsx")
    exportar_itens_excel(linhas, destino, filtro_aplicado=filtro)
    return FileResponse(destino, media_type=_MEDIA_XLSX,
                        filename="itens_auditoria.xlsx")
