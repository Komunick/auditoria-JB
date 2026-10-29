"""Central operacional: contagens completas e snapshot, apenas dados sinteticos."""
import os
from pathlib import Path
import sys
import tempfile
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.core.tarefas import ErroTarefas

HOJE = date(2026, 10, 28)


def montar(s, usuarios=None):
    us = usuarios or dict(pessoa=1, outra=2, chefe=3, externo=4, substituto=5)
    cid = s.criar_cliente({'nome': 'Empresa Sintetica Central'})
    outro = s.criar_cliente({'nome': 'Empresa Sintetica Restrita'})
    sid = s.salvar_setor(dict(nome='Setor Sintetico Central', responsavel_usuario_id=us['chefe'],
                             membros=[us['pessoa'], us['outra'], us['chefe'], us['substituto']]))['id']
    separado = s.salvar_setor(dict(nome='Setor Sintetico Restrito', responsavel_usuario_id=us['externo'],
                                  membros=[us['externo']]))['id']
    linhas = [
        ('a_fazer', '2026-10-27', us['pessoa'], False, '2026-09'),
        ('em_andamento', '2026-10-28', us['pessoa'], False, '2026-10'),
        ('aguardando_cliente', '2026-10-31', us['pessoa'], False, '2026-10'),
        ('a_fazer', '2026-11-01', us['outra'], False, '2026-10'),
        ('aguardando_cliente', '', None, False, '2026-10'),
        ('concluida', '2026-10-01', us['pessoa'], True, '2026-10'),
        ('concluida', '2026-10-01', us['outra'], False, '2026-10'),
        ('conferida', '2026-10-01', us['outra'], True, '2026-10'),
        ('dispensada', '2026-10-01', us['outra'], False, '2026-10'),
        ('devolvida', '', us['pessoa'], True, '2026-10'),
        ('concluida', '', None, True, '2026-10'),
    ]
    ids = []
    def gravar(conn):
        for numero, (situacao, vencimento, responsavel, conferencia, competencia) in enumerate(linhas, 1):
            tid = s._inserir_tarefa(dict(cliente_id=cid, setor_id=sid, titulo=f'Rotina sintetica {numero:02}',
                inicio='2026-10-01', vencimento=vencimento, responsavel_usuario_id=responsavel,
                competencia=competencia, exige_conferencia=conferencia), 0, 'fixture_sintetica')
            conn.execute('UPDATE tarefa SET situacao=?,fora_do_prazo=? WHERE id=?',
                         (situacao, int(numero == 7), tid))
            ids.append(tid)
        secreto = s._inserir_tarefa(dict(cliente_id=outro, setor_id=separado, titulo='Rotina restrita',
            inicio='2026-10-01', vencimento='2026-10-01', responsavel_usuario_id=us['externo'],
            competencia='2026-10'), 0, 'fixture_sintetica')
        return secreto
    secreto = s._transacao(gravar)
    return dict(cliente=cid, setor=sid, separado=separado, ids=ids, secreto=secreto, usuarios=us)


