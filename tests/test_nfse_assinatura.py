"""Assinatura XMLDSig da DPS (spec 008, FR-204, research.md R-3).

Estrutura exigida: Signature dentro da raiz DPS, irma de infDPS, sem prefixo;
Reference para o Id do infDPS; transforms enveloped + C14N 1.0; C14N 1.0 no
SignedInfo. SHA-256 por padrao, SHA-1 configuravel.

A conferencia propria (conferir_assinatura) e' a mesma implementacao que
assina; por isso uma segunda conferencia refaz tudo com o C14N da biblioteca
padrao do Python (expat), independente do libxml2. Foi ela que pegou, em
16/10/2026, a canonizacao de sub-arvore do libxml2 2.11 soltando `xmlns=""`:
a assinatura conferia consigo mesma e seria recusada pela Sefin (E0714). O
signxml nao serve de juiz aqui porque usa o mesmo caminho do libxml2.
"""

from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

import base64  # noqa: E402
import hashlib  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

from cryptography.exceptions import InvalidSignature  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402
from lxml import etree  # noqa: E402

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_assinatura as na  # noqa: E402
from auditoria_fiscal.core import nfse_certificado as nc  # noqa: E402
from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402
from fixtures.nfse import dps as fd  # noqa: E402

DS = "{http://www.w3.org/2000/09/xmldsig#}"
NFSE = "{http://www.sped.fazenda.gov.br/nfse}"


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def codigo_do_erro(funcao, *args, **kwargs) -> str | None:
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc.codigo
    return None


def c14n_independente(elemento) -> bytes:
    """C14N do elemento pela biblioteca padrao: o lxml so serializa o trecho
    (com os namespaces em escopo); quem canoniza e' o xml.etree (expat)."""
    return ET.canonicalize(etree.tostring(elemento).decode("utf-8")).encode("utf-8")


def conferencia_independente(assinado: bytes, cert, algoritmo: str) -> None:
    hash_lib, hash_cripto = {"sha256": (hashlib.sha256, hashes.SHA256),
                             "sha1": (hashlib.sha1, hashes.SHA1)}[algoritmo]
    raiz = etree.fromstring(assinado)
    inf = raiz.find(f"{NFSE}infDPS")
    info = raiz.find(f"{DS}Signature/{DS}SignedInfo")
    digest = base64.b64encode(hash_lib(c14n_independente(inf)).digest()).decode()
    checar(info.findtext(f"{DS}Reference/{DS}DigestValue") == digest,
           f"digest do infDPS nao confere pelo C14N da biblioteca padrao ({algoritmo})")
    canonico = c14n_independente(info)
    checar(b'xmlns=""' not in canonico, "SignedInfo canonico sem xmlns vazio")
    valor = base64.b64decode(raiz.findtext(f"{DS}Signature/{DS}SignatureValue"))
    try:
        cert.certificado.public_key().verify(valor, canonico, padding.PKCS1v15(),
                                             hash_cripto())
    except InvalidSignature:
        checar(False, f"assinatura nao confere pelo C14N da biblioteca padrao "
                      f"({algoritmo})")


