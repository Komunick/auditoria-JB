"""Transportes simulados: jamais conectar ao provedor ou enviar email real."""
import smtplib
import ssl
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from test_alertas_email import preparar_store_real, TarefasStore, ConfigSMTP, enviar_resumos


def main():
    users = [dict(id=i, nome='Pessoa Sintetica', email=f'p{i}@example.test', ativo=True) for i in range(1,5)]
    secret = 'synthetic-password-do-not-log'
    for tls in ('ssl', 'starttls'):
        for failure in (None, 'tls', 'auth', 'send', 'quit'):
            calls = []
            class Transport:
                def __init__(self, host, port, **kwargs):
                    calls.append('connect')
                    assert kwargs['timeout'] == 20
                    if tls == 'ssl':
                        context = kwargs['context']
                        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
                        if failure == 'tls': raise ssl.SSLError(secret)
                def __enter__(self): return self
                def __exit__(self, *args):
                    if failure == 'quit': raise OSError(secret)
                def ehlo(self): calls.append('ehlo')
                def starttls(self, *, context):
                    calls.append('tls')
                    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
                    if failure == 'tls': raise ssl.SSLError(secret)
                def login(self, user, password):
                    calls.append('auth')
                    assert user == 'sender@example.test' and password == secret
                    if tls == 'starttls': assert calls[-3:] == ['tls','ehlo','auth']
                    if failure == 'auth': raise smtplib.SMTPAuthenticationError(535, secret.encode())
                def send_message(self, message):
                    calls.append('send')
                    assert calls[-2] == 'auth'
                    assert message['To'] in ('p3@example.test','p4@example.test')
                    if failure == 'send': raise smtplib.SMTPServerDisconnected(secret)
            with tempfile.TemporaryDirectory(prefix='smtp_synthetic_') as folder:
                path = str(Path(folder)/'clientes.db')
                store, _ = preparar_store_real(path)
                cfg = ConfigSMTP(host='smtp.example.test', porta=465 if tls=='ssl' else 587,
                                 usuario='sender@example.test', senha=secret, remetente='sender@example.test', tls=tls)
                try:
                    with patch('smtplib.SMTP_SSL' if tls=='ssl' else 'smtplib.SMTP', Transport):
                        result = enviar_resumos(store, users, date(2026,10,27), configuracao=cfg)
                    assert result['falha' if failure else 'ok'] == 2
                    if failure in ('tls','auth'): assert 'send' not in calls
                    assert secret not in repr(store.listar_envios())
                finally: store.fechar()
                # Reabrir o banco simula reinício; até resultado incerto no QUIT
                # conserva a reserva, sem repetir mensagem já aceita pelo servidor.
                store = TarefasStore(path)
                try:
                    with patch('smtplib.SMTP_SSL', side_effect=AssertionError('envio duplicado')), \
                         patch('smtplib.SMTP', side_effect=AssertionError('envio duplicado')):
                        again = enviar_resumos(store, users, date(2026,10,27), configuracao=cfg)
                    assert again['ja_registrado'] == 2 and again['falha'] == 0
                finally: store.fechar()
    print('OK - SSL/STARTTLS, autenticacao, falhas e reservas persistentes sem duplicacao')


if __name__ == '__main__': main()
