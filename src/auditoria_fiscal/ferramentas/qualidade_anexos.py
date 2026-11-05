"""Evidências privadas da qualidade; objetos imutáveis, sem dependência da web.

O modo local é exclusivo de desenvolvimento. O modo privado de servidor exige
habilitacao explicita e inclui quota e reserva de disco, sem fallback para S3.
Na implantação, as credenciais S3 seguem a cadeia padrão do SDK e nunca entram nos
metadados públicos. A verificação de formato não substitui inspeção antimalware.
"""
from contextlib import contextmanager, nullcontext
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from hashlib import sha256
import hmac
import importlib
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import threading
import time
import unicodedata
from urllib.parse import urlsplit
from uuid import uuid4
import warnings


LIMITE_BYTES = 10 * 1024 * 1024
LIMITE_PIXELS = 25_000_000
MIMES = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg',
         '.jpeg': 'image/jpeg', '.eml': 'message/rfc822'}
_CHAVE = re.compile(r'qualidade/[0-9a-f]{32}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_INDISPONIVEL = 'Armazenamento de evidências indisponível. Confira a configuração.'
_TRAVA_PRIVADA = threading.Lock()
_LIMITE_OBJETOS = 10_000


class ErroAnexo(ValueError):
    """Nome, formato, tamanho ou metadados não permitidos."""


class ErroConfiguracaoAnexos(RuntimeError):
    """Configuração ausente ou armazenamento sem resposta; mensagem sem segredos."""


class ErroIntegridadeAnexo(ErroConfiguracaoAnexos):
    """Objeto armazenado não confere com o recibo imutável."""


def _imagem(conteudo, extensao):
    formato = 'PNG' if extensao == '.png' else 'JPEG'
    if formato == 'PNG':
        if (not conteudo.startswith(b'\x89PNG\r\n\x1a\n') or len(conteudo) < 33
                or conteudo[12:16] != b'IHDR'
                or not conteudo.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82')):
            raise ErroAnexo('PNG inválido ou incompleto.')
        # Limita antes de abrir: alguns formatos animados alocam na abertura.
        largura, altura = struct.unpack('>II', conteudo[16:24])
        if not largura or not altura or largura * altura > LIMITE_PIXELS:
            raise ErroAnexo('Imagem excede o limite de resolução.')
    elif not conteudo.startswith(b'\xff\xd8\xff') or not conteudo.endswith(b'\xff\xd9'):
        raise ErroAnexo('JPEG inválido ou incompleto.')
    try:
        from PIL import Image
    except ImportError:
        raise ErroConfiguracaoAnexos(_INDISPONIVEL) from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(conteudo), formats=[formato]) as img:
                if img.width * img.height > LIMITE_PIXELS or getattr(img, 'n_frames', 1) != 1:
                    raise ValueError('Resolução ou animação não permitida')
                img.verify()
            # verify() de JPEG valida cabeçalhos, mas só load() detecta truncamentos.
            with Image.open(BytesIO(conteudo), formats=[formato]) as img:
                img.load()
    except Exception:
        raise ErroAnexo('Imagem inválida, incompleta ou com resolução excessiva.') from None


def _pdf(conteudo):
    """Validação estrutural mínima; não executa ações nem extrai conteúdo do PDF."""
    inicio = re.match(rb'%PDF-(?:1\.[0-7]|2\.0)(?:\r\n|\r|\n)', conteudo)
    fim = re.search(rb'startxref\s+(\d{1,12})\s+%%EOF\s*\Z', conteudo)
    if not inicio or not fim:
        raise ErroAnexo('PDF inválido ou incompleto.')
    posicao = int(fim.group(1))
    xref = conteudo[posicao:fim.start()]
    tabela = re.match(rb'xref\s', xref)
    fluxo = (re.match(rb'\d+\s+\d+\s+obj\s*<<', xref)
             and re.search(rb'/Type\s*/XRef\b', xref[:xref.find(b'stream')]))
    if (posicao < len(inicio.group()) or not (tabela or fluxo)
            or not re.search(rb'/Root\s+\d+\s+\d+\s+R\b', xref)
            or not re.search(rb'\d{1,10}\s+\d{1,5}\s+obj\b', conteudo)
            or not re.search(rb'\bendobj\b', conteudo)):
        raise ErroAnexo('Estrutura do PDF inválida ou incompleta.')


def _email(conteudo):
    if b'\r\n\r\n' not in conteudo and b'\n\n' not in conteudo:
        raise ErroAnexo('EML deve conter cabeçalhos e corpo da mensagem.')
    try:
        mensagem = BytesParser(policy=policy.default).parsebytes(conteudo)
        if any(parte.defects for parte in mensagem.walk()):
            raise ValueError('Estrutura inválida')
        for campo in ['From', 'To', 'Subject', 'Date']:
            if len(mensagem.get_all(campo, [])) != 1 or not str(mensagem[campo]).strip():
                raise ValueError('Cabeçalhos ausentes ou duplicados')
            if getattr(mensagem[campo], 'defects', ()):
                raise ValueError('Cabeçalho inválido')
        for campo in ['From', 'To']:
            enderecos = mensagem[campo].addresses
            if not enderecos or any(not e.username or not e.domain for e in enderecos):
                raise ValueError('Endereço inválido')
        if parsedate_to_datetime(str(mensagem['Date'])) is None:
            raise ValueError('Data inválida')
    except Exception:
        raise ErroAnexo('EML inválido: confira From, To, Subject, Date e o corpo.') from None


def validar_arquivo(nome, conteudo):
    if (not isinstance(nome, str) or not nome or len(nome) > 200 or nome != nome.strip()
            or nome.startswith('.') or any(c in nome for c in '/\\:')
            or any(unicodedata.category(c) in {'Cc', 'Cf', 'Cs'} for c in nome)):
        raise ErroAnexo('Informe apenas o nome original do arquivo, sem caminho.')
    extensao = Path(nome).suffix.lower()
    if extensao not in MIMES:
        raise ErroAnexo('São permitidos PDF, PNG, JPEG e EML.')
    if not isinstance(conteudo, bytes) or not 0 < len(conteudo) <= LIMITE_BYTES:
        raise ErroAnexo('O arquivo deve ter conteúdo e no máximo 10 MiB.')
    if extensao in {'.png', '.jpg', '.jpeg'}:
        _imagem(conteudo, extensao)
    elif extensao == '.pdf':
        _pdf(conteudo)
    else:
        _email(conteudo)
    return {'nome': nome, 'mime': MIMES[extensao], 'tamanho': len(conteudo),
            'sha256': sha256(conteudo).hexdigest()}


def _pasta(dados, criar=False):
    base = Path(dados)
    if not base.is_absolute():
        raise ErroConfiguracaoAnexos(_INDISPONIVEL)
    base = base.resolve()
    pasta = base / 'qualidade' / 'anexos'
    for parte in [pasta.parent, pasta]:
        if parte.is_symlink() or (parte.exists() and not parte.is_dir()):
            raise ErroConfiguracaoAnexos(_INDISPONIVEL)
        if not parte.resolve().is_relative_to(base):
            raise ErroConfiguracaoAnexos(_INDISPONIVEL)
    if criar:
        pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
        pasta.chmod(0o700)
    return pasta


def _configuracao():
    try:
        if os.getenv('AUDITORIA_QUALIDADE_ANEXOS_PRIVADO') == '1':
            if (os.getenv('AUDITORIA_QUALIDADE_ANEXOS_LOCAL') == '1'
                    or any(os.getenv('AUDITORIA_QUALIDADE_S3_' + k, '').strip()
                           for k in ('BUCKET', 'ENDPOINT', 'REGION'))):
                raise ValueError('Modos de armazenamento conflitantes')
            dados = os.getenv('AUDITORIA_WEB_DADOS', '').strip()
            if not dados:
                raise ValueError('Dados nao configurados')
            def limite(nome):
                valor = os.getenv('AUDITORIA_QUALIDADE_ANEXOS_' + nome + '_MB', '1024')
                if not re.fullmatch(r'[0-9]{1,6}', valor) or not 1 <= int(valor) <= 102400:
                    raise ValueError('Limite de armazenamento invalido')
                return int(valor) * 1024 * 1024
            return {'modo': 'privado', 'dados': dados, 'pasta': _pasta(dados),
                    'limite_bytes': limite('LIMITE'), 'reserva_bytes': limite('RESERVA')}
        if os.getenv('AUDITORIA_QUALIDADE_ANEXOS_LOCAL') == '1':
            dados = os.getenv('AUDITORIA_WEB_DADOS', '').strip()
            if not dados:
                raise ValueError('Dados não configurados')
            return {'modo': 'local', 'dados': dados, 'pasta': _pasta(dados)}
        bucket = os.getenv('AUDITORIA_QUALIDADE_S3_BUCKET', '').strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
            raise ValueError('Bucket não configurado')
        endpoint = os.getenv('AUDITORIA_QUALIDADE_S3_ENDPOINT', '').strip() or None
        if endpoint:
            url = urlsplit(endpoint)
            if (url.scheme != 'https' or not url.hostname or url.username or url.password
                    or url.query or url.fragment or url.path not in {'', '/'}):
                raise ValueError('Endpoint inválido')
            _ = url.port  # Rejeita porta malformada sem criar cliente ou enviar rede.
        region = os.getenv('AUDITORIA_QUALIDADE_S3_REGION', '').strip() or None
        if region and not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', region):
            raise ValueError('Região inválida')
        # Imports lazy; consultar disponibilidade não instancia cliente nem usa rede.
        boto = importlib.import_module('boto3')
        config = importlib.import_module('botocore.config')
        return {'modo': 's3', 'bucket': bucket, 'endpoint': endpoint, 'region': region,
                'boto': boto, 'config': config}
    except Exception:
        raise ErroConfiguracaoAnexos(_INDISPONIVEL) from None


def disponivel():
    """Configuração e dependências presentes; não é uma sondagem de conectividade."""
    try:
        _configuracao()
        return True
    except ErroConfiguracaoAnexos:
        return False


def _cliente(config):
    return config['boto'].client(
        's3', endpoint_url=config['endpoint'], region_name=config['region'],
        config=config['config'].Config(connect_timeout=5, read_timeout=20,
            retries={'mode': 'standard', 'total_max_attempts': 2},
            s3={'addressing_style': 'path'}))


def _chave(chave):
    if not isinstance(chave, str) or not _CHAVE.fullmatch(chave):
        raise ErroAnexo('Identificador do anexo inválido.')
    return chave


def _arquivo(config, chave, criar=False):
    pasta = _pasta(config['dados'], criar=criar)
    arquivo = pasta / _chave(chave).split('/')[1]
    if arquivo.is_symlink() or not arquivo.resolve().is_relative_to(pasta.resolve()):
        raise ErroConfiguracaoAnexos(_INDISPONIVEL)
    return arquivo


@contextmanager
def _reservar_espaco(config, tamanho):
    """Serializa quota e escrita entre threads e processos no mesmo diretorio."""
    with _TRAVA_PRIVADA:
        pasta = _pasta(config['dados'], criar=True)
        trava = pasta / '.gravacao.lock'
        if trava.is_symlink():
            raise ErroConfiguracaoAnexos(_INDISPONIVEL)
        fd = os.open(trava, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        bloqueado = False
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ErroConfiguracaoAnexos(_INDISPONIVEL)
            if info.st_size == 0:
                os.write(fd, b'0')
            if os.name == 'nt':
                import msvcrt
                ate = time.monotonic() + 5
                while True:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= ate:
                            raise
                        time.sleep(0.02)
            else:
                import fcntl
                ate = time.monotonic() + 5
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= ate:
                            raise
                        time.sleep(0.02)
            bloqueado = True
            usados = objetos = 0
            for arquivo in pasta.iterdir():
                if arquivo.name == '.gravacao.lock':
                    continue
                info = arquivo.lstat()
                if (not re.fullmatch(r'[0-9a-f]{32}', arquivo.name)
                        or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ErroConfiguracaoAnexos(_INDISPONIVEL)
                objetos += 1
                usados += info.st_size
                if objetos >= _LIMITE_OBJETOS or usados + tamanho > config['limite_bytes']:
                    raise ErroConfiguracaoAnexos(_INDISPONIVEL)
            if (usados + tamanho > config['limite_bytes']
                    or shutil.disk_usage(pasta).free - tamanho < config['reserva_bytes']):
                raise ErroConfiguracaoAnexos(_INDISPONIVEL)
            yield
        finally:
            try:
                if bloqueado:
                    if os.name == 'nt':
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def salvar(nome, conteudo):
    meta = validar_arquivo(nome, conteudo)
    config = _configuracao()
    chave = 'qualidade/' + uuid4().hex
    try:
        if config['modo'] in {'local', 'privado'}:
            reserva = _reservar_espaco(config, meta['tamanho']) if config['modo'] == 'privado' else nullcontext()
            with reserva:
                arquivo = _arquivo(config, chave, criar=True)
                fd = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                try:
                    with os.fdopen(fd, 'wb') as saida:
                        saida.write(conteudo)
                        saida.flush()
                        os.fsync(saida.fileno())
                except Exception:
                    arquivo.unlink(missing_ok=True)
                    raise
        else:
            _cliente(config).put_object(Bucket=config['bucket'], Key=chave, Body=conteudo,
                ContentLength=meta['tamanho'], ContentType=meta['mime'],
                ContentDisposition='attachment', CacheControl='private, no-store',
                Metadata={'sha256': meta['sha256']}, IfNoneMatch='*')
    except Exception:
        raise ErroConfiguracaoAnexos(_INDISPONIVEL) from None
    return dict(meta, chave_objeto=chave)


def ler(meta):
    if not isinstance(meta, dict):
        raise ErroAnexo('Metadados do anexo inválidos.')
    chave = _chave(meta.get('chave_objeto'))
    tamanho, resumo = meta.get('tamanho'), meta.get('sha256')
    if (type(tamanho) is not int or not 0 < tamanho <= LIMITE_BYTES
            or not isinstance(resumo, str) or not _HASH.fullmatch(resumo)):
        raise ErroAnexo('Metadados do anexo inválidos.')
    config = _configuracao()
    try:
        if config['modo'] in {'local', 'privado'}:
            arquivo = _arquivo(config, chave)
            fd = os.open(arquivo, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as entrada:
                conteudo = entrada.read(LIMITE_BYTES + 1)
        else:
            resposta = _cliente(config).get_object(Bucket=config['bucket'], Key=chave)
            corpo = resposta['Body']
            try:
                conteudo = corpo.read(LIMITE_BYTES + 1)
            finally:
                corpo.close()
    except Exception:
        raise ErroConfiguracaoAnexos(_INDISPONIVEL) from None
    if not isinstance(conteudo, bytes) or len(conteudo) != tamanho or not hmac.compare_digest(
            sha256(conteudo).hexdigest(), resumo):
        raise ErroIntegridadeAnexo('A integridade da evidência não confere. Download bloqueado.')
    return conteudo


def excluir(chave):
    """Compensa falha antes de vincular ao banco; não é uma operação pública."""
    chave = _chave(chave)
    config = _configuracao()
    try:
        if config['modo'] in {'local', 'privado'}:
            _arquivo(config, chave).unlink(missing_ok=True)
        else:
            _cliente(config).delete_object(Bucket=config['bucket'], Key=chave)
    except Exception:
        raise ErroConfiguracaoAnexos(_INDISPONIVEL) from None
