"""Versao web — Patrimonio (setima ferramenta).

Exercita o portao de acesso (401/403 com trilha), cadastro, movimentacao,
a separacao entre movimentar e BAIXAR, inventario, filtros, exportacao,
termo em PDF e a trilha de uso.
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_pat_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.core import patrimonio as pt  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402

ADMIN = {"usuario": "weslley", "nome": "Weslley", "senha": "segredo1"}
# Quem cadastra e movimenta, mas NAO pode dar baixa.
OPERADOR = {"usuario": "ana", "nome": "Ana", "senha": "segredo2"}
# Quem so consulta.
CONSULTA = {"usuario": "bruno", "nome": "Bruno", "senha": "segredo3"}


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def entrar(app, credenciais: dict) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post("/api/login", json={"usuario": credenciais["usuario"],
                                         "senha": credenciais["senha"]})
    checar(r.status_code == 200, f"login {credenciais['usuario']}: {r.text}")
    return cliente


def eventos(adm, **filtros) -> list[dict]:
    r = adm.get("/api/admin/historico", params={"limite": 300, **filtros})
    checar(r.status_code == 200, r.status_code)
    return r.json()["itens"]


def main() -> int:
    app = criar_app()
    adm = TestClient(app)
    checar(adm.post("/api/bootstrap", json=ADMIN).status_code == 200,
           "bootstrap")

    # ------------------------------------------------------------------
    # Sem login: 401 antes de qualquer checagem de permissao

    anonimo = TestClient(app)
    for caminho in ("/api/patrimonio/resumo", "/api/patrimonio/bens",
                    "/api/patrimonio/catalogo"):
        checar(anonimo.get(caminho).status_code == 401,
               f"{caminho} sem login")

    # ------------------------------------------------------------------
    # Com login, sem a aba: 403 e trilha

    r = adm.post("/api/admin/usuarios", json={
        **OPERADOR, "admin": False, "permissoes": ["aba.conferencia"]})
    checar(r.status_code == 200, r.text[:160])
    ana_id = r.json()["id"]
    ana = entrar(app, OPERADOR)
    checar(ana.get("/api/patrimonio/bens").status_code == 403, "sem a aba")
    # As rotas de LEITURA usam `exigir_aba`, que nao audita de proposito: a
    # tela recarrega a lista o tempo todo e isso afogaria a trilha. Quem
    # registra negativa e' a MUTACAO, que passa por `acesso(<slug>)`.
    r = ana.post("/api/patrimonio/locais", json={"nome": "Tentativa"})
    checar(r.status_code == 403, f"cadastrar sem a aba: {r.status_code}")
    negados = [e for e in eventos(adm, usuario_filtro="ana")
               if e["resultado"] == "negado"]
    checar(negados and all(e["http_status"] == 403 for e in negados),
           f"a tentativa negada deveria estar na trilha com 403: {negados[:1]}")

    # ------------------------------------------------------------------
    # Catalogo: os 6 slugs existem e o padrao concede so a aba

    catalogo = adm.get("/api/admin/usuarios").json()
    slugs = {i["slug"] for g in catalogo["catalogo"] for i in g["itens"]}
    esperados = {"aba.patrimonio", "patrimonio.cadastrar",
                 "patrimonio.movimentar", "patrimonio.baixar",
                 "patrimonio.inventariar", "patrimonio.exportar"}
    checar(not (esperados - slugs), f"slugs ausentes: {esperados - slugs}")
    padrao = set(catalogo["padrao_novo"])
    checar("aba.patrimonio" in padrao, "o padrao deveria conceder a aba")
    sobrando = [s for s in esperados
                if s != "aba.patrimonio" and s in padrao]
    checar(not sobrando,
           f"o padrao NAO podia conceder {sobrando}: mexer no acervo e dar "
           f"baixa exigem liberacao explicita")

    # Operador: tudo menos baixar.
    adm.put(f"/api/admin/usuarios/{ana_id}/permissoes", json={
        "permissoes": ["aba.patrimonio", "patrimonio.cadastrar",
                       "patrimonio.movimentar", "patrimonio.inventariar",
                       "patrimonio.exportar"]})

    r = adm.post("/api/admin/usuarios", json={
        **CONSULTA, "admin": False, "permissoes": ["aba.patrimonio"]})
    checar(r.status_code == 200, r.text[:160])
    bruno = entrar(app, CONSULTA)

    # ------------------------------------------------------------------
    # Catalogo da ferramenta e resumo vazio

    catalogo = ana.get("/api/patrimonio/catalogo").json()
    checar("Notebook" in catalogo["tipos"], catalogo["tipos"][:4])
    juntos = " ".join(catalogo["tipos"]).lower()
    for fora in ("epi", "botina", "capacete"):
        checar(fora not in juntos,
               f"'{fora}' e' dominio de transportadora, nao de contabilidade")
    checar(any(m["chave"] == pt.MOV_BAIXA for m in catalogo["movimentos"]),
           "baixa deveria estar no catalogo de movimentos")

    resumo = ana.get("/api/patrimonio/resumo").json()
    checar(resumo["total"] == 0, resumo)
    checar(resumo["valor_total"]["centavos"] == 0, resumo["valor_total"])

    # ------------------------------------------------------------------
    # Cadastro

    checar(bruno.post("/api/patrimonio/locais",
                      json={"nome": "Sala 1"}).status_code == 403,
           "quem so consulta nao cadastra")

    sala = ana.post("/api/patrimonio/locais",
                    json={"nome": "Sala Fiscal"}).json()["id"]
    maria = ana.post("/api/patrimonio/pessoas", json={
        "nome": "Maria Silva", "cpf": "529.982.247-25",
        "setor": "Fiscal"}).json()["id"]

    r = ana.post("/api/patrimonio/pessoas", json={"nome": "X", "cpf": "123"})
    checar(r.status_code == 422, f"CPF invalido: {r.status_code}")
    checar(r.json()["detail"]["code"] == pt.CPF_INVALIDO, r.json())

    r = ana.post("/api/patrimonio/bens", json={
        "descricao": "Notebook Dell Latitude", "tipo": "Notebook",
        "conservacao": "novo", "valor_aquisicao": "4.500,00",
        "local_id": sala})
    checar(r.status_code == 200, f"cadastrar bem: {r.text[:200]}")
    bem = r.json()
    checar(bem["etiqueta"] == "JBF-000001", bem["etiqueta"])

    periferico = ana.post("/api/patrimonio/bens", json={
        "descricao": "Fonte do notebook", "tipo": "Outro",
        "pai_id": bem["id"]}).json()
    checar(periferico["etiqueta"] == "PER-000001", periferico["etiqueta"])

    r = ana.post("/api/patrimonio/bens", json={"tipo": "Notebook"})
    checar(r.status_code == 422, f"descricao obrigatoria: {r.status_code}")

    # ------------------------------------------------------------------
    # Movimentacao

    r = bruno.post(f"/api/patrimonio/bens/{bem['id']}/movimentar",
                   json={"tipo": pt.MOV_ATRIBUICAO, "pessoa_id": maria})
    checar(r.status_code == 403, f"consulta nao movimenta: {r.status_code}")

    r = ana.post(f"/api/patrimonio/bens/{bem['id']}/movimentar",
                 json={"tipo": pt.MOV_ATRIBUICAO, "pessoa_id": maria,
                       "observacao": "Entrega inicial."})
    checar(r.status_code == 200, f"atribuir: {r.text[:200]}")
    checar(r.json()["situacao_nova"] == pt.SITUACAO_EM_USO, r.json())

    # Atribuir de novo sem devolver.
    r = ana.post(f"/api/patrimonio/bens/{bem['id']}/movimentar",
                 json={"tipo": pt.MOV_ATRIBUICAO, "pessoa_id": maria})
    checar(r.status_code == 409, f"ja tem responsavel: {r.status_code}")

    # Atribuicao sem pessoa.
    outro = ana.post("/api/patrimonio/bens", json={
        "descricao": "Monitor 24", "tipo": "Monitor"}).json()
    r = ana.post(f"/api/patrimonio/bens/{outro['id']}/movimentar",
                 json={"tipo": pt.MOV_ATRIBUICAO})
    checar(r.status_code == 422, f"atribuicao exige pessoa: {r.status_code}")

    # BAIXA exige slug proprio: o operador movimenta, mas nao baixa.
    r = ana.post(f"/api/patrimonio/bens/{outro['id']}/movimentar",
                 json={"tipo": pt.MOV_BAIXA, "observacao": "Quebrado."})
    checar(r.status_code == 403,
           f"baixar sem patrimonio.baixar deveria dar 403: {r.status_code}")

    # O admin pode.
    r = adm.post(f"/api/patrimonio/bens/{outro['id']}/movimentar",
                 json={"tipo": pt.MOV_BAIXA, "observacao": "Tela quebrada."})
    checar(r.status_code == 200, f"admin baixa: {r.text[:200]}")
    r = adm.post(f"/api/patrimonio/bens/{outro['id']}/movimentar",
                 json={"tipo": pt.MOV_MANUTENCAO, "observacao": "x"})
    checar(r.status_code == 409, f"baixa e terminal: {r.status_code}")
    checar(r.json()["detail"]["code"] == pt.BEM_BAIXADO, r.json())

    # Baixa sem justificativa.
    terceiro = ana.post("/api/patrimonio/bens", json={
        "descricao": "Teclado", "tipo": "Outro"}).json()
    r = adm.post(f"/api/patrimonio/bens/{terceiro['id']}/movimentar",
                 json={"tipo": pt.MOV_BAIXA})
    checar(r.status_code == 409, f"baixa sem justificativa: {r.status_code}")
    checar(r.json()["detail"]["code"] == pt.JUSTIFICATIVA_OBRIGATORIA,
           r.json())

    # ------------------------------------------------------------------
    # Detalhe com historico e proveniencia da decisao

    d = ana.get(f"/api/patrimonio/bens/{bem['id']}").json()
    checar(d["responsavel"]["nome"] == "Maria Silva", d["responsavel"])
    checar(d["situacao_rotulo"] == "Em uso", d["situacao_rotulo"])
    checar(len(d["movimentacoes"]) == 2, d["movimentacoes"])
    checar(all(m["usuario"] == "ana" for m in d["movimentacoes"]),
           "o autor vem da sessao autenticada")
    checar(len(d["perifericos"]) == 1, d["perifericos"])
    checar(d["valor_aquisicao"]["texto"].startswith("R$"),
           d["valor_aquisicao"])

    # Leitura pela etiqueta (o QR colado no equipamento).
    r = ana.get("/api/patrimonio/etiqueta/jbf-000001")
    checar(r.status_code == 200 and r.json()["id"] == bem["id"], r.text[:120])
    checar(ana.get("/api/patrimonio/etiqueta/JBF-999999").status_code == 404,
           "etiqueta inexistente")

    # ------------------------------------------------------------------
    # Filtros e listagem

    lista = ana.get("/api/patrimonio/bens").json()
    checar(lista["total"] == 3,
           f"o baixado sai da lista por padrao: {lista['total']}")
    checar(ana.get("/api/patrimonio/bens",
                   params={"incluir_baixados": True}).json()["total"] == 4,
           "com incluir_baixados o total volta")
    checar(ana.get("/api/patrimonio/bens",
                   params={"situacao": "em_uso"}).json()["total"] == 1,
           "filtro por situacao")
    checar(ana.get("/api/patrimonio/bens",
                   params={"pessoa_id": maria}).json()["total"] == 1,
           "filtro por responsavel")
    checar(ana.get("/api/patrimonio/bens",
                   params={"texto": "Latitude"}).json()["total"] == 1, "busca")
    r = ana.get("/api/patrimonio/bens", params={"situacao": "inventada"})
    checar(r.status_code == 422, f"situacao invalida: {r.status_code}")

    resumo = ana.get("/api/patrimonio/resumo").json()
    checar(resumo["total"] == 3 and resumo["baixados"] == 1, resumo)
    lista_resumo = ana.get("/api/patrimonio/bens").json()["total"]
    checar(resumo["total"] == lista_resumo,
           "resumo e lista tem de contar o mesmo universo")

    # ------------------------------------------------------------------
    # Inventario

    r = bruno.post("/api/patrimonio/inventario", json={})
    checar(r.status_code == 403, "consulta nao abre inventario")
    inv = ana.post("/api/patrimonio/inventario",
                   json={"observacao": "Conferência anual."}).json()["id"]
    r = ana.post("/api/patrimonio/inventario", json={})
    checar(r.status_code == 409, f"uma sessao por vez: {r.status_code}")

    atual = ana.get("/api/patrimonio/inventario").json()
    checar(atual["aberto"]["total"] == 3,
           f"o baixado nao entra: {atual['aberto']['total']}")

    ana.post(f"/api/patrimonio/inventario/{inv}/conferir",
             json={"bem_id": bem["id"], "resultado": "localizado"})
    r = ana.post(f"/api/patrimonio/inventario/{inv}/conferir",
                 json={"bem_id": bem["id"], "resultado": "sumiu"})
    checar(r.status_code == 409, f"resultado invalido: {r.status_code}")
    r = ana.post(f"/api/patrimonio/inventario/{inv}/conferir",
                 json={"bem_id": outro["id"], "resultado": "localizado"})
    checar(r.status_code == 404, "bem baixado nao esta no inventario")

    fechado = ana.post(f"/api/patrimonio/inventario/{inv}/fechar",
                       json={}).json()
    checar(fechado["estado"] == "fechado", fechado)
    checar(fechado["contagens"].get("localizado") == 1, fechado["contagens"])
    checar(ana.get("/api/patrimonio/inventario").json()["aberto"] is None,
           "nao ha sessao aberta depois de fechar")

    # ------------------------------------------------------------------
    # Saidas

    r = bruno.post("/api/patrimonio/exportar")
    checar(r.status_code == 403, "consulta nao exporta")
    r = ana.post("/api/patrimonio/exportar")
    checar(r.status_code == 200, f"exportar: {r.status_code} {r.text[:200]}")
    checar(r.content[:2] == b"PK", "a relacao precisa ser um xlsx")
    checar("patrimonio_" in r.headers.get("content-disposition", ""),
           r.headers.get("content-disposition"))

    r = ana.post(f"/api/patrimonio/bens/{bem['id']}/termo")
    checar(r.status_code == 200, f"termo: {r.status_code} {r.text[:200]}")
    checar(r.content[:4] == b"%PDF", "o termo precisa ser um PDF")
    checar("termo_JBF-000001" in r.headers.get("content-disposition", ""),
           r.headers.get("content-disposition"))

    # Bem sem responsavel nao gera termo.
    r = ana.post(f"/api/patrimonio/bens/{terceiro['id']}/termo")
    checar(r.status_code == 409, f"sem responsavel: {r.status_code}")
    checar(r.json()["detail"]["code"] == "SEM_RESPONSAVEL", r.json())

    # ------------------------------------------------------------------
    # Trilha: ok, negado e erro

    itens = eventos(adm, usuario_filtro="ana")
    for acao in ("patrimonio.cadastrar", "patrimonio.movimentar",
                 "patrimonio.inventariar", "patrimonio.exportar",
                 "patrimonio.termo"):
        checar(any(e["acao"] == acao and e["resultado"] == "ok"
                   for e in itens), f"{acao} deveria estar na trilha")
    checar(any(e["acao"] == "patrimonio.baixar" and e["resultado"] == "negado"
               for e in itens),
           "a tentativa de baixa sem permissao tem de ficar registrada")
    baixas = [e for e in eventos(adm, usuario_filtro="weslley")
              if e["acao"] == "patrimonio.baixar" and e["resultado"] == "ok"]
    checar(baixas, "a baixa do admin deveria estar na trilha")

    print("OK - patrimonio web (401 sem login, 403 sem a aba com trilha, "
          "catalogo de contabilidade, cadastro com etiqueta sequencial, "
          "periferico, movimentacao com um responsavel por vez, baixa "
          "separada por permissao propria e terminal, inventario com sessao "
          "unica, filtros, relacao em Excel e termo em PDF) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
