# Feature Specification: Conciliação Fiscal — Receita e DIMP

**Feature Branch**: `003-conciliacao-fiscal`

**Created**: 2026-08-13

**Status**: Pronta para implementação

**Input**: Incorporar ao Auditoria-JB o sistema web que automatiza a leitura de
relatórios da Malha Fiscal da SEFAZ/BA, a conciliação dos valores declarados e
calculados, a revisão de exceções e as exportações de controle.

## Objetivo e escopo

Incorporar o processo como a sexta ferramenta nativa do Auditoria-JB,
denominada **Conciliação Fiscal — Receita e DIMP**. A ferramenta permite
importar relatórios mensais, reconciliar valores declarados e calculados,
separar movimentos DIMP por instituição, tratar exceções e versões
conflitantes, aprovar competências e gerar arquivos Excel auditáveis.

A experiência deve usar o mesmo endereço, login, permissões, histórico e padrão
visual das demais ferramentas. Não haverá aplicação, servidor ou autenticação
paralela.

### Incluído

- Relatórios `.xlsx` nos layouts Quadro 50-3/DIMP e Quadro 50-5.
- Importação individual ou em lote.
- Identificação de CNPJ e competência pelo conteúdo do relatório.
- Receitas declaradas e calculadas, totais e com/sem ST.
- Movimentos DIMP por instituição, incluindo PIX e não-PIX.
- Avisos, bloqueios, conflitos e revisão humana.
- Rastreabilidade até fonte e regra de extração.
- Exportação consolidada e preenchimento de cópia da planilha-mestre.
- Controle de acesso e auditoria integrados ao Auditoria-JB.

### Fora do escopo inicial

- Leitura de PDF, imagem, `.xls` ou `.xlsm`.
- Acesso automático ao portal ou envio de dados à SEFAZ/BA.
- Cálculo de DAS pago, DAS devido ou RBT12, pois as fontes fornecidas não
  contêm regras ou insumos suficientes.
- Cruzamento automático com SPED ou notas fiscais.
- Escolha automática entre arquivos diferentes para a mesma competência.
- Exclusão de fontes, versões ou histórico fiscal pela interface.
- Mudança funcional das cinco ferramentas atuais.

## User Scenarios & Testing

Testes automatizados são obrigatórios para todas as histórias P1 e para os
casos de autorização, concorrência, importação e exportação.

### User Story 1 — Acessar a sexta ferramenta com segurança (Priority: P1)

Como usuário autorizado, quero acessar a Conciliação Fiscal dentro do
Auditoria-JB para trabalhar sem outro login ou endereço.

**Why this priority**: É a base da integração; sem isolamento e autorização, as
demais operações podem expor dados fiscais entre usuários.

**Independent Test**: Criar dois usuários com permissões distintas, validar a
visibilidade da aba, o acesso direto às operações e o isolamento das sessões e
jobs.

**Acceptance Scenarios**:

1. **Given** um usuário com acesso, **When** ele entra no Auditoria-JB, **Then**
   vê a sexta ferramenta e consegue abri-la.
2. **Given** um usuário sem acesso, **When** ele entra, **Then** a aba não é
   exibida.
3. **Given** um usuário sem acesso, **When** tenta uma operação diretamente,
   **Then** recebe acesso negado e a tentativa é auditada.
4. **Given** que a permissão foi retirada durante a sessão, **When** ocorre a
   próxima operação, **Then** a autorização é reavaliada e negada.
5. **Given** uma sessão ou job de outro usuário, **When** alguém tenta consultá-
   lo, processá-lo, exportá-lo ou descartá-lo, **Then** o sistema não revela nem
   permite acesso ao recurso.

---

### User Story 2 — Importar relatórios com validação e deduplicação (Priority: P1)

Como analista fiscal, quero importar vários relatórios SEFAZ/BA de uma vez para
eliminar a digitação manual e receber um resultado por arquivo.

**Why this priority**: É o principal ganho operacional e produz o conjunto de
dados usado por todas as histórias seguintes.

**Independent Test**: Importar fixtures sintéticas dos dois layouts, repetir um
arquivo com outro nome, enviar um arquivo inválido e conferir o resumo do lote.

**Acceptance Scenarios**:

1. O usuário seleciona um ou vários `.xlsx` e acompanha o processamento sem
   bloquear a interface.
2. O layout é reconhecido pelos rótulos e conteúdo, não pelo nome do arquivo.
3. CNPJ e competência são extraídos do conteúdo.
4. Um SHA-256 já recebido é classificado como duplicado e não cria outra fonte
   nem conciliação.
