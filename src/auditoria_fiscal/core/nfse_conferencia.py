"""Conferencia do lote da Emissao de NFS-e (spec 006, historia 5).

Funcao pura: recebe a versao do perfil, as linhas com os valores efetivos
(bruto ou a ultima correcao), as chaves de duplicata ja reservadas por lotes
aprovados e a data de hoje; devolve os valores normalizados e os apontamentos
de cada linha. Quem grava a rodada e' `ferramentas/nfse_store.py`.

Cada regra mora num lugar so e devolve apontamento com codigo do catalogo
(`core/nfse.CATALOGO`). Bloqueio impede a aprovacao; aviso pede confirmacao
na tela.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field

from . import nfse as nf

VERSAO_REGRAS = "1"

SITUACAO_OK = "ok"
SITUACAO_AVISO = "aviso"
SITUACAO_BLOQUEIO = "bloqueio"
SITUACAO_EXCLUIDA = "excluida"

CAMPOS_ENDERECO = (("cep", "CEP"), ("logradouro", "logradouro"),
                   ("numero", "número"), ("bairro", "bairro"),
                   ("municipio_ibge", "código IBGE do município"))


@dataclass
class LinhaConferida:
    ref: int
    excluida: bool = False
    cpf: str | None = None
    competencia: str | None = None
    valor_centavos: int | None = None
    turma: nf.Turma | None = None
    responsavel: str | None = None
    aluno: str | None = None
    endereco: dict | None = None
    chave_duplicata: str | None = None
    discriminacao: str | None = None
    apontamentos: list[nf.Apontamento] = field(default_factory=list)
    situacao: str = SITUACAO_OK


@dataclass
class ResultadoConferencia:
    linhas: list[LinhaConferida]
    competencia_predominante: str | None
    totais: dict


def _texto(linha: LinhaConferida, bruto, campo: str) -> str:
    texto, removeu = nf.normalizar_texto(bruto)
    if removeu:
        linha.apontamentos.append(nf.apontamento(
            nf.CARACTERE_REMOVIDO, campo,
            "Havia caractere invisível ou de controle no campo; foi removido."))
    return texto


def _conferir_cpf(linha, campos, tipos):
    try:
        linha.cpf, completado = nf.ler_cpf(
            campos.get("responsavel_cpf"), tipo=tipos.get("responsavel_cpf", "texto"))
    except nf.ErroNfse as exc:
        linha.apontamentos.append(nf.apontamento(exc.codigo, "responsavel_cpf",
                                                 exc.mensagem))
        return
    if completado:
        linha.apontamentos.append(nf.apontamento(
            nf.CPF_COMPLETADO, "responsavel_cpf",
            "A célula da planilha era número e perdeu o zero inicial; o CPF foi "
            f"completado para {linha.cpf}. Confira."))


def _conferir_valor(linha, campos, tipos):
    try:
        linha.valor_centavos = nf.ler_valor(campos.get("valor"),
                                            tipo=tipos.get("valor", "texto"))
    except nf.ErroNfse as exc:
        linha.apontamentos.append(nf.apontamento(exc.codigo, "valor", exc.mensagem))


def _conferir_competencia(linha, campos, tipos, hoje: dt.date):
    try:
        competencia = nf.ler_competencia(campos.get("competencia"),
                                         tipo=tipos.get("competencia", "texto"))
    except nf.ErroNfse as exc:
        linha.apontamentos.append(nf.apontamento(exc.codigo, "competencia",
                                                 exc.mensagem))
        return
    linha.competencia = competencia
    if nf.primeiro_dia(competencia) > hoje:
        linha.apontamentos.append(nf.apontamento(
            nf.COMPETENCIA_FUTURA, "competencia",
            f"A competência {competencia[5:]}/{competencia[:4]} ainda não começou; o "
            "Emissor Nacional recusa competência posterior à data de emissão "
            "(E0015)."))


def _conferir_turma(linha, campos, perfil: nf.PerfilVersao):
    bruto = _texto(linha, campos.get("turma"), "turma")
    if not bruto:
        linha.apontamentos.append(nf.apontamento(
            nf.TURMA_AUSENTE, "turma", "Turma não informada."))
        return
    turma = nf.resolver_turma(bruto, perfil.turmas)
    if turma is None:
        nomes = ", ".join(t.nome for t in perfil.turmas)
        linha.apontamentos.append(nf.apontamento(
            nf.TURMA_DESCONHECIDA, "turma",
            f"Turma {bruto!r} não está no perfil. Turmas: {nomes}."))
        return
    linha.turma = turma
    if nf.turma_pendente(turma):
        linha.apontamentos.append(nf.apontamento(
            nf.TURMA_PENDENTE, "turma",
            f"A turma {turma.nome!r} ainda não tem código de tributação "
            "nacional ou NBS no perfil (JB-3)."))


def _conferir_nomes(linha, campos):
    responsavel = _texto(linha, campos.get("responsavel_nome"), "responsavel_nome")
    if not responsavel:
        linha.apontamentos.append(nf.apontamento(
            nf.RESPONSAVEL_AUSENTE, "responsavel_nome",
            "Nome do responsável não informado."))
    elif len(responsavel) > nf.MAX_NOME:
        linha.apontamentos.append(nf.apontamento(
            nf.NOME_LONGO, "responsavel_nome",
            f"O nome do responsável passa de {nf.MAX_NOME} caracteres."))
    else:
        linha.responsavel = responsavel
    aluno = _texto(linha, campos.get("aluno_nome"), "aluno_nome")
    if not aluno:
        linha.apontamentos.append(nf.apontamento(
            nf.ALUNO_AUSENTE, "aluno_nome", "Nome do aluno não informado."))
    else:
        linha.aluno = aluno


def _conferir_endereco(linha, campos, perfil: nf.PerfilVersao):
    if perfil.endereco_tomador == nf.ENDERECO_OMITIR:
        return
    nivel = nf.BLOQUEIO if perfil.endereco_tomador == nf.ENDERECO_INFORMAR else nf.AVISO
    partes = {c: _texto(linha, campos.get(c), c) for c, _ in CAMPOS_ENDERECO}
    complemento = _texto(linha, campos.get("complemento"), "complemento")
    estruturado = any(partes[c] for c in ("logradouro", "numero", "bairro",
                                          "municipio_ibge"))
    texto_livre = _texto(linha, campos.get("endereco_texto"), "endereco_texto")
    if not estruturado and texto_livre:
        linha.apontamentos.append(nf.apontamento(
            nf.ENDERECO_NAO_ESTRUTURADO, "endereco_texto",
            "O endereço veio em texto livre. Para ir na nota, ele precisa de CEP, "
            "logradouro, número, bairro e código IBGE do município separados.",
            nivel=nivel))
        return
    if not estruturado and not partes["cep"]:
        linha.apontamentos.append(nf.apontamento(
            nf.ENDERECO_INCOMPLETO, "endereco", "Endereço não informado.",
            nivel=nivel))
        return

    faltam = [rotulo for campo, rotulo in CAMPOS_ENDERECO if not partes[campo]]
    cep = re.sub(r"\D", "", partes["cep"])
    ibge = re.sub(r"\D", "", partes["municipio_ibge"])
    if partes["cep"] and len(cep) != 8:
        faltam.append("CEP com 8 dígitos")
    if partes["municipio_ibge"] and len(ibge) != 7:
        faltam.append("código IBGE com 7 dígitos")
    for campo, limite, rotulo in (("logradouro", nf.MAX_LOGRADOURO, "logradouro"),
                                  ("numero", nf.MAX_NUMERO, "número"),
                                  ("bairro", nf.MAX_BAIRRO, "bairro")):
        if len(partes[campo]) > limite:
            faltam.append(f"{rotulo} com até {limite} caracteres")
    if len(complemento) > nf.MAX_COMPLEMENTO:
        faltam.append(f"complemento com até {nf.MAX_COMPLEMENTO} caracteres")
    if faltam:
        linha.apontamentos.append(nf.apontamento(
            nf.ENDERECO_INCOMPLETO, "endereco",
            "Endereço incompleto: falta " + ", ".join(faltam) + ".", nivel=nivel))
        return
    if perfil.endereco_tomador == nf.ENDERECO_INFORMAR:
        linha.endereco = {"cMun": ibge, "CEP": cep, "xLgr": partes["logradouro"],
                          "nro": partes["numero"], "xCpl": complemento or None,
                          "xBairro": partes["bairro"]}


def _conferir_bloco_de_texto(linha, efetiva: nf.LinhaEfetiva):
    for rotulo in efetiva.rotulos_repetidos:
        linha.apontamentos.append(nf.apontamento(
            nf.ROTULO_REPETIDO, rotulo,
            f"O rótulo {rotulo!r} aparece duas vezes no bloco; o sistema não "
            "escolhe um dos valores. Corrija o campo."))
    if efetiva.nao_reconhecido:
        linha.apontamentos.append(nf.apontamento(
            nf.TEXTO_NAO_RECONHECIDO, None,
            "Linhas sem rótulo no bloco: " + " / ".join(efetiva.nao_reconhecido)))


def _discriminacao(linha, perfil: nf.PerfilVersao):
    if not (linha.turma and linha.aluno and linha.competencia):
        return
    texto = nf.montar_discriminacao(
        perfil.modelo_discriminacao, turma=linha.turma.nome, aluno=linha.aluno,
        responsavel=linha.responsavel or "", competencia=linha.competencia)
    linha.discriminacao = texto
    if len(texto) > nf.MAX_DISCRIMINACAO:
        linha.apontamentos.append(nf.apontamento(
            nf.DISCRIMINACAO_LONGA, "discriminacao",
            f"A discriminação montada tem {len(texto)} caracteres; o limite do "
            f"Emissor Nacional é {nf.MAX_DISCRIMINACAO}."))


def _situacao(linha: LinhaConferida) -> str:
    if linha.excluida:
        return SITUACAO_EXCLUIDA
    niveis = {a.nivel for a in linha.apontamentos}
    if nf.BLOQUEIO in niveis:
        return SITUACAO_BLOQUEIO
    if nf.AVISO in niveis:
        return SITUACAO_AVISO
    return SITUACAO_OK


def conferir(perfil: nf.PerfilVersao, linhas: list[nf.LinhaEfetiva], *,
             chaves_aprovadas: dict[str, int], hoje: dt.date) -> ResultadoConferencia:
    """Confere o lote inteiro. `chaves_aprovadas` = chave -> id do lote aprovado."""
    conferidas: list[LinhaConferida] = []
    for efetiva in linhas:
        linha = LinhaConferida(ref=efetiva.ref, excluida=efetiva.excluida)
        conferidas.append(linha)
        if efetiva.excluida:
            linha.situacao = SITUACAO_EXCLUIDA
            continue
        campos, tipos = efetiva.campos, efetiva.tipos
        _conferir_cpf(linha, campos, tipos)
        _conferir_valor(linha, campos, tipos)
        _conferir_competencia(linha, campos, tipos, hoje)
        _conferir_turma(linha, campos, perfil)
        _conferir_nomes(linha, campos)
        _conferir_endereco(linha, campos, perfil)
        _conferir_bloco_de_texto(linha, efetiva)
        _discriminacao(linha, perfil)
        if linha.cpf and linha.aluno and linha.competencia:
            linha.chave_duplicata = "|".join(
                (linha.cpf, nf.chave_comparacao(linha.aluno), linha.competencia))

    # Duplicata: dentro do lote, a primeira ocorrencia fica; contra lotes
    # aprovados, a reserva do banco e' a fonte (chaves_aprovadas).
    primeira: dict[str, int] = {}
    for linha in conferidas:
        if linha.excluida or not linha.chave_duplicata:
            continue
        chave = linha.chave_duplicata
        if chave in primeira:
            linha.apontamentos.append(nf.apontamento(
                nf.DUPLICATA_NO_LOTE, None,
                f"Mesmo CPF, aluno e competência da linha {primeira[chave]} deste "
                "lote.", referencia={"linha": primeira[chave]}))
        else:
            primeira[chave] = linha.ref
        if chave in chaves_aprovadas:
            linha.apontamentos.append(nf.apontamento(
                nf.DUPLICATA_APROVADA, None,
                f"Esta nota já está no lote aprovado {chaves_aprovadas[chave]}.",
                referencia={"lote": chaves_aprovadas[chave]}))

    contagem = Counter(l.competencia for l in conferidas
                       if not l.excluida and l.competencia)
    predominante = None
    if contagem:
        (primeira_comp, maior), *resto = contagem.most_common()
        if not resto or resto[0][1] < maior:
            predominante = primeira_comp
    if predominante:
        for linha in conferidas:
            if (not linha.excluida and linha.competencia
                    and linha.competencia != predominante):
                linha.apontamentos.append(nf.apontamento(
                    nf.COMPETENCIA_DIVERGENTE, "competencia",
                    f"A maioria do lote é {predominante[5:]}/{predominante[:4]}; "
                    "confira esta competência.",
                    referencia={"predominante": predominante}))

    for linha in conferidas:
        linha.situacao = _situacao(linha)
    ativas = [l for l in conferidas if not l.excluida]
    totais = {
        "linhas": len(conferidas),
        "ativas": len(ativas),
        "excluidas": len(conferidas) - len(ativas),
        "bloqueio": sum(1 for l in ativas if l.situacao == SITUACAO_BLOQUEIO),
        "aviso": sum(1 for l in ativas if l.situacao == SITUACAO_AVISO),
        "ok": sum(1 for l in ativas if l.situacao == SITUACAO_OK),
        "soma_centavos": sum(l.valor_centavos or 0 for l in ativas),
    }
    return ResultadoConferencia(conferidas, predominante, totais)
