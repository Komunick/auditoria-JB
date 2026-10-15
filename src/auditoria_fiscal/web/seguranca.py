"""Defesas de borda do site: Host, Origin, cabecalhos da API e IP do cliente.

Portado do clone do Cadastro JB (auditoria de 23/08/2026, WEB-01 e AUD-01),
que nunca chegou ao Git. A producao (intra.jbfraga.com.br, Caddy -> uvicorn)
aceitava mutacao de qualquer origem, respondia a qualquer Host, servia a API
sem nosniff/CSP e gravava na trilha o X-Forwarded-For que o cliente quisesse.
Concentrar isso aqui evita que cada rota precise lembrar das defesas.

Middleware ASGI puro (nao BaseHTTPMiddleware): nao toca no corpo, entao
uploads grandes e downloads passam direto. Nada aqui abre CORS.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import config

# JSON, CSV e planilhas nunca sao documento: nada carrega, nada emoldura.
CSP_API = ("default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
           "form-action 'none'")

# PDF servido inline (o DANFE abre numa janela e o navegador EXIBE): no
# Chrome o leitor de PDF e um plugin sujeito ao object-src, e
# default-src 'none' o bloquearia. Fica so o que nao interfere no leitor.
CSP_PDF = "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

METODOS_QUE_MUDAM = {"POST", "PUT", "PATCH", "DELETE"}

# A propria maquina sempre passa na lista de Hosts: o `ctl.sh status` e o
# acesso local usam esses nomes, e DNS rebinding nunca chega com eles (o
# navegador manda o nome do atacante no Host).
_HOSTS_LOCAIS = {"localhost", "127.0.0.1", "[::1]"}


def csp_da_api(tipo_conteudo: str) -> str:
    """CSP de uma resposta de /api/** conforme o Content-Type."""
    tipo = (tipo_conteudo or "").split(";")[0].strip().lower()
    return CSP_PDF if tipo == "application/pdf" else CSP_API


class SegurancaMiddleware:
    """Recusa Host fora da lista e mutacao de outra origem; carimba nosniff e
    CSP em toda resposta da API."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive,
                       send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        motivo = _motivo_da_recusa(request)
        if motivo:
            print(f"AVISO - requisicao recusada ({motivo}): "
                  f"{request.method} {scope.get('path', '')[:80]} "
                  f"host={request.headers.get('host', '')[:80]!r} "
                  f"origin={request.headers.get('origin', '')[:80]!r} "
                  f"ip={ip_do_cliente(request) or '?'}")
            resposta = JSONResponse(status_code=400,
                                    content={"detail": _MENSAGENS[motivo]})
            await resposta(scope, receive, _carimbando(send, api=True))
            return

        api = scope.get("path", "").startswith("/api/")
        await self.app(scope, receive, _carimbando(send, api=api))


_MENSAGENS = {
    "host": "Endereco (Host) nao reconhecido por este servidor.",
    "origem": "Origem da requisicao nao reconhecida. Recarregue a pagina e "
              "tente de novo.",
}


def _carimbando(send: Send, *, api: bool) -> Send:
    """Envolve o `send` para acrescentar os cabecalhos na resposta da API.

    O webui (arquivos estaticos) fica como estava: no Windows o mimetypes do
    Python le o registro e pode servir .js como text/plain, e com nosniff o
    navegador recusaria o script."""
    if not api:
        return send

    async def enviar(mensagem: Message) -> None:
        if mensagem["type"] == "http.response.start":
            cabecalhos = MutableHeaders(scope=mensagem)
            cabecalhos["X-Content-Type-Options"] = "nosniff"
            if "content-security-policy" not in cabecalhos:
                cabecalhos["Content-Security-Policy"] = csp_da_api(
                    cabecalhos.get("content-type", ""))
        await send(mensagem)

    return enviar


def _motivo_da_recusa(request: Request) -> str:
    if _host_recusado(request):
        return "host"
    if request.method in METODOS_QUE_MUDAM and _origem_recusada(request):
        return "origem"
    return ""


# ----------------------------------------------------------------------
# Host (DNS rebinding)


def _nome_do_host(valor: str) -> str:
    """Nome sem porta, minusculo ('[::1]' para IPv6). Invalido = ''."""
    try:
        nome = urlsplit("//" + (valor or "").strip()).hostname or ""
    except ValueError:
        return ""
    nome = nome.rstrip(".")
    return f"[{nome}]" if ":" in nome else nome


def _endereco(netloc: str, portas_padrao: set[int]) -> str:
    """'nome[:porta]' normalizado; a porta some quando e a padrao."""
    try:
        partes = urlsplit("//" + (netloc or "").strip())
        porta = partes.port
    except ValueError:
        return ""
    nome = _nome_do_host(netloc)
    if not nome:
        return ""
    return nome if porta is None or porta in portas_padrao else f"{nome}:{porta}"


def _host_recusado(request: Request) -> bool:
    """Com AUDITORIA_HOSTS_CONFIAVEIS definido, so os nomes da lista (e a
    propria maquina) sao atendidos. Sem ela, qualquer Host passa — a LAN
    acessa por IP ou pelo nome do servidor."""
    permitidos = config.hosts_confiaveis()
    host = request.headers.get("host", "")
    if not permitidos or not host:
        return False
    aceitos = {_nome_do_host(h) for h in permitidos} | _HOSTS_LOCAIS
    nome = _nome_do_host(host)
    return not nome or nome not in aceitos


# ----------------------------------------------------------------------
# Origin (CSRF)


def _enderecos_da_requisicao(request: Request) -> set[str]:
    """Para onde o navegador mandou a requisicao: o Host, ou o
    X-Forwarded-Host quando um proxy declarado reescreveu o Host."""
    enderecos = {_endereco(request.headers.get("host", ""), {80, 443})}
    if _veio_de_proxy_confiavel(request):
        encaminhado = request.headers.get("x-forwarded-host", "")
        if encaminhado:
            enderecos.add(_endereco(encaminhado.split(",")[0], {80, 443}))
    enderecos.discard("")
    return enderecos


def _origem_aceita(origem: str, request: Request) -> bool:
    origem = origem.strip().rstrip("/").lower()
    if not origem or origem == "null":
        return False
    if origem in {o.lower() for o in config.origens_confiaveis()}:
        return True
    try:
        partes = urlsplit(origem)
    except ValueError:
        return False
    if partes.scheme not in ("http", "https") or not partes.netloc:
        return False
    padrao = {443} if partes.scheme == "https" else {80}
    return _endereco(partes.netloc, padrao) in _enderecos_da_requisicao(request)


def _origem_recusada(request: Request) -> bool:
    """Defesa CSRF das mutacoes: quem manda tem de ser o proprio site.

    Ordem: Origin (todo navegador atual manda em POST/PUT/PATCH/DELETE,
    inclusive na mesma origem) -> Sec-Fetch-Site (nao falsificavel por pagina
    de terceiro) -> Referer. Sem nenhum dos tres e um cliente que nao e
    navegador (curl, script interno), que nao carrega o cookie de ninguem;
    ali o que protege e o SameSite do cookie."""
    origem = request.headers.get("origin")
    if origem is not None and origem.strip():
        return not _origem_aceita(origem, request)

    sec_fetch = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if sec_fetch in {"cross-site", "same-site"}:
        # same-site = subdominio vizinho (ex.: o site publico da JB): o
        # cookie SameSite iria junto, entao tambem nao serve.
        return True
    if sec_fetch in {"same-origin", "none"}:
        return False

    referer = (request.headers.get("referer") or "").strip()
    if not referer:
        return False
    try:
        partes = urlsplit(referer)
    except ValueError:
        return True
    if not partes.scheme or not partes.netloc:
        return True
    return not _origem_aceita(f"{partes.scheme}://{partes.netloc}", request)


# ----------------------------------------------------------------------
# IP do cliente e HTTPS atras de proxy (AUD-01)


def _ip_valido(valor: str) -> str:
    """O IP normalizado, ou '' se nao for IP (nunca texto arbitrario).
    Aceita porta grudada ('1.2.3.4:80', '[2001:db8::1]:443')."""
    valor = (valor or "").strip()
    if valor.startswith("[") and "]" in valor:
        valor = valor[1:valor.index("]")]
    elif valor.count(":") == 1:
        valor = valor.split(":")[0]
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return ""


def _redes_confiaveis() -> list:
    redes = []
    for item in config.proxies_confiaveis():
        try:
            redes.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return redes


def _na_lista(ip: str, redes: list) -> bool:
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(endereco in rede for rede in redes
               if rede.version == endereco.version)


def _peer(request: Request) -> str:
    return _ip_valido(request.client.host if request.client else "")


def _veio_de_proxy_confiavel(request: Request) -> bool:
    peer = _peer(request)
    return bool(peer) and _na_lista(peer, _redes_confiaveis())


def ip_do_cliente(request: Request) -> str:
    """IP de quem fez a requisicao, para a trilha e o limite de login.

    X-Forwarded-For so vale quando a conexao vem de um proxy declarado em
    AUDITORIA_PROXIES_CONFIAVEIS; fora disso o valor e escolhido pelo
    cliente — dava para forjar a trilha, escapar do limite de login e, pelo
    CSV do historico, injetar formula na planilha.

    A cadeia e lida da DIREITA para a esquerda: cada proxy acrescenta o IP de
    quem falou com ele, entao o primeiro IP que nao e de proxy declarado e o
    cliente. O que estiver mais a esquerda pode ter sido escrito pelo proprio
    cliente. Observacao: o uvicorn ja troca o peer pelo X-Forwarded-For quando
    a conexao vem de 127.0.0.1 (FORWARDED_ALLOW_IPS), e nesse caso o peer que
    chega aqui ja e o cliente."""
    peer = _peer(request)
    redes = _redes_confiaveis()
    if not peer or not redes or not _na_lista(peer, redes):
        return peer

    cadeia = [p.strip() for p in
              (request.headers.get("x-forwarded-for") or "").split(",")
              if p.strip()]
    for candidato in reversed(cadeia):
        ip = _ip_valido(candidato)
        if not ip:
            return peer        # lixo: nada a esquerda dele e confiavel
        if not _na_lista(ip, redes):
            return ip
    # Cadeia vazia, ou so proxies declarados: o cliente e interno.
    return (_ip_valido(cadeia[0]) if cadeia else "") or peer


def requisicao_https(request: Request) -> bool:
    """A requisicao chegou por HTTPS — direto ou num proxy declarado que
    terminou o TLS e avisou por X-Forwarded-Proto."""
    if request.scope.get("scheme") == "https":
        return True
    if not _veio_de_proxy_confiavel(request):
        return False
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0]
    return proto.strip().lower() == "https"


def cookie_seguro(request: Request) -> bool:
    """Secure no cookie de sessao: HTTPS detectado ou forcado pelo operador.
    Em HTTP puro (LAN) fica sem, senao o navegador descartaria o cookie."""
    return config.cookies_seguros_forcados() or requisicao_https(request)
