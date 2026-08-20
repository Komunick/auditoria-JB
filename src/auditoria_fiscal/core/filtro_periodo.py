"""Filtro por periodo (intervalo de datas) das notas do SPED.

Duas bases de data, escolhidas pelo usuario na tela de conferencia:

- "escrituracao": data de entrada/saida do registro C100 (DT_E_S). E a data
  que serve de escrituracao - o periodo em que a nota entra nos livros.
- "emissao": data de emissao do documento (DT_DOC).

Ambas ja vem preenchidas do parser (core/sped_parser.py) e do XML. Notas sem
a data escolhida sao EXCLUIDAS quando ha qualquer limite ativo, porque nao ha
como saber se caem no intervalo; a contagem dessas fica disponivel para a tela
avisar o auditor.

O modulo fica em core/ para que a versao web e a desktop usem exatamente o
mesmo criterio, como acontece com o filtro de entradas (core/filtro_sped.py).
"""

from __future__ import annotations

from datetime import date, datetime

from .modelos import NotaFiscal

BASE_ESCRITURACAO = "escrituracao"
BASE_EMISSAO = "emissao"
BASES = (BASE_ESCRITURACAO, BASE_EMISSAO)

# Rotulo curto de cada base (tela e cabecalho da coluna de data).
ROTULO_BASE = {
    BASE_ESCRITURACAO: "Escrituracao",
    BASE_EMISSAO: "Emissao",
}


def normalizar_base(base) -> str:
    """Qualquer valor invalido cai no padrao: escrituracao (o pedido do uso)."""
    return base if base in BASES else BASE_ESCRITURACAO


def data_base(nota: NotaFiscal, base: str):
    """A data da nota na base escolhida (date ou None)."""
    if normalizar_base(base) == BASE_EMISSAO:
        return nota.dt_emissao
    return nota.dt_entrada_saida


def para_data(valor):
    """date/'aaaa-mm-dd'/None -> date ou None (formato dos <input type=date>)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def tem_periodo(de=None, ate=None) -> bool:
    """True se ao menos um limite (inicio ou fim) esta definido."""
    return para_data(de) is not None or para_data(ate) is not None


def no_periodo(nota: NotaFiscal, de=None, ate=None,
               base: str = BASE_ESCRITURACAO) -> bool:
    """True se a nota cai em [de, ate] (limites inclusivos) na base escolhida.

    Sem nenhum limite, toda nota passa. Com limite, nota sem a data escolhida
    e considerada FORA do periodo.
    """
    ini = para_data(de)
    fim = para_data(ate)
    if ini is None and fim is None:
        return True
    d = data_base(nota, base)
    if d is None:
        return False
    if isinstance(d, datetime):
        d = d.date()
    if ini is not None and d < ini:
        return False
    if fim is not None and d > fim:
        return False
    return True


def filtrar_por_periodo(notas, de=None, ate=None,
                        base: str = BASE_ESCRITURACAO):
    """Copia da lista contendo apenas as notas dentro do periodo."""
    base = normalizar_base(base)
    if not tem_periodo(de, ate):
        return list(notas)
    return [n for n in notas if no_periodo(n, de, ate, base)]


def chaves_no_periodo(notas, de=None, ate=None,
                      base: str = BASE_ESCRITURACAO) -> set[str]:
    """Chaves normalizadas das notas dentro do periodo (para filtrar correcoes).

    Sem periodo ativo, devolve None: o chamador entende como "sem restricao"
    e nao precisa filtrar nada.
    """
    if not tem_periodo(de, ate):
        return None
    base = normalizar_base(base)
    return {n.chave_normalizada for n in notas
            if no_periodo(n, de, ate, base)}
