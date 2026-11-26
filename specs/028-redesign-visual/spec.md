# Feature Specification: Redesign Visual e Arquitetura de Interface (JB Fraga)

**Feature Branch**: `028-redesign-visual`  
**Created**: 2026-11-26  
**Status**: Approved  
**Input**: User request: "redesign auditoria-jb" — alinhamento integral à identidade oficial JB Fraga Contabilidade, reorganização da navegação para 13+ ferramentas e revisão de layout, componentes e usabilidade em todas as telas sem build e sem CDN.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identidade oficial JB Fraga e tela de acesso (Priority: P1)

Ao abrir a plataforma sem sessão ativa (ou em primeiro acesso via bootstrap), o colaborador encontra uma cena de login alinhada à marca oficial da JB Fraga Contabilidade: fundo azul-marinho profundo (`#060D28`), acentos dourados metálicos (`#C9A227`), marca transparente em alta definição sem molduras improvisadas e cartão de autenticação claro (ou escuro conforme tema) com feedback imediato e acessível.

**Why this priority**: A tela de acesso e o sistema de cores/ativos de marca estruturam todas as demais telas do sistema e eliminam a desconexão visual com os demais produtos da JB Fraga (`jbfraga-site` e `jbfraga-acompanhamento`).

**Independent Test**: Subir o servidor web com pasta de dados isolada e abrir `/` sem autenticação nos temas claro e escuro, em desktop e mobile; verificar ausência de imagens quebradas, contraste WCAG AA e funcionamento completo de login e bootstrap.

**Acceptance Scenarios**:

1. **Given** a plataforma sem usuário autenticado, **When** o usuário abre `/`, **Then** vê a cena dividida com a marca JB Fraga em fundo `#060D28`, tipografia e destaques em dourado `#C9A227`, formulário de login acessível (incluindo alternância de visibilidade da senha e alternância de tema) e nenhum elemento com `logo.jpg` em caixa branca improvisada.
2. **Given** primeiro acesso ao sistema (`precisa_bootstrap = true`), **When** a tela carrega, **Then** o formulário `#form-bootstrap` é exibido corretamente, cria o administrador e recarrega para o painel autenticado.
3. **Given** queda de sessão (`401`) com modal aberto, **When** a resposta retorna `401`, **Then** modais são fechados e o formulário de login volta funcional sem exigir recarga manual.

---

### User Story 2 - Shell principal, navegação para 13+ módulos e busca rápida (Priority: P1)

Após autenticação, o colaborador navega com fluidez entre Central, Gestão, Ferramentas Fiscais e Administração através de uma barra lateral redesenhada com agrupamento claro, numeração discreta para as ferramentas numeradas, recolhimento de menu persistente no desktop, gaveta lateral deslizante em telas estreitas (`<= 920px`) e seletor rápido de ferramentas (`Ctrl+K`) no cabeçalho.

**Why this priority**: O sistema cresceu de 8 para 13+ ferramentas e a lista lateral antiga ficava congestionada, fora de sequência visual e se expandia de forma ruidosa em telas menores.

**Independent Test**: Autenticar como usuário administrador (todas as abas) e como usuário restrito (1 aba); verificar visibilidade por permissão, recolhimento da lateral, abertura via `Ctrl+K` e gaveta responsiva em 390px/768px/1440px.

**Acceptance Scenarios**:

1. **Given** um usuário autenticado com múltiplas ferramentas liberadas, **When** aciona o botão de atalho `Ir para...` ou `Ctrl+K`, **Then** abre o seletor rápido listando apenas as abas permitidas ao usuário, filtrando por nome, número ou palavra-chave e abrindo a aba escolhida via teclado ou clique.
2. **Given** tela estreita (`<= 920px`), **When** o usuário acessa a aplicação, **Then** a navegação lateral se recolhe em gaveta acessível por botão no cabeçalho, evitando empurrar o conteúdo principal para baixo por dezenas de botões empilhados.
3. **Given** usuário sem nenhuma ferramenta liberada, **When** entra no sistema, **Then** visualiza o estado `#sem-acesso` estilizado com clareza e sem atalhos quebrados.

