"""Regras puras da qualidade: valores, moeda e transições sintéticas."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.core import qualidade as q


def recusa(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError('Entrada inválida aceita')


def main():
    assert q.custo('100.00', 1) == ('100.00', '1.67')
    assert q.custo('0', 1440) == ('0.00', '0.00')
    assert q.custo(None, 60) == (None, None)
    for valor in ['NaN', 'Infinity', '-1', '1.001', '1000001', True, 1.2, '1,50']:
        recusa(q.custo, valor, 60)
    for minutos in [0, -1, 1441, True, 1.5, '60']:
        recusa(q.minutos, minutos)
    assert q.data('2026-10-30') == '2026-10-30'
    for valor in ['2026-02-30', '30/10/2026', '2026-1-1', True]:
        recusa(q.data, valor)
    for entidade, origem, destino in [('ocorrencia', 'aberta', 'em_tratamento'),
                                      ('ocorrencia', 'em_tratamento', 'resolvida'),
                                      ('plano', 'aberto', 'em_andamento'),
                                      ('plano', 'aguardando_validacao', 'validado')]:
        assert q.transicao(entidade, origem, destino, 'Conferência sintética') == destino
    for entidade, origem, destino, comentario in [
        ('ocorrencia', 'aberta', 'encerrada', 'Motivo'),
        ('ocorrencia', 'resolvida', 'em_tratamento', ''),
        ('plano', 'aberto', 'validado', 'Motivo'),
        ('plano', 'aguardando_validacao', 'em_andamento', ''),
        ('plano', 'validado', 'em_andamento', 'Motivo'),
    ]:
        recusa(q.transicao, entidade, origem, destino, comentario)
    for destino in [None, [], {}, True, 1]:
        recusa(q.transicao, 'ocorrencia', 'aberta', destino, '')
    assert q.texto('  Texto sintético  ', 'Descrição') == 'Texto sintético'
    recusa(q.texto, '', 'Descrição')
    recusa(q.texto, 'a' * 6001, 'Descrição')
    print('OK - qualidade: transições, datas, minutos e moeda Decimal')


if __name__ == '__main__':
    main()
