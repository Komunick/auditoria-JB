"""Leitura dos relatorios da Malha Fiscal da SEFAZ/BA (Receita e DIMP).

Modulo PURO: nao conhece FastAPI, HTTP, sessao nem banco. Recebe um caminho de
arquivo e devolve um `RelatorioConciliacao` com valores em `Decimal`, a
proveniencia de cada fato e a lista de excecoes detectadas. Quem persiste e
quem serve HTTP sao outras camadas (constituicao, principio II).

Tres garantias que orientam o codigo inteiro:

1. **Ausencia nunca vira zero.** Campo obrigatorio vazio e' erro fatal; campo
   opcional ausente e' `None`. Um zero informado pelo Fisco continua zero.
2. **Nada e' adivinhado.** Numero com separador ambiguo, layout desconhecido,
   formula sem valor calculado e CNPJ divergente falham com codigo estavel em
   vez de produzir um numero plausivel.
3. **Todo valor e' rastreavel.** Fato de celula guarda aba, celula, rotulo e
   regra; fato derivado guarda a formula canonica e os fatos de origem.

O pacote XLSX e' validado ANTES do openpyxl: extensao e MIME nao provam nada,
e `load_workbook` sobre um arquivo hostil ja e' execucao de codigo de terceiro
sobre entrada nao confiavel.
"""

from __future__ import annotations

import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

VERSAO_PARSER = "conciliacao-sefaz/1"

LAYOUT_50_5 = "quadro_50_5"
LAYOUT_50_3 = "quadro_50_3_dimp"

# ----------------------------------------------------------------------
# Codigos de erro estaveis (contracts/xlsx-inputs.md)
#
# A interface reage ao CODIGO, nunca ao texto: a mensagem e' escrita para
# pessoas e pode mudar sem aviso.

XLSX_INVALIDO = "XLSX_INVALIDO"
XLSX_MACRO_NAO_PERMITIDA = "XLSX_MACRO_NAO_PERMITIDA"
XLSX_VINCULO_EXTERNO = "XLSX_VINCULO_EXTERNO"
XLSX_COMPACTACAO_INSEGURA = "XLSX_COMPACTACAO_INSEGURA"
XLSX_ACIMA_DO_LIMITE = "XLSX_ACIMA_DO_LIMITE"
LAYOUT_NAO_RECONHECIDO = "LAYOUT_NAO_RECONHECIDO"
RELATORIO_AMBIGUO = "RELATORIO_AMBIGUO"
CNPJ_INVALIDO = "CNPJ_INVALIDO"
CNPJ_DIVERGENTE = "CNPJ_DIVERGENTE"
COMPETENCIA_INVALIDA = "COMPETENCIA_INVALIDA"
CAMPO_OBRIGATORIO_AUSENTE = "CAMPO_OBRIGATORIO_AUSENTE"
FORMULA_SEM_VALOR = "FORMULA_SEM_VALOR"
VALOR_INVALIDO = "VALOR_INVALIDO"
FECHAMENTO_RECEITA = "FECHAMENTO_RECEITA"
FECHAMENTO_DIMP = "FECHAMENTO_DIMP"
DIMP_OBRIGATORIA_AUSENTE = "DIMP_OBRIGATORIA_AUSENTE"
DIMP_AUSENTE_NO_LAYOUT = "DIMP_AUSENTE_NO_LAYOUT"
DIMP_ACIMA_DA_CALCULADA = "DIMP_ACIMA_DA_CALCULADA"
DIMP_ABAIXO_DA_CALCULADA = "DIMP_ABAIXO_DA_CALCULADA"
DIMP_LINHA_DE_OUTRA_CHAVE = "DIMP_LINHA_DE_OUTRA_CHAVE"
DIMP_LINHA_AMBIGUA = "DIMP_LINHA_AMBIGUA"

AVISO = "aviso"
BLOQUEIO = "bloqueio"

# Diferenca ate 1 centavo e' arredondamento da fonte, nao divergencia.
TOLERANCIA = Decimal("0.01")
CENTAVO = Decimal("0.01")

# Limites do pacote (contracts/xlsx-inputs.md). Sao defaults da feature;
# parametrizar so mantendo os testes de rejeicao.
MAX_ENTRADAS_ZIP = 5000
MAX_DESCOMPACTADO = 120 * 1024 * 1024
MAX_RAZAO_COMPRESSAO = 120


class ErroConciliacao(Exception):
    """Falha FATAL: nao produz conciliacao parcial (FR-028)."""

    def __init__(self, codigo: str, mensagem: str, *, onde: str = ""):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.onde = onde


