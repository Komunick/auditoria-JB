"""Fixtures SINTETICAS da Emissao de NFS-e (spec 006).

Tudo aqui e' ficticio: prestador "Escola Exemplo Ltda", CNPJ de livro-texto
(11.222.333/0001-81), CPFs de exemplo com DV valido (123.456.789-09,
111.444.777-35, 987.654.321-00), alunos "Pedro Exemplo", "Lia Exemplo" e "Caio
Teste". Nenhum nome, CPF, endereco ou valor do video da creche entra no
repositorio (spec.md, "Dados de exemplo").

Os codigos da turma Berçário sao os confirmados no video e no Anexo B
(cTribNac 080101, NBS 1.2201.11.00); os demais campos do perfil sao escolhas
ficticias para exercitar cada opcao do leiaute, nao a configuracao da creche.
"""

from __future__ import annotations

import copy
import os
import zipfile

from openpyxl import Workbook

CNPJ = "11.222.333/0001-81"
CPF_ANA = "123.456.789-09"
CPF_BRUNO = "111.444.777-35"
CPF_CARLA = "987.654.321-00"
CPF_RUIM = "123.456.789-00"

MODELO_CRECHE = ("REFERENTE AOS SERVIÇOS PRESTADOS DE {TURMA} AO MENOR: "
                 "{ALUNO} NO PERÍODO DE {MES}/{ANO}.")

TURMAS = [
    {"nome": "Berçário", "apelidos": ["Bercario I", "Berçário 1"],
     "categoria": "infantil", "c_trib_nac": "080101", "c_nbs": "1.2201.11.00",
     "c_ind_op": "030101", "c_class_trib": "200028",
     "ref_cnae": "8511200", "ref_item_lista": "00801", "ref_ctiss": "0801-0/01"},
    {"nome": "Infantil II", "apelidos": ["Infantil 2"], "categoria": "infantil",
     "c_trib_nac": "080101", "c_nbs": "122011100"},
    # Sem NBS: fica "pendente" (JB-3) e bloqueia as linhas dela.
    {"nome": "Fundamental I", "categoria": "fundamental",
     "c_trib_nac": "080101", "ref_cnae": "8513900"},
]


def perfil_completo(*, endereco: str = "omitir", **extra) -> dict:
    """Perfil sem nenhuma pendencia. Os valores de JB-8/R5 sao FICTICIOS."""
    dados = {
        "cnpj": CNPJ,
        "razao_social": "Escola Exemplo Ltda",
        "inscricao_municipal": "0000000001",
        "informar_im": True,
        "municipio_ibge": "2927408",
        "municipio_prestacao_ibge": "2927408",
        "iss_retido": False,
        "reg_ap_trib_sn": 1,
        "reg_esp_trib": 0,
        "convenio_incidencia_ativo": True,
        "aliquota": "5,00",
        "tributos_aprox": "pTotTribSN",
        "p_tot_trib_sn": "6,00",
        "endereco_tomador": endereco,
        "serie_dps": "900",
        "modelo_discriminacao": MODELO_CRECHE,
        "turmas": copy.deepcopy(TURMAS),
    }
    dados.update(extra)
    return dados


def perfil_cru() -> dict:
    """So o obrigatorio do cadastro: todas as decisoes de JB-2/JB-8/R5 vazias."""
    return {
        "cnpj": CNPJ,
        "razao_social": "Escola Exemplo Ltda",
        "municipio_ibge": "2927408",
        "municipio_prestacao_ibge": "2927408",
        "iss_retido": False,
        "serie_dps": "900",
        "modelo_discriminacao": MODELO_CRECHE,
        "turmas": copy.deepcopy(TURMAS),
    }


# ----------------------------------------------------------------------
# Texto colado da conversa

