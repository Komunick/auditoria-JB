"""Rotas da Conciliacao Fiscal (sexta ferramenta).

Portao de acesso da aba e contratos de erro comuns. Importacao, consulta,
revisao, conflitos e exportacoes entram nas fases seguintes; o resumo ja
responde com a forma final do contrato, zerado, para a aba existir de ponta a
ponta antes de haver qualquer dado.

Autorizacao: toda rota exige CUMULATIVAMENTE `aba.conciliacao` e o slug da
acao. As rotas de LEITURA usam `exigir_aba` (nao entopem o historico); as de
processamento, mutacao e download usam `acesso(<slug>)`, que autentica,
confere as duas permissoes e marca a linha do historico — inclusive quando a
tentativa e negada.

Este modulo e a UNICA camada que conhece FastAPI nesta feature: parser
(`core/conciliacao_sefaz.py`), persistencia
(`ferramentas/conciliacao_store.py`) e exportadores
(`ferramentas/relatorio_conciliacao.py`) permanecem puros e testaveis sem
servidor (constituicao, principio II).
"""

from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import threading
from datetime import datetime
from decimal import Decimal

from fastapi import (APIRouter, Depends, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..core.conciliacao_sefaz import (VERSAO_PARSER, ErroConciliacao,
                                      validar_pacote_xlsx)
from ..core.utils import formatar_moeda
from ..ferramentas.conciliacao_store import (ConciliacaoStore,
                                             ConcorrenciaError,
                                             TransicaoInvalida)
from ..ferramentas.relatorio_conciliacao import (ModeloIncompativel,
                                                 cnpj_do_modelo,
                                                 gerar_consolidado,
                                                 preencher_modelo)
from .auditoria import acesso, detalhar, exigir_aba
from .permissoes import tem_permissao
from .auth import Usuario
from .infra import caminho_db_conciliacao, pasta_origens_conciliacao
from .sessoes import SessaoTrabalho, iniciar_job, obter_sessao

router = APIRouter(prefix="/api/conciliacao", tags=["conciliacao"])

FERRAMENTA = "conciliacao"
MIME_XLSX = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")
SUBPASTA_STAGING = "conciliacao"

# ----------------------------------------------------------------------
# Limite de upload proprio da ferramenta
#
# O teto generico `AUDITORIA_WEB_MAX_UPLOAD_MB` vale 2048 MB porque bancos
# Firebird (.FDB) de ERP passam de 300 MB com facilidade; a Auditoria de
# Produtos depende disso. Um relatorio XLSX da SEFAZ vive na casa de poucos
# MB: aceitar 2 GB nesta porta seria dar de graca superficie de negacao de
# servico e de zip bomb justamente ao modulo que precisa validar o pacote
# antes do openpyxl. Os dois limites coexistem; este NAO altera aquele.

MAX_UPLOAD_MB_PADRAO = 50
VAR_MAX_UPLOAD_MB = "AUDITORIA_CONCILIACAO_MAX_UPLOAD_MB"


def max_upload_mb() -> int:
    """Teto por arquivo, em MB, lido do ambiente A CADA chamada.

    Lido na hora (e nao no import) para poder ser ajustado na implantacao e
    exercitado nos testes sem recarregar o modulo. Valor ausente, vazio, nao
    numerico ou <= 0 volta ao default: um teto invalido nunca pode virar
    "sem teto".
    """
    bruto = (os.environ.get(VAR_MAX_UPLOAD_MB) or "").strip()
    try:
        valor = int(bruto)
    except ValueError:
        return MAX_UPLOAD_MB_PADRAO
    return valor if valor > 0 else MAX_UPLOAD_MB_PADRAO


def max_upload_bytes() -> int:
    return max_upload_mb() * 1024 * 1024


# ----------------------------------------------------------------------
# Contratos de erro comuns (schema Error do OpenAPI)

def erro(status: int, detalhe: str, codigo: str = "", **extras) -> HTTPException:
    """HTTPException no formato {detail, code?, ...} do contrato.

    `code` carrega o erro estavel do parser (`XLSX_INVALIDO`,
    `FECHAMENTO_DIMP`...) para a interface poder reagir sem depender do texto,
    que e escrito para pessoas e pode mudar.
    """
    corpo: dict = {"detail": detalhe}
    if codigo:
        corpo["code"] = codigo
    corpo.update(extras)
    return HTTPException(status_code=status, detail=corpo)


def nao_encontrado(detalhe: str = "Registro nao encontrado.") -> HTTPException:
    """404 tambem para recurso ALHEIO: nunca confirmamos que o ID existe."""
    return erro(404, detalhe)


def desatualizado(revision_atual: int) -> HTTPException:
    """409 de concorrencia otimista, com a revision para o cliente recarregar."""
    return erro(
        409,
        "Este registro mudou enquanto voce decidia. Recarregue e revise o "
        "estado atual antes de confirmar.",
        "REVISION_DESATUALIZADA",
        current_revision=revision_atual,
    )


def dinheiro(centavos: int | None) -> dict | None:
    """Centavos -> schema Money. `None` continua None: ausencia nao vira zero.

    Os centavos sao a verdade para conta; o texto e so para a tela. Mandar o
    valor formatado sozinho obrigaria o front a desfazer a formatacao para
    somar — caminho conhecido para erro de arredondamento.
    """
    if centavos is None:
        return None
    return {"centavos": int(centavos),
            "texto": formatar_moeda(Decimal(centavos) / 100, True)}


RESUMO_VAZIO: dict = {
    "total": 0, "em_revisao": 0, "aprovadas": 0, "rejeitadas": 0,
    "avisos": 0, "bloqueios": 0, "conflitos": 0,
}


# ----------------------------------------------------------------------
# Limites de lote (contracts/xlsx-inputs.md)

MAX_ARQUIVOS_LOTE = 100
MAX_STAGING_MB = 500

# Uma sessao processa um lote por vez. Sem isto, dois cliques no botao
# duplicariam o trabalho e disputariam os mesmos arquivos de staging.
_processando: set[str] = set()
_trava_processamento = threading.Lock()


def _store() -> ConciliacaoStore:
    """Conexao por operacao: SQLite nao atravessa thread com seguranca."""
    return ConciliacaoStore(db_path=caminho_db_conciliacao(),
                            origens_path=pasta_origens_conciliacao())


def _staging(sessao: SessaoTrabalho) -> str:
    pasta = os.path.join(sessao.pasta, SUBPASTA_STAGING)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _arquivos_em_staging(sessao: SessaoTrabalho) -> list[tuple[str, str]]:
    """(upload_id, nome_original) na ordem de chegada."""
    pasta = _staging(sessao)
    if not os.path.isdir(pasta):
        return []
    itens = []
    for upload_id in sorted(os.listdir(pasta)):
        manifesto = os.path.join(pasta, upload_id, "nome.txt")
        binario = os.path.join(pasta, upload_id, "arquivo.xlsx")
        if os.path.isfile(manifesto) and os.path.isfile(binario):
            with open(manifesto, encoding="utf-8") as arq:
                itens.append((upload_id, arq.read()))
    return itens


class ProcessarEntrada(BaseModel):
    sessao_id: str


# ----------------------------------------------------------------------
# Upload

@router.post("/upload")
async def upload(sessao_id: str, arquivo: UploadFile, request: Request,
                 usuario: Usuario = Depends(
                     acesso("conciliacao.upload"))) -> dict:
    """Recebe UM .xlsx no staging da sessao.

    O arquivo e' gravado em blocos, contando os bytes durante o streaming: um
    upload gigante nunca chega inteiro a memoria, e o teto e' aplicado antes
    de o disco encher. Se estourar, o parcial e' removido — deixar meio
    arquivo no staging faria o processamento seguinte tentar parsear lixo.

    O nome enviado pelo usuario NAO controla o caminho de destino: cada upload
    vai para uma pasta com id opaco e o nome original fica num manifesto ao
    lado. Assim dois arquivos homonimos convivem e nenhum `..` no nome escapa
    do staging.
    """
    sessao = obter_sessao(sessao_id, usuario, FERRAMENTA)
    pasta = _staging(sessao)

    ja_enviados = _arquivos_em_staging(sessao)
    if len(ja_enviados) >= MAX_ARQUIVOS_LOTE:
        raise erro(422, f"Um lote aceita no maximo {MAX_ARQUIVOS_LOTE} "
                        f"arquivos.", "LOTE_CHEIO")

    nome = os.path.basename((arquivo.filename or "").replace("\\", "/")).strip()
    if not nome.lower().endswith(".xlsx"):
        raise erro(422, "Somente arquivos .xlsx sao aceitos.", "XLSX_INVALIDO")

    upload_id = secrets.token_urlsafe(12)
    destino_dir = os.path.join(pasta, upload_id)
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, "arquivo.xlsx")

    teto = max_upload_bytes()
    acumulado = sum(
        os.path.getsize(os.path.join(pasta, uid, "arquivo.xlsx"))
        for uid, _ in ja_enviados)
    tamanho = 0
    try:
        with open(destino, "wb") as saida:
            while True:
                pedaco = await arquivo.read(1024 * 1024)
                if not pedaco:
                    break
                tamanho += len(pedaco)
                if tamanho > teto:
                    raise erro(
                        413,
                        f"Arquivo maior que {max_upload_mb()} MB.",
                        "XLSX_ACIMA_DO_LIMITE")
                if acumulado + tamanho > MAX_STAGING_MB * 1024 * 1024:
                    raise erro(
                        413,
                        f"O lote passou de {MAX_STAGING_MB} MB acumulados.",
                        "LOTE_ACIMA_DO_LIMITE")
                saida.write(pedaco)
        with open(os.path.join(destino_dir, "nome.txt"), "w",
                  encoding="utf-8") as manifesto:
            manifesto.write(nome)
    except Exception:
        shutil.rmtree(destino_dir, ignore_errors=True)
        raise

    detalhar(request, f"arquivo: {nome} ({tamanho} bytes)")
    return {"ok": True, "upload_id": upload_id, "arquivo": nome,
            "tamanho": tamanho}


