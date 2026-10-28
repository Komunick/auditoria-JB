"""Resumo interno diário. Credenciais só em ambiente; reserva antes do SMTP."""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import date, timedelta
from email.message import EmailMessage

from ..core.tarefas import ErroTarefas, validar_email, data_salvador

def email_valido(valor: str) -> bool:
    try:
        return bool(validar_email(valor))
    except ErroTarefas:
        return False


@dataclass(frozen=True)
class ConfigSMTP:
    host: str = ''
    porta: int = 587
    usuario: str = ''
    senha: str = field(default='', repr=False)
    remetente: str = ''
    tls: str = 'starttls'

    @property
    def ativo(self):
        return bool(self.host and email_valido(self.remetente) and
                    0 < self.porta < 65536 and self.tls in ('ssl', 'starttls') and
                    (not self.usuario or self.senha))

    @classmethod
    def de_ambiente(cls, ambiente=None):
        env = os.environ if ambiente is None else ambiente
        tls = env.get('AUDITORIA_SMTP_TLS', 'starttls').lower().strip()
        try:
            porta = int(env.get('AUDITORIA_SMTP_PORTA', '465' if tls == 'ssl' else '587'))
        except (ValueError, TypeError):
            porta = 0
        return cls(host=env.get('AUDITORIA_SMTP_HOST', '').strip(), porta=porta,
                   usuario=env.get('AUDITORIA_SMTP_USUARIO', ''),
                   senha=env.get('AUDITORIA_SMTP_SENHA', ''),
                   remetente=env.get('AUDITORIA_SMTP_REMETENTE', '').strip(), tls=tls)


def montar_resumos(store, usuarios: list[dict], hoje: date) -> dict:
    """Uma tarefa por pessoa, mesmo quando carteira e chefia se sobrepõem."""
    ativos = {u['id']: u for u in usuarios if u.get('ativo', True)}
    setores = {s['id']: s for s in store.listar_setores() if s.get('ativo', True)}
    cfg = store.configuracao()
    limite = hoje + timedelta(days=int(cfg.get('tarefas_alerta_dias', 3)))
    espera = int(cfg.get('tarefas_aguardando_cliente_dias', 5))
    resumos = {}
    offset = 0
    while True:
        pagina = store.listar_tarefas(hoje=hoje, todas=True, offset=offset, limite=500)
        for tarefa in pagina['itens']:
            situacao = tarefa['situacao']
            if situacao in ('conferida', 'dispensada'):
                continue
            conferencia = situacao == 'concluida' and tarefa.get('exige_conferencia')
            if situacao == 'concluida' and not conferencia:
                continue
            vencimento = date.fromisoformat(tarefa['vencimento']) if tarefa.get('vencimento') else None
            atrasada = vencimento is not None and situacao != 'concluida' and vencimento < hoje
            vencendo = vencimento is not None and situacao != 'concluida' and hoje <= vencimento <= limite
            carimbo = tarefa.get('aguardando_desde') or tarefa.get('atualizada_em') or hoje.isoformat()
            dia_espera = data_salvador(carimbo)
            aguardando = situacao == 'aguardando_cliente' and (hoje - dia_espera).days > espera
            if not (atrasada or vencendo or conferencia or aguardando):
                continue
            setor = setores.get(tarefa['setor_id'])
            if not setor:
                continue
            titular = tarefa.get('responsavel_usuario_id')
            dono = store.responsavel_efetivo(setor['id'], titular, hoje) if titular else None
            chefe_id = setor.get('responsavel_usuario_id')
            chefe = store.responsavel_efetivo(setor['id'], chefe_id, hoje) if chefe_id else None
            destinos = {dono} if not conferencia else set()
            if chefe in ativos and ativos[chefe].get('pode_setor', True):
                destinos.add(chefe)
            for uid in destinos & ativos.keys():
                resumo = resumos.setdefault(uid, dict(usuario=ativos[uid], tarefas=[],
                    quantidades=dict(vencendo=0, atrasadas=0, conferencias=0, aguardando=0)))
                resumo['tarefas'].append(dict(tarefa, alerta_conferencia=bool(conferencia)))
                for chave, incluir in (('vencendo', vencendo), ('atrasadas', atrasada),
                                       ('conferencias', conferencia), ('aguardando', aguardando)):
                    resumo['quantidades'][chave] += int(bool(incluir))
        offset += len(pagina['itens'])
        if not pagina['itens'] or offset >= pagina['total']:
            break
    return resumos