TEXTO_TRES_BLOCOS = """Boa tarde! Segue a lista de novembro.

Competência: 11/2026
Responsável: Ana Exemplo
CPF: 123.456.789-09
Celular: (71) 90000-0000
ENDEREÇO: Rua das Flores, 100, ap 201, Bairro Exemplo, Salvador-BA, CEP 40000-000
ALUNO: Pedro Exemplo - BERÇÁRIO
Valor: R$ 1.250,00

Competência: 11/2026
Responsável: Bruno Teste
CPF: 123.456.789-00
ALUNO: Caio Teste - Bercario I
Valor: R$ 980,50

competencia - 11/2026
responsavel - Carla Teste
cpf - 987.654.321-00
aluno - Lia Exemplo
turma - Infantil 2
"""

TEXTO_PREFIXO = """[13/10/2026 10:15] Escola Exemplo: Competência: 11/2026
[13/10/2026 10:15] Escola Exemplo: Responsável: Ana Exemplo
[13/10/2026 10:16] Escola Exemplo: CPF: 123.456.789-09
[13/10/2026 10:16] Escola Exemplo: ALUNO: Pedro Exemplo - BERÇÁRIO
[13/10/2026 10:16] Escola Exemplo: Valor: 1.250,00
"""

TEXTO_REPETIDO = """Competência: 11/2026
Responsável: Ana Exemplo
CPF: 123.456.789-09
ALUNO: Pedro Exemplo
Turma: Berçário
Valor: 1.250,00
Valor: 1.300,00
obs: pagou adiantado
"""

TEXTO_INVISIVEIS = ("Competência: 11/2026\nResponsável: Ana​ Exemplo\n"
                    "CPF: 123.456.789-09\nALUNO: Pedro Exemplo\u0007\n"
                    "Turma: Berçário\nValor: 1.250,00\n")


# ----------------------------------------------------------------------
# Planilha-modelo preenchida

ROTULOS_MODELO = ["Competência (MM/AAAA)", "Nome do responsável",
                  "CPF do responsável", "Celular", "E-mail", "Nome do aluno",
                  "Turma", "Valor (R$)", "CEP", "Logradouro", "Número",
                  "Complemento", "Bairro", "Município", "UF",
                  "Código IBGE do município"]

LINHA_ANA = ["11/2026", "Ana Exemplo", "123.456.789-09", "(71) 90000-0000",
             "ana@exemplo.invalid", "Pedro Exemplo", "Berçário", 1250,
             "40000-000", "Rua das Flores", "100", "ap 201", "Bairro Exemplo",
             "Salvador", "BA", "2927408"]

LINHA_BRUNO = ["11/2026", "Bruno Teste", "111.444.777-35", None, None,
               "Caio Teste", "Bercario I", 980.5, None, None, None, None,
               None, None, None, None]


def gerar_planilha(pasta: str, linhas: list[list], *, nome: str = "lista.xlsx",
                   rotulos: list[str] | None = None, aba: str = "Notas",
                   antes: list[list] | None = None) -> str:
    """Grava uma planilha no formato da planilha-modelo.

    `antes` insere linhas acima do cabecalho (titulo da escola, por exemplo).
    Valor que comece por "=" vira formula (sem valor calculado guardado).
    """
    livro = Workbook()
    folha = livro.active
    folha.title = aba
    for linha in antes or []:
        folha.append(linha)
    folha.append(rotulos or ROTULOS_MODELO)
    for linha in linhas:
        folha.append(linha)
    caminho = os.path.join(pasta, nome)
    livro.save(caminho)
    return caminho


def planilha_com_macro(pasta: str) -> str:
    base = gerar_planilha(pasta, [LINHA_ANA], nome="base_macro.xlsx")
    destino = os.path.join(pasta, "com_macro.xlsx")
    with zipfile.ZipFile(base) as origem, \
            zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as saida:
        for item in origem.infolist():
            saida.writestr(item, origem.read(item.filename))
        saida.writestr("xl/vbaProject.bin", b"\x00macro")
    return destino
