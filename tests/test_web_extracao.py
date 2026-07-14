"""Versao web — Extracao de Itens de ponta a ponta.

Sobe o app FastAPI com TestClient e exercita: upload de SPED (.txt) e de
XMLs em zip, extracao como job (com filtro de operacao, previa formatada em
pt-BR e aviso MSG_SEM_ENTRADAS), dedupe de XMLs pela chave de acesso e
exportacao do Excel completo. Usa dados_web isolado (AUDITORIA_WEB_DADOS)
e reusa os construtores de test_extracao.py e test_xml.py.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import time
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_ext_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.core.filtro_sped import (  # noqa: E402
    MSG_SEM_ENTRADAS, ROTULO_FILTRO_ENTRADAS,
)
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from test_extracao import CHV, linha, montar_sped  # noqa: E402
from test_xml import XML  # noqa: E402


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def esperar_job(cliente, job_id: str) -> dict:
    """Espera o job terminar e devolve o job inteiro (status + resultado)."""
    for _ in range(200):
        job = cliente.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("concluido", "erro"):
            return job
        time.sleep(0.1)
    raise AssertionError("job nao concluiu a tempo")


def montar_sped_saidas() -> str:
    """SPED sintetico so com documento de SAIDA (reusa linha() do teste base)."""
    linhas = [
        linha("0000", {4: "01032026", 5: "31032026", 6: "EMPRESA TESTE LTDA",
                       7: "11222333000181", 9: "SP"}),
        linha("0150", {2: "C001", 3: "CLIENTE BETA LTDA", 5: "55444333000122"}),
        linha("0200", {2: "P001", 3: "PARAFUSO SEXTAVADO M8", 8: "73181500"}),
        linha("C100", {2: "1", 3: "1", 4: "C001", 5: "55", 6: "00", 7: "1",
                       8: "2001", 9: CHV, 10: "10032026", 11: "10032026",
                       12: "100,00", 16: "100,00"}),
        linha("C170", {2: "1", 3: "P001", 4: "PARAFUSO SEXTAVADO M8",
                       5: "10,00", 6: "UN", 7: "100,00", 10: "000",
                       11: "5102", 13: "100,00", 14: "18,00", 15: "18,00"}),
    ]
    return "\r\n".join(linhas) + "\r\n"


def nova_sessao(cliente) -> str:
    return cliente.post("/api/sessoes",
                        json={"ferramenta": "extracao"}).json()["sessao_id"]


def main() -> int:
    cliente = TestClient(criar_app())

    # Sem login: API bloqueada
    checar(cliente.post("/api/extracao/exportar?sessao_id=x").status_code == 401,
           "API deveria exigir login")

    r = cliente.post("/api/bootstrap", json={
        "usuario": "weslley", "nome": "Weslley", "senha": "segredo1"})
    checar(r.status_code == 200, f"bootstrap falhou: {r.text}")

    # ------------------------------------------------------------------
    # Fonte SPED, apenas entradas: previa formatada + rotulo do filtro
    sessao = nova_sessao(cliente)
    r = cliente.post(
        f"/api/extracao/upload?sessao_id={sessao}",
        files={"arquivo": ("sped_032026.txt",
                           montar_sped().encode("cp1252"), "text/plain")})
    checar(r.status_code == 200, f"upload do SPED falhou: {r.text}")

    job = cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao, "fonte": "sped", "operacao": "0"}).json()
    job = esperar_job(cliente, job["job_id"])
    checar(job["status"] == "concluido", f"extracao falhou: {job['erro']}")
    resultado = job["resultado"]
    checar(resultado["total"] == 2, f"esperava 2 itens: {resultado['total']}")
    checar(resultado["contexto"] == "EMPRESA TESTE LTDA",
           f"contexto: {resultado['contexto']}")
    checar(len(resultado["titulos"]) == 32,
           f"titulos: {len(resultado['titulos'])}")
    checar(len(resultado["previa"]) == 2,
           f"previa: {len(resultado['previa'])}")
    checar(resultado["filtro"] == ROTULO_FILTRO_ENTRADAS,
           f"rotulo do filtro: {resultado['filtro']!r}")
    checar(resultado["aviso"] == "", f"aviso indevido: {resultado['aviso']!r}")

    l1 = dict(zip(resultado["titulos"], resultado["previa"][0]))
    checar(l1["Chave de acesso"] == CHV, f"chave: {l1['Chave de acesso']}")
    checar(l1["Numero"] == "1001", f"numero: {l1['Numero']}")
    checar(l1["Data emissao"] == "05/03/2026", f"data: {l1['Data emissao']}")
    checar(l1["Operacao"] == "Entrada", f"operacao: {l1['Operacao']}")
    checar(l1["CFOP"] == "1102", f"cfop: {l1['CFOP']}")
    checar(l1["CST/CSOSN"] == "000", f"cst: {l1['CST/CSOSN']}")
    checar(l1["Quantidade"] == "100,0000",
           f"quantidade num4 pt-BR: {l1['Quantidade']}")
    checar(l1["Vlr unitario"] == "5,00", f"unitario: {l1['Vlr unitario']}")
    checar(l1["Vlr total"] == "500,00", f"total: {l1['Vlr total']}")

    # Exportacao usa TODAS as linhas do estado da sessao
    r = cliente.post(f"/api/extracao/exportar?sessao_id={sessao}")
    checar(r.status_code == 200, f"exportar falhou: {r.status_code} {r.text[:120]}")
    checar(r.content.startswith(b"PK"), "resposta nao e um xlsx (PK)")
    checar("itens_auditoria.xlsx" in r.headers.get("content-disposition", ""),
           "filename do download errado")

    # Apenas saidas no mesmo SPED: 0 itens, sem aviso (o aviso e do filtro
    # de entradas); exportar agora deve dar 422 (estado sem linhas)
    job = cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao, "fonte": "sped", "operacao": "1"}).json()
    job = esperar_job(cliente, job["job_id"])
    checar(job["status"] == "concluido", f"extracao saidas falhou: {job['erro']}")
    checar(job["resultado"]["total"] == 0,
           f"saidas: {job['resultado']['total']}")
    checar(job["resultado"]["aviso"] == "",
           "aviso de entradas nao vale para o filtro de saidas")
    checar(cliente.post(
        f"/api/extracao/exportar?sessao_id={sessao}").status_code == 422,
        "exportar sem linhas deveria dar 422")

    # Operacao invalida
    checar(cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao, "fonte": "sped",
        "operacao": "9"}).status_code == 422,
        "operacao invalida deveria dar 422")

    # ------------------------------------------------------------------
    # SPED so com saidas + filtro de entradas -> MSG_SEM_ENTRADAS
    sessao2 = nova_sessao(cliente)
    cliente.post(
        f"/api/extracao/upload?sessao_id={sessao2}",
        files={"arquivo": ("sped_saidas.txt",
                           montar_sped_saidas().encode("cp1252"), "text/plain")})
    job = cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao2, "fonte": "sped", "operacao": "0"}).json()
    job = esperar_job(cliente, job["job_id"])
    checar(job["status"] == "concluido", f"sped de saidas falhou: {job['erro']}")
    checar(job["resultado"]["total"] == 0,
           f"filtro de entradas: {job['resultado']['total']}")
    checar(job["resultado"]["aviso"] == MSG_SEM_ENTRADAS,
           f"aviso: {job['resultado']['aviso']!r}")

    # Extrair sem upload -> job termina em erro
    sessao3 = nova_sessao(cliente)
    job = cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao3, "fonte": "sped", "operacao": ""}).json()
    job = esperar_job(cliente, job["job_id"])
    checar(job["status"] == "erro" and "SPED" in job["erro"],
           f"sem upload deveria dar erro: {job}")

    # ------------------------------------------------------------------
    # Fonte XML via zip com subpastas: dedupe pela chave de acesso
    sessao4 = nova_sessao(cliente)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as zf:
        zf.writestr("2026/03/nota1001.xml", XML)
        zf.writestr("copia/nota1001_copia.xml", XML)   # duplicada: mesma chave
    memoria.seek(0)
    r = cliente.post(f"/api/extracao/upload?sessao_id={sessao4}",
                     files={"arquivo": ("xmls_2026.zip", memoria,
                                        "application/zip")})
    checar(r.status_code == 200, f"upload do zip falhou: {r.text}")

    job = cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao4, "fonte": "xml", "operacao": ""}).json()
    job = esperar_job(cliente, job["job_id"])
    checar(job["status"] == "concluido", f"extracao xml falhou: {job['erro']}")
    resultado = job["resultado"]
    checar(resultado["total"] == 2,
           f"xml deduplicado deveria dar 2 itens: {resultado['total']}")
    checar(resultado["contexto"] == "1 XML(s)",
           f"contexto xml: {resultado['contexto']}")
    lx = dict(zip(resultado["titulos"], resultado["previa"][0]))
    checar(lx["Operacao"] == "Saida", f"operacao xml: {lx['Operacao']}")
    checar(lx["CFOP"] == "5102", f"cfop xml: {lx['CFOP']}")
    checar(lx["Aliq ICMS %"] == "18,00", f"aliquota xml: {lx['Aliq ICMS %']}")

    r = cliente.post(f"/api/extracao/exportar?sessao_id={sessao4}")
    checar(r.status_code == 200 and r.content.startswith(b"PK"),
           "exportacao da fonte xml nao gerou xlsx")

    print("OK - extracao de itens web (upload SPED/zip de XMLs, job, previa "
          "pt-BR, filtro de entradas, dedupe e Excel) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
