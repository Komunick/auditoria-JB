"""Regras de negocio da Emissao de NFS-e (nucleo puro, spec 006).

Sem FastAPI, sem banco e sem rede: tipos, catalogo de apontamentos,
normalizacao de texto, leitura de competencia, CPF e valor, o perfil de
emissao com as pendencias dele, a regra oficial da aliquota e o modelo da
discriminacao.

Tres regras estruturam o modulo:

1. **Pendencia nao vira padrao.** O que depende de resposta da JB (JB-2, JB-8)
   ou do Sistema Nacional (R5) fica `None` no perfil, e `None` quer dizer
   "pendente". Perfil com pendencia nao gera DPS. Nenhum campo de decisao tem
   valor padrao aqui.
2. **O que a documentacao oficial decide nao e' escolha.** Se a aliquota vai
   ou nao na DPS sai da tabela do Anexo I (`regra_aliquota`), e as faixas de
   serie, aliquota e regime especial sao conferidas na validacao do perfil
   (specs/006-emissao-nfse/research.md).
3. **Nada e' adivinhado.** Valor ambiguo, turma parecida e competencia fora
   dos formatos aceitos sao recusados com mensagem; ausencia nunca vira zero.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from . import documentos_br

# ----------------------------------------------------------------------
# Erros e niveis

AVISO = "aviso"
BLOQUEIO = "bloqueio"

PERFIL_INVALIDO = "PERFIL_INVALIDO"
MODELO_INVALIDO = "MODELO_INVALIDO"
PERFIL_COM_PENDENCIA = "PERFIL_COM_PENDENCIA"


class ErroNfse(Exception):
    """Erro de regra de negocio, com codigo estavel e campo afetado."""

    def __init__(self, codigo: str, mensagem: str, *, campo: str | None = None):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.campo = campo


# ----------------------------------------------------------------------
# Catalogo de apontamentos (data-model.md, "Catalogo de apontamentos")

CPF_AUSENTE = "CPF_AUSENTE"
CPF_INVALIDO = "CPF_INVALIDO"
CPF_COMPLETADO = "CPF_COMPLETADO"
VALOR_AUSENTE = "VALOR_AUSENTE"
VALOR_INVALIDO = "VALOR_INVALIDO"
VALOR_NAO_POSITIVO = "VALOR_NAO_POSITIVO"
COMPETENCIA_AUSENTE = "COMPETENCIA_AUSENTE"
COMPETENCIA_INVALIDA = "COMPETENCIA_INVALIDA"
COMPETENCIA_DIVERGENTE = "COMPETENCIA_DIVERGENTE"
COMPETENCIA_FUTURA = "COMPETENCIA_FUTURA"
TURMA_AUSENTE = "TURMA_AUSENTE"
TURMA_DESCONHECIDA = "TURMA_DESCONHECIDA"
TURMA_PENDENTE = "TURMA_PENDENTE"
RESPONSAVEL_AUSENTE = "RESPONSAVEL_AUSENTE"
ALUNO_AUSENTE = "ALUNO_AUSENTE"
NOME_LONGO = "NOME_LONGO"
ENDERECO_INCOMPLETO = "ENDERECO_INCOMPLETO"
ENDERECO_NAO_ESTRUTURADO = "ENDERECO_NAO_ESTRUTURADO"
DUPLICATA_NO_LOTE = "DUPLICATA_NO_LOTE"
DUPLICATA_APROVADA = "DUPLICATA_APROVADA"
DISCRIMINACAO_LONGA = "DISCRIMINACAO_LONGA"
ROTULO_REPETIDO = "ROTULO_REPETIDO"
TEXTO_NAO_RECONHECIDO = "TEXTO_NAO_RECONHECIDO"
CARACTERE_REMOVIDO = "CARACTERE_REMOVIDO"

# Nivel padrao. Os de endereco sobem para bloqueio quando o perfil decide que
# o endereco vai para a nota (`endereco_tomador = 'informar'`).
CATALOGO = {
    CPF_AUSENTE: BLOQUEIO,
    CPF_INVALIDO: BLOQUEIO,
    CPF_COMPLETADO: AVISO,
    VALOR_AUSENTE: BLOQUEIO,
    VALOR_INVALIDO: BLOQUEIO,
    VALOR_NAO_POSITIVO: BLOQUEIO,
    COMPETENCIA_AUSENTE: BLOQUEIO,
    COMPETENCIA_INVALIDA: BLOQUEIO,
    COMPETENCIA_DIVERGENTE: AVISO,
    COMPETENCIA_FUTURA: BLOQUEIO,
    TURMA_AUSENTE: BLOQUEIO,
    TURMA_DESCONHECIDA: BLOQUEIO,
    TURMA_PENDENTE: BLOQUEIO,
    RESPONSAVEL_AUSENTE: BLOQUEIO,
    ALUNO_AUSENTE: BLOQUEIO,
    NOME_LONGO: BLOQUEIO,
    ENDERECO_INCOMPLETO: AVISO,
    ENDERECO_NAO_ESTRUTURADO: AVISO,
    DUPLICATA_NO_LOTE: BLOQUEIO,
    DUPLICATA_APROVADA: BLOQUEIO,
    DISCRIMINACAO_LONGA: BLOQUEIO,
    ROTULO_REPETIDO: BLOQUEIO,
    TEXTO_NAO_RECONHECIDO: AVISO,
    CARACTERE_REMOVIDO: AVISO,
}

# Limites do leiaute v1.01 (research.md, R1).
MAX_DISCRIMINACAO = 2000
MAX_NOME = 300
MAX_LOGRADOURO = 255
MAX_NUMERO = 60
MAX_COMPLEMENTO = 156
MAX_BAIRRO = 60
MAX_INSC_MUNICIPAL = 15


@dataclass(frozen=True)
class Apontamento:
    codigo: str
    nivel: str
    campo: str | None
    mensagem: str
    referencia: dict | None = None


def apontamento(codigo: str, campo: str | None, mensagem: str, *,
                nivel: str | None = None,
                referencia: dict | None = None) -> Apontamento:
    return Apontamento(codigo, nivel or CATALOGO[codigo], campo, mensagem,
                       referencia)


# ----------------------------------------------------------------------
# Normalizacao de texto


def normalizar_texto(valor) -> tuple[str, bool]:
    """NFKC, sem caracteres de controle nem invisiveis, espacos juntados.

    Devolve `(texto, removeu)`: `removeu` diz se havia caractere de controle
    ou invisivel (zero-width, BOM, campainha...) — vira aviso, nunca some
    calado. Quebra de linha e tabulacao viram espaco, sem aviso.
    """
    if valor is None:
        return "", False
    texto = unicodedata.normalize("NFKC", str(valor))
    removeu = False
    partes = []
    for ch in texto:
        if ch in "\n\r\t\v\f":
            partes.append(" ")
            continue
        if unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs"):
            removeu = True
            continue
        partes.append(ch)
    return " ".join("".join(partes).split()), removeu


def chave_comparacao(valor) -> str:
    """Forma de comparar nomes e turmas: sem caixa, sem acento, sem espaco
    sobrando. So para comparar; o que vai para a nota mantem a grafia."""
    texto, _ = normalizar_texto(valor)
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto)
                         if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.casefold().split())


# ----------------------------------------------------------------------
# Competencia

MESES_EXTENSO = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
                 "julho", "agosto", "setembro", "outubro", "novembro",
                 "dezembro")

_MES_POR_NOME = {}
for _i, _nome in enumerate(MESES_EXTENSO, start=1):
    _chave = chave_comparacao(_nome)
    _MES_POR_NOME[_chave] = _i
    _MES_POR_NOME[_chave[:3]] = _i

_RE_MM_AAAA = re.compile(r"^(\d{1,2})/(\d{4})$")
_RE_AAAA_MM = re.compile(r"^(\d{4})-(\d{2})$")
_RE_NOME_AAAA = re.compile(r"^([a-z]+)\s*(?:/|\s+de\s+|\s)\s*(\d{4})$")
_RE_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _competencia(ano: int, mes: int, bruto) -> str:
    if not 1 <= mes <= 12:
        raise ErroNfse(COMPETENCIA_INVALIDA, f"Mês inválido em {bruto!r}.")
    if not 2000 <= ano <= 2099:
        raise ErroNfse(COMPETENCIA_INVALIDA, f"Ano inválido em {bruto!r}.")
    return f"{ano:04d}-{mes:02d}"


def ler_competencia(valor, *, tipo: str = "texto") -> str:
    """Competencia em `AAAA-MM`, a partir dos formatos de data-model.md.

    `tipo='data'` e' a celula de data da planilha (gravada como AAAA-MM-DD).
    Ano com dois digitos e mes sem ano sao recusados: nao se chuta.
    """
    if isinstance(valor, (dt.date, dt.datetime)):
        return _competencia(valor.year, valor.month, valor)
    texto, _ = normalizar_texto(valor)
    if not texto:
        raise ErroNfse(COMPETENCIA_AUSENTE, "Competência não informada.")
    if tipo == "data":
        achado = _RE_DATA_ISO.match(texto)
        if achado:
            return _competencia(int(achado.group(1)), int(achado.group(2)), valor)
    achado = _RE_MM_AAAA.match(texto)
    if achado:
        return _competencia(int(achado.group(2)), int(achado.group(1)), valor)
    achado = _RE_AAAA_MM.match(texto)
    if achado:
        return _competencia(int(achado.group(1)), int(achado.group(2)), valor)
    achado = _RE_NOME_AAAA.match(chave_comparacao(texto))
    if achado and achado.group(1) in _MES_POR_NOME:
        return _competencia(int(achado.group(2)), _MES_POR_NOME[achado.group(1)],
                            valor)
    raise ErroNfse(COMPETENCIA_INVALIDA,
                   f"Competência {texto!r} fora dos formatos aceitos "
                   "(MM/AAAA, AAAA-MM ou mês/AAAA).")


def primeiro_dia(competencia: str) -> dt.date:
    ano, mes = competencia.split("-")
    return dt.date(int(ano), int(mes), 1)


# ----------------------------------------------------------------------
# CPF e valor


def ler_cpf(valor, *, tipo: str = "texto") -> tuple[str, bool]:
    """CPF em 11 digitos e se foi completado com zeros.

    Celula NUMERICA da planilha perde o zero inicial (o Excel guarda numero);
    so nesse caso o CPF e' completado, e quem chama transforma isso em aviso.
    Texto com menos de 11 digitos e' erro: ali o zero nao sumiu sozinho.
    """
    bruto = str(valor if valor is not None else "").strip()
    if not bruto:
        raise ErroNfse(CPF_AUSENTE, "CPF do responsável não informado.")
    digitos = re.sub(r"\D", "", bruto)
    completado = False
    if tipo == "numero" and 0 < len(digitos) < 11:
        digitos = digitos.zfill(11)
        completado = True
    try:
        return documentos_br.digitos_cpf(digitos), completado
    except documentos_br.DocumentoInvalido as exc:
        raise ErroNfse(CPF_INVALIDO, exc.mensagem) from exc


def ler_valor(valor, *, tipo: str = "texto") -> int:
    """Valor da nota em centavos, maior que zero.

    Texto aceita o prefixo `R$`; o resto segue `decimal_monetario`, que
    recusa separador ambiguo (`1.250`) em vez de chutar. Formula sem valor
    calculado e' ausencia, e ausencia nunca vira zero.
    """
    bruto = str(valor if valor is not None else "").strip()
    if not bruto:
        raise ErroNfse(VALOR_AUSENTE, "Valor não informado.")
    try:
        if tipo == "numero":
            try:
                numero = documentos_br.decimal_monetario(Decimal(bruto))
            except InvalidOperation as exc:
                raise ErroNfse(VALOR_INVALIDO, f"Número inválido: {bruto!r}.") from exc
        else:
            sem_moeda = re.sub(r"^R\$\s*", "", bruto, flags=re.IGNORECASE).strip()
            numero = documentos_br.decimal_monetario(sem_moeda)
    except documentos_br.DocumentoInvalido as exc:
        if exc.codigo == documentos_br.FORMULA_SEM_VALOR:
            raise ErroNfse(VALOR_AUSENTE,
                           "Fórmula sem valor calculado na planilha.") from exc
        if exc.codigo == documentos_br.VALOR_VAZIO:
            raise ErroNfse(VALOR_AUSENTE, "Valor não informado.") from exc
        raise ErroNfse(VALOR_INVALIDO, exc.mensagem) from exc
    if numero <= 0:
        raise ErroNfse(VALOR_NAO_POSITIVO,
                       f"Valor {bruto!r} tem de ser maior que zero.")
    return int(numero * 100)


def centavos_em_texto(centavos: int) -> str:
    """Centavos -> `1250.00`, o formato decimal do leiaute."""
    return f"{centavos // 100}.{centavos % 100:02d}"


# ----------------------------------------------------------------------
# Perfil de emissao

ENDERECO_INFORMAR = "informar"
ENDERECO_OMITIR = "omitir"
TRIB_PTOTTRIBSN = "pTotTribSN"
TRIB_PTOTTRIB = "pTotTrib"

ALIQ_INFORMAR = "informar"
ALIQ_NAO_INFORMAR = "nao_informar"
ALIQ_DEPENDE = "depende_do_convenio"
ALIQ_PENDENTE = "pendente"

REGIMES_ESPECIAIS = (0, 1, 2, 3, 4, 5, 6, 9)
SERIE_MIN, SERIE_MAX = 1, 49999          # aplicativo proprio (E0010)
ALIQUOTA_MAX = 500                       # 5,00% (E0595)
ALIQUOTA_MIN_RETIDO = 180                # 1,8% (RN #508)
CATEGORIAS = ("infantil", "fundamental")


@dataclass(frozen=True)
class Turma:
    nome: str
    apelidos: tuple[str, ...] = ()
    categoria: str | None = None
    c_trib_nac: str | None = None
    c_nbs: str | None = None
    c_ind_op: str | None = None
    c_class_trib: str | None = None
    ref_cnae: str | None = None
    ref_item_lista: str | None = None
    ref_ctiss: str | None = None


@dataclass(frozen=True)
class PerfilVersao:
    """Uma versao do perfil. Campos de decisao `None` = pendente."""

    cnpj: str
    razao_social: str
    municipio_ibge: str
    municipio_prestacao_ibge: str
    iss_retido: bool
    serie_dps: str
    modelo_discriminacao: str
    turmas: tuple[Turma, ...]
    inscricao_municipal: str | None
    informar_im: bool | None
    reg_ap_trib_sn: int | None
    reg_esp_trib: int | None
    convenio_incidencia_ativo: bool | None
    aliquota_centesimos: int | None
    tributos_aprox: str | None
    p_tot_trib_sn: int | None
    p_tot_trib_fed: int | None
    p_tot_trib_est: int | None
    p_tot_trib_mun: int | None
    endereco_tomador: str | None
    emissor: str = "nacional"
    op_simp_nac: int = 3
    ambiente: int = 2


@dataclass(frozen=True)
class Pendencia:
    campo: str
    descricao: str
    origem: str          # JB-n, Rn ou "cadastro"


def _invalido(campo: str, mensagem: str) -> ErroNfse:
    return ErroNfse(PERFIL_INVALIDO, mensagem, campo=campo)


def _texto_opcional(dados: dict, campo: str, maximo: int) -> str | None:
    texto, _ = normalizar_texto(dados.get(campo))
    if not texto:
        return None
    if len(texto) > maximo:
        raise _invalido(campo, f"'{campo}' passa de {maximo} caracteres.")
    return texto


def _texto_obrigatorio(dados: dict, campo: str, maximo: int) -> str:
    texto = _texto_opcional(dados, campo, maximo)
    if texto is None:
        raise _invalido(campo, f"'{campo}' é obrigatório.")
    return texto


def _bool_opcional(dados: dict, campo: str) -> bool | None:
    valor = dados.get(campo)
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return valor
    if valor in (0, 1, "0", "1"):
        return str(valor) == "1"
    raise _invalido(campo, f"'{campo}' deve ser sim ou não.")


def _int_opcional(dados: dict, campo: str, permitidos) -> int | None:
    valor = dados.get(campo)
    if valor is None or valor == "":
        return None
    try:
        numero = int(str(valor).strip())
    except ValueError as exc:
        raise _invalido(campo, f"'{campo}' inválido: {valor!r}.") from exc
    if numero not in permitidos:
        raise _invalido(campo, f"'{campo}' = {numero} não está entre "
                               f"{', '.join(map(str, permitidos))}.")
    return numero


def _percentual_opcional(dados: dict, campo: str, maximo: int) -> int | None:
    """Percentual em centesimos de ponto (5,00% -> 500)."""
    valor = dados.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    try:
        numero = documentos_br.decimal_monetario(
            valor if not isinstance(valor, str) else valor.replace("%", "").strip())
    except documentos_br.DocumentoInvalido as exc:
        raise _invalido(campo, f"'{campo}': {exc.mensagem}") from exc
    centesimos = int(numero * 100)
    if not 0 <= centesimos <= maximo:
        raise _invalido(campo, f"'{campo}' fora do intervalo permitido "
                               f"(0 a {centavos_em_texto(maximo)}%).")
    return centesimos


def _ibge(dados: dict, campo: str) -> str:
    valor = re.sub(r"\D", "", str(dados.get(campo) or ""))
    if len(valor) != 7:
        raise _invalido(campo, f"'{campo}' deve ter os 7 dígitos do código IBGE.")
    return valor


def _codigo(valor, digitos: int, rotulo: str) -> str | None:
    texto = re.sub(r"[.\-/\s]", "", str(valor or ""))
    if not texto:
        return None
    if not re.fullmatch(rf"\d{{{digitos}}}", texto):
        raise _invalido("turmas", f"{rotulo} deve ter {digitos} dígitos: {valor!r}.")
    return texto


def _turmas(lista) -> tuple[Turma, ...]:
    if not lista:
        raise _invalido("turmas", "O perfil precisa de pelo menos uma turma.")
    turmas = []
    vistos: dict[str, str] = {}
    for item in lista:
        nome, _ = normalizar_texto(item.get("nome"))
        if not nome:
            raise _invalido("turmas", "Turma sem nome.")
        if len(nome) > 60:
            raise _invalido("turmas", f"Nome de turma longo demais: {nome!r}.")
        apelidos = []
        for apelido in item.get("apelidos") or []:
            texto, _ = normalizar_texto(apelido)
            if texto:
                apelidos.append(texto)
        for chave_texto in [nome, *apelidos]:
            chave = chave_comparacao(chave_texto)
            if chave in vistos:
                raise _invalido("turmas",
                                f"{chave_texto!r} repete o nome ou apelido da "
                                f"turma {vistos[chave]!r}.")
            vistos[chave] = nome
        categoria = item.get("categoria") or None
        if categoria is not None and categoria not in CATEGORIAS:
            raise _invalido("turmas", f"Categoria inválida: {categoria!r}.")
        refs = {}
        for ref in ("ref_cnae", "ref_item_lista", "ref_ctiss"):
            texto, _ = normalizar_texto(item.get(ref))
            refs[ref] = texto[:30] or None
        turmas.append(Turma(
            nome=nome, apelidos=tuple(apelidos), categoria=categoria,
            c_trib_nac=_codigo(item.get("c_trib_nac"), 6, "Código de tributação nacional"),
            c_nbs=_codigo(item.get("c_nbs"), 9, "NBS"),
            c_ind_op=_codigo(item.get("c_ind_op"), 6, "Indicador de operação"),
            c_class_trib=_codigo(item.get("c_class_trib"), 6, "Classificação tributária"),
            **refs))
    return tuple(turmas)


def validar_perfil(dados: dict) -> PerfilVersao:
    """Dados do formulario -> versao do perfil, ou `ErroNfse(PERFIL_INVALIDO)`.

    Campo de decisao ausente continua `None` (pendente); so o que e' do
    cadastro e' obrigatorio aqui. Regras oficiais conferidas: serie de 1 a
    49999 (E0010), aliquota ate 5% (E0595), regime especial 0 com ISS pelo
    Simples (E0175) e `indTotTrib` proibido para ME/EPP (E0712).
    """
    try:
        cnpj = documentos_br.digitos_cnpj(dados.get("cnpj"))
    except documentos_br.DocumentoInvalido as exc:
        raise _invalido("cnpj", exc.mensagem) from exc

    emissor = dados.get("emissor") or "nacional"
    if emissor != "nacional":
        raise _invalido("emissor", "Na Fase 1 só o Emissor Nacional é aceito.")
    op_simp_nac = int(dados.get("op_simp_nac") or 3)
    if op_simp_nac != 3:
        raise _invalido("op_simp_nac", "Na Fase 1 só ME/EPP do Simples (3).")

    iss_retido = _bool_opcional(dados, "iss_retido")
    if iss_retido is None:
        raise _invalido("iss_retido", "Informe se o ISS é retido pelo tomador.")

    serie_bruta = str(dados.get("serie_dps") or "").strip()
    if not serie_bruta.isdigit() or not SERIE_MIN <= int(serie_bruta) <= SERIE_MAX:
        raise _invalido("serie_dps", "A série da DPS deve estar entre 1 e 49999 "
                                     "(faixa de aplicativo próprio, E0010).")

    reg_ap = _int_opcional(dados, "reg_ap_trib_sn", (1, 2, 3))
    reg_esp = _int_opcional(dados, "reg_esp_trib", REGIMES_ESPECIAIS)
    if reg_ap == 1 and reg_esp not in (None, 0):
        raise _invalido("reg_esp_trib", "Com ISS apurado pelo Simples "
                                        "(regApTribSN = 1) o regime especial "
                                        "deve ser 0 (E0175).")

    aliquota = _percentual_opcional(dados, "aliquota", ALIQUOTA_MAX)
    if aliquota == 0:
        raise _invalido("aliquota", "Alíquota zero não é aceita.")
    convenio = _bool_opcional(dados, "convenio_incidencia_ativo")
    if (aliquota is not None and reg_ap == 1 and iss_retido and convenio
            and aliquota < ALIQUOTA_MIN_RETIDO):
        raise _invalido("aliquota", "Com retenção, a alíquota mínima é 1,8% (E0621).")

    tributos = dados.get("tributos_aprox") or None
    if tributos not in (None, TRIB_PTOTTRIBSN, TRIB_PTOTTRIB):
        raise _invalido("tributos_aprox", "Para ME/EPP use pTotTribSN ou pTotTrib "
                                          "(indTotTrib é proibido, E0712).")

    endereco = dados.get("endereco_tomador") or None
    if endereco not in (None, ENDERECO_INFORMAR, ENDERECO_OMITIR):
        raise _invalido("endereco_tomador", "Use 'informar' ou 'omitir'.")

    modelo = str(dados.get("modelo_discriminacao") or "")
    try:
        validar_modelo(modelo)
    except ErroNfse as exc:
        raise _invalido("modelo_discriminacao", exc.mensagem) from exc

    return PerfilVersao(
        cnpj=cnpj,
        razao_social=_texto_obrigatorio(dados, "razao_social", 300),
        municipio_ibge=_ibge(dados, "municipio_ibge"),
        municipio_prestacao_ibge=_ibge(dados, "municipio_prestacao_ibge"),
        iss_retido=iss_retido,
        serie_dps=str(int(serie_bruta)),
        modelo_discriminacao=modelo.strip(),
        turmas=_turmas(dados.get("turmas")),
        inscricao_municipal=_texto_opcional(dados, "inscricao_municipal",
                                            MAX_INSC_MUNICIPAL),
        informar_im=_bool_opcional(dados, "informar_im"),
        reg_ap_trib_sn=reg_ap,
        reg_esp_trib=reg_esp,
        convenio_incidencia_ativo=convenio,
        aliquota_centesimos=aliquota,
        tributos_aprox=tributos,
        p_tot_trib_sn=_percentual_opcional(dados, "p_tot_trib_sn", 9999),
        p_tot_trib_fed=_percentual_opcional(dados, "p_tot_trib_fed", 99999),
        p_tot_trib_est=_percentual_opcional(dados, "p_tot_trib_est", 99999),
        p_tot_trib_mun=_percentual_opcional(dados, "p_tot_trib_mun", 99999),
        endereco_tomador=endereco,
    )


def regra_aliquota(p: PerfilVersao) -> str:
    """Se `pAliq` vai na DPS, pela tabela do Anexo I (research.md).

    ME/EPP sem beneficio municipal: regime especial diferente de 0 proibe
    (E0604); ISS pelo Simples (regApTribSN = 1) informa so com retencao;
    ISS fora do Simples (2 ou 3) informa so com convenio inativo.
    """
    if p.reg_esp_trib not in (None, 0):
        return ALIQ_NAO_INFORMAR
    if p.reg_ap_trib_sn is None:
        return ALIQ_PENDENTE
    if p.reg_ap_trib_sn == 1:
        return ALIQ_INFORMAR if p.iss_retido else ALIQ_NAO_INFORMAR
    if p.convenio_incidencia_ativo is None:
        return ALIQ_DEPENDE
    return ALIQ_NAO_INFORMAR if p.convenio_incidencia_ativo else ALIQ_INFORMAR


def pendencias_do_perfil(p: PerfilVersao) -> list[Pendencia]:
    """O que falta decidir antes de gerar DPS, com a origem de cada item."""
    falta: list[Pendencia] = []
    if p.endereco_tomador is None:
        falta.append(Pendencia(
            "endereco_tomador",
            "Endereço do tomador: informar o que a escola mandou ou não informar.",
            "JB-2"))
    if p.reg_ap_trib_sn is None:
        falta.append(Pendencia(
            "reg_ap_trib_sn",
            "Regime de apuração no Simples (regApTribSN: 1, 2 ou 3).", "JB-8"))
    if p.reg_esp_trib is None:
        falta.append(Pendencia(
            "reg_esp_trib", "Regime especial de tributação (regEspTrib).", "JB-8"))
    if p.tributos_aprox is None:
        falta.append(Pendencia(
            "tributos_aprox",
            "Forma dos tributos aproximados (pTotTribSN ou pTotTrib).", "JB-8"))
    elif p.tributos_aprox == TRIB_PTOTTRIBSN and p.p_tot_trib_sn is None:
        falta.append(Pendencia(
            "p_tot_trib_sn", "Percentual aproximado do Simples (pTotTribSN).",
            "JB-8"))
    elif p.tributos_aprox == TRIB_PTOTTRIB:
        for campo, nome in (("p_tot_trib_fed", "federais"),
                            ("p_tot_trib_est", "estaduais"),
                            ("p_tot_trib_mun", "municipais")):
            if getattr(p, campo) is None:
                falta.append(Pendencia(
                    campo, f"Percentual aproximado dos tributos {nome}.", "JB-8"))
    if p.informar_im is None:
        falta.append(Pendencia(
            "informar_im",
            "Se a escola tem registro complementar no CNC do município "
            "(define se a inscrição municipal vai na DPS).", "R5"))
    elif p.informar_im and not p.inscricao_municipal:
        falta.append(Pendencia(
            "inscricao_municipal", "Inscrição municipal marcada para ir na DPS, "
                                   "mas não cadastrada.", "cadastro"))
    regra = regra_aliquota(p)
    if regra == ALIQ_DEPENDE:
        falta.append(Pendencia(
            "convenio_incidencia_ativo",
            "Se o convênio do município de incidência está ativo no Sistema "
            "Nacional (decide se a alíquota vai na DPS).", "R5"))
    elif regra == ALIQ_INFORMAR and p.aliquota_centesimos is None:
        falta.append(Pendencia(
            "aliquota", "A regra oficial manda informar a alíquota, e ela não "
                        "foi cadastrada.", "JB-8"))
    return falta


# ----------------------------------------------------------------------
# Turmas


def resolver_turma(texto, turmas) -> Turma | None:
    """Turma pelo nome ou apelido exatos, depois da normalizacao. Sem busca
    aproximada: `Infantil` nao vira `Infantil II`."""
    chave = chave_comparacao(texto)
    if not chave:
        return None
    for turma in turmas:
        if chave == chave_comparacao(turma.nome) or chave in {
                chave_comparacao(a) for a in turma.apelidos}:
            return turma
    return None


def turma_pendente(turma: Turma) -> bool:
    """Sem codigo de tributacao nacional ou sem NBS, a turma nao emite."""
    return not turma.c_trib_nac or not turma.c_nbs


_RE_SEPARADOR = re.compile(r"\s+[-–—/]\s+")


def separar_turma_do_aluno(texto, turmas) -> tuple[str, str | None]:
    """`"Pedro Exemplo - BERÇÁRIO"` -> `("Pedro Exemplo", "BERÇÁRIO")`.

    So separa quando o que vem depois do separador e' turma do perfil; do
    contrario devolve o texto inteiro como nome e a turma vazia.
    """
    nome, _ = normalizar_texto(texto)
    for achado in reversed(list(_RE_SEPARADOR.finditer(nome))):
        resto = nome[achado.end():].strip()
        aluno = nome[:achado.start()].strip()
        if aluno and resolver_turma(resto, turmas) is not None:
            return aluno, resto
    return nome, None


# ----------------------------------------------------------------------
# Modelo da discriminacao

CAMPOS_MODELO = ("turma", "aluno", "responsavel", "mes", "mes_extenso", "ano",
                 "competencia")
_RE_CAMPO = re.compile(r"\{([^{}]*)\}")


def validar_modelo(modelo) -> None:
    """Campos so da lista fechada, todo em minusculas ou todo em maiusculas."""
    texto = str(modelo or "")
    if not texto.strip():
        raise ErroNfse(MODELO_INVALIDO, "O modelo da discriminação está vazio.")
    if len(texto) > MAX_DISCRIMINACAO:
        raise ErroNfse(MODELO_INVALIDO, "O modelo passa de 2000 caracteres.")
    for campo in _RE_CAMPO.findall(texto):
        if not (campo in CAMPOS_MODELO
                or (campo.isupper() and campo.lower() in CAMPOS_MODELO)):
            raise ErroNfse(MODELO_INVALIDO,
                           f"Campo {{{campo}}} não existe. Use: "
                           + ", ".join("{" + c + "}" for c in CAMPOS_MODELO)
                           + " (ou em maiúsculas).")
    if "{" in _RE_CAMPO.sub("", texto) or "}" in _RE_CAMPO.sub("", texto):
        raise ErroNfse(MODELO_INVALIDO, "Chave { ou } sem par no modelo.")


def montar_discriminacao(modelo: str, *, turma: str, aluno: str,
                         responsavel: str, competencia: str) -> str:
    """Preenche o modelo. Campo em maiusculas devolve o valor em maiusculas."""
    ano, mes = (int(x) for x in competencia.split("-"))
    valores = {
        "turma": turma,
        "aluno": aluno,
        "responsavel": responsavel or "",
        "mes": f"{mes:02d}",
        "mes_extenso": MESES_EXTENSO[mes - 1],
        "ano": f"{ano:04d}",
        "competencia": f"{mes:02d}/{ano:04d}",
    }

    def trocar(achado: re.Match) -> str:
        campo = achado.group(1)
        valor = valores[campo.lower()]
        return valor.upper() if campo.isupper() else valor

    return _RE_CAMPO.sub(trocar, modelo).strip()


# ----------------------------------------------------------------------
# Linha para conferencia (os valores efetivos ja com as correcoes)


@dataclass(frozen=True)
class LinhaEfetiva:
    """Uma linha do lote como a conferencia ve: valores efetivos (bruto ou a
    ultima correcao) e o tipo de celula de cada campo que veio da planilha
    sem correcao (`numero`, `data` ou `texto`)."""

    ref: int
    campos: dict
    tipos: dict = field(default_factory=dict)
    excluida: bool = False
    nao_reconhecido: tuple[str, ...] = ()
    rotulos_repetidos: tuple[str, ...] = ()