5. Um arquivo diferente para CNPJ e competência já existentes cria versão
   candidata e conflito, sem substituir o vigente.
6. Um erro em um arquivo não cancela os demais itens do lote.
7. O resumo apresenta quantidades de processados, duplicados, conflitantes e
   rejeitados, com mensagem individual.
8. Fontes aceitas são preservadas de forma imutável e relacionadas ao usuário e
   ao instante da importação.

---

### User Story 3 — Obter conciliação automática e rastreável (Priority: P1)

Como analista fiscal, quero visualizar os valores extraídos e calculados para
entender a diferença entre o informado e o apurado.

**Why this priority**: A automação só é confiável quando o resultado financeiro
é exato e cada valor pode ser conferido na fonte.

**Independent Test**: Processar um arquivo válido de cada layout e comparar
campos, cálculos e proveniência com resultados conhecidos.

**Acceptance Scenarios**:

1. Para ambos os layouts, o sistema extrai CNPJ, razão social, competência,
   receita total declarada, declarada com ST, declarada sem ST, total calculada,
   calculada com ST e calculada sem ST.
2. Calcula `total calculado − total declarado`, `calculado com ST − declarado
   com ST` e `calculado sem ST − declarado sem ST`.
3. No Quadro 50-3, extrai por linha e instituição: débito, crédito,
   transferência, PIX, voucher, outras operações e total DIMP.
4. Calcula não-PIX como `total DIMP − PIX`; esse campo não deve ser rotulado
   simplesmente como cartão, pois também pode conter voucher, transferência e
   outras operações.
5. No Quadro 50-5, PIX e não-PIX permanecem **não informados**, nunca zero.
6. Valores monetários permanecem exatos ao centavo.
7. Cada fato extraído exibe fonte, hash, aba, célula, rótulo e regra. Valores
   derivados exibem fórmula e fatos de origem.
8. Linhas DIMP de outra competência não são incorporadas à competência atual.
9. Linhas repetidas de uma instituição podem ser agregadas na exibição sem
   eliminar as linhas e proveniências originais.

---

### User Story 4 — Revisar exceções e aprovar competências (Priority: P1)

Como revisor fiscal, quero examinar avisos e bloqueios para decidir se uma
competência pode ser aprovada.

**Why this priority**: A automação é apoio à decisão fiscal; a aprovação humana
e sua autoria precisam permanecer explícitas.

**Independent Test**: Criar conciliações sem problema, com aviso e com bloqueio,
e testar permissões e transições de estado.

**Acceptance Scenarios**:

1. Toda conciliação nova inicia como **Em revisão**.
2. Os estados de decisão são **Em revisão**, **Aprovada** e **Rejeitada**.
3. O detalhe apresenta valores, DIMP, proveniência, fontes, exceções e histórico
   de decisões.
4. Aviso não impede aprovação; bloqueio aberto ou conflito aberto impede.
5. Resolver bloqueio exige permissão e justificativa.
6. Aprovar exige permissão própria; rejeitar ou devolver à revisão exige
   permissão de revisão.
7. Usuário, data e hora vêm da sessão autenticada e não são editáveis.
8. Cada decisão é append-only e contém estado anterior, novo estado, versão,
   usuário e justificativa.
9. Alterações concorrentes não sobrescrevem silenciosamente a decisão de outro
   revisor; o segundo usuário é instruído a recarregar o estado atual.

---

### User Story 5 — Resolver versões conflitantes sem perder histórico (Priority: P1)

Como revisor autorizado, quero comparar arquivos diferentes da mesma
competência e decidir qual versão deve ficar vigente.

**Why this priority**: Relatórios retificados são esperados e não podem apagar
a evidência ou a aprovação anterior.

**Independent Test**: Importar dois arquivos de hashes diferentes para a mesma
chave CNPJ + competência e exercer as duas decisões possíveis.

**Acceptance Scenarios**:

1. O sistema preserva a versão vigente e a candidata.
2. A interface compara campo a campo e destaca diferenças.
3. O revisor escolhe **manter vigente** ou **promover candidata**, sempre com
   justificativa.
4. Ao promover, a versão anterior fica como substituída, nunca apagada.
5. A versão promovida volta a **Em revisão**, mesmo se a anterior estava
   aprovada.
6. Nenhuma versão é aprovada enquanto o conflito está aberto.
7. Importações concorrentes da mesma fonte produzem somente uma fonte e um
   resultado idempotente.

