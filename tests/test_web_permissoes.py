"""Versao web — permissoes por usuario e historico de acessos.

Sobe o app FastAPI com TestClient e exercita: bootstrap do admin, criacao de
um segundo administrador e de um usuario comum com permissoes recortadas,
bloqueio 403 nas abas e nas acoes que ele nao alcanca, a tentativa de
escalacao de privilegio (corrigir em LOTE tendo so a permissao de corrigir
uma nota), o efeito imediato de uma mudanca de permissao, a protecao do
ultimo administrador, a desativacao derrubando o login, e o historico
respondendo quando entrou, o que acessou, o que fez e quando saiu (inclusive
as tentativas negadas). Usa dados_web isolado em pasta temporaria
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
          "troca de senha e trilha de entrada/navegacao/acoes/negadas/saida) "
          "passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
