"""Versao web — Emissao de NFS-e (oitava ferramenta, spec 006).

Portao de acesso por rota (401/403 com trilha), catalogo e padrao de usuario
novo, fluxo completo (perfil -> planilha -> texto -> corrigir -> reconferir ->
aprovar -> baixar), 409/413/422, identidade so da sessao, trilha geral sem
CPF nem nome e o fluxo inteiro sem conexao para fora da maquina.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import socket
import sys
import tempfile
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_nfse_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from auditoria_fiscal.web import rotas_nfse  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from fixtures import nfse as fx  # noqa: E402

ADMIN = {"usuario": "weslley", "nome": "Weslley", "senha": "segredo1"}
ATENDENTE = {"usuario": "atendente", "nome": "Atendente", "senha": "segredo2"}
FISCAL = {"usuario": "fiscal", "nome": "Fiscal", "senha": "segredo3"}
CONSULTA = {"usuario": "consulta", "nome": "Consulta", "senha": "segredo4"}
FORA = {"usuario": "fora", "nome": "Fora", "senha": "segredo5"}

HOJE = dt.datetime.now(nd.FUSO_SALVADOR).date()
COMP = f"{HOJE.month:02d}/{HOJE.year}"
SLUGS = {"aba.nfse", "nfse.perfis", "nfse.importar", "nfse.aprovar_emitir",
         "nfse.exportar"}

TEXTO = f"""Competência: {COMP}
Responsável: Carla Teste
CPF: 987.654.321-01
Aluno: Lia Exemplo
Turma: Infantil 2
Valor: 980,50

