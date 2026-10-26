"""Cliente da Sefin Nacional (spec 008, FR-201/202/205/208/209).

Fala com a Sefin FALSA (fixtures/nfse/sefin_falsa.py): HTTPS em 127.0.0.1 que
exige o e-CNPJ de teste no mTLS. Confere destino permitido, ambiente, corpo
gzip+Base64, cada tipo de resposta (201, 400, 403, 500, tempo esgotado), as
consultas, a verificacao do servidor e que a chave nao fica em disco.
"""

from __future__ import annotations

import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_assinatura as na  # noqa: E402
from auditoria_fiscal.core import nfse_certificado as nc  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_sefin as sf  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402
from fixtures.nfse import dps as fd  # noqa: E402
from fixtures.nfse.sefin_falsa import SefinFalsa  # noqa: E402


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


def pastas_tls() -> set[str]:
    base = tempfile.gettempdir()
    return {n for n in os.listdir(base) if n.startswith("nfse_tls_")}


def main() -> int:
    pasta = tempfile.mkdtemp(prefix="nfse_sefin_teste_")
    kit = cf.montar_kit(pasta)
    falsa = SefinFalsa(kit, atraso=2.5)
    base = falsa.iniciar()
    try:
        cert = nc.ler_pfx(kit.pfx(), cf.SENHA)

        # Destinos: so producao restrita (ou loopback, para estes testes).
        for url in ("https://sefin.nfse.gov.br/SefinNacional",
                    "http://127.0.0.1:9/SefinNacional",
                    "https://sefin.producaorestrita.nfse.gov.br.exemplo.com/x",
                    "https://exemplo.com/SefinNacional"):
            checar(codigo_do_erro(sf.ClienteSefin, cert, url_sefin=url,
                                  url_adn=sf.URL_ADN_RESTRITA) == sf.DESTINO_PROIBIDO,
                   f"destino deveria ser proibido: {url}")
        checar(codigo_do_erro(sf.ClienteSefin, cert, url_sefin=sf.URL_SEFIN_RESTRITA,
                              url_adn="https://adn.nfse.gov.br") == sf.DESTINO_PROIBIDO,
               "ADN de producao tambem e' proibido")
        antes = pastas_tls()
        sf.ClienteSefin(cert)           # padrao = producao restrita (sem conectar)
        checar(pastas_tls() == antes, "a chave em PEM temporario precisa sumir")

        cliente = sf.ClienteSefin(cert, url_sefin=base + "/SefinNacional", url_adn=base,
                                  ca_extra=kit.ca_pem, timeout=1.5)
        checar(cliente.destino == "127.0.0.1", cliente.destino)

        # Ambiente de producao nunca sai daqui.
        producao = na.assinar_dps(fd.xml_dps(9, tp_amb=1), cert)
        checar(codigo_do_erro(cliente.enviar, producao) == sf.AMBIENTE_PROIBIDO,
               "tpAmb=1 e' recusado antes de conectar")
        checar(falsa.posts == [], "nada foi enviado")

        # 201.
        r = cliente.enviar(na.assinar_dps(fd.xml_dps(1), cert))
        checar(r.resultado == sf.AUTORIZADA and r.http_status == 201, r)
        checar(r.chave_acesso and len(r.chave_acesso) == 50, r.chave_acesso)
        checar(r.nfse_xml.startswith(b"<?xml") and b"<NFSe" in r.nfse_xml, r.nfse_xml[:80])
        checar(r.versao_aplicativo == "SefinFalsa-1", r.versao_aplicativo)
        checar(falsa.cnpjs_conexao[-1] == cf.CNPJ, "o mTLS apresentou o e-CNPJ")
        chave1 = r.chave_acesso

        # 400 (E0014 = ja existe) — o cliente so relata.
        r = cliente.enviar(na.assinar_dps(fd.xml_dps(1), cert))
        checar(r.resultado == sf.REJEITADA and r.duplicada, r)
        checar(r.erros[0]["codigo"] == "E0014" and r.erros[0]["descricao"], r.erros)

        falsa.programar(("400", "E0312", "Código de tributação nacional inexistente."))
        r = cliente.enviar(na.assinar_dps(fd.xml_dps(2), cert))
        checar(r.resultado == sf.REJEITADA and not r.duplicada
               and r.erros == [{"codigo": "E0312", "descricao":
                                "Código de tributação nacional inexistente.",
                                "complemento": ""}], r.erros)

        falsa.programar("403")
        r = cliente.enviar(na.assinar_dps(fd.xml_dps(2), cert))
        checar(r.resultado == sf.CERTIFICADO_RECUSADO and r.http_status == 403, r)

        falsa.programar("500")
        r = cliente.enviar(na.assinar_dps(fd.xml_dps(2), cert))
        checar(r.resultado == sf.INCERTA and r.http_status == 500, r)

        falsa.programar("emitir_e_demorar")
        r = cliente.enviar(na.assinar_dps(fd.xml_dps(3), cert))
        checar(r.resultado == sf.INCERTA and r.http_status is None
               and "tempo" in r.mensagem.lower(), r)

        # Consultas.
        c = cliente.consultar_dps(fd.id_dps(3))
        checar(c.resultado == sf.EXISTE and c.chave_acesso, c)
        c = cliente.consultar_dps(fd.id_dps(2))
        checar(c.resultado == sf.NAO_EXISTE and c.chave_acesso is None, c)
        checar(codigo_do_erro(cliente.consultar_dps, "DPS../../etc") == sf.ID_INVALIDO,
               "id de DPS fora do formato nao vira caminho")
        n = cliente.baixar_nfse(chave1)
        checar(n.resultado == sf.EXISTE and n.xml.startswith(b"<?xml"), n)
        checar(cliente.baixar_nfse("0" * 50).resultado == sf.NAO_EXISTE, "chave inexistente")
        checar(cliente.baixar_danfse(chave1).startswith(b"%PDF"), "DANFSe")
        falsa.danfse_disponivel = False
        checar(cliente.baixar_danfse(chave1) is None, "DANFSe fora do ar = None")

        # Servidor nao confiavel: nada e' enviado.
        sem_ca = sf.ClienteSefin(cert, url_sefin=base + "/SefinNacional", url_adn=base,
                                 timeout=1.5)
        quantos = len(falsa.posts)
        r = sem_ca.enviar(na.assinar_dps(fd.xml_dps(4), cert))
        checar(r.resultado == sf.SEM_CONEXAO and r.http_status is None, r)
        checar(len(falsa.posts) == quantos, "sem TLS confiavel, nada chega a Sefin")

        # Certificado de outra AC: a Sefin derruba o TLS; nada e' processado.
        estranho = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(cf.gerar_ac("AC Estranha"))),
                              cf.SENHA)
        outro = sf.ClienteSefin(estranho, url_sefin=base + "/SefinNacional",
                                url_adn=base, ca_extra=kit.ca_pem, timeout=1.5)
        r = outro.enviar(na.assinar_dps(fd.xml_dps(5), estranho))
        checar(r.resultado in (sf.SEM_CONEXAO, sf.INCERTA), r)
        checar(len(falsa.posts) == quantos, "mTLS recusado nao processa nada")

        checar(pastas_tls() == antes, "nenhuma pasta de PEM temporario ficou para tras")
    finally:
        falsa.parar()

    print("OK - cliente da Sefin (destino e ambiente travados, mTLS, gzip/Base64, "
          "201/400/403/500/tempo esgotado, consultas, DANFSe, TLS nao confiavel) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
