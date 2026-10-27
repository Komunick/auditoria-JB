# Feature Specification: Tarefas e Prazos (Fase 1 do módulo de gestão da qualidade)

**Feature Branch**: `013-tarefas-e-prazos`

**Created**: 2026-10-27

**Status**: Rascunho para implementação. Pendências marcadas em "Pendências"; o que depende delas fica
configurável ou com padrão anotado.

**Input**: a solicitação "Módulo de Gestão da Qualidade e Acompanhamento Operacional", da diretoria da
JB Fraga (PDF de 27/10/2026), e as respostas recebidas no mesmo dia. O PDF e as respostas ficam na pasta
Briefing da JB, fora deste repositório, que é público. Esta spec não traz nomes de colaboradores nem de
clientes, só papéis.

## Contexto

A solicitação pede dez coisas: atividades por setor, registro de ocorrências, prazos e produtividade,
indicadores, planos de ação, alertas, painel da diretoria, relatórios, níveis de acesso e integração.
A diretoria definiu a ordem:

- **Primeiro a funcionar: tarefas e prazos.** Ocorrências, planos de ação, indicadores e painel completo
  vêm em specs seguintes.
- **Primeiro setor: Fiscal.** O modelo de dados já nasce com setores, para os outros entrarem depois sem
  refazer nada.
- **Clientes: todos.** Não há piloto com poucos clientes.
- **Agenda de obrigações personalizada por cliente**, sem usar a do sistema contábil.
- **Hoje não há controle unificado.** Cada colaborador tem a sua planilha ou o seu sistema, com a sua
  carteira de clientes. O pedido é unificar no sistema.
- **Alertas no sistema e por e-mail.**

Planilhas reais recebidas (DP) mostram o formato atual: uma lista de empresas por colaborador, com contato,
e-mail, município, atividade, colunas de checklist mensal (folha, e-consignado, boleto sindical) e uma
observação com características que mudam o trabalho do mês (adiantamento quinzenal, contribuição
negocial, lucro real, sem movimento).

## Objetivo e escopo

Criar a ferramenta **"10. Tarefas e prazos"**. Ela gera, mês a mês, as tarefas de cada cliente a partir
das obrigações que se aplicam a ele, distribui pela carteira de cada colaborador, acompanha o andamento e
os atrasos, exige conferência quando configurado e avisa antes do prazo.

### Ideia central: a personalização é marcar o cliente

Montar à mão a agenda de centenas de clientes é inviável. A personalização funciona assim:

1. O escritório cadastra as **obrigações** (DAS, EFD, DCTFWeb...): periodicidade, regra de vencimento e
   **a quem se aplicam**, por **características**.
2. Cada cliente recebe as suas **características** (regime, contribuinte de ICMS, tem folha, sem
   movimento, adiantamento quinzenal...).
3. O sistema cruza os dois e gera a agenda. O que fugir da regra se ajusta **naquele cliente**: incluir ou
   tirar uma obrigação, mudar o dia de vencimento ou o responsável.

### Incluído

- Setores, com responsável e **substituto por período** (caso real: responsável de licença).
- Colaboradores ligados a um ou mais setores (caso real: uma pessoa em todos os setores).
- **Carteira**: em cada cliente, o colaborador responsável por setor.
- Catálogo de características de cliente e de obrigações, editável pelo escritório.
- Ajustes por cliente: incluir, excluir ou mudar o vencimento de uma obrigação.
- Calendário de feriados para "dia útil".
- Geração mensal das tarefas, idempotente.
- Tarefas avulsas, sem obrigação ligada.
- Ciclo da tarefa com conferência do responsável do setor, quando a obrigação exige.
- Telas "Minhas tarefas", "Setor" e "Agenda do cliente", com cores verde/amarelo/vermelho e filtros.
- Alertas no sistema e e-mail diário (resumo).
- Importação das planilhas de carteira de cada colaborador.
- Histórico imutável de tudo; exportação em Excel.

### Fora do escopo desta fase

- Ocorrências e não conformidades, planos de ação com anexos e validação (Fase 2).
- Indicadores (KPIs), painel gerencial completo e relatórios em PDF (Fase 3). Esta fase **grava os dados
  que eles vão usar**: datas de conclusão, atraso, conferência e responsável na data.
