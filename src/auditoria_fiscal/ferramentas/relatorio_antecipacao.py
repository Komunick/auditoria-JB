"""Planilha da apuracao da Antecipacao/DIFAL do ICMS-BA (spec 027).

Modulo PURO: recebe as linhas ja consultadas e um caminho de destino. A
escrita segura vem de `core/planilha_segura` — descricao de produto e nome de
fornecedor chegam de XML de terceiros, e um texto comecando por `=` viraria
formula ao abrir a planilha.

Tres abas: "Itens" (a memoria de calculo completa, secao 7 da especificacao),
"Totais" (por empresa e competencia) e "Metadados" (quem gerou, filtros e os
avisos que acompanham o numero).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook

from ..core import antecipacao_ba as ab
from ..core.planilha_segura import (cnpj_formatado, escrever_cabecalho,
                                    escrever_moeda, escrever_texto,
                                    salvar_atomico)
from .antecipacao_store import ESTADOS

AVISO_HOMOLOGACAO = (
    "Cálculo de apoio à conferência. Método, enquadramento e crédito de "
    "referência dependem da homologação da equipe fiscal; o crédito de "
    "referência não é crédito escritural do Simples Nacional.")
AVISO_REDUCAO = (
    "A redução é simulação: a elegibilidade (art. 274 do RICMS/BA) e o "
    "pagamento até o vencimento não são verificados pelo sistema.")


def _centavos_texto(texto) -> int | None:
    valor = ab.para_decimal(texto)
    return ab.centavos(valor) if valor is not None else None


def _percentual(aba, linha: int, coluna: int, texto) -> None:
    valor = ab.para_decimal(texto)
    celula = aba.cell(row=linha, column=coluna)
    if valor is None:
        celula.value = None
        return
    celula.value = valor / Decimal(100)
    celula.number_format = "0.00%"


def _data_br(iso: str) -> str:
    try:
        ano, mes, dia = iso[:10].split("-")
        return f"{dia}/{mes}/{ano}"
    except ValueError:
        return iso or ""


def _competencia_br(competencia: str) -> str:
    try:
        ano, mes = competencia.split("-")
        return f"{mes}/{ano}"
    except ValueError:
        return competencia or ""


def gerar_apuracao(destino: str, *, itens: list[dict], totais: list[dict],
                   gerado_por: str, filtros: dict | None = None) -> str:
    livro = Workbook()
    aba = livro.active
    aba.title = "Itens"
    escrever_cabecalho(aba, [
        "Competência", "Empresa", "CNPJ", "Nota", "Chave de acesso", "Emissão",
        "Fornecedor", "UF origem", "Item", "Produto", "NCM", "CFOP",
        "CST/CSOSN", "Finalidade", "Método", "Valor da operação",
        "Alíq. interestadual", "Tipo de crédito", "Crédito", "Alíq. interna",
        "Divisor", "Base de cálculo", "ICMS interno", "A recolher",
        "Pelo outro método", "Decisão", "Motivo da decisão", "Decidido por",
        "Pendências e avisos", "Situação da nota"])
    linha = 2
    for item in itens:
        memoria = item["memoria"]
        comparativo = memoria.get("comparativo") or {}
        valores = [
            _competencia_br(item["competencia"]), item["nome_dest"],
            cnpj_formatado(item["cnpj_dest"]),
            f"{item['numero']}/{item['serie']}", item["chave"],
            _data_br(item["dt_emissao"]), item["nome_emit"], item["uf_origem"],
            item["num_item"] or str(item["ordem"]), item["descricao"],
            item["ncm"], item["cfop"], item["cst"],
            ab.FINALIDADES.get(item["finalidade"], "A definir"),
            ab.METODOS.get(item["metodo"], item["metodo"])]
        for coluna, valor in enumerate(valores, start=1):
            escrever_texto(aba, linha, coluna, valor)
        escrever_moeda(aba, linha, 16, _centavos_texto(memoria.get("valor_operacao")))
        _percentual(aba, linha, 17, memoria.get("aliquota_interestadual"))
        escrever_texto(aba, linha, 18,
                       ab.TIPOS_CREDITO.get(memoria.get("tipo_credito"), ""))
        escrever_moeda(aba, linha, 19, _centavos_texto(memoria.get("credito")))
        _percentual(aba, linha, 20, memoria.get("aliquota_interna"))
        divisor = ab.para_decimal(memoria.get("divisor"))
        aba.cell(row=linha, column=21).value = divisor
        escrever_moeda(aba, linha, 22, _centavos_texto(memoria.get("base_calculo")))
        escrever_moeda(aba, linha, 23, _centavos_texto(memoria.get("icms_interno")))
        escrever_moeda(aba, linha, 24, item["a_recolher"])
        escrever_moeda(aba, linha, 25, _centavos_texto(comparativo.get("a_recolher")))
        escrever_texto(aba, linha, 26,
                       ab.DECISOES.get(item["decisao"], "Aguardando decisão"))
        escrever_texto(aba, linha, 27, item["decisao_motivo"])
        escrever_texto(aba, linha, 28, item["decisao_por_login"])
        escrever_texto(aba, linha, 29, " | ".join(
            p["mensagem"] for p in item["pendencias"]))
        escrever_texto(aba, linha, 30, ESTADOS.get(item["estado"], item["estado"]))
        linha += 1
    for letra, largura in (("B", 34), ("E", 48), ("G", 34), ("J", 40),
                           ("O", 30), ("AA", 40), ("AC", 70)):
        aba.column_dimensions[letra].width = largura

    resumo = livro.create_sheet("Totais")
    escrever_cabecalho(resumo, [
        "Competência", "Empresa", "CNPJ", "Regime", "Notas", "Aprovadas",
        "A recolher (aprovado)", "Em revisão (não liberado)",
        "Itens aguardando decisão", "Itens fora do cálculo",
        "Redução simulada", "Aprovado com redução", "Vencimento de referência"])
    linha = 2
    for total in totais:
        escrever_texto(resumo, linha, 1, _competencia_br(total["competencia"]))
        escrever_texto(resumo, linha, 2, total["nome"])
        escrever_texto(resumo, linha, 3, cnpj_formatado(total["cnpj_dest"]))
        escrever_texto(resumo, linha, 4,
                       ab.REGIMES.get(total["regime"], "Não informado"))
        resumo.cell(row=linha, column=5).value = total["notas"]
        resumo.cell(row=linha, column=6).value = total["aprovadas"]
        escrever_moeda(resumo, linha, 7, total["aprovado"])
        escrever_moeda(resumo, linha, 8, total["em_revisao"])
        resumo.cell(row=linha, column=9).value = total["itens_pendentes"]
        resumo.cell(row=linha, column=10).value = total["itens_fora"]
        escrever_moeda(resumo, linha, 11, total["reducao_simulada"])
        escrever_moeda(resumo, linha, 12, total["aprovado_com_reducao"])
        escrever_texto(resumo, linha, 13,
                       _data_br(total["vencimento_referencia"]))
        linha += 1
    resumo.column_dimensions["B"].width = 38

    meta = livro.create_sheet("Metadados")
    escrever_cabecalho(meta, ["Item", "Valor"])
    linhas_meta = [
        ("Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Gerado por", gerado_por),
        ("Filtros aplicados",
         ", ".join(f"{k}={v}" for k, v in sorted((filtros or {}).items()))
         or "nenhum"),
        ("Itens na planilha", str(len(itens))),
        ("Aviso", AVISO_HOMOLOGACAO),
        ("Redução", AVISO_REDUCAO),
        ("Soma", "O total é a soma dos itens com decisão 'Calcular' de notas "
                 "aprovadas, em centavos. Item aguardando decisão não tem "
                 "valor na soma."),
    ]
    for numero, (rotulo, valor) in enumerate(linhas_meta, start=2):
        escrever_texto(meta, numero, 1, rotulo)
        escrever_texto(meta, numero, 2, valor)
    meta.column_dimensions["A"].width = 22
    meta.column_dimensions["B"].width = 110

    salvar_atomico(livro, destino)
    return destino
