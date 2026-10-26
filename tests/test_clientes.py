"""Regras puras do cadastro de clientes (spec 012).

Documento (CNPJ/CPF) vindo de celula numerica, separacao entre valor e
situacao do campo e faixas de vencimento. Dados sinteticos.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import clientes as cl  # noqa: E402
from auditoria_fiscal.core.documentos_br import dv_cnpj  # noqa: E402

# CNPJ sintetico com zero a esquerda: e' o caso que a celula numerica estraga.
BASE = "012345678000"
CNPJ_ZERO = BASE + dv_cnpj(BASE)
CPF = "52998224725"


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def erro_de(funcao, *args, **kwargs) -> str:
    try:
        funcao(*args, **kwargs)
    except cl.ErroClientes as exc:
        return exc.codigo
    return ""


def main() -> int:
    # ------------------------------------------------------------------
    # Documento

    checar(cl.normalizar_documento("01.234.567/8000-" + CNPJ_ZERO[-2:])
           == CNPJ_ZERO, "CNPJ formatado")
    # A planilha guarda o CNPJ como numero: o zero da frente some.
    checar(cl.normalizar_documento(float(int(CNPJ_ZERO))) == CNPJ_ZERO,
           "CNPJ vindo de celula numerica tem de recuperar o zero a esquerda")
    checar(cl.normalizar_documento(int(CNPJ_ZERO)) == CNPJ_ZERO, "inteiro")
    checar(cl.normalizar_documento("529.982.247-25") == CPF, "CPF formatado")
    checar(cl.normalizar_documento(float(CPF)) == CPF, "CPF numerico")
    checar(cl.tipo_documento(CNPJ_ZERO) == "cnpj"
           and cl.tipo_documento(CPF) == "cpf", "tipo do documento")
    checar(erro_de(cl.normalizar_documento, CNPJ_ZERO[:-1] + "9")
           == cl.DOCUMENTO_INVALIDO, "DV errado e' recusado")
    checar(erro_de(cl.normalizar_documento, "123") == cl.DOCUMENTO_INVALIDO,
           "tamanho errado")
    checar(erro_de(cl.normalizar_documento, "") == cl.DOCUMENTO_INVALIDO,
           "vazio e' recusado: quem aceita vazio decide antes")
    checar(cl.formatar_documento(CNPJ_ZERO).startswith("01.234.567/8000-"),
           cl.formatar_documento(CNPJ_ZERO))
    checar(cl.formatar_documento(CPF) == "529.982.247-25", "CPF formatado")

    # ------------------------------------------------------------------
    # Valor x situacao do campo

    casos = {
        "NÃO TEM": cl.CAMPO_NAO_TEM, "nao tem": cl.CAMPO_NAO_TEM,
        "N": cl.CAMPO_NAO_TEM, "SEM INSCRIÇÃO": cl.CAMPO_NAO_TEM,
        "PENDENTE": cl.CAMPO_PENDENTE, "PENTENDE": cl.CAMPO_PENDENTE,
        "IM PENDENTE": cl.CAMPO_PENDENTE,
        "AGUARDANDO CERTIFICADO": cl.CAMPO_AGUARDANDO_CERTIFICADO,
        "CERTIFICADO PENDENTE": cl.CAMPO_AGUARDANDO_CERTIFICADO,
        "BAIXADA": cl.CAMPO_BAIXADA, "NÃO SE ENQUEDRA": cl.CAMPO_NAO_SE_APLICA,
        "DEFINITIVO": cl.CAMPO_DEFINITIVO, "DEFFINITIVO": cl.CAMPO_DEFINITIVO,
        "VENCIDO": cl.CAMPO_VENCIDO, "RENOVANDO": cl.CAMPO_RENOVANDO,
    }
    for texto, esperada in casos.items():
        valor, situacao = cl.classificar_campo(texto)
        checar(situacao == esperada and valor == "",
               f"{texto!r} -> {situacao!r}, esperado {esperada!r}")

    checar(cl.classificar_campo(None) == ("", ""), "vazio")
    checar(cl.classificar_campo("   ") == ("", ""), "so espaco")
    # Valor de verdade nunca vira situacao, nem e' alterado.
    checar(cl.classificar_campo("12.345.678") == ("12.345.678", ""), "IE")
    checar(cl.classificar_campo(123456.0) == ("123456", ""),
           "numero inteiro de celula sai sem '.0'")
    checar(cl.classificar_campo("  12 ") == ("12", ""), "inscricao sem espaco")
    # Senha e' guardada exatamente como veio: espaco no fim faz parte dela.
    checar(cl.classificar_campo("Senha#2026 ", preservar=True)
           == ("Senha#2026 ", ""), "senha preservada exatamente como veio")
    checar(cl.classificar_campo("NÃO TEM", preservar=True)
           == ("", cl.CAMPO_NAO_TEM), "preservar nao muda a situacao")

    # ------------------------------------------------------------------
    # Faixas de vencimento

    hoje = date(2026, 10, 26)
    faixas = cl.FAIXAS_PADRAO
    checar(faixas == (15, 20, 30), faixas)
    checar(cl.classificar_vencimento(date(2026, 10, 25), hoje, faixas)
           == (cl.FAIXA_VENCIDO, -1), "ontem venceu")
    checar(cl.classificar_vencimento(hoje, hoje, faixas)
           == ("ate_15", 0), "vence hoje cai na faixa mais curta")
    checar(cl.classificar_vencimento(date(2026, 11, 10), hoje, faixas)
           == ("ate_15", 15), "15 dias inclusive")
    checar(cl.classificar_vencimento(date(2026, 11, 11), hoje, faixas)
           == ("ate_20", 16), "16 dias")
    checar(cl.classificar_vencimento(date(2026, 11, 25), hoje, faixas)
           == ("ate_30", 30), "30 dias")
    checar(cl.classificar_vencimento(date(2026, 11, 26), hoje, faixas)
           == (cl.FAIXA_EM_DIA, 31), "31 dias esta em dia")
    checar(cl.classificar_vencimento(None, hoje, faixas)
           == (cl.FAIXA_SEM_DATA, None), "sem data")
    checar(cl.classificar_vencimento(datetime(2026, 10, 27, 23, 0), hoje,
                                     faixas) == ("ate_15", 1),
           "datetime conta pelo dia")

    checar(cl.validar_faixas([30, 15, 20, 15]) == (15, 20, 30),
           "faixas ordenadas e sem repeticao")
    for ruim in ([], [0], [400], ["x"], [1, 2, 3, 4, 5, 6]):
        checar(erro_de(cl.validar_faixas, ruim) == cl.FAIXAS_INVALIDAS,
               f"faixas {ruim!r} deveriam ser recusadas")

    # ------------------------------------------------------------------
    # Datas da planilha

    checar(cl.data_plausivel(datetime(2027, 9, 7)) == date(2027, 9, 7), "data")
    checar(cl.data_plausivel(datetime(2878, 7, 13)) is None,
           "ano 2878 e' erro de digitacao, nao data")
    checar(cl.data_plausivel("DEFINITIVO") is None, "texto nao e' data")
    # A planilha real tem datas digitadas como texto brasileiro.
    checar(cl.data_plausivel("05/11/2026") == date(2026, 11, 5), "dd/mm/aaaa")
    checar(cl.data_plausivel(" 5/1/2027 ") == date(2027, 1, 5), "d/m/aaaa")
    checar(cl.data_plausivel("31/02/2026") is None, "31 de fevereiro nao existe")
    checar(cl.data_plausivel("05/11//2026") is None, "barra dupla e' erro")
    checar(cl.erro_do_excel("#REF!") and cl.erro_do_excel("#N/A")
           and not cl.erro_do_excel("#1 loja"), "celula com erro do Excel")

    print("OK - regras do cadastro de clientes (documento de celula numerica, "
          "valor x situacao do campo, faixas de vencimento, datas plausiveis) "
          "passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
