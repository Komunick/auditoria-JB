# Tarefas recorrentes, consulta do setor e autorização de execução

Escopo local aprovado em 04/11/2026. Base: `dev` em
`101fe047908c7e580bcaff3013e4b6b3526e7e55`. Após a validação local, foram
autorizados commit, push e abertura de PR para a `dev`, na mesma data.
Merge, deploy e alterações em produção ou no Linear permanecem fora do escopo.

## Necessidade

A obrigação mensal deve continuar gerando tarefas nos meses seguintes, com
distribuição pela carteira. Integrantes autorizados precisam consultar o trabalho
do setor. O responsável pode permitir que um colega execute uma tarefa; um colega
também pode pedir essa autorização, sem assumir a tarefa antes da aprovação.

## Regras

1. A obrigação recorrente permanece cadastrada. A tarefa avulsa vale apenas para
   sua ocorrência. Uma tarefa por cliente, obrigação, competência e ocorrência;
   a quantidade de integrantes do setor não multiplica tarefas.
2. A geração automática existente processa cada setor/competência uma vez.
   Novas configurações de um mês já processado exigem geração manual com prévia.
3. Carteira define o responsável. Mudanças redistribuem tarefas abertas e
   preservam o responsável histórico das concluídas. Ausência de responsável
   mantém a tarefa na fila do setor.
4. `tarefas.consultar_setor` permite leitura dos setores ativos de participação
   atual. É uma concessão explícita, independente de gestão, execução e exportação.
5. A consulta inclui lista, detalhe, histórico, filtros, painel, agenda e Central.
   Não concede acesso adicional a Clientes, cofre, certificados ou Qualidade.
6. O responsável efetivo pode autorizar colegas ativos do mesmo setor, com acesso
   a Tarefas e permissão de execução. A autorização vale somente para uma tarefa;
   não altera a carteira nem o responsável original.
7. Um colega elegível que já pode consultar a tarefa pode solicitar execução.
   O pedido pendente não permite executar. O responsável efetivo aprova, recusa ou
   revoga, com justificativa. Gestão do setor não substitui essa aprovação.
8. Responsável e colegas autorizados podem iniciar, aguardar cliente, concluir e
   comentar. Conferir, dispensar, reativar, alterar prazo e redistribuir continuam
   exigindo as permissões e o escopo de gestão existentes.
9. Minhas tarefas inclui as próprias tarefas e as autorizações válidas recebidas.
   A conclusão registra quem executou. O histórico conserva solicitações,
   decisões e revogações. Uma autorização não se transfere para o próximo mês.
10. Revogação, mudança de responsável, perda do vínculo, inativação ou perda da
    permissão impedem execução. Retornar a carteira ou vínculo anterior não
    ressuscita uma autorização antiga. Reativação/devolução exige nova autorização.
11. Escritas verificam a revisão da tarefa e registram o evento na mesma transação.
    Pedidos/autorização duplicados e conclusão concorrente não produzem efeitos
    parciais. Identidade vem da sessão, nunca de campos enviados pelo cliente.

## Aceite

- Testes sintéticos demonstram novembro/dezembro de 2026, idempotência, carteira,
  tarefa avulsa, fila sem responsável e preservação da tarefa concluída.
- Leitura compartilhada não permite execução sem autorização nem consulta de
  outros setores. A nova permissão não é atribuída automaticamente.
- Autorização direta e pedido/aprovação funcionam; recusa, revogação, mudança de
  vínculo e conflitos de revisão bloqueiam ações indevidas.
- Responsável original, executor real e eventos permanecem verificáveis.
- Migração é aditiva/idempotente e conserva registros existentes.
- Testes anteriores e novos passam; demonstração navegável usa apenas dados
  fictícios e não envia e-mail nem executa o agendador real.