@dataclass(frozen=True)
class ExcecaoDetectada:
    """Problema que NAO impede extrair os dados, mas exige alguem decidir."""

    codigo: str
    severidade: str          # aviso | bloqueio
    mensagem: str


@dataclass(frozen=True)
class FatoExtraido:
    """Proveniencia de um unico valor (FR-025)."""

    metrica: str
    valor: Decimal | None
    tipo_origem: str                     # celula | formula
    regra_parser: str
    rotulo: str = ""
    aba: str | None = None
    celula: str | None = None
    formula: str | None = None
    fatos_origem: tuple[str, ...] = ()
    sha256: str = ""
    versao_parser: str = VERSAO_PARSER


@dataclass(frozen=True)
class MovimentoDimp:
    """Uma linha do bloco DIMP, preservada como veio."""

    instituicao: str
    linha_origem: int
    debito: Decimal
    credito: Decimal
    transferencia: Decimal
    pix: Decimal
    voucher: Decimal
    outras: Decimal
    total_dimp: Decimal
    total_nao_pix: Decimal
    aba: str = ""
    celula_total: str = ""


@dataclass
class RelatorioConciliacao:
    """Resultado da leitura de UM arquivo: um CNPJ, uma competencia."""

    layout: str
    cnpj: str
    competencia: str
    razao_social: str
    receita_declarada: Decimal
    declarada_com_st: Decimal
    declarada_sem_st: Decimal
    receita_calculada: Decimal
    calculada_com_st: Decimal
    calculada_sem_st: Decimal
    diferenca_receita: Decimal
    diferenca_com_st: Decimal
    diferenca_sem_st: Decimal
    total_pix: Decimal | None
    total_nao_pix: Decimal | None
    aba_origem: str
    linha_resumo: int
    movimentos: list[MovimentoDimp] = field(default_factory=list)
    fatos: list[FatoExtraido] = field(default_factory=list)
    excecoes: list[ExcecaoDetectada] = field(default_factory=list)
    sha256: str = ""
    nome_original: str = ""
    versao_parser: str = VERSAO_PARSER

    @property
    def tem_bloqueio(self) -> bool:
        return any(e.severidade == BLOQUEIO for e in self.excecoes)


# ----------------------------------------------------------------------
# Normalizacao


