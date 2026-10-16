"""Certificado A1 do prestador para a Fase 2 da NFS-e (spec 008).

Le o .pfx (PKCS#12) em memoria e confere, antes de qualquer conexao, o que o
Sistema Nacional rejeitaria (Anexo I, RN DPS_NFS-e E0715 a E0718 e
RN_RECEPCAO_DPS E1200 a E1209): validade, certificado de AC, uso para
assinatura e o CNPJ do emitente na extensao da ICP-Brasil.

A cadeia ate a raiz ICP-Brasil e a lista de revogacao sao conferidas pela
Sefin; aqui nao ha copia da cadeia oficial para isso.

O certificado nunca e' gravado por este modulo, e o objeto nao mostra a chave
em `repr` (mensagem de erro de job e log nao a vazam).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from . import nfse as nf

OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")
MAX_PFX_BYTES = 50 * 1024

CERTIFICADO_ILEGIVEL = "CERTIFICADO_ILEGIVEL"
CERTIFICADO_GRANDE_DEMAIS = "CERTIFICADO_GRANDE_DEMAIS"
CERTIFICADO_SEM_CHAVE = "CERTIFICADO_SEM_CHAVE"
CERTIFICADO_VENCIDO = "CERTIFICADO_VENCIDO"
CERTIFICADO_AINDA_NAO_VALIDO = "CERTIFICADO_AINDA_NAO_VALIDO"
CERTIFICADO_DE_AC = "CERTIFICADO_DE_AC"
CERTIFICADO_SEM_CNPJ = "CERTIFICADO_SEM_CNPJ"
CERTIFICADO_DE_OUTRO_CNPJ = "CERTIFICADO_DE_OUTRO_CNPJ"
CERTIFICADO_SEM_USO_ASSINATURA = "CERTIFICADO_SEM_USO_ASSINATURA"


@dataclass(frozen=True)
class CertificadoA1:
    certificado: x509.Certificate
    cadeia: tuple
    cnpj: str | None
    titular: str
    emissor: str
    valido_de: dt.datetime
    valido_ate: dt.datetime
    impressao: str
    chave: object = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return (f"CertificadoA1(cnpj={self.cnpj!r}, titular={self.titular!r}, "
                f"impressao={self.impressao[:16]}..., chave=<oculta>)")

    @property
    def razao_social(self) -> str:
        return razao_social_do_titular(self.titular)

    def resumo(self) -> dict:
        """O que pode ir para banco, trilha e tela: nada secreto."""
        return {"cnpj": self.cnpj, "titular": self.titular, "emissor": self.emissor,
                "valido_de": self.valido_de.isoformat(timespec="seconds"),
                "valido_ate": self.valido_ate.isoformat(timespec="seconds"),
                "impressao": self.impressao}

    def certificado_der(self) -> bytes:
        return self.certificado.public_bytes(serialization.Encoding.DER)


def _texto_der(valor: bytes) -> str:
    """Conteudo de uma string DER curta (OCTET/Printable/UTF8/IA5), com ou sem
    o invólucro [0] EXPLICIT que algumas bibliotecas mantem."""
    dado = bytes(valor or b"")
    for _ in range(2):
        if len(dado) < 2:
            return ""
        tag, tamanho = dado[0], dado[1]
        inicio = 2
        if tamanho & 0x80:
            n = tamanho & 0x7F
            tamanho = int.from_bytes(dado[2:2 + n], "big")
            inicio = 2 + n
        conteudo = dado[inicio:inicio + tamanho]
        if tag == 0xA0:              # [0] EXPLICIT: desce um nivel
            dado = conteudo
            continue
        return conteudo.decode("latin-1", errors="replace")
    return ""


def cnpj_do_certificado(certificado: x509.Certificate) -> str | None:
    """CNPJ da extensao OtherName 2.16.76.1.3.3 (padrao ICP-Brasil)."""
    try:
        san = certificado.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return None
    for nome in san.get_values_for_type(x509.OtherName):
        if nome.type_id == OID_CNPJ:
            digitos = re.sub(r"\D", "", _texto_der(nome.value))
            if len(digitos) >= 14:
                return digitos[:14]
    return None


def razao_social_do_titular(titular: str) -> str:
    """No e-CNPJ da ICP-Brasil o CN e' `NOME EMPRESARIAL:CNPJ`; tira o sufixo
    do CNPJ (so o ultimo, o nome pode ter dois-pontos)."""
    titular = (titular or "").strip()
    nome, separador, fim = titular.rpartition(":")
    if separador and re.fullmatch(r"\d{14}", fim.strip()):
        return nome.strip()
    return titular


def _nome_comum(nome: x509.Name) -> str:
    atributos = nome.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return str(atributos[0].value) if atributos else nome.rfc4514_string()


def ler_pfx(dados: bytes, senha: str) -> CertificadoA1:
    """Abre o .pfx em memoria. Senha errada e arquivo invalido dao o mesmo
    erro: a biblioteca nao os distingue, e o usuario resolve do mesmo jeito."""
    dados = bytes(dados or b"")
    if len(dados) > MAX_PFX_BYTES:
        raise nf.ErroNfse(CERTIFICADO_GRANDE_DEMAIS,
                          f"O certificado tem mais de {MAX_PFX_BYTES // 1024} KB; "
                          "um .pfx de A1 costuma ter de 3 a 10 KB.")
    try:
        chave, certificado, cadeia = pkcs12.load_key_and_certificates(
            dados, (senha or "").encode("utf-8"))
    except (ValueError, TypeError):
        raise nf.ErroNfse(CERTIFICADO_ILEGIVEL,
                          "Não foi possível abrir o certificado: senha errada ou "
                          "arquivo que não é .pfx/.p12.") from None
    if chave is None or certificado is None:
        raise nf.ErroNfse(CERTIFICADO_SEM_CHAVE,
                          "O arquivo não traz a chave privada do certificado "
                          "(exporte o A1 com a chave).")
    der = certificado.public_bytes(serialization.Encoding.DER)
    return CertificadoA1(
        certificado=certificado, cadeia=tuple(cadeia or ()),
        cnpj=cnpj_do_certificado(certificado),
        titular=_nome_comum(certificado.subject),
        emissor=_nome_comum(certificado.issuer),
        valido_de=certificado.not_valid_before_utc,
        valido_ate=certificado.not_valid_after_utc,
        impressao=hashlib.sha256(der).hexdigest(), chave=chave)


def conferir_para_emissao(cert: CertificadoA1, cnpj_prestador: str,
                          agora: dt.datetime) -> None:
    """Levanta ErroNfse com o primeiro motivo pelo qual a Sefin recusaria."""
    if agora.tzinfo is None:
        raise ValueError("`agora` precisa de fuso.")
    if agora < cert.valido_de:
        raise nf.ErroNfse(CERTIFICADO_AINDA_NAO_VALIDO,
                          f"O certificado só vale a partir de "
                          f"{cert.valido_de:%d/%m/%Y}.")
    if agora > cert.valido_ate:
        raise nf.ErroNfse(CERTIFICADO_VENCIDO,
                          f"O certificado venceu em {cert.valido_ate:%d/%m/%Y} (E1203).")
    try:
        basico = cert.certificado.extensions.get_extension_for_class(
            x509.BasicConstraints).value
        if basico.ca:
            raise nf.ErroNfse(CERTIFICADO_DE_AC,
                              "Este é um certificado de autoridade certificadora, "
                              "não de empresa (E0716).")
    except x509.ExtensionNotFound:
        pass
    try:
        uso = cert.certificado.extensions.get_extension_for_class(x509.KeyUsage).value
        if not (uso.digital_signature and uso.content_commitment):
            raise nf.ErroNfse(CERTIFICADO_SEM_USO_ASSINATURA,
                              "O certificado não permite assinatura digital com não "
                              "repúdio (E0716).")
    except x509.ExtensionNotFound:
        pass
    if not cert.cnpj:
        raise nf.ErroNfse(CERTIFICADO_SEM_CNPJ,
                          "O certificado não traz CNPJ (e-CNPJ da ICP-Brasil) (E1209).")
    esperado = re.sub(r"\D", "", cnpj_prestador or "")
    if cert.cnpj != esperado:
        raise nf.ErroNfse(CERTIFICADO_DE_OUTRO_CNPJ,
                          f"O certificado é do CNPJ {cert.cnpj}, e o perfil é do "
                          f"{esperado}: a DPS tem de ser assinada pelo emitente (E0718).")
