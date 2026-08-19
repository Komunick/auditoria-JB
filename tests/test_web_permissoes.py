"""Versao web — permissoes por usuario e historico de acessos.

Sobe o app FastAPI com TestClient e exercita: bootstrap do admin, criacao de
um segundo administrador e de um usuario comum com permissoes recortadas,
bloqueio 403 nas abas e nas acoes que ele nao alcanca, a tentativa de
escalacao de privilegio (corrigir em LOTE tendo so a permissao de corrigir
uma nota), o efeito imediato de uma mudanca de permissao, a protecao do
ultimo administrador, a desativacao derrubando o login, a PROPRIEDADE das
sessoes de trabalho e dos jobs (conhecer o ID nao autoriza ninguem), e o
historico respondendo quando entrou, o que acessou, o que fez e quando saiu
(inclusive as tentativas negadas). Usa dados_web isolado em pasta temporaria
(AUDITORIA_WEB_DADOS).
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_perm_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.web import auditoria  # noqa: E402
from auditoria_fiscal.web.infra import pasta_sessoes  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def eventos(cliente, **filtros) -> list[dict]:
    resposta = cliente.get("/api/admin/historico", params=filtros)
    checar(resposta.status_code == 200,
           f"historico deveria responder: {resposta.status_code} "
           f"{resposta.text[:120]}")
    return resposta.json()["itens"]


def tem_evento(itens, acao: str, resultado: str = "") -> bool:
    return any(i["acao"] == acao and (not resultado or i["resultado"] == resultado)
               for i in itens)


def propriedade_de_sessoes_e_jobs(app, adm) -> None:
    """Conhecer o ID de uma sessao/job alheio NAO e autorizacao.

    Os IDs sao sorteados com `secrets.token_urlsafe`, mas alta entropia e
    segredo, nao controle de acesso: um ID vaza em log, historico, print de
    tela ou URL colada no chat. Sem dono, qualquer usuario AUTENTICADO que
    conheca o ID le o estado da sessao de outro (notas, empresa, valores),
    acompanha o job dele e — pior — DESCARTA a sessao alheia, apagando os
    uploads de quem estava trabalhando.

    Recurso alheio responde 404, nunca 403: um 403 confirmaria que aquele ID
    existe (research R7). A regra vale tambem para administrador: sessao de
    trabalho e estado transitorio de UMA pessoa, nao recurso administrado.
    """
    permitidas = ["aba.conferencia", "conferencia.conferir", "aba.produtos"]
    for login, nome in (("dono", "Dono"), ("xereta", "Xereta")):
        r = adm.post("/api/admin/usuarios", json={
            "usuario": login, "nome": nome, "senha": f"{login}12345",
            "admin": False, "permissoes": permitidas})
        checar(r.status_code == 200, f"criar {login} falhou: {r.text}")

    dono, xereta = TestClient(app), TestClient(app)
    for cliente, login in ((dono, "dono"), (xereta, "xereta")):
        checar(cliente.post("/api/login", json={"usuario": login,
                                                "senha": f"{login}12345"}
                            ).status_code == 200, f"{login} deveria entrar")

    r = dono.post("/api/sessoes", json={"ferramenta": "conferencia"})
    checar(r.status_code == 200, f"sessao do dono: {r.text}")
    sessao_dono = r.json()["sessao_id"]
    r = xereta.post("/api/sessoes", json={"ferramenta": "conferencia"})
    checar(r.status_code == 200, f"sessao do xereta: {r.text}")
    sessao_xereta = r.json()["sessao_id"]
    checar(sessao_dono != sessao_xereta, "as sessoes deveriam ser distintas")

    # O dono trabalha normalmente na PROPRIA sessao (a correcao nao pode
    # quebrar o uso legitimo).
    checar(dono.get("/api/conferencia/notas",
                    params={"sessao_id": sessao_dono}).status_code == 200,
           "o dono deveria ler a propria sessao")

    # LEITURA de sessao alheia.
    r = xereta.get("/api/conferencia/notas", params={"sessao_id": sessao_dono})
    checar(r.status_code == 404,
           f"ler a sessao do dono deveria dar 404: {r.status_code} "
           f"{r.text[:120]}")

    # MUTACAO usando sessao alheia.
    r = xereta.post("/api/conferencia/conferir", json={
        "sessao_id": sessao_dono, "chave": "3" * 44, "conferida": True,
        "observacao": "escrevendo na sessao dos outros"})
    checar(r.status_code == 404,
           f"conferir na sessao do dono deveria dar 404: {r.status_code}")

    # JOB alheio: o polling nao pode virar janela para o processamento de
    # outra pessoa (a carga falha por falta de arquivo, mas o job existe).
    r = dono.post("/api/conferencia/carregar",
                  json={"sessao_id": sessao_dono, "fonte": "sped"})
    checar(r.status_code == 200, f"carregar do dono: {r.text}")
    job_dono = r.json()["job_id"]
    checar(dono.get(f"/api/jobs/{job_dono}",
                    params={"ferramenta": "conferencia"}).status_code == 200,
           "o dono deveria acompanhar o proprio job")
    r = xereta.get(f"/api/jobs/{job_dono}",
                   params={"ferramenta": "conferencia"})
    checar(r.status_code == 404,
           f"consultar o job do dono deveria dar 404: {r.status_code} "
           f"{r.text[:120]}")

    # O job tambem carrega a FERRAMENTA. A rota de polling e compartilhada
    # pelas seis abas: sem declarar qual delas o cliente espera, um job_id da
    # conciliacao poderia ser consumido pelo cliente da conferencia e vice-
    # versa. `ferramenta` e obrigatoria — omiti-la e erro de contrato (422),
    # nao um atalho silencioso.
    r = dono.get(f"/api/jobs/{job_dono}", params={"ferramenta": "produtos"})
    checar(r.status_code == 404,
           f"job proprio com ferramenta divergente deveria dar 404: "
           f"{r.status_code} {r.text[:120]}")
    r = dono.get(f"/api/jobs/{job_dono}")
    checar(r.status_code == 422,
           f"job sem a ferramenta deveria dar 422: {r.status_code} "
           f"{r.text[:120]}")
    r = dono.get(f"/api/jobs/{job_dono}", params={"ferramenta": "inventada"})
    checar(r.status_code == 404,
           f"ferramenta desconhecida deveria dar 404, nao revelar nada: "
           f"{r.status_code}")

    # A sessao carrega a FERRAMENTA: uma sessao de produtos nao serve de
    # passe para as rotas da conferencia.
    r = dono.post("/api/sessoes", json={"ferramenta": "produtos"})
    checar(r.status_code == 200, f"sessao de produtos: {r.text}")
    sessao_produtos = r.json()["sessao_id"]
    r = dono.get("/api/conferencia/notas",
                 params={"sessao_id": sessao_produtos})
    checar(r.status_code == 404,
           f"sessao de produtos na rota de conferencia deveria dar 404: "
           f"{r.status_code}")

    # DESCARTE de sessao alheia: o dano aqui e destrutivo (apaga os uploads).
    pasta_do_dono = os.path.join(pasta_sessoes(), sessao_dono)
    checar(os.path.isdir(pasta_do_dono),
           "a pasta da sessao do dono deveria existir")
    r = xereta.delete(f"/api/sessoes/{sessao_dono}")
    checar(r.status_code == 404,
           f"descartar a sessao do dono deveria dar 404: {r.status_code}")
    checar(os.path.isdir(pasta_do_dono),
           "a pasta da sessao do dono NAO podia ter sido apagada")

    # Nem o administrador opera a sessao de trabalho de outra pessoa.
    checar(adm.get("/api/conferencia/notas",
                   params={"sessao_id": sessao_dono}).status_code == 404,
           "nem o admin le a sessao de trabalho alheia")
    checar(adm.delete(f"/api/sessoes/{sessao_dono}").status_code == 404,
           "nem o admin descarta a sessao de trabalho alheia")
    checar(os.path.isdir(pasta_do_dono),
           "a pasta da sessao do dono deveria seguir intacta")

    # ID inexistente responde igual a ID alheio: nada e revelado.
    r = xereta.get("/api/conferencia/notas",
                   params={"sessao_id": "sessao-que-nunca-existiu"})
    checar(r.status_code == 404, f"ID inexistente: {r.status_code}")
    inexistente = xereta.get("/api/jobs/job-que-nunca-existiu",
                             params={"ferramenta": "conferencia"})
    checar(inexistente.status_code == 404, f"job inexistente: {inexistente.status_code}")
    alheio = xereta.get(f"/api/jobs/{job_dono}",
                        params={"ferramenta": "conferencia"})
    checar(alheio.json() == inexistente.json(),
           f"job alheio e job inexistente deveriam responder igual: "
           f"{alheio.json()} != {inexistente.json()}")
    # Job proprio com a ferramenta errada tambem nao pode se distinguir de um
    # job que nunca existiu.
    divergente = dono.get(f"/api/jobs/{job_dono}",
                          params={"ferramenta": "produtos"})
    checar(divergente.json() == inexistente.json(),
           f"ferramenta divergente deveria responder igual a inexistente: "
           f"{divergente.json()} != {inexistente.json()}")

    # O dono continua no controle do que e dele, do inicio ao fim.
    checar(dono.get("/api/conferencia/notas",
                    params={"sessao_id": sessao_dono}).status_code == 200,
           "o dono deveria continuar lendo a propria sessao")
    checar(dono.delete(f"/api/sessoes/{sessao_dono}").status_code == 200,
           "o dono deveria descartar a propria sessao")
    checar(not os.path.isdir(pasta_do_dono),
           "descartar a propria sessao deveria remover a pasta")
    checar(xereta.get("/api/conferencia/notas",
                      params={"sessao_id": sessao_xereta}).status_code == 200,
           "a sessao do xereta nao podia ser afetada")


SLUGS_CONCILIACAO = (
    "aba.conciliacao", "conciliacao.importar", "conciliacao.revisar",
    "conciliacao.aprovar", "conciliacao.resolver_excecao",
    "conciliacao.exportar", "conciliacao.preencher_modelo",
    "conciliacao.incluir_pendentes",
)

# O que um usuario comum NOVO recebe por padrao: entrar e importar. Decidir,
# exportar e preencher o modelo oficial ficam de fora ate o admin liberar
# (menor privilegio, research R13).
PADRAO_ESPERADO_CONCILIACAO = ("aba.conciliacao", "conciliacao.importar")


def catalogo_e_permissoes_da_conciliacao(app, adm) -> None:
    """Sexta ferramenta no catalogo, no padrao e no 403 de quem nao tem."""
    catalogo = adm.get("/api/admin/usuarios").json()["catalogo"]
    do_catalogo = {item["slug"] for grupo in catalogo for item in grupo["itens"]}
    faltando = [s for s in SLUGS_CONCILIACAO if s not in do_catalogo]
    checar(not faltando, f"slugs ausentes do catalogo: {faltando}")

    grupos = {grupo["grupo"] for grupo in catalogo}
    checar(any("Concilia" in g for g in grupos),
           f"o catalogo deveria ter o grupo da conciliacao: {sorted(grupos)}")

    # Admin alcanca tudo implicitamente.
    permissoes_admin = adm.get("/api/estado").json()["usuario"]["permissoes"]
    ausentes = [s for s in SLUGS_CONCILIACAO if s not in permissoes_admin]
    checar(not ausentes, f"admin deveria alcancar tudo, faltou: {ausentes}")

    # Padrao sugerido para usuario NOVO: exatamente aba + importar da
    # conciliacao. O servidor nao concede nada sozinho — quem marca as caixas
    # e a tela de administracao, a partir deste `padrao_novo`; e ele que
    # precisa estar certo, senao o admin concede demais sem perceber.
    padrao = set(adm.get("/api/admin/usuarios").json()["padrao_novo"])
    for slug in PADRAO_ESPERADO_CONCILIACAO:
        checar(slug in padrao, f"o padrao deveria sugerir {slug}: {sorted(padrao)}")
    sobrando = [s for s in SLUGS_CONCILIACAO
                if s not in PADRAO_ESPERADO_CONCILIACAO and s in padrao]
    checar(not sobrando,
           f"o padrao NAO podia sugerir {sobrando} — decisao fiscal e saida "
           f"oficial exigem liberacao explicita")

    # Criar sem informar permissoes nao concede nada (o padrao e' sugestao da
    # tela, nunca um default silencioso do servidor).
    r = adm.post("/api/admin/usuarios", json={
        "usuario": "novato", "nome": "Novato", "senha": "novato12345"})
    checar(r.status_code == 200, f"criar novato falhou: {r.text}")
    novato_id = r.json()["id"]
    checar(r.json()["permissoes"] == [],
           f"sem permissoes no corpo, nada e concedido: {r.json()['permissoes']}")

    # Usuario que ja existia nao ganha slug novo por migracao silenciosa.
    usuarios = {u["usuario"]: u for u in adm.get(
        "/api/admin/usuarios").json()["usuarios"]}
    antigo = usuarios.get("junior")
    checar(antigo is not None, "o junior deveria continuar cadastrado")
    invadiram = [s for s in SLUGS_CONCILIACAO if s in antigo["permissoes"]]
    checar(not invadiram,
           f"usuario existente nao pode receber {invadiram} automaticamente")

    # Sem a aba: nao abre sessao, nao navega e nao alcanca a rota.
    sem_aba = TestClient(app)
    r = adm.post("/api/admin/usuarios", json={
        "usuario": "forasteiro", "nome": "Forasteiro",
        "senha": "forasteiro12345", "permissoes": ["aba.conferencia"]})
    checar(r.status_code == 200, f"criar forasteiro falhou: {r.text}")
    checar(sem_aba.post("/api/login", json={"usuario": "forasteiro",
                                            "senha": "forasteiro12345"}
                        ).status_code == 200, "forasteiro deveria entrar")
    checar(sem_aba.post("/api/sessoes",
                        json={"ferramenta": "conciliacao"}).status_code == 403,
           "sem a aba, criar sessao da conciliacao deveria dar 403")
    checar(sem_aba.post("/api/eventos/aba",
                        json={"aba": "conciliacao"}).status_code == 403,
           "sem a aba, navegar para a conciliacao deveria dar 403")
    checar(sem_aba.get("/api/conciliacao/resumo").status_code == 403,
           "sem a aba, o resumo deveria dar 403")

    # Concessao e remocao valem na acao seguinte, sem novo login.
    checar(adm.put(f"/api/admin/usuarios/{novato_id}/permissoes", json={
        "permissoes": ["aba.conciliacao", "conciliacao.importar",
                       "conciliacao.aprovar"]}).status_code == 200,
           "conceder aprovar ao novato")
    novato = TestClient(app)
    checar(novato.post("/api/login", json={"usuario": "novato",
                                           "senha": "novato12345"}
                       ).status_code == 200, "novato deveria entrar")
    checar("conciliacao.aprovar" in
           novato.get("/api/estado").json()["usuario"]["permissoes"],
           "a concessao deveria valer na hora")
    checar(adm.put(f"/api/admin/usuarios/{novato_id}/permissoes",
                   json={"permissoes": ["aba.conciliacao"]}).status_code == 200,
           "retirar as permissoes do novato")
    checar(novato.get("/api/estado").json()["usuario"]["permissoes"]
           == ["aba.conciliacao"],
           "a remocao deveria valer na hora, sem novo login")
    checar(novato.get("/api/conciliacao/resumo").status_code == 200,
           "com a aba, o resumo continua acessivel")


def main() -> int:
    app = criar_app()
    # Um cliente por pessoa: o TestClient guarda o cookie de sessao.
    adm = TestClient(app)
    carol = TestClient(app)
    junior = TestClient(app)

    # ------------------------------------------------------------------
    # Bootstrap do primeiro administrador

    r = adm.post("/api/bootstrap", json={"usuario": "weslley",
                                         "nome": "Weslley",
                                         "senha": "segredo1"})
    checar(r.status_code == 200, f"bootstrap falhou: {r.text}")
    estado = adm.get("/api/estado").json()
    checar(estado["usuario"]["admin"] is True, f"deveria ser admin: {estado}")
    checar("conferencia.sped_corrigido" in estado["usuario"]["permissoes"],
           "admin deveria receber o catalogo inteiro de permissoes")

    # ------------------------------------------------------------------
    # O admin cria a Carol como segunda administradora

    r = adm.post("/api/admin/usuarios", json={
        "usuario": "carol", "nome": "Carol", "senha": "segredo2",
        "admin": True})
    checar(r.status_code == 200, f"criar carol falhou: {r.text}")
    checar(r.json()["admin"] is True, f"carol deveria ser admin: {r.json()}")

    checar(carol.post("/api/login", json={"usuario": "carol",
                                          "senha": "segredo2"}
                      ).status_code == 200, "carol deveria conseguir entrar")
    # Administradora plena: administra usuarios e ve o historico de todos.
    checar(carol.get("/api/admin/usuarios").status_code == 200,
           "carol deveria administrar usuarios")
    checar(carol.get("/api/admin/historico").status_code == 200,
           "carol deveria ver o historico")

    # ------------------------------------------------------------------
    # Carol cria um usuario comum com acesso recortado

    r = carol.post("/api/admin/usuarios", json={
        "usuario": "junior", "nome": "Junior", "senha": "segredo3",
        "admin": False,
        "permissoes": ["aba.conferencia", "conferencia.conferir",
                       "conferencia.corrigir"]})
    checar(r.status_code == 200, f"criar junior falhou: {r.text}")
    junior_id = r.json()["id"]
    checar(r.json()["permissoes"] == ["aba.conferencia", "conferencia.conferir",
                                      "conferencia.corrigir"],
           f"permissoes gravadas fora do esperado: {r.json()['permissoes']}")

    r = carol.post("/api/admin/usuarios", json={
        "usuario": "junior", "nome": "Outro", "senha": "segredo4"})
    checar(r.status_code == 422, f"usuario repetido deveria dar 422: {r.text}")

    r = carol.post("/api/admin/usuarios", json={
        "usuario": "fulano", "nome": "Fulano", "senha": "segredo5",
        "permissoes": ["aba.inventada"]})
    checar(r.status_code == 422,
           f"permissao inexistente deveria dar 422: {r.text}")

    # ------------------------------------------------------------------
    # O usuario comum so alcanca o que foi liberado

    checar(junior.post("/api/login", json={"usuario": "junior",
                                           "senha": "segredo3"}
                       ).status_code == 200, "junior deveria conseguir entrar")
    estado = junior.get("/api/estado").json()
    checar(estado["usuario"]["admin"] is False, "junior nao e admin")
    checar(estado["usuario"]["permissoes"] == [
        "aba.conferencia", "conferencia.conferir", "conferencia.corrigir"],
        f"estado devolveu permissoes erradas: {estado['usuario']}")

    # Aba liberada: abre e cria sessao de trabalho.
    r = junior.post("/api/sessoes", json={"ferramenta": "conferencia"})
    checar(r.status_code == 200, f"conferencia deveria abrir: {r.text}")
    sessao = r.json()["sessao_id"]
    checar(junior.post("/api/eventos/aba",
                       json={"aba": "conferencia"}).status_code == 200,
           "junior deveria abrir a aba de conferencia")

    # Abas negadas: 403 tanto na sessao de trabalho quanto na navegacao.
    for ferramenta in ("produtos", "comparador", "diff", "extracao"):
        r = junior.post("/api/sessoes", json={"ferramenta": ferramenta})
        checar(r.status_code == 403,
               f"{ferramenta} deveria dar 403 para junior: {r.status_code}")
    checar(junior.post("/api/eventos/aba",
                       json={"aba": "produtos"}).status_code == 403,
           "aba negada deveria dar 403")

    # Administracao e proibida para quem nao e admin.
    checar(junior.get("/api/admin/usuarios").status_code == 403,
           "junior nao pode administrar usuarios")
    checar(junior.get("/api/admin/historico").status_code == 403,
           "junior nao pode ver o historico")
    r = junior.post("/api/admin/usuarios", json={
        "usuario": "invasor", "nome": "Invasor", "senha": "segredo6",
        "admin": True})
    checar(r.status_code == 403, f"junior nao pode criar usuario: {r.text}")

    # Acao liberada dentro da aba liberada.
    r = junior.post("/api/conferencia/conferir", json={
        "sessao_id": sessao, "chave": "3" * 44, "conferida": True,
        "observacao": "conferida pelo junior"})
    checar(r.status_code == 200, f"junior deveria conferir: {r.text}")

    # Acoes NAO liberadas dentro da aba liberada.
    for caminho in ("livro-fiscal", "inconsistencias", "sped-corrigido"):
        r = junior.post(f"/api/conferencia/{caminho}",
                        params={"sessao_id": sessao})
        checar(r.status_code == 403,
               f"{caminho} deveria dar 403 para junior: {r.status_code}")
    r = junior.post("/api/conferencia/composicao/editar", json={
        "sessao_id": sessao, "chave": "3" * 44, "grupo": "g", "coluna": 3,
        "texto": "1,00"})
    checar(r.status_code == 403,
           f"editar composicao deveria dar 403: {r.status_code}")

    # ESCALACAO DE PRIVILEGIO: junior tem "corrigir" mas NAO "corrigir_lote".
    # Corrigir a base inteira nao pode passar pela permissao de uma nota so.
    r = junior.post("/api/conferencia/corrigir", json={
        "sessao_id": sessao, "chave": "3" * 44, "campo": "cfop",
        "original": "1102", "novo": "2102", "lote": True})
    checar(r.status_code == 403,
           f"correcao em LOTE deveria dar 403 sem a permissao: "
           f"{r.status_code} {r.text[:120]}")

    # ------------------------------------------------------------------
    # Mudanca de permissao vale na hora seguinte (sem novo login)

    r = carol.put(f"/api/admin/usuarios/{junior_id}/permissoes", json={
        "permissoes": ["aba.conferencia", "conferencia.conferir",
                       "conferencia.corrigir", "conferencia.corrigir_lote",
                       "aba.produtos"]})
    checar(r.status_code == 200, f"definir permissoes falhou: {r.text}")
    checar(junior.post("/api/sessoes",
                       json={"ferramenta": "produtos"}).status_code == 200,
           "produtos deveria abrir depois da liberacao")
    r = junior.post("/api/conferencia/corrigir", json={
        "sessao_id": sessao, "chave": "3" * 44, "campo": "cfop",
        "original": "1102", "novo": "2102", "lote": True})
    checar(r.status_code != 403,
           f"lote nao deveria mais dar 403: {r.status_code} {r.text[:120]}")

    # Retirar a permissao fecha a porta de novo.
    r = carol.put(f"/api/admin/usuarios/{junior_id}/permissoes",
                  json={"permissoes": ["aba.conferencia"]})
    checar(r.status_code == 200, f"retirar permissoes falhou: {r.text}")
    checar(junior.post("/api/sessoes",
                       json={"ferramenta": "produtos"}).status_code == 403,
           "produtos deveria voltar a dar 403")

    # Recortar permissao de administrador nao faz sentido: 422 explicativo.
    usuarios = {u["usuario"]: u for u in carol.get(
        "/api/admin/usuarios").json()["usuarios"]}
    r = carol.put(f"/api/admin/usuarios/{usuarios['weslley']['id']}/permissoes",
                  json={"permissoes": ["aba.conferencia"]})
    checar(r.status_code == 422,
           f"permissao de admin deveria dar 422: {r.status_code}")

    # ------------------------------------------------------------------
    # Historico: quando entrou, o que acessou, o que fez, quando saiu

    checar(junior.post("/api/logout").status_code == 200, "logout do junior")

    itens = eventos(adm, usuario_filtro="junior", limite=200)
    checar(tem_evento(itens, "sessao.login", "ok"),
           "o historico deveria ter a ENTRADA do junior")
    checar(tem_evento(itens, "navegacao.aba", "ok"),
           "o historico deveria ter a aba que o junior acessou")
    checar(tem_evento(itens, "conferencia.conferir", "ok"),
           "o historico deveria ter a conferencia que o junior fez")
    checar(tem_evento(itens, "conferencia.corrigir", "negado"),
           "o historico deveria ter a tentativa NEGADA de correcao em lote")
    checar(tem_evento(itens, "sessao.trabalho_nova", "negado"),
           "o historico deveria ter a tentativa NEGADA de abrir outra aba")
    checar(tem_evento(itens, "sessao.logout", "ok"),
           "o historico deveria ter a SAIDA do junior")

    negados = [i for i in itens if i["resultado"] == "negado"]
    checar(negados and all(i["http_status"] == 403 for i in negados),
           f"tentativa negada deveria gravar 403: {negados[:1]}")
    conferiu = next(i for i in itens if i["acao"] == "conferencia.conferir")
    checar("3333" in conferiu["detalhe"] or conferiu["detalhe"],
           f"o evento deveria dizer o que foi feito: {conferiu}")
    checar(conferiu["nome"] == "Junior",
           f"o evento deveria identificar a pessoa: {conferiu}")

    # Login errado entra no historico sem revelar sessao.
    TestClient(app).post("/api/login", json={"usuario": "junior",
                                             "senha": "errada"})
    checar(tem_evento(eventos(adm, categoria="sessao", limite=200),
                      "sessao.login_negado", "negado"),
           "o historico deveria registrar a tentativa de login sem sucesso")

    # Acao administrativa tambem e auditada.
    itens = eventos(adm, usuario_filtro="carol", limite=200)
    checar(tem_evento(itens, "admin.usuario_criado", "ok"),
           "criar usuario deveria entrar no historico")
    mudancas = [i["detalhe"] for i in itens if i["acao"] == "admin.permissoes"
                and i["resultado"] == "ok"]
    checar(mudancas and all(d.startswith("junior:") for d in mudancas),
           f"a mudanca de permissao deveria dizer de quem foi: {mudancas}")
    checar(any("concedeu: aba.produtos" in d for d in mudancas),
           f"o historico deveria dizer o que foi CONCEDIDO: {mudancas}")
    checar(any("retirou: aba.produtos" in d for d in mudancas),
           f"o historico deveria dizer o que foi RETIRADO: {mudancas}")
    # A tentativa recusada tambem diz sobre quem era.
    recusada = next((i for i in itens if i["acao"] == "admin.permissoes"
                     and i["resultado"] == "erro"), None)
    checar(recusada is not None and "weslley" in recusada["detalhe"],
           f"a tentativa recusada deveria nomear o alvo: {recusada}")

    # Filtros e exportacao.
    checar(all(i["usuario"] == "carol" for i in itens),
           "o filtro por usuario nao deveria vazar outros usuarios")
    r = adm.get("/api/admin/historico/exportar", params={"usuario_filtro":
                                                         "junior"})
    checar(r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf"),
           f"CSV deveria sair com BOM para o Excel: {r.status_code}")
    checar(b"Data e hora;Usuario" in r.content,
           f"CSV deveria ter o cabecalho: {r.content[:60]}")

    # ------------------------------------------------------------------
    # Protecao do ultimo administrador e desativacao

    r = carol.put(f"/api/admin/usuarios/{junior_id}",
                  json={"nome": "Junior", "admin": False, "ativo": False})
    checar(r.status_code == 200, f"desativar junior falhou: {r.text}")
    checar(junior.post("/api/login", json={"usuario": "junior",
                                           "senha": "segredo3"}
                       ).status_code == 401,
           "usuario desativado nao pode entrar")

    # Com dois admins, rebaixar um e permitido.
    r = adm.put(f"/api/admin/usuarios/{usuarios['carol']['id']}",
                json={"nome": "Carol", "admin": False, "ativo": True})
    checar(r.status_code == 200, f"rebaixar carol deveria passar: {r.text}")
    # Agora Weslley e o ultimo: o sistema nao pode ficar sem dono.
    r = adm.put(f"/api/admin/usuarios/{usuarios['weslley']['id']}",
                json={"nome": "Weslley", "admin": False, "ativo": True})
    checar(r.status_code == 422,
           f"rebaixar o ultimo admin deveria dar 422: {r.status_code}")
    r = adm.put(f"/api/admin/usuarios/{usuarios['weslley']['id']}",
                json={"nome": "Weslley", "admin": True, "ativo": False})
    checar(r.status_code == 422,
           f"desativar o ultimo admin deveria dar 422: {r.status_code}")
    checar(adm.get("/api/admin/usuarios").status_code == 200,
           "o ultimo admin deveria continuar administrando")

    # Trocar a senha derruba as sessoes abertas daquele usuario.
    carol_id = usuarios["carol"]["id"]
    checar(adm.put(f"/api/admin/usuarios/{carol_id}/senha",
                   json={"senha": "nova12345"}).status_code == 200,
           "trocar a senha da carol")
    checar(carol.get("/api/estado").json()["logado"] is False,
           "a sessao aberta deveria cair depois da troca de senha")
    checar(adm.put(f"/api/admin/usuarios/{carol_id}/senha",
                   json={"senha": "123"}).status_code == 422,
           "senha curta deveria dar 422")

    # ------------------------------------------------------------------
    # Nenhum admin remove o proprio acesso (evita se trancar para fora)

    r = adm.put(f"/api/admin/usuarios/{usuarios['weslley']['id']}",
                json={"nome": "Weslley", "admin": False, "ativo": True})
    checar(r.status_code == 422,
           f"tirar o proprio admin deveria dar 422: {r.status_code}")
    r = adm.put(f"/api/admin/usuarios/{usuarios['weslley']['id']}",
                json={"nome": "Weslley", "admin": True, "ativo": False})
    checar(r.status_code == 422,
           f"desativar a si mesmo deveria dar 422: {r.status_code}")
    checar(adm.get("/api/estado").json()["usuario"]["admin"] is True,
           "o admin deveria continuar admin depois das tentativas barradas")

    # ------------------------------------------------------------------
    # Consulta do historico: pagina absurda nao derruba (sem 500 por overflow)

    r = adm.get("/api/admin/historico",
                params={"pagina": 9223372036854775807})
    checar(r.status_code == 200,
           f"pagina gigante deveria ser presa, nao 500: {r.status_code}")

    # ------------------------------------------------------------------
    # Uma falha inesperada (500) ainda deixa rastro no historico

    original = auditoria.consultar

    def _quebrar(*args, **kwargs):
        raise RuntimeError("falha proposital de teste")

    # Cliente que devolve 500 em vez de propagar a excecao (o middleware grava
    # a linha e re-levanta; o TestClient padrao re-levantaria para o teste).
    adm_tolerante = TestClient(app, raise_server_exceptions=False)
    adm_tolerante.cookies.update(adm.cookies)
    auditoria.consultar = _quebrar
    try:
        r = adm_tolerante.get("/api/admin/historico")
        checar(r.status_code == 500,
               f"esperava 500 forcado: {r.status_code}")
    finally:
        auditoria.consultar = original
    quebrados = [i for i in eventos(adm, acao="admin.historico", limite=50)
                 if i["resultado"] == "erro" and i["http_status"] == 500]
    checar(quebrados,
           "um 500 numa rota auditada deveria virar linha 'erro' no historico")

    # ------------------------------------------------------------------
    # Quem so tem admin.historico filtra por usuario mesmo sem a lista

    so_hist = TestClient(app)
    r = adm.post("/api/admin/usuarios", json={
        "usuario": "auditor", "nome": "Auditor", "senha": "segredo7",
        "admin": False, "permissoes": ["admin.historico"]})
    checar(r.status_code == 200, f"criar auditor falhou: {r.text}")
    checar(so_hist.post("/api/login", json={"usuario": "auditor",
                                            "senha": "segredo7"}
                        ).status_code == 200, "auditor deveria entrar")
    checar(so_hist.get("/api/admin/usuarios").status_code == 403,
           "auditor nao alcanca a lista de usuarios")
    corpo = so_hist.get("/api/admin/historico").json()
    checar(corpo["usuarios"] and any(u["valor"] == "junior"
                                     for u in corpo["usuarios"]),
           f"o historico deveria trazer os usuarios para o filtro: "
           f"{corpo.get('usuarios')}")

    # ------------------------------------------------------------------
    # Propriedade das sessoes de trabalho e dos jobs

    propriedade_de_sessoes_e_jobs(app, adm)

    # ------------------------------------------------------------------
    # Sexta ferramenta: catalogo, padrao de usuario novo e negacao

    catalogo_e_permissoes_da_conciliacao(app, adm)

    # ------------------------------------------------------------------
    # Exportacao CSV nao corta em 1000 linhas (paginacao no servidor)

    # Grava direto no historico (login de verdade faria PBKDF2 mil vezes).
    for _ in range(1100):
        auditoria.registrar("sessao.login_negado", None,
                            detalhe="carga de teste",
                            resultado=auditoria.RESULTADO_NEGADO,
                            http_status=401)
    total = adm.get("/api/admin/historico").json()["total"]
    checar(total > 1000, f"esperava mais de 1000 eventos no total: {total}")
    r = adm.get("/api/admin/historico/exportar")
    linhas = r.content.decode("utf-8-sig").strip().split("\r\n")
    checar(len(linhas) - 1 >= total,
           f"o CSV deveria ter TODAS as {total} linhas, veio {len(linhas) - 1}")

    print("OK - permissoes e historico web (abas e acoes por usuario, 403 em "
          "aba e acao negadas, bloqueio da correcao em lote, mudanca de "
          "permissao na hora, ultimo administrador protegido, desativacao, "
          "troca de senha, propriedade de sessoes/jobs e trilha de "
          "entrada/navegacao/acoes/negadas/saida) passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
