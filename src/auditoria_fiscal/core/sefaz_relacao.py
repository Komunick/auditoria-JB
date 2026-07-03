"""Leitor da relacao de documentos da SEFAZ.

A SEFAZ (e portais estaduais / consultas de NF-e destinadas) exportam a relacao
de notas emitidas contra o CNPJ do contribuinte em varios formatos (xlsx, csv),
com nomes de coluna e linhas de titulo que variam por estado/origem.

Este leitor e deliberadamente TOLERANTE:
  * detecta a linha de cabecalho procurando palavras-chave;
  * mapeia colunas por aproximacao (chave, numero, emitente, valor, situacao,
    data), sem acento e sem diferenciar maiusculas;
  * se nao achar coluna "chave" pelo nome, identifica a coluna cujos valores sao
    majoritariamente numeros de 44 digitos.

>>> Ajustar/confirmar o mapeamento quando houver a amostra real do cliente. <<<
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

import pandas as pd

from .modelos import so_digitos
from .utils import para_data, para_decimal


# ----------------------------------------------------------------------
# Modelo de um registro da relacao SEFAZ (uma linha da planilha).
# ----------------------------------------------------------------------
@dataclass
class RegistroSefaz:
    chave: str = ""
    numero: str = ""
    serie: str = ""
    modelo: str = ""
    emitente_cnpj: str = ""
    emitente_nome: str = ""
    dt_emissao: Optional[date] = None
    valor: Decimal = Decimal("0")
    situacao: str = ""          # texto original (ex.: "Autorizada", "Cancelada")

    @property
    def chave_normalizada(self) -> str:
        return so_digitos(self.chave)

    @property
    def cancelada(self) -> bool:
        return "cancel" in _sem_acento(self.situacao)

    @property
    def denegada(self) -> bool:
        return "deneg" in _sem_acento(self.situacao)

    @property
    def autorizada(self) -> bool:
        # Sem situacao informada, tratamos como autorizada (a relacao geralmente
        # so lista documentos validos, salvo coluna explicita).
        return not self.cancelada and not self.denegada

    @property
    def cnpj_emitente_da_chave(self) -> str:
        chv = self.chave_normalizada
        return chv[6:20] if len(chv) == 44 else so_digitos(self.emitente_cnpj)


# ----------------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# Palavras-chave que identificam cada campo no cabecalho.
_MAPA_COLUNAS = {
    "chave": ["chave", "chave de acesso", "chave nfe", "chave nf-e"],
    "numero": ["numero", "num nf", "nº nf", "no nf", "nf", "numero nfe", "numero da nota"],
    "serie": ["serie"],
    "modelo": ["modelo", "mod"],
    "emitente_cnpj": ["cnpj emitente", "cnpj do emitente", "cnpj emit", "cpf/cnpj",
                       "cnpj", "cnpj/cpf"],
    "emitente_nome": ["razao social", "nome emitente", "emitente", "razao",
                      "nome do emitente", "fornecedor"],
    "valor": ["valor total", "valor da nota", "valor nf", "vl total", "valor",
              "valor total da nota"],
    "situacao": ["situacao", "situacao nfe", "status", "situacao da nota",
                 "situacao do documento"],
    "dt_emissao": ["data emissao", "dt emissao", "emissao", "data de emissao",
                   "data"],
}


def _melhor_aba(xls: "pd.ExcelFile") -> str:
    """Escolhe a aba com os dados da SEFAZ em planilhas de varias abas.

    Prioriza abas cujo nome remete a SEFAZ; senao, a que tem mais palavras-chave
    de cabecalho. Evita, por exemplo, a aba auxiliar 'Sped' de planilhas manuais.
    """
    nomes = xls.sheet_names
    if len(nomes) == 1:
        return nomes[0]
    for nome in nomes:
        if any(p in _sem_acento(nome)
               for p in ("sefaz", "relacao", "destinada", "emitida", "nfe")):
            return nome
    palavras = {"chave", "numero", "valor", "emitente", "situacao", "cnpj", "razao"}
    melhor, melhor_pont = nomes[0], -1
    for nome in nomes:
        df = pd.read_excel(xls, sheet_name=nome, header=None, dtype=str, nrows=30)
        pont = 0
        for idx in range(len(df)):
            celulas = [_sem_acento(c) for c in df.iloc[idx].tolist() if c is not None]
            pont = max(pont, sum(1 for cel in celulas
                                 if any(p in cel for p in palavras)))
        if pont > melhor_pont:
            melhor_pont, melhor = pont, nome
    return melhor


def _carregar_dataframe(caminho: str) -> pd.DataFrame:
    """Carrega o arquivo como DataFrame de strings, sem assumir cabecalho."""
    lower = caminho.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        xls = pd.ExcelFile(caminho)
        aba = _melhor_aba(xls)
        return pd.read_excel(xls, sheet_name=aba, header=None, dtype=str)
    # CSV/TXT: tenta ; depois ,  (SEFAZ costuma usar ; e latin-1).
    for sep in (";", ",", "\t"):
        try:
            df = pd.read_csv(caminho, header=None, dtype=str, sep=sep,
                             encoding="latin-1", engine="python")
            if df.shape[1] > 1:
                return df
        except Exception:  # noqa: BLE001
            continue
    return pd.read_csv(caminho, header=None, dtype=str, encoding="latin-1",
                       engine="python")


def _detectar_linha_cabecalho(df: pd.DataFrame) -> int:
    """Acha a linha que parece ser o cabecalho (contem palavras-chave)."""
    palavras = {"chave", "numero", "valor", "emitente", "situacao", "cnpj",
                "razao", "data"}
    melhor_idx, melhor_pont = 0, -1
    for idx in range(min(len(df), 30)):  # cabecalho costuma estar no topo
        celulas = [_sem_acento(c) for c in df.iloc[idx].tolist() if c is not None]
        pont = sum(1 for cel in celulas if any(p in cel for p in palavras))
        if pont > melhor_pont:
            melhor_pont, melhor_idx = pont, idx
    return melhor_idx if melhor_pont > 0 else 0


def _mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    """Associa cada campo ao indice de coluna, por aproximacao de nome."""
    normalizado = [_sem_acento(c) for c in cabecalho]
    mapa: dict[str, int] = {}
    usados: set[int] = set()
    for campo, chaves in _MAPA_COLUNAS.items():
        # Ordena chaves da mais especifica (maior) para a mais curta.
        for alvo in sorted(chaves, key=len, reverse=True):
            for i, nome in enumerate(normalizado):
                if i in usados or not nome:
                    continue
                if nome == alvo or alvo in nome:
                    mapa[campo] = i
                    usados.add(i)
                    break
            if campo in mapa:
                break
    return mapa


def _coluna_chave_por_conteudo(df: pd.DataFrame) -> Optional[int]:
    """Acha a coluna cujos valores sao majoritariamente chaves de 44 digitos."""
    melhor_col, melhor_taxa = None, 0.0
    for col in df.columns:
        valores = df[col].dropna().astype(str)
        if len(valores) == 0:
            continue
        acertos = sum(1 for v in valores if len(so_digitos(v)) == 44)
        taxa = acertos / len(valores)
        if taxa > melhor_taxa:
            melhor_taxa, melhor_col = taxa, col
    return melhor_col if melhor_taxa >= 0.5 else None


def ler_relacao_sefaz(caminho: str) -> tuple[list[RegistroSefaz], dict]:
    """Le a relacao da SEFAZ. Retorna (registros, diagnostico).

    O diagnostico traz o mapeamento de colunas detectado, util para conferir se a
    deteccao automatica acertou o layout do arquivo.
    """
    df_bruto = _carregar_dataframe(caminho)
    linha_cab = _detectar_linha_cabecalho(df_bruto)
    cabecalho = [("" if c is None else str(c)) for c in df_bruto.iloc[linha_cab].tolist()]
    dados = df_bruto.iloc[linha_cab + 1:].reset_index(drop=True)

    mapa = _mapear_colunas(cabecalho)

    # Se nao achou a chave pelo nome, procura pelo conteudo.
    if "chave" not in mapa:
        col_chave = _coluna_chave_por_conteudo(dados)
        if col_chave is not None:
            mapa["chave"] = col_chave

    def pega(linha, campo: str) -> str:
        idx = mapa.get(campo)
        if idx is None or idx >= len(linha):
            return ""
        val = linha[idx]
        return "" if val is None else str(val).strip()

    registros: list[RegistroSefaz] = []
    for _, serie_linha in dados.iterrows():
        linha = serie_linha.tolist()
        chave = so_digitos(pega(linha, "chave"))
        # Ignora linhas de rodape/total sem chave valida.
        if len(chave) != 44:
            continue
        registros.append(RegistroSefaz(
            chave=chave,
            numero=pega(linha, "numero"),
            serie=pega(linha, "serie"),
            modelo=pega(linha, "modelo"),
            emitente_cnpj=so_digitos(pega(linha, "emitente_cnpj")),
            emitente_nome=pega(linha, "emitente_nome"),
            dt_emissao=para_data(pega(linha, "dt_emissao")),
            valor=para_decimal(pega(linha, "valor")),
            situacao=pega(linha, "situacao"),
        ))

    diagnostico = {
        "linha_cabecalho": linha_cab,
        "cabecalho_detectado": cabecalho,
        "mapa_colunas": {k: cabecalho[v] if v < len(cabecalho) else f"col{v}"
                         for k, v in mapa.items()},
        "total_linhas_dados": len(dados),
        "registros_validos": len(registros),
    }
    return registros, diagnostico
