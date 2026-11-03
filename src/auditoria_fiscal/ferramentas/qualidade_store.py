"""Gestão da qualidade no clientes.db: schema aditivo, revisão e trilha atômica."""
from __future__ import annotations

import json
import re

from ..core import qualidade as q
from .tarefas_store import TarefasStore

VERSAO_SCHEMA = 4
_TABELAS = {'ocorrencia': 'qualidade_ocorrencia', 'plano': 'qualidade_plano',
            'horas': 'qualidade_horas', 'anexo': 'qualidade_anexo'}
_OCORRENCIA = {'data', 'cliente_id', 'setor_id', 'responsavel_usuario_id',
               'tarefa_id', 'tipo', 'descricao', 'criticidade', 'prazo'}
_PLANO = {'ocorrencia_id', 'causa', 'descricao', 'tipo', 'responsavel_usuario_id', 'prazo'}
_HORAS = {'cliente_id', 'setor_id', 'tarefa_id', 'ocorrencia_id', 'data',
          'minutos', 'descricao', 'custo_hora'}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS qualidade_ocorrencia (
 id INTEGER PRIMARY KEY, data TEXT NOT NULL, cliente_id INTEGER NOT NULL REFERENCES cliente(id),
 setor_id INTEGER NOT NULL REFERENCES setor(id), responsavel_usuario_id INTEGER NOT NULL,
 tarefa_id INTEGER REFERENCES tarefa(id), tipo TEXT NOT NULL, descricao TEXT NOT NULL,
 criticidade TEXT NOT NULL, prazo TEXT NOT NULL, situacao TEXT NOT NULL DEFAULT 'aberta',
 resolvida_em TEXT NOT NULL DEFAULT '', encerrada_em TEXT NOT NULL DEFAULT '',
 criada_por INTEGER NOT NULL, criada_por_login TEXT NOT NULL, criado_em TEXT NOT NULL,
 atualizado_em TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 CHECK(prazo>=data), CHECK(revision>0),
 CHECK(situacao IN ('aberta','em_tratamento','resolvida','encerrada')),
 CHECK(criticidade IN ('baixa','media','alta','critica')),
 CHECK(tipo IN ('erro','atraso','comunicacao','reclamacao','retrabalho','pendencia','procedimento','nao_conformidade')));
CREATE INDEX IF NOT EXISTS idx_qualidade_ocorrencia_escopo ON qualidade_ocorrencia(setor_id,responsavel_usuario_id,situacao,data);
CREATE INDEX IF NOT EXISTS idx_qualidade_ocorrencia_cliente ON qualidade_ocorrencia(cliente_id,data);
CREATE TABLE IF NOT EXISTS qualidade_plano (
 id INTEGER PRIMARY KEY, ocorrencia_id INTEGER NOT NULL REFERENCES qualidade_ocorrencia(id),
 cliente_id INTEGER NOT NULL REFERENCES cliente(id), setor_id INTEGER NOT NULL REFERENCES setor(id),
 data TEXT NOT NULL, causa TEXT NOT NULL, descricao TEXT NOT NULL, tipo TEXT NOT NULL,
 responsavel_usuario_id INTEGER NOT NULL, prazo TEXT NOT NULL,
 situacao TEXT NOT NULL DEFAULT 'aberto', iniciado_em TEXT NOT NULL DEFAULT '',
 validado_em TEXT NOT NULL DEFAULT '', validado_por INTEGER,
 criada_por INTEGER NOT NULL, criada_por_login TEXT NOT NULL, criado_em TEXT NOT NULL,
 atualizado_em TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 CHECK(revision>0), CHECK(tipo IN ('corretiva','preventiva')),
 CHECK(situacao IN ('aberto','em_andamento','aguardando_validacao','validado')));
