"""Item 1 - Comparacao entre a relacao da SEFAZ e o SPED Fiscal.

Objetivo: identificar notas emitidas contra o CNPJ do cliente que constam na
SEFAZ mas NAO foram escrituradas no SPED, alem de outras divergencias uteis
antes da entrega das obrigacoes acessorias.

O cruzamento e feito pela chave de acesso (44 digitos), presente tanto no C100
do SPED (CHV_NFE) quanto na relacao da SEFAZ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..core.modelos import DocumentoFiscalConjunto, NotaFiscal
from ..core.sefaz_relacao import RegistroSefaz


TOLERANCIA_VALOR = Decimal("0.01")


@dataclass
class DivergenciaValor:
    chave: str
    numero: str
    emitente: str
    valor_sefaz: Decimal
    valor_sped: Decimal

    @property
    def diferenca(self) -> Decimal:
        return (self.valor_sped - self.valor_sefaz).copy_abs()


@dataclass
class NotaCanceladaEscriturada:
    chave: str
    numero: str
    emitente: str
    situacao_sefaz: str


@dataclass
class ResultadoComparacao:
    # Foco principal: na SEFAZ (autorizadas) e ausentes no SPED.
    faltantes_no_sped: list[RegistroSefaz] = field(default_factory=list)
    # Escrituradas no SPED como regulares, porem canceladas/denegadas na SEFAZ.
    canceladas_escrituradas: list[NotaCanceladaEscriturada] = field(default_factory=list)
    # Presentes em ambos, mas com valor total divergente.
    divergencias_valor: list[DivergenciaValor] = field(default_factory=list)
    # Escrituradas no SPED sem correspondencia na relacao SEFAZ (informativo).
    apenas_no_sped: list[NotaFiscal] = field(default_factory=list)

    total_sefaz: int = 0
    total_sped: int = 0
    total_conciliadas: int = 0

    def tem_pendencias(self) -> bool:
        return bool(self.faltantes_no_sped or self.canceladas_escrituradas
                    or self.divergencias_valor)

    def resumo(self) -> dict:
        return {
            "notas_na_sefaz": self.total_sefaz,
            "notas_no_sped": self.total_sped,
            "conciliadas": self.total_conciliadas,
            "faltantes_no_sped": len(self.faltantes_no_sped),
            "canceladas_escrituradas": len(self.canceladas_escrituradas),
            "divergencias_valor": len(self.divergencias_valor),
            "apenas_no_sped": len(self.apenas_no_sped),
        }


def comparar(
    doc_sped: DocumentoFiscalConjunto,
    registros_sefaz: list[RegistroSefaz],
    tolerancia_valor: Decimal = TOLERANCIA_VALOR,
    apenas_entradas: bool = True,
) -> ResultadoComparacao:
    """Compara o SPED com a relacao da SEFAZ e retorna o resultado.

    apenas_entradas: quando True, a comparacao considera no SPED apenas os
    documentos de entrada (IND_OPER = 0), pois a relacao da SEFAZ lista as notas
    emitidas CONTRA o CNPJ do cliente (entradas). Notas de saida escrituradas
    ficam de fora do cruzamento.
    """
    # Indice do SPED por chave (considerando o filtro de entradas).
    sped_por_chave: dict[str, NotaFiscal] = {}
    for nota in doc_sped.notas:
        chave = nota.chave_normalizada
        if len(chave) != 44:
            continue
        if apenas_entradas and nota.ind_oper not in ("0", ""):
            continue
        sped_por_chave[chave] = nota

    # Indice da SEFAZ por chave (deduplica, mantendo a ultima ocorrencia).
    sefaz_por_chave: dict[str, RegistroSefaz] = {}
    for reg in registros_sefaz:
        if len(reg.chave_normalizada) == 44:
            sefaz_por_chave[reg.chave_normalizada] = reg

    resultado = ResultadoComparacao(
        total_sefaz=len(sefaz_por_chave),
        total_sped=len(sped_por_chave),
    )

    conciliadas = 0
    for chave, reg in sefaz_por_chave.items():
        nota = sped_por_chave.get(chave)
        if nota is None:
            # Nao esta no SPED. So e pendencia se estiver autorizada na SEFAZ.
            if reg.autorizada:
                resultado.faltantes_no_sped.append(reg)
            continue

        conciliadas += 1

        # Cancelada/denegada na SEFAZ mas escriturada como regular no SPED.
        if (reg.cancelada or reg.denegada) and not (nota.cancelada or nota.denegada):
            resultado.canceladas_escrituradas.append(NotaCanceladaEscriturada(
                chave=chave,
                numero=nota.numero or reg.numero,
                emitente=_nome_emitente(nota, reg),
                situacao_sefaz=reg.situacao or ("cancelada" if reg.cancelada else "denegada"),
            ))

        # Divergencia de valor total (apenas quando a SEFAZ informa valor).
        if reg.valor > 0 and (nota.valor_documento - reg.valor).copy_abs() > tolerancia_valor:
            resultado.divergencias_valor.append(DivergenciaValor(
                chave=chave,
                numero=nota.numero or reg.numero,
                emitente=_nome_emitente(nota, reg),
                valor_sefaz=reg.valor,
                valor_sped=nota.valor_documento,
            ))

    resultado.total_conciliadas = conciliadas

    # Escrituradas sem correspondencia na SEFAZ (informativo).
    for chave, nota in sped_por_chave.items():
        if chave not in sefaz_por_chave:
            resultado.apenas_no_sped.append(nota)

    # Ordena as faltantes por data/numero para leitura no relatorio.
    resultado.faltantes_no_sped.sort(
        key=lambda r: (r.dt_emissao or _DATA_MIN, r.numero)
    )
    return resultado


def _nome_emitente(nota: Optional[NotaFiscal], reg: RegistroSefaz) -> str:
    if nota is not None and nota.participante and nota.participante.nome:
        return nota.participante.nome
    return reg.emitente_nome or reg.cnpj_emitente_da_chave


from datetime import date as _date  # noqa: E402
_DATA_MIN = _date(1900, 1, 1)
