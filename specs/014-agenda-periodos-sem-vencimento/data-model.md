# Modelo de dados e contratos

## clientes.db, schema 3

- Nova coluna: `tarefa.ocorrencia INTEGER NOT NULL DEFAULT 1`.
- Índice único: `(cliente_id, obrigacao_id, competencia, ocorrencia)` quando `obrigacao_id IS NOT NULL`.
- `vencimento=''` representa ausência explícita de vencimento, gerada por regra `sem_vencimento`; manter o tipo e o NOT NULL existentes.
- `origem` acrescenta ocorrência e o intervalo aplicado quando houver. Conservar regra efetiva, revisão, ajustes e proveniência já existentes.
- Nenhuma alteração de identidade, evento histórico, certificado, cifra ou cadastro anterior.

## Obrigação e API

`regra_vencimento` continua JSON; novas variantes conforme plan.md. Campos HTTP de obrigação não precisam ganhar nomes paralelos. O contrato de resposta de tarefa acrescenta `ocorrencia` e continua usando strings ISO para datas presentes e string vazia para vencimento ausente.

Filtros de faixa de vencimento excluem tarefas sem data. Ordenação as apresenta depois das tarefas com vencimento, com desempate estável. Conclusão de tarefa sem prazo mantém `fora_do_prazo=false`, mas a interface distingue ausência de prazo de conclusão pontual.

## Compatibilidade

Leitura e migração de schema 1 e 2 preservadas. O esquema muda para versão 3; voltar ao código anterior exige análise de compatibilidade e não deve ser feito por restauração cega de bancos. A documentação operacional deve informar essa migração.
