"""Antecipacao e DIFAL do ICMS nas compras interestaduais — Bahia (spec 027).

Modulo PURO (constituicao, II): nao conhece FastAPI, banco nem arquivo. Recebe
os dados da nota ja lidos, a tabela de aliquotas e os parametros escolhidos por
uma pessoa, e devolve a memoria de calculo de cada item com as pendencias.

Dois metodos convivem porque os dois documentos que originaram a ferramenta
pedem contas diferentes para a mesma nota (spec 027, pendencia P-01):

- ``por_dentro``: especificacao funcional do Departamento Fiscal, versao 1.0.
  BC = (valor da operacao - credito) / (1 - aliquota interna);
  ICMS interno = BC x aliquota interna; a recolher = ICMS interno - credito.
- ``diferenca_simples``: aliquota interna sobre o valor da operacao, menos o
  credito (a conta do prototipo e a redacao do art. 12-A da Lei 7.014/1996
  para a antecipacao parcial).

O metodo nunca e' escolhido pelo programa: vem dos parametros da nota, fica
gravado na memoria e a memoria mostra quanto daria pelo outro metodo.

Nada aqui "libera" imposto: item com excecao ou duvida nasce sem decisao e so
entra na soma depois que uma pessoa decide (secoes 6 e 8 da especificacao).
Ausencia de valor nunca vira zero (constituicao, I).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")
CEM = Decimal("100")
UF_DESTINO = "BA"

# ----------------------------------------------------------------------
# Catalogos

METODO_POR_DENTRO = "por_dentro"
METODO_DIFERENCA = "diferenca_simples"
METODOS = {
    METODO_POR_DENTRO:
        "Base por dentro (especificação do Fiscal, v1.0)",
    METODO_DIFERENCA:
        "Alíquota interna sobre o valor da operação, menos o crédito",
}

FINALIDADE_REVENDA = "revenda"
FINALIDADES = {
    FINALIDADE_REVENDA: "Revenda (comercialização)",
    "uso_consumo": "Uso e consumo",
    "ativo": "Ativo imobilizado",
}

REGIME_SIMPLES = "simples_nacional"
REGIMES = {
    REGIME_SIMPLES: "Simples Nacional",
    "outro": "Outro regime",
}

DECISAO_CALCULAR = "calcular"
DECISAO_EXCLUIR = "excluir"
DECISOES = {
    DECISAO_CALCULAR: "Calcular",
    DECISAO_EXCLUIR: "Fora do cálculo",
}

CREDITO_DESTACADO = "destacado"
CREDITO_CALCULADO = "calculado"
TIPOS_CREDITO = {
    CREDITO_DESTACADO: "Destacado na nota",
    CREDITO_CALCULADO: "Calculado (crédito de referência)",
}

# Parcelas que compoem o valor da operacao. Quais entram e' parametro, porque
# a especificacao deixa a definicao com o Fiscal (secao 2; pendencia P-03).
COMPONENTES = ("desconto", "frete", "seguro", "outras", "ipi")
COMPONENTES_PADRAO = {nome: True for nome in COMPONENTES}
ROTULO_COMPONENTE = {
    "desconto": "Desconto (abate)",
    "frete": "Frete",
    "seguro": "Seguro",
    "outras": "Outras despesas",
    "ipi": "IPI",
}

# Tipos de pendencia:
#   impede  — nao ha como calcular enquanto o dado nao for corrigido;
#   decisao — ha calculo, mas uma pessoa precisa decidir se ele vale;
#   aviso   — informacao que acompanha a memoria, sem travar nada.
IMPEDE = "impede"
DECISAO = "decisao"
AVISO = "aviso"

P_DADO_FALTANTE = "DADO_FALTANTE"
P_FINALIDADE = "FINALIDADE_INDEFINIDA"
P_SEM_DESTAQUE = "SEM_DESTAQUE"
P_SEM_ALIQUOTA_INTERNA = "SEM_ALIQUOTA_INTERNA"
P_SEM_ALIQUOTA_INTERESTADUAL = "SEM_ALIQUOTA_INTERESTADUAL"
P_VALOR_NEGATIVO = "VALOR_NEGATIVO"
P_ICMS_ST = "ICMS_ST"
P_ISENTO = "ISENTO_OU_NAO_TRIBUTADO"
P_REDUCAO_BASE = "REDUCAO_DE_BASE"
P_DIFERIMENTO = "DIFERIMENTO"
P_TRIBUTACAO_ESPECIAL = "TRIBUTACAO_ESPECIAL"
P_FCP = "FCP"
P_CFOP = "CFOP_NAO_INTERESTADUAL"
P_ALIQUOTA_DIVERGENTE = "ALIQUOTA_DIVERGENTE"
P_NFE_NAO_NORMAL = "NFE_NAO_NORMAL"
P_CREDITO_CALCULADO = "CREDITO_CALCULADO"
P_FORNECEDOR_SIMPLES = "FORNECEDOR_SIMPLES"

# Motivos para a nota nem entrar (fora do escopo desta ferramenta).
R_CHAVE = "CHAVE_INVALIDA"
R_MODELO = "MODELO_NAO_55"
R_DESTINO = "DESTINO_NAO_BA"
R_ORIGEM_BA = "ORIGEM_BA"
R_ORIGEM_EXTERIOR = "ORIGEM_EXTERIOR"
R_SITUACAO = "NOTA_NAO_AUTORIZADA"
R_ENTRADA = "NOTA_DE_ENTRADA"
R_SEM_ITENS = "SEM_ITENS"
R_SEM_CNPJ = "DESTINATARIO_SEM_CNPJ"
R_SEM_DATA = "SEM_DATA_DE_EMISSAO"

# CST (2 digitos) e CSOSN (3 digitos) que tiram o item da conta automatica.
_CST_ST = {"10", "30", "60", "70", "201", "202", "203", "500"}
_CST_ISENTO = {"40", "41", "50", "103", "300", "400"}
_CST_REDUCAO = {"20"}
_CST_DIFERIMENTO = {"51"}
_CST_ESPECIAL = {"02", "15", "53", "61", "90", "900"}
_CSOSN_SIMPLES = {"101", "102", "103", "201", "202", "203", "300", "400",
                  "500", "900"}

# Origem da mercadoria (campo `orig` da NF-e) sujeita a aliquota interestadual
# de 4% (Resolucao do Senado 13/2012): importada (1, 2) e nacional com
# conteudo de importacao acima de 40% (3, 8). As origens 6 e 7 (importada sem
# similar nacional) ficam fora da regra dos 4%.
ORIGENS_4 = frozenset({"1", "2", "3", "8"})
ORIGENS_VALIDAS = frozenset("012345678")

UFS_7 = ("SP", "RJ", "MG", "PR", "SC", "RS")
UFS_12 = ("AC", "AL", "AM", "AP", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
          "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO")
UF_IMPORTADO = "IMPORTADO"

CODIGO_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

TIPO_INTERNA = "interna"
TIPO_INTERESTADUAL = "interestadual"


class ErroAntecipacao(ValueError):
    """Regra de negocio violada; `codigo` e' estavel, `mensagem` e' da tela."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