# ----------------------------------------------------------------------
# Processamento

@router.post("/processar")
def processar(entrada: ProcessarEntrada, request: Request,
              usuario: Usuario = Depends(
                  acesso("conciliacao.processar"))) -> dict:
    """Processa em job tudo que esta no staging da sessao."""
    sessao = obter_sessao(entrada.sessao_id, usuario, FERRAMENTA)
    manifesto = _arquivos_em_staging(sessao)
    if not manifesto:
        raise erro(422, "Envie ao menos um arquivo antes de processar.",
                   "LOTE_VAZIO")

    with _trava_processamento:
        if sessao.id in _processando:
            raise erro(409, "Esta sessao ja tem um processamento em "
                            "andamento. Aguarde o termino.",
                       "PROCESSAMENTO_EM_ANDAMENTO")
        _processando.add(sessao.id)

    # Identidade capturada AQUI, da sessao autenticada, e levada ao job como
    # snapshot primitivo. O corpo da requisicao nunca informa ator.
    ator = {"usuario_id": usuario.id, "usuario_login": usuario.usuario}
    pasta = _staging(sessao)
    teto = max_upload_bytes()

    store = _store()
    try:
        lote_id = store.abrir_lote(sessao_id=sessao.id,
                                   total_arquivos=len(manifesto), **ator)
    finally:
        store.fechar()

    detalhar(request, f"lote {lote_id}: {len(manifesto)} arquivo(s)")

    def _executar() -> dict:
        # Store proprio da thread do job.
        interno = _store()
        try:
            interno.marcar_processando(lote_id)
            for ordem, (upload_id, nome) in enumerate(manifesto, start=1):
                caminho = os.path.join(pasta, upload_id, "arquivo.xlsx")
                interno.importar_arquivo(
                    lote_id, caminho_staging=caminho, nome_recebido=nome,
                    ordem=ordem, max_bytes=teto, **ator)
            resumo_lote = interno.concluir_lote(lote_id)
            # O staging ja cumpriu o papel: toda fonte aceita foi preservada
            # em origens/<sha>.xlsx. A limpeza acontece AQUI, ainda sob a
            # trava da sessao: solta-la antes deixaria uma janela em que um
            # segundo pedido encontraria a trava livre e o staging ainda de
            # pe, abrindo um lote duplicado sobre arquivos prestes a sumir.
            # Se o processamento falhar, o staging fica para nova tentativa.
            shutil.rmtree(pasta, ignore_errors=True)
            return {**resumo_lote, "lote_id": lote_id}
        finally:
            interno.fechar()
            with _trava_processamento:
                _processando.discard(sessao.id)

    job = iniciar_job(sessao, "Processando relatorios da SEFAZ", _executar)
    return {"job_id": job.id, "lote_id": lote_id}


