"""Evidencias ficticias no disco privado; sem cloud nem dados de producao."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas import qualidade_anexos as a

EML = (b'From: teste@example.invalid\r\nTo: equipe@example.invalid\r\n'
       b'Subject: Evidencia ficticia\r\nDate: Thu, 05 Nov 2026 12:00:00 -0300\r\n\r\nTeste.\r\n')

def recusar(fn, *args):
    try:
        fn(*args)
    except a.ErroConfiguracaoAnexos as exc:
        assert 'Armazenamento' in str(exc)
    else:
        raise AssertionError('Gravacao deveria ser recusada')

def main():
    # copy_tree abre cada ancestral com O_RDONLY/O_DIRECTORY. O TMPDIR do
    # executor passa por um ancestral 0711 do root, atravessavel mas nao legivel
    # pela conta de testes. /tmp e privado por PrivateTmp na unit de sandbox.
    raiz_temporaria = '/tmp' if os.name == 'posix' else None
    with TemporaryDirectory(prefix='qualidade_privado_sintetico_', dir=raiz_temporaria) as pasta:
        base = Path(pasta) / 'dados'
        base.mkdir()
        ambiente = dict(AUDITORIA_WEB_DADOS=str(base), AUDITORIA_QUALIDADE_ANEXOS_PRIVADO='1',
                        AUDITORIA_QUALIDADE_ANEXOS_LIMITE_MB='1', AUDITORIA_QUALIDADE_ANEXOS_RESERVA_MB='1')
        with patch.dict(os.environ, ambiente, clear=True):
            assert a.disponivel(), 'Modo privado explicito deve funcionar sem S3'
            assert not list(base.iterdir()), 'Consulta nao cria pastas nem trava'
            meta = a.salvar('evidencia.eml', EML)
            assert a.ler(meta) == EML
            destino = base / 'qualidade/anexos' / meta['chave_objeto'].split('/')[1]
            assert destino.read_bytes() == EML
            if os.name != 'nt':
                assert destino.stat().st_mode & 0o777 == 0o600
                assert destino.parent.stat().st_mode & 0o777 == 0o700
            # Restaura uma copia inteira dos dados, conservando chave e checksum.
            copia = Path(pasta) / 'restauracao'
            script = Path(__file__).resolve().parents[1] / 'devops/autodeploy/runner.py'
            spec = importlib.util.spec_from_file_location('backup_anexos_sinteticos', script)
            runner = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = runner
            spec.loader.exec_module(runner)
            if os.name == 'nt':
                shutil.copytree(base, copia)  # O executor real usa descritores POSIX.
            else:
                runner.copy_tree(base, copia)
            with patch.dict(os.environ, {'AUDITORIA_WEB_DADOS': str(copia)}):
                assert a.ler(meta) == EML
            assert meta['sha256'] == sha256(EML).hexdigest()
            with patch.object(a.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(10**9, 10**9, 0)):
                recusar(a.salvar, 'sem-espaco.eml', EML)
            assert a.ler(meta) == EML
            a.excluir(meta['chave_objeto'])
            # Quota inclusiva; falha nao apaga nem sobrescreve o objeto anterior.
            cheio = EML + b'x' * (1024 * 1024 - len(EML))
            limite = a.salvar('limite.eml', cheio)
            recusar(a.salvar, 'excedente.eml', EML)
            assert a.ler(limite) == cheio
            a.excluir(limite['chave_objeto'])
            # Duas threads disputam mais de metade da mesma quota.
            medio = EML + b'x' * (600 * 1024 - len(EML))
            def enviar(_):
                try:
                    return a.salvar('concorrente.eml', medio)
                except a.ErroConfiguracaoAnexos:
                    return None
            with ThreadPoolExecutor(max_workers=2) as executor:
                respostas = list(executor.map(enviar, range(2)))
            sucesso = [r for r in respostas if r]
            assert len(sucesso) == 1 and a.ler(sucesso[0]) == medio
            a.excluir(sucesso[0]['chave_objeto'])
            # Arquivo estranho na pasta impede gravacao; nao e' ignorado na quota.
            inesperado = destino.parent / 'arquivo-inesperado'
            inesperado.write_bytes(b'preservar')
            recusar(a.salvar, 'e.eml', EML)
            assert inesperado.read_bytes() == b'preservar'
            inesperado.unlink()
            with patch.object(a, '_LIMITE_OBJETOS', 1):
                unico = a.salvar('unico.eml', EML)
                recusar(a.salvar, 'segundo.eml', EML)
                assert a.ler(unico) == EML
                a.excluir(unico['chave_objeto'])
            # Link/arquivo irregular nunca deve ser tratado como evidencia.
            link = destino.parent / ('a' * 32)
            externo = Path(pasta) / 'fora.eml'
            externo.write_bytes(EML)
            try:
                link.symlink_to(externo)
            except OSError:
                # Windows sem permissao de symlink: verifica o caso diretorio.
                link.mkdir()
                recusar(a.salvar, 'e.eml', EML)
                link.rmdir()
            else:
                recusar(a.salvar, 'e.eml', EML)
                link.unlink()
            assert externo.read_bytes() == EML
        for extra in ({'AUDITORIA_QUALIDADE_ANEXOS_LOCAL': '1'},
                      {'AUDITORIA_QUALIDADE_S3_BUCKET': 'bucket-existente'},
                      {'AUDITORIA_QUALIDADE_ANEXOS_LIMITE_MB': '0'},
                      {'AUDITORIA_QUALIDADE_ANEXOS_RESERVA_MB': '-1'},
                      {'AUDITORIA_WEB_DADOS': 'relativo'}):
            with patch.dict(os.environ, dict(ambiente, **extra), clear=True):
                assert not a.disponivel()
        # Trava funciona entre processos reais, nao apenas entre threads.
        programa = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from auditoria_fiscal.ferramentas import qualidade_anexos as a
conteudo = bytes.fromhex(sys.argv[2])
try:
    a.salvar('processo.eml', conteudo)
except a.ErroConfiguracaoAnexos:
    raise SystemExit(3)
'''
        env = {k: v for k, v in os.environ.items() if not k.startswith('AUDITORIA_')}
        env.update(ambiente)
        # Conteudo grande e' montado no filho para nao exceder a linha de comando.
        programa = programa.replace("conteudo = bytes.fromhex(sys.argv[2])", "conteudo = bytes.fromhex(sys.argv[2]); conteudo += b'x' * (600 * 1024 - len(conteudo))")
        args = [sys.executable, '-B', '-c', programa, str(Path(a.__file__).parents[2]), EML.hex()]
        processos = [subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        saidas = [p.communicate(timeout=20) for p in processos]
        assert sorted(p.returncode for p in processos) == [0, 3], saidas
        with patch.dict(os.environ, ambiente, clear=True):
            arquivos = [p for p in destino.parent.iterdir() if p.name != '.gravacao.lock']
            assert len(arquivos) == 1 and arquivos[0].stat().st_size == 600 * 1024
    print('OK - anexos privados: quota, reserva, concorrencia, integridade e restauracao')

if __name__ == '__main__':
    main()