def _mensagem(resumo, cfg, hoje):
    mensagem = EmailMessage()
    mensagem['From'] = cfg.remetente
    mensagem['To'] = resumo['usuario']['email']
    mensagem['Subject'] = f'Tarefas e prazos — {hoje:%d/%m/%Y}'
    linhas = ['Resumo interno de tarefas e prazos', f'Data: {hoje:%d/%m/%Y}', '']
    for tarefa in resumo['tarefas']:
        indicacao = 'aguarda conferência' if tarefa['alerta_conferencia'] else tarefa['situacao'].replace('_', ' ')
        intervalo = tarefa.get('origem', {}).get('intervalo', '')
        ocorrencia = f" | ocorrência {tarefa.get('ocorrencia', 1)} ({intervalo})" if intervalo else ''
        prazo = f"prazo {tarefa['vencimento']}" if tarefa.get('vencimento') else 'Sem vencimento'
        linhas.append(f"• {tarefa.get('cliente_nome', '')} — {tarefa['titulo']} | "
                      f"{prazo}{ocorrencia} | {indicacao}")
    linhas.extend(['', 'Consulte a aba Tarefas e prazos no sistema para registrar o andamento.'])
    mensagem.set_content('\n'.join(linhas))
    return mensagem


def enviar_resumos(store, usuarios, hoje, *, configuracao=None, smtp_factory=None):
    cfg = configuracao or ConfigSMTP.de_ambiente()
    resultados = {'ok': 0, 'falha': 0, 'desligado': 0, 'ja_registrado': 0}
    for uid, resumo in montar_resumos(store, usuarios, hoje).items():
        destino = str(resumo['usuario'].get('email') or '').strip()
        destino_valido = email_valido(destino)
        # O banco nao aceita endereco malformado. Mesmo assim a tentativa precisa
        # ter resultado e nao pode impedir o resumo dos demais destinatarios.
        if not store.reservar_envio(uid, hoje.isoformat(), destino if destino_valido else '', resumo['quantidades']):
            resultados['ja_registrado'] += 1
            continue
        resultado, erro = 'desligado', ''
        if cfg.ativo:
            if not destino_valido:
                resultado, erro = 'falha', 'EMAIL_DESTINATARIO_AUSENTE_OU_INVALIDO'
            else:
                try:
                    factory = smtp_factory or (smtplib.SMTP_SSL if cfg.tls == 'ssl' else smtplib.SMTP)
                    kwargs = {'timeout': 20}
                    if cfg.tls == 'ssl' and smtp_factory is None:
                        kwargs['context'] = ssl.create_default_context()
                    with factory(cfg.host, cfg.porta, **kwargs) as smtp:
                        if cfg.tls == 'starttls':
                            smtp.ehlo()
                            smtp.starttls(context=ssl.create_default_context())
                            smtp.ehlo()
                        if cfg.usuario:
                            smtp.login(cfg.usuario, cfg.senha)
                        smtp.send_message(_mensagem(resumo, cfg, hoje))
                    resultado = 'ok'
                except Exception:
                    # Nunca persistir a mensagem da exceção: servidores podem ecoar
                    # usuário, senha, endereço ou conversa SMTP nela.
                    resultado, erro = 'falha', 'FALHA_SMTP'
        store.finalizar_envio(uid, hoje.isoformat(), resultado, erro)
        resultados[resultado] += 1
    return resultados
