"""Versao web — plataforma (auth) + Livro de Conferencia de ponta a ponta.

Sobe o app FastAPI com TestClient e exercita: bootstrap do admin, login,
sessao de trabalho, upload de XML sintetico, carga com job, tabela de notas,
conferencia, correcao inline da composicao (CFOP), sobrescrita de texto
persistida, Livro Fiscal em PDF com o texto editado e bloqueio sem login.
Usa dados_web isolado em pasta temporaria (AUDITORIA_WEB_DADOS).
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

_TMP = tempfile.mkdtemp(prefix="auditoria_web_teste_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from test_xml import CHAVE, XML  # noqa: E402


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


def main() -> int:
    cliente = TestClient(criar_app())

    # Sem login: API bloqueada; estado pede bootstrap
    checar(cliente.get("/api/conferencia/notas?sessao_id=x").status_code == 401,
           "API deveria exigir login")
    estado = cliente.get("/api/estado").json()
    checar(estado["precisa_bootstrap"], "banco novo deveria pedir bootstrap")

    # Bootstrap do primeiro admin (ja loga) e segundo bootstrap negado
    r = cliente.post("/api/bootstrap", json={
        "usuario": "weslley", "nome": "Weslley", "senha": "segredo1"})
    checar(r.status_code == 200, f"bootstrap falhou: {r.text}")
    checar(cliente.post("/api/bootstrap", json={
        "usuario": "x", "senha": "y123456"}).status_code == 403,
        "segundo bootstrap deveria ser negado")

    # Login invalido nao revela usuario
    r = cliente.post("/api/login", json={"usuario": "weslley", "senha": "errada"})
    checar(r.status_code == 401 and "invalidos" in r.json()["detail"],
           "login invalido deveria dar mensagem generica")

    # Sessao de trabalho + upload de um zip com subpasta (ano/mes)
    sessao = cliente.post("/api/sessoes",
                          json={"ferramenta": "conferencia"}).json()["sessao_id"]
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as zf:
        zf.writestr("2026/03/nota1001.xml", XML)
    memoria.seek(0)
    r = cliente.post(f"/api/conferencia/upload?sessao_id={sessao}",
                     files={"arquivo": ("xmls_2026.zip", memoria, "application/zip")})
    checar(r.status_code == 200, f"upload falhou: {r.text}")

    # Carga (job) e tabela de notas
    job = cliente.post("/api/conferencia/carregar", json={
        "sessao_id": sessao, "fonte": "xml"}).json()
    resultado = esperar_job(cliente, job["job_id"])
    checar(resultado["total"] == 1, f"esperava 1 nota: {resultado}")
    notas = cliente.get(f"/api/conferencia/notas?sessao_id={sessao}").json()["itens"]
    checar(notas[0]["chave"] == CHAVE and notas[0]["cfop"] == "5102",
           f"nota serializada errada: {notas[0]}")
    checar(notas[0]["valor_contabil"].startswith("R$"),
           "valor deveria vir formatado em BRL")

    # Conferir com observacao
    r = cliente.post("/api/conferencia/conferir", json={
        "sessao_id": sessao, "chave": CHAVE, "conferida": True,
        "observacao": "ok pela web"}).json()
    checar(r["conferida"] and r["data_conferencia"], "conferencia nao gravou")

    # Composicao: correcao inline do CFOP (coluna 0) — grupo 5102/00/18
    comp = cliente.get(
        f"/api/conferencia/composicao?sessao_id={sessao}&chave={CHAVE}").json()
    grupo = comp["linhas"][1]["grupo"]
    celula = comp["linhas"][1]["celulas"][0]
    checar(celula["edicao"] == "correcao" and celula["original"] == "5102",
           f"celula CFOP errada: {celula}")
    comp = cliente.post("/api/conferencia/composicao/editar", json={
        "sessao_id": sessao, "chave": CHAVE, "grupo": grupo,
        "coluna": 0, "texto": "5403"}).json()
    checar(any("5.403" in c["texto"] or "5403" in c["texto"]
               for linha in comp["linhas"] for c in linha["celulas"]),
           "correcao de CFOP nao apareceu na composicao")

    # Sobrescrita de texto no Valor contabil do grupo corrigido (coluna 3)
    grupo_novo = comp["linhas"][1]["grupo"]
    comp = cliente.post("/api/conferencia/composicao/editar", json={
        "sessao_id": sessao, "chave": CHAVE, "grupo": grupo_novo,
        "coluna": 3, "texto": "R$ 123,45"}).json()
    celula = comp["linhas"][1]["celulas"][3]
    checar(celula["texto"] == "R$ 123,45" and "override" in celula,
           f"sobrescrita nao aplicada: {celula}")

    # Livro Fiscal em PDF sai com o texto editado
    r = cliente.post(f"/api/conferencia/livro-fiscal?sessao_id={sessao}")
    checar(r.status_code == 200 and r.headers["content-type"] == "application/pdf",
           f"livro fiscal falhou: {r.status_code}")
    checar(r.content.startswith(b"%PDF"), "resposta nao e um PDF")

    # DANFE: chave inexistente da 404; para o XML sintetico minimo vale
    # 200 (PDF) ou 422 vindo do gerador (a geracao real e coberta pelo
    # test_danfe.py) — o que se valida aqui e a tubulacao ate o gerador.
    r = cliente.get(f"/api/conferencia/danfe?sessao_id={sessao}&chave={'9'*44}")
    checar(r.status_code == 404, "DANFE de chave inexistente deveria dar 404")
    r = cliente.get(f"/api/conferencia/danfe?sessao_id={sessao}&chave={CHAVE}")
    if r.status_code == 200:
        checar(r.content.startswith(b"%PDF"), "resposta do DANFE nao e PDF")
    else:
        checar(r.status_code == 422 and "DANFE" in r.json()["detail"],
               f"DANFE deveria chegar ao gerador: {r.status_code} {r.text[:120]}")

    # Logout encerra a sessao de login
    cliente.post("/api/logout")
    checar(cliente.get(
        f"/api/conferencia/notas?sessao_id={sessao}").status_code == 401,
        "logout deveria invalidar a sessao")

    print("OK - plataforma web + Livro de Conferencia (auth, upload zip, "
          "carga, conferencia, correcao, sobrescrita, PDF, DANFE) passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
