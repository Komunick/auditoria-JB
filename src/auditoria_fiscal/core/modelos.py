"""Modelos de dados normalizados.

Estes modelos sao a "lingua franca" das ferramentas: tanto o leitor de SPED
quanto o de XML da NF-e produzem os mesmos objetos, de forma que o restante do
sistema (comparadores, livro de conferencia, exportacoes) nao precisa saber a
origem dos dados.

Todos os valores monetarios e quantidades usam Decimal para evitar erros de
arredondamento tipicos de ponto flutuante em contexto fiscal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


# Origem de onde a nota/dado foi lido (util em relatorios e depuracao).
ORIGEM_SPED = "SPED"
ORIGEM_XML = "XML"
ORIGEM_SEFAZ = "SEFAZ"

# Codigo IBGE da UF (2 primeiros digitos da chave de acesso) -> sigla.
UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}


def so_digitos(valor: Optional[str]) -> str:
    """Remove tudo que nao for digito (CNPJ, CPF, chave, etc.)."""
    if not valor:
        return ""
    return "".join(c for c in valor if c.isdigit())


@dataclass
class Participante:
    """Cadastro do participante (registro 0150 do SPED / emitente-dest. do XML)."""

    cod_part: str = ""          # codigo interno usado pelo SPED (liga C100 -> 0150)
    nome: str = ""
    cnpj: str = ""
    cpf: str = ""
    ie: str = ""
    cod_municipio: str = ""
    uf: str = ""

    @property
    def documento(self) -> str:
        """CNPJ (ou CPF quando pessoa fisica), so digitos."""
        return so_digitos(self.cnpj) or so_digitos(self.cpf)


@dataclass
class ItemNota:
    """Um item/produto de uma nota (registro C170 do SPED / det do XML)."""

    num_item: str = ""
    cod_item: str = ""
    descricao: str = ""
    ncm: str = ""               # do 0200 (SPED) ou do proprio XML
    cest: str = ""
    unidade: str = ""
    quantidade: Decimal = Decimal("0")
    valor_unitario: Decimal = Decimal("0")
    valor_item: Decimal = Decimal("0")      # valor total do item
    valor_desconto: Decimal = Decimal("0")
    cfop: str = ""
    cst_icms: str = ""          # CST ou CSOSN (Simples Nacional)
    vl_bc_icms: Decimal = Decimal("0")
    aliq_icms: Decimal = Decimal("0")
    vl_icms: Decimal = Decimal("0")
    vl_bc_icms_st: Decimal = Decimal("0")
    aliq_st: Decimal = Decimal("0")
    vl_icms_st: Decimal = Decimal("0")
    cst_ipi: str = ""
    vl_ipi: Decimal = Decimal("0")
    cst_pis: str = ""
    vl_pis: Decimal = Decimal("0")
    cst_cofins: str = ""
    vl_cofins: Decimal = Decimal("0")

    # Auditoria de correcoes: campo -> valor original importado. Preenchido
    # apenas em COPIAS corrigidas (core/correcoes.py); o objeto original
    # importado nunca e alterado.
    corrigido_de: dict = field(default_factory=dict)


@dataclass
class NotaFiscal:
    """Documento fiscal normalizado (registro C100 do SPED / infNFe do XML)."""

    origem: str = ""            # ORIGEM_SPED / ORIGEM_XML / ORIGEM_SEFAZ
    xml_path: str = ""          # caminho do XML de origem (habilita gerar DANFE)
    chave: str = ""             # 44 digitos (chave de acesso da NF-e)
    modelo: str = ""            # COD_MOD (55 = NF-e)
    serie: str = ""
    numero: str = ""
    ind_oper: str = ""          # 0 = entrada / 1 = saida
    ind_emit: str = ""          # 0 = emissao propria / 1 = terceiros
    situacao: str = ""          # COD_SIT do SPED (00 regular, 02 cancelado, ...)
    cod_part: str = ""          # codigo do participante no SPED
    participante: Optional[Participante] = None
    dt_emissao: Optional[date] = None
    dt_entrada_saida: Optional[date] = None

    valor_documento: Decimal = Decimal("0")
    valor_mercadoria: Decimal = Decimal("0")
    valor_desconto: Decimal = Decimal("0")
    valor_frete: Decimal = Decimal("0")
    vl_bc_icms: Decimal = Decimal("0")
    vl_icms: Decimal = Decimal("0")
    vl_bc_icms_st: Decimal = Decimal("0")
    vl_icms_st: Decimal = Decimal("0")
    vl_ipi: Decimal = Decimal("0")
    vl_pis: Decimal = Decimal("0")
    vl_cofins: Decimal = Decimal("0")

    itens: list[ItemNota] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def chave_normalizada(self) -> str:
        return so_digitos(self.chave)

    @property
    def cancelada(self) -> bool:
        # 02/03 = cancelamento; 05 = numeracao inutilizada (varia por versao do layout)
        return self.situacao in {"02", "03", "05"}

    @property
    def denegada(self) -> bool:
        # 04 = documento denegado
        return self.situacao == "04"

    @property
    def cnpj_emitente(self) -> str:
        """Emitente extraido da propria chave (posicoes 7 a 20)."""
        chv = self.chave_normalizada
        if len(chv) == 44:
            return chv[6:20]
        return self.participante.documento if self.participante else ""

    @property
    def uf_origem(self) -> str:
        """UF de origem: codigo IBGE da chave; sem chave, UF do participante."""
        chv = self.chave_normalizada
        if len(chv) == 44 and chv[:2] in UF_POR_CODIGO:
            return UF_POR_CODIGO[chv[:2]]
        return self.participante.uf if self.participante else ""

    @property
    def tem_correcao(self) -> bool:
        """True se algum item desta (copia de) nota teve campo corrigido."""
        return any(item.corrigido_de for item in self.itens)


@dataclass
class Empresa:
    """Identificacao da entidade do arquivo (registro 0000 do SPED)."""

    cnpj: str = ""
    nome: str = ""
    uf: str = ""
    ie: str = ""
    dt_inicial: Optional[date] = None
    dt_final: Optional[date] = None


@dataclass
class DocumentoFiscalConjunto:
    """Resultado da leitura de um arquivo SPED completo."""

    empresa: Empresa = field(default_factory=Empresa)
    notas: list[NotaFiscal] = field(default_factory=list)

    def por_chave(self) -> dict[str, NotaFiscal]:
        """Indexa as notas pela chave de acesso (ignora notas sem chave)."""
        indice: dict[str, NotaFiscal] = {}
        for nota in self.notas:
            chave = nota.chave_normalizada
            if len(chave) == 44:
                indice[chave] = nota
        return indice
