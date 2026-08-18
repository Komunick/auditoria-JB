"""Regras de negocio do Patrimonio (nucleo puro).

Sem FastAPI, sem HTTP, sem banco: tipos, catalogo, etiqueta, CPF e a maquina
de transicoes de situacao. Quem persiste e quem serve HTTP sao outras camadas
(constituicao, principio II).

Duas regras estruturam o modulo:

1. **A etiqueta e' um contrato com o mundo fisico.** Ela e' impressa e colada
   no equipamento. Renumerar significa alguem ler a etiqueta na mesa e
   encontrar outro bem no sistema — por isso a etiqueta e' imutavel e este
   modulo so sabe FORMATAR e LER, nunca reatribuir.
2. **Baixa e' terminal.** Nao existe exclusao de bem: excluir apagaria a
   historia de um patrimonio que existiu e foi usado por alguem. O que existe
   e' baixa, que fecha o ciclo e preserva tudo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# ----------------------------------------------------------------------
# Codigos de erro estaveis

ETIQUETA_INVALIDA = "ETIQUETA_INVALIDA"
CPF_INVALIDO = "CPF_INVALIDO"
TRANSICAO_INVALIDA = "TRANSICAO_INVALIDA"
BEM_BAIXADO = "BEM_BAIXADO"
HIERARQUIA_INVALIDA = "HIERARQUIA_INVALIDA"
VALOR_INVALIDO = "VALOR_INVALIDO"
CAMPO_OBRIGATORIO = "CAMPO_OBRIGATORIO"
JUSTIFICATIVA_OBRIGATORIA = "JUSTIFICATIVA_OBRIGATORIA"


class ErroPatrimonio(Exception):
    """Falha de regra de negocio, com codigo estavel para a interface."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem


# ----------------------------------------------------------------------
# Catalogo

PREFIXO_BEM = "JBF"
PREFIXO_PERIFERICO = "PER"

SITUACAO_DISPONIVEL = "disponivel"
SITUACAO_EM_USO = "em_uso"
SITUACAO_MANUTENCAO = "manutencao"
SITUACAO_EMPRESTADO = "emprestado"
SITUACAO_BAIXADO = "baixado"

SITUACOES = {
    SITUACAO_DISPONIVEL: "Disponível",
    SITUACAO_EM_USO: "Em uso",
    SITUACAO_MANUTENCAO: "Em manutenção",
    SITUACAO_EMPRESTADO: "Emprestado (home office)",
    SITUACAO_BAIXADO: "Baixado",
}

CONSERVACOES = {
    "novo": "Novo", "bom": "Bom", "regular": "Regular", "ruim": "Ruim",
}

# Tipos que uma contabilidade realmente tem. Nao ha EPI, frota nem turno:
# esses conceitos sao da transportadora, nao daqui.
TIPOS = (
    "Notebook", "Desktop", "Monitor", "Impressora", "Scanner", "Nobreak",
    "Servidor", "Switch/Roteador", "Telefone", "Celular", "Mesa", "Cadeira",
    "Armário", "Ar-condicionado", "Licença de software", "Outro",
)

MOV_AQUISICAO = "aquisicao"
MOV_ATRIBUICAO = "atribuicao"
MOV_DEVOLUCAO = "devolucao"
MOV_MANUTENCAO = "manutencao"
MOV_RETORNO_MANUTENCAO = "retorno_manutencao"
MOV_EMPRESTIMO = "emprestimo"
MOV_RETORNO_EMPRESTIMO = "retorno_emprestimo"
MOV_TRANSFERENCIA = "transferencia"
MOV_BAIXA = "baixa"

MOVIMENTOS = {
    MOV_AQUISICAO: "Aquisição",
    MOV_ATRIBUICAO: "Atribuição de responsabilidade",
    MOV_DEVOLUCAO: "Devolução",
    MOV_MANUTENCAO: "Envio para manutenção",
    MOV_RETORNO_MANUTENCAO: "Retorno de manutenção",
    MOV_EMPRESTIMO: "Empréstimo (home office)",
    MOV_RETORNO_EMPRESTIMO: "Retorno de empréstimo",
    MOV_TRANSFERENCIA: "Transferência de local",
    MOV_BAIXA: "Baixa",
}

