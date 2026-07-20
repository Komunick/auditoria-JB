"""Versao web — Extracao de Itens de ponta a ponta.

Sobe o app FastAPI com TestClient e exercita: upload de SPED (.txt) e de
XMLs em zip, extracao como job (com filtro de operacao, previa formatada em
pt-BR e aviso MSG_SEM_ENTRADAS), dedupe de XMLs pela chave de acesso,
importacao COMBINADA (SPED + XMLs no mesmo envio, com o SPED definindo
quais XMLs entram) e exportacao do Excel completo. Usa dados_web isolado
(AUDITORIA_WEB_DADOS) e reusa os construtores de test_extracao.py e
test_xml.py.
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


# Chaves extras do cenario combinado (mesmo emitente/serie do CHV base).
CHV_SEM_C170 = "35260399888777000166550010000010021123456780"
CHV_SEM_XML = "35260399888777000166550010000010031123456780"
CHV_FORA_SPED = "35260399888777000166550010000099991123456780"


def montar_sped_combinado() -> str:
    """SPED com tres notas de ENTRADA: 1001 com C170 (os itens declarados
    mandam), 1002 sem C170 (o XML correspondente completa) e 1003 sem XML."""
    linhas = [
        linha("0000", {4: "01032026", 5: "31032026", 6: "EMPRESA TESTE LTDA",
                       7: "11222333000181", 9: "SP"}),
        linha("0150", {2: "F001", 3: "FORNECEDOR ALPHA LTDA", 5: "99888777000166"}),
        linha("0200", {2: "P001", 3: "PARAFUSO SEXTAVADO M8", 8: "73181500"}),
        linha("C100", {2: "0", 3: "1", 4: "F001", 5: "55", 6: "00", 7: "1",
                       8: "1001", 9: CHV, 10: "05032026", 11: "05032026",
                       12: "500,00", 16: "500,00"}),
        linha("C170", {2: "1", 3: "P001", 4: "PARAFUSO SEXTAVADO M8", 5: "100,00",
                       6: "UN", 7: "500,00", 10: "000", 11: "1102", 13: "500,00",
                       14: "18,00", 15: "90,00"}),
        linha("C100", {2: "0", 3: "1", 4: "F001", 5: "55", 6: "00", 7: "1",
                       8: "1002", 9: CHV_SEM_C170, 10: "12032026", 11: "12032026",
                       12: "900,00", 16: "900,00"}),
        linha("C100", {2: "0", 3: "1", 4: "F001", 5: "55", 6: "00", 7: "1",
                       8: "1003", 9: CHV_SEM_XML, 10: "20032026", 11: "20032026",
                       12: "150,00", 16: "150,00"}),
    ]
    return "\r\n".join(linhas) + "\r\n"


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
    checar(resultado["vinculo"] is None,
           f"sem pasta de XMLs nao ha vinculo: {resultado['vinculo']!r}")

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

    # ------------------------------------------------------------------
    # Importacao COMBINADA: SPED + zip de XMLs no MESMO envio. O SPED define
    # as notas; so os XMLs correspondentes entram (o "fora do SPED" e
    # ignorado); nota sem C170 ganha os itens do XML sem herdar o tpNF.
    sessao5 = nova_sessao(cliente)
    r = cliente.post(
        f"/api/extracao/upload?sessao_id={sessao5}",
        files={"arquivo": ("sped_combinado.txt",
                           montar_sped_combinado().encode("cp1252"),
                           "text/plain")})
    checar(r.status_code == 200, f"upload do SPED combinado falhou: {r.text}")

    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as zf:
        zf.writestr("nota1001.xml", XML)
        zf.writestr("nota1002.xml",
                    XML.replace(CHV, CHV_SEM_C170)
                       .replace("<nNF>1001</nNF>", "<nNF>1002</nNF>"))
        zf.writestr("fora_do_sped.xml",
                    XML.replace(CHV, CHV_FORA_SPED)
                       .replace("<nNF>1001</nNF>", "<nNF>9999</nNF>"))
    memoria.seek(0)
    r = cliente.post(f"/api/extracao/upload?sessao_id={sessao5}",
                     files={"arquivo": ("xmls_combinado.zip", memoria,
                                        "application/zip")})
    checar(r.status_code == 200, f"upload do zip combinado falhou: {r.text}")

    job = cliente.post("/api/extracao/extrair", json={
        "sessao_id": sessao5, "fonte": "sped", "operacao": "0"}).json()
    job = esperar_job(cliente, job["job_id"])
    checar(job["status"] == "concluido", f"combinado falhou: {job['erro']}")
    resultado = job["resultado"]

    # 1001 mantem o item do C170; 1002 adota os 2 itens do XML; 1003 sem
    # C170 e sem XML nao gera linha; o XML 9999 (fora do SPED) fica de fora.
    checar(resultado["total"] == 3,
           f"combinado deveria dar 3 itens: {resultado['total']}")
    checar(resultado["contexto"] == "EMPRESA TESTE LTDA + 2 XML(s)",
           f"contexto combinado: {resultado['contexto']}")
    checar(resultado["filtro"] == ROTULO_FILTRO_ENTRADAS,
           f"filtro do combinado: {resultado['filtro']!r}")
    checar(resultado["vinculo"] == {"com_xml": 2, "completadas": 1,
                                    "sem_xml": 1, "ignorados": 1},
           f"contadores do vinculo: {resultado['vinculo']!r}")

    linhas_comb = [dict(zip(resultado["titulos"], ln))
                   for ln in resultado["previa"]]
    por_numero = {}
    for ln in linhas_comb:
        por_numero.setdefault(ln["Numero"], []).append(ln)
    checar(sorted(por_numero) == ["1001", "1002"],
           f"numeros na previa: {sorted(por_numero)}")
    # Nota COM C170: o CFOP declarado (1102) NAO e sobrescrito pelo do XML.
    checar(por_numero["1001"][0]["CFOP"] == "1102",
           f"CFOP declarado mudou: {por_numero['1001'][0]['CFOP']}")
    # Nota SEM C170: itens vem do XML (CFOP 5102 do emitente), mas a
    # operacao continua a declarada no SPED (entrada) — senao o filtro de
    # entradas teria descartado a nota.
    checar(len(por_numero["1002"]) == 2,
           f"itens adotados do XML: {len(por_numero['1002'])}")
    checar(por_numero["1002"][0]["CFOP"] == "5102",
           f"CFOP do item do XML: {por_numero['1002'][0]['CFOP']}")
    checar(por_numero["1002"][0]["Operacao"] == "Entrada",
           f"operacao devia seguir o SPED: {por_numero['1002'][0]['Operacao']}")
    checar(por_numero["1002"][0]["Descricao"] == "PARAFUSO SEXTAVADO M8",
           f"descricao do item do XML: {por_numero['1002'][0]['Descricao']}")

    r = cliente.post(f"/api/extracao/exportar?sessao_id={sessao5}")
    checar(r.status_code == 200 and r.content.startswith(b"PK"),
           "exportacao do combinado nao gerou xlsx")

    print("OK - extracao de itens web (upload SPED/zip de XMLs, job, previa "
          "pt-BR, filtro de entradas, dedupe, importacao combinada SPED+XML "
          "e Excel) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
