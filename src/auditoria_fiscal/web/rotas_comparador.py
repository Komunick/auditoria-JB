"""API do Comparador SPED x SEFAZ (paridade com a aba 1 do desktop).

Cruza pela chave de acesso (44 digitos) as notas do SPED Fiscal (.txt) com a
relacao de notas da SEFAZ (planilha). Os uploads ficam na sessao de trabalho
(subpastas sped/ e sefaz/), a comparacao roda como job (ler_sped +
ler_relacao_sefaz + comparar) e o ResultadoComparacao fica no estado da
sessao — a exportacao do Excel (gerar_relatorio, 5 abas) reusa esse
resultado, como o self._resultado do widget desktop.
"""

from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.filtro_sped import MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS
from ..core.modelos import NotaFiscal
from ..core.sefaz_relacao import RegistroSefaz, ler_relacao_sefaz
from ..core.sped_parser import ler_sped
from ..ferramentas.comparador_sped_sefaz import (
    DivergenciaValor, NotaCanceladaEscriturada, ResultadoComparacao, comparar,
)
from ..ferramentas.relatorio_excel import gerar_relatorio
from .auditoria import acesso, detalhar
from .auth import Usuario
from .infra import texto_data, texto_moeda
from .sessoes import SessaoTrabalho, iniciar_job, obter_sessao, salvar_upload

router = APIRouter(prefix="/api/comparador", tags=["comparador"])

MEDIA_XLSX = ("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet")

# Extensoes aceitas para a relacao da SEFAZ (mesmo filtro do desktop).
_EXT_SEFAZ = (".xlsx", ".xlsm", ".xls", ".csv", ".txt")


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


# ----------------------------------------------------------------------
# Serializacao (Decimal/date nao serializam em JSON; RegistroSefaz tem
# properties que dataclasses.asdict nao inclui — tudo manual)


def _faltante_json(reg: RegistroSefaz) -> dict:
    return {
        "chave": reg.chave_normalizada,
        "numero": reg.numero,
        "serie": reg.serie,
        "cnpj_emitente": reg.cnpj_emitente_da_chave,
        "emitente": reg.emitente_nome,
        "data": texto_data(reg.dt_emissao),
        "valor": texto_moeda(reg.valor),
        "situacao": reg.situacao or "Autorizada",
    }


def _cancelada_json(nc: NotaCanceladaEscriturada) -> dict:
    return {"chave": nc.chave, "numero": nc.numero, "emitente": nc.emitente,
            "situacao_sefaz": nc.situacao_sefaz}


def _divergencia_json(dv: DivergenciaValor) -> dict:
    return {"chave": dv.chave, "numero": dv.numero, "emitente": dv.emitente,
            "valor_sefaz": texto_moeda(dv.valor_sefaz),
            "valor_sped": texto_moeda(dv.valor_sped),
            "diferenca": texto_moeda(dv.diferenca)}


def _nota_sped_json(nota: NotaFiscal) -> dict:
    return {"chave": nota.chave_normalizada, "numero": nota.numero,
            "serie": nota.serie,
            "fornecedor": nota.participante.nome if nota.participante else "",
            "data": texto_data(nota.dt_emissao),
            "valor": texto_moeda(nota.valor_documento)}


def _resultado_json(resultado: ResultadoComparacao, empresa: str,
                    diagnostico: dict) -> dict:
    # Regra de negocio do desktop: filtro de entradas sem nenhum documento.
    sem_entradas = resultado.apenas_entradas and resultado.total_sped == 0
    return {
        "resumo": resultado.resumo(),
        "empresa": empresa,
        "filtro": ROTULO_FILTRO_ENTRADAS if resultado.apenas_entradas else "",
        "faltantes": [_faltante_json(r) for r in resultado.faltantes_no_sped],
        "canceladas": [_cancelada_json(c)
                       for c in resultado.canceladas_escrituradas],
        "divergencias": [_divergencia_json(d)
                         for d in resultado.divergencias_valor],
        "apenas_no_sped": [_nota_sped_json(n)
                           for n in resultado.apenas_no_sped],
        "diagnostico": {
            "mapa_colunas": diagnostico.get("mapa_colunas", {}),
            "registros_validos": diagnostico.get("registros_validos", 0),
        },
        "aviso": MSG_SEM_ENTRADAS if sem_entradas else "",
    }