# De qual situacao cada movimento pode partir, e para onde leva.
# `None` no destino significa "nao muda a situacao" (caso da transferencia).
TRANSICOES: dict[str, tuple[tuple[str, ...], str | None]] = {
    MOV_ATRIBUICAO: ((SITUACAO_DISPONIVEL,), SITUACAO_EM_USO),
    MOV_DEVOLUCAO: ((SITUACAO_EM_USO, SITUACAO_EMPRESTADO),
                    SITUACAO_DISPONIVEL),
    MOV_MANUTENCAO: ((SITUACAO_DISPONIVEL, SITUACAO_EM_USO,
                      SITUACAO_EMPRESTADO), SITUACAO_MANUTENCAO),
    MOV_RETORNO_MANUTENCAO: ((SITUACAO_MANUTENCAO,), SITUACAO_DISPONIVEL),
    MOV_EMPRESTIMO: ((SITUACAO_EM_USO,), SITUACAO_EMPRESTADO),
    MOV_RETORNO_EMPRESTIMO: ((SITUACAO_EMPRESTADO,), SITUACAO_EM_USO),
    MOV_TRANSFERENCIA: ((SITUACAO_DISPONIVEL, SITUACAO_EM_USO,
                         SITUACAO_MANUTENCAO, SITUACAO_EMPRESTADO), None),
    MOV_BAIXA: ((SITUACAO_DISPONIVEL, SITUACAO_EM_USO, SITUACAO_MANUTENCAO,
                 SITUACAO_EMPRESTADO), SITUACAO_BAIXADO),
}


@dataclass(frozen=True)
class Transicao:
    """Resultado de uma transicao validada."""

    movimento: str
    situacao_anterior: str
    situacao_nova: str
    exige_pessoa: bool = False
    exige_justificativa: bool = False


MOVIMENTOS_COM_PESSOA = (MOV_ATRIBUICAO, MOV_DEVOLUCAO, MOV_EMPRESTIMO,
                         MOV_RETORNO_EMPRESTIMO)


def validar_transicao(movimento: str, situacao_atual: str) -> Transicao:
    """Confere se o movimento pode partir da situacao atual.

    Falhar aqui, com codigo estavel, e' melhor que gravar um estado que ninguem
    consegue explicar depois — um bem "emprestado" que nunca foi atribuido a
    ninguem, por exemplo.
    """
    if movimento not in TRANSICOES:
        raise ErroPatrimonio(TRANSICAO_INVALIDA,
                             f"Movimento desconhecido: {movimento}.")
    if situacao_atual == SITUACAO_BAIXADO:
        raise ErroPatrimonio(
            BEM_BAIXADO,
            "Bem baixado não recebe movimentação. A baixa é definitiva; o "
            "histórico continua consultável.")
    if situacao_atual not in SITUACOES:
        raise ErroPatrimonio(TRANSICAO_INVALIDA,
                             f"Situação desconhecida: {situacao_atual}.")

    partidas, destino = TRANSICOES[movimento]
    if situacao_atual not in partidas:
        rotulos = ", ".join(SITUACOES[s] for s in partidas)
        raise ErroPatrimonio(
            TRANSICAO_INVALIDA,
            f"'{MOVIMENTOS[movimento]}' só é possível a partir de: {rotulos}. "
            f"O bem está em '{SITUACOES[situacao_atual]}'.")

    return Transicao(
        movimento=movimento, situacao_anterior=situacao_atual,
        situacao_nova=destino or situacao_atual,
        exige_pessoa=movimento in MOVIMENTOS_COM_PESSOA,
        exige_justificativa=movimento == MOV_BAIXA)


# ----------------------------------------------------------------------
# Etiqueta

_RE_ETIQUETA = re.compile(r"^(JBF|PER)-(\d{6,})$")


def formatar_etiqueta(numero: int, *, periferico: bool = False) -> str:
    """`1` -> `JBF-000001`. Seis digitos cobrem 999.999 itens."""
    if not isinstance(numero, int) or numero < 1:
        raise ErroPatrimonio(ETIQUETA_INVALIDA,
                             "Número da etiqueta deve ser inteiro positivo.")
    prefixo = PREFIXO_PERIFERICO if periferico else PREFIXO_BEM
    return f"{prefixo}-{numero:06d}"


def ler_etiqueta(etiqueta: str) -> tuple[str, int]:
    """`JBF-000001` -> ('JBF', 1). Aceita espaco e caixa variada do leitor."""
    bruto = str(etiqueta or "").strip().upper().replace(" ", "")
    achado = _RE_ETIQUETA.match(bruto)
    if not achado:
        raise ErroPatrimonio(
            ETIQUETA_INVALIDA,
            f"Etiqueta '{etiqueta}' fora do formato JBF-000000 ou PER-000000.")
    return achado.group(1), int(achado.group(2))