def main():
    with tempfile.TemporaryDirectory(prefix='painel_sintetico_') as pasta:
        banco = os.path.join(pasta, 'clientes.db')
        s = TarefasStore(banco)
        outro = None
        try:
            f = montar(s)
            escopo = dict(escopo_setores=[f['setor']], hoje=HOJE)
            chamadas = []
            original = s._tarefa_dict
            def dto(row, hoje=None):
                chamadas.append(row['id'])
                return original(row, hoje)
            s._tarefa_dict = dto
            p = s.painel_tarefas(limite=2, **escopo)
            assert p['resumo'] == dict(total=11, por_situacao=dict(a_fazer=2, em_andamento=1,
                aguardando_cliente=2, concluida=3, conferida=1, devolvida=1, dispensada=1),
                abertas=6, pendentes=8, atrasadas=1, vencendo_hoje=1, proximas=1,
                pendentes_conferencia=2, aguardando_cliente=2, sem_vencimento=3, sem_responsavel=2)
            assert p['fila']['total'] == 8 and len(p['fila']['itens']) == 2
            assert chamadas == f['ids'][:2], 'So a pagina deve montar DTO; atrasada/hoje primeiro'
            assert sum(x['total'] for x in p['por_responsavel']) == 11
            assert s.conn.in_transaction is False
            esperado = dict(todas=11, pendentes=8, atrasadas=1, hoje=1, proximas=1,
                            aguardando_cliente=2, conferencia=2, sem_vencimento=3, sem_responsavel=2)
            for fila, total in esperado.items():
                painel = s.painel_tarefas(fila=fila, limite=200, **escopo)
                assert painel['resumo'] == p['resumo'], fila
                assert painel['fila']['total'] == total, fila
                lista = s.listar_tarefas({'fila': fila}, **escopo)
                assert lista['total'] == total, fila
                assert {t['id'] for t in lista['itens']} == {t['id'] for t in painel['fila']['itens']}, fila
            assert s.painel_tarefas({'competencia':'2026-10'}, **escopo)['resumo']['atrasadas'] == 0
            assert s.painel_tarefas({'texto':'  01  '}, **escopo)['resumo']['total'] == 1
            assert s.painel_tarefas({'texto':'%'}, **escopo)['resumo']['total'] == 0
            assert s.painel_tarefas({'cliente_id':f['cliente']}, **escopo)['resumo']['total'] == 11
            assert s.painel_tarefas({'vencimento_ate':'2099-01-01'}, **escopo)['resumo']['total'] == 8
            assert s.listar_tarefas({'abertas':True}, **escopo)['total'] == 8
            assert s.listar_tarefas({'pendente_conferencia':True}, **escopo)['total'] == 2
            assert s.painel_tarefas(hoje=HOJE)['resumo']['total'] == 0
            for argumentos in ({'fila':'inventada'}, {'limite':201}, {'pagina':0}, {'filtros':{'texto':'a'*201}}):
                try: s.painel_tarefas(**argumentos, **escopo)
                except (ErroTarefas, ValueError): pass
                else: raise AssertionError(argumentos)
            us=f['usuarios']
            s.criar_substituicao(dict(titular_usuario_id=us['pessoa'], substituto_usuario_id=us['substituto'],
                setor_id=f['setor'], inicio=HOJE.isoformat(), fim=HOJE.isoformat(), motivo='Ausencia sintetica'))
            assert s.painel_tarefas(hoje=HOJE, escopo_usuario_id=us['pessoa'])['resumo']['total'] == 0
            sub=s.painel_tarefas(hoje=HOJE, escopo_usuario_id=us['substituto'])
            assert sub['resumo']['total'] == 5 and {r['id'] for r in sub['por_responsavel']} == {us['substituto']}
            assert s.painel_tarefas({'responsavel_usuario_id':us['substituto']}, **escopo)['resumo']['total'] == 5
            # Escrita concorrente apos comecar a agregacao nao divide resumo e fila.
            outro = TarefasStore(banco)
            mudou = []
            def observar(sql):
                if not mudou and 'SUM(' in sql.upper():
                    mudou.append(True)
                    outro.conn.execute("UPDATE tarefa SET situacao='dispensada' WHERE id=?", (f['ids'][0],))
            s.conn.set_trace_callback(observar)
            snapshot = s.painel_tarefas(fila='atrasadas', **escopo)
            s.conn.set_trace_callback(None)
            assert mudou and snapshot['resumo']['atrasadas'] == snapshot['fila']['total'] == 1
            assert s.painel_tarefas(fila='atrasadas', **escopo)['resumo']['atrasadas'] == 0
            print('OK - painel SQL: escopo, totais, filas, filtros, substituicao e snapshot')
        finally:
            if outro: outro.fechar()
            s.fechar()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
