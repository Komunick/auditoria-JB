"""Auditoria de Produtos via .FDB pela API web (upload -> listar -> auditar).

Cria um .FDB temporario com uma tabela de produtos, sobe pela API, lista as
tabelas, escolhe a certa e audita — o mesmo caminho do frontend. Pula sozinho
quando o Firebird embedded nao esta empacotado.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_fdb_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from auditoria_fiscal.core import fdb_reader  # noqa: E402


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def esperar_job(cliente, job_id: str) -> dict:
    for _ in range(100):
        job = cliente.get(f"/api/jobs/{job_id}").json()
        if job["status"] == "concluido":
            return job["resultado"]
        if job["status"] == "erro":
            raise AssertionError(f"job falhou: {job['erro']}")
        time.sleep(0.1)
    raise AssertionError("job nao concluiu a tempo")


def _criar_fdb(caminho: str) -> None:
    fdb_reader._preparar_ambiente()
    import fdb
    con = fdb.create_database(
        f"CREATE DATABASE '{caminho}' USER 'TESTOWNER' PASSWORD 'x' "
        "DEFAULT CHARACTER SET WIN1252", fb_library_name=fdb_reader._dll())
    cur = con.cursor()
    cur.execute('CREATE TABLE "T10_PRO" (CODPRO VARCHAR(20), '
                "DESCRPRO VARCHAR(80), NCMPRO VARCHAR(10), CESTPRO VARCHAR(10),"
                " CFOPPRO VARCHAR(6), CSTPRO VARCHAR(4), ALIQPRO NUMERIC(5,2))")
    con.commit()
    cur.executemany(
        'INSERT INTO "T10_PRO" (CODPRO,DESCRPRO,NCMPRO,CESTPRO,CFOPPRO,CSTPRO,'
        "ALIQPRO) VALUES (?,?,?,?,?,?,?)",
        [("P1", "REFRIGERANTE COLA 2L", "22021000", "", "5102", "00", 20.5),
         ("P2", "PARAFUSO M8", "73181500", "", "5405", "060", None)])
    con.commit()
    con.close()


def main() -> int:
    ok, motivo = fdb_reader.firebird_disponivel()
    if not ok:
        print(f"PULADO - {motivo}")
        return 0

    from fastapi.testclient import TestClient

    from auditoria_fiscal.web.servidor import criar_app

    cliente = TestClient(criar_app())
    cliente.post("/api/bootstrap", json={
        "usuario": "admin", "nome": "Admin", "senha": "segredo1"})

    caminho_fdb = os.path.join(_TMP, "cliente.fdb")
    _criar_fdb(caminho_fdb)

    sessao = cliente.post("/api/sessoes",
                          json={"ferramenta": "produtos"}).json()["sessao_id"]
    with open(caminho_fdb, "rb") as fh:
        r = cliente.post(f"/api/produtos/upload?sessao_id={sessao}",
                         files={"arquivo": ("cliente.fdb", fh,
                                            "application/octet-stream")})
    checar(r.status_code == 200, f"upload .fdb falhou: {r.text}")

    r = cliente.get(f"/api/produtos/fdb/tabelas?sessao_id={sessao}")
    checar(r.status_code == 200, f"listar tabelas falhou: {r.text}")
    tabelas = {t["nome"]: t["linhas"] for t in r.json()["tabelas"]}
    checar("T10_PRO" in tabelas and tabelas["T10_PRO"] == 2,
           f"tabelas: {tabelas}")

    # Auditar SEM escolher a tabela: erro claro.
    job = cliente.post("/api/produtos/auditar",
                       json={"sessao_id": sessao}).json()
    res = cliente.get(f"/api/jobs/{job['job_id']}").json()
    for _ in range(50):
        if res["status"] in ("concluido", "erro"):
            break
        time.sleep(0.1)
        res = cliente.get(f"/api/jobs/{job['job_id']}").json()
    checar(res["status"] == "erro" and "tabela" in res["erro"].lower(),
           f"auditar sem tabela deveria falhar: {res}")

    # Auditar escolhendo a tabela certa.
    job = cliente.post("/api/produtos/auditar", json={
        "sessao_id": sessao, "tabela_fdb": "T10_PRO"}).json()
    resultado = esperar_job(cliente, job["job_id"])
    checar(resultado["total"] == 2, f"total auditado: {resultado}")
    checar(resultado["mapa_colunas"].get("ncm") == "NCMPRO",
           f"mapa: {resultado['mapa_colunas']}")

    dados = cliente.get(f"/api/produtos/resultados?sessao_id={sessao}").json()
    ncms = sorted(p["ncm"] for p in dados["itens"])
    checar(ncms == ["22021000", "73181500"], f"ncms: {ncms}")

    # Corrigir alta confianca e gerar nova base: a saida de uma fonte .FDB tem
    # que sair como CSV (o .fdb nunca e reescrito) e com o nome .csv.
    cliente.post("/api/produtos/corrigir",
                 json={"sessao_id": sessao, "alta_confianca": True})
    r = cliente.post(f"/api/produtos/nova-base?sessao_id={sessao}")
    checar(r.status_code == 200, f"nova-base falhou: {r.text}")
    disp = r.headers.get("content-disposition", "")
    checar(".csv" in disp and ".fdb" not in disp,
           f"nova base de .fdb deveria vir como .csv: {disp}")
    checar(b";" in r.content and b"CODPRO" in r.content,
           "nova base de .fdb deveria ter cabecalho/conteudo CSV")

    print("OK - Auditoria de Produtos via .FDB (upload, listar tabelas, "
          "escolher tabela, auditar, nova base CSV) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
