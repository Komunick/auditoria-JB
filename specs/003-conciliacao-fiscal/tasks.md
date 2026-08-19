# Tasks: Conciliação Fiscal — Receita e DIMP

**Input**: documentos em `/specs/003-conciliacao-fiscal/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md` e
`contracts/`.

**Tests**: obrigatórios. Em cada fatia, escrever/ajustar testes, observar a
falha esperada e só então implementar. Seguir o padrão `main()` + `OK/FALHOU`
do repositório, sem converter toda a suíte para pytest.

**Format**: `[ID] [P?] [Story] descrição com caminho exato`.

## Phase 1 — Setup e baseline

**Purpose**: preservar o estado atual e criar dados de teste sem dados fiscais
reais.

- [x] T001 Criar branch de trabalho para `003-conciliacao-fiscal`, confirmar o
  commit-base atual e registrar divergências em
  `specs/003-conciliacao-fiscal/implementation-log.md`, sem editar documentação
  normativa nem sobrescrever trabalho alheio.
- [x] T002 Executar todos os scripts `tests/test_*.py` aplicáveis no ambiente e
  registrar o baseline (passou/falhou/pulado e motivo) no handoff de execução.
- [x] T003 [P] Criar geradores/fixtures sintéticas de Quadro 50-5, Quadro
  50-3/DIMP e planilha-mestre em `tests/fixtures/conciliacao/`, usando CNPJ
  sintético válido e sem nomes/valores reais.
- [x] T004 [P] Inspecionar a árvore/importações atuais e registrar no handoff o
  baseline dos limites entre `core/`, `ferramentas/` e `web/`; o teste
  executável dos módulos novos será criado junto com T020, depois que os
  módulos existirem.

**Checkpoint**: baseline conhecido e fixtures sintéticas suficientes para CI.

---

## Phase 2 — Foundational: propriedade de sessões/jobs e infraestrutura

**Purpose**: fechar a fragilidade transversal que bloqueia uma ferramenta
fiscal multiusuário.

**CRITICAL**: nenhuma rota da nova ferramenta pode ser liberada antes desta
fase.

- [x] T005 [P] Adicionar a `tests/test_web_permissoes.py` cenários em que dois
  usuários autenticados tentam consultar e descartar sessão alheia e consultar
  job alheio; observar que falham no código atual.
- [x] T006 Alterar `src/auditoria_fiscal/web/sessoes.py` para que
  `obter_sessao()` valide proprietário **e a ferramenta esperada**, sem revelar
  existência de recurso alheio. FR-005 e SEC003 exigem as duas validações
  (MUST); o parâmetro de ferramenta pode ter default vazio na assinatura por
  compatibilidade, mas toda rota que consome uma sessão é obrigada a informá-lo
  e isso é conferido no fechamento da fase.
- [x] T007 Alterar `src/auditoria_fiscal/web/sessoes.py` para que jobs carreguem
  owner e `obter_job()` o valide por usuário/sessão, aceitando também a
  ferramenta esperada. A validação de ferramenta do job só fica completa em
  T069, porque a rota de polling é compartilhada com as cinco ferramentas
  anteriores.
- [x] T008 Atualizar `src/auditoria_fiscal/web/servidor.py` e todas as chamadas
  em `src/auditoria_fiscal/web/rotas_{comparador,conferencia,diff,extracao,produtos}.py`
  para passar o usuário e a ferramenta esperada.
- [x] T009 Atualizar os scripts `tests/test_web_*.py` afetados e confirmar que
  isolamento, fluxos existentes e polling continuam funcionando.
- [x] T010 [P] Adicionar `caminho_db_conciliacao()` e
  `pasta_origens_conciliacao()` em `src/auditoria_fiscal/web/infra.py`, sempre
  abaixo de `AUDITORIA_WEB_DADOS`.
- [x] T011 [P] Registrar o limite configurável
  `AUDITORIA_CONCILIACAO_MAX_UPLOAD_MB` com default 50 MB em
  `src/auditoria_fiscal/web/rotas_conciliacao.py`, sem mudar o teto genérico
  necessário às bases FDB.

**Checkpoint**: um usuário não consegue operar sessão/job de outro e toda a
suíte web anterior permanece verde. Conferir também que **nenhuma** rota
consumidora de sessão deixou de informar a ferramenta esperada (T006). A
amarração de ferramenta do **job** fica pendente de T069 e não bloqueia este
checkpoint.

---

## Phase 3 — User Story 1: acesso nativo à sexta ferramenta (P1)