---

### User Story 3 - Central operacional e consistência visual dos módulos (Priority: P2)

Na Central (`inicio.js`) e em todas as ferramentas (`tarefas`, `qualidade`, `clientes`, `comparador`, `diff`, `conferencia`, `extracao`, `produtos`, `conciliacao`, `nfse`, `patrimonio`, `admin`), cartões KPI, tabelas com cabeçalho fixo, filtros, zonas de upload, sub-abas, emblemas de status, modais e notificações compartilham uma hierarquia visual coesa nos temas claro e escuro, sem bordas duplas excessivas.

**Why this priority**: Garante que o redesign não fique restrito à casca: melhora leitura de números fiscais, diferencia superfícies primárias de blocos internos e unifica a aba `qualidade` (`qualidade.css`) ao mesmo sistema visual.

**Independent Test**: Navegar por todas as 13 abas no navegador em ambos os temas e executar os testes automatizados de UI (`test_*_ui.py`) e web (`test_web_*.py`).

**Acceptance Scenarios**:

1. **Given** usuário com permissão `aba.tarefas`, **When** abre a Central, **Then** visualiza o painel executivo sem duplicação de selo JPEG, indicadores de prioridade com semântica visual clara e estado ativo evidente, fila de tarefas e distribuição por responsável legíveis e grade de atalhos organizada.
2. **Given** usuário na aba Gestão da qualidade ou em qualquer ferramenta fiscal, **When** alterna entre tema claro e escuro, **Then** todas as superfícies, tabelas, formulários, sub-abas, badges semânticos e modais mantêm contraste legível (>= 4.5:1 para texto normal) e alinhamento responsivo.
3. **Given** todas as ferramentas com scripts de contrato em Node (`vm.runInContext`), **When** a suíte completa de testes roda, **Then** todos os IDs, contratos JS (`Abas`, `Sessao`, `Telas`, `CentralUI`, `TarefasUI`, `QualidadeUI`, `BaseFiscalUI`) e restrições de segurança permanecem íntegros.

### Edge Cases

