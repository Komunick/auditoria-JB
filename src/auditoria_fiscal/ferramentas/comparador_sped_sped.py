"""Item 2 - Comparacao entre duas versoes de SPED.

Cenario: a contabilidade corrige o SPED e o cliente replica os ajustes no
sistema, gerando um novo SPED. Nem sempre todos os ajustes sao aplicados.

Esta ferramenta casa as notas dos dois arquivos pela CHAVE DE ACESSO e aponta,
nota a nota, exatamente quais campos divergem (valor contabil, base de calculo,
aliquota, imposto, CFOP, CST/CSOSN, entre outros), no nivel da nota e do item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..core.modelos import DocumentoFiscalConjunto, ItemNota, NotaFiscal


# (atributo, rotulo, tipo)  -- tipo: texto | valor | valor4
CAMPOS_NOTA = [
    ("valor_documento", "Valor contabil", "valor"),
    ("valor_mercadoria", "Valor mercadoria", "valor"),
    ("valor_desconto", "Desconto", "valor"),
    ("vl_bc_icms", "Base de calculo ICMS", "valor"),
    ("vl_icms", "Valor ICMS", "valor"),
    ("vl_bc_icms_st", "Base ICMS ST", "valor"),
    ("vl_icms_st", "Valor ICMS ST", "valor"),
    ("vl_ipi", "Valor IPI", "valor"),
    ("vl_pis", "Valor PIS", "valor"),
    ("vl_cofins", "Valor COFINS", "valor"),
    ("situacao", "Situacao", "texto"),
    ("cod_part", "Cod. participante", "texto"),
]

CAMPOS_ITEM = [
    ("cfop", "CFOP", "texto"),
    ("cst_icms", "CST/CSOSN", "texto"),
    ("ncm", "NCM", "texto"),
    ("descricao", "Descricao", "texto"),
    ("quantidade", "Quantidade", "valor4"),
    ("valor_item", "Valor do item", "valor"),
    ("valor_unitario", "Valor unitario", "valor"),
    ("valor_desconto", "Desconto", "valor"),
    ("vl_bc_icms", "Base ICMS", "valor"),
    ("aliq_icms", "Aliquota ICMS", "valor"),
    ("vl_icms", "Valor ICMS", "valor"),
    ("vl_bc_icms_st", "Base ICMS ST", "valor"),
    ("aliq_st", "Aliquota ST", "valor"),
    ("vl_icms_st", "Valor ICMS ST", "valor"),
    ("cst_ipi", "CST IPI", "texto"),
    ("vl_ipi", "Valor IPI", "valor"),
    ("cst_pis", "CST PIS", "texto"),
    ("vl_pis", "Valor PIS", "valor"),
    ("cst_cofins", "CST COFINS", "texto"),
    ("vl_cofins", "Valor COFINS", "valor"),
]

_TOL_VALOR = Decimal("0.01")
_TOL_VALOR4 = Decimal("0.0001")


@dataclass
class DiferencaCampo:
    nivel: str          # "nota" ou "item"
    campo: str
    valor_a: str
    valor_b: str
    num_item: str = ""


@dataclass
class NotaDivergente:
    chave: str
    numero: str
    fornecedor: str
    diferencas: list[DiferencaCampo] = field(default_factory=list)


@dataclass
class ResultadoDiffSped:
    rotulo_a: str = "Arquivo A"
    rotulo_b: str = "Arquivo B"
    divergentes: list[NotaDivergente] = field(default_factory=list)
    apenas_em_a: list[NotaFiscal] = field(default_factory=list)
    apenas_em_b: list[NotaFiscal] = field(default_factory=list)
    total_a: int = 0
    total_b: int = 0
    conciliadas: int = 0
    iguais: int = 0

    @property
    def total_diferencas(self) -> int:
        return sum(len(n.diferencas) for n in self.divergentes)

    def resumo(self) -> dict:
        return {
            "total_a": self.total_a,
            "total_b": self.total_b,
            "conciliadas": self.conciliadas,
            "iguais": self.iguais,
            "divergentes": len(self.divergentes),
            "apenas_em_a": len(self.apenas_em_a),
            "apenas_em_b": len(self.apenas_em_b),
            "total_diferencas": self.total_diferencas,
        }


# ----------------------------------------------------------------------
def _fmt(tipo: str, valor) -> str:
    if valor is None:
        return ""
    if tipo in ("valor", "valor4"):
        casas = 4 if tipo == "valor4" else 2
        return f"{float(valor):.{casas}f}"
    return str(valor).strip()


def _difere(tipo: str, a, b) -> bool:
    if tipo == "texto":
        return (str(a).strip() if a is not None else "") != \
               (str(b).strip() if b is not None else "")
    tol = _TOL_VALOR4 if tipo == "valor4" else _TOL_VALOR
    va = a if isinstance(a, Decimal) else Decimal(str(a or 0))
    vb = b if isinstance(b, Decimal) else Decimal(str(b or 0))
    return (va - vb).copy_abs() > tol


def _ordena_num(num: str):
    return (0, int(num)) if num.isdigit() else (1, num)


def _descr_item(item: ItemNota) -> str:
    return f"{item.cod_item} {item.descricao}".strip()


def _fornecedor(na: NotaFiscal, nb: NotaFiscal) -> str:
    for nota in (na, nb):
        if nota.participante and nota.participante.nome:
            return nota.participante.nome
    return na.cnpj_emitente or nb.cnpj_emitente


def _comparar_nota(na: NotaFiscal, nb: NotaFiscal) -> list[DiferencaCampo]:
    difs = []
    for attr, rotulo, tipo in CAMPOS_NOTA:
        va, vb = getattr(na, attr), getattr(nb, attr)
        if _difere(tipo, va, vb):
            difs.append(DiferencaCampo("nota", rotulo, _fmt(tipo, va), _fmt(tipo, vb)))
    return difs


def _comparar_itens(na: NotaFiscal, nb: NotaFiscal) -> list[DiferencaCampo]:
    difs = []
    itens_a = {(it.num_item or str(i)): it for i, it in enumerate(na.itens)}
    itens_b = {(it.num_item or str(i)): it for i, it in enumerate(nb.itens)}
    for num in sorted(set(itens_a) | set(itens_b), key=_ordena_num):
        ia, ib = itens_a.get(num), itens_b.get(num)
        if ia is None:
            difs.append(DiferencaCampo("item", "Item so no arquivo B", "",
                                       _descr_item(ib), num))
            continue
        if ib is None:
            difs.append(DiferencaCampo("item", "Item so no arquivo A",
                                       _descr_item(ia), "", num))
            continue
        for attr, rotulo, tipo in CAMPOS_ITEM:
            va, vb = getattr(ia, attr), getattr(ib, attr)
            if _difere(tipo, va, vb):
                difs.append(DiferencaCampo("item", rotulo, _fmt(tipo, va),
                                           _fmt(tipo, vb), num))
    return difs


def comparar_speds(
    doc_a: DocumentoFiscalConjunto,
    doc_b: DocumentoFiscalConjunto,
    rotulo_a: str = "Arquivo A",
    rotulo_b: str = "Arquivo B",
) -> ResultadoDiffSped:
    """Compara dois SPEDs por chave e retorna as divergencias campo a campo."""
    idx_a = doc_a.por_chave()
    idx_b = doc_b.por_chave()
    chaves_a, chaves_b = set(idx_a), set(idx_b)
    comuns = chaves_a & chaves_b

    resultado = ResultadoDiffSped(
        rotulo_a=rotulo_a, rotulo_b=rotulo_b,
        total_a=len(idx_a), total_b=len(idx_b), conciliadas=len(comuns),
    )

    for chave in comuns:
        na, nb = idx_a[chave], idx_b[chave]
        difs = _comparar_nota(na, nb) + _comparar_itens(na, nb)
        if difs:
            resultado.divergentes.append(NotaDivergente(
                chave=chave, numero=na.numero or nb.numero,
                fornecedor=_fornecedor(na, nb), diferencas=difs))
        else:
            resultado.iguais += 1

    resultado.apenas_em_a = [idx_a[c] for c in (chaves_a - chaves_b)]
    resultado.apenas_em_b = [idx_b[c] for c in (chaves_b - chaves_a)]
    resultado.divergentes.sort(key=lambda d: _ordena_num(d.numero) if d.numero
                               else (1, ""))
    return resultado
