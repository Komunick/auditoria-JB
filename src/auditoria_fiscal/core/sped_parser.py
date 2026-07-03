"""Leitor de arquivo SPED Fiscal (EFD ICMS/IPI).

O arquivo e texto, um registro por linha, campos delimitados por pipe "|".
A linha comeca e termina com "|", entao ao dividir por "|" obtemos:

    "|C100|0|1|..." -> ["", "C100", "0", "1", ...]

Assim, o codigo do registro fica em campos[1] e o campo de posicao P do layout
(onde REG = posicao 1) fica em campos[P]. Isso facilita mapear pelo layout
oficial (Guia Pratico da EFD ICMS/IPI).

Registros tratados:
    0000 - abertura / identificacao da entidade
    0150 - cadastro de participantes (fornecedores/clientes)
    0200 - identificacao do item/produto (traz o NCM)
    C100 - nota fiscal (modelos 01, 1B, 04, 55)
    C170 - itens do documento

Outros registros sao ignorados com seguranca.
"""

from __future__ import annotations

from typing import Optional

from .modelos import (
    DocumentoFiscalConjunto,
    Empresa,
    ItemNota,
    NotaFiscal,
    Participante,
    ORIGEM_SPED,
    so_digitos,
)
from .utils import ler_texto, para_data, para_decimal


def _campo(campos: list[str], posicao: int) -> str:
    """Retorna o campo na posicao do layout (1-based) ou "" se nao existir."""
    if 0 <= posicao < len(campos):
        return campos[posicao].strip()
    return ""


