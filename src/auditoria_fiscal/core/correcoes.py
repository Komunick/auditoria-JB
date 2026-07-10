"""Correcoes de campos fiscais com auditoria e precedencia centralizada.

REGRA DE PRECEDENCIA (unica para todo o sistema — tela de conferencia,
Livro Fiscal, relatorio de inconsistencias e SPED corrigido):

    1. Usa o valor corrigido quando existe correcao valida e aplicada;
    2. Usa o valor original quando nao ha correcao.

O objeto importado NUNCA e alterado: `aplicar_correcoes` devolve uma COPIA
da nota com os campos trocados e o valor original guardado em
`item.corrigido_de[campo]` para auditoria. Toda saida posterior a conferencia
deve consumir a nota retornada por esta funcao.

Campos corrigiveis nesta versao: CFOP, CST de ICMS e aliquota de ICMS.
A correcao aplica-se aos itens da nota cujo valor atual do campo coincide
com o valor original informado (ex.: CFOP 1102 -> 1403 troca todos os itens
que estejam com 1102).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .modelos import NotaFiscal
from .utils import para_decimal

TIPO_MANUAL = "manual"
TIPO_AUTOMATICA = "automatica"

STATUS_APLICADA = "aplicada"
STATUS_REVERTIDA = "revertida"

# campo do ItemNota -> rotulo exibido
CAMPOS_CORRIGIVEIS = {
    "cfop": "CFOP",
    "cst_icms": "CST",
    "aliq_icms": "Aliquota ICMS",
}

# Primeiro digito valido de um CFOP (entradas 1-3, saidas 5-7).
_CFOP_INICIO = set("123567")


@dataclass
class Correcao:
    """Uma correcao registrada (espelha a tabela `correcao` do SQLite)."""

    id: int = 0
    chave: str = ""
    campo: str = ""
    valor_original: str = ""
    valor_corrigido: str = ""
    usuario: str = ""
    data_hora: str = ""
    tipo: str = TIPO_MANUAL
    motivo: str = ""
    status: str = STATUS_APLICADA
    inconsistencia: str = ""     # observacao/inconsistencia que a originou

    @property
    def ativa(self) -> bool:
        return self.status == STATUS_APLICADA


def normalizar_valor(campo: str, valor) -> str:
    """Normaliza o valor de um campo para comparacao e gravacao."""
    if campo == "aliq_icms":
        try:
            return str(para_decimal(str(valor)).quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            return str(valor)
    # CFOP/CST: apenas digitos (aceita "1.102" e "1102").
    return "".join(c for c in str(valor or "") if c.isdigit())


def validar_correcao(campo: str, valor_original, valor_corrigido,
                     usuario: str) -> None:
    """Levanta ValueError com mensagem clara quando a correcao e invalida."""
    if campo not in CAMPOS_CORRIGIVEIS:
        raise ValueError(f"Campo nao corrigivel: {campo!r}. "
                         f"Aceitos: {', '.join(CAMPOS_CORRIGIVEIS)}.")
    if not str(usuario or "").strip():
        raise ValueError("Informe o usuario responsavel pela correcao.")

    orig = normalizar_valor(campo, valor_original)
    novo = normalizar_valor(campo, valor_corrigido)
    if not orig or not novo:
        raise ValueError("Informe o valor original e o valor corrigido.")
    if orig == novo:
        raise ValueError("O valor corrigido e igual ao original.")

    if campo == "cfop":
        for rotulo, v in (("original", orig), ("corrigido", novo)):
            if len(v) != 4 or v[0] not in _CFOP_INICIO:
                raise ValueError(
                    f"CFOP {rotulo} invalido: {v!r} (esperado 4 digitos "
                    "iniciando em 1, 2, 3, 5, 6 ou 7).")
    elif campo == "cst_icms":
        for rotulo, v in (("original", orig), ("corrigido", novo)):
            if len(v) not in (2, 3, 4):
                raise ValueError(
                    f"CST {rotulo} invalido: {v!r} (esperado 2 a 4 digitos — "
                    "CST com origem ou CSOSN).")
    elif campo == "aliq_icms":
        # Valida o texto BRUTO: para_decimal transformaria lixo em 0.
        for rotulo, bruto in (("original", valor_original),
                              ("corrigido", valor_corrigido)):
            texto = str(bruto).strip()
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            try:
                aliq = Decimal(texto)
            except InvalidOperation as exc:
                raise ValueError(
                    f"Aliquota {rotulo} invalida: {bruto!r} (use numeros, "
                    "ex.: 20,50).") from exc
            if not Decimal("0") <= aliq <= Decimal("100"):
                raise ValueError(
                    f"Aliquota {rotulo} fora do intervalo 0-100%: {bruto}.")


def aplicar_correcoes(nota: NotaFiscal,
                      correcoes: list[Correcao]) -> NotaFiscal:
    """Retorna uma COPIA da nota com as correcoes ativas aplicadas.

    O original permanece intacto. Cada item corrigido guarda o valor
    importado em `corrigido_de[campo]` (o PRIMEIRO original, mesmo com
    correcoes encadeadas).
    """
    ativas = [c for c in correcoes if c.ativa]
    if not ativas:
        return nota
    corrigida = copy.deepcopy(nota)
    for correcao in ativas:
        campo = correcao.campo
        alvo = normalizar_valor(campo, correcao.valor_original)
        for item in corrigida.itens:
            atual = normalizar_valor(campo, getattr(item, campo))
            if atual != alvo:
                continue
            original_txt = str(getattr(item, campo))
            if campo == "aliq_icms":
                setattr(item, campo, para_decimal(correcao.valor_corrigido))
            else:
                setattr(item, campo,
                        normalizar_valor(campo, correcao.valor_corrigido))
            item.corrigido_de.setdefault(campo, original_txt)
    return corrigida


def descrever(correcao: Correcao) -> str:
    """Descricao curta da correcao para relatorios e status."""
    rotulo = CAMPOS_CORRIGIVEIS.get(correcao.campo, correcao.campo)
    situacao = "" if correcao.ativa else f" [{correcao.status}]"
    return (f"{rotulo}: {correcao.valor_original} -> "
            f"{correcao.valor_corrigido} ({correcao.tipo}, "
            f"{correcao.usuario}, {correcao.data_hora}){situacao}")
