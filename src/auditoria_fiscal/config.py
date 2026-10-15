"""Configuracao de rede e seguranca lida do ambiente do servidor.

Portado do clone do Cadastro JB (auditoria de 23/08/2026), so a parte de
rede: as flags de contencao fiscal daquele clone NAO vieram, porque
desligariam ferramentas que estao em uso aqui.

Diferenca deliberada em relacao ao clone: la o servidor passou a escutar so
em 127.0.0.1 e a lista de Hosts tem padrao fechado. Aqui o servidor continua
em 0.0.0.0 atendendo a LAN (servidor.py, devops/README.md), entao cada
restricao que depende do endereco publico so liga quando o operador declara
esse endereco. O que nao depende de configuracao (Origin igual ao Host nas
mutacoes, X-Forwarded-For ignorado, Secure quando a requisicao chegou por
HTTPS, limite de login, nosniff/CSP na API) vale sempre.

    AUDITORIA_HOSTS_CONFIAVEIS    Hosts aceitos, separados por virgula
                                  (ex.: intra.jbfraga.com.br). Vazio = sem
                                  restricao de Host. localhost, 127.0.0.1 e
                                  [::1] passam sempre.
    AUDITORIA_ORIGENS_CONFIAVEIS  Origins extras aceitas nas mutacoes, alem
                                  da propria (ex.: https://intra.jbfraga...).
    AUDITORIA_PROXIES_CONFIAVEIS  IPs ou redes (CIDR) do proxy reverso cujos
                                  X-Forwarded-For/-Proto/-Host valem. Vazio =
                                  nenhum cabecalho de proxy e acreditado.
    AUDITORIA_COOKIES_SEGUROS     1 forca o Secure no cookie de sessao mesmo
                                  quando o HTTPS nao e detectado.

Nada aqui e guardado em cache: a leitura e por chamada (barata) para que a
troca de valor valha no proximo reinicio sem surpresa e os testes possam
variar o ambiente.
"""

from __future__ import annotations

import os

_LIGADO = {"1", "true", "t", "sim", "s", "on", "yes", "y"}


def flag(nome: str, padrao: bool = False) -> bool:
    """Le uma flag de ambiente. Ausente = `padrao`."""
    bruto = os.environ.get(nome)
    if bruto is None:
        return padrao
    return bruto.strip().lower() in _LIGADO


def _lista(nome: str) -> list[str]:
    bruto = (os.environ.get(nome) or "").strip()
    return [item.strip() for item in bruto.split(",") if item.strip()]


def hosts_confiaveis() -> list[str]:
    """Hosts aceitos no cabecalho Host. Vazio = sem restricao."""
    return _lista("AUDITORIA_HOSTS_CONFIAVEIS")


def origens_confiaveis() -> list[str]:
    """Origins extras aceitas em requisicoes que mudam estado."""
    return [o.rstrip("/") for o in _lista("AUDITORIA_ORIGENS_CONFIAVEIS")]


def proxies_confiaveis() -> list[str]:
    """IPs/redes do proxy reverso cujos cabecalhos X-Forwarded-* valem."""
    return _lista("AUDITORIA_PROXIES_CONFIAVEIS")


def cookies_seguros_forcados() -> bool:
    """Secure no cookie mesmo sem HTTPS detectado (ato explicito)."""
    return flag("AUDITORIA_COOKIES_SEGUROS")
