# Tasks: Redesign Visual e Arquitetura de Interface (JB Fraga)

**Input**: Design documents from `/specs/028-redesign-visual/`  
**Prerequisites**: `plan.md`, `spec.md`, `checklists/requirements.md`

## Phase 1: Setup & Brand Assets

- [x] T001 Validar worktree `028-redesign-visual` a partir de `origin/dev` e rodar baseline da suíte `tests/test_*_ui.py` e `tests/test_web_*.py` (35/35 UI/web no baseline, 1 pulado sem Firebird)
- [x] T002 Copiar ativos oficiais transparentes da marca (`favicon-64.png`, `icon-192.png`, `symbol-256.png`, `logo-horizontal-light.png`, `logo-horizontal.png`) para `webui/img/` e remover uso de `logo.jpg`

## Phase 2: Tests First (TDD)

- [x] T003 Criar `tests/test_redesign_ui.py` validando antes da implementação:
  - existência dos ativos locais em `webui/img/` e ausência de URLs externas/CDN (`http://`, `https://` em `<link>`/`<script>`/`@import`/`url()`) em `webui/`
  - contraste WCAG AA (`>= 4.5:1`) entre os principais pares de tokens de `estilo.css` (claro, escuro e barra lateral `#060D28`)
  - integridade de elementos obrigatórios de `index.html` (login, bootstrap, gaveta mobile, paleta rápida, botões de abas)
  - comportamento de `app.js` em Node `vm`: alternância de tema, recolhimento da lateral, abertura/fechamento da gaveta mobile, filtragem de permissões na paleta rápida (`Ctrl+K`) e preservação das invariantes de `test_base_fiscal_ui.py`

## Phase 3: Design System, Shell & Login (US1 + US2)

- [x] T004 [US1] Atualizar `webui/index.html` com novo favicon/ícones locais, cena de login aprimorada (marca transparente, tema acessível no login, toggle de visibilidade de senha), sidebar reorganizada em 4 grupos semânticos com badges numéricos discretos, cabeçalho com botão de gaveta mobile e botão de paleta rápida (`Ctrl+K`) e container do modal de paleta
- [x] T005 [US1] [US2] Reescrever `webui/estilo.css` com paleta oficial JB Fraga (`#060D28` navy, `#C9A227` gold, ação esmeralda WCAG AA, 3 níveis de superfície para eliminar caixas duplas), tipografia local refinada, nova tela de login, nova lateral + gaveta responsiva (`<= 920px`), novo cabeçalho, paleta `Ctrl+K`, cartões, tabelas, formulários/dropzones, badges, modais e toasts nos temas claro e escuro
- [x] T006 [US1] [US2] Atualizar `webui/app.js` mantendo as invariantes literais de sessão/login e adicionando controle da gaveta mobile, paleta de comandos (`Ctrl+K`), botão de mostrar/ocultar senha no login/bootstrap, atualização limpa do breadcrumb/título com `data-numero` e proteção total contra XSS e `null` em DOM mínimo

## Phase 4: Central & Módulos (US3)

- [x] T007 [US3] Refinar `webui/inicio.js` (capa executiva com marca d'água transparente sem caixa JPEG branca, leitura limpa de `data-numero` para cartões de atalho, hierarquia de prioridades da Central preservando `#central-*` e contratos de `test_central_ui.py`)
- [x] T008 [US3] Atualizar `webui/qualidade.css` para alinhar integralmente a aba Gestão da qualidade aos novos tokens navy/gold/esmeralda e elevações de superfície nos temas claro e escuro
- [x] T009 [US3] Revisar módulos (`comparador.js`, `diff.js`, `conferencia.js`, `extracao.js`, `produtos.js`, `conciliacao.js`, `patrimonio.js`, `nfse.js`, `clientes.js`, `tarefas.js`, `admin.js`) e `estilo.css` (correção de checkboxes inline via `:has()`, espaçamento de upload/busca e quebra de células `colspan`) sem quebrar nenhum teste de contrato

## Phase 5: Verification & Visual Audit

- [x] T010 Executar `tests/test_redesign_ui.py` e toda a suíte `tests/test_*.py` do repositório (**115 total · 113 PASS · 2 SKIP [Firebird ausente] · 0 FAIL**)
- [x] T011 Subir o servidor em porta descartável (`8699`) com pasta de dados isolada e validar visualmente no navegador real (claro/escuro, desktop 1440px e mobile 390px) login, Central, paleta `Ctrl+K`, gaveta e ferramentas principais (0 erros de console, 0 exceções, 0 overflow horizontal)
- [x] T012 Atualizar `tasks.md` e validar conformidade final do diff (sem dados reais, sem CDN, sem build, sem regressões)

## Phase 6: Publicação

- [x] T013 PR #51 aberto para `dev`. Merge na `dev` e promoção para a `main` autorizados pela direção em 26/11/2026; sem Linear.
- [ ] T014 Conferir o ciclo do deploy automático na arm07 (SHA da `main` em `last_deploy`) e a interface nova no ar.
