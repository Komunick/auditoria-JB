"""Reativacao e prazo individual: dados sinteticos, autorizacao e historico."""
from __future__ import annotations

import concurrent.futures
from datetime import date, datetime, timezone
import gc
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.core import tarefas as regras
from auditoria_fiscal.ferramentas.clientes_store import ConcorrenciaError
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore

HOJE = date(2026, 11, 4)
QUEM = dict(usuario_id=1, usuario_login='gestor_sintetico')


class RegrasTest(unittest.TestCase):
    def test_reativar_exige_dispensa_gestor_e_motivo(self):
        self.assertEqual(regras.validar_transicao('dispensada', 'a_fazer', motivo='Engano', responsavel_setor=True), 'a_fazer')
        for atual, nova, motivo, gestor in (
                ('dispensada', 'a_fazer', '', True), ('dispensada', 'a_fazer', 'Engano', False),
                ('dispensada', 'em_andamento', 'Engano', True), ('concluida', 'a_fazer', 'Engano', True),
                ('conferida', 'a_fazer', 'Engano', True), ('em_andamento', 'a_fazer', 'Engano', True)):
            with self.subTest(atual=atual, nova=nova, motivo=motivo, gestor=gestor), self.assertRaises(regras.ErroTarefas):
                regras.validar_transicao(atual, nova, motivo=motivo, responsavel_setor=gestor)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='prazo_tarefa_sintetico_')
        self.db = str(Path(self.tmp.name) / 'clientes.db')
        self.s = TarefasStore(self.db, usuario_ativo=lambda _: True,
                             agora_fn=lambda: datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
        self.cid = self.s.criar_cliente({'nome': 'Empresa ficticia'}, **QUEM)
        self.sid = self.s.salvar_setor({'nome': 'Fiscal ficticio', 'responsavel_usuario_id': 1, 'membros': [1, 2]}, **QUEM)['id']
        self.t = self.s.criar_avulsa(dict(cliente_id=self.cid, setor_id=self.sid, titulo='Prazo ficticio',
            responsavel_usuario_id=2, inicio='2026-11-01', vencimento='2026-11-10', exige_conferencia=True), **QUEM)

    def tearDown(self):
        self.s.fechar()
        self.tmp.cleanup()

    def test_reativar_preserva_dados_eventos_e_revision(self):
        antiga = self.s.obter_tarefa(self.t['id'])
        eventos = self.s.eventos(self.t['id'])
        dispensada = self.s.mudar_situacao(self.t['id'], 'dispensada', antiga['revision'],
            motivo='Dispensa por engano', responsavel_setor=True, **QUEM)
        nova = self.s.mudar_situacao(self.t['id'], 'a_fazer', dispensada['revision'],
            motivo='Retomar obrigacao', responsavel_setor=True, **QUEM)
        self.assertEqual(nova['situacao'], 'a_fazer')
        self.assertEqual(nova['revision'], antiga['revision'] + 2)
        for campo in ('id', 'origem', 'inicio', 'vencimento', 'responsavel_usuario_id', 'competencia', 'ocorrencia'):
            self.assertEqual(nova[campo], antiga[campo], campo)
        trilha = self.s.eventos(nova['id'])
        self.assertEqual(trilha[:len(eventos)], eventos)
        self.assertEqual((trilha[-1]['de'], trilha[-1]['para'], trilha[-1]['comentario'], trilha[-1]['usuario_id']),
                         ('dispensada', 'a_fazer', 'Retomar obrigacao', 1))
        with self.assertRaises(ConcorrenciaError):
            self.s.mudar_situacao(nova['id'], 'a_fazer', dispensada['revision'], motivo='Repeticao', responsavel_setor=True, **QUEM)
        self.assertEqual(self.s.eventos(nova['id']), trilha)
        with self.assertRaises(sqlite3.IntegrityError):
            self.s.conn.execute('UPDATE tarefa_evento SET comentario=? WHERE id=?', ('Apagar rastreio', trilha[-1]['id']))
        self.s.conn.rollback()

    def test_prazo_gerado_nao_altera_regra_ou_outra_tarefa(self):
        self.s.definir_carteira(self.cid, self.sid, 2, **QUEM)
        obrigacao = self.s.salvar_obrigacao(dict(nome='Obrigacao ficticia', setor_id=self.sid,
            regra_vencimento=dict(tipo='dia_mes_seguinte', dia=20, inicio_dia=1, sem_expediente='manter')), **QUEM)
        gerada = self.s.gerar('2026-11', setor_id=self.sid, hoje=HOJE, **QUEM)['tarefas'][0]
        tarefa = self.s.obter_tarefa(gerada['id'])
        avulsa = self.s.obter_tarefa(self.t['id'])
        eventos = self.s.eventos(tarefa['id'])
        nova = self.s.alterar_vencimento(tarefa['id'], '2026-12-22', tarefa['revision'], 'Ajuste pontual', **QUEM)
        self.assertEqual(nova['vencimento'], '2026-12-22')
        self.assertEqual(nova['revision'], tarefa['revision'] + 1)
        for campo in ('inicio', 'origem', 'competencia', 'obrigacao_id', 'responsavel_usuario_id', 'situacao', 'fora_do_prazo'):
            self.assertEqual(nova[campo], tarefa[campo], campo)
        self.assertEqual(self.s.obter_tarefa(self.t['id']), avulsa)
        self.assertEqual(self.s.listar_obrigacoes()[0], obrigacao)
        proxima = self.s.previa_geracao('2026-12', setor_id=self.sid, hoje=HOJE)['tarefas'][0]
        self.assertEqual(proxima['vencimento'], '2027-01-20')
        self.assertEqual(self.s.previa_geracao('2026-11', setor_id=self.sid, hoje=HOJE)['contagens']['novas'], 0)
        trilha = self.s.eventos(tarefa['id'])
        self.assertEqual(trilha[:-1], eventos)
        self.assertEqual((trilha[-1]['tipo'], trilha[-1]['de'], trilha[-1]['para'], trilha[-1]['comentario']),
                         ('vencimento', '2026-12-20', '2026-12-22', 'Ajuste pontual'))

    def test_prazo_invalido_e_tarefa_fechada_nao_gravam(self):
        for data, motivo in (('', 'Remover'), (None, 'Remover'), ('2026-02-30', 'Invalido'),
                ('2026-10-31', 'Antes do inicio'), ('2026-11-10', 'Sem mudanca'), ('2026-11-11', ''),
                ('2026-11-11', 'x' * 4001)):
            antes = self.s.obter_tarefa(self.t['id'])
            eventos = self.s.eventos(self.t['id'])
            with self.subTest(data=data, motivo=motivo[:20]), self.assertRaises(regras.ErroTarefas):
                self.s.alterar_vencimento(self.t['id'], data, antes['revision'], motivo, **QUEM)
            self.assertEqual(self.s.obter_tarefa(self.t['id']), antes)
            self.assertEqual(self.s.eventos(self.t['id']), eventos)
        for estado in ('dispensada', 'concluida', 'conferida'):
            with self.subTest(estado=estado):
                t = self.s.criar_avulsa(dict(cliente_id=self.cid, setor_id=self.sid, titulo='Fechada '+estado,
                    inicio='2026-11-01', vencimento='2026-11-10', exige_conferencia=True), **QUEM)
                passos = ['dispensada'] if estado == 'dispensada' else ['em_andamento', 'concluida'] + (['conferida'] if estado == 'conferida' else [])
                for passo in passos:
                    t = self.s.mudar_situacao(t['id'], passo, t['revision'], motivo='Fixture', responsavel_setor=True, **QUEM)
                with self.assertRaises(regras.ErroTarefas):
                    self.s.alterar_vencimento(t['id'], '2026-11-20', t['revision'], 'Nao mascarar atraso', **QUEM)

    def test_rollback_se_evento_falhar_e_concorrencia(self):
        self.s.conn.execute("CREATE TRIGGER rejeitar_prazo BEFORE INSERT ON tarefa_evento WHEN NEW.tipo='vencimento' BEGIN SELECT RAISE(ABORT,'Falha sintetica'); END")
        with self.assertRaises(regras.ErroTarefas):
            self.s.alterar_vencimento(self.t['id'], '2026-11-12', 1, 'Teste atomico', **QUEM)
        self.assertEqual(self.s.obter_tarefa(self.t['id']), self.t)
        self.assertEqual(len(self.s.eventos(self.t['id'])), 1)
        self.s.conn.execute('DROP TRIGGER rejeitar_prazo')
        barreira = threading.Barrier(2)
        def alterar(dia):
            s = TarefasStore(self.db, usuario_ativo=lambda _: True)
            try:
                barreira.wait(timeout=5)
                try:
                    s.alterar_vencimento(self.t['id'], dia, 1, 'Concorrente', **QUEM)
                    return 'salvou'
                except ConcorrenciaError:
                    return 'conflito'
            finally:
                s.fechar()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(alterar, ['2026-11-12', '2026-11-13'])), ['conflito', 'salvou'])
        self.assertEqual(len(self.s.eventos(self.t['id'])), 2)

    def test_prazo_ausente_e_atraso_historico_preservado(self):
        self.s.definir_carteira(self.cid, self.sid, 2, **QUEM)
        self.s.salvar_obrigacao(dict(nome='Rotina sem prazo', setor_id=self.sid,
            regra_vencimento={'tipo': 'sem_vencimento'}), **QUEM)
        gerada = self.s.gerar('2026-11', setor_id=self.sid, hoje=HOJE, **QUEM)['tarefas'][0]
        sem = self.s.obter_tarefa(gerada['id'])
        self.assertEqual(sem['vencimento'], '')
        nova = self.s.alterar_vencimento(sem['id'], '2026-12-22', sem['revision'], 'Prazo desta ocorrencia', **QUEM)
        self.assertEqual(nova['origem'], sem['origem'])
        self.assertEqual(self.s.eventos(sem['id'])[-1]['de'], '')
        t = self.s.mudar_situacao(self.t['id'], 'em_andamento', 1, **QUEM)
        t = self.s.mudar_situacao(t['id'], 'concluida', t['revision'], hoje=date(2026, 11, 12), **QUEM)
        self.assertTrue(t['fora_do_prazo'])
        for estado in ('devolvida', 'dispensada', 'a_fazer'):
            t = self.s.mudar_situacao(t['id'], estado, t['revision'], motivo='Correcao ficticia', responsavel_setor=True, **QUEM)
        t = self.s.alterar_vencimento(t['id'], '2026-11-30', t['revision'], 'Nova entrega', **QUEM)
        self.assertTrue(t['fora_do_prazo'])
        self.assertEqual(t['cor'], 'vermelho')
        self.assertEqual(len([e for e in self.s.eventos(t['id']) if e['para'] == 'concluida']), 1)


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='web_prazo_sintetico_')
        os.environ['AUDITORIA_WEB_DADOS'] = cls.tmp.name
        from fastapi.testclient import TestClient
        from auditoria_fiscal.web import rotas_tarefas
        from auditoria_fiscal.web.servidor import criar_app
        cls.rt = rotas_tarefas
        cls.rt._hoje = lambda: HOJE
        cls.app = criar_app()
        cls.adm = TestClient(cls.app)
        cls.call(cls.adm, 'post', '/api/bootstrap', dict(usuario='admin_ficticio', nome='Admin ficticio', senha='sintetica-123'))
        cls.usuarios = {}
        cls.clientes = {}
        for nome, permissoes in [('gestor', ['aba.tarefas', 'tarefas.setor']),
                ('colab', ['aba.tarefas', 'tarefas.executar']), ('outro', ['aba.tarefas', 'tarefas.setor']),
                ('diretoria', ['aba.tarefas', 'tarefas.todas']), ('substituto', ['aba.tarefas', 'tarefas.setor'])]:
            u = cls.call(cls.adm, 'post', '/api/admin/usuarios', dict(usuario=nome, nome=nome+' ficticio', senha='sintetica-123', permissoes=permissoes))
            cls.usuarios[nome] = u['id']
            c = TestClient(cls.app)
            cls.call(c, 'post', '/api/login', dict(usuario=nome, senha='sintetica-123'))
            cls.clientes[nome] = c
        cls.sid = cls.call(cls.adm, 'post', '/api/tarefas/setores', dict(nome='Fiscal ficticio',
            responsavel_usuario_id=cls.usuarios['gestor'], membros=list(cls.usuarios.values())))['id']
        cls.call(cls.adm, 'post', '/api/tarefas/setores', dict(nome='Outro setor ficticio',
            responsavel_usuario_id=cls.usuarios['outro'], membros=[cls.usuarios['outro']]))
        cls.cid = cls.call(cls.adm, 'post', '/api/clientes', dict(nome='Empresa ficticia HTTP'))['id']

    @classmethod
    def tearDownClass(cls):
        for c in cls.clientes.values():
            c.close()
        cls.adm.close()
        gc.collect()
        cls.tmp.cleanup()

    @staticmethod
    def call(client, method, path, data=None, status=200):
        response = getattr(client, method)(path, **({'json': data} if data is not None else {}))
        assert response.status_code == status, (response.status_code, response.text)
        return response.json() if status == 200 else None

    def setUp(self):
        self.t = self.call(self.adm, 'post', '/api/tarefas/avulsas', dict(cliente_id=self.cid, setor_id=self.sid,
            titulo='Tarefa ficticia HTTP', inicio='2026-11-01', vencimento='2026-11-20', responsavel_usuario_id=self.usuarios['colab']))
        self.url = '/api/tarefas/'+str(self.t['id'])

    def test_permissoes_e_reativacao_sem_permissao_executar(self):
        gestor = self.clientes['gestor']
        dispensada = self.call(gestor, 'post', self.url+'/situacao', dict(situacao='dispensada', revision=1, motivo='Engano'))
        self.assertTrue(dispensada['pode_reativar'])
        self.assertFalse(dispensada['pode_alterar_vencimento'])
        for nome in ('colab', 'outro', 'diretoria'):
            c = self.clientes[nome]
            if nome != 'outro':
                dto = self.call(c, 'get', self.url)
                self.assertFalse(dto['pode_reativar'])
                self.assertFalse(dto['pode_alterar_vencimento'])
            self.call(c, 'post', self.url+'/situacao', dict(situacao='a_fazer', revision=2, motivo='Engano'), status=403)
        self.call(gestor, 'post', self.url+'/situacao', dict(situacao='a_fazer', revision=2), status=422)
        nova = self.call(gestor, 'post', self.url+'/situacao', dict(situacao='a_fazer', revision=2, comentario='Retomar tarefa'))
        self.assertEqual(nova['situacao'], 'a_fazer')
        self.assertFalse(nova['pode_reativar'])
        self.assertTrue(nova['pode_alterar_vencimento'])
        self.call(gestor, 'post', self.url+'/situacao', dict(situacao='a_fazer', revision=2, motivo='Repeticao'), status=409)
        eventos = self.call(gestor, 'get', self.url)['eventos']
        self.assertEqual([(e['de'], e['para']) for e in eventos], [('', 'a_fazer'), ('a_fazer', 'dispensada'), ('dispensada', 'a_fazer')])

    def test_edicao_prazo_validacao_revision_e_escopo(self):
        dados = dict(vencimento='2026-11-23', revision=1, motivo='Ajuste pontual')
        for nome in ('colab', 'outro', 'diretoria'):
            self.call(self.clientes[nome], 'post', self.url+'/vencimento', dados, status=403)
        gestor = self.clientes['gestor']
        for invalido in ({'vencimento': ''}, {'vencimento': '2026-10-31'}, {'motivo': ''}, {'vencimento': '2026-02-30'}, {'revision': True}):
            self.call(gestor, 'post', self.url+'/vencimento', dict(dados, **invalido), status=422)
        nova = self.call(gestor, 'post', self.url+'/vencimento', dados)
        self.assertEqual((nova['vencimento'], nova['revision']), ('2026-11-23', 2))
        self.call(gestor, 'post', self.url+'/vencimento', dados, status=409)
        self.call(gestor, 'post', self.url+'/vencimento', dict(dados, revision=2), status=422)
        trilha = self.call(gestor, 'get', self.url)['eventos']
        self.assertEqual(len(trilha), 2)
        self.assertEqual((trilha[-1]['tipo'], trilha[-1]['de'], trilha[-1]['para']), ('vencimento', '2026-11-20', '2026-11-23'))

    def test_escopo_e_gravacao_compartilham_transacao(self):
        preparada, disparar, tentando, terminou = (threading.Event() for _ in range(4))
        erros = []
        original = TarefasStore.alterar_vencimento
        def revogar_gestao():
            store = None
            try:
                store = self.rt.criar_store()
                preparada.set()
                if not disparar.wait(timeout=5):
                    raise AssertionError('A rota nao chegou a gravacao')
                tentando.set()
                store.salvar_setor(dict(nome='Fiscal ficticio', responsavel_usuario_id=self.usuarios['outro'],
                    membros=list(self.usuarios.values())), id=self.sid, **QUEM)
            except Exception as exc:
                erros.append(exc)
            finally:
                if store:
                    store.fechar()
                terminou.set()
        def gravar_com_disputa(store, *args, **kwargs):
            disparar.set()
            self.assertTrue(tentando.wait(timeout=5))
            self.assertFalse(terminou.wait(timeout=.2), 'A chefia mudou entre autorizacao e escrita')
            return original(store, *args, **kwargs)
        worker = threading.Thread(target=revogar_gestao, daemon=True)
        worker.start()
        try:
            self.assertTrue(preparada.wait(timeout=5), erros)
            TarefasStore.alterar_vencimento = gravar_com_disputa
            nova = self.call(self.clientes['gestor'], 'post', self.url+'/vencimento',
                dict(vencimento='2026-11-25', revision=1, motivo='Correcao antes de trocar chefia'))
            self.assertEqual(nova['vencimento'], '2026-11-25')
        finally:
            TarefasStore.alterar_vencimento = original
            disparar.set()
            worker.join(timeout=10)
        try:
            self.assertFalse(worker.is_alive())
            self.assertEqual(erros, [])
            self.call(self.clientes['gestor'], 'post', self.url+'/vencimento',
                dict(vencimento='2026-11-26', revision=2, motivo='Chefia ja foi alterada'), status=403)
        finally:
            self.call(self.adm, 'put', '/api/tarefas/setores/'+str(self.sid),
                dict(nome='Fiscal ficticio', responsavel_usuario_id=self.usuarios['gestor'], membros=list(self.usuarios.values())))

    def test_substituicao_de_gestor_e_administrador(self):
        self.call(self.adm, 'post', '/api/tarefas/substituicoes', dict(titular_usuario_id=self.usuarios['gestor'],
            substituto_usuario_id=self.usuarios['substituto'], setor_id=self.sid, inicio='2026-11-05', fim='2026-11-05', motivo='Ausencia ficticia'))
        self.rt._hoje = lambda: date(2026, 11, 5)
        try:
            dados = dict(vencimento='2026-11-24', revision=1, motivo='Ajuste durante substituicao')
            self.call(self.clientes['gestor'], 'post', self.url+'/vencimento', dados, status=403)
            self.assertFalse(self.call(self.adm, 'get', self.url)['pode_reativar'])
            nova = self.call(self.clientes['substituto'], 'post', self.url+'/vencimento', dados)
            self.assertTrue(nova['pode_alterar_vencimento'])
            nova = self.call(self.adm, 'post', self.url+'/situacao', dict(situacao='dispensada', revision=2, motivo='Engano sintetico'))
            nova = self.call(self.clientes['substituto'], 'post', self.url+'/situacao', dict(situacao='a_fazer', revision=3, motivo='Retomar'))
            self.assertEqual(nova['situacao'], 'a_fazer')
        finally:
            self.rt._hoje = lambda: HOJE


if __name__ == '__main__':
    unittest.main(verbosity=2)
