"""Identificacao operacional: somente repositorios e metadados sinteticos."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.web import versao


INDISPONIVEL = {'sha': None, 'origem': 'indisponivel', 'arvore': 'desconhecida'}


def git(raiz, *argumentos):
    ambiente = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    return subprocess.run(
        ['git', '-c', 'user.name=Teste Sintetico', '-c', 'user.email=teste@example.invalid',
         '-c', 'commit.gpgSign=false', '-c', f'core.hooksPath={raiz / "sem_hooks"}', *argumentos],
        cwd=raiz, env=ambiente, check=True, capture_output=True, text=True,
        encoding='utf-8', timeout=10, shell=False).stdout.strip()


def repositorios_reais():
    with tempfile.TemporaryDirectory(prefix='versao_sintetica_') as pasta:
        base = Path(pasta)
        raiz = base / 'projeto com espacos'
        raiz.mkdir()
        git(raiz, 'init', '-q')
        assert versao.identificar_versao(raiz) == INDISPONIVEL, 'HEAD ainda inexistente'
        (raiz / '.gitignore').write_text('ignorado/\n', encoding='utf-8')
        arquivo = raiz / 'arquivo.txt'
        arquivo.write_text('original\n', encoding='utf-8')
        git(raiz, 'add', '.gitignore', 'arquivo.txt')
        git(raiz, 'commit', '-qm', 'Fixture sintetica')
        sha = git(raiz, 'rev-parse', 'HEAD')
        limpa = {'sha': sha, 'origem': 'git', 'arvore': 'limpa'}
        alterada = dict(limpa, arvore='alterada')
        assert versao.identificar_versao(str(raiz)) == limpa

        (raiz / 'ignorado').mkdir()
        (raiz / 'ignorado' / 'cache.txt').write_text('sintetico', encoding='utf-8')
        assert versao.identificar_versao(raiz) == limpa
        arquivo.write_text('modificado\n', encoding='utf-8')
        assert versao.identificar_versao(raiz) == alterada
        git(raiz, 'add', 'arquivo.txt')
        assert versao.identificar_versao(raiz) == alterada, 'Alteracao staged tambem conta'
        git(raiz, 'restore', '--staged', '--worktree', 'arquivo.txt')
        novo = raiz / 'novo.txt'
        novo.write_text('nao rastreado\n', encoding='utf-8')
        assert versao.identificar_versao(raiz) == alterada
        novo.unlink()
        assert versao.identificar_versao(raiz) == limpa

        subpasta = raiz / 'src'
        subpasta.mkdir()
        assert versao.identificar_versao(subpasta) == INDISPONIVEL, 'Nao identificar repositorio pai'
        assert versao.identificar_versao(base) == INDISPONIVEL
        assert versao.identificar_versao(base / 'ausente') == INDISPONIVEL
        assert versao.identificar_versao(arquivo) == INDISPONIVEL
        worktree = base / 'checkout separado'
        git(raiz, 'worktree', 'add', '--detach', str(worktree), 'HEAD')
        assert versao.identificar_versao(worktree) == limpa, 'Worktree usa arquivo .git'

        # Variaveis do processo nao podem redirecionar o checkout observado.
        with patch.dict(os.environ, {'GIT_DIR': str(base / 'git_inexistente'),
                                     'GIT_WORK_TREE': str(base), 'GIT_INDEX_FILE': str(base / 'indice')}):
            assert versao.identificar_versao(raiz) == limpa


def falhas_e_corrida():
    with tempfile.TemporaryDirectory(prefix='versao_respostas_') as pasta:
        raiz = Path(pasta).resolve()
        sha = 'a' * 40

        def resposta(texto):
            return subprocess.CompletedProcess(['git'], 0, stdout=texto, stderr=None)

        respostas = [resposta(str(raiz) + '\n'), resposta(sha + '\n'), resposta(''), resposta(sha + '\n')]
        with patch.object(versao.subprocess, 'run', side_effect=respostas) as executar:
            assert versao.identificar_versao(raiz) == {'sha': sha, 'origem': 'git', 'arvore': 'limpa'}
            for chamada in executar.call_args_list:
                argumentos, opcoes = chamada.args[0], chamada.kwargs
                assert isinstance(argumentos, list) and argumentos[0] == 'git'
                assert opcoes.get('shell') is False and 0 < opcoes['timeout'] <= 3
                assert Path(opcoes['cwd']).resolve() == raiz
                assert opcoes['stderr'] == subprocess.DEVNULL
                assert opcoes['stdin'] == subprocess.DEVNULL

        for falha in (FileNotFoundError('caminho secreto'), PermissionError('caminho secreto'),
                      subprocess.TimeoutExpired(['git'], 2, stderr='segredo'),
                      subprocess.CalledProcessError(128, ['git'], stderr='segredo')):
            for etapa in range(4):
                with patch.object(versao.subprocess, 'run', side_effect=respostas[:etapa] + [falha]):
                    assert versao.identificar_versao(raiz) == INDISPONIVEL
        for invalido in ('', 'a' * 7, 'g' * 40, sha + '\nramo-ou-caminho', 'a' * 41):
            with patch.object(versao.subprocess, 'run', side_effect=[respostas[0], resposta(invalido)]):
                assert versao.identificar_versao(raiz) == INDISPONIVEL
        with patch.object(versao.subprocess, 'run', side_effect=respostas[:3] + [resposta('b' * 40)]):
            assert versao.identificar_versao(raiz) == INDISPONIVEL, 'Troca de HEAD durante captura'
        with patch.object(versao.subprocess, 'run', side_effect=[resposta(str(raiz.parent))]):
            assert versao.identificar_versao(raiz) == INDISPONIVEL
        # Repositorios Git com SHA-256 tambem retornam o identificador completo.
        sha256 = 'c' * 64
        with patch.object(versao.subprocess, 'run', side_effect=[respostas[0], resposta(sha256), resposta('?? novo\0'), resposta(sha256)]):
            assert versao.identificar_versao(raiz) == {'sha': sha256, 'origem': 'git', 'arvore': 'alterada'}


def main():
    repositorios_reais()
    falhas_e_corrida()
    print('OK - versao Git, arvore, worktree, raiz exata, indisponibilidade e corrida de HEAD')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
