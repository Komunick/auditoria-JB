"""Bases legais atualizaveis para a auditoria do cadastro de produtos.

As tabelas legais (Anexo I do RICMS/BA, TIPI, monofasico, isencoes, reducoes
de base e diferimento) ficam em arquivos CSV na pasta dados/, editaveis pelo
usuario sem alterar o codigo. Este modulo:

  * localiza a pasta dados/ (exe congelado, LOCALAPPDATA, projeto em dev,
    dados empacotados no exe);
  * carrega os CSVs de forma TOLERANTE: arquivo ausente/vazio vira aviso,
    linhas iniciadas com "#" e vazias sao ignoradas, colunas sao mapeadas
    por nome (sem acento, minusculas);
  * busca itens do Anexo I por CEST/NCM (prioridade cest > ncm8 > prefixo
    mais longo; empate resolvido pela similaridade de descricao);
  * busca regras tributarias (monofasico, isencao, reducao, diferimento)
    pelo prefixo de NCM mais longo;
  * calcula similaridade de descricoes (SequenceMatcher + jaccard de tokens).
"""

from __future__ import annotations

import csv
import difflib
import json
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from .modelos import so_digitos
from .utils import para_decimal


# ----------------------------------------------------------------------
# Nomes dos arquivos esperados na pasta dados/.
# ----------------------------------------------------------------------
ARQ_ANEXO1 = "anexo1_ba.csv"
ARQ_TIPI = "ncm_tipi.csv"
ARQ_MONOFASICO = "monofasico.csv"
ARQ_ISENCAO = "isencao_ba.csv"
ARQ_REDUCAO = "reducao_base_ba.csv"
ARQ_DIFERIMENTO = "diferimento_ba.csv"
ARQ_PARAMETROS = "parametros.json"

_ALIQUOTA_FALLBACK = Decimal("20.5")


# ----------------------------------------------------------------------
# Modelos.
# ----------------------------------------------------------------------
@dataclass
class ItemAnexo1:
    """Item do Anexo I do RICMS/BA (produtos sujeitos a ST)."""

    cest: str            # 7 digitos (ou "" se nao houver)
    ncm: str             # prefixo de 2 a 8 digitos (so digitos)
    descricao: str
    segmento: str = ""
    fundamentacao: str = ""


@dataclass
class RegraTributaria:
    """Regra por NCM (monofasico, isencao, reducao de base, diferimento)."""

    ncm: str             # prefixo (so digitos)
    descricao: str = ""
    fundamentacao: str = ""
    detalhe: str = ""    # ex.: carga efetiva, condicao


@dataclass
class MatchAnexo1:
    """Resultado de uma busca no Anexo I."""

    item: ItemAnexo1
    criterio: str        # "cest" | "ncm8" | "ncm_prefixo"
    tamanho_prefixo: int  # len do ncm do item que casou (0 p/ criterio cest sem ncm)
    similaridade: float  # descricao produto x descricao item (0..1)


