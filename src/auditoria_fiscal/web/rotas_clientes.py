"""Rotas da nona ferramenta: Clientes, cofre de senhas e vencimentos (spec 012).

Mesma divisao das outras abas: leitura com `exigir_aba` (nao entope o
historico), mutacao e download com `acesso(<slug>)`. O cofre tem tres
camadas a mais, todas no servidor:

1. `cofre.ver` conferido a cada revelacao — e a tentativa negada vai tambem
   para a trilha do cofre, nao so para a trilha de uso.
2. **Desbloqueio**: antes de revelar, a pessoa confirma a propria senha; vale
   15 minutos para AQUELA sessao de login (proposta P-04 da spec). Fica em
   memoria do processo: reiniciar o servidor pede de novo.
3. Limite por hora, contado na trilha imutavel do `clientes.db`.

As previas de importacao tambem ficam em memoria (30 minutos, presas a quem
enviou). As senhas da planilha sao cifradas na hora da leitura, com um AAD
temporario, e so sao decifradas no instante de gravar.

Este modulo e' a UNICA camada que conhece FastAPI nesta feature.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
from dataclasses import dataclass, field

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from ..core import certificados as ct
from ..core import clientes as cl
from ..core import planilha_clientes as pc
from ..core import planilha_empresas as pe
from ..core.cofre import Cofre, CofreIndisponivel, SegredoIlegivel
from ..ferramentas import clientes_store as cs
from ..ferramentas.relatorio_clientes import gerar_relacao
from ..ferramentas.relatorio_base_fiscal import gerar_relatorio_base_fiscal
from . import auditoria as trilha
from . import auth, permissoes
from .auditoria import acesso, detalhar, exigir_aba
from .auth import Usuario
from .infra import caminho_db_clientes

router = APIRouter(prefix="/api/clientes", tags=["clientes"])

MIME_XLSX = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")
FUSO_SALVADOR = dt.timezone(dt.timedelta(hours=-3))

DESBLOQUEIO_MINUTOS = 15
PREVIA_MINUTOS = 30
PREVIAS_POR_USUARIO = 3
TENTATIVAS_DESBLOQUEIO = 5
MAX_COLETA_BYTES = 10 * 1024 * 1024

COFRE_BLOQUEADO = "COFRE_BLOQUEADO"
COFRE_INDISPONIVEL = "COFRE_INDISPONIVEL"
SENHA_INCORRETA = "SENHA_INCORRETA"
MUITAS_TENTATIVAS = "MUITAS_TENTATIVAS"
LIMITE_EXCEDIDO = "LIMITE_EXCEDIDO"
SEGREDO_ILEGIVEL = "SEGREDO_ILEGIVEL"
PREVIA_EXPIRADA = "PREVIA_EXPIRADA"
ARQUIVO_GRANDE = "ARQUIVO_GRANDE"


def _agora() -> dt.datetime:
    return dt.datetime.now(FUSO_SALVADOR)


def _hoje() -> dt.date:
    return _agora().date()


def erro(status: int, detalhe: str, codigo: str = "", **extras) -> HTTPException:
    corpo: dict = {"detail": detalhe}
    if codigo:
        corpo["code"] = codigo
    corpo.update(extras)
    return HTTPException(status_code=status, detail=corpo)


def _cofre() -> Cofre | None:
    try:
        return Cofre.de_ambiente()
    except CofreIndisponivel:
        return None


def _store(com_cofre: bool = False) -> cs.ClientesStore:
    return cs.ClientesStore(caminho_db_clientes(),
                            cofre=_cofre() if com_cofre else None)


def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, cs.ConcorrenciaError):
        return erro(409, "Este cliente mudou enquanto você editava. Recarregue "
                         "e confira antes de salvar.", "REVISION_DESATUALIZADA",
                    current_revision=exc.revision_atual)
    if isinstance(exc, cs.LimiteExcedido):
        return erro(429, str(exc), LIMITE_EXCEDIDO)
    if isinstance(exc, CofreIndisponivel):
        return erro(503, str(exc), COFRE_INDISPONIVEL)
    if isinstance(exc, SegredoIlegivel):
        return erro(409, str(exc), SEGREDO_ILEGIVEL)
    if isinstance(exc, ct.ErroCertificado):
        return erro(422, exc.mensagem, exc.codigo)
    if isinstance(exc, cl.ErroClientes):
        status = 422 if exc.codigo in (
            cl.CAMPO_OBRIGATORIO, cl.VALOR_INVALIDO, cl.DOCUMENTO_INVALIDO,
            cl.FAIXAS_INVALIDAS, pc.PLANILHA_INVALIDA,
            pc.CABECALHO_NAO_ENCONTRADO, cs.COLETA_INVALIDA) else 409
        return erro(status, exc.mensagem, exc.codigo)
    if isinstance(exc, LookupError):
        return erro(404, str(exc) or "Registro não encontrado.")
    if isinstance(exc, ValueError):
        return erro(422, str(exc), "FILTRO_INVALIDO")
    raise exc


_TRADUZIVEIS = (cs.ConcorrenciaError, cs.LimiteExcedido, CofreIndisponivel,
                SegredoIlegivel, ct.ErroCertificado, cl.ErroClientes,
                LookupError, ValueError)


def _executar(operacao, *, com_cofre: bool = False):
    store = _store(com_cofre)
    try:
        return operacao(store)
    except _TRADUZIVEIS as exc:
        raise _traduzir(exc) from exc
    finally:
        store.fechar()


def _quem(usuario: Usuario) -> dict:
    return {"usuario_id": usuario.id, "usuario_login": usuario.usuario}


def _ip(request: Request) -> str:
    return trilha._ip(request)  # noqa: SLF001 — mesma regra de IP da trilha


# ----------------------------------------------------------------------
# Desbloqueio do cofre e previas (memoria do processo)

_trava = threading.Lock()
_desbloqueios: dict[str, dt.datetime] = {}
_tentativas: dict[int, list[dt.datetime]] = {}


def _chave_sessao(request: Request) -> str:
    token = request.cookies.get(auth.COOKIE_SESSAO) or ""
    return hashlib.sha256(token.encode()).hexdigest()


def _desbloqueado_ate(request: Request) -> dt.datetime | None:
    chave = _chave_sessao(request)
    with _trava:
        ate = _desbloqueios.get(chave)
        if ate is not None and ate <= _agora():
            _desbloqueios.pop(chave, None)
            return None
        return ate


@dataclass
class Previa:
    tipo: str
    usuario_id: int
    criada: dt.datetime
    nome_arquivo: str
    hash_arquivo: str
    dados: object
    segredos: dict = field(default_factory=dict)   # linha -> {campo: (cifra, situacao)}
    aad: str = ""


_previas: dict[str, Previa] = {}


def _limpar_previas() -> None:
    limite = _agora() - dt.timedelta(minutes=PREVIA_MINUTOS)
    for token in [t for t, p in _previas.items() if p.criada < limite]:
        _previas.pop(token, None)


def _guardar_previa(previa: Previa) -> str:
    with _trava:
        _limpar_previas()
        minhas = sorted((p.criada, t) for t, p in _previas.items()
                        if p.usuario_id == previa.usuario_id)
        for _, antiga in minhas[:max(0, len(minhas) - PREVIAS_POR_USUARIO + 1)]:
            _previas.pop(antiga, None)
        token = secrets.token_urlsafe(18)
        _previas[token] = previa
        return token


def _obter_previa(token: str, usuario: Usuario, tipo: str) -> Previa:
    with _trava:
        _limpar_previas()
        previa = _previas.get(token)
    if previa is None or previa.usuario_id != usuario.id or previa.tipo != tipo:
        raise erro(404, "A prévia expirou ou não é sua. Envie o arquivo de novo.",
                   PREVIA_EXPIRADA)
    return previa


def _descartar_previa(token: str) -> None:
    with _trava:
        _previas.pop(token, None)


async def _receber(arquivo: UploadFile, destino: str, limite: int) -> None:
    tamanho = 0
    with open(destino, "wb") as saida:
        while True:
            pedaco = await arquivo.read(1024 * 1024)
            if not pedaco:
                break
            tamanho += len(pedaco)
            if tamanho > limite:
                raise erro(413, f"Arquivo maior que {limite // (1024 * 1024)} MB.",
                           ARQUIVO_GRANDE)
            saida.write(pedaco)


# ----------------------------------------------------------------------
# Catalogo, resumo e leitura

def _rotulos(mapa: dict) -> list[dict]:
    return [{"chave": k, "rotulo": v} for k, v in mapa.items()]


@router.get("/catalogo")
def catalogo(request: Request,
             usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    faixas = _executar(lambda s: s.faixas())
    ate = _desbloqueado_ate(request)
    return {
        "situacoes": _rotulos(cl.SITUACOES_CLIENTE),
        "situacoes_campo": _rotulos(cl.SITUACOES_CAMPO),
        "situacoes_senha": [{"chave": k, "rotulo": cl.SITUACOES_CAMPO[k]}
                            for k in cs.SITUACOES_SEGREDO],
        "campos_senha": _rotulos(cs.CAMPOS_SEGREDO),
        "licencas": _rotulos(pc.ROTULOS_LICENCA),
        "tipos_certificado": list(cs.TIPOS_CERTIFICADO),
        "situacoes_certificado": _rotulos(cs.SITUACOES_CERTIFICADO),
        "faixas": list(faixas),
        "cofre_disponivel": _cofre() is not None,
        "desbloqueado_ate": ate.isoformat() if ate else "",
        "desbloqueio_minutos": DESBLOQUEIO_MINUTOS,
    }


@router.get("/resumo")
def resumo(usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    def _consulta(s):
        return {**s.resumo(), "vencimentos": s.resumo_vencimentos(_hoje()),
                "municipios": s.municipios()}
    return _executar(_consulta)


@router.get("/avisos")
def avisos(usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    """O que o aviso do topo mostra ao entrar no sistema."""
    r = _executar(lambda s: s.resumo_vencimentos(_hoje()))
    return {"aviso": r["aviso"], "vencidos": r["contagem"].get(cl.FAIXA_VENCIDO, 0),
            "faixa_curta": r["faixa_curta"],
            "na_faixa_curta": r["contagem"].get(f"ate_{r['faixa_curta']}", 0)}


def _cliente_json(c: dict) -> dict:
    return {
        "id": c["id"], "nome": c["nome"],
        "documento": cl.formatar_documento(c["documento"] or ""),
        "documento_digitos": c["documento"] or "",
        "documento_informado": c.get("documento_informado", ""),
        "tipo_documento": cl.tipo_documento(c["documento"] or ""),
        "ie": c["ie"], "ie_situacao": c["ie_situacao"],
        "im": c["im"], "im_situacao": c["im_situacao"],
        "iptu": c["iptu"], "iptu_situacao": c["iptu_situacao"],
        "municipio": c["municipio"], "situacao": c["situacao"],
        "contato_nome": c.get("contato_nome", ""),
        "contato_email": c.get("contato_email", ""),
        "situacao_rotulo": cl.SITUACOES_CLIENTE.get(c["situacao"], ""),
        "pendencias": c.get("pendencias") or [],
        "certificado_fim": c.get("certificado_fim") or "",
        "revision": c["revision"],
    }


def _filtros(texto: str, situacao: str, municipio: str,
             com_pendencia: bool) -> dict:
    bruto = {"texto": texto, "situacao": situacao, "municipio": municipio,
             "com_pendencia": com_pendencia or None}
    return {k: v for k, v in bruto.items() if v}


@router.get("")
def listar(texto: str = "", situacao: str = "", municipio: str = "",
           com_pendencia: bool = False, pagina: int = 1, limite: int = 50,
           usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    dados = _executar(lambda s: s.listar(
        pagina=pagina, limite=limite,
        **_filtros(texto, situacao, municipio, com_pendencia)))
    return {**{k: dados[k] for k in ("total", "pagina", "limite", "paginas")},
            "itens": [_cliente_json(c) for c in dados["itens"]]}


def _certificado_json(k: dict, hoje: dt.date, faixas) -> dict:
    faixa, dias = cl.classificar_vencimento(k["fim"], hoje, faixas)
    return {
        "id": k["id"], "tipo": k["tipo"], "titular_nome": k["titular_nome"],
        "titular_documento": cl.formatar_documento(k["titular_documento"]),
        "emissor": k["emissor"], "inicio": k["inicio"], "fim": k["fim"],
        "serie": k["serie"], "local_guarda": k["local_guarda"],
        "origem": k["origem"], "coletado_em": k["coletado_em"],
        "situacao": k["situacao"],
        "situacao_rotulo": cs.SITUACOES_CERTIFICADO.get(k["situacao"], ""),
        "substituido_por_id": k["substituido_por_id"],
        "renovacao_em_andamento": bool(k["renovacao_em_andamento"]),
        "renovacao_por": k["renovacao_por_login"],
        "observacao": k["observacao"],
        "faixa": faixa if k["situacao"] == cs.CERT_VIGENTE else "",
        "faixa_rotulo": cl.rotulo_faixa(faixa) if k["situacao"] == cs.CERT_VIGENTE
        else "", "dias": dias,
    }


@router.get("/{cliente_id}")
def detalhar_cliente(cliente_id: int,
                     usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    def _consulta(s):
        return s.detalhar(cliente_id), s.faixas()
    d, faixas = _executar(_consulta)
    hoje = _hoje()
    return {
        **_cliente_json(d), "observacao": d["observacao"],
        "origem": d["origem"], "criado_em": d["criado_em"],
        "licencas": [{"tipo": t, "rotulo": pc.ROTULOS_LICENCA.get(t, t),
                      **{k: v for k, v in l.items() if k != "tipo"},
                      "situacao_rotulo": cl.SITUACOES_CAMPO.get(l["situacao"], "")}
                     for t, l in d["licencas"].items()],
        "senhas": [{**s, "rotulo": cs.CAMPOS_SEGREDO.get(s["campo"], s["campo"]),
                    "situacao_rotulo": cl.SITUACOES_CAMPO.get(s["situacao"], "")}
                   for s in d["segredos"]],
        "certificados": [_certificado_json(k, hoje, faixas)
                         for k in d["certificados"]],
        "alteracoes": d["alteracoes"],
    }


# ----------------------------------------------------------------------
# Cadastro

class ClienteEntrada(BaseModel):
    nome: str
    documento: str = ""
    ie: str = ""
    ie_situacao: str = ""
    im: str = ""
    im_situacao: str = ""
    iptu: str = ""
    iptu_situacao: str = ""
    municipio: str = ""
    observacao: str = ""
    contato_nome: str = ""
    contato_email: str = ""
    revision: int | None = None


class SituacaoEntrada(BaseModel):
    situacao: str
    motivo: str = ""


@router.post("")
def criar(entrada: ClienteEntrada, request: Request,
          usuario: Usuario = Depends(acesso("clientes.cadastrar"))) -> dict:
    cliente_id = _executar(lambda s: s.criar_cliente(
        entrada.model_dump(exclude={"revision"}), **_quem(usuario)))
    detalhar(request, f"cliente {cliente_id} criado")
    return {"id": cliente_id}


@router.put("/{cliente_id}")
def editar(cliente_id: int, entrada: ClienteEntrada, request: Request,
           usuario: Usuario = Depends(acesso("clientes.cadastrar"))) -> dict:
    r = _executar(lambda s: s.editar_cliente(
        cliente_id, entrada.model_dump(exclude={"revision"}),
        revision=entrada.revision, **_quem(usuario)))
    detalhar(request, f"cliente {cliente_id} editado")
    return r


@router.post("/{cliente_id}/situacao")
def mudar_situacao(cliente_id: int, entrada: SituacaoEntrada, request: Request,
                   usuario: Usuario = Depends(acesso("clientes.situacao"))) -> dict:
    r = _executar(lambda s: s.mudar_situacao(
        cliente_id, entrada.situacao, entrada.motivo, **_quem(usuario)))
    detalhar(request, f"cliente {cliente_id}: {entrada.situacao}")
    return r


# ----------------------------------------------------------------------
# Cofre

class DesbloqueioEntrada(BaseModel):
    senha: str


class SenhaEntrada(BaseModel):
    campo: str
    valor: str = ""
    situacao: str = ""
    portal: str = ""
    usuario_portal: str = ""
    segredo_id: int | None = None


@router.post("/cofre/desbloquear")
def desbloquear(entrada: DesbloqueioEntrada, request: Request,
                usuario: Usuario = Depends(acesso("cofre.desbloquear"))) -> dict:
    """Confirma a senha de quem esta logado e libera o cofre por 15 minutos.

    Senha errada responde 422, nunca 401: o 401 derrubaria a sessao inteira
    no navegador. Cinco erros em 15 minutos bloqueiam novas tentativas."""
    agora = _agora()
    janela = agora - dt.timedelta(minutes=DESBLOQUEIO_MINUTOS)
    with _trava:
        recentes = [t for t in _tentativas.get(usuario.id, []) if t > janela]
        _tentativas[usuario.id] = recentes
    if len(recentes) >= TENTATIVAS_DESBLOQUEIO:
        detalhar(request, "bloqueado por tentativas")
        raise erro(429, "Muitas tentativas. Espere 15 minutos.", MUITAS_TENTATIVAS)
    if not auth.conferir_senha(usuario.id, entrada.senha):
        with _trava:
            _tentativas.setdefault(usuario.id, []).append(agora)
        detalhar(request, "senha incorreta")
        raise erro(422, "Senha incorreta.", SENHA_INCORRETA)
    ate = agora + dt.timedelta(minutes=DESBLOQUEIO_MINUTOS)
    with _trava:
        _tentativas.pop(usuario.id, None)
        _desbloqueios[_chave_sessao(request)] = ate
    return {"desbloqueado_ate": ate.isoformat()}


@router.post("/cofre/bloquear")
def bloquear(request: Request,
             usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    with _trava:
        _desbloqueios.pop(_chave_sessao(request), None)
    return {"ok": True}


@router.post("/senhas/{segredo_id}/revelar")
def revelar(segredo_id: int, request: Request,
            usuario: Usuario = Depends(exigir_aba("clientes"))) -> JSONResponse:
    """Uma senha por vez. Sem `cofre.ver`, a tentativa fica nas DUAS trilhas:
    a de uso (middleware) e a do cofre (clientes.db)."""
    request.state.auditoria_acao = "cofre.revelar"
    request.state.auditoria_usuario = usuario
    if not permissoes.tem_permissao(usuario, "cofre.ver"):
        def _negar(s):
            try:
                alvo = s.segredo(segredo_id)
            except LookupError:
                alvo = {"cliente_id": None}
            s.registrar_negado(alvo["cliente_id"], segredo_id, ip=_ip(request),
                               **_quem(usuario))
        _executar(_negar)
        detalhar(request, f"senha {segredo_id}")
        raise erro(403, "Você não tem permissão para ver senhas de clientes.")
    if _desbloqueado_ate(request) is None:
        detalhar(request, f"senha {segredo_id}: cofre bloqueado")
        raise erro(428, "Confirme sua senha para abrir o cofre.", COFRE_BLOQUEADO)
    r = _executar(lambda s: s.revelar(segredo_id, ip=_ip(request),
                                      **_quem(usuario)), com_cofre=True)
    detalhar(request, f"cliente {r['cliente_id']} campo {r['campo']}")
    # Resposta com senha nao fica em cache de navegador nem de proxy.
    return JSONResponse(r, headers={"Cache-Control": "no-store",
                                    "Pragma": "no-cache"})


@router.put("/{cliente_id}/senhas")
def gravar_senha(cliente_id: int, entrada: SenhaEntrada, request: Request,
                 usuario: Usuario = Depends(acesso("cofre.gravar"))) -> dict:
    segredo_id = _executar(lambda s: s.gravar_segredo(
        cliente_id, entrada.campo, entrada.valor, situacao=entrada.situacao,
        portal=entrada.portal, usuario_portal=entrada.usuario_portal,
        segredo_id=entrada.segredo_id, **_quem(usuario)), com_cofre=True)
    detalhar(request, f"cliente {cliente_id} campo {entrada.campo}")
    return {"id": segredo_id}


@router.delete("/senhas/{segredo_id}")
def remover_senha(segredo_id: int, request: Request,
                  usuario: Usuario = Depends(acesso("cofre.gravar"))) -> dict:
    r = _executar(lambda s: s.remover_segredo(segredo_id, **_quem(usuario)))
    detalhar(request, f"cliente {r['cliente_id']} senha {segredo_id} removida")
    return r


@router.get("/cofre/acessos")
def acessos(usuario_filtro: str = "", cliente_id: int = 0, de: str = "",
            ate: str = "", pagina: int = 1, request: Request = None,
            usuario: Usuario = Depends(acesso("cofre.acessos"))) -> dict:
    r = _executar(lambda s: s.acessos(usuario=usuario_filtro,
                                      cliente_id=cliente_id, de=de, ate=ate,
                                      pagina=pagina))
    detalhar(request, f"filtros: usuario={usuario_filtro or '-'} "
                      f"cliente={cliente_id or '-'}")
    campos = cs.CAMPOS_SEGREDO
    return {**{k: r[k] for k in ("total", "pagina", "paginas")},
            "itens": [{"id": a["id"], "quando": a["criado_em"],
                       "usuario": a["usuario_login"], "ip": a["ip"],
                       "cliente_id": a["cliente_id"],
                       "cliente_nome": a["cliente_nome"] or "",
                       "campo": campos.get(a["campo"], a["campo"]),
                       "portal": a["portal"] or "", "acao": a["acao"],
                       "resultado": a["resultado"]} for a in r["itens"]]}


# ----------------------------------------------------------------------
# Certificados

class CertificadoEntrada(BaseModel):
    tipo: str = ""
    titular_nome: str = ""
    titular_documento: str = ""
    emissor: str = ""
    inicio: str = ""
    fim: str = ""
    serie: str = ""
    local_guarda: str = ""
    observacao: str = ""


class CertificadoEdicao(BaseModel):
    tipo: str | None = None
    local_guarda: str | None = None
    observacao: str | None = None
    situacao: str | None = None


class RenovacaoEntrada(BaseModel):
    em_andamento: bool


@router.post("/{cliente_id}/certificados")
def adicionar_certificado(cliente_id: int, entrada: CertificadoEntrada,
                          request: Request,
                          usuario: Usuario = Depends(
                              acesso("clientes.certificado"))) -> dict:
    cert_id = _executar(lambda s: s.adicionar_certificado(
        cliente_id, entrada.model_dump(), origem=cs.ORIGEM_MANUAL,
        **_quem(usuario)))
    detalhar(request, f"cliente {cliente_id} certificado {cert_id} (manual)")
    return {"id": cert_id}


@router.post("/{cliente_id}/certificados/arquivo")
async def certificado_por_arquivo(
        cliente_id: int, request: Request, arquivo: UploadFile = File(...),
        senha: str = Form(""), tipo: str = Form(""), local_guarda: str = Form(""),
        usuario: Usuario = Depends(acesso("clientes.certificado"))) -> dict:
    """Le validade e titular do .cer/.pfx enviado. O arquivo e a senha so
    passam pela memoria deste pedido: nada e' gravado alem dos dados lidos."""
    conteudo = await arquivo.read(ct.MAX_BYTES + 1)
    if len(conteudo) > ct.MAX_BYTES:
        raise erro(413, "Arquivo grande demais para ser um certificado.",
                   ARQUIVO_GRANDE)
    try:
        dados = ct.ler_certificado(conteudo, senha=senha or None)
    except ct.ErroCertificado as exc:
        raise _traduzir(exc) from exc
    registro = {**dados.como_dict(),
                "tipo": tipo or dados.tipo, "local_guarda": local_guarda}
    cert_id = _executar(lambda s: s.adicionar_certificado(
        cliente_id, registro, origem=cs.ORIGEM_ARQUIVO, **_quem(usuario)))
    detalhar(request, f"cliente {cliente_id} certificado {cert_id} (arquivo)")
    return {"id": cert_id, "fim": dados.fim.isoformat(),
            "titular_nome": dados.titular_nome,
            "titular_documento": cl.formatar_documento(dados.titular_documento)}