CREATE INDEX IF NOT EXISTS idx_qualidade_plano_escopo ON qualidade_plano(setor_id,responsavel_usuario_id,situacao,data);
CREATE INDEX IF NOT EXISTS idx_qualidade_plano_ocorrencia ON qualidade_plano(ocorrencia_id);
CREATE TABLE IF NOT EXISTS qualidade_horas (
 id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES cliente(id),
 setor_id INTEGER NOT NULL REFERENCES setor(id), responsavel_usuario_id INTEGER NOT NULL,
 tarefa_id INTEGER REFERENCES tarefa(id), ocorrencia_id INTEGER REFERENCES qualidade_ocorrencia(id),
 data TEXT NOT NULL, minutos INTEGER NOT NULL CHECK(minutos BETWEEN 1 AND 1440),
 descricao TEXT NOT NULL, custo_hora TEXT, custo_total TEXT,
 cancelado INTEGER NOT NULL DEFAULT 0 CHECK(cancelado IN (0,1)), motivo_cancelamento TEXT NOT NULL DEFAULT '',
 cancelado_em TEXT NOT NULL DEFAULT '', cancelado_por INTEGER,
 criada_por INTEGER NOT NULL, criada_por_login TEXT NOT NULL, criado_em TEXT NOT NULL,
 atualizado_em TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 CHECK((custo_hora IS NULL AND custo_total IS NULL) OR (custo_hora IS NOT NULL AND custo_total IS NOT NULL)));
