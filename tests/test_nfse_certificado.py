"""Certificado A1 da Fase 2 (spec 008, FR-202/FR-203): leitura do .pfx e
conferencia antes de qualquer conexao.

Os certificados sao gerados na hora (fixtures/nfse/certificados.py).
"""

from __future__ import annotations

import datetime as dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_certificado as nc  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402

AGORA = dt.datetime.now(dt.timezone.utc)


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


def main() -> int:
    ac = cf.gerar_ac()
    bom = cf.gerar_ecnpj(ac)

    # Leitura.
    cert = nc.ler_pfx(cf.pfx(bom, ac=ac), cf.SENHA)
    checar(cert.cnpj == cf.CNPJ, f"CNPJ do OtherName: {cert.cnpj!r}")
    checar("ESCOLA EXEMPLO" in cert.titular, cert.titular)
    checar(len(cert.impressao) == 64, cert.impressao)
    checar(len(cert.cadeia) == 1, "a AC do .pfx vem na cadeia")
    resumo = cert.resumo()
    checar(set(resumo) == {"cnpj", "titular", "emissor", "valido_de", "valido_ate",
                           "impressao"}, resumo)
    checar("chave" not in repr(cert).lower() or "oculta" in repr(cert).lower(),
           f"repr nao pode expor a chave: {repr(cert)}")
    checar(cf.SENHA not in repr(cert) and cf.SENHA not in str(resumo),
           "a senha nao aparece em lugar nenhum")

    # PrintableString no lugar de OCTET STRING: o CNPJ sai igual.
    impresso = cf.gerar_ecnpj(ac, tag_cnpj=0x13)
    checar(nc.ler_pfx(cf.pfx(impresso), cf.SENHA).cnpj == cf.CNPJ,
           "CNPJ em PrintableString")

    # Arquivo e senha.
    checar(codigo_do_erro(nc.ler_pfx, cf.pfx(bom), "senha-errada")
           == nc.CERTIFICADO_ILEGIVEL, "senha errada")
    checar(codigo_do_erro(nc.ler_pfx, b"isto nao e um pfx", cf.SENHA)
           == nc.CERTIFICADO_ILEGIVEL, "arquivo que nao e PKCS#12")
    checar(codigo_do_erro(nc.ler_pfx, b"", cf.SENHA) == nc.CERTIFICADO_ILEGIVEL,
           "arquivo vazio")
    checar(codigo_do_erro(nc.ler_pfx, b"0" * (nc.MAX_PFX_BYTES + 1), cf.SENHA)
           == nc.CERTIFICADO_GRANDE_DEMAIS, "arquivo grande demais")
    checar(codigo_do_erro(nc.ler_pfx, cf.pfx_sem_chave(bom), cf.SENHA)
           == nc.CERTIFICADO_SEM_CHAVE, "pfx sem chave privada")

    # Conferencia para emitir.
    nc.conferir_para_emissao(cert, cf.CNPJ, AGORA)
    nc.conferir_para_emissao(cert, "11.222.333/0001-81", AGORA)   # formatado
    checar(codigo_do_erro(nc.conferir_para_emissao, cert, cf.OUTRO_CNPJ, AGORA)
           == nc.CERTIFICADO_DE_OUTRO_CNPJ, "certificado de outro CNPJ (E0718)")

    vencido = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(
        ac, de=AGORA - dt.timedelta(days=400), ate=AGORA - dt.timedelta(days=1))),
        cf.SENHA)
    checar(codigo_do_erro(nc.conferir_para_emissao, vencido, cf.CNPJ, AGORA)
           == nc.CERTIFICADO_VENCIDO, "vencido (E1203)")
    futuro = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(
        ac, de=AGORA + dt.timedelta(days=2), ate=AGORA + dt.timedelta(days=30))),
        cf.SENHA)
    checar(codigo_do_erro(nc.conferir_para_emissao, futuro, cf.CNPJ, AGORA)
           == nc.CERTIFICADO_AINDA_NAO_VALIDO, "ainda nao valido")
    de_ac = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(ac, eh_ac=True)), cf.SENHA)
    checar(codigo_do_erro(nc.conferir_para_emissao, de_ac, cf.CNPJ, AGORA)
           == nc.CERTIFICADO_DE_AC, "certificado de AC (E0716)")
    sem_cnpj = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(ac, cnpj=None)), cf.SENHA)
    checar(sem_cnpj.cnpj is None, "sem a extensao do CNPJ")
    checar(codigo_do_erro(nc.conferir_para_emissao, sem_cnpj, cf.CNPJ, AGORA)
           == nc.CERTIFICADO_SEM_CNPJ, "sem CNPJ (E1209)")
    sem_assinatura = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(ac, assinatura=False)),
                                cf.SENHA)
    checar(codigo_do_erro(nc.conferir_para_emissao, sem_assinatura, cf.CNPJ, AGORA)
           == nc.CERTIFICADO_SEM_USO_ASSINATURA, "KeyUsage sem assinatura (E0716)")

    print("OK - certificado A1 (leitura do .pfx, CNPJ do OtherName, senha errada, "
          "sem chave, vencido, de AC, de outro CNPJ, KeyUsage) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
