"""Qualidade: persistência aditiva, eventos, concorrência e integridade sintéticas."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas.clientes_store import ClientesStore, ConcorrenciaError
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.ferramentas.qualidade_store import QualidadeStore
from auditoria_fiscal.ferramentas import qualidade_store as modulo_qualidade

QUEM = dict(usuario_id=1, usuario_login='qa_sintetico')
AGORA = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)


def recusa(fn, *args, tipo=ValueError, **kwargs):
    try:
        fn(*args, **kwargs)
    except tipo:
        return
    raise AssertionError(f'{fn.__name__}: deveria recusar')


def main():
    # Falha durante o schema novo não pode deixar tabelas pela metade.
    with tempfile.TemporaryDirectory(prefix='qa_migracao_qualidade_') as pasta:
        db = str(Path(pasta) / 'clientes.db')
        legado = TarefasStore(db)
        legado.fechar()
        with patch.object(modulo_qualidade, '_SCHEMA', modulo_qualidade._SCHEMA + '\nINVALID SQL;'):
            recusa(QualidadeStore, db, tipo=sqlite3.OperationalError)
        conn = sqlite3.connect(db)
        try:
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
            assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'qualidade_%'").fetchall(), 'Migração parcial permaneceu após falha'
        finally:
            conn.close()
        nova = QualidadeStore(db)
        nova.fechar()
    with tempfile.TemporaryDirectory(prefix='qa_qualidade_') as pasta:
        db = str(Path(pasta) / 'clientes.db')
        antigo = TarefasStore(db)
        cid = antigo.criar_cliente({'nome': 'Empresa sintética de qualidade'}, **QUEM)
        outro = antigo.criar_cliente({'nome': 'Outra empresa sintética'}, **QUEM)
        sid = antigo.salvar_setor({'nome': 'Setor sintético', 'responsavel_usuario_id': 1,
                                  'membros': [1, 2]}, **QUEM)['id']
        tarefa = antigo.criar_avulsa({'cliente_id': cid, 'setor_id': sid,
            'responsavel_usuario_id': 1, 'titulo': 'Tarefa sintética',
            'inicio': '2026-10-01', 'vencimento': '2026-10-30'}, **QUEM)
        snapshot = [tuple(r) for r in antigo.conn.execute('SELECT * FROM cliente')]
        antigo.fechar()
        s = QualidadeStore(db, usuario_ativo=lambda uid: uid in {1, 2, 3}, agora_fn=lambda: AGORA)
        try:
            assert s.conn.execute('PRAGMA user_version').fetchone()[0] == 4
            assert [tuple(r) for r in s.conn.execute('SELECT * FROM cliente')] == snapshot
            dados = {'data': '2026-10-29', 'cliente_id': cid, 'setor_id': sid,
                'responsavel_usuario_id': 2, 'tarefa_id': tarefa['id'], 'tipo': 'nao_conformidade',
                'descricao': 'Ocorrência inteiramente fictícia', 'criticidade': 'alta',
                'prazo': '2026-11-02'}
            for troca in [{'responsavel_usuario_id': 3}, {'cliente_id': outro},
                          {'tipo': 'inventado'}, {'prazo': '2026-10-01'}, {'revision': 999}]:
                recusa(s.criar_ocorrencia, {**dados, **troca}, **QUEM)
            o = s.criar_ocorrencia(dados, **QUEM)
            assert o['revision'] == 1 and o['situacao'] == 'aberta'
            assert o['cliente_nome'] == 'Empresa sintética de qualidade'
            assert len(o['historico']) == 1 and o['historico'][0]['usuario_id'] == 1
            recusa(s.editar_ocorrencia, o['id'], {'descricao': 'Não pode'}, 99,
                   tipo=ConcorrenciaError, **QUEM)
            o = s.editar_ocorrencia(o['id'], {'descricao': 'Descrição revisada'}, 1, **QUEM)
            assert o['revision'] == 2 and len(o['historico']) == 2
            p = s.criar_plano({'ocorrencia_id': o['id'], 'causa': 'Causa sintética',
                'descricao': 'Revisar procedimento', 'tipo': 'corretiva',
                'responsavel_usuario_id': 1, 'prazo': '2026-11-02'}, **QUEM)
            assert p['cliente_id'] == cid and p['setor_id'] == sid
            recusa(s.transicionar_ocorrencia, o['id'], 'resolvida', 'Sem corrigir plano', o['revision'], **QUEM)
            recusa(s.transicionar_plano, p['id'], 'validado', 'Atalho indevido', p['revision'], **QUEM)
            p = s.transicionar_plano(p['id'], 'em_andamento', '', p['revision'], **QUEM)
            p = s.transicionar_plano(p['id'], 'aguardando_validacao', 'Evidência sintética', p['revision'], **QUEM)
            recusa(s.transicionar_plano, p['id'], 'em_andamento', '', p['revision'], **QUEM)
            p = s.transicionar_plano(p['id'], 'validado', 'Solução conferida', p['revision'], **QUEM)
            assert p['validado_em'] and p['validado_por'] == 1
            recusa(s.editar_plano, p['id'], {'descricao': 'Mudar validado'}, p['revision'], **QUEM)
            o = s.obter_ocorrencia(o['id'])
            o = s.transicionar_ocorrencia(o['id'], 'resolvida', 'Problema resolvido', o['revision'], **QUEM)
            assert o['resolvida_em']
            o = s.transicionar_ocorrencia(o['id'], 'em_tratamento', 'Reabrir para revisar', o['revision'], **QUEM)
            assert not o['resolvida_em']
            o = s.comentar_ocorrencia(o['id'], 'Comentário rastreável', o['revision'], **QUEM)
            assert o['historico'][-1]['comentario'] == 'Comentário rastreável'
            metadados = dict(nome='evidencia-sintetica.pdf', mime='application/pdf', tamanho=1024,
                             sha256='a' * 64, chave_objeto='qualidade/objeto-sintetico')
            anexo = s.registrar_anexo('ocorrencia', o['id'], metadados, **QUEM)
            assert s.obter_anexo(anexo['id'])['sha256'] == 'a' * 64
            assert s.obter_ocorrencia(o['id'])['anexos'][0]['id'] == anexo['id']
            for troca in [{'nome': '../escape.pdf'}, {'chave_objeto': '../escape'},
                          {'mime': 'text/html'}, {'sha256': 'x'}, {'tamanho': 0}]:
                recusa(s.registrar_anexo, 'ocorrencia', o['id'], {**metadados, **troca}, **QUEM)
            h = s.registrar_horas({'cliente_id': cid, 'setor_id': sid, 'tarefa_id': tarefa['id'],
                'ocorrencia_id': o['id'], 'data': '2026-10-30', 'minutos': 1,
                'descricao': 'Atendimento sintético', 'custo_hora': '100.00'}, **QUEM)
            assert h['custo_total'] == '1.67' and h['responsavel_usuario_id'] == 1
            sem_custo = s.registrar_horas({'cliente_id': cid, 'setor_id': sid, 'data': '2026-10-29',
                'minutos': 60, 'descricao': 'Sem custo informado'}, **QUEM)
            assert sem_custo['custo_total'] is None and sem_custo['custo_hora'] is None
            recusa(s.registrar_horas, {'cliente_id': cid, 'setor_id': sid, 'data': '2026-10-30',
                'minutos': 1440, 'descricao': 'Estoura o dia'}, **QUEM)
            recusa(s.registrar_horas, {'cliente_id': cid, 'setor_id': sid, 'data': '2026-10-31',
                'minutos': 1, 'descricao': 'Tempo futuro'}, **QUEM)
            h = s.cancelar_horas(h['id'], 'Lançamento sintético duplicado', h['revision'], **QUEM)
            assert h['cancelado'] and h['custo_total'] == '1.67'
            recusa(s.cancelar_horas, h['id'], 'De novo', h['revision'], **QUEM)
            assert len(s.listar_ocorrencias({'cliente_id': cid, 'de': '2026-10-29', 'ate': '2026-10-29'})) == 1
            assert not s.listar_ocorrencias({'cliente_id': outro})
            recusa(s.listar_ocorrencias, {'de': '2026-11-01', 'ate': '2026-10-01'})
            for tabela in ['qualidade_evento', 'qualidade_anexo']:
                for operacao in [f'UPDATE {tabela} SET id=id', f'DELETE FROM {tabela}']:
                    recusa(s.conn.execute, operacao, tipo=sqlite3.IntegrityError)
            recusa(s.conn.execute, 'UPDATE qualidade_horas SET minutos=10', tipo=sqlite3.IntegrityError)
            for tabela in ['qualidade_ocorrencia', 'qualidade_plano', 'qualidade_horas']:
                recusa(s.conn.execute, f'DELETE FROM {tabela}', tipo=sqlite3.IntegrityError)
            # Falha no evento desfaz a mutação; transação externa permanece aberta.
            antes = s.obter_ocorrencia(o['id'])
            original = s._evento_qualidade
            def falhar(*args, **kwargs):
                raise RuntimeError('Falha sintética no evento')
            s._evento_qualidade = falhar
            recusa(s.editar_ocorrencia, o['id'], {'descricao': 'Não persistir'}, antes['revision'],
                   tipo=RuntimeError, **QUEM)
            s._evento_qualidade = original
            assert s.obter_ocorrencia(o['id']) == antes
            s.conn.execute('BEGIN IMMEDIATE')
            s.editar_ocorrencia(o['id'], {'descricao': 'Rollback externo'}, antes['revision'], **QUEM)
            assert s.conn.in_transaction
            s.conn.rollback()
            assert s.obter_ocorrencia(o['id']) == antes
            assert s.conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not s.conn.execute('PRAGMA foreign_key_check').fetchall()
        finally:
            s.fechar()
        # Reabrir pelo legado não rebaixa schema nem perde os registros novos.
        legado = TarefasStore(db)
        assert legado.conn.execute('PRAGMA user_version').fetchone()[0] == 4
        legado.fechar()
        s = QualidadeStore(db)
        assert len(s.listar_ocorrencias()) == 1 and len(s.listar_planos()) == 1
        assert len(s.listar_horas()) == 2
        s.fechar()
        # Dois editores reais em conexões diferentes: apenas uma revisão vence.
        barreira = Barrier(2)
        revision = antes['revision']
        def editar_concorrente(texto):
            local = QualidadeStore(db, agora_fn=lambda: AGORA)
            try:
                barreira.wait(timeout=10)
                try:
                    local.editar_ocorrencia(o['id'], {'descricao': texto}, revision, **QUEM)
                    return 'ok'
                except ConcorrenciaError:
                    return 'conflito'
            finally:
                local.fechar()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(editar_concorrente, ['Primeiro editor sintético', 'Segundo editor sintético']))
        assert sorted(resultados) == ['conflito', 'ok']
        barreira = Barrier(2)
        def horas_concorrentes(minutos):
            local = QualidadeStore(db, agora_fn=lambda: AGORA)
            try:
                barreira.wait(timeout=10)
                try:
                    local.registrar_horas({'cliente_id': cid, 'setor_id': sid,
                        'data': '2026-10-28', 'minutos': minutos,
                        'descricao': 'Apontamento concorrente sintético'}, **QUEM)
                    return 'ok'
                except ValueError:
                    return 'limite'
            finally:
                local.fechar()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(horas_concorrentes, [600, 900]))
        assert sorted(resultados) == ['limite', 'ok']
        s = QualidadeStore(db)
        try:
            assert sum(h['minutos'] for h in s.listar_horas({'de': '2026-10-28', 'ate': '2026-10-28'})) <= 1440
            # Comentário opcional null não causa erro de atributo/HTTP 500.
            novo = s.criar_ocorrencia(dict(dados, descricao='Transição sintética com null'), **QUEM)
            novo = s.transicionar_ocorrencia(novo['id'], 'em_tratamento', None, novo['revision'], **QUEM)
            assert novo['historico'][-1]['comentario'] == ''
            plano = s.criar_plano({'ocorrencia_id': novo['id'], 'causa': 'Causa sintética',
                'descricao': 'Plano sintético com null', 'tipo': 'corretiva',
                'responsavel_usuario_id': 1, 'prazo': '2026-11-02'}, **QUEM)
            plano = s.transicionar_plano(plano['id'], 'em_andamento', None, plano['revision'], **QUEM)
            assert plano['historico'][-1]['comentario'] == ''
        finally:
            s.fechar()
    print('OK - qualidade store: schema aditivo, fluxo, moeda, eventos imutáveis e rollback')


if __name__ == '__main__':
    main()
