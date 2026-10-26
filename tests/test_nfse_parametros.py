"""Perfil pelo certificado (spec 009): o que vem do proprio e-CNPJ e o que vem
da parametrizacao do ADN, contra o ADN FALSO (fixtures/nfse/sefin_falsa.py).

Confere: razao social do CN, codigo de servico com pontos, competencia ISO,
convenio ativo/inativo, aliquota vigente na competencia, retencao so como
aviso, destino travado no ADN (so GET), e que uma falha de consulta vira
aviso sem perder o que veio do certificado.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_certificado as nc  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_parametros as npar  # noqa: E402
from auditoria_fiscal.ferramentas import nfse_sefin as sf  # noqa: E402
from fixtures.nfse import certificados as cf  # noqa: E402
from fixtures.nfse.sefin_falsa import SefinFalsa  # noqa: E402

COMPETENCIA = dt.date(2026, 10, 1)


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
    # Do certificado, sem rede.
    ac = cf.gerar_ac()
    cert = nc.ler_pfx(cf.pfx(cf.gerar_ecnpj(ac), ac=ac), cf.SENHA)
    checar(cert.razao_social == "ESCOLA EXEMPLO LTDA", cert.razao_social)
    checar(nc.razao_social_do_titular("ACME LTDA") == "ACME LTDA",
           "CN sem o sufixo do CNPJ fica como esta")
    checar(nc.razao_social_do_titular("A:B LTDA:11222333000181") == "A:B LTDA",
           "so o ultimo ':CNPJ' sai")

    # Codigo de servico como o ADN exige.
    checar(npar.codigo_servico("080101") == "08.01.01.000", "codigo com pontos")
    checar(npar.codigo_servico("08.01.01") == "08.01.01.000", "aceita com pontos")
    checar(npar.codigo_servico("080101", "007") == "08.01.01.007", "complemento")
    for ruim in ("8101", "0801011", "abc", ""):
        checar(codigo_do_erro(npar.codigo_servico, ruim) == npar.CODIGO_SERVICO_INVALIDO,
               f"codigo invalido: {ruim!r}")

    # Destino: so o ADN (producao ou restrita) e loopback.
    checar(npar.URL_PARAMETROS_PRODUCAO == "https://adn.nfse.gov.br/parametrizacao",
           npar.URL_PARAMETROS_PRODUCAO)
    for url in ("https://sefin.nfse.gov.br/SefinNacional", "http://adn.nfse.gov.br/x",
                "https://adn.nfse.gov.br.exemplo.com/parametrizacao",
                "https://exemplo.com/parametrizacao"):
        checar(codigo_do_erro(npar.ClienteParametros, cert, url=url) == sf.DESTINO_PROIBIDO,
               f"destino deveria ser proibido: {url}")
    npar.ClienteParametros(cert)                                   # producao (sem conectar)
    npar.ClienteParametros(cert, url=npar.URL_PARAMETROS_RESTRITA)

    kit = cf.montar_kit(tempfile.mkdtemp(prefix="nfse_param_kit_"))
    falsa = SefinFalsa(kit)
    base = falsa.iniciar()
    try:
        cert = nc.ler_pfx(kit.pfx(), cf.SENHA)
        cliente = npar.ClienteParametros(cert, url=base + "/parametrizacao",
                                         ca_extra=kit.ca_pem, timeout=3)

        c = cliente.convenio("2927408")
        checar(c.resultado == npar.OK and c.dados["aderenteAmbienteNacional"] == 1, c)
        c = cliente.convenio("2611606")
        checar(c.resultado == npar.NAO_ENCONTRADO and "não está ativo" in c.mensagem, c)
        checar(codigo_do_erro(cliente.convenio, "29274") == npar.MUNICIPIO_INVALIDO,
               "municipio fora do formato")

        a = cliente.aliquota("2927408", "080101", COMPETENCIA)
        checar(a.resultado == npar.OK and str(a.dados["aliquota"]) == "5.00", a)
        checar(falsa.caminhos_parametros[-1]
               == "/parametrizacao/2927408/08.01.01.000/2026-10-01/aliquota",
               falsa.caminhos_parametros[-1])
        a = cliente.aliquota("2927408", "080101", dt.date(2021, 5, 1))
        checar(str(a.dados["aliquota"]) == "2.00", "aliquota da vigencia antiga")
        a = cliente.aliquota("2927408", "070201", COMPETENCIA)
        checar(a.resultado == npar.NAO_ENCONTRADO and a.dados is None, a)

        # Sugestao completa.
        s = npar.sugerir_perfil(cliente, cert, municipio="2927408",
                                c_trib_nacs=["080101"], competencia=COMPETENCIA)
        campos = s["campos"]
        checar(campos["cnpj"]["valor"] == "11.222.333/0001-81"
               and campos["cnpj"]["fonte"] == npar.FONTE_CERTIFICADO, campos["cnpj"])
        checar(campos["razao_social"]["valor"] == "ESCOLA EXEMPLO LTDA", campos)
        checar(campos["convenio_incidencia_ativo"]["valor"] is True
               and "ADN" in campos["convenio_incidencia_ativo"]["fonte"], campos)
        checar(campos["aliquota"]["valor"] == "5,00" and "08.01.01.000"
               in campos["aliquota"]["fonte"], campos["aliquota"])
        checar(s["ambiente"] == "teste local", s["ambiente"])
        checar(any("CNC" in m for m in s["manuais"]) and len(s["manuais"]) >= 6, s["manuais"])
        checar(not any("retenção" in a.lower() for a in s["avisos"]),
               f"080101 nao tem retencao no exemplo: {s['avisos']}")
        checar(set(s["certificado"]) == set(cert.resumo()), "resumo sem segredo")

        # Retencao do servico vira aviso (nao muda campo nenhum).
        falsa.aliquotas[("2927408", "07.02.01.000")] = [
            {"Incidencia": "SIM", "Aliq": 3.00, "DtIni": "2023-01-01T00:00:00", "DtFim": None}]
        s = npar.sugerir_perfil(cliente, cert, municipio="2927408",
                                c_trib_nacs=["080101", "070201"], competencia=COMPETENCIA)
        checar("aliquota" not in s["campos"], "aliquotas diferentes nao sao escolhidas")
        checar(any("08.01.01.000" in a and "07.02.01.000" in a for a in s["avisos"]),
               s["avisos"])
        checar(any("retenção" in a.lower() and "07.02.01.000" in a for a in s["avisos"]),
               s["avisos"])

        # Municipio sem convenio: sugere "nao", com o motivo.
        s = npar.sugerir_perfil(cliente, cert, municipio="2611606",
                                c_trib_nacs=["080101"], competencia=COMPETENCIA)
        checar(s["campos"]["convenio_incidencia_ativo"]["valor"] is False, s["campos"])
        checar(any("não está ativo" in a for a in s["avisos"]), s["avisos"])

        # ADN fora do ar: o que veio do certificado continua.
        falsa.parametros_fora_do_ar = True
        s = npar.sugerir_perfil(cliente, cert, municipio="2927408",
                                c_trib_nacs=["080101"], competencia=COMPETENCIA)
        checar(set(s["campos"]) == {"cnpj", "razao_social"}, s["campos"])
        checar(len(s["avisos"]) >= 2, s["avisos"])
        falsa.parametros_fora_do_ar = False

        # Servidor nao confiavel: avisos, nada quebra.
        sem_ca = npar.ClienteParametros(cert, url=base + "/parametrizacao", timeout=3)
        s = npar.sugerir_perfil(sem_ca, cert, municipio="2927408",
                                c_trib_nacs=["080101"], competencia=COMPETENCIA)
        checar(set(s["campos"]) == {"cnpj", "razao_social"} and s["avisos"], s)
    finally:
        falsa.parar()

    print("OK - perfil pelo certificado (CNPJ e razao social do e-CNPJ, convenio e "
          "aliquota do ADN, retencao como aviso, destino travado, falhas viram aviso) "
          "passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
