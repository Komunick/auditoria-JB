"""Certificados de TESTE da Fase 2, gerados na hora (spec 008).

Nenhuma chave privada vai para o Git: cada execucao cria uma AC de mentira,
o certificado do servidor (127.0.0.1) e o e-CNPJ do prestador ficticio, no
formato da ICP-Brasil que importa aqui (OtherName 2.16.76.1.3.3 com o CNPJ,
KeyUsage de assinatura, uso estendido de autenticacao de cliente). A cadeia
NAO e' da ICP-Brasil: a conferencia de cadeia e' da Sefin, nao nossa.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")
CNPJ = "11222333000181"          # o mesmo do perfil ficticio (fixtures.nfse)
OUTRO_CNPJ = "11444777000161"
SENHA = "senha-de-teste"

_AGORA = dt.datetime.now(dt.timezone.utc)


def _chave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _nome(texto: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
                      x509.NameAttribute(NameOID.COMMON_NAME, texto)])


def der_string(texto: str, tag: int = 0x04) -> bytes:
    """DER de uma string curta: 0x04 OCTET STRING, 0x13 PrintableString."""
    dado = texto.encode("ascii")
    return bytes([tag, len(dado)]) + dado


@dataclass
class Par:
    certificado: x509.Certificate
    chave: object


def gerar_ac(nome: str = "AC Teste NFS-e") -> Par:
    chave = _chave()
    certificado = (
        x509.CertificateBuilder()
        .subject_name(_nome(nome)).issuer_name(_nome(nome))
        .public_key(chave.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(_AGORA - dt.timedelta(days=1))
        .not_valid_after(_AGORA + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .sign(chave, hashes.SHA256()))
    return Par(certificado, chave)


def gerar_servidor(ac: Par) -> Par:
    chave = _chave()
    certificado = (
        x509.CertificateBuilder()
        .subject_name(_nome("127.0.0.1")).issuer_name(ac.certificado.subject)
        .public_key(chave.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(_AGORA - dt.timedelta(days=1))
        .not_valid_after(_AGORA + dt.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                       critical=False)
        .sign(ac.chave, hashes.SHA256()))
    return Par(certificado, chave)


def gerar_ecnpj(ac: Par, cnpj: str | None = CNPJ, *, de: dt.datetime | None = None,
                ate: dt.datetime | None = None, eh_ac: bool = False,
                assinatura: bool = True, tag_cnpj: int = 0x04) -> Par:
    """e-CNPJ A1 de teste. `cnpj=None` = sem a extensao do CNPJ."""
    chave = _chave()
    titular = f"ESCOLA EXEMPLO LTDA:{cnpj or 'SEMCNPJ'}"
    construtor = (
        x509.CertificateBuilder()
        .subject_name(_nome(titular)).issuer_name(ac.certificado.subject)
        .public_key(chave.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(de or _AGORA - dt.timedelta(days=1))
        .not_valid_after(ate or _AGORA + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=eh_ac, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=assinatura, content_commitment=assinatura,
            key_encipherment=True, data_encipherment=False, key_agreement=False,
            key_cert_sign=eh_ac, crl_sign=False, encipher_only=False,
            decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH,
                                              ExtendedKeyUsageOID.EMAIL_PROTECTION]),
                       critical=False))
    if cnpj:
        construtor = construtor.add_extension(x509.SubjectAlternativeName([
            x509.OtherName(OID_CNPJ, der_string(cnpj, tag_cnpj))]), critical=False)
    return Par(construtor.sign(ac.chave, hashes.SHA256()), chave)


def pfx(par: Par, senha: str = SENHA, ac: Par | None = None) -> bytes:
    return pkcs12.serialize_key_and_certificates(
        b"teste", par.chave, par.certificado,
        [ac.certificado] if ac else None,
        serialization.BestAvailableEncryption(senha.encode()))


def pfx_sem_chave(par: Par, senha: str = SENHA) -> bytes:
    return pkcs12.serialize_key_and_certificates(
        b"teste", None, par.certificado, None,
        serialization.BestAvailableEncryption(senha.encode()))


def pem(certificado: x509.Certificate) -> bytes:
    return certificado.public_bytes(serialization.Encoding.PEM)


@dataclass
class Kit:
    """AC + servidor + e-CNPJ, com os arquivos que o servidor TLS precisa."""
    ac: Par
    servidor: Par
    ecnpj: Par
    pasta: str

    @property
    def ca_pem(self) -> str:
        return os.path.join(self.pasta, "ac.pem")

    @property
    def servidor_pem(self) -> str:
        return os.path.join(self.pasta, "servidor.pem")

    @property
    def servidor_chave(self) -> str:
        return os.path.join(self.pasta, "servidor.key")

    def pfx(self, senha: str = SENHA) -> bytes:
        return pfx(self.ecnpj, senha, self.ac)


def montar_kit(pasta: str) -> Kit:
    ac = gerar_ac()
    servidor = gerar_servidor(ac)
    kit = Kit(ac=ac, servidor=servidor, ecnpj=gerar_ecnpj(ac), pasta=pasta)
    os.makedirs(pasta, exist_ok=True)
    with open(kit.ca_pem, "wb") as arq:
        arq.write(pem(ac.certificado))
    with open(kit.servidor_pem, "wb") as arq:
        arq.write(pem(servidor.certificado))
    with open(kit.servidor_chave, "wb") as arq:
        arq.write(servidor.chave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    return kit
