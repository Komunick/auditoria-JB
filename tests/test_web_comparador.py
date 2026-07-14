"""Versao web — Comparador SPED x SEFAZ de ponta a ponta.

Sobe o app FastAPI com TestClient e exercita: bloqueio sem login, bootstrap,
sessao de trabalho, upload do SPED (.txt) e da relacao SEFAZ (.xlsx),
comparacao como job (resumo, listas serializadas, diagnostico), aviso
MSG_SEM_ENTRADAS quando o filtro de entradas zera o SPED e exportacao do
Excel. Reusa os construtores de fixtures de test_comparador.py.
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

from auditoria_fiscal.core.filtro_sped import MSG_SEM_ENTRADAS  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from test_comparador import (  # noqa: E402
    CH_B, CH_D, chave, linha, montar_sefaz_xlsx, montar_sped,
)

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


def montar_sped_saidas() -> str:
    """SPED sintetico so com uma nota de SAIDA (IND_OPER=1)."""
    ch = chave("22333444000155", "000007007", "77777777")
    linhas = [
        linha("0000", {4: "01032026", 5: "31032026",
                       6: "EMPRESA TESTE LTDA", 7: "11222333000181",
                       9: "SP"}),
        linha("C100", {2: "1", 3: "1", 5: "55", 6: "00", 7: "1", 8: "7007",
                       9: ch, 10: "05032026", 11: "05032026", 12: "700,00",
                       16: "700,00", 21: "700,00"}),
    ]
    return "\r\n".join(linhas) + "\r\n"


def bytes_sefaz() -> bytes:
    caminho = os.path.join(_TMP, "sefaz.xlsx")
    montar_sefaz_xlsx(caminho)
    with open(caminho, "rb") as fh:
        return fh.read()


def nova_sessao(cliente) -> str:
    return cliente.post("/api/sessoes",
                        json={"ferramenta": "comparador"}).json()["sessao_id"]


def enviar(cliente, sessao: str, tipo: str, nome: str, conteudo: bytes):
    r = cliente.post(f"/api/comparador/upload?sessao_id={sessao}&tipo={tipo}",
                     files={"arquivo": (nome, conteudo,
                                        "application/octet-stream")})
    checar(r.status_code == 200, f"upload {tipo} falhou: {r.text}")


def main() -> int:
    cliente = TestClient(criar_app())

    # Sem login: API bloqueada
    checar(cliente.post("/api/comparador/comparar",
                        json={"sessao_id": "x"}).status_code == 401,
           "API deveria exigir login")

    # Bootstrap do primeiro admin (ja loga)
    r = cliente.post("/api/bootstrap", json={
        "usuario": "weslley", "nome": "Weslley", "senha": "segredo1"})
    checar(r.status_code == 200, f"bootstrap falhou: {r.text}")

    # Comparar sem uploads: 422 com mensagem de validacao
    sessao = nova_sessao(cliente)
    r = cliente.post("/api/comparador/comparar", json={"sessao_id": sessao})
    checar(r.status_code == 422 and "SPED" in r.json()["detail"],
           f"comparar sem SPED deveria dar 422: {r.status_code} {r.text}")

    # Upload de tipo invalido e extensao errada
    r = cliente.post(f"/api/comparador/upload?sessao_id={sessao}&tipo=zzz",
                     files={"arquivo": ("x.txt", b"x", "text/plain")})
    checar(r.status_code == 422, "tipo de upload invalido deveria dar 422")
    r = cliente.post(f"/api/comparador/upload?sessao_id={sessao}&tipo=sped",
                     files={"arquivo": ("sped.pdf", b"x", "application/pdf")})
    checar(r.status_code == 422, "SPED sem .txt deveria dar 422")

    # Uploads validos (mesmas fixtures do teste do core)
    enviar(cliente, sessao, "sped", "sped.txt",
           montar_sped().encode("cp1252"))
    enviar(cliente, sessao, "sefaz", "sefaz.xlsx", bytes_sefaz())

    # Exportar antes de comparar: 422
    r = cliente.post(f"/api/comparador/exportar?sessao_id={sessao}")
    checar(r.status_code == 422 and "Compare" in r.json()["detail"],
           f"exportar antes de comparar deveria dar 422: {r.status_code}")

    # Comparacao como job
    job = cliente.post("/api/comparador/comparar", json={
        "sessao_id": sessao, "apenas_entradas": True}).json()
    resultado = esperar_job(cliente, job["job_id"])

    resumo = resultado["resumo"]
    checar(resumo["notas_na_sefaz"] == 4, f"sefaz: {resumo}")
    checar(resumo["notas_no_sped"] == 4, f"sped entradas: {resumo}")
    checar(resumo["conciliadas"] == 3, f"conciliadas: {resumo}")
    checar(resumo["faltantes_no_sped"] == 1, f"faltantes: {resumo}")
    checar(resumo["canceladas_escrituradas"] == 1, f"canceladas: {resumo}")
    checar(resumo["divergencias_valor"] == 1, f"divergencias: {resumo}")
    checar(resumo["apenas_no_sped"] == 1, f"apenas sped: {resumo}")

    checar(resultado["empresa"] == "EMPRESA TESTE LTDA",
           f"empresa: {resultado['empresa']}")
    checar(resultado["filtro"].startswith("Filtro aplicado"),
           f"rotulo do filtro: {resultado['filtro']}")
    checar(resultado["aviso"] == "", f"nao deveria ter aviso: {resultado['aviso']}")

    faltante = resultado["faltantes"][0]
    checar(faltante["chave"] == CH_B, f"faltante deveria ser B: {faltante}")
    checar(faltante["valor"].startswith("R$"),
           f"valor deveria vir formatado em BRL: {faltante}")
    checar(faltante["data"].count("/") == 2,
           f"data deveria vir dd/mm/aaaa: {faltante}")
    checar(faltante["cnpj_emitente"] == "55666777000188",
           f"cnpj do emitente (da chave): {faltante}")

    divergencia = resultado["divergencias"][0]
    checar(divergencia["chave"] == CH_D, f"divergencia deveria ser D: {divergencia}")
    checar(divergencia["diferenca"] == "R$ 50,00",
           f"diferenca formatada: {divergencia}")

    checar(len(resultado["canceladas"]) == 1
           and resultado["canceladas"][0]["situacao_sefaz"] == "Cancelada",
           f"cancelada escriturada: {resultado['canceladas']}")
    checar(len(resultado["apenas_no_sped"]) == 1
           and resultado["apenas_no_sped"][0]["valor"].startswith("R$"),
           f"apenas no SPED: {resultado['apenas_no_sped']}")

    diagnostico = resultado["diagnostico"]
    checar("chave" in diagnostico["mapa_colunas"],
           f"diagnostico sem coluna chave: {diagnostico}")
    checar(diagnostico["registros_validos"] == 4,
           f"registros validos: {diagnostico}")

    # Exportacao do Excel a partir do resultado guardado na sessao
    r = cliente.post(f"/api/comparador/exportar?sessao_id={sessao}")
    checar(r.status_code == 200, f"exportar falhou: {r.status_code} {r.text}")
    checar(r.headers["content-type"] == MEDIA_XLSX,
           f"content-type errado: {r.headers['content-type']}")
    checar(r.content.startswith(b"PK"), "resposta nao e um xlsx (bytes PK)")
    checar("conferencia_sped_sefaz.xlsx" in
           r.headers.get("content-disposition", ""),
           "download sem filename sugerido")

    # Regra MSG_SEM_ENTRADAS: SPED so com saidas + filtro de entradas
    sessao2 = nova_sessao(cliente)
    enviar(cliente, sessao2, "sped", "sped_saidas.txt",
           montar_sped_saidas().encode("cp1252"))
    enviar(cliente, sessao2, "sefaz", "sefaz.xlsx", bytes_sefaz())
    job = cliente.post("/api/comparador/comparar", json={
        "sessao_id": sessao2, "apenas_entradas": True}).json()
    resultado = esperar_job(cliente, job["job_id"])
    checar(resultado["resumo"]["notas_no_sped"] == 0,
           f"filtro deveria zerar o SPED: {resultado['resumo']}")
    checar(resultado["aviso"] == MSG_SEM_ENTRADAS,
           f"aviso de sem entradas: {resultado['aviso']!r}")

    print("OK - comparador SPED x SEFAZ web (auth, uploads, job, resumo, "
          "listas, diagnostico, aviso sem entradas, Excel) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