**Goal**: criar o portão de acesso e o esqueleto visual/API dentro do sistema
existente.

**Independent Test**: admin vê e abre a aba; usuário autorizado também; usuário
sem `aba.conciliacao` não vê e recebe 403 em chamada direta.

### Tests

- [x] T012 [P] [US1] Adicionar ao `tests/test_web_permissoes.py` o catálogo,
  concessão/remoção imediata e negação da aba `conciliacao`.
- [x] T013 [P] [US1] Criar esqueleto de `tests/test_web_conciliacao.py` com 401,
  403, criação de sessão da ferramenta e navegação auditada.

### Implementation

- [x] T014 [US1] Adicionar `GRUPO_CONCILIACAO` e os oito slugs definidos no
  plano em `src/auditoria_fiscal/web/permissoes.py`; incluir exatamente
  `aba.conciliacao` e `conciliacao.importar` em `PADRAO_NOVO_USUARIO`, não
  incluir os outros seis e não alterar permissões de usuários existentes.
- [x] T015 [US1] Adicionar as ações da conciliação em
  `src/auditoria_fiscal/web/auditoria.py`, separando processamento, mutação e
  download.
- [x] T016 [P] [US1] Criar `src/auditoria_fiscal/web/rotas_conciliacao.py` com
  router, uma leitura protegida de resumo vazio e contratos de erro comuns.
- [x] T017 [US1] Registrar o router antes do mount estático em
  `src/auditoria_fiscal/web/servidor.py`.
- [x] T018 [P] [US1] Adicionar botão, section e script da sexta ferramenta em
  `webui/index.html` sem renumerar as cinco anteriores.
- [x] T019 [US1] Criar `webui/conciliacao.js` com
  `Abas.registrar("conciliacao", ...)`, shell de subtelas e uso exclusivo dos
  helpers compartilhados de `webui/app.js`.

**Checkpoint**: a sexta ferramenta existe nativamente, mas ainda mostra estado
vazio; autorização funciona ponta a ponta.

---

## Phase 4 — User Story 2: importação segura e idempotente (P1)

**Goal**: receber lotes, reconhecer os dois layouts, persistir versões e
classificar cada arquivo.

**Independent Test**: lote sintético com dois layouts, duplicata renomeada,
arquivo conflitante e XLSX inválido produz contagens e dados exatos.

### Tests

- [x] T020 [P] [US2] Criar em `tests/test_conciliacao_sefaz.py` testes dos dois
  layouts, números BR, célula numérica, CNPJ/competência, vazio versus zero,
  fórmula obrigatória sem cache, cabeçalho deslocado, múltiplas abas inclusive
  ocultas, tolerância exatamente R$ 0,01 e acima, fechamento, proveniência de
  fatos e componentes DIMP, linha DIMP de outro período/CNPJ, instituições
  repetidas preservadas, layout desconhecido e limites arquiteturais que
  impedem parser/store/exportador de importar Flask, FastAPI,
  `auditoria_fiscal.web` ou estado de requisição.
- [x] T021 [US2] Adicionar ao mesmo teste casos de XLSX falso, truncado, macro,
  external link, traversal, entries/tamanho/razão de compressão em
  `tests/test_conciliacao_sefaz.py`.
- [x] T022 [P] [US2] Criar `tests/test_conciliacao_store.py` com schema
  idempotente, centavos, SHA duplicado, candidato para mesma chave, duas
  importações concorrentes e reinício com lote interrompido.
- [x] T023 [P] [US2] Adicionar a `tests/test_web_conciliacao.py` upload múltiplo,
  teto 413, job, resumo por item, tentativa cruzada de sessão/job e auditoria
  geral de ok/negado/erro sem valores fiscais. Cobrir contagem durante
  streaming, interrupção/413 com remoção do parcial, nomes de staging únicos
  para arquivos homônimos e rejeição de dois processamentos simultâneos da
  mesma sessão.

### Implementation

- [x] T024 [US2] Criar `src/auditoria_fiscal/core/conciliacao_sefaz.py` com
  tipos puros, normalização, CNPJ, Decimal, fatos e erros estáveis.
- [x] T025 [US2] Implementar validação segura do pacote XLSX antes de
  `load_workbook` em `src/auditoria_fiscal/core/conciliacao_sefaz.py`.
- [x] T026 [US2] Implementar adaptadores semânticos Quadro 50-5 e Quadro
  50-3/DIMP e todas as validações de `contracts/xlsx-inputs.md`.
