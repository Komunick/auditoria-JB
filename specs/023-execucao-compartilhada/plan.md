# Plano técnico

## Decisões

- Reutilizar o processo FastAPI, JavaScript estático, sessões e clientes.db.
- Preservar o agendador e a trava por competência/setor. Melhorar a orientação
  da interface e testar o fluxo integrado, sem mudar a semântica de recorrência.
- Separar setores consultáveis de setores geridos. Não ampliar `_geridos` nem
  reaproveitar `tarefas.setor` para a concessão de leitura.
- Persistir pedidos e autorizações por tarefa com contexto de responsável,
  vínculo e substituição. Múltiplos colegas podem receber autorização; a revisão
  da tarefa serializa as alterações e impede dupla conclusão.
- Store valida domínio sem importar web. Um callback informa a elegibilidade de
  execução atual; as rotas fornecem usuário ativo, aba e permissão.
- Incorporar IDs de tarefas autorizadas ao predicado compartilhado de consulta,
  antes de paginação, totais ou exportação. Detalhe usa a mesma autorização.
- Autorização concluída pode manter leitura do histórico pelo executor enquanto
  seu contexto permanecer válido; não permite alterar uma tarefa encerrada.

## Contratos HTTP

Todos os POSTs exigem sessão, aba, execução, revisão e justificativa. A rota
revalida escopo sob a transação de escrita.

| Rota relativa a `/api/tarefas` | Entrada | Efeito |
| --- | --- | --- |
| `/{id}/execucao/autorizar` | `usuario_id`, `revision`, `motivo` | Responsável autoriza um colega |
| `/{id}/execucao/solicitar` | `revision`, `motivo` | Usuário da sessão pede execução |
| `/{id}/execucao/{autorizacao_id}/decidir` | `acao`, `revision`, `motivo` | Responsável aprova, recusa ou revoga |

`acao`: `aprovar`, `recusar`, `revogar`. O catálogo acrescenta
`setores_consultaveis`. O DTO de tarefa acrescenta `execucao_delegada` e preserva
as capacidades de gestão. O detalhe inclui `execucao` com capacidades,
candidatos elegíveis e registros de pedidos/autorizações. `pode_executar` considera
responsável ou autorização válida. Erros de revisão retornam 409.

## Entrega e verificação

TDD em store, rotas e interface. Testes incluem acesso direto por ID, filtros,
paginação, exportação, sessão antiga, autorização revogada, troca de carteira,
vínculo e concorrência. Regressão cobre os consumidores de Tarefas, incluindo
Central, Qualidade e agendador. Demonstração em loopback com contas fictícias,
diretório de dados próprio e SMTP/agendador desabilitados.

Não há novo serviço, cron ou dependência. Após a validação local, commit, push
e abertura de PR para a `dev` foram autorizados em 04/11/2026. Nenhuma operação
em produção, merge, deploy ou alteração no Linear faz parte desta publicação.