- Custo × produtividade e registro de horas. Depende de definição da diretoria (pendência P-09).
- Setores além do Fiscal **com obrigações cadastradas**. A estrutura aceita todos; o catálogo inicial é do
  Fiscal.
- Avisar o **cliente** por e-mail. Depende da pendência P-03; a estrutura de destinatário já prevê.
- Integração com o sistema contábil (decisão da diretoria: não usar).

## User Scenarios & Testing

Testes automatizados obrigatórios para as histórias P1 e para autorização, geração idempotente,
vencimento com feriado, substituição por período e alertas. Fixtures sintéticas.

### User Story 1 — Setores, responsáveis e substitutos (P1)

Como diretoria, quero cadastrar os setores, quem pertence a cada um, quem responde por ele e quem o
substitui num período.

**Acceptance Scenarios**:

1. Setor tem nome, responsável e membros. Uma pessoa pode estar em vários setores.
2. Membros são **usuários do sistema** (o login que já existe). Usuário desativado sai das distribuições
   novas, mas continua no histórico.
3. Substituição tem titular, substituto, início e fim. Durante o período, o substituto **recebe o que iria
   para o titular**: conferências, alertas e tarefas novas da carteira do titular. Quando o período acaba,
   tudo volta sozinho para o titular.
4. O histórico guarda quem respondia em cada data. Uma conferência feita pelo substituto mostra "conferido
   por X, substituindo Y".
5. Substituições sobrepostas para o mesmo titular são recusadas.

### User Story 2 — Características do cliente e carteira (P1)

Como responsável do setor, quero marcar as características de cada cliente e quem cuida dele no meu setor.

**Acceptance Scenarios**:

1. Catálogo de características editável, agrupado (Regime, Tributos, Folha, Situação, Outros). Exemplos
   do material recebido: regime (Simples, Lucro Presumido, Lucro Real, MEI), sem movimento, adiantamento
   quinzenal, contribuição negocial. A lista final é da JB (P-01).
2. Grupo **exclusivo** (só uma opção por cliente, como regime) ou **múltiplo** (várias, como tributos).
3. Carteira: em cada cliente, um responsável por setor. Um colaborador vê a sua carteira filtrando por ele.
4. Mudar o responsável muda as tarefas **abertas e futuras** daquele setor. As concluídas ficam com quem
   as fez.
5. Marcar ou trocar características em lote para vários clientes (por exemplo, todos os do Simples).
6. Toda mudança fica no histórico do cliente, junto com as da aba 9.

### User Story 3 — Obrigações e regras de vencimento (P1)

Como responsável do Fiscal, quero cadastrar cada obrigação uma vez e dizer para quem ela vale e quando
vence.

**Acceptance Scenarios**:

1. Obrigação tem nome, setor, periodicidade (mensal, trimestral, anual ou por demanda), competência (a que
   período se refere) e **regra de vencimento**.
2. A regra de vencimento cobre os casos usuais: "dia N do mês seguinte à competência", "último dia útil do
   mês seguinte", "dia N do mês M" (anuais). Também diz o que fazer quando cai em dia sem expediente:
   antecipar, adiar ou manter.
3. **Aplica-se quando**: um conjunto de condições sobre as características. Por exemplo: "regime = Simples
   E NÃO sem movimento". Sem condição, vale para todos os clientes do setor.
4. Antecedência do início: quantos dias antes do vencimento a tarefa aparece como "a fazer". O padrão é a
   tarefa já nascer na geração do mês.
5. "Exige conferência": a tarefa só fecha depois de o responsável do setor conferir.
6. Mudar uma obrigação vale para as próximas gerações. As tarefas já geradas não mudam; o sistema pode
   **propor** a atualização das abertas, que a pessoa confirma.
7. O catálogo começa **vazio**. A lista de obrigações fiscais é da JB (P-01); a spec não inventa prazo.

### User Story 4 — Ajustes por cliente (P1)

Como responsável da carteira, quero tratar a exceção de um cliente sem criar uma regra nova.

**Acceptance Scenarios**:

