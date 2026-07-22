"""API do Livro de Conferencia Fiscal (paridade com a aba 3 do desktop).

O estado da sessao de trabalho espelha o do widget: notas carregadas,
copias corrigidas (precedencia central de core/correcoes.py) e a fonte da
carga. Conferencias, correcoes e sobrescritas persistem no MESMO
ConferenciaStore do desktop, com o banco no servidor
(dados_web/conferencia.db) e o usuario LOGADO como autor.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.composicao_fiscal import GRUPO_TOTAL, chave_grupo, compor_nota
from ..core.correcoes import (
    CAMPOS_CORRIGIVEIS, TIPO_AUTOMATICA, TIPO_MANUAL, aplicar_correcoes,
    normalizar_valor, validar_correcao,
)
from ..core.filtro_sped import filtrar_entradas
from ..core.modelos import NotaFiscal
from ..core.nfe_xml import associar_xmls, ler_pasta_xml
from ..core.sped_parser import ler_sped
from ..core.utils import formatar_cfop, formatar_moeda, formatar_percentual
from ..ferramentas.conferencia_store import ConferenciaStore
from ..ferramentas.danfe import gerar_danfe_pdf
from ..ferramentas.livro_fiscal import gerar_livro_fiscal
from ..ferramentas.livro_inconsistencias import (
    gerar_livro_inconsistencias, notas_inconsistentes,
)
from ..ferramentas.sped_corrigido import gerar_sped_corrigido
from .auditoria import acesso, detalhar, exigir_aba, exigir_permissao
from .auth import Usuario
from .infra import caminho_db_conferencia, texto_data, texto_moeda
from .sessoes import iniciar_job, obter_sessao, salvar_upload

router = APIRouter(prefix="/api/conferencia", tags=["conferencia"])

_CAMPO_POR_COLUNA = {0: "cfop", 1: "cst_icms", 2: "aliq_icms"}


def _store() -> ConferenciaStore:
    return ConferenciaStore(caminho_db_conferencia())


def _rotulo_nota(chave: str) -> str:
    """Chave de 44 digitos nao cabe no historico; as pontas ja identificam."""
    return f"{chave[:4]}...{chave[-4:]}" if len(chave) > 8 else chave


def _distintos(itens, campo) -> str:
    valores = sorted({str(getattr(i, campo) or "").strip()
                      for i in itens} - {""})
    return ", ".join(valores)


def _aliquotas(itens) -> str:
    valores = sorted({i.aliq_icms for i in itens
                      if i.aliq_icms is not None})
    return ", ".join(formatar_percentual(v) for v in valores)


def _originais(itens) -> dict[str, str]:
    """Valor original por campo corrigido (o PRIMEIRO item vence, como em
    conferencia_widget._preencher_fiscal): a celula da coluna do campo e que
    ganha o destaque, e o tooltip diz de onde o valor veio."""
    originais: dict[str, str] = {}
    for item in itens:
        for campo, original in item.corrigido_de.items():
            originais.setdefault(campo, original)
    return originais


def _valores_distintos(itens) -> dict[str, list[str]]:
    """Valores que REALMENTE existem nos itens, por campo corrigivel.

    Mesma apuracao do combo "Valor original" do DialogoCorrecao do desktop:
    normalizado, sem vazios e na ordem em que aparece nos itens.
    """
    valores: dict[str, list[str]] = {}
    for campo in CAMPOS_CORRIGIVEIS:
        vistos: list[str] = []
        for item in itens:
            v = normalizar_valor(campo, getattr(item, campo))
            if v and v not in vistos:
                vistos.append(v)
        valores[campo] = vistos
    return valores


def _valores_da_nota(nota, campo: str) -> set[str]:
    """REGRA UNICA do alcance do lote: os valores normalizados que a nota (JA
    corrigida) tem no campo.

    A contagem que a confirmacao PROMETE e o ramo de lote de /corrigir que a
    APLICA derivam os dois daqui. Enquanto eram duas copias da mesma regra, a
    primeira mudanca em uma delas faria a tela prometer um numero de notas
    diferente do que a correcao gravaria — num aviso em que o auditor confia.
    """
    return {normalizar_valor(campo, getattr(item, campo))
            for item in nota.itens}


def _tem_valor(nota, campo: str, alvo: str) -> bool:
    return alvo in _valores_da_nota(nota, campo)


def _notas_por_valor(sessao, valores: dict[str, list[str]]) -> dict[str, dict]:
    """Quantas notas carregadas o LOTE alcancaria, por campo e valor.

    Uma passada por campo (nao por valor) para nao pesar em SPED grande.
    """
    corrigidas = sessao.estado.get("corrigidas", {})
    contagem: dict[str, dict] = {}
    for campo, lista in valores.items():
        alvos = set(lista)
        por_valor = dict.fromkeys(lista, 0)
        for nota in corrigidas.values():
            for valor in _valores_da_nota(nota, campo) & alvos:
                por_valor[valor] += 1
        contagem[campo] = por_valor
    return contagem


def _reaplicar(sessao) -> None:
    store = _store()
    try:
        mapa = store.todas_correcoes()
    finally:
        store.fechar()
    corrigidas: dict[str, NotaFiscal] = {}
    for nota in sessao.estado.get("notas", []):
        chave = nota.chave_normalizada
        corrigidas[chave] = aplicar_correcoes(nota, mapa.get(chave, []))
    sessao.estado["corrigidas"] = corrigidas


def _linha_nota(nota: NotaFiscal, corrigida: NotaFiscal, estado) -> dict:
    return {
        "chave": nota.chave_normalizada,
        "conferida": bool(estado and estado.conferida),
        "numero": nota.numero,
        "serie": nota.serie,
        "data": texto_data(nota.dt_emissao),
        "fornecedor": nota.participante.nome if nota.participante else "",
        "cnpj": nota.cnpj_emitente,
        "uf": nota.uf_origem or "",
        "valor_contabil": texto_moeda(corrigida.valor_documento),
        "base_icms": texto_moeda(corrigida.vl_bc_icms),
        "valor_icms": texto_moeda(corrigida.vl_icms),
        "cfop": _distintos(corrigida.itens, "cfop"),
        "cst": _distintos(corrigida.itens, "cst_icms"),
        "aliquota": _aliquotas(corrigida.itens),
        "observacao": estado.observacao if estado else "",
        "data_conferencia": estado.data_conferencia if estado else "",
        "tem_correcao": corrigida.tem_correcao,
        "corrigido_de": _originais(corrigida.itens),
        "tem_xml": bool(nota.xml_path),
    }


def _notas_json(sessao) -> list[dict]:
    store = _store()
    try:
        estados = store.carregar()
    finally:
        store.fechar()
    corrigidas = sessao.estado.get("corrigidas", {})
    linhas = []
    for nota in sessao.estado.get("notas", []):
        chave = nota.chave_normalizada
        linhas.append(_linha_nota(nota, corrigidas.get(chave, nota),
                                  estados.get(chave)))
    return linhas


# ----------------------------------------------------------------------
# Upload + carga


@router.post("/upload")
async def upload(sessao_id: str, arquivo: UploadFile, request: Request,
                 usuario: Usuario = Depends(
                     acesso("conferencia.upload"))) -> dict:
    """Recebe SPED (.txt) na raiz da sessao e XMLs/zips em xml/."""
    sessao = obter_sessao(sessao_id)
    nome = (arquivo.filename or "").lower()
    subpasta = "" if nome.endswith(".txt") else "xml"
    caminho = await salvar_upload(sessao, arquivo, subpasta)
    detalhar(request, f"arquivo: {os.path.basename(caminho)}")
    return {"ok": True, "arquivo": os.path.basename(caminho)}


class CargaEntrada(BaseModel):
    sessao_id: str
    fonte: str                       # "xml" | "sped"
    apenas_entradas: bool = True


@router.post("/carregar")
def carregar(entrada: CargaEntrada, request: Request,
             usuario: Usuario = Depends(
                 acesso("conferencia.carregar"))) -> dict:
    sessao = obter_sessao(entrada.sessao_id)
    pasta_xml = os.path.join(sessao.pasta, "xml")
    escopo = ("somente entradas" if entrada.apenas_entradas
              else "entradas e saidas")
    detalhar(request, f"fonte: {entrada.fonte} ({escopo})")

    def _executar() -> dict:
        if entrada.fonte == "xml":
            if not os.path.isdir(pasta_xml):
                raise ValueError("Envie os XMLs (.xml ou .zip) antes de carregar.")
            notas, vistas = [], set()
            for nota in ler_pasta_xml(pasta_xml):
                chave = nota.chave_normalizada
                if len(chave) == 44:
                    if chave in vistas:
                        continue
                    vistas.add(chave)
                notas.append(nota)
            contexto = f"{len(notas)} XML(s)"
            caminho_fonte = pasta_xml
        else:
            speds = [f for f in os.listdir(sessao.pasta)
                     if f.lower().endswith(".txt")]
            if not speds:
                raise ValueError("Envie o arquivo SPED (.txt) antes de carregar.")
            caminho_fonte = os.path.join(sessao.pasta, sorted(speds)[-1])
            doc = ler_sped(caminho_fonte)
            notas = doc.notas
            if entrada.apenas_entradas:
                notas = filtrar_entradas(notas)
            contexto = doc.empresa.nome or "SPED"
            if os.path.isdir(pasta_xml):
                associar_xmls(notas, pasta_xml)

        notas = [n for n in notas if len(n.chave_normalizada) == 44]
        with sessao.trava:
            sessao.estado.update({
                "notas": notas, "contexto": contexto,
                "fonte": entrada.fonte, "caminho_fonte": caminho_fonte,
                "apenas_entradas": entrada.apenas_entradas,
            })
            _reaplicar(sessao)
        return {"total": len(notas), "contexto": contexto}

    job = iniciar_job(sessao, "Carregando notas", _executar)
    return {"job_id": job.id}


@router.get("/notas")
def notas(sessao_id: str,
          usuario: Usuario = Depends(exigir_aba("conferencia"))) -> dict:
    sessao = obter_sessao(sessao_id)
    # `fonte`/`apenas_entradas` voltam para a tela poder REPETIR a carga com
    # os mesmos parametros ao vincular XMLs novos (DANFE de nota do SPED).
    return {"contexto": sessao.estado.get("contexto", ""),
            "fonte": sessao.estado.get("fonte", ""),
            "apenas_entradas": bool(sessao.estado.get("apenas_entradas")),
            "rotulos_campos": dict(CAMPOS_CORRIGIVEIS),
            "itens": _notas_json(sessao)}


# ----------------------------------------------------------------------
# Conferencia e correcoes


class ConferirEntrada(BaseModel):
    sessao_id: str
    chave: str
    conferida: bool
    observacao: str = ""


@router.post("/conferir")
def conferir(entrada: ConferirEntrada, request: Request,
             usuario: Usuario = Depends(
                 acesso("conferencia.conferir"))) -> dict:
    obter_sessao(entrada.sessao_id)
    store = _store()
    try:
        estado = store.salvar(entrada.chave, entrada.conferida,
                              entrada.observacao)
    finally:
        store.fechar()
    marca = "conferida" if estado.conferida else "conferencia desfeita"
    detalhar(request, f"nota {_rotulo_nota(entrada.chave)}: {marca}")
    return {"conferida": estado.conferida,
            "data_conferencia": estado.data_conferencia}


class CorrecaoEntrada(BaseModel):
    sessao_id: str
    chave: str
    campo: str
    original: str
    novo: str
    motivo: str = ""
    lote: bool = False


@router.post("/corrigir")
def corrigir(entrada: CorrecaoEntrada, request: Request,
             usuario: Usuario = Depends(
                 acesso("conferencia.corrigir"))) -> dict:
    escopo = "em lote" if entrada.lote else "em uma nota"
    # Detalhe da INTENCAO antes da checagem: assim o 403 de lote negado e o
    # 422 de valor invalido dizem no historico o que foi tentado. O detalhe
    # final (com a contagem) sobrescreve este quando a correcao grava.
    detalhar(request,
             f"{CAMPOS_CORRIGIVEIS.get(entrada.campo, entrada.campo)} "
             f"{entrada.original} -> {entrada.novo} {escopo}: tentativa")
    # So o corpo revela que e lote: a dependency cobre uma nota apenas.
    if entrada.lote:
        exigir_permissao(
            usuario, "conferencia.corrigir_lote",
            "Voce nao tem permissao para corrigir em lote. Fale com o "
            "administrador.")
    sessao = obter_sessao(entrada.sessao_id)
    try:
        validar_correcao(entrada.campo, entrada.original, entrada.novo,
                         usuario.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    store = _store()
    aplicadas = 0
    try:
        corrigidas = sessao.estado.get("corrigidas", {})
        if entrada.lote:
            alvo = normalizar_valor(entrada.campo, entrada.original)
            for chave, nota in corrigidas.items():
                if not _tem_valor(nota, entrada.campo, alvo):
                    continue
                tipo = TIPO_MANUAL if chave == entrada.chave else TIPO_AUTOMATICA
                store.registrar_correcao(
                    chave, entrada.campo, entrada.original, entrada.novo,
                    usuario.usuario, tipo=tipo, motivo=entrada.motivo,
                    inconsistencia=store.obter(chave).observacao)
                aplicadas += 1
        else:
            store.registrar_correcao(
                entrada.chave, entrada.campo, entrada.original, entrada.novo,
                usuario.usuario, tipo=TIPO_MANUAL, motivo=entrada.motivo,
                inconsistencia=store.obter(entrada.chave).observacao)
            aplicadas = 1
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        store.fechar()

    with sessao.trava:
        _reaplicar(sessao)
    rotulo = CAMPOS_CORRIGIVEIS[entrada.campo]
    detalhar(request,
             f"{rotulo} {entrada.original} -> {entrada.novo} {escopo}: "
             f"{aplicadas} nota(s)")
    return {"aplicadas": aplicadas,
            "mensagem": (f"Correcao registrada em {aplicadas} nota(s): "
                         f"{rotulo} {entrada.original} -> {entrada.novo} "
                         f"(por {usuario.usuario}).")}


# ----------------------------------------------------------------------
# Composicao fiscal (com sobrescritas)


def _composicao_json(sessao, chave: str) -> dict:
    corrigida = sessao.estado.get("corrigidas", {}).get(chave)
    if corrigida is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada.")
    comp = compor_nota(corrigida)
    store = _store()
    try:
        overrides = store.overrides_da_chave(chave)
    finally:
        store.fechar()

    def _celulas(grupo_ch: str, textos: list, brutos: dict[int, str],
                 corrigido_de: dict[str, str] | None = None) -> list[dict]:
        cels = []
        for coluna, texto in enumerate(textos):
            campo = _CAMPO_POR_COLUNA.get(coluna)
            celula = {"texto": str(texto), "coluna": coluna}
            if grupo_ch != GRUPO_TOTAL and campo:
                original = brutos.get(coluna, "")
                if original:
                    celula["edicao"] = "correcao"
                    celula["campo"] = campo
                    celula["original"] = original
                origem = (corrigido_de or {}).get(campo)
                if origem:
                    celula["corrigido_de"] = origem
            elif not (grupo_ch == GRUPO_TOTAL and coluna == 0):
                celula["edicao"] = "texto"
                ov = overrides.get((grupo_ch, coluna))
                if ov is not None:
                    celula["texto"] = ov.valor
                    celula["override"] = {
                        "calculado": ov.valor_original,
                        "usuario": ov.usuario, "data": ov.data_hora}
            cels.append(celula)
        return cels

    linhas = [{
        "grupo": GRUPO_TOTAL,
        "celulas": _celulas(GRUPO_TOTAL, [
            "TOTAL DA NOTA", "", "", texto_moeda(comp.total_nota), "", "", "",
            f"soma itens: {texto_moeda(comp.soma_valor_contabil)}"], {}),
    }]
    for g in comp.grupos:
        gch = chave_grupo(g)
        st = (texto_moeda(g.vl_icms_st)
              if (g.vl_icms_st or g.vl_bc_icms_st) else "")
        linhas.append({
            "grupo": gch,
            "celulas": _celulas(gch, [
                formatar_cfop(g.cfop) or "--", g.cst or "--",
                formatar_percentual(g.aliquota),
                texto_moeda(g.valor_contabil), texto_moeda(g.vl_bc_icms),
                texto_moeda(g.vl_icms), st, g.qtd_itens or ""],
                {0: str(g.cfop or ""), 1: str(g.cst or ""),
                 2: "" if g.aliquota is None else str(g.aliquota)},
                g.corrigido_de),
        })
    return {"linhas": linhas, "alertas": list(comp.alertas)}


@router.get("/composicao")
def composicao(sessao_id: str, chave: str,
               usuario: Usuario = Depends(exigir_aba("conferencia"))) -> dict:
    return _composicao_json(obter_sessao(sessao_id), chave)


@router.get("/valores-corrigiveis")
def valores_corrigiveis(sessao_id: str, chave: str,
                        usuario: Usuario = Depends(
                            exigir_aba("conferencia"))) -> dict:
    """Alimenta o combo "Valor original" do dialogo de correcao.

    Os valores saem da nota JA corrigida (como no desktop): o proximo passo
    corrige sobre o que esta valendo, nao sobre o que foi importado.
    """
    sessao = obter_sessao(sessao_id)
    corrigida = sessao.estado.get("corrigidas", {}).get(chave)
    if corrigida is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada.")
    valores = _valores_distintos(corrigida.itens)
    return {
        "numero": corrigida.numero,
        "tem_itens": bool(corrigida.itens),
        "valores": valores,
        "notas_por_valor": _notas_por_valor(sessao, valores),
    }


class EdicaoComposicao(BaseModel):
    sessao_id: str
    chave: str
    grupo: str
    coluna: int
    texto: str
    motivo: str = ""


@router.post("/composicao/editar")
def editar_composicao(entrada: EdicaoComposicao, request: Request,
                      usuario: Usuario = Depends(
                          acesso("conferencia.composicao_editar"))) -> dict:
    """Colunas 0-2 dos grupos registram CORRECAO; o resto vira SOBRESCRITA
    de texto persistida (tela + Livro Fiscal), como no desktop."""
    sessao = obter_sessao(entrada.sessao_id)
    campo = _CAMPO_POR_COLUNA.get(entrada.coluna)
    eh_correcao = entrada.grupo != GRUPO_TOTAL and campo is not None
    tipo = "correcao" if eh_correcao else "sobrescrita de texto"
    detalhar(request,
             f"{tipo} no grupo {entrada.grupo}, coluna {entrada.coluna}: "
             f"{entrada.texto}")

    if eh_correcao:
        corrigida = sessao.estado.get("corrigidas", {}).get(entrada.chave)
        if corrigida is None:
            raise HTTPException(status_code=404, detail="Nota nao encontrada.")
        original = ""
        for g in compor_nota(corrigida).grupos:
            if chave_grupo(g) == entrada.grupo:
                original = {0: str(g.cfop or ""), 1: str(g.cst or ""),
                            2: "" if g.aliquota is None else str(g.aliquota)
                            }[entrada.coluna]
                break
        if not original:
            raise HTTPException(
                status_code=422,
                detail="Grupo sem valor original para corrigir.")
        novo = entrada.texto.strip().replace("%", "").strip()
        if normalizar_valor(campo, original) == normalizar_valor(campo, novo):
            # Nada foi gravado: o historico nao pode dizer que corrigiu.
            detalhar(request,
                     f"correcao no grupo {entrada.grupo}, coluna "
                     f"{entrada.coluna}: sem alteracao ({original})")
            return _composicao_json(sessao, entrada.chave)
        try:
            validar_correcao(campo, original, novo, usuario.usuario)
            store = _store()
            try:
                store.registrar_correcao(
                    entrada.chave, campo, original, novo, usuario.usuario,
                    tipo=TIPO_MANUAL,
                    motivo=entrada.motivo or "Edicao direta na composicao fiscal",
                    inconsistencia=store.obter(entrada.chave).observacao)
            finally:
                store.fechar()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        with sessao.trava:
            _reaplicar(sessao)
    else:
        comp_atual = _composicao_json(sessao, entrada.chave)
        calculado = ""
        for linha in comp_atual["linhas"]:
            if linha["grupo"] == entrada.grupo:
                celula = linha["celulas"][entrada.coluna]
                calculado = celula.get("override", {}).get(
                    "calculado", celula["texto"])
                break
        novo_texto = entrada.texto.strip()
        if novo_texto == calculado:
            novo_texto = ""   # voltou ao calculado: remove
        store = _store()
        try:
            store.salvar_override(entrada.chave, entrada.grupo,
                                  entrada.coluna, novo_texto, calculado,
                                  usuario.usuario)
        finally:
            store.fechar()

    return _composicao_json(sessao, entrada.chave)


# ----------------------------------------------------------------------
# DANFE e documentos gerados


def _nota_para_danfe(sessao, chave: str):
    """Nota da sessao com XML vinculado — validacao comum as rotas de DANFE."""
    nota = next((n for n in sessao.estado.get("notas", [])
                 if n.chave_normalizada == chave), None)
    if nota is None:
        raise HTTPException(status_code=404, detail="Nota nao encontrada.")
    if not nota.xml_path or not os.path.isfile(nota.xml_path):
        raise HTTPException(
            status_code=422,
            detail="O XML desta nota nao esta na sessao. Envie os XMLs e "
                   "recarregue para vincular pela chave de acesso.")
    return nota


def _gerar_danfe(nota, destino: str) -> None:
    try:
        gerar_danfe_pdf(nota.xml_path, destino)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail=f"Nao foi possivel gerar o DANFE: {exc}") from exc


@router.get("/danfe")
def danfe(sessao_id: str, chave: str, request: Request,
          usuario: Usuario = Depends(
              acesso("conferencia.danfe"))) -> FileResponse:
    sessao = obter_sessao(sessao_id)
    # Detalhe da INTENCAO antes das checagens (padrao de /corrigir): o 422 de
    # nota sem XML precisa dizer no historico QUAL nota foi tentada.
    detalhar(request, f"nota {_rotulo_nota(chave)}: tentativa")
    nota = _nota_para_danfe(sessao, chave)
    detalhar(request, f"nota {nota.numero or _rotulo_nota(chave)}")
    destino = tempfile.mktemp(prefix=f"danfe_{chave[:8]}_", suffix=".pdf")
    _gerar_danfe(nota, destino)
    return FileResponse(destino, media_type="application/pdf",
                        filename=f"danfe_{nota.numero or chave[:8]}.pdf")


def _estados_e_correcoes():
    store = _store()
    try:
        return store.carregar(), store.todas_correcoes(), store.todas_overrides()
    finally:
        store.fechar()


@router.post("/livro-fiscal")
def livro_fiscal(sessao_id: str, request: Request,
                 usuario: Usuario = Depends(acesso(
                     "conferencia.livro_fiscal"))) -> FileResponse:
    sessao = obter_sessao(sessao_id)
    if not sessao.estado.get("notas"):
        raise HTTPException(status_code=422, detail="Carregue as notas antes.")
    detalhar(request, f"{len(sessao.estado['notas'])} nota(s) no PDF")
    estados, correcoes, overrides = _estados_e_correcoes()
    destino = tempfile.mktemp(prefix="livro_fiscal_", suffix=".pdf")
    filtro = ("Somente documentos de entrada"
              if sessao.estado.get("apenas_entradas") else "")
    gerar_livro_fiscal(sessao.estado["notas"], estados, destino,
                       contexto=sessao.estado.get("contexto", ""),
                       filtro=filtro, correcoes_por_chave=correcoes,
                       overrides_por_chave=overrides)
    return FileResponse(destino, media_type="application/pdf",
                        filename="livro_fiscal.pdf")


@router.post("/inconsistencias")
def inconsistencias(sessao_id: str, request: Request,
                    usuario: Usuario = Depends(acesso(
                        "conferencia.inconsistencias"))) -> FileResponse:
    sessao = obter_sessao(sessao_id)
    if not sessao.estado.get("notas"):
        raise HTTPException(status_code=422, detail="Carregue as notas antes.")
    estados, correcoes, _ = _estados_e_correcoes()
    inconsistentes = notas_inconsistentes(sessao.estado["notas"], estados,
                                          correcoes)
    if not inconsistentes:
        raise HTTPException(
            status_code=422,
            detail="Nenhuma nota carregada tem observacao ou correcao.")
    detalhar(request, f"{len(inconsistentes)} nota(s) inconsistente(s)")
    destino = tempfile.mktemp(prefix="inconsistencias_", suffix=".pdf")
    filtro = ("Somente documentos de entrada"
              if sessao.estado.get("apenas_entradas") else "")
    gerar_livro_inconsistencias(sessao.estado["notas"], estados, destino,
                                contexto=sessao.estado.get("contexto", ""),
                                filtro=filtro, correcoes_por_chave=correcoes)
    return FileResponse(destino, media_type="application/pdf",
                        filename="relatorio_inconsistencias.pdf")


def _exigir_fonte_sped(sessao) -> None:
    if sessao.estado.get("fonte") != "sped":
        raise HTTPException(
            status_code=422,
            detail="O SPED corrigido so vale para cargas de arquivo SPED.")


@router.get("/sped-corrigido/resumo")
def resumo_sped_corrigido(sessao_id: str,
                          usuario: Usuario = Depends(
                              exigir_aba("conferencia"))) -> dict:
    """Pre-checagem do SPED corrigido, consultada ANTES do download.

    O desktop mostra o resumo depois de salvar (QMessageBox); como a rota de
    download devolve o arquivo, o resumo nao cabe no corpo dela e vem aqui.
    A geracao e refeita no download: `gerar_sped_corrigido` so depende do
    arquivo de origem e das correcoes, entao o resumo previsto e o real.
    """
    # Rota de LEITURA (nao audita como download), mas a pre-checagem revela o
    # conteudo do SPED corrigido: exige a MESMA permissao de quem o gera.
    exigir_permissao(
        usuario, "conferencia.sped_corrigido",
        "Voce nao tem permissao para gerar o SPED corrigido. Fale com o "
        "administrador.")
    sessao = obter_sessao(sessao_id)
    _exigir_fonte_sped(sessao)
    _, correcoes, _ = _estados_e_correcoes()
    ativas = [c for lista in correcoes.values() for c in lista if c.ativa]
    if not ativas:
        return {"tem_correcoes": False, "itens_c170_alterados": 0,
                "c190_mesclados": 0, "notas_alteradas": 0,
                "ignoradas": [], "avisos": []}
    destino = tempfile.mktemp(prefix="sped_resumo_", suffix=".txt")
    try:
        resumo = gerar_sped_corrigido(sessao.estado["caminho_fonte"], destino,
                                      correcoes)
    finally:
        # A pre-checagem so quer o resumo; o arquivo sai no download.
        if os.path.isfile(destino):
            os.remove(destino)
    return {
        "tem_correcoes": True,
        "itens_c170_alterados": resumo.itens_c170_alterados,
        "c190_mesclados": resumo.c190_mesclados,
        "notas_alteradas": resumo.notas_alteradas,
        "ignoradas": list(resumo.ignoradas),
        "avisos": list(resumo.avisos),
    }


@router.post("/sped-corrigido")
def sped_corrigido(sessao_id: str, request: Request,
                   usuario: Usuario = Depends(acesso(
                       "conferencia.sped_corrigido"))) -> FileResponse:
    sessao = obter_sessao(sessao_id)
    _exigir_fonte_sped(sessao)
    _, correcoes, _ = _estados_e_correcoes()
    destino = tempfile.mktemp(prefix="sped_corrigido_", suffix=".txt")
    resumo = gerar_sped_corrigido(sessao.estado["caminho_fonte"], destino,
                                  correcoes)
    # O historico conta o que ENTROU no arquivo (notas alteradas), nao todas
    # as correcoes do banco: revertidas e ignoradas nao viram numero fiscal.
    detalhar(request, f"{resumo.notas_alteradas} nota(s) alterada(s), "
                      f"{resumo.itens_c170_alterados} item(ns)")
    return FileResponse(destino, media_type="text/plain",
                        filename="sped_corrigido.txt")
