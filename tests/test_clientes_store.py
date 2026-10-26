"""Persistencia do cadastro de clientes (spec 012): clientes.db.

Garantias provadas aqui: documento unico, concorrencia por revision, trilha
append-only, senha so cifrada no disco, revelacao com trilha na mesma
transacao e limite por hora, cifra fora do lugar falha, importacao em uma
transacao e idempotente, coleta casando por CNPJ com renovacao, vencimentos.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tests"))

from auditoria_fiscal.core import clientes as cl  # noqa: E402
from auditoria_fiscal.core import cofre as cf  # noqa: E402
from auditoria_fiscal.core import planilha_clientes as pc  # noqa: E402
from auditoria_fiscal.ferramentas import clientes_store as cs  # noqa: E402
from auditoria_fiscal.core.documentos_br import dv_cnpj  # noqa: E402

import test_planilha_clientes as tp  # noqa: E402

U = {"usuario_id": 1, "usuario_login": "ana"}
SENHA = "Pref#Sintetica 1"


def cnpj(base: str) -> str:
    return base + dv_cnpj(base)


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def codigo_de(funcao, *args, **kwargs) -> str:
    try:
        funcao(*args, **kwargs)
    except cl.ErroClientes as exc:
        return exc.codigo
    return ""


def levanta(excecao, funcao, *args, **kwargs) -> bool:
    try:
        funcao(*args, **kwargs)
    except excecao:
        return True
    return False


def bytes_do_banco(caminho: str) -> bytes:
    tudo = b""
    for sufixo in ("", "-wal", "-shm"):
        if os.path.exists(caminho + sufixo):
            with open(caminho + sufixo, "rb") as arquivo:
                tudo += arquivo.read()
    return tudo


def main() -> int:
    pasta = tempfile.mkdtemp(prefix="clientes_store_")
    caminho = os.path.join(pasta, "clientes.db")
    cofre = cf.Cofre(cf.decodificar_chave(cf.gerar_chave()))
    store = cs.ClientesStore(caminho, cofre=cofre)

    # ------------------------------------------------------------------
    # Cadastro

    doc = cnpj("011111111000")
    cid = store.criar_cliente({"nome": "  Alfa   Comercio ", "documento": doc,
                               "ie": "NÃO TEM", "im": "123"}, **U)
    alfa = store.obter(cid)
    checar(alfa["nome"] == "Alfa Comercio", "nome com espacos colapsados")
    checar(alfa["ie"] == "" and alfa["ie_situacao"] == cl.CAMPO_NAO_TEM,
           "IE 'NAO TEM' vira situacao")
    checar(alfa["situacao"] == cl.SITUACAO_ATIVO and alfa["revision"] == 1, alfa)
    checar(codigo_de(store.criar_cliente, {"nome": "Outro", "documento": doc},
                     **U) == cs.DOCUMENTO_DUPLICADO, "documento unico")
    checar(codigo_de(store.criar_cliente, {"nome": "X", "documento": "123"},
                     **U) == cl.DOCUMENTO_INVALIDO, "documento invalido")
    checar(codigo_de(store.criar_cliente, {"nome": " ", "documento": ""},
                     **U) == cl.CAMPO_OBRIGATORIO, "nome obrigatorio")
    sem_doc = store.criar_cliente({"nome": "Sem Documento"}, **U)
    checar(store.obter(sem_doc)["documento"] is None,
           "documento e' opcional no cadastro manual")

    r = store.editar_cliente(cid, {"nome": "Alfa Comercio Ltda", "documento": doc,
                                   "ie": "12.345", "im": "123",
                                   "municipio": "Salvador"},
                             revision=1, **U)
    checar(r["revision"] == 2, r)
    checar(levanta(cs.ConcorrenciaError, store.editar_cliente, cid,
                   {"nome": "Antiga"}, revision=1, **U),
           "revision velha e' recusada")
    alteracoes = store.detalhar(cid)["alteracoes"]
    campos = {a["campo"] for a in alteracoes}
    checar({"nome", "ie", "municipio"} <= campos, f"trilha por campo: {campos}")
    checar(all(a["usuario_login"] == "ana" for a in alteracoes), "autor")

    checar(codigo_de(store.mudar_situacao, cid, cl.SITUACAO_BAIXADO, "",
                     **U) == cl.CAMPO_OBRIGATORIO, "mudar situacao exige motivo")
    store.mudar_situacao(cid, cl.SITUACAO_INATIVO, "Encerrou contrato.", **U)
    checar(store.obter(cid)["situacao"] == cl.SITUACAO_INATIVO, "situacao")
    store.mudar_situacao(cid, cl.SITUACAO_ATIVO, "Voltou.", **U)

    conn = sqlite3.connect(caminho)
    for sql in ("UPDATE alteracao SET depois='x'", "DELETE FROM alteracao",
                "DELETE FROM cliente"):
        checar(levanta(sqlite3.DatabaseError, conn.execute, sql),
               f"trigger deveria barrar: {sql}")
    conn.close()

    lista = store.listar(texto="alfa")
    checar(lista["total"] == 1 and lista["itens"][0]["id"] == cid, lista)
    checar(store.listar(texto=doc[:6])["total"] == 1, "busca pelo documento")
    checar(store.listar(situacao=cl.SITUACAO_BAIXADO)["total"] == 0, "filtro")
    checar(store.listar(municipio="Salvador")["total"] == 1, "municipio")
    checar(levanta(ValueError, store.listar, situacao="inventada"),
           "situacao desconhecida")

    # ------------------------------------------------------------------
    # Cofre

    sid = store.gravar_segredo(cid, "prefeitura", SENHA, **U)
    checar(SENHA.encode() not in bytes_do_banco(caminho),
           "a senha nunca pode estar em texto no banco")
    detalhe = store.detalhar(cid)
    segredo = next(s for s in detalhe["segredos"] if s["id"] == sid)
    checar(segredo["presente"] and "valor" not in segredo
           and "cifra" not in segredo, f"detalhe sem valor: {segredo}")

    revelado = store.revelar(sid, ip="10.0.0.1", **U)
    checar(revelado["valor"] == SENHA, "revelar devolve a senha exata")
    acessos = store.acessos()["itens"]
    checar(acessos[0]["acao"] == "revelar" and acessos[0]["resultado"] == "ok"
           and acessos[0]["usuario_login"] == "ana"
           and acessos[0]["ip"] == "10.0.0.1", acessos[0])
    checar(all(SENHA not in str(a) for a in acessos), "trilha sem o valor")

    # Troca: o valor anterior nao fica guardado, a troca fica na trilha.
    store.gravar_segredo(cid, "prefeitura", "Nova#Senha", **U)
    checar(store.revelar(sid, ip="", **U)["valor"] == "Nova#Senha", "troca")
    checar(any(a["campo"] == "segredo:prefeitura" for a in
               store.detalhar(cid)["alteracoes"]), "troca na trilha")

    # Situacao sem valor.
    sid2 = store.gravar_segredo(cid, "sefaz", "", situacao=cl.CAMPO_PENDENTE, **U)
    checar(codigo_de(store.revelar, sid2, ip="", **U) == cs.SEM_VALOR,
           "senha pendente nao tem o que revelar")

    # Outros portais: varios por cliente.
    o1 = store.gravar_segredo(cid, "outro", "a1", portal="e-CAC",
                              usuario_portal="alfa", **U)
    o2 = store.gravar_segredo(cid, "outro", "b2", portal="Domínio", **U)
    checar(o1 != o2, "mais de um 'outro portal'")
    checar(codigo_de(store.gravar_segredo, cid, "outro", "x", **U)
           == cl.CAMPO_OBRIGATORIO, "outro portal exige o nome do portal")
    checar(codigo_de(store.gravar_segredo, cid, "inventado", "x", **U)
           == cl.VALOR_INVALIDO, "campo desconhecido")

    # Cifra trocada de linha no banco: falha, nao mostra a senha de outro.
    conn = sqlite3.connect(caminho)
    linha = conn.execute("SELECT cifra, nonce FROM segredo WHERE id=?",
                         (o1,)).fetchone()
    conn.execute("UPDATE segredo SET cifra=?, nonce=? WHERE id=?",
                 (linha[0], linha[1], o2))
    conn.commit()
    conn.close()
    checar(levanta(cf.SegredoIlegivel, store.revelar, o2, ip="", **U),
           "cifra fora do lugar tem de falhar")

    # Limite por hora.
    limitado = {"usuario_id": 2, "usuario_login": "bruno"}
    store.revelar(sid, ip="", limite_hora=2, **limitado)
    store.revelar(sid, ip="", limite_hora=2, **limitado)
    checar(levanta(cs.LimiteExcedido, store.revelar, sid, ip="",
                   limite_hora=2, **limitado), "terceira revelacao bloqueada")
    checar(store.acessos(usuario="bruno")["itens"][0]["resultado"] == "limite",
           "o bloqueio fica na trilha")

    store.registrar_negado(cid, sid, ip="1.2.3.4", usuario_id=3,
                           usuario_login="carla")
    checar(store.acessos(usuario="carla")["itens"][0]["resultado"] == "negado",
           "tentativa sem permissao fica na trilha do cofre")

    conn = sqlite3.connect(caminho)
    checar(levanta(sqlite3.DatabaseError, conn.execute,
                   "DELETE FROM acesso_cofre"), "acesso ao cofre e' imutavel")
    conn.close()

    # Sem cofre: le o cadastro, nao mexe em senha.
    sem_cofre = cs.ClientesStore(caminho, cofre=None)
    checar(sem_cofre.detalhar(cid)["nome"] == "Alfa Comercio Ltda", "le")
    checar(levanta(cf.CofreIndisponivel, sem_cofre.revelar, sid, ip="", **U),
           "sem chave nao revela")
    checar(levanta(cf.CofreIndisponivel, sem_cofre.gravar_segredo, cid,
                   "sefaz", "x", **U), "sem chave nao grava")
    sem_cofre.fechar()

    # ------------------------------------------------------------------
    # Importacao da planilha

    xlsx = os.path.join(pasta, "senhas.xlsx")
    tp.planilha(xlsx)
    leitura = pc.ler_planilha_clientes(xlsx)
    checar(store.situacao_importacao(leitura)[3] == "atualiza",
           "linha cujo CNPJ ja existe aparece como atualizacao")
    r = store.importar_planilha(leitura, decisoes={}, nome_arquivo="senhas.xlsx",
                                **U)
    checar(r["criados"] == 5 and r["atualizados"] == 1 and r["ignorados"] == 2,
           f"contagens: {r}")
    checar(tp.SENHAS[0].encode() not in bytes_do_banco(caminho),
           "senha importada so cifrada")
    beta = store.listar(texto="Beta")["itens"][0]
    checar(beta["situacao"] == cl.SITUACAO_BAIXADO, "cor vira situacao")
    d = store.detalhar(beta["id"])
    checar(d["licencas"]["tvl"]["situacao"] == cl.CAMPO_DEFINITIVO, d["licencas"])
    checar(d["origem"]["linha"] == 4 and len(d["origem"]["arquivo"]) == 64,
           f"origem rastreavel: {d['origem']}")
    checar(d["pendencias"], "pendencias da importacao ficam no cliente")
    seg = {s["campo"]: s for s in d["segredos"]}
    checar(seg["sefaz"]["presente"] and seg["prefeitura"]["situacao"]
           == cl.CAMPO_PENDENTE, seg)
    alfa_import = store.listar(texto="Alfa Comercio Ltda")["itens"][0]
    checar(alfa_import["id"] == cid, "atualizou o cliente que ja existia")
    sefaz_alfa = next(s for s in store.detalhar(cid)["segredos"]
                      if s["campo"] == "sefaz")
    checar(store.revelar(sefaz_alfa["id"], ip="", **U)["valor"] == tp.SENHAS[0],
           "senha da planilha decifra")

    total = store.contar("cliente")
    r = store.importar_planilha(leitura, decisoes={}, nome_arquivo="senhas.xlsx",
                                **U)
    checar(store.contar("cliente") == total and r["criados"] == 0,
           f"reimportar nao duplica: {r}")

    # Decisao da pessoa: incluir a repetida? Nao — documento unico; ignorar a
    # primeira e incluir a segunda e' o que a decisao permite.
    leitura2 = pc.ler_planilha_clientes(xlsx)
    checar(codigo_de(store.importar_planilha, leitura2, decisoes={8: "incluir"},
                     nome_arquivo="x.xlsx", **U) == cs.DECISAO_INVALIDA,
           "incluir duas linhas com o mesmo documento e' recusado inteiro")
    checar(store.contar("cliente") == total, "a recusa nao grava nada")

    # ------------------------------------------------------------------
    # Certificados e coleta

    hoje = date(2026, 10, 26)
    base_item = {"pasta": "ALFA", "arquivo": "alfa.pfx", "hash_arquivo": "a" * 64,
                 "titular_nome": "ALFA", "titular_documento": doc,
                 "emissor": "AC SINTETICA", "inicio": "2025-11-01",
                 "fim": "2026-11-05", "serie": "AA01", "tipo": "A1",
                 "info": {}, "problemas": []}
    coleta = {"formato": "auditoria-jb/coleta-certificados", "versao": 1,
              "gerada_em": "2026-10-26T09:00:00", "pasta": "CERTIFICADOS",
              "itens": [base_item,
                        {**base_item, "pasta": "FANTASMA", "serie": "ZZ",
                         "titular_documento": cnpj("999999990001")},
                        {**base_item, "pasta": "QUEBRADO", "fim": "",
                         "titular_documento": "", "problemas": ["SENHA_NAO_ABRE"]}]}
    previa = store.previa_coleta(coleta)
    casos = {p["pasta"]: p["resultado"] for p in previa}
    checar(casos == {"ALFA": "casou", "FANTASMA": "sem_cliente",
                     "QUEBRADO": "nao_lido"}, casos)
    r = store.importar_coleta(coleta, nome_arquivo="c.json", hash_arquivo="h",
                              **U)
    checar(r == {"novos": 1, "atualizados": 0, "sem_cliente": 1, "nao_lidos": 1},
           r)
    r = store.importar_coleta(coleta, nome_arquivo="c.json", hash_arquivo="h",
                              **U)
    checar(r["novos"] == 0 and r["atualizados"] == 1, f"mesma serie atualiza: {r}")

    venc = store.vencimentos(hoje)
    checar(len(venc) == 1 and venc[0]["faixa"] == "ate_15"
           and venc[0]["dias"] == 10, venc)
    checar(store.resumo_vencimentos(hoje)["aviso"] == 1, "aviso no topo")

    # Renovacao: certificado novo do mesmo titular substitui o antigo.
    renovado = {**base_item, "serie": "AA02", "inicio": "2026-10-20",
                "fim": "2027-10-20", "hash_arquivo": "b" * 64}
    store.importar_coleta({**coleta, "itens": [renovado]}, nome_arquivo="c2",
                          hash_arquivo="h2", **U)
    certs = store.detalhar(cid)["certificados"]
    antigo = next(c for c in certs if c["serie"] == "AA01")
    novo = next(c for c in certs if c["serie"] == "AA02")
    checar(antigo["situacao"] == cs.CERT_SUBSTITUIDO
           and antigo["substituido_por_id"] == novo["id"], antigo)
    checar([v["serie"] for v in store.vencimentos(hoje, faixa=None)] == ["AA02"],
           "substituido sai do painel")
    checar(store.resumo_vencimentos(hoje)["aviso"] == 0, "renovado, sem aviso")

    # Certificado manual + renovacao em andamento tira do aviso.
    outro = store.criar_cliente({"nome": "Gama Manual",
                                 "documento": cnpj("777777770001")}, **U)
    cert = store.adicionar_certificado(outro, {
        "tipo": "A3", "titular_nome": "GAMA", "fim": "2026-10-20",
        "local_guarda": "Token na gaveta"}, origem=cs.ORIGEM_MANUAL, **U)
    checar(store.vencimentos(hoje, faixa=cl.FAIXA_VENCIDO)[0]["id"] == cert,
           "vencido")
    checar(store.resumo_vencimentos(hoje)["aviso"] == 1, "vencido avisa")
    store.marcar_renovacao(cert, True, **U)
    checar(store.resumo_vencimentos(hoje)["aviso"] == 0,
           "renovacao em andamento sai do aviso")
    checar(len(store.vencimentos(hoje, faixa=cl.FAIXA_VENCIDO)) == 1,
           "mas continua no painel")
    checar(codigo_de(store.adicionar_certificado, outro, {"fim": ""},
                     origem=cs.ORIGEM_MANUAL, **U) == cl.CAMPO_OBRIGATORIO,
           "certificado sem validade nao entra")

    # Cliente baixado sai do painel.
    store.mudar_situacao(outro, cl.SITUACAO_BAIXADO, "Fechou.", **U)
    checar(all(v["cliente_id"] != outro for v in store.vencimentos(hoje)),
           "cliente baixado sai do painel")

    # ------------------------------------------------------------------
    # Faixas configuraveis

    checar(store.faixas() == cl.FAIXAS_PADRAO, store.faixas())
    store.definir_faixas([45, 10], **U)
    checar(store.faixas() == (10, 45), store.faixas())
    checar(store.vencimentos(hoje)[0]["faixa"] == "em_dia",
           "faixas novas valem na consulta seguinte")
    checar(codigo_de(store.definir_faixas, [0], **U) == cl.FAIXAS_INVALIDAS,
           "faixa invalida")

    store.fechar()
    print("OK - clientes.db (documento unico, revision, trilha append-only, "
          "senha so cifrada, revelacao auditada com limite, cifra fora do "
          "lugar, importacao idempotente em transacao, coleta por CNPJ com "
          "renovacao, vencimentos e faixas) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
