"""Coletor da pasta de certificados do escritorio (spec 012, US8/FR-016).

A JB guarda os certificados numa pasta compartilhada da rede, com uma
subpasta por cliente: o `.pfx`, a chave `.key` e um texto `_info` digitado a
mao (razao social, fantasia, CNPJ, validade e a SENHA do certificado). O
servidor do sistema roda na nuvem e nao alcanca essa pasta; este coletor roda
num computador do escritorio, le cada `.pfx` com a senha do `_info` e grava um
arquivo de coleta para enviar na aba 9.

O que a coleta leva: titular, documento, AC, validade, serie, hash do arquivo
e o que o `_info` diz (menos a senha). O que NAO leva: senha, chave privada
nem o certificado (pendencia P-13 da spec). A validade que vale e' a de
dentro do certificado; a do `_info` so aparece como divergencia.
"""

from __future__ import annotations

import os
from datetime import datetime

from . import certificados as ct
from . import clientes as cl

FORMATO = "auditoria-jb/coleta-certificados"
VERSAO = 1

SEM_CERTIFICADO = "SEM_CERTIFICADO"
SEM_INFO = "SEM_INFO"
SEM_SENHA = "SEM_SENHA"
SENHA_NAO_ABRE = "SENHA_NAO_ABRE"
CERTIFICADO_INVALIDO = "CERTIFICADO_INVALIDO"
VARIOS_CERTIFICADOS = "VARIOS_CERTIFICADOS"
VALIDADE_DIVERGENTE = "VALIDADE_DIVERGENTE"
DOCUMENTO_DIVERGENTE = "DOCUMENTO_DIVERGENTE"

MENSAGENS = {
    SEM_CERTIFICADO: "Pasta sem .pfx nem .cer.",
    SEM_INFO: "Pasta sem o texto _info.",
    SEM_SENHA: "Sem senha no _info: o .pfx não pôde ser aberto.",
    SENHA_NAO_ABRE: "A senha do _info não abre o .pfx.",
    CERTIFICADO_INVALIDO: "Arquivo de certificado corrompido ou desconhecido.",
    VARIOS_CERTIFICADOS: "Mais de um certificado na pasta.",
    VALIDADE_DIVERGENTE: "A validade do _info é diferente da do certificado.",
    DOCUMENTO_DIVERGENTE: "O CNPJ do _info é diferente do do certificado.",
}

EXTENSOES_PFX = (".pfx", ".p12")
EXTENSOES_CER = (".cer", ".crt")

_ROTULOS_INFO = (
    ("FANTASIA", "nome_fantasia"),
    ("RAZAO", "razao_social"),
    ("CNPJ", "documento"), ("CPF", "documento"),
    ("VALIDADE", "validade"), ("VENCIMENTO", "validade"),
    ("SENHA", "senha"),
)


def _ler_texto(caminho: str) -> str:
    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read(64 * 1024)
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1")


def ler_info(texto: str) -> dict:
    """Rotulo: valor, em qualquer ordem. A senha sai separada do resto."""
    dados: dict[str, str] = {}
    for linha in texto.splitlines():
        if ":" not in linha:
            continue
        rotulo, _, valor = linha.partition(":")
        chave = cl.chave_texto(rotulo)
        for trecho, campo in _ROTULOS_INFO:
            if trecho in chave and campo not in dados:
                # Senha preserva espacos internos; o resto e' texto comum.
                dados[campo] = valor.strip() if campo != "senha" \
                    else valor.strip("\r\n").strip()
                break
    if "documento" in dados:
        try:
            dados["documento"] = cl.normalizar_documento(dados["documento"])
        except cl.ErroClientes:
            dados["documento_invalido"] = dados.pop("documento")
    if "validade" in dados:
        data = cl.data_plausivel(dados["validade"])
        if data is not None:
            dados["validade"] = data.isoformat()
        else:
            dados["validade_invalida"] = dados.pop("validade")
    return dados


def _arquivos(pasta: str) -> tuple[list[str], list[str], str | None]:
    certificados, cers, info = [], [], None
    for nome in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho) or os.path.islink(caminho):
            continue
        minusculo = nome.lower()
        if minusculo.endswith(EXTENSOES_PFX):
            certificados.append(caminho)
        elif minusculo.endswith(EXTENSOES_CER):
            cers.append(caminho)
        elif os.path.splitext(minusculo)[0] == "_info" and info is None:
            info = caminho
    return certificados, cers, info


