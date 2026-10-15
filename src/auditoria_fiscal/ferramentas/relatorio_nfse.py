"""Saidas da Emissao de NFS-e (spec 006, historia 8), sem FastAPI.

- **Planilha-modelo**: o que a JB entrega a escola. So cabecalho, coluna de
  CPF como texto e uma aba de instrucoes; nenhum dado.
- **Planilha-resumo**: uma linha por nota do lote, dinheiro como numero,
  texto neutralizado contra formula (`core/planilha_segura.py`).
- **Zip das DPS**: os XML exatamente como gravados, com um LEIA-ME.

Tudo leva a marca "DPS NAO TRANSMITIDA": na Fase 1 nada vai ao Emissor
Nacional, e uma previa nao pode ser confundida com nota emitida. Nenhuma
saida fica parcial: planilha por `salvar_atomico`, zip por arquivo temporario
renomeado so no fim.
"""

from __future__ import annotations

import os
import zipfile

from openpyxl import Workbook

from ..core import nfse_entrada as ne
from ..core import planilha_segura as ps

MARCA = "DPS NÃO TRANSMITIDA — produção restrita, sem efeito fiscal"
LINHAS_FORMATADAS_MODELO = 500

INSTRUCOES = (
    "Planilha-modelo da JB Fraga para a emissão de NFS-e.",
    "",
    "Preencha a aba Notas com uma linha por aluno, a partir da linha 2.",
    "Não mude os títulos da linha 1; a ordem das colunas pode mudar.",
    "",
    "Obrigatórias: Competência (MM/AAAA, por exemplo 11/2026), Nome do "
    "responsável, CPF do responsável, Nome do aluno, Turma e Valor (R$).",
    "A turma tem de ser escrita como está cadastrada na JB.",
    "O CPF pode ir com ou sem pontos; a coluna já está como texto para o "
    "Excel não apagar o zero do começo.",
    "Valor: use vírgula nos centavos (1.250,00). '1.250' sem centavos é "
    "ambíguo e volta para correção.",
    "Endereço (CEP, Logradouro, Número, Complemento, Bairro, Município, UF e "
    "Código IBGE do município) só é necessário se a JB pedir.",
    "Linhas totalmente vazias são ignoradas.",
)


def gerar_planilha_modelo(destino: str) -> None:
    livro = Workbook()
    notas = livro.active
    notas.title = "Notas"
    ps.escrever_cabecalho(notas, list(ne.ROTULOS_MODELO))
    coluna_cpf = ne.ROTULOS_MODELO.index("CPF do responsável") + 1
    for linha in range(2, LINHAS_FORMATADAS_MODELO + 2):
        notas.cell(row=linha, column=coluna_cpf).number_format = "@"
    instrucoes = livro.create_sheet("Instruções")
    instrucoes.column_dimensions["A"].width = 110
    for numero, texto in enumerate(INSTRUCOES, start=1):
        ps.escrever_texto(instrucoes, numero, 1, texto)
    ps.salvar_atomico(livro, destino)


_COLUNAS_RESUMO = ["Ordem", "Situação", "Competência", "Responsável", "CPF",
                   "Aluno", "Turma", "Valor", "Discriminação", "Nº DPS",
                   "Id da DPS", "SHA-256 da DPS", "Apontamentos"]


