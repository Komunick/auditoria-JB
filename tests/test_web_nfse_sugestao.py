"""Versao web — preencher o perfil pelo certificado (spec 009).

Rota POST /api/nfse/perfis/sugestao: so quem cadastra perfis; senha errada,
arquivo grande e municipio invalido recusados; sugestoes com a fonte; nada
gravado (nenhum perfil novo) e o certificado sem rastro (banco, pasta de
dados, trilha). Contra o ADN FALSO em HTTPS com mTLS.
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_nfse_sug_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from fixtures import nfse as fx  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402
from fixtures.nfse.sefin_falsa import SefinFalsa  # noqa: E402

ADMIN = {"usuario": "weslley", "nome": "Weslley", "senha": "segredo1"}
CADASTRO = {"usuario": "cadastro", "nome": "Cadastro", "senha": "segredo7"}
SO_ABA = {"usuario": "soaba", "nome": "So aba", "senha": "segredo8"}


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


def sugerir(cliente, pfx: bytes, senha: str = cf.SENHA, **extra):
    dados = {"senha": senha, "municipio_ibge": "2927408", "c_trib_nac": "080101"}
    dados.update(extra)
    return cliente.post("/api/nfse/perfis/sugestao", data=dados,
                        files={"certificado": ("a1.pfx", pfx, "application/x-pkcs12")})


def main() -> int:
    kit = cf.montar_kit(tempfile.mkdtemp(prefix="nfse_sug_kit_"))
    falsa = SefinFalsa(kit)
    base = falsa.iniciar()
    os.environ.update({"AUDITORIA_NFSE_PARAMETROS_URL": base + "/parametrizacao",
                       "AUDITORIA_NFSE_CA_EXTRA": kit.ca_pem,
                       "AUDITORIA_NFSE_TIMEOUT": "3"})
    try:
        app = criar_app()
        adm = TestClient(app)
        checar(adm.post("/api/bootstrap", json=ADMIN).status_code == 200, "bootstrap")
        for cred, perms in ((CADASTRO, ["aba.nfse", "nfse.perfis"]),
                            (SO_ABA, ["aba.nfse"])):
            r = adm.post("/api/admin/usuarios", json={**cred, "admin": False,
                                                      "permissoes": perms})
            checar(r.status_code == 200, r.text)
        cadastro = entrar(app, CADASTRO)
        so_aba = entrar(app, SO_ABA)
        pfx = kit.pfx()

        checar(sugerir(TestClient(app), pfx).status_code == 401, "sem login")
        checar(sugerir(so_aba, pfx).status_code == 403, "sem nfse.perfis")
        r = sugerir(cadastro, pfx, senha="errada")
        checar(r.status_code == 422 and codigo(r) == "CERTIFICADO_ILEGIVEL", r.text)
        r = sugerir(cadastro, b"0" * (60 * 1024))
        checar(r.status_code == 413 and codigo(r) == "CERTIFICADO_GRANDE_DEMAIS", r.text)
        r = sugerir(cadastro, pfx, municipio_ibge="salvador")
        checar(r.status_code == 422 and codigo(r) == "MUNICIPIO_INVALIDO", r.text)
        checar(falsa.caminhos_parametros == [], "nenhuma recusa chegou ao ADN")

        r = sugerir(cadastro, pfx, c_trib_nac="080101, 080101")
        checar(r.status_code == 200, r.text)
        s = r.json()
        campos = s["campos"]
        checar(campos["cnpj"]["valor"] == "11.222.333/0001-81"
               and campos["razao_social"]["valor"] == "ESCOLA EXEMPLO LTDA", campos)
        checar(campos["convenio_incidencia_ativo"]["valor"] is True, campos)
        checar(campos["aliquota"]["valor"] == "5,00", campos)
        checar(s["manuais"] and isinstance(s["avisos"], list), s)
        checar(s["competencia"].endswith("-01"), s["competencia"])

        # Nada gravado e nada do certificado sobra.
        checar(cadastro.get("/api/nfse/perfis").json()["itens"] == [],
               "a sugestao nao cria perfil")
        for raiz, _, arquivos in os.walk(_TMP):
            for nome in arquivos:
                checar(not nome.lower().endswith((".pfx", ".p12", ".pem", ".key")),
                       f"arquivo de certificado na pasta de dados: {nome}")
                with open(os.path.join(raiz, nome), "rb") as arq:
                    conteudo = arq.read()
                checar(cf.SENHA.encode() not in conteudo and b"PRIVATE KEY" not in conteudo,
                       f"senha ou chave gravada em {nome}")
        itens = adm.get("/api/admin/historico", params={"limite": 500}).json()["itens"]
        checar(cf.SENHA not in str(itens), "trilha sem a senha")
        checar(any(i["acao"] == "nfse.perfil_sugestao" and i["resultado"] == "ok"
                   for i in itens), "consulta na trilha")
        checar(any(i["acao"] == "nfse.perfil_sugestao" and i["resultado"] == "negado"
                   for i in itens), "tentativa negada na trilha")

        # O que veio pode ser usado para cadastrar o perfil, como sempre.
        dados = fx.perfil_completo(razao_social=campos["razao_social"]["valor"])
        r = cadastro.post("/api/nfse/perfis", json={"dados": dados,
                                                    "motivo": "preenchido pelo certificado"})
        checar(r.status_code == 200, r.text)
    finally:
        falsa.parar()

    print("OK - perfil pelo certificado na web (permissao, recusas antes de consultar, "
          "sugestoes com fonte, nada gravado, certificado sem rastro) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
