"""Relógio fixo e retomada do agendador sem dormir nem acessar SMTP real."""
import sys
import sqlite3
import tempfile
import copy
import io
import json
import logging
import logging.config
from contextlib import redirect_stderr
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from auditoria_fiscal.web.agendador import Agendador
from auditoria_fiscal.web import agendador as modulo_agendador
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore
from auditoria_fiscal.ferramentas.alertas_email import ConfigSMTP, enviar_resumos


def integracao_store_real():
    fuso = timezone(timedelta(hours=-3))
    instante = [datetime(2026, 10, 1, 6, 59, tzinfo=fuso)]
    usuarios = [dict(id=2, ativo=True, email='pessoa@example.test', pode_setor=True)]
    ator = dict(usuario_id=2, usuario_login='gestor_sintetico')
    with tempfile.TemporaryDirectory(prefix='agendador_real_sintetico_') as pasta:
        banco = str(Path(pasta) / 'clientes.db')
        def factory():
            return TarefasStore(banco, usuario_ativo=lambda uid: uid == 2, agora_fn=lambda: instante[0])
        s = factory()
        cid = s.criar_cliente({'nome': 'Empresa Sintetica do Agendador'}, **ator)
        sid = s.salvar_setor({'nome': 'Setor Sintetico', 'responsavel_usuario_id': 2}, **ator)['id']
        s.definir_membros(sid, [2], **ator)
        s.definir_carteira(cid, sid, 2, **ator)
        s.salvar_obrigacao(dict(setor_id=sid, nome='Obrigacao Mensal Sintetica', periodicidade='mensal',
            regra_vencimento={'tipo':'dia_mes_seguinte','dia':1}, condicao={}), **ator)
        s.criar_avulsa(dict(cliente_id=cid, setor_id=sid, titulo='Prazo Avulso Sintetico',
            responsavel_usuario_id=2, inicio='2026-10-01', vencimento='2026-10-01'), **ator)
        s.fechar()
        def enviar(store, pessoas, hoje):
            # Nunca consulta ambiente/SMTP real; a reserva e' a implementacao de producao.
            return enviar_resumos(store, pessoas, hoje, configuracao=ConfigSMTP())
        def criar():
            return Agendador(factory, lambda: usuarios, relogio=lambda: instante[0], enviar=enviar)
        def contagens():
            store = factory()
            try:
                return (store.conn.execute('SELECT count(*) FROM tarefa').fetchone()[0],
                        store.conn.execute("SELECT count(*) FROM geracao WHERE disparo='automatico'").fetchone()[0],
                        len(store.listar_envios()))
            finally:
                store.fechar()
        agendador = criar()
        agendador.executar_ciclo()
        assert agendador.diagnostico['geracoes'] == agendador.diagnostico['tarefas_criadas'] == 1
        agendador.executar_ciclo()
        assert agendador.diagnostico['geracoes'] == agendador.diagnostico['tarefas_criadas'] == 0
        assert contagens() == (2, 1, 0), 'Mes gerado uma vez antes do horario de envio'
        instante[0] = instante[0].replace(hour=7)
        agendador.executar_ciclo(); agendador.executar_ciclo()
        assert contagens() == (2, 1, 1), 'Um resumo por pessoa/dia, mesmo quando responsavel e chefe coincidem'
        instante[0] = datetime(2026, 10, 2, 2, 30, tzinfo=timezone.utc)
        criar().executar_ciclo()
        assert contagens() == (2, 1, 1), 'Virada UTC nao pode antecipar o dia de Salvador'
        instante[0] = datetime(2026, 11, 4, 7, 30, tzinfo=fuso)
        criar().executar_ciclo(); criar().executar_ciclo()
        assert contagens() == (3, 2, 2), 'Retoma competencia corrente apos desligado no dia primeiro'
        instante[0] = datetime(2026, 12, 4, 8, tzinfo=fuso)
        def ciclo_concorrente(_):
            novo = criar()
            novo.executar_ciclo()
            return novo.ultimo_resultado
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(ciclo_concorrente, range(2)))
        assert all(r['estado'] == 'ok' for r in resultados)
        assert contagens() == (4, 3, 3), 'Dois agendadores nao duplicam agenda nem resumo'
        agendador.iniciar(); agendador.parar()
        assert not agendador.rodando

class Store:
    geracoes=set()
    def listar_setores(self): return [dict(id=1,ativo=True)]
    def gerar(self,competencia,**kwargs):
        self.geracoes.add((competencia,kwargs['setor_id']))
    def configuracao(self): return {'tarefas_resumo_hora':'07:00'}
    def fechar(self): pass

