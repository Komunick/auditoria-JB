"""Regras puras da gestão da qualidade; sem dependência de interfaces ou banco."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

TIPOS = {
    'erro': 'Erro no serviço', 'atraso': 'Obrigação fora do prazo',
    'comunicacao': 'Falha de comunicação', 'reclamacao': 'Reclamação do cliente',
    'retrabalho': 'Retrabalho', 'pendencia': 'Pendência não solucionada',
    'procedimento': 'Descumprimento de procedimento', 'nao_conformidade': 'Não conformidade',
}
CRITICIDADES = {'baixa': 'Baixa', 'media': 'Média', 'alta': 'Alta', 'critica': 'Crítica'}
TIPOS_PLANO = {'corretiva': 'Corretiva', 'preventiva': 'Preventiva'}
SITUACOES_OCORRENCIA = {'aberta': 'Aberta', 'em_tratamento': 'Em tratamento',
                       'resolvida': 'Resolvida', 'encerrada': 'Encerrada pela gestão'}
SITUACOES_PLANO = {'aberto': 'Aberto', 'em_andamento': 'Em andamento',
                  'aguardando_validacao': 'Aguardando validação', 'validado': 'Validado'}
TRANSICOES = {
    'ocorrencia': {'aberta': {'em_tratamento', 'resolvida'},
                   'em_tratamento': {'resolvida'},
                   'resolvida': {'em_tratamento', 'encerrada'}, 'encerrada': set()},
    'plano': {'aberto': {'em_andamento', 'aguardando_validacao'},
              'em_andamento': {'aguardando_validacao'},
              'aguardando_validacao': {'em_andamento', 'validado'}, 'validado': set()},
}


def texto(valor, rotulo, limite=6000, *, opcional=False):
    if valor is None and opcional:
        return ''
    if not isinstance(valor, str):
        raise ValueError(f'{rotulo} deve ser texto.')
    valor = valor.strip()
    if (not valor and not opcional) or len(valor) > limite or '\x00' in valor:
        raise ValueError(f'{rotulo} deve ter de {0 if opcional else 1} a {limite} caracteres.')
    return valor


def identificador(valor, *, opcional=False):
    if valor is None and opcional:
        return None
    if type(valor) is not int or valor < 1:
        raise ValueError('Identificador deve ser inteiro positivo.')
    return valor


def data(valor):
    if not isinstance(valor, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', valor):
        raise ValueError('Informe data no formato AAAA-MM-DD.')
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError as exc:
        raise ValueError('Informe uma data válida.') from exc


def escolha(valor, catalogo, rotulo):
    if not isinstance(valor, str) or valor not in catalogo:
        raise ValueError(f'{rotulo} inválido.')
    return valor


def campos(dados, permitidos):
    if not isinstance(dados, dict) or set(dados) - set(permitidos):
        raise ValueError('Campos não permitidos para esta operação.')


def minutos(valor):
    if type(valor) is not int or not 1 <= valor <= 1440:
        raise ValueError('Informe de 1 a 1440 minutos inteiros.')
    return valor


def custo(valor, duracao):
    minutos(duracao)
    if valor is None or valor == '':
        return None, None
    if isinstance(valor, bool) or isinstance(valor, float) or not isinstance(valor, (str, int, Decimal)):
        raise ValueError('Informe custo/hora como valor decimal.')
    try:
        numero = Decimal(valor)
        if not numero.is_finite() or numero < 0 or numero > Decimal('1000000'):
            raise ValueError()
        arredondado = numero.quantize(Decimal('.01'))
        if arredondado != numero:
            raise ValueError()
        total = (numero * Decimal(duracao) / Decimal(60)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        return format(arredondado, '.2f'), format(total, '.2f')
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError('Custo/hora deve ser finito, não negativo e ter até duas casas decimais.') from exc


def transicao(entidade, origem, destino, comentario):
    if (not all(isinstance(v, str) for v in (entidade, origem, destino))
            or destino not in TRANSICOES.get(entidade, {}).get(origem, set())):
        raise ValueError('Transição não permitida para a situação atual.')
    exige = destino in {'resolvida', 'encerrada', 'aguardando_validacao', 'validado'} or (
        origem in {'resolvida', 'aguardando_validacao'})
    texto(comentario, 'Comentário', opcional=not exige)
    return destino
