"""Versao web — transmissao a producao restrita (spec 008).

Rota que recebe o .pfx e a senha e abre um job; permissao nova
`nfse.transmitir` (fora do padrao de usuario novo); recusas antes de
qualquer conexao (senha errada, outro CNPJ, sem confirmacao, lote em
revisao, arquivo grande); job ate o fim contra a Sefin FALSA; downloads da
NFS-e e do DANFSe; descarte bloqueado; e o certificado nao sobra em lugar
nenhum (banco, pasta de dados, temporarios, trilha, resultado do job).
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_nfse_tx_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from auditoria_fiscal.web import permissoes  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from fixtures import nfse as fx  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402
from fixtures.nfse.sefin_falsa import SefinFalsa  # noqa: E402

ADMIN = {"usuario": "weslley", "nome": "Weslley", "senha": "segredo1"}
FISCAL = {"usuario": "fiscal", "nome": "Fiscal", "senha": "segredo3"}
TRANSMISSOR = {"usuario": "transmissor", "nome": "Transmissor", "senha": "segredo6"}

HOJE = dt.datetime.now(nd.FUSO_SALVADOR).date()


def texto(competencia: str) -> str:
    return (f"Competência: {competencia}\nResponsável: Ana Exemplo\nCPF: {fx.CPF_ANA}\n"
            "Aluno: Pedro Exemplo\nTurma: Berçário\nValor: 1.250,00\n\n"
            f"Competência: {competencia}\nResponsável: Bruno Teste\nCPF: {fx.CPF_BRUNO}\n"
            "Aluno: Caio Teste\nTurma: Infantil 2\nValor: 980,50\n")


def competencia(meses_atras: int) -> str:
    ano, mes = HOJE.year, HOJE.month - meses_atras
    while mes < 1:
        mes += 12
        ano -= 1
    return f"{mes:02d}/{ano}"


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def entrar(app, credenciais: dict) -> TestClient:
    cliente = TestClient(app)
    r = cliente.post("/api/login", json={"usuario": credenciais["usuario"],
                                         "senha": credenciais["senha"]})
    checar(r.status_code == 200, f"login {credenciais['usuario']}: {r.text}")
    return cliente


def codigo(r) -> str:
    try:
        return r.json()["detail"].get("code", "")
    except Exception:  # noqa: BLE001
        return ""


def lote_aprovado(adm, perfil_id: int, comp: str) -> int:
    r = adm.post("/api/nfse/lotes/texto", json={"perfil_id": perfil_id, "texto": texto(comp)})
    checar(r.status_code == 200, r.text)
    lote_id = r.json()["lote_id"]
    lote = adm.get(f"/api/nfse/lotes/{lote_id}").json()
    r = adm.post(f"/api/nfse/lotes/{lote_id}/aprovar",
                 json={"revision": lote["lote"]["revision"], "confirmar_avisos": True})
    checar(r.status_code == 200, f"aprovar: {r.text}")
    return lote_id


def transmitir(cliente, lote_id: int, pfx: bytes, senha: str = cf.SENHA, **extra):
    dados = {"senha": senha, "confirmar_producao_restrita": "true"}
    dados.update(extra)
    return cliente.post(f"/api/nfse/lotes/{lote_id}/transmitir", data=dados,
                        files={"certificado": ("a1.pfx", pfx, "application/x-pkcs12")})


def esperar_job(cliente, job_id: str) -> dict:
    for _ in range(200):
        r = cliente.get(f"/api/jobs/{job_id}", params={"ferramenta": "nfse"})
        checar(r.status_code == 200, f"job: {r.status_code} {r.text}")
        if r.json()["status"] != "executando":
            return r.json()
        time.sleep(0.05)
    checar(False, "o job nao terminou")
    return {}


def pastas_tls() -> set[str]:
    return {n for n in os.listdir(tempfile.gettempdir()) if n.startswith("nfse_tls_")}


def main() -> int:
    kit = cf.montar_kit(tempfile.mkdtemp(prefix="nfse_web_kit_"))
    falsa = SefinFalsa(kit, atraso=3.0)
    base = falsa.iniciar()
    os.environ.update({"AUDITORIA_NFSE_SEFIN_URL": base + "/SefinNacional",
                       "AUDITORIA_NFSE_ADN_URL": base,
                       "AUDITORIA_NFSE_CA_EXTRA": kit.ca_pem,
                       "AUDITORIA_NFSE_TIMEOUT": "2"})
    tls_antes = pastas_tls()
    try:
        app = criar_app()
        adm = TestClient(app)
        r = adm.post("/api/bootstrap", json=ADMIN)
        checar(r.status_code == 200, r.text)

        # Permissao nova: no catalogo, fora do padrao de usuario novo.
        checar("nfse.transmitir" in permissoes.SLUGS, "slug no catalogo")
        checar("nfse.transmitir" not in permissoes.PADRAO_NOVO_USUARIO,
               "transmitir nao vem marcado para usuario novo")
        for cred, perms in ((FISCAL, ["aba.nfse", "nfse.importar", "nfse.aprovar_emitir",
                                      "nfse.exportar"]),
                            (TRANSMISSOR, ["aba.nfse", "nfse.transmitir", "nfse.exportar"])):
            r = adm.post("/api/admin/usuarios", json={**cred, "admin": False,
                                                      "permissoes": perms})
            checar(r.status_code == 200, r.text)
        fiscal = entrar(app, FISCAL)
        transmissor = entrar(app, TRANSMISSOR)

        r = adm.post("/api/nfse/perfis", json={"dados": fx.perfil_completo()})
        checar(r.status_code == 200, r.text)
        perfil_id = r.json()["perfil_id"]
        lote_id = lote_aprovado(adm, perfil_id, competencia(0))
        pfx = kit.pfx()

        # Portao.
        checar(transmitir(TestClient(app), lote_id, pfx).status_code == 401, "sem login")
        r = transmitir(fiscal, lote_id, pfx)
        checar(r.status_code == 403, f"sem nfse.transmitir: {r.status_code}")

        # Recusas antes de qualquer conexao.
        r = transmitir(transmissor, lote_id, pfx, confirmar_producao_restrita="false")
        checar(r.status_code == 422 and codigo(r) == "CONFIRMACAO_OBRIGATORIA", r.text)
        r = transmitir(transmissor, lote_id, pfx, senha="errada")
        checar(r.status_code == 422 and codigo(r) == "CERTIFICADO_ILEGIVEL", r.text)
        outro = cf.pfx(cf.gerar_ecnpj(kit.ac, cnpj=cf.OUTRO_CNPJ))
        r = transmitir(transmissor, lote_id, outro)
        checar(r.status_code == 422 and codigo(r) == "CERTIFICADO_DE_OUTRO_CNPJ", r.text)
        r = transmitir(transmissor, lote_id, b"0" * (60 * 1024))
        checar(r.status_code == 413 and codigo(r) == "CERTIFICADO_GRANDE_DEMAIS", r.text)
        r = adm.post("/api/nfse/lotes/texto",
                     json={"perfil_id": perfil_id, "texto": texto(competencia(3))})
        r = transmitir(transmissor, r.json()["lote_id"], pfx)
        checar(r.status_code == 409 and codigo(r) == "ESTADO_INVALIDO", r.text)
        checar(falsa.posts == [], "nenhuma recusa chegou a Sefin")

        # Transmissao de verdade (contra a falsa).
        r = transmitir(transmissor, lote_id, pfx)
        checar(r.status_code == 200 and r.json().get("job_id"), r.text)
        job = esperar_job(transmissor, r.json()["job_id"])
        checar(job["status"] == "concluido", job)
        checar(job["resultado"]["autorizadas"] == 2 and job["resultado"]["interrompida"] is None,
               job["resultado"])
        checar(fiscal.get(f"/api/jobs/{r.json()['job_id']}",
                          params={"ferramenta": "nfse"}).status_code == 404,
               "job de outra pessoa nao aparece")

        lote = adm.get(f"/api/nfse/lotes/{lote_id}").json()
        checar([d["situacao"] for d in lote["dps"]] == ["autorizada"] * 2, lote["dps"])
        dps_id = lote["dps"][0]["id"]
        r = fiscal.post(f"/api/nfse/dps/{dps_id}/nfse-xml")
        checar(r.status_code == 200 and r.content.startswith(b"<?xml"), r.status_code)
        checar("PRODUCAO-RESTRITA-SEM-VALOR-FISCAL" in r.headers["content-disposition"],
               r.headers["content-disposition"])
        r = fiscal.post(f"/api/nfse/dps/{dps_id}/danfse")
        checar(r.status_code == 200 and r.content.startswith(b"%PDF")
               and "PRODUCAO-RESTRITA" in r.headers["content-disposition"], r.status_code)

        # Lote com NFS-e nao e' descartado.
        r = fiscal.post(f"/api/nfse/lotes/{lote_id}/descartar",
                        json={"revision": lote["lote"]["revision"], "motivo": "teste"})
        checar(r.status_code == 409 and codigo(r) == "LOTE_COM_NFSE", r.text)

        # Interrupcao (403 da Sefin) termina o job sem erro e com o motivo.
        lote2 = lote_aprovado(adm, perfil_id, competencia(1))
        falsa.programar("403")
        r = transmitir(transmissor, lote2, pfx)
        job = esperar_job(transmissor, r.json()["job_id"])
        checar(job["status"] == "concluido" and job["resultado"]["interrompida"], job)
        lote = adm.get(f"/api/nfse/lotes/{lote2}").json()
        checar([d["situacao"] for d in lote["dps"]] == ["gerada"] * 2, lote["dps"])
        r = fiscal.post(f"/api/nfse/dps/{lote['dps'][0]['id']}/nfse-xml")
        checar(r.status_code == 404 and codigo(r) == "NFSE_NAO_ENCONTRADA", r.text)

        # Nada do certificado sobra.
        checar(pastas_tls() == tls_antes, "PEM temporario apagado")
        for raiz, _, arquivos in os.walk(_TMP):
            for nome in arquivos:
                checar(not nome.lower().endswith((".pfx", ".p12", ".pem", ".key")),
                       f"arquivo de certificado na pasta de dados: {nome}")
                with open(os.path.join(raiz, nome), "rb") as arq:
                    conteudo = arq.read()
                checar(cf.SENHA.encode() not in conteudo and b"PRIVATE KEY" not in conteudo,
                       f"senha ou chave gravada em {nome}")
        itens = adm.get("/api/admin/historico", params={"limite": 1000}).json()["itens"]
        trilha = str(itens)
        checar(cf.SENHA not in trilha and "Ana Exemplo" not in trilha
               and fx.CPF_ANA not in trilha, "trilha geral sem senha, nome ou CPF")
        checar(any(i["acao"] == "nfse.transmitir" and i["resultado"] == "negado"
                   for i in itens), "tentativa negada na trilha")
        checar(any(i["acao"] == "nfse.transmitir" and i["resultado"] == "ok"
                   for i in itens), "transmissao na trilha")
    finally:
        falsa.parar()

    print("OK - transmissao web (permissao nova, recusas antes de conectar, job, "
          "downloads da NFS-e e do DANFSe, descarte bloqueado, interrupcao, "
          "certificado sem rastro) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
