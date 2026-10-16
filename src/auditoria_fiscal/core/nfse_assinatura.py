"""Assinatura XMLDSig da DPS para a Sefin Nacional (spec 008, research.md R-3).

Estrutura: `Signature` dentro da raiz `DPS`, irma de `infDPS`, sem prefixo;
`Reference URI="#<Id do infDPS>"` com os transforms enveloped-signature e
C14N 1.0; C14N 1.0 no `SignedInfo`; certificado do emitente no `KeyInfo`.

O algoritmo e' SHA-256 por padrao e SHA-1 sob pedido: as fontes divergem e o
Anexo I nao o fixa. A primeira transmissao real decide (E0714).

Sem rede e sem disco: recebe o XML e o certificado ja carregado, devolve o XML
assinado. `conferir_assinatura` refaz as contas — e' o que o servidor falso
dos testes usa e o que a transmissao roda antes de enviar.
"""

from __future__ import annotations

import base64
import copy
import hashlib

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

from . import nfse as nf
from .nfse_certificado import CertificadoA1, cnpj_do_certificado

DS = "http://www.w3.org/2000/09/xmldsig#"
NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"

ALGORITMOS = {
    # nome: (SignatureMethod, DigestMethod, hash da cryptography, hashlib)
    "sha256": ("http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
               "http://www.w3.org/2001/04/xmlenc#sha256", hashes.SHA256,
               hashlib.sha256),
    "sha1": ("http://www.w3.org/2000/09/xmldsig#rsa-sha1",
             "http://www.w3.org/2000/09/xmldsig#sha1", hashes.SHA1, hashlib.sha1),
}
ALGORITMO_PADRAO = "sha256"

ALGORITMO_DESCONHECIDO = "ALGORITMO_DESCONHECIDO"
ASSINATURA_INVALIDA = "ASSINATURA_INVALIDA"
ASSINATURA_AUSENTE = "ASSINATURA_AUSENTE"
DPS_JA_ASSINADA = "DPS_JA_ASSINADA"
XML_INVALIDO = "XML_INVALIDO"


def _parser() -> etree.XMLParser:
    return etree.XMLParser(no_network=True, resolve_entities=False, load_dtd=False,
                           huge_tree=False, remove_blank_text=False)


def _ler(xml: bytes):
    try:
        raiz = etree.fromstring(xml, _parser())
    except etree.XMLSyntaxError as exc:
        raise nf.ErroNfse(XML_INVALIDO, f"XML malformado: {exc}") from None
    if raiz.getroottree().docinfo.doctype:
        raise nf.ErroNfse(XML_INVALIDO, "XML com DOCTYPE não é aceito.")
    if raiz.tag != f"{{{NS_NFSE}}}DPS":
        raise nf.ErroNfse(XML_INVALIDO, "A raiz não é uma DPS do padrão nacional.")
    if raiz.nsmap != {None: NS_NFSE}:
        # C14N inclusiva levaria qualquer namespace extra da raiz para dentro
        # do infDPS; a DPS desta ferramenta nunca tem, entao recusar e' mais
        # seguro que adivinhar o que o verificador faria.
        raise nf.ErroNfse(XML_INVALIDO, "A raiz da DPS tem namespaces além do "
                                        "padrão nacional.")
    inf = raiz.find(f"{{{NS_NFSE}}}infDPS")
    if inf is None or not inf.get("Id"):
        raise nf.ErroNfse(XML_INVALIDO, "A DPS não tem infDPS com Id.")
    return raiz, inf


def _b64(dado: bytes) -> str:
    return base64.b64encode(dado).decode("ascii")


def _c14n(elemento) -> bytes:
    """C14N 1.0 inclusiva do elemento, com os namespaces herdados.

    NAO usa `tostring(elemento, method="c14n")` direto num subelemento: com o
    libxml2 2.11 (o do lxml 6.1 no Windows) a canonizacao de sub-arvore solta
    `xmlns=""` nos netos quando ha namespace padrao redeclarado, e o digest e
    a assinatura saem sobre bytes que nenhum verificador correto reproduz
    (E0714). Copiar o elemento para um documento proprio leva os namespaces
    em escopo para a raiz e usa a canonizacao de documento inteiro, que
    confere com o C14N da biblioteca padrao (teste test_nfse_assinatura)."""
    copia = copy.deepcopy(elemento)
    return etree.tostring(etree.ElementTree(copia), method="c14n", exclusive=False,
                          with_comments=False)


def _sub(pai, nome: str, texto: str | None = None, **atributos):
    elemento = etree.SubElement(pai, f"{{{DS}}}{nome}")
    for chave, valor in atributos.items():
        elemento.set(chave, valor)
    if texto is not None:
        elemento.text = texto
    return elemento


