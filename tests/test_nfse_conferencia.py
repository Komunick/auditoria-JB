"""Conferencia do lote da NFS-e (spec 006, historia 5): cada codigo do
catalogo dispara no caso dele e nao dispara na linha boa. Funcao pura, sem
banco: recebe perfil, linhas efetivas, chaves ja aprovadas e a data de hoje.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from auditoria_fiscal.core import nfse as nf  # noqa: E402
from auditoria_fiscal.core import nfse_conferencia as nc  # noqa: E402
from fixtures import nfse as fx  # noqa: E402

HOJE = dt.date(2026, 11, 15)
OMITIR = nf.validar_perfil(fx.perfil_completo(endereco="omitir"))
INFORMAR = nf.validar_perfil(fx.perfil_completo(endereco="informar"))
PENDENTE = nf.validar_perfil(fx.perfil_completo(endereco_tomador=None))

ENDERECO = {"cep": "40000-000", "logradouro": "Rua das Flores", "numero": "100",
            "complemento": "ap 201", "bairro": "Bairro Exemplo",
            "municipio_ibge": "2927408"}


def checar(cond, msg):
    if not cond:
        print(f"FALHOU - {msg}")
        raise SystemExit(1)


def linha(ref=1, *, tipos=None, excluida=False, nao_reconhecido=(),
          rotulos_repetidos=(), endereco=True, **campos):
    base = {"competencia": "11/2026", "responsavel_nome": "Ana Exemplo",
            "responsavel_cpf": fx.CPF_ANA, "aluno_nome": "Pedro Exemplo",
            "turma": "Berçário", "valor": "R$ 1.250,00"}
    if endereco:
        base.update(ENDERECO)
    base.update(campos)
    return nf.LinhaEfetiva(ref=ref, campos=base, tipos=tipos or {},
                           excluida=excluida, nao_reconhecido=nao_reconhecido,
                           rotulos_repetidos=rotulos_repetidos)


def conferir(linhas, perfil=OMITIR, aprovadas=None):
    return nc.conferir(perfil, linhas, chaves_aprovadas=aprovadas or {}, hoje=HOJE)


def codigos(resultado, indice=0):
    return [(a.codigo, a.nivel) for a in resultado.linhas[indice].apontamentos]


def so(resultado, codigo, nivel=None, indice=0):
    """A linha tem exatamente este apontamento."""
    obtido = codigos(resultado, indice)
    esperado = [(codigo, nivel or nf.CATALOGO[codigo])]
    checar(obtido == esperado, f"esperado {esperado}, obtido {obtido}")


def testar_linha_boa() -> None:
    for perfil in (OMITIR, INFORMAR):
        r = conferir([linha()], perfil)
        l = r.linhas[0]
        checar(l.apontamentos == [], f"linha boa sem apontamento: {codigos(r)}")
        checar(l.situacao == "ok", l.situacao)
        checar((l.cpf, l.competencia, l.valor_centavos) == ("12345678909", "2026-11", 125000),
               (l.cpf, l.competencia, l.valor_centavos))
        checar(l.turma.nome == "Berçário" and l.aluno == "Pedro Exemplo"
               and l.responsavel == "Ana Exemplo", (l.turma, l.aluno))
        checar(l.discriminacao == "REFERENTE AOS SERVIÇOS PRESTADOS DE BERÇÁRIO AO "
                                  "MENOR: PEDRO EXEMPLO NO PERÍODO DE 11/2026.",
               l.discriminacao)
        checar(l.chave_duplicata == "12345678909|pedro exemplo|2026-11",
               l.chave_duplicata)
    l = conferir([linha()], INFORMAR).linhas[0]
    checar(l.endereco == {"cMun": "2927408", "CEP": "40000000", "xLgr": "Rua das Flores",
                          "nro": "100", "xCpl": "ap 201", "xBairro": "Bairro Exemplo"},
           l.endereco)
    checar(conferir([linha()], OMITIR).linhas[0].endereco is None,
           "com 'omitir' o endereco nao vai para a nota")


def testar_cpf() -> None:
    so(conferir([linha(responsavel_cpf=None)]), nf.CPF_AUSENTE)
    so(conferir([linha(responsavel_cpf=fx.CPF_RUIM)]), nf.CPF_INVALIDO)
    r = conferir([linha(responsavel_cpf="1234567890", tipos={"responsavel_cpf": "numero"})])
    so(r, nf.CPF_COMPLETADO)
    checar(r.linhas[0].cpf == "01234567890" and r.linhas[0].situacao == "aviso",
           (r.linhas[0].cpf, r.linhas[0].situacao))
    so(conferir([linha(responsavel_cpf="1234567890")]), nf.CPF_INVALIDO)


def testar_valor() -> None:
    r = conferir([linha(valor=None)])
    so(r, nf.VALOR_AUSENTE)
    checar(r.linhas[0].valor_centavos is None, "valor ausente nunca vira zero")
    so(conferir([linha(valor="abc")]), nf.VALOR_INVALIDO)
    so(conferir([linha(valor="1.250")]), nf.VALOR_INVALIDO)
    so(conferir([linha(valor="0,00")]), nf.VALOR_NAO_POSITIVO)
    r = conferir([linha(valor="980.5", tipos={"valor": "numero"})])
    checar(r.linhas[0].valor_centavos == 98050 and r.linhas[0].apontamentos == [],
           r.linhas[0].valor_centavos)


def testar_competencia() -> None:
    so(conferir([linha(competencia=None)]), nf.COMPETENCIA_AUSENTE)
    so(conferir([linha(competencia="13/2026")]), nf.COMPETENCIA_INVALIDA)
    so(conferir([linha(competencia="12/2026")]), nf.COMPETENCIA_FUTURA)
    r = conferir([linha(competencia="2026-11-01", tipos={"competencia": "data"})])
    checar(r.linhas[0].competencia == "2026-11" and r.linhas[0].apontamentos == [],
           codigos(r))

    linhas = [linha(1), linha(2, responsavel_cpf=fx.CPF_BRUNO, aluno_nome="Caio Teste"),
              linha(3, responsavel_cpf=fx.CPF_CARLA, aluno_nome="Lia Exemplo",
                    competencia="10/2026")]
    r = conferir(linhas)
    checar(r.competencia_predominante == "2026-11", r.competencia_predominante)
    checar(codigos(r, 0) == [] and codigos(r, 1) == [], "as da maioria ficam limpas")
    so(r, nf.COMPETENCIA_DIVERGENTE, indice=2)
    empate = conferir([linha(1), linha(2, responsavel_cpf=fx.CPF_BRUNO,
                                       aluno_nome="Caio Teste", competencia="10/2026")])
    checar(empate.competencia_predominante is None
           and all(not l.apontamentos for l in empate.linhas),
           "empate: sem maioria, sem aviso")


def testar_turma() -> None:
    so(conferir([linha(turma=None)]), nf.TURMA_AUSENTE)
    r = conferir([linha(turma="Infantil")])
    so(r, nf.TURMA_DESCONHECIDA)
    checar("Infantil II" in r.linhas[0].apontamentos[0].mensagem,
           "a mensagem lista as turmas do perfil")
    so(conferir([linha(turma="Fundamental I")]), nf.TURMA_PENDENTE)
    r = conferir([linha(turma="bercario 1")])
    checar(r.linhas[0].turma.nome == "Berçário" and not r.linhas[0].apontamentos,
           "apelido resolve")


def testar_nomes() -> None:
    so(conferir([linha(responsavel_nome="  ")]), nf.RESPONSAVEL_AUSENTE)
    r = conferir([linha(aluno_nome=None)])
    so(r, nf.ALUNO_AUSENTE)
    checar(r.linhas[0].discriminacao is None, "sem aluno nao ha discriminacao")
    so(conferir([linha(responsavel_nome="A" * 301)]), nf.NOME_LONGO)
    r = conferir([linha(responsavel_nome="Ana​ Exemplo")])
    so(r, nf.CARACTERE_REMOVIDO)
    checar(r.linhas[0].responsavel == "Ana Exemplo", r.linhas[0].responsavel)


def testar_endereco() -> None:
    texto_livre = dict(endereco=False, endereco_texto="Rua X, 1, Centro",
                       cep="40000000")
    so(conferir([linha(**texto_livre)], INFORMAR), nf.ENDERECO_NAO_ESTRUTURADO,
       nf.BLOQUEIO)
    so(conferir([linha(**texto_livre)], PENDENTE), nf.ENDERECO_NAO_ESTRUTURADO,
       nf.AVISO)
    checar(conferir([linha(**texto_livre)], OMITIR).linhas[0].apontamentos == [],
           "com 'omitir' o endereco nao e' conferido")
    r = conferir([linha(numero=None)], INFORMAR)
    so(r, nf.ENDERECO_INCOMPLETO, nf.BLOQUEIO)
    checar("número" in r.linhas[0].apontamentos[0].mensagem,
           r.linhas[0].apontamentos[0].mensagem)
    so(conferir([linha(numero=None)], PENDENTE), nf.ENDERECO_INCOMPLETO, nf.AVISO)
    so(conferir([linha(cep="4000")], INFORMAR), nf.ENDERECO_INCOMPLETO, nf.BLOQUEIO)
    so(conferir([linha(municipio_ibge="Salvador")], INFORMAR), nf.ENDERECO_INCOMPLETO,
       nf.BLOQUEIO)
    so(conferir([linha(endereco=False)], INFORMAR), nf.ENDERECO_INCOMPLETO, nf.BLOQUEIO)


def testar_duplicata() -> None:
    r = conferir([linha(1), linha(2, aluno_nome="PEDRO  EXEMPLO")])
    checar(codigos(r, 0) == [], "a primeira ocorrencia fica")
    so(r, nf.DUPLICATA_NO_LOTE, indice=1)
    checar(r.linhas[1].apontamentos[0].referencia == {"linha": 1},
           r.linhas[1].apontamentos[0].referencia)

    irmaos = conferir([linha(1), linha(2, aluno_nome="Caio Teste")])
    checar(all(not l.apontamentos for l in irmaos.linhas),
           "mesmo CPF com alunos diferentes e' permitido (irmaos)")

    r = conferir([linha()], aprovadas={"12345678909|pedro exemplo|2026-11": 7})
    so(r, nf.DUPLICATA_APROVADA)
    checar(r.linhas[0].apontamentos[0].referencia == {"lote": 7},
           r.linhas[0].apontamentos[0].referencia)

    r = conferir([linha(1, excluida=True, valor="abc"), linha(2)])
    checar(r.linhas[0].situacao == "excluida" and r.linhas[0].apontamentos == [],
           "linha excluida nao gera apontamento")
    checar(codigos(r, 1) == [], "linha excluida nao entra na duplicata")


def testar_texto_e_discriminacao() -> None:
    so(conferir([linha(rotulos_repetidos=("Valor",))]), nf.ROTULO_REPETIDO)
    r = conferir([linha(nao_reconhecido=("obs: pagou adiantado",))])
    so(r, nf.TEXTO_NAO_RECONHECIDO)
    checar("pagou adiantado" in r.linhas[0].apontamentos[0].mensagem,
           "a sobra aparece na mensagem")
    so(conferir([linha(aluno_nome="P" * 2100)]), nf.DISCRIMINACAO_LONGA)


def testar_totais() -> None:
    r = conferir([linha(1), linha(2, aluno_nome="Caio Teste", valor="980,50"),
                  linha(3, aluno_nome="Lia Exemplo", valor=None),
                  linha(4, aluno_nome="X", excluida=True)])
    checar(r.totais == {"linhas": 4, "ativas": 3, "excluidas": 1, "bloqueio": 1,
                        "aviso": 0, "ok": 2, "soma_centavos": 223050}, r.totais)


def main() -> int:
    testar_linha_boa()
    testar_cpf()
    testar_valor()
    testar_competencia()
    testar_turma()
    testar_nomes()
    testar_endereco()
    testar_duplicata()
    testar_texto_e_discriminacao()
    testar_totais()
    print("OK - conferencia da NFS-e (cada codigo do catalogo dispara so no "
          "caso dele; irmaos permitidos; duplicata no lote e contra aprovados; "
          "endereco aviso ou bloqueio conforme o perfil; valor ausente nunca "
          "vira zero; linha excluida fora da conta) passou.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
