# Reativação de tarefas e ajuste individual de vencimento

Implementação aprovada em 04/11/2026, com testes sintéticos e preview local.
A publicação por commit, push e PR para `dev` foi autorizada em etapa posterior,
no mesmo dia. Merge, deploy, produção e Linear continuam fora do escopo.

## Problema

A tarefa dispensada não tinha ação para voltar à fila. Depois de criar uma
tarefa, também não havia operação para corrigir apenas seu vencimento. Editar
a obrigação já preserva as tarefas geradas e vale para gerações futuras.

## Comportamento esperado

- Administradores e responsáveis pelo setor, com a permissão de gestão vigente,
  podem reativar uma tarefa dispensada. A substituição vigente segue as mesmas
  regras de gestão do setor.
- Reativar exige motivo e devolve a mesma tarefa para `a_fazer`. Identidade,
  responsável, início, vencimento, regra de origem e histórico são preservados.
  A operação não reabre tarefas concluídas ou conferidas.
- O gestor pode alterar o vencimento de uma tarefa aberta. A alteração exige
  uma data válida, igual ou posterior ao início previsto, e um motivo. Não
  remove o prazo nem altera o início. Uma tarefa sem prazo pode receber uma
  data explícita; a regra da obrigação continua preservada.
- A nova data é o vencimento final escolhido para aquela tarefa. Esta operação
  não reaplica automaticamente a regra de feriado ou fim de semana da obrigação.
- Uma tarefa dispensada precisa ser reativada antes de editar seu vencimento.
  Tarefas concluídas e conferidas mantêm seus prazos e resultados históricos.
- A alteração individual não modifica outras tarefas, obrigações, ajustes por
  cliente, competências ou gerações futuras. Informar a mesma data é recusado
  sem criar evento artificial.
- Ambas as operações exigem a revisão atual. Revisão desatualizada, falta de
  permissão ou dados inválidos não produzem alterações parciais.
- O histórico registra usuário, data, valores anterior e novo e motivo na mesma
  transação da alteração. Eventos anteriores continuam imutáveis.

## Contratos

- `POST /api/tarefas/{id}/situacao`: reativação com `situacao="a_fazer"`,
  `revision` e `motivo` ou `comentario`, partindo de `dispensada`.
- `POST /api/tarefas/{id}/vencimento`: `vencimento="YYYY-MM-DD"`, `revision`
  e `motivo` obrigatório, com até 4.000 caracteres.
- Os DTOs informam `pode_reativar` e `pode_alterar_vencimento`. A interface usa
  essas capacidades; a autorização continua sendo conferida no servidor.
- Não há migração de schema ou nova permissão.

## Interface

O detalhe apresenta Reativar tarefa ou Alterar vencimento conforme a situação
e as permissões. Cada formulário explica seu efeito antes de salvar; cancelar
não envia a operação. Erros preservam os campos para correção. O histórico
mostra as duas datas na alteração de vencimento, usando Sem vencimento quando
o valor anterior estiver vazio.

No cadastro da obrigação, Dia do vencimento é o dia-base da regra escolhida,
sujeito ao ajuste de expediente. Dia fixo de início é a data planejada no mês
seguinte à competência; registrar o andamento é uma ação separada. A edição
da obrigação explica que tarefas existentes são ajustadas pelo próprio detalhe.

## Verificação

- [x] Reproduzir os dois problemas com testes antes da alteração.
- [x] Validar reativação, prazo individual, isolamento e histórico no núcleo/store.
- [x] Validar permissões, substituição, concorrência e atomicidade via HTTP.
- [x] Validar ações, formulários, erros e histórico na interface.
- [x] Demonstrar o fluxo no navegador com dados fictícios.
- [x] Executar regressão proporcional e revisão independente.

## Resultado local — 04/11/2026

RED registrado no núcleo/store, HTTP e UI antes de implementar. O teste
`test_tarefas_reativacao_prazo.py` passou em dez casos, incluindo revisão
concorrente, rollback quando o evento falha, troca de chefia durante a gravação,
gestor sem permissão de executar, substituto vigente, atribuição de prazo a uma
tarefa sem vencimento e preservação de atraso histórico. O teste
`test_tarefas_acoes_ui.py` cobre formulários, cancelamento, erro de revisão,
atualização da revisão após salvar, troca de sessão e histórico como texto seguro.

A regressão de **18 scripts passou sem falhas ou testes pulados**, cobrindo
tarefas, regras de prazo, filtros, Central, agenda, relatórios, alertas,
agendador e consumidores da Gestão da qualidade. Os arquivos de código e teste
permaneceram idênticos durante a execução. Revisão independente do backend e
da interface sem achados bloqueantes; `git diff --check` aprovado.

No navegador, em `http://127.0.0.1:8627/`, a tarefa fictícia da Empresa Aurora
foi reativada para A fazer e teve o prazo alterado de 20/12/2026 para 22/12/2026.
O histórico e o novo prazo persistiram após recarregar e abrir a tarefa pela
Central. Cancelar a reativação não gravou evento. Salvar a mesma data mostrou
erro e preservou o motivo digitado, sem acrescentar evento.

A conferência independente do banco confirmou quatro tarefas, apenas dois
novos eventos e preservação dos eventos anteriores, da origem e do responsável.
As outras três tarefas ficaram idênticas ao inventário inicial, inclusive a
tarefa da Empresa Horizonte, com vencimento em 20/12/2026. A regra da obrigação
continuou no dia 20. `integrity_check` aprovado e zero violações de FK.

Evidências locais em `tmp/correcao-tarefas-20261104`: logs RED/GREEN em `backend`
e `ui`, relatório e manifestos em `regressao`, capturas e conferência dos dados
em `navegador`. Bancos e credenciais fictícias ficam fora do Git. O preview usa
cookie próprio e loopback, com agendador, SMTP e S3 desligados. Os testes HTTP
precisaram executar com sockets locais liberados, pois o sandbox bloqueava a
criação do loop do TestClient antes de alcançar as rotas.

Na etapa de implementação, não houve commit, push, merge, deploy ou acesso à
produção e ao Linear. As dez alterações locais preexistentes do semáforo, menu
e documentação foram conferidas por hash e preservadas.

## Preparação do PR para dev — 04/11/2026

Branch `codex/reativacao-vencimento-tarefas`, criado em checkout separado a
partir de `origin/dev` no commit `4bdcdd5054c9291a159b864d09a5163775c15516`.
O diff inclui quatro arquivos funcionais, dois testes novos e este documento.
As correções do menu lateral e do semáforo ficaram fora do PR; não há
dependência funcional delas para estas ações de tarefas.

Os mesmos **18 scripts foram executados novamente no checkout isolado**, sem
falhas ou testes pulados. Os manifestos confirmam que nenhum arquivo de código
ou teste mudou durante essa execução. Evidências em
`tmp/publicacao-tarefas-20261104/regressao`, fora do Git. A revisão independente
conferiu o escopo, os contratos e as evidências, sem bloqueios de publicação.

A autorização desta etapa abrange commit, push do branch e abertura de PR
para `dev`. Não inclui merge, promoção para `main`, deploy ou alterações em
produção e no Linear.
