"""Versao web — Comparador SPED x SPED de ponta a ponta.

Sobe o app FastAPI com TestClient e exercita: bloqueio sem login, bootstrap,
sessao de trabalho, upload dos dois SPEDs (subpastas a/ e b/), comparacao
como job (resumo, divergencias campo a campo, so em A/B), recusa de
arquivos identicos por conteudo e exportacao do Excel. Reusa os
construtores de fixtures de test_diff_sped.py.
Usa dados_web isolado em pasta temporaria (AUDITORIA_WEB_DADOS).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_teste_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from test_diff_sped import CH2, CH3, CH4, sped_a, sped_b  # noqa: E402

MEDIA_XLSX = ("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet")


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


def nova_sessao(cliente) -> str:
    return cliente.post("/api/sessoes",
                        json={"ferramenta": "diff"}).json()["sessao_id"]


def enviar(cliente, sessao: str, lado: str, nome: str, conteudo: bytes):
    r = cliente.post(f"/api/diff/upload?sessao_id={sessao}&lado={lado}",
                     files={"arquivo": (nome, conteudo, "text/plain")})
    checar(r.status_code == 200, f"upload lado {lado} falhou: {r.text}")


def main() -> int:
    cliente = TestClient(criar_app())

    # Sem login: API bloqueada
    checar(cliente.post("/api/diff/comparar",
                        json={"sessao_id": "x"}).status_code == 401,
           "API deveria exigir login")

    # Bootstrap do primeiro admin (ja loga)
    r = cliente.post("/api/bootstrap", json={
        "usuario": "weslley", "nome": "Weslley", "senha": "segredo1"})
    checar(r.status_code == 200, f"bootstrap falhou: {r.text}")

    # Comparar sem uploads: 422; lado invalido e extensao errada: 422
    sessao = nova_sessao(cliente)
    r = cliente.post("/api/diff/comparar", json={"sessao_id": sessao})
    checar(r.status_code == 422 and "SPED A" in r.json()["detail"],
           f"comparar sem uploads deveria dar 422: {r.status_code} {r.text}")
    r = cliente.post(f"/api/diff/upload?sessao_id={sessao}&lado=c",
                     files={"arquivo": ("x.txt", b"x", "text/plain")})
    checar(r.status_code == 422, "lado invalido deveria dar 422")
    r = cliente.post(f"/api/diff/upload?sessao_id={sessao}&lado=a",
                     files={"arquivo": ("sped.xlsx", b"x", "text/plain")})
    checar(r.status_code == 422, "SPED sem .txt deveria dar 422")

    # Uploads validos (mesmas fixtures do teste do core)
    bytes_a = sped_a().encode("cp1252")
    bytes_b = sped_b().encode("cp1252")
    enviar(cliente, sessao, "a", "sped_a.txt", bytes_a)
    enviar(cliente, sessao, "b", "sped_b.txt", bytes_b)

    # Exportar antes de comparar: 422
    r = cliente.post(f"/api/diff/exportar?sessao_id={sessao}")
    checar(r.status_code == 422 and "Compare" in r.json()["detail"],
           f"exportar antes de comparar deveria dar 422: {r.status_code}")

    # Comparacao como job
    job = cliente.post("/api/diff/comparar", json={
        "sessao_id": sessao, "apenas_entradas": False}).json()
    resultado = esperar_job(cliente, job["job_id"])

    resumo = resultado["resumo"]
    checar(resumo["total_a"] == 3, f"total_a: {resumo}")
    checar(resumo["total_b"] == 3, f"total_b: {resumo}")
    checar(resumo["conciliadas"] == 2, f"conciliadas: {resumo}")
    checar(resumo["iguais"] == 1, f"iguais: {resumo}")
    checar(resumo["divergentes"] == 1, f"divergentes: {resumo}")
    checar(resumo["apenas_em_a"] == 1, f"apenas_em_a: {resumo}")
    checar(resumo["apenas_em_b"] == 1, f"apenas_em_b: {resumo}")
    checar(resumo["total_diferencas"] == len(resultado["divergencias"]),
           f"previa deveria conter todas as diferencas: {resumo}")

    checar(resultado["rotulo_a"] == "A (contabilidade)"
           and resultado["rotulo_b"] == "B (cliente)",
           f"rotulos fixos do desktop: {resultado['rotulo_a']} / "
           f"{resultado['rotulo_b']}")
    checar(resultado["filtro"] == "" and resultado["aviso"] == "",
           "sem filtro de entradas nao deveria ter rotulo/aviso")

    # Divergencias campo a campo (flatten: uma linha por DiferencaCampo)
    linhas = resultado["divergencias"]
    checar(all(linha["chave"] == CH2 for linha in linhas),
           f"todas as divergencias deveriam ser da nota 2002: {linhas}")
    valor_contabil = next(
        (x for x in linhas if x["campo"] == "Valor contabil"), None)
    checar(valor_contabil is not None
           and valor_contabil["nivel"] == "Nota"
           and (valor_contabil["valor_a"], valor_contabil["valor_b"])
           == ("200.00", "250.00"),
           f"diferenca de Valor contabil: {valor_contabil}")
    cfop = next((x for x in linhas if x["campo"] == "CFOP"), None)
    checar(cfop is not None and cfop["nivel"] == "Item"
           and cfop["item"] == "1"
           and (cfop["valor_a"], cfop["valor_b"]) == ("1102", "5102"),
           f"diferenca de CFOP do item 1: {cfop}")
    checar(any(x["campo"] == "Item so no arquivo A" and x["item"] == "2"
               for x in linhas),
           f"faltou o item removido (so em A): {linhas}")

    # So em A / So em B
    so_a, so_b = resultado["apenas_em_a"], resultado["apenas_em_b"]
    checar(len(so_a) == 1 and so_a[0]["chave"] == CH3,
           f"so em A deveria ser a nota 3003: {so_a}")
    checar(len(so_b) == 1 and so_b[0]["chave"] == CH4,
           f"so em B deveria ser a nota 4004: {so_b}")
    checar(so_a[0]["valor"].startswith("R$") and so_a[0]["fornecedor"],
           f"valor em BRL e fornecedor preenchido: {so_a}")

    # Exportacao do Excel a partir do resultado guardado na sessao
    r = cliente.post(f"/api/diff/exportar?sessao_id={sessao}")
    checar(r.status_code == 200, f"exportar falhou: {r.status_code} {r.text}")
    checar(r.headers["content-type"] == MEDIA_XLSX,
           f"content-type errado: {r.headers['content-type']}")
    checar(r.content.startswith(b"PK"), "resposta nao e um xlsx (bytes PK)")
    checar("comparacao_speds.xlsx" in
           r.headers.get("content-disposition", ""),
           "download sem filename sugerido")

    # Arquivos identicos por conteudo: recusa como no desktop
    sessao2 = nova_sessao(cliente)
    enviar(cliente, sessao2, "a", "sped_a.txt", bytes_a)
    enviar(cliente, sessao2, "b", "sped_copia.txt", bytes_a)
    r = cliente.post("/api/diff/comparar", json={"sessao_id": sessao2})
    checar(r.status_code == 422 and "mesmo" in r.json()["detail"],
           f"arquivos identicos deveriam dar 422: {r.status_code} {r.text}")

    print("OK - comparador SPED x SPED web (auth, uploads a/b, job, resumo, "
          "divergencias, so em A/B, arquivos identicos, Excel) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