@router.get("/lotes/{lote_id}")
def obter_lote(lote_id: int,
               usuario: Usuario = Depends(exigir_aba("conciliacao"))) -> dict:
    """Resultado PERSISTENTE do lote.

    O job vive em memoria e some no reinicio; esta rota continua respondendo,
    porque o resultado de cada arquivo foi gravado durante o processamento.
    """
    store = _store()
    try:
        lote = store.obter_lote(lote_id, usuario_login=usuario.usuario)
    except LookupError as exc:
        raise nao_encontrado("Lote nao encontrado.") from exc
    finally:
        store.fechar()

    return {
        "id": lote["id"], "estado": lote["estado"],
        "total_arquivos": lote["total_arquivos"],
        "processados": lote["processados"], "duplicados": lote["duplicados"],
        "conflitantes": lote["conflitantes"], "rejeitados": lote["rejeitados"],
        "criado_em": lote["criado_em"],
        "iniciado_em": lote["iniciado_em"] or None,
        "concluido_em": lote["concluido_em"] or None,
        "itens": [{
            "id": i["id"], "fonte_id": i["fonte_id"],
            "conciliacao_id": None,
            "nome_recebido": i["nome_recebido"],
            "sha256": i["sha256_tentativa"] or None,
            "resultado": i["resultado"], "mensagem": i["mensagem"],
            "codigo": i["codigo_erro"] or None,
        } for i in lote["itens"]],
    }


# ----------------------------------------------------------------------
# Leitura
#
# Rotas de consulta usam `exigir_aba`: exigem a permissao da ferramenta mas
# NAO entram no historico. A tela recarrega a lista a cada filtro digitado, e
# auditar isso afogaria o que importa — o acesso ja ficou registrado em
# `navegacao.aba`. Downloads e mutacoes, esses sim, sao auditados.

def _filtros(cnpj: str, texto: str, competencia_de: str, competencia_ate: str,
             estado: str, layout: str, excecao: str) -> dict:
    """Somente os filtros preenchidos, para a allowlist do store decidir."""
    bruto = {"cnpj": cnpj, "texto": texto, "competencia_de": competencia_de,
             "competencia_ate": competencia_ate, "estado": estado,
             "layout": layout, "excecao": excecao}
    return {k: v for k, v in bruto.items() if v}