- [x] T027 [US2] Criar `src/auditoria_fiscal/ferramentas/conciliacao_store.py`
  com schema de `data-model.md`, migrações idempotentes, conexão por thread,
  WAL, busy timeout e triggers append-only; receber `db_path` e `origens_path`
  por injeção, receber identidade como snapshots primitivos e, na
  inicialização, marcar lotes abandonados em `processando` como `interrompido`
  para permitir nova tentativa idempotente.
- [x] T028 [US2] Implementar staging, SHA-256 e promoção atômica da fonte para
  `dados_web/conciliacao/origens/<sha>.xlsx`, sem deixar banco apontar para
  arquivo ausente.
- [x] T029 [US2] Implementar importação transacional/idempotente, lote e itens,
  primeira versão vigente, candidata/conflito e eventos fiscais em
  `src/auditoria_fiscal/ferramentas/conciliacao_store.py`.
- [x] T030 [US2] Implementar upload e processamento em job em
  `src/auditoria_fiscal/web/rotas_conciliacao.py`, incluindo streaming com teto,
  limpeza de parcial, `upload_id` opaco/staging sem colisão, limites de lote,
  manifesto congelado, trava por sessão e
  `GET /api/conciliacao/lotes/{id}` com o resultado persistente do OpenAPI;
  ator sempre vem de `Usuario`.
- [x] T031 [US2] Implementar seletor múltiplo, fila visual, processamento e
  resumo do lote em `webui/conciliacao.js`, usando `textContent`/`esc` para todo
  conteúdo externo. O polling chama `esperarJob(job_id, "conciliacao")`: desde
  T069 a ferramenta é argumento obrigatório e omiti-la falha no cliente.

**Checkpoint**: arquivos são importados e persistidos com segurança; duplicatas
e conflitos nunca sobrescrevem dados.

---

## Phase 5 — User Story 3: consulta e proveniência (P1)

**Goal**: mostrar valores, DIMP, fórmulas e origem verificável.

**Independent Test**: detalhe dos dois layouts corresponde às fixtures; no 50-5
PIX/não-PIX são nulos e no 50-3 movimentos originais permanecem visíveis.

### Tests

- [x] T032 [P] [US3] Adicionar ao `tests/test_conciliacao_store.py` consultas
  paginadas, agregação de instituições sem perda das linhas, nulos do 50-5 e
  fatos derivados.
- [x] T033 [P] [US3] Adicionar a `tests/test_web_conciliacao.py` contrato JSON de
  lista/detalhe completo, filtros e paginação, incluindo com/sem ST,
  diferenças, fonte/hash/versão do parser, proveniência de células e
  componentes DIMP, revisão completa, texto externo malicioso e download
  auditado da fonte.

### Implementation

- [x] T034 [US3] Implementar em
  `src/auditoria_fiscal/ferramentas/conciliacao_store.py` resumo e listagem com filtros
  allowlist/índices (`cnpj`, texto, período, estado, layout e exceção),
  paginação e detalhe completo da versão vigente, candidatas, fatos,
  movimentos, exceções e histórico; resumo e lista aplicam os mesmos filtros.
- [x] T035 [US3] Implementar `GET /resumo`, `/conciliacoes`,
  `/conciliacoes/{id}`, `/excecoes` e `/fontes/{id}/download` em
  `src/auditoria_fiscal/web/rotas_conciliacao.py` conforme OpenAPI, mantendo
  indicadores e lista coerentes.
- [x] T036 [US3] Implementar em `webui/conciliacao.js` indicadores, filtros,
  tabela paginada e detalhe com comparação declarada/calculada, ST, DIMP e
  proveniência.
- [x] T037 [P] [US3] Adicionar somente estilos necessários, prefixados `conc-`,
  em `webui/estilo.css`, verificando tema claro/escuro e tela estreita.

**Checkpoint**: todo valor financeiro exibido pode ser rastreado à fonte ou
fórmula.

---

## Phase 6 — User Story 4: revisão e exceções (P1)

**Goal**: permitir revisão, aprovação e resolução de exceções de forma
versionada e transacional.

**Independent Test**: aprovar caso limpo; bloquear aprovação com bloqueio ou
conflito; resolver exceção e detectar revision desatualizada.

### Tests

- [x] T038 [P] [US4] Adicionar a `tests/test_conciliacao_store.py` transições,
  justificativa, bloqueios, revision otimista, autoria, atomicidade e
  imutabilidade de revisões/eventos.