@router.put("/certificados/{cert_id}")
def editar_certificado(cert_id: int, entrada: CertificadoEdicao,
                       request: Request,
                       usuario: Usuario = Depends(
                           acesso("clientes.certificado"))) -> dict:
    mudancas = {k: v for k, v in entrada.model_dump().items() if v is not None}
    r = _executar(lambda s: s.editar_certificado(cert_id, mudancas,
                                                 **_quem(usuario)))
    detalhar(request, f"certificado {cert_id}: {', '.join(mudancas) or 'nada'}")
    return r


@router.post("/certificados/{cert_id}/renovacao")
def renovacao(cert_id: int, entrada: RenovacaoEntrada, request: Request,
              usuario: Usuario = Depends(acesso("clientes.certificado"))) -> dict:
    r = _executar(lambda s: s.marcar_renovacao(cert_id, entrada.em_andamento,
                                               **_quem(usuario)))
    detalhar(request, f"certificado {cert_id}: renovação "
                      f"{'em andamento' if entrada.em_andamento else 'desmarcada'}")
    return r


# ----------------------------------------------------------------------
# Vencimentos

class FaixasEntrada(BaseModel):
    faixas: list[int]


@router.get("/vencimentos/lista")
def vencimentos(faixa: str = "", texto: str = "",
                usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    hoje = _hoje()

    def _consulta(s):
        return s.vencimentos(hoje, faixa=faixa or None, texto=texto), s.faixas()
    itens, faixas = _executar(_consulta)
    return {"hoje": hoje.isoformat(), "faixas": list(faixas),
            "itens": [{**_certificado_json(k, hoje, faixas),
                       "cliente_id": k["cliente_id"],
                       "cliente_nome": k["cliente_nome"],
                       "cliente_documento": cl.formatar_documento(
                           k["cliente_documento"] or "")} for k in itens]}


@router.put("/vencimentos/faixas")
def definir_faixas(entrada: FaixasEntrada, request: Request,
                   usuario: Usuario = Depends(
                       acesso("vencimentos.configurar"))) -> dict:
    faixas = _executar(lambda s: s.definir_faixas(entrada.faixas,
                                                  **_quem(usuario)))
    detalhar(request, f"faixas: {list(faixas)}")
    return {"faixas": list(faixas)}


# ----------------------------------------------------------------------
# Importacao com previa

@router.post("/base-fiscal/previa")
async def previa_base_fiscal(request: Request, arquivo: UploadFile = File(...),
                             usuario: Usuario = Depends(
                                 acesso("clientes.importar"))) -> JSONResponse:
    """Conferencia da fonte, sem abrir store ou preparar uma confirmacao."""
    nome = (arquivo.filename or "base-fiscal.xlsx").replace("\\", "/").rsplit("/", 1)[-1]
    try:
        if os.path.splitext(nome)[1].lower() != ".xlsx":
            raise erro(422, "Envie a base Fiscal em uma planilha .xlsx.", pc.PLANILHA_INVALIDA)
        with tempfile.TemporaryDirectory(prefix="base_fiscal_previa_") as pasta:
            destino = os.path.join(pasta, "base-fiscal.xlsx")
            await _receber(arquivo, destino, pe.MAX_PLANILHA_BYTES)
            try:
                dados = pe.ler_planilha_empresas(destino).resumo()
            except cl.ErroClientes as exc:
                raise _traduzir(exc) from exc
    finally:
        await arquivo.close()
    detalhar(request, f"previa base fiscal: {dados['contagens']['linhas']} linha(s)")
    return JSONResponse(dict(dados, somente_leitura=True, nome_arquivo=nome[:200]),
                        headers={"Cache-Control": "no-store"})


@router.post("/base-fiscal/relatorio")
async def relatorio_base_fiscal(
        request: Request, arquivo: UploadFile = File(...),
        hash_esperado: str = Form(..., min_length=64, max_length=64,
                                 pattern=r"^[0-9a-f]{64}$"),
        usuario: Usuario = Depends(acesso("clientes.exportar"))) -> Response:
    """Rele a fonte conferida; nao recebe linhas do navegador nem abre o cadastro."""
    try:
        trilha.exigir_permissao(usuario, "clientes.importar",
                               "Você não tem permissão para conferir a base Fiscal.")
        nome = (arquivo.filename or "base-fiscal.xlsx").replace("\\", "/").rsplit("/", 1)[-1]
        if os.path.splitext(nome)[1].lower() != ".xlsx":
            raise erro(422, "Envie a base Fiscal em uma planilha .xlsx.", pc.PLANILHA_INVALIDA)
        with tempfile.TemporaryDirectory(prefix="base_fiscal_relatorio_") as pasta:
            destino = os.path.join(pasta, "base-fiscal.xlsx")
            await _receber(arquivo, destino, pe.MAX_PLANILHA_BYTES)
            try:
                leitura = await run_in_threadpool(pe.ler_planilha_empresas, destino)
                if leitura.hash_arquivo != hash_esperado:
                    raise erro(409, "O arquivo difere da prévia. Confira a base Fiscal novamente.",
                               "BASE_FISCAL_DIVERGENTE")
                conteudo = await run_in_threadpool(
                    gerar_relatorio_base_fiscal, leitura, nome_arquivo=nome[:200])
            except cl.ErroClientes as exc:
                raise _traduzir(exc) from exc
    finally:
        await arquivo.close()
    detalhar(request, f"relatorio base fiscal: {len(leitura.linhas)} linha(s)")
    return Response(conteudo, media_type=MIME_XLSX, headers={
        "Cache-Control": "no-store",
        "Content-Disposition": 'attachment; filename="conferencia-base-fiscal.xlsx"',
    })


class ConfirmacaoEntrada(BaseModel):
    decisoes: dict[str, str] = {}


def _aad_previa(previa_aad: str, linha: int, campo: str) -> str:
    return f"previa:{previa_aad}:{linha}:{campo}"


@router.post("/importar/planilha")
async def previa_planilha(request: Request, arquivo: UploadFile = File(...),
                          usuario: Usuario = Depends(
                              acesso("clientes.importar"))) -> dict:
    pasta = tempfile.mkdtemp(prefix="clientes_upload_")
    destino = os.path.join(pasta, "clientes.xlsx")
    try:
        await _receber(arquivo, destino, pc.MAX_PLANILHA_BYTES)
        try:
            leitura = pc.ler_planilha_clientes(destino)
        except cl.ErroClientes as exc:
            raise _traduzir(exc) from exc
    finally:
        # O arquivo enviado (com as senhas em texto) sai do disco ja aqui,
        # com sucesso ou com erro.
        shutil.rmtree(pasta, ignore_errors=True)

    previa = Previa(tipo="planilha", usuario_id=usuario.id, criada=_agora(),
                    nome_arquivo=(arquivo.filename or "clientes.xlsx")[:200],
                    hash_arquivo=leitura.hash_arquivo, dados=leitura,
                    aad=secrets.token_hex(8))
    tem_senha = any(l.segredos for l in leitura.linhas)
    cofre = _cofre()
    if tem_senha and cofre is None:
        raise erro(503, "A planilha tem senhas e o cofre está desligado (falta a "
                        "chave no servidor). Nada foi importado.",
                   COFRE_INDISPONIVEL)
    for linha in leitura.linhas:
        if linha.segredos:
            previa.segredos[linha.linha] = {
                campo: (cofre.cifrar(valor, _aad_previa(previa.aad, linha.linha,
                                                        campo)) if valor else None,
                        situacao)
                for campo, (valor, situacao) in linha.segredos.items()}
            # A previa guarda so a cifra: o texto some do objeto em memoria.
            linha.segredos = {campo: ("", situacao) for campo, (_, situacao)
                              in linha.segredos.items()}
    token = _guardar_previa(previa)
    situacoes = _executar(lambda s: s.situacao_importacao(leitura))
    resumo_dados = leitura.resumo()
    for item in resumo_dados["linhas"]:
        item["resultado"] = situacoes.get(item["linha"], "ignorar")
        cifras = previa.segredos.get(item["linha"], {})
        item["segredos"] = {campo: ("presente" if cifra else situacao)
                            for campo, (cifra, situacao) in cifras.items()}
    detalhar(request, f"previa planilha: {resumo_dados['contagens']['total']} "
                      "linha(s)")
    return {"token": token, "nome_arquivo": previa.nome_arquivo,
            "expira_em_minutos": PREVIA_MINUTOS, **resumo_dados}


def _decisoes(entrada: ConfirmacaoEntrada) -> dict[int, str]:
    decisoes = {}
    for linha, acao in entrada.decisoes.items():
        if not str(linha).isdigit():
            raise erro(422, f"Linha inválida: {linha}.", cs.DECISAO_INVALIDA)
        decisoes[int(linha)] = acao
    return decisoes


@router.post("/importar/planilha/{token}/confirmar")
def confirmar_planilha(token: str, entrada: ConfirmacaoEntrada, request: Request,
                       usuario: Usuario = Depends(
                           acesso("clientes.importar"))) -> dict:
    previa = _obter_previa(token, usuario, "planilha")
    decisoes = _decisoes(entrada)
    segredos = {}
    if previa.segredos:
        cofre = _cofre()
        if cofre is None:
            raise erro(503, "O cofre está desligado: falta a chave no servidor.",
                       COFRE_INDISPONIVEL)
        try:
            segredos = {
                linha: {campo: (cofre.decifrar(cifra, _aad_previa(
                    previa.aad, linha, campo)) if cifra else "", situacao)
                    for campo, (cifra, situacao) in campos.items()}
                for linha, campos in previa.segredos.items()}
        except SegredoIlegivel as exc:
            raise erro(409, "A chave do cofre mudou desde a prévia. Envie o "
                            "arquivo de novo.", SEGREDO_ILEGIVEL) from exc
    r = _executar(lambda s: s.importar_planilha(
        previa.dados, decisoes=decisoes, nome_arquivo=previa.nome_arquivo,
        segredos=segredos, **_quem(usuario)), com_cofre=bool(segredos))
    segredos.clear()
    _descartar_previa(token)
    detalhar(request, f"planilha: {r['criados']} novo(s), {r['atualizados']} "
                      f"atualizado(s), {r['ignorados']} ignorado(s)")
    return r


@router.post("/importar/coleta")
async def previa_coleta(request: Request, arquivo: UploadFile = File(...),
                        usuario: Usuario = Depends(
                            acesso("clientes.importar"))) -> dict:
    conteudo = await arquivo.read(MAX_COLETA_BYTES + 1)
    if len(conteudo) > MAX_COLETA_BYTES:
        raise erro(413, "Arquivo de coleta grande demais.", ARQUIVO_GRANDE)
    try:
        coleta = json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise erro(422, "O arquivo não é uma coleta válida (JSON).",
                   cs.COLETA_INVALIDA) from exc
    itens = _executar(lambda s: s.previa_coleta(coleta))
    previa = Previa(tipo="coleta", usuario_id=usuario.id, criada=_agora(),
                    nome_arquivo=(arquivo.filename or "coleta.json")[:200],
                    hash_arquivo=hashlib.sha256(conteudo).hexdigest(),
                    dados=coleta)
    token = _guardar_previa(previa)
    contagem: dict[str, int] = {}
    for item in itens:
        contagem[item["resultado"]] = contagem.get(item["resultado"], 0) + 1
    detalhar(request, f"previa coleta: {len(itens)} certificado(s)")
    return {"token": token, "nome_arquivo": previa.nome_arquivo,
            "gerada_em": str(coleta.get("gerada_em") or ""),
            "expira_em_minutos": PREVIA_MINUTOS, "contagens": contagem,
            "itens": [{**i, "titular_documento": cl.formatar_documento(
                i["titular_documento"])} for i in itens]}


@router.post("/importar/coleta/{token}/confirmar")
def confirmar_coleta(token: str, request: Request,
                     usuario: Usuario = Depends(
                         acesso("clientes.importar"))) -> dict:
    previa = _obter_previa(token, usuario, "coleta")
    r = _executar(lambda s: s.importar_coleta(
        previa.dados, nome_arquivo=previa.nome_arquivo,
        hash_arquivo=previa.hash_arquivo, **_quem(usuario)))
    _descartar_previa(token)
    detalhar(request, f"coleta: {r['novos']} novo(s), {r['atualizados']} "
                      f"atualizado(s), {r['sem_cliente']} sem cliente")
    return r


@router.delete("/importar/{token}")
def descartar(token: str,
              usuario: Usuario = Depends(exigir_aba("clientes"))) -> dict:
    with _trava:
        previa = _previas.get(token)
        if previa is not None and previa.usuario_id == usuario.id:
            _previas.pop(token, None)
    return {"ok": True}


# ----------------------------------------------------------------------
# Exportacao

@router.post("/exportar")
def exportar(texto: str = "", situacao: str = "", municipio: str = "",
             com_pendencia: bool = False, request: Request = None,
             usuario: Usuario = Depends(acesso("clientes.exportar"))):
    filtros = _filtros(texto, situacao, municipio, com_pendencia)
    hoje = _hoje()

    def _consulta(s):
        pagina = s.listar(limite=200, pagina=1, **filtros)
        itens = list(pagina["itens"])
        for numero in range(2, pagina["paginas"] + 1):
            itens += s.listar(limite=200, pagina=numero, **filtros)["itens"]
        return itens, s.senhas_presentes(), s.vencimentos(hoje)

    clientes, presentes, certs = _executar(_consulta)
    ids = {c["id"] for c in clientes}
    pasta = tempfile.mkdtemp(prefix="clientes_saida_")
    nome = f"clientes_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    destino = os.path.join(pasta, nome)
    try:
        gerar_relacao(destino, clientes=clientes, senhas_presentes=presentes,
                      certificados=[k for k in certs if k["cliente_id"] in ids],
                      gerado_por=usuario.usuario, filtros=filtros)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    detalhar(request, f"{len(clientes)} cliente(s); filtros: {filtros or 'nenhum'}")
    return FileResponse(destino, media_type=MIME_XLSX, filename=nome,
                        background=BackgroundTask(
                            lambda: shutil.rmtree(pasta, ignore_errors=True)))
