"""API do Comparador SPED x SPED (paridade com a aba 2 do desktop).

Recebe duas versoes de SPED (.txt) na sessao de trabalho (subpastas a/ e b/),
casa as notas pela chave de acesso e compara campo a campo em um job
(ler_sped nos dois arquivos + comparar_speds). O ResultadoDiffSped fica no
estado da sessao — a exportacao do Excel (gerar_relatorio_diff, 4 abas)
reusa esse resultado. A previa de divergencias no JSON e limitada como a
tabela do desktop; o Excel sempre leva tudo.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.filtro_sped import MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS
from ..core.modelos import NotaFiscal
from ..core.sped_parser import ler_sped
from ..ferramentas.comparador_sped_sped import (
    ResultadoDiffSped, comparar_speds,
)
from ..ferramentas.relatorio_diff_excel import gerar_relatorio_diff
from .auth import Usuario, exigir_usuario
from .infra import texto_moeda
from .sessoes import SessaoTrabalho, iniciar_job, obter_sessao, salvar_upload

router = APIRouter(prefix="/api/diff", tags=["diff"])

MEDIA_XLSX = ("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet")

# Rotulos fixos do desktop: aparecem nos cabecalhos e nas abas do Excel.
ROTULO_A = "A (contabilidade)"
ROTULO_B = "B (cliente)"

# Limite da previa de divergencias no JSON (a exportacao inclui tudo).
LIMITE_PREVIA = 5000


def _arquivo_da_subpasta(sessao: SessaoTrabalho, subpasta: str,
                         mensagem: str) -> str:
    """Ultimo arquivo enviado na subpasta da sessao (422 se nao houver)."""
    pasta = os.path.join(sessao.pasta, subpasta)
    arquivos = ([f for f in os.listdir(pasta)
                 if os.path.isfile(os.path.join(pasta, f))]
                if os.path.isdir(pasta) else [])
    if not arquivos:
        raise HTTPException(status_code=422, detail=mensagem)
    return os.path.join(pasta, sorted(arquivos)[-1])


def _hash_arquivo(caminho: str) -> str:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


# ----------------------------------------------------------------------
# Serializacao (NotaFiscal/Decimal nao serializam em JSON direto)


def _nota_json(nota: NotaFiscal) -> dict:
    return {"chave": nota.chave_normalizada, "numero": nota.numero,
            "serie": nota.serie,
            "fornecedor": nota.participante.nome if nota.participante else "",
            "valor": texto_moeda(nota.valor_documento)}


def _divergencias_json(resultado: ResultadoDiffSped) -> list[dict]:
    """Uma linha por DiferencaCampo (flatten), como a tabela do desktop."""
    linhas: list[dict] = []
    for nota in resultado.divergentes:
        for dif in nota.diferencas:
            if len(linhas) >= LIMITE_PREVIA:
                return linhas
            linhas.append({
                "chave": nota.chave, "numero": nota.numero,
                "fornecedor": nota.fornecedor,
                "nivel": "Nota" if dif.nivel == "nota" else "Item",
                "item": dif.num_item, "campo": dif.campo,
                "valor_a": dif.valor_a, "valor_b": dif.valor_b,
            })
    return linhas


def _ordena_numero(nota: NotaFiscal):
    numero = nota.numero or ""
    return (0, int(numero)) if numero.isdigit() else (1, numero)


def _resultado_json(resultado: ResultadoDiffSped) -> dict:
    # Regra de negocio do desktop: filtro de entradas sem nenhum documento.
    sem_entradas = (resultado.apenas_entradas and resultado.total_a == 0
                    and resultado.total_b == 0)
    return {
        "resumo": resultado.resumo(),
        "rotulo_a": resultado.rotulo_a,
        "rotulo_b": resultado.rotulo_b,
        "filtro": ROTULO_FILTRO_ENTRADAS if resultado.apenas_entradas else "",
        "divergencias": _divergencias_json(resultado),
        "apenas_em_a": [_nota_json(n) for n in
                        sorted(resultado.apenas_em_a, key=_ordena_numero)],
        "apenas_em_b": [_nota_json(n) for n in
                        sorted(resultado.apenas_em_b, key=_ordena_numero)],
        "aviso": MSG_SEM_ENTRADAS if sem_entradas else "",
    }


# ----------------------------------------------------------------------
# Endpoints


@router.post("/upload")
async def upload(sessao_id: str, lado: str, arquivo: UploadFile,
                 usuario: Usuario = Depends(exigir_usuario)) -> dict:
    """Recebe os SPEDs: lado 'a' (contabilidade) ou 'b' (cliente)."""
    sessao = obter_sessao(sessao_id)
    if lado not in ("a", "b"):
        raise HTTPException(status_code=422,
                            detail="Lado invalido (use 'a' ou 'b').")
    nome = (arquivo.filename or "").lower()
    if not nome.endswith(".txt"):
        raise HTTPException(status_code=422,
                            detail="O arquivo SPED deve ser um .txt.")
    caminho = await salvar_upload(sessao, arquivo, lado)
    return {"ok": True, "arquivo": os.path.basename(caminho)}


# Modelos Pydantic no nivel do modulo: com `from __future__ import
# annotations`, classes locais nao resolvem e o corpo viraria query param.
class CompararEntrada(BaseModel):
    sessao_id: str
    apenas_entradas: bool = False


@router.post("/comparar")
def comparar_arquivos(entrada: CompararEntrada,
                      usuario: Usuario = Depends(exigir_usuario)) -> dict:
    sessao = obter_sessao(entrada.sessao_id)
    caminho_a = _arquivo_da_subpasta(
        sessao, "a", "Envie o arquivo SPED A (.txt) antes de comparar.")
    caminho_b = _arquivo_da_subpasta(
        sessao, "b", "Envie o arquivo SPED B (.txt) antes de comparar.")
    # No desktop a validacao era por caminho; com uploads, por conteudo.
    if _hash_arquivo(caminho_a) == _hash_arquivo(caminho_b):
        raise HTTPException(status_code=422,
                            detail="Os dois arquivos sao o mesmo.")

    def _executar() -> dict:
        doc_a = ler_sped(caminho_a)
        doc_b = ler_sped(caminho_b)
        resultado = comparar_speds(doc_a, doc_b, ROTULO_A, ROTULO_B,
                                   apenas_entradas=entrada.apenas_entradas)
        with sessao.trava:
            sessao.estado["resultado"] = resultado
        return _resultado_json(resultado)

    job = iniciar_job(sessao, "Comparando os dois SPEDs", _executar)
    return {"job_id": job.id}


@router.post("/exportar")
def exportar(sessao_id: str,
             usuario: Usuario = Depends(exigir_usuario)) -> FileResponse:
    """Excel de 4 abas com TODAS as divergencias (sem o limite da previa)."""
    sessao = obter_sessao(sessao_id)
    with sessao.trava:
        resultado = sessao.estado.get("resultado")
    if resultado is None:
        raise HTTPException(status_code=422,
                            detail="Compare os arquivos antes de exportar.")
    destino = tempfile.mktemp(prefix="comparacao_speds_", suffix=".xlsx")
    gerar_relatorio_diff(resultado, destino)
    return FileResponse(destino, media_type=MEDIA_XLSX,
                        filename="comparacao_speds.xlsx")
