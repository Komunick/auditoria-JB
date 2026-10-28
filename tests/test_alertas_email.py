"""Resumo diário: destinatários efetivos, reserva única e SMTP local sintético."""
import os
import socketserver
import smtplib
import sys
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas.alertas_email import ConfigSMTP, montar_resumos, enviar_resumos, _mensagem
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore


def preparar_store_real(caminho):
    """Cenarios de destinatario e espera usando os campos e transacoes de producao."""
    relogio = [datetime(2026, 10, 20, 12, tzinfo=timezone.utc)]
    s = TarefasStore(caminho, usuario_ativo=lambda uid: uid in range(1, 5), agora_fn=lambda: relogio[0])
    ator = dict(usuario_id=1, usuario_login='gestor_sintetico')
    cid = s.criar_cliente({'nome': 'Empresa Sintetica de Alertas'}, **ator)
    sid = s.salvar_setor({'nome': 'Setor Sintetico', 'responsavel_usuario_id': 1}, **ator)['id']
    s.definir_membros(sid, [1, 2, 3, 4], **ator)
    for titular, substituto in ((1, 4), (2, 3)):
        s.criar_substituicao(dict(titular_usuario_id=titular, substituto_usuario_id=substituto,
            setor_id=sid, inicio='2026-10-20', fim='2026-10-30', motivo='Ausencia sintetica'), **ator)
    def tarefa(titulo, dono, prazo, conferencia=False):
        return s.criar_avulsa(dict(cliente_id=cid, setor_id=sid, titulo=titulo,
            responsavel_usuario_id=dono, vencimento=prazo, inicio='2026-10-20',
            exige_conferencia=conferencia), **ator)
    prazo = tarefa('Prazo sintetico', 2, '2026-10-27')
    conferir = tarefa('Conferencia sintetica', 3, '2026-10-24', True)
    conferir = s.mudar_situacao(conferir['id'], 'em_andamento', conferir['revision'], **ator)
    conferir = s.mudar_situacao(conferir['id'], 'concluida', conferir['revision'], **ator)
    esperar = tarefa('Espera sintetica', 3, '2026-11-30')
    # Em Salvador este carimbo ainda e' dia 21. Um comentario futuro nao zera a espera.
    relogio[0] = datetime(2026, 10, 22, 2, 59, tzinfo=timezone.utc)
    esperar = s.mudar_situacao(esperar['id'], 'aguardando_cliente', esperar['revision'], **ator)
    relogio[0] = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    s.comentar(esperar['id'], 'Contato sintetico registrado', esperar['revision'], **ator)
    return s, (prazo['id'], conferir['id'], esperar['id'])


