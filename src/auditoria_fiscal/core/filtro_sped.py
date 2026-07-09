"""Filtro "Considerar apenas documentos de entrada no SPED".

Classificacao da natureza do documento usando os dados do proprio SPED,
nesta ordem de prioridade:

1. IND_OPER do registro C100 (campo 2): "0" = entrada, "1" = saida.
2. CFOP dos itens (registro C170), quando o IND_OPER nao veio preenchido:
   CFOP iniciado em 1/2/3 = entrada; iniciado em 5/6/7 = saida.
3. Sem nenhuma informacao disponivel, a nota e MANTIDA (beneficio da
   duvida) - preserva o comportamento historico do comparador SPED x SEFAZ,
   que nunca descartou notas sem IND_OPER.

O texto exibido nas telas e o rotulo carimbado nos relatorios ficam aqui
para que todas as ferramentas usem exatamente as mesmas mensagens.
"""

from __future__ import annotations

from .modelos import DocumentoFiscalConjunto, NotaFiscal

# Texto da opcao nas telas (identico em todas as abas).
TEXTO_OPCAO_ENTRADAS = "Considerar apenas documentos de entrada no SPED"

# Indicacao do filtro nos relatorios e resultados.
ROTULO_FILTRO_ENTRADAS = "Filtro aplicado: somente documentos de entrada no SPED"

# Aviso quando o filtro nao encontra nenhum documento de entrada.
MSG_SEM_ENTRADAS = ("Nenhum documento de entrada foi localizado no SPED "
                    "para os filtros selecionados.")

_CFOP_ENTRADA = ("1", "2", "3")
_CFOP_SAIDA = ("5", "6", "7")


def e_entrada(nota: NotaFiscal) -> bool:
    """True se a nota e classificada como documento de ENTRADA."""
    if nota.ind_oper == "0":
        return True
    if nota.ind_oper == "1":
        return False
    # IND_OPER ausente: decide pelo CFOP dos itens (dado do proprio SPED).
    for item in nota.itens:
        inicial = (item.cfop or "").strip()[:1]
        if inicial in _CFOP_ENTRADA:
            return True
        if inicial in _CFOP_SAIDA:
            return False
    return True  # sem informacao para classificar: mantem a nota


def filtrar_entradas(notas: list[NotaFiscal]) -> list[NotaFiscal]:
    """Somente as notas de entrada (ver criterio em e_entrada)."""
    return [nota for nota in notas if e_entrada(nota)]


def filtrar_documento_entradas(doc: DocumentoFiscalConjunto) -> DocumentoFiscalConjunto:
    """Copia do conjunto contendo apenas os documentos de entrada."""
    return DocumentoFiscalConjunto(empresa=doc.empresa,
                                   notas=filtrar_entradas(doc.notas))
