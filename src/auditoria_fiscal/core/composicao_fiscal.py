"""Composicao fiscal da nota: agrupamento por CFOP -> CST -> aliquota de ICMS.

Hierarquia de agrupamento (usada pela tela de conferencia, pelo Livro Fiscal
e pelo relatorio de inconsistencias — sempre a MESMA funcao, para nao haver
divergencia entre as saidas):

    1. Nota fiscal
    2. CFOP
    3. CST
    4. Aliquota de ICMS

Itens com o mesmo CFOP e CST mas aliquotas diferentes NUNCA sao somados no
mesmo grupo. Todos os calculos usam Decimal (nunca ponto flutuante binario).

Regras de valor (documentadas — o modelo atual nao rateia frete/seguro/
despesas por item, entao a composicao nao inventa rateio):

- Valor contabil do grupo = soma do valor dos itens do grupo (VL_ITEM do
  C170 / vProd do XML). Corresponde ao valor das mercadorias do grupo.
- A conferencia do total reconstroi o valor da nota com os componentes
  disponiveis no modelo (mercadorias - desconto + frete + IPI + ICMS-ST) e,
  quando diverge do VL_DOC, emite um ALERTA descritivo em vez de presumir
  erro: a diferenca pode ser seguro/despesas acessorias (nao detalhadas no
  layout lido) ou regra fiscal legitima.
- ICMS incompativel com base x aliquota gera alerta mencionando reducao de
  base, diferimento e arredondamento como causas possiveis — nunca bloqueia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from .modelos import NotaFiscal

# Tolerancia de centavos por item para diferencas de arredondamento.
_TOL_ITEM = Decimal("0.02")
_CENT = Decimal("0.01")

# CSTs de ICMS em que nao se espera destaque de imposto proprio.
_CST_SEM_ICMS = {"30", "40", "41", "50", "60"}


def _q2(valor: Decimal) -> Decimal:
    return (valor or Decimal("0")).quantize(_CENT, rounding=ROUND_HALF_UP)


def _cst_puro(cst: str) -> str:
    """Ultimos 2 digitos do CST (descarta o digito de origem quando houver)."""
    digitos = "".join(c for c in str(cst or "") if c.isdigit())
    return digitos[-2:] if len(digitos) >= 2 else digitos


@dataclass
class GrupoFiscal:
    """Um agrupamento CFOP + CST + aliquota dentro de uma nota."""

    cfop: str = ""
    cst: str = ""
    aliquota: Decimal = Decimal("0")
    valor_contabil: Decimal = Decimal("0")
    vl_bc_icms: Decimal = Decimal("0")
    vl_icms: Decimal = Decimal("0")
    vl_bc_icms_st: Decimal = Decimal("0")
    vl_icms_st: Decimal = Decimal("0")
    qtd_itens: int = 0
    # Auditoria: {campo: valor original} quando algum item do grupo foi
    # corrigido (o grupo ja reflete o valor corrigido).
    corrigido_de: dict = field(default_factory=dict)

    @property
    def tem_icms(self) -> bool:
        """True quando o grupo tem base, aliquota ou imposto destacado."""
        return bool(self.vl_bc_icms or self.vl_icms or self.aliquota)


# Identificacao estavel de grupo para sobrescritas manuais da composicao
# (tela e Livro Fiscal usam a MESMA chave). A linha TOTAL usa GRUPO_TOTAL.
GRUPO_TOTAL = "__total__"


def chave_grupo(grupo: "GrupoFiscal") -> str:
    """Chave estavel do grupo (valores JA corrigidos): cfop|cst|aliquota."""
    return f"{grupo.cfop or ''}|{grupo.cst or ''}|{grupo.aliquota or ''}"


@dataclass
class ComposicaoNota:
    """Composicao fiscal completa de uma nota + alertas de validacao."""

    total_nota: Decimal = Decimal("0")
    grupos: list[GrupoFiscal] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    sem_itens: bool = False

    @property
    def soma_valor_contabil(self) -> Decimal:
        return _q2(sum((g.valor_contabil for g in self.grupos), Decimal("0")))


def compor_nota(nota: NotaFiscal) -> ComposicaoNota:
    """Agrupa os itens da nota por CFOP -> CST -> aliquota, com validacoes."""
    comp = ComposicaoNota(total_nota=_q2(nota.valor_documento))

    if not nota.itens:
        # C100 sem C170 (ou XML sem det): so a capa da nota esta disponivel.
        comp.sem_itens = True
        comp.grupos.append(GrupoFiscal(
            valor_contabil=_q2(nota.valor_documento),
            vl_bc_icms=_q2(nota.vl_bc_icms),
            vl_icms=_q2(nota.vl_icms),
            vl_bc_icms_st=_q2(nota.vl_bc_icms_st),
            vl_icms_st=_q2(nota.vl_icms_st),
        ))
        comp.alertas.append(
            "Nota sem detalhe de itens (sem C170/det): composicao apresentada "
            "pela capa da nota, sem CFOP/CST por grupo.")
        return comp

    # ---- Agrupamento: chave = (CFOP, CST, aliquota quantizada) ----
    grupos: dict[tuple, GrupoFiscal] = {}
    for item in nota.itens:
        aliq = _q2(item.aliq_icms)
        chave = (str(item.cfop or ""), str(item.cst_icms or ""), aliq)
        g = grupos.get(chave)
        if g is None:
            g = grupos[chave] = GrupoFiscal(
                cfop=chave[0], cst=chave[1], aliquota=aliq)
        g.valor_contabil += item.valor_item or Decimal("0")
        g.vl_bc_icms += item.vl_bc_icms or Decimal("0")
        g.vl_icms += item.vl_icms or Decimal("0")
        g.vl_bc_icms_st += item.vl_bc_icms_st or Decimal("0")
        g.vl_icms_st += item.vl_icms_st or Decimal("0")
        g.qtd_itens += 1
        for campo, original in item.corrigido_de.items():
            g.corrigido_de.setdefault(campo, original)

    comp.grupos = sorted(grupos.values(),
                         key=lambda g: (g.cfop, g.cst, g.aliquota))
    for g in comp.grupos:
        g.valor_contabil = _q2(g.valor_contabil)
        g.vl_bc_icms = _q2(g.vl_bc_icms)
        g.vl_icms = _q2(g.vl_icms)
        g.vl_bc_icms_st = _q2(g.vl_bc_icms_st)
        g.vl_icms_st = _q2(g.vl_icms_st)

    _validar_totais(nota, comp)
    _validar_icms(comp)
    return comp


def _validar_totais(nota: NotaFiscal, comp: ComposicaoNota) -> None:
    """Concilia a soma dos grupos com os totais da capa da nota (alertas)."""
    tol = _TOL_ITEM * max(1, len(nota.itens))
    soma = comp.soma_valor_contabil

    # Soma dos itens x valor de mercadorias da capa (quando informado).
    mercadoria = _q2(nota.valor_mercadoria)
    if mercadoria and abs(soma - mercadoria) > tol:
        comp.alertas.append(
            f"Soma dos itens ({soma}) difere do valor de mercadorias da capa "
            f"({mercadoria}).")

    # Reconstrucao do total com os componentes disponiveis no modelo.
    reconstruido = _q2(soma - (nota.valor_desconto or Decimal("0"))
                       + (nota.valor_frete or Decimal("0"))
                       + (nota.vl_ipi or Decimal("0"))
                       + (nota.vl_icms_st or Decimal("0")))
    if comp.total_nota and abs(reconstruido - comp.total_nota) > tol:
        comp.alertas.append(
            f"Valor reconstruido dos grupos ({reconstruido} = itens - desconto "
            f"+ frete + IPI + ICMS-ST) difere do total da nota "
            f"({comp.total_nota}). Pode haver seguro/despesas acessorias nao "
            "detalhadas no layout lido ou regra especifica — validar.")


def _validar_icms(comp: ComposicaoNota) -> None:
    """Verifica base x aliquota x imposto por grupo (alerta, nunca bloqueio)."""
    for g in comp.grupos:
        rotulo = f"CFOP {g.cfop} / CST {g.cst}"
        cst = _cst_puro(g.cst)
        if cst in _CST_SEM_ICMS:
            if g.vl_icms:
                comp.alertas.append(
                    f"{rotulo}: CST sem destaque de ICMS proprio, mas ha "
                    f"imposto informado ({g.vl_icms}) — validar.")
            continue
        if g.aliquota and g.vl_bc_icms:
            esperado = _q2(g.vl_bc_icms * g.aliquota / Decimal("100"))
            tolerancia = _TOL_ITEM * max(1, g.qtd_itens)
            if abs(esperado - g.vl_icms) > tolerancia:
                comp.alertas.append(
                    f"{rotulo} (aliquota {g.aliquota}%): ICMS informado "
                    f"({g.vl_icms}) difere do calculado ({esperado}). Pode "
                    "decorrer de reducao de base, diferimento, desoneracao ou "
                    "arredondamento — validar antes de tratar como erro.")