def _versao_json(versao: dict, *, completa: bool, fonte: dict | None) -> dict:
    corpo = {
        "id": versao["id"], "numero": versao["numero"],
        "estado": versao["estado"], "layout": versao["layout"],
        "receita_declarada": dinheiro(versao["receita_declarada"]),
        "receita_calculada": dinheiro(versao["receita_calculada"]),
        "diferenca_receita": dinheiro(versao["diferenca_receita"]),
        # None continua None: no Quadro 50-5 nao existe DIMP, e mostrar
        # "R$ 0,00" afirmaria que a empresa nao teve movimento eletronico.
        "total_pix": dinheiro(versao["total_pix"]),
        "total_nao_pix": dinheiro(versao["total_nao_pix"]),
    }
    if not completa:
        return corpo
    corpo.update({
        "declarada_com_st": dinheiro(versao["declarada_com_st"]),
        "declarada_sem_st": dinheiro(versao["declarada_sem_st"]),
        "calculada_com_st": dinheiro(versao["calculada_com_st"]),
        "calculada_sem_st": dinheiro(versao["calculada_sem_st"]),
        "diferenca_com_st": dinheiro(versao["diferenca_com_st"]),
        "diferenca_sem_st": dinheiro(versao["diferenca_sem_st"]),
        "razao_social": versao["razao_social"],
        "aba_origem": versao["aba_origem"],
        "linha_resumo": versao["linha_resumo"],
        "fonte": _fonte_json(fonte),
    })
    return corpo


def _fonte_json(fonte: dict | None) -> dict | None:
    if not fonte:
        return None
    return {"id": fonte["id"], "arquivo": fonte["nome_original"],
            "sha256": fonte["sha256"],
            "versao_parser": fonte["versao_parser"]}


@router.get("/resumo")
def resumo(cnpj: str = "", texto: str = "", competencia_de: str = "",
           competencia_ate: str = "", estado: str = "", layout: str = "",
           excecao: str = "",
           usuario: Usuario = Depends(exigir_aba("conciliacao"))) -> dict:
    """Indicadores do painel, com os MESMOS filtros da listagem."""
    store = _store()
    try:
        dados = store.resumo(**_filtros(cnpj, texto, competencia_de,
                                        competencia_ate, estado, layout,
                                        excecao))
    except ValueError as exc:
        raise erro(422, str(exc), "FILTRO_INVALIDO") from exc
    finally:
        store.fechar()
    return {**{k: dados[k] for k in RESUMO_VAZIO},
            "diferenca_total": dinheiro(dados["diferenca_total"])}


@router.get("/conciliacoes")
def listar(cnpj: str = "", texto: str = "", competencia_de: str = "",
           competencia_ate: str = "", estado: str = "", layout: str = "",
           excecao: str = "", pagina: int = 1, limite: int = 50,
           ordenar: str = "competencia_desc",
           usuario: Usuario = Depends(exigir_aba("conciliacao"))) -> dict:
    store = _store()
    try:
        dados = store.listar(
            pagina=pagina, limite=limite, ordenar=ordenar,
            **_filtros(cnpj, texto, competencia_de, competencia_ate, estado,
                       layout, excecao))
    except ValueError as exc:
        raise erro(422, str(exc), "FILTRO_INVALIDO") from exc
    finally:
        store.fechar()

    return {
        "itens": [{**linha,
                   "versao": _versao_json(linha["versao"], completa=False,
                                          fonte=None)}
                  for linha in dados["itens"]],
        "total": dados["total"], "pagina": dados["pagina"],
        "limite": dados["limite"], "paginas": dados["paginas"],
    }


