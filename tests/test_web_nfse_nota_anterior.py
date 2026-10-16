"""Versao web — preencher o perfil por uma nota ja emitida (spec 009, Parte 2).

Rota POST /api/nfse/perfis/sugestao-nota: so quem cadastra perfis; arquivo
grande, DOCTYPE, arquivo sem NFS-e e nota de outro CNPJ recusados; sugestoes
com a fonte; nada gravado (nenhum perfil novo, nenhum arquivo) e nenhum CPF ou
nome de tomador ou aluno na resposta, na pasta de dados ou na trilha.
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

_TMP = tempfile.mkdtemp(prefix="auditoria_web_nfse_nota_")
os.environ["AUDITORIA_WEB_DADOS"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from auditoria_fiscal.core import nfse_nota_anterior as na  # noqa: E402
from auditoria_fiscal.web.servidor import criar_app  # noqa: E402
from fixtures import nfse as fx  # noqa: E402
from fixtures.nfse import notas_anteriores as nt  # noqa: E402

ADMIN = {"usuario": "weslley", "nome": "Weslley", "senha": "segredo1"}
CADASTRO = {"usuario": "cadastro", "nome": "Cadastro", "senha": "segredo7"}
SO_ABA = {"usuario": "soaba", "nome": "So aba", "senha": "segredo8"}
PESSOAIS = ("12345678909", "123.456.789-09", "ANA EXEMPLO", "PEDRO EXEMPLO")


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


def enviar(cliente, dados: bytes, nome: str = "nota.xml", **extra):
    campos = {"turmas": "Berçário\nInfantil II", "cnpj": ""}
    campos.update(extra)
    return cliente.post("/api/nfse/perfis/sugestao-nota", data=campos,
                        files={"arquivo": (nome, dados, "text/xml")})


def main() -> int:
    app = criar_app()
    adm = TestClient(app)
    checar(adm.post("/api/bootstrap", json=ADMIN).status_code == 200, "bootstrap")
    for cred, perms in ((CADASTRO, ["aba.nfse", "nfse.perfis"]), (SO_ABA, ["aba.nfse"])):
        r = adm.post("/api/admin/usuarios", json={**cred, "admin": False,
                                                  "permissoes": perms})
        checar(r.status_code == 200, r.text)
    cadastro = entrar(app, CADASTRO)
    so_aba = entrar(app, SO_ABA)
    nota = nt.nota_salvador()

    checar(enviar(TestClient(app), nota).status_code == 401, "sem login")
    checar(enviar(so_aba, nota).status_code == 403, "sem nfse.perfis")
    r = enviar(cadastro, b" " * (na.MAX_ARQUIVO_BYTES + 1))
    checar(r.status_code == 413 and codigo(r) == na.NOTA_GRANDE_DEMAIS, r.text)
    r = enviar(cadastro, b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>')
    checar(r.status_code == 422 and codigo(r) == na.NOTA_ILEGIVEL, r.text)
    r = enviar(cadastro, b"<NFe/>")
    checar(r.status_code == 422 and codigo(r) == na.NOTA_SEM_NFSE, r.text)
    r = enviar(cadastro, nota, cnpj="11.444.777/0001-61")
    checar(r.status_code == 422 and codigo(r) == na.NOTA_DE_OUTRO_CNPJ, r.text)

    r = enviar(cadastro, nota, cnpj=fx.CNPJ)
    checar(r.status_code == 200, r.text)
    s = r.json()
    campos = s["campos"]
    checar(campos["cnpj"]["valor"] == fx.CNPJ and campos["inscricao_municipal"]["valor"]
           == nt.IM and campos["aliquota"]["valor"] == "5,00", campos)
    checar(campos["modelo_discriminacao"]["valor"] == fx.MODELO_CRECHE, campos)
    checar(s["turmas"][0]["nome"] == "Berçário"
           and s["turmas"][0]["c_trib_nac"] == "080101", s["turmas"])
    checar(s["manuais"] and isinstance(s["avisos"], list), s)
    for pessoal in PESSOAIS:
        checar(pessoal not in r.text, f"dado pessoal {pessoal!r} na resposta")

    # Zip e NFS-e nacional pela mesma rota.
    r = enviar(cadastro, nt.zip_de({"a.xml": nt.nfse_nacional()}), nome="notas.zip")
    checar(r.status_code == 200 and r.json()["campos"]["informar_im"]["valor"] is True,
           r.text)

    # Nada gravado e nada da nota sobra.
    checar(cadastro.get("/api/nfse/perfis").json()["itens"] == [],
           "a sugestão não cria perfil")
    for raiz, _, arquivos in os.walk(_TMP):
        for nome in arquivos:
            checar(not nome.lower().endswith((".xml", ".zip")),
                   f"arquivo da nota na pasta de dados: {nome}")
            with open(os.path.join(raiz, nome), "rb") as arq:
                conteudo = arq.read()
            for pessoal in PESSOAIS:
                checar(pessoal.encode() not in conteudo,
                       f"dado pessoal {pessoal!r} gravado em {nome}")
    itens = adm.get("/api/admin/historico", params={"limite": 500}).json()["itens"]
    for pessoal in PESSOAIS:
        checar(pessoal not in str(itens), f"dado pessoal {pessoal!r} na trilha")
    checar(any(i["acao"] == "nfse.perfil_nota_anterior" and i["resultado"] == "ok"
               for i in itens), "leitura na trilha")
    checar(any(i["acao"] == "nfse.perfil_nota_anterior" and i["resultado"] == "negado"
               for i in itens), "tentativa negada na trilha")

    # O que veio serve para cadastrar o perfil, no formato do formulário.
    dados = fx.perfil_completo()
    for nome in ("razao_social", "inscricao_municipal", "municipio_ibge",
                 "municipio_prestacao_ibge", "iss_retido", "aliquota", "reg_esp_trib",
                 "modelo_discriminacao"):
        dados[nome] = campos[nome]["valor"]
    dados["turmas"][0].update({k: v for k, v in s["turmas"][0].items()
                               if k.startswith(("c_", "ref_")) and v})
    r = cadastro.post("/api/nfse/perfis", json={"dados": dados,
                                                "motivo": "preenchido pela nota"})
    checar(r.status_code == 200, r.text)

    print("OK - perfil pela nota já emitida na web (permissão, recusas, sugestões com "
          "fonte, zip e nacional, nada gravado, sem dados pessoais) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
