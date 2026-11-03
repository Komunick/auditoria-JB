"""Resumo diário único: sete alertas, escopo efetivo e nenhuma informação de custo."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import tempfile
from threading import Barrier, Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas.alertas_email import ConfigSMTP, montar_resumos, enviar_resumos, _mensagem
from auditoria_fiscal.ferramentas.qualidade_store import QualidadeStore
from test_alertas_email import Store as StoreLegado

HOJE = date(2026, 10, 30)


class Store(StoreLegado):
    def __init__(self):
        super().__init__()
        base = dict(cliente_id=1, cliente_nome='Empresa sintética', setor_id=1,
            responsavel_usuario_id=2, situacao='a_fazer', inicio='2026-10-01',
            criada_em='2026-10-01T12:00:00+00:00', atualizada_em='2026-10-01T12:00:00+00:00')
        self.itens = [dict(base, id=1, titulo='Vence em breve', vencimento='2026-11-01'),
            dict(base, id=2, titulo='Tarefa atrasada', vencimento='2026-10-29'),
            dict(base, id=3, titulo='Documento faltante', vencimento='2026-11-30', situacao='aguardando_cliente'),
            dict(base, id=4, titulo='Conferência pendente', vencimento='2026-10-30',
                situacao='concluida', exige_conferencia=True, concluida_em='2026-10-30T12:00:00+00:00'),
            dict(base, id=5, titulo='TAREFA PRIVADA USUARIO SEM ABA', responsavel_usuario_id=7, vencimento='2026-10-29'),
            dict(base, id=6, titulo='Tarefa de quem só tem Tarefas', responsavel_usuario_id=8, vencimento='2026-10-29'),
            dict(base, id=7, titulo='Tarefa de outro setor', setor_id=2, responsavel_usuario_id=5, vencimento='2026-10-29')]
        obase = dict(cliente_id=1, setor_id=1, responsavel_usuario_id=2, tipo='nao_conformidade',
            descricao='NC sintética', situacao='aberta', criticidade='alta', prazo='2026-10-29',
            criado_em='2026-10-01T12:00:00+00:00', atualizado_em='2026-10-01T12:00:00+00:00')
        self.ocorrencias = [dict(obase, id=1), dict(obase, id=2, responsavel_usuario_id=7, descricao='NC só qualidade'),
            dict(obase, id=3, responsavel_usuario_id=8, descricao='NC VEDADA A USUARIO SO TAREFAS'),
            dict(obase, id=4, setor_id=2, responsavel_usuario_id=5, descricao='NC outro setor')]
        self.planos = [dict(obase, id=1, ocorrencia_id=1, tipo='corretiva', situacao='aberto', descricao='Plano vencido')]
    def listar_setores(self):
        return [dict(id=1, responsavel_usuario_id=1, ativo=True), dict(id=2, responsavel_usuario_id=5, ativo=True)]
    def listar_ocorrencias(self):
        return self.ocorrencias
    def listar_planos(self):
        return self.planos
    def listar_horas(self, *args, **kwargs):
        raise AssertionError('Resumo SMTP nunca deve consultar horas ou custos')


def usuarios():
    pessoas = [dict(id=i, email=f'p{i}@example.test', ativo=True, pode_tarefas=True,
        pode_qualidade=True, pode_qualidade_gerir=False, pode_qualidade_todas=False) for i in range(1, 11)]
    for u in pessoas:
        if u['id'] in (1, 4):
            u['pode_qualidade_gerir'] = True
        if u['id'] == 6:
            u['pode_qualidade_todas'] = True
        if u['id'] == 7:
            u['pode_tarefas'] = False
        if u['id'] == 8:
            u['pode_qualidade'] = False
        if u['id'] == 9:
            u.update(pode_tarefas=False, pode_qualidade=False, pode_qualidade_todas=True)
        if u['id'] == 10:
            u['ativo'] = False
    return pessoas


def integracao_concorrente():
    ator = dict(usuario_id=1, usuario_login='gestor_sintetico')
    with tempfile.TemporaryDirectory(prefix='qualidade_alerta_') as pasta:
        db = str(Path(pasta) / 'clientes.db')
        s = QualidadeStore(db, usuario_ativo=lambda uid: uid in (1, 2),
            agora_fn=lambda: datetime(2026, 10, 30, 12, tzinfo=timezone.utc))
        cid = s.criar_cliente(dict(nome='Empresa SMTP sintética'), **ator)
        sid = s.salvar_setor(dict(nome='Setor SMTP sintético', responsavel_usuario_id=1, membros=[1, 2]), **ator)['id']
        s.criar_ocorrencia(dict(data='2026-10-29', cliente_id=cid, setor_id=sid,
            responsavel_usuario_id=2, tipo='nao_conformidade', descricao='NC sintética para resumo',
            criticidade='alta', prazo='2026-10-30'), **ator)
        s.fechar()
        pessoas = [dict(id=i, ativo=True, email=f'p{i}@example.test', pode_tarefas=False,
            pode_qualidade=True, pode_qualidade_gerir=i == 1) for i in (1, 2)]
        mensagens, trava, barreira = [], Lock(), Barrier(2)
        class SMTP:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def ehlo(self): pass
            def starttls(self, **kwargs): pass
            def send_message(self, m):
                with trava:
                    mensagens.append(m)
        cfg = ConfigSMTP(host='synthetic.invalid', remetente='resumo@example.test')
        def enviar(_):
            s = QualidadeStore(db)
            try:
                barreira.wait(timeout=10)
                return enviar_resumos(s, pessoas, HOJE, configuracao=cfg, smtp_factory=SMTP)
            finally:
                s.fechar()
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(enviar, range(2)))
        assert len(mensagens) == 2 and sum(r['ok'] for r in resultados) == 2
        assert all('Não conformidades' in m.get_content() for m in mensagens)
        s = QualidadeStore(db)
        try:
            envios = s.listar_envios(HOJE.isoformat())
            assert len(envios) == 2 and all(e['resultado'] == 'ok' for e in envios)
            assert all(e['quantidades']['qualidade_nao_conformidades'] == 1 for e in envios)
        finally:
            s.fechar()


def main():
    s, pessoas = Store(), usuarios()
    antes = deepcopy((s.itens, s.ocorrencias, s.planos, pessoas))
    resumos = montar_resumos(s, pessoas, HOJE)
    tipos = {a['tipo'] for a in resumos[4]['alertas_qualidade']}
    assert tipos == {'proximos_vencimentos', 'tarefas_atrasadas', 'sem_movimentacao',
                     'documentos_pendentes', 'aguardando_conferencia', 'nao_conformidades', 'planos_vencidos'}
    assert 1 not in resumos and 2 not in resumos and 9 not in resumos and 10 not in resumos
    assert not any(a['tipo'] == 'aguardando_conferencia' for a in resumos[3]['alertas_qualidade']), 'Conferência cabe à chefia efetiva'
    assert not resumos[7]['tarefas']
    cfg = ConfigSMTP(remetente='resumo@example.test')
    textos = {uid: _mensagem(r, cfg, HOJE).get_content() for uid, r in resumos.items()}
    assert 'TAREFA PRIVADA' not in textos[7] and 'NC só qualidade' in textos[7]
    assert 'NC VEDADA' not in textos[8] and 'Tarefa de quem só tem Tarefas' in textos[8]
    assert 'outro setor' not in textos[3] and 'outro setor' not in textos[4]
    assert 'NC outro setor' in textos[6], 'Visão global exige flag explícita e aba'
    assert all('custo_hora' not in texto and 'R$' not in texto for texto in textos.values())
    assert (s.itens, s.ocorrencias, s.planos, pessoas) == antes
    # Sem permissão explícita não há alertas de qualidade; legados mantêm comportamento.
    sem_flags = [dict(id=i, ativo=True, email=f'p{i}@example.test') for i in range(1, 11)]
    basicos = montar_resumos(s, sem_flags, HOJE)
    assert all(not any(a['tipo'] in ('nao_conformidades', 'planos_vencidos') for a in r.get('alertas_qualidade', [])) for r in basicos.values())
    legado = montar_resumos(StoreLegado(), sem_flags, date(2026, 10, 27))
    assert all('alertas_qualidade' not in r for r in legado.values())
    # Paginação do núcleo é visível e não altera quantidade real do resumo.
    s.ocorrencias = [dict(s.ocorrencias[0], id=i) for i in range(25)]
    resumo = montar_resumos(s, pessoas, HOJE)[3]
    alerta = next(a for a in resumo['alertas_qualidade'] if a['tipo'] == 'nao_conformidades')
    assert alerta['quantidade'] == 25 and len(alerta['itens']) == 20 and alerta['truncado']
    assert '25' in _mensagem(resumo, cfg, HOJE).get_content() and '20' in _mensagem(resumo, cfg, HOJE).get_content()
    desligado = enviar_resumos(s, pessoas, HOJE, configuracao=ConfigSMTP())
    assert desligado['desligado'] > 0
    assert enviar_resumos(s, pessoas, HOJE, configuracao=ConfigSMTP())['ja_registrado'] == desligado['desligado']
    integracao_concorrente()
    print('OK - sete alertas no resumo único, escopo por aba, substituição, SMTP desligado e concorrência')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