def normalizar_rotulo(texto) -> str:
    """Rotulo comparavel: sem acento, minusculo, espaco simples.

    O contrato diz que acento, caixa e espaco repetido nao podem alterar o
    reconhecimento — as fontes variam entre exportacoes.
    """
    if texto is None:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def normalizar_cnpj(valor) -> str:
    """CNPJ com 14 digitos e DV conferido."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) != 14:
        raise ErroConciliacao(CNPJ_INVALIDO,
                              "CNPJ deve ter 14 digitos.")
    if digitos == digitos[0] * 14:
        # 00.000.000/0000-00 e afins passam no calculo mas nao existem.
        raise ErroConciliacao(CNPJ_INVALIDO, "CNPJ com digitos repetidos.")
    if _dv_cnpj(digitos[:12]) != digitos[12:]:
        raise ErroConciliacao(CNPJ_INVALIDO,
                              "Digito verificador do CNPJ nao confere.")
    return digitos


def _dv_cnpj(base12: str) -> str:
    def _dv(numero: str) -> str:
        pesos = [p if p <= 9 else p - 8
                 for p in range(len(numero) + 1, 1, -1)]
        soma = sum(int(d) * p for d, p in zip(numero, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = _dv(base12)
    return d1 + _dv(base12 + d1)


def normalizar_competencia(valor) -> str:
    """Competencia em AAAAMM, com mes entre 01 e 12."""
    bruto = str(valor or "").strip()
    if not bruto:
        raise ErroConciliacao(COMPETENCIA_INVALIDA, "Competencia ausente.")
    digitos = re.sub(r"\D", "", bruto)
    if re.fullmatch(r"\d{2}[/-]\d{4}", bruto):        # 01/2024
        mes, ano = bruto[:2], bruto[-4:]
    elif re.fullmatch(r"\d{4}[/-]\d{2}", bruto):      # 2024-01
        ano, mes = bruto[:4], bruto[-2:]
    elif len(digitos) == 6:
        ano, mes = digitos[:4], digitos[4:]
    else:
        raise ErroConciliacao(
            COMPETENCIA_INVALIDA,
            f"Competencia '{bruto}' nao esta no formato AAAAMM.")
    if not (mes.isdigit() and 1 <= int(mes) <= 12):
        raise ErroConciliacao(COMPETENCIA_INVALIDA,
                              f"Mes invalido em '{bruto}'.")
    if not (ano.isdigit() and 1900 <= int(ano) <= 2999):
        raise ErroConciliacao(COMPETENCIA_INVALIDA,
                              f"Ano invalido em '{bruto}'.")
    return f"{ano}{int(mes):02d}"


def _grupos_de_milhar_ok(inteiro: str, separador: str) -> bool:
    partes = inteiro.split(separador)
    if len(partes) == 1:
        return True
    if not 1 <= len(partes[0]) <= 3:
        return False
    return all(len(p) == 3 for p in partes[1:])


def para_decimal(valor) -> Decimal:
    """Numero monetario exato. Formato ambiguo e' RECUSADO, nunca chutado.

    `1.234` pode ser mil duzentos e trinta e quatro (milhar brasileiro) ou um
    virgula dois tres quatro (decimal americano). Escolher errado erra por
    1000x num numero fiscal, entao o parser exige que o separador decimal
    seja inequivoco.
    """
    if isinstance(valor, bool):           # bool e' int em Python; aqui nao serve
        raise ErroConciliacao(VALOR_INVALIDO, "Valor booleano em campo numerico.")
    if isinstance(valor, (int, float, Decimal)):
        try:
            numero = Decimal(str(valor))
        except InvalidOperation as exc:
            raise ErroConciliacao(VALOR_INVALIDO,
                                  f"Numero invalido: {valor!r}") from exc
        return _quantizar(numero, valor)

    bruto = str(valor or "").strip()
    if not bruto:
        raise ErroConciliacao(CAMPO_OBRIGATORIO_AUSENTE, "Valor vazio.")
    if bruto.startswith("="):
        # data_only=True devolveu a formula: o cache de valor nao existe.
        raise ErroConciliacao(FORMULA_SEM_VALOR,
                              "Formula sem valor calculado armazenado.")
    if not re.fullmatch(r"[+-]?[\d.,\s]+", bruto):
        raise ErroConciliacao(
            VALOR_INVALIDO,
            f"'{bruto}' nao e' numero (simbolo de moeda ou texto).")

    sinal = -1 if bruto.startswith("-") else 1
    corpo = bruto.lstrip("+-").replace(" ", "")
    tem_ponto, tem_virgula = "." in corpo, "," in corpo

    if tem_ponto and tem_virgula:
        # O ultimo separador a aparecer e' o decimal.
        decimal_sep = "." if corpo.rfind(".") > corpo.rfind(",") else ","
        milhar_sep = "," if decimal_sep == "." else "."
        inteiro, _, fracao = corpo.rpartition(decimal_sep)
        if not _grupos_de_milhar_ok(inteiro, milhar_sep):
            raise ErroConciliacao(VALOR_INVALIDO,
                                  f"Separadores inconsistentes em '{bruto}'.")
        inteiro = inteiro.replace(milhar_sep, "")
    elif tem_ponto or tem_virgula:
        sep = "." if tem_ponto else ","
        if corpo.count(sep) > 1:
            # Varios separadores iguais so podem ser milhar.
            if not _grupos_de_milhar_ok(corpo, sep):
                raise ErroConciliacao(
                    VALOR_INVALIDO, f"Grupos de milhar invalidos em '{bruto}'.")
            inteiro, fracao = corpo.replace(sep, ""), ""
        else:
            inteiro, _, fracao = corpo.partition(sep)
            if len(fracao) == 3:
                raise ErroConciliacao(
                    VALOR_INVALIDO,
                    f"'{bruto}' e' ambiguo: '{sep}' pode ser milhar ou decimal.")
            if not fracao or not fracao.isdigit():
                raise ErroConciliacao(VALOR_INVALIDO,
                                      f"Parte decimal invalida em '{bruto}'.")
    else:
        inteiro, fracao = corpo, ""

    if not inteiro.isdigit() or (fracao and not fracao.isdigit()):
        raise ErroConciliacao(VALOR_INVALIDO, f"Numero invalido: '{bruto}'.")
    if len(fracao) > 2:
        raise ErroConciliacao(
            VALOR_INVALIDO,
            f"'{bruto}' tem fracao de centavo; valor monetario para em 2 casas.")

    texto = inteiro + ("." + fracao if fracao else "")
    return (Decimal(texto) * sinal).quantize(CENTAVO)


def _quantizar(numero: Decimal, original) -> Decimal:
    """Numero de celula ja e' exato; sub-centavo e' recusado, nao arredondado."""
    if numero != numero.quantize(CENTAVO):
        raise ErroConciliacao(
            VALOR_INVALIDO,
            f"{original!r} tem fracao de centavo em campo monetario.")
    return numero.quantize(CENTAVO)


def para_decimal_opcional(valor) -> Decimal | None:
    """`None` para celula VAZIA. Zero informado continua zero."""
    if valor is None:
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    return para_decimal(valor)


def centavos(valor: Decimal | None) -> int | None:
    """Decimal -> centavos inteiros (o que o SQLite guarda)."""
    if valor is None:
        return None
    return int(valor.quantize(CENTAVO) * 100)


# ----------------------------------------------------------------------
# Validacao do pacote, ANTES do openpyxl


def validar_pacote_xlsx(caminho: str, *, max_bytes: int | None = None) -> None:
    """Recusa o arquivo antes de qualquer parser de alto nivel.

    `load_workbook` monta XML de terceiro; um pacote hostil vira consumo de
    memoria, leitura de caminho fora da pasta ou macro. Extensao e MIME nao
    provam nada — o conteudo tem de ser conferido.
    """
    if not caminho.lower().endswith(".xlsx"):
        raise ErroConciliacao(XLSX_INVALIDO,
                              "Somente arquivos .xlsx sao aceitos.")
    if not os.path.isfile(caminho):
        raise ErroConciliacao(XLSX_INVALIDO, "Arquivo nao encontrado.")

    tamanho = os.path.getsize(caminho)
    if max_bytes is not None and tamanho > max_bytes:
        raise ErroConciliacao(
            XLSX_ACIMA_DO_LIMITE,
            f"Arquivo com {tamanho} bytes excede o limite de {max_bytes}.")
    if tamanho == 0:
        raise ErroConciliacao(XLSX_INVALIDO, "Arquivo vazio.")

    if not zipfile.is_zipfile(caminho):
        raise ErroConciliacao(XLSX_INVALIDO,
                              "Nao e' um pacote Open XML valido.")
    try:
        with zipfile.ZipFile(caminho) as pacote:
            entradas = pacote.infolist()
            nomes = [e.filename for e in entradas]

            if len(entradas) > MAX_ENTRADAS_ZIP:
                raise ErroConciliacao(
                    XLSX_COMPACTACAO_INSEGURA,
                    f"Pacote com {len(entradas)} entradas (limite "
                    f"{MAX_ENTRADAS_ZIP}).")

            for nome in nomes:
                normalizado = nome.replace("\\", "/")
                if (normalizado.startswith("/")
                        or re.match(r"^[A-Za-z]:", normalizado)
                        or ".." in normalizado.split("/")):
                    raise ErroConciliacao(
                        XLSX_COMPACTACAO_INSEGURA,
                        f"Caminho interno inseguro: {nome!r}.")

            if any(os.path.basename(n).lower() == "vbaproject.bin"
                   for n in nomes):
                raise ErroConciliacao(XLSX_MACRO_NAO_PERMITIDA,
                                      "O arquivo contem macro.")
            if any(n.replace("\\", "/").lower().startswith("xl/externallinks/")
                   for n in nomes):
                raise ErroConciliacao(XLSX_VINCULO_EXTERNO,
                                      "O arquivo contem vinculo externo.")

            if ("[Content_Types].xml" not in nomes
                    or "xl/workbook.xml" not in nomes):
                raise ErroConciliacao(
                    XLSX_INVALIDO,
                    "Estrutura minima do pacote Open XML ausente.")

            # Somas lidas do indice do ZIP: nada e' descompactado aqui.
            total = sum(e.file_size for e in entradas)
            comprimido = sum(e.compress_size for e in entradas) or 1
            if total > MAX_DESCOMPACTADO:
                raise ErroConciliacao(
                    XLSX_COMPACTACAO_INSEGURA,
                    f"Conteudo descompactado de {total} bytes excede o limite.")
            if total / comprimido > MAX_RAZAO_COMPRESSAO:
                raise ErroConciliacao(
                    XLSX_COMPACTACAO_INSEGURA,
                    f"Razao de compressao {total / comprimido:.0f}:1 e' abusiva.")
    except zipfile.BadZipFile as exc:
        raise ErroConciliacao(XLSX_INVALIDO,
                              "Pacote Open XML corrompido.") from exc


# ----------------------------------------------------------------------
# Reconhecimento dos blocos

_ROTULO_DECLARADA = "receita total informada"
_ROTULO_CALCULADA = "receita total calculada"
_ROTULO_INSTITUICAO = "instituicao financeira"
_ROTULO_TOTAL_DIMP = "total dimp"

# Mapa coluna -> campo, conforme contracts/xlsx-inputs.md. Trocar coluna exige
# um adaptador novo e testado: extracao posicional silenciosa e' o erro que a
# spec proibe.
COLUNAS_RESUMO = {
    "C": ("receita_declarada", _ROTULO_DECLARADA),
    "E": ("declarada_com_st", "receita com substituicao tributaria de icms"),
    "F": ("declarada_sem_st", "receita sem substituicao tributaria"),
    "G": ("receita_calculada", _ROTULO_CALCULADA),
    "I": ("calculada_com_st", "receita calculada com st"),
    "J": ("calculada_sem_st", "receita calculada sem st"),
}

COLUNAS_DIMP = {
    "D": "debito", "E": "credito", "F": "transferencia",
    "G": "pix", "H": "voucher", "I": "outras", "J": "total_dimp",
}

_RE_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_RE_QUADRO_50_3 = re.compile(r"quadro\s*50[\s\-/]*3")


def _texto(celula) -> str:
    return "" if celula is None else str(celula)


def _linha_tem(valores: list, *rotulos: str) -> bool:
    normalizados = [normalizar_rotulo(v) for v in valores]
    return all(any(r in n for n in normalizados if n) for r in rotulos)


def _achar_cabecalho_resumo(aba) -> int:
    """Linha do cabecalho do bloco-resumo, ou 0."""
    for linha in aba.iter_rows():
        valores = [c.value for c in linha]
        if _linha_tem(valores, _ROTULO_DECLARADA, _ROTULO_CALCULADA):
            return linha[0].row
    return 0


def _achar_cabecalho_dimp(aba, apos: int) -> int:
    for linha in aba.iter_rows(min_row=apos + 1):
        valores = [c.value for c in linha]
        if _linha_tem(valores, _ROTULO_INSTITUICAO, _ROTULO_TOTAL_DIMP):
            return linha[0].row
    return 0


def _achar_linha_de_dados(aba, cabecalho: int) -> int:
    """Primeira linha mensal valida abaixo do cabecalho reconhecido."""
    for linha in aba.iter_rows(min_row=cabecalho + 1,
                               max_row=min(cabecalho + 30, aba.max_row)):
        competencia, documento = linha[0].value, linha[1].value
        if competencia is None and documento is None:
            continue
        try:
            normalizar_competencia(competencia)
            normalizar_cnpj(documento)
        except ErroConciliacao:
            continue
        return linha[0].row
    return 0


def _cnpj_do_cabecalho(aba, ate_linha: int) -> str:
    """CNPJ anunciado acima do bloco (quando existir)."""
    for linha in aba.iter_rows(min_row=1, max_row=max(ate_linha - 1, 1)):
        for celula in linha:
            achado = _RE_CNPJ.search(_texto(celula.value))
            if achado:
                try:
                    return normalizar_cnpj(achado.group(0))
                except ErroConciliacao:
                    continue
    return ""


def _razao_social(aba, ate_linha: int) -> str:
    for linha in aba.iter_rows(min_row=1, max_row=max(ate_linha - 1, 1)):
        for celula in linha:
            texto = _texto(celula.value)
            if normalizar_rotulo(texto).startswith("contribuinte"):
                _, _, nome = texto.partition(":")
                if nome.strip():
                    return nome.strip()
    return ""


def _anuncia_50_3(aba, ate_linha: int) -> bool:
    for linha in aba.iter_rows(min_row=1, max_row=max(ate_linha, 1)):
        for celula in linha:
            if _RE_QUADRO_50_3.search(normalizar_rotulo(celula.value)):
                return True
    return False


class _Formulas:
    """Visao de FORMULAS do mesmo arquivo, aberta so quando precisa.

    Com `data_only=True` o openpyxl devolve `None` tanto para celula vazia
    quanto para formula cujo resultado o Excel nunca gravou — e o contrato
    exige codigos diferentes para os dois casos, porque a correcao e' outra:
    uma celula vazia se preenche, uma formula sem cache se resolve reabrindo e
    salvando a planilha na origem. A segunda leitura so acontece quando um
    campo obrigatorio aparece vazio, entao o caminho normal continua com uma
    unica carga do arquivo.
    """

    def __init__(self, caminho: str):
        self._caminho = caminho
        self._livro = None
        self._tentou = False

    def em(self, aba_titulo: str, coordenada: str) -> str:
        if not self._tentou:
            self._tentou = True
            try:
                self._livro = load_workbook(self._caminho, data_only=False)
            except Exception:             # noqa: BLE001 — sem formula, sem pista
                self._livro = None
        if self._livro is None or aba_titulo not in self._livro.sheetnames:
            return ""
        valor = self._livro[aba_titulo][coordenada].value
        return valor if isinstance(valor, str) and valor.startswith("=") else ""

    def fechar(self) -> None:
        if self._livro is not None:
            self._livro.close()
            self._livro = None


def _valor_obrigatorio(aba, coluna: str, linha: int, campo: str,
                       rotulo: str, formulas: _Formulas) -> Decimal:
    celula = aba[f"{coluna}{linha}"]
    coordenada = f"{coluna}{linha}"
    if celula.value is None or (isinstance(celula.value, str)
                                and not celula.value.strip()):
        formula = formulas.em(aba.title, coordenada)
        if formula:
            raise ErroConciliacao(
                FORMULA_SEM_VALOR,
                f"'{rotulo}' ({coordenada}) contem a formula {formula} sem "
                f"valor calculado armazenado. Reabra e salve a planilha na "
                f"origem para que o Excel grave o resultado.",
                onde=f"{aba.title}!{coordenada}")
        raise ErroConciliacao(
            CAMPO_OBRIGATORIO_AUSENTE,
            f"'{rotulo}' esta vazio na celula {coordenada}.",
            onde=f"{aba.title}!{coordenada}")
    try:
        return para_decimal(celula.value)
    except ErroConciliacao as exc:
        raise ErroConciliacao(
            exc.codigo, f"{exc.mensagem} (campo '{campo}', celula "
                        f"{coluna}{linha})",
            onde=f"{aba.title}!{coluna}{linha}") from exc


# ----------------------------------------------------------------------
# Leitura


def ler_relatorio(caminho: str, *, sha256: str = "",
                  nome_original: str = "",
                  max_bytes: int | None = None) -> RelatorioConciliacao:
    """Le UM relatorio: um CNPJ, uma competencia, uma linha-resumo."""
    validar_pacote_xlsx(caminho, max_bytes=max_bytes)

    # data_only=True: interessa o VALOR calculado, nunca a formula. Se o cache
    # nao existir, o openpyxl devolve a formula como texto e o parser recusa.
    livro = load_workbook(caminho, data_only=True, read_only=False)
    formulas = _Formulas(caminho)
    try:
        candidatos = []
        for aba in livro.worksheets:            # inclui abas ocultas
            cabecalho = _achar_cabecalho_resumo(aba)
            if not cabecalho:
                continue
            dados = _achar_linha_de_dados(aba, cabecalho)
            if dados:
                candidatos.append((aba, cabecalho, dados))

        if not candidatos:
            raise ErroConciliacao(
                LAYOUT_NAO_RECONHECIDO,
                "Nenhum bloco-resumo da SEFAZ foi reconhecido no arquivo.")
        if len(candidatos) > 1:
            onde = ", ".join(f"{a.title}!linha {d}" for a, _, d in candidatos)
            raise ErroConciliacao(
                RELATORIO_AMBIGUO,
                f"O arquivo tem mais de uma linha-resumo reconhecida ({onde}). "
                f"Cada arquivo deve representar um unico relatorio.")

        aba, cabecalho, linha = candidatos[0]
        return _montar(aba, cabecalho, linha, sha256, nome_original, formulas)
    finally:
        formulas.fechar()
        livro.close()


def _montar(aba, cabecalho: int, linha: int, sha256: str,
            nome_original: str, formulas: _Formulas) -> RelatorioConciliacao:
    excecoes: list[ExcecaoDetectada] = []
    fatos: list[FatoExtraido] = []

    competencia = normalizar_competencia(aba[f"A{linha}"].value)
    cnpj = normalizar_cnpj(aba[f"B{linha}"].value)

    do_cabecalho = _cnpj_do_cabecalho(aba, cabecalho)
    if do_cabecalho and do_cabecalho != cnpj:
        # Nao ha como saber qual e' o certo: nenhum dos dois pode ser adotado.
        raise ErroConciliacao(
            CNPJ_DIVERGENTE,
            "O CNPJ do cabecalho nao coincide com o da linha mensal.")

    valores: dict[str, Decimal] = {}
    for coluna, (campo, rotulo) in COLUNAS_RESUMO.items():
        valores[campo] = _valor_obrigatorio(aba, coluna, linha, campo, rotulo,
                                            formulas)
        fatos.append(FatoExtraido(
            metrica=campo, valor=valores[campo], tipo_origem="celula",
            regra_parser=f"resumo/{campo}", rotulo=rotulo, aba=aba.title,
            celula=f"{coluna}{linha}", sha256=sha256))

    declarada = valores["receita_declarada"]
    calculada = valores["receita_calculada"]

    for total, com_st, sem_st, nome in (
        (declarada, valores["declarada_com_st"], valores["declarada_sem_st"],
         "declarada"),
        (calculada, valores["calculada_com_st"], valores["calculada_sem_st"],
         "calculada"),
    ):
        if abs(com_st + sem_st - total) > TOLERANCIA:
            excecoes.append(ExcecaoDetectada(
                FECHAMENTO_RECEITA, BLOQUEIO,
                f"Receita {nome}: com ST ({com_st}) + sem ST ({sem_st}) nao "
                f"fecha com o total ({total})."))

    # Diferenca e' SEMPRE calculado menos declarado.
    derivados = {
        "diferenca_receita": (calculada - declarada,
                              "receita_calculada - receita_declarada",
                              ("receita_calculada", "receita_declarada")),
        "diferenca_com_st": (valores["calculada_com_st"]
                             - valores["declarada_com_st"],
                             "calculada_com_st - declarada_com_st",
                             ("calculada_com_st", "declarada_com_st")),
        "diferenca_sem_st": (valores["calculada_sem_st"]
                             - valores["declarada_sem_st"],
                             "calculada_sem_st - declarada_sem_st",
                             ("calculada_sem_st", "declarada_sem_st")),
    }
    for metrica, (valor, formula, origem) in derivados.items():
        fatos.append(FatoExtraido(
            metrica=metrica, valor=valor, tipo_origem="formula",
            regra_parser=f"derivado/{metrica}", formula=formula,
            fatos_origem=origem, sha256=sha256))

    inicio_dimp = _achar_cabecalho_dimp(aba, linha)
    anunciado_50_3 = _anuncia_50_3(aba, cabecalho)

    movimentos: list[MovimentoDimp] = []
    total_pix: Decimal | None = None
    total_nao_pix: Decimal | None = None

    if inicio_dimp:
        layout = LAYOUT_50_3
        movimentos = _ler_movimentos(aba, inicio_dimp, competencia, cnpj,
                                     excecoes, formulas)
        if movimentos:
            total_pix = sum((m.pix for m in movimentos), Decimal("0.00"))
            total_dimp = sum((m.total_dimp for m in movimentos),
                             Decimal("0.00"))
            total_nao_pix = total_dimp - total_pix
            fatos.append(FatoExtraido(
                metrica="total_pix", valor=total_pix, tipo_origem="formula",
                regra_parser="derivado/total_pix",
                formula="soma(movimento.pix)",
                fatos_origem=tuple(f"movimento[{m.linha_origem}].pix"
                                   for m in movimentos), sha256=sha256))
            fatos.append(FatoExtraido(
                metrica="total_nao_pix", valor=total_nao_pix,
                tipo_origem="formula", regra_parser="derivado/total_nao_pix",
                formula="total_dimp - total_pix",
                fatos_origem=("total_dimp", "total_pix"), sha256=sha256))
            _conferir_dimp_contra_calculada(total_dimp, calculada, excecoes)
        else:
            excecoes.append(ExcecaoDetectada(
                DIMP_OBRIGATORIA_AUSENTE, BLOQUEIO,
                "O bloco DIMP foi reconhecido, mas nenhuma linha valida desta "
                "competencia e CNPJ foi encontrada."))
    elif anunciado_50_3:
        # O relatorio se anuncia como Quadro 50-3 e chegou sem DIMP. Tratar
        # como 50-5 trocaria um bloqueio por um aviso benigno e deixaria a
        # competencia aprovavel sem ninguem notar a falta (contrato de
        # entrada: "nao e' reinterpretado como Quadro 50-5").
        layout = LAYOUT_50_3
        excecoes.append(ExcecaoDetectada(
            DIMP_OBRIGATORIA_AUSENTE, BLOQUEIO,
            "O relatorio se identifica como Quadro 50-3, mas nao traz bloco "
            "DIMP reconhecivel."))
    else:
        layout = LAYOUT_50_5
        excecoes.append(ExcecaoDetectada(
            DIMP_AUSENTE_NO_LAYOUT, AVISO,
            "Quadro 50-5 nao traz DIMP: PIX e nao-PIX ficam nao informados "
            "para esta competencia."))

    return RelatorioConciliacao(
        layout=layout, cnpj=cnpj, competencia=competencia,
        razao_social=_razao_social(aba, cabecalho),
        receita_declarada=declarada,
        declarada_com_st=valores["declarada_com_st"],
        declarada_sem_st=valores["declarada_sem_st"],
        receita_calculada=calculada,
        calculada_com_st=valores["calculada_com_st"],
        calculada_sem_st=valores["calculada_sem_st"],
        diferenca_receita=derivados["diferenca_receita"][0],
        diferenca_com_st=derivados["diferenca_com_st"][0],
        diferenca_sem_st=derivados["diferenca_sem_st"][0],
        total_pix=total_pix, total_nao_pix=total_nao_pix,
        aba_origem=aba.title, linha_resumo=linha, movimentos=movimentos,
        fatos=fatos, excecoes=excecoes, sha256=sha256,
        nome_original=nome_original)


def _conferir_dimp_contra_calculada(total_dimp: Decimal, calculada: Decimal,
                                    excecoes: list) -> None:
    """DIMP acima da receita calculada e' bloqueio; abaixo e' aviso (FR-023).

    Movimentacao financeira maior que a receita apurada indica receita nao
    declarada e nao pode ser aprovada sem analise. Menor e' comum e explicavel
    (nem toda receita passa por meio eletronico), entao apenas avisa.
    """
    if total_dimp - calculada > TOLERANCIA:
        excecoes.append(ExcecaoDetectada(
            DIMP_ACIMA_DA_CALCULADA, BLOQUEIO,
            f"Total DIMP ({total_dimp}) supera a receita calculada "
            f"({calculada})."))
    elif calculada - total_dimp > TOLERANCIA:
        excecoes.append(ExcecaoDetectada(
            DIMP_ABAIXO_DA_CALCULADA, AVISO,
            f"Total DIMP ({total_dimp}) e' menor que a receita calculada "
            f"({calculada})."))


def _ler_movimentos(aba, cabecalho: int, competencia: str, cnpj: str,
                    excecoes: list, formulas: _Formulas) -> list[MovimentoDimp]:
    """Linhas do bloco DIMP desta competencia e CNPJ.

    Linha plenamente identificada como de outra chave sai com aviso; linha com
    chave ausente, invalida ou ambigua BLOQUEIA — incorpora-la ou descarta-la
    em silencio seriam os dois jeitos de errar.
    """
    movimentos: list[MovimentoDimp] = []
    for linha in aba.iter_rows(min_row=cabecalho + 1):
        numero = linha[0].row
        instituicao = _texto(aba[f"C{numero}"].value).strip()
        if not instituicao and all(
                aba[f"{c}{numero}"].value in (None, "") for c in COLUNAS_DIMP):
            break                                # fim do bloco

        bruta_comp = aba[f"A{numero}"].value
        bruto_cnpj = aba[f"B{numero}"].value
        try:
            comp_linha = normalizar_competencia(bruta_comp)
            cnpj_linha = normalizar_cnpj(bruto_cnpj)
        except ErroConciliacao:
            excecoes.append(ExcecaoDetectada(
                DIMP_LINHA_AMBIGUA, BLOQUEIO,
                f"Linha {numero} do bloco DIMP nao identifica competencia e "
                f"CNPJ; nao da para decidir se pertence a esta conciliacao."))
            continue

        if comp_linha != competencia or cnpj_linha != cnpj:
            excecoes.append(ExcecaoDetectada(
                DIMP_LINHA_DE_OUTRA_CHAVE, AVISO,
                f"Linha {numero} do bloco DIMP pertence a outra competencia ou "
                f"CNPJ e foi excluida desta conciliacao."))
            continue

        componentes: dict[str, Decimal] = {}
        for coluna, campo in COLUNAS_DIMP.items():
            componentes[campo] = _valor_obrigatorio(
                aba, coluna, numero, campo, campo, formulas)

        soma = sum((componentes[c] for c in
                    ("debito", "credito", "transferencia", "pix", "voucher",
                     "outras")), Decimal("0.00"))
        if abs(soma - componentes["total_dimp"]) > TOLERANCIA:
            excecoes.append(ExcecaoDetectada(
                FECHAMENTO_DIMP, BLOQUEIO,
                f"Linha {numero} ({instituicao}): componentes somam {soma}, "
                f"mas o total DIMP e' {componentes['total_dimp']}."))

        movimentos.append(MovimentoDimp(
            instituicao=instituicao, linha_origem=numero,
            debito=componentes["debito"], credito=componentes["credito"],
            transferencia=componentes["transferencia"],
            pix=componentes["pix"], voucher=componentes["voucher"],
            outras=componentes["outras"],
            total_dimp=componentes["total_dimp"],
            total_nao_pix=componentes["total_dimp"] - componentes["pix"],
            aba=aba.title,
            celula_total=f"{get_column_letter(10)}{numero}"))

    return movimentos