- [x] T039 [P] [US4] Adicionar a `tests/test_web_conciliacao.py` 403 por ação,
  ausência de campos `actor/reviewer`, tentativa de forjar autoria, 409 por
  revision e auditoria geral/fiscal.

### Implementation

- [x] T040 [US4] Implementar no store revisar, aprovar e resolver exceção em
  `src/auditoria_fiscal/ferramentas/conciliacao_store.py`, em transações que
  também inserem revisão/evento; nunca aceitar ator externo.
- [x] T041 [US4] Implementar endpoints `/revisar`, `/aprovar` e
  `/excecoes/{id}/resolver` em
  `src/auditoria_fiscal/web/rotas_conciliacao.py`, com permissões distintas e
  `detalhar()`.
- [x] T042 [US4] Implementar fila de exceções e modais de revisão/aprovação em
  `webui/conciliacao.js`, exigindo justificativa e confirmação.

**Checkpoint**: nenhuma decisão fiscal perde autoria; bloqueio ou conflito
aberto impede aprovação.

---

## Phase 7 — User Story 5: conflitos e versões (P1)

**Goal**: comparar e resolver versões concorrentes sem perder histórico.

**Independent Test**: manter vigente; promover candidata; preservar a anterior;
voltar a Em revisão; detectar revision desatualizada e vigente alterada.

### Tests

- [x] T043 [US5] Adicionar a `tests/test_conciliacao_store.py` comparação campo
  a campo, múltiplas candidatas, manter vigente, promover candidata, preservar
  anterior e voltar a Em revisão.

### Implementation

- [x] T044 [US5] Implementar em
  `src/auditoria_fiscal/ferramentas/conciliacao_store.py` comparação e resolução
  de conflito com estados e atomicidade definidos em `data-model.md`.
- [x] T045 [US5] Implementar em
  `src/auditoria_fiscal/web/rotas_conciliacao.py` `GET /conflitos`,
  `/conflitos/{id}/resolver` e resposta 409 com `current_revision` quando o
  cliente estiver desatualizado.
- [x] T046 [US5] Implementar comparação de versões e decisões manter/promover,
  em `webui/conciliacao.js`, exibindo somente ações autorizadas e recarregando
  após 409.

**Checkpoint**: nenhuma decisão fiscal perde autoria, histórico ou versão
anterior; conflito/bloqueio impede aprovação.

---

## Phase 8 — User Story 6: consolidado auditável (P1)

**Goal**: exportar dados e trilhas com filtros e proteção de conteúdo.

**Independent Test**: gerar workbook, reabri-lo e conferir todas as abas,
valores/nulos, metadados, filtros e formula injection.

### Tests

- [x] T047 [P] [US6] Criar `tests/test_relatorio_conciliacao.py` para o
  consolidado de `contracts/xlsx-outputs.md`, inclusive nulos 50-5, negativos,
  textos perigosos e falha sem arquivo parcial.
- [x] T048 [P] [US6] Adicionar a `tests/test_web_conciliacao.py` permissão,
  MIME/nome, filtros e eventos de exportação ok/negado/erro.

### Implementation

- [x] T049 [US6] Criar
  `src/auditoria_fiscal/ferramentas/relatorio_conciliacao.py` e implementar o
  consolidado sem dependência web.
- [x] T050 [US6] Implementar sanitização central de texto Excel e as abas
  Conciliações, Versões, Movimentos DIMP, Proveniência, Exceções, Conflitos,
  Revisões e Metadados em
  `src/auditoria_fiscal/ferramentas/relatorio_conciliacao.py`.
- [x] T051 [US6] Implementar `/api/conciliacao/exportar` em
  `src/auditoria_fiscal/web/rotas_conciliacao.py`, com filtros allowlist,
  permissão, auditoria e geração segura em memória ou temporário removível.
- [x] T052 [US6] Implementar a área de download do consolidado em
  `webui/conciliacao.js`.

**Checkpoint**: consolidado auditável reproduz dados e origem sem executar texto
como fórmula.

---

## Phase 9 — User Story 7: planilha-mestre (P1)

**Goal**: automatizar o preenchimento da cópia do modelo para uma empresa.

**Independent Test**: preencher o modelo sintético e o de referência local,
preservando células fora do mapa e incluindo somente elegíveis.

### Tests

- [x] T053 [P] [US7] Adicionar a `tests/test_relatorio_conciliacao.py` estrutura
  válida/inválida, CNPJ, meses ausentes/duplicados, células/fórmulas mapeadas,
  neutralização de fórmula nos textos L/M, preservação de valores, fórmulas,
  estilos, larguras, mesclagens e conjunto de abas e recálculo anual.
