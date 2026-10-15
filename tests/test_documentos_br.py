"""Validadores brasileiros compartilhados (CPF, CNPJ, decimal monetario) e a
validacao do pacote .xlsx antes do openpyxl.

Estas funcoes nasceram no Patrimonio e na Conciliacao e foram extraidas quando
a Emissao de NFS-e passou a precisar delas (spec 006, plan.md). O teste fixa o
comportamento compartilhado e confere que os modulos de origem continuam com
os mesmos nomes, codigos e mensagens.
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import conciliacao_sefaz as cs  # noqa: E402
from auditoria_fiscal.core import documentos_br as db  # noqa: E402
from auditoria_fiscal.core import patrimonio as pt  # noqa: E402
from auditoria_fiscal.core import planilha_segura as ps  # noqa: E402


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def motivo_de(funcao, *args):
    try:
        funcao(*args)
    except db.DocumentoInvalido as exc:
        return exc.motivo
    return ""


def codigo_de(funcao, *args):
    try:
        funcao(*args)
    except db.DocumentoInvalido as exc:
        return exc.codigo
    return ""


def testar_cpf() -> None:
    # CPFs ficticios de livro-texto, com DV valido.
    checar(db.digitos_cpf("123.456.789-09") == "12345678909", "CPF formatado")
    checar(db.digitos_cpf("11144477735") == "11144477735", "CPF so digitos")
    checar(db.digitos_cpf(" 111.444.777-35 ") == "11144477735", "espacos")
    checar(motivo_de(db.digitos_cpf, "123.456.789-00") == "dv", "DV errado")
    checar(motivo_de(db.digitos_cpf, "1234567890") == "tamanho", "10 digitos")
    checar(motivo_de(db.digitos_cpf, "") == "tamanho", "vazio")
    checar(motivo_de(db.digitos_cpf, None) == "tamanho", "None")
    checar(motivo_de(db.digitos_cpf, "111.111.111-11") == "repetidos",
           "digitos repetidos passam no calculo mas nao existem")
    checar(codigo_de(db.digitos_cpf, "123.456.789-00") == db.CPF_INVALIDO,
           "codigo do erro de CPF")


def testar_cnpj() -> None:
    checar(db.digitos_cnpj("11.222.333/0001-81") == "11222333000181",
           "CNPJ formatado")
    checar(motivo_de(db.digitos_cnpj, "11.222.333/0001-80") == "dv", "DV")
    checar(motivo_de(db.digitos_cnpj, "1122233300018") == "tamanho", "13")
    checar(motivo_de(db.digitos_cnpj, "00.000.000/0000-00") == "repetidos",
           "zeros")
    checar(db.dv_cnpj("112223330001") == "81", "calculo do DV")


def testar_decimal() -> None:
    casos = {
        "1.250,00": Decimal("1250.00"),
        "1250,00": Decimal("1250.00"),
        "1250.50": Decimal("1250.50"),
        "980,5": Decimal("980.50"),
        "1.234.567,89": Decimal("1234567.89"),
        "-12,30": Decimal("-12.30"),
        "1250": Decimal("1250.00"),
    }
    for texto, esperado in casos.items():
        checar(db.decimal_monetario(texto) == esperado,
               f"{texto!r} -> {db.decimal_monetario(texto)} (esperado {esperado})")
    # Separador unico com 3 casas: milhar ou decimal? Recusado, nunca chutado.
    for ambiguo in ("1.250", "1,250"):
        checar(codigo_de(db.decimal_monetario, ambiguo) == db.VALOR_INVALIDO,
               f"{ambiguo!r} e' ambiguo")
    checar(codigo_de(db.decimal_monetario, "12,345") == db.VALOR_INVALIDO,
           "fracao de centavo / ambiguo")
    checar(codigo_de(db.decimal_monetario, "1.2,3") == db.VALOR_INVALIDO,
           "separadores inconsistentes")
    checar(codigo_de(db.decimal_monetario, "") == db.VALOR_VAZIO, "vazio")
    checar(codigo_de(db.decimal_monetario, "=A1*2") == db.FORMULA_SEM_VALOR,
           "formula sem valor calculado")
    checar(codigo_de(db.decimal_monetario, "R$ 10,00") == db.VALOR_INVALIDO,
           "simbolo de moeda nao e' aceito aqui (quem chama tira o R$)")
    checar(codigo_de(db.decimal_monetario, True) == db.VALOR_INVALIDO, "bool")
    # Celula numerica: exata, sub-centavo recusado (nao arredondado).
    checar(db.decimal_monetario(1250.5) == Decimal("1250.50"), "float")
    checar(db.decimal_monetario(0) == Decimal("0.00"), "zero numerico")
    checar(codigo_de(db.decimal_monetario, 10.005) == db.VALOR_INVALIDO,
           "float com fracao de centavo")


def testar_modulos_de_origem() -> None:
    """Patrimonio e Conciliacao continuam iguais por fora."""
    checar(pt.normalizar_cpf("") == "", "CPF vazio segue opcional no patrimonio")
    for ruim, trecho in (("123", "11 dígitos"), ("111.111.111-11", "repetidos"),
                         ("123.456.789-00", "verificador")):
        try:
            pt.normalizar_cpf(ruim)
            checar(False, f"{ruim!r} deveria falhar no patrimonio")
        except pt.ErroPatrimonio as exc:
            checar(exc.codigo == pt.CPF_INVALIDO, exc.codigo)
            checar(trecho in exc.mensagem, exc.mensagem)

    for ruim, trecho in (("123", "14 digitos"), ("00000000000000", "repetidos"),
                         ("11.222.333/0001-80", "verificador")):
        try:
            cs.normalizar_cnpj(ruim)
            checar(False, f"{ruim!r} deveria falhar na conciliacao")
        except cs.ErroConciliacao as exc:
            checar(exc.codigo == cs.CNPJ_INVALIDO, exc.codigo)
            checar(trecho in exc.mensagem, exc.mensagem)

    for ruim, codigo in (("", cs.CAMPO_OBRIGATORIO_AUSENTE),
                         ("=SOMA(A1)", cs.FORMULA_SEM_VALOR),
                         ("1.250", cs.VALOR_INVALIDO)):
        try:
            cs.para_decimal(ruim)
            checar(False, f"{ruim!r} deveria falhar na conciliacao")
        except cs.ErroConciliacao as exc:
            checar(exc.codigo == codigo, f"{ruim!r}: {exc.codigo}")
    checar(cs.para_decimal("1.250,00") == Decimal("1250.00"), "conciliacao ok")


def _xlsx(pasta: str, nome: str, extras: dict[str, bytes] | None = None) -> str:
    caminho = os.path.join(pasta, nome)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        for n, conteudo in (extras or {}).items():
            z.writestr(n, conteudo)
    return caminho


def testar_pacote_xlsx() -> None:
    with tempfile.TemporaryDirectory() as pasta:
        bom = _xlsx(pasta, "bom.xlsx")
        ps.validar_pacote_xlsx(bom)
        macro = _xlsx(pasta, "macro.xlsx", {"xl/vbaProject.bin": b"x"})
        externo = _xlsx(pasta, "ext.xlsx", {"xl/externalLinks/externalLink1.xml": b"x"})
        texto = os.path.join(pasta, "texto.xlsx")
        with open(texto, "w", encoding="utf-8") as arq:
            arq.write("nao sou zip")
        for caminho, codigo in ((macro, ps.XLSX_MACRO_NAO_PERMITIDA),
                                (externo, ps.XLSX_VINCULO_EXTERNO),
                                (texto, ps.XLSX_INVALIDO)):
            try:
                ps.validar_pacote_xlsx(caminho)
                checar(False, f"{caminho} deveria ser recusado")
            except ps.PacoteRecusado as exc:
                checar(exc.codigo == codigo, f"{caminho}: {exc.codigo}")
            # A conciliacao continua levantando o erro dela, com o mesmo codigo.
            try:
                cs.validar_pacote_xlsx(caminho)
                checar(False, f"{caminho} deveria ser recusado na conciliacao")
            except cs.ErroConciliacao as exc:
                checar(exc.codigo == codigo, f"conciliacao {caminho}: {exc.codigo}")
        try:
            ps.validar_pacote_xlsx(bom, max_bytes=10)
            checar(False, "teto de bytes")
        except ps.PacoteRecusado as exc:
            checar(exc.codigo == ps.XLSX_ACIMA_DO_LIMITE, exc.codigo)
    for nome in ("XLSX_INVALIDO", "XLSX_ACIMA_DO_LIMITE", "XLSX_COMPACTACAO_INSEGURA",
                 "XLSX_MACRO_NAO_PERMITIDA", "XLSX_VINCULO_EXTERNO"):
        checar(getattr(ps, nome) == getattr(cs, nome), f"{nome} igual nos dois")


def main() -> int:
    testar_cpf()
    testar_cnpj()
    testar_decimal()
    testar_modulos_de_origem()
    testar_pacote_xlsx()
    print("OK - validadores compartilhados (CPF, CNPJ, decimal monetario sem "
          "chute, pacote .xlsx) e modulos de origem com os mesmos codigos e "
          "mensagens passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
