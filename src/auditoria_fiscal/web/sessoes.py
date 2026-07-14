"""Sessoes de trabalho e jobs da versao web.

Uma SESSAO DE TRABALHO equivale ao estado que cada aba do desktop mantinha em
memoria (notas carregadas, resultado da comparacao, linhas extraidas, base de
produtos auditada...): uploads em disco (dados_web/sessoes/<id>/) + um dict de
estado em memoria. Um JOB e um processamento em thread (carga de SPED/XMLs,
comparacao, auditoria) com status consultavel por polling — o equivalente aos
QThread/Worker do desktop. Reiniciar o servidor perde jobs e estados em
memoria, nunca os uploads (edge case da spec).
"""

from __future__ import annotations

import os
import secrets
import shutil
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException, UploadFile

from .infra import pasta_sessoes

_MAX_UPLOAD_MB = int(os.environ.get("AUDITORIA_WEB_MAX_UPLOAD_MB", "300"))


@dataclass
class SessaoTrabalho:
    id: str
    ferramenta: str
    usuario: str
    criada_em: str
    pasta: str
    estado: dict[str, Any] = field(default_factory=dict)
    trava: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class Job:
    id: str
    sessao_id: str
    descricao: str
    status: str = "executando"        # executando | concluido | erro
    erro: str = ""
    resultado: dict[str, Any] | None = None


_sessoes: dict[str, SessaoTrabalho] = {}
_jobs: dict[str, Job] = {}
_trava = threading.Lock()


def criar_sessao(ferramenta: str, usuario: str) -> SessaoTrabalho:
    sessao_id = secrets.token_urlsafe(12)
    pasta = os.path.join(pasta_sessoes(), sessao_id)
    os.makedirs(pasta, exist_ok=True)
    sessao = SessaoTrabalho(
        id=sessao_id, ferramenta=ferramenta, usuario=usuario,
        criada_em=datetime.now().strftime("%d/%m/%Y %H:%M"), pasta=pasta)
    with _trava:
        _sessoes[sessao_id] = sessao
    return sessao


def obter_sessao(sessao_id: str) -> SessaoTrabalho:
    sessao = _sessoes.get(sessao_id or "")
    if sessao is None:
        raise HTTPException(
            status_code=404,
            detail="Sessao de trabalho nao encontrada (o servidor pode ter "
                   "sido reiniciado). Envie os arquivos novamente.")
    return sessao


def descartar_sessao(sessao_id: str) -> None:
    with _trava:
        sessao = _sessoes.pop(sessao_id, None)
    if sessao is not None:
        shutil.rmtree(sessao.pasta, ignore_errors=True)


def _nome_seguro(nome: str) -> str:
    base = os.path.basename(nome or "").strip().replace("\\", "_")
    return base or "arquivo"


async def salvar_upload(sessao: SessaoTrabalho, arquivo: UploadFile,
                        subpasta: str = "") -> str:
    """Grava um upload na pasta da sessao. Zips sao expandidos (XMLs em
    subpastas — ex.: o ano inteiro com os meses — mantem a estrutura, pois a
    leitura de XMLs ja e recursiva)."""
    destino_dir = os.path.join(sessao.pasta, subpasta) if subpasta else sessao.pasta
    os.makedirs(destino_dir, exist_ok=True)
    nome = _nome_seguro(arquivo.filename)
    destino = os.path.join(destino_dir, nome)

    tamanho = 0
    with open(destino, "wb") as saida:
        while True:
            pedaco = await arquivo.read(1024 * 1024)
            if not pedaco:
                break
            tamanho += len(pedaco)
            if tamanho > _MAX_UPLOAD_MB * 1024 * 1024:
                saida.close()
                os.remove(destino)
                raise HTTPException(
                    status_code=413,
                    detail=f"Arquivo maior que {_MAX_UPLOAD_MB} MB.")
            saida.write(pedaco)

    if nome.lower().endswith(".zip"):
        pasta_zip = destino[:-4]
        try:
            with zipfile.ZipFile(destino) as zf:
                for membro in zf.infolist():
                    alvo = os.path.realpath(os.path.join(
                        pasta_zip, membro.filename))
                    if not alvo.startswith(os.path.realpath(pasta_zip)):
                        raise HTTPException(
                            status_code=422,
                            detail="Zip invalido (caminhos fora da pasta).")
                zf.extractall(pasta_zip)
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=422, detail="Arquivo .zip invalido.") from exc
        finally:
            if os.path.isfile(destino):
                os.remove(destino)
        return pasta_zip
    return destino


def iniciar_job(sessao: SessaoTrabalho, descricao: str,
                funcao: Callable[[], dict[str, Any] | None]) -> Job:
    """Roda `funcao` numa thread; o resultado (dict) fica no job."""
    job = Job(id=secrets.token_urlsafe(8), sessao_id=sessao.id,
              descricao=descricao)
    with _trava:
        _jobs[job.id] = job

    def _executar() -> None:
        try:
            job.resultado = funcao() or {}
            job.status = "concluido"
        except Exception as exc:  # noqa: BLE001 — espelha os Workers do desktop
            job.erro = f"{type(exc).__name__}: {exc}"
            job.status = "erro"

    threading.Thread(target=_executar, daemon=True).start()
    return job


def obter_job(job_id: str) -> Job:
    job = _jobs.get(job_id or "")
    if job is None:
        raise HTTPException(status_code=404, detail="Job nao encontrado.")
    return job