Competência: {COMP}
Responsável: Ana Exemplo
CPF: 123.456.789-09
Aluno: Davi Exemplo
Turma: Berçário
Valor: 1.100,00
obs: entrou no meio do mes
"""

# Tudo que nao pode aparecer na trilha geral.
PESSOAIS = ["123.456.789-09", "12345678909", "111.444.777-35", "11144477735",
            "987.654.321-0", "9876543210", "Ana Exemplo", "Pedro Exemplo",
            "Bruno Teste", "Caio Teste", "Carla Teste", "Lia Exemplo", "Davi Exemplo"]


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


# ----------------------------------------------------------------------
# Rede: nada pode sair da maquina. Loopback continua liberado porque o
# proprio asyncio do Windows usa um par de sockets locais.

TENTATIVAS: list = []
_connect_original = socket.socket.connect
_getaddrinfo_original = socket.getaddrinfo
_LOCAIS = {"127.0.0.1", "::1", "localhost"}


def _connect_vigiado(self, endereco):
    host = endereco[0] if isinstance(endereco, tuple) else str(endereco)
    if host not in _LOCAIS:
        TENTATIVAS.append(endereco)
        raise OSError("Rede bloqueada no teste da NFS-e (Fase 1 nao transmite).")
    return _connect_original(self, endereco)


def _getaddrinfo_vigiado(host, *args, **kwargs):
    if host not in _LOCAIS and host is not None:
        TENTATIVAS.append(host)
        raise OSError("DNS bloqueado no teste da NFS-e.")
    return _getaddrinfo_original(host, *args, **kwargs)


def entrar(app, credenciais: dict) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post("/api/login", json={"usuario": credenciais["usuario"],
                                         "senha": credenciais["senha"]})
    checar(r.status_code == 200, f"login {credenciais['usuario']}: {r.text}")
    return cliente


def criar_usuario(adm, credenciais, permissoes) -> None:
    r = adm.post("/api/admin/usuarios", json={**credenciais, "admin": False,
                                              "permissoes": permissoes})
    checar(r.status_code == 200, r.text[:200])


def historico(adm) -> list[dict]:
    r = adm.get("/api/admin/historico", params={"limite": 1000})
    checar(r.status_code == 200, r.status_code)
    return r.json()["itens"]


def planilha(pasta: str, nome: str, linhas: list[list]) -> bytes:
    caminho = fx.gerar_planilha(pasta, linhas, nome=nome)
    with open(caminho, "rb") as arq:
        return arq.read()


def lote(cliente, lote_id) -> dict:
    r = cliente.get(f"/api/nfse/lotes/{lote_id}")
    checar(r.status_code == 200, r.text[:200])
    return r.json()


def main() -> int:
    socket.socket.connect = _connect_vigiado
    socket.getaddrinfo = _getaddrinfo_vigiado
    try:
        return _main()
    finally:
        socket.socket.connect = _connect_original
        socket.getaddrinfo = _getaddrinfo_original


def _main() -> int:
    app = criar_app()
    adm = TestClient(app)
    checar(adm.post("/api/bootstrap", json=ADMIN).status_code == 200, "bootstrap")
    pasta = tempfile.mkdtemp(prefix="nfse_web_arquivos_")

    # ------------------------------------------------------------------
    # 401 sem login, em leitura e em mutacao

    anonimo = TestClient(app)
    for metodo, caminho in (("get", "/api/nfse/perfis"), ("get", "/api/nfse/lotes"),
                            ("get", "/api/nfse/lotes/1"),
                            ("post", "/api/nfse/lotes/texto"),
                            ("post", "/api/nfse/planilha-modelo"),
                            ("post", "/api/nfse/lotes/1/aprovar")):
        r = getattr(anonimo, metodo)(caminho, **({"json": {}} if metodo == "post" else {}))
        checar(r.status_code == 401, f"{metodo} {caminho} sem login: {r.status_code}")

    # ------------------------------------------------------------------
    # Catalogo: os cinco slugs e o padrao de usuario novo (so a aba)

    cat = adm.get("/api/admin/usuarios").json()
    slugs = {i["slug"] for g in cat["catalogo"] for i in g["itens"]}
    checar(SLUGS <= slugs, f"slugs ausentes: {SLUGS - slugs}")
    padrao = set(cat["padrao_novo"])
    checar("aba.nfse" in padrao, "o padrao sugere a aba")
    checar(not (SLUGS - {"aba.nfse"}) & padrao,
           f"o padrao NAO pode sugerir {(SLUGS - {'aba.nfse'}) & padrao}")

    criar_usuario(adm, ATENDENTE, ["aba.nfse", "nfse.importar"])
    criar_usuario(adm, FISCAL, ["aba.nfse", "nfse.perfis", "nfse.aprovar_emitir",
                                "nfse.exportar"])
    criar_usuario(adm, CONSULTA, ["aba.nfse"])
    criar_usuario(adm, FORA, ["aba.conferencia"])
    atendente, fiscal = entrar(app, ATENDENTE), entrar(app, FISCAL)
    consulta, fora = entrar(app, CONSULTA), entrar(app, FORA)

    # ------------------------------------------------------------------
    # Sem a aba: 403 em tudo, e a mutacao negada fica na trilha

    checar(fora.get("/api/nfse/lotes").status_code == 403, "leitura sem a aba")
    r = fora.post("/api/nfse/lotes/texto", json={"perfil_id": 1, "texto": "x"})
    checar(r.status_code == 403, f"importar sem a aba: {r.status_code}")
    negados = [e for e in historico(adm)
               if e.get("usuario") == "fora" and e["resultado"] == "negado"]
    checar(negados and negados[0]["acao"] == "nfse.importar", negados[:1])
    checar(fora.post("/api/eventos/aba", json={"aba": "nfse"}).status_code == 403,
           "nem o evento de abrir a aba")

    # ------------------------------------------------------------------
    # Perfil: so quem tem nfse.perfis; pendencias aparecem

    dados = fx.perfil_cru()
    checar(atendente.post("/api/nfse/perfis", json={"dados": dados}).status_code == 403,
           "atendente nao cadastra perfil")
    r = fiscal.post("/api/nfse/perfis", json={"dados": dados, "motivo": "cadastro"})
    checar(r.status_code == 200, r.text[:300])
    perfil_id = r.json()["perfil_id"]
    p = consulta.get(f"/api/nfse/perfis/{perfil_id}").json()
    checar({x["origem"] for x in p["pendencias"]} == {"JB-2", "JB-8", "R5"},
           p["pendencias"])
    r = fiscal.post("/api/nfse/perfis", json={"dados": fx.perfil_completo(
        cnpj="11.222.333/0001-80")})
    checar(r.status_code == 422 and r.json()["detail"]["campo"] == "cnpj", r.text[:200])
    r = fiscal.post(f"/api/nfse/perfis/{perfil_id}/versoes",
                    json={"dados": fx.perfil_completo(), "motivo": "respostas da JB"})
    checar(r.status_code == 200 and r.json()["versao"] == 2, r.text[:200])
    checar(consulta.get(f"/api/nfse/perfis/{perfil_id}").json()["pendencias"] == [],
           "versao 2 sem pendencias")
    checar(consulta.post("/api/nfse/planilha-modelo").status_code == 200,
           "a planilha-modelo exige so a aba")

    # ------------------------------------------------------------------
    # Importar planilha (multipart) e texto

    linhas = [[COMP, "Ana Exemplo", fx.CPF_ANA, None, None, "Pedro Exemplo",
               "Berçário", 1250] + [None] * 8,
              [COMP, "Bruno Teste", fx.CPF_BRUNO, None, None, "Caio Teste",
               "Bercario I", 980.5] + [None] * 8]
    conteudo = planilha(pasta, "lista.xlsx", linhas)
    arquivo = {"arquivo": ("lista.xlsx", conteudo, rotas_nfse.MIME_XLSX)}
    checar(consulta.post("/api/nfse/lotes/planilha", data={"perfil_id": perfil_id},
                         files=arquivo).status_code == 403, "consulta nao importa")
    r = atendente.post("/api/nfse/lotes/planilha", data={"perfil_id": perfil_id},
                       files=arquivo)
    checar(r.status_code == 200 and not r.json()["reaproveitado"], r.text[:300])
    lote_planilha = r.json()["lote_id"]
    r = atendente.post("/api/nfse/lotes/planilha", data={"perfil_id": perfil_id},
                       files={"arquivo": ("outro nome.xlsx", conteudo, rotas_nfse.MIME_XLSX)})
    checar(r.json() == {"lote_id": lote_planilha, "reaproveitado": True}, r.text[:200])
    lp = lote(consulta, lote_planilha)
    checar([l["situacao"] for l in lp["linhas"]] == ["ok", "ok"],
           [l["apontamentos"] for l in lp["linhas"]])

    teto = rotas_nfse.MAX_UPLOAD_BYTES
    rotas_nfse.MAX_UPLOAD_BYTES = 1000
    try:
        r = atendente.post("/api/nfse/lotes/planilha", data={"perfil_id": perfil_id},
                           files={"arquivo": ("grande.xlsx", conteudo + b"x" * 2000,
                                              rotas_nfse.MIME_XLSX)})
    finally:
        rotas_nfse.MAX_UPLOAD_BYTES = teto
    checar(r.status_code == 413, f"planilha grande: {r.status_code}")
    r = atendente.post("/api/nfse/lotes/texto",
                       json={"perfil_id": perfil_id, "texto": "x" * (300 * 1024)})
    checar(r.status_code == 413, f"texto grande: {r.status_code}")
    r = atendente.post("/api/nfse/lotes/planilha", data={"perfil_id": perfil_id},
                       files={"arquivo": ("falsa.xlsx", b"nao sou planilha",
                                          rotas_nfse.MIME_XLSX)})
    checar(r.status_code == 422 and r.json()["detail"]["code"] == "ARQUIVO_RECUSADO",
           r.text[:200])

    # Sem perfil escolhido (lista de perfis vazia ou nada selecionado): a tela
    # recebia a lista de validacao do FastAPI e so mostrava "Erro 422".
    for dados in ({"perfil_id": ""}, {}, {"perfil_id": "abc"}):
        r = atendente.post("/api/nfse/lotes/planilha", data=dados, files=arquivo)
        checar(r.status_code == 422 and isinstance(r.json()["detail"], dict)
               and r.json()["detail"]["code"] == "PERFIL_OBRIGATORIO"
               and "perfil" in r.json()["detail"]["detail"].lower(),
               f"planilha sem perfil {dados}: {r.status_code} {r.text[:200]}")
    for corpo in ({"texto": TEXTO}, {"perfil_id": 0, "texto": TEXTO},
                  {"perfil_id": None, "texto": TEXTO}):
        r = atendente.post("/api/nfse/lotes/texto", json=corpo)
        checar(r.status_code == 422 and isinstance(r.json()["detail"], dict)
               and r.json()["detail"]["code"] == "PERFIL_OBRIGATORIO",
               f"texto sem perfil {corpo}: {r.status_code} {r.text[:200]}")

    r = atendente.post("/api/nfse/lotes/texto", json={"perfil_id": perfil_id,
                                                      "texto": TEXTO})
    checar(r.status_code == 200, r.text[:300])
    lote_texto = r.json()["lote_id"]
    lt = lote(atendente, lote_texto)
    carla, ana = lt["linhas"]
    checar(carla["situacao"] == "bloqueio"
           and carla["apontamentos"][0]["codigo"] == nf.CPF_INVALIDO, carla)
    checar(ana["situacao"] == "aviso", ana["apontamentos"])

    # ------------------------------------------------------------------
    # Correcao: revisao, motivo e identidade so da sessao

    corpo = {"campo": "responsavel_cpf", "valor": fx.CPF_CARLA, "motivo": "",
             "revision": 1}
    r = atendente.post(f"/api/nfse/lotes/{lote_texto}/linhas/{carla['id']}/correcoes",
                       json=corpo)
    checar(r.status_code == 422 and r.json()["detail"]["code"] == "MOTIVO_OBRIGATORIO",
           r.text[:200])
    r = atendente.post(f"/api/nfse/lotes/{lote_texto}/linhas/{carla['id']}/correcoes",
                       json={**corpo, "motivo": "Escola reenviou", "revision": 7})
    checar(r.status_code == 409
           and r.json()["detail"]["code"] == "REVISION_DESATUALIZADA"
           and r.json()["detail"]["current_revision"] == 1, r.text[:200])
    r = atendente.post(f"/api/nfse/lotes/{lote_texto}/linhas/{carla['id']}/correcoes",
                       json={**corpo, "motivo": "Escola reenviou",
                             "usuario_login": "intruso", "usuario_id": 999})
    checar(r.status_code == 200 and r.json()["revision"] == 2, r.text[:200])
    historico_linha = atendente.get(
        f"/api/nfse/lotes/{lote_texto}/linhas/{carla['id']}/correcoes").json()["itens"]
    checar(historico_linha[0]["criada_por_login"] == "atendente",
           "identidade vem da sessao, nunca do corpo")
    checar(consulta.post(f"/api/nfse/lotes/{lote_texto}/reconferir",
                         json={"revision": 2}).status_code == 403,
           "consulta nao reconfere")
    r = atendente.post(f"/api/nfse/lotes/{lote_texto}/reconferir", json={"revision": 2})
    checar(r.status_code == 200 and r.json()["revision"] == 3, r.text[:200])

    # ------------------------------------------------------------------
    # Aprovar: so quem tem nfse.aprovar_emitir; avisos pedem confirmacao

    r = atendente.post(f"/api/nfse/lotes/{lote_planilha}/aprovar", json={"revision": 1})
    checar(r.status_code == 403, "atendente nao aprova")
    r = fiscal.post(f"/api/nfse/lotes/{lote_texto}/aprovar", json={"revision": 3})
    checar(r.status_code == 422
           and r.json()["detail"]["code"] == rotas_nfse.AVISOS_NAO_CONFIRMADOS,
           r.text[:200])
    r = fiscal.post(f"/api/nfse/lotes/{lote_texto}/aprovar",
                    json={"revision": 3, "confirmar_avisos": True})
    checar(r.status_code == 200 and r.json()["dps"] == 2, r.text[:300])
    r = fiscal.post(f"/api/nfse/lotes/{lote_texto}/aprovar",
                    json={"revision": 3, "confirmar_avisos": True})
    checar(r.status_code == 409, f"aprovar de novo com revisao velha: {r.status_code}")
    r = fiscal.post(f"/api/nfse/lotes/{lote_planilha}/aprovar", json={"revision": 1})
    checar(r.status_code == 200 and r.json()["dps"] == 2, r.text[:300])

    # Lote com bloqueio nao aprova.
    r = atendente.post("/api/nfse/lotes/texto", json={
        "perfil_id": perfil_id, "texto": TEXTO.replace("980,50", "")})
    bloqueado = r.json()["lote_id"]
    r = fiscal.post(f"/api/nfse/lotes/{bloqueado}/aprovar",
                    json={"revision": 1, "confirmar_avisos": True})
    checar(r.status_code == 422 and r.json()["detail"]["code"] in (
        "LOTE_COM_BLOQUEIO",), r.text[:200])

    # ------------------------------------------------------------------
    # Saidas: so com nfse.exportar; tudo marcado como nao transmitido

    checar(atendente.post(f"/api/nfse/lotes/{lote_texto}/dps-zip").status_code == 403,
           "atendente nao baixa DPS")
    r = fiscal.post(f"/api/nfse/lotes/{lote_texto}/dps-zip")
    checar(r.status_code == 200 and "NAO-TRANSMITIDA" in r.headers["content-disposition"],
           r.headers)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        xmls = [n for n in z.namelist() if n.endswith(".xml")]
        checar(len(xmls) == 2, z.namelist())
        for nome in xmls:
            checar(nd.validar_xsd(z.read(nome)) == [], f"{nome} valida no XSD")
    r = fiscal.post(f"/api/nfse/lotes/{lote_texto}/resumo")
    checar(r.status_code == 200 and r.content[:2] == b"PK", r.status_code)
    dps_id = lote(fiscal, lote_texto)["dps"][0]["id"]
    r = fiscal.post(f"/api/nfse/dps/{dps_id}/xml")
    checar(r.status_code == 200 and b"<tpAmb>2</tpAmb>" in r.content
           and "NAO-TRANSMITIDA" in r.headers["content-disposition"], r.status_code)
    checar(fiscal.post(f"/api/nfse/lotes/{bloqueado}/dps-zip").status_code == 409,
           "lote sem DPS")
    checar(fiscal.post("/api/nfse/dps/99999/xml").status_code == 404, "DPS inexistente")

    # ------------------------------------------------------------------
    # Descartar: em revisao quem importa; aprovado so quem aprova

    r = atendente.post(f"/api/nfse/lotes/{bloqueado}/descartar",
                       json={"revision": 1, "motivo": "Lista refeita pela escola"})
    checar(r.status_code == 200, r.text[:200])
    r = atendente.post(f"/api/nfse/lotes/{lote_planilha}/descartar",
                       json={"revision": 2, "motivo": "x"})
    checar(r.status_code == 403, f"atendente nao descarta aprovado: {r.status_code}")
    r = fiscal.post(f"/api/nfse/lotes/{lote_planilha}/descartar",
                    json={"revision": 2, "motivo": "Valor errado na lista"})
    checar(r.status_code == 200, r.text[:200])
    checar(consulta.get("/api/nfse/lotes", params={"estado": "descartado"}).json()["total"]
           == 2, "dois descartados")
    checar(consulta.get("/api/nfse/lotes", params={"estado": "x"}).status_code == 409,
           "filtro por allowlist")

    tipos = [e["tipo"] for e in consulta.get(
        f"/api/nfse/lotes/{lote_texto}/eventos").json()["itens"]]
    checar(tipos[:3] == ["lote_importado", "linha_corrigida", "lote_reconferido"]
           and "lote_aprovado" in tipos and tipos.count("dps_gerada") == 2
           and "exportacao" in tipos, tipos)

    # ------------------------------------------------------------------
    # Trilha geral: acoes registradas, sem nenhum dado pessoal

    itens = historico(adm)
    acoes = {e["acao"] for e in itens}
    for acao in ("nfse.perfil", "nfse.importar", "nfse.corrigir", "nfse.reconferir",
                 "nfse.aprovar", "nfse.descartar", "nfse.exportar", "nfse.modelo"):
        checar(acao in acoes, f"{acao} deveria estar na trilha geral")
    texto_trilha = json.dumps(itens, ensure_ascii=False)
    for pessoal in PESSOAIS:
        checar(pessoal not in texto_trilha,
               f"dado pessoal na trilha geral: {pessoal!r}")
    checar(not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto_trilha),
           "nenhum CPF formatado na trilha geral")

    checar(TENTATIVAS == [], f"tentativa de conexao para fora: {TENTATIVAS}")
    print("OK - web da NFS-e (401/403 por rota com trilha, cinco slugs e padrao "
          "so com a aba, perfil com pendencias e versoes, planilha e texto com "
          "reaproveitamento e limites 413, correcao com motivo, revisao 409 e "
          "identidade da sessao, aprovacao com confirmacao de avisos e 409, "
          "saidas marcadas como nao transmitidas, descarte por estado, trilha "
          "geral sem dado pessoal e nenhuma conexao para fora) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
