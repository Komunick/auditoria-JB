"""Anexos sintéticos: validação, armazenamento isolado e S3 sem rede."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import re
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from auditoria_fiscal.ferramentas import qualidade_anexos as a
from PIL import Image


EML = (b'From: remetente@example.invalid\r\nTo: destino@example.invalid\r\n'
       b'Subject: Evidencia sintetica\r\nDate: Fri, 30 Oct 2026 12:00:00 -0300\r\n'
       b'\r\nMensagem sintetica.\r\n')


def pdf():
    conteudo = b'%PDF-1.4\n'
    objetos = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [] /Count 0 >>']
    posicoes = [0]
    for numero, objeto in enumerate(objetos, 1):
        posicoes.append(len(conteudo))
        conteudo += str(numero).encode() + b' 0 obj\n' + objeto + b'\nendobj\n'
    inicio = len(conteudo)
    conteudo += b'xref\n0 3\n0000000000 65535 f \n'
    for posicao in posicoes[1:]:
        conteudo += f'{posicao:010} 00000 n \n'.encode()
    return (conteudo + b'trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n'
            + str(inicio).encode() + b'\n%%EOF\n')


def imagem(formato):
    arquivo = BytesIO()
    with Image.new('RGB', (3, 2), '#edf2f5') as img:
        img.save(arquivo, format=formato)
    return arquivo.getvalue()


def recusa(erro, fn, *args):
    try:
        fn(*args)
    except erro as exc:
        return str(exc)
    raise AssertionError('Entrada inválida aceita')


class S3Falso:
    def __init__(self):
        self.objetos = {}
        self.chamadas = []
        self.falhar = False
        self.corpos = []

    def _chamada(self, operacao, kwargs):
        self.chamadas.append((operacao, kwargs))
        if self.falhar:
            raise RuntimeError('segredo-falso /caminho/privado credencial-sintetica')

    def put_object(self, **kwargs):
        self._chamada('put', kwargs)
        self.objetos[kwargs['Key']] = kwargs['Body']
        return {'ETag': 'etag-sintetico'}

    def get_object(self, **kwargs):
        self._chamada('get', kwargs)
        corpo = BytesIO(self.objetos[kwargs['Key']])
        self.corpos.append(corpo)
        return {'Body': corpo, 'ContentLength': len(self.objetos[kwargs['Key']])}

    def delete_object(self, **kwargs):
        self._chamada('delete', kwargs)
        self.objetos.pop(kwargs['Key'], None)


def test_validacao():
    for nome, dados, mime in [('evidencia.pdf', pdf(), 'application/pdf'),
                              ('evidencia.PNG', imagem('PNG'), 'image/png'),
                              ('evidencia.jpeg', imagem('JPEG'), 'image/jpeg'),
                              ('evidencia.eml', EML, 'message/rfc822')]:
        metadados = a.validar_arquivo(nome, dados)
        assert metadados == {'nome': nome, 'mime': mime, 'tamanho': len(dados),
                             'sha256': sha256(dados).hexdigest()}
    for nome in ['../e.pdf', 'pasta/e.pdf', 'pasta\\e.pdf', 'C:e.pdf',
                 '.e.pdf', 'e\x00.pdf', 'e\r\n.pdf', 'e\x7f.pdf',
                 'e\u202e.pdf', 'x' * 200 + '.pdf', 'arquivo.exe', '', None]:
        recusa(a.ErroAnexo, a.validar_arquivo, nome, pdf())
    for nome, dados in [('e.pdf', b'%PDF-1.4\n%%EOF'), ('e.pdf', pdf()[:-12]),
                         ('e.pdf', pdf().replace(b'startxref\n', b'startxref\n999')),
                         ('e.pdf', b'<html>arquivo</html>'),
                         ('e.png', imagem('JPEG')), ('e.jpg', imagem('PNG')),
                         ('e.png', imagem('PNG')[:-12]), ('e.jpg', imagem('JPEG')[:-20]),
                         ('e.jpg', imagem('JPEG')[:100] + b'\xff\xd9'),
                         ('e.eml', b'Texto livre\n'),
                         ('e.eml', b'From: invalido\nTo: b@example.invalid\nSubject: x\nDate: hoje\n\nX')]:
        recusa(a.ErroAnexo, a.validar_arquivo, nome, dados)
    for dados in [b'', b'x' * (a.LIMITE_BYTES + 1), 'conteudo', None]:
        recusa(a.ErroAnexo, a.validar_arquivo, 'e.pdf', dados)
    # Limite inclusivo, email simples sem anexos ou descompressão.
    grande = EML + b'x' * (a.LIMITE_BYTES - len(EML))
    assert a.validar_arquivo('limite.eml', grande)['tamanho'] == a.LIMITE_BYTES
    # Dimensões são conferidas antes de permitir decodificação.
    with patch.object(Image, 'MAX_IMAGE_PIXELS', 1):
        recusa(a.ErroAnexo, a.validar_arquivo, 'grande.png', imagem('PNG'))


def test_local():
    with TemporaryDirectory(prefix='qa_anexos_') as pasta:
        with patch.dict(os.environ, {'AUDITORIA_WEB_DADOS': pasta}, clear=True):
            assert a.disponivel() is False
            recusa(a.ErroConfiguracaoAnexos, a.salvar, 'e.eml', EML)
            assert not list(Path(pasta).iterdir())
        with patch.dict(os.environ, {'AUDITORIA_QUALIDADE_ANEXOS_LOCAL': '1'}, clear=True):
            assert a.disponivel() is False
        ambiente = {'AUDITORIA_QUALIDADE_ANEXOS_LOCAL': '1', 'AUDITORIA_WEB_DADOS': pasta}
        with patch.dict(os.environ, ambiente, clear=True):
            assert a.disponivel() is True
            assert not list(Path(pasta).iterdir()), 'Consultar disponibilidade não grava arquivos'
            meta = a.salvar('evidencia.eml', EML)
            assert re.fullmatch(r'qualidade/[0-9a-f]{32}', meta['chave_objeto'])
            assert 'evidencia' not in meta['chave_objeto']
            assert a.ler(meta) == EML
            outra = a.salvar('evidencia.eml', EML)
            assert outra['chave_objeto'] != meta['chave_objeto']
            arquivo = Path(pasta) / 'qualidade' / 'anexos' / meta['chave_objeto'].split('/')[1]
            assert arquivo.read_bytes() == EML
            # Colisão de identificador nunca sobrescreve evidência anterior.
            colidente = type('UUIDFalso', (), {'hex': meta['chave_objeto'].split('/')[1]})()
            with patch.object(a, 'uuid4', return_value=colidente):
                recusa(a.ErroConfiguracaoAnexos, a.salvar, 'outro.eml', EML + b'novo')
            assert a.ler(meta) == EML
            for chave in ['../fora', '/fora', 'qualidade/../../fora', 'qualidade/teste', 'C:fora']:
                invalido = dict(meta, chave_objeto=chave)
                recusa(a.ErroAnexo, a.ler, invalido)
                recusa(a.ErroAnexo, a.excluir, chave)
            for campos in [{'tamanho': len(EML) + 1}, {'sha256': '0' * 64}]:
                recusa(a.ErroIntegridadeAnexo, a.ler, dict(meta, **campos))
            for campos in [{'tamanho': True}, {'tamanho': a.LIMITE_BYTES + 1},
                           {'sha256': 'resumo invalido'}]:
                recusa(a.ErroAnexo, a.ler, dict(meta, **campos))
            arquivo.write_bytes(b'corrompido')
            recusa(a.ErroIntegridadeAnexo, a.ler, meta)
            a.excluir(meta['chave_objeto'])
            a.excluir(meta['chave_objeto'])  # Compensação idempotente.
            assert a.ler(outra) == EML
            a.excluir(outra['chave_objeto'])
            assert list(arquivo.parent.iterdir()) == []


def test_s3():
    falso = S3Falso()
    clientes = []
    modulo = ModuleType('boto3')
    modulo.client = lambda *args, **kwargs: clientes.append((args, kwargs)) or falso
    config = ModuleType('botocore.config')
    config.Config = lambda **kwargs: kwargs
    ambiente = {'AUDITORIA_QUALIDADE_S3_BUCKET': 'bucket-sintetico',
                'AUDITORIA_QUALIDADE_S3_REGION': 'sa-east-1',
                'AUDITORIA_QUALIDADE_S3_ENDPOINT': 'https://s3.example.invalid'}
    with patch.dict(sys.modules, {'boto3': modulo, 'botocore.config': config}):
        with patch.dict(os.environ, ambiente, clear=True):
            assert a.disponivel() is True
            assert clientes == [] and falso.chamadas == [], 'Disponibilidade sem rede'
            meta = a.salvar('e.eml', EML)
            chamada = falso.chamadas[-1][1]
            assert chamada['Bucket'] == 'bucket-sintetico'
            assert chamada['Body'] == EML and chamada['ContentType'] == 'message/rfc822'
            assert chamada.get('ACL') not in {'public-read', 'public-read-write'}
            assert chamada['Metadata']['sha256'] == sha256(EML).hexdigest()
            args, kwargs = clientes[0]
            assert args == ('s3',) and kwargs['endpoint_url'].startswith('https://')
            assert kwargs['config']['connect_timeout'] <= 5
            assert kwargs['config']['read_timeout'] <= 20
            assert kwargs['config']['retries']['total_max_attempts'] <= 3
            assert a.ler(meta) == EML and falso.corpos[-1].closed
            falso.objetos[meta['chave_objeto']] = b'outro conteudo'
            recusa(a.ErroIntegridadeAnexo, a.ler, meta)
            assert falso.corpos[-1].closed
            a.excluir(meta['chave_objeto'])
            assert meta['chave_objeto'] not in falso.objetos
            falso.falhar = True
            for fn, args in [(a.salvar, ('e.eml', EML)), (a.ler, (meta,)),
                             (a.excluir, (meta['chave_objeto'],))]:
                mensagem = recusa(a.ErroConfiguracaoAnexos, fn, *args)
                assert 'segredo' not in mensagem and 'caminho' not in mensagem
            falso.falhar = False
        for endpoint in ['http://s3.example.invalid', 'https://user:secret@example.invalid',
                         'https://example.invalid/?token=secret', 'ftp://example.invalid']:
            with patch.dict(os.environ, dict(ambiente, AUDITORIA_QUALIDADE_S3_ENDPOINT=endpoint), clear=True):
                assert a.disponivel() is False
                antes = len(falso.chamadas)
                recusa(a.ErroConfiguracaoAnexos, a.salvar, 'e.eml', EML)
                assert len(falso.chamadas) == antes


def main():
    test_validacao()
    test_local()
    test_s3()
    print('OK - anexos: formatos, limites, modo local explícito, integridade e S3 falso')


if __name__ == '__main__':
    main()
