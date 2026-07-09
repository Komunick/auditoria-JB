"""Ferramenta 5 - Motor de auditoria tributaria do cadastro de produtos (BA).

Cruza cada produto do cadastro do cliente com as bases legais da pasta
dados/ (Anexo I do RICMS/BA, TIPI, monofasico, isencoes, reducoes de base e
diferimento) e aponta inconsistencias com sugestao de correcao:

  * validacoes estruturais (NCM, CEST, CST/CSOSN);
  * classificacao da tributacao atual (CST prioridade; CFOP desempata);
  * tributacao sugerida pelas bases legais (monofasico > ST > isencao >
    reducao > diferimento > tributado integralmente), com grau de confianca;
  * comparacao atual x sugerida, gerando as inconsistencias classicas
    "ST vendido como tributado" e "Tributado vendido como ST" com as
    correcoes de CST, CFOP, CEST e aliquota prontas para aplicar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..core.base_legal import (
    BaseLegal, ItemAnexo1, MatchAnexo1, RegraTributaria,
    normalizar_descricao, similaridade,
)
from ..core.cadastro_produtos import ProdutoCadastro
from ..core.modelos import so_digitos


# ----------------------------------------------------------------------
# Constantes de CFOP / CST / CSOSN.
# ----------------------------------------------------------------------
CFOPS_ST = {"5401", "5402", "5403", "5405", "6401", "6402", "6403", "6404",
            "6405"}
CFOPS_TRIBUTADO = {"5101", "5102", "5103", "5104", "5115", "6101", "6102",
                   "6103", "6104", "6107", "6108"}
DE_PARA_CFOP_ST = {"5101": "5401", "5102": "5405", "5103": "5405",
                   "5104": "5405", "5115": "5405", "6101": "6401",
                   "6102": "6404", "6103": "6404", "6104": "6404",
                   "6107": "6404", "6108": "6404"}
DE_PARA_CFOP_NORMAL = {"5401": "5101", "5402": "5101", "5403": "5102",
                       "5405": "5102", "6401": "6101", "6402": "6101",
                       "6403": "6102", "6404": "6102", "6405": "6102"}

CSTS_VALIDOS = {"00", "10", "20", "30", "40", "41", "50", "51", "60", "70",
                "90"}
CSOSNS_VALIDOS = {"101", "102", "103", "201", "202", "203", "300", "400",
                  "500", "900"}
CSTS_ST = {"10", "30", "60", "70"}
CSOSNS_ST = {"201", "202", "203", "500"}
CSTS_ISENTO = {"40", "41", "50"}
CSOSNS_ISENTO = {"103", "300", "400"}
CSTS_REDUCAO = {"20", "70"}
CSTS_DIFERIMENTO = {"51"}

CONF_ALTA, CONF_MEDIA, CONF_BAIXA = "alta", "media", "baixa"

TRIB_INTEGRAL = "Tributado Integralmente"
TRIB_ST = "Substituicao Tributaria"
TRIB_ISENTO = "Isento/Nao Tributado"
TRIB_REDUCAO = "Reducao de Base de Calculo"
TRIB_MONOFASICO = "Monofasico"
TRIB_DIFERIMENTO = "Diferimento"
TRIB_OUTROS = "Outros"
TRIB_INDETERMINADA = "Indeterminada"

TIPO_ST_COMO_TRIBUTADO = "ST vendido como tributado"
TIPO_TRIBUTADO_COMO_ST = "Tributado vendido como ST"
TIPO_NCM_AUSENTE = "NCM ausente"
TIPO_NCM_INVALIDO = "NCM invalido"
TIPO_NCM_NAO_TIPI = "NCM nao encontrado na TIPI"
TIPO_CEST_AUSENTE = "CEST ausente para produto ST"
TIPO_CEST_INVALIDO = "CEST invalido"
TIPO_CEST_INCOMPATIVEL = "CEST incompativel com o NCM"
TIPO_CST_INVALIDO = "CST/CSOSN invalido"
TIPO_CST_ALIQUOTA = "CST x aliquota inconsistentes"
TIPO_DIVERGENCIA_DESCRICAO = "Possivel erro de cadastro (NCM x descricao)"
TIPO_TRIBUTACAO_DIVERGENTE = "Tributacao divergente da sugerida"

MSG_ST_COMO_TRIBUTADO = ("Produto sujeito ao regime de Substituicao Tributaria, porem "
                         "esta sendo comercializado como tributado normalmente.")
MSG_TRIBUTADO_COMO_ST = ("Produto comercializado como ST, porem nao localizado na relacao "
                         "de produtos sujeitos a Substituicao Tributaria.")


# ----------------------------------------------------------------------
# Modelos do resultado.
# ----------------------------------------------------------------------
@dataclass
class Inconsistencia:
    """Uma inconsistencia apontada em um produto."""

    tipo: str
    mensagem: str
    nivel: str = "erro"          # "erro" | "alerta"
    fundamentacao: str = ""


@dataclass
class ResultadoAuditoria:
    """Resultado da auditoria de um produto do cadastro."""

    produto: ProdutoCadastro
    situacao: str = "OK"                      # "OK" | "ALERTA" | "INCONSISTENTE"
    tributacao_atual: str = TRIB_INDETERMINADA
    tributacao_sugerida: str = TRIB_INDETERMINADA
    confianca: str = ""                       # "" | alta | media | baixa
    inconsistencias: list[Inconsistencia] = field(default_factory=list)
    correcoes: dict[str, str] = field(default_factory=dict)
    cfop_map: dict[str, str] = field(default_factory=dict)
    match_anexo1: MatchAnexo1 | None = None
    fundamentacao: str = ""
    status_correcao: str = "Nao corrigido"

    @property
    def tem_correcao(self) -> bool:
        """True quando ha correcoes de campo ou de CFOP a aplicar."""
        return bool(self.correcoes or self.cfop_map)

    @property
    def tipos(self) -> str:
        """Tipos das inconsistencias, separados por '; '."""
        return "; ".join(i.tipo for i in self.inconsistencias)


# ----------------------------------------------------------------------
# Normalizacao de CST/CSOSN.
# ----------------------------------------------------------------------
def normalizar_cst(texto: str) -> tuple[str, str, str]:
    """Normaliza CST/CSOSN em (origem, codigo, regime).

    "060" -> ("0", "60", "normal"); "60" -> ("", "60", "normal");
    "102" -> ("", "102", "simples"); "0102"/"1102" -> (d0, resto, "simples");
    "160" -> ("1", "60", "normal"); invalido -> (..., "desconhecido").
    """
    digitos = so_digitos(texto)
    if not digitos:
        return "", "", "desconhecido"
    if len(digitos) == 2:
        regime = "normal" if digitos in CSTS_VALIDOS else "desconhecido"
        return "", digitos, regime
    if len(digitos) == 3:
        if digitos in CSOSNS_VALIDOS:
            return "", digitos, "simples"
        origem, codigo = digitos[0], digitos[1:]
        if codigo in CSTS_VALIDOS:
            return origem, codigo, "normal"
        return origem, codigo, "desconhecido"
    if len(digitos) == 4:
        origem, codigo = digitos[0], digitos[1:]
        if codigo in CSOSNS_VALIDOS:
            return origem, codigo, "simples"
        return origem, codigo, "desconhecido"
    return "", digitos, "desconhecido"


def formatar_cst_como_original(original: str, novo_codigo: str) -> str:
    """Formata o novo codigo preservando o padrao (com/sem origem) do original.

    "060" + "00" -> "000"; "60" + "00" -> "00"; "0500" + "102" -> "0102";
    original sem origem -> novo_codigo puro.
    """
    origem, _codigo, _regime = normalizar_cst(original)
    if origem:
        return origem + novo_codigo
    return novo_codigo


# ----------------------------------------------------------------------
# Auxiliares internos.
# ----------------------------------------------------------------------
def _aliquota_texto(valor: Decimal) -> str:
    """Aliquota como texto brasileiro (ponto -> virgula), ex. '20,5'."""
    return str(valor).replace(".", ",")


def _fundamentacao_item(item: ItemAnexo1) -> str:
    """Fundamentacao legivel de um item do Anexo I."""
    texto = item.fundamentacao or ("Anexo I RICMS/BA (Dec. 13.780/2012); "
                                   "Conv. ICMS 142/18")
    partes = []
    if item.cest:
        partes.append("CEST " + item.cest)
    if item.ncm:
        partes.append("NCM " + item.ncm)
    if partes:
        return texto + " - " + ", ".join(partes)
    return texto


def _fundamentacao_regra(regra: RegraTributaria) -> str:
    """Fundamentacao legivel de uma regra tributaria (com detalhe)."""
    texto = regra.fundamentacao or ""
    if regra.detalhe:
        texto = (texto + " (" + regra.detalhe + ")") if texto else regra.detalhe
    return texto


def _confianca_match(match: MatchAnexo1, produto: ProdutoCadastro) -> str:
    """Grau de confianca de um match do Anexo I para o produto."""
    if match.criterio == "cest":
        return CONF_ALTA
    sim = match.similaridade
    if match.criterio == "ncm8":
        sem_descricao = (not normalizar_descricao(produto.descricao)
                         or not normalizar_descricao(match.item.descricao))
        return CONF_ALTA if (sim >= 0.35 or sem_descricao) else CONF_MEDIA
    tamanho = match.tamanho_prefixo
    if tamanho >= 6:
        if not so_digitos(produto.cest) and sim >= 0.55:
            return CONF_ALTA
        return CONF_MEDIA
    if tamanho >= 4:
        return CONF_MEDIA if sim >= 0.35 else CONF_BAIXA
    return CONF_BAIXA


def _melhor_item_por_descricao(base: BaseLegal,
                               descricao: str) -> tuple[ItemAnexo1 | None, float]:
    """Item do Anexo I com descricao mais parecida com a do produto."""
    melhor: ItemAnexo1 | None = None
    melhor_sim = 0.0
    for item in base.anexo1:
        sim = similaridade(descricao, item.descricao)
        if sim > melhor_sim:
            melhor_sim, melhor = sim, item
    return melhor, melhor_sim


# ----------------------------------------------------------------------
# Auditoria.
# ----------------------------------------------------------------------
def _auditar_um(produto: ProdutoCadastro, base: BaseLegal) -> ResultadoAuditoria:
    """Audita um unico produto contra as bases legais."""
    res = ResultadoAuditoria(produto=produto)
    inc = res.inconsistencias
    ncm = so_digitos(produto.ncm)
    cest = so_digitos(produto.cest)
    cst_original = so_digitos(produto.cst)
    if cst_original:
        origem, codigo, regime = normalizar_cst(cst_original)
    else:
        origem, codigo, regime = "", "", ""

    # 1. Validacoes estruturais.
    ncm_ok = False
    if not ncm:
        inc.append(Inconsistencia(
            TIPO_NCM_AUSENTE, "Produto sem NCM informado no cadastro.", "erro"))
    elif len(ncm) != 8 or not ("01" <= ncm[:2] <= "97"):
        inc.append(Inconsistencia(
            TIPO_NCM_INVALIDO,
            f"NCM invalido: '{produto.ncm}' (esperado 8 digitos com capitulo "
            "entre 01 e 97).", "erro"))
    else:
        ncm_ok = True
        if base.tipi_ativa and ncm not in base.tipi:
            inc.append(Inconsistencia(
                TIPO_NCM_NAO_TIPI,
                f"NCM {ncm} nao encontrado na tabela TIPI vigente.", "erro"))
    if cest and len(cest) != 7:
        inc.append(Inconsistencia(
            TIPO_CEST_INVALIDO,
            f"CEST invalido: '{produto.cest}' (esperado 7 digitos).", "erro"))
    if cst_original and codigo not in CSTS_VALIDOS and codigo not in CSOSNS_VALIDOS:
        inc.append(Inconsistencia(
            TIPO_CST_INVALIDO, f"CST/CSOSN invalido: '{produto.cst}'.", "erro"))

    # 2. Tributacao atual (CST prioridade; CFOP desempata).
    cfops_venda = [c for c in produto.cfops if c[:1] in ("5", "6")]
    tem_cfop_st = any(c in CFOPS_ST for c in cfops_venda)
    tem_cfop_trib = any(c in CFOPS_TRIBUTADO for c in cfops_venda)
    if codigo in CSTS_ST or codigo in CSOSNS_ST or tem_cfop_st:
        atual = TRIB_ST
    elif codigo in CSTS_ISENTO or codigo in CSOSNS_ISENTO:
        atual = TRIB_ISENTO
    elif codigo in CSTS_DIFERIMENTO:
        atual = TRIB_DIFERIMENTO
    elif codigo in CSTS_REDUCAO:
        atual = TRIB_REDUCAO
    elif codigo == "00" or codigo in ("101", "102") or \
            (not cst_original and tem_cfop_trib):
        atual = TRIB_INTEGRAL
    elif codigo in ("90", "900"):
        atual = TRIB_OUTROS
    else:
        atual = TRIB_INDETERMINADA

    # 3. Tributacao sugerida (monofasico > ST > isencao > reducao >
    #    diferimento > integral).
    match = base.buscar_anexo1(ncm, cest, produto.descricao)
    conf_match = _confianca_match(match, produto) if match else ""
    res.match_anexo1 = match
    regra_mono = base.buscar_regra(base.monofasico, ncm)
    regra_isen = base.buscar_regra(base.isencao, ncm)
    regra_red = base.buscar_regra(base.reducao, ncm)
    regra_dif = base.buscar_regra(base.diferimento, ncm)

    sugerida = TRIB_INTEGRAL
    fundamentacao = ""
    conf_sugestao = CONF_MEDIA if base.anexo1 else CONF_BAIXA
    if regra_mono:
        sugerida = TRIB_MONOFASICO
        fundamentacao = _fundamentacao_regra(regra_mono)
        conf_sugestao = CONF_MEDIA
    elif match and conf_match in (CONF_MEDIA, CONF_ALTA):
        sugerida = TRIB_ST
        fundamentacao = _fundamentacao_item(match.item)
        conf_sugestao = conf_match
    elif regra_isen:
        sugerida = TRIB_ISENTO
        fundamentacao = _fundamentacao_regra(regra_isen)
        conf_sugestao = CONF_MEDIA
    elif regra_red:
        sugerida = TRIB_REDUCAO
        fundamentacao = _fundamentacao_regra(regra_red)
        conf_sugestao = CONF_MEDIA
    elif regra_dif:
        sugerida = TRIB_DIFERIMENTO
        fundamentacao = _fundamentacao_regra(regra_dif)
        conf_sugestao = CONF_MEDIA

    # Match fraco (baixa) nao muda a sugestao para ST: apenas alerta.
    conf_erros: list[str] = []
    conf_alertas: list[str] = []
    if match and conf_match == CONF_BAIXA:
        segmento = match.item.segmento or "nao informado"
        inc.append(Inconsistencia(
            TIPO_TRIBUTACAO_DIVERGENTE,
            f"Possivel item de ST (segmento {segmento}) - conferir manualmente.",
            "alerta", _fundamentacao_item(match.item)))
        conf_alertas.append(CONF_BAIXA)

    # 4. Comparacao atual x sugerida.
    if sugerida == TRIB_ST and atual in (TRIB_INTEGRAL, TRIB_REDUCAO):
        inc.append(Inconsistencia(
            TIPO_ST_COMO_TRIBUTADO, MSG_ST_COMO_TRIBUTADO, "erro",
            fundamentacao))
        novo = "500" if regime == "simples" else "60"
        res.correcoes["cst"] = formatar_cst_como_original(cst_original, novo)
        mapa = {c: DE_PARA_CFOP_ST[c] for c in produto.cfops
                if c in DE_PARA_CFOP_ST}
        if mapa:
            res.cfop_map.update(mapa)
        if not cest and match and match.item.cest:
            res.correcoes["cest"] = match.item.cest
        conf_erros.append(conf_match or conf_sugestao)

    if atual == TRIB_ST and sugerida != TRIB_ST:
        if base.anexo1 and (match is None or
                            (match.criterio == "ncm_prefixo"
                             and match.tamanho_prefixo < 4)):
            conf_st = CONF_ALTA
        elif match is not None:
            conf_st = CONF_MEDIA
        else:
            conf_st = CONF_BAIXA
        inc.append(Inconsistencia(
            TIPO_TRIBUTADO_COMO_ST, MSG_TRIBUTADO_COMO_ST, "erro",
            fundamentacao))
        if sugerida == TRIB_INTEGRAL:
            novo = "102" if regime == "simples" else "00"
            res.correcoes["cst"] = formatar_cst_como_original(cst_original, novo)
            mapa = {c: DE_PARA_CFOP_NORMAL[c] for c in produto.cfops
                    if c in DE_PARA_CFOP_NORMAL}
            if mapa:
                res.cfop_map.update(mapa)
            if produto.aliquota is None or produto.aliquota == 0:
                res.correcoes["aliquota"] = _aliquota_texto(base.aliquota_padrao)
        conf_erros.append(conf_st)

    if sugerida == TRIB_ST and atual == TRIB_ST and not cest:
        inc.append(Inconsistencia(
            TIPO_CEST_AUSENTE, "Produto sujeito a ST sem CEST informado.",
            "alerta", fundamentacao))
        if match and conf_match in (CONF_MEDIA, CONF_ALTA) and match.item.cest:
            res.correcoes["cest"] = match.item.cest
            conf_alertas.append(conf_match)

    if (match and match.criterio in ("ncm8", "ncm_prefixo") and cest
            and match.item.cest and cest != match.item.cest):
        inc.append(Inconsistencia(
            TIPO_CEST_INCOMPATIVEL,
            f"CEST informado ({cest}) difere do CEST do Anexo I "
            f"({match.item.cest}).", "alerta", _fundamentacao_item(match.item)))
        if conf_match == CONF_ALTA:
            res.correcoes["cest"] = match.item.cest
            conf_alertas.append(conf_match)

    if sugerida in (TRIB_ISENTO, TRIB_REDUCAO, TRIB_MONOFASICO,
                    TRIB_DIFERIMENTO) and atual != sugerida \
            and atual != TRIB_INDETERMINADA:
        inc.append(Inconsistencia(
            TIPO_TRIBUTACAO_DIVERGENTE,
            f"Tributacao atual ({atual}) diverge da sugerida ({sugerida}).",
            "erro", fundamentacao))
        conf_erros.append(CONF_MEDIA)

    aliquota = produto.aliquota
    if codigo in ("00", "20") and (aliquota is None or aliquota == 0):
        inc.append(Inconsistencia(
            TIPO_CST_ALIQUOTA,
            "CST tributado sem aliquota de ICMS informada.", "erro"))
        if sugerida == TRIB_INTEGRAL and "aliquota" not in res.correcoes:
            res.correcoes["aliquota"] = _aliquota_texto(base.aliquota_padrao)
        conf_erros.append(CONF_MEDIA)
    elif codigo and (codigo in CSTS_ISENTO or codigo == "60"
                     or codigo in CSOSNS_ISENTO or codigo == "500") \
            and aliquota is not None and aliquota > 0:
        inc.append(Inconsistencia(
            TIPO_CST_ALIQUOTA,
            "Aliquota informada para CST isento/ST (verificar se e aliquota "
            "interna de referencia).", "alerta"))

    if not ncm_ok and base.anexo1 and normalizar_descricao(produto.descricao):
        item_desc, sim_desc = _melhor_item_por_descricao(base, produto.descricao)
        if item_desc is not None and sim_desc >= 0.55:
            segmento = item_desc.segmento or "nao informado"
            ncm_item = item_desc.ncm or "?"
            inc.append(Inconsistencia(
                TIPO_DIVERGENCIA_DESCRICAO,
                f"Descricao sugere item de ST (segmento {segmento}, NCM "
                f"{ncm_item}) - revisar NCM do cadastro.", "alerta",
                _fundamentacao_item(item_desc)))

    # 5. Situacao, confianca dominante e fundamentacao.
    tem_erro = any(i.nivel == "erro" for i in inc)
    tem_alerta = any(i.nivel == "alerta" for i in inc)
    res.situacao = "INCONSISTENTE" if tem_erro else ("ALERTA" if tem_alerta
                                                     else "OK")
    res.tributacao_atual = atual
    res.tributacao_sugerida = sugerida
    res.fundamentacao = fundamentacao

    confianca = ""
    for conf in conf_erros + conf_alertas:
        if conf:
            confianca = conf
            break
    if not confianca and res.tem_correcao:
        confianca = conf_sugestao
    if res.situacao == "OK" and not res.tem_correcao:
        confianca = ""
    res.confianca = confianca
    return res


def auditar_produtos(produtos: list[ProdutoCadastro],
                     base: BaseLegal) -> list[ResultadoAuditoria]:
    """Audita todos os produtos do cadastro contra as bases legais."""
    return [_auditar_um(produto, base) for produto in produtos]


# ----------------------------------------------------------------------
# Indicadores.
# ----------------------------------------------------------------------
def calcular_indicadores(resultados: list[ResultadoAuditoria]) -> dict:
    """Indicadores agregados da auditoria (para painel e relatorio)."""
    total = len(resultados)
    corretos = sum(1 for r in resultados if r.situacao == "OK")
    inconsistentes = sum(1 for r in resultados if r.situacao == "INCONSISTENTE")
    alertas = sum(1 for r in resultados if r.situacao == "ALERTA")
    tipos_st = {TIPO_ST_COMO_TRIBUTADO, TIPO_TRIBUTADO_COMO_ST}
    st_incorretos = sum(1 for r in resultados
                        if any(i.tipo in tipos_st for i in r.inconsistencias))
    por_tipo: dict[str, int] = {}
    for r in resultados:
        for i in r.inconsistencias:
            por_tipo[i.tipo] = por_tipo.get(i.tipo, 0) + 1
    percentual = round(100.0 * inconsistentes / total, 1) if total else 0.0
    return {
        "total": total,
        "corretos": corretos,
        "inconsistentes": inconsistentes,
        "alertas": alertas,
        "percentual_inconsistencias": percentual,
        "sujeitos_st": sum(1 for r in resultados
                           if r.tributacao_sugerida == TRIB_ST),
        "st_incorretos": st_incorretos,
        "corrigidos": sum(1 for r in resultados
                          if r.status_correcao == "Corrigido"),
        "por_tipo": por_tipo,
    }