def integracao_store_real():
    usuarios = [dict(id=i, nome=f'Pessoa Teste {i}', email=f'p{i}@example.test', ativo=True) for i in range(1, 5)]
    hoje = date(2026, 10, 27)
    with tempfile.TemporaryDirectory(prefix='alertas_store_sintetico_') as pasta:
        banco = str(Path(pasta) / 'clientes.db')
        s, (prazo, conferir, esperar) = preparar_store_real(banco)
        try:
            resumos = montar_resumos(s, usuarios, hoje)
            assert set(resumos) == {3, 4}
            assert {t['id'] for t in resumos[3]['tarefas']} == {prazo, esperar}
            assert {t['id'] for t in resumos[4]['tarefas']} == {prazo, conferir, esperar}
            assert resumos[4]['quantidades'] == dict(vencendo=1, atrasadas=0, conferencias=1, aguardando=1)
            limite_espera = montar_resumos(s, usuarios, date(2026, 10, 26))
            assert limite_espera[3]['quantidades']['aguardando'] == 0, 'O alerta exige mais de cinco dias, nao apenas cinco'
            depois = montar_resumos(s, usuarios, date(2026, 10, 31))
            assert set(depois) == {1, 2, 3}, 'Fim de substituicao devolve os destinatarios sem reescrever tarefas'
            assert {t['id'] for t in depois[2]['tarefas']} == {prazo}
            assert depois[1]['quantidades']['conferencias'] == 1
            sem_chefia = [dict(u, pode_setor=False) if u['id'] == 4 else u for u in usuarios]
            assert 4 not in montar_resumos(s, sem_chefia, hoje), 'Sem permissao de setor nao recebe conferencia de terceiros'
            inativo = [dict(u, ativo=False) if u['id'] == 3 else u for u in usuarios]
            assert 3 not in montar_resumos(s, inativo, hoje)
        finally:
            s.fechar()

        enviados = []
        trava = threading.Lock()
        barreira = threading.Barrier(2)
        class SMTPMemoria:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def ehlo(self): pass
            def starttls(self, **kwargs): pass
            def send_message(self, mensagem):
                with trava:
                    enviados.append(str(mensagem['To']))
        cfg = ConfigSMTP(host='smtp.example.test', remetente='resumo@example.test')
        def enviar_concorrente(_):
            outro = TarefasStore(banco)
            try:
                barreira.wait(timeout=10)
                return enviar_resumos(outro, usuarios, hoje, configuracao=cfg, smtp_factory=SMTPMemoria)
            finally:
                outro.fechar()
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(enviar_concorrente, range(2)))
        assert sorted(enviados) == ['p3@example.test', 'p4@example.test'], enviados
        assert sum(r['ok'] for r in resultados) == 2
        s = TarefasStore(banco)
        try:
            assert len(s.listar_envios()) == 2 and all(e['resultado'] == 'ok' for e in s.listar_envios())
            assert enviar_resumos(s, usuarios, hoje, configuracao=cfg, smtp_factory=SMTPMemoria)['ja_registrado'] == 2
            invalidos = [dict(u, email='nao-e-email') if u['id'] == 3 else u for u in usuarios]
            r = enviar_resumos(s, invalidos, date(2026, 10, 28), configuracao=cfg, smtp_factory=SMTPMemoria)
            assert r['falha'] == 1 and r['ok'] == 1, 'Email invalido nao interrompe outros destinatarios'
            registros = s.listar_envios('2026-10-28')
            assert next(e for e in registros if e['usuario_id'] == 3)['erro'] == 'EMAIL_DESTINATARIO_AUSENTE_OU_INVALIDO'
            r = enviar_resumos(s, usuarios, date(2026, 10, 29), configuracao=ConfigSMTP())
            assert r['desligado'] == 2
        finally:
            s.fechar()


class Store:
    def __init__(self):
        self.envios = {}
        self.itens = [
            dict(id=1, titulo='Obrigação sintética', cliente_nome='Empresa Teste', setor_id=1,
                 responsavel_usuario_id=2, vencimento='2026-10-27', situacao='a_fazer'),
            dict(id=2, titulo='Conferência', cliente_nome='Empresa Teste', setor_id=1,
                 responsavel_usuario_id=3, vencimento='2026-10-24', situacao='concluida', exige_conferencia=True),
            dict(id=3, titulo='Aguardar', cliente_nome='Empresa Teste', setor_id=1,
                 responsavel_usuario_id=3, vencimento='2026-11-30', situacao='aguardando_cliente',
                 atualizada_em='2026-10-10T12:00:00+00:00'),
        ]
    def listar_tarefas(self, **kwargs):
        offset = kwargs.get('offset', 0)
        return {'itens': self.itens[offset:offset+kwargs.get('limite',100)], 'total': len(self.itens)}
    def listar_setores(self):
        return [dict(id=1, responsavel_usuario_id=1, ativo=True)]
    def responsavel_efetivo(self, setor_id, titular_id, hoje):
        return {1:4, 2:3}.get(titular_id, titular_id)
    def configuracao(self):
        return dict(tarefas_alerta_dias=3, tarefas_aguardando_cliente_dias=5, tarefas_resumo_hora='07:00')
    def reservar_envio(self, usuario_id, dia, destino, quantidades):
        chave = (usuario_id, dia)
        if chave in self.envios:
            return False
        self.envios[chave] = dict(destino=destino, quantidades=quantidades, resultado='pendente')
        return True
    def finalizar_envio(self, usuario_id, dia, resultado, erro=''):
        self.envios[usuario_id, dia].update(resultado=resultado, erro=erro)


class SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 synthetic.local ESMTP\r\n')
        while True:
            line = self.rfile.readline()
            if not line:
                break
            command = line.upper()
            if command.startswith(b'DATA'):
                self.wfile.write(b'354 send\r\n')
                message = []
                while True:
                    part = self.rfile.readline()
                    if part == b'.\r\n' or not part:
                        break
                    message.append(part)
                self.server.messages.append(b''.join(message))
                self.wfile.write(b'250 accepted\r\n')
            elif command.startswith(b'QUIT'):
                self.wfile.write(b'221 bye\r\n')
                break
            else:
                self.wfile.write(b'250 synthetic.local\r\n')


def main():
    hoje = date(2026,10,27)
    usuarios = [dict(id=i, nome=f'Pessoa Teste {i}', email=f'p{i}@example.test', ativo=True) for i in range(1,5)]
    # Sem prazo nao atrasa nem vence; conferencia e espera continuam alertando.
    sem_prazo = Store()
    sem_prazo.itens = [dict(t, vencimento='', ocorrencia=1) for t in sem_prazo.itens]
    sem_resumos = montar_resumos(sem_prazo, usuarios, hoje)
    assert {t['id'] for t in sem_resumos[3]['tarefas']} == {3}
    assert {t['id'] for t in sem_resumos[4]['tarefas']} == {2, 3}
    assert sem_resumos[4]['quantidades'] == dict(vencendo=0, atrasadas=0, conferencias=1, aguardando=1)
    mensagem = _mensagem(sem_resumos[4], ConfigSMTP(remetente='resumo@example.test'), hoje)
    assert 'Sem vencimento' in mensagem.get_content()
    sem_resumos[4]['tarefas'][0].update(ocorrencia=2, origem={'intervalo': '11–20'})
    assert '11–20' in _mensagem(sem_resumos[4], ConfigSMTP(remetente='resumo@example.test'), hoje).get_content()
    s = Store()
    resumos = montar_resumos(s, usuarios, hoje)
    assert set(resumos) == {3,4}, resumos
    assert {t['id'] for t in resumos[3]['tarefas']} == {1,3}
    assert {t['id'] for t in resumos[4]['tarefas']} == {1,2,3}
    assert resumos[4]['quantidades']['conferencias'] == 1
    assert not ConfigSMTP.de_ambiente({}).ativo
    enviar_resumos(s, usuarios, hoje, configuracao=ConfigSMTP.de_ambiente({}))
    assert all(e['resultado'] == 'desligado' for e in s.envios.values())
    assert len(s.envios) == 2
    with socketserver.TCPServer(('127.0.0.1',0), SMTPHandler) as server:
        server.messages=[]
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        def smtp_local(host,port,timeout):
            conn=smtplib.SMTP(host,port,timeout=timeout)
            conn.starttls=lambda **kw: (220,b'Test-only transport')
            return conn
        cfg=ConfigSMTP(host='127.0.0.1',porta=server.server_address[1],remetente='resumo@example.test')
        s=Store()
        enviar_resumos(s,usuarios,hoje,configuracao=cfg,smtp_factory=smtp_local)
        enviar_resumos(s,usuarios,hoje,configuracao=cfg,smtp_factory=smtp_local)
        assert len(server.messages)==2, len(server.messages)
        assert all(e['resultado']=='ok' for e in s.envios.values())
        assert b'Tarefas e prazos' in server.messages[0]
        server.shutdown(); worker.join(timeout=2)
    s=Store()
    def falha(*args,**kwargs):
        raise RuntimeError('senha-secreta host privado')
    enviar_resumos(s,usuarios,hoje,configuracao=cfg,smtp_factory=falha)
    assert all(e['resultado']=='falha' for e in s.envios.values())
    assert 'senha-secreta' not in repr(s.envios)
    integracao_store_real()
    print('OK - resumo efetivo, SMTP local, idempotência, desligado e falha sem segredo')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