- [x] T054 [US7] Cobrir no exportador puro a seleção já autorizada de versão
  vigente/aprovada, rejeitada, bloqueada, conflito e `em_revisao`, incluindo a
  marcação visível em `tests/test_relatorio_conciliacao.py`; RBAC pertence ao
  teste web T055, não ao módulo puro.
- [x] T055 [P] [US7] Adicionar a `tests/test_web_conciliacao.py` upload do
  modelo, permissão simples e adicional, confirmação, 422/409, nome de download
  distinto, hash do modelo, competências/resultado na auditoria, sinalização
  visível de pendentes e ausência de saída parcial.

### Implementation

- [x] T056 [US7] Implementar validação/mapeamento do modelo e preenchimento em
  `src/auditoria_fiscal/ferramentas/relatorio_conciliacao.py` conforme contrato.
- [x] T057 [US7] Implementar seleção estrita por CNPJ, versão vigente e estado;
  em `src/auditoria_fiscal/ferramentas/conciliacao_store.py`, nunca preenchendo
  múltiplas empresas na mesma operação.
- [x] T058 [US7] Implementar `/api/conciliacao/preencher-modelo` em
  `src/auditoria_fiscal/web/rotas_conciliacao.py`, com validação XLSX,
  permissões cumulativas, nome de saída distinto, hash do modelo,
  competências/resultado na auditoria e limpeza segura.
- [x] T059 [US7] Implementar formulário de modelo em `webui/conciliacao.js` com
  CNPJ obrigatório e alerta/confirmacão de pendentes.

**Checkpoint**: processo demonstrado no vídeo é automatizado numa cópia segura
e rastreável.

---

## Phase 10 — User Story 8: painel e filtros (P2)

**Goal**: gestão de volume por indicadores, busca, filtros e paginação.

- [x] T060 [P] [US8] Adicionar casos de indicadores filtrados, busca, intervalo,
  layout, exceções, ordenação e paginação em `tests/test_web_conciliacao.py`.
- [x] T061 [US8] Completar painel e filtros em `webui/conciliacao.js`, mantendo
  indicadores e lista consistentes.

**Checkpoint**: usuários localizam e priorizam competências sem percorrer todo
o histórico.

---

## Phase 11 — Polish, documentação e aceite

**Goal**: documentação, desempenho, validação privada e regressão final.

- [x] T062 [P] Atualizar `README.md` com a sexta ferramenta, limites, semântica
  não-PIX e comandos dos novos testes.
- [x] T063 [P] Atualizar `README-servidor.md` com permissões, `conciliacao.db`,
  origens, variável de upload, um worker e backup consistente em WAL.
- [x] T064 Criar benchmark reproduzível para SC-010 a SC-012, registrar hardware
  e medições em `specs/003-conciliacao-fiscal/implementation-log.md`; otimizar
  consultas/índices se necessário. O aceite das metas só ocorre no servidor de
  referência de 4 núcleos, 8 GB e disco local.
- [ ] T065 Validar localmente, quando
  `AUDITORIA_CONCILIACAO_AMOSTRAS` estiver configurada, os 12 relatórios e a
  planilha-mestre do inventário (13 arquivos), sem copiá-los ao repo, e
  comparar classificação, duplicidades e valores com a cópia do modelo,
  registrando somente o resultado sanitizado em
  `specs/003-conciliacao-fiscal/implementation-log.md`.
- [x] T066 Fazer smoke test no navegador: dois perfis, temas, tela estreita,
  lote, detalhe, decisão, conflito e downloads; registrar em
  `specs/003-conciliacao-fiscal/implementation-log.md`. Cobre **SC-013**:
  durante um lote em processamento, navegar entre subtelas, abrir um detalhe e
  aplicar um filtro sem esperar o job terminar; registrar explicitamente o
  resultado de SC-013, que é o único critério de sucesso sem tarefa própria.
- [x] T067 Rodar toda a suíte anterior e a nova; corrigir regressões sem
  enfraquecer testes e registrar o resultado em
  `specs/003-conciliacao-fiscal/implementation-log.md`.
- [x] T068 Revisar o diff para confirmar ausência de Flask, iframe, segunda
  porta, `mktemp`, credenciais, banco, uploads e planilhas reais; registrar o
  resultado em `specs/003-conciliacao-fiscal/implementation-log.md`.

