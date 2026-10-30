# Tarefas

- [x] T001 Especificar contrato, limites, modelo e checklist.
- [x] T002 Testes RED e persistência atômica, proveniência e recibo idempotente.
- [x] T003 Testes RED e autorização, preparação, confirmação e descarte HTTP.
- [x] T004 Testes RED e interface com confirmação, expiração e isolamento de sessão.
- [x] T005 Revisão independente de integridade, autorização e concorrência.
- [x] T006 Regressão integral e conferência sintética no navegador local.
- [x] T007 Registrar evidências e atualizar documentação.
- [x] T008 Corrigir Limpar prévia para descartar a preparação no servidor,
  incluindo respostas atrasadas, expiração e nova tentativa após falha.
- [x] T009 Cobrir descarte sem carga, isolamento de sessão e confirmação já
  enviada com testes sintéticos e revisão independente.
- [x] T010 Registrar a regressão final e a conferência local do cancelamento.

Concluída localmente em 30/10/2026. Validação final: 89 scripts aprovados,
2 opcionais Firebird pulados, nenhuma falha, código estável durante a suíte.
Fluxo sintético no navegador e integridade do banco aprovados. Evidências e
limitação de limpeza local em [validacao.md](validacao.md). A validação foi
executada sem operações no Linear ou na produção e antes de commit, push,
merge ou deploy.
