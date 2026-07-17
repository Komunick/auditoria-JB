# Tasks — Controle de acesso por usuário e histórico de acessos

Todas concluídas: o código foi implementado e validado (26/26 testes da casa
passam, incluindo o novo `tests/test_web_permissoes.py`, e a verificação no
navegador). Referência: [spec.md](./spec.md) e [plan.md](./plan.md).

## P0 — Núcleo de permissões e auditoria (US1, US2)
- [X] T001 web/permissoes.py: catálogo de 21 permissões (5 abas + ações
      sensíveis + 2 admin), tabela `permissao_usuario` (concessões de não-admin),
      admin com tudo implícito, validação de slug, PADRAO_NOVO_USUARIO
- [X] T002 web/auditoria.py: registro `ACOES`, dependency `acesso("<slug>")`
      (autentica + aba + ação + marca p/ histórico), `exigir_aba()` para leitura,
      `exigir_permissao()` para checagem pontual (lote), `detalhar()`
- [X] T003 web/auditoria.py: tabela `evento` (índices por data e por usuário),
      `registrar()`, middleware que grava após a resposta (inclusive 500),
      `registrar_login()`, `varrer_sessoes_expiradas()`, `consultar()` filtrável
- [X] T004 web/auth.py: `conexao()` pública (banco compartilhado por 3 módulos),
      gestão de usuários (listar/obter/atualizar/trocar senha), guarda do último
      admin com `BEGIN IMMEDIATE`, sessão expirada com hora real do vencimento

## P1 — API de administração e pontos de entrada (US1, US2)
- [X] T010 web/rotas_admin.py: /api/admin/usuarios (listar/criar/editar/senha),
      /permissoes, /historico (filtros) e /historico/exportar (CSV com todas as
      linhas); nomeia o alvo no histórico mesmo em tentativa recusada
- [X] T011 web/servidor.py: middleware do histórico, login/logout/bootstrap
      auditados, varredura de sessões vencidas no login, rota de navegação por
      aba, sessões de trabalho exigindo a aba, `Cache-Control: no-cache`,
      bloqueio de auto-rebaixamento

## P2 — Permissões e auditoria nas 5 ferramentas (US3)
- [X] T020 rotas_conferencia.py: 11 rotas com acesso/exigir_aba; lote exige
      `conferencia.corrigir_lote`; resumo do SPED corrigido; detalhe fiel no
      histórico
- [X] T021 rotas_comparador.py + rotas_diff.py + rotas_extracao.py: uploads,
      comparações/extração e exportações com permissão e auditoria
- [X] T022 rotas_produtos.py: upload/auditar/corrigir/relatorio/nova-base com
      permissão e auditoria; leitura por `exigir_aba("produtos")`

## P3 — Frontend: administração, recorte e segurança (US1, US2, US3)
- [X] T030 webui/app.js: objeto `Sessao` (permissões), filtro de abas, registro
      de navegação, helper `esc()` (anti-XSS), fechar modais ao cair a sessão
- [X] T031 webui/admin.js + index.html + estilo.css: aba Administração
      (usuários + permissões em grupos; histórico filtrável e exportável),
      aviso "sem acesso", cracha de perfil, realces herdados do desktop
- [X] T032 conferencia/produtos/diff/comparador/extracao.js: esconder os
      controles sem permissão; escapar dados de terceiros/observações nas tabelas
      (fecha o XSS armazenado)

## P4 — Testes e documentação
- [X] T040 tests/test_web_permissoes.py: abas/ações por usuário, 403 em negadas,
      bloqueio de lote, mudança de permissão na hora, último admin protegido,
      auto-rebaixamento barrado, paginação/overflow, 500 auditado, filtro do
      usuário só-histórico, CSV completo, trilha entrada/navegação/ação/saída
- [X] T041 README-servidor.md (seção de usuários, permissões e histórico) +
      README.md (testes web listados)
- [X] T042 Rodar toda a suíte (26/26) + smoke no navegador (junior recortado,
      admin completo, XSS neutralizado, self-lockout barrado, corrida do último
      admin) + commit
