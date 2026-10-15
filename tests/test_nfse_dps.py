"""Gerador da DPS do padrao nacional (spec 006, historia 7), sem envio.

O XML de referencia foi escrito a mao a partir do Anexo I v1.01 e do XSD
(research.md), nao copiado da saida do gerador: e' o teste que diz se o
mapeamento linha -> DPS esta certo. Toda DPS e' validada no XSD oficial
versionado em dados/nfse/xsd/v1.01, sem rede.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_conferencia as nc  # noqa: E402
from auditoria_fiscal.core import nfse_dps as nd  # noqa: E402
from fixtures import nfse as fx  # noqa: E402

QUANDO = dt.datetime(2026, 11, 15, 10, 30, 0, tzinfo=nd.FUSO_SALVADOR)
HOJE = QUANDO.date()

ENDERECO = {"cep": "40000-000", "logradouro": "Rua das Flores", "numero": "100",
            "complemento": "ap 201", "bairro": "Bairro Exemplo",
            "municipio_ibge": "2927408"}

ID_ESPERADO = "DPS" + "2927408" + "2" + "11222333000181" + "00900" + "000000000000001"

XML_ESPERADO = (
    "<?xml version='1.0' encoding='UTF-8'?>\n"
    '<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
    f'<infDPS Id="{ID_ESPERADO}">'
    "<tpAmb>2</tpAmb>"
    "<dhEmi>2026-11-15T10:30:00-03:00</dhEmi>"
    "<verAplic>auditoriaJB-nfse-1</verAplic>"
    "<serie>900</serie>"
    "<nDPS>1</nDPS>"
    "<dCompet>2026-11-01</dCompet>"
    "<tpEmit>1</tpEmit>"
    "<cLocEmi>2927408</cLocEmi>"
    "<prest><CNPJ>11222333000181</CNPJ><IM>0000000001</IM>"
    "<regTrib><opSimpNac>3</opSimpNac><regApTribSN>1</regApTribSN>"
    "<regEspTrib>0</regEspTrib></regTrib></prest>"
    "<toma><CPF>12345678909</CPF><xNome>Ana Exemplo</xNome></toma>"
    "<serv><locPrest><cLocPrestacao>2927408</cLocPrestacao></locPrest>"
    "<cServ><cTribNac>080101</cTribNac>"
    "<xDescServ>REFERENTE AOS SERVIÇOS PRESTADOS DE BERÇÁRIO AO MENOR: PEDRO "
    "EXEMPLO NO PERÍODO DE 11/2026.</xDescServ>"
    "<cNBS>122011100</cNBS></cServ></serv>"
    "<valores><vServPrest><vServ>1250.00</vServ></vServPrest>"
    "<trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN></tribMun>"
    "<totTrib><pTotTribSN>6.00</pTotTribSN></totTrib></trib></valores>"
    "</infDPS></DPS>"
).encode("utf-8")


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def erro(funcao, *args, **kwargs):
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc
    return None


def nota(perfil, **campos):
    base = {"competencia": "11/2026", "responsavel_nome": "Ana Exemplo",
            "responsavel_cpf": fx.CPF_ANA, "aluno_nome": "Pedro Exemplo",
            "turma": "Berçário", "valor": "1.250,00", **ENDERECO}
    base.update(campos)
    r = nc.conferir(perfil, [nf.LinhaEfetiva(ref=1, campos=base)],
                    chaves_aprovadas={}, hoje=HOJE)
    return r.linhas[0]


def gerar(perfil, linha, numero=1, quando=QUANDO):
    return nd.montar_dps(perfil, nd.dados_da_linha(linha), numero=numero, dh_emi=quando)


def testar_referencia() -> None:
    perfil = nf.validar_perfil(fx.perfil_completo(endereco="omitir"))
    dps = gerar(perfil, nota(perfil))
    checar(dps.xml == XML_ESPERADO,
           "XML difere da referencia:\n" + dps.xml.decode("utf-8") + "\n---\n"
           + XML_ESPERADO.decode("utf-8"))
    checar(dps.id_dps == ID_ESPERADO and len(dps.id_dps) == 45, dps.id_dps)
    checar((dps.serie, dps.numero) == ("900", 1), (dps.serie, dps.numero))
    checar(dps.d_compet == "2026-11-01" and dps.dh_emi == "2026-11-15T10:30:00-03:00",
           (dps.d_compet, dps.dh_emi))
    checar(dps.sha256 == hashlib.sha256(XML_ESPERADO).hexdigest(), dps.sha256)
    checar(dps.versao_leiaute == "1.01" and dps.versao_gerador == nd.VERSAO_GERADOR,
           (dps.versao_leiaute, dps.versao_gerador))
    checar(nd.validar_xsd(dps.xml) == [], nd.validar_xsd(dps.xml))
    checar(b"Signature" not in dps.xml, "a Fase 1 nao assina")
    # Mesma entrada, mesmos bytes.
    checar(gerar(perfil, nota(perfil)).xml == dps.xml, "geracao nao deterministica")


def testar_variacoes() -> None:
    com_endereco = nf.validar_perfil(fx.perfil_completo(endereco="informar"))
    xml = gerar(com_endereco, nota(com_endereco), numero=42).xml
    checar(b"<toma><CPF>12345678909</CPF><xNome>Ana Exemplo</xNome><end><endNac>"
           b"<cMun>2927408</cMun><CEP>40000000</CEP></endNac><xLgr>Rua das Flores"
           b"</xLgr><nro>100</nro><xCpl>ap 201</xCpl><xBairro>Bairro Exemplo"
           b"</xBairro></end></toma>" in xml, xml)
    checar(b"<nDPS>42</nDPS>" in xml and b"000000000000042\"" in xml, "numero 42")
    checar(nd.validar_xsd(xml) == [], nd.validar_xsd(xml))

    sem_complemento = nota(com_endereco, complemento=None)
    xml = gerar(com_endereco, sem_complemento).xml
    checar(b"<xCpl>" not in xml and nd.validar_xsd(xml) == [], "complemento opcional")

    # Retido com ISS pelo Simples: a regra oficial manda informar a aliquota.
    retido = nf.validar_perfil(fx.perfil_completo(iss_retido=True))
    xml = gerar(retido, nota(retido)).xml
    checar(b"<tpRetISSQN>2</tpRetISSQN><pAliq>5.00</pAliq>" in xml, xml)
    checar(nd.validar_xsd(xml) == [], nd.validar_xsd(xml))

    tres = nf.validar_perfil(fx.perfil_completo(
        tributos_aprox="pTotTrib", p_tot_trib_sn=None, p_tot_trib_fed="4,50",
        p_tot_trib_est="0", p_tot_trib_mun="2,00", informar_im=False,
        inscricao_municipal=None))
    xml = gerar(tres, nota(tres)).xml
    checar(b"<totTrib><pTotTrib><pTotTribFed>4.50</pTotTribFed><pTotTribEst>0.00"
           b"</pTotTribEst><pTotTribMun>2.00</pTotTribMun></pTotTrib></totTrib>" in xml,
           xml)
    checar(b"<IM>" not in xml, "sem registro no CNC a IM nao vai (R5)")
    checar(nd.validar_xsd(xml) == [], nd.validar_xsd(xml))

    especiais = nota(nf.validar_perfil(fx.perfil_completo()),
                     aluno_nome="Davi D'Ávila & <Filhos>", valor="0,50")
    perfil = nf.validar_perfil(fx.perfil_completo())
    xml = gerar(perfil, especiais).xml
    checar("DAVI D'ÁVILA &amp; &lt;FILHOS&gt;".encode("utf-8") in xml, xml)
    checar(b"<vServ>0.50</vServ>" in xml, "centavos")
    checar(nd.validar_xsd(xml) == [], nd.validar_xsd(xml))

    # Fuso: instante em UTC vira horario de Salvador.
    em_utc = dt.datetime(2026, 11, 15, 13, 30, tzinfo=dt.timezone.utc)
    checar(gerar(perfil, nota(perfil), quando=em_utc).dh_emi == "2026-11-15T10:30:00-03:00",
           "dhEmi no fuso de Salvador")


def testar_recusas() -> None:
    completo = nf.validar_perfil(fx.perfil_completo())
    cru = nf.validar_perfil(fx.perfil_cru())
    e = erro(gerar, cru, nota(completo))
    checar(e is not None and e.codigo == nf.PERFIL_COM_PENDENCIA
           and "JB-2" in e.mensagem, e and e.mensagem)

    bloqueada = nota(completo, valor=None)
    e = erro(nd.dados_da_linha, bloqueada)
    checar(e is not None and e.codigo == nd.LINHA_COM_BLOQUEIO, e and e.codigo)

    pendente = nota(completo, turma="Fundamental I")
    e = erro(nd.dados_da_linha, pendente)
    checar(e is not None and e.codigo == nd.LINHA_COM_BLOQUEIO, "turma pendente bloqueia")

    dados = nd.dados_da_linha(nota(completo))
    e = erro(nd.montar_dps, completo, dados, numero=1,
             dh_emi=dt.datetime(2026, 10, 31, 23, 0, tzinfo=nd.FUSO_SALVADOR))
    checar(e is not None and e.codigo == nf.COMPETENCIA_FUTURA, "dCompet > dhEmi (E0015)")
    for numero in (0, -1, 10 ** 15):
        e = erro(nd.montar_dps, completo, dados, numero=numero, dh_emi=QUANDO)
        checar(e is not None and e.codigo == nd.NUMERO_INVALIDO, f"numero {numero}")
    e = erro(nd.montar_dps, completo, dados, numero=1,
             dh_emi=dt.datetime(2026, 11, 15, 10, 30))
    checar(e is not None and e.codigo == nd.DATA_SEM_FUSO, "dhEmi sem fuso")


def testar_xsd() -> None:
    checar(nd.padrao_serie_no_xsd_oficial() == r"^0{0,4}\d{1,5}$",
           "o XSD oficial mudou o padrao da serie: revisar o contorno (research.md)")
    perfil = nf.validar_perfil(fx.perfil_completo())
    xml = gerar(perfil, nota(perfil)).xml
    sem_ctribnac = xml.replace(b"<cTribNac>080101</cTribNac>", b"")
    erros = nd.validar_xsd(sem_ctribnac)
    checar(erros and any("cTribNac" in e or "xDescServ" in e for e in erros), erros)
    serie_literal = xml.replace(b"<serie>900</serie>", b"<serie>^900$</serie>")
    checar(nd.validar_xsd(serie_literal) != [],
           "o contorno troca so o padrao: '^900$' continua invalido")
    checar(nd.validar_xsd(b"<nao-e-xml") != [], "XML malformado vira erro, nao excecao")
    e = erro(nd.garantir_valida, sem_ctribnac)
    checar(e is not None and e.codigo == nd.DPS_INVALIDA, "garantir_valida levanta")


def main() -> int:
    testar_referencia()
    testar_variacoes()
    testar_recusas()
    testar_xsd()
    print("OK - DPS v1.01 (XML de referencia escrito a mao, Id de 45 posicoes, "
          "deterministica, valida no XSD oficial com o contorno da serie, "
          "endereco, aliquota pela regra oficial, pTotTrib, sem IM sem CNC, "
          "escape, fuso de Salvador, recusas por pendencia, bloqueio, "
          "competencia futura e numero invalido, sem assinatura) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
