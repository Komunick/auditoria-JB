# Feature Specification: Controle de acesso por usuário e histórico de acessos

**Feature Branch**: `main` (fase commitada sobre a versão web — 002)

**Created**: 2026-07-17

**Status**: Implementada

**Input**: User description: "crie um site completo para o sistema de auditoria
fiscal, todas as funções devem ir para o site funcionando de forma idêntica ao
app, o site deve possuir login e senha com controle feito pelo usuário adm e o
usuário Carol, onde será possível definir quais abas, opções e configurações
cada usuário poderá acessar e sistema de histórico para saber quando um usuário
acessou, o que acessou, o que fez ao acessar e quando saiu."

> **Contexto**: o sistema já era um site interno (spec 001-auditoria-web): as
> cinco ferramentas do desktop viraram páginas, com login simples por usuário.
> Esta feature acrescenta o que faltava — **permissões por usuário** e **trilha
> de acessos** — administradas pelo `adm` e pela **Carol**.
>
> **Decisões do dono (2026-07-17)**: (1) `adm` e Carol são administradores
> **plenos e iguais**; (2) o recorte de acesso é por **aba E por ação
> sensível** (não só por ferramenta); (3) o histórico cobre **tudo** — uploads
> e processamentos, mutações fiscais, downloads gerados e ações administrativas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administração de usuários e permissões (Priority: P1)

O administrador (adm ou Carol) abre a aba **Administração**, cria os usuários da
equipe e define, caixa por caixa, o que cada um alcança: quais das cinco
ferramentas aparecem e quais ações de peso ele pode executar dentro delas.
Também troca senhas, desativa quem saiu e reativa quem voltou. Um usuário novo
já vem com uma sugestão marcada (vê todas as ferramentas e trabalha nelas, mas
as ações que mudam número fiscal ou geram a saída oficial ficam de fora até o
administrador liberar).

**Why this priority**: Sem isto não há "controle feito pelo adm e pela Carol" —
é o coração do pedido. Entrega valor sozinho: mesmo sem histórico, a equipe já
passa a ter acessos individuais e recortados.

**Independent Test**: Criar um usuário comum com um subconjunto de permissões,
entrar com ele e confirmar que só as abas/ações liberadas aparecem e funcionam,
enquanto as demais são recusadas.

**Acceptance Scenarios**:

1. **Given** um administrador logado, **When** ele cria um usuário com acesso
   apenas ao Livro de Conferência e à ação de conferir, **Then** esse usuário,
   ao entrar, vê somente essa aba e não vê os botões de gerar SPED corrigido,
   Livro Fiscal, Inconsistências nem de corrigir campo fiscal.
2. **Given** um usuário comum sem a aba de Produtos, **When** ele tenta acessar
   a ferramenta de Produtos (pela navegação ou direto pela API), **Then** o
   acesso é recusado com mensagem orientando falar com o administrador.
3. **Given** um usuário com permissão de corrigir uma nota mas **sem** a de
   corrigir em lote, **When** ele tenta uma correção em lote, **Then** o sistema
   recusa (a permissão de nota única não autoriza mexer na base inteira).
4. **Given** um administrador altera as permissões de alguém, **When** a pessoa
   faz a próxima ação, **Then** a mudança já vale, sem novo login.
5. **Given** apenas um administrador ativo, **When** alguém tenta rebaixá-lo,
   desativá-lo ou ele tenta remover o próprio acesso, **Then** o sistema recusa
   (o sistema nunca pode ficar sem administrador).

---

### User Story 2 - Histórico de acessos (Priority: P1)

O administrador abre a aba **Administração → Histórico** e responde, para
qualquer pessoa e período: **quando acessou, o que acessou, o que fez ao acessar
e quando saiu**. Cada linha traz usuário, data/hora, IP e o resultado (deu
certo, foi negado ou deu erro). Ele filtra por usuário, categoria, ação,
período e texto, e exporta o resultado em CSV.

