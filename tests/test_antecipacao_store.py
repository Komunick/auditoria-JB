"""Persistencia da Antecipacao/DIFAL do ICMS-BA (spec 027).

Duplicidade pela chave, memoria por item, decisao humana nas excecoes,
aprovacao, reabertura, totais por empresa/periodo, tabela por vigencia e a
trilha gravada na mesma transacao.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import antecipacao_ba as ab  # noqa: E402
from auditoria_fiscal.core.antecipacao_nfe import ler_nfe  # noqa: E402
from auditoria_fiscal.ferramentas.antecipacao_store import (  # noqa: E402
    AntecipacaoStore, ConcorrenciaError, agrupar)

import nfe_sintetica as fab  # noqa: E402

QUEM = {"usuario_id": 7, "usuario_login": "ana"}


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def levanta(funcao, codigo: str, msg: str):
    try:
        funcao()
    except ab.ErroAntecipacao as exc:
        checar(exc.codigo == codigo, f"{msg}: veio {exc.codigo}")
        return
    checar(False, f"{msg}: deveria recusar")


def importar(store, xml: bytes, *, metodo=ab.METODO_POR_DENTRO,
             presuncao=False, finalidade="revenda") -> dict:
    return store.importar(
        ler_nfe(xml), sha256="a" * 64,
        parametros=ab.validar_parametros(metodo, presuncao,
                                         store.configuracao()["componentes"]),
        finalidade=finalidade, **QUEM)


def tipos(store, nota_id=None) -> list[str]:
    conn = sqlite3.connect(store.db_path)
    try:
        if nota_id is None:
            return [l[0] for l in conn.execute(
                "SELECT tipo FROM evento ORDER BY id")]
        return [l[0] for l in conn.execute(
            "SELECT tipo FROM evento WHERE nota_id=? ORDER BY id", (nota_id,))]
    finally:
        conn.close()


def main() -> int:
    pasta = tempfile.mkdtemp(prefix="antecipacao_store_")
    caminho = os.path.join(pasta, "antecipacao.db")
    store = AntecipacaoStore(caminho)

    # ------------------------------------------------------------------
    # Carga inicial e idempotencia da migracao

    checar(store.contar("aliquota") == 28, store.contar("aliquota"))
    store.fechar()
    store = AntecipacaoStore(caminho)
    checar(store.contar("aliquota") == 28, "reabrir o banco nao pode duplicar")
    config = store.configuracao()
    checar(config["metodo_padrao"] == ab.METODO_POR_DENTRO
           and config["reducao_percentual"] == "20"
           and config["dia_vencimento"] == 25, config)

    # ------------------------------------------------------------------
    # Importacao: os tres exemplos da especificacao

    r1 = importar(store, fab.nota_sp_com_destaque(1))
    checar(r1["situacao"] == "importada" and r1["a_recolher"] == 16981
           and r1["pendentes"] == 0, r1)

    # Sem presuncao autorizada: fica pendente e NAO soma zero como se fosse valor.
    r2 = importar(store, fab.nota_go_sem_destaque(2))
    checar(r2["situacao"] == "importada" and r2["pendentes"] == 1
           and r2["a_recolher"] == 0, r2)
    d2 = store.detalhar(r2["nota_id"])
    checar(d2["itens"][0]["a_recolher"] is None,
           "item sem credito tem de ficar SEM valor, nao com zero")
    checar(d2["itens"][0]["decisao"] == "", d2["itens"][0]["decisao"])

    r3 = importar(store, fab.nota_importado_sem_destaque(3), presuncao=True)
    checar(r3["a_recolher"] == 20755 and r3["pendentes"] == 0, r3)

    # Duplicidade pela chave: nada e' sobrescrito.
    de_novo = importar(store, fab.nota_sp_com_destaque(1),
                       metodo=ab.METODO_DIFERENCA)
    checar(de_novo["situacao"] == "duplicada"
           and de_novo["nota_id"] == r1["nota_id"], de_novo)
    checar(store.contar("nota") == 3, store.contar("nota"))
    checar(store.detalhar(r1["nota_id"])["metodo"] == ab.METODO_POR_DENTRO,
           "a segunda importacao nao pode trocar o metodo da primeira")

    # Fora do escopo: nao entra.
    fora = importar(store, fab.xml_nfe([fab.item(p_icms="18.00", v_icms="180.00")],
                                       uf="BA", numero=9))
    checar(fora["situacao"] == "recusada" and fora["codigo"] == ab.R_ORIGEM_BA,
           fora)
    checar(store.contar("nota") == 3, "nota recusada nao pode ser gravada")

    # ------------------------------------------------------------------
    # Revisao: autorizar a presuncao refaz a conta

    levanta(lambda: store.alterar_nota(r2["nota_id"], {"metodo": "inventado"},
                                       revision=d2["revision"], **QUEM),
            "METODO_INVALIDO", "metodo desconhecido")
    try:
        store.alterar_nota(r2["nota_id"], {"presuncao": True}, revision=99,
                           **QUEM)
        checar(False, "revision errada deveria ser recusada")
    except ConcorrenciaError as exc:
        checar(exc.revision_atual == d2["revision"], exc.revision_atual)

    d2 = store.alterar_nota(r2["nota_id"], {"presuncao": True},
                            revision=d2["revision"], **QUEM)
    checar(d2["a_recolher"] == 10692 and d2["pendentes"] == 0, d2["a_recolher"])
    checar(d2["itens"][0]["memoria"]["tipo_credito"] == ab.CREDITO_CALCULADO,
           d2["itens"][0]["memoria"])
    checar(d2["itens"][0]["decisao_origem"] == "automatica", d2["itens"][0])

    # Trocar o metodo muda o numero e fica na trilha.
    d2 = store.alterar_nota(r2["nota_id"], {"metodo": ab.METODO_DIFERENCA,
                                            "competencia": "11/2026"},
                            revision=d2["revision"], **QUEM)
    checar(d2["a_recolher"] == 8500 and d2["competencia"] == "2026-11", d2)
    d2 = store.alterar_nota(r2["nota_id"], {"metodo": ab.METODO_POR_DENTRO,
                                            "competencia": "10/2026"},
                            revision=d2["revision"], **QUEM)
    checar(d2["a_recolher"] == 10692, d2["a_recolher"])
    checar(tipos(store, r2["nota_id"]) == ["nota_importada", "nota_alterada",
                                           "nota_alterada", "nota_alterada"],
           tipos(store, r2["nota_id"]))

    # ------------------------------------------------------------------
    # Excecoes: decisao humana, com motivo

    mista = fab.xml_nfe([
        fab.item(v_prod="1000.00", p_icms="7.00", v_icms="70.00"),
        fab.item(v_prod="500.00", grupo="ICMS10", cst="10", p_icms="7.00",
                 v_icms="35.00", cfop="6403"),
        fab.item(v_prod="200.00", grupo="ICMS40", cst="40"),
        fab.item(v_prod="300.00", p_icms="7.00", v_icms="21.00"),
    ], uf="SP", numero=4)
    r4 = importar(store, mista, finalidade="")
    d4 = store.detalhar(r4["nota_id"])
    checar(d4["pendentes"] == 4 and d4["a_recolher"] == 0,
           "sem finalidade nada pode ser proposto")
    ids = [i["id"] for i in d4["itens"]]

    d4 = store.alterar_itens(r4["nota_id"], ids, finalidade="revenda",
                             revision=d4["revision"], **QUEM)
    decisoes = [i["decisao"] for i in d4["itens"]]
    checar(decisoes == ["calcular", "", "", "calcular"], decisoes)
    # 169,81 + (300 -> 50,94): so os dois itens limpos.
    checar(d4["a_recolher"] == 16981 + 5094, d4["a_recolher"])

    levanta(lambda: store.aprovar(r4["nota_id"], revision=d4["revision"], **QUEM),
            "REGIME_NAO_INFORMADO", "aprovar sem regime")
    store.definir_regime(fab.CNPJ_DEST, ab.REGIME_SIMPLES, **QUEM)
    levanta(lambda: store.aprovar(r4["nota_id"], revision=d4["revision"], **QUEM),
            "ITENS_SEM_DECISAO", "aprovar com item pendente")

    # ST: mandar calcular exige motivo; deixar fora, tambem.
    levanta(lambda: store.alterar_itens(r4["nota_id"], [ids[1]],
                                        decisao="calcular",
                                        revision=d4["revision"], **QUEM),
            "MOTIVO_OBRIGATORIO", "calcular ST sem motivo")
    levanta(lambda: store.alterar_itens(r4["nota_id"], [ids[1]],
                                        decisao="excluir",
                                        revision=d4["revision"], **QUEM),
            "MOTIVO_OBRIGATORIO", "excluir sem motivo")
    d4 = store.alterar_itens(r4["nota_id"], [ids[1]], decisao="excluir",
                             motivo="Produto do Anexo 1: ST na origem",
                             revision=d4["revision"], **QUEM)
    # Isento sem destaque e sem presuncao: nao ha o que calcular.
    levanta(lambda: store.alterar_itens(r4["nota_id"], [ids[2]],
                                        decisao="calcular", motivo="quero calcular",
                                        revision=d4["revision"], **QUEM),
            "ITEM_SEM_CALCULO", "calcular item sem credito")
    d4 = store.alterar_itens(r4["nota_id"], [ids[2]], decisao="excluir",
                             motivo="Isento na origem, conferido na nota",
                             revision=d4["revision"], **QUEM)
    checar(d4["pendentes"] == 0 and d4["a_recolher"] == 22075, d4)
    checar(d4["itens"][1]["decisao_por_login"] == "ana"
           and d4["itens"][1]["decisao_origem"] == "revisor", d4["itens"][1])

    # Item de outra nota nao pode ser alterado por esta.
    try:
        store.alterar_itens(r4["nota_id"], [d2["itens"][0]["id"]],
                            finalidade="ativo", revision=d4["revision"], **QUEM)
        checar(False, "item de outra nota deveria ser recusado")
    except LookupError:
        pass

    # Grupos por CFOP e aliquota.
    grupos = {(g["cfop"], g["aliquota"]): g for g in d4["grupos"]}
    checar(set(grupos) == {("6102", "7"), ("6403", "7"), ("6102", "")},
           set(grupos))
    checar(grupos[("6102", "7")]["itens"] == 2
           and grupos[("6102", "7")]["a_recolher"] == 22075
           and grupos[("6102", "7")]["valor_operacao"] == 130000,
           grupos[("6102", "7")])
    checar(grupos[("6403", "7")]["fora"] == 1, grupos[("6403", "7")])
    checar(agrupar([]) == [], "sem itens, sem grupos")

    # ------------------------------------------------------------------
    # Aprovacao, imutabilidade e reabertura

    d4 = store.aprovar(r4["nota_id"], revision=d4["revision"], **QUEM)
    checar(d4["estado"] == "aprovada" and d4["aprovada_por_login"] == "ana", d4)
    levanta(lambda: store.alterar_nota(r4["nota_id"], {"presuncao": True},
                                       revision=d4["revision"], **QUEM),
            "NOTA_APROVADA", "alterar nota aprovada")
    levanta(lambda: store.excluir_nota(r4["nota_id"], "apagar mesmo",
                                       revision=d4["revision"], **QUEM),
            "NOTA_APROVADA", "excluir nota aprovada")
    conn = sqlite3.connect(caminho)
    for sql in ("UPDATE item SET a_recolher=1 WHERE nota_id=%d" % r4["nota_id"],
                "DELETE FROM nota WHERE id=%d" % r4["nota_id"],
                "UPDATE evento SET detalhe='x'", "DELETE FROM evento",
                "UPDATE aliquota SET percentual='1'", "DELETE FROM aliquota"):
        try:
            conn.execute(sql)
            conn.commit()
            checar(False, f"o banco deveria recusar: {sql}")
        except sqlite3.DatabaseError:
            conn.rollback()
    conn.close()

    levanta(lambda: store.reabrir(r4["nota_id"], "", revision=d4["revision"],
                                  **QUEM),
            "MOTIVO_OBRIGATORIO", "reabrir sem motivo")
    d4 = store.reabrir(r4["nota_id"], "Finalidade do item 4 estava errada",
                       revision=d4["revision"], **QUEM)
    checar(d4["estado"] == "em_revisao" and d4["aprovada_por_login"] == "", d4)
    d4 = store.alterar_itens(r4["nota_id"], [ids[3]], finalidade="uso_consumo",
                             revision=d4["revision"], **QUEM)
    checar(d4["itens"][1]["decisao"] == "excluir",
           "a decisao do revisor sobrevive ao recalculo")
    d4 = store.aprovar(r4["nota_id"], revision=d4["revision"], **QUEM)

    # ------------------------------------------------------------------
    # Totais por empresa e periodo

    d1 = store.detalhar(r1["nota_id"])
    store.aprovar(r1["nota_id"], revision=d1["revision"], **QUEM)
    linha = store.resumo(competencia="10/2026")
    checar(len(linha) == 1, linha)
    linha = linha[0]
    # Aprovadas: nota 1 (169,81) e nota 4 (220,75). Em revisao: 2 e 3.
    checar(linha["aprovado"] == 16981 + 22075, linha["aprovado"])
    checar(linha["em_revisao"] == 10692 + 20755, linha["em_revisao"])
    checar(linha["notas"] == 4 and linha["aprovadas"] == 2, linha)
    # Reducao simulada so sobre REVENDA: o item 4 da nota 4 virou uso e consumo.
    checar(linha["aprovado_revenda"] == 16981 + 16981, linha["aprovado_revenda"])
    checar(linha["reducao_simulada"] == 6792, linha["reducao_simulada"])
    checar(linha["aprovado_com_reducao"] == 39056 - 6792, linha)
    checar(linha["vencimento_referencia"] == "2026-11-25", linha)
    checar(store.resumo(competencia="09/2026") == [], "mes sem nota")

    store.definir_regime(fab.CNPJ_DEST, "outro", **QUEM)
    checar(store.resumo()[0]["reducao_simulada"] is None,
           "fora do Simples nao ha simulacao de reducao")
    store.definir_regime(fab.CNPJ_DEST, ab.REGIME_SIMPLES, **QUEM)

    exportados = store.itens_para_exportar(competencia="2026-10",
                                           estado="aprovada")
    checar(len(exportados) == 5, len(exportados))
    checar(store.listar_notas(estado="em_revisao")["total"] == 2, "filtro")
    checar(store.listar_notas(texto="FORNECEDOR")["total"] == 4, "busca")

    # ------------------------------------------------------------------
    # Exclusao de nota em revisao: some a nota, fica o evento

    d3 = store.detalhar(r3["nota_id"])
    saida = store.excluir_nota(r3["nota_id"], "XML importado na empresa errada",
                               revision=d3["revision"], **QUEM)
    checar(saida["chave"] == d3["chave"], saida)
    checar(store.contar("nota") == 3, store.contar("nota"))
    checar(tipos(store, r3["nota_id"]) == ["nota_importada", "nota_excluida"],
           tipos(store, r3["nota_id"]))
    de_volta = importar(store, fab.nota_importado_sem_destaque(3), presuncao=True)
    checar(de_volta["situacao"] == "importada", "chave liberada apos a exclusao")

    # ------------------------------------------------------------------
    # Tabela por vigencia: nova aliquota fecha a anterior e nao mexe no aprovado

    antes = store.detalhar(r1["nota_id"])["a_recolher"]
    levanta(lambda: store.criar_aliquota({
        "tipo": "interna", "percentual": "22", "vigencia_inicio": "2026-10-01",
        "vigencia_fim": "2026-10-31", "base_legal": "teste"}, **QUEM),
        "VIGENCIA_SOBREPOSTA", "vigencia sobreposta com fim")
    store.criar_aliquota({"tipo": "interna", "percentual": "22",
                          "vigencia_inicio": "01/10/2026",
                          "base_legal": "Lei de teste"}, **QUEM)
    internas = [l for l in store.aliquotas() if l["tipo"] == "interna"]
    checar([(l["percentual"], l["vigencia_inicio"], l["vigencia_fim"])
            for l in internas]
           == [("22", "2026-10-01", ""), ("20.5", "2024-02-07", "2026-09-30")],
           internas)
    checar(store.detalhar(r1["nota_id"])["a_recolher"] == antes,
           "nota aprovada nao muda quando a tabela muda")
    # Nota em revisao passa a usar a aliquota nova no proximo recalculo.
    d2 = store.detalhar(r2["nota_id"])
    d2 = store.alterar_nota(r2["nota_id"], {"metodo": ab.METODO_DIFERENCA},
                            revision=d2["revision"], **QUEM)
    checar(d2["itens"][0]["memoria"]["aliquota_interna"] == "22"
           and d2["a_recolher"] == 10000, d2["a_recolher"])
    encerrada = store.encerrar_aliquota(internas[0]["id"], "31/12/2026", **QUEM)
    checar(encerrada["vigencia_fim"] == "2026-12-31", encerrada)
    levanta(lambda: store.encerrar_aliquota(internas[0]["id"], "2027-01-31",
                                            **QUEM),
            "JA_ENCERRADA", "encerrar duas vezes")

    # ------------------------------------------------------------------
    # Configuracao

    levanta(lambda: store.definir_configuracao({"dia_vencimento": 31}, **QUEM),
            "DIA_INVALIDO", "dia 31")
    nova = store.definir_configuracao({"metodo_padrao": ab.METODO_DIFERENCA,
                                       "componentes": {"ipi": False},
                                       "reducao_percentual": "20,0"}, **QUEM)
    checar(nova["metodo_padrao"] == ab.METODO_DIFERENCA
           and nova["componentes"]["ipi"] is False
           and nova["componentes"]["frete"] is True, nova)
    gerais = [e["tipo"] for e in store.eventos_gerais()]
    for esperado in ("configuracao_alterada", "aliquota_criada",
                     "aliquota_encerrada", "regime_definido", "nota_excluida"):
        checar(esperado in gerais, f"{esperado} fora da trilha: {gerais}")

    # Falha no meio nao deixa meia mudanca: a decisao invalida no segundo item
    # desfaz a do primeiro (mesma transacao).
    dupla = fab.xml_nfe([
        fab.item(grupo="ICMS10", cst="10", p_icms="7.00", v_icms="70.00"),
        fab.item(grupo="ICMS40", cst="40"),
    ], uf="SP", numero=5)
    r5 = importar(store, dupla)
    d5 = store.detalhar(r5["nota_id"])
    eventos_antes = store.contar("evento")
    levanta(lambda: store.alterar_itens(
        r5["nota_id"], [i["id"] for i in d5["itens"]], decisao="calcular",
        motivo="calcular os dois", revision=d5["revision"], **QUEM),
        "ITEM_SEM_CALCULO", "segundo item nao calculavel")
    depois = store.detalhar(r5["nota_id"])
    checar([i["decisao"] for i in depois["itens"]] == ["", ""]
           and depois["revision"] == d5["revision"]
           and store.contar("evento") == eventos_antes,
           "a transacao deveria ter sido desfeita por inteiro")

    store.fechar()
    print("OK - antecipacao store: duplicidade, revisao, aprovacao, totais e trilha")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