class LeitorSped:
    """Le um arquivo SPED Fiscal e produz um DocumentoFiscalConjunto."""

    def __init__(self) -> None:
        self.empresa = Empresa()
        # codigo do participante (0150) -> Participante
        self._participantes: dict[str, Participante] = {}
        # codigo do item (0200) -> (descricao, ncm, cest)
        self._produtos: dict[str, tuple[str, str, str]] = {}
        self.notas: list[NotaFiscal] = []
        self._nota_atual: Optional[NotaFiscal] = None

    # ------------------------------------------------------------------
    def ler(self, caminho: str) -> DocumentoFiscalConjunto:
        texto = ler_texto(caminho)
        for linha in texto.splitlines():
            if not linha or "|" not in linha:
                continue
            campos = linha.split("|")
            reg = _campo(campos, 1)
            processador = self._despachante.get(reg)
            if processador is not None:
                processador(self, campos)

        self._fechar_nota_atual()
        # Liga participantes as notas depois de ter lido todos os 0150.
        self._vincular_participantes()
        return DocumentoFiscalConjunto(empresa=self.empresa, notas=self.notas)

    # ------------------------------------------------------------------
    def _reg_0000(self, campos: list[str]) -> None:
        self.empresa = Empresa(
            cnpj=so_digitos(_campo(campos, 7)),
            nome=_campo(campos, 6),
            uf=_campo(campos, 9),
            ie=_campo(campos, 10),
            dt_inicial=para_data(_campo(campos, 4)),
            dt_final=para_data(_campo(campos, 5)),
        )

    def _reg_0150(self, campos: list[str]) -> None:
        cod_part = _campo(campos, 2)
        self._participantes[cod_part] = Participante(
            cod_part=cod_part,
            nome=_campo(campos, 3),
            cnpj=so_digitos(_campo(campos, 5)),
            cpf=so_digitos(_campo(campos, 6)),
            ie=_campo(campos, 7),
            cod_municipio=_campo(campos, 8),
        )

    def _reg_0200(self, campos: list[str]) -> None:
        cod_item = _campo(campos, 2)
        descricao = _campo(campos, 3)
        ncm = _campo(campos, 8)
        cest = _campo(campos, 13)
        self._produtos[cod_item] = (descricao, ncm, cest)

    def _reg_C100(self, campos: list[str]) -> None:
        # Fecha a nota anterior antes de abrir a nova.
        self._fechar_nota_atual()
        self._nota_atual = NotaFiscal(
            origem=ORIGEM_SPED,
            ind_oper=_campo(campos, 2),
            ind_emit=_campo(campos, 3),
            cod_part=_campo(campos, 4),
            modelo=_campo(campos, 5),
            situacao=_campo(campos, 6),
            serie=_campo(campos, 7),
            numero=_campo(campos, 8),
            chave=so_digitos(_campo(campos, 9)),
            dt_emissao=para_data(_campo(campos, 10)),
            dt_entrada_saida=para_data(_campo(campos, 11)),
            valor_documento=para_decimal(_campo(campos, 12)),
            valor_desconto=para_decimal(_campo(campos, 14)),
            valor_mercadoria=para_decimal(_campo(campos, 16)),
            valor_frete=para_decimal(_campo(campos, 18)),
            vl_bc_icms=para_decimal(_campo(campos, 21)),
            vl_icms=para_decimal(_campo(campos, 22)),
            vl_bc_icms_st=para_decimal(_campo(campos, 23)),
            vl_icms_st=para_decimal(_campo(campos, 24)),
            vl_ipi=para_decimal(_campo(campos, 25)),
            vl_pis=para_decimal(_campo(campos, 26)),
            vl_cofins=para_decimal(_campo(campos, 27)),
        )

    def _reg_C170(self, campos: list[str]) -> None:
        if self._nota_atual is None:
            return
        cod_item = _campo(campos, 3)
        descricao_produto, ncm, cest = self._produtos.get(cod_item, ("", "", ""))
        descricao_item = _campo(campos, 4) or descricao_produto

        qtd = para_decimal(_campo(campos, 5))
        vl_item = para_decimal(_campo(campos, 7))
        vl_unit = (vl_item / qtd) if qtd else para_decimal("0")

        item = ItemNota(
            num_item=_campo(campos, 2),
            cod_item=cod_item,
            descricao=descricao_item,
            ncm=ncm,
            cest=cest,
            quantidade=qtd,
            unidade=_campo(campos, 6),
            valor_item=vl_item,
            valor_unitario=vl_unit,
            valor_desconto=para_decimal(_campo(campos, 8)),
            cst_icms=_campo(campos, 10),
            cfop=_campo(campos, 11),
            vl_bc_icms=para_decimal(_campo(campos, 13)),
            aliq_icms=para_decimal(_campo(campos, 14)),
            vl_icms=para_decimal(_campo(campos, 15)),
            vl_bc_icms_st=para_decimal(_campo(campos, 16)),
            aliq_st=para_decimal(_campo(campos, 17)),
            vl_icms_st=para_decimal(_campo(campos, 18)),
            cst_ipi=_campo(campos, 20),
            vl_ipi=para_decimal(_campo(campos, 24)),
            cst_pis=_campo(campos, 25),
            vl_pis=para_decimal(_campo(campos, 30)),
            cst_cofins=_campo(campos, 31),
            vl_cofins=para_decimal(_campo(campos, 36)),
        )
        self._nota_atual.itens.append(item)

    # ------------------------------------------------------------------
    def _fechar_nota_atual(self) -> None:
        if self._nota_atual is not None:
            self.notas.append(self._nota_atual)
            self._nota_atual = None

    def _vincular_participantes(self) -> None:
        for nota in self.notas:
            if nota.cod_part and nota.cod_part in self._participantes:
                nota.participante = self._participantes[nota.cod_part]

    # Mapa registro -> metodo. Definido apos os metodos existirem.
    _despachante = {
        "0000": _reg_0000,
        "0150": _reg_0150,
        "0200": _reg_0200,
        "C100": _reg_C100,
        "C170": _reg_C170,
    }


def ler_sped(caminho: str) -> DocumentoFiscalConjunto:
    """Atalho: le um arquivo SPED e retorna o conjunto de documentos."""
    return LeitorSped().ler(caminho)
