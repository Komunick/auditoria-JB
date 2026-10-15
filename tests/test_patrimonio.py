"""Regras de negocio do Patrimonio (nucleo puro, sem servidor nem banco).

Cobre etiqueta, CPF, valores em centavos, campos obrigatorios, hierarquia de
dois niveis, a maquina de transicoes de situacao e os limites arquiteturais do
modulo.
"""

from __future__ import annotations

import ast
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import patrimonio as pt  # noqa: E402


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def erro_de(funcao, *args, **kwargs) -> str:
    try:
        funcao(*args, **kwargs)
    except pt.ErroPatrimonio as exc:
        return exc.codigo
    return ""


def testar_etiqueta() -> None:
    checar(pt.formatar_etiqueta(1) == "JBF-000001", pt.formatar_etiqueta(1))
    checar(pt.formatar_etiqueta(42) == "JBF-000042", pt.formatar_etiqueta(42))
    checar(pt.formatar_etiqueta(1, periferico=True) == "PER-000001",
           pt.formatar_etiqueta(1, periferico=True))
    checar(pt.formatar_etiqueta(999999) == "JBF-999999", "seis digitos")

    for ruim in (0, -1, "x", None, 1.5):
        checar(erro_de(pt.formatar_etiqueta, ruim) == pt.ETIQUETA_INVALIDA,
               f"{ruim!r} deveria ser recusado")

    # O leitor de codigo de barras entrega caixa e espaco variados.
    for entrada in ("JBF-000007", "jbf-000007", " JBF - 000007 ",
                    "Jbf-000007"):
        checar(pt.normalizar_etiqueta(entrada) == "JBF-000007",
               f"{entrada!r} -> {pt.normalizar_etiqueta(entrada)}")
    prefixo, numero = pt.ler_etiqueta("PER-000123")
    checar((prefixo, numero) == ("PER", 123), (prefixo, numero))

    for ruim in ("", "JBF", "JBF-1", "XXX-000001", "JBF_000001", "000001"):
        checar(erro_de(pt.ler_etiqueta, ruim) == pt.ETIQUETA_INVALIDA,
               f"etiqueta {ruim!r} deveria ser recusada")


def testar_cpf() -> None:
    # CPF sintetico valido.
    checar(pt.normalizar_cpf("529.982.247-25") == "52998224725",
           pt.normalizar_cpf("529.982.247-25"))
    checar(pt.normalizar_cpf("52998224725") == "52998224725", "sem mascara")
    # Opcional: vazio nao e' erro, e' ausencia.
    for vazio in ("", None, "   "):
        checar(pt.normalizar_cpf(vazio) == "", f"{vazio!r} deveria virar ''")
    for ruim in ("529.982.247-26", "111.111.111-11", "123", "abc",
                 "5299822472"):
        checar(erro_de(pt.normalizar_cpf, ruim) == pt.CPF_INVALIDO,
               f"CPF {ruim!r} deveria ser recusado")


def testar_valores() -> None:
    checar(pt.centavos("1234,56") == 123456, pt.centavos("1234,56"))
    checar(pt.centavos("1.234,56") == 123456, pt.centavos("1.234,56"))
    checar(pt.centavos("R$ 1.234,56") == 123456, pt.centavos("R$ 1.234,56"))
    checar(pt.centavos("1234.56") == 123456, pt.centavos("1234.56"))
    checar(pt.centavos(0) == 0, "zero informado continua zero")
    for vazio in (None, "", "  "):
        checar(pt.centavos(vazio) is None,
               f"{vazio!r} deveria ser None, nunca 0")
    for ruim in ("-10,00", "abc", "10,005"):
        checar(erro_de(pt.centavos, ruim) == pt.VALOR_INVALIDO,
               f"valor {ruim!r} deveria ser recusado")