1. Em um cliente, para uma obrigação: **incluir** (mesmo sem casar com a regra), **excluir** (mesmo
   casando) ou **mudar o vencimento** (outro dia ou outra regra).
2. O ajuste pode ter **validade** (de/até). Exemplo: "excluir enquanto estiver sem movimento".
3. Todo ajuste exige motivo e fica no histórico.
4. A agenda do cliente mostra o que vem da regra e o que vem de ajuste, com o motivo.

### User Story 5 — Geração mensal das tarefas (P1)

Como escritório, quero que as tarefas do mês apareçam sozinhas, sem ninguém digitar.

**Acceptance Scenarios**:

1. A geração cria uma tarefa por **cliente × obrigação × competência** aplicável, com o vencimento
   calculado e o responsável da carteira (ou o substituto do período).
2. **Idempotente**: rodar de novo não duplica (chave única cliente + obrigação + competência).
3. Roda sozinha no começo de cada mês e pode ser disparada à mão pelo responsável do setor, para um mês ou
   para um cliente, com prévia ("vai criar N tarefas").
4. Cliente baixado ou "não é mais cliente" não recebe tarefa. Inativo também não, salvo ajuste de
   inclusão.
5. Cliente sem responsável no setor gera a tarefa **sem responsável**. Ela aparece numa fila "sem
   responsável" do setor, nunca some.
6. Obrigação trimestral ou anual só gera na competência certa.

### User Story 6 — Executar, conferir e acompanhar (P1)

Como colaborador, quero ver o que é meu, em ordem de prazo, e registrar o andamento.

**Acceptance Scenarios**:

1. Situações: **a fazer → em andamento → concluída**. Com conferência: **concluída → conferida** ou
   **devolvida** (volta para em andamento, com motivo). Também: **aguardando cliente** (documento ou
   informação que o cliente não mandou) e **dispensada** (não se aplica neste mês, com motivo e só pelo
   responsável do setor).
2. Cores do painel (pedido do PDF):
   - **verde**: concluída ou conferida dentro do prazo;
   - **amarelo**: em andamento, aguardando cliente ou vencendo em até N dias (configurável, padrão 3);
   - **vermelho**: atrasada ou devolvida.
3. **Atraso**: prazo vencido e não concluída. Concluída depois do prazo fica marcada como **"fora do
   prazo"** para sempre. É o dado do indicador "entregue no prazo" da Fase 3.
4. Cada mudança grava quem, quando, de qual para qual situação e o comentário, num histórico imutável.
5. Comentários livres na tarefa.
6. "Minhas tarefas": a carteira do colaborador, mais o que ele substitui, por prazo.
   "Setor": o responsável vê tudo do setor, redistribui e confere.
   "Agenda do cliente": tudo de um cliente, todos os setores, por competência.
7. Filtros por cliente, setor, colaborador, período (competência ou vencimento) e situação, como pede o
   PDF.
8. Ações em lote para o responsável do setor: redistribuir e dispensar, com motivo.

### User Story 7 — Alertas no sistema e por e-mail (P1)

Como colaborador e como responsável, quero saber antes que algo atrase.

**Acceptance Scenarios**:

1. **No sistema**: aviso no topo com "N tarefas vencendo nos próximos dias e M atrasadas", para a carteira
   de quem entrou, e do setor inteiro para o responsável.
2. **E-mail**: um resumo por dia por pessoa, nunca uma mensagem por tarefa. Traz o que vence nos próximos
   N dias, o que atrasou, o que espera a conferência dela e o que está "aguardando cliente" há mais de X
   dias.
3. Destinatários desta fase: o responsável da tarefa (ou o substituto do período) e o responsável do setor.
   A estrutura já prevê o **responsável legal do cliente** como destinatário, ligado só quando a P-03 for
   respondida.
4. Sem configuração de envio de e-mail (P-04), o alerta no sistema funciona e a tela diz "e-mail
   desligado". Nunca falha em silêncio.
5. Cada e-mail enviado ou que falhou fica registrado (para quem, quando, quantas tarefas e o resultado),
   sem repetir o mesmo resumo no mesmo dia.

### User Story 8 — Trazer as planilhas de carteira (P2)

