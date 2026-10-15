"""Persistencia da Emissao de NFS-e (spec 006, data-model.md): SQLite proprio,
trilha append-only, aprovacao tudo ou nada e garantias no banco.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3
import sys
import tempfile
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_store as ns  # noqa: E402
from fixtures import nfse as fx  # noqa: E402

HOJE = dt.date(2026, 11, 15)
AGORA = dt.datetime(2026, 11, 15, 10, 30, tzinfo=nd.FUSO_SALVADOR)
U = {"usuario_id": 7, "usuario_login": "atendente"}
APROVADORA = {"usuario_id": 8, "usuario_login": "fiscal"}

TEXTO_DOIS = """Competência: 11/2026
Responsável: Ana Exemplo
CPF: 123.456.789-09
Aluno: Pedro Exemplo
Turma: Berçário
Valor: 1.250,00

Competência: 11/2026
Responsável: Bruno Teste
CPF: 111.444.777-35
Aluno: Caio Teste
Turma: Infantil 2
Valor: 980,50
"""


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def erro(funcao, *args, **kwargs):
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc
    except ns.ConcorrenciaError as exc:
        return exc
    return None


def novo_store(pasta: str, nome: str = "nfse.db") -> ns.NfseStore:
    return ns.NfseStore(os.path.join(pasta, nome), os.path.join(pasta, "origens"))


def perfil_pronto(store, **extra) -> int:
    return store.criar_perfil(fx.perfil_completo(**extra), **U)["perfil_id"]


def testar_schema_e_perfil(pasta: str) -> None:
    store = novo_store(pasta)
    ns.NfseStore(store.db_path, store.pasta_origens).fechar()   # idempotente
    r = store.criar_perfil(fx.perfil_cru(), motivo="cadastro inicial", **U)
    checar(r["versao"] == 1, r)
    e = erro(store.criar_perfil, fx.perfil_cru(), **U)
    checar(e is not None and e.codigo == ns.PERFIL_DUPLICADO, "um perfil por CNPJ")
    detalhe = store.perfil(r["perfil_id"])
    checar({p["origem"] for p in detalhe["pendencias"]} == {"JB-2", "JB-8", "R5"},
           detalhe["pendencias"])
    checar([t["nome"] for t in detalhe["atual"]["turmas"]]
           == ["Berçário", "Infantil II", "Fundamental I"], detalhe["atual"]["turmas"])
    checar(detalhe["atual"]["turmas"][0]["apelidos"] == ["Bercario I", "Berçário 1"],
           detalhe["atual"]["turmas"][0])

    v2 = store.criar_versao(r["perfil_id"], fx.perfil_completo(), motivo="respostas", **U)
    checar(v2["versao"] == 2, v2)
    detalhe = store.perfil(r["perfil_id"])
    checar(detalhe["pendencias"] == [] and len(detalhe["versoes"]) == 2, detalhe["versoes"])
    v1 = store.carregar_versao(r["versao_id"])
    checar(v1.endereco_tomador is None, "a versao 1 continua como era")
    e = erro(store.criar_versao, r["perfil_id"],
             fx.perfil_completo(cnpj="11.444.777/0001-61"), **U)
    checar(e is not None and e.codigo == ns.CNPJ_DIFERENTE, e and e.codigo)

    conn = sqlite3.connect(store.db_path)
    for sql in ("UPDATE perfil_versao SET razao_social='x'",
                "DELETE FROM perfil_versao", "UPDATE perfil_turma SET nome='x'",
                "DELETE FROM perfil", "UPDATE perfil SET cnpj='1'"):
        try:
            conn.execute(sql)
            checar(False, f"deveria ser recusado: {sql}")
        except sqlite3.DatabaseError:
            pass
    conn.close()
    store.fechar()


def testar_importacao(pasta: str) -> None:
    store = novo_store(pasta, "imp.db")
    pid = perfil_pronto(store)
    caminho = fx.gerar_planilha(pasta, [fx.LINHA_ANA, fx.LINHA_BRUNO], nome="imp.xlsx")
    r = store.importar_planilha(pid, caminho, "lista novembro.xlsx", hoje=HOJE, **U)
    checar(not r["reaproveitado"], r)
    lote = store.lote(r["lote_id"])
    checar(lote["lote"]["estado"] == "em_revisao" and lote["lote"]["revision"] == 1,
           lote["lote"])
    checar(len(lote["linhas"]) == 2, len(lote["linhas"]))
    ana = lote["linhas"][0]
    checar(ana["origem"]["aba"] == "Notas" and ana["origem"]["linha_planilha"] == 2,
           ana["origem"])
    checar(ana["brutos"]["valor"] == "1250" and ana["valor_centavos"] == 125000, ana)
    checar(ana["situacao"] == "ok", (ana["situacao"], ana["apontamentos"]))
    checar(lote["conferencia"]["totais"]["soma_centavos"] == 125000 + 98050,
           lote["conferencia"]["totais"])

    sha = hashlib.sha256(open(caminho, "rb").read()).hexdigest()
    guardado = os.path.join(store.pasta_origens, f"{sha}.xlsx")
    checar(os.path.isfile(guardado), "planilha original guardada pelo SHA-256")
    checar(lote["lote"]["origem"]["sha256"] == sha, lote["lote"]["origem"])

    # Mesmo arquivo, outro nome: aponta o lote que ja existe.
    copia = os.path.join(pasta, "outro nome.xlsx")
    with open(caminho, "rb") as a, open(copia, "wb") as b:
        b.write(a.read())
    de_novo = store.importar_planilha(pid, copia, "outro nome.xlsx", hoje=HOJE, **U)
    checar(de_novo == {"lote_id": r["lote_id"], "reaproveitado": True}, de_novo)

    t = store.importar_texto(pid, TEXTO_DOIS, hoje=HOJE, **U)
    lt = store.lote(t["lote_id"])
    checar(lt["lote"]["origem"]["tipo"] == "texto" and len(lt["linhas"]) == 2, lt["lote"])
    checar(lt["linhas"][1]["origem"]["bloco"] == 2, lt["linhas"][1]["origem"])
    checar(store.importar_texto(pid, TEXTO_DOIS, hoje=HOJE, **U)["reaproveitado"],
           "o mesmo texto aponta o lote existente")
    checar(store.contar("origem") == 2, store.contar("origem"))
    store.fechar()


def testar_correcao(pasta: str) -> None:
    store = novo_store(pasta, "corr.db")
    pid = perfil_pronto(store)
    texto = TEXTO_DOIS.replace("123.456.789-09", "123.456.789-00")
    lote_id = store.importar_texto(pid, texto, hoje=HOJE, **U)["lote_id"]
    lote = store.lote(lote_id)
    linha = lote["linhas"][0]
    checar(linha["situacao"] == "bloqueio", "CPF errado bloqueia")

    e = erro(store.corrigir, lote_id, linha["id"], "responsavel_cpf", "123.456.789-09",
             "  ", revision=1, hoje=HOJE, **U)
    checar(e is not None and e.codigo == ns.MOTIVO_OBRIGATORIO, "motivo obrigatorio")
    e = erro(store.corrigir, lote_id, linha["id"], "senha", "x", "m", revision=1,
             hoje=HOJE, **U)
    checar(e is not None and e.codigo == ns.CAMPO_NAO_CORRIGIVEL, "campo fora da lista")
    e = erro(store.corrigir, lote_id, linha["id"], "responsavel_cpf", "123.456.789-09",
             "m", revision=99, hoje=HOJE, **U)
    checar(isinstance(e, ns.ConcorrenciaError) and e.revision_atual == 1, e)

    r = store.corrigir(lote_id, linha["id"], "responsavel_cpf", "123.456.789-09",
                       "Escola confirmou o CPF por telefone", revision=1, hoje=HOJE, **U)
    checar(r["revision"] == 2, r)
    lote = store.lote(lote_id)
    linha = lote["linhas"][0]
    checar(linha["brutos"]["responsavel_cpf"] == "123.456.789-00",
           "o valor de origem nunca e' apagado")
    checar(linha["efetivos"]["responsavel_cpf"] == "123.456.789-09"
           and linha["corrigidos"] == ["responsavel_cpf"], linha)
    checar(linha["situacao"] == "ok", linha["apontamentos"])
    historico = store.correcoes(linha["id"])
    checar(len(historico) == 1 and historico[0]["valor_anterior"] == "123.456.789-00"
           and historico[0]["criada_por_login"] == "atendente", historico)
    checar(store.contar("conferencia") == 2, "nova rodada a cada correcao")

    r = store.corrigir(lote_id, linha["id"], "excluida", "1", "Aluno saiu da escola",
                       revision=2, hoje=HOJE, **U)
    lote = store.lote(lote_id)
    checar(lote["linhas"][0]["excluida"] and lote["conferencia"]["totais"]["excluidas"] == 1,
           lote["conferencia"]["totais"])
    store.corrigir(lote_id, linha["id"], "excluida", "0", "Engano", revision=3,
                   hoje=HOJE, **U)
    checar(not store.lote(lote_id)["linhas"][0]["excluida"], "reincluida")
    tipos = [ev["tipo"] for ev in store.eventos(lote_id)]
    checar(tipos == ["lote_importado", "linha_corrigida", "linha_excluida",
                     "linha_reincluida"], tipos)

    conn = sqlite3.connect(store.db_path)
    for sql in ("UPDATE linha SET valor='1'", "DELETE FROM correcao",
                "UPDATE conferencia_linha SET situacao='ok'", "DELETE FROM apontamento",
                "UPDATE evento SET tipo='x'", "DELETE FROM origem"):
        try:
            conn.execute(sql)
            checar(False, f"deveria ser recusado: {sql}")
        except sqlite3.DatabaseError:
            pass
    conn.close()
    store.fechar()


def testar_aprovacao(pasta: str) -> None:
    store = novo_store(pasta, "apr.db")
    pid = perfil_pronto(store)
    lote_id = store.importar_texto(pid, TEXTO_DOIS, hoje=HOJE, **U)["lote_id"]

    r = store.aprovar(lote_id, revision=1, agora=AGORA, **APROVADORA)
    checar(r["dps"] == 2 and r["revision"] == 2, r)
    lote = store.lote(lote_id)
    checar(lote["lote"]["estado"] == "aprovado"
           and lote["lote"]["aprovado_por_login"] == "fiscal"
           and len(lote["lote"]["hash_aprovacao"]) == 64, lote["lote"])
    dps = store.dps_do_lote(lote_id)
    checar([d["numero"] for d in dps] == [1, 2], dps)
    for d in dps:
        checar(nd.validar_xsd(d["xml"]) == [], "DPS gravada valida no XSD")
        checar(hashlib.sha256(d["xml"]).hexdigest() == d["sha256"], "sha256 gravado")
        checar(d["versao_leiaute"] == "1.01" and d["perfil_versao_id"], d)
    checar(b"<xNome>Ana Exemplo</xNome>" in dps[0]["xml"], "tomador da linha 1")

    e = erro(store.corrigir, lote_id, lote["linhas"][0]["id"], "valor", "1,00", "m",
             revision=2, hoje=HOJE, **U)
    checar(e is not None and e.codigo == ns.ESTADO_INVALIDO, "aprovado nao muda")
    e = erro(store.aprovar, lote_id, revision=2, agora=AGORA, **APROVADORA)
    checar(e is not None and e.codigo == ns.ESTADO_INVALIDO, "nao aprova duas vezes")

    # Mesmas notas em outro lote: a conferencia ja aponta a duplicata aprovada.
    outro = store.importar_texto(pid, TEXTO_DOIS + "\n", hoje=HOJE, **U)["lote_id"]
    lo = store.lote(outro)
    checar(all(a["codigo"] == nf.DUPLICATA_APROVADA for l in lo["linhas"]
               for a in l["apontamentos"]) and lo["linhas"][0]["apontamentos"],
           lo["linhas"][0]["apontamentos"])
    e = erro(store.aprovar, outro, revision=1, agora=AGORA, **APROVADORA)
    checar(e is not None and e.codigo == ns.LOTE_COM_BLOQUEIO, e and e.codigo)

    # Descartar o aprovado libera as chaves; os numeros nao voltam.
    e = erro(store.descartar, lote_id, revision=2, motivo="", **APROVADORA)
    checar(e is not None and e.codigo == ns.MOTIVO_OBRIGATORIO, "motivo do descarte")
    store.descartar(lote_id, revision=2, motivo="Valores errados na lista", **APROVADORA)
    checar(store.lote(lote_id)["lote"]["estado"] == "descartado", "descartado")
    store.reconferir(outro, revision=1, hoje=HOJE, **U)
    checar(store.lote(outro)["linhas"][0]["situacao"] == "ok",
           "com as chaves liberadas a duplicata some")
    store.aprovar(outro, revision=2, agora=AGORA, **APROVADORA)
    checar([d["numero"] for d in store.dps_do_lote(outro)] == [3, 4],
           "numero de DPS nunca e' reutilizado")
    e = erro(store.descartar, lote_id, revision=3, motivo="de novo", **APROVADORA)
    checar(e is not None and e.codigo == ns.ESTADO_INVALIDO, "descarte e' terminal")

    conn = sqlite3.connect(store.db_path)
    for sql in ("UPDATE dps SET xml=x'00'", "DELETE FROM dps",
                "UPDATE numeracao_dps SET ultimo_numero=1",
                "DELETE FROM chave_aprovada",
                "UPDATE lote SET estado='em_revisao' WHERE estado='descartado'",
                "UPDATE lote SET estado='em_revisao' WHERE estado='aprovado'"):
        try:
            conn.execute(sql)
            checar(conn.total_changes == 0, f"deveria ser recusado: {sql}")
        except sqlite3.DatabaseError:
            pass
    conn.close()
    store.fechar()


def testar_condicoes_de_aprovacao(pasta: str) -> None:
    store = novo_store(pasta, "cond.db")
    pid = store.criar_perfil(fx.perfil_cru(), **U)["perfil_id"]
    lote_id = store.importar_texto(pid, TEXTO_DOIS, hoje=HOJE, **U)["lote_id"]
    e = erro(store.aprovar, lote_id, revision=1, agora=AGORA, **APROVADORA)
    checar(e is not None and e.codigo == nf.PERFIL_COM_PENDENCIA, e and e.codigo)
    checar(any(a["codigo"] == nf.PERFIL_COM_PENDENCIA
               for a in store.lote(lote_id)["apontamentos_lote"]), "aparece no lote")

    store.criar_versao(pid, fx.perfil_completo(), **U)
    e = erro(store.aprovar, lote_id, revision=1, agora=AGORA, **APROVADORA)
    checar(e is not None and e.codigo == ns.PERFIL_DESATUALIZADO,
           "rodada feita com versao antiga do perfil")
    store.reconferir(lote_id, revision=1, hoje=HOJE, **U)

    ids = [l["id"] for l in store.lote(lote_id)["linhas"]]
    store.corrigir(lote_id, ids[0], "excluida", "1", "fora", revision=2, hoje=HOJE, **U)
    store.corrigir(lote_id, ids[1], "excluida", "1", "fora", revision=3, hoje=HOJE, **U)
    e = erro(store.aprovar, lote_id, revision=4, agora=AGORA, **APROVADORA)
    checar(e is not None and e.codigo == ns.LOTE_VAZIO, e and e.codigo)
    store.fechar()


def testar_tudo_ou_nada(pasta: str) -> None:
    store = novo_store(pasta, "tudo.db")
    pid = perfil_pronto(store)
    lote_id = store.importar_texto(pid, TEXTO_DOIS, hoje=HOJE, **U)["lote_id"]
    original = nd.montar_dps
    chamadas = {"n": 0}

    def falha_na_segunda(*args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise nf.ErroNfse(nd.DPS_INVALIDA, "falha injetada")
        return original(*args, **kwargs)

    nd.montar_dps = falha_na_segunda
    try:
        e = erro(store.aprovar, lote_id, revision=1, agora=AGORA, **APROVADORA)
    finally:
        nd.montar_dps = original
    checar(e is not None and e.codigo == nd.DPS_INVALIDA, e)
    checar(store.contar("dps") == 0 and store.contar("chave_aprovada") == 0,
           "nada fica gravado de uma aprovacao que falhou")
    checar(store.contar("numeracao_dps") == 0, "nem o numero e' reservado")
    lote = store.lote(lote_id)
    checar(lote["lote"]["estado"] == "em_revisao" and lote["lote"]["revision"] == 1,
           lote["lote"])
    checar([ev["tipo"] for ev in store.eventos(lote_id)] == ["lote_importado"],
           "sem evento de aprovacao")
    store.aprovar(lote_id, revision=1, agora=AGORA, **APROVADORA)
    checar(store.contar("dps") == 2, "depois da falha, aprova normalmente")
    store.fechar()


def testar_concorrencia(pasta: str) -> None:
    """Dois lotes com a MESMA nota aprovados ao mesmo tempo: so um passa."""
    base = novo_store(pasta, "conc.db")
    pid = perfil_pronto(base)
    a = base.importar_texto(pid, TEXTO_DOIS, hoje=HOJE, **U)["lote_id"]
    b = base.importar_texto(pid, TEXTO_DOIS + "\n\n", hoje=HOJE, **U)["lote_id"]
    base.fechar()

    barreira = threading.Barrier(2)
    resultados = {}

    def aprovar(lote_id):
        store = novo_store(pasta, "conc.db")
        try:
            barreira.wait()
            resultados[lote_id] = store.aprovar(lote_id, revision=1, agora=AGORA,
                                                **APROVADORA)
        except (nf.ErroNfse, ns.ConcorrenciaError) as exc:
            resultados[lote_id] = exc
        finally:
            store.fechar()

    fios = [threading.Thread(target=aprovar, args=(x,)) for x in (a, b)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    ok = [r for r in resultados.values() if isinstance(r, dict)]
    falhas = [r for r in resultados.values() if not isinstance(r, dict)]
    checar(len(ok) == 1 and len(falhas) == 1, resultados)
    checar(getattr(falhas[0], "codigo", "") == nf.DUPLICATA_APROVADA, falhas[0])

    # Lotes diferentes ao mesmo tempo: numeros sem repeticao.
    store = novo_store(pasta, "conc.db")
    textos = [TEXTO_DOIS.replace("Pedro Exemplo", f"Aluno {i}").replace(
        "Caio Teste", f"Irmao {i}") for i in range(4)]
    lotes = [store.importar_texto(pid, t, hoje=HOJE, **U)["lote_id"] for t in textos]
    store.fechar()
    barreira = threading.Barrier(len(lotes))
    resultados.clear()
    fios = [threading.Thread(target=aprovar, args=(x,)) for x in lotes]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    checar(all(isinstance(r, dict) for r in resultados.values()), resultados)
    store = novo_store(pasta, "conc.db")
    numeros = [d["numero"] for x in lotes for d in store.dps_do_lote(x)]
    checar(sorted(numeros) == list(range(3, 3 + 2 * len(lotes))), sorted(numeros))
    store.fechar()


def main() -> int:
    with tempfile.TemporaryDirectory() as pasta:
        testar_schema_e_perfil(pasta)
        testar_importacao(pasta)
        testar_correcao(pasta)
        testar_aprovacao(pasta)
        testar_condicoes_de_aprovacao(pasta)
        testar_tudo_ou_nada(pasta)
        testar_concorrencia(pasta)
    print("OK - store da NFS-e (schema idempotente, perfil versionado e imutavel, "
          "origem pelo SHA-256, correcao preserva o bruto, exclusao reversivel, "
          "rodadas, aprovacao tudo ou nada, duplicata e numeracao garantidas "
          "pelo banco sob concorrencia, descarte terminal que libera chaves, "
          "triggers de imutabilidade) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
