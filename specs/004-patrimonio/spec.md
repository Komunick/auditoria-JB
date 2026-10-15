# Feature Specification: Patrimônio — Bens e Responsabilidade

**Feature Branch**: `004-patrimonio`

**Created**: 2026-08-18

**Status**: Pronta para implementação

**Input**: Unificar os sistemas da JB Fraga Contabilidade num portal único.
O `auditoria-JB` já é esse portal — tem login, RBAC por aba e ação, trilha de
auditoria e frontend estático. Falta o controle patrimonial, hoje inexistente
para a JB Fraga.

## Objetivo e escopo

Incorporar o controle de **bens patrimoniais** como sétima ferramenta nativa
do Auditoria-JB: cadastrar o que a empresa possui, saber **quem está com
cada coisa**, registrar movimentações de forma rastreável, conferir inventário
periodicamente e emitir o **termo de responsabilidade** que o colaborador
assina ao receber um equipamento.

A experiência usa o mesmo endereço, login, permissões, histórico e padrão
visual das seis ferramentas existentes. Não haverá aplicação, servidor ou
autenticação paralela.

### Por que não reusar o sistema da Brazil Transports

O `controle-patrimonial` da Brazil Transports resolve um problema **de
transportadora**: EPI (25 itens de segurança), turnos de motorista, inspeção
de veículo e assinatura de termo de entrega de EPI em campo. Uma contabilidade
não entrega botina de segurança nem opera turno noturno.

Além disso, aquele sistema já tem destino definido — ser absorvido pelo
`brazil-tms` (§6.3 e fase F5 do `PLANO-UNIFICACAO.md` da Brazil) — e move
dados de outra empresa: CPF de motorista, entregas de EPI e assinaturas. Trazê-
lo para o portal da JB Fraga misturaria duas empresas sob um login só.

O que se aproveita dele é **conhecimento de domínio**, não código: a etiqueta
com prefixo preservada, o vínculo periférico→bem pai em dois níveis, a
conferência de inventário como sessão com histórico e a trilha append-only.

### Incluído

- Cadastro de bens, com periféricos vinculados a um bem pai.
- Cadastro de colaboradores e locais.
- Termo de responsabilidade: quem está com cada bem, desde quando.
- Movimentações rastreáveis: aquisição, atribuição, devolução, manutenção,
  empréstimo (home office) e baixa.
- Inventário por sessão, com histórico de conferências.
- Etiqueta com QR para leitura pelo celular.
- Exportação em Excel e termo de responsabilidade em PDF.
- Controle de acesso e auditoria integrados ao Auditoria-JB.

### Fora do escopo inicial

- EPI, ficha de segurança e assinatura em campo (não se aplica a contabilidade).
- Turnos e escala.
- Inspeção de veículo.
- Depreciação contábil e integração com o SPED Contábil.
- Importação do banco da Brazil Transports (empresa diferente).
- Compras, cotação e contas a pagar.

## User Scenarios & Testing

Testes automatizados são obrigatórios para todas as histórias P1 e para os
casos de autorização, concorrência e exportação.

### User Story 1 — Acessar a sétima ferramenta com segurança (P1)

Como usuário autorizado, quero acessar o Patrimônio dentro do Auditoria-JB
sem outro login ou endereço.

**Independent Test**: usuário com `aba.patrimonio` abre a aba; usuário sem ela
não vê o botão e recebe 403 em chamada direta, com a tentativa auditada.

**Acceptance Scenarios**:

1. Usuário com acesso vê a sétima ferramenta e consegue abri-la.
2. Usuário sem acesso não vê a aba nem obtém dados por chamada direta.
3. Permissão retirada durante a sessão vale na operação seguinte.

### User Story 2 — Cadastrar bens com etiqueta estável (P1)

Como responsável pelo patrimônio, quero cadastrar cada bem e receber uma
etiqueta que será colada nele.

**Independent Test**: cadastrar bem e periférico, conferir que a etiqueta é
sequencial, única e nunca muda.

**Acceptance Scenarios**:

1. Cada bem recebe etiqueta `JBF-000001` sequencial, **imutável** depois de
   criada — ela vai colada no equipamento.
2. Periférico recebe prefixo `PER-` e aponta para um bem pai.
3. A hierarquia tem no máximo **dois níveis**: periférico de periférico é
   recusado.
4. Número de série, quando informado, é único.
5. Bem nasce com situação **Disponível** e conservação informada.
6. Excluir bem não existe: o que existe é **baixa**, e ela preserva o
   histórico.

### User Story 3 — Saber quem está com cada bem (P1)

Como gestor, quero ver o responsável atual de cada bem e desde quando.

**Independent Test**: atribuir, devolver e reatribuir um bem, conferindo que o
histórico registra as três operações e que só há um responsável por vez.

**Acceptance Scenarios**:

1. Um bem tem **no máximo um responsável ativo** por vez.
2. Atribuir a alguém quando já há responsável exige devolver antes.
3. Devolver encerra a responsabilidade com data de fim; o registro não é
   apagado.
4. O histórico mostra todas as responsabilidades passadas com início e fim.
5. Atribuir bem baixado é recusado.
6. A identidade de quem registrou vem da sessão autenticada, nunca do corpo.

### User Story 4 — Registrar movimentações rastreáveis (P1)

Como responsável pelo patrimônio, quero que toda mudança de situação fique
registrada com autor, data e motivo.