@router.get("/conciliacoes/{conciliacao_id}")
def detalhar_conciliacao(
        conciliacao_id: int,
        usuario: Usuario = Depends(exigir_aba("conciliacao"))) -> dict:
    """Detalhe completo: valores, versoes, DIMP, proveniencia e historico."""
    store = _store()
    try:
        d = store.detalhar(conciliacao_id)
        instituicoes = (store.instituicoes(d["versao_vigente"]["id"])
                        if d["versao_vigente"] else [])
        fontes = {v["fonte_id"]: store.obter_fonte(v["fonte_id"])
                  for v in d["versoes"]}
    except LookupError as exc:
        raise nao_encontrado("Conciliacao nao encontrada.") from exc
    finally:
        store.fechar()

    fonte_vigente = _fonte_json(d["fonte"])
    return {
        "id": d["id"], "cnpj": d["cnpj"], "razao_social": d["razao_social"],
        "competencia": d["competencia"], "estado": d["estado"],
        "revision": d["revision"],
        "avisos_abertos": d["avisos_abertos"],
        "bloqueios_abertos": d["bloqueios_abertos"],
        "conflitos_abertos": d["conflitos_abertos"],
        "versao": _versao_json(d["versao_vigente"], completa=False,
                               fonte=None) if d["versao_vigente"] else None,
        "versao_vigente": _versao_json(
            d["versao_vigente"], completa=True,
            fonte=fontes.get(d["versao_vigente"]["fonte_id"])
        ) if d["versao_vigente"] else None,
        "versoes": [_versao_json(v, completa=True,
                                 fonte=fontes.get(v["fonte_id"]))
                    for v in d["versoes"]],
        "movimentos": [{
            "id": m["id"], "versao_id": m["versao_id"],
            "instituicao": m["instituicao"], "linha_origem": m["linha_origem"],
            "debito": dinheiro(m["debito"]), "credito": dinheiro(m["credito"]),
            "transferencia": dinheiro(m["transferencia"]),
            "pix": dinheiro(m["pix"]), "voucher": dinheiro(m["voucher"]),
            "outras": dinheiro(m["outras"]),
            "total_dimp": dinheiro(m["total_dimp"]),
            "total_nao_pix": dinheiro(m["total_nao_pix"]),
            "proveniencia": {
                "fonte": fonte_vigente, "aba": m["aba"],
                "celulas": _celulas_do_movimento(m),
            },
        } for m in d["movimentos"]],
        # Agregado POR INSTITUICAO para leitura; as linhas originais acima
        # continuam inteiras, com a celula de cada total.
        "instituicoes": [{
            "instituicao": i["instituicao"], "linhas": i["linhas"],
            "pix": dinheiro(i["pix"]),
            "total_dimp": dinheiro(i["total_dimp"]),
            "total_nao_pix": dinheiro(i["total_nao_pix"]),
        } for i in instituicoes],
        "fatos": [{
            "id": f["id"], "versao_id": f["versao_id"],
            "metrica": f["metrica"], "valor": dinheiro(f["valor_numerico"]),
            "tipo_origem": f["tipo_origem"], "aba": f["aba"] or "",
            "celula": f["celula"] or "", "rotulo": f["rotulo"],
            "regra_parser": f["regra_parser"], "formula": f["formula"] or "",
            "fatos_origem": f["fatos_origem"],
            "fonte": fonte_vigente,
        } for f in d["fatos"]],
        "excecoes": [_excecao_json(e) for e in d["excecoes"]],
        "conflitos": [{
            "id": k["id"], "estado": k["estado"],
            "versao_vigente_id": k["versao_vigente_id"],
            "versao_candidata_id": k["versao_candidata_id"],
            "justificativa": k["justificativa"],
            "resolvido_por": k["resolvido_por_login"],
            "criado_em": k["criado_em"],
            "resolvido_em": k["resolvido_em"] or "",
        } for k in d["conflitos"]],
        "revisoes": [{
            "id": r["id"], "versao_id": r["versao_id"],
            "revision_anterior": r["revision_anterior"],
            "estado_anterior": r["estado_anterior"],
            "estado_novo": r["estado_novo"],
            "justificativa": r["justificativa"],
            "usuario": r["usuario_login"], "criada_em": r["criada_em"],
        } for r in d["revisoes"]],
    }


def _celulas_do_movimento(m: dict) -> dict:
    """Celula exata de cada componente, deduzida da coluna do contrato."""
    linha = m["linha_origem"]
    return {campo: f"{coluna}{linha}" for coluna, campo in (
        ("C", "instituicao"), ("D", "debito"), ("E", "credito"),
        ("F", "transferencia"), ("G", "pix"), ("H", "voucher"),
        ("I", "outras"), ("J", "total_dimp"))}


def _excecao_json(e: dict) -> dict:
    corpo = {
        "id": e["id"], "conciliacao_id": e["conciliacao_id"],
        "versao_id": e["versao_id"], "codigo": e["codigo"],
        "severidade": e["severidade"], "mensagem": e["mensagem"],
        "estado": e["estado"], "resolucao": e["resolucao"],
        "resolvida_por": e["resolvida_por_login"],
        "criada_em": e["criada_em"], "resolvida_em": e["resolvida_em"] or "",
    }
    for extra in ("cnpj", "competencia", "razao_social"):
        if extra in e:
            corpo[extra] = e[extra]
    return corpo


@router.get("/excecoes")
def listar_excecoes(estado: str = "aberta", severidade: str = "",
                    cnpj: str = "", pagina: int = 1, limite: int = 50,
                    usuario: Usuario = Depends(
                        exigir_aba("conciliacao"))) -> dict:
    store = _store()
    try:
        dados = store.listar_excecoes(estado=estado, severidade=severidade,
                                      cnpj=cnpj, pagina=pagina, limite=limite)
    except ValueError as exc:
        raise erro(422, str(exc), "FILTRO_INVALIDO") from exc
    finally:
        store.fechar()
    return {"itens": [_excecao_json(e) for e in dados["itens"]],
            "total": dados["total"], "pagina": dados["pagina"],
            "limite": dados["limite"], "paginas": dados["paginas"]}


# ----------------------------------------------------------------------
# Decisoes
#
# O corpo destas rotas NAO tem campo de ator: usuario e' sempre `usuario`, a
# identidade da sessao autenticada. Um `reviewer` vindo do JSON seria
# assinatura falsificavel numa decisao fiscal (SEC005).

