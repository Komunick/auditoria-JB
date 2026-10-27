"""Agendamento no processo existente; o banco arbitra geração/envio únicos."""
from __future__ import annotations
import logging
import threading
from datetime import datetime, timezone, timedelta

from ..ferramentas.alertas_email import enviar_resumos

FUSO_SALVADOR = timezone(timedelta(hours=-3))
logger = logging.getLogger(__name__)


class Agendador:
    def __init__(self, store_factory, usuarios_fn, *, relogio=None, enviar=None, intervalo=900):
        self.store_factory = store_factory
        self.usuarios_fn = usuarios_fn
        self.relogio = relogio or (lambda: datetime.now(FUSO_SALVADOR))
        self.enviar = enviar or enviar_resumos
        self.intervalo = intervalo
        self._parar = threading.Event()
        self._thread = None
        self.ultimo_resultado = {'estado': 'aguardando'}

    @property
    def rodando(self):
        return bool(self._thread and self._thread.is_alive())

    def executar_ciclo(self):
        instante = self.relogio().astimezone(FUSO_SALVADOR)
        hoje = instante.date()
        store = self.store_factory()
        try:
            for setor in store.listar_setores():
                if setor.get('ativo', True):
                    store.gerar(hoje.strftime('%Y-%m'), setor_id=setor['id'], hoje=hoje,
                                disparo='automatico', usuario_login='agendador', usuario_id=0)
            hora = store.configuracao().get('tarefas_resumo_hora', '07:00')
            envios = None
            if instante.strftime('%H:%M') >= hora:
                envios = self.enviar(store, self.usuarios_fn(), hoje)
            self.ultimo_resultado = {'estado': 'ok', 'em': instante.isoformat(), 'envios': envios}
        finally:
            store.fechar()

    def _loop(self):
        while not self._parar.is_set():
            try:
                self.executar_ciclo()
            except Exception:
                self.ultimo_resultado = {'estado': 'falha', 'erro': 'FALHA_AGENDADOR'}
                logger.error('Falha no ciclo de tarefas e prazos; o próximo ciclo tentará retomar.')
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
