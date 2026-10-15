"""Versao web — endurecimento de seguranca para expor o site fora da LAN.

A producao (intra.jbfraga.com.br, Caddy -> uvicorn) rodava sem as defesas que
a constituicao exige para exposicao externa: cookie sem Secure, mutacao
aceita de qualquer Origin/Host, login sem limite de tentativas,
X-Forwarded-For acreditado de qualquer cliente e API sem nosniff/CSP. Este
teste cobre as cinco frentes:

* cabecalhos: toda resposta de /api/** sai com nosniff e CSP (PDF inline com
  uma CSP que nao bloqueia o leitor do navegador); o webui nao muda;
* Host: com AUDITORIA_HOSTS_CONFIAVEIS definido, Host fora da lista e recusado
  (loopback sempre passa); sem a variavel, nada muda;
* Origin: POST/PUT/PATCH/DELETE vindos de outra origem sao recusados antes da
  rota (Origin, Sec-Fetch-Site e Referer); cliente sem nenhum deles passa;
* cookie: Secure quando a requisicao chegou por HTTPS (direto ou por proxy
  confiavel) ou com AUDITORIA_COOKIES_SEGUROS=1; sempre HttpOnly e SameSite;
* IP: X-Forwarded-For so vale vindo de AUDITORIA_PROXIES_CONFIAVEIS, e so
  IP valido chega a trilha;
* login: 8 falhas no mesmo IP bloqueiam aquele IP (429 + Retry-After), sem
  trancar a conta para quem esta em outro lugar; o bloqueio sobrevive a
  reinicio e vence sozinho.

Usa dados_web isolado em pasta temporaria (AUDITORIA_WEB_DADOS).
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_seg_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP
for _var in ("AUDITORIA_HOSTS_CONFIAVEIS", "AUDITORIA_ORIGENS_CONFIAVEIS",
             "AUDITORIA_PROXIES_CONFIAVEIS", "AUDITORIA_COOKIES_SEGUROS"):
    os.environ.pop(_var, None)

from fastapi.testclient import TestClient  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import Response  # noqa: E402
from starlette.routing import Route  # noqa: E402

from auditoria_fiscal.web import auth, seguranca  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402

SENHA_ADM = "senha-do-admin"
SENHA_ANA = "senha-da-ana"
ORIGEM_MA = "https://site-malicioso.example"


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


class ambiente:
    """Define variaveis de ambiente so dentro do bloco (a config e lida a
    cada requisicao, entao nao precisa recriar o app)."""

    def __init__(self, **valores: str) -> None:
        self.valores = valores
        self.antes: dict[str, str | None] = {}

    def __enter__(self):
        for nome, valor in self.valores.items():
            self.antes[nome] = os.environ.get(nome)
            os.environ[nome] = valor
        return self

    def __exit__(self, *_):
        for nome, valor in self.antes.items():
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor


def atributos_cookie(resposta) -> set[str]:
    """Atributos do Set-Cookie da sessao, em minusculas ('secure',
    'httponly', 'samesite=lax'...)."""
    bruto = resposta.headers.get("set-cookie", "")
    checar(bruto.startswith(auth.COOKIE_SESSAO + "="),
           f"esperava o cookie de sessao, veio: {bruto[:80]!r}")
    return {parte.strip().lower() for parte in bruto.split(";")[1:]}


def login(cliente, usuario="ana", senha=SENHA_ANA, **kwargs):
    return cliente.post("/api/login", json={"usuario": usuario,
                                            "senha": senha}, **kwargs)


def eventos(adm, acao: str) -> list[dict]:
    r = adm.get("/api/admin/historico", params={"acao": acao, "limite": 500})
    checar(r.status_code == 200, f"historico: {r.status_code} {r.text[:120]}")
    return r.json()["itens"]


def requisicao(peer: str | None, xff: str | None = None,
               extras: dict[str, str] | None = None,
               scheme: str = "http") -> Request:
    cabecalhos = []
    if xff is not None:
        cabecalhos.append((b"x-forwarded-for", xff.encode("latin-1")))
    for nome, valor in (extras or {}).items():
        cabecalhos.append((nome.encode("latin-1"), valor.encode("latin-1")))
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": cabecalhos, "scheme": scheme,
        "server": ("testserver", 80),
        "client": (peer, 50000) if peer is not None else None})


# ----------------------------------------------------------------------


def cabecalhos_da_api(app) -> None:
    anon = TestClient(app)
    respostas = {
        "estado (200)": anon.get("/api/estado"),
        "sem login (401)": anon.get("/api/admin/usuarios"),
        "rota inexistente": anon.get("/api/nao-existe"),
        "login negado (401)": login(anon, senha="errada"),
    }
    for rotulo, r in respostas.items():
        checar(r.headers.get("x-content-type-options") == "nosniff",
               f"{rotulo}: faltou nosniff ({dict(r.headers)})")
        csp = r.headers.get("content-security-policy", "")
        checar("default-src 'none'" in csp and "frame-ancestors 'none'" in csp,
               f"{rotulo}: CSP da API ausente ou fraca: {csp!r}")

    # O webui NAO recebe a CSP da API: ela bloquearia o proprio front.
    r = anon.get("/")
    checar(r.status_code == 200, f"webui deveria abrir: {r.status_code}")
    checar("default-src 'none'"
           not in r.headers.get("content-security-policy", ""),
           "a CSP estrita da API nao pode ir para o webui")

    # PDF inline (DANFE abre numa janela): default-src/object-src 'none'
    # derrubariam o leitor de PDF do Chrome, entao a politica e outra.
    def pdf(_request):
        return Response(b"%PDF-1.4\n", media_type="application/pdf")

    def json_(_request):
        return Response(b"{}", media_type="application/json")

    mini = Starlette(routes=[Route("/api/doc.pdf", pdf),
                             Route("/api/dado", json_)],
                     middleware=[Middleware(seguranca.SegurancaMiddleware)])
    cliente = TestClient(mini)
    r = cliente.get("/api/doc.pdf")
    csp = r.headers.get("content-security-policy", "")
    checar(r.headers.get("x-content-type-options") == "nosniff",
           "PDF da API tambem leva nosniff")
    checar(csp and "default-src" not in csp and "object-src" not in csp,
           f"CSP do PDF nao pode bloquear o leitor: {csp!r}")
    checar("frame-ancestors 'none'" in csp,
           f"PDF continua proibido de ser emoldurado: {csp!r}")
    checar("default-src 'none'"
           in cliente.get("/api/dado").headers.get("content-security-policy",
                                                    ""),
           "JSON no mesmo app volta a CSP estrita")


def host_confiavel(app) -> None:
    anon = TestClient(app)
    # Sem a variavel: comportamento atual (a LAN acessa por IP ou nome).
    r = anon.get("/api/estado", headers={"host": "nome-qualquer.lan"})
    checar(r.status_code == 200,
           f"sem AUDITORIA_HOSTS_CONFIAVEIS nada muda: {r.status_code}")

    with ambiente(AUDITORIA_HOSTS_CONFIAVEIS="intra.exemplo.com.br"):
        for host in ("intra.exemplo.com.br", "INTRA.Exemplo.com.br:443",
                     "localhost:8600", "127.0.0.1", "[::1]:8600"):
            r = anon.get("/api/estado", headers={"host": host})
            checar(r.status_code == 200,
                   f"Host {host!r} deveria passar: {r.status_code} {r.text}")
        for host in ("site-malicioso.example",
                     "intra.exemplo.com.br.site-malicioso.example",
                     "testserver"):
            r = anon.get("/api/estado", headers={"host": host})
            checar(r.status_code == 400,
                   f"Host {host!r} deveria ser recusado: {r.status_code}")
            checar(r.headers.get("x-content-type-options") == "nosniff",
                   "a recusa tambem leva os cabecalhos")
        # Vale para o site inteiro (DNS rebinding le a pagina tambem).
        r = anon.get("/", headers={"host": "site-malicioso.example"})
        checar(r.status_code == 400, f"webui com Host estranho: {r.status_code}")
        r = login(anon, headers={"host": "site-malicioso.example"})
        checar(r.status_code == 400, f"login com Host estranho: {r.status_code}")


def origem_nas_mutacoes(app, adm) -> None:
    anon = TestClient(app)
    recusadas = {
        "Origin de outro site": {"origin": ORIGEM_MA},
        "Origin null (iframe sandbox)": {"origin": "null"},
        "Origin com outra porta": {"origin": "http://testserver:9999"},
        "Sec-Fetch-Site cross-site": {"sec-fetch-site": "cross-site"},
        "Sec-Fetch-Site same-site (subdominio vizinho)":
            {"sec-fetch-site": "same-site"},
        "Referer de outro site": {"referer": ORIGEM_MA + "/pagina"},
    }
    for rotulo, cabecalhos in recusadas.items():
        r = login(anon, headers=cabecalhos)
        checar(r.status_code == 400,
               f"{rotulo}: deveria ser 400, veio {r.status_code} {r.text}")
        checar("origem" in r.json()["detail"].lower(),
               f"{rotulo}: a mensagem deveria explicar: {r.text}")

    # 401 = passou pela borda e chegou a rota (a senha e que esta errada).
    aceitas = {
        "mesma origem": {"origin": "http://testserver"},
        "Sec-Fetch-Site same-origin": {"sec-fetch-site": "same-origin"},
        "Referer da propria pagina": {"referer": "http://testserver/"},
        "sem Origin/Referer (curl, script interno)": {},
    }
    for rotulo, cabecalhos in aceitas.items():
        r = login(anon, senha="errada", headers=cabecalhos)
        checar(r.status_code == 401,
               f"{rotulo}: deveria chegar a rota, veio {r.status_code} {r.text}")

    # Leitura nao muda estado: GET de outra origem segue respondendo.
    r = anon.get("/api/estado", headers={"origin": ORIGEM_MA})
    checar(r.status_code == 200, f"GET nao e mutacao: {r.status_code}")

    # Logado: a mutacao forjada nao chega a rota (nem cria nem apaga nada).
    r = adm.post("/api/sessoes", json={"ferramenta": "conferencia"},
                 headers={"origin": ORIGEM_MA})
    checar(r.status_code == 400, f"POST forjado: {r.status_code}")
    sessao = adm.post("/api/sessoes", json={"ferramenta": "conferencia"},
                      headers={"origin": "http://testserver"}).json()["sessao_id"]
    r = adm.delete(f"/api/sessoes/{sessao}", headers={"origin": ORIGEM_MA})
    checar(r.status_code == 400, f"DELETE forjado: {r.status_code}")
    r = adm.delete(f"/api/sessoes/{sessao}")
    checar(r.status_code == 200,
           f"a sessao deveria continuar la depois do DELETE forjado: "
           f"{r.status_code} {r.text}")

    # Origem extra declarada pelo operador.
    with ambiente(AUDITORIA_ORIGENS_CONFIAVEIS="https://intra.exemplo.com.br/"):
        r = login(anon, senha="errada",
                  headers={"origin": "https://intra.exemplo.com.br"})
        checar(r.status_code == 401,
               f"origem da lista deveria passar: {r.status_code} {r.text}")

    # Proxy que reescreve o Host: vale o X-Forwarded-Host, mas so de proxy
    # declarado (senao qualquer um mandaria o cabecalho e passaria).
    proxy = TestClient(app, client=("10.0.0.5", 50000))
    via_proxy = {"host": "127.0.0.1:8600",
                 "x-forwarded-host": "intra.exemplo.com.br",
                 "origin": "https://intra.exemplo.com.br"}
    r = login(proxy, senha="errada", headers=via_proxy)
    checar(r.status_code == 400,
           f"X-Forwarded-Host de quem nao e proxy nao conta: {r.status_code}")
    with ambiente(AUDITORIA_PROXIES_CONFIAVEIS="10.0.0.5"):
        r = login(proxy, senha="errada", headers=via_proxy)
        checar(r.status_code == 401,
               f"X-Forwarded-Host do proxy declarado: {r.status_code} {r.text}")


def cookie_de_sessao(app) -> None:
    # HTTP puro (LAN): sem Secure, senao o navegador descartaria o cookie.
    attrs = atributos_cookie(login(TestClient(app)))
    checar("httponly" in attrs and "samesite=lax" in attrs,
           f"cookie deveria ser HttpOnly e SameSite=lax: {attrs}")
    checar("secure" not in attrs, f"HTTP puro nao leva Secure: {attrs}")

    # HTTPS direto.
    attrs = atributos_cookie(login(TestClient(app,
                                              base_url="https://testserver")))
    checar("secure" in attrs, f"HTTPS deveria levar Secure: {attrs}")

    # HTTPS terminado no proxy: X-Forwarded-Proto so vale de proxy declarado.
    proxy = TestClient(app, client=("10.0.0.5", 50000))
    https = {"x-forwarded-proto": "https"}
    attrs = atributos_cookie(login(proxy, headers=https))
    checar("secure" not in attrs,
           f"X-Forwarded-Proto de qualquer um nao conta: {attrs}")
    with ambiente(AUDITORIA_PROXIES_CONFIAVEIS="10.0.0.0/24"):
        attrs = atributos_cookie(login(proxy, headers=https))
        checar("secure" in attrs, f"proxy declarado com HTTPS: {attrs}")

    # Forcado pelo operador.
    with ambiente(AUDITORIA_COOKIES_SEGUROS="1"):
        attrs = atributos_cookie(login(TestClient(app)))
        checar("secure" in attrs, f"AUDITORIA_COOKIES_SEGUROS=1: {attrs}")

    # Logout por HTTPS apaga o cookie com os mesmos atributos.
    cliente = TestClient(app, base_url="https://testserver")
    login(cliente)
    attrs = atributos_cookie(cliente.post("/api/logout"))
    checar("secure" in attrs and "httponly" in attrs,
           f"o logout deveria repetir os atributos: {attrs}")


def ip_do_cliente(app, adm) -> None:
    ip = seguranca.ip_do_cliente
    checar(ip(requisicao("203.0.113.9", "1.2.3.4")) == "203.0.113.9",
           "sem proxy declarado, X-Forwarded-For e ignorado")
    checar(ip(requisicao("testclient")) == "", "peer que nao e IP vira vazio")
    checar(ip(requisicao(None)) == "", "sem peer vira vazio")
    with ambiente(AUDITORIA_PROXIES_CONFIAVEIS="203.0.113.9"):
        checar(ip(requisicao("203.0.113.9", "1.2.3.4")) == "1.2.3.4",
               "proxy declarado: vale o X-Forwarded-For")
        checar(ip(requisicao("198.51.100.1", "1.2.3.4")) == "198.51.100.1",
               "quem nao e o proxy continua sem poder escolher o IP")
        checar(ip(requisicao("203.0.113.9", "")) == "203.0.113.9",
               "cabecalho vazio cai no peer")
    with ambiente(AUDITORIA_PROXIES_CONFIAVEIS="10.0.0.0/8, 192.0.2.1"):
        # O cliente pode mandar o proprio X-Forwarded-For e o proxy so
        # acrescenta: o IP certo e o primeiro NAO confiavel pela direita.
        r = requisicao("10.1.2.3", "6.6.6.6, 1.2.3.4, 10.9.9.9")
        checar(ip(r) == "1.2.3.4", f"cadeia de proxies: {ip(r)!r}")
        r = requisicao("10.1.2.3", '=HYPERLINK("http://x")')
        checar(ip(r) == "10.1.2.3",
               f"lixo no cabecalho nunca vira IP (CSV da trilha): {ip(r)!r}")
        checar(ip(requisicao("192.0.2.1", "1.2.3.4:5678")) == "1.2.3.4",
               "IPv4 com porta")
        checar(ip(requisicao("192.0.2.1", "[2001:db8::7]:443"))
               == "2001:db8::7", "IPv6 com porta")

    # Na trilha de verdade.
    cliente = TestClient(app, client=("203.0.113.9", 50000))
    login(cliente, usuario="fulano-inexistente", senha="x",
          headers={"x-forwarded-for": "1.2.3.4"})
    ultimo = eventos(adm, "sessao.login_negado")[0]
    checar(ultimo["ip"] == "203.0.113.9",
           f"trilha com IP escolhido pelo cliente: {ultimo['ip']!r}")
    with ambiente(AUDITORIA_PROXIES_CONFIAVEIS="203.0.113.9"):
        login(cliente, usuario="fulano-inexistente", senha="x",
              headers={"x-forwarded-for": "1.2.3.4"})
    ultimo = eventos(adm, "sessao.login_negado")[0]
    checar(ultimo["ip"] == "1.2.3.4",
           f"trilha atras do proxy declarado: {ultimo['ip']!r}")


def limite_de_login(app, adm) -> None:
    ip_a = TestClient(app, client=("198.51.100.7", 50000))
    for tentativa in range(auth.MAX_FALHAS):
        r = login(ip_a, senha="errada")
        checar(r.status_code == 401,
               f"tentativa {tentativa + 1}: {r.status_code} {r.text}")

    # Bloqueado: nem a senha certa passa, e o 429 diz quanto esperar.
    r = login(ip_a)
    checar(r.status_code == 429, f"deveria bloquear: {r.status_code} {r.text}")
    espera = int(r.headers.get("retry-after", "0"))
    checar(1 <= espera <= 60, f"Retry-After fora do esperado: {espera}")
    checar("tentativas" in r.json()["detail"].lower(),
           f"mensagem do bloqueio: {r.text}")
    checar("set-cookie" not in r.headers, "bloqueado nao recebe cookie")

    # A CONTA nao fica trancada: quem tem a senha entra de outro lugar
    # (senao bastaria errar a senha de alguem para tira-lo do sistema).
    ip_b = TestClient(app, client=("198.51.100.8", 50000))
    r = login(ip_b)
    checar(r.status_code == 200, f"ana de outro IP deveria entrar: {r.text}")

    # O bloqueio esta no banco: reiniciar o servidor nao libera.
    r = login(TestClient(criar_app(), client=("198.51.100.7", 50000)))
    checar(r.status_code == 429,
           f"bloqueio deveria sobreviver ao reinicio: {r.status_code}")

    negados = [e for e in eventos(adm, "sessao.login_negado")
               if e["ip"] == "198.51.100.7"]
    checar(any(e["http_status"] == 429 for e in negados),
           f"o bloqueio deveria ficar na trilha com 429: {negados[:3]}")

    # O bloqueio vence sozinho; o login certo zera o contador do IP.
    passado = (datetime.now() - timedelta(seconds=1)).isoformat()
    with auth.conexao() as conn:
        conn.execute("UPDATE tentativa_login SET bloqueado_ate=? WHERE chave=?",
                     (passado, "ip:198.51.100.7"))
    r = login(ip_a)
    checar(r.status_code == 200,
           f"bloqueio vencido deveria liberar: {r.status_code} {r.text}")
    r = login(ip_a, senha="errada")
    checar(r.status_code == 401, f"um erro isolado depois: {r.status_code}")

    # Falhas fora da janela nao somam.
    antigo = (datetime.now() - auth.JANELA_FALHAS
              - timedelta(minutes=1)).isoformat()
    with auth.conexao() as conn:
        conn.execute("UPDATE tentativa_login SET falhas=?, primeira_em=?"
                     " WHERE chave=?",
                     (auth.MAX_FALHAS - 1, antigo, "ip:198.51.100.7"))
    r = login(ip_a, senha="errada")
    checar(r.status_code == 401, f"janela vencida: {r.status_code}")
    with auth.conexao() as conn:
        falhas = conn.execute("SELECT falhas FROM tentativa_login WHERE"
                              " chave=?", ("ip:198.51.100.7",)).fetchone()[0]
    checar(falhas == 1, f"janela vencida deveria recomecar em 1: {falhas}")

    # Requisicao barrada na borda (Origin) nem chega a contar tentativa.
    ip_c = TestClient(app, client=("198.51.100.9", 50000))
    for _ in range(auth.MAX_FALHAS + 2):
        r = login(ip_c, senha="errada", headers={"origin": ORIGEM_MA})
        checar(r.status_code == 400, f"origem forjada: {r.status_code}")
    r = login(ip_c)
    checar(r.status_code == 200,
           f"recusas de borda nao deveriam bloquear: {r.status_code}")

    # Usuario gigante nao vira chave gigante no banco.
    login(TestClient(app, client=("198.51.100.10", 50000)),
          usuario="x" * 10_000, senha="errada")
    with auth.conexao() as conn:
        maior = conn.execute(
            "SELECT MAX(LENGTH(chave)) FROM tentativa_login").fetchone()[0]
    checar(maior <= 80, f"chave do contador sem limite: {maior} caracteres")


def main() -> int:
    app = criar_app()

    # Bootstrap por HTTPS: o primeiro cookie ja sai com Secure.
    adm = TestClient(app, base_url="https://testserver")
    r = adm.post("/api/bootstrap", json={"usuario": "admin", "nome": "Admin",
                                         "senha": SENHA_ADM})
    checar(r.status_code == 200, f"bootstrap falhou: {r.text}")
    attrs = atributos_cookie(r)
    checar("secure" in attrs and "httponly" in attrs,
           f"bootstrap por HTTPS: {attrs}")
    r = adm.post("/api/admin/usuarios", json={
        "usuario": "ana", "nome": "Ana", "senha": SENHA_ANA, "admin": False,
        "permissoes": ["aba.conferencia"]})
    checar(r.status_code == 200, f"criar ana falhou: {r.text}")

    cabecalhos_da_api(app)
    host_confiavel(app)
    origem_nas_mutacoes(app, adm)
    cookie_de_sessao(app)
    ip_do_cliente(app, adm)
    limite_de_login(app, adm)

    print("OK - endurecimento web (nosniff/CSP na API, Host da lista, Origin "
          "nas mutacoes, cookie Secure atras de HTTPS, X-Forwarded-For so de "
          "proxy declarado e limite de tentativas de login) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
