"""Contrato SMTP do controlador; somente arquivos e processos simulados."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import runpy
import stat

ROOT = Path(__file__).resolve().parents[1]
ad = SimpleNamespace(**runpy.run_path(str(ROOT / 'devops/autodeploy/runner.py')))
BASE = dict(schema_version=1, repository='/srv/repo', repository_url='https://github.com/Komunick/auditoria-JB.git',
            venv='/srv/repo/.venv', data_dir='/srv/data', service='auditoria-jb.service', control_plane_digest='a'*40)
ENV = dict(AUDITORIA_SMTP_HOST='smtp.example.test', AUDITORIA_SMTP_PORTA='465',
           AUDITORIA_SMTP_USUARIO='sender@example.test', AUDITORIA_SMTP_SENHA='synthetic-only-secret',
           AUDITORIA_SMTP_REMETENTE='sender@example.test', AUDITORIA_SMTP_TLS='ssl')
PATH = '/etc/auditoria-jb/smtp.env'


def rejects(fn, code):
    try:
        fn()
    except ad.DeployError as exc:
        assert exc.code == code, exc.code
        assert ENV['AUDITORIA_SMTP_SENHA'] not in str(exc)
    else:
        raise AssertionError('Aceitou configuracao insegura: ' + code)


def main():
    off = ad.Config.from_dict(BASE)
    assert off.smtp_env is None
    on = ad.Config.from_dict(dict(BASE, smtp_env=PATH, secret_paths=[PATH]))
    for changes in (dict(smtp_env=True), dict(smtp_env=PATH),
                    dict(smtp_env=PATH, secret_paths=[PATH], configuration_paths=['/etc']),
                    dict(smtp_env='/srv/runtime/smtp.env', secret_paths=['/srv/runtime/smtp.env'], venv='/srv/runtime'),
                    dict(smtp_env='/srv/data/smtp.env', secret_paths=['/srv/data/smtp.env'])):
        rejects(lambda: ad.Config.from_dict(dict(BASE, **changes)), 'config_smtp')
    values = {k.encode(): v.encode() for k, v in ENV.items()}
    raw = '\n'.join(k+'='+v for k,v in ENV.items()).encode()
    assert ad.parse_smtp_environment(raw) == values
    for tls, port in (('ssl', '465'), ('starttls', '587')):
        env = dict(ENV, AUDITORIA_SMTP_TLS=tls, AUDITORIA_SMTP_PORTA=port)
        assert ad.parse_smtp_environment('\n'.join(k+'='+v for k,v in env.items()).encode())
    for change in ({'AUDITORIA_SMTP_TLS':'none'}, {'AUDITORIA_SMTP_PORTA':'25'},
                   {'AUDITORIA_SMTP_PORTA':'587'}, {'AUDITORIA_SMTP_SENHA':''},
                   {'AUDITORIA_SMTP_USUARIO':''}, {'AUDITORIA_SMTP_HOST':'bad host'},
                   {'AUDITORIA_SMTP_EXTRA':'x'}, {'AUDITORIA_SMTP_REMETENTE':'bad'}):
        bad = '\n'.join(k+'='+v for k,v in dict(ENV, **change).items()).encode()
        rejects(lambda: ad.parse_smtp_environment(bad), 'smtp_environment_invalid')
    for bad in (raw+b'\nAUDITORIA_SMTP_TLS=ssl', raw.replace(b'=ssl',b'="ssl"'),
                raw.replace(b'=ssl',b'=ss\\l'), b'X'*8193, raw.replace(b'=ssl',b'=\xff')):
        rejects(lambda: ad.parse_smtp_environment(bad), 'smtp_environment_invalid')
    ad.validate_smtp_environment(off, {})
    rejects(lambda: ad.validate_smtp_environment(off, values), 'service_environment')
    rejects(lambda: ad.validate_smtp_environment(off, {b'AUDITORIA_SMTP_HOST': b''}), 'service_environment')
    with patch.object(Path, 'lstat', side_effect=FileNotFoundError):
        rejects(lambda: ad.validate_smtp_environment(on, values), 'smtp_file_unsafe')
    # Root-owned private file contract, no actual root files are read.
    file_info = SimpleNamespace(st_mode=stat.S_IFREG|0o600, st_uid=0, st_nlink=1, st_size=len(raw))
    dir_info = SimpleNamespace(st_mode=stat.S_IFDIR|0o700, st_uid=0)
    def info(path): return file_info if str(path).replace('\\','/') == PATH else dir_info
    with patch.object(Path, 'lstat', info), patch.object(Path, 'read_bytes', return_value=raw):
        ad.validate_smtp_environment(on, values)
        for mode, uid in ((stat.S_IFREG|0o644,0),(stat.S_IFREG|0o600,1000),(stat.S_IFLNK|0o600,0)):
            file_info.st_mode, file_info.st_uid = mode, uid
            rejects(lambda: ad.validate_smtp_environment(on, values), 'smtp_file_unsafe')
        file_info.st_mode, file_info.st_uid = stat.S_IFREG|0o600, 0
        dir_info.st_mode = stat.S_IFDIR|0o755
        rejects(lambda: ad.validate_smtp_environment(on, values), 'smtp_file_unsafe')
        dir_info.st_mode = stat.S_IFDIR|0o700
        rejects(lambda: ad.validate_smtp_environment(on, {}), 'service_environment')
        rejects(lambda: ad.validate_smtp_environment(on, {**values, b'AUDITORIA_SMTP_EXTRA': b'x'}), 'service_environment')
        changed = dict(values); changed[b'AUDITORIA_SMTP_SENHA'] = b'other'
        rejects(lambda: ad.validate_smtp_environment(on, changed), 'service_environment')
    # Real health path must call validation before HTTP (including default off).
    host = object.__new__(ad.Host); host.c = on
    host.service = lambda: dict(MainPID='42', ActiveState='active', SubState='running')
    process = b'AUDITORIA_COFRE_CHAVE=fake\0AUDITORIA_WEB_DADOS=/srv/data\0' + raw.replace(b'\n',b'\0')
    globals_ = ad.Host.health.__globals__
    with patch.object(Path, 'read_bytes', return_value=process), patch.dict(globals_,
            validate_smtp_environment=lambda c,v: (_ for _ in ()).throw(ad.DeployError('probe'))):
        rejects(host.health, 'probe')
    command = ad.sandbox_command(on, '/work', ['python'], 'smtp', 30)
    assert '--property=InaccessiblePaths='+PATH in command
    assert not any(ENV['AUDITORIA_SMTP_SENHA'] in item for item in command)
    print('OK - SMTP opt-in, TLS, arquivo privado, ambiente efetivo e isolamento')


if __name__ == '__main__':
    main()
