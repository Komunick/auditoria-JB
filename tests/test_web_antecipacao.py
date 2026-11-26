"""Versao web — Antecipacao e DIFAL do ICMS-BA (spec 027).

Portao de acesso (401/403 com trilha), separacao importar/revisar/aprovar,
importacao de varios XML de uma vez, duplicidade, revisao das excecoes,
aprovacao, totais por empresa e periodo, exportacao, DANFE, chaves coladas,
calculadora e tabela de aliquotas.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_antecipacao_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from auditoria_fiscal.web.servidor import criar_app  # noqa: E402

import nfe_sintetica as fab  # noqa: E402

API = "/api/antecipacao"
ADMIN = {"usuario": "weslley", "nome": "Weslley", "senha": "segredo1"}
# Importa e revisa, mas NAO aprova nem mexe na tabela.
FISCAL = {"usuario": "ana", "nome": "Ana", "senha": "segredo2"}
# So consulta.
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


def enviar(cliente, xmls: list[tuple[str, bytes]], **campos):
    return cliente.post(
        f"{API}/importar", data=campos,
        files=[("arquivos", (nome, conteudo, "text/xml"))
               for nome, conteudo in xmls])


def eventos(adm, **filtros) -> list[dict]:
    r = adm.get("/api/admin/historico", params={"limite": 300, **filtros})
    checar(r.status_code == 200, r.status_code)
    return r.json()["itens"]


def main() -> int:
    app = criar_app()
    adm = TestClient(app)
    checar(adm.post("/api/bootstrap", json=ADMIN).status_code == 200, "bootstrap")

    # ------------------------------------------------------------------
    # Sem login: 401

    anonimo = TestClient(app)
    for caminho in (f"{API}/catalogo", f"{API}/notas", f"{API}/resumo",
                    f"{API}/aliquotas"):
        checar(anonimo.get(caminho).status_code == 401, f"{caminho} sem login")
    checar(enviar(anonimo, [("a.xml", fab.nota_sp_com_destaque())],
                  metodo="por_dentro").status_code == 401, "importar sem login")

    # ------------------------------------------------------------------
    # Catalogo de permissoes: slugs novos, nenhum no padrao de usuario novo

    usuarios = adm.get("/api/admin/usuarios").json()
    slugs = {i["slug"] for g in usuarios["catalogo"] for i in g["itens"]}
    esperados = {"aba.antecipacao", "antecipacao.importar",
                 "antecipacao.revisar", "antecipacao.aprovar",
                 "antecipacao.configurar", "antecipacao.exportar"}
    checar(not (esperados - slugs), f"slugs ausentes: {esperados - slugs}")
    checar(not (esperados & set(usuarios["padrao_novo"])),
           "permissao nova nao entra sozinha no padrao de usuario novo")

    # Com login, sem a aba: 403 e trilha da tentativa.
    r = adm.post("/api/admin/usuarios", json={
        **FISCAL, "admin": False, "permissoes": ["aba.conferencia"]})
    checar(r.status_code == 200, r.text[:160])
    ana_id = r.json()["id"]
    ana = entrar(app, FISCAL)
    checar(ana.get(f"{API}/notas").status_code == 403, "sem a aba")
    r = enviar(ana, [("a.xml", fab.nota_sp_com_destaque())], metodo="por_dentro")
    checar(r.status_code == 403, f"importar sem a aba: {r.status_code}")
    negados = [e for e in eventos(adm, usuario_filtro="ana")
               if e["resultado"] == "negado"]
    checar(negados and negados[0]["http_status"] == 403,
           f"a tentativa negada deveria estar na trilha: {negados[:1]}")

    adm.put(f"/api/admin/usuarios/{ana_id}/permissoes", json={
        "permissoes": ["aba.antecipacao", "antecipacao.importar",
                       "antecipacao.revisar", "antecipacao.exportar"]})
    r = adm.post("/api/admin/usuarios", json={
        **CONSULTA, "admin": False, "permissoes": ["aba.antecipacao"]})
    checar(r.status_code == 200, r.text[:160])
    bruno = entrar(app, CONSULTA)

    # ------------------------------------------------------------------
    # Catalogo da ferramenta

    cat = ana.get(f"{API}/catalogo").json()
    checar({m["chave"] for m in cat["metodos"]}
           == {"por_dentro", "diferenca_simples"}, cat["metodos"])
    checar(cat["configuracao"]["metodo_padrao"] == "por_dentro", cat)
    checar("BA" not in cat["ufs_origem"] and len(cat["ufs_origem"]) == 26,
           cat["ufs_origem"])

    # ------------------------------------------------------------------
    # Importacao em lote: 3 exemplos + duplicada + fora do escopo + lixo

    checar(enviar(bruno, [("a.xml", fab.nota_sp_com_destaque())],
                  metodo="por_dentro").status_code == 403,
           "quem so consulta nao importa")
    r = enviar(ana, [("a.xml", fab.nota_sp_com_destaque())])
    checar(r.status_code == 422 and r.json()["detail"]["code"] == "METODO_INVALIDO",
           f"sem metodo escolhido: {r.status_code} {r.text[:200]}")

    lote = [
        ("sp.xml", fab.nota_sp_com_destaque(1)),
        ("go.xml", fab.nota_go_sem_destaque(2)),
        ("importado.xml", fab.nota_importado_sem_destaque(3)),
        ("sp-de-novo.xml", fab.nota_sp_com_destaque(1)),
        ("interna.xml", fab.xml_nfe([fab.item(p_icms="18.00", v_icms="180.00")],
                                    uf="BA", numero=8)),
        ("lixo.xml", b"isto nao e xml"),
    ]
    r = enviar(ana, lote, metodo="por_dentro", finalidade="revenda",
               presuncao="1")
    checar(r.status_code == 200, f"importar: {r.status_code} {r.text[:300]}")
    corpo = r.json()
    checar(corpo["contagem"] == {"importada": 3, "duplicada": 1,
                                 "recusada": 1, "invalido": 1},
           corpo["contagem"])
    por_arquivo = {i["arquivo"]: i for i in corpo["itens"]}
    checar(por_arquivo["sp.xml"]["a_recolher"]["centavos"] == 16981,
           por_arquivo["sp.xml"])
    checar(por_arquivo["go.xml"]["a_recolher"]["centavos"] == 10692,
           por_arquivo["go.xml"])
    checar(por_arquivo["importado.xml"]["a_recolher"]["centavos"] == 20755,
           por_arquivo["importado.xml"])
    checar("já importada" in por_arquivo["sp-de-novo.xml"]["mensagem"].lower(),
           por_arquivo["sp-de-novo.xml"])
    checar("fora do escopo" in por_arquivo["interna.xml"]["mensagem"].lower(),
           por_arquivo["interna.xml"])

    origens = os.path.join(_TMP, "antecipacao", "origens")
    checar(len(os.listdir(origens)) == 3,
           f"so as 3 notas importadas guardam XML: {os.listdir(origens)}")

    notas = ana.get(f"{API}/notas").json()
    checar(notas["total"] == 3, notas["total"])
    ids = {n["numero"]: n["id"] for n in notas["itens"]}
    checar(all(n["estado"] == "em_revisao" for n in notas["itens"]),
           "nota importada nasce em revisao, nunca aprovada")

    # A trilha de uso registra a importacao sem valores.
    feitos = [e for e in eventos(adm, usuario_filtro="ana")
              if e["acao"] == "antecipacao.importar" and e["resultado"] == "ok"]
    checar(feitos and "importada=3" in feitos[0]["detalhe"], feitos[:1])

    # ------------------------------------------------------------------
    # Detalhe: memoria completa e grupos por CFOP e aliquota

    d = ana.get(f"{API}/notas/{ids['1']}").json()
    memoria = d["lista_itens"][0]["memoria"]
    checar((memoria["valor_operacao"], memoria["credito"], memoria["divisor"],
            memoria["valor_sem_icms"], memoria["base_calculo"],
            memoria["icms_interno"], memoria["a_recolher"])
           == ("1000.00", "70.00", "0.795", "930.00", "1169.81", "239.81",
               "169.81"), memoria)
    checar(memoria["comparativo"]["a_recolher"] == "135.00", memoria)
    checar(d["grupos"][0]["cfop"] == "6102" and d["grupos"][0]["aliquota"] == "7"
           and d["grupos"][0]["a_recolher"]["centavos"] == 16981, d["grupos"])
    checar(d["tem_xml"] is True, "o XML da nota deveria estar guardado")
    checar(ana.get(f"{API}/notas/999999").status_code == 404, "nota inexistente")

    # ------------------------------------------------------------------
    # Revisao: quem so consulta nao muda; revision errada e' 409

    r = bruno.put(f"{API}/notas/{ids['1']}", json={
        "revision": d["revision"], "metodo": "diferenca_simples"})
    checar(r.status_code == 403, f"consulta nao revisa: {r.status_code}")
    r = ana.put(f"{API}/notas/{ids['1']}", json={
        "revision": d["revision"] + 5, "metodo": "diferenca_simples"})
    checar(r.status_code == 409
           and r.json()["detail"]["code"] == "REVISION_DESATUALIZADA"
           and r.json()["detail"]["current_revision"] == d["revision"], r.text)
    r = ana.put(f"{API}/notas/{ids['1']}", json={
        "revision": d["revision"], "metodo": "diferenca_simples"})
    checar(r.status_code == 200 and r.json()["a_recolher"]["centavos"] == 13500,
           r.text[:200])
    d = ana.put(f"{API}/notas/{ids['1']}", json={
        "revision": r.json()["revision"], "metodo": "por_dentro"}).json()
    checar(d["a_recolher"]["centavos"] == 16981, d["a_recolher"])

    # Nota com excecao: ST fica aguardando decisao.
    mista = fab.xml_nfe([
        fab.item(v_prod="1000.00", p_icms="7.00", v_icms="70.00"),
        fab.item(v_prod="500.00", grupo="ICMS10", cst="10", p_icms="7.00",
                 v_icms="35.00", cfop="6403",
                 descricao="=HYPERLINK(\"http://x\")"),
    ], uf="SP", numero=4)
    r = enviar(ana, [("mista.xml", mista)], metodo="por_dentro",
               finalidade="revenda")
    checar(r.json()["itens"][0]["pendentes"] == 1, r.json())
    mista_id = r.json()["itens"][0]["nota_id"]
    dm = ana.get(f"{API}/notas/{mista_id}").json()
    st = dm["lista_itens"][1]
    checar(st["decisao"] == "" and any(p["codigo"] == "ICMS_ST"
                                       for p in st["pendencias"]), st)

    # ------------------------------------------------------------------
    # Aprovacao: slug proprio, regime obrigatorio, nada pendente

    r = ana.post(f"{API}/notas/{ids['1']}/aprovar", json={"revision": d["revision"]})
    checar(r.status_code == 403, f"quem revisa nao aprova: {r.status_code}")
    r = adm.post(f"{API}/notas/{ids['1']}/aprovar", json={"revision": d["revision"]})
    checar(r.status_code == 409
           and r.json()["detail"]["code"] == "REGIME_NAO_INFORMADO", r.text)

    checar(bruno.put(f"{API}/empresas/{fab.CNPJ_DEST}",
                     json={"regime": "simples_nacional"}).status_code == 403,
           "consulta nao define regime")
    r = ana.put(f"{API}/empresas/{fab.CNPJ_DEST}", json={"regime": "inventado"})
    checar(r.status_code == 422, f"regime invalido: {r.status_code}")
    r = ana.put(f"{API}/empresas/{fab.CNPJ_DEST}",
                json={"regime": "simples_nacional"})
    checar(r.status_code == 200 and r.json()["regime"] == "simples_nacional",
           r.text)

    r = adm.post(f"{API}/notas/{mista_id}/aprovar", json={"revision": dm["revision"]})
    checar(r.status_code == 409
           and r.json()["detail"]["code"] == "ITENS_SEM_DECISAO", r.text)
    r = ana.put(f"{API}/notas/{mista_id}/itens", json={
        "revision": dm["revision"], "item_ids": [st["id"]],
        "decisao": "excluir"})
    checar(r.status_code == 422
           and r.json()["detail"]["code"] == "MOTIVO_OBRIGATORIO", r.text)
    r = ana.put(f"{API}/notas/{mista_id}/itens", json={
        "revision": dm["revision"], "item_ids": [st["id"]],
        "decisao": "excluir", "motivo": "ST retida na origem (Anexo 1)"})
    checar(r.status_code == 200 and r.json()["pendentes"] == 0, r.text[:200])
    dm = r.json()
    checar(dm["lista_itens"][1]["decisao_por"] == "ana",
           "quem decide vem da sessao, nao do corpo")

    for nota_id in (ids["1"], mista_id):
        atual = adm.get(f"{API}/notas/{nota_id}").json()
        r = adm.post(f"{API}/notas/{nota_id}/aprovar",
                     json={"revision": atual["revision"]})
        checar(r.status_code == 200 and r.json()["estado"] == "aprovada",
               f"aprovar {nota_id}: {r.status_code} {r.text[:200]}")
        checar(r.json()["aprovada_por"] == "weslley", r.json()["aprovada_por"])

    aprovada = adm.get(f"{API}/notas/{ids['1']}").json()
    r = ana.put(f"{API}/notas/{ids['1']}", json={
        "revision": aprovada["revision"], "metodo": "diferenca_simples"})
    checar(r.status_code == 409 and r.json()["detail"]["code"] == "NOTA_APROVADA",
           r.text)
    r = ana.post(f"{API}/notas/{ids['1']}/reabrir", json={
        "revision": aprovada["revision"], "motivo": "conferir de novo"})
    checar(r.status_code == 403, "reabrir exige a permissao de aprovar")

    # ------------------------------------------------------------------
    # Totais por empresa e periodo

    resumo = bruno.get(f"{API}/resumo", params={"competencia": "10/2026"}).json()
    checar(len(resumo["itens"]) == 1, resumo)
    linha = resumo["itens"][0]
    # Aprovadas: nota 1 (169,81) + item limpo da mista (169,81).
    checar(linha["aprovado"]["centavos"] == 33962, linha["aprovado"])
    checar(linha["em_revisao"]["centavos"] == 10692 + 20755, linha["em_revisao"])
    checar(linha["reducao_simulada"]["centavos"] == 6792
           and linha["aprovado_com_reducao"]["centavos"] == 27170, linha)
    checar(linha["vencimento_referencia"] == "2026-11-25", linha)
    checar(bruno.get(f"{API}/resumo",
                     params={"competencia": "xx"}).status_code == 422,
           "competencia invalida no filtro")

    # ------------------------------------------------------------------
    # Exportacao: permissao propria; texto de XML nao vira formula

    checar(bruno.post(f"{API}/exportar").status_code == 403,
           "consulta nao exporta")
    r = ana.post(f"{API}/exportar", params={"competencia": "2026-10"})
    checar(r.status_code == 200, f"exportar: {r.status_code} {r.text[:200]}")
    livro = load_workbook(io.BytesIO(r.content))
    checar(livro.sheetnames == ["Itens", "Totais", "Metadados"], livro.sheetnames)
    aba = livro["Itens"]
    checar(aba.max_row == 6, f"5 itens + cabecalho: {aba.max_row}")
    cabecalho = [c.value for c in aba[1]]
    linhas = [dict(zip(cabecalho, [c.value for c in linha]))
              for linha in aba.iter_rows(min_row=2)]
    sp = next(l for l in linhas if l["UF origem"] == "SP"
              and l["Nota"] == "1/1")
    checar(float(sp["A recolher"]) == 169.81
           and float(sp["Base de cálculo"]) == 1169.81
           and float(sp["Pelo outro método"]) == 135.0, sp)
    perigoso = next(l for l in linhas if "HYPERLINK" in str(l["Produto"]))
    checar(str(perigoso["Produto"]).startswith("'="),
           f"descricao que comeca por = tem de ser neutralizada: {perigoso['Produto']!r}")
    checar(perigoso["Decisão"] == "Fora do cálculo"
           and perigoso["Motivo da decisão"], perigoso)
    totais = livro["Totais"]
    checar(float(totais.cell(row=2, column=7).value) == 339.62,
           totais.cell(row=2, column=7).value)

    # ------------------------------------------------------------------
    # DANFE a partir do XML guardado

    # O XML enxuto dos testes nao tem o que o DANFE exige: erro explicito.
    r = bruno.get(f"{API}/notas/{ids['1']}/danfe")
    checar(r.status_code == 422
           and r.json()["detail"]["code"] == "DANFE_INDISPONIVEL", r.text[:200])
    # Com um XML completo (o mesmo do teste do DANFE, com chave valida) sai PDF.
    from test_danfe import CHAVE as chave_modelo, XML as xml_modelo
    chave_boa = chave_modelo[:43] + fab._dv(chave_modelo[:43])
    completo = xml_modelo.replace(chave_modelo, chave_boa).encode("utf-8")
    r = enviar(ana, [("completo.xml", completo)], metodo="por_dentro",
               finalidade="revenda")
    checar(r.json()["contagem"] == {"importada": 1}, r.json())
    completa_id = r.json()["itens"][0]["nota_id"]
    r = bruno.get(f"{API}/notas/{completa_id}/danfe")
    checar(r.status_code == 200 and r.content[:4] == b"%PDF",
           f"danfe do XML completo: {r.status_code} {r.content[:60]!r}")
    baixou = [e for e in eventos(adm, usuario_filtro="bruno")
              if e["acao"] == "antecipacao.danfe" and e["resultado"] == "ok"]
    checar(baixou, "o download do DANFE deveria estar na trilha de uso")
    atual = ana.get(f"{API}/notas/{completa_id}").json()
    r = ana.post(f"{API}/notas/{completa_id}/excluir",
                 json={"revision": atual["revision"],
                       "motivo": "nota usada so para conferir o DANFE"})
    checar(r.status_code == 200, r.text)

    # ------------------------------------------------------------------
    # Exclusao de nota em revisao: some a nota e o XML dela

    go = ana.get(f"{API}/notas/{ids['2']}").json()
    r = ana.post(f"{API}/notas/{ids['2']}/excluir",
                 json={"revision": go["revision"], "motivo": ""})
    checar(r.status_code == 422, "excluir sem motivo")
    r = ana.post(f"{API}/notas/{ids['2']}/excluir",
                 json={"revision": go["revision"],
                       "motivo": "XML enviado por engano"})
    checar(r.status_code == 200, r.text)
    checar(len(os.listdir(origens)) == 3,
           f"3 notas restantes, 3 XML: {os.listdir(origens)}")
    checar(ana.get(f"{API}/notas").json()["total"] == 3, "nota excluida")
    r = ana.post(f"{API}/notas/{ids['1']}/excluir",
                 json={"revision": aprovada["revision"], "motivo": "apagar a aprovada"})
    checar(r.status_code == 409, "nota aprovada nao e' excluida")

    # ------------------------------------------------------------------
    # Chaves coladas: valida, aponta repetida e o que falta de XML

    nova = fab.chave("PE", 77)
    texto = (f"{fab.chave('SP', 1)}\n{nova}, {nova}\n123\n"
             f"{fab.chave('BA', 5)}")
    r = bruno.post(f"{API}/chaves/conferir", json={"texto": texto})
    checar(r.status_code == 200, r.text)
    situacoes = [i["situacao"] for i in r.json()["itens"]]
    checar(situacoes == ["importada", "falta_xml", "repetida", "invalida",
                         "fora_do_escopo"], situacoes)
    checar(r.json()["itens"][1]["uf"] == "PE"
           and r.json()["itens"][1]["numero"] == "77", r.json()["itens"][1])

    # ------------------------------------------------------------------
    # Calculadora (lancamento manual para conferencia): nao grava nada

    antes = ana.get(f"{API}/notas").json()["total"]
    r = bruno.post(f"{API}/simular", json={
        "valor_operacao": "1.000,00", "uf_origem": "GO", "data": "05/10/2026"})
    checar(r.status_code == 200, r.text)
    sim = r.json()
    checar(sim["credito"] == "120.00" and sim["tipo_credito"] == "calculado"
           and sim["metodos"]["por_dentro"]["a_recolher"] == "106.92"
           and sim["metodos"]["diferenca_simples"]["a_recolher"] == "85.00", sim)
    r = bruno.post(f"{API}/simular", json={
        "valor_operacao": "1000", "uf_origem": "SP", "icms_destacado": "70",
        "data": "2026-10-05"})
    checar(r.json()["metodos"]["por_dentro"]["a_recolher"] == "169.81", r.text)
    r = bruno.post(f"{API}/simular", json={
        "valor_operacao": "1000", "uf_origem": "BA"})
    checar(r.status_code == 422 and r.json()["detail"]["code"] == "ORIGEM_BA",
           r.text)
    r = bruno.post(f"{API}/simular", json={
        "valor_operacao": "", "uf_origem": "SP"})
    checar(r.status_code == 422, "valor vazio")
    checar(ana.get(f"{API}/notas").json()["total"] == antes,
           "a calculadora nao pode gravar nota")

    # ------------------------------------------------------------------
    # Tabela de aliquotas e parametros: so quem configura

    nova_aliquota = {"tipo": "interna", "ncm": "3924", "percentual": "12",
                     "vigencia_inicio": "01/01/2026",
                     "base_legal": "Norma de teste"}
    checar(ana.post(f"{API}/aliquotas", json=nova_aliquota).status_code == 403,
           "revisor nao mexe na tabela")
    r = adm.post(f"{API}/aliquotas", json=nova_aliquota)
    checar(r.status_code == 200, r.text)
    tabela = bruno.get(f"{API}/aliquotas").json()["itens"]
    checar(len(tabela) == 29 and any(l["ncm"] == "3924" for l in tabela),
           len(tabela))
    r = adm.post(f"{API}/aliquotas", json={**nova_aliquota, "base_legal": ""})
    checar(r.status_code == 422, "aliquota sem base legal")
    r = adm.post(f"{API}/aliquotas", json={**nova_aliquota,
                                           "vigencia_inicio": "2025-01-01",
                                           "vigencia_fim": "2026-06-30"})
    checar(r.status_code == 409
           and r.json()["detail"]["code"] == "VIGENCIA_SOBREPOSTA", r.text)

    # Nota aprovada nao muda com a tabela; a memoria dela guarda os 20,5%.
    depois = adm.get(f"{API}/notas/{ids['1']}").json()
    checar(depois["a_recolher"]["centavos"] == 16981
           and depois["lista_itens"][0]["memoria"]["aliquota_interna"] == "20.5",
           depois["a_recolher"])

    checar(ana.put(f"{API}/configuracao",
                   json={"dia_vencimento": 20}).status_code == 403,
           "revisor nao muda parametro")
    r = adm.put(f"{API}/configuracao", json={"dia_vencimento": 20,
                                             "componentes": {"ipi": False}})
    checar(r.status_code == 200 and r.json()["dia_vencimento"] == 20
           and r.json()["componentes"]["ipi"] is False, r.text)
    checar(adm.put(f"{API}/configuracao",
                   json={"dia_vencimento": 40}).status_code == 422, "dia 40")
    gerais = [e["tipo"] for e in bruno.get(f"{API}/eventos").json()["itens"]]
    for esperado in ("aliquota_criada", "configuracao_alterada",
                     "regime_definido", "nota_excluida"):
        checar(esperado in gerais, f"{esperado} fora da trilha: {gerais}")

    # Reabrir (com motivo) devolve a nota a revisao.
    r = adm.post(f"{API}/notas/{ids['1']}/reabrir", json={
        "revision": depois["revision"], "motivo": "Conferir o método com o Fiscal"})
    checar(r.status_code == 200 and r.json()["estado"] == "em_revisao", r.text)
    tipos_eventos = [e["tipo"] for e in r.json()["eventos"]]
    checar(tipos_eventos[0] == "nota_importada"
           and tipos_eventos[-2:] == ["nota_aprovada", "nota_reaberta"],
           tipos_eventos)

    # Limite de arquivos por envio.
    muitos = [(f"n{i}.xml", b"x") for i in range(201)]
    checar(enviar(ana, muitos, metodo="por_dentro").status_code == 422,
           "mais de 200 arquivos")

    # A tela existe e esta registrada.
    pagina = adm.get("/").text
    checar('data-aba="antecipacao"' in pagina and "antecipacao.js" in pagina,
           "a aba deveria estar no index.html")
    checar(adm.get("/antecipacao.js").status_code == 200, "antecipacao.js")
    checar(adm.post("/api/eventos/aba",
                    json={"aba": "antecipacao"}).status_code == 200,
           "a aba deveria ser aceita no historico de navegacao")

    print("OK - web antecipacao: acesso, importacao, revisao, aprovacao e saidas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