- O navegador pode rodar em rede interna sem acesso à internet: nenhum recurso (`fonts`, `css`, `js`, `svg`, `png`) pode depender de CDN externo.
- Usuários com `prefers-reduced-motion: reduce` não devem receber animações nem transições de movimento.
- Tabelas fiscais largas (SPED, Produtos, Conferência, Qualidade) precisam manter rolagem horizontal e vertical confortável sem vazar da largura da viewport nem quebrar colunas monetárias (`tabular-nums`).
- Módulos testados com DOM sintético mínimo em Node (`test_central_ui.py`, `test_base_fiscal_ui.py`, `test_tarefas_*_ui.py`, `test_qualidade_ui.py`) não devem quebrar caso `window`, `matchMedia`, `localStorage` ou métodos DOM avançados não existam no contexto simulado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema visual MUST adotar os tokens oficiais da marca JB Fraga Contabilidade (`--navy-950: #04091A`, `--navy-900: #060D28`, `--navy-800: #0B1739`, `--navy-700: #12244F`, `--gold-500: #C9A227`, `--gold-600: #A9812A`, `--gold-grad`) para cromo, destaques de marca e hierarquia editorial, combinados a uma escala esmeralda refinada de ação e estados semânticos (`ok`, `alerta`, `erro`).
- **FR-002**: O sistema MUST substituir os usos de `logo.jpg` na interface por ativos de marca transparentes em alta resolução armazenados localmente em `webui/img/` (`favicon-64.png`, `icon-192.png`, `symbol-256.png`, `logo-horizontal-light.png`, `logo-horizontal.png`).
- **FR-003**: Todo carregamento de fontes, estilos, ícones SVG e imagens MUST permanecer 100% local e sem etapa de build, em conformidade com a Constituição do Auditoria-JB (zero CDN externo).
- **FR-004**: O cabeçalho e a barra lateral MUST organizar as 13 ferramentas em grupos claros, suportar recolhimento persistente em desktop (`>= 920px`), gaveta deslizante acessível em telas estreitas (`<= 920px`) e um seletor rápido de ferramentas (`Ctrl+K` / botão no cabeçalho) restrito às abas permitidas ao usuário.
- **FR-005**: A tela de login/bootstrap MUST permitir alternar a visibilidade da senha e o tema claro/escuro sem alterar os IDs `#form-login`, `#form-bootstrap`, `#login-*`, `#boot-*` nem os fluxos de segurança de `app.js`.
- **FR-006**: A Central (`inicio.js`) e os avisos do topo (`#aviso-topo`, `#aviso-tarefas`) MUST apresentar hierarquia visual limpa (sem selo em caixa branca repetida na capa), indicadores de prioridade distintos, carga por responsável legível e cartões de atalho organizados.
- **FR-007**: As folhas de estilo `webui/estilo.css` e `webui/qualidade.css` MUST unificar elevação de cartões, sub-abas, tabelas, inputs, dropzones de arquivo, badges semânticos, modais e toasts nos temas claro e escuro, atingindo contraste WCAG AA (`>= 4.5:1` em texto normal) nos pares principais.
- **FR-008**: Todas as ferramentas existentes (`comparador`, `diff`, `conferencia`, `extracao`, `produtos`, `conciliacao`, `patrimonio`, `nfse`, `clientes`, `tarefas`, `qualidade`, `admin`) MUST preservar integralmente seus IDs de elementos, contratos de API, verificações de permissão, neutralização de XSS (`textContent` / `esc`) e compatibilidade com todos os testes automatizados existentes.

### Key Entities

- **Design Tokens (`:root` / `[data-theme]`)**: Paleta institucional JB Fraga (Navy, Gold), superfície em 3 níveis (`--fundo`, `--papel`, `--papel-2`), ação esmeralda e semântica fiscal (`ok`, `alerta`, `erro`).
- **Shell de Navegação (`#tela-app`, `#abas-nav`, `.cabecalho`, `#paleta-comando`)**: Estrutura persistente que reflete `Sessao.usuario`, `Sessao.permissoes` e preferências locais (`tema`, `menuRecolhido`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos testes automatizados de UI (`tests/test_*_ui.py`), testes web (`tests/test_web_*.py`) e suíte de regressão relevante passam sem falhas nem regressões após a última edição.
- **SC-002**: Novos testes automatizados verificam contraste WCAG AA (`>= 4.5:1`) dos pares de tokens definidos em `estilo.css` para os temas claro e escuro, presença dos novos ativos locais em `webui/img/`, ausência de URLs externas/CDN em `webui/` e integridade dos elementos do shell, login, gaveta mobile e seletor rápido (`Ctrl+K`).
- **SC-003**: Inspeção visual em navegador real (Playwright / Chromium headless) confirma renderização correta nos temas claro e escuro, em desktop (`1440x900`) e mobile (`390x844`), para login, Central e módulos representativos (Tarefas, Qualidade, Clientes, Conferência, Conciliação, Administração) sem overflow horizontal indesejado nem texto cortado.
- **SC-004**: Zero dados reais de clientes ou colaboradores e zero dependências externas adicionadas no diff.

## Assumptions

- O servidor continua servindo `webui/` diretamente via `WebuiSemCache(StaticFiles)` sem alterações de backend ou novas rotas.
- O branch de trabalho é `028-redesign-visual` derivado de `origin/dev`, respeitando o fluxo de PR para `dev` sem merge/push automático.
- As 13 abas atuais de `origin/dev` permanecem no mesmo conjunto de permissões (`aba.*`, `admin.*`) já conhecidas pelo backend.
