# Tasks: Tarefas e Prazos

Testes antes da implementação em cada fase. `[US#]` = história da spec. Nenhuma tarefa depende das
pendências para ser feita; elas só mudam dados (catálogo, configuração).

## Fase 1 — Núcleo

- [x] T001 [US3] `tests/test_regras_vencimento.py`: competências mensal/trimestral/anual; "dia N do mês
  seguinte"; "último dia útil"; dia 30 em fevereiro; antecipar/adiar/manter em sábado, domingo e feriado;
  Páscoa e móveis de 2026–2030 conferidos contra datas conhecidas; regra inválida recusada.
- [x] T002 [US3] `core/regras_vencimento.py`.
- [x] T003 [US5][US6] `tests/test_tarefas.py`: aplicabilidade (todas/alguma/nenhuma, vazio); transições
  válidas e inválidas (conferida sem concluir, dispensar sem motivo); cor por situação e data; atraso e
  "fora do prazo".
- [x] T004 [US5][US6] `core/tarefas.py`.
- [x] T005 [US8] `tests/test_planilha_carteira.py`: `.xls` e `.xlsx` sintéticos no formato das planilhas
  do DP (título na linha 1, cabeçalho na 2, Empresas/Contato/Local/Atividade/E-mail/checklist/Observação);
  observação vira sugestão de característica; e-mail inválido sinalizado.
- [x] T006 [US8] `core/planilha_carteira.py` + `xlrd>=2.0` nos dois requirements.

## Fase 2 — Persistência

- [x] T007 `tests/test_tarefas_store.py`: migração 1→2 sem perda (banco da spec 012 com dados);
  setores e membros; substituição sem sobreposição e `responsavel_efetivo` antes/durante/depois;
  característica exclusiva; carteira e troca de responsável só nas abertas; obrigação + ajuste
  (incluir/excluir/vencimento com validade); geração idempotente (duas vezes, concorrente); cliente
  baixado/inativo; sem responsável vai para a fila; eventos imutáveis; revision.
- [x] T008 `ferramentas/tarefas_store.py`.
- [x] T009 [US7] `tests/test_alertas_email.py`: montagem do resumo por pessoa (titular + substituído +
  conferências do setor); um por dia; desligado sem SMTP; falha registrada sem a senha; um servidor SMTP
  mínimo do próprio teste (socket local em thread — o módulo `smtpd` não existe mais no Python 3.12 da
  VM) recebe a mensagem.
- [x] T010 [US7] `ferramentas/alertas_email.py`.
- [x] T011 [US9] `ferramentas/relatorio_tarefas.py`.

## Fase 3 — Web

- [x] T012 `tests/test_web_tarefas.py`: 401/403; slugs fora do padrão; colaborador só vê e muda as
  próprias; responsável vê o setor só enquanto responde (substituição com data); diretoria vê tudo;
  configuração exige `tarefas.configurar`; geração manual com prévia; importação de carteira com prévia
  de uso único; exportação; trilha de uso sem dado pessoal.
- [x] T013 Permissões, ações da trilha, rotas e registro no servidor; atalhos de perfil na
  administração.
- [x] T014 `web/agendador.py`: thread no startup; teste com relógio injetado (gera no dia 1º, não repete,
  retoma depois de desligado; resumo depois do horário, uma vez).
- [x] T015 `webui/tarefas.js` e aba 10: Minhas tarefas, Setor, Agenda do cliente, Configuração
  (características, obrigações, ajustes, feriados, setores e substituições), Importar carteira; aviso no
  topo; cores; filtros; ações em lote.
- [x] T016 Aba 9: campos de contato e e-mail do cliente, e as características e a carteira na ficha.

## Fase 4 — Fechamento

- [x] T017 Suíte inteira; conferência no navegador com dados sintéticos.
- [x] T018 README-servidor: variáveis SMTP, agendador, primeiro uso (setores → características →
  obrigações → carteira → geração).
- [ ] T019 Carregar o catálogo do Fiscal quando a P-01 chegar (dado, não código).

Implementação T001–T018 validada em 27/10/2026. Estado final: 70 scripts
aprovados, 2 pulados por ausência do motor Firebird, sem falha pendente.
O teste da Conciliação foi repetido após a correção da concorrência encontrada
na suíte completa. Evidências e limites em [validation.md](validation.md).
T019 depende da lista da JB; o catálogo inicial permanece vazio.
