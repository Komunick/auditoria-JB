"""DPS de exemplo, valida no XSD, para os testes da Fase 2 (spec 008).

Mesmo prestador ficticio de fixtures.nfse (CNPJ 11.222.333/0001-81, serie
900). So muda o numero, para dar Id e chave diferentes.
"""

from __future__ import annotations


def id_dps(numero: int, cnpj: str = "11222333000181") -> str:
    return f"DPS29274082{cnpj}00900{numero:015d}"


def xml_dps(numero: int = 1, *, nome: str = "Ana Exemplo", tp_amb: int = 2,
            cnpj: str = "11222333000181") -> bytes:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        '<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        f'<infDPS Id="{id_dps(numero, cnpj)}">'
        f"<tpAmb>{tp_amb}</tpAmb>"
        "<dhEmi>2026-11-15T10:30:00-03:00</dhEmi>"
        "<verAplic>auditoriaJB-nfse-1</verAplic>"
        "<serie>900</serie>"
        f"<nDPS>{numero}</nDPS>"
        "<dCompet>2026-11-01</dCompet>"
        "<tpEmit>1</tpEmit>"
        "<cLocEmi>2927408</cLocEmi>"
        f"<prest><CNPJ>{cnpj}</CNPJ>"
        "<regTrib><opSimpNac>3</opSimpNac><regApTribSN>1</regApTribSN>"
        "<regEspTrib>0</regEspTrib></regTrib></prest>"
        f"<toma><CPF>12345678909</CPF><xNome>{nome}</xNome></toma>"
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