---

### User Story 6 — Exportar resultados auditáveis (Priority: P1)

Como analista autorizado, quero gerar uma planilha consolidada para analisar e
compartilhar os resultados com a respectiva trilha.

**Why this priority**: O consolidado substitui parte importante do controle
manual e é a principal saída de análise.

**Independent Test**: Exportar filtros com estados distintos e conferir abas,
valores, metadados, neutralização de fórmulas e auditoria.

**Acceptance Scenarios**:

1. A exportação respeita os filtros escolhidos e identifica o status e a versão
   de cada competência.
2. Contém conciliações, movimentos DIMP, proveniência, exceções, revisões e
   metadados de geração.
3. Registra usuário, data/hora, filtros e quantidade de registros.
4. Textos iniciados por caracteres interpretáveis como fórmula são
   neutralizados quando forem dados.
5. Usuário sem permissão não inicia nem baixa o arquivo.
6. Falha de geração não apresenta arquivo parcial como válido.

---

### User Story 7 — Preencher uma cópia da planilha-mestre (Priority: P1)

Como analista fiscal, quero enviar a planilha-mestre e receber uma cópia
preenchida com as competências elegíveis.

**Why this priority**: É a automação direta do processo demonstrado no vídeo e
elimina a cópia célula a célula.

**Independent Test**: Preencher um modelo sintético e o modelo de referência,
comparando células alteradas, fórmulas e conteúdo preservado.

**Acceptance Scenarios**:

1. A planilha original nunca é alterada.
2. O usuário seleciona explicitamente um CNPJ; se o modelo contiver CNPJ, ele
   deve corresponder.
3. Somente versões vigentes e aprovadas entram por padrão.
4. Incluir registros em revisão exige permissão especial, confirmação explícita
   e marcação visível no resultado; registros rejeitados nunca entram.
5. Células, fórmulas, estilos e conteúdos fora do mapeamento são preservados.
6. Competência ausente, duplicada ou ambígua no modelo produz erro claro e não
   gera arquivo parcial.
7. A cópia recebe nome distinto e a operação registra hash do modelo,
   competências, usuário e resultado.

---

### User Story 8 — Acompanhar situação e localizar competências (Priority: P2)

Como gestor, quero indicadores e filtros para localizar empresas e priorizar
pendências.

**Why this priority**: Melhora a gestão do volume, mas o fluxo principal
continua utilizável pelas listas e detalhes das histórias P1.

**Independent Test**: Gerar registros em todos os estados e validar totais,
filtros, ordenação e paginação combinados.

**Acceptance Scenarios**:

1. O painel mostra totais em revisão, aprovados, rejeitados, com avisos, com
   bloqueios e com conflitos.
2. A lista filtra por CNPJ, razão social, intervalo de competências, estado,
   layout e presença de exceções.
3. Indicadores refletem os mesmos filtros da lista.
4. Paginação e ordenação não duplicam nem omitem registros.
5. Qualquer resultado abre seu detalhe.

## Edge Cases

- O mesmo arquivo chega com outro nome.
- Dois usuários importam simultaneamente o mesmo arquivo.
- Dois arquivos diferentes representam o mesmo CNPJ e competência.
- CNPJ é inválido ou diverge entre cabeçalho e linha mensal.
- Competência é ausente, inválida ou diverge nas linhas DIMP.
- O arquivo possui várias abas, inclusive ocultas e não relacionadas.
- Cabeçalhos mudam de linha, mas mantêm rótulos reconhecíveis.
- Campo obrigatório contém fórmula sem valor calculado armazenado.
- Zero ou valor negativo válido precisa ser distinguido de célula vazia.
- Uma instituição aparece em várias linhas.
- Uma linha DIMP pertence a outra competência.
- Um fechamento diverge exatamente R$ 0,01 ou mais de R$ 0,01.
- Quadro 50-5 não tem DIMP; ausência não vira zero.
- O upload é XLSX falso, truncado, contém macro, vínculo externo ou compactação
  abusiva.
- A rede falha no meio do upload ou o servidor reinicia no processamento.
- A permissão é retirada durante uma sessão.
- Um usuário tenta usar a sessão ou job de outro.
- O modelo não tem um mês, contém mês duplicado ou estrutura alterada.
- A geração da exportação falha depois de começar.
- Uma versão nova chega após a versão vigente já ter sido aprovada.
- Texto importado ou digitado começa com `=`, `+`, `-` ou `@`.