Como responsável do setor, quero aproveitar as planilhas que cada colaborador já tem.

**Acceptance Scenarios**:

1. Enviar a planilha (.xls ou .xlsx) de um colaborador e escolher **de quem é a carteira** e **de qual
   setor**.
2. Cada linha é ligada a um cliente da aba 9: pelo CNPJ quando houver; senão, pelo nome, com sugestão e
   confirmação. Quem não casar aparece para decidir, e nada é criado sem confirmação.
3. Contato e e-mail entram no cadastro do cliente (campos novos, ver Requisitos).
4. A coluna de observação vira **sugestão de características** ("adiantamento quinzenal", "sem movimento"
   etc.), que a pessoa confirma.
5. Colunas de checklist (folha, e-consignado, taxa) **não são importadas**: viram obrigações do setor no
   catálogo. A semântica das marcas fica para a P-05.
6. Prévia antes de gravar, uma transação só, arquivo apagado depois de lido — mesmo padrão da importação da
   aba 9.

### User Story 9 — Exportar (P2)

1. Exportar em Excel a lista filtrada de tarefas, com situação, prazos, responsável, quem concluiu e quem
   conferiu.

### Edge Cases

- Vencimento que cai em feriado ou fim de semana: segue a regra da obrigação (antecipar, adiar ou manter).
- Fevereiro e "dia 30": vencimento num dia que não existe no mês vira o último dia do mês.
- Característica removida de um cliente com tarefas abertas daquela obrigação: as abertas ficam, com aviso
  "não se aplica mais — dispensar?"; nada some sozinho.
- Substituto que também é membro do setor: recebe as duas carteiras, sem duplicar tarefa.
- Duas pessoas mudando a mesma tarefa: a segunda recebe conflito (revision), como no resto do sistema.
- Geração rodando duas vezes ao mesmo tempo: a chave única impede duplicata.
- O servidor esteve desligado no dia 1º: a geração do mês roda na primeira oportunidade, porque o sistema
  sabe qual foi a última competência gerada.

## Requirements

### Functional Requirements

- **FR-001**: Setores com responsável e membros (usuários). Pessoa em vários setores.
- **FR-002**: Substituição por período, sem sobreposição, com resolução automática de "quem responde hoje".
- **FR-003**: Catálogo de características com grupos exclusivos ou múltiplos; atribuição a clientes,
  individual e em lote.
- **FR-004**: Carteira: um responsável por cliente e setor.
- **FR-005**: Obrigações com periodicidade, competência, regra de vencimento, ajuste de dia sem expediente,
  condição de aplicação por características e "exige conferência".
- **FR-006**: Ajustes por cliente (incluir, excluir, mudar vencimento) com validade e motivo.
- **FR-007**: Feriados cadastráveis. Os nacionais fixos e os móveis (calculados a partir da Páscoa) vêm
  prontos; os estaduais e municipais são confirmados pela JB (P-08).
- **FR-008**: Geração idempotente por cliente + obrigação + competência, automática no mês e manual com
  prévia.
- **FR-009**: Ciclo de situações da US6, com histórico imutável na mesma transação da mudança.
- **FR-010**: Atraso e "fora do prazo" calculados no servidor, no fuso de Salvador.
- **FR-011**: Alertas no sistema e e-mail diário por pessoa, com registro de envio e sem duplicar.
- **FR-012**: Importação de planilha de carteira com casamento por CNPJ ou nome e confirmação.
- **FR-013**: Cadastro do cliente (aba 9) ganha **contato** e **e-mail** do cliente (aditivo).
- **FR-014**: Exportação em Excel pela escrita segura (`core/planilha_segura.py`).

### Permissões novas (nenhuma no padrão de usuário novo)

| Slug | O que libera | Perfil sugerido |
|---|---|---|
| `aba.tarefas` | Abrir a aba, ver a própria carteira e as próprias tarefas | colaborador |
| `tarefas.executar` | Mudar a situação e comentar as **próprias** tarefas | colaborador |
| `tarefas.setor` | Ver e redistribuir todas as tarefas dos setores **que responde**, dispensar e conferir | responsável do setor |
| `tarefas.todas` | Ver tudo de todos os setores | diretoria |
| `tarefas.configurar` | Catálogos de características e obrigações, ajustes por cliente, geração manual | responsável do setor |
| `setores.administrar` | Setores, membros, responsáveis e substituições | diretoria |
| `tarefas.exportar` | Exportar em Excel | responsável e diretoria |

