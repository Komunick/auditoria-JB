"""Geracao do SPED Fiscal corrigido (EFD ICMS/IPI).

O projeto nao monta um SPED do zero: ele REESCREVE o arquivo original do
cliente aplicando as correcoes registradas na conferencia. Assim o leiaute,
a versao e todos os registros nao tratados sao preservados exatamente como
importados — sem presumir versao de leiaute diferente da que o arquivo usa.

O que e alterado:

- C170: campos CST_ICMS (posicao 10) e CFOP (posicao 11) dos itens cujo
  valor atual coincide com o valor original da correcao;
- C190 (registro analitico por CST/CFOP/aliquota): os grupos da nota sao
  re-derivados apos a correcao — grupos que passam a ter a mesma combinacao
  sao MESCLADOS somando VL_OPR, VL_BC_ICMS, VL_ICMS, VL_BC_ICMS_ST,
  VL_ICMS_ST, VL_RED_BC e VL_IPI (evitando duplicidade de registros);
- Contadores: C990/0990/9990/etc. (linhas por bloco), 9900 (linhas por
  registro) e 9999 (total) sao recalculados quando a mesclagem de C190
  reduz o numero de linhas.

O que NAO e alterado (limitacao documentada, exige validacao fiscal):

- Correcoes de ALIQUOTA nao sao levadas ao SPED nesta versao: alterariam
  valores de imposto e a apuracao (E110), o que este gerador nao recalcula.
  Elas sao listadas em `ignoradas` no resumo para tratamento manual.
- Notas cujos C190 tenham registros filhos (C191/FCP) nao sao mescladas:
  os campos sao corrigidos linha a linha e um aviso e emitido.

Sem correcoes aplicaveis, o arquivo gerado e IDENTICO ao original.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from ..core.correcoes import Correcao, normalizar_valor
from ..core.modelos import so_digitos
from ..core.utils import ler_texto, para_decimal

# Posicoes (layout EFD ICMS/IPI; REG = posicao 1)
_C170_CST, _C170_CFOP = 10, 11
_C190_CST, _C190_CFOP, _C190_ALIQ = 2, 3, 4
_C190_SOMAVEIS = (5, 6, 7, 8, 9, 10, 11)   # VL_OPR..VL_IPI
_C190_COD_OBS = 12


@dataclass
class ResumoSpedCorrigido:
    """Resultado da geracao do SPED corrigido."""

    caminho: str = ""
    itens_c170_alterados: int = 0
    c190_mesclados: int = 0            # linhas C190 removidas por mesclagem
    notas_alteradas: int = 0
    avisos: list[str] = field(default_factory=list)
    ignoradas: list[str] = field(default_factory=list)


def _fmt_valor(valor: Decimal) -> str:
    """Formata valor no padrao do SPED (virgula decimal, sem milhar)."""
    return f"{valor:.2f}".replace(".", ",")


def _campo(campos: list[str], pos: int) -> str:
    return campos[pos].strip() if 0 <= pos < len(campos) else ""


def _correcoes_sped(correcoes: list[Correcao],
                    resumo: ResumoSpedCorrigido) -> list[Correcao]:
    """Filtra as correcoes aplicaveis ao SPED (CFOP/CST ativas)."""
    aplicaveis = []
    for c in correcoes:
        if not c.ativa:
            continue
        if c.campo in ("cfop", "cst_icms"):
            aplicaveis.append(c)
        else:
            resumo.ignoradas.append(
                f"Nota {c.chave}: correcao de {c.campo} "
                f"({c.valor_original} -> {c.valor_corrigido}) nao aplicada ao "
                "SPED — altera valores de imposto/apuracao (E110); tratar "
                "manualmente com o responsavel fiscal.")
    return aplicaveis


def _aplicar_em_campos(campos: list[str], pos: int,
                       correcoes: list[Correcao], campo_nome: str) -> bool:
    """Aplica no campo da linha as correcoes cujo original coincide."""
    alterado = False
    for c in correcoes:
        if c.campo != campo_nome:
            continue
        atual = normalizar_valor(campo_nome, _campo(campos, pos))
        if atual and atual == c.valor_original:
            campos[pos] = c.valor_corrigido
            alterado = True
    return alterado


def _mesclar_c190(buffer: list[list[str]],
                  correcoes: list[Correcao],
                  resumo: ResumoSpedCorrigido, chave: str) -> list[str]:
    """Corrige e mescla um conjunto de C190 de uma nota. Retorna as linhas."""
    grupos: dict[tuple, list[str]] = {}
    ordem: list[tuple] = []
    for campos in buffer:
        _aplicar_em_campos(campos, _C190_CST, correcoes, "cst_icms")
        _aplicar_em_campos(campos, _C190_CFOP, correcoes, "cfop")
        chave_grupo = (
            normalizar_valor("cst_icms", _campo(campos, _C190_CST)),
            normalizar_valor("cfop", _campo(campos, _C190_CFOP)),
            str(para_decimal(_campo(campos, _C190_ALIQ))),
        )
        existente = grupos.get(chave_grupo)
        if existente is None:
            grupos[chave_grupo] = campos
            ordem.append(chave_grupo)
            continue
        # Mescla: soma os campos de valor no registro ja existente.
        for pos in _C190_SOMAVEIS:
            soma = (para_decimal(_campo(existente, pos))
                    + para_decimal(_campo(campos, pos)))
            if pos < len(existente):
                existente[pos] = _fmt_valor(soma)
        obs_a = _campo(existente, _C190_COD_OBS)
        obs_b = _campo(campos, _C190_COD_OBS)
        if obs_b and obs_a and obs_b != obs_a:
            resumo.avisos.append(
                f"Nota {chave}: C190 mesclados com COD_OBS distintos "
                f"({obs_a!r} mantido, {obs_b!r} descartado) — conferir.")
        elif obs_b and not obs_a and _C190_COD_OBS < len(existente):
            existente[_C190_COD_OBS] = obs_b
        resumo.c190_mesclados += 1
    return ["|".join(grupos[k]) for k in ordem]


def gerar_sped_corrigido(caminho_original: str, caminho_saida: str,
                         correcoes_por_chave: dict[str, list[Correcao]],
                         ) -> ResumoSpedCorrigido:
    """Gera o SPED corrigido a partir do arquivo original. Ver docstring."""
    resumo = ResumoSpedCorrigido(caminho=caminho_saida)
    aplicaveis: dict[str, list[Correcao]] = {}
    for chave, correcoes in (correcoes_por_chave or {}).items():
        filtradas = _correcoes_sped(correcoes, resumo)
        if filtradas:
            aplicaveis[chave] = filtradas

    linhas_originais = ler_texto(caminho_original).splitlines()
    saida: list[str] = []
    chaves_vistas: set[str] = set()

    correcoes_nota: list[Correcao] = []
    chave_nota = ""
    nota_alterada = False
    buffer_c190: list[list[str]] = []

    def _flush_c190(mesclar: bool = True) -> None:
        nonlocal nota_alterada
        if not buffer_c190:
            return
        antes = len(buffer_c190)
        if mesclar:
            novas = _mesclar_c190(buffer_c190, correcoes_nota, resumo,
                                  chave_nota)
        else:
            for campos in buffer_c190:
                _aplicar_em_campos(campos, _C190_CST, correcoes_nota,
                                   "cst_icms")
                _aplicar_em_campos(campos, _C190_CFOP, correcoes_nota, "cfop")
            novas = ["|".join(c) for c in buffer_c190]
            resumo.avisos.append(
                f"Nota {chave_nota}: C190 com registros filhos (C191) — "
                "campos corrigidos sem mesclagem; conferir se ha grupos "
                "duplicados.")
        if len(novas) != antes:
            nota_alterada = True
        saida.extend(novas)
        buffer_c190.clear()

    def _fechar_nota() -> None:
        nonlocal nota_alterada
        _flush_c190()
        if nota_alterada:
            resumo.notas_alteradas += 1
        nota_alterada = False

    for linha in linhas_originais:
        if not linha or "|" not in linha:
            _flush_c190()
            saida.append(linha)
            continue
        campos = linha.split("|")
        reg = _campo(campos, 1)

        if reg == "C100":
            _fechar_nota()
            chave_nota = so_digitos(_campo(campos, 9))
            correcoes_nota = aplicaveis.get(chave_nota, [])
            if correcoes_nota:
                chaves_vistas.add(chave_nota)
            saida.append(linha)
            continue

        if correcoes_nota and reg == "C170":
            _flush_c190()
            alterou_cst = _aplicar_em_campos(campos, _C170_CST,
                                             correcoes_nota, "cst_icms")
            alterou_cfop = _aplicar_em_campos(campos, _C170_CFOP,
                                              correcoes_nota, "cfop")
            if alterou_cst or alterou_cfop:
                resumo.itens_c170_alterados += 1
                nota_alterada = True
            saida.append("|".join(campos))
            continue

        if correcoes_nota and reg == "C190":
            buffer_c190.append(campos)
            continue

        if buffer_c190 and reg == "C191":
            # Filho de C190: nao e seguro mesclar os pais.
            _flush_c190(mesclar=False)
            saida.append(linha)
            continue

        _flush_c190()
        saida.append(linha)

    _fechar_nota()

    # Correcoes de notas que nao estao no arquivo: avisa (nada e aplicado).
    for chave in aplicaveis:
        if chave not in chaves_vistas:
            resumo.avisos.append(
                f"Nota {chave}: ha correcao registrada, mas a chave nao foi "
                "encontrada neste arquivo SPED.")

    saida = _atualizar_contadores(saida)

    with open(caminho_saida, "w", encoding="latin-1", errors="replace",
              newline="") as fh:
        fh.write("\r\n".join(saida))
        if saida:
            fh.write("\r\n")
    return resumo


def _atualizar_contadores(linhas: list[str]) -> list[str]:
    """Recalcula X990 (linhas por bloco), 9900 (por registro) e 9999 (total)."""
    regs = []
    for linha in linhas:
        partes = linha.split("|")
        regs.append(partes[1].strip() if len(partes) > 1 else "")
    validas = [r for r in regs if r]
    total = len(validas)
    por_reg = Counter(validas)
    por_bloco = Counter(r[0] for r in validas)

    resultado = []
    for linha, reg in zip(linhas, regs):
        if reg == "9999":
            campos = linha.split("|")
            if len(campos) > 2:
                campos[2] = str(total)
            linha = "|".join(campos)
        elif reg == "9900":
            campos = linha.split("|")
            if len(campos) > 3:
                campos[3] = str(por_reg.get(campos[2].strip(), 0))
            linha = "|".join(campos)
        elif len(reg) == 4 and reg.endswith("990"):
            campos = linha.split("|")
            if len(campos) > 2:
                campos[2] = str(por_bloco.get(reg[0], 0))
            linha = "|".join(campos)
        resultado.append(linha)
    return resultado