## Requirements

### Functional Requirements

#### Integração e autorização

- **FR-001**: A funcionalidade MUST aparecer como a sexta ferramenta nativa do
  Auditoria-JB.
- **FR-002**: A ferramenta MUST reutilizar autenticação, sessão, navegação,
  permissões e trilha de uso do Auditoria-JB.
- **FR-003**: O sistema MUST possuir permissões distintas para acessar,
  importar, revisar, aprovar, resolver exceções/conflitos, exportar, preencher o
  modelo e incluir pendentes.
- **FR-004**: A autorização MUST ser validada no servidor em cada operação.
- **FR-005**: Sessões de trabalho e jobs MUST validar o usuário proprietário e a
  ferramenta esperada.
- **FR-006**: Usuário sem acesso MUST não visualizar a aba nem obter seus dados
  por chamada direta.

#### Importação e proteção dos arquivos

- **FR-007**: Apenas `.xlsx` MUST ser aceito nesta versão.
- **FR-008**: O upload da conciliação MUST possuir limite próprio, configurável,
  com padrão de 50 MB por arquivo.
- **FR-009**: O pacote MUST ser rejeitado se malformado, com macro, vínculo
  externo, caminho interno inseguro, entradas excessivas, tamanho descompactado
  excessivo ou razão de compressão abusiva.
- **FR-010**: Fonte apenas renomeada MUST ser reconhecida pelo SHA-256.
- **FR-011**: O sistema MUST guardar nome original, hash, tamanho, usuário,
  instante, layout, versão do parser e resultado da importação.
- **FR-012**: Fonte aceita MUST ser preservada de forma imutável.
- **FR-013**: Itens de um lote MUST ser independentes e produzir resumo final.
- **FR-014**: Processamento demorado MUST ocorrer em job observável.
- **FR-015**: Após reinício, processamento persistente abandonado MUST ser
  marcado como interrompido ou apto a tentativa idempotente; nunca permanecer
  indefinidamente em execução.
- **FR-050**: O staging MUST usar identificador interno opaco por upload,
  limitar quantidade e bytes totais do lote, remover parciais e impedir dois
  processamentos simultâneos da mesma sessão.

#### Extração e cálculos

- **FR-016**: O layout MUST ser identificado semanticamente.
- **FR-017**: CNPJ MUST ser válido e consistente entre cabeçalho e linha.
- **FR-018**: Competência MUST ser válida no formato `AAAAMM`.
- **FR-019**: Campo obrigatório ausente ou fórmula sem valor calculado MUST
  causar erro explícito, nunca zero silencioso.
- **FR-020**: Valores monetários MUST preservar precisão de centavos.
- **FR-021**: Com ST + sem ST MUST fechar com o total correspondente, com
  tolerância de até R$ 0,01.
- **FR-022**: Componentes DIMP MUST fechar com seu total, com tolerância de até
  R$ 0,01.
- **FR-023**: Total DIMP superior ao faturamento calculado em mais de R$ 0,01
  MUST gerar bloqueio; inferior em mais de R$ 0,01 MUST gerar aviso.
- **FR-024**: Layout sem DIMP MUST gerar aviso e valores nulos.
- **FR-025**: Todo fato financeiro MUST possuir proveniência.
- **FR-026**: A chave lógica MUST ser CNPJ + competência, com uma versão vigente
  e histórico de versões.

#### Exceções, conflitos e revisão

- **FR-027**: Problemas MUST ser classificados como erro fatal, aviso ou
  bloqueio.
- **FR-028**: Erro fatal MUST não criar conciliação parcial.
- **FR-029**: Bloqueio ou conflito aberto MUST impedir aprovação.
- **FR-030**: Resolver bloqueio ou conflito MUST exigir justificativa e
  permissão.
- **FR-031**: Fonte diferente para chave existente MUST criar candidata e
  conflito, sem sobrescrita.
- **FR-032**: Promover candidata MUST preservar a versão anterior e retornar o
  registro a Em revisão.
- **FR-033**: O ator de uma decisão MUST vir da sessão autenticada.
- **FR-034**: Decisões e eventos fiscais MUST ser append-only.
- **FR-035**: Mutações concorrentes MUST detectar estado desatualizado e impedir
  perda silenciosa de atualização.
- **FR-051**: A chegada de candidata MUST devolver conciliação aprovada ou
  rejeitada a Em revisão; apenas bloqueios da versão vigente e conflitos
  abertos impedem nova aprovação, sem apagar problemas históricos.