def main() -> int:
    ac = cf.gerar_ac()
    cert = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(ac), ac=ac), cf.SENHA)
    xml = fd.xml_dps(1)
    checar(nd.validar_xsd(xml) == [], "a DPS de exemplo precisa ser valida")

    assinado = na.assinar_dps(xml, cert)
    checar(nd.validar_xsd(assinado) == [],
           f"a DPS assinada continua valida: {nd.validar_xsd(assinado)}")
    info = na.conferir_assinatura(assinado)
    checar(info["algoritmo"] == "sha256" and info["cnpj"] == cf.CNPJ, info)
    checar(info["impressao"] == cert.impressao, "o certificado do KeyInfo e' o usado")

    raiz = etree.fromstring(assinado)
    filhos = list(raiz)
    checar([f.tag for f in filhos] == [f"{NFSE}infDPS", f"{DS}Signature"],
           f"Signature irma de infDPS, depois dele: {[f.tag for f in filhos]}")
    assinatura = filhos[1]
    checar(assinatura.prefix is None, "Signature sem prefixo de namespace")
    referencia = assinatura.find(f"{DS}SignedInfo/{DS}Reference")
    checar(referencia.get("URI") == "#" + fd.id_dps(1), referencia.get("URI"))
    transforms = [t.get("Algorithm") for t in referencia.iter(f"{DS}Transform")]
    checar(transforms == [na.ENVELOPED, na.C14N], transforms)
    checar(assinatura.find(f"{DS}SignedInfo/{DS}CanonicalizationMethod")
           .get("Algorithm") == na.C14N, "C14N 1.0 no SignedInfo")
    checar(assinatura.find(f"{DS}SignedInfo/{DS}SignatureMethod").get("Algorithm")
           == "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256", "RSA-SHA256")
    checar(assinatura.find(f".//{DS}X509Certificate") is not None, "KeyInfo com X509")
    checar(b"<ds:" not in assinado, "nada de prefixo ds:")
    checar(b'xmlns=""' not in na._c14n(assinatura.find(f"{DS}SignedInfo")),
           "regressao: a canonizacao propria nao pode soltar xmlns vazio")
    conferencia_independente(assinado, cert, "sha256")

    # SHA-1, para o caso de a Sefin exigir (research.md, R-3).
    sha1 = na.assinar_dps(xml, cert, algoritmo="sha1")
    checar(na.conferir_assinatura(sha1)["algoritmo"] == "sha1", "SHA-1")
    checar(etree.fromstring(sha1).find(f".//{DS}SignatureMethod").get("Algorithm")
           == "http://www.w3.org/2000/09/xmldsig#rsa-sha1", "RSA-SHA1")
    conferencia_independente(sha1, cert, "sha1")
    checar(codigo_do_erro(na.assinar_dps, xml, cert, algoritmo="md5")
           == na.ALGORITMO_DESCONHECIDO, "algoritmo fora da lista")

    # Adulteracoes.
    trocado = assinado.replace(b"<xNome>Ana Exemplo</xNome>",
                               b"<xNome>Ana Exemplar</xNome>")
    checar(trocado != assinado, "a troca precisa acontecer")
    checar(codigo_do_erro(na.conferir_assinatura, trocado) == na.ASSINATURA_INVALIDA,
           "conteudo alterado depois de assinado")
    raiz = etree.fromstring(assinado)
    valor = raiz.find(f".//{DS}SignatureValue")
    valor.text = ("A" if valor.text[0] != "A" else "B") + valor.text[1:]
    checar(codigo_do_erro(na.conferir_assinatura, etree.tostring(raiz))
           == na.ASSINATURA_INVALIDA, "SignatureValue adulterado")
    outro = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(ac)), cf.SENHA)
    raiz = etree.fromstring(assinado)
    raiz.find(f".//{DS}X509Certificate").text = etree.fromstring(
        na.assinar_dps(xml, outro)).find(f".//{DS}X509Certificate").text
    checar(codigo_do_erro(na.conferir_assinatura, etree.tostring(raiz))
           == na.ASSINATURA_INVALIDA, "certificado trocado no KeyInfo")
    checar(codigo_do_erro(na.conferir_assinatura, xml) == na.ASSINATURA_AUSENTE,
           "DPS sem assinatura")
    checar(codigo_do_erro(na.assinar_dps, assinado, cert) == na.DPS_JA_ASSINADA,
           "nao assina duas vezes")

    # Entrada hostil: entidade externa nao e' resolvida.
    hostil = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM '
              b'"file:///etc/passwd">]><DPS xmlns="http://www.sped.fazenda.gov.br/nfse">'
              b'<infDPS Id="X">&e;</infDPS></DPS>')
    checar(codigo_do_erro(na.assinar_dps, hostil, cert) is not None,
           "XML com DOCTYPE/entidade e' recusado")

    print("OK - assinatura da DPS (estrutura, SHA-256 e SHA-1, XSD, adulteracao, "
          "certificado trocado, entrada hostil) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