def _item_base(subpasta: str, info: dict) -> dict:
    return {
        "pasta": subpasta, "arquivo": "", "hash_arquivo": "",
        "titular_nome": "", "titular_documento": "", "emissor": "",
        "inicio": "", "fim": "", "serie": "", "tipo": "",
        "info": {k: v for k, v in info.items() if k != "senha"},
        "problemas": [],
    }


def _coletar_subpasta(caminho: str, subpasta: str) -> list[dict]:
    pfxs, cers, caminho_info = _arquivos(caminho)
    info = ler_info(_ler_texto(caminho_info)) if caminho_info else {}
    senha = info.get("senha")
    arquivos = pfxs or cers
    if not arquivos:
        item = _item_base(subpasta, info)
        item["problemas"].append(SEM_CERTIFICADO)
        if not caminho_info:
            item["problemas"].append(SEM_INFO)
        return [item]

    itens = []
    for arquivo in arquivos:
        item = _item_base(subpasta, info)
        item["arquivo"] = os.path.basename(arquivo)
        if not caminho_info:
            item["problemas"].append(SEM_INFO)
        if len(arquivos) > 1:
            item["problemas"].append(VARIOS_CERTIFICADOS)
        with open(arquivo, "rb") as f:
            conteudo = f.read(ct.MAX_BYTES + 1)
        try:
            dados = ct.ler_certificado(conteudo, senha=senha if arquivo in pfxs
                                       else None)
        except ct.ErroCertificado as exc:
            if exc.codigo == ct.SENHA_OBRIGATORIA:
                item["problemas"].append(SEM_SENHA)
            elif exc.codigo == ct.SENHA_INCORRETA:
                item["problemas"].append(SENHA_NAO_ABRE)
            else:
                item["problemas"].append(CERTIFICADO_INVALIDO)
            itens.append(item)
            continue

        item.update({k: v for k, v in dados.como_dict().items()})
        if info.get("validade") and info["validade"] != item["fim"]:
            item["problemas"].append(VALIDADE_DIVERGENTE)
        if (info.get("documento") and item["titular_documento"]
                and info["documento"] != item["titular_documento"]):
            item["problemas"].append(DOCUMENTO_DIVERGENTE)
        itens.append(item)
    return itens


def coletar(raiz: str, *, agora: datetime | None = None) -> dict:
    if not os.path.isdir(raiz):
        raise FileNotFoundError(f"Pasta não encontrada: {raiz}")
    itens: list[dict] = []
    subpastas = 0
    for nome in sorted(os.listdir(raiz), key=str.upper):
        caminho = os.path.join(raiz, nome)
        if not os.path.isdir(caminho) or os.path.islink(caminho):
            continue
        subpastas += 1
        itens.extend(_coletar_subpasta(caminho, nome))
    lidos = sum(1 for i in itens if i["fim"])
    return {
        "formato": FORMATO, "versao": VERSAO,
        "gerada_em": (agora or datetime.now()).isoformat(timespec="seconds"),
        "pasta": os.path.basename(os.path.normpath(raiz)),
        "totais": {"subpastas": subpastas, "certificados": len(itens),
                   "lidos": lidos,
                   "com_problema": sum(1 for i in itens if i["problemas"])},
        "itens": itens,
    }


def resumo_texto(coleta: dict) -> str:
    """Resumo para a tela do comando — so contagens e nomes de pasta."""
    totais = coleta["totais"]
    linhas = [f"Subpastas: {totais['subpastas']}",
              f"Certificados encontrados: {totais['certificados']}",
              f"Lidos com validade: {totais['lidos']}",
              f"Com algum problema: {totais['com_problema']}"]
    contagem: dict[str, int] = {}
    for item in coleta["itens"]:
        for problema in item["problemas"]:
            contagem[problema] = contagem.get(problema, 0) + 1
    for problema, n in sorted(contagem.items(), key=lambda p: -p[1]):
        linhas.append(f"  {n:4d}  {MENSAGENS.get(problema, problema)}")
    return "\n".join(linhas)


def nome_padrao(agora: datetime | None = None) -> str:
    return f"coleta-certificados-{(agora or datetime.now()):%Y%m%d-%H%M}.json"
