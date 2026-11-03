# Seleção de tarefas e filtros combinados

## Solicitação e aceite

Em 03/11/2026, foi aprovado melhorar a seleção de tarefas por opções, investigar
listas vazias ao combinar filtros e conferir a ação Limpar. Implementação e
validação locais com dados sintéticos, sem publicação ou alteração da produção.

## Comportamento

- O campo **Tarefa** é uma lista de títulos distintos de todas as tarefas
  autorizadas na visão atual, incluindo avulsas, concluídas e itens além da
  primeira página. Selecionar um título usa igualdade exata; nomes semelhantes
  ou caracteres como `%` e `_` não ampliam a consulta.
- **Busca complementar (opcional)** conserva a busca parcial e o contexto
  recebido da Central. É possível usar todos os filtros principais sem digitar.
- Os filtros continuam combinados por interseção. Não foi identificada perda de
  tarefas no SQL com filtros compatíveis. A ausência de resultados pode decorrer
  de filtros sem correspondência, de uma visão sem tarefas ou de uma combinação
  impossível. A interface diferencia essas situações e explica o escopo de
  Minhas tarefas, Setor e Agenda do cliente.
- A interface sinaliza responsável definido + sem responsável, fila sem
  responsável em Minhas tarefas, fila sem vencimento + datas e situações
  encerradas combinadas com pendências. Datas invertidas são recusadas também
  pelo servidor. Competência e vencimento continuam conceitos separados.
- **Limpar** remove título, busca, identificadores, competência, datas, situação
  e indicadores adicionais; seleciona Todas as tarefas e volta à página 1,
  preservando a visão e as permissões.
- Respostas antigas e de sessões encerradas são descartadas. Uma resposta de
  opções não desfaz uma escolha feita durante o carregamento.

## Contrato e persistência

`GET /api/tarefas/opcoes-filtros?visao=...` retorna `titulos` e `total_escopo`,
com autorização no servidor, snapshot de leitura e `Cache-Control: no-store`.
Não aceita filtros de negócio para recortar as opções. O filtro opcional
`titulo` (até 200 caracteres) está disponível na listagem, painel e exportação.
O filtro parcial `texto` continua compatível. Sem alteração de schema ou migração.

## Validação local

Os testes novos falharam antes da implementação e passaram depois. Dez scripts
passaram, sem skips nesta seleção:

- `test_filtros_tarefas.py`: 214 tarefas autorizadas, título literal, opções
  completas, combinações, intervalo de datas, autenticação, isolamento de
  setores, substituição e paridade da exportação.
- `test_tarefas_filtros_ui.py`: eventos reais com DOM/API sintéticos, escolha,
  mensagens, limpeza, contexto da Central, concorrência e encerramento de sessão.
- Regressões: `test_painel_tarefas.py`, `test_web_tarefas.py`,
  `test_tarefas_store.py`, `test_tarefas_ui.py`, `test_central_ui.py`,
  `test_relatorio_tarefas.py`, `test_web_agenda_periodos.py`, `test_tarefas.py`.

No navegador local, com 12 tarefas fictícias: Minhas tarefas mostrou 6; selecionar
Conferir documentos mostrou 1 em Minhas e 2 na Agenda; combinar com Aurora
Comércio retornou 1; com Ateliê Solar retornou 0 e mensagem explicativa; Limpar
restaurou 12 na Agenda. Título, cliente, setor, responsável, competência outubro,
vencimento novembro, situação e pendências juntos retornaram a tarefa esperada.
Os avisos de filtros incompatíveis e a fila sem vencimento também foram
conferidos. Nenhum erro de JavaScript foi registrado no preview.

Revisão independente encontrou uma resposta tardia sobrescrevendo a seleção
mais recente; o caso ganhou teste de regressão e foi corrigido. A revisão final
não encontrou outros defeitos acionáveis. `git diff --check` passou.

Limitação: a captura enviada pelo usuário não demonstra a configuração nem os
dados de produção. Esta validação comprova os cenários sintéticos, sem afirmar
qual deles explica a lista vazia naquele ambiente.

Uma pasta temporária sintética da primeira execução com falha permaneceu no
Windows após um lock SQLite. A revisão automática bloqueou sua exclusão; nenhuma
tentativa de contorno foi feita. O teste passou a fechar seus recursos e limpou
normalmente o temporário da execução aprovada. Não houve impacto em produção.