def gerar_resumo(lote: dict, dps: list[dict], destino: str) -> None:
    """`lote` e' o detalhe de `NfseStore.lote`; `dps`, o de `dps_do_lote`."""
    por_linha = {d["linha_id"]: d for d in dps}
    livro = Workbook()
    notas = livro.active
    notas.title = "Notas"
    ps.escrever_cabecalho(notas, _COLUNAS_RESUMO)
    for numero, linha in enumerate(lote["linhas"], start=2):
        d = por_linha.get(linha["id"])
        comp = linha["competencia"]
        valores = [
            linha["ordem"], linha["situacao"],
            f"{comp[5:]}/{comp[:4]}" if comp else "",
            linha["responsavel"] or linha["efetivos"].get("responsavel_nome"),
            ps.cpf_formatado(linha["cpf"]) if linha["cpf"]
            else linha["efetivos"].get("responsavel_cpf"),
            linha["aluno"] or linha["efetivos"].get("aluno_nome"),
            linha["turma"] or linha["efetivos"].get("turma"),
            None, linha["discriminacao"],
            None, d["id_dps"] if d else "", d["sha256"] if d else "",
            "; ".join(f"{a['codigo']}: {a['mensagem']}" for a in linha["apontamentos"]),
        ]
        for coluna, valor in enumerate(valores, start=1):
            if coluna == 8:
                ps.escrever_moeda(notas, numero, coluna, linha["valor_centavos"])
            elif coluna in (1, 10):
                notas.cell(row=numero, column=coluna).value = (
                    valor if coluna == 1 else (d["numero"] if d else None))
            else:
                ps.escrever_texto(notas, numero, coluna, valor)

    info = livro.create_sheet("Lote")
    dados = lote["lote"]
    perfil = lote["perfil"]
    totais = lote["conferencia"]["totais"]
    linhas_info = [
        ("Atenção", MARCA),
        ("Lote", dados["id"]),
        ("Estado", dados["estado"]),
        ("Prestador", f"{perfil['razao_social']} — {ps.cnpj_formatado(perfil['cnpj'])}"),
        ("Origem", f"{dados['origem']['tipo']} — SHA-256 {dados['origem']['sha256']}"),
        ("Importado por", dados["criado_por_login"]),
        ("Aprovado por", dados["aprovado_por_login"] or ""),
        ("Aprovado em", dados["aprovado_em"] or ""),
        ("Hash da aprovação", dados["hash_aprovacao"] or ""),
        ("Notas ativas", totais["ativas"]),
        ("Linhas excluídas", totais["excluidas"]),
    ]
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 90
    for numero, (rotulo, valor) in enumerate(linhas_info, start=1):
        ps.escrever_texto(info, numero, 1, rotulo)
        if isinstance(valor, int):
            info.cell(row=numero, column=2).value = valor
        else:
            ps.escrever_texto(info, numero, 2, valor)
    ps.escrever_texto(info, len(linhas_info) + 1, 1, "Soma dos valores")
    ps.escrever_moeda(info, len(linhas_info) + 1, 2, totais["soma_centavos"])
    ps.salvar_atomico(livro, destino)


def nome_xml(lote_id: int, dps: dict) -> str:
    return (f"DPS-NAO-TRANSMITIDA_lote{lote_id}_{int(dps['numero']):06d}_"
            f"{dps['id_dps']}.xml")


LEIA_ME = """DPS NÃO TRANSMITIDAS

Estas DPS (Declarações de Prestação de Serviço) foram geradas pela
auditoria-JB no ambiente de produção restrita do leiaute nacional v1.01 e
NÃO foram transmitidas ao Emissor Nacional. Não têm efeito fiscal e não
são notas fiscais.

Cada arquivo foi validado contra o XSD oficial e gravado com o SHA-256 que
aparece na planilha-resumo do lote.
"""


def gerar_zip(lote_id: int, dps: list[dict], destino: str) -> None:
    parcial = destino + ".parcial"
    try:
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as pacote:
            pacote.writestr("LEIA-ME.txt", LEIA_ME.encode("utf-8"))
            for d in dps:
                if not isinstance(d.get("xml"), (bytes, bytearray)):
                    raise ValueError(f"DPS {d.get('id')} sem XML gravado.")
                pacote.writestr(nome_xml(lote_id, d), bytes(d["xml"]))
        os.replace(parcial, destino)
    except Exception:
        for caminho in (parcial, destino):
            if os.path.exists(caminho):
                os.remove(caminho)
        raise
