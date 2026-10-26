"""Leitura de certificado digital (spec 012, US6/FR-012).

Certificados SINTETICOS gerados aqui, no formato ICP-Brasil: titular no CN
como "NOME:CNPJ" ou so no otherName 2.16.76.1.3.3 (e-CNPJ) / 2.16.76.1.3.1
(e-CPF). Cobre .cer DER e PEM, .pfx com senha, senha errada e lixo.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from auditoria_fiscal.core import certificados as ct  # noqa: E402
from auditoria_fiscal.core.documentos_br import dv_cnpj  # noqa: E402

CNPJ = "012345670001" + dv_cnpj("012345670001")
CPF = "52998224725"


def certificado(cn: str, *, outros: list | None = None,
                inicio=datetime(2026, 1, 10, tzinfo=timezone.utc),
                dias: int = 365, serie: int = 0xABC123):
    chave = ec.generate_private_key(ec.SECP256R1())
    construtor = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "AC SINTETICA RFB v5")]))
        .public_key(chave.public_key())
        .serial_number(serie)
        .not_valid_before(inicio)
        .not_valid_after(inicio + timedelta(days=dias)))
    if outros:
        construtor = construtor.add_extension(
            x509.SubjectAlternativeName(outros), critical=False)
    return chave, construtor.sign(chave, hashes.SHA256())


def other_name(oid: str, texto: str, tag: int = 0x04):
    conteudo = texto.encode("ascii")
    return x509.OtherName(x509.ObjectIdentifier(oid),
                          bytes([tag, len(conteudo)]) + conteudo)


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def codigo_de(funcao, *args, **kwargs) -> str:
    try:
        funcao(*args, **kwargs)
    except ct.ErroCertificado as exc:
        return exc.codigo
    return ""


def main() -> int:
    chave, cert = certificado(f"EMPRESA SINTETICA LTDA:{CNPJ}")
    der = cert.public_bytes(serialization.Encoding.DER)
    pem = cert.public_bytes(serialization.Encoding.PEM)
    pfx = pkcs12.serialize_key_and_certificates(
        b"sintetico", chave, cert, None,
        serialization.BestAvailableEncryption(b"senha-sintetica"))

    # ------------------------------------------------------------------
    # .cer DER e PEM (sem senha) e .pfx (com senha) dao o mesmo resultado

    for nome, conteudo, senha in (("der", der, None), ("pem", pem, None),
                                  ("pfx", pfx, "senha-sintetica")):
        dados = ct.ler_certificado(conteudo, senha=senha)
        checar(dados.titular_documento == CNPJ, f"{nome}: {dados.titular_documento}")
        checar(dados.titular_nome == "EMPRESA SINTETICA LTDA", dados.titular_nome)
        checar(dados.emissor == "AC SINTETICA RFB v5", dados.emissor)
        checar(dados.inicio == date(2026, 1, 10), dados.inicio)
        checar(dados.fim == date(2027, 1, 10), dados.fim)
        checar(dados.serie == "ABC123", dados.serie)
        checar(dados.tipo == "A1" if nome == "pfx" else dados.tipo == "",
               f"{nome}: .pfx e' A1; .cer nao diz o tipo ({dados.tipo})")
        checar(len(dados.hash_arquivo) == 64, "hash do arquivo")

    # A senha do .pfx nao sobra em lugar nenhum do resultado.
    dados = ct.ler_certificado(pfx, senha="senha-sintetica")
    checar("senha-sintetica" not in repr(dados) and
           "senha-sintetica" not in str(dados.como_dict()),
           "a senha nao pode aparecer no resultado")

    # ------------------------------------------------------------------
    # Erros claros

    checar(codigo_de(ct.ler_certificado, pfx, senha="errada")
           == ct.SENHA_INCORRETA, "senha errada")
    checar(codigo_de(ct.ler_certificado, pfx) == ct.SENHA_OBRIGATORIA,
           ".pfx sem senha")
    checar(codigo_de(ct.ler_certificado, b"lixo qualquer")
           == ct.ARQUIVO_INVALIDO, "lixo")
    checar(codigo_de(ct.ler_certificado, b"") == ct.ARQUIVO_INVALIDO, "vazio")
    checar(codigo_de(ct.ler_certificado, b"0" * (ct.MAX_BYTES + 1))
           == ct.ARQUIVO_INVALIDO, "grande demais")

    # ------------------------------------------------------------------
    # Documento so no otherName (ICP-Brasil), CN sem ":"

    _, so_oid = certificado("EMPRESA DOIS LTDA", outros=[
        other_name(ct.OID_CNPJ, CNPJ)])
    dados = ct.ler_certificado(so_oid.public_bytes(serialization.Encoding.DER))
    checar(dados.titular_documento == CNPJ, f"otherName e-CNPJ: {dados}")
    checar(dados.titular_nome == "EMPRESA DOIS LTDA", dados.titular_nome)

    _, ecpf = certificado("FULANA SINTETICA", outros=[
        other_name(ct.OID_PESSOA_FISICA, "01011980" + CPF + "00000000000",
                   tag=0x13)])
    dados = ct.ler_certificado(ecpf.public_bytes(serialization.Encoding.DER))
    checar(dados.titular_documento == CPF, f"e-CPF pelo otherName: {dados}")

    _, sem_doc = certificado("SEM DOCUMENTO")
    dados = ct.ler_certificado(sem_doc.public_bytes(serialization.Encoding.DER))
    checar(dados.titular_documento == "", "sem documento nao e' inventado")

    print("OK - certificados (.cer DER/PEM, .pfx com senha, CN e otherName "
          "ICP-Brasil, e-CPF, senha errada, lixo, senha fora do resultado) "
          "passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