CREATE INDEX IF NOT EXISTS idx_qualidade_horas_escopo ON qualidade_horas(setor_id,responsavel_usuario_id,data);
CREATE TABLE IF NOT EXISTS qualidade_anexo (
 id INTEGER PRIMARY KEY, entidade TEXT NOT NULL CHECK(entidade IN ('ocorrencia','plano')),
 entidade_id INTEGER NOT NULL, nome TEXT NOT NULL, mime TEXT NOT NULL,
 tamanho INTEGER NOT NULL CHECK(tamanho BETWEEN 1 AND 10485760), sha256 TEXT NOT NULL,
 chave_objeto TEXT NOT NULL UNIQUE, usuario_id INTEGER NOT NULL, usuario_login TEXT NOT NULL,
 criado_em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_qualidade_anexo_alvo ON qualidade_anexo(entidade,entidade_id);
CREATE TABLE IF NOT EXISTS qualidade_evento (
 id INTEGER PRIMARY KEY, entidade TEXT NOT NULL CHECK(entidade IN ('ocorrencia','plano','horas')),
 entidade_id INTEGER NOT NULL, tipo TEXT NOT NULL, antes TEXT NOT NULL, depois TEXT NOT NULL,
 comentario TEXT NOT NULL DEFAULT '', usuario_id INTEGER NOT NULL, usuario_login TEXT NOT NULL,
 criado_em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_qualidade_evento_alvo ON qualidade_evento(entidade,entidade_id,id);
CREATE TRIGGER IF NOT EXISTS trg_qualidade_evento_sem_update BEFORE UPDATE ON qualidade_evento
 BEGIN SELECT RAISE(ABORT,'Evento de qualidade e imutavel.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_evento_sem_delete BEFORE DELETE ON qualidade_evento
 BEGIN SELECT RAISE(ABORT,'Evento de qualidade e imutavel.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_anexo_sem_update BEFORE UPDATE ON qualidade_anexo
 BEGIN SELECT RAISE(ABORT,'Evidencia de qualidade e imutavel.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_anexo_sem_delete BEFORE DELETE ON qualidade_anexo
 BEGIN SELECT RAISE(ABORT,'Evidencia de qualidade e imutavel.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_ocorrencia_sem_delete BEFORE DELETE ON qualidade_ocorrencia
 BEGIN SELECT RAISE(ABORT,'Ocorrencia nao pode ser excluida.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_plano_sem_delete BEFORE DELETE ON qualidade_plano
 BEGIN SELECT RAISE(ABORT,'Plano nao pode ser excluido.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_horas_sem_delete BEFORE DELETE ON qualidade_horas
 BEGIN SELECT RAISE(ABORT,'Apontamento nao pode ser excluido.'); END;
CREATE TRIGGER IF NOT EXISTS trg_qualidade_horas_original BEFORE UPDATE ON qualidade_horas
 WHEN NEW.cliente_id IS NOT OLD.cliente_id OR NEW.setor_id IS NOT OLD.setor_id
 OR NEW.responsavel_usuario_id IS NOT OLD.responsavel_usuario_id OR NEW.tarefa_id IS NOT OLD.tarefa_id
 OR NEW.ocorrencia_id IS NOT OLD.ocorrencia_id OR NEW.data IS NOT OLD.data
 OR NEW.minutos IS NOT OLD.minutos OR NEW.descricao IS NOT OLD.descricao
 OR NEW.custo_hora IS NOT OLD.custo_hora OR NEW.custo_total IS NOT OLD.custo_total
 OR NEW.criada_por IS NOT OLD.criada_por OR NEW.criada_por_login IS NOT OLD.criada_por_login
 OR NEW.criado_em IS NOT OLD.criado_em OR OLD.cancelado=1 OR NEW.cancelado<>1
 BEGIN SELECT RAISE(ABORT,'Apontamento original e imutavel; apenas cancelamento e permitido.'); END;
"""


class QualidadeStore(TarefasStore):
    def _migrar(self):
        super()._migrar()
        # executescript confirma uma transação anterior antes de executar o SQL.
        # O BEGIN precisa integrar o próprio script para proteger DDL e versão.
        try:
            self.conn.executescript('BEGIN IMMEDIATE;\n' + _SCHEMA)
            if self.conn.execute('PRAGMA user_version').fetchone()[0] < VERSAO_SCHEMA:
                self.conn.execute(f'PRAGMA user_version={VERSAO_SCHEMA}')
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def _qual_um(self, entidade, id):
        if entidade not in _TABELAS:
            raise ValueError('Entidade de qualidade inválida.')
        r = self.conn.execute(f'SELECT * FROM {_TABELAS[entidade]} WHERE id=?',
                              (q.identificador(id),)).fetchone()
        if r is None:
            raise LookupError('Registro não encontrado.')
        return dict(r)

    def _autor(self, usuario_id, usuario_login):
        return self._usuario(q.identificador(usuario_id)), q.texto(usuario_login, 'Login', 160)

    def _evento_qualidade(self, entidade, rid, tipo, antes, depois, comentario, usuario_id, usuario_login):
        self.conn.execute('INSERT INTO qualidade_evento(entidade,entidade_id,tipo,antes,depois,comentario,usuario_id,usuario_login,criado_em) VALUES(?,?,?,?,?,?,?,?,?)',
            (entidade, rid, tipo, json.dumps(antes, ensure_ascii=False, sort_keys=True),
             json.dumps(depois, ensure_ascii=False, sort_keys=True), comentario,
             usuario_id, usuario_login, self._agora()))

    def _vinculos(self, dados, *, responsavel=True):
        cid, sid = q.identificador(dados.get('cliente_id')), q.identificador(dados.get('setor_id'))
        self._um('cliente', cid)
        if not self._um('setor', sid)['ativo']:
            raise ValueError('Selecione um setor ativo.')
        if responsavel:
            self._membro(sid, q.identificador(dados.get('responsavel_usuario_id')))
        tid = q.identificador(dados.get('tarefa_id'), opcional=True)
        if tid:
            tarefa = self._um('tarefa', tid)
            if tarefa['cliente_id'] != cid or tarefa['setor_id'] != sid:
                raise ValueError('A tarefa deve pertencer ao mesmo cliente e setor.')
        return cid, sid, tid

    def _inserir(self, entidade, dados, usuario_id, usuario_login):
        valores = dict(dados, criada_por=usuario_id, criada_por_login=usuario_login,
                       criado_em=self._agora(), atualizado_em=self._agora())
        colunas = ','.join(valores)
        rid = self.conn.execute(f'INSERT INTO {_TABELAS[entidade]}({colunas}) VALUES({",".join("?" for _ in valores)})',
                                tuple(valores.values())).lastrowid
        self._evento_qualidade(entidade, rid, 'criacao', None, self._qual_um(entidade, rid), '', usuario_id, usuario_login)
        return rid

    def _atualizar(self, entidade, antes, campos, tipo, comentario, usuario_id, usuario_login):
        campos = dict(campos, revision=antes['revision'] + 1, atualizado_em=self._agora())
        self.conn.execute(f'UPDATE {_TABELAS[entidade]} SET {",".join(k+"=?" for k in campos)} WHERE id=?',
                          (*campos.values(), antes['id']))
        self._evento_qualidade(entidade, antes['id'], tipo, antes,
                              self._qual_um(entidade, antes['id']), comentario, usuario_id, usuario_login)

    def _validar_ocorrencia(self, dados):
        cid, sid, tid = self._vinculos(dados)
        data, prazo = q.data(dados.get('data')), q.data(dados.get('prazo'))
        if data > self._hoje().isoformat() or prazo < data:
            raise ValueError('Data da ocorrência não pode ser futura e prazo deve ser igual ou posterior à data.')
        return dict(cliente_id=cid, setor_id=sid, tarefa_id=tid, data=data, prazo=prazo,
                    responsavel_usuario_id=q.identificador(dados.get('responsavel_usuario_id')),
                    tipo=q.escolha(dados.get('tipo'), q.TIPOS, 'Tipo'),
                    descricao=q.texto(dados.get('descricao'), 'Descrição'),
                    criticidade=q.escolha(dados.get('criticidade'), q.CRITICIDADES, 'Criticidade'))

    def criar_ocorrencia(self, dados, *, usuario_id, usuario_login):
        q.campos(dados, _OCORRENCIA)
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            rid = self._inserir('ocorrencia', self._validar_ocorrencia(dados), usuario_id, usuario_login)
            return self.obter_ocorrencia(rid)
        return self._transacao(gravar)

    def editar_ocorrencia(self, id, dados, revision, *, usuario_id, usuario_login):
        # Cliente, setor e tarefa são a identidade do vínculo; não se mudam após a criação.
        q.campos(dados, _OCORRENCIA - {'cliente_id', 'setor_id', 'tarefa_id'})
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um('ocorrencia', id)
            self._revision(antes, revision)
            if antes['situacao'] in {'resolvida', 'encerrada'}:
                raise ValueError('Reabra a ocorrência antes de editar; encerrada é definitiva.')
            novo = self._validar_ocorrencia({**antes, **dados})
            self._atualizar('ocorrencia', antes, novo, 'edicao', '', usuario_id, usuario_login)
            return self.obter_ocorrencia(id)
        return self._transacao(gravar)

    def transicionar_ocorrencia(self, id, situacao, comentario, revision, *, usuario_id, usuario_login):
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um('ocorrencia', id)
            self._revision(antes, revision)
            q.transicao('ocorrencia', antes['situacao'], situacao, comentario)
            if situacao in {'resolvida', 'encerrada'} and self.conn.execute(
                    "SELECT 1 FROM qualidade_plano WHERE ocorrencia_id=? AND situacao<>'validado'", (id,)).fetchone():
                raise ValueError('Valide os planos de ação antes de resolver a ocorrência.')
            campos = {'situacao': situacao}
            if situacao == 'resolvida':
                campos['resolvida_em'] = self._agora()
            elif situacao == 'encerrada':
                campos['encerrada_em'] = self._agora()
            elif antes['situacao'] == 'resolvida':
                campos['resolvida_em'] = ''
            self._atualizar('ocorrencia', antes, campos, 'situacao',
                            q.texto(comentario, 'Comentário', opcional=True), usuario_id, usuario_login)
            return self.obter_ocorrencia(id)
        return self._transacao(gravar)

    def _validar_plano(self, dados, ocorrencia):
        if ocorrencia['situacao'] in {'resolvida', 'encerrada'}:
            raise ValueError('Reabra a ocorrência antes de criar ou editar seu plano.')
        uid = q.identificador(dados.get('responsavel_usuario_id'))
        self._membro(ocorrencia['setor_id'], uid)
        if not self._um('setor', ocorrencia['setor_id'])['ativo']:
            raise ValueError('Selecione um setor ativo.')
        prazo = q.data(dados.get('prazo'))
        if prazo < ocorrencia['data']:
            raise ValueError('Prazo do plano não pode anteceder a ocorrência.')
        return dict(causa=q.texto(dados.get('causa'), 'Causa'),
                    descricao=q.texto(dados.get('descricao'), 'Ação'),
                    tipo=q.escolha(dados.get('tipo'), q.TIPOS_PLANO, 'Tipo de ação'),
                    responsavel_usuario_id=uid, prazo=prazo)

    def criar_plano(self, dados, *, usuario_id, usuario_login):
        q.campos(dados, _PLANO)
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            ocorrencia = self._qual_um('ocorrencia', q.identificador(dados.get('ocorrencia_id')))
            valores = dict(self._validar_plano(dados, ocorrencia), ocorrencia_id=ocorrencia['id'],
                           cliente_id=ocorrencia['cliente_id'], setor_id=ocorrencia['setor_id'],
                           data=self._hoje().isoformat())
            rid = self._inserir('plano', valores, usuario_id, usuario_login)
            return self.obter_plano(rid)
        return self._transacao(gravar)

    def editar_plano(self, id, dados, revision, *, usuario_id, usuario_login):
        q.campos(dados, _PLANO - {'ocorrencia_id'})
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um('plano', id)
            self._revision(antes, revision)
            if antes['situacao'] in {'validado', 'aguardando_validacao'}:
                raise ValueError('Plano em validação ou validado não pode ser editado; devolva antes de corrigir.')
            ocorrencia = self._qual_um('ocorrencia', antes['ocorrencia_id'])
            self._atualizar('plano', antes, self._validar_plano({**antes, **dados}, ocorrencia),
                            'edicao', '', usuario_id, usuario_login)
            return self.obter_plano(id)
        return self._transacao(gravar)

    def transicionar_plano(self, id, situacao, comentario, revision, *, usuario_id, usuario_login):
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um('plano', id)
            self._revision(antes, revision)
            q.transicao('plano', antes['situacao'], situacao, comentario)
            campos = {'situacao': situacao}
            if situacao == 'em_andamento' and not antes['iniciado_em']:
                campos['iniciado_em'] = self._agora()
            if situacao == 'validado':
                campos.update(validado_em=self._agora(), validado_por=usuario_id)
            self._atualizar('plano', antes, campos, 'situacao',
                            q.texto(comentario, 'Comentário', opcional=True), usuario_id, usuario_login)
            return self.obter_plano(id)
        return self._transacao(gravar)

    def _comentar_qualidade(self, entidade, id, comentario, revision, usuario_id, usuario_login):
        comentario = q.texto(comentario, 'Comentário')
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um(entidade, id)
            if antes['situacao'] in {'encerrada', 'validado'}:
                raise ValueError('O registro já foi encerrado pela gestão e não aceita comentários.')
            self._revision(antes, revision)
            self._atualizar(entidade, antes, {}, 'comentario', comentario, usuario_id, usuario_login)
            return self._detalhe(entidade, id)
        return self._transacao(gravar)

    def comentar_ocorrencia(self, id, comentario, revision, *, usuario_id, usuario_login):
        return self._comentar_qualidade('ocorrencia', id, comentario, revision, usuario_id, usuario_login)

    def comentar_plano(self, id, comentario, revision, *, usuario_id, usuario_login):
        return self._comentar_qualidade('plano', id, comentario, revision, usuario_id, usuario_login)

    def registrar_horas(self, dados, *, usuario_id, usuario_login):
        q.campos(dados, _HORAS)
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            cid, sid, tid = self._vinculos(dict(dados, responsavel_usuario_id=usuario_id))
            oid = q.identificador(dados.get('ocorrencia_id'), opcional=True)
            if oid:
                ocorrencia = self._qual_um('ocorrencia', oid)
                if ocorrencia['cliente_id'] != cid or ocorrencia['setor_id'] != sid:
                    raise ValueError('A ocorrência deve pertencer ao mesmo cliente e setor.')
                if tid and ocorrencia['tarefa_id'] and tid != ocorrencia['tarefa_id']:
                    raise ValueError('A tarefa informada difere da tarefa da ocorrência.')
            data = q.data(dados.get('data'))
            if data > self._hoje().isoformat():
                raise ValueError('Não é permitido apontar tempo de uma data futura.')
            duracao = q.minutos(dados.get('minutos'))
            total = conn.execute('SELECT coalesce(sum(minutos),0) FROM qualidade_horas WHERE responsavel_usuario_id=? AND data=? AND cancelado=0', (usuario_id, data)).fetchone()[0]
            if total + duracao > 1440:
                raise ValueError('Os apontamentos ativos do colaborador ultrapassam 24 horas no dia.')
            custo_hora, custo_total = q.custo(dados.get('custo_hora'), duracao)
            valores = dict(cliente_id=cid, setor_id=sid, tarefa_id=tid, ocorrencia_id=oid,
                           responsavel_usuario_id=usuario_id, data=data, minutos=duracao,
                           descricao=q.texto(dados.get('descricao'), 'Descrição'),
                           custo_hora=custo_hora, custo_total=custo_total)
            rid = self._inserir('horas', valores, usuario_id, usuario_login)
            return self.obter_horas(rid)
        return self._transacao(gravar)

    def cancelar_horas(self, id, motivo, revision, *, usuario_id, usuario_login):
        motivo = q.texto(motivo, 'Motivo')
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um('horas', id)
            self._revision(antes, revision)
            if antes['cancelado']:
                raise ValueError('Este apontamento já foi cancelado.')
            self._atualizar('horas', antes, dict(cancelado=1, motivo_cancelamento=motivo,
                cancelado_em=self._agora(), cancelado_por=usuario_id), 'cancelamento', motivo,
                usuario_id, usuario_login)
            return self.obter_horas(id)
        return self._transacao(gravar)

    def registrar_anexo(self, entidade, entidade_id, metadados, *, usuario_id, usuario_login):
        q.escolha(entidade, {'ocorrencia', 'plano'}, 'Destino da evidência')
        q.campos(metadados, {'nome', 'mime', 'tamanho', 'sha256', 'chave_objeto'})
        nome = q.texto(metadados.get('nome'), 'Nome do arquivo', 200)
        if any(c in nome for c in '/\\') or nome.startswith('.') or any(ord(c) < 32 for c in nome):
            raise ValueError('Nome de arquivo inválido.')
        mime = q.escolha(metadados.get('mime'), {'application/pdf', 'image/png', 'image/jpeg', 'message/rfc822'}, 'Tipo de arquivo')
        tamanho = metadados.get('tamanho')
        if type(tamanho) is not int or not 1 <= tamanho <= 10 * 1024 * 1024:
            raise ValueError('Arquivo deve ter de 1 byte a 10 MB.')
        sha = metadados.get('sha256')
        chave = q.texto(metadados.get('chave_objeto'), 'Chave do objeto', 512)
        if not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{64}', sha):
            raise ValueError('Identificação do arquivo inválida.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*', chave) or any(p in {'.', '..'} for p in chave.split('/')):
            raise ValueError('Chave do objeto inválida.')
        def gravar(conn):
            self._autor(usuario_id, usuario_login)
            antes = self._qual_um(entidade, entidade_id)
            if antes['situacao'] in {'encerrada', 'validado'}:
                raise ValueError('Registro finalizado não aceita novas evidências.')
            rid = conn.execute('INSERT INTO qualidade_anexo(entidade,entidade_id,nome,mime,tamanho,sha256,chave_objeto,usuario_id,usuario_login,criado_em) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (entidade, entidade_id, nome, mime, tamanho, sha, chave, usuario_id, usuario_login, self._agora())).lastrowid
            self._atualizar(entidade, antes, {}, 'evidencia', f'Evidência anexada: {rid}.', usuario_id, usuario_login)
            return self.obter_anexo(rid)
        return self._transacao(gravar)

    def obter_anexo(self, id):
        return self._qual_um('anexo', id)

    def _nomes(self, registro):
        return dict(registro, cliente_nome=self._um('cliente', registro['cliente_id'])['nome'],
                    setor_nome=self._um('setor', registro['setor_id'])['nome'])

    def _detalhe(self, entidade, id):
        registro = self._nomes(self._qual_um(entidade, id))
        registro['historico'] = []
        for r in self.conn.execute('SELECT * FROM qualidade_evento WHERE entidade=? AND entidade_id=? ORDER BY id', (entidade, id)):
            evento = dict(r)
            evento['antes'], evento['depois'] = json.loads(evento['antes']), json.loads(evento['depois'])
            registro['historico'].append(evento)
        if entidade in {'ocorrencia', 'plano'}:
            registro['anexos'] = [dict(r) for r in self.conn.execute('SELECT * FROM qualidade_anexo WHERE entidade=? AND entidade_id=? ORDER BY id', (entidade, id))]
        if entidade == 'ocorrencia':
            registro['planos'] = self.listar_planos({'ocorrencia_id': id})
        return registro

    def obter_ocorrencia(self, id):
        return self._detalhe('ocorrencia', id)

    def obter_plano(self, id):
        return self._detalhe('plano', id)

    def obter_horas(self, id):
        return self._detalhe('horas', id)

    def _listar_qualidade(self, entidade, filtros=None):
        filtros = filtros or {}
        permitidos = {'cliente_id', 'setor_id', 'responsavel_usuario_id', 'de', 'ate'}
        if entidade != 'horas':
            permitidos |= {'situacao', 'tipo'}
        if entidade == 'ocorrencia':
            permitidos.add('criticidade')
        if entidade == 'plano':
            permitidos.add('ocorrencia_id')
        if entidade == 'horas':
            permitidos |= {'cancelado', 'ocorrencia_id', 'tarefa_id'}
        q.campos(filtros, permitidos)
        partes, valores = [], []
        for chave, valor in filtros.items():
            if valor is None or valor == '':
                continue
            if chave in {'de', 'ate'}:
                valor = q.data(valor)
                partes.append('r.data' + ('>=?' if chave == 'de' else '<=?'))
            elif chave.endswith('_id'):
                valor = q.identificador(valor)
                partes.append('r.' + chave + '=?')
            elif chave == 'cancelado':
                if type(valor) not in {bool, int} or valor not in {0, 1}:
                    raise ValueError('Filtro de cancelamento inválido.')
                partes.append('r.cancelado=?')
            else:
                catalogo = (q.CRITICIDADES if chave == 'criticidade' else
                            q.TIPOS if chave == 'tipo' and entidade == 'ocorrencia' else
                            q.TIPOS_PLANO if chave == 'tipo' else
                            q.SITUACOES_OCORRENCIA if entidade == 'ocorrencia' else q.SITUACOES_PLANO)
                valor = q.escolha(valor, catalogo, 'Filtro')
                partes.append('r.' + chave + '=?')
            valores.append(valor)
        if filtros.get('de') and filtros.get('ate') and filtros['de'] > filtros['ate']:
            raise ValueError('Início do período deve anteceder o fim.')
        where = ' WHERE ' + ' AND '.join(partes) if partes else ''
        sql = f'SELECT r.*,c.nome AS cliente_nome,s.nome AS setor_nome FROM {_TABELAS[entidade]} r JOIN cliente c ON c.id=r.cliente_id JOIN setor s ON s.id=r.setor_id{where} ORDER BY r.data DESC,r.id DESC'
        return [dict(r) for r in self.conn.execute(sql, valores)]

    def listar_ocorrencias(self, filtros=None):
        return self._listar_qualidade('ocorrencia', filtros)

    def listar_planos(self, filtros=None):
        return self._listar_qualidade('plano', filtros)

    def listar_horas(self, filtros=None):
        return self._listar_qualidade('horas', filtros)