# ----------------------------------------------------------------------
# Numeros

def so_digitos(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def para_decimal(valor) -> Decimal | None:
    """Texto digitado ("1.234,56", "1234.56", "20,5") -> Decimal.

    Vazio ou invalido devolve None: quem chama decide se o campo e'
    obrigatorio. Nunca devolve zero no lugar do que nao foi informado."""
    if isinstance(valor, Decimal):
        return valor if valor.is_finite() else None
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        return Decimal(valor)
    texto = str(valor).strip().replace("R$", "").replace("%", "").strip()
    if not texto:
        return None
    texto = texto.replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def arredondar(valor: Decimal) -> Decimal:
    """Resultado monetario com duas casas, meio para cima."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def centavos(valor: Decimal | None) -> int | None:
    if valor is None:
        return None
    return int((arredondar(valor) * 100).to_integral_value())


def de_centavos(valor: int | None) -> Decimal | None:
    if valor is None:
        return None
    return Decimal(int(valor)) / 100


def _txt(valor: Decimal | None) -> str | None:
    """Decimal -> texto estavel para a memoria (JSON), sem notacao cientifica."""
    if valor is None:
        return None
    return format(valor, "f")


def texto_percentual(valor: Decimal | None) -> str | None:
    if valor is None:
        return None
    return format(valor.normalize() if valor != valor.to_integral()
                  else valor.quantize(Decimal("1")), "f")


# ----------------------------------------------------------------------
# Chave de acesso

@dataclass(frozen=True)
class ChaveAcesso:
    chave: str
    uf: str
    ano_mes: str        # AAAA-MM
    cnpj_emitente: str
    modelo: str
    serie: str
    numero: str


def dv_chave(base43: str) -> str:
    """Digito verificador da chave (modulo 11, pesos 2 a 9)."""
    soma = 0
    peso = 2
    for digito in reversed(base43):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def decompor_chave(texto) -> ChaveAcesso:
    """Valida os 44 digitos e o DV e separa os campos da chave.

    A chave identifica a nota, mas NAO traz os produtos: sem o XML nao ha o
    que calcular (spec 027, fora do escopo: consulta a SEFAZ)."""
    chave = so_digitos(texto)
    if len(chave) != 44:
        raise ErroAntecipacao(
            R_CHAVE, f"A chave precisa ter 44 dígitos (vieram {len(chave)}).")
    if dv_chave(chave[:43]) != chave[43]:
        raise ErroAntecipacao(R_CHAVE, "O dígito verificador da chave não confere.")
    uf = CODIGO_UF.get(chave[:2])
    mes = chave[4:6]
    if uf is None or not "01" <= mes <= "12":
        raise ErroAntecipacao(R_CHAVE, "UF ou mês da chave inválido.")
    return ChaveAcesso(
        chave=chave, uf=uf, ano_mes=f"20{chave[2:4]}-{mes}",
        cnpj_emitente=chave[6:20], modelo=chave[20:22],
        serie=str(int(chave[22:25])), numero=str(int(chave[25:34])))


def extrair_chaves(texto: str) -> list[str]:
    """Sequencias de digitos de um texto colado (linha, espaco ou virgula).

    Aceita a chave com espacos de 4 em 4, como vem impressa no DANFE: os
    blocos sao reunidos quando somam 44 digitos."""
    achadas: list[str] = []
    for linha in str(texto or "").replace(";", "\n").replace(",", "\n").splitlines():
        blocos = ["".join(c for c in parte if c.isdigit())
                  for parte in linha.split()]
        blocos = [b for b in blocos if b]
        if not blocos:
            continue
        if sum(len(b) for b in blocos) == 44:
            achadas.append("".join(blocos))
        else:
            achadas.extend(blocos)
    return achadas


# ----------------------------------------------------------------------
# Aliquotas por vigencia

def aliquotas_iniciais() -> list[dict]:
    """Carga inicial da tabela (secao 4 da especificacao e parametro vigente).

    E' ponto de partida editavel: a especificacao pede validacao com a
    legislacao vigente antes do uso em producao (secao 9; pendencia P-06)."""
    linhas = [{
        "tipo": TIPO_INTERNA, "uf": UF_DESTINO, "ncm": "",
        "percentual": "20.5", "vigencia_inicio": "2024-02-07",
        "base_legal": "Lei 7.014/1996, art. 15, I (red. Lei 14.629/2023)",
    }]
    for uf in UFS_7:
        linhas.append({
            "tipo": TIPO_INTERESTADUAL, "uf": uf, "ncm": "",
            "percentual": "7", "vigencia_inicio": "1989-06-01",
            "base_legal": "Resolução do Senado 22/1989"})
    for uf in UFS_12:
        linhas.append({
            "tipo": TIPO_INTERESTADUAL, "uf": uf, "ncm": "",
            "percentual": "12", "vigencia_inicio": "1989-06-01",
            "base_legal": "Resolução do Senado 22/1989"})
    linhas.append({
        "tipo": TIPO_INTERESTADUAL, "uf": UF_IMPORTADO, "ncm": "",
        "percentual": "4", "vigencia_inicio": "2013-01-01",
        "base_legal": "Resolução do Senado 13/2012"})
    return linhas


def validar_aliquota(dados: dict) -> dict:
    """Confere uma linha nova da tabela. Devolve a linha normalizada."""
    tipo = str(dados.get("tipo") or "").strip()
    if tipo not in (TIPO_INTERNA, TIPO_INTERESTADUAL):
        raise ErroAntecipacao("TIPO_INVALIDO", "Tipo de alíquota desconhecido.")
    uf = str(dados.get("uf") or "").strip().upper()
    ncm = so_digitos(dados.get("ncm"))
    if tipo == TIPO_INTERNA:
        uf = UF_DESTINO
        if len(ncm) not in (0, 2, 4, 5, 6, 7, 8):
            raise ErroAntecipacao(
                "NCM_INVALIDO",
                "NCM da alíquota interna: deixe vazio (geral) ou informe um "
                "prefixo de 2 a 8 dígitos.")
    else:
        ncm = ""
        if uf not in UFS_7 + UFS_12 + (UF_IMPORTADO,):
            raise ErroAntecipacao(
                "UF_INVALIDA",
                "UF de origem inválida (BA fica fora do escopo interestadual).")
    percentual = para_decimal(dados.get("percentual"))
    if percentual is None or not Decimal("0") <= percentual < CEM:
        raise ErroAntecipacao(
            "PERCENTUAL_INVALIDO", "Informe a alíquota entre 0 e 100 (ex.: 20,5).")
    inicio = _data_iso(dados.get("vigencia_inicio"))
    if not inicio:
        raise ErroAntecipacao(
            "VIGENCIA_INVALIDA", "Informe o início da vigência (dd/mm/aaaa).")
    fim_bruto = str(dados.get("vigencia_fim") or "").strip()
    fim = _data_iso(fim_bruto) if fim_bruto else ""
    if fim_bruto and not fim:
        raise ErroAntecipacao("VIGENCIA_INVALIDA", "Fim da vigência inválido.")
    if fim and fim < inicio:
        raise ErroAntecipacao(
            "VIGENCIA_INVALIDA", "O fim da vigência não pode ser antes do início.")
    base_legal = str(dados.get("base_legal") or "").strip()[:300]
    if not base_legal:
        raise ErroAntecipacao(
            "BASE_LEGAL_OBRIGATORIA",
            "Informe a base legal: cada alíquota guarda de onde veio.")
    return {"tipo": tipo, "uf": uf, "ncm": ncm,
            "percentual": texto_percentual(percentual),
            "vigencia_inicio": inicio, "vigencia_fim": fim,
            "base_legal": base_legal}


def _data_iso(valor) -> str:
    """dd/mm/aaaa ou aaaa-mm-dd -> aaaa-mm-dd ("" se invalida)."""
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor or "").strip()[:10]
    try:
        if "/" in texto:
            dia, mes, ano = texto.split("/")
            return date(int(ano), int(mes), int(dia)).isoformat()
        return date.fromisoformat(texto).isoformat()
    except (ValueError, TypeError):
        return ""


def data_iso(valor) -> str:
    return _data_iso(valor)


class TabelaAliquotas:
    """Consulta das aliquotas vigentes numa data. Recebe as linhas do banco."""

    def __init__(self, linhas: list[dict]):
        self._linhas = [dict(linha) for linha in linhas]

    def _vigentes(self, tipo: str, quando: str) -> list[dict]:
        return [l for l in self._linhas
                if l["tipo"] == tipo and l["vigencia_inicio"] <= quando
                and (not l.get("vigencia_fim") or quando <= l["vigencia_fim"])]

    def interna(self, ncm: str, quando: date) -> dict | None:
        """Aliquota interna do produto: o prefixo de NCM mais longo vence a
        regra geral; entre iguais, a vigencia mais recente."""
        ncm = so_digitos(ncm)
        candidatas = [l for l in self._vigentes(TIPO_INTERNA, quando.isoformat())
                      if ncm.startswith(l.get("ncm") or "")]
        if not candidatas:
            return None
        return max(candidatas, key=lambda l: (len(l.get("ncm") or ""),
                                              l["vigencia_inicio"]))

    def interestadual(self, uf_origem: str, origem_mercadoria: str,
                      quando: date) -> dict | None:
        """Aliquota interestadual de referencia: 4% para a mercadoria
        importada (independe da UF), senao a da UF de origem."""
        uf = UF_IMPORTADO if origem_mercadoria in ORIGENS_4 else uf_origem
        candidatas = [l for l in self._vigentes(TIPO_INTERESTADUAL,
                                                quando.isoformat())
                      if l["uf"] == uf]
        if not candidatas:
            return None
        return max(candidatas, key=lambda l: l["vigencia_inicio"])


# ----------------------------------------------------------------------
# Formulas

@dataclass(frozen=True)
class Calculo:
    metodo: str
    valor_operacao: Decimal
    credito: Decimal
    aliquota_interna: Decimal      # percentual (20.5)
    divisor: Decimal | None        # so no metodo por dentro
    valor_sem_icms: Decimal | None
    base_calculo: Decimal
    icms_interno: Decimal
    a_recolher: Decimal


def calcular(valor_operacao: Decimal, credito: Decimal,
             aliquota_interna: Decimal, metodo: str) -> Calculo:
    """Aplica a formula. Precisao intermediaria preservada; so o resultado
    monetario e' arredondado a duas casas (secao 8 da especificacao).

    O MESMO credito entra na base e no abatimento (secao 3: "o mesmo credito
    deve ser utilizado nas etapas 3 e 5")."""
    if metodo not in METODOS:
        raise ErroAntecipacao("METODO_INVALIDO", "Método de cálculo desconhecido.")
    fracao = aliquota_interna / CEM
    if metodo == METODO_POR_DENTRO:
        divisor = Decimal(1) - fracao
        if divisor <= 0:
            raise ErroAntecipacao(
                "ALIQUOTA_INVALIDA", "Alíquota interna inválida para o divisor.")
        sem_icms = valor_operacao - credito
        base = sem_icms / divisor
        interno = base * fracao
        return Calculo(metodo, arredondar(valor_operacao), arredondar(credito),
                       aliquota_interna, divisor, arredondar(sem_icms),
                       arredondar(base), arredondar(interno),
                       arredondar(interno - credito))
    interno = valor_operacao * fracao
    return Calculo(metodo, arredondar(valor_operacao), arredondar(credito),
                   aliquota_interna, None, None, arredondar(valor_operacao),
                   arredondar(interno), arredondar(interno - credito))


def outro_metodo(metodo: str) -> str:
    return METODO_DIFERENCA if metodo == METODO_POR_DENTRO else METODO_POR_DENTRO


# ----------------------------------------------------------------------
# Nota e itens (o que o leitor de XML entrega)

@dataclass
class ItemEntrada:
    num_item: str = ""
    descricao: str = ""
    ncm: str = ""
    cest: str = ""
    cfop: str = ""
    cst: str = ""                  # CST (2 digitos) ou CSOSN (3 digitos)
    origem_mercadoria: str = ""
    v_prod: Decimal | None = None
    v_desc: Decimal = Decimal("0")
    v_frete: Decimal = Decimal("0")
    v_seg: Decimal = Decimal("0")
    v_outro: Decimal = Decimal("0")
    v_ipi: Decimal = Decimal("0")
    aliq_icms: Decimal | None = None   # pICMS destacado
    v_icms: Decimal | None = None      # vICMS destacado
    v_bc_st: Decimal = Decimal("0")
    v_st: Decimal = Decimal("0")
    v_fcp: Decimal = Decimal("0")
    v_cred_sn: Decimal = Decimal("0")


@dataclass
class NotaEntrada:
    chave: str = ""
    modelo: str = ""
    numero: str = ""
    serie: str = ""
    dt_emissao: date | None = None
    tp_nf: str = ""
    fin_nfe: str = ""
    situacao: str = ""             # cStat do protocolo, quando houver
    uf_origem: str = ""
    uf_destino: str = ""
    cnpj_emit: str = ""
    nome_emit: str = ""
    crt_emit: str = ""
    cnpj_dest: str = ""
    nome_dest: str = ""
    valor_total: Decimal | None = None
    itens: list[ItemEntrada] = field(default_factory=list)


_CSTAT_CANCELADA = {"101", "135", "151", "155"}
_CSTAT_DENEGADA = {"110", "301", "302", "303"}


def recusa_da_nota(nota: NotaEntrada) -> tuple[str, str] | None:
    """Motivo para a nota ficar de fora, ou None se ela entra para revisao."""
    try:
        decompor_chave(nota.chave)
    except ErroAntecipacao as exc:
        return R_CHAVE, exc.mensagem
    if nota.modelo != "55":
        return R_MODELO, "Só NF-e modelo 55 entra neste cálculo."
    if nota.situacao in _CSTAT_CANCELADA:
        return R_SITUACAO, "A nota está cancelada."
    if nota.situacao in _CSTAT_DENEGADA:
        return R_SITUACAO, "A nota foi denegada."
    if nota.tp_nf == "0":
        return R_ENTRADA, "É nota de entrada do emitente, não uma venda."
    if not nota.itens:
        return R_SEM_ITENS, "A nota não tem itens."
    if nota.dt_emissao is None:
        return R_SEM_DATA, "A nota não traz a data de emissão."
    if nota.uf_destino != UF_DESTINO:
        return R_DESTINO, (f"O destinatário está em {nota.uf_destino or '?'}; "
                           "esta ferramenta calcula compras com destino BA.")
    if nota.uf_origem == UF_DESTINO:
        return R_ORIGEM_BA, "Origem BA: fora do escopo interestadual."
    if nota.uf_origem == "EX" or nota.uf_origem not in CODIGO_UF.values():
        return R_ORIGEM_EXTERIOR, (f"UF de origem '{nota.uf_origem or '?'}' "
                                   "fora do escopo (importação direta ou UF inválida).")
    if len(nota.cnpj_dest) != 14:
        return R_SEM_CNPJ, "O destinatário não tem CNPJ."
    return None


# ----------------------------------------------------------------------
# Avaliacao do item

@dataclass(frozen=True)
class Parametros:
    metodo: str
    presuncao: bool = False
    componentes: dict = field(default_factory=lambda: dict(COMPONENTES_PADRAO))


def validar_parametros(metodo, presuncao=False, componentes=None) -> Parametros:
    if metodo not in METODOS:
        raise ErroAntecipacao(
            "METODO_INVALIDO",
            "Escolha o método de cálculo: o sistema não decide por você.")
    limpo = dict(COMPONENTES_PADRAO)
    for nome, valor in (componentes or {}).items():
        if nome not in COMPONENTES:
            raise ErroAntecipacao(
                "COMPONENTE_INVALIDO", f"Componente da base desconhecido: {nome}.")
        limpo[nome] = bool(valor)
    return Parametros(metodo=metodo, presuncao=bool(presuncao), componentes=limpo)


def _pendencia(codigo: str, tipo: str, mensagem: str) -> dict:
    return {"codigo": codigo, "tipo": tipo, "mensagem": mensagem}


def valor_da_operacao(item: ItemEntrada, componentes: dict) -> tuple[Decimal | None, dict]:
    """Valor da operacao do item e as parcelas que entraram nele."""
    if item.v_prod is None:
        return None, {}
    parcelas = {"produto": item.v_prod}
    total = item.v_prod
    for nome, valor, sinal in (("desconto", item.v_desc, -1),
                               ("frete", item.v_frete, 1),
                               ("seguro", item.v_seg, 1),
                               ("outras", item.v_outro, 1),
                               ("ipi", item.v_ipi, 1)):
        if componentes.get(nome) and valor:
            parcelas[nome] = valor
            total += sinal * valor
    return total, parcelas


def avaliar_item(item: ItemEntrada, nota: NotaEntrada, parametros: Parametros,
                 tabela: TabelaAliquotas, finalidade: str = "") -> dict:
    """Memoria de calculo e pendencias de um item.

    Devolve {"pendencias": [...], "memoria": {...}, "a_recolher": Decimal|None,
    "aliquota_credito": str|None}. `a_recolher` e' None quando nao ha como
    calcular — nunca zero no lugar do desconhecido."""
    pendencias: list[dict] = []
    quando = nota.dt_emissao

    faltando = []
    if len(so_digitos(item.ncm)) != 8:
        faltando.append("NCM")
    if len(so_digitos(item.cfop)) != 4:
        faltando.append("CFOP")
    if not item.cst:
        faltando.append("CST/CSOSN")
    if item.origem_mercadoria not in ORIGENS_VALIDAS:
        faltando.append("origem da mercadoria")
    if item.v_prod is None:
        faltando.append("valor do produto")
    if faltando:
        pendencias.append(_pendencia(
            P_DADO_FALTANTE, IMPEDE,
            "Dado faltante ou inválido na nota: " + ", ".join(faltando) + "."))

    if finalidade not in FINALIDADES:
        pendencias.append(_pendencia(
            P_FINALIDADE, IMPEDE,
            "Informe a finalidade da compra (revenda, uso e consumo ou ativo)."))

    # ------------------------------------------------------------------
    # Enquadramento: o que tira o item da conta automatica.
    cst = item.cst
    if cst in _CST_ST or item.v_st > 0 or item.v_bc_st > 0:
        pendencias.append(_pendencia(
            P_ICMS_ST, DECISAO,
            "Indício de ICMS-ST ou antecipação total (CST/CSOSN "
            f"{cst or '?'} ou ST destacada): esta fórmula não se aplica "
            "sem conferência."))
    if cst in _CST_ISENTO:
        pendencias.append(_pendencia(
            P_ISENTO, DECISAO,
            f"CST/CSOSN {cst}: operação isenta, não tributada ou com "
            "suspensão. Ausência de destaque não é o mesmo que crédito "
            "de referência."))
    if cst in _CST_REDUCAO:
        pendencias.append(_pendencia(
            P_REDUCAO_BASE, DECISAO,
            f"CST {cst}: redução de base de cálculo na origem."))
    if cst in _CST_DIFERIMENTO:
        pendencias.append(_pendencia(
            P_DIFERIMENTO, DECISAO, f"CST {cst}: diferimento."))
    if cst in _CST_ESPECIAL:
        pendencias.append(_pendencia(
            P_TRIBUTACAO_ESPECIAL, DECISAO,
            f"CST/CSOSN {cst}: tributação monofásica ou 'outras'."))
    if item.v_fcp > 0:
        pendencias.append(_pendencia(
            P_FCP, DECISAO,
            "A nota traz Fundo de Combate à Pobreza (FCP), que esta "
            "fórmula não trata."))
    cfop = so_digitos(item.cfop)
    if len(cfop) == 4 and not cfop.startswith("6"):
        pendencias.append(_pendencia(
            P_CFOP, DECISAO,
            f"CFOP {cfop} não é de saída interestadual (6xxx), embora as "
            "UFs sejam diferentes."))
    if nota.fin_nfe and nota.fin_nfe != "1":
        pendencias.append(_pendencia(
            P_NFE_NAO_NORMAL, DECISAO,
            "NF-e complementar, de ajuste ou de devolução (finalidade "
            f"{nota.fin_nfe})."))
    if nota.crt_emit in ("1", "4") or cst in _CSOSN_SIMPLES:
        pendencias.append(_pendencia(
            P_FORNECEDOR_SIMPLES, AVISO,
            "Fornecedor do Simples Nacional ou MEI: a nota não destaca "
            "ICMS próprio."
            + (f" Crédito informado (vCredICMSSN): R$ {arredondar(item.v_cred_sn)}."
               if item.v_cred_sn > 0 else "")))

    # ------------------------------------------------------------------
    # Aliquotas e credito
    valor, parcelas = valor_da_operacao(item, parametros.componentes)
    interna = tabela.interna(item.ncm, quando) if quando else None
    referencia = (tabela.interestadual(nota.uf_origem, item.origem_mercadoria,
                                       quando) if quando else None)
    aliq_interna = Decimal(interna["percentual"]) if interna else None
    aliq_referencia = Decimal(referencia["percentual"]) if referencia else None

    if interna is None:
        pendencias.append(_pendencia(
            P_SEM_ALIQUOTA_INTERNA, IMPEDE,
            "Não há alíquota interna cadastrada para este produto na data "
            "da nota."))

    credito: Decimal | None = None
    tipo_credito: str | None = None
    aliq_credito: Decimal | None = None
    if item.v_icms is not None and item.v_icms > 0:
        credito, tipo_credito = item.v_icms, CREDITO_DESTACADO
        aliq_credito = item.aliq_icms if item.aliq_icms else None
        if (aliq_credito is not None and aliq_referencia is not None
                and aliq_credito != aliq_referencia):
            pendencias.append(_pendencia(
                P_ALIQUOTA_DIVERGENTE, DECISAO,
                f"A nota destaca ICMS a {texto_percentual(aliq_credito)}%, "
                f"mas a alíquota interestadual de referência é "
                f"{texto_percentual(aliq_referencia)}%."))
    elif not parametros.presuncao:
        pendencias.append(_pendencia(
            P_SEM_DESTAQUE, IMPEDE,
            "A nota não destaca ICMS próprio e o crédito de referência "
            "(presunção) não foi autorizado para esta nota."))
    elif aliq_referencia is None:
        pendencias.append(_pendencia(
            P_SEM_ALIQUOTA_INTERESTADUAL, IMPEDE,
            f"Não há alíquota interestadual cadastrada para a origem "
            f"{nota.uf_origem or '?'} na data da nota."))
    elif valor is not None:
        credito = valor * aliq_referencia / CEM
        tipo_credito, aliq_credito = CREDITO_CALCULADO, aliq_referencia
        pendencias.append(_pendencia(
            P_CREDITO_CALCULADO, AVISO,
            f"Crédito de referência calculado a "
            f"{texto_percentual(aliq_referencia)}% por autorização de quem "
            "revisou; não é crédito escritural do Simples Nacional."))

    memoria: dict = {
        "metodo": parametros.metodo,
        "componentes": {nome: _txt(v) for nome, v in parcelas.items()},
        "valor_operacao": _txt(arredondar(valor)) if valor is not None else None,
        "tipo_credito": tipo_credito,
        "credito": _txt(arredondar(credito)) if credito is not None else None,
        "aliquota_nota": texto_percentual(item.aliq_icms) if item.aliq_icms else None,
        "aliquota_interestadual": texto_percentual(aliq_referencia),
        "aliquota_interestadual_base_legal": (referencia or {}).get("base_legal"),
        "aliquota_interna": texto_percentual(aliq_interna),
        "aliquota_interna_base_legal": (interna or {}).get("base_legal"),
        "aliquota_interna_ncm": (interna or {}).get("ncm") or "",
        "divisor": None, "valor_sem_icms": None, "base_calculo": None,
        "icms_interno": None, "a_recolher": None, "comparativo": None,
    }

    a_recolher: Decimal | None = None
    if valor is not None and credito is not None and aliq_interna is not None:
        if valor <= 0:
            pendencias.append(_pendencia(
                P_VALOR_NEGATIVO, IMPEDE,
                "O valor da operação do item é zero ou negativo."))
        else:
            conta = calcular(valor, credito, aliq_interna, parametros.metodo)
            outra = calcular(valor, credito, aliq_interna,
                             outro_metodo(parametros.metodo))
            a_recolher = conta.a_recolher
            memoria.update({
                "divisor": _txt(conta.divisor),
                "valor_sem_icms": _txt(conta.valor_sem_icms),
                "base_calculo": _txt(conta.base_calculo),
                "icms_interno": _txt(conta.icms_interno),
                "a_recolher": _txt(conta.a_recolher),
                "comparativo": {"metodo": outra.metodo,
                                "a_recolher": _txt(outra.a_recolher)},
            })
            if conta.a_recolher < 0:
                pendencias.append(_pendencia(
                    P_VALOR_NEGATIVO, IMPEDE,
                    "O resultado é negativo (crédito maior que o ICMS "
                    "interno): não entra na soma."))

    return {"pendencias": pendencias, "memoria": memoria,
            "a_recolher": a_recolher,
            "aliquota_credito": texto_percentual(aliq_credito)}


def impede_calculo(pendencias: list[dict]) -> bool:
    return any(p["tipo"] == IMPEDE for p in pendencias)


def pede_decisao(pendencias: list[dict]) -> bool:
    return any(p["tipo"] == DECISAO for p in pendencias)


def decisao_automatica(pendencias: list[dict], a_recolher) -> str:
    """So o item sem nenhuma pendencia de bloqueio e' proposto para a soma.
    O resto nasce SEM decisao ("nao liberar automaticamente")."""
    if a_recolher is None or impede_calculo(pendencias) or pede_decisao(pendencias):
        return ""
    return DECISAO_CALCULAR


# ----------------------------------------------------------------------
# Lancamento manual para conferencia (nao grava nada)

def simular(*, valor_operacao, uf_origem, quando: date, tabela: TabelaAliquotas,
            icms_destacado=None, origem_mercadoria: str = "0",
            ncm: str = "") -> dict:
    """Conta de conferencia a partir de numeros digitados (secao 2 da
    especificacao: "permitir lancamento manual para conferencia").

    Sem destaque informado, usa o credito de referencia da tabela — aqui a
    presuncao e' explicita, porque quem digita esta conferindo, nao apurando.
    Devolve os dois metodos lado a lado."""
    valor = para_decimal(valor_operacao)
    if valor is None or valor <= 0:
        raise ErroAntecipacao("VALOR_INVALIDO",
                              "Informe o valor da operação (maior que zero).")
    uf = str(uf_origem or "").strip().upper()
    if uf == UF_DESTINO:
        raise ErroAntecipacao(R_ORIGEM_BA, "Origem BA: fora do escopo interestadual.")
    if uf not in UFS_7 + UFS_12:
        raise ErroAntecipacao("UF_INVALIDA", "UF de origem inválida.")
    origem = str(origem_mercadoria or "0").strip()
    if origem not in ORIGENS_VALIDAS:
        raise ErroAntecipacao("ORIGEM_INVALIDA",
                              "Origem da mercadoria inválida (0 a 8).")
    interna = tabela.interna(ncm, quando)
    if interna is None:
        raise ErroAntecipacao(
            P_SEM_ALIQUOTA_INTERNA,
            "Não há alíquota interna cadastrada para essa data e produto.")
    referencia = tabela.interestadual(uf, origem, quando)
    aliq_referencia = Decimal(referencia["percentual"]) if referencia else None

    texto_destaque = str(icms_destacado if icms_destacado is not None else "").strip()
    if texto_destaque:
        credito = para_decimal(texto_destaque)
        if credito is None or credito < 0:
            raise ErroAntecipacao("VALOR_INVALIDO", "ICMS destacado inválido.")
        tipo = CREDITO_DESTACADO
    else:
        if aliq_referencia is None:
            raise ErroAntecipacao(
                P_SEM_ALIQUOTA_INTERESTADUAL,
                "Não há alíquota interestadual cadastrada para essa origem.")
        credito = valor * aliq_referencia / CEM
        tipo = CREDITO_CALCULADO

    aliq_interna = Decimal(interna["percentual"])
    metodos = {}
    for metodo in METODOS:
        conta = calcular(valor, credito, aliq_interna, metodo)
        metodos[metodo] = {
            "divisor": _txt(conta.divisor),
            "valor_sem_icms": _txt(conta.valor_sem_icms),
            "base_calculo": _txt(conta.base_calculo),
            "icms_interno": _txt(conta.icms_interno),
            "a_recolher": _txt(conta.a_recolher),
        }
    return {
        "valor_operacao": _txt(arredondar(valor)),
        "tipo_credito": tipo,
        "credito": _txt(arredondar(credito)),
        "aliquota_interestadual": texto_percentual(aliq_referencia),
        "aliquota_interestadual_base_legal": (referencia or {}).get("base_legal"),
        "aliquota_interna": texto_percentual(aliq_interna),
        "aliquota_interna_base_legal": interna.get("base_legal"),
        "metodos": metodos,
    }


# ----------------------------------------------------------------------
# Periodo, vencimento e reducao

def competencia_de(data: date) -> str:
    return f"{data.year:04d}-{data.month:02d}"


def validar_competencia(texto) -> str:
    """"AAAA-MM" ou "MM/AAAA" -> "AAAA-MM"."""
    bruto = str(texto or "").strip()
    try:
        if "/" in bruto:
            mes, ano = bruto.split("/")
        else:
            ano, mes = bruto.split("-")[:2]
        ano_n, mes_n = int(ano), int(mes)
        date(ano_n, mes_n, 1)
    except (ValueError, TypeError):
        raise ErroAntecipacao(
            "COMPETENCIA_INVALIDA",
            "Competência inválida: use mm/aaaa.") from None
    if not 2000 <= ano_n <= 2100:
        raise ErroAntecipacao("COMPETENCIA_INVALIDA", "Ano da competência inválido.")
    return f"{ano_n:04d}-{mes_n:02d}"


def vencimento_de_referencia(competencia: str, dia: int = 25) -> date:
    """Dia `dia` do mes seguinte ao da competencia. E' referencia: o prazo
    real depende das condicoes do art. 332 do RICMS/BA (pendencia P-04)."""
    ano, mes = (int(p) for p in competencia.split("-"))
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return date(ano, mes, max(1, min(int(dia), 28)))


def reducao_simulada(base: Decimal, percentual: Decimal) -> Decimal:
    """Reducao sobre o valor apurado (ex.: 20% do art. 274 do RICMS/BA).
    Sempre SIMULACAO: a elegibilidade e o pagamento no prazo nao sao
    verificados pelo sistema."""
    return arredondar(base * percentual / CEM)
