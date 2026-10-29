"""Identificacao operacional do checkout, sem dados do repositorio na resposta.

O lifespan decide quando capturar e guardar o resultado. Esta leitura nao atesta
os modulos ja carregados nem permite declarar uma revisao por configuracao.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


_SHA_COMPLETO = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
_TIMEOUT_SEGUNDOS = 2


def identificar_versao(raiz: str | os.PathLike) -> dict:
    """Retorna apenas SHA completo, origem e estado da arvore observados juntos."""
    indisponivel = {'sha': None, 'origem': 'indisponivel', 'arvore': 'desconhecida'}
    try:
        projeto = Path(raiz).resolve(strict=True)
        if not projeto.is_dir():
            return indisponivel
        # Variaveis Git herdadas podem apontar para outro indice/repositorio.
        ambiente = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        ambiente['GIT_TERMINAL_PROMPT'] = '0'

        def git(*argumentos):
            return subprocess.run(
                ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', *argumentos],
                cwd=str(projeto), env=ambiente, shell=False, check=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', timeout=_TIMEOUT_SEGUNDOS,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            ).stdout

        topo = git('rev-parse', '--show-toplevel').rstrip('\r\n')
        if not topo or not projeto.samefile(topo):
            return indisponivel
        antes = git('rev-parse', '--verify', 'HEAD^{commit}').strip().lower()
        if not _SHA_COMPLETO.fullmatch(antes):
            return indisponivel
        estado = git('status', '--porcelain=v1', '-z', '--untracked-files=normal', '--ignore-submodules=none')
        depois = git('rev-parse', '--verify', 'HEAD^{commit}').strip().lower()
        if antes != depois:
            return indisponivel
        return {'sha': antes, 'origem': 'git', 'arvore': 'alterada' if estado else 'limpa'}
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, TypeError, RuntimeError):
        # Nem stderr, mensagem da excecao, caminhos ou nomes de arquivos saem.
        return indisponivel
