# Contrato de leitura

Sem alteração de schema. Fonte: tarefa, cliente, setor e substituicao existentes.

## GET /api/tarefas/painel

Mesma permissão `aba.tarefas` e resolução de escopo de `/api/tarefas`.

Filtros-base: `visao=cliente` por padrão, `setor_id`, `cliente_id`,
`responsavel_usuario_id` (efetivo), `competencia`, `texto`. Aceitar também os
filtros existentes de situação, vencimento e sem responsável para equivalência
com a lista. Limites de texto/paginação explícitos e erros 422.
`texto` remove espaços nas extremidades e aceita no máximo 200 caracteres.

Seletor `fila=pendentes` por padrão; opções: `todas`, `pendentes`, `atrasadas`,
`hoje`, `proximas`, `aguardando_cliente`, `conferencia`, `sem_vencimento`,
`sem_responsavel`. `pagina=1`, `limite=10`, limite máximo 200.

Resposta:

```text
{
  hoje: ISO date, fuso: "America/Bahia", alerta_dias: integer,
  filtros: filtros-base normalizados,
  resumo: {
    total, por_situacao: {chave: contagem}, abertas, pendentes,
    pendentes_conferencia, atrasadas, vencendo_hoje, proximas,
    aguardando_cliente, sem_vencimento, sem_responsavel
  },
  por_responsavel: [{id: integer|null, nome, total, abertas, pendentes,
                    atrasadas, pendentes_conferencia}],
  fila: {itens: [DTO atual de tarefa], total, pagina, limite, paginas}
}
```

Resumo e distribuição consideram escopo + filtros-base, ignorando seletor fila.
A fila usa os mesmos filtros acrescidos da categoria escolhida. Totais e fila
vêm de uma única transação de leitura. `por_responsavel` usa o responsável
efetivo na data; `null` aparece como Sem responsável. Não expor responsáveis de
registros fora do escopo. DTO mantém flags pode_executar/pode_gerir atuais.

## Lista e exportação

Adicionar `texto`, `fila`, `abertas` e `pendente_conferencia` aos filtros HTTP
compartilhados de `/api/tarefas` e `/api/tarefas/exportar`. Sem fila conserva
consulta anterior. Fila inválida é erro, nunca ignorada. Sem vencimento não
entra em filtros de faixa de datas. `abertas` legado inclui conferência pendente.

## Navegação do frontend

O evento `tarefas:abrir` recebe `detail={filtros:{visao,competencia,cliente_id,
setor_id,responsavel_usuario_id,texto,...},fila,tarefa_id?}`. A aba mantém controles visíveis em acordo com a
consulta; nunca transportar permissão ou autor de mutação pelo evento.
Resposta antiga não prevalece sobre filtro novo. Data civil exibida sem UTC.
