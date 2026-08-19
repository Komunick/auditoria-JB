"""Persistencia da Conciliacao Fiscal (SQLite dedicado, sem camada web).

Cobre schema idempotente, dinheiro em centavos inteiros, deduplicacao por
SHA-256, criacao de versao candidata e conflito para a mesma chave, duas
importacoes concorrentes do mesmo arquivo, imutabilidade da trilha fiscal e
lote abandonado marcado como interrompido no reinicio.

O store recebe caminhos e identidade por injecao: nada aqui conhece FastAPI,
sessao HTTP ou request.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tests"))

from fixtures import conciliacao as fx  # noqa: E402

from auditoria_fiscal.core import conciliacao_sefaz as cs  # noqa: E402
from auditoria_fiscal.ferramentas import conciliacao_store as st  # noqa: E402

ANA = {"usuario_id": 7, "usuario_login": "ana"}


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def abrir(pasta: str) -> st.ConciliacaoStore:
    return st.ConciliacaoStore(
        db_path=os.path.join(pasta, "conciliacao.db"),
        origens_path=os.path.join(pasta, "origens"))


def importar(store, caminho: str, *, nome: str = "", ordem: int = 1,
             lote_id: int | None = None):
    if lote_id is None:
        lote_id = store.abrir_lote(sessao_id="s1", total_arquivos=1, **ANA)
    return store.importar_arquivo(
        lote_id, caminho_staging=caminho,
        nome_recebido=nome or os.path.basename(caminho), ordem=ordem, **ANA)


# ----------------------------------------------------------------------


def testar_schema_idempotente(pasta: str) -> None:
    """Abrir o banco varias vezes nao pode falhar nem perder dado."""
    caminho = os.path.join(pasta, "conciliacao.db")
    origens = os.path.join(pasta, "origens")
    for _ in range(3):
        store = st.ConciliacaoStore(db_path=caminho, origens_path=origens)
        store.fechar()

    with sqlite3.connect(caminho) as conn:
        tabelas = {l[0] for l in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        esperadas = {"lote_importacao", "fonte_fiscal", "item_lote",
                     "conciliacao", "versao_conciliacao", "movimento_dimp",
                     "fato_extraido", "excecao_conciliacao",
                     "conflito_importacao", "revisao_conciliacao",
                     "evento_fiscal"}
        faltando = esperadas - tabelas
        checar(not faltando, f"tabelas ausentes: {faltando}")
        fk = conn.execute("PRAGMA foreign_keys").fetchone()
        checar(conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal",
               "o banco deveria estar em WAL")
    checar(os.path.isdir(origens), "a pasta de origens deveria ser criada")


def testar_importacao_basica(pasta: str) -> None:
    trabalho = os.path.join(pasta, "t1")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b1"))
    try:
        arquivo = fx.gerar_quadro_50_3_dimp(os.path.join(trabalho, "a.xlsx"))
        item = importar(store, arquivo)
        checar(item.resultado == "processado", f"{item.resultado}: {item.mensagem}")
        checar(item.sha256 and len(item.sha256) == 64, item.sha256)

        # A fonte foi preservada fora da sessao, nomeada pelo hash.
        destino = os.path.join(store.origens_path, f"{item.sha256}.xlsx")
        checar(os.path.isfile(destino), f"fonte durável ausente: {destino}")
        checar(os.path.getsize(destino) == os.path.getsize(arquivo),
               "a copia durável deveria ser identica")

        detalhe = store.detalhar(item.conciliacao_id)
        checar(detalhe["cnpj"] == fx.CNPJ_A, detalhe["cnpj"])
        checar(detalhe["competencia"] == "202401", detalhe["competencia"])
        checar(detalhe["estado"] == "em_revisao",
               f"toda conciliacao nova nasce Em revisao: {detalhe['estado']}")
        checar(detalhe["revision"] == 1, detalhe["revision"])

        vigente = detalhe["versao_vigente"]
        checar(vigente["estado"] == "vigente", vigente["estado"])
        checar(vigente["numero"] == 1, vigente["numero"])

        # DINHEIRO EM CENTAVOS INTEIROS: 40000.00 -> 4000000.
        checar(vigente["receita_declarada"] == 4000000,
               f"centavos: {vigente['receita_declarada']}")
        checar(vigente["receita_calculada"] == 4150000, vigente["receita_calculada"])
        checar(vigente["diferenca_receita"] == 150000, vigente["diferenca_receita"])
        checar(isinstance(vigente["receita_declarada"], int),
               "dinheiro no banco tem de ser INTEGER, nunca float")
        checar(vigente["total_pix"] == 900000, vigente["total_pix"])
        checar(vigente["total_nao_pix"] == 2200000, vigente["total_nao_pix"])

        checar(len(detalhe["movimentos"]) == 3, len(detalhe["movimentos"]))
        checar(len(detalhe["fatos"]) >= 9, len(detalhe["fatos"]))
        checar(any(e["codigo"] == cs.DIMP_ABAIXO_DA_CALCULADA
                   for e in detalhe["excecoes"]), detalhe["excecoes"])

        eventos = store.eventos(detalhe["id"])
        checar(any(e["acao"] == "importacao" for e in eventos),
               f"a importacao deveria gerar evento fiscal: {eventos}")
        checar(all(e["usuario_login"] == "ana" for e in eventos),
               "o ator do evento vem do snapshot, nunca do corpo")
    finally:
        store.fechar()


def testar_50_5_sem_dimp(pasta: str) -> None:
    """PIX e nao-PIX ficam NULL no 50-5; NULL nao pode virar 0."""
    trabalho = os.path.join(pasta, "t2")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b2"))
    try:
        arquivo = fx.gerar_quadro_50_5(os.path.join(trabalho, "b.xlsx"))
        item = importar(store, arquivo)
        checar(item.resultado == "processado", item.mensagem)
        vigente = store.detalhar(item.conciliacao_id)["versao_vigente"]
        checar(vigente["total_pix"] is None, f"pix: {vigente['total_pix']}")
        checar(vigente["total_nao_pix"] is None, vigente["total_nao_pix"])
    finally:
        store.fechar()


def testar_duplicata_por_sha(pasta: str) -> None:
    """Mesmo conteudo com outro nome: duplicado, sem nova fonte nem versao."""
    trabalho = os.path.join(pasta, "t3")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b3"))
    try:
        original = fx.gerar_quadro_50_5(os.path.join(trabalho, "orig.xlsx"))
        copia = os.path.join(trabalho, "renomeado.xlsx")
        shutil.copyfile(original, copia)

        lote = store.abrir_lote(sessao_id="s", total_arquivos=2, **ANA)
        primeiro = importar(store, original, ordem=1, lote_id=lote)
        segundo = importar(store, copia, ordem=2, lote_id=lote)

        checar(primeiro.resultado == "processado", primeiro.mensagem)
        checar(segundo.resultado == "duplicado",
               f"a copia renomeada deveria ser duplicada: {segundo.resultado}")
        checar(segundo.sha256 == primeiro.sha256, "mesmo conteudo, mesmo SHA")
        checar(segundo.conciliacao_id == primeiro.conciliacao_id,
               "a duplicata aponta para a conciliacao existente")

        checar(store.contar("fonte_fiscal") == 1, "uma unica fonte")
        checar(store.contar("versao_conciliacao") == 1, "uma unica versao")
        checar(store.contar("conciliacao") == 1, "uma unica conciliacao")
        checar(store.contar("item_lote") == 2, "os dois itens ficam no lote")

        resumo = store.concluir_lote(lote)
        checar(resumo["processados"] == 1 and resumo["duplicados"] == 1,
               f"resumo do lote: {resumo}")
    finally:
        store.fechar()


def testar_candidata_e_conflito(pasta: str) -> None:
    """Outro arquivo para a mesma chave nunca sobrescreve a vigente."""
    trabalho = os.path.join(pasta, "t4")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b4"))
    try:
        primeiro = fx.gerar_quadro_50_5(os.path.join(trabalho, "v1.xlsx"))
        retificado = fx.gerar_quadro_50_5(
            os.path.join(trabalho, "v2.xlsx"),
            valores=fx.valores_resumo(declarada_sem_st="30000.01"))

        a = importar(store, primeiro)
        b = importar(store, retificado)
        checar(a.resultado == "processado", a.mensagem)
        checar(b.resultado == "conflitante",
               f"o retificado deveria conflitar: {b.resultado}")
        checar(b.conciliacao_id == a.conciliacao_id, "mesma chave logica")

        detalhe = store.detalhar(a.conciliacao_id)
        checar(detalhe["versao_vigente"]["receita_declarada"] == 4000000,
               "a vigente NAO pode ter sido sobrescrita")
        candidatas = [v for v in detalhe["versoes"] if v["estado"] == "candidata"]
        checar(len(candidatas) == 1, f"uma candidata: {detalhe['versoes']}")
        checar(candidatas[0]["receita_declarada"] == 4000001, candidatas[0])
        checar(candidatas[0]["numero"] == 2, candidatas[0]["numero"])

        abertos = [c for c in detalhe["conflitos"] if c["estado"] == "aberto"]
        checar(len(abertos) == 1, f"um conflito aberto: {detalhe['conflitos']}")
        checar(abertos[0]["versao_vigente_id"] == detalhe["versao_vigente"]["id"],
               "o conflito guarda a vigente do instante em que nasceu")

        # A chegada da candidata devolve a conciliacao a Em revisao e
        # incrementa a revision exatamente uma vez.
        checar(detalhe["estado"] == "em_revisao", detalhe["estado"])
        checar(detalhe["revision"] == 2,
               f"a revision deveria ter subido para 2: {detalhe['revision']}")
        checar(any(r["estado_novo"] == "em_revisao"
                   for r in detalhe["revisoes"]),
               f"a volta a Em revisao e' uma revisao registrada: "
               f"{detalhe['revisoes']}")
    finally:
        store.fechar()


def testar_concorrencia(pasta: str) -> None:
    """Duas importacoes simultaneas do MESMO arquivo: uma fonte so."""
    trabalho = os.path.join(pasta, "t5")
    os.makedirs(trabalho, exist_ok=True)
    base = os.path.join(pasta, "b5")
    store = abrir(base)
    try:
        arquivo = fx.gerar_quadro_50_5(os.path.join(trabalho, "c.xlsx"))
        copias = []
        for i in range(4):
            copia = os.path.join(trabalho, f"c{i}.xlsx")
            shutil.copyfile(arquivo, copia)
            copias.append(copia)

        resultados: list = []
        erros: list = []
        barreira = threading.Barrier(len(copias))

        def _importar(indice: int) -> None:
            # Um store por thread: conexao SQLite nao atravessa thread.
            proprio = abrir(base)
            try:
                lote = proprio.abrir_lote(sessao_id=f"s{indice}",
                                          total_arquivos=1, **ANA)
                barreira.wait(timeout=10)
                resultados.append(proprio.importar_arquivo(
                    lote, caminho_staging=copias[indice],
                    nome_recebido=f"c{indice}.xlsx", ordem=1, **ANA))
            except Exception as exc:            # noqa: BLE001
                erros.append(exc)
            finally:
                proprio.fechar()

        threads = [threading.Thread(target=_importar, args=(i,))
                   for i in range(len(copias))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        checar(not erros, f"nenhuma importacao deveria estourar: {erros[:2]}")
        checar(len(resultados) == len(copias), f"resultados: {len(resultados)}")
        processados = [r for r in resultados if r.resultado == "processado"]
        duplicados = [r for r in resultados if r.resultado == "duplicado"]
        checar(len(processados) == 1,
               f"exatamente uma deveria processar: {[r.resultado for r in resultados]}")
        checar(len(duplicados) == len(copias) - 1,
               f"as demais sao duplicadas: {[r.resultado for r in resultados]}")
        checar(store.contar("fonte_fiscal") == 1, "uma unica fonte")
        checar(store.contar("versao_conciliacao") == 1, "uma unica versao")
        checar(len({r.sha256 for r in resultados}) == 1, "todas com o mesmo SHA")
    finally:
        store.fechar()


def testar_imutabilidade(pasta: str) -> None:
    """A trilha fiscal recusa UPDATE e DELETE no proprio SQL."""
    trabalho = os.path.join(pasta, "t6")
    os.makedirs(trabalho, exist_ok=True)
    base = os.path.join(pasta, "b6")
    store = abrir(base)
    try:
        arquivo = fx.gerar_quadro_50_3_dimp(os.path.join(trabalho, "d.xlsx"))
        importar(store, arquivo)
    finally:
        store.fechar()

    conn = sqlite3.connect(os.path.join(base, "conciliacao.db"))
    try:
        proibidos = [
            ("UPDATE fonte_fiscal SET nome_original='outro'", "fonte"),
            ("DELETE FROM fonte_fiscal", "fonte"),
            ("UPDATE movimento_dimp SET pix=0", "movimento"),
            ("DELETE FROM movimento_dimp", "movimento"),
            ("UPDATE fato_extraido SET valor_numerico=0", "fato"),
            ("DELETE FROM fato_extraido", "fato"),
            ("UPDATE evento_fiscal SET acao='nada'", "evento"),
            ("DELETE FROM evento_fiscal", "evento"),
            ("UPDATE versao_conciliacao SET receita_declarada=1", "valor da versao"),
            ("DELETE FROM versao_conciliacao", "versao"),
        ]
        for sql, alvo in proibidos:
            try:
                conn.execute(sql)
                conn.commit()
                checar(False, f"{alvo}: '{sql}' deveria ter sido recusado")
            except sqlite3.IntegrityError:
                conn.rollback()

        # A transicao de ESTADO da versao continua permitida (e' assim que a
        # promocao de candidata funciona).
        conn.execute("UPDATE versao_conciliacao SET estado='substituida'")
        conn.commit()
    finally:
        conn.close()


def testar_lote_interrompido(pasta: str) -> None:
    """Reinicio nao pode deixar lote eternamente 'processando' (FR-015)."""
    base = os.path.join(pasta, "b7")
    store = abrir(base)
    try:
        lote = store.abrir_lote(sessao_id="s", total_arquivos=3, **ANA)
        store.marcar_processando(lote)
        checar(store.obter_lote(lote)["estado"] == "processando",
               "o lote deveria estar processando")
    finally:
        store.fechar()

    # Simula a queda: o processo morre com o lote em processando.
    novo = abrir(base)
    try:
        estado = novo.obter_lote(lote)["estado"]
        checar(estado == "interrompido",
               f"na abertura, lote abandonado vira interrompido: {estado}")
        # Interrompido nao trava a chave: uma nova tentativa e' idempotente.
        outro = novo.abrir_lote(sessao_id="s", total_arquivos=1, **ANA)
        checar(outro != lote, "a nova tentativa e' outro lote")
    finally:
        novo.fechar()


def testar_rejeitado(pasta: str) -> None:
    """Erro fatal registra o item, sem criar conciliacao nem fonte."""
    trabalho = os.path.join(pasta, "t8")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b8"))
    try:
        ruim = fx.gerar_nao_xlsx(os.path.join(trabalho, "ruim.xlsx"))
        item = importar(store, ruim)
        checar(item.resultado == "rejeitado", item.resultado)
        checar(item.codigo_erro == cs.XLSX_INVALIDO, item.codigo_erro)
        checar(store.contar("fonte_fiscal") == 0,
               "arquivo rejeitado nao vira fonte")
        checar(store.contar("conciliacao") == 0,
               "erro fatal nao deixa conciliacao parcial")
        checar(store.contar("item_lote") == 1, "mas o item fica registrado")
        checar(not os.listdir(store.origens_path),
               "nada e' promovido para origens")
    finally:
        store.fechar()


def testar_consultas(pasta: str) -> None:
    """Resumo, listagem filtrada/paginada e detalhe completo (T032)."""
    trabalho = os.path.join(pasta, "t9")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b9"))
    try:
        for mes, gerar in (("202401", fx.gerar_quadro_50_5),
                           ("202402", fx.gerar_quadro_50_3_dimp),
                           ("202403", fx.gerar_quadro_50_5)):
            caminho = gerar(os.path.join(trabalho, "a" + mes + ".xlsx"),
                            competencia=mes)
            item = importar(store, caminho)
            checar(item.resultado == "processado", mes + ": " + item.mensagem)
        b = fx.gerar_quadro_50_3_dimp(os.path.join(trabalho, "b.xlsx"),
                                      cnpj=fx.CNPJ_B, razao_social=fx.RAZAO_B,
                                      competencia="202401")
        importar(store, b)

        resumo = store.resumo()
        checar(resumo["total"] == 4, resumo)
        checar(resumo["em_revisao"] == 4, resumo)
        checar(resumo["aprovadas"] == 0 and resumo["rejeitadas"] == 0, resumo)
        checar(resumo["avisos"] == 4, resumo)
        checar(resumo["bloqueios"] == 0, resumo)
        checar(isinstance(resumo["diferenca_total"], int),
               "diferenca_total em centavos inteiros")

        # Resumo e lista aplicam EXATAMENTE os mesmos filtros.
        for filtros, esperado in (
            ({"cnpj": fx.CNPJ_A}, 3),
            ({"cnpj": fx.CNPJ_B}, 1),
            ({"competencia_de": "202402"}, 2),
            ({"competencia_de": "202401", "competencia_ate": "202401"}, 2),
            ({"layout": "quadro_50_5"}, 2),
            ({"layout": "quadro_50_3_dimp"}, 2),
            ({"estado": "aprovada"}, 0),
            ({"texto": "BETA"}, 1),
            ({"excecao": "aviso"}, 4),
            ({"excecao": "bloqueio"}, 0),
        ):
            pagina = store.listar(**filtros)
            checar(pagina["total"] == esperado,
                   "lista " + str(filtros) + ": " + str(pagina["total"]))
            checar(store.resumo(**filtros)["total"] == esperado,
                   "resumo " + str(filtros) + " deveria bater com a lista")

        try:
            store.listar(coluna_inventada="x")
            checar(False, "filtro fora da allowlist deveria ser recusado")
        except ValueError:
            pass

        vistos = []
        for pag in (1, 2, 3, 4):
            p = store.listar(pagina=pag, limite=1)
            checar(p["limite"] == 1 and p["pagina"] == pag, p)
            checar(p["paginas"] == 4, p["paginas"])
            vistos += [i["id"] for i in p["itens"]]
        checar(len(vistos) == 4 and len(set(vistos)) == 4,
               "paginacao duplicou ou omitiu: " + str(vistos))
        todos = [i["id"] for i in store.listar(limite=100)["itens"]]
        checar(set(vistos) == set(todos), "as paginas cobrem a lista inteira")

        desc = [i["competencia"] for i in store.listar(
            cnpj=fx.CNPJ_A, ordenar="competencia_desc")["itens"]]
        checar(desc == sorted(desc, reverse=True), desc)
        asc = [i["competencia"] for i in store.listar(
            cnpj=fx.CNPJ_A, ordenar="competencia_asc")["itens"]]
        checar(asc == sorted(asc), asc)

        linha = store.listar(cnpj=fx.CNPJ_B)["itens"][0]
        checar(linha["razao_social"] == fx.RAZAO_B, linha["razao_social"])
        checar(linha["avisos_abertos"] >= 1, linha)
        checar(linha["bloqueios_abertos"] == 0, linha)
        checar(linha["conflitos_abertos"] == 0, linha)
        checar(linha["versao"]["layout"] == "quadro_50_3_dimp", linha["versao"])

        so_50_5 = store.listar(layout="quadro_50_5", cnpj=fx.CNPJ_A)["itens"][0]
        detalhe = store.detalhar(so_50_5["id"])
        checar(detalhe["versao_vigente"]["total_pix"] is None,
               "50-5 nao inventa PIX zero")
        checar(detalhe["fonte"]["sha256"], "o detalhe expoe a fonte e o hash")
        checar(detalhe["fonte"]["versao_parser"] == cs.VERSAO_PARSER,
               detalhe["fonte"])

        derivados = [f for f in detalhe["fatos"] if f["tipo_origem"] == "formula"]
        checar(derivados, "o detalhe precisa trazer os fatos derivados")
        dif = next(f for f in derivados if f["metrica"] == "diferenca_receita")
        checar(dif["formula"] == "receita_calculada - receita_declarada",
               dif["formula"])
        checar(set(dif["fatos_origem"]) == {"receita_calculada",
                                            "receita_declarada"},
               dif["fatos_origem"])
        celulas = [f for f in detalhe["fatos"] if f["tipo_origem"] == "celula"]
        checar(all(f["aba"] and f["celula"] for f in celulas),
               "todo fato de celula precisa de aba e celula")

        com_dimp = store.listar(layout="quadro_50_3_dimp",
                                cnpj=fx.CNPJ_A)["itens"][0]
        detalhe = store.detalhar(com_dimp["id"])
        checar(len(detalhe["movimentos"]) == 3,
               "as 3 linhas originais ficam: " + str(len(detalhe["movimentos"])))
        agregado = store.instituicoes(detalhe["versao_vigente"]["id"])
        checar(len(agregado) == 2, agregado)
        banco = next(a for a in agregado
                     if a["instituicao"] == "BANCO SINTETICO S.A.")
        checar(banco["linhas"] == 2, banco)
        checar(banco["pix"] == 900000, banco)
        checar(sum(a["total_dimp"] for a in agregado)
               == sum(m["total_dimp"] for m in detalhe["movimentos"]),
               "o agregado tem de somar exatamente como as linhas")

        pagina = store.listar_excecoes(severidade="aviso", limite=2)
        checar(pagina["total"] == 4, pagina["total"])
        checar(len(pagina["itens"]) == 2, len(pagina["itens"]))
        checar(all(e["severidade"] == "aviso" for e in pagina["itens"]),
               pagina["itens"])
        checar(all(e["cnpj"] and e["competencia"] for e in pagina["itens"]),
               "a fila de excecoes precisa localizar a competencia")
        checar(store.listar_excecoes(cnpj=fx.CNPJ_B)["total"] >= 1,
               "excecoes filtram por CNPJ")

        fonte = store.obter_fonte(detalhe["fonte"]["id"])
        checar(fonte["sha256"] == detalhe["fonte"]["sha256"], fonte)
        checar(os.path.isfile(os.path.join(store.origens_path,
                                           fonte["sha256"] + ".xlsx")),
               "a fonte precisa existir em disco para o download")
        try:
            store.obter_fonte(999999)
            checar(False, "fonte inexistente deveria falhar")
        except LookupError:
            pass
    finally:
        store.fechar()


def testar_decisoes(pasta: str) -> None:
    """Revisao, aprovacao e excecoes: transacional e append-only (T038)."""
    trabalho = os.path.join(pasta, "t10")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b10"))
    try:
        limpo = fx.gerar_quadro_50_5(os.path.join(trabalho, "limpo.xlsx"))
        item = importar(store, limpo)
        cid = item.conciliacao_id

        # Justificativa e' obrigatoria em qualquer decisao fiscal.
        try:
            store.revisar(cid, estado_novo="rejeitada", justificativa="  ",
                          **ANA)
            checar(False, "sem justificativa deveria falhar")
        except st.TransicaoInvalida as exc:
            checar(exc.codigo == "JUSTIFICATIVA_OBRIGATORIA", exc.codigo)

        antes = store.detalhar(cid)
        r = store.aprovar(cid, justificativa="Conferido.",
                          revision=antes["revision"], **ANA)
        checar(r["estado"] == "aprovada", r)
        checar(r["revision"] == antes["revision"] + 1,
               "aprovar incrementa a revision exatamente uma vez")

        depois = store.detalhar(cid)
        checar(depois["estado"] == "aprovada", depois["estado"])
        ultima = depois["revisoes"][-1]
        checar(ultima["estado_anterior"] == "em_revisao"
               and ultima["estado_novo"] == "aprovada", ultima)
        checar(ultima["usuario_login"] == "ana",
               "a autoria vem do snapshot, nunca do corpo da requisicao")
        checar(any(e["acao"] == "aprovacao" for e in store.eventos(cid)),
               "aprovar tem de gravar evento fiscal na mesma transacao")

        try:
            store.aprovar(cid, justificativa="de novo", **ANA)
            checar(False, "aprovar duas vezes deveria falhar")
        except st.TransicaoInvalida:
            pass

        # Revision desatualizada nao sobrescreve decisao alheia.
        try:
            store.revisar(cid, estado_novo="rejeitada",
                          justificativa="Revi e discordo.", revision=1, **ANA)
            checar(False, "revision velha deveria dar conflito de concorrencia")
        except st.ConcorrenciaError as exc:
            checar(exc.revision_atual == depois["revision"],
                   "o erro precisa trazer a revision atual")

        atual = store.detalhar(cid)["revision"]
        store.revisar(cid, estado_novo="em_revisao",
                      justificativa="Reabrindo para conferir a DIMP.",
                      revision=atual, **ANA)
        atual = store.detalhar(cid)["revision"]
        store.revisar(cid, estado_novo="rejeitada",
                      justificativa="Fonte incorreta.", revision=atual, **ANA)
        final = store.detalhar(cid)
        checar(final["estado"] == "rejeitada", final["estado"])
        checar(len(final["revisoes"]) == 4,
               "cada decisao vira uma revisao append-only")

        # BLOQUEIO aberto impede aprovacao.
        bloqueada = fx.gerar_quadro_50_3_dimp(
            os.path.join(trabalho, "bloqueada.xlsx"), competencia="202405",
            movimentos=(fx.movimento("BANCO ALTO", pix="99000.00"),))
        item2 = importar(store, bloqueada)
        d2 = store.detalhar(item2.conciliacao_id)
        checar(d2["bloqueios_abertos"] >= 1, d2["excecoes"])
        try:
            store.aprovar(item2.conciliacao_id, justificativa="tentando",
                          revision=d2["revision"], **ANA)
            checar(False, "bloqueio aberto deveria impedir a aprovacao")
        except st.TransicaoInvalida as exc:
            checar(exc.codigo == "APROVACAO_IMPEDIDA", exc.codigo)

        bloqueio = next(e for e in d2["excecoes"]
                        if e["severidade"] == "bloqueio")
        try:
            store.resolver_excecao(bloqueio["id"], resolucao="", **ANA)
            checar(False, "resolucao vazia deveria falhar")
        except st.TransicaoInvalida:
            pass
        store.resolver_excecao(bloqueio["id"],
                               resolucao="Conferido com o contribuinte.",
                               **ANA)
        d2 = store.detalhar(item2.conciliacao_id)
        checar(d2["bloqueios_abertos"] == 0, d2["bloqueios_abertos"])
        resolvida = next(e for e in d2["excecoes"] if e["id"] == bloqueio["id"])
        checar(resolvida["estado"] == "resolvida", resolvida)
        checar(resolvida["resolvida_por_login"] == "ana", resolvida)
        store.aprovar(item2.conciliacao_id, justificativa="Liberado.",
                      revision=d2["revision"], **ANA)
        checar(store.detalhar(item2.conciliacao_id)["estado"] == "aprovada",
               "depois de resolver o bloqueio, a aprovacao passa")

        try:
            store.resolver_excecao(bloqueio["id"], resolucao="de novo", **ANA)
            checar(False, "excecao resolvida nao se resolve de novo")
        except st.TransicaoInvalida:
            pass
    finally:
        store.fechar()


def testar_conflitos(pasta: str) -> None:
    """Comparacao, manter vigente e promover candidata (T043)."""
    trabalho = os.path.join(pasta, "t11")
    os.makedirs(trabalho, exist_ok=True)
    store = abrir(os.path.join(pasta, "b11"))
    try:
        v1 = fx.gerar_quadro_50_5(os.path.join(trabalho, "v1.xlsx"))
        v2 = fx.gerar_quadro_50_5(
            os.path.join(trabalho, "v2.xlsx"),
            valores=fx.valores_resumo(declarada_sem_st="35000.00"))
        v3 = fx.gerar_quadro_50_5(
            os.path.join(trabalho, "v3.xlsx"),
            valores=fx.valores_resumo(declarada_sem_st="36000.00"))

        a = importar(store, v1)
        cid = a.conciliacao_id
        store.aprovar(cid, justificativa="Ok.",
                      revision=store.detalhar(cid)["revision"], **ANA)
        checar(store.detalhar(cid)["estado"] == "aprovada", "aprovada")

        b = importar(store, v2)
        checar(b.resultado == "conflitante", b.resultado)
        d = store.detalhar(cid)
        checar(d["estado"] == "em_revisao",
               "candidata nova devolve a competencia aprovada a Em revisao")

        conflitos = store.listar_conflitos()
        checar(conflitos["total"] == 1, conflitos["total"])
        conflito = conflitos["itens"][0]

        diff = store.comparar_versoes(conflito["versao_vigente_id"],
                                      conflito["versao_candidata_id"])
        mudaram = {x["campo"] for x in diff if x["mudou"]}
        checar("declarada_sem_st" in mudaram, mudaram)
        checar("receita_declarada" in mudaram, mudaram)
        checar("declarada_com_st" not in mudaram, mudaram)
        campo = next(x for x in diff if x["campo"] == "declarada_sem_st")
        checar(campo["vigente"] == 3000000, campo)
        checar(campo["candidata"] == 3500000, campo)
        checar(campo["delta"] == 500000, campo["delta"])
        nulo = next(x for x in diff if x["campo"] == "total_pix")
        checar(nulo["delta"] is None,
               "None de um lado nao pode virar delta numerico")

        d = store.detalhar(cid)
        store.resolver_conflito(conflito["id"], decisao="manter_vigente",
                                justificativa="A original esta correta.",
                                revision=d["revision"], **ANA)
        d = store.detalhar(cid)
        checar(d["versao_vigente"]["numero"] == 1, "a vigente nao mudou")
        descartadas = [v for v in d["versoes"] if v["estado"] == "descartada"]
        checar(len(descartadas) == 1, d["versoes"])
        checar(d["conflitos_abertos"] == 0, d["conflitos_abertos"])
        checar(d["estado"] == "em_revisao",
               "resolver conflito devolve para Em revisao")

        c = importar(store, v3)
        checar(c.resultado == "conflitante", c.resultado)
        conflito2 = store.listar_conflitos()["itens"][0]
        d = store.detalhar(cid)
        antes_vigente = d["versao_vigente"]["id"]
        r = store.resolver_conflito(
            conflito2["id"], decisao="promover_candidata",
            justificativa="Retificacao oficial do contribuinte.",
            revision=d["revision"], **ANA)
        d = store.detalhar(cid)
        checar(d["versao_vigente"]["id"] == r["versao_vigente_id"], d)
        checar(d["versao_vigente"]["numero"] == 3, d["versao_vigente"])
        checar(d["versao_vigente"]["receita_declarada"] == 4600000,
               d["versao_vigente"]["receita_declarada"])
        substituida = next(v for v in d["versoes"] if v["id"] == antes_vigente)
        checar(substituida["estado"] == "substituida",
               "a anterior e' preservada como substituida, nunca apagada")
        checar(substituida["receita_declarada"] == 4000000,
               "os valores da versao anterior continuam intactos")
        checar(d["estado"] == "em_revisao", d["estado"])
        checar(store.contar("versao_conciliacao") == 3,
               "as tres versoes continuam no banco")

        try:
            store.resolver_conflito(conflito2["id"], decisao="manter_vigente",
                                    justificativa="x", **ANA)
            checar(False, "conflito resolvido deveria recusar nova decisao")
        except st.TransicaoInvalida:
            pass

        # Multiplas candidatas: promover uma invalida a decisao pendente da
        # outra, porque a base de comparacao mudou.
        v4 = fx.gerar_quadro_50_5(
            os.path.join(trabalho, "v4.xlsx"),
            valores=fx.valores_resumo(declarada_sem_st="37000.00"))
        v5 = fx.gerar_quadro_50_5(
            os.path.join(trabalho, "v5.xlsx"),
            valores=fx.valores_resumo(declarada_sem_st="38000.00"))
        importar(store, v4)
        importar(store, v5)
        abertos = store.listar_conflitos()["itens"]
        checar(len(abertos) == 2, len(abertos))
        antigo, recente = abertos[1], abertos[0]
        d = store.detalhar(cid)
        store.resolver_conflito(recente["id"], decisao="promover_candidata",
                                justificativa="Promovendo a mais nova.",
                                revision=d["revision"], **ANA)
        d = store.detalhar(cid)
        try:
            store.resolver_conflito(
                antigo["id"], decisao="promover_candidata",
                justificativa="Contra uma base que ja mudou.",
                revision=d["revision"], **ANA)
            checar(False, "promover contra vigente alterada deveria falhar")
        except st.TransicaoInvalida as exc:
            checar(exc.codigo == "VIGENTE_ALTERADA", exc.codigo)
    finally:
        store.fechar()


def main() -> int:
    pasta = tempfile.mkdtemp(prefix="conc_store_")
    try:
        testar_schema_idempotente(os.path.join(pasta, "b0"))
        testar_importacao_basica(pasta)
        testar_50_5_sem_dimp(pasta)
        testar_duplicata_por_sha(pasta)
        testar_candidata_e_conflito(pasta)
        testar_concorrencia(pasta)
        testar_imutabilidade(pasta)
        testar_lote_interrompido(pasta)
        testar_rejeitado(pasta)
        testar_consultas(pasta)
        testar_decisoes(pasta)
        testar_conflitos(pasta)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    print("OK - store da conciliacao (schema idempotente, centavos inteiros, "
          "fonte imutavel por SHA, duplicata renomeada, candidata e conflito "
          "sem sobrescrita, importacoes concorrentes, trilha append-only e "
          "lote interrompido no reinicio, consultas filtradas e paginadas e agregacao por instituicao sem perder linha, decisoes com revision otimista, bloqueio impedindo aprovacao e conflitos resolvidos sem perder versao) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