def assinar_dps(xml: bytes, certificado: CertificadoA1, *,
                algoritmo: str = ALGORITMO_PADRAO) -> bytes:
    if algoritmo not in ALGORITMOS:
        raise nf.ErroNfse(ALGORITMO_DESCONHECIDO,
                          f"Algoritmo de assinatura desconhecido: {algoritmo!r} "
                          f"(use {', '.join(ALGORITMOS)}).")
    metodo, metodo_digest, hash_cripto, hash_lib = ALGORITMOS[algoritmo]
    raiz, inf = _ler(xml)
    if raiz.find(f"{{{DS}}}Signature") is not None:
        raise nf.ErroNfse(DPS_JA_ASSINADA, "Esta DPS já está assinada.")

    digest = _b64(hash_lib(_c14n(inf)).digest())
    assinatura = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
    info = _sub(assinatura, "SignedInfo")
    _sub(info, "CanonicalizationMethod", Algorithm=C14N)
    _sub(info, "SignatureMethod", Algorithm=metodo)
    referencia = _sub(info, "Reference", URI="#" + inf.get("Id"))
    transforms = _sub(referencia, "Transforms")
    _sub(transforms, "Transform", Algorithm=ENVELOPED)
    _sub(transforms, "Transform", Algorithm=C14N)
    _sub(referencia, "DigestMethod", Algorithm=metodo_digest)
    _sub(referencia, "DigestValue", digest)

    valor = certificado.chave.sign(_c14n(info), padding.PKCS1v15(), hash_cripto())
    _sub(assinatura, "SignatureValue", _b64(valor))
    _sub(_sub(_sub(assinatura, "KeyInfo"), "X509Data"), "X509Certificate",
         _b64(certificado.certificado_der()))
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def conferir_assinatura(xml: bytes) -> dict:
    """Refaz digest e assinatura. Devolve algoritmo, CNPJ e impressao do
    certificado do KeyInfo; levanta ASSINATURA_INVALIDA/AUSENTE."""
    raiz, inf = _ler(xml)
    assinatura = raiz.find(f"{{{DS}}}Signature")
    if assinatura is None:
        raise nf.ErroNfse(ASSINATURA_AUSENTE, "A DPS não está assinada.")

    def _invalida(motivo: str) -> nf.ErroNfse:
        return nf.ErroNfse(ASSINATURA_INVALIDA, f"Assinatura inválida: {motivo}.")

    info = assinatura.find(f"{{{DS}}}SignedInfo")
    if info is None:
        raise _invalida("sem SignedInfo")
    canon = info.find(f"{{{DS}}}CanonicalizationMethod")
    metodo = info.find(f"{{{DS}}}SignatureMethod")
    referencias = info.findall(f"{{{DS}}}Reference")
    if canon is None or canon.get("Algorithm") != C14N:
        raise _invalida("canonicalização diferente de C14N 1.0")
    algoritmo = next((nome for nome, alg in ALGORITMOS.items()
                      if metodo is not None and alg[0] == metodo.get("Algorithm")), None)
    if algoritmo is None:
        raise _invalida("método de assinatura não suportado")
    if len(referencias) != 1 or referencias[0].get("URI") != "#" + inf.get("Id"):
        raise _invalida("a referência não aponta para o infDPS")
    referencia = referencias[0]
    transforms = [t.get("Algorithm") for t in referencia.iter(f"{{{DS}}}Transform")]
    if transforms != [ENVELOPED, C14N]:
        raise _invalida("transforms diferentes de enveloped + C14N")
    _, metodo_digest, hash_cripto, hash_lib = ALGORITMOS[algoritmo]
    digest_metodo = referencia.find(f"{{{DS}}}DigestMethod")
    digest_valor = referencia.find(f"{{{DS}}}DigestValue")
    if digest_metodo is None or digest_metodo.get("Algorithm") != metodo_digest:
        raise _invalida("método de digest incoerente com a assinatura")
    if digest_valor is None or (digest_valor.text or "").strip() != _b64(
            hash_lib(_c14n(inf)).digest()):
        raise _invalida("o conteúdo do infDPS mudou depois de assinado")

    texto_cert = assinatura.findtext(f"{{{DS}}}KeyInfo/{{{DS}}}X509Data/"
                                     f"{{{DS}}}X509Certificate")
    valor = assinatura.findtext(f"{{{DS}}}SignatureValue")
    try:
        der = base64.b64decode("".join((texto_cert or "").split()), validate=True)
        certificado = x509.load_der_x509_certificate(der)
        bruto = base64.b64decode("".join((valor or "").split()), validate=True)
    except (ValueError, TypeError):
        raise _invalida("certificado ou valor da assinatura ilegível") from None
    try:
        certificado.public_key().verify(bruto, _c14n(info), padding.PKCS1v15(),
                                        hash_cripto())
    except (InvalidSignature, TypeError, ValueError):
        raise _invalida("o valor não confere com o certificado") from None
    return {"algoritmo": algoritmo, "cnpj": cnpj_do_certificado(certificado),
            "impressao": hashlib.sha256(der).hexdigest()}
