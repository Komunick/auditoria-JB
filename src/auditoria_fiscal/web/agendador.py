"""Agendamento no processo existente; o banco arbitra geração/envio únicos."""
from __future__ import annotations
import copy
import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta

from ..ferramentas.alertas_email import enviar_resumos

FUSO_SALVADOR = timezone(timedelta(hours=-3))
logger = logging.getLogger('uvicorn.error.agendador')


def _contagem(valor):
    """Somente totais inteiros entram no diagnostico, nunca textos do retorno."""
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0 else 0


class Agendador:
    def __init__(self, store_factory, usuarios_fn, *, relogio=None, enviar=None, intervalo=900,
                 monotonico=None):
        self.store_factory = store_factory
        self.usuarios_fn = usuarios_fn
        self.relogio = relogio or (lambda: datetime.now(FUSO_SALVADOR))
        self.enviar = enviar or enviar_resumos
        self.intervalo = intervalo
        self.monotonico = monotonico or time.monotonic
        self._parar = threading.Event()
        self._thread = None
        self.ultimo_resultado = {'estado': 'aguardando'}
        self._diagnostico = {'estado': 'aguardando'}

    @property
    def diagnostico(self):
        # Troca atomica do snapshot ao fim do ciclo; leitores nao o modificam.
        return copy.deepcopy(self._diagnostico)

    @property
    def rodando(self):
        return bool(self._thread and self._thread.is_alive())

    def executar_ciclo(self):
        inicio = self.monotonico()
        store, falha, envios = None, None, None
        etapa = 'abertura'
        diagnostico = dict(estado='ok', em=None, competencia=None, duracao_ms=0,
                          setores_ativos=0, geracoes=0, tarefas_criadas=0, envios=None)
        try:
            instante = self.relogio().astimezone(FUSO_SALVADOR)
            hoje = instante.date()
            diagnostico.update(em=instante.isoformat(), competencia=hoje.strftime('%Y-%m'))
            store = self.store_factory()
            etapa = 'geracao'
            setores = [s for s in store.listar_setores() if s.get('ativo', True)]
            diagnostico['setores_ativos'] = len(setores)
            for setor in setores:
                resultado = store.gerar(hoje.strftime('%Y-%m'), setor_id=setor['id'], hoje=hoje,
                                        disparo='automatico', usuario_login='agendador', usuario_id=0) or {}
                diagnostico['geracoes'] += len(resultado.get('geracao_ids') or [])
                diagnostico['tarefas_criadas'] += _contagem((resultado.get('contagens') or {}).get('criadas'))
            etapa = 'configuracao'
            hora = store.configuracao().get('tarefas_resumo_hora', '07:00')
            if instante.strftime('%H:%M') >= hora:
                etapa = 'alertas'
                envios = self.enviar(store, self.usuarios_fn(), hoje)
                resumo_envios = envios if isinstance(envios, dict) else {}
                diagnostico['envios'] = {chave: _contagem(resumo_envios.get(chave))
                                         for chave in ('ok', 'falha', 'desligado', 'ja_registrado')}
        except Exception as exc:
            falha = exc
        finally:
            if store is not None:
                try:
                    # O store de produção oferece fechamento que não suprime
                    # sqlite3.Error; factories simples mantêm o contrato antigo.
                    getattr(store, 'fechar_estrito', store.fechar)()
                except Exception as exc:
                    # Preservar a primeira falha; a limpeza nunca a substitui.
                    if falha is None:
                        falha, etapa = exc, 'fechamento'
        diagnostico['duracao_ms'] = max(0, round((self.monotonico() - inicio) * 1000))
        if falha is not None:
            diagnostico.update(estado='falha', etapa=etapa, erro='FALHA_AGENDADOR')
            self.ultimo_resultado = {'estado': 'falha', 'erro': 'FALHA_AGENDADOR'}
        else:
            self.ultimo_resultado = {'estado': 'ok', 'em': diagnostico['em'], 'envios': envios}
        self._diagnostico = diagnostico
        logger.log(logging.ERROR if falha is not None else logging.INFO,
                   'agendador_ciclo %s', json.dumps(diagnostico, ensure_ascii=True, separators=(',', ':')))
        if falha is not None:
            raise falha

    def _loop(self):
        while not self._parar.is_set():
            try:
                self.executar_ciclo()
            except Exception:
                # O ciclo ja registrou a falha sanitizada; retomar sem duplicar log.
                pass
            if self._parar.wait(self.intervalo):
                break

    def iniciar(self):
        if not self.rodando:
            self._parar.clear()
            self._thread = threading.Thread(target=self._loop, name='tarefas-agendador', daemon=True)
            self._thread.start()

    def parar(self):
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=25)
