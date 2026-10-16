"""Rotas da Emissao de NFS-e (oitava ferramenta, spec 006, Fase 1).

Mesma divisao das outras ferramentas: leitura com `exigir_aba` (nao entope o
historico), mutacao e download com `acesso(<acao>)`, que autentica, confere
aba + slug e marca a linha da trilha — inclusive quando a tentativa e negada.

A trilha geral recebe so IDs e contagens (`detalhar`). Nomes de alunos e CPFs
de responsaveis ficam no `nfse.db`, nunca no historico de uso.

A Fase 1 gera a DPS e para. A Fase 2 (spec 008) acrescenta a transmissao a
PRODUCAO RESTRITA: o .pfx e a senha chegam no proprio pedido, sao conferidos
antes de qualquer conexao e vivem so na memoria do job. Este modulo e a UNICA
camada que conhece FastAPI nesta feature.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..core import nfse as nf
from ..core import nfse_assinatura as na
from ..core import nfse_certificado as ncert
from ..core import nfse_dps as nd
from ..core import nfse_entrada as ne
from ..ferramentas import nfse_parametros as npar
from ..ferramentas import nfse_sefin as sf
from ..ferramentas import nfse_transmissao as nt
from ..ferramentas import relatorio_nfse as rn
from ..ferramentas.nfse_store import ConcorrenciaError, NfseStore
from ..ferramentas import nfse_store as ns
from .auditoria import acesso, detalhar, exigir_aba, exigir_permissao
from .auth import Usuario
from .infra import caminho_db_nfse, pasta_origens_nfse
from .sessoes import criar_sessao, descartar_sessao, iniciar_job

router = APIRouter(prefix="/api/nfse", tags=["nfse"])

MIME_XLSX = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")
MAX_UPLOAD_BYTES = ne.MAX_PLANILHA_BYTES
AVISOS_NAO_CONFIRMADOS = "AVISOS_NAO_CONFIRMADOS"
LOTE_SEM_DPS = "LOTE_SEM_DPS"
CONFIRMACAO_OBRIGATORIA = "CONFIRMACAO_OBRIGATORIA"
NFSE_NAO_ENCONTRADA = "NFSE_NAO_ENCONTRADA"
DANFSE_NAO_ENCONTRADO = "DANFSE_NAO_ENCONTRADO"
MAX_SENHA_CERTIFICADO = 200
MARCA_RESTRITA = "PRODUCAO-RESTRITA-SEM-VALOR-FISCAL"

_STATUS = {
    ns.PERFIL_NAO_ENCONTRADO: 404, ns.LOTE_NAO_ENCONTRADO: 404,
    ns.LINHA_NAO_ENCONTRADA: 404, ns.DPS_NAO_ENCONTRADA: 404,
    NFSE_NAO_ENCONTRADA: 404, DANFSE_NAO_ENCONTRADO: 404,
    ns.PERFIL_DUPLICADO: 409, ns.ESTADO_INVALIDO: 409, nf.DUPLICATA_APROVADA: 409,
    LOTE_SEM_DPS: 409, ns.LOTE_COM_NFSE: 409,
    ne.TEXTO_GRANDE_DEMAIS: 413, ne.PLANILHA_GRANDE_DEMAIS: 413,
    ncert.CERTIFICADO_GRANDE_DEMAIS: 413,
    # Configuracao do servidor apontando para fora da producao restrita.
    sf.DESTINO_PROIBIDO: 503,
}


def _store() -> NfseStore:
    """Conexao por operacao: SQLite nao atravessa thread com seguranca."""
    return NfseStore(caminho_db_nfse(), pasta_origens_nfse())


def _agora() -> dt.datetime:
    return dt.datetime.now(nd.FUSO_SALVADOR)


def erro(status: int, detalhe: str, codigo: str = "", **extras) -> HTTPException:
    corpo: dict = {"detail": detalhe}
    if codigo:
        corpo["code"] = codigo
    corpo.update(extras)
    return HTTPException(status_code=status, detail=corpo)


def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, ConcorrenciaError):
        return erro(409, "Este lote mudou enquanto você revisava. Recarregue e "
                         "confira antes de confirmar.",
                    "REVISION_DESATUALIZADA", current_revision=exc.revision_atual)
    if isinstance(exc, nf.ErroNfse):
        extras = {"campo": exc.campo} if exc.campo else {}
        return erro(_STATUS.get(exc.codigo, 422), exc.mensagem, exc.codigo, **extras)
    raise exc


def _executar(operacao):
    store = _store()
    try:
        return operacao(store)
    except (ConcorrenciaError, nf.ErroNfse) as exc:
        raise _traduzir(exc) from exc
    finally:
        store.fechar()


def _quem(usuario: Usuario) -> dict:
    """Identidade SEMPRE da sessao; o corpo da requisicao nunca a define."""
    return {"usuario_id": usuario.id, "usuario_login": usuario.usuario}


def _limpar(pasta: str):
    return lambda: shutil.rmtree(pasta, ignore_errors=True)


# ----------------------------------------------------------------------
# Corpos

class PerfilCorpo(BaseModel):
    dados: dict
    motivo: str = ""


class TextoCorpo(BaseModel):
    perfil_id: int
    texto: str


class CorrecaoCorpo(BaseModel):
    campo: str
    valor: str | None = None
    motivo: str = ""
    revision: int


class RevisaoCorpo(BaseModel):
    revision: int


class AprovacaoCorpo(BaseModel):
    revision: int
    confirmar_avisos: bool = False


class DescarteCorpo(BaseModel):
    revision: int
    motivo: str = ""


# ----------------------------------------------------------------------
# Perfis

@router.get("/perfis")
def listar_perfis(usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    return {"itens": _executar(lambda s: s.listar_perfis())}


@router.get("/perfis/{perfil_id}")
def obter_perfil(perfil_id: int, usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    return _executar(lambda s: s.perfil(perfil_id))


@router.get("/catalogo")
def catalogo(usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    """O que a tela de perfil precisa para montar o formulario."""
    return {
        "campos_modelo": list(nf.CAMPOS_MODELO),
        "regimes_especiais": list(nf.REGIMES_ESPECIAIS),
        "serie": {"min": nf.SERIE_MIN, "max": nf.SERIE_MAX},
        "campos_corrigiveis": list(ns.CAMPOS_CORRIGIVEIS),
        "rotulos_modelo": list(ne.ROTULOS_MODELO),
    }


@router.post("/perfis")
def criar_perfil(corpo: PerfilCorpo, request: Request,
                 usuario: Usuario = Depends(acesso("nfse.perfil"))) -> dict:
    r = _executar(lambda s: s.criar_perfil(corpo.dados, motivo=corpo.motivo,
                                           **_quem(usuario)))
    detalhar(request, f"perfil={r['perfil_id']} versao={r['versao']}")
    return r


@router.post("/perfis/{perfil_id}/versoes")
def criar_versao(perfil_id: int, corpo: PerfilCorpo, request: Request,
                 usuario: Usuario = Depends(acesso("nfse.perfil"))) -> dict:
    r = _executar(lambda s: s.criar_versao(perfil_id, corpo.dados,
                                           motivo=corpo.motivo, **_quem(usuario)))
    detalhar(request, f"perfil={perfil_id} versao={r['versao']}")
    return r


@router.post("/perfis/sugestao")
def sugestao_de_perfil(request: Request, certificado: UploadFile = File(...),
                       senha: str = Form(""), municipio_ibge: str = Form(""),
                       c_trib_nac: str = Form(""),
                       usuario: Usuario = Depends(acesso("nfse.perfil_sugestao"))) -> dict:
    """Spec 009: le o certificado e consulta a parametrizacao do ADN para
    PREENCHER o formulario. Nao grava nada; o certificado vive so neste
    pedido, como na transmissao."""
    if len(senha) > MAX_SENHA_CERTIFICADO:
        raise erro(422, "Senha do certificado longa demais.", ncert.CERTIFICADO_ILEGIVEL)
    dados = certificado.file.read(ncert.MAX_PFX_BYTES + 1)
    try:
        cert = ncert.ler_pfx(dados, senha)
    except nf.ErroNfse as exc:
        raise _traduzir(exc) from None
    finally:
        dados = b""
    codigos = [c.strip() for c in (c_trib_nac or "").split(",") if c.strip()]
    competencia = _agora().date().replace(day=1)
    try:
        npar.municipio_valido(municipio_ibge)
        cliente = npar.ClienteParametros.do_ambiente(cert)
        r = npar.sugerir_perfil(cliente, cert, municipio=municipio_ibge,
                                c_trib_nacs=codigos, competencia=competencia)
    except nf.ErroNfse as exc:
        raise _traduzir(exc) from None
    detalhar(request, f"consultas={len(r['consultas'])} campos={len(r['campos'])}")
    return r


@router.post("/planilha-modelo")
def planilha_modelo(request: Request,
                    usuario: Usuario = Depends(acesso("nfse.modelo"))) -> FileResponse:
    pasta = tempfile.mkdtemp(prefix="nfse_modelo_")
    destino = os.path.join(pasta, "planilha-modelo-nfse.xlsx")
    try:
        rn.gerar_planilha_modelo(destino)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    return FileResponse(destino, media_type=MIME_XLSX,
                        filename="planilha-modelo-nfse.xlsx",
                        background=BackgroundTask(_limpar(pasta)))


# ----------------------------------------------------------------------
# Importacao

@router.post("/lotes/planilha")
async def importar_planilha(request: Request, perfil_id: int = Form(...),
                            arquivo: UploadFile = File(...),
                            usuario: Usuario = Depends(acesso("nfse.importar"))) -> dict:
    pasta = tempfile.mkdtemp(prefix="nfse_upload_")
    destino = os.path.join(pasta, "lote.xlsx")
    try:
        tamanho = 0
        with open(destino, "wb") as saida:
            while True:
                pedaco = await arquivo.read(1024 * 1024)
                if not pedaco:
                    break
                tamanho += len(pedaco)
                if tamanho > MAX_UPLOAD_BYTES:
                    raise erro(413, f"Planilha maior que "
                                    f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                               ne.PLANILHA_GRANDE_DEMAIS)
                saida.write(pedaco)
        hoje = _agora().date()
        r = _executar(lambda s: s.importar_planilha(
            perfil_id, destino, arquivo.filename or "planilha.xlsx", hoje=hoje,
            **_quem(usuario)))
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    detalhar(request, f"perfil={perfil_id} lote={r['lote_id']} planilha"
                      f"{' reaproveitada' if r['reaproveitado'] else ''}")
    return r


@router.post("/lotes/texto")
def importar_texto(corpo: TextoCorpo, request: Request,
                   usuario: Usuario = Depends(acesso("nfse.importar"))) -> dict:
    hoje = _agora().date()
    r = _executar(lambda s: s.importar_texto(corpo.perfil_id, corpo.texto, hoje=hoje,
                                             **_quem(usuario)))
    detalhar(request, f"perfil={corpo.perfil_id} lote={r['lote_id']} texto"
                      f"{' reaproveitado' if r['reaproveitado'] else ''}")
    return r


# ----------------------------------------------------------------------
# Lotes

@router.get("/lotes")
def listar_lotes(perfil_id: int | None = None, estado: str | None = None,
                 limite: int = 50, deslocamento: int = 0,
                 usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    return _executar(lambda s: s.listar_lotes(perfil_id=perfil_id, estado=estado,
                                              limite=limite, deslocamento=deslocamento))


@router.get("/lotes/{lote_id}")
def obter_lote(lote_id: int, usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    return _executar(lambda s: s.lote(lote_id))


@router.get("/lotes/{lote_id}/eventos")
def eventos(lote_id: int, usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    return {"itens": _executar(lambda s: (s.estado_do_lote(lote_id),
                                          s.eventos(lote_id))[1])}


@router.get("/lotes/{lote_id}/linhas/{linha_id}/correcoes")
def correcoes(lote_id: int, linha_id: int,
              usuario: Usuario = Depends(exigir_aba("nfse"))) -> dict:
    def _consulta(s):
        if not any(l["id"] == linha_id for l in s.lote(lote_id)["linhas"]):
            raise nf.ErroNfse(ns.LINHA_NAO_ENCONTRADA, "Linha não encontrada no lote.")
        return s.correcoes(linha_id)
    return {"itens": _executar(_consulta)}


@router.post("/lotes/{lote_id}/linhas/{linha_id}/correcoes")
def corrigir(lote_id: int, linha_id: int, corpo: CorrecaoCorpo, request: Request,
             usuario: Usuario = Depends(acesso("nfse.corrigir"))) -> dict:
    hoje = _agora().date()
    r = _executar(lambda s: s.corrigir(lote_id, linha_id, corpo.campo, corpo.valor,
                                       corpo.motivo, revision=corpo.revision,
                                       hoje=hoje, **_quem(usuario)))
    detalhar(request, f"lote={lote_id} linha={linha_id} campo={corpo.campo}")
    return r


@router.post("/lotes/{lote_id}/reconferir")
def reconferir(lote_id: int, corpo: RevisaoCorpo, request: Request,
               usuario: Usuario = Depends(acesso("nfse.reconferir"))) -> dict:
    hoje = _agora().date()
    r = _executar(lambda s: s.reconferir(lote_id, revision=corpo.revision, hoje=hoje,
                                         **_quem(usuario)))
    detalhar(request, f"lote={lote_id}")
    return r


@router.post("/lotes/{lote_id}/aprovar")
def aprovar(lote_id: int, corpo: AprovacaoCorpo, request: Request,
            usuario: Usuario = Depends(acesso("nfse.aprovar"))) -> dict:
    def _aprovar(s: NfseStore):
        totais = s.lote(lote_id)["conferencia"]["totais"]
        if totais["aviso"] and not corpo.confirmar_avisos:
            raise nf.ErroNfse(AVISOS_NAO_CONFIRMADOS,
                              f"{totais['aviso']} linha(s) com aviso. Confira e "
                              "confirme os avisos antes de aprovar.")
        return s.aprovar(lote_id, revision=corpo.revision, agora=_agora(),
                         **_quem(usuario))
    r = _executar(_aprovar)
    detalhar(request, f"lote={lote_id} dps={r['dps']}")
    return r


@router.post("/lotes/{lote_id}/descartar")
def descartar(lote_id: int, corpo: DescarteCorpo, request: Request,
              usuario: Usuario = Depends(acesso("nfse.descartar"))) -> dict:
    """Em revisao: quem importa descarta. Aprovado: so quem aprova."""
    estado = _executar(lambda s: s.estado_do_lote(lote_id))
    slug = "nfse.aprovar_emitir" if estado == ns.APROVADO else "nfse.importar"
    exigir_permissao(usuario, slug, "Voce nao tem permissao para descartar este "
                                    "lote. Fale com o administrador.")
    r = _executar(lambda s: s.descartar(lote_id, revision=corpo.revision,
                                        motivo=corpo.motivo, **_quem(usuario)))
    detalhar(request, f"lote={lote_id} estado_anterior={r['estado_anterior']}")
    return r


# ----------------------------------------------------------------------
# Saidas (marcadas como DPS NAO TRANSMITIDA)

@router.post("/lotes/{lote_id}/resumo")
def resumo(lote_id: int, request: Request,
           usuario: Usuario = Depends(acesso("nfse.exportar"))) -> FileResponse:
    lote, dps = _executar(lambda s: (s.lote(lote_id), s.dps_do_lote(lote_id)))
    pasta = tempfile.mkdtemp(prefix="nfse_resumo_")
    nome = f"resumo-lote{lote_id}-DPS-NAO-TRANSMITIDA.xlsx"
    destino = os.path.join(pasta, nome)
    try:
        rn.gerar_resumo(lote, dps, destino)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    _executar(lambda s: s.registrar_exportacao(lote_id, "resumo", **_quem(usuario)))
    detalhar(request, f"lote={lote_id} resumo")
    return FileResponse(destino, media_type=MIME_XLSX, filename=nome,
                        background=BackgroundTask(_limpar(pasta)))


@router.post("/lotes/{lote_id}/dps-zip")
def dps_zip(lote_id: int, request: Request,
            usuario: Usuario = Depends(acesso("nfse.exportar"))) -> FileResponse:
    def _consulta(s):
        s.estado_do_lote(lote_id)
        dps = s.dps_do_lote(lote_id)
        if not dps:
            raise nf.ErroNfse(LOTE_SEM_DPS, "Este lote ainda não tem DPS gerada.")
        return dps
    dps = _executar(_consulta)
    pasta = tempfile.mkdtemp(prefix="nfse_zip_")
    nome = f"DPS-NAO-TRANSMITIDA_lote{lote_id}.zip"
    destino = os.path.join(pasta, nome)
    try:
        rn.gerar_zip(lote_id, dps, destino)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    _executar(lambda s: s.registrar_exportacao(lote_id, "zip", **_quem(usuario)))
    detalhar(request, f"lote={lote_id} zip dps={len(dps)}")
    return FileResponse(destino, media_type="application/zip", filename=nome,
                        background=BackgroundTask(_limpar(pasta)))


@router.post("/dps/{dps_id}/xml")
def dps_xml(dps_id: int, request: Request,
            usuario: Usuario = Depends(acesso("nfse.exportar"))) -> Response:
    d = _executar(lambda s: s.dps(dps_id))
    _executar(lambda s: s.registrar_exportacao(d["lote_id"], "xml", dps_id=dps_id,
                                               **_quem(usuario)))
    detalhar(request, f"lote={d['lote_id']} dps={dps_id}")
    nome = rn.nome_xml(d["lote_id"], d)
    return Response(content=bytes(d["xml"]), media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# ----------------------------------------------------------------------
# Transmissao a producao restrita (spec 008)

def _algoritmo() -> str:
    """SHA-256 por padrao; AUDITORIA_NFSE_ASSINATURA=sha1 se a Sefin exigir
    (research.md, R-3). Valor fora da lista vira erro na transmissao."""
    return (os.environ.get("AUDITORIA_NFSE_ASSINATURA") or na.ALGORITMO_PADRAO).lower()


@router.post("/lotes/{lote_id}/transmitir")
async def transmitir(lote_id: int, request: Request,
                     certificado: UploadFile = File(...), senha: str = Form(""),
                     confirmar_producao_restrita: bool = Form(False),
                     incluir_rejeitadas: bool = Form(False),
                     usuario: Usuario = Depends(acesso("nfse.transmitir"))) -> dict:
    """Confere tudo o que da para conferir sem rede e abre o job.

    O .pfx e' lido em memoria (nunca vai para disco) e o objeto do
    certificado so existe dentro do job; quando ele termina, sai de escopo."""
    if not confirmar_producao_restrita:
        raise erro(422, "Confirme que a transmissão é para a produção restrita "
                        "(sem valor fiscal).", CONFIRMACAO_OBRIGATORIA)
    if len(senha) > MAX_SENHA_CERTIFICADO:
        raise erro(422, "Senha do certificado longa demais.", ncert.CERTIFICADO_ILEGIVEL)
    dados = await certificado.read(ncert.MAX_PFX_BYTES + 1)
    try:
        cert = ncert.ler_pfx(dados, senha)
    except nf.ErroNfse as exc:
        raise _traduzir(exc) from None
    finally:
        dados = b""
    lote = _executar(lambda s: s.lote_para_transmitir(lote_id))
    try:
        ncert.conferir_para_emissao(cert, lote["cnpj"], dt.datetime.now(dt.timezone.utc))
        cliente = sf.ClienteSefin.do_ambiente(cert)
    except nf.ErroNfse as exc:
        raise _traduzir(exc) from None
    algoritmo = _algoritmo()
    quem = _quem(usuario)
    sessao = criar_sessao("nfse", usuario.usuario)

    def _rodar() -> dict:
        store = _store()
        try:
            return nt.transmitir_lote(store, lote_id, cliente, cert, algoritmo=algoritmo,
                                      incluir_rejeitadas=incluir_rejeitadas, **quem)
        except nf.ErroNfse as exc:
            # So a mensagem de negocio vai para o job: nada de objeto, caminho
            # ou dado do certificado.
            raise RuntimeError(exc.mensagem) from None
        finally:
            store.fechar()
            try:
                descartar_sessao(sessao.id, usuario)
            except HTTPException:
                pass

    job = iniciar_job(sessao, "Transmitindo DPS à produção restrita", _rodar)
    detalhar(request, f"lote={lote_id} transmissao")
    return {"job_id": job.id}


@router.post("/dps/{dps_id}/nfse-xml")
def nfse_xml(dps_id: int, request: Request,
             usuario: Usuario = Depends(acesso("nfse.exportar"))) -> Response:
    def _consulta(s):
        d = s.dps(dps_id)
        n = s.nfse_da_dps(dps_id)
        if n is None:
            raise nf.ErroNfse(NFSE_NAO_ENCONTRADA, "Esta DPS ainda não virou NFS-e.")
        s.registrar_exportacao(d["lote_id"], "nfse_xml", dps_id=dps_id, **_quem(usuario))
        return d, n
    d, n = _executar(_consulta)
    detalhar(request, f"lote={d['lote_id']} dps={dps_id} nfse")
    nome = f"NFSe-{MARCA_RESTRITA}_{n['chave_acesso']}.xml"
    return Response(content=bytes(n["xml"]), media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/dps/{dps_id}/danfse")
def danfse(dps_id: int, request: Request,
           usuario: Usuario = Depends(acesso("nfse.exportar"))) -> Response:
    def _consulta(s):
        d = s.dps(dps_id)
        n = s.nfse_da_dps(dps_id)
        pdf = s.danfse_da_dps(dps_id)
        if n is None or pdf is None:
            raise nf.ErroNfse(DANFSE_NAO_ENCONTRADO,
                              "O DANFSe desta nota não foi recebido da Sefin.")
        s.registrar_exportacao(d["lote_id"], "danfse", dps_id=dps_id, **_quem(usuario))
        return d, n, pdf
    d, n, pdf = _executar(_consulta)
    detalhar(request, f"lote={d['lote_id']} dps={dps_id} danfse")
    nome = f"DANFSe-{MARCA_RESTRITA}_{n['chave_acesso']}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})