**Why this priority**: É a segunda metade explícita do pedido do dono ("sistema
de histórico para saber quando ... o que ... o que fez ... e quando saiu"). É
independente da US1: mesmo com permissões simples, a trilha já entrega valor de
auditoria.

**Independent Test**: Fazer um usuário entrar, abrir uma aba, executar uma ação
e sair; depois, como administrador, encontrar essas quatro linhas no histórico
com quem, quando e o quê.

**Acceptance Scenarios**:

1. **Given** um usuário que entrou, abriu uma aba, marcou uma conferência e
   saiu, **When** o administrador consulta o histórico daquele usuário, **Then**
   as quatro linhas aparecem (entrada, aba acessada, conferência feita, saída),
   cada uma com data/hora, IP e resultado.
2. **Given** uma tentativa de ação sem permissão, **When** ela é recusada,
   **Then** o histórico registra a tentativa como "negado" (a trilha vê também o
   que foi barrado).
3. **Given** um filtro por usuário e período, **When** o administrador exporta,
   **Then** o CSV traz **todas** as linhas do filtro (sem corte silencioso) e
   abre corretamente no Excel.
4. **Given** uma sessão que venceu por tempo, **When** o histórico a registra,
   **Then** a saída é carimbada com o momento real do vencimento.

---

### User Story 3 - Paridade das ferramentas com o app (Priority: P2)

As cinco ferramentas continuam funcionando de forma idêntica ao app desktop,
agora com o recorte de acesso aplicado por cima: quem tem a aba trabalha nela
normalmente; quem não tem a ação sensível não vê o controle correspondente.

**Why this priority**: O dono exigiu "funcionando de forma idêntica ao app". A
paridade já existia (spec 001); esta feature não pode regredi-la ao esconder
controles.

**Independent Test**: Entrar como administrador (todas as permissões) e
confirmar que as cinco abas e todos os controles aparecem e operam como antes.

**Acceptance Scenarios**:

1. **Given** um administrador, **When** ele abre cada uma das cinco
   ferramentas, **Then** todos os controles e resultados aparecem como no app,
   sem nenhum a menos.
2. **Given** um dado vindo de XML/planilha/observação com conteúdo perigoso,
   **When** ele é exibido numa tabela, **Then** aparece como texto literal e não
   executa nada na sessão de quem abre.

---

### Edge Cases

- **Usuário sem nenhum acesso liberado**: vê um aviso claro para pedir liberação
  ao administrador, em vez de uma tela vazia.
- **Último administrador**: não pode ser rebaixado, desativado, nem remover o
  próprio acesso; duas tentativas simultâneas de rebaixamento não podem zerar os
  administradores.
- **Desativar ou trocar a senha de alguém**: encerra as sessões abertas daquela
  pessoa na hora.
- **Sessão aberta quando o acesso é retirado**: a próxima ação é recusada; a
  mudança de permissão vale imediatamente.
- **Falha inesperada no meio de uma ação auditada**: a tentativa ainda deixa
  linha no histórico (não some da trilha).
- **Banco já existente**: as estruturas novas (permissões e histórico) entram
  sem perder os dados anteriores.
- **Atualização do sistema**: o navegador não pode servir metade da interface
  antiga após uma atualização.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST autenticar por usuário e senha; o primeiro acesso
  cria o administrador; a sessão identifica quem fez cada ação.
- **FR-002**: O sistema MUST tratar `adm` e `Carol` como administradores plenos
  e iguais — ambos criam usuários, definem permissões de qualquer um e veem o
  histórico completo.
- **FR-003**: O administrador MUST poder criar, editar, ativar/desativar
  usuários e trocar senhas.
- **FR-004**: O administrador MUST poder conceder/retirar, por usuário, o acesso
  a cada uma das cinco abas (Comparador SPED×SEFAZ, Comparar versões de SPED,
  Livro de Conferência, Extração de Itens, Auditoria de Produtos).
- **FR-005**: O administrador MUST poder conceder/retirar, por usuário, cada
  ação sensível dentro das abas: marcar conferência, corrigir campo fiscal,
  corrigir **em lote**, editar a composição fiscal, gerar Livro Fiscal, gerar
  Relatório de Inconsistências, gerar SPED corrigido, exportar as planilhas dos
  comparadores/extração, corrigir a tributação de produtos e gerar a nova base.
- **FR-006**: O sistema MUST tratar o administrador como detentor de todas as
  permissões implicitamente; para os demais, ausência de concessão significa
  acesso negado.
- **FR-007**: O sistema MUST recusar no servidor qualquer ação para a qual o
  usuário não tenha permissão (esconder o controle na tela é conforto, não a
  barreira); a correção em lote exige permissão própria, além da de corrigir.
- **FR-008**: As mudanças de permissão MUST valer imediatamente, sem novo login.
- **FR-009**: O sistema MUST impedir que fique sem administrador: o último
  administrador ativo não pode ser rebaixado nem desativado, ninguém remove o
  próprio acesso de administrador, e rebaixamentos concorrentes não podem zerar
  os administradores.
- **FR-010**: O sistema MUST registrar no histórico, com usuário, data/hora, IP
  e resultado (ok/negado/erro): entrada e saída (inclusive sessão expirada por
  tempo e tentativa de login sem sucesso), navegação por aba, uploads e
  processamentos, mutações fiscais (com o valor antes/depois quando aplicável),
  downloads gerados e ações administrativas.
- **FR-011**: O histórico MUST registrar também as tentativas **negadas** e as
  que resultaram em **erro**, não só as bem-sucedidas.
- **FR-012**: A saída por vencimento de sessão MUST ser registrada com o momento
  real do vencimento (não o da detecção), e não pode ficar indefinidamente em
  aberto para quem não retorna.
- **FR-013**: O administrador MUST poder filtrar o histórico por usuário,
  categoria, ação, período e texto, e exportá-lo em CSV com **todas** as linhas
  do filtro.
- **FR-014**: O sistema MUST manter a paridade funcional das cinco ferramentas
  com o app desktop; o recorte de acesso não pode remover recurso de quem tem a
  permissão.
- **FR-015**: O sistema MUST exibir dados vindos de terceiros (XML, planilha do
  cliente) e digitados por usuários (observações) como texto inerte, sem
  permitir execução de conteúdo na sessão de quem visualiza.
- **FR-016**: A trilha de **uso** do sistema (esta feature) MUST ser separada da
  trilha **fiscal** existente (a correção em si, para o Fisco); uma não
  substitui a outra.
- **FR-017**: As estruturas de dados novas MUST entrar sobre um banco existente
  sem perda; a atualização do sistema não pode deixar o navegador com interface
  parcialmente antiga.

### Key Entities *(include if feature involves data)*

- **Usuário**: quem acessa. Login, nome de exibição, se é administrador, se está
  ativo, quando foi criado. Assina as ações que faz.
- **Permissão**: uma capacidade recortável (uma aba ou uma ação sensível),
  identificada por um rótulo legível e agrupada por área. Concedida a um usuário
  não-administrador; administradores as têm todas.
- **Evento de histórico**: um registro do que aconteceu — quem, quando (momento
  real), o que fez (ação e descrição), detalhe (ex.: "CFOP 1102 → 2102 em 37
  notas"), categoria, IP e resultado (ok/negado/erro).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O administrador cria um usuário e define seu acesso, aba por aba e
  ação por ação, inteiramente pela tela, sem editar arquivo nem banco.
- **SC-002**: Para os mesmos insumos, quem tem acesso completo produz na web os
  mesmos resultados/documentos que o app desktop (100% de paridade percebida).
- **SC-003**: 100% das ações sensíveis ficam registradas no histórico
  atribuídas ao usuário, incluindo as tentativas negadas.
- **SC-004**: O histórico responde às quatro perguntas do dono — quando acessou,
  o que acessou, o que fez, quando saiu — para qualquer usuário e período.
- **SC-005**: O sistema nunca fica sem administrador em nenhuma sequência de
  operações administrativas, inclusive concorrentes.
- **SC-006**: A exportação do histórico contém todas as linhas do filtro, sem
  corte silencioso.
- **SC-007**: Conteúdo perigoso vindo de arquivos ou observações é exibido como
  texto e não executa nada na sessão do administrador.

## Assumptions

- Rede interna confiável (mesmo pressuposto dos outros sistemas da casa); a
  exposição externa (ex.: via Tailscale/HTTPS) é feita por camada à frente.
- A base de usuários e a trilha de acessos vivem no servidor, com backup pela
  cópia da pasta de dados.
- Equipe pequena; o volume de usuários e de eventos é compatível com um único
  processo e armazenamento local.
- O app desktop continua existindo durante a transição; a fonte da verdade das
  conferências/correções é o banco compartilhado no servidor.
- Frontend sem framework/build (vanilla JS + fetch), espelhando o padrão dos
  demais sistemas da casa.