def normalizar_etiqueta(etiqueta: str) -> str:
    prefixo, numero = ler_etiqueta(etiqueta)
    return f"{prefixo}-{numero:06d}"


# ----------------------------------------------------------------------
# CPF

def normalizar_cpf(valor) -> str:
    """CPF com 11 digitos e DV conferido. Vazio devolve string vazia.

    CPF e' opcional no cadastro de pessoa — nem todo colaborador precisa dele
    para receber um monitor —, mas se vier, tem de ser valido.
    """
    bruto = str(valor or "").strip()
    if not bruto:
        return ""
    digitos = re.sub(r"\D", "", bruto)
    if len(digitos) != 11:
        raise ErroPatrimonio(CPF_INVALIDO, "CPF deve ter 11 dígitos.")
    if digitos == digitos[0] * 11:
        raise ErroPatrimonio(CPF_INVALIDO, "CPF com dígitos repetidos.")
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(digitos[tamanho]):
            raise ErroPatrimonio(CPF_INVALIDO,
                                 "Dígito verificador do CPF não confere.")
    return digitos


# ----------------------------------------------------------------------
# Valores e campos

def centavos(valor) -> int | None:
    """Texto/numero -> centavos inteiros. Vazio continua None.

    Dinheiro em float acumula residuo binario; em centavos inteiros, soma e
    comparacao sao exatas.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ErroPatrimonio(VALOR_INVALIDO,
                             f"Valor inválido: {valor!r}.") from exc
    if numero < 0:
        raise ErroPatrimonio(VALOR_INVALIDO,
                             "Valor de aquisição não pode ser negativo.")
    if numero != numero.quantize(Decimal("0.01")):
        raise ErroPatrimonio(
            VALOR_INVALIDO,
            f"{valor!r} tem fração de centavo em campo monetário.")
    return int(numero * 100)


def texto_obrigatorio(valor, campo: str, *, maximo: int = 200) -> str:
    limpo = " ".join(str(valor or "").split())
    if not limpo:
        raise ErroPatrimonio(CAMPO_OBRIGATORIO, f"'{campo}' é obrigatório.")
    return limpo[:maximo]


def validar_hierarquia(pai_e_periferico: bool) -> None:
    """Periferico de periferico e' recusado: a arvore tem dois niveis.

    Tres niveis transformariam a pergunta "o que veio junto com este
    notebook?" numa travessia recursiva, sem ganho pratico nenhum para um
    escritorio.
    """
    if pai_e_periferico:
        raise ErroPatrimonio(
            HIERARQUIA_INVALIDA,
            "Periférico não pode ser vinculado a outro periférico. A "
            "hierarquia tem no máximo dois níveis.")


@dataclass
class DadosBem:
    """Campos validados de um bem, prontos para persistir."""

    descricao: str
    tipo: str
    conservacao: str = "bom"
    marca: str = ""
    modelo: str = ""
    numero_serie: str = ""
    valor_aquisicao: int | None = None
    data_aquisicao: str = ""
    nota_fiscal: str = ""
    observacao: str = ""
    local_id: int | None = None
    pai_id: int | None = None
    extras: dict = field(default_factory=dict)


def validar_bem(dados: dict) -> DadosBem:
    """Valida e normaliza o cadastro de um bem."""
    conservacao = str(dados.get("conservacao") or "bom").strip()
    if conservacao not in CONSERVACOES:
        raise ErroPatrimonio(
            CAMPO_OBRIGATORIO,
            f"Conservação inválida: {conservacao}. Use uma de "
            f"{', '.join(CONSERVACOES)}.")
    data = str(dados.get("data_aquisicao") or "").strip()
    if data and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
        raise ErroPatrimonio(CAMPO_OBRIGATORIO,
                             "Data de aquisição deve estar em AAAA-MM-DD.")
    return DadosBem(
        descricao=texto_obrigatorio(dados.get("descricao"), "Descrição"),
        tipo=texto_obrigatorio(dados.get("tipo"), "Tipo", maximo=60),
        conservacao=conservacao,
        marca=" ".join(str(dados.get("marca") or "").split())[:80],
        modelo=" ".join(str(dados.get("modelo") or "").split())[:80],
        numero_serie=" ".join(str(dados.get("numero_serie") or "").split())[:80],
        valor_aquisicao=centavos(dados.get("valor_aquisicao")),
        data_aquisicao=data,
        nota_fiscal=" ".join(str(dados.get("nota_fiscal") or "").split())[:60],
        observacao=str(dados.get("observacao") or "").strip()[:1000],
        local_id=dados.get("local_id"),
        pai_id=dados.get("pai_id"),
    )
