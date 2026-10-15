"""Escrita segura de planilhas Excel, compartilhada pelos exportadores.

Extraido de `ferramentas/relatorio_conciliacao.py` quando o Patrimonio passou
a precisar das mesmas garantias. Duplicar um controle de seguranca e' como uma
das copias envelhece: alguem corrige um lado, esquece o outro, e a
vulnerabilidade volta pela porta que ninguem estava olhando.

Duas regras valem para qualquer saida Excel do sistema:

1. **Texto de terceiro nunca vira formula.** Razao social, nome de arquivo,
   descricao de bem e justificativa sao digitados por pessoas ou vem de fonte
   externa. Um valor que comece por `=`, `+`, `-` ou `@` e' formula para o
   Excel — abrir a planilha executaria conteudo de origem externa.
2. **Dinheiro e' celula numerica**, com formato monetario brasileiro, nunca
   string. String impede somar, ordenar e filtrar no proprio Excel, que e'
   exatamente o que a pessoa vai fazer com o arquivo.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

FORMATO_MOEDA = 'R$ #,##0.00;[RED]-R$ #,##0.00'

# Caracteres que o Excel interpreta como inicio de formula. O tab e o retorno
# de carro entram porque colam o conteudo na celula seguinte.
_INICIO_FORMULA = re.compile(r"^[=+\-@\t\r]")


def sanitizar_texto(valor) -> str:
    """Neutraliza injecao de formula preservando o texto original.

    O apostrofo inicial e' a marca do Excel para "isto e' texto": nao aparece
    na celula, nao altera o conteudo lido e impede a avaliacao. Apagar o
    caractere ou recusar o valor perderia dado da fonte — o objetivo e' exibir
    exatamente o que veio, sem executar.
    """
    if valor is None:
        return ""
    texto = str(valor)
    if _INICIO_FORMULA.match(texto):
        return "'" + texto
    return texto


def escrever_moeda(aba, linha: int, coluna: int, centavos: int | None) -> None:
    """Centavos -> celula numerica. `None` deixa a celula VAZIA.

    Vazio e zero sao coisas diferentes: um `0,00` onde o valor e' desconhecido
    afirma um fato que ninguem apurou.
    """
    celula = aba.cell(row=linha, column=coluna)
    if centavos is None:
        celula.value = None
        return
    celula.value = Decimal(centavos) / 100
    celula.number_format = FORMATO_MOEDA


def escrever_texto(aba, linha: int, coluna: int, valor) -> None:
    aba.cell(row=linha, column=coluna).value = sanitizar_texto(valor)


def escrever_cabecalho(aba, titulos: list[str]) -> None:
    """Cabecalho em negrito, com autofiltro, primeira linha congelada e
    larguras que permitem leitura sem ajuste manual."""
    for coluna, titulo in enumerate(titulos, start=1):
        celula = aba.cell(row=1, column=coluna)
        celula.value = titulo
        celula.font = _negrito()
        largura = max(12, min(len(titulo) + 4, 46))
        aba.column_dimensions[get_column_letter(coluna)].width = largura
    aba.freeze_panes = "A2"
    if titulos:
        aba.auto_filter.ref = f"A1:{get_column_letter(len(titulos))}1"


def _negrito():
    from openpyxl.styles import Font
    return Font(bold=True)


def salvar_atomico(livro: Workbook, destino: str) -> None:
    """Salva num temporario e so entao move para o destino.

    Falha no meio da escrita nao pode deixar um arquivo com cara de planilha
    valida — que abriria corrompido na mao de quem confiou nele.
    """
    parcial = f"{destino}.parcial"
    try:
        livro.save(parcial)
        os.replace(parcial, destino)
    except Exception:
        if os.path.exists(parcial):
            os.remove(parcial)
        if os.path.exists(destino):
            os.remove(destino)
        raise


def cpf_formatado(cpf: str) -> str:
    """11 digitos -> 000.000.000-00. Texto, para nao perder zero a esquerda."""
    digitos = "".join(c for c in str(cpf or "") if c.isdigit())
    if len(digitos) != 11:
        return sanitizar_texto(cpf)
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def cnpj_formatado(cnpj: str) -> str:
    """14 digitos -> 00.000.000/0000-00. Texto, pelo mesmo motivo."""
    digitos = "".join(c for c in str(cnpj or "") if c.isdigit())
    if len(digitos) != 14:
        return sanitizar_texto(cnpj)
    return (f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/"
            f"{digitos[8:12]}-{digitos[12:]}")