def main():
    diagnostico_operacional()
    envios=set()
    def enviar(store,usuarios,hoje): envios.add(hoje.isoformat())
    instante=[datetime(2026,10,1,6,59,tzinfo=timezone(timedelta(hours=-3)))]
    a=Agendador(Store,lambda:[],relogio=lambda:instante[0],enviar=enviar)
    a.executar_ciclo(); a.executar_ciclo()
    assert Store.geracoes=={('2026-10',1)} and not envios
    instante[0]=instante[0].replace(hour=7)
    a.executar_ciclo(); a.executar_ciclo()
    assert envios=={'2026-10-01'}
    instante[0]=instante[0].replace(month=11,day=4)
    Agendador(Store,lambda:[],relogio=lambda:instante[0],enviar=enviar).executar_ciclo()
    assert ('2026-11',1) in Store.geracoes and '2026-11-04' in envios
    a.iniciar(); a.parar(); assert not a.rodando
    integracao_store_real()
    print('OK - agendador no processo, relógio Salvador, retomada e encerramento')
    return 0
def diagnostico_operacional():
    """Logs capturados com a configuracao real do Uvicorn e nenhuma credencial."""
    from uvicorn.config import LOGGING_CONFIG
    confidencial = 'senha-sintetica-nao-publicar@example.invalid'
    registros = []
    class Captura(logging.Handler):
        def emit(self, registro):
            registros.append(registro)
    class StoreDiagnostico:
        def __init__(self, *, vazio=False, falha=None, falha_fechar=False, geracao=None):
            self.vazio, self.falha, self.falha_fechar = vazio, falha, falha_fechar
            self.fechamentos = 0
            self.erro = RuntimeError(confidencial)
            self.geracao = geracao
        def listar_setores(self):
            if self.falha == 'geracao': raise self.erro
            return [] if self.vazio else [dict(id=77, nome=confidencial, ativo=True), dict(id=88, ativo=False)]
        def gerar(self, competencia, **kwargs):
            if self.geracao is not None: return self.geracao
            return dict(contagens=dict(novas=100, criadas=2), geracao_ids=[500], tarefas=[dict(nome=confidencial)])
        def configuracao(self):
            if self.falha == 'configuracao': raise self.erro
            return dict(tarefas_resumo_hora='07:00')
        def fechar(self):
            self.fechamentos += 1
            if self.falha == 'fechamento' or self.falha_fechar: raise RuntimeError('fechamento-'+confidencial)
    instante = datetime(2026, 10, 28, 6, 59, tzinfo=timezone(timedelta(hours=-3)))
    def novo(store, *, hora=None, enviar=None, factory=None):
        tempo = iter((10.0, 10.125))
        return Agendador(factory or (lambda: store), lambda: [], relogio=lambda: hora or instante,
                         enviar=enviar or (lambda *args: dict(ok=1, falha=0, desligado=0, ja_registrado=3,
                                                              destino=confidencial, senha=confidencial)),
                         monotonico=lambda: next(tempo))
    def falhar(a, etapa, erro_esperado=None):
        antes = len(registros)
        try:
            a.executar_ciclo()
        except RuntimeError as exc:
            if erro_esperado is not None: assert exc is erro_esperado
        else:
            raise AssertionError('O ciclo deve propagar a falha ao chamador direto')
        assert len(registros) == antes + 1 and registros[-1].levelno == logging.ERROR
        assert a.ultimo_resultado == dict(estado='falha', erro='FALHA_AGENDADOR')
        assert a.diagnostico['estado'] == 'falha' and a.diagnostico['etapa'] == etapa
        assert a.diagnostico['erro'] == 'FALHA_AGENDADOR' and a.diagnostico['duracao_ms'] == 125
        assert a.diagnostico['em'] == instante.isoformat() or etapa == 'alertas'
        assert registros[-1].exc_info is None and registros[-1].stack_info is None
    captura = Captura()
    stderr = io.StringIO()
    logger = modulo_agendador.logger
    assert logger.name.startswith('uvicorn.error.') and not logger.handlers and logger.level == logging.NOTSET
    with redirect_stderr(stderr):
        logging.config.dictConfig(copy.deepcopy(LOGGING_CONFIG))
        logger.addHandler(captura)
        try:
            s = StoreDiagnostico(vazio=True)
            a = novo(s)
            assert a.diagnostico == {'estado': 'aguardando'}
            antes = len(registros)
            a.executar_ciclo()
            assert len(registros) == antes + 1 and registros[-1].levelno == logging.INFO
            assert a.diagnostico == dict(estado='ok', em=instante.isoformat(), competencia='2026-10',
                duracao_ms=125, setores_ativos=0, geracoes=0, tarefas_criadas=0, envios=None)
            assert a.ultimo_resultado == dict(estado='ok', em=instante.isoformat(), envios=None)
            assert s.fechamentos == 1
            s = StoreDiagnostico()
            a = novo(s, hora=instante.replace(hour=7))
            a.executar_ciclo()
            d = a.diagnostico
            assert d['setores_ativos'] == 1 and d['geracoes'] == 1 and d['tarefas_criadas'] == 2
            assert d['envios'] == dict(ok=1, falha=0, desligado=0, ja_registrado=3)
            assert 'destino' not in d['envios'] and 'senha' not in d['envios']
            d['envios']['ok'] = 999
            assert a.diagnostico['envios']['ok'] == 1, 'A resposta nao altera o snapshot interno'
            # Nem um valor textual sob uma chave conhecida pode escapar como contagem.
            a = novo(StoreDiagnostico(vazio=True), hora=instante.replace(hour=7),
                     enviar=lambda *args: dict(ok=confidencial, falha=True, desligado=-1, ja_registrado=3))
            a.executar_ciclo()
            assert a.diagnostico['envios'] == dict(ok=0, falha=0, desligado=0, ja_registrado=3)
            # Candidatas nao sao operacoes efetuadas: geracao ja registrada fica em zero.
            s = StoreDiagnostico(geracao=dict(contagens=dict(novas=100, criadas=0), geracao_ids=[]))
            a = novo(s); a.executar_ciclo()
            assert a.diagnostico['geracoes'] == a.diagnostico['tarefas_criadas'] == 0
            # Falha de abertura tambem tem carimbo/duracao; nenhuma conexao existe para fechar.
            erro_abertura = RuntimeError(confidencial)
            def abrir(): raise erro_abertura
            falhar(novo(None, factory=abrir), 'abertura', erro_abertura)
            for etapa in ('geracao', 'configuracao', 'fechamento'):
                s = StoreDiagnostico(falha=etapa)
                falhar(novo(s), etapa)
                assert s.fechamentos == 1
            # O store de produção herda um fechar() tolerante: verificar a
            # integração real para que ela não esconda a falha do SQLite.
            class ConexaoComFalha:
                def close(self):
                    raise sqlite3.OperationalError(confidencial)
            real = TarefasStore.__new__(TarefasStore)
            real._conn = ConexaoComFalha()
            real.listar_setores = lambda: []
            real.configuracao = lambda: dict(tarefas_resumo_hora='07:00')
            a = novo(real)
            try:
                a.executar_ciclo()
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError('Falha SQLite real no fechamento não pode anunciar sucesso')
            assert a.diagnostico['estado'] == 'falha' and a.diagnostico['etapa'] == 'fechamento'
            assert registros[-1].levelno == logging.ERROR
            real.fechar()  # Contrato tolerante dos consumidores anteriores preservado.
            class StoreParcial(StoreDiagnostico):
                def listar_setores(self): return [dict(id=1), dict(id=2)]
                def gerar(self, competencia, **kwargs):
                    if kwargs['setor_id'] == 2: raise self.erro
                    return super().gerar(competencia, **kwargs)
            s = StoreParcial()
            a = novo(s)
            falhar(a, 'geracao', s.erro)
            assert a.diagnostico['geracoes'] == 1 and a.diagnostico['tarefas_criadas'] == 2
            assert a.diagnostico['setores_ativos'] == 2 and s.fechamentos == 1
            s = StoreDiagnostico()
            def enviar_falha(*args): raise s.erro
            falhar(novo(s, hora=instante.replace(hour=7), enviar=enviar_falha), 'alertas', s.erro)
            assert s.fechamentos == 1
            # Fechar em erro nao mascara a etapa/excecao primaria.
            s = StoreDiagnostico(falha='configuracao', falha_fechar=True)
            falhar(novo(s), 'configuracao', s.erro)
            assert s.fechamentos == 1
            # O loop trata a falha uma vez e retoma sem log duplicado nem sleep real.
            lojas = iter((StoreDiagnostico(falha='geracao'), StoreDiagnostico(vazio=True)))
            tempos = iter((1.0, 1.01, 2.0, 2.02))
            a = Agendador(lambda: next(lojas), lambda: [], relogio=lambda: instante,
                          monotonico=lambda: next(tempos))
            class Parada:
                def __init__(self): self.esperas = []
                def is_set(self): return False
                def wait(self, intervalo):
                    self.esperas.append(intervalo)
                    return len(self.esperas) == 2
            a._parar = Parada()
            antes = len(registros)
            a._loop()
            assert [r.levelno for r in registros[antes:]] == [logging.ERROR, logging.INFO]
            assert a._parar.esperas == [900, 900] and a.diagnostico['estado'] == 'ok'
            for registro in registros:
                mensagem = registro.getMessage()
                assert mensagem.startswith('agendador_ciclo ')
                payload = json.loads(mensagem.split(' ', 1)[1])
                assert set(payload) <= {'estado','em','competencia','duracao_ms','setores_ativos','geracoes','tarefas_criadas','envios','etapa','erro'}
                assert confidencial not in mensagem
            assert 'agendador_ciclo' in stderr.getvalue(), 'INFO deve sair pelo handler padrao Uvicorn'
            assert confidencial not in stderr.getvalue()
        finally:
            logger.removeHandler(captura)
    assert not logger.handlers and logger.level == logging.NOTSET


if __name__=='__main__': raise SystemExit(main())
