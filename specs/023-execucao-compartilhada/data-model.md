# Dados e validade da autorização

`tarefa_execucao_autorizacao` guarda a tarefa, o executor autorizado, o solicitante,
quem decidiu, estado, contexto, motivos e datas. Estados: `pendente`, `autorizada`,
`recusada`, `revogada`. Um índice parcial impede dois registros pendentes ou
autorizados para a mesma pessoa na mesma tarefa.

Cada solicitação, autorização, decisão e revogação incrementa `tarefa.revision`
e acrescenta um `tarefa_evento` imutável na mesma transação. Atualizar o estado do
pedido não apaga o evento anterior. A conclusão conserva o responsável original
em `responsavel_usuario_id` e grava o executor real em `concluida_por`.

O contexto contém titular, responsável efetivo, IDs dos vínculos atuais e marcos
do histórico de carteira, tarefa, setor e substituição. Ao consultar ou executar,
o contexto é comparado com o atual; autorização antiga não acompanha mudança de
responsável nem volta a valer quando a carteira ou o vínculo retorna. Uma nova
concessão encerra um registro obsoleto antes de inserir o substituto e registra
esse encerramento no histórico.

Atividade e permissão de execução são verificadas no banco de autenticação em
cada chamada, por callback. Não há cópia nem histórico de permissões nesse banco
de tarefas. Remover uma permissão bloqueia a autorização enquanto ela estiver
ausente; uma remoção e reconcessão sem mudança de contexto não equivalem a uma
revogação permanente da autorização. Para isso existe a ação Revogar.

A tabela e seus índices são criados aditivamente com `IF NOT EXISTS`. Não há
reescrita de tarefas, carteiras, obrigações ou eventos anteriores. O número de
schema já existente não é reduzido; a tabela complementa o schema de Tarefas e
coexiste com o schema 4 de Qualidade.
