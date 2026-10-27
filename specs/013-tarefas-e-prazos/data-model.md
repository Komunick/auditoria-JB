# Data Model: Tarefas e Prazos (clientes.db, schema 2)

Tudo aditivo sobre o schema 1 da spec 012. Datas ISO; carimbos em UTC; "hoje" em Salvador.

## cliente (colunas novas)

| Campo | Regra |
|---|---|
| contato_nome | texto, opcional (vem das planilhas de carteira) |
| contato_email | e-mail validado, opcional; destino futuro dos alertas ao cliente (P-03) |

## setor

| Campo | Regra |
|---|---|
| id, nome | nome único (Fiscal, Contábil, Pessoal, Legalização, Financeiro...) |
| responsavel_usuario_id | usuário titular (pode ser vazio) |
| ativo | 0/1 |

## setor_membro

`setor_id`, `usuario_id`, `desde`, `ate` (vazio = atual). Único (setor_id, usuario_id) quando `ate` vazio.

## substituicao

`titular_usuario_id`, `substituto_usuario_id`, `setor_id` (opcional: só naquele setor), `inicio`, `fim`,
`motivo`, `criada_por`. Sem sobreposição para o mesmo titular e setor (conferido em transação).

## caracteristica / cliente_caracteristica

- `caracteristica`: `id`, `grupo`, `nome`, `exclusiva_no_grupo` (0/1), `ativa`. Único (grupo, nome).
- `cliente_caracteristica`: `cliente_id`, `caracteristica_id`, `desde`, `marcada_por`. Único (cliente_id,
  caracteristica_id). Em grupo exclusivo, marcar uma desmarca as outras na mesma transação.

## carteira

`cliente_id`, `setor_id`, `responsavel_usuario_id`, `desde`, `atualizada_por`. Único (cliente_id,
setor_id).

## obrigacao

| Campo | Regra |
|---|---|
| id, setor_id, nome | único (setor_id, nome) |
| periodicidade | `mensal`, `trimestral`, `anual`, `demanda` |
| competencias | JSON: meses que geram (trimestral `[3,6,9,12]`; anual `[12]` etc.) |
| regra_vencimento | JSON validado (ver plan.md, decisão 2) |
| condicao | JSON `{"todas", "alguma", "nenhuma"}` sobre característica.id |
| inicio_antecedencia_dias | opcional |
| exige_conferencia | 0/1 |
| ativa | 0/1 |
| revision, criada_em, atualizada_em | |

Mudanças em obrigação ficam em `alteracao` (entidade `obrigacao`).

## ajuste_cliente

`cliente_id`, `obrigacao_id`, `tipo` (`incluir`, `excluir`, `vencimento`), `regra_vencimento` (só para
`vencimento`), `valido_de`, `valido_ate`, `motivo` (obrigatório), `criado_por`, `criado_em`.

## feriado

`data`, `descricao`, `abrangencia` (`nacional`, `estadual`, `municipal`), `origem` (`calculado`, `manual`),
`sem_expediente` (0/1). Único (data, abrangencia).

## tarefa

| Campo | Regra |
|---|---|
| id | |
| cliente_id, setor_id | obrigatórios |
| obrigacao_id | NULL = avulsa |
| competencia | `AAAA-MM` (avulsa pode ser vazia) |
| titulo | da obrigação ou digitado |
| responsavel_usuario_id | titular da carteira na geração; NULL = fila "sem responsável" |
| inicio, vencimento | datas |
| situacao | `a_fazer`, `em_andamento`, `aguardando_cliente`, `concluida`, `conferida`, `devolvida`, `dispensada` |
| exige_conferencia | copiado da obrigação na geração |
| concluida_em, concluida_por | |
| conferida_em, conferida_por, conferida_substituindo | |
| fora_do_prazo | 0/1, gravado na conclusão |
| origem | JSON: regra/ajuste que gerou, geração_id |
| revision, criada_em, atualizada_em | |

Único (cliente_id, obrigacao_id, competencia) quando `obrigacao_id` não é NULL. Índices: (setor_id,
situacao, vencimento), (responsavel_usuario_id, situacao, vencimento), (cliente_id, competencia).

## tarefa_evento (append-only por trigger)

`tarefa_id`, `tipo` (`criada`, `situacao`, `comentario`, `responsavel`, `vencimento`), `de`, `para`,
`comentario`, `usuario_id`, `usuario_login`, `substituindo_usuario_id`, `criado_em`.

## geracao

`competencia`, `setor_id`, `disparo` (`automatico`, `manual`), `usuario_login`, `criada_em`, `contagens`
(JSON). Único (competencia, setor_id, disparo='automatico'): a geração automática roda uma vez; a manual
pode rodar várias, porque a tarefa já é única.

## envio_alerta

`usuario_id`, `dia`, `canal` (`email`), `destino` (endereço), `quantidades` (JSON), `resultado` (`ok`,
`falha`, `desligado`), `erro` (texto curto, sem credencial), `criado_em`. Único (usuario_id, dia, canal).

## configuracao (chaves novas)

`tarefas_alerta_dias` (padrão 3), `tarefas_resumo_hora` (padrão "07:00"),
`tarefas_aguardando_cliente_dias` (padrão 5).
