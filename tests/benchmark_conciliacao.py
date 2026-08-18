"""Benchmark reproduzivel de SC-010, SC-011 e SC-012 (T064).

NAO faz parte da suite (o nome nao comeca com `test_`): mede tempo, e tempo
depende da maquina. Rode explicitamente e registre o hardware junto do
resultado, senao o numero nao quer dizer nada.

    .\\.venv\\Scripts\\python.exe tests\\benchmark_conciliacao.py

Metas do spec, validas no SERVIDOR DE REFERENCIA (4 nucleos, 8 GB, disco
local) — nao nesta maquina:

- SC-010: lote de 30 arquivos de ate 10 MB processado em ate 120 s
- SC-011: listagens e filtros ate 2 s no p95 com 10 mil conciliacoes
- SC-012: exportacao de ate 10 mil conciliacoes em ate 60 s
"""

from __future__ import annotations

import os
import platform
import shutil
import statistics
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tests"))

from fixtures import conciliacao as fx  # noqa: E402

from auditoria_fiscal.ferramentas import conciliacao_store as st  # noqa: E402
from auditoria_fiscal.ferramentas import relatorio_conciliacao as rc  # noqa: E402

ATOR = {"usuario_id": 1, "usuario_login": "benchmark"}

META_LOTE_S = 120
META_LISTAGEM_S = 2
META_EXPORTACAO_S = 60


def cronometrar(rotulo: str, funcao):
    inicio = time.perf_counter()
    resultado = funcao()
    gasto = time.perf_counter() - inicio
    print(f"  {rotulo:<44} {gasto:8.2f} s")
    return gasto, resultado


def sc010(pasta: str) -> float:
    """Lote de 30 arquivos, os dois layouts."""
    print("\nSC-010 — lote de 30 arquivos")
    arquivos = os.path.join(pasta, "lote")
    os.makedirs(arquivos, exist_ok=True)
    caminhos = []
    for i in range(30):
        gerar = fx.gerar_quadro_50_3_dimp if i % 2 else fx.gerar_quadro_50_5
        ano, mes = 2020 + i // 12, i % 12 + 1
        caminhos.append(gerar(os.path.join(arquivos, f"r{i:02d}.xlsx"),
                              competencia=f"{ano}{mes:02d}"))

    store = st.ConciliacaoStore(db_path=os.path.join(pasta, "sc010.db"),
                                origens_path=os.path.join(pasta, "org010"))
    try:
        lote = store.abrir_lote(sessao_id="bench", total_arquivos=30, **ATOR)

        def _processar():
            for ordem, caminho in enumerate(caminhos, start=1):
                store.importar_arquivo(
                    lote, caminho_staging=caminho,
                    nome_recebido=os.path.basename(caminho), ordem=ordem,
                    **ATOR)
            return store.concluir_lote(lote)

        gasto, resumo = cronometrar("30 arquivos importados", _processar)
        print(f"     resultado: {resumo}")
        return gasto
    finally:
        store.fechar()


def _popular(store, quantidade: int, pasta: str) -> None:
    """Insere `quantidade` conciliacoes direto no banco.

    Passar pelo parser 10 mil vezes mediria o openpyxl, nao a consulta — e o
    que SC-011 e SC-012 cobram e' consulta e exportacao.
    """
    modelo = fx.gerar_quadro_50_5(os.path.join(pasta, "modelo_bench.xlsx"))
    conn = store._conn                       # noqa: SLF001 — benchmark interno
    conn.execute("BEGIN IMMEDIATE")
    for i in range(quantidade):
        cnpj = fx.cnpj_sintetico(f"{11000000 + i:08d}0001")
        competencia = f"{2015 + i % 10}{i % 12 + 1:02d}"
        cur = conn.execute(
            "INSERT INTO fonte_fiscal(sha256, nome_original,"
            " caminho_relativo, tamanho_bytes, layout, versao_parser,"
            " resultado, mensagem, enviada_por_id, enviada_por_login,"
            " recebida_em) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (f"{i:064d}", f"r{i}.xlsx", f"conciliacao/origens/{i:064d}.xlsx",
             5000, "quadro_50_5", "bench", "processada", "", 1, "benchmark",
             st.agora()))
        fonte_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO conciliacao(cnpj, competencia, razao_social, estado,"
            " revision, criada_em, atualizada_em) VALUES(?,?,?,?,?,?,?)",
            (cnpj, competencia, f"EMPRESA SINTETICA {i}", "em_revisao", 1,
             st.agora(), st.agora()))
        conciliacao_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO versao_conciliacao(conciliacao_id, fonte_id, numero,"
            " estado, layout, razao_social, receita_declarada,"
            " declarada_com_st, declarada_sem_st, receita_calculada,"
            " calculada_com_st, calculada_sem_st, diferenca_receita,"
            " diferenca_com_st, diferenca_sem_st, total_pix, total_nao_pix,"
            " aba_origem, linha_resumo, versao_parser, criada_em)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (conciliacao_id, fonte_id, 1, "vigente", "quadro_50_5",
             f"EMPRESA SINTETICA {i}", 4000000, 1000000, 3000000, 4150000,
             1050000, 3100000, 150000, 50000, 100000, None, None,
             "Quadro 50-5", 7, "bench", st.agora()))
        versao_id = cur.lastrowid
        conn.execute("UPDATE conciliacao SET versao_vigente_id=? WHERE id=?",
                     (versao_id, conciliacao_id))
        conn.execute(
            "INSERT INTO excecao_conciliacao(conciliacao_id, versao_id,"
            " codigo, severidade, mensagem, estado, criada_em)"
            " VALUES(?,?,?,?,?,?,?)",
            (conciliacao_id, versao_id, "DIMP_AUSENTE_NO_LAYOUT", "aviso",
             "Quadro 50-5 nao traz DIMP.", "aberta", st.agora()))
        conn.execute(
            "INSERT INTO fato_extraido(versao_id, metrica, valor_numerico,"
            " tipo_origem, aba, celula, rotulo, regra_parser,"
            " fatos_origem_json, versao_parser) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (versao_id, "receita_declarada", 4000000, "celula", "Quadro 50-5",
             "C7", "Receita Total Informada", "resumo/receita_declarada",
             "[]", "bench"))
    conn.execute("COMMIT")
    del modelo


