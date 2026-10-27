"""Relógio fixo e retomada do agendador sem dormir nem acessar SMTP real."""
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from auditoria_fiscal.web.agendador import Agendador
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
        agendador.executar_ciclo(); agendador.executar_ciclo()
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
if __name__=='__main__': raise SystemExit(main())
