"""Ferramenta 5 - Aplicacao das correcoes sugeridas pela auditoria.

Transforma os resultados da auditoria com correcao proposta no dict de
`alteracoes` esperado por `core.cadastro_produtos.gerar_nova_base`, marca os
resultados como corrigidos e grava um historico auditavel em CSV (uma linha
por campo alterado), por padrao em
%LOCALAPPDATA%/AuditoriaFiscal/historico_produtos.csv.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime

from .auditoria_produtos import CONF_ALTA, ResultadoAuditoria

CABECALHO_HISTORICO = ["data_hora", "arquivo_base", "codigo", "descricao",
                       "campo", "valor_anterior", "valor_novo", "confianca",
                       "tipos", "fundamentacao"]

# Campos simples aceitos por gerar_nova_base (ordem estavel no historico).
_CAMPOS_SIMPLES = ("ncm", "cest", "cst", "aliquota")


def caminho_historico_padrao() -> str:
    """Caminho padrao do historico (cria a pasta AuditoriaFiscal se preciso)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    pasta = os.path.join(base, "AuditoriaFiscal")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, "historico_produtos.csv")


def selecionar_alta_confianca(
        resultados: list[ResultadoAuditoria]) -> list[ResultadoAuditoria]:
    """Resultados auto-corrigiveis: correcao proposta com confianca alta."""
    return [r for r in resultados
            if r.tem_correcao and r.confianca == CONF_ALTA
            and r.situacao == "INCONSISTENTE"]


def _valor_atual(produto, campo: str) -> str:
    """Valor atual do campo no produto, como texto (para o historico)."""
    if campo == "aliquota":
        if produto.aliquota is None:
            return ""
        return str(produto.aliquota).replace(".", ",")
    return str(getattr(produto, campo, "") or "")


def _gravar_historico(caminho: str, linhas: list[list[str]]) -> None:
    """Anexa linhas ao historico CSV (cria com cabecalho se nao existe)."""
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    novo = not os.path.exists(caminho) or os.path.getsize(caminho) == 0
    # utf-8-sig apenas na criacao (BOM uma unica vez, no inicio do arquivo).
    encoding = "utf-8-sig" if novo else "utf-8"
    with open(caminho, "a", newline="", encoding=encoding) as fh:
        escritor = csv.writer(fh, delimiter=";")
        if novo:
            escritor.writerow(CABECALHO_HISTORICO)
        escritor.writerows(linhas)


def aplicar_correcoes(resultados: list[ResultadoAuditoria], arquivo_base: str,
                      caminho_historico: str | None = None
                      ) -> dict[int, dict[str, object]]:
    """Aplica as correcoes dos resultados informados.

    Para cada resultado com correcao proposta, monta a entrada de
    `alteracoes` no formato de `gerar_nova_base` (indice do produto ->
    campos + cfop_map), marca `status_correcao = "Corrigido"` e grava no
    historico uma linha por campo alterado. Retorna o dict de alteracoes.
    """
    if caminho_historico is None:
        caminho_historico = caminho_historico_padrao()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alteracoes: dict[int, dict[str, object]] = {}
    linhas: list[list[str]] = []
    for res in resultados:
        if not res.tem_correcao:
            continue
        produto = res.produto
        entrada: dict[str, object] = {}
        for campo in _CAMPOS_SIMPLES:
            if campo not in res.correcoes:
                continue
            novo = str(res.correcoes[campo])
            entrada[campo] = novo
            linhas.append([agora, arquivo_base, produto.codigo,
                           produto.descricao, campo,
                           _valor_atual(produto, campo), novo,
                           res.confianca, res.tipos, res.fundamentacao])
        if res.cfop_map:
            entrada["cfop_map"] = dict(res.cfop_map)
            for de, para in res.cfop_map.items():
                linhas.append([agora, arquivo_base, produto.codigo,
                               produto.descricao, f"cfop {de}->{para}",
                               de, para, res.confianca, res.tipos,
                               res.fundamentacao])
        alteracoes[produto.indice] = entrada
        res.status_correcao = "Corrigido"
    if linhas:
        _gravar_historico(caminho_historico, linhas)
    return alteracoes
