"""Notas ja emitidas, SINTETICAS, para o perfil pela nota (spec 009, Parte 2).

- `nota_salvador`: NFS-e da Nota Salvador no leiaute ABRASF v1 (CompNfse >
  Nfse > InfNfse), com a aliquota em fracao como o provedor de Salvador.
- `nfse_nacional`: NFS-e do padrao nacional montada em volta de uma DPS do
  proprio gerador (`montar_dps`), com o grupo `emit` que a Sefin preenche.

Tudo ficticio, como em `fixtures/nfse/__init__.py`: Escola Exemplo, CNPJ
11.222.333/0001-81, tomadora Ana Exemplo (CPF 123.456.789-09), aluno Pedro
Exemplo. Nenhum dado do video da creche.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from xml.sax.saxutils import escape

from auditoria_fiscal.core import nfse as nf
from auditoria_fiscal.core import nfse_dps as nd

from . import CNPJ, CPF_ANA, perfil_completo

NS_ABRASF = "http://www.abrasf.org.br/ABRASF/arquivos/nfse.xsd"
CNPJ_DIGITOS = "".join(c for c in CNPJ if c.isdigit())
IM = "0000000001"
SALVADOR = "2927408"
TOMADORA = "ANA EXEMPLO"
ALUNO = "PEDRO EXEMPLO"
DISCRIMINACAO = ("REFERENTE AOS SERVIÇOS PRESTADOS DE BERÇÁRIO AO MENOR: "
                 f"{ALUNO} NO PERÍODO DE 09/2026.")


def _tag(nome: str, valor) -> str:
    return "" if valor is None else f"<{nome}>{escape(str(valor))}</{nome}>"


def inf_salvador(*, numero: str = "901", competencia: str = "2026-09-01T00:00:00",
                 cnpj: str = CNPJ_DIGITOS, im: str | None = IM,
                 razao_social: str = "ESCOLA EXEMPLO LTDA",
                 regime_especial: int | None = None, optante: int = 1,
                 iss_retido: int = 2, aliquota: str | None = "0.05",
                 item: str = "0801", cnae: str | None = "8511200",
                 ctiss: str | None = "0801001", discriminacao: str = DISCRIMINACAO,
                 tomador: str = TOMADORA, cpf: str = CPF_ANA,
                 municipio_servico: str = SALVADOR, extra_servico: str = "") -> str:
    """Um `InfNfse` (sem a raiz), na ordem do ABRASF v1."""
    cpf = "".join(c for c in cpf if c.isdigit())
    return (
        "<InfNfse>"
        f"{_tag('Numero', numero)}{_tag('CodigoVerificacao', 'ABCD1234')}"
        f"{_tag('DataEmissao', '2026-09-08T16:22:00')}"
        f"{_tag('NaturezaOperacao', 1)}"
        f"{_tag('RegimeEspecialTributacao', regime_especial)}"
        f"{_tag('OptanteSimplesNacional', optante)}{_tag('IncentivadorCultural', 2)}"
        f"{_tag('Competencia', competencia)}"
        "<Servico><Valores>"
        f"{_tag('ValorServicos', '1250.00')}{_tag('IssRetido', iss_retido)}"
        f"{_tag('ValorIss', '0.00')}{_tag('BaseCalculo', '1250.00')}"
        f"{_tag('Aliquota', aliquota)}{_tag('ValorLiquidoNfse', '1250.00')}"
        "</Valores>"
        f"{_tag('ItemListaServico', item)}{_tag('CodigoCnae', cnae)}"
        f"{_tag('CodigoTributacaoMunicipio', ctiss)}"
        f"{_tag('Discriminacao', discriminacao)}{_tag('CodigoMunicipio', municipio_servico)}"
        f"{extra_servico}"
        "</Servico>"
        "<PrestadorServico><IdentificacaoPrestador>"
        f"{_tag('Cnpj', cnpj)}{_tag('InscricaoMunicipal', im)}"
        "</IdentificacaoPrestador>"
        f"{_tag('RazaoSocial', razao_social)}{_tag('NomeFantasia', 'Escola Exemplo')}"
        "<Endereco><Endereco>Rua Exemplo</Endereco><Numero>100</Numero>"
        f"<Bairro>Centro</Bairro><CodigoMunicipio>{SALVADOR}</CodigoMunicipio>"
        "<Uf>BA</Uf><Cep>40000000</Cep></Endereco>"
        "</PrestadorServico>"
        "<TomadorServico><IdentificacaoTomador><CpfCnpj>"
        f"{_tag('Cpf', cpf)}"
        "</CpfCnpj></IdentificacaoTomador>"
        f"{_tag('RazaoSocial', tomador)}"
        "<Endereco><Endereco>Rua dos Testes</Endereco><Numero>5</Numero>"
        f"<Bairro>Pituba</Bairro><CodigoMunicipio>{SALVADOR}</CodigoMunicipio>"
        "<Uf>BA</Uf><Cep>41000000</Cep></Endereco>"
        "</TomadorServico>"
        f"<OrgaoGerador><CodigoMunicipio>{SALVADOR}</CodigoMunicipio><Uf>BA</Uf></OrgaoGerador>"
        "</InfNfse>")


def nota_salvador(**campos) -> bytes:
    """Uma NFS-e da Nota Salvador, como o portal exporta uma nota."""
    return ('<?xml version="1.0" encoding="utf-8"?>'
            f'<CompNfse xmlns="{NS_ABRASF}"><Nfse>{inf_salvador(**campos)}</Nfse>'
            '</CompNfse>').encode("utf-8")


def lista_salvador(*notas: dict) -> bytes:
    """Varias notas numa resposta de consulta (`ConsultarNfseResposta`)."""
    corpo = "".join(f"<CompNfse><Nfse>{inf_salvador(**n)}</Nfse></CompNfse>"
                    for n in notas)
    return ('<?xml version="1.0" encoding="ISO-8859-1"?>'
            f'<ConsultarNfseResposta xmlns="{NS_ABRASF}"><ListaNfse>{corpo}'
            '</ListaNfse></ConsultarNfseResposta>').encode("iso-8859-1")


def nfse_nacional(*, perfil: dict | None = None, numero: int = 7,
                  competencia: str = "2026-10", tp_amb: int | None = None,
                  discriminacao: str | None = None) -> bytes:
    """NFS-e nacional: DPS do gerador + o envelope `NFSe/infNFSe` da Sefin."""
    p = nf.validar_perfil(perfil or perfil_completo())
    turma = p.turmas[0]
    mes = int(competencia[5:])
    texto = discriminacao or nf.montar_discriminacao(
        p.modelo_discriminacao, turma=turma.nome, aluno=ALUNO,
        responsavel=TOMADORA, competencia=competencia)
    nota = nd.DadosNota(cpf="".join(c for c in CPF_ANA if c.isdigit()),
                        nome=TOMADORA, endereco=None, turma=turma,
                        discriminacao=texto, valor_centavos=125000,
                        competencia=competencia)
    dps = nd.montar_dps(p, nota, numero=numero,
                        dh_emi=dt.datetime(2026, mes, 20, 10, 0, tzinfo=nd.FUSO_SALVADOR))
    dps = dps.xml.split(b"?>", 1)[1]
    if tp_amb is not None:
        dps = dps.replace(b"<tpAmb>2</tpAmb>", f"<tpAmb>{tp_amb}</tpAmb>".encode())
    inicio = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<NFSe xmlns="{nd.NS}" versao="1.01"><infNFSe Id="NFS{SALVADOR}2{CNPJ_DIGITOS}">'
        "<xLocEmi>Salvador</xLocEmi><xLocPrestacao>Salvador</xLocPrestacao>"
        f"<nNFSe>{numero}</nNFSe><cLocIncid>{SALVADOR}</cLocIncid>"
        f"<emit><CNPJ>{p.cnpj}</CNPJ><IM>{IM}</IM><xNome>ESCOLA EXEMPLO LTDA</xNome>"
        "</emit>"
        "<valores><vBC>1250.00</vBC><pAliqAplic>5.00</pAliqAplic><vISSQN>62.50</vISSQN>"
        "<vLiq>1250.00</vLiq></valores>")
    return inicio.encode("utf-8") + dps + b"</infNFSe></NFSe>"


def zip_de(arquivos: dict[str, bytes]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        for nome, dados in arquivos.items():
            pacote.writestr(nome, dados)
    return saida.getvalue()
