"""Rotas da Antecipacao e DIFAL do ICMS-BA (spec 027).

Mesma divisao das outras ferramentas: leitura com `exigir_aba` (nao entope o
historico), mutacao e download com `acesso(<slug>)`, que autentica, confere
aba + slug e marca a linha da trilha de uso — inclusive a tentativa negada.

Este modulo e' a UNICA camada que conhece FastAPI nesta feature. A identidade
de quem importa, revisa e aprova vem sempre da sessao, nunca do corpo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..core import antecipacao_ba as ab
from ..core.antecipacao_nfe import MAX_XML_BYTES, NFeInvalida, ler_nfe
from ..core.utils import formatar_moeda
from ..ferramentas.antecipacao_store import (ESTADOS, AntecipacaoStore,
                                             ConcorrenciaError)
from ..ferramentas.relatorio_antecipacao import (AVISO_HOMOLOGACAO,
                                                 AVISO_REDUCAO, gerar_apuracao)
from .auditoria import acesso, detalhar, exigir_aba
from .auth import Usuario
from .infra import caminho_db_antecipacao, pasta_origens_antecipacao

router = APIRouter(prefix="/api/antecipacao", tags=["antecipacao"])

MIME_XLSX = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")
MAX_ARQUIVOS = 200
MAX_LOTE_BYTES = 100 * 1024 * 1024
MAX_CHAVES = 500
MAX_TEXTO_CHAVES = 60_000

# Regra violada por causa do ESTADO do registro e' 409; campo mal preenchido
# e' 422.
_CODIGOS_409 = {"NOTA_APROVADA", "NOTA_EM_REVISAO", "ITENS_SEM_DECISAO",
                "REGIME_NAO_INFORMADO", "ITEM_SEM_CALCULO",
                "VIGENCIA_SOBREPOSTA", "JA_ENCERRADA"}


def _store() -> AntecipacaoStore:
    """Conexao por operacao: SQLite nao atravessa thread com seguranca."""
    return AntecipacaoStore(db_path=caminho_db_antecipacao())


def erro(status: int, detalhe: str, codigo: str = "", **extras) -> HTTPException:
    corpo: dict = {"detail": detalhe}
    if codigo:
        corpo["code"] = codigo
    corpo.update(extras)
    return HTTPException(status_code=status, detail=corpo)


def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, ConcorrenciaError):
        return erro(409,
                    "Esta nota mudou enquanto você revisava. Recarregue e "
                    "confira o estado atual antes de confirmar.",
                    "REVISION_DESATUALIZADA",
                    current_revision=exc.revision_atual)
    if isinstance(exc, ab.ErroAntecipacao):
        return erro(409 if exc.codigo in _CODIGOS_409 else 422,
                    exc.mensagem, exc.codigo)
    if isinstance(exc, LookupError):
        return erro(404, str(exc) or "Registro não encontrado.")
    if isinstance(exc, ValueError):
        return erro(422, str(exc), "FILTRO_INVALIDO")
    raise exc


def _executar(operacao, request: Request | None = None, detalhe: str = ""):
    store = _store()
    try:
        resultado = operacao(store)
    except (ConcorrenciaError, ab.ErroAntecipacao, LookupError,
            ValueError) as exc:
        raise _traduzir(exc) from exc
    finally:
        store.fechar()
    if request is not None and detalhe:
        detalhar(request, detalhe)
    return resultado


def _quem(usuario: Usuario) -> dict:
    return {"usuario_id": usuario.id, "usuario_login": usuario.usuario}


def dinheiro(centavos: int | None) -> dict | None:
    """Centavos -> {centavos, texto}. `None` continua None (sem valor)."""
    if centavos is None:
        return None
    return {"centavos": int(centavos),
            "texto": formatar_moeda(ab.de_centavos(centavos), True)}


def _rotulos(mapa: dict) -> list[dict]:
    return [{"chave": k, "rotulo": v} for k, v in mapa.items()]


def _caminho_xml(sha256: str) -> str:
    return os.path.join(pasta_origens_antecipacao(), f"{sha256}.xml")


# ----------------------------------------------------------------------
# JSON

def _nota_json(linha: dict) -> dict:
    return {
        "id": linha["id"], "chave": linha["chave"],
        "numero": linha["numero"], "serie": linha["serie"],
        "dt_emissao": linha["dt_emissao"], "competencia": linha["competencia"],
        "cnpj_dest": linha["cnpj_dest"], "nome_dest": linha["nome_dest"],
        "cnpj_emit": linha["cnpj_emit"], "nome_emit": linha["nome_emit"],
        "uf_origem": linha["uf_origem"], "metodo": linha["metodo"],
        "metodo_rotulo": ab.METODOS.get(linha["metodo"], linha["metodo"]),
        "presuncao": bool(linha["presuncao"]),
        "estado": linha["estado"],
        "estado_rotulo": ESTADOS.get(linha["estado"], linha["estado"]),
        "regime": linha.get("regime") or "",
        "regime_rotulo": ab.REGIMES.get(linha.get("regime") or "",
                                        "Não informado"),
        "valor_total": dinheiro(linha["valor_total"]),
        "a_recolher": dinheiro(linha["a_recolher"]),
        "itens": linha.get("itens") if isinstance(linha.get("itens"), int) else None,
        "pendentes": linha.get("pendentes", 0),
        "revision": linha["revision"],
        "importada_por": linha["importada_por_login"],
        "importada_em": linha["importada_em"],
        "aprovada_por": linha["aprovada_por_login"],
        "aprovada_em": linha["aprovada_em"],
    }


def _item_json(item: dict) -> dict:
    return {
        "id": item["id"], "num_item": item["num_item"] or str(item["ordem"]),
        "descricao": item["descricao"], "ncm": item["ncm"],
        "cest": item["cest"], "cfop": item["cfop"], "cst": item["cst"],
        "origem_mercadoria": item["origem_mercadoria"],
        "finalidade": item["finalidade"],
        "finalidade_rotulo": ab.FINALIDADES.get(item["finalidade"], "A definir"),
        "decisao": item["decisao"],
        "decisao_rotulo": ab.DECISOES.get(item["decisao"], "Aguardando decisão"),
        "decisao_origem": item["decisao_origem"],
        "decisao_motivo": item["decisao_motivo"],
        "decisao_por": item["decisao_por_login"],
        "pendencias": item["pendencias"], "memoria": item["memoria"],
        "tipo_credito": item["tipo_credito"],
        "tipo_credito_rotulo": ab.TIPOS_CREDITO.get(item["tipo_credito"], ""),
        "aliquota_credito": item["aliquota_credito"],
        "a_recolher": dinheiro(item["a_recolher"]),
    }


def _detalhe_json(dados: dict) -> dict:
    corpo = _nota_json({**dados, "itens": len(dados["itens"])})
    corpo["componentes"] = dados["componentes"]
    corpo["tem_xml"] = bool(dados["sha256"]) and os.path.exists(
        _caminho_xml(dados["sha256"]))
    corpo["lista_itens"] = [_item_json(i) for i in dados["itens"]]
    corpo["grupos"] = [{
        "cfop": g["cfop"], "aliquota": g["aliquota"],
        "tipo_credito": g["tipo_credito"],
        "tipo_credito_rotulo": ab.TIPOS_CREDITO.get(g["tipo_credito"],
                                                    "Sem crédito"),
        "itens": g["itens"], "item_ids": g["item_ids"],
        "pendentes": g["pendentes"], "fora": g["fora"],
        "valor_operacao": dinheiro(g["valor_operacao"]),
        "a_recolher": dinheiro(g["a_recolher"]),
    } for g in dados["grupos"]]
    corpo["eventos"] = dados["eventos"]
    return corpo


def _aliquota_json(linha: dict) -> dict:
    return {
        "id": linha["id"], "tipo": linha["tipo"], "uf": linha["uf"],
        "ncm": linha["ncm"], "percentual": linha["percentual"],
        "vigencia_inicio": linha["vigencia_inicio"],
        "vigencia_fim": linha["vigencia_fim"],
        "base_legal": linha["base_legal"], "origem": linha["origem"],
        "criada_por": linha["criada_por_login"],
        "encerrada_por": linha["encerrada_por_login"],
    }


# ----------------------------------------------------------------------
# Catalogo e leitura

@router.get("/catalogo")
def catalogo(usuario: Usuario = Depends(exigir_aba("antecipacao"))) -> dict:
    config = _executar(lambda s: s.configuracao())
    return {
        "metodos": _rotulos(ab.METODOS),
        "finalidades": _rotulos(ab.FINALIDADES),
        "regimes": _rotulos(ab.REGIMES),
        "decisoes": _rotulos(ab.DECISOES),
        "estados": _rotulos(ESTADOS),
        "componentes": _rotulos(ab.ROTULO_COMPONENTE),
        "ufs_origem": sorted(ab.UFS_7 + ab.UFS_12),
        "configuracao": config,
        "limites": {"arquivos": MAX_ARQUIVOS,
                    "xml_mb": MAX_XML_BYTES // (1024 * 1024),
                    "chaves": MAX_CHAVES},
        "avisos": {"homologacao": AVISO_HOMOLOGACAO, "reducao": AVISO_REDUCAO},
    }


@router.get("/notas")
def listar_notas(cnpj: str = "", competencia: str = "", estado: str = "",
                 texto: str = "", pagina: int = 1, limite: int = 50,
                 usuario: Usuario = Depends(exigir_aba("antecipacao"))) -> dict:
    dados = _executar(lambda s: s.listar_notas(
        pagina=pagina, limite=limite, cnpj=cnpj, competencia=competencia,
        estado=estado, texto=texto))
    return {"itens": [_nota_json(n) for n in dados["itens"]],
            "total": dados["total"], "pagina": dados["pagina"],
            "limite": dados["limite"], "paginas": dados["paginas"]}


@router.get("/notas/{nota_id}")
def detalhar_nota(nota_id: int,
                  usuario: Usuario = Depends(exigir_aba("antecipacao"))) -> dict:
    return _detalhe_json(_executar(lambda s: s.detalhar(nota_id)))


@router.get("/empresas")
def listar_empresas(usuario: Usuario = Depends(
        exigir_aba("antecipacao"))) -> dict:
    empresas = _executar(lambda s: s.empresas())
    return {"itens": [{
        "cnpj": e["cnpj"], "nome": e["nome"], "regime": e["regime"],
        "regime_rotulo": ab.REGIMES.get(e["regime"], "Não informado"),
        "notas": e["notas"]} for e in empresas]}


@router.get("/resumo")
def resumo(cnpj: str = "", competencia: str = "",
           usuario: Usuario = Depends(exigir_aba("antecipacao"))) -> dict:
    linhas = _executar(lambda s: s.resumo(cnpj=cnpj, competencia=competencia))
    return {"itens": [{
        "cnpj": l["cnpj_dest"], "nome": l["nome"], "regime": l["regime"],
        "regime_rotulo": ab.REGIMES.get(l["regime"], "Não informado"),
        "competencia": l["competencia"], "notas": l["notas"],
        "aprovadas": l["aprovadas"],
        "itens_pendentes": l["itens_pendentes"], "itens_fora": l["itens_fora"],
        "aprovado": dinheiro(l["aprovado"]),
        "em_revisao": dinheiro(l["em_revisao"]),
        "reducao_percentual": l["reducao_percentual"],
        "reducao_simulada": dinheiro(l["reducao_simulada"]),
        "aprovado_com_reducao": dinheiro(l["aprovado_com_reducao"]),
        "vencimento_referencia": l["vencimento_referencia"],
    } for l in linhas]}


@router.get("/aliquotas")
def listar_aliquotas(usuario: Usuario = Depends(
        exigir_aba("antecipacao"))) -> dict:
    return {"itens": [_aliquota_json(l)
                      for l in _executar(lambda s: s.aliquotas())]}


@router.get("/eventos")
def eventos_gerais(usuario: Usuario = Depends(
        exigir_aba("antecipacao"))) -> dict:
    """Trilha do que nao pertence a uma nota: tabela, parametros, regime de
    empresa e exclusoes."""
    return {"itens": _executar(lambda s: s.eventos_gerais())}


# ----------------------------------------------------------------------
# Conferencia sem gravar: chaves coladas e lancamento manual

class ChavesEntrada(BaseModel):
    texto: str = ""


@router.post("/chaves/conferir")
def conferir_chaves(entrada: ChavesEntrada,
                    usuario: Usuario = Depends(
                        exigir_aba("antecipacao"))) -> dict:
    """Valida as chaves coladas e diz quais ja foram importadas.

    A chave nao traz os produtos: o que falta precisa do XML. Consultar a
    SEFAZ pela chave exige certificado do destinatario e esta fora desta
    entrega (spec 027)."""
    if len(entrada.texto) > MAX_TEXTO_CHAVES:
        raise erro(422, "Texto grande demais.", "TEXTO_GRANDE")
    brutas = ab.extrair_chaves(entrada.texto)
    if len(brutas) > MAX_CHAVES:
        raise erro(422, f"Cole no máximo {MAX_CHAVES} chaves por vez.",
                   "CHAVES_DEMAIS")
    validas: list[ab.ChaveAcesso] = []
    linhas: list[dict] = []
    vistas: set[str] = set()
    for bruta in brutas:
        try:
            partes = ab.decompor_chave(bruta)
        except ab.ErroAntecipacao as exc:
            linhas.append({"chave": bruta[:60], "situacao": "invalida",
                           "mensagem": exc.mensagem})
            continue
        if partes.chave in vistas:
            linhas.append({"chave": partes.chave, "situacao": "repetida",
                           "mensagem": "Repetida na lista colada."})
            continue
        vistas.add(partes.chave)
        validas.append(partes)
        linhas.append({"chave": partes.chave, "situacao": "", "uf": partes.uf,
                       "ano_mes": partes.ano_mes,
                       "cnpj_emitente": partes.cnpj_emitente,
                       "modelo": partes.modelo, "numero": partes.numero,
                       "serie": partes.serie, "mensagem": ""})
    existentes = _executar(
        lambda s: s.chaves_existentes([p.chave for p in validas]))
    for linha in linhas:
        if linha["situacao"]:
            continue
        achada = existentes.get(linha["chave"])
        if achada:
            linha.update(situacao="importada", nota_id=achada["nota_id"],
                         mensagem="Já importada ("
                                  + ESTADOS.get(achada["estado"], "") + ").")
        elif linha["uf"] == ab.UF_DESTINO:
            linha.update(situacao="fora_do_escopo",
                         mensagem="Emitente da BA: fora do escopo interestadual.")
        elif linha["modelo"] != "55":
            linha.update(situacao="fora_do_escopo",
                         mensagem="Não é NF-e modelo 55.")
        else:
            linha.update(situacao="falta_xml",
                         mensagem="Ainda não importada: envie o XML desta nota.")
    contagem: dict[str, int] = {}
    for linha in linhas:
        contagem[linha["situacao"]] = contagem.get(linha["situacao"], 0) + 1
    return {"itens": linhas, "contagem": contagem}


class SimulacaoEntrada(BaseModel):
    valor_operacao: str
    uf_origem: str
    icms_destacado: str = ""
    origem_mercadoria: str = "0"
    ncm: str = ""
    data: str = ""


@router.post("/simular")
def simular(entrada: SimulacaoEntrada,
            usuario: Usuario = Depends(exigir_aba("antecipacao"))) -> dict:
    """Lancamento manual para conferencia. Nao grava nada."""
    quando = ab.data_iso(entrada.data) if entrada.data.strip() else ""
    if entrada.data.strip() and not quando:
        raise erro(422, "Data inválida (dd/mm/aaaa).", "DATA_INVALIDA")
    dia = date.fromisoformat(quando) if quando else date.today()
    return _executar(lambda s: ab.simular(
        valor_operacao=entrada.valor_operacao, uf_origem=entrada.uf_origem,
        icms_destacado=entrada.icms_destacado,
        origem_mercadoria=entrada.origem_mercadoria, ncm=entrada.ncm,
        quando=dia, tabela=s.tabela()))


# ----------------------------------------------------------------------
# Importacao

def _nome_arquivo(upload: UploadFile) -> str:
    nome = os.path.basename((upload.filename or "arquivo.xml").replace("\\", "/"))
    return nome[:120] or "arquivo.xml"


def _guardar_xml(sha256: str, conteudo: bytes) -> bool:
    """Grava a fonte imutavel. Devolve True se o arquivo foi criado agora."""
    destino = _caminho_xml(sha256)
    if os.path.exists(destino):
        return False
    parcial = f"{destino}.parcial"
    with open(parcial, "wb") as saida:
        saida.write(conteudo)
    os.replace(parcial, destino)
    return True


@router.post("/importar")
async def importar(request: Request, metodo: str = Form(""),
                   finalidade: str = Form(""), presuncao: str = Form(""),
                   arquivos: list[UploadFile] = File(...),
                   usuario: Usuario = Depends(
                       acesso("antecipacao.importar"))) -> dict:
    """Importa um ou varios XML de NF-e. Cada arquivo tem o seu resultado;
    um arquivo ruim nao derruba os outros."""
    if len(arquivos) > MAX_ARQUIVOS:
        raise erro(422, f"Envie no máximo {MAX_ARQUIVOS} arquivos por vez.",
                   "ARQUIVOS_DEMAIS")
    autorizada = presuncao.strip().lower() in ("1", "true", "sim", "on")
    conteudos: list[tuple[str, bytes]] = []
    acumulado = 0
    for upload in arquivos:
        conteudo = await upload.read(MAX_XML_BYTES + 1)
        acumulado += len(conteudo)
        if acumulado > MAX_LOTE_BYTES:
            raise erro(413, "O envio passou de "
                            f"{MAX_LOTE_BYTES // (1024 * 1024)} MB somados. "
                            "Divida em mais de um envio.", "LOTE_GRANDE_DEMAIS")
        conteudos.append((_nome_arquivo(upload), conteudo))

    def _processar(store: AntecipacaoStore) -> list[dict]:
        config = store.configuracao()
        parametros = ab.validar_parametros(metodo.strip(), autorizada,
                                           config["componentes"])
        if finalidade.strip() and finalidade.strip() not in ab.FINALIDADES:
            raise ab.ErroAntecipacao("FINALIDADE_INVALIDA",
                                     "Finalidade desconhecida.")
        resultados = []
        for nome, conteudo in conteudos:
            try:
                nota = ler_nfe(conteudo)
            except NFeInvalida as exc:
                resultados.append({"arquivo": nome, "situacao": "invalido",
                                   "mensagem": str(exc)})
                continue
            sha256 = hashlib.sha256(conteudo).hexdigest()
            criado = _guardar_xml(sha256, conteudo)
            try:
                r = store.importar(nota, sha256=sha256, parametros=parametros,
                                   finalidade=finalidade.strip(),
                                   **_quem(usuario))
            except Exception:
                if criado:
                    os.remove(_caminho_xml(sha256))
                raise
            if r["situacao"] != "importada" and criado:
                os.remove(_caminho_xml(sha256))
            linha = {"arquivo": nome, "situacao": r["situacao"],
                     "chave": r.get("chave", ""),
                     "nota_id": r.get("nota_id"),
                     "mensagem": r.get("mensagem", "")}
            if r["situacao"] == "importada":
                linha.update(itens=r["itens"], pendentes=r["pendentes"],
                             a_recolher=dinheiro(r["a_recolher"]))
            elif r["situacao"] == "duplicada":
                linha["mensagem"] = ("Nota já importada ("
                                     + ESTADOS.get(r["estado"], "")
                                     + "). Nada foi alterado.")
            resultados.append(linha)
        return resultados

    resultados = _executar(_processar)
    contagem: dict[str, int] = {}
    for linha in resultados:
        contagem[linha["situacao"]] = contagem.get(linha["situacao"], 0) + 1
    detalhar(request, f"{len(resultados)} arquivo(s): "
                      + ", ".join(f"{k}={v}" for k, v in sorted(contagem.items())))
    return {"itens": resultados, "contagem": contagem}


# ----------------------------------------------------------------------
# Revisao

class NotaCorpo(BaseModel):
    revision: int
    metodo: str | None = None
    presuncao: bool | None = None
    competencia: str | None = None


class ItensEntrada(BaseModel):
    revision: int
    item_ids: list[int]
    finalidade: str | None = None
    decisao: str | None = None
    motivo: str = ""


class RevisionEntrada(BaseModel):
    revision: int


class MotivoEntrada(BaseModel):
    revision: int
    motivo: str = ""


class RegimeEntrada(BaseModel):
    regime: str


@router.put("/notas/{nota_id}")
def alterar_nota(nota_id: int, entrada: NotaCorpo, request: Request,
                 usuario: Usuario = Depends(
                     acesso("antecipacao.revisar"))) -> dict:
    dados = _executar(
        lambda s: s.alterar_nota(
            nota_id, entrada.model_dump(exclude={"revision"}),
            revision=entrada.revision, **_quem(usuario)),
        request, f"nota {nota_id}: parâmetros")
    return _detalhe_json(dados)


@router.put("/notas/{nota_id}/itens")
def alterar_itens(nota_id: int, entrada: ItensEntrada, request: Request,
                  usuario: Usuario = Depends(
                      acesso("antecipacao.revisar"))) -> dict:
    if len(entrada.item_ids) > 990:
        raise erro(422, "Itens demais.", "ITENS_DEMAIS")
    dados = _executar(
        lambda s: s.alterar_itens(
            nota_id, entrada.item_ids, finalidade=entrada.finalidade,
            decisao=entrada.decisao, motivo=entrada.motivo,
            revision=entrada.revision, **_quem(usuario)),
        request, f"nota {nota_id}: {len(entrada.item_ids)} item(ns)")
    return _detalhe_json(dados)


@router.post("/notas/{nota_id}/aprovar")
def aprovar(nota_id: int, entrada: RevisionEntrada, request: Request,
            usuario: Usuario = Depends(acesso("antecipacao.aprovar"))) -> dict:
    dados = _executar(
        lambda s: s.aprovar(nota_id, revision=entrada.revision,
                            **_quem(usuario)),
        request, f"nota {nota_id}: aprovada")
    return _detalhe_json(dados)


@router.post("/notas/{nota_id}/reabrir")
def reabrir(nota_id: int, entrada: MotivoEntrada, request: Request,
            usuario: Usuario = Depends(acesso("antecipacao.aprovar"))) -> dict:
    dados = _executar(
        lambda s: s.reabrir(nota_id, entrada.motivo,
                            revision=entrada.revision, **_quem(usuario)),
        request, f"nota {nota_id}: reaberta")
    return _detalhe_json(dados)


@router.post("/notas/{nota_id}/excluir")
def excluir(nota_id: int, entrada: MotivoEntrada, request: Request,
            usuario: Usuario = Depends(acesso("antecipacao.revisar"))) -> dict:
    """Descarta uma nota em revisao. O XML guardado sai junto; o evento fica."""
    saida = _executar(
        lambda s: s.excluir_nota(nota_id, entrada.motivo,
                                 revision=entrada.revision, **_quem(usuario)),
        request, f"nota {nota_id}: excluída")
    if saida["sha256"]:
        try:
            os.remove(_caminho_xml(saida["sha256"]))
        except OSError:
            pass
    return {"ok": True, "chave": saida["chave"]}


@router.put("/empresas/{cnpj}")
def definir_regime(cnpj: str, entrada: RegimeEntrada, request: Request,
                   usuario: Usuario = Depends(
                       acesso("antecipacao.revisar"))) -> dict:
    empresa = _executar(
        lambda s: s.definir_regime(cnpj, entrada.regime, **_quem(usuario)),
        request, f"empresa {ab.so_digitos(cnpj)[:14]}: regime")
    return {"cnpj": empresa["cnpj"], "nome": empresa["nome"],
            "regime": empresa["regime"],
            "regime_rotulo": ab.REGIMES.get(empresa["regime"], "Não informado")}


# ----------------------------------------------------------------------
# Tabela e parametros

class AliquotaEntrada(BaseModel):
    tipo: str
    uf: str = ""
    ncm: str = ""
    percentual: str
    vigencia_inicio: str
    vigencia_fim: str = ""
    base_legal: str = ""


class EncerrarEntrada(BaseModel):
    vigencia_fim: str


class ConfiguracaoEntrada(BaseModel):
    metodo_padrao: str | None = None
    componentes: dict[str, bool] | None = None
    reducao_percentual: str | None = None
    dia_vencimento: int | None = None


@router.post("/aliquotas")
def criar_aliquota(entrada: AliquotaEntrada, request: Request,
                   usuario: Usuario = Depends(
                       acesso("antecipacao.configurar"))) -> dict:
    novo_id = _executar(
        lambda s: s.criar_aliquota(entrada.model_dump(), **_quem(usuario)),
        request, f"alíquota {entrada.tipo} {entrada.uf or 'BA'}")
    return {"id": novo_id}


@router.post("/aliquotas/{aliquota_id}/encerrar")
def encerrar_aliquota(aliquota_id: int, entrada: EncerrarEntrada,
                      request: Request,
                      usuario: Usuario = Depends(
                          acesso("antecipacao.configurar"))) -> dict:
    linha = _executar(
        lambda s: s.encerrar_aliquota(aliquota_id, entrada.vigencia_fim,
                                      **_quem(usuario)),
        request, f"alíquota {aliquota_id}: encerrada")
    return _aliquota_json(linha)


@router.put("/configuracao")
def definir_configuracao(entrada: ConfiguracaoEntrada, request: Request,
                         usuario: Usuario = Depends(
                             acesso("antecipacao.configurar"))) -> dict:
    return _executar(
        lambda s: s.definir_configuracao(
            entrada.model_dump(exclude_none=True), **_quem(usuario)),
        request, "parâmetros de cálculo")


# ----------------------------------------------------------------------
# Saidas

def _limpar(pasta: str):
    def _tarefa() -> None:
        shutil.rmtree(pasta, ignore_errors=True)
    return _tarefa


@router.post("/exportar")
def exportar(request: Request, cnpj: str = "", competencia: str = "",
             estado: str = "",
             usuario: Usuario = Depends(
                 acesso("antecipacao.exportar"))) -> FileResponse:
    filtros = {k: v for k, v in (("cnpj", cnpj), ("competencia", competencia),
                                 ("estado", estado)) if v}

    def _consulta(store):
        return (store.itens_para_exportar(cnpj=cnpj, competencia=competencia,
                                          estado=estado),
                store.resumo(cnpj=cnpj, competencia=competencia))

    itens, totais = _executar(_consulta)
    pasta = tempfile.mkdtemp(prefix="antecipacao_saida_")
    nome = f"antecipacao_icms_ba_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    destino = os.path.join(pasta, nome)
    try:
        gerar_apuracao(destino, itens=itens, totais=totais,
                       gerado_por=usuario.usuario, filtros=filtros)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    detalhar(request, f"{len(itens)} item(ns); filtros: {filtros or 'nenhum'}")
    return FileResponse(destino, media_type=MIME_XLSX, filename=nome,
                        background=BackgroundTask(_limpar(pasta)))


@router.get("/notas/{nota_id}/danfe")
def danfe(nota_id: int, request: Request,
          usuario: Usuario = Depends(acesso("antecipacao.danfe"))) -> FileResponse:
    """DANFE gerado do XML guardado na importacao."""
    from ..ferramentas.danfe import gerar_danfe_pdf

    dados = _executar(lambda s: s.detalhar(nota_id))
    origem = _caminho_xml(dados["sha256"]) if dados["sha256"] else ""
    if not origem or not os.path.exists(origem):
        raise erro(404, "O XML desta nota não está guardado.", "SEM_XML")
    pasta = tempfile.mkdtemp(prefix="antecipacao_danfe_")
    nome = f"danfe_{dados['chave']}.pdf"
    destino = os.path.join(pasta, nome)
    try:
        gerar_danfe_pdf(origem, destino)
    except Exception as exc:
        shutil.rmtree(pasta, ignore_errors=True)
        raise erro(422, "Não foi possível gerar o DANFE deste XML.",
                   "DANFE_INDISPONIVEL") from exc
    detalhar(request, f"nota {nota_id}")
    return FileResponse(destino, media_type="application/pdf", filename=nome,
                        background=BackgroundTask(_limpar(pasta)))