# ----------------------------------------------------------------------
# Normalizacao e similaridade de textos.
# ----------------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    """Remove acentos, baixa a caixa e apara espacos (nomes de coluna)."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def normalizar_descricao(texto: str) -> str:
    """Normaliza descricao: sem acento, minusculas, sem pontuacao, espacos unicos."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    limpo = "".join(c if c.isalnum() else " " for c in sem_acento)
    return " ".join(limpo.split())


def similaridade(a: str, b: str) -> float:
    """Similaridade 0..1 entre descricoes: max(SequenceMatcher, jaccard).

    Normaliza as duas entradas; o jaccard usa os conjuntos de tokens com
    pelo menos 3 caracteres (|intersecao| / |uniao|).
    """
    norm_a, norm_b = normalizar_descricao(a), normalizar_descricao(b)
    if not norm_a or not norm_b:
        return 0.0
    razao = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    tokens_a = {t for t in norm_a.split() if len(t) >= 3}
    tokens_b = {t for t in norm_b.split() if len(t) >= 3}
    uniao = tokens_a | tokens_b
    jaccard = len(tokens_a & tokens_b) / len(uniao) if uniao else 0.0
    return max(razao, jaccard)


# Prioridade dos criterios de match do Anexo I (maior = melhor).
_PRIORIDADE_CRITERIO = {"cest": 2, "ncm8": 1, "ncm_prefixo": 0}


def _chave_match(m: MatchAnexo1) -> tuple[int, int, float]:
    """Chave de ordenacao: criterio > prefixo mais longo > similaridade."""
    prefixo = m.tamanho_prefixo if m.criterio == "ncm_prefixo" else 0
    return (_PRIORIDADE_CRITERIO.get(m.criterio, -1), prefixo, m.similaridade)


# ----------------------------------------------------------------------
# Conjunto das bases legais.
# ----------------------------------------------------------------------
@dataclass
class BaseLegal:
    """Bases legais carregadas da pasta dados/ (ou vazias, com avisos)."""

    pasta: str | None = None
    anexo1: list[ItemAnexo1] = field(default_factory=list)
    tipi: set[str] = field(default_factory=set)          # NCMs 8 digitos
    monofasico: list[RegraTributaria] = field(default_factory=list)
    isencao: list[RegraTributaria] = field(default_factory=list)
    reducao: list[RegraTributaria] = field(default_factory=list)
    diferimento: list[RegraTributaria] = field(default_factory=list)
    parametros: dict = field(default_factory=dict)       # de parametros.json
    avisos: list[str] = field(default_factory=list)      # arquivos ausentes etc.

    @property
    def tipi_ativa(self) -> bool:
        """Validacao TIPI so ativa com a tabela razoavelmente completa."""
        return len(self.tipi) >= 1000

    @property
    def aliquota_padrao(self) -> Decimal:
        """Aliquota interna padrao (parametros.json); fallback 20.5."""
        valor = self.parametros.get("aliquota_interna_padrao")
        if valor is None:
            return _ALIQUOTA_FALLBACK
        convertido = para_decimal(str(valor))
        return convertido if convertido > 0 else _ALIQUOTA_FALLBACK

    def buscar_anexo1(self, ncm: str, cest: str, descricao: str) -> MatchAnexo1 | None:
        """Melhor item do Anexo I para o produto informado.

        Candidatos: cest igual ("cest"), ncm de 8 digitos igual ("ncm8") e
        ncm do item (2..7 digitos) prefixo do ncm do produto ("ncm_prefixo").
        Prioridade cest > ncm8 > prefixo mais longo; empate decidido pela
        maior similaridade de descricao. None se nada casa.
        """
        ncm_prod = so_digitos(ncm)
        cest_prod = so_digitos(cest)
        candidatos: list[MatchAnexo1] = []
        for item in self.anexo1:
            criterio = ""
            if cest_prod and item.cest and item.cest == cest_prod:
                criterio = "cest"
            elif ncm_prod and len(item.ncm) == 8 and item.ncm == ncm_prod:
                criterio = "ncm8"
            elif ncm_prod and 2 <= len(item.ncm) <= 7 and ncm_prod.startswith(item.ncm):
                criterio = "ncm_prefixo"
            if not criterio:
                continue
            candidatos.append(MatchAnexo1(
                item=item,
                criterio=criterio,
                tamanho_prefixo=len(item.ncm),
                similaridade=similaridade(descricao, item.descricao),
            ))
        if not candidatos:
            return None
        return max(candidatos, key=_chave_match)

    def buscar_regra(self, regras: list[RegraTributaria],
                     ncm: str) -> RegraTributaria | None:
        """Regra cujo NCM (prefixo) mais longo casa com o NCM informado."""
        ncm_prod = so_digitos(ncm)
        if not ncm_prod:
            return None
        melhor: RegraTributaria | None = None
        for regra in regras:
            if regra.ncm and ncm_prod.startswith(regra.ncm):
                if melhor is None or len(regra.ncm) > len(melhor.ncm):
                    melhor = regra
        return melhor


# ----------------------------------------------------------------------
# Localizacao da pasta dados/.
# ----------------------------------------------------------------------
def localizar_pasta_dados() -> str | None:
    """Primeiro caminho existente da pasta dados/, ou None.

    Ordem: (1) pasta dados ao lado do executavel congelado; (2)
    %LOCALAPPDATA%/AuditoriaFiscal/dados; (3) raiz do projeto em dev;
    (4) dados empacotados no exe (sys._MEIPASS).
    """
    candidatos: list[str] = []
    if getattr(sys, "frozen", False):
        candidatos.append(os.path.join(os.path.dirname(sys.executable), "dados"))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidatos.append(os.path.join(local_appdata, "AuditoriaFiscal", "dados"))
    # .../src/auditoria_fiscal/core/ -> sobe 3 niveis = raiz do projeto.
    pasta_core = os.path.dirname(os.path.abspath(__file__))
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(pasta_core)))
    candidatos.append(os.path.join(raiz, "dados"))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.append(os.path.join(meipass, "dados"))
    for cand in candidatos:
        if os.path.isdir(cand):
            return cand
    return None


# ----------------------------------------------------------------------
# Leitura dos arquivos da pasta dados/.
# ----------------------------------------------------------------------
def _ler_texto_arquivo(caminho: str) -> str:
    """Le o arquivo tentando utf-8-sig e caindo para latin-1."""
    with open(caminho, "rb") as fh:
        bruto = fh.read()
    try:
        return bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def _ler_csv(pasta: str, nome: str, avisos: list[str]) -> list[dict[str, str]]:
    """Le um CSV (sep ';') como lista de dicts {coluna normalizada: valor}.

    Tolerante: arquivo ausente ou sem linhas de dados gera aviso e lista
    vazia; linhas vazias e iniciadas com '#' sao ignoradas; a primeira
    linha util e o cabecalho.
    """
    caminho = os.path.join(pasta, nome)
    if not os.path.exists(caminho):
        avisos.append(f"Arquivo ausente na pasta dados: {nome}")
        return []
    texto = _ler_texto_arquivo(caminho)
    uteis = [ln for ln in texto.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if len(uteis) < 2:
        avisos.append(f"Arquivo sem linhas de dados: {nome}")
        return []
    linhas = list(csv.reader(uteis, delimiter=";"))
    cabecalho = [_sem_acento(c) for c in linhas[0]]
    registros: list[dict[str, str]] = []
    for partes in linhas[1:]:
        registros.append({col: (partes[i].strip() if i < len(partes) else "")
                          for i, col in enumerate(cabecalho) if col})
    return registros


def _carregar_anexo1(pasta: str, avisos: list[str]) -> list[ItemAnexo1]:
    itens: list[ItemAnexo1] = []
    for reg in _ler_csv(pasta, ARQ_ANEXO1, avisos):
        cest = so_digitos(reg.get("cest", ""))
        ncm = so_digitos(reg.get("ncm", ""))
        if not cest and not ncm:
            continue
        itens.append(ItemAnexo1(
            cest=cest,
            ncm=ncm,
            descricao=reg.get("descricao", ""),
            segmento=reg.get("segmento", ""),
            fundamentacao=reg.get("fundamentacao", ""),
        ))
    return itens


def _carregar_tipi(pasta: str, avisos: list[str]) -> set[str]:
    ncms: set[str] = set()
    for reg in _ler_csv(pasta, ARQ_TIPI, avisos):
        ncm = so_digitos(reg.get("ncm", ""))
        if len(ncm) == 8:
            ncms.add(ncm)
    return ncms


def _carregar_regras(pasta: str, nome: str,
                     avisos: list[str]) -> list[RegraTributaria]:
    regras: list[RegraTributaria] = []
    for reg in _ler_csv(pasta, nome, avisos):
        ncm = so_digitos(reg.get("ncm", ""))
        if not ncm:
            continue
        regras.append(RegraTributaria(
            ncm=ncm,
            descricao=reg.get("descricao", ""),
            fundamentacao=reg.get("fundamentacao", ""),
            detalhe=reg.get("detalhe", ""),
        ))
    return regras


def _carregar_parametros(pasta: str, avisos: list[str]) -> dict:
    caminho = os.path.join(pasta, ARQ_PARAMETROS)
    if not os.path.exists(caminho):
        avisos.append(f"Arquivo ausente na pasta dados: {ARQ_PARAMETROS}")
        return {}
    try:
        dados = json.loads(_ler_texto_arquivo(caminho))
    except (ValueError, OSError):
        avisos.append(f"Arquivo invalido (JSON): {ARQ_PARAMETROS}")
        return {}
    if not isinstance(dados, dict):
        avisos.append(f"Conteudo inesperado em {ARQ_PARAMETROS} "
                      "(esperado objeto JSON).")
        return {}
    return dados


def carregar_base_legal(pasta: str | None = None) -> BaseLegal:
    """Carrega as bases legais da pasta informada (ou da pasta dados/ padrao).

    Nunca lanca erro por arquivo ausente: cada falta vira uma entrada em
    `avisos` e a lista correspondente fica vazia.
    """
    if pasta is None:
        pasta = localizar_pasta_dados()
    base = BaseLegal(pasta=pasta)
    if pasta is None:
        base.avisos.append(
            "Pasta dados/ nao localizada; bases legais vazias "
            "(validacoes contra o Anexo I ficam limitadas)."
        )
        return base
    base.anexo1 = _carregar_anexo1(pasta, base.avisos)
    base.tipi = _carregar_tipi(pasta, base.avisos)
    base.monofasico = _carregar_regras(pasta, ARQ_MONOFASICO, base.avisos)
    base.isencao = _carregar_regras(pasta, ARQ_ISENCAO, base.avisos)
    base.reducao = _carregar_regras(pasta, ARQ_REDUCAO, base.avisos)
    base.diferimento = _carregar_regras(pasta, ARQ_DIFERIMENTO, base.avisos)
    base.parametros = _carregar_parametros(pasta, base.avisos)
    return base
