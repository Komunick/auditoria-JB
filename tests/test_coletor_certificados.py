"""Coletor da pasta de certificados (spec 012, US8/FR-016).

Pasta SINTETICA com a mesma forma da pasta da JB (fotos de 22/10/2026): uma
subpasta por cliente com `_info.txt` (razao social, fantasia, CNPJ, validade
e senha em texto aberto), o `.pfx` e a `.key`, e lixo de sistema
(`GPUCache`). O resultado nao pode levar senha, chave nem certificado.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from auditoria_fiscal.core import coletor_certificados as cc  # noqa: E402
from auditoria_fiscal.core.documentos_br import dv_cnpj  # noqa: E402


def cnpj(base: str) -> str:
    return base + dv_cnpj(base)


C_OK, C_OUTRO, C_DIV = cnpj("011111110001"), cnpj("022222220001"), cnpj("033333330001")
SENHAS = ["SenhaPfx#1", "SenhaPfx#2", "SenhaPfx#3", "SenhaPfx#4", "Senha$5"]


def pfx(cn: str, senha: str, fim: datetime) -> tuple[bytes, bytes]:
    chave = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                                       "AC SINTETICA")]))
            .public_key(chave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(fim - timedelta(days=365)).not_valid_after(fim)
            .sign(chave, hashes.SHA256()))
    return (pkcs12.serialize_key_and_certificates(
        b"x", chave, cert, None,
        serialization.BestAvailableEncryption(senha.encode())),
        cert.public_bytes(serialization.Encoding.DER))


def info(razao: str, documento: str, validade: str, senha: str | None) -> str:
    linhas = [f"RAZÃO DE EMPRESA: {razao}", "NOME DA FANTASIA: LOJA SINTETICA",
              f"CNPJ: {documento[:2]}.{documento[2:5]}.{documento[5:8]}/"
              f"{documento[8:12]}-{documento[12:]}", f"VALIDADE: {validade}"]
    if senha is not None:
        linhas.append(f"SENHA:{senha}")
    return "\r\n\r\n".join(linhas) + "\r\n"


def escrever(caminho: str, conteudo, modo="wb") -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, modo, **({} if "b" in modo else {"encoding": "cp1252"})) as f:
        f.write(conteudo)


def montar(raiz: str) -> None:
    fim = datetime(2027, 3, 15, tzinfo=timezone.utc)
    # 1. Tudo certo
    conteudo, _ = pfx(f"ALFA LTDA:{C_OK}", SENHAS[0], fim)
    escrever(os.path.join(raiz, "ALFA LTDA", "ALFA LTDA.pfx"), conteudo)
    escrever(os.path.join(raiz, "ALFA LTDA", "_info.txt"),
             info("Alfa Ltda", C_OK, "15/03/2027", SENHAS[0]), "w")
    escrever(os.path.join(raiz, "ALFA LTDA", "ChavePrivada.key"), b"chave")
    os.makedirs(os.path.join(raiz, "ALFA LTDA", "GPUCache"))
    # 2. Validade e CNPJ do _info desatualizados
    conteudo, _ = pfx(f"BETA LTDA:{C_DIV}", SENHAS[1], fim)
    escrever(os.path.join(raiz, "BETA", "beta.pfx"), conteudo)
    escrever(os.path.join(raiz, "BETA", "_info.txt"),
             info("Beta", C_OUTRO, "08/06/2023", SENHAS[1]), "w")
    # 3. Senha do _info nao abre
    conteudo, _ = pfx(f"GAMA:{C_OK}", SENHAS[2], fim)
    escrever(os.path.join(raiz, "GAMA", "gama.pfx"), conteudo)
    escrever(os.path.join(raiz, "GAMA", "_info.txt"),
             info("Gama", C_OK, "15/03/2027", "outra-senha"), "w")
    # 4. Sem .pfx (so a chave e o _info)
    escrever(os.path.join(raiz, "DELTA", "_info.txt"),
             info("Delta", C_OK, "01/01/2027", SENHAS[3]), "w")
    escrever(os.path.join(raiz, "DELTA", "x.key"), b"chave")
    # 5. Sem _info: o .pfx nao abre sem senha
    conteudo, _ = pfx(f"EPSILON:{C_OK}", SENHAS[4], fim)
    escrever(os.path.join(raiz, "EPSILON", "e.pfx"), conteudo)
    # 6. Dois .pfx (renovado e antigo) com a mesma senha
    conteudo1, _ = pfx(f"ZETA:{C_OK}", SENHAS[4], fim)
    conteudo2, _ = pfx(f"ZETA:{C_OK}", SENHAS[4], datetime(2025, 1, 1,
                                                            tzinfo=timezone.utc))
    escrever(os.path.join(raiz, "ZETA", "novo.pfx"), conteudo1)
    escrever(os.path.join(raiz, "ZETA", "antigo.P12"), conteudo2)
    escrever(os.path.join(raiz, "ZETA", "_INFO.TXT"),
             info("Zeta", C_OK, "15/03/2027", SENHAS[4]), "w")
    # 7. So o .cer (sem senha nenhuma)
    _, cer = pfx(f"ETA:{C_OK}", "x", fim)
    escrever(os.path.join(raiz, "ETA", "eta.cer"), cer)
    # 8. Arquivo solto na raiz: nao e' cliente
    escrever(os.path.join(raiz, "leia-me.txt"), "nada", "w")


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def main() -> int:
    raiz = tempfile.mkdtemp(prefix="certificados_")
    montar(raiz)

    coleta = cc.coletar(raiz, agora=datetime(2026, 10, 26, 9, 0))
    texto = json.dumps(coleta, ensure_ascii=False)
    for senha in SENHAS + ["outra-senha"]:
        checar(senha not in texto, f"a coleta nao pode levar a senha {senha!r}")
    checar("chave" not in texto.lower().replace("chave_", ""),
           "nada da chave privada")
    checar(coleta["formato"] == cc.FORMATO and coleta["versao"] == 1, coleta)

    por_pasta: dict[str, list] = {}
    for item in coleta["itens"]:
        por_pasta.setdefault(item["pasta"], []).append(item)
    checar(sorted(por_pasta) == ["ALFA LTDA", "BETA", "DELTA", "EPSILON",
                                 "ETA", "GAMA", "ZETA"],
           f"uma entrada por subpasta, sem a raiz: {sorted(por_pasta)}")

    alfa = por_pasta["ALFA LTDA"][0]
    checar(alfa["titular_documento"] == C_OK and alfa["fim"] == "2027-03-15",
           alfa)
    checar(alfa["problemas"] == [], f"ALFA esta certa: {alfa['problemas']}")
    checar(alfa["info"]["razao_social"] == "Alfa Ltda"
           and alfa["info"]["documento"] == C_OK
           and alfa["info"]["validade"] == "2027-03-15"
           and "senha" not in alfa["info"], alfa["info"])
    checar(alfa["tipo"] == "A1" and len(alfa["hash_arquivo"]) == 64, alfa)

    beta = por_pasta["BETA"][0]
    checar(cc.VALIDADE_DIVERGENTE in beta["problemas"]
           and cc.DOCUMENTO_DIVERGENTE in beta["problemas"], beta["problemas"])
    checar(beta["fim"] == "2027-03-15",
           "a validade que vale e' a do certificado, nao a do _info")

    gama = por_pasta["GAMA"][0]
    checar(gama["problemas"] == [cc.SENHA_NAO_ABRE] and not gama["fim"], gama)

    delta = por_pasta["DELTA"][0]
    checar(delta["problemas"] == [cc.SEM_CERTIFICADO], delta["problemas"])
    checar(delta["info"]["validade"] == "2027-01-01",
           "sem certificado, o _info ainda informa o que diz")

    epsilon = por_pasta["EPSILON"][0]
    checar(cc.SEM_INFO in epsilon["problemas"]
           and cc.SENHA_NAO_ABRE not in epsilon["problemas"]
           and cc.SEM_SENHA in epsilon["problemas"], epsilon["problemas"])

    zeta = por_pasta["ZETA"]
    checar(len(zeta) == 2 and all(cc.VARIOS_CERTIFICADOS in z["problemas"]
                                  for z in zeta), zeta)
    checar(sorted(z["fim"] for z in zeta) == ["2025-01-01", "2027-03-15"],
           "os dois certificados sao lidos")

    eta = por_pasta["ETA"][0]
    checar(eta["problemas"] == [cc.SEM_INFO] and eta["fim"] == "2027-03-15",
           f".cer abre sem senha: {eta}")

    totais = coleta["totais"]
    checar(totais["subpastas"] == 7 and totais["lidos"] == 5
           and totais["com_problema"] >= 5, totais)

    # ------------------------------------------------------------------
    # Comando de linha: grava o arquivo e o resumo nao mostra senha

    saida = os.path.join(tempfile.mkdtemp(prefix="coleta_saida_"), "coleta.json")
    processo = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "coletar-certificados.py"), raiz,
         saida], capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    checar(processo.returncode == 0, processo.stderr[-400:])
    checar(os.path.isfile(saida), "o comando grava o arquivo de coleta")
    for senha in SENHAS:
        checar(senha not in processo.stdout, "o resumo na tela nao mostra senha")
    with open(saida, encoding="utf-8") as arquivo:
        gravada = json.load(arquivo)
    checar(len(gravada["itens"]) == len(coleta["itens"]), "mesmo conteudo")

    processo = subprocess.run(
        [sys.executable, os.path.join(RAIZ, "coletar-certificados.py"),
         os.path.join(raiz, "nao-existe"), saida],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    checar(processo.returncode != 0, "pasta inexistente e' erro")

    print("OK - coletor de certificados (pasta por cliente, _info com "
          "rotulos, validade e CNPJ divergentes, senha que nao abre, sem "
          ".pfx, sem _info, dois certificados, .cer sem senha, coleta e "
          "comando sem senha) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
