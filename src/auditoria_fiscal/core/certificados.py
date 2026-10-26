"""Leitura dos dados de um certificado digital (spec 012, US6/FR-012).

Le titular, documento, autoridade certificadora, validade e numero de serie
de um `.cer` (DER ou PEM, sem senha) ou de um `.pfx` (A1, com a senha). O
arquivo e a senha so passam por aqui: nada e' guardado, e o resultado nao
carrega a senha nem a chave privada.

Documento do titular no padrao ICP-Brasil: o CN costuma vir como
"NOME:CNPJ" (ou "NOME:CPF"); quando nao vem, o documento esta no
SubjectAltName, nos otherName 2.16.76.1.3.3 (CNPJ do e-CNPJ) e
2.16.76.1.3.1 (dados do titular do e-CPF: nascimento + CPF + ...). Sem
nenhum dos dois, o documento fica vazio — nunca e' deduzido do nome.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date

ARQUIVO_INVALIDO = "CERTIFICADO_INVALIDO"
SENHA_OBRIGATORIA = "CERTIFICADO_SENHA_OBRIGATORIA"
SENHA_INCORRETA = "CERTIFICADO_SENHA_INCORRETA"

MAX_BYTES = 256 * 1024
OID_CNPJ = "2.16.76.1.3.3"
OID_PESSOA_FISICA = "2.16.76.1.3.1"


class ErroCertificado(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class DadosCertificado:
    titular_nome: str
    titular_documento: str
    emissor: str
    inicio: date
    fim: date
    serie: str
    tipo: str            # "A1" quando veio de .pfx; "" quando nao da para saber
    hash_arquivo: str

    def como_dict(self) -> dict:
        d = asdict(self)
        d["inicio"] = self.inicio.isoformat()
        d["fim"] = self.fim.isoformat()
        return d


def _texto_der(valor: bytes) -> str:
    """Conteudo de um TLV DER simples (OCTET/Printable/UTF8 String)."""
    if len(valor) >= 2 and valor[0] in (0x04, 0x0C, 0x13, 0x16):
        tamanho = valor[1]
        inicio = 2
        if tamanho & 0x80:
            bytes_tamanho = tamanho & 0x7F
            tamanho = int.from_bytes(valor[2:2 + bytes_tamanho], "big")
            inicio = 2 + bytes_tamanho
        valor = valor[inicio:inicio + tamanho]
    return valor.decode("latin-1", errors="ignore")


def _documento_alternativo(cert) -> str:
    from cryptography import x509

    try:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return ""
    for nome in (n for n in san if isinstance(n, x509.OtherName)):
        digitos = re.sub(r"\D", "", _texto_der(nome.value))
        if nome.type_id.dotted_string == OID_CNPJ and len(digitos) >= 14:
            return digitos[:14]
        if nome.type_id.dotted_string == OID_PESSOA_FISICA and len(digitos) >= 19:
            return digitos[8:19]
    return ""


def _nome_comum(nome) -> str:
    from cryptography.x509.oid import NameOID

    atributos = nome.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(atributos[0].value).strip() if atributos else ""


def _carregar(conteudo: bytes, senha: str | None):
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import pkcs12

    for carregar in (x509.load_der_x509_certificate,
                     x509.load_pem_x509_certificate):
        try:
            return carregar(conteudo), ""
        except ValueError:
            continue
    # Nao e' .cer: so pode ser .pfx, que exige a senha.
    if senha is None:
        try:
            pkcs12.load_key_and_certificates(conteudo, None)
        except ValueError:
            # Sem senha nao abre: ou e' .pfx protegido ou e' lixo. Um .pfx
            # comeca por SEQUENCE DER; lixo nao.
            if conteudo[:1] == b"\x30":
                raise ErroCertificado(
                    SENHA_OBRIGATORIA,
                    "Este arquivo é um certificado A1 (.pfx): informe a senha "
                    "para ler a validade.") from None
            raise ErroCertificado(
                ARQUIVO_INVALIDO,
                "O arquivo não é um certificado (.cer, .crt ou .pfx).") from None
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(
            conteudo, (senha or "").encode("utf-8"))
    except ValueError as exc:
        if conteudo[:1] == b"\x30":
            raise ErroCertificado(
                SENHA_INCORRETA,
                "A senha não abre este certificado.") from exc
        raise ErroCertificado(
            ARQUIVO_INVALIDO,
            "O arquivo não é um certificado (.cer, .crt ou .pfx).") from exc
    if cert is None:
        raise ErroCertificado(ARQUIVO_INVALIDO,
                              "O .pfx não traz certificado.")
    return cert, "A1"


def ler_certificado(conteudo: bytes, *, senha: str | None = None
                    ) -> DadosCertificado:
    if not conteudo or len(conteudo) > MAX_BYTES:
        raise ErroCertificado(
            ARQUIVO_INVALIDO,
            "Arquivo vazio ou grande demais para ser um certificado.")
    cert, tipo = _carregar(conteudo, senha)

    cn = _nome_comum(cert.subject)
    nome, documento = cn, ""
    if ":" in cn:
        antes, _, depois = cn.rpartition(":")
        digitos = re.sub(r"\D", "", depois)
        if len(digitos) in (11, 14):
            nome, documento = antes.strip(), digitos
    if not documento:
        documento = _documento_alternativo(cert)

    return DadosCertificado(
        titular_nome=nome[:160], titular_documento=documento,
        emissor=_nome_comum(cert.issuer)[:160],
        inicio=cert.not_valid_before_utc.date(),
        fim=cert.not_valid_after_utc.date(),
        serie=format(cert.serial_number, "X"), tipo=tipo,
        hash_arquivo=hashlib.sha256(conteudo).hexdigest())