def testar_transicoes() -> None:
    """A maquina de estados e' o coracao da rastreabilidade."""
    # Caminho feliz completo de um notebook.
    t = pt.validar_transicao(pt.MOV_ATRIBUICAO, pt.SITUACAO_DISPONIVEL)
    checar(t.situacao_nova == pt.SITUACAO_EM_USO, t)
    checar(t.exige_pessoa, "atribuicao precisa de pessoa")
    checar(not t.exige_justificativa, t)

    checar(pt.validar_transicao(pt.MOV_EMPRESTIMO, pt.SITUACAO_EM_USO)
           .situacao_nova == pt.SITUACAO_EMPRESTADO, "emprestimo")
    checar(pt.validar_transicao(pt.MOV_RETORNO_EMPRESTIMO,
                                pt.SITUACAO_EMPRESTADO)
           .situacao_nova == pt.SITUACAO_EM_USO, "retorno de emprestimo")
    checar(pt.validar_transicao(pt.MOV_DEVOLUCAO, pt.SITUACAO_EM_USO)
           .situacao_nova == pt.SITUACAO_DISPONIVEL, "devolucao")
    checar(pt.validar_transicao(pt.MOV_MANUTENCAO, pt.SITUACAO_EM_USO)
           .situacao_nova == pt.SITUACAO_MANUTENCAO, "manutencao")
    checar(pt.validar_transicao(pt.MOV_RETORNO_MANUTENCAO,
                                pt.SITUACAO_MANUTENCAO)
           .situacao_nova == pt.SITUACAO_DISPONIVEL, "retorno de manutencao")

    # Transferencia muda de lugar, nao de situacao.
    t = pt.validar_transicao(pt.MOV_TRANSFERENCIA, pt.SITUACAO_EM_USO)
    checar(t.situacao_nova == pt.SITUACAO_EM_USO,
           "transferencia nao pode alterar a situacao")

    # Baixa exige justificativa e parte de qualquer situacao ativa.
    for origem in (pt.SITUACAO_DISPONIVEL, pt.SITUACAO_EM_USO,
                   pt.SITUACAO_MANUTENCAO, pt.SITUACAO_EMPRESTADO):
        t = pt.validar_transicao(pt.MOV_BAIXA, origem)
        checar(t.situacao_nova == pt.SITUACAO_BAIXADO, origem)
        checar(t.exige_justificativa, "baixa exige justificativa")

    # BAIXADO E TERMINAL: nenhum movimento sai de la.
    for movimento in pt.TRANSICOES:
        codigo = erro_de(pt.validar_transicao, movimento, pt.SITUACAO_BAIXADO)
        checar(codigo == pt.BEM_BAIXADO,
               f"{movimento} a partir de baixado deveria dar BEM_BAIXADO, "
               f"deu {codigo}")

    # Transicoes que nao fazem sentido.
    invalidas = [
        (pt.MOV_ATRIBUICAO, pt.SITUACAO_EM_USO),        # ja tem responsavel
        (pt.MOV_ATRIBUICAO, pt.SITUACAO_MANUTENCAO),    # esta na assistencia
        (pt.MOV_DEVOLUCAO, pt.SITUACAO_DISPONIVEL),     # ninguem tem
        (pt.MOV_EMPRESTIMO, pt.SITUACAO_DISPONIVEL),    # sem responsavel
        (pt.MOV_RETORNO_MANUTENCAO, pt.SITUACAO_EM_USO),
        (pt.MOV_RETORNO_EMPRESTIMO, pt.SITUACAO_EM_USO),
    ]
    for movimento, origem in invalidas:
        codigo = erro_de(pt.validar_transicao, movimento, origem)
        checar(codigo == pt.TRANSICAO_INVALIDA,
               f"{movimento} de {origem} deveria ser invalido, deu {codigo}")

    checar(erro_de(pt.validar_transicao, "voar", pt.SITUACAO_DISPONIVEL)
           == pt.TRANSICAO_INVALIDA, "movimento inexistente")
    checar(erro_de(pt.validar_transicao, pt.MOV_ATRIBUICAO, "sei_la")
           == pt.TRANSICAO_INVALIDA, "situacao inexistente")


def testar_hierarquia() -> None:
    pt.validar_hierarquia(False)          # pai comum: ok
    checar(erro_de(pt.validar_hierarquia, True) == pt.HIERARQUIA_INVALIDA,
           "periferico de periferico deveria ser recusado")


def testar_validacao_do_bem() -> None:
    bem = pt.validar_bem({
        "descricao": "  Notebook   Dell Latitude  ", "tipo": "Notebook",
        "conservacao": "novo", "valor_aquisicao": "4.500,00",
        "data_aquisicao": "2026-03-15", "numero_serie": " ABC123 "})
    checar(bem.descricao == "Notebook Dell Latitude",
           f"espaco repetido deveria ser normalizado: {bem.descricao!r}")
    checar(bem.valor_aquisicao == 450000, bem.valor_aquisicao)
    checar(bem.numero_serie == "ABC123", bem.numero_serie)

    checar(erro_de(pt.validar_bem, {"tipo": "Notebook"}) == pt.CAMPO_OBRIGATORIO,
           "descricao e' obrigatoria")
    checar(erro_de(pt.validar_bem, {"descricao": "x"}) == pt.CAMPO_OBRIGATORIO,
           "tipo e' obrigatorio")
    checar(erro_de(pt.validar_bem, {"descricao": "x", "tipo": "y",
                                    "conservacao": "otimo"})
           == pt.CAMPO_OBRIGATORIO, "conservacao fora do catalogo")
    checar(erro_de(pt.validar_bem, {"descricao": "x", "tipo": "y",
                                    "data_aquisicao": "15/03/2026"})
           == pt.CAMPO_OBRIGATORIO, "data fora do formato ISO")

    # O catalogo e' de contabilidade, nao de transportadora.
    checar("Notebook" in pt.TIPOS and "Cadeira" in pt.TIPOS, pt.TIPOS)
    juntos = " ".join(pt.TIPOS).lower()
    for fora in ("epi", "botina", "capacete", "caminhao", "pneu"):
        checar(fora not in juntos,
               f"'{fora}' e' domínio da transportadora, nao da contabilidade")


def testar_limites_arquiteturais() -> None:
    """O nucleo do patrimonio nao pode conhecer a interface."""
    proibidos = ("fastapi", "starlette", "flask", "pydantic", "uvicorn",
                 "PySide6", "sqlite3")
    caminho = os.path.join(RAIZ, "src", "auditoria_fiscal", "core",
                           "patrimonio.py")
    with open(caminho, encoding="utf-8") as arq:
        arvore = ast.parse(arq.read())
    for no in ast.walk(arvore):
        modulos = []
        if isinstance(no, ast.Import):
            modulos = [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            modulos = ["." * no.level + (no.module or "")]
        for modulo in modulos:
            checar(modulo.split(".")[0] not in proibidos,
                   f"core/patrimonio.py nao pode importar {modulo}")
            checar("web" not in modulo,
                   f"core/patrimonio.py nao pode importar {modulo}")


def main() -> int:
    testar_etiqueta()
    testar_cpf()
    testar_valores()
    testar_transicoes()
    testar_hierarquia()
    testar_validacao_do_bem()
    testar_limites_arquiteturais()
    print("OK - nucleo do patrimonio (etiqueta imutavel e tolerante ao leitor, "
          "CPF opcional mas validado, centavos, campos obrigatorios, "
          "hierarquia de dois niveis, maquina de transicoes com baixa terminal "
          "e limites arquiteturais) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
