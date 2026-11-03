"""Executor valida schema da qualidade em cópia, preservando a fonte sintética."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from unittest.mock import patch

raiz=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(raiz/'src'))
from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore

spec=importlib.util.spec_from_file_location('runner_qualidade',raiz/'devops/autodeploy/runner.py')
ad=importlib.util.module_from_spec(spec); sys.modules[spec.name]=ad; spec.loader.exec_module(ad)


def main():
    with tempfile.TemporaryDirectory(prefix='qa_migracao_') as pasta:
        base=Path(pasta); snapshot=base/'snapshot'; dados=snapshot/'data'; dados.mkdir(parents=True)
        for nome in ad.DATABASES:
            with closing(sqlite3.connect(dados/nome)) as conn:
                conn.execute('CREATE TABLE legado(id INTEGER PRIMARY KEY, valor TEXT)')
                conn.execute("INSERT INTO legado VALUES(1,'sintético')")
                conn.commit()
        s=TarefasStore(dados/'clientes.db'); s.fechar()
        antes=ad.sqlite_inventory(dados)
        h=ad.Host.__new__(ad.Host); h.work=base/'work'; h.work.mkdir()
        h.deadline=None; h.uid=None; h.gid=None; h.chown=lambda p:None
        def sandbox(cmd,timeout):
            if '-c' in cmd:
                env={k:v for k,v in os.environ.items() if not k.startswith('AUDITORIA_')}
                env['PYTHONPATH']=str(raiz/'src')
                subprocess.run([sys.executable,*cmd[1:]],env=env,check=True,capture_output=True)
                return ''
            if '--helper-integrity' in cmd:
                ad.validate_sqlite(Path(cmd[-1])); return ''
            directory=Path(cmd[cmd.index('--helper-inventory')+1])
            baseline=json.loads(Path(cmd[-1]).read_text()) if '--inventory-baseline' in cmd else None
            return json.dumps(ad.sqlite_inventory(directory,baseline))
        h.sandbox=sandbox
        # Copiador Linux no executor real; aqui só o transporte é substituído.
        with patch.object(ad,'copy_tree',side_effect=lambda a,b,**kw:shutil.copytree(a,b)):
            h.validate(snapshot,migrate=True)
        assert ad.sqlite_inventory(dados)==antes, 'Fonte do snapshot foi alterada'
        esperado=h.expected_inventory['clientes.db']
        assert esperado['schema']==4, esperado['schema']
        assert {'qualidade_ocorrencia','qualidade_plano','qualidade_horas','qualidade_anexo','qualidade_evento'} <= esperado['tables'].keys()
        assert esperado['tables']['qualidade_evento']['immutable']
        assert esperado['tables']['qualidade_anexo']['immutable']
        ad.compare_inventory(antes,h.expected_inventory)
        print('OK - migração do executor valida qualidade em cópia e preserva dados anteriores')

if __name__=='__main__': main()
