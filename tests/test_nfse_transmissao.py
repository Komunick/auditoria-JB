"""Transmissao de lote a producao restrita (spec 008, US1, US2 e US4).

Banco (schema 2) + orquestracao contra a Sefin FALSA: situacao por DPS,
tentativas imutaveis com o XML assinado, NFS-e e DANFSe guardados, e o que
mais importa — nenhuma DPS e' enviada duas vezes quando o resultado e'
incerto, quando a Sefin diz que ja existe (E0014), quando o processo caiu no
meio (`enviando` velha) ou quando duas transmissoes correm juntas.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
import tempfile
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_assinatura as na  # noqa: E402
from auditoria_fiscal.core import nfse_certificado as nc  # noqa: E402
from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_sefin as sf  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_store as ns  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_transmissao as nt  # noqa: E402
from fixtures import nfse as fx  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402
from fixtures.nfse.sefin_falsa import SefinFalsa  # noqa: E402

HOJE = dt.date(2026, 11, 15)
AGORA = dt.datetime(2026, 11, 15, 10, 30, tzinfo=nd.FUSO_SALVADOR)
U = {"usuario_id": 7, "usuario_login": "atendente"}
FISCAL = {"usuario_id": 8, "usuario_login": "fiscal"}


def texto(competencia: str) -> str:
    return (f"Competência: {competencia}\nResponsável: Ana Exemplo\nCPF: {fx.CPF_ANA}\n"
            "Aluno: Pedro Exemplo\nTurma: Berçário\nValor: 1.250,00\n\n"
            f"Competência: {competencia}\nResponsável: Bruno Teste\nCPF: {fx.CPF_BRUNO}\n"
            "Aluno: Caio Teste\nTurma: Infantil 2\nValor: 980,50\n\n"
            f"Competência: {competencia}\nResponsável: Carla Teste\nCPF: {fx.CPF_CARLA}\n"
            "Aluno: Lia Exemplo\nTurma: Berçário\nValor: 1.100,00\n")


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def codigo_do_erro(funcao, *args, **kwargs) -> str | None:
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc.codigo
    return None


def lote_aprovado(store, perfil_id: int, competencia: str) -> int:
    r = store.importar_texto(perfil_id, texto(competencia), hoje=HOJE, **U)
    lote = store.lote(r["lote_id"])
    checar(lote["conferencia"]["totais"]["bloqueio"] == 0, lote["conferencia"]["totais"])
    store.aprovar(r["lote_id"], revision=lote["lote"]["revision"], agora=AGORA, **FISCAL)
    return r["lote_id"]


def situacoes(store, lote_id: int) -> list[str]:
    return [d["situacao"] for d in store.dps_para_transmitir(lote_id)]


def main() -> int:
    pasta = tempfile.mkdtemp(prefix="nfse_transm_teste_")
    kit = cf.montar_kit(os.path.join(pasta, "kit"))
    falsa = SefinFalsa(kit, atraso=2.5)
    base = falsa.iniciar()
    try:
        cert = nc.ler_pfx(kit.pfx(), cf.SENHA)

        def cliente(**extra):
            opcoes = dict(url_sefin=base + "/SefinNacional", url_adn=base,
                          ca_extra=kit.ca_pem, timeout=1.5)
            opcoes.update(extra)
            return sf.ClienteSefin(cert, **opcoes)

        caminho = os.path.join(pasta, "nfse.db")
        store = ns.NfseStore(caminho, os.path.join(pasta, "origens"))
        perfil_id = store.criar_perfil(fx.perfil_completo(), **U)["perfil_id"]

        def transmitir(lote_id, c=None, **extra):
            return nt.transmitir_lote(store, lote_id, c or cliente(), cert, **FISCAL,
                                      **extra)

        # Lote em revisao nao transmite.
        r = store.importar_texto(perfil_id, texto("09/2026"), hoje=HOJE, **U)
        checar(codigo_do_erro(transmitir, r["lote_id"]) == ns.ESTADO_INVALIDO,
               "lote em revisao")

        # ----------------------------------------------------------------
        # US1: autorizada, rejeitada, autorizada
        lote_a = lote_aprovado(store, perfil_id, "11/2026")
        outro = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(kit.ac, cnpj=cf.OUTRO_CNPJ)), cf.SENHA)
        checar(codigo_do_erro(nt.transmitir_lote, store, lote_a, cliente(), outro, **FISCAL)
               == nc.CERTIFICADO_DE_OUTRO_CNPJ, "certificado de outro CNPJ")
        checar(falsa.posts == [], "nada sai com certificado errado")

        falsa.programar("normal", ("400", "E0312", "Código inexistente."), "normal")
        resumo = transmitir(lote_a)
        checar((resumo["autorizadas"], resumo["rejeitadas"], resumo["interrompida"])
               == (2, 1, None), resumo)
        checar(situacoes(store, lote_a) == [ns.AUTORIZADA, ns.REJEITADA, ns.AUTORIZADA],
               situacoes(store, lote_a))
        dps_a = store.dps_para_transmitir(lote_a)
        checar(len(falsa.posts) == 3 and falsa.posts == [d["id_dps"] for d in dps_a],
               "uma POST por DPS, em ordem de numero")
        checar(dps_a[1]["erros"][0]["codigo"] == "E0312", dps_a[1])
        nfse = store.nfse_da_dps(dps_a[0]["id"])
        checar(nfse and nfse["chave_acesso"] == dps_a[0]["chave_acesso"]
               and bytes(nfse["xml"]).startswith(b"<?xml") and nfse["origem"] == "envio",
               nfse and {k: nfse[k] for k in ("chave_acesso", "origem")})
        checar(store.danfse_da_dps(dps_a[0]["id"]).startswith(b"%PDF"), "DANFSe guardado")
        tentativas = store.tentativas(dps_a[0]["id"])
        checar(len(tentativas) == 1 and tentativas[0]["operacao"] == "envio"
               and tentativas[0]["resultado"] == ns.AUTORIZADA, tentativas)
        assinado = bytes(tentativas[0]["xml_assinado"])
        checar(na.conferir_assinatura(assinado)["cnpj"] == cf.CNPJ,
               "a tentativa guarda o XML assinado que foi enviado")
        checar(tentativas[0]["certificado_cnpj"] == cf.CNPJ
               and tentativas[0]["certificado_impressao"] == cert.impressao, tentativas[0])
        lote = store.lote(lote_a)
        checar([d["situacao"] for d in lote["dps"]] == situacoes(store, lote_a),
               "a tela do lote mostra a situacao")
        checar(lote["dps"][1]["erros"][0]["codigo"] == "E0312", lote["dps"][1])

        # Imutabilidade.
        conn = sqlite3.connect(caminho)
        for sql in ("UPDATE transmissao SET resultado='x'", "DELETE FROM transmissao",
                    "UPDATE nfse SET chave_acesso='x'", "DELETE FROM nfse",
                    f"UPDATE dps_situacao SET situacao='rejeitada' WHERE dps_id={dps_a[0]['id']}",
                    "DELETE FROM dps_situacao"):
            try:
                conn.execute(sql)
                conn.commit()
                checar(False, f"deveria ser recusado: {sql}")
            except sqlite3.DatabaseError:
                conn.rollback()
        conn.close()

        # Rodar de novo nao reenvia nada; rejeitada so com pedido explicito.
        resumo = transmitir(lote_a)
        checar(len(falsa.posts) == 3 and resumo["puladas"] == 3, resumo)
        resumo = transmitir(lote_a, incluir_rejeitadas=True)
        checar(len(falsa.posts) == 4 and resumo["autorizadas"] == 1, resumo)
        checar(situacoes(store, lote_a) == [ns.AUTORIZADA] * 3, situacoes(store, lote_a))

        # US4: lote com NFS-e nao e' descartado.
        rev = store.lote(lote_a)["lote"]["revision"]
        checar(codigo_do_erro(store.descartar, lote_a, revision=rev, motivo="teste", **FISCAL)
               == ns.LOTE_COM_NFSE, "descarte de lote com NFS-e")

        # ----------------------------------------------------------------
        # US2: incerto -> consulta antes de reenviar
        lote_b = lote_aprovado(store, perfil_id, "10/2026")
        ids_b = [d["id_dps"] for d in store.dps_para_transmitir(lote_b)]
        falsa.programar("emitir_e_500")
        resumo = transmitir(lote_b)
        checar(resumo["incertas"] == 1 and resumo["interrompida"], resumo)
        checar(situacoes(store, lote_b) == [ns.INCERTA, ns.GERADA, ns.GERADA],
               situacoes(store, lote_b))

        falsa.programar("emitir_e_demorar")
        resumo = transmitir(lote_b)
        checar(falsa.posts.count(ids_b[0]) == 1, "a DPS que virou nota nao e' reenviada")
        checar(resumo["ja_existiam"] == 1 and resumo["incertas"] == 1, resumo)
        checar(situacoes(store, lote_b) == [ns.AUTORIZADA, ns.INCERTA, ns.GERADA],
               situacoes(store, lote_b))
        primeira = store.dps_para_transmitir(lote_b)[0]
        checar(store.nfse_da_dps(primeira["id"])["origem"] == "consulta",
               "NFS-e baixada pela consulta")
        checar([t["operacao"] for t in store.tentativas(primeira["id"])]
               == ["envio", "consulta"], store.tentativas(primeira["id"]))

        resumo = transmitir(lote_b)
        checar(falsa.posts.count(ids_b[1]) == 1 and falsa.posts.count(ids_b[2]) == 1,
               "nem a do tempo esgotado e' reenviada; a terceira vai uma vez")
        checar(situacoes(store, lote_b) == [ns.AUTORIZADA] * 3, situacoes(store, lote_b))
        checar(resumo["interrompida"] is None, resumo)

        # E0014: a Sefin ja tem a nota, o banco nao sabia.
        lote_c = lote_aprovado(store, perfil_id, "08/2026")
        dps_c = store.dps_para_transmitir(lote_c)
        falsa._emitir(dps_c[0]["id_dps"],
                      na.assinar_dps(bytes(store.dps(dps_c[0]["id"])["xml"]), cert))
        # `enviando` velha (processo caiu) vira incerta; nova (outra transmissao
        # em curso) e' respeitada.
        store._conn.execute(
            "INSERT INTO dps_situacao(dps_id, situacao, desde, tentativas) VALUES(?,?,?,0)",
            (dps_c[1]["id"], ns.ENVIANDO,
             (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)).isoformat()))
        store._conn.execute(
            "INSERT INTO dps_situacao(dps_id, situacao, desde, tentativas) VALUES(?,?,?,0)",
            (dps_c[2]["id"], ns.ENVIANDO, ns.agora_iso()))
        checar(situacoes(store, lote_c) == [ns.GERADA, ns.INCERTA, ns.ENVIANDO],
               situacoes(store, lote_c))
        resumo = transmitir(lote_c)
        checar(situacoes(store, lote_c) == [ns.AUTORIZADA, ns.AUTORIZADA, ns.ENVIANDO],
               situacoes(store, lote_c))
        checar([t["resultado"] for t in store.tentativas(dps_c[0]["id"])]
               == [ns.REJEITADA, "ja_existia"], store.tentativas(dps_c[0]["id"]))
        checar([t["resultado"] for t in store.tentativas(dps_c[1]["id"])]
               == ["nao_existe", ns.AUTORIZADA], store.tentativas(dps_c[1]["id"]))
        checar(falsa.posts.count(dps_c[2]["id_dps"]) == 0 and resumo["puladas"] == 1,
               "enviando recente nao e' tocada")

        # 403 e sem conexao: interrompem e devolvem a DPS como estava.
        lote_d = lote_aprovado(store, perfil_id, "07/2026")
        falsa.programar("403")
        resumo = transmitir(lote_d)
        checar(resumo["interrompida"] and situacoes(store, lote_d) == [ns.GERADA] * 3,
               (resumo, situacoes(store, lote_d)))
        primeira = store.dps_para_transmitir(lote_d)[0]
        checar(store.tentativas(primeira["id"])[-1]["resultado"] == sf.CERTIFICADO_RECUSADO,
               store.tentativas(primeira["id"]))
        quantos = len(falsa.posts)
        resumo = transmitir(lote_d, c=cliente(ca_extra=None))
        checar(resumo["interrompida"] and len(falsa.posts) == quantos
               and situacoes(store, lote_d) == [ns.GERADA] * 3, resumo)

        # Duas transmissoes ao mesmo tempo: cada DPS vai uma vez so.
        lote_e = lote_aprovado(store, perfil_id, "06/2026")
        ids_e = [d["id_dps"] for d in store.dps_para_transmitir(lote_e)]
        erros: list = []

        def em_paralelo():
            outro_store = ns.NfseStore(caminho, os.path.join(pasta, "origens"))
            try:
                nt.transmitir_lote(outro_store, lote_e, cliente(), cert, **FISCAL)
            except Exception as exc:  # noqa: BLE001
                erros.append(exc)
            finally:
                outro_store.fechar()

        fios = [threading.Thread(target=em_paralelo) for _ in range(2)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()
        checar(not erros, erros)
        checar(all(falsa.posts.count(i) == 1 for i in ids_e),
               [falsa.posts.count(i) for i in ids_e])
        checar(situacoes(store, lote_e) == [ns.AUTORIZADA] * 3, situacoes(store, lote_e))

        # Trilha de dominio sem dado pessoal.
        eventos = store.eventos(lote_a)
        tipos = {e["tipo"] for e in eventos}
        checar({"transmissao_iniciada", "dps_autorizada", "dps_rejeitada",
                "transmissao_concluida"} <= tipos, tipos)
        texto_eventos = str(eventos)
        checar("Ana Exemplo" not in texto_eventos and "12345678909" not in texto_eventos,
               "trilha de transmissao sem nome nem CPF")
        store.fechar()
    finally:
        falsa.parar()

    print("OK - transmissao (autorizada/rejeitada, tentativas imutaveis com XML "
          "assinado, NFS-e e DANFSe, incerta consultada antes de reenviar, E0014, "
          "enviando velha, 403, sem conexao, concorrencia, descarte bloqueado) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