**Independent Test**: mover um bem por manutenção, empréstimo e baixa, e
conferir que cada passo virou uma linha imutável na trilha.

**Acceptance Scenarios**:

1. Movimentação é **append-only**: nunca é editada nem apagada.
2. Toda movimentação grava tipo, bem, autor, data/hora e observação.
3. Situação e movimentação são gravadas **na mesma transação**.
4. Baixa exige justificativa e é **terminal**: bem baixado não recebe nova
   movimentação além de consulta.
5. Transição inválida responde erro claro, não estado inconsistente.

### User Story 5 — Conferir inventário (P1)

Como gestor, quero abrir uma conferência de inventário e saber o que foi
localizado.

**Independent Test**: abrir sessão, conferir parte dos bens, fechar e conferir
que o resultado ficou no histórico e que uma nova sessão começa do zero.

**Acceptance Scenarios**:

1. Uma sessão de inventário aberta por vez.
2. Cada bem é marcado como localizado, não localizado ou divergente.
3. Fechar a sessão congela o resultado; sessões anteriores continuam
   consultáveis.
4. Bem cadastrado depois da abertura não entra naquela sessão.

### User Story 6 — Emitir termo e exportar (P1)

Como responsável, quero o termo de responsabilidade em PDF e a relação de
bens em Excel.

**Independent Test**: gerar termo de um bem atribuído e exportar a relação
filtrada, reabrindo os dois arquivos.

**Acceptance Scenarios**:

1. O termo traz bem, etiqueta, responsável, data e o texto de compromisso.
2. A exportação respeita os filtros da tela.
3. Texto começando por `=`, `+`, `-` ou `@` é neutralizado no Excel.
4. Falha de geração não apresenta arquivo parcial como válido.
5. Usuário sem permissão não gera nem baixa.

## Edge Cases

- Dois usuários atribuem o mesmo bem simultaneamente.
- Bem com número de série repetido.
- Periférico cujo pai foi baixado.
- Colaborador desligado com bem ainda sob responsabilidade.
- Inventário aberto quando já existe um aberto.
- Etiqueta lida pelo QR que não existe mais.
- Texto de descrição começando com caractere de fórmula.
- Bem baixado recebendo tentativa de atribuição.

## Requirements

### Integração e autorização

- **FR-001**: A funcionalidade MUST aparecer como sétima ferramenta nativa.
- **FR-002**: MUST reutilizar autenticação, sessão, permissões e trilha de uso.
- **FR-003**: MUST possuir permissões distintas para acessar, cadastrar,
  movimentar, baixar, inventariar e exportar.
- **FR-004**: Autorização MUST ser validada no servidor em cada operação.
- **FR-005**: Identidade de quem registra MUST vir da sessão autenticada.

### Cadastro

- **FR-006**: Etiqueta MUST ser sequencial, única e imutável após a criação.
- **FR-007**: Periférico MUST apontar para um bem pai, com no máximo dois
  níveis.
- **FR-008**: Número de série, quando informado, MUST ser único.
- **FR-009**: Exclusão de bem MUST não existir; baixa preserva o histórico.
- **FR-010**: Valor de aquisição MUST usar precisão de centavos.

### Responsabilidade e movimentação

- **FR-011**: Um bem MUST ter no máximo um responsável ativo.
- **FR-012**: Devolução MUST encerrar a responsabilidade sem apagá-la.
- **FR-013**: Movimentações MUST ser append-only.
- **FR-014**: Situação e movimentação MUST ser gravadas na mesma transação.
- **FR-015**: Baixa MUST exigir justificativa e ser terminal.
- **FR-016**: Operações concorrentes sobre o mesmo bem MUST ser detectadas e
  não podem perder atualização silenciosamente.

### Inventário

- **FR-017**: MUST existir no máximo uma sessão de inventário aberta.
- **FR-018**: Sessão fechada MUST ser imutável e continuar consultável.

### Saídas

- **FR-019**: Termo de responsabilidade MUST identificar bem, etiqueta,
  responsável e data.
- **FR-020**: Texto exportado para Excel MUST ser protegido contra injeção de
  fórmula.
- **FR-021**: Falha de geração MUST não produzir arquivo parcial válido.
- **FR-022**: Exportação e emissão de termo MUST ser auditadas.

### Compatibilidade

- **FR-023**: A ferramenta MUST não alterar o comportamento das seis
  existentes.
- **FR-024**: Dados persistentes MUST integrar o backup de `dados_web`.

## Success Criteria

- **SC-001**: 100% das mudanças de situação têm autor, data e motivo.
- **SC-002**: Nenhum bem tem dois responsáveis ativos ao mesmo tempo.
- **SC-003**: Etiqueta nunca muda depois de criada.
- **SC-004**: Nenhum acesso não autorizado dos testes passa.
- **SC-005**: Listagens respondem em até 2 s no p95 com 5 mil bens.
- **SC-006**: Toda a suíte existente continua passando.
- **SC-007**: A ferramenta funciona no mesmo processo, endereço e login.

## Assumptions

- A JB Fraga não distribui EPI nem opera frota.
- O parque é de dezenas a poucos milhares de itens, não centenas de milhares.
- Etiquetas são impressas e coladas fisicamente, por isso a estabilidade da
  numeração é requisito e não conveniência.
- O termo de responsabilidade é assinado em papel ou digitalmente fora do
  sistema nesta versão.