class RevisaoEntrada(BaseModel):
    estado: str                      # em_revisao | rejeitada
    justificativa: str
    revision: int | None = None


class AprovacaoEntrada(BaseModel):
    justificativa: str = ""
    revision: int | None = None


class ResolucaoEntrada(BaseModel):
    resolucao: str


class ConflitoEntrada(BaseModel):
    decisao: str                     # manter_vigente | promover_candidata
    justificativa: str
    revision: int | None = None


def _traduzir(exc: Exception):
    """Excecoes do dominio -> contrato HTTP, sem vazar detalhe interno."""
    if isinstance(exc, ConcorrenciaError):
        return desatualizado(exc.revision_atual)
    if isinstance(exc, TransicaoInvalida):
        return erro(409, exc.mensagem, exc.codigo)
    if isinstance(exc, LookupError):
        return nao_encontrado(str(exc) or "Registro nao encontrado.")
    return None


def _decidir(operacao, request: Request, detalhe: str):
    """Executa a operacao do store traduzindo as falhas conhecidas."""
    store = _store()
    try:
        resultado = operacao(store)
    except (ConcorrenciaError, TransicaoInvalida, LookupError) as exc:
        raise _traduzir(exc) from exc
    finally:
        store.fechar()
    detalhar(request, detalhe)
    return resultado


@router.post("/conciliacoes/{conciliacao_id}/revisar")
def revisar(conciliacao_id: int, entrada: RevisaoEntrada, request: Request,
            usuario: Usuario = Depends(acesso("conciliacao.revisar"))) -> dict:
    """Rejeita a competencia ou a devolve para Em revisao."""
    return _decidir(
        lambda store: store.revisar(
            conciliacao_id, estado_novo=entrada.estado,
            justificativa=entrada.justificativa, revision=entrada.revision,
            usuario_id=usuario.id, usuario_login=usuario.usuario),
        request, f"conciliacao {conciliacao_id} -> {entrada.estado}")


@router.post("/conciliacoes/{conciliacao_id}/aprovar")
def aprovar(conciliacao_id: int, entrada: AprovacaoEntrada, request: Request,
            usuario: Usuario = Depends(acesso("conciliacao.aprovar"))) -> dict:
    """Aprova a versao vigente. Bloqueio ou conflito aberto impedem."""
    return _decidir(
        lambda store: store.aprovar(
            conciliacao_id, justificativa=entrada.justificativa,
            revision=entrada.revision, usuario_id=usuario.id,
            usuario_login=usuario.usuario),
        request, f"conciliacao {conciliacao_id} aprovada")


@router.post("/excecoes/{excecao_id}/resolver")
def resolver_excecao(excecao_id: int, entrada: ResolucaoEntrada,
                     request: Request,
                     usuario: Usuario = Depends(
                         acesso("conciliacao.resolver_excecao"))) -> dict:
    return _decidir(
        lambda store: store.resolver_excecao(
            excecao_id, resolucao=entrada.resolucao, usuario_id=usuario.id,
            usuario_login=usuario.usuario),
        request, f"excecao {excecao_id} resolvida")


@router.get("/conflitos")
def listar_conflitos(estado: str = "aberto", pagina: int = 1,
                     limite: int = 50,
                     usuario: Usuario = Depends(
                         exigir_aba("conciliacao"))) -> dict:
    store = _store()
    try:
        dados = store.listar_conflitos(estado=estado, pagina=pagina,
                                       limite=limite)
        comparacoes = {
            k["id"]: store.comparar_versoes(k["versao_vigente_id"],
                                            k["versao_candidata_id"])
            for k in dados["itens"]}
    except ValueError as exc:
        raise erro(422, str(exc), "FILTRO_INVALIDO") from exc
    except LookupError as exc:
        raise nao_encontrado(str(exc)) from exc
    finally:
        store.fechar()

    return {
        "itens": [{
            "id": k["id"], "conciliacao_id": k["conciliacao_id"],
            "cnpj": k["cnpj"], "competencia": k["competencia"],
            "razao_social": k["razao_social"], "revision": k["revision"],
            "estado": k["estado"],
            "versao_vigente_id": k["versao_vigente_id"],
            "versao_candidata_id": k["versao_candidata_id"],
            "justificativa": k["justificativa"],
            "resolvido_por": k["resolvido_por_login"],
            "criado_em": k["criado_em"],
            "resolvido_em": k["resolvido_em"] or "",
            "diferencas": [{
                "campo": d["campo"],
                "vigente": dinheiro(d["vigente"]),
                "candidata": dinheiro(d["candidata"]),
                "delta": dinheiro(d["delta"]),
                "mudou": d["mudou"],
            } for d in comparacoes[k["id"]] if d["mudou"]],
        } for k in dados["itens"]],
        "total": dados["total"], "pagina": dados["pagina"],
        "limite": dados["limite"], "paginas": dados["paginas"],
    }