---

## Tarefas acrescentadas por `/speckit-analyze` (17/08/2026)

Numeradas a partir de T069 para não renumerar referências existentes. Cada uma
fecha uma lacuna encontrada na análise de consistência; nenhuma reduz requisito
de segurança ou integridade.

### Fechamento de FR-005 para jobs (achado C1)

**Contexto**: `POST /processar` devolve `job_id`, mas o polling acontece na rota
genérica `GET /api/jobs/{job_id}`, compartilhada pelas seis ferramentas. Depois
de T007 o **dono** do job é validado; a **ferramenta esperada**, que FR-005 e
SEC003 também exigem, ainda não, porque exigi-la de imediato quebraria as cinco
interfaces existentes (FR-049). Esta tarefa faz a migração.

- [x] T069 Amarrar o job à ferramenta em
  `src/auditoria_fiscal/web/servidor.py`, `webui/app.js` e nos seis clientes de
  aba. Antes do código, estender `tests/test_web_permissoes.py` com: job
  consultado com a ferramenta correta responde 200; com ferramenta divergente
  responde 404 idêntico ao de job inexistente; e sem o parâmetro responde 200
  enquanto a migração não terminar. Em seguida aceitar `ferramenta` opcional em
  `GET /api/jobs/{job_id}`, repassando-a a `obter_job()`; fazer os seis
  `webui/*.js` sempre enviarem a própria aba no polling; só então tornar o
  parâmetro obrigatório, atualizar
  `contracts/openapi.yaml` (remover a nota de migração de `FerramentaQuery`,
  marcar `required: true`) e marcar SEC003 no gate de aceite. Executar todos os
  `tests/test_web_*.py`: nenhuma das cinco ferramentas pode regredir.

### Cobertura de SC-013 (achado C2)

**Contexto**: SC-013 ("a interface permanece utilizável durante jobs") era o
único critério de sucesso sem tarefa. T066 passou a cobri-lo no smoke manual;
esta tarefa acrescenta a verificação automatizável do lado servidor, que é a
causa raiz de uma interface travada.

- [x] T070 [P] Adicionar a `tests/test_web_conciliacao.py` o caso de
  concorrência de SC-013: com um lote em processamento na sessão, as leituras
  `GET /resumo`, `/conciliacoes` e `/excecoes` do mesmo usuário respondem 200
  dentro do orçamento de tempo, e o polling do job continua respondendo — ou
  seja, o job não segura a trava da sessão nem a conexão do banco durante todo
  o processamento. Registrar o resultado de SC-013 em
  `specs/003-conciliacao-fiscal/implementation-log.md`.

**Dependências**: T069 depende de T007 (concluída) e deve terminar antes do
gate de aceite; T070 depende de T030 e T034.

## Dependencies & Execution Order

```text
Phase 1
   |
Phase 2 ownership/infra
   |
Phase 3 acesso
   |
Phase 4 importação/parser/store
   |
Phase 5 consulta/proveniência
   |
Phase 6 revisão/exceções
   |
Phase 7 conflitos/versões
   |
Phase 8 consolidado/helpers
   |
Phase 9 planilha-mestre
   |
Phase 10 painel/filtros
   |
Phase 11 polish/aceite
```

### Parallel opportunities

- Fixtures e teste de arquitetura podem andar em paralelo.
- Testes de parser, store e web podem ser escritos em paralelo depois dos
  contratos estabilizados.
- A Fase 9 depende dos helpers e da sanitização de T049–T050. Depois disso,
  testes específicos do modelo e ajustes de UI podem avançar em paralelo quando
  não editarem os mesmos arquivos.
- CSS/documentação podem andar em paralelo com backend quando os contratos
  estiverem estáveis.

## Implementation Strategy

### MVP operacional

Fases 1–5 entregam acesso, importação, dados exatos e consulta rastreável. Não
chamar de produção enquanto revisão/conflitos e exportações não existirem.

### Entrega incremental segura

Após cada checkpoint:

1. executar testes específicos;
2. executar testes web afetados;
3. revisar autorizações e migração;
4. registrar resultado;
5. só então iniciar a fase seguinte.

## Notes

- Não marcar tarefa concluída somente porque o código existe; o teste e o
  critério correspondente devem passar.
- Não alterar os artefatos para acomodar uma implementação incompleta sem
  aprovação do proprietário.
- Se o repositório atual divergir do commit-base, documentar a adaptação e
  preservar a intenção dos requisitos.