def sc011_sc012(pasta: str, quantidade: int = 10000) -> tuple[float, float]:
    print(f"\nSC-011 e SC-012 — {quantidade} conciliacoes")
    store = st.ConciliacaoStore(db_path=os.path.join(pasta, "sc011.db"),
                                origens_path=os.path.join(pasta, "org011"))
    try:
        cronometrar(f"popular {quantidade} conciliacoes",
                    lambda: _popular(store, quantidade, pasta))
        total = store.contar("conciliacao")
        print(f"     conciliacoes no banco: {total}")

        consultas = [
            ("resumo sem filtro", lambda: store.resumo()),
            ("lista pagina 1", lambda: store.listar(limite=50)),
            ("lista pagina 100", lambda: store.listar(limite=50, pagina=100)),
            ("filtro por texto", lambda: store.listar(texto="SINTETICA 9")),
            ("filtro por estado", lambda: store.listar(estado="em_revisao")),
            ("filtro por excecao", lambda: store.listar(excecao="aviso")),
            ("intervalo de competencia",
             lambda: store.listar(competencia_de="201801",
                                  competencia_ate="202012")),
            ("ordenar por diferenca",
             lambda: store.listar(ordenar="diferenca_desc")),
            ("fila de excecoes", lambda: store.listar_excecoes(limite=50)),
        ]
        tempos = []
        for rotulo, funcao in consultas:
            # 5 repeticoes: a primeira paga o cache frio do SQLite.
            medidas = []
            for _ in range(5):
                inicio = time.perf_counter()
                funcao()
                medidas.append(time.perf_counter() - inicio)
            pior = max(medidas)
            tempos.extend(medidas)
            marca = "OK " if pior <= META_LISTAGEM_S else "LENTO"
            print(f"  {rotulo:<44} {pior:8.3f} s  {marca}")
        p95 = statistics.quantiles(tempos, n=20)[-1] if len(tempos) > 1 else tempos[0]
        print(f"  {'p95 de todas as consultas':<44} {p95:8.3f} s")

        # SC-012: exportacao. Detalhar 10 mil e' o custo real.
        def _exportar():
            detalhes = []
            pagina = store.listar(limite=200)
            for numero in range(1, pagina["paginas"] + 1):
                atual = (pagina if numero == 1
                         else store.listar(limite=200, pagina=numero))
                for linha in atual["itens"]:
                    detalhes.append(store.detalhar(linha["id"]))
            return rc.gerar_consolidado(
                os.path.join(pasta, "consolidado_bench.xlsx"),
                conciliacoes=detalhes, gerado_por="benchmark", filtros={},
                versao_parser="bench")

        exportacao, _ = cronometrar("exportar consolidado completo", _exportar)
        return p95, exportacao
    finally:
        store.fechar()


def main() -> int:
    print("Benchmark da Conciliacao Fiscal — SC-010, SC-011 e SC-012")
    print(f"  maquina : {platform.processor() or platform.machine()}")
    print(f"  cpus    : {os.cpu_count()}")
    print(f"  python  : {platform.python_version()} ({platform.system()} "
          f"{platform.release()})")
    print("\n  ATENCAO: as metas do spec valem no servidor de referencia "
          "(4 nucleos,\n  8 GB, disco local). Este numero e' indicativo.")

    pasta = tempfile.mkdtemp(prefix="conc_bench_")
    try:
        lote = sc010(pasta)
        p95, exportacao = sc011_sc012(pasta)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    print("\nResumo")
    for rotulo, medido, meta in (
        ("SC-010 lote de 30 arquivos", lote, META_LOTE_S),
        ("SC-011 p95 das listagens", p95, META_LISTAGEM_S),
        ("SC-012 exportacao completa", exportacao, META_EXPORTACAO_S),
    ):
        marca = "dentro da meta" if medido <= meta else "ACIMA DA META"
        print(f"  {rotulo:<32} {medido:8.2f} s  (meta {meta:>3} s) {marca}")
    print("\nRegistre estes numeros e o hardware no implementation-log.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
