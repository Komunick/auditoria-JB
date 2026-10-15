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


# ----------------------------------------------------------------------
# Validacao do pacote .xlsx, ANTES do openpyxl
#
# Extraida de `core/conciliacao_sefaz.py` quando a Emissao de NFS-e passou a
# receber planilha de cliente (spec 006). Os codigos sao os mesmos da
# conciliacao, que traduz `PacoteRecusado` para o erro dela.

XLSX_INVALIDO = "XLSX_INVALIDO"
XLSX_ACIMA_DO_LIMITE = "XLSX_ACIMA_DO_LIMITE"
XLSX_COMPACTACAO_INSEGURA = "XLSX_COMPACTACAO_INSEGURA"
XLSX_MACRO_NAO_PERMITIDA = "XLSX_MACRO_NAO_PERMITIDA"
XLSX_VINCULO_EXTERNO = "XLSX_VINCULO_EXTERNO"

MAX_ENTRADAS_ZIP = 5000
MAX_DESCOMPACTADO = 120 * 1024 * 1024
MAX_RAZAO_COMPRESSAO = 120


class PacoteRecusado(ValueError):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem


def validar_pacote_xlsx(caminho: str, *, max_bytes: int | None = None) -> None:
    """Recusa o arquivo antes de qualquer parser de alto nivel.

    `load_workbook` monta XML de terceiro; um pacote hostil vira consumo de
    memoria, leitura de caminho fora da pasta ou macro. Extensao e MIME nao
    provam nada — o conteudo tem de ser conferido.
    """
    import zipfile

    if not caminho.lower().endswith(".xlsx"):
        raise PacoteRecusado(XLSX_INVALIDO, "Somente arquivos .xlsx sao aceitos.")
    if not os.path.isfile(caminho):
        raise PacoteRecusado(XLSX_INVALIDO, "Arquivo nao encontrado.")

    tamanho = os.path.getsize(caminho)
    if max_bytes is not None and tamanho > max_bytes:
        raise PacoteRecusado(
            XLSX_ACIMA_DO_LIMITE,
            f"Arquivo com {tamanho} bytes excede o limite de {max_bytes}.")
    if tamanho == 0:
        raise PacoteRecusado(XLSX_INVALIDO, "Arquivo vazio.")

    if not zipfile.is_zipfile(caminho):
        raise PacoteRecusado(XLSX_INVALIDO, "Nao e' um pacote Open XML valido.")
    try:
        with zipfile.ZipFile(caminho) as pacote:
            entradas = pacote.infolist()
            nomes = [e.filename for e in entradas]

            if len(entradas) > MAX_ENTRADAS_ZIP:
                raise PacoteRecusado(
                    XLSX_COMPACTACAO_INSEGURA,
                    f"Pacote com {len(entradas)} entradas (limite "
                    f"{MAX_ENTRADAS_ZIP}).")

            for nome in nomes:
                normalizado = nome.replace("\\", "/")
                if (normalizado.startswith("/")
                        or re.match(r"^[A-Za-z]:", normalizado)
                        or ".." in normalizado.split("/")):
                    raise PacoteRecusado(
                        XLSX_COMPACTACAO_INSEGURA,
                        f"Caminho interno inseguro: {nome!r}.")

            if any(os.path.basename(n).lower() == "vbaproject.bin"
                   for n in nomes):
                raise PacoteRecusado(XLSX_MACRO_NAO_PERMITIDA,
                                     "O arquivo contem macro.")
            if any(n.replace("\\", "/").lower().startswith("xl/externallinks/")
                   for n in nomes):
                raise PacoteRecusado(XLSX_VINCULO_EXTERNO,
                                     "O arquivo contem vinculo externo.")

            if ("[Content_Types].xml" not in nomes
                    or "xl/workbook.xml" not in nomes):
                raise PacoteRecusado(
                    XLSX_INVALIDO,
                    "Estrutura minima do pacote Open XML ausente.")

            # Somas lidas do indice do ZIP: nada e' descompactado aqui.
            total = sum(e.file_size for e in entradas)
            comprimido = sum(e.compress_size for e in entradas) or 1
            if total > MAX_DESCOMPACTADO:
                raise PacoteRecusado(
                    XLSX_COMPACTACAO_INSEGURA,
                    f"Conteudo descompactado de {total} bytes excede o limite.")
            if total / comprimido > MAX_RAZAO_COMPRESSAO:
                raise PacoteRecusado(
                    XLSX_COMPACTACAO_INSEGURA,
                    f"Razao de compressao {total / comprimido:.0f}:1 e' abusiva.")
    except zipfile.BadZipFile as exc:
        raise PacoteRecusado(XLSX_INVALIDO, "Pacote Open XML corrompido.") from exc
