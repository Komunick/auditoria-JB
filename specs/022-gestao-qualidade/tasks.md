# Tarefas

- [x] T001 Ler o PDF original, mapear dez itens e definir contratos.
- [x] T002 Testes RED e núcleo/persistência de ocorrências, planos, horas e eventos.
- [x] T003 Testes RED de indicadores, alertas e relatórios Excel/PDF.
- [x] T004 Rotas, permissões, escopo por setor/pessoa e trilha de uso.
- [x] T005 Anexos privados com validação, autorização e armazenamento configurável.
- [x] T006 Interface integrada: painel, ocorrências, planos, horas e relatórios.
- [x] T007 Integração de notificações e modelos de atividades de todos os setores.
- [x] T008 Revisão independente, segurança, migração e regressão completa.
- [x] T009 Preview navegável com dados sintéticos e evidências por item do PDF.
- [x] T010 Roteiro de implantação e treinamento; limites operacionais documentados.
- [x] T011 Transição administrativa de dependências restrita a SHA de origem e
  árvore candidata, testes RED/GREEN e revisão independente do executor.
- [x] T012 Revisar os dez itens do pedido e unificar o semáforo de ocorrências
  e planos entre painel, lista e detalhe; testes RED/GREEN e preview local.
- [x] T013 Corrigir a sobreposição entre Administração e Minimizar o menu;
  validar rolagem, navegação por teclado e layout responsivo no preview local.

Revisão local de 04/11/2026: [cobertura e pendências](revisao-pdf-20261104.md).
A correção T012 está preparada para PR para `dev`; sua integração e implantação
dependem de autorização posterior. T013 foi integrada pelo PR #34 e publicada
pela promoção #36, com validação autenticada em 04/11/2026. Configuração real e
treinamento permanecem separados do aceite técnico.

Aceite local: [validacao.md](validacao.md). Publicação autorizada posteriormente
em 03/11/2026, incluindo correção do executor, PRs por merge commit e implantação
verificada na arm07. O resultado operacional deve ser conferido no relatório da
implantação; tarefas de código concluídas não comprovam deploy por si sós.
