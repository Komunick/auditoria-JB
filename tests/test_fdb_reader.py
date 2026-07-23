"""Leitor de .FDB (Firebird embedded) + caminho FDB da base de produtos.

Cria um banco Firebird temporario com uma tabela estilo Symac (colunas com
sufixo, ex.: CODPRO/NCMPRO/CFOPPRO), le pelo leitor compartilhado e pelo
ler_base_produtos_fdb, conferindo o mapeamento automatico de colunas. Pula
sozinho (sem falhar) quando o motor Firebird embedded nao esta empacotado.
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import fdb_reader  # noqa: E402
from auditoria_fiscal.core.cadastro_produtos import (  # noqa: E402
    ler_base_produtos_fdb,
)


def _criar_fdb_teste(caminho: str) -> None:
    """Cria um .FDB com uma tabela de produtos estilo Symac e 3 linhas."""
    fdb_reader._preparar_ambiente()
    import fdb

    con = fdb.create_database(
        f"CREATE DATABASE '{caminho}' USER 'TESTOWNER' PASSWORD 'x' "
        "DEFAULT CHARACTER SET WIN1252",
        fb_library_name=fdb_reader._dll())
    cur = con.cursor()
    cur.execute(
        'CREATE TABLE "T10_PRO" ('
        " CODPRO VARCHAR(20), DESCRPRO VARCHAR(80), NCMPRO VARCHAR(10),"
        " CESTPRO VARCHAR(10), CFOPPRO VARCHAR(6), CSTPRO VARCHAR(4),"
        " ALIQPRO NUMERIC(5,2))")
    con.commit()
    linhas = [
        ("P1", "REFRIGERANTE COLA 2L", "22021000", "", "5102", "00", 20.5),
        ("P2", "PARAFUSO SEXTAVADO M8", "73181500", "", "5405", "060", None),
        ("P3", "ARROZ TIPO 1 5KG", "10063021", "", "5116", "00", 12.0),
    ]
    cur.executemany(
        'INSERT INTO "T10_PRO" '
        "(CODPRO, DESCRPRO, NCMPRO, CESTPRO, CFOPPRO, CSTPRO, ALIQPRO) "
        "VALUES (?,?,?,?,?,?,?)", linhas)
    con.commit()
    con.close()


def main() -> int:
    ok, motivo = fdb_reader.firebird_disponivel()
    if not ok:
        print(f"PULADO - {motivo}")
        return 0

    falhas: list[str] = []

    def checar(cond, msg):
        if not cond:
            falhas.append(msg)

    pasta = tempfile.mkdtemp(prefix="fdb_teste_")
    caminho = os.path.join(pasta, "teste.fdb")
    try:
        _criar_fdb_teste(caminho)

        # Leitor compartilhado (isolado em subprocesso): listar, ler.
        tabelas = {t.nome: t for t in fdb_reader.listar_tabelas(caminho)}
        checar("T10_PRO" in tabelas, f"tabela nao listada: {list(tabelas)}")
        checar(tabelas["T10_PRO"].linhas == 3 and not tabelas["T10_PRO"].mais,
               f"contagem: {tabelas['T10_PRO']}")
        colunas, linhas, truncado = fdb_reader.ler_tabela(caminho, "T10_PRO")
        checar(colunas[:3] == ["CODPRO", "DESCRPRO", "NCMPRO"],
               f"colunas: {colunas}")
        checar(len(linhas) == 3 and not truncado, f"linhas lidas: {len(linhas)}")
        checar(linhas[0][0] == "P1" and linhas[0][4] == "5102",
               f"linha 0: {linhas[0]}")
        try:
            fdb_reader.ler_tabela(caminho, "NAO_EXISTE")
            checar(False, "tabela inexistente deveria dar erro")
        except ValueError:
            pass

        # Teto de linhas (isolamento de OOM): limite 2 trunca as 3 linhas.
        _c, lim, trunc = fdb_reader.ler_tabela(caminho, "T10_PRO", limite=2)
        checar(len(lim) == 2 and trunc, f"truncagem: {len(lim)} {trunc}")

        # Arquivo que nao e Firebird: erro tratado (nao derruba o processo).
        naofdb = os.path.join(pasta, "lixo.fdb")
        with open(naofdb, "wb") as fh:
            fh.write(b"isto nao e um banco firebird" * 10)
        try:
            fdb_reader.listar_tabelas(naofdb)
            checar(False, "arquivo invalido deveria dar ValueError")
        except ValueError:
            pass

        # Caminho de base de produtos a partir do FDB (mapeamento automatico).
        base = ler_base_produtos_fdb(caminho, "T10_PRO")
        checar(len(base.produtos) == 3, f"produtos: {len(base.produtos)}")
        mapa = base.diagnostico["mapa_colunas"]
        checar(mapa.get("codigo") == "CODPRO", f"map codigo: {mapa}")
        checar(mapa.get("ncm") == "NCMPRO", f"map ncm: {mapa}")
        checar(mapa.get("cfop") == "CFOPPRO", f"map cfop: {mapa}")
        checar(mapa.get("cst") == "CSTPRO", f"map cst: {mapa}")
        p1, p2, p3 = base.produtos
        checar(p1.ncm == "22021000" and p1.cfops == ["5102"],
               f"p1: {p1.ncm} {p1.cfops}")
        checar(p2.cst == "060" and p2.cfops == ["5405"],
               f"p2: {p2.cst} {p2.cfops}")
        checar(p1.aliquota is not None and float(p1.aliquota) == 20.5,
               f"p1 aliq: {p1.aliquota}")
        checar(p3.cfops == ["5116"], f"p3 cfop: {p3.cfops}")
    finally:
        # Fecha handles do Firebird antes de apagar a pasta.
        import shutil
        shutil.rmtree(pasta, ignore_errors=True)

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("OK - leitor de FDB (abrir, listar, ler) e base de produtos via FDB "
          "passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
