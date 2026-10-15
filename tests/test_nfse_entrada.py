"""Entrada do lote da NFS-e (spec 006): planilha-modelo e texto colado da
conversa, com a proveniencia de cada valor. Fixtures sinteticas.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_entrada as ne  # noqa: E402
from fixtures import nfse as fx  # noqa: E402

TURMAS = nf.validar_perfil(fx.perfil_completo()).turmas


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def erro(funcao, *args, **kwargs):
    try:
        funcao(*args, **kwargs)
    except nf.ErroNfse as exc:
        return exc
    return None


# ----------------------------------------------------------------------
# Planilha


def testar_planilha_modelo(pasta: str) -> None:
    caminho = fx.gerar_planilha(pasta, [fx.LINHA_ANA, [None] * 16, fx.LINHA_BRUNO])
    r = ne.ler_planilha(caminho)
    checar(r.tipo == "planilha", r.tipo)
    checar(len(r.linhas) == 2, f"duas linhas com dado: {len(r.linhas)}")
    checar(r.ignoradas == 1, f"uma linha vazia ignorada e contada: {r.ignoradas}")
    ana, bruno = r.linhas
    checar(ana.ordem == 1 and bruno.ordem == 2, (ana.ordem, bruno.ordem))
    checar(ana.aba == "Notas" and ana.linha_planilha == 2, (ana.aba, ana.linha_planilha))
    checar(bruno.linha_planilha == 4, "a linha vazia conta na numeracao da planilha")
    checar(ana.campos["responsavel_cpf"] == "123.456.789-09", ana.campos)
    checar(ana.campos["valor"] == "1250" and ana.tipos["valor"] == "numero",
           (ana.campos["valor"], ana.tipos))
    checar(bruno.campos["valor"] == "980.5", bruno.campos["valor"])
    checar(ana.campos["municipio_ibge"] == "2927408", ana.campos)
    checar(bruno.campos["cep"] is None, "celula vazia = None, nunca ''")
    prov = ana.proveniencia["valor"]
    checar(prov == {"celula": "H2", "rotulo": "Valor (R$)",
                    "regra": "planilha.coluna_por_rotulo", "tipo_celula": "numero"},
           prov)
    checar(r.avisos == [], r.avisos)


def testar_planilha_colunas(pasta: str) -> None:
    # Ordem trocada, titulo acima do cabecalho e rotulos curtos: acha pelo rotulo.
    rotulos = ["Valor", "Aluno", "Turma", "CPF", "Responsável", "Competência",
               "Observação"]
    linha = [980.5, "Lia Exemplo", "Infantil 2", "987.654.321-00",
             "Carla Teste", "11/2026", "irmã do Pedro"]
    caminho = fx.gerar_planilha(pasta, [linha], nome="trocada.xlsx",
                                rotulos=rotulos,
                                antes=[["Escola Exemplo - lista de novembro"]])
    r = ne.ler_planilha(caminho)
    l = r.linhas[0]
    checar(l.campos["aluno_nome"] == "Lia Exemplo" and l.campos["valor"] == "980.5",
           l.campos)
    checar(l.linha_planilha == 3, l.linha_planilha)
    checar(l.proveniencia["turma"]["celula"] == "C3", l.proveniencia["turma"])
    checar(len(r.avisos) == 1 and "Observação" in r.avisos[0],
           f"coluna desconhecida vira aviso do lote: {r.avisos}")

    sem_cpf = fx.gerar_planilha(pasta, [linha[:3]], nome="sem_cpf.xlsx",
                                rotulos=["Valor", "Aluno", "Turma", "Responsável",
                                         "Competência"])
    e = erro(ne.ler_planilha, sem_cpf)
    checar(e is not None and e.codigo == ne.COLUNA_OBRIGATORIA_AUSENTE
           and "CPF" in e.mensagem, e and e.mensagem)

    repetida = fx.gerar_planilha(pasta, [], nome="repetida.xlsx",
                                 rotulos=fx.ROTULOS_MODELO + ["Valor"])
    e = erro(ne.ler_planilha, repetida)
    checar(e is not None and e.codigo == ne.COLUNA_REPETIDA, e and e.codigo)

    sem_cabecalho = fx.gerar_planilha(pasta, [], nome="sem_cab.xlsx",
                                      rotulos=["a", "b", "c"])
    e = erro(ne.ler_planilha, sem_cabecalho)
    checar(e is not None and e.codigo == ne.PLANILHA_SEM_CABECALHO, e and e.codigo)


def testar_planilha_celulas(pasta: str) -> None:
    linhas = [
        # CPF numerico sem zero inicial; competencia como data; formula sem valor.
        [dt.datetime(2026, 11, 1), "Ana Exemplo", 1234567890, None, None,
         "Pedro Exemplo", "Berçário", "=H2*2"] + [None] * 8,
        # Linha parcial: so o aluno. Entra (vai ter bloqueio na conferencia).
        [None, None, None, None, None, "Caio Teste"] + [None] * 10,
    ]
    caminho = fx.gerar_planilha(pasta, linhas, nome="celulas.xlsx")
    r = ne.ler_planilha(caminho)
    checar(len(r.linhas) == 2, f"linha parcial e' mantida: {len(r.linhas)}")
    l = r.linhas[0]
    checar(l.campos["responsavel_cpf"] == "1234567890"
           and l.tipos["responsavel_cpf"] == "numero", (l.campos, l.tipos))
    checar(l.campos["competencia"] == "2026-11-01" and l.tipos["competencia"] == "data",
           l.campos["competencia"])
    checar(l.campos["valor"] is None, f"formula sem valor = ausente: {l.campos['valor']}")
    checar(l.proveniencia["valor"].get("formula_sem_valor") is True,
           l.proveniencia["valor"])
    parcial = r.linhas[1]
    checar(parcial.campos["aluno_nome"] == "Caio Teste"
           and parcial.campos["responsavel_cpf"] is None, parcial.campos)


def testar_planilha_hostil(pasta: str) -> None:
    macro = fx.planilha_com_macro(pasta)
    e = erro(ne.ler_planilha, macro)
    checar(e is not None and e.codigo == ne.ARQUIVO_RECUSADO
           and "macro" in e.mensagem, e and (e.codigo, e.mensagem))
    falsa = os.path.join(pasta, "falsa.xlsx")
    with open(falsa, "w", encoding="utf-8") as arq:
        arq.write("Competencia;CPF\n11/2026;123")
    e = erro(ne.ler_planilha, falsa)
    checar(e is not None and e.codigo == ne.ARQUIVO_RECUSADO, e and e.codigo)
    grande = fx.gerar_planilha(pasta, [fx.LINHA_ANA] * 6, nome="grande.xlsx")
    e = erro(ne.ler_planilha, grande, max_linhas=5)
    checar(e is not None and e.codigo == ne.PLANILHA_GRANDE_DEMAIS, e and e.codigo)


# ----------------------------------------------------------------------
# Texto colado


def testar_texto_tres_blocos() -> None:
    r = ne.ler_texto(fx.TEXTO_TRES_BLOCOS, TURMAS)
    checar(r.tipo == "texto", r.tipo)
    checar(len(r.linhas) == 3, f"tres blocos: {len(r.linhas)}")
    ana, bruno, carla = r.linhas
    checar((ana.bloco, bruno.bloco, carla.bloco) == (1, 2, 3), "numero do bloco")
    checar(ana.texto_linha_ini == 3 and ana.texto_linha_fim == 9,
           (ana.texto_linha_ini, ana.texto_linha_fim))
    checar(ana.campos["aluno_nome"] == "Pedro Exemplo"
           and ana.campos["turma"] == "BERÇÁRIO", ana.campos)
    checar(ana.proveniencia["turma"]["regra"] == "texto.turma_no_aluno",
           ana.proveniencia["turma"])
    checar(ana.campos["cep"] == "40000000"
           and ana.proveniencia["cep"]["regra"] == "texto.cep_no_endereco",
           ana.campos["cep"])
    checar(ana.campos["endereco_texto"].startswith("Rua das Flores"), ana.campos)
    checar(ana.campos["valor"] == "R$ 1.250,00", ana.campos["valor"])
    checar(ana.proveniencia["valor"] == {"linha_texto": 9, "rotulo": "Valor",
                                         "regra": "texto.rotulo"},
           ana.proveniencia["valor"])
    checar(bruno.campos["turma"] == "Bercario I", bruno.campos)
    # Rotulos em minusculas, com "-" no lugar de ":".
    checar(carla.campos["responsavel_nome"] == "Carla Teste"
           and carla.campos["turma"] == "Infantil 2"
           and carla.campos["valor"] is None, carla.campos)
    checar(len(r.avisos) == 1 and "Boa tarde" in r.avisos[0],
           f"texto antes do primeiro bloco aparece como aviso: {r.avisos}")


def testar_texto_prefixo() -> None:
    r = ne.ler_texto(fx.TEXTO_PREFIXO, TURMAS)
    checar(len(r.linhas) == 1, len(r.linhas))
    l = r.linhas[0]
    checar(l.campos["competencia"] == "11/2026" and l.campos["valor"] == "1.250,00"
           and l.campos["aluno_nome"] == "Pedro Exemplo", l.campos)
    checar(l.nao_reconhecido == (), l.nao_reconhecido)


def testar_texto_repetido_e_sobras() -> None:
    r = ne.ler_texto(fx.TEXTO_REPETIDO, TURMAS)
    l = r.linhas[0]
    checar(l.rotulos_repetidos == ("Valor",), l.rotulos_repetidos)
    checar(l.campos["valor"] == "1.250,00", "o primeiro valor fica; nada e' escolhido")
    checar(l.nao_reconhecido == ("obs: pagou adiantado",), l.nao_reconhecido)


def testar_texto_blocos_sem_quebra() -> None:
    # Competencia sozinha, linha em branco, depois o resto: e' um bloco so.
    texto = ("Competência: 11/2026\n\nResponsável: Ana Exemplo\nCPF: 123.456.789-09\n"
             "Aluno: Pedro Exemplo\nTurma: Berçário\nValor: 1.250,00\n"
             "Responsável: Bruno Teste\nCPF: 111.444.777-35\nAluno: Caio Teste\n")
    r = ne.ler_texto(texto, TURMAS)
    checar(len(r.linhas) == 2, f"rotulo repetido abre bloco novo: {len(r.linhas)}")
    checar(r.linhas[0].campos["competencia"] == "11/2026", r.linhas[0].campos)
    checar(r.linhas[1].campos["competencia"] is None,
           "competencia nao e' copiada de outro bloco (nada e' chutado)")


def testar_texto_limites() -> None:
    e = erro(ne.ler_texto, "x" * (ne.MAX_TEXTO_BYTES + 1), TURMAS)
    checar(e is not None and e.codigo == ne.TEXTO_GRANDE_DEMAIS, e and e.codigo)
    e = erro(ne.ler_texto, "Bom dia, tudo bem?\nAmanhã mando a lista.", TURMAS)
    checar(e is not None and e.codigo == ne.TEXTO_SEM_BLOCOS, e and e.codigo)
    r = ne.ler_texto(fx.TEXTO_INVISIVEIS, TURMAS)
    checar(r.linhas[0].campos["responsavel_nome"] == "Ana​ Exemplo",
           "o bruto guarda o caractere; a conferencia avisa e limpa")


def main() -> int:
    with tempfile.TemporaryDirectory() as pasta:
        testar_planilha_modelo(pasta)
        testar_planilha_colunas(pasta)
        testar_planilha_celulas(pasta)
        testar_planilha_hostil(pasta)
    testar_texto_tres_blocos()
    testar_texto_prefixo()
    testar_texto_repetido_e_sobras()
    testar_texto_blocos_sem_quebra()
    testar_texto_limites()
    print("OK - entrada da NFS-e (planilha por rotulo com proveniencia de "
          "celula, linha vazia contada, parcial mantida, formula sem valor = "
          "ausente, pacote hostil recusado; texto em blocos com rotulos "
          "variados, turma junto do aluno, prefixo de mensagem, rotulo "
          "repetido e sobras como aviso) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
