# Contratos de implementação

Base HTTP `/api/qualidade`, aba `qualidade`. Objetos JSON sem envelope salvo
listagens `{itens,total}`. Erros com `detail`; concorrência HTTP409. Todos os IDs
inteiros positivos; datas ISO; moeda decimal como string; `revision` nas mutações.

## API da interface

- GET `/catalogo`: `{clientes:[{id,nome}],setores:[{id,nome}],usuarios:[{id,nome,setor_ids}],
  tipos:[{valor,rotulo}],criticidades:[{valor,rotulo}],modelos:[{setor,atividades}],
  permissoes:{registrar,gerir,validar,exportar,custos},anexos:{disponivel,limite_bytes}}`.
- GET `/painel?cliente_id=&setor_id=&responsavel_usuario_id=&de=&ate=&situacao=`:
  objeto agregado pelo núcleo (ver contrato do indicador).
- GET `/ocorrencias` com filtros acima e `tipo`, `criticidade`: `{itens,total}`;
  POST `/ocorrencias`: data, cliente_id, setor_id, responsavel_usuario_id,
  tarefa_id opcional, tipo, descricao, criticidade, prazo. Retorna registro.
- GET `/ocorrencias/{id}`: registro com `historico`, `planos`, `anexos`.
  PATCH mesma rota: campos editáveis + revision. POST `/{id}/transicao`:
  `{situacao,comentario,revision}`; POST `/{id}/comentarios`: `{comentario,revision}`.
  Situações: aberta, em_tratamento, resolvida, encerrada. Encerrar exige
  `qualidade.validar` e gestão efetiva do setor.
- GET/POST `/planos`: lista/cria. Campos ocorrência_id (grafia HTTP `ocorrencia_id`),
  causa, descricao, tipo (corretiva/preventiva), responsavel_usuario_id, prazo.
  GET/PATCH `/planos/{id}`; POST `/{id}/transicao` e `/{id}/comentarios` como acima.
  Situações: aberto, em_andamento, aguardando_validacao, validado; devolução para
  em_andamento com comentário obrigatório. Validar/devolver exige gestão.
- GET/POST `/horas`: lista/cria `{tarefa_id?,ocorrencia_id?,cliente_id,setor_id,
  data,minutos,descricao,custo_hora?}`; responsável é usuário da sessão.
  POST `/horas/{id}/cancelar`: `{motivo,revision}`. Não apaga original.
- POST `/ocorrencias/{id}/anexos`, `/planos/{id}/anexos`: multipart `arquivo`.
  GET `/anexos/{id}/download`; DELETE não existe, histórico preservado.
- GET `/relatorio.xlsx` e `/relatorio.pdf`: mesmos filtros, parâmetro opcional
  `periodo=diario|semanal|mensal` e `referencia=AAAA-MM-DD`; filtros prevalecem se
  intervalo explícito completo. UI usa download autenticado existente.

## Persistência (QualidadeStore herda TarefasStore)

`criar_ocorrencia(dados, **quem)`, `editar_ocorrencia(id,dados,revision,**quem)`,
`transicionar_ocorrencia(id,situacao,comentario,revision,**quem)`,
`comentar_ocorrencia(id,comentario,revision,**quem)`, `obter_ocorrencia(id)`,
`listar_ocorrencias(filtros=None)` → lista de dicts (filtros mínimos cliente_id,
setor_id,responsavel_usuario_id,de,ate,situacao,tipo,criticidade).
Planos: mesmos nomes com `plano`; criar exige ocorrência existente e herda
cliente_id/setor_id dela. `obter_*` traz `historico` e `anexos` (ocorrência planos).
`registrar_horas(dados,**quem)`, `cancelar_horas(id,motivo,revision,**quem)`,
`listar_horas(filtros=None)`, `obter_horas(id)`.
`registrar_anexo(entidade,entidade_id,metadados,**quem)` e `obter_anexo(id)`;
entidade `ocorrencia|plano`; metadados `nome,mime,tamanho,sha256,chave_objeto`.
Permissões e escopo conferidos pelas rotas sob BEGIN IMMEDIATE; store valida
regras, vínculo cliente/setor/tarefa/responsável e invariantes, mas não conhece web.

## Indicadores e relatórios

`core/qualidade_indicadores.py`: `calcular_painel(tarefas,ocorrencias,planos,horas,
hoje,usuarios=None,setores=None,custos_permitidos=False)` → dicionário.
Entrada já autorizada/filtrada pela rota; nenhuma consulta de banco no núcleo.
Resultado `qualidade_painel_v1`: `referencia`, `kpis` (chave, rótulo, valor,
unidade, fórmula e amostra quando aplicável), `totais`, `semaforo`,
`por_colaborador`, `por_setor`, `alertas`, `custos`, `dimensoes` e `metodologia`.
Alertas exibem quantidade completa e até vinte exemplos, com `truncado` quando
necessário. Parâmetros adicionais: `proximos_dias=3`, `dias_sem_movimento=7`.
`intervalo_relatorio(periodo,referencia)` retorna `(deISO,ateISO)` inclusivo.
`ferramentas/relatorio_qualidade.py`: `gerar_excel(painel,tarefas,ocorrencias,
planos,horas,filtros=None)` e `gerar_pdf(...)` → bytes. Exportar somente dados
autorizados, neutralizar fórmulas e escape de markup. Custos sensíveis são
removidos nas rotas quando a permissão não existe, antes dos indicadores/exports.

DTOs incluem capacidades calculadas no servidor: `pode_editar`, `pode_comentar`,
`pode_validar`, `pode_transicionar`, `transicoes_permitidas`; horas incluem
`pode_cancelar`. Anexos nunca expõem `chave_objeto`. Todas as respostas destas
rotas incluem `Cache-Control: no-store`, inclusive erros de autorização.