# ----------------------------------------------------------------------
# Endpoints


@router.post("/upload")
async def upload(sessao_id: str, tipo: str, arquivo: UploadFile,
                 request: Request,
                 usuario: Usuario = Depends(
                     acesso("comparador.upload"))) -> dict:
    """Recebe o SPED (.txt) em sped/ e a relacao da SEFAZ em sefaz/.

    A extensao e preservada: a leitura da SEFAZ decide o parser (xlsx/csv)
    pelo final do caminho.
    """
    sessao = obter_sessao(sessao_id)
    nome = (arquivo.filename or "").lower()
    if tipo == "sped":
        if not nome.endswith(".txt"):
            raise HTTPException(status_code=422,
                                detail="O arquivo SPED deve ser um .txt.")
    elif tipo == "sefaz":
        if not nome.endswith(_EXT_SEFAZ):
            raise HTTPException(
                status_code=422,
                detail="A relacao da SEFAZ deve ser uma planilha "
                       "(.xlsx, .xlsm, .xls, .csv ou .txt).")
    else:
        raise HTTPException(status_code=422,
                            detail="Tipo de upload invalido (sped ou sefaz).")
    caminho = await salvar_upload(sessao, arquivo, tipo)
    detalhar(request, f"{tipo}: {os.path.basename(caminho)}")
    return {"ok": True, "arquivo": os.path.basename(caminho)}


# Modelos Pydantic no nivel do modulo: com `from __future__ import
# annotations`, classes locais nao resolvem e o corpo viraria query param.
class CompararEntrada(BaseModel):
    sessao_id: str
    apenas_entradas: bool = True


@router.post("/comparar")
def comparar_arquivos(entrada: CompararEntrada, request: Request,
                      usuario: Usuario = Depends(
                          acesso("comparador.comparar"))) -> dict:
    sessao = obter_sessao(entrada.sessao_id)
    caminho_sped = _arquivo_da_subpasta(
        sessao, "sped", "Envie o arquivo SPED (.txt) antes de comparar.")
    caminho_sefaz = _arquivo_da_subpasta(
        sessao, "sefaz", "Envie a relacao da SEFAZ antes de comparar.")

    def _executar() -> dict:
        doc = ler_sped(caminho_sped)
        registros, diagnostico = ler_relacao_sefaz(caminho_sefaz)
        resultado = comparar(doc, registros,
                             apenas_entradas=entrada.apenas_entradas)
        empresa = doc.empresa.nome or ""
        with sessao.trava:
            sessao.estado.update({"resultado": resultado, "empresa": empresa})
        return _resultado_json(resultado, empresa, diagnostico)

    detalhar(request, "somente documentos de entrada"
             if entrada.apenas_entradas else "todos os documentos")
    job = iniciar_job(sessao, "Comparando SPED x SEFAZ", _executar)
    return {"job_id": job.id}


@router.post("/exportar")
def exportar(sessao_id: str, request: Request,
             usuario: Usuario = Depends(
                 acesso("comparador.exportar"))) -> FileResponse:
    """Excel de 5 abas gerado do resultado guardado na sessao."""
    sessao = obter_sessao(sessao_id)
    with sessao.trava:
        resultado = sessao.estado.get("resultado")
        empresa = sessao.estado.get("empresa", "")
    if resultado is None:
        raise HTTPException(status_code=422,
                            detail="Compare os arquivos antes de exportar.")
    if empresa:
        detalhar(request, f"empresa: {empresa}")
    destino = tempfile.mktemp(prefix="conferencia_sped_sefaz_",
                              suffix=".xlsx")
    gerar_relatorio(resultado, destino, nome_empresa=empresa)
    return FileResponse(destino, media_type=MEDIA_XLSX,
                        filename="conferencia_sped_sefaz.xlsx")