@router.post("/conflitos/{conflito_id}/resolver")
def resolver_conflito(conflito_id: int, entrada: ConflitoEntrada,
                      request: Request,
                      usuario: Usuario = Depends(
                          acesso("conciliacao.resolver_conflito"))) -> dict:
    """Mantem a vigente ou promove a candidata. Nada e' apagado."""
    return _decidir(
        lambda store: store.resolver_conflito(
            conflito_id, decisao=entrada.decisao,
            justificativa=entrada.justificativa, revision=entrada.revision,
            usuario_id=usuario.id, usuario_login=usuario.usuario),
        request, f"conflito {conflito_id}: {entrada.decisao}")


# ----------------------------------------------------------------------
# Exportacoes
#
# Temporarios sao criados com `mkdtemp` (permissao restrita, nome nao
# adivinhavel) e removidos por BackgroundTask DEPOIS que a resposta foi
# enviada. `mktemp` so reserva um nome e deixa janela de corrida — o plano
# proibe para esta feature.

def _pasta_temporaria() -> str:
    return tempfile.mkdtemp(prefix="conciliacao_saida_")


def _limpar(pasta: str):
    def _tarefa() -> None:
        shutil.rmtree(pasta, ignore_errors=True)
    return _tarefa


class ExportarEntrada(BaseModel):
    cnpj: str = ""
    texto: str = ""
    competencia_de: str = ""
    competencia_ate: str = ""
    estado: str = ""
    layout: str = ""
    excecao: str = ""


@router.post("/exportar")
def exportar(entrada: ExportarEntrada, request: Request,
             usuario: Usuario = Depends(
                 acesso("conciliacao.exportar"))) -> FileResponse:
    """Consolidado auditavel com os filtros escolhidos."""
    filtros = _filtros(entrada.cnpj, entrada.texto, entrada.competencia_de,
                       entrada.competencia_ate, entrada.estado,
                       entrada.layout, entrada.excecao)
    store = _store()
    try:
        pagina = store.listar(limite=200, pagina=1, **filtros)
        total = pagina["total"]
        detalhes = []
        # Pagina ate o fim: o consolidado nao pode entregar so a primeira
        # pagina e parecer completo.
        for numero in range(1, pagina["paginas"] + 1):
            atual = (pagina if numero == 1
                     else store.listar(limite=200, pagina=numero, **filtros))
            for linha in atual["itens"]:
                detalhes.append(store.detalhar(linha["id"]))
    except ValueError as exc:
        raise erro(422, str(exc), "FILTRO_INVALIDO") from exc
    finally:
        store.fechar()

    pasta = _pasta_temporaria()
    nome = f"conciliacao_fiscal_{_carimbo()}.xlsx"
    destino = os.path.join(pasta, nome)
    try:
        gerar_consolidado(
            destino, conciliacoes=detalhes, gerado_por=usuario.usuario,
            filtros=filtros, versao_parser=VERSAO_PARSER)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise

    detalhar(request, f"{total} conciliacao(oes); filtros: "
                      f"{filtros or 'nenhum'}")
    return FileResponse(
        destino, media_type=MIME_XLSX, filename=nome,
        background=BackgroundTask(_limpar(pasta)))


