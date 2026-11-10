"""Diagnóstico operacional: startup estável, acesso administrativo e logs sem dados."""
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ['AUDITORIA_WEB_DADOS'] = tempfile.mkdtemp(prefix='web_diagnostico_')
from fastapi.testclient import TestClient
from auditoria_fiscal.web import servidor


class AgendadorSintetico:
    instancias = []

    def __init__(self, *args):
        self.iniciou = self.parou = False
        self.ultimo_resultado = {'estado': 'ok', 'em': '2026-10-28T09:00:00-03:00', 'envios': None}
        self.diagnostico = dict(self.ultimo_resultado, competencia='2026-10', duracao_ms=12,
                               setores_ativos=0, geracoes=0, tarefas_criadas=0)
        self.instancias.append(self)

    def iniciar(self):
        self.iniciou = True

    def parar(self):
        self.parou = True


class StoreSintetico:
    def fechar(self):
        pass


class Captura(logging.Handler):
    def __init__(self):
        super().__init__()
        self.mensagens = []

    def emit(self, record):
        self.mensagens.append(record.getMessage())


def main():
    chamadas = []
    versao = {'sha': 'a' * 40, 'origem': 'git', 'arvore': 'limpa'}
    def identificar(raiz):
        chamadas.append(raiz)
        return versao
    originais = {nome: getattr(servidor, nome, None) for nome in ('identificar_versao', 'Agendador', 'criar_store_tarefas')}
    servidor.identificar_versao = identificar
    servidor.Agendador = AgendadorSintetico
    servidor.criar_store_tarefas = StoreSintetico
    logger = logging.getLogger('uvicorn.error')
    nivel = logger.level
    captura = Captura()
    logger.addHandler(captura)
    logger.setLevel(logging.INFO)
    try:
        app = servidor.criar_app()
        assert not chamadas, 'A identificação pertence ao startup, não à criação/importação do app.'
        with TestClient(app) as adm:
            assert len(chamadas) == 1, 'O lifespan deve capturar a versão uma única vez.'
            assert AgendadorSintetico.instancias[-1].iniciou
            estado = adm.get('/api/estado').json()
            assert estado['precisa_bootstrap'] and not estado['logado'] and 'operacao' not in estado
            r = adm.post('/api/bootstrap', json=dict(usuario='admin_sintetico', nome='Admin sintético', senha='sintetica-123'))
            assert r.status_code == 200, r.text
            estado = adm.get('/api/estado').json()
            operacao = estado['operacao']
            assert set(operacao) == {'versao', 'agendador'}
            assert set(operacao['versao']) == {'sha', 'origem', 'arvore', 'iniciado_em'}
            assert operacao['versao']['sha'] == 'a' * 40
            inicio = datetime.fromisoformat(operacao['versao']['iniciado_em'])
            assert inicio.utcoffset().total_seconds() == 0
            assert operacao['agendador']['setores_ativos'] == 0
            assert operacao['agendador']['estado'] == 'ok'
            # O checkout ou objeto retornado pelo coletor pode mudar depois do startup.
            versao['sha'] = 'b' * 40
            for _ in range(3):
                assert adm.get('/api/estado').json()['operacao']['versao'] == operacao['versao']
            assert len(chamadas) == 1, 'Nenhuma requisição deve chamar Git.'
            r = adm.post('/api/admin/usuarios', json=dict(usuario='pessoa_sintetica', nome='Pessoa sintética', senha='sintetica-123', permissoes=['aba.tarefas']))
            assert r.status_code == 200, r.text
            pessoa = TestClient(app)
            r = pessoa.post('/api/login', json=dict(usuario='pessoa_sintetica', senha='sintetica-123'))
            assert r.status_code == 200, r.text
            estado_comum = pessoa.get('/api/estado').json()
            assert estado_comum['logado'] and 'operacao' not in estado_comum
            avisos = pessoa.get('/api/tarefas/avisos')
            assert avisos.status_code == 200, avisos.text
            assert avisos.json()['agendador'] == AgendadorSintetico.instancias[-1].ultimo_resultado
            assert 'setores_ativos' not in avisos.json()['agendador']
            assert 'operacao' not in TestClient(app).get('/api/estado').json()
            linhas = [m for m in captura.mensagens if m.startswith('aplicacao_inicio ')]
            assert len(linhas) == 1 and 'a' * 40 in linhas[0] and 'arvore=limpa' in linhas[0], linhas
            assert 'admin_sintetico' not in linhas[0] and 'senha' not in linhas[0] and str(Path.cwd()) not in linhas[0]
        assert AgendadorSintetico.instancias[-1].parou
        # Apps usados sem lifespan em ferramentas/testes não inventam versão.
        sem_startup = TestClient(servidor.criar_app())
        assert sem_startup.post('/api/login', json=dict(usuario='admin_sintetico', senha='sintetica-123')).status_code == 200
        indisponivel = sem_startup.get('/api/estado').json()['operacao']
        assert indisponivel['versao'] == dict(sha=None, origem='indisponivel', arvore='desconhecida', iniciado_em=None)
        assert indisponivel['agendador'] == {'estado': 'aguardando'}
        assert len(chamadas) == 1
        versao.update(sha=None, origem='indisponivel', arvore='desconhecida')
        with TestClient(servidor.criar_app()) as sem_git:
            assert sem_git.get('/api/estado').status_code == 200
        assert len(chamadas) == 2 and AgendadorSintetico.instancias[-1].parou
        assert any('origem=indisponivel' in m for m in captura.mensagens if m.startswith('aplicacao_inicio '))
        print('OK - diagnóstico web: captura única, acesso administrativo, indisponibilidade e log sanitizado')
        return 0
    finally:
        for nome, valor in originais.items():
            if valor is None:
                delattr(servidor, nome)
            else:
                setattr(servidor, nome, valor)
        logger.removeHandler(captura)
        logger.setLevel(nivel)


if __name__ == '__main__':
    raise SystemExit(main())