`tarefas.setor` vale só para o setor em que a pessoa é responsável ou substituta naquela data. O servidor
confere isso a cada pedido. A tela de administração ganha **atalhos de perfil** (colaborador, responsável,
diretoria) que marcam o conjunto sugerido; o administrador ainda vê e ajusta caixa por caixa.

### Key Entities

- **Setor**, **membro do setor**, **substituição** (titular, substituto, período).
- **Característica** (grupo, exclusivo/múltiplo) e **característica do cliente**.
- **Carteira** (cliente, setor, responsável).
- **Obrigação** (setor, periodicidade, regra de vencimento, condição, exige conferência, ativa).
- **Ajuste do cliente** (cliente, obrigação, tipo, valores, validade, motivo).
- **Feriado** (data, abrangência, descrição).
- **Tarefa** (cliente, setor, obrigação ou avulsa, competência, responsável, início, vencimento, situação,
  datas de conclusão e conferência, fora do prazo, revision).
- **Evento da tarefa** (imutável: quem, quando, de/para, comentário, "substituindo quem").
- **Geração** (competência, setor, quem disparou, contagens).
- **Envio de alerta** (pessoa, data, canal, quantidades, resultado).

Banco: as tabelas entram no `clientes.db` (schema 2, aditivo). Tarefa sem cliente não existe, e a
integridade referencial com `cliente` exige o mesmo banco.

## Success Criteria

- **SC-001**: Com as obrigações do Fiscal cadastradas e os clientes marcados, a geração do mês cria a
  agenda de todos os clientes sem digitação, e rodar de novo não muda nada.
- **SC-002**: Nenhuma tarefa gerada fica sem aparecer em alguma lista: a do responsável, a do substituto ou
  a fila "sem responsável" do setor.
- **SC-003**: Durante uma substituição, o substituto recebe os alertas e as conferências do titular; no dia
  seguinte ao fim, voltam para o titular sem ninguém mexer.
- **SC-004**: Toda tarefa concluída tem quem, quando e se foi no prazo. Toda conferida tem quem conferiu.
- **SC-005**: A suíte existente continua passando, mais os testes novos.

## Pendências (perguntas à JB)

**Como fica enquanto não há resposta:** catálogo de obrigações vazio (P-01); carteira montada à mão ou pela
importação (P-02); e-mail só para pessoas da JB (P-03); e-mail desligado até haver conta (P-04); colunas de
checklist viram obrigações e as marcas antigas não são importadas (P-05); diretoria = administradores
(P-06); feriados só nacionais (P-08); resumo diário às 7h, alerta 3 dias antes (P-10).

- **P-01**: Lista de obrigações fiscais: nome, periodicidade, regra de vencimento e para quais clientes
  (regime/características). Lista final de características.
- **P-02**: Planilha ou print de cada pessoa do Fiscal, para montar a carteira inicial.
- **P-03**: "Responsável legal" do alerta por e-mail: o do cliente (sócio) ou o do setor na JB? Se for o do
  cliente, quais alertas vão para ele.
- **P-04**: Conta de e-mail que envia os alertas (remetente @jbfraga.com.br e o serviço de envio).
- **P-05**: O que se marca nas colunas de checklist das planilhas (X, data, valor).
- **P-06**: Quem é a diretoria e qual o papel da pessoa que está em todos os setores.
- **P-07**: O setor "Administrativo" do PDF existe, é o "Financeiro" ou fica fora?
- **P-08**: Feriados estaduais e municipais que o escritório respeita.
- **P-09**: Custo × produtividade: horas × valor da hora ou honorário? Haverá registro de tempo? (Fase 3.)
- **P-10**: Horário do resumo por e-mail e antecedência padrão do alerta.
- **P-11**: Quais obrigações exigem conferência do responsável.
- **P-12**: "Aguardando cliente" para o relógio do prazo interno ou não? (O prazo legal continua o mesmo.)