@router.post("/preencher-modelo")
async def preencher_modelo_rota(
        arquivo: UploadFile, request: Request, cnpj: str = Form(""),
        competencia_de: str = Form(""), competencia_ate: str = Form(""),
        incluir_em_revisao: bool = Form(False),
        confirmacao_pendentes: bool = Form(False),
        usuario: Usuario = Depends(
            acesso("conciliacao.preencher_modelo"))) -> FileResponse:
    """Devolve uma COPIA do modelo preenchida para UM CNPJ.

    O arquivo enviado nunca e' alterado: ele e' salvo num temporario, validado
    e usado apenas como base da copia.
    """
    digitos = "".join(c for c in cnpj if c.isdigit())
    if len(digitos) != 14:
        raise erro(422, "Informe um CNPJ com 14 digitos. O preenchimento vale "
                        "para uma empresa por vez.", "CNPJ_INVALIDO")

    pasta = _pasta_temporaria()
    try:
        modelo = os.path.join(pasta, "modelo.xlsx")
        tamanho = 0
        teto = max_upload_bytes()
        with open(modelo, "wb") as saida:
            while True:
                pedaco = await arquivo.read(1024 * 1024)
                if not pedaco:
                    break
                tamanho += len(pedaco)
                if tamanho > teto:
                    raise erro(413, f"Modelo maior que {max_upload_mb()} MB.",
                               "XLSX_ACIMA_DO_LIMITE")
                saida.write(pedaco)

        # O modelo passa pela MESMA validacao de pacote dos relatorios.
        try:
            validar_pacote_xlsx(modelo, max_bytes=teto)
        except ErroConciliacao as exc:
            raise erro(422, exc.mensagem, exc.codigo) from exc

        sha_modelo = ConciliacaoStore.sha256_do_arquivo(modelo)
        do_modelo = cnpj_do_modelo(modelo)
        if do_modelo and do_modelo != digitos:
            raise erro(422,
                       "O CNPJ do modelo nao coincide com o CNPJ escolhido.",
                       "CNPJ_DIVERGENTE")

        store = _store()
        try:
            filtros = {"cnpj": digitos}
            if competencia_de:
                filtros["competencia_de"] = competencia_de
            if competencia_ate:
                filtros["competencia_ate"] = competencia_ate
            pagina = store.listar(limite=200, **filtros)
            elegiveis, pendentes, recusadas = {}, [], []
            detalhes_texto = {}
            for linha in pagina["itens"]:
                d = store.detalhar(linha["id"])
                # Rejeitada NUNCA entra. Bloqueio ou conflito aberto tambem
                # nao, mesmo que o estado persistido diga "aprovada" — o
                # estado pode ter sido gravado antes de a pendencia aparecer.
                if (d["estado"] == "rejeitada" or d["bloqueios_abertos"]
                        or d["conflitos_abertos"]):
                    recusadas.append(d["competencia"])
                    continue
                if d["estado"] != "aprovada":
                    if not incluir_em_revisao:
                        recusadas.append(d["competencia"])
                        continue
                    pendentes.append(d["competencia"])
                vigente = d["versao_vigente"]
                elegiveis[d["competencia"]] = {
                    campo: vigente[campo] for campo in (
                        "receita_declarada", "declarada_com_st",
                        "declarada_sem_st", "receita_calculada",
                        "calculada_com_st")}
                agregado = store.instituicoes(vigente["id"])
                detalhes_texto[d["competencia"]] = {
                    "pix_texto": _por_instituicao(agregado, "pix"),
                    "nao_pix_texto": _por_instituicao(agregado, "total_nao_pix"),
                }
        except ValueError as exc:
            raise erro(422, str(exc), "FILTRO_INVALIDO") from exc
        finally:
            store.fechar()

        if pendentes:
            if not usuario.admin and not tem_permissao(
                    usuario, "conciliacao.incluir_pendentes"):
                raise erro(403, "Incluir competencias Em revisao exige a "
                                "permissao adicional.", "PERMISSAO_ADICIONAL")
            if not confirmacao_pendentes:
                raise erro(409,
                           "Ha competencias Em revisao na selecao. Confirme "
                           "explicitamente para incluir; elas sairao "
                           "sinalizadas no arquivo.",
                           "CONFIRMACAO_PENDENTES")
        if not elegiveis:
            raise erro(422,
                       "Nenhuma competencia elegivel para este CNPJ no "
                       "periodo escolhido.", "SEM_COMPETENCIAS")

        nome = f"planilha_mestre_{digitos}_preenchida_{_carimbo()}.xlsx"
        destino = os.path.join(pasta, nome)
        try:
            resultado = preencher_modelo(
                modelo, destino, competencias=elegiveis,
                detalhes_por_competencia=detalhes_texto,
                pendentes=pendentes)
        except ModeloIncompativel as exc:
            raise erro(422, str(exc), exc.codigo) from exc
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise

    detalhar(request,
             f"cnpj {digitos}; modelo sha {sha_modelo[:12]}; "
             f"{len(resultado['competencias'])} competencia(s); "
             f"pendentes: {len(pendentes)}; recusadas: {len(recusadas)}")
    return FileResponse(
        destino, media_type=MIME_XLSX, filename=nome,
        background=BackgroundTask(_limpar(pasta)))


def _por_instituicao(agregado: list[dict], campo: str) -> str:
    """'Instituicao: R$ 1.234,56' por linha, como o modelo legado espera."""
    partes = []
    for item in agregado:
        valor = dinheiro(item.get(campo))
        if valor:
            partes.append(f"{item['instituicao']}: {valor['texto']}")
    return "\n".join(partes)


def _carimbo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


@router.get("/fontes/{fonte_id}/download")
def baixar_fonte(fonte_id: int, request: Request,
                 usuario: Usuario = Depends(
                     acesso("conciliacao.fonte_download"))) -> FileResponse:
    """Baixa a evidencia XLSX original, exatamente como chegou.

    E' a prova de que o numero exibido veio de algum lugar, entao o download
    e' auditado — e o arquivo servido e' o imutavel de `origens/`, nunca uma
    reconstrucao.
    """
    store = _store()
    try:
        fonte = store.obter_fonte(fonte_id)
    except LookupError as exc:
        raise nao_encontrado("Fonte nao encontrada.") from exc
    finally:
        store.fechar()

    caminho = os.path.join(pasta_origens_conciliacao(),
                           f"{fonte['sha256']}.xlsx")
    if not os.path.isfile(caminho):
        # Banco apontando para arquivo ausente e' incidente, nao "nao achei".
        raise erro(500, "A evidencia desta fonte nao esta disponivel no "
                        "servidor. Avise o administrador.",
                   "FONTE_INDISPONIVEL")

    detalhar(request, f"fonte {fonte_id} ({fonte['sha256'][:12]})")
    return FileResponse(
        caminho,
        media_type=MIME_XLSX,
        filename=fonte["nome_original"] or f"{fonte['sha256'][:12]}.xlsx")