#### Exportações

- **FR-036**: O consolidado MUST conter dados, movimentos, proveniência,
  exceções, decisões e metadados.
- **FR-037**: A planilha-mestre MUST ser gerada como arquivo novo para um CNPJ
  explicitamente selecionado.
- **FR-038**: Apenas a versão vigente e aprovada MUST entrar por padrão.
- **FR-039**: Inclusão de Em revisão MUST exigir permissão especial,
  confirmação e sinalização no arquivo; Rejeitada MUST nunca entrar.
- **FR-040**: Texto exportado MUST ser protegido contra injeção de fórmula.
- **FR-041**: A estrutura do modelo MUST ser validada antes da escrita.
- **FR-042**: Erro MUST não produzir download parcial apresentado como válido.
- **FR-043**: Exportação MUST registrar usuário, parâmetros, quantidade e
  resultado.

#### Auditoria, concorrência e compatibilidade

- **FR-044**: Importação, duplicidade, erro, conflito, resolução, revisão,
  aprovação, rejeição, promoção, download de fonte e exportação MUST gerar
  evento de auditoria apropriado.
- **FR-045**: Estado fiscal e evento de domínio correspondente MUST ser gravados
  na mesma transação.
- **FR-046**: Trilha fiscal MUST impedir atualização e exclusão pela aplicação.
- **FR-047**: Operações concorrentes MUST ser atômicas e idempotentes.
- **FR-048**: Dados e fontes persistentes MUST integrar o procedimento de backup
  existente do Auditoria-JB.
- **FR-049**: A nova ferramenta MUST não alterar o comportamento das cinco
  ferramentas existentes.

### Key Entities

- **Lote de importação**: operação contendo itens de arquivos e seus resultados.
- **Fonte fiscal**: XLSX imutável identificado pelo SHA-256.
- **Conciliação**: chave CNPJ + competência e ponteiro para a versão vigente.
- **Versão**: dados extraídos de uma fonte; pode ser vigente, candidata,
  substituída ou descartada.
- **Movimento DIMP**: componentes por instituição e linha da versão.
- **Fato extraído**: valor e proveniência ou fórmula de derivação.
- **Exceção**: aviso ou bloqueio detectado por uma regra.
- **Conflito**: comparação entre versão vigente e candidata.
- **Revisão**: decisão imutável sobre o estado da conciliação.
- **Evento fiscal**: ação de domínio append-only.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% dos arquivos de referência são classificados conforme o
  resultado esperado: processado, duplicado, conflitante ou rejeitado.
- **SC-002**: Todos os valores conhecidos coincidem ao centavo.
- **SC-003**: Reimportar o conjunto, mesmo renomeado, não aumenta a quantidade
  de fontes nem conciliações.
- **SC-004**: Nenhuma candidata substitui automaticamente a vigente.
- **SC-005**: 100% dos fatos financeiros possuem fonte/célula ou fórmula de
  derivação.
- **SC-006**: Nenhuma competência com bloqueio ou conflito aberto é aprovada.
- **SC-007**: 100% das ações críticas registram usuário autenticado, data/hora,
  ação e resultado.
- **SC-008**: Todos os acessos não autorizados dos testes são bloqueados,
  inclusive cruzamento de sessões/jobs.
- **SC-009**: O modelo de referência preserva todas as células fora do
  mapeamento e preenche somente versões elegíveis.
- **SC-010**: Um lote de 30 arquivos de até 10 MB é processado em até 120
  segundos num servidor de referência com 4 núcleos, 8 GB de RAM e disco local.
- **SC-011**: Listagens e filtros respondem em até 2 segundos no percentil 95
  com 10 mil conciliações.
- **SC-012**: Exportação de até 10 mil conciliações termina em até 60 segundos.
- **SC-013**: A interface permanece utilizável durante jobs.
- **SC-014**: Toda a suíte existente continua passando.
- **SC-015**: A ferramenta funciona no mesmo processo, endereço e login, sem
  segundo servidor.

## Assumptions

- CNPJ + competência identifica a unidade lógica.
- Os relatórios fornecidos são a referência funcional inicial.
- Mudança desconhecida de layout falha explicitamente, sem extração posicional
  silenciosa.
- O modelo é fornecido em cada operação de preenchimento.
- Fontes e trilha fiscal não têm exclusão pela interface nesta versão.
- Exposição externa e automação de backup online são evoluções separadas.
