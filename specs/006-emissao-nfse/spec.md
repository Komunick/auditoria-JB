# Feature Specification: Emissão de NFS-e — Fase 1 (lote revisado e DPS sem envio)

**Feature Branch**: `006-emissao-nfse`

**Created**: 2026-10-15

**Status**: Rascunho para revisão. Pendências da JB marcadas como JB-1 a JB-13.

**Input**: A JB Fraga Contabilidade emite à mão, no portal Nota Salvador, uma
NFS-e por aluno de uma creche cliente (ME/EPP do Simples Nacional), com os
dados que a escola manda pelo WhatsApp (Zappy Contábil). A partir de
01/11/2026, ME/EPP do Simples só emitem pelo **Emissor Nacional da NFS-e**.
Base: `Clientes\JB Fraga Contabilidade\Briefing\nfse-creche-analise-do-video.md`
(15/10/2026), seções 1, 4 e 5. O briefing fica fora do repositório porque o
vídeo mostra dados pessoais.

## Legenda

| Marca | Significado |
|---|---|
| **[confirmado]** | visto no vídeo de 13/10/2026 ou em fonte oficial |
| **[sistema atual]** | visto no código do `dev` (c5c6b16) |
| **[proposta]** | decisão desta spec, revisável |
| **[JB-n]** | depende da pergunta n da seção 5 do briefing (JB-11 a JB-13 são novas, ver o fim). O sistema **não decide por padrão** |
| **[Rn]** | depende da documentação oficial do Emissor Nacional; é tarefa da própria Fase 1 (plan.md, "Pesquisas") |

## Objetivo e escopo

Criar a **oitava ferramenta** nativa da auditoria-JB. Ela recebe a lista de
cobranças que um cliente prestador manda (planilha ou texto colado da
conversa), monta cada nota a partir de um **perfil de emissão** do cliente,
confere tudo, mostra o lote para a atendente aprovar e gera, para cada linha
aprovada, a **DPS** (Declaração de Prestação de Serviço) no leiaute do padrão
nacional.

**Nada é transmitido nesta fase.** Não há certificado, assinatura, mTLS nem
chamada de rede. A DPS da Fase 1 é uma prévia validada contra o XSD oficial,
sem efeito fiscal.

O primeiro cliente é a creche do vídeo, mas nada fica preso a ela: perfil,
turmas, códigos e modelo da discriminação são dados cadastrados.

### Por que esta fase vem primeiro

No vídeo, cada nota leva uns 2 minutos, metade disso digitando a
discriminação, e houve retrabalho porque faltou a alíquota **[confirmado]**.
A Fase 1 tira a digitação e a conferência manual. Ela não depende de
certificado nem de respostas da JB: toda decisão que depende delas é um campo
do perfil **sem valor padrão**, e o perfil incompleto bloqueia a geração da
DPS. Os testes usam perfis fictícios com cada opção preenchida.

### Incluído

- Perfil de emissão por cliente, versionado, com a tabela turma → códigos.
- Planilha-modelo para baixar e importação dela.
- Importação do texto colado da conversa do WhatsApp.
- Conferência automática por linha: CPF, valor, competência, turma,
  nomes, endereço, duplicata e tamanho da discriminação.
- Tela de revisão do lote: corrigir campo com motivo, excluir linha,
  reconferir, aprovar ou descartar.
- Geração da DPS (XML sem assinatura, ambiente de produção restrita) na
  aprovação, validada contra o XSD oficial.
- Download do XML de cada DPS, do zip do lote e da planilha-resumo.
- Permissões, trilha geral e trilha de domínio.

### Fora do escopo (fases seguintes do briefing)

- Certificado digital, assinatura XML, mTLS e qualquer chamada à Sefin
  Nacional (Fase 2). Ver JB-1.
- Consulta de DPS antes de reenviar, guarda de XML e PDF da NFS-e (Fase 2).
- Emissão em produção e devolução das notas à escola (Fase 3). Ver JB-5.
- Cancelamento e substituição (Fase 4). Ver JB-7.
- WebService do Nota Salvador para quem não é do Simples (Fase 4).
- Entrada automática pelo webhook do Zappy ou pelo portal do cliente
  (Fase 4). Ver JB-6.
- Importador do formato de planilha que a escola já usa. Ver JB-4. A Fase 1
  entrega a planilha-modelo da JB.
- A "ponte" pela extensão `nfse-automacao` até 31/10.

## Dados de exemplo

Todos os exemplos desta spec e das fixtures são **fictícios**. Nenhum nome,
CPF, endereço ou valor do vídeo entra no repositório.

| Papel | Dado fictício |
|---|---|
| Prestador | Escola Exemplo Ltda, CNPJ 11.222.333/0001-81 |
| Responsável 1 | Ana Exemplo, CPF 123.456.789-09 |
| Responsável 2 | Bruno Teste, CPF 111.444.777-35 |
| CPF com dígito errado | 123.456.789-00 |
| Alunos | Pedro Exemplo (Berçário), Lia Exemplo (Infantil II), Caio Teste (Berçário) |
| Valores | R$ 1.250,00 e R$ 980,50 |

Texto colado de exemplo:

```text
Competência: 11/2026
Responsável: Ana Exemplo
CPF: 123.456.789-09
Celular: (71) 90000-0000
ENDEREÇO: Rua das Flores, 100, ap 201, Bairro Exemplo, Salvador-BA, CEP 40000-000
ALUNO: Pedro Exemplo - BERÇÁRIO
Valor: R$ 1.250,00
```

Os rótulos seguem os blocos vistos no vídeo (competência, responsável, CPF,
celular, endereço, aluno com a turma, valor) **[confirmado]**. O formato exato
das mensagens reais (separadores, ordem, prefixos) depende de JB-4.

## User Scenarios & Testing

Testes automatizados são obrigatórios para todas as histórias P1 e para os
casos de autorização, concorrência, idempotência e exportação (constituição,
princípio V). Parsers são testados com fixtures sintéticas.

### User Story 1 — Acessar a oitava ferramenta com segurança (P1)

Como usuário autorizado, quero abrir a Emissão de NFS-e dentro da auditoria-JB,
sem outro login nem endereço.

**Independent Test**: usuário com `aba.nfse` abre a aba; usuário sem ela não
vê o botão e recebe 403 em chamada direta, com a tentativa na trilha.

**Acceptance Scenarios**:

1. Usuário com `aba.nfse` vê a oitava ferramenta e consegue abri-la.
2. Usuário sem `aba.nfse` não vê a aba nem obtém dados por chamada direta.
3. Toda ação exige, cumulativamente, a aba e o slug próprio.
4. Permissão retirada durante a sessão vale na operação seguinte.
5. A trilha geral nunca grava CPF, nome de aluno nem nome de responsável:
   grava IDs e contagens.

### User Story 2 — Cadastrar o perfil de emissão do cliente (P1)

Como responsável fiscal, quero cadastrar uma vez como cada cliente emite, para
a atendente não digitar códigos nem alíquota a cada nota.

**Independent Test**: criar um perfil fictício com duas turmas, alterá-lo e
conferir que surgiu a versão 2 sem apagar a 1; deixar a decisão de endereço
vazia e conferir que a geração da DPS é recusada com a lista do que falta.

**Acceptance Scenarios**:

1. O perfil identifica o prestador: CNPJ com dígito conferido, razão social,
   inscrição municipal e município pelo código IBGE (Salvador, no caso da
   creche **[confirmado]**).
2. Regime: Simples Nacional ME/EPP **[confirmado]**. Emissor: Nacional, o
   único aceito na Fase 1 **[proposta]**.
3. ISS retido pelo tomador é escolhido no cadastro (na creche, "Não"
   **[confirmado]**).
4. Estes campos **não têm valor padrão**. Enquanto vazios, o perfil aparece
   como "com pendências", e a geração da DPS é recusada com a lista:
   - alíquota, se ela vai na DPS, regime de apuração no Simples, regime
     especial e tributos aproximados **[JB-8]**. No portal foi 5,00%
     **[confirmado]**; o perfil guarda o número, mas o uso na DPS espera JB-8;
   - endereço do tomador: usar o que a escola mandou ou não informar
     **[JB-2]**;
   - grupo do IBS/CBS na DPS **[R3; se for opcional, JB-8]**;
   - série da DPS **[R4]**.
5. O modelo da discriminação usa campos de uma lista fechada. O da creche é o
   do vídeo **[confirmado]**:
   `REFERENTE AOS SERVIÇOS PRESTADOS DE {TURMA} AO MENOR: {ALUNO} NO PERÍODO DE {MES}/{ANO}.`
   Se o mês vai em número ou por extenso, e se os nomes vão em maiúsculas,
   ainda não se sabe **[JB-11]**. Na sintaxe desta spec, campo escrito em
   maiúsculas devolve o valor em maiúsculas (lista em `data-model.md`), então
   a forma final do modelo da creche sai de JB-11. Campo fora da lista é
   recusado ao salvar.
6. A tabela turma → códigos guarda, por turma: nome, apelidos, categoria
   (infantil ou fundamental), código de tributação nacional, código
   municipal, NBS, indicador de operação e classificação tributária do
   IBS/CBS e, como referência do Nota Salvador, CNAE, item da lista e CTISS.
   - Berçário e infantil: os códigos usados no Nota Salvador estão no vídeo
     **[confirmado]**; a correspondência com os campos da DPS nacional sai
     de **[R2]**.
   - Fundamental: CNAE 8513900 **[confirmado na lista do prestador]**; os
     demais códigos **[JB-3]**.
   - A lista completa de turmas da escola **[JB-3]**.
   - Turma sem um código obrigatório fica "pendente".
7. Alterar o perfil cria uma versão nova. A anterior nunca é sobrescrita, e
   cada lote e cada DPS apontam a versão que usaram.
8. Só quem tem `nfse.perfis` cria ou altera perfil.

### User Story 3 — Importar o lote pela planilha-modelo (P1)

Como atendente, quero subir a planilha que a escola preencheu e ver uma linha
por aluno.

**Independent Test**: baixar a planilha-modelo, preencher com dados
fictícios, importar e conferir que cada linha mostra a aba e a linha de
origem; importar o mesmo arquivo com outro nome e conferir que o sistema
aponta o lote existente.

**Acceptance Scenarios**:

1. O sistema oferece a planilha-modelo (`.xlsx`) com colunas fixas, uma aba
   de instruções e nenhum dado **[proposta]**. A coluna de CPF vem formatada
   como texto, para o Excel não apagar o zero inicial.
2. O arquivo é validado antes do openpyxl: extensão, tamanho, macro, vínculo
   externo, caminho inseguro e compressão abusiva **[sistema atual:
   `validar_pacote_xlsx`]**.
3. As colunas são achadas pelo rótulo normalizado (sem diferenciar caixa,
   acento e espaço), não pela posição. Coluna obrigatória ausente recusa o
   arquivo inteiro, dizendo qual falta.
4. Cada valor guarda arquivo, SHA-256, aba, célula, rótulo e regra de
   leitura.
5. Linha totalmente vazia é ignorada e contada. Linha parcial entra com
   bloqueio; nunca é descartada.
6. Célula com fórmula sem valor calculado conta como ausente.
7. O mesmo arquivo (mesmo SHA-256) para o mesmo perfil não cria outro lote:
   o sistema aponta o lote que já existe, salvo se ele foi descartado.
8. O arquivo original é guardado sem alteração, nomeado pelo SHA-256, fora
   do Git.

### User Story 4 — Importar o lote pelo texto colado da conversa (P1)

Como atendente, quero colar o que a escola mandou no WhatsApp e ter as linhas
prontas, sem redigitar.

**Independent Test**: colar um texto sintético com três blocos (um com CPF
inválido e um sem valor) e conferir três linhas, cada uma com o número do
bloco e as linhas do texto de onde veio, e os dois bloqueios.

**Acceptance Scenarios**:

1. O texto é separado em blocos, um por aluno. Um bloco começa no rótulo de
   competência ou de responsável **[proposta; validar com mensagens reais:
   JB-4]**.
2. Rótulos aceitos, sem diferenciar caixa e acento, seguidos de `:` ou `-`:
   Competência, Responsável, CPF, Celular ou Telefone, E-mail, Endereço,
   Aluno, Turma e Valor.
3. A turma pode vir separada ou junto do aluno (`ALUNO: Pedro Exemplo -
   BERÇÁRIO`), como no vídeo **[confirmado]**. A separação só aceita, no fim
   do campo, um nome ou apelido de turma do perfil. Sem isso, a linha fica
   com turma ausente; o sistema não adivinha.
4. Prefixo de data, hora e remetente de mensagem copiada, se existir, é
   ignorado. O formato real desse prefixo depende de JB-4.
5. Linha do texto que não casa com nenhum rótulo aparece no bloco como
   "texto não reconhecido" (aviso). Nada some calado.
6. Bloco com rótulo repetido (dois "Valor") recebe bloqueio. O sistema não
   escolhe um dos dois.
7. O endereço do texto fica como veio, em texto livre; o CEP é extraído
   quando houver. Se o perfil disser que o endereço vai para a nota (JB-2),
   a linha vinda do texto fica com "endereço não estruturado" (bloqueio) até
   ser corrigida ou reimportada pela planilha.
8. O texto original é guardado sem alteração, com SHA-256. Colar o mesmo
   texto de novo aponta o lote existente.
9. O texto colado tem limite de tamanho **[proposta: 256 KB]**.

### User Story 5 — Conferir cada linha automaticamente (P1)

Como atendente, quero que o sistema aponte o que está errado antes de eu
aprovar, para não descobrir o erro depois de emitir.

**Independent Test**: lote sintético com um caso de cada regra; cada linha
recebe exatamente os apontamentos esperados, e o lote com bloqueio não
aprova.

**Acceptance Scenarios**:

1. **CPF do responsável**: 11 dígitos com dígito verificador válido. Ausente
   ou inválido: bloqueio. Célula numérica da planilha com menos de 11 dígitos
   é completada com zeros à esquerda e recebe aviso **[proposta]**.
2. **Valor**: maior que zero e com no máximo duas casas decimais; o prefixo
   `R$` é aceito. Ausente, zero, negativo, com fração de centavo ou em
   formato ambíguo (`1.250`: milhar ou decimal?): bloqueio. O formato ambíguo
   é recusado, nunca chutado, como já faz a conciliação **[sistema atual:
   `para_decimal`]**. Valor ausente nunca vira zero **[constituição,
   princípio I]**.
3. **Competência**: mês e ano válidos, nos formatos de `data-model.md`.
   Ausente ou inválida: bloqueio. Competência diferente da maioria do lote:
   aviso **[proposta]**. Limites do Emissor Nacional para competência
   passada ou futura **[R4]**.
4. **Turma**: tem de existir no perfil, pelo nome ou por um apelido, depois
   da normalização. Desconhecida: bloqueio. Conhecida mas sem os códigos:
   bloqueio "turma pendente" **[JB-3]**.
5. **Nomes**: responsável e aluno são obrigatórios. Ausente: bloqueio.
6. **Endereço**: incompleto gera aviso enquanto o perfil não decide (JB-2);
   gera bloqueio se o perfil disser que o endereço vai para a nota.
7. **Duplicata**: a chave é CPF + aluno normalizado + competência
   **[confirmado: regra do briefing]**. Chave repetida no mesmo lote:
   bloqueio na segunda ocorrência, apontando a primeira. Chave já presente
   em lote aprovado do mesmo perfil: bloqueio, apontando o lote. Na Fase 2,
   "já emitida" passa a incluir NFS-e autorizada.
8. **Irmãos**: o mesmo CPF com alunos diferentes é permitido, uma nota por
   aluno **[confirmado]**.
9. **Discriminação**: a montada não pode passar do tamanho máximo do campo
   da DPS **[R1]**. Passou: bloqueio.
10. Caractere de controle ou invisível no texto é removido, com aviso.
11. Cada apontamento traz código, nível (aviso ou bloqueio), campo e
    mensagem em português.
12. A conferência roda de novo quando uma linha é corrigida e quando o
    perfil muda (botão "reconferir"). As rodadas anteriores ficam guardadas.

### User Story 6 — Revisar e aprovar o lote (P1)

Como atendente, quero ver cada nota montada antes de aprovar e corrigir o que
estiver errado sem perder o que a escola mandou.

**Independent Test**: corrigir um CPF com motivo, excluir uma linha e
aprovar; a trilha mostra valor de origem, valor corrigido, autor e motivo.
Outro usuário tenta aprovar o mesmo lote ao mesmo tempo e recebe 409.

**Acceptance Scenarios**:

1. A tela do lote mostra, por linha: tomador, aluno, turma, competência,
   valor, discriminação montada, os códigos que vão para a DPS, os
   apontamentos e a origem (aba e linha, ou bloco e linhas do texto).
2. O lote mostra totais: linhas, soma dos valores, linhas com bloqueio, com
   aviso e excluídas.
3. Corrigir um campo exige motivo. O valor de origem nunca é apagado, e a
   correção prevalece sobre ele, como no Livro de Conferência **[sistema
   atual: `core/correcoes.py`]**. Correção e evento vão na mesma transação.
4. Excluir uma linha exige motivo e pode ser desfeito enquanto o lote não for
   aprovado.
5. Aprovar exige `nfse.aprovar_emitir`, nenhuma linha com bloqueio, pelo
   menos uma linha ativa, perfil sem pendência e conferência feita com a
   versão atual do perfil. Faltando algo, a resposta diz o quê.
6. Avisos não impedem a aprovação, mas a tela pede que a atendente os
   confirme **[proposta]**.
7. A aprovação grava o usuário da sessão, a data e um hash do conteúdo
   aprovado. Depois dela, o lote não muda.
8. Quem pode aprovar, e se pode ser quem importou, depende de JB-5. A Fase 1
   não impõe separação de funções; a trilha guarda quem importou e quem
   aprovou, para a regra entrar depois sem migração.
9. Duas aprovações simultâneas do mesmo lote: só uma vale; a outra recebe
   409.
10. Descartar um lote exige motivo. O lote descartado continua consultável.

### User Story 7 — Gerar a DPS sem transmitir (P1)

Como JB, quero o XML de cada nota pronto e validado, para que a Fase 2 só
precise assinar e enviar.

**Independent Test**: aprovar um lote fictício e conferir que cada linha
gerou uma DPS que valida no XSD oficial; repetir a geração com as mesmas
entradas e obter o mesmo XML byte a byte; rodar o fluxo inteiro com a rede
bloqueada.

**Acceptance Scenarios**:

1. Uma DPS por linha aprovada e não excluída, gerada na mesma transação da
   aprovação. Se qualquer DPS falhar na validação, a aprovação inteira é
   desfeita e nenhuma DPS fica gravada.
2. O leiaute é o do pacote oficial fixado em R1. Em 15/10/2026, a página
   "Documentação atual" do portal da NFS-e lista os esquemas XSD v1.01 de
   09/02/2026 e o Anexo I (leiaute da DPS) v1.01 de 09/02/2026
   **[confirmado]**.
3. Ambiente: sempre produção restrita na Fase 1 **[proposta]**. Produção é
   Fase 3, com autorização explícita.
4. Série e número são controlados pelo sistema, por perfil, ambiente e série.
   Número nunca se repete nem volta, mesmo quando o lote é descartado.
   Faixas e tamanhos **[R4]**.
5. O identificador da DPS segue a composição do Anexo I **[R1]**.
6. A DPS leva prestador (CNPJ, inscrição municipal, regime), tomador (CPF,
   nome e, conforme JB-2, endereço), serviço (local da prestação, códigos da
   turma, discriminação) e valores (valor do serviço, ISS retido e, conforme
   JB-8, alíquota e tributos). O grupo do IBS/CBS segue R3.
7. O XML sai sem assinatura, em UTF-8.
8. A DPS é gravada sem possibilidade de alteração, com SHA-256, versão do
   leiaute, versão do perfil e versão do gerador.
9. Nenhuma requisição de rede é feita e nenhum certificado é lido.

### User Story 8 — Baixar as DPS e o resumo do lote (P2)

Como atendente, quero baixar o que foi gerado para conferir fora do sistema.

**Independent Test**: baixar o XML de uma DPS, o zip do lote e a
planilha-resumo; reabrir os três; usuário sem permissão recebe 403.

**Acceptance Scenarios**:

1. Saídas: XML de uma DPS, zip com todas as DPS do lote e planilha-resumo
   (`.xlsx`) com uma linha por nota.
2. Texto da planilha neutralizado contra injeção de fórmula; valores em
   formato de moeda **[sistema atual: `core/planilha_segura.py`]**.
3. Falha na geração não entrega arquivo parcial.
4. Exige `nfse.exportar`. O download vai para a trilha, sem dado pessoal.
5. Nomes de arquivo e a planilha-resumo levam a marca "DPS NÃO TRANSMITIDA"
   **[proposta]**, para ninguém confundir prévia com nota emitida.

## Edge Cases

- CPF em célula numérica da planilha, sem o zero inicial.
- Valor `1.250` ou `1,250`: o separador pode ser milhar ou decimal. Vira
  bloqueio para a atendente corrigir.
- Competência digitada como data na planilha (01/11/2026).
- Competência com ano de dois dígitos (`11/26`).
- O mesmo texto colado duas vezes; o mesmo arquivo com outro nome.
- Irmãos com o mesmo CPF de responsável.
- O mesmo aluno duas vezes na mesma competência (mensagem encaminhada duas
  vezes).
- Turma escrita de outro jeito (`Bercario`, `berçário `, `BERÇÁRIO I`).
- Perfil alterado entre a importação e a aprovação.
- Turma retirada do perfil com lote em revisão.
- Lote com todas as linhas excluídas.
- Nome com apóstrofo, acento, emoji, espaço não separável ou caractere
  invisível.
- Discriminação maior que o campo da DPS.
- Dois usuários corrigindo a mesma linha.
- Dois lotes diferentes aprovados ao mesmo tempo com a mesma chave de
  duplicata.
- Lote aprovado e depois descartado: os números não voltam.
- Planilha com macro, vínculo externo ou compressão abusiva.
- Usuário sem permissão chamando a rota direto.

## Requirements

### Integração e autorização

- **FR-001**: A funcionalidade MUST aparecer como oitava ferramenta nativa,
  no mesmo processo, endereço e login.
- **FR-002**: MUST reutilizar autenticação, sessão, permissões e trilha de
  uso.
- **FR-003**: MUST ter permissões distintas para acessar (`aba.nfse`),
  cadastrar perfis (`nfse.perfis`), importar e revisar (`nfse.importar`),
  aprovar e gerar DPS (`nfse.aprovar_emitir`) e baixar (`nfse.exportar`). As
  quatro primeiras vêm do briefing; `nfse.exportar` é **[proposta]**.
- **FR-004**: A autorização MUST ser validada no servidor em cada operação,
  cumulativa com a aba.
- **FR-005**: A identidade de quem registra MUST vir da sessão autenticada.
- **FR-006**: As novas permissões MUST NOT ser concedidas automaticamente a
  usuários existentes; usuário novo recebe só `aba.nfse`.
- **FR-007**: A trilha geral MUST NOT conter CPF nem nomes de alunos e
  responsáveis.

### Perfil de emissão

- **FR-008**: MUST existir um perfil por CNPJ de prestador, com dígito
  verificador conferido.
- **FR-009**: Versões de perfil MUST ser imutáveis; alterar cria versão nova.
- **FR-010**: Decisões que dependem de JB-2, JB-8, R3 e R4 MUST NOT ter valor
  padrão; perfil com decisão vazia MUST bloquear a geração da DPS, listando o
  que falta.
- **FR-011**: A tabela turma → códigos MUST marcar como pendente a turma sem
  código obrigatório.
- **FR-012**: O modelo da discriminação MUST aceitar só campos da lista
  fechada.
- **FR-013**: Na Fase 1, o perfil MUST aceitar só o Emissor Nacional e o
  regime ME/EPP do Simples.

### Importação

- **FR-014**: MUST oferecer a planilha-modelo para download.
- **FR-015**: Planilha MUST ser validada antes de qualquer biblioteca de alto
  nível.
- **FR-016**: Colunas MUST ser reconhecidas pelo rótulo, não pela posição.
- **FR-017**: O texto colado MUST ser lido por rótulos; texto não
  reconhecido MUST aparecer como aviso.
- **FR-018**: Cada valor importado MUST registrar origem (SHA-256), posição
  (aba e célula, ou bloco e linha do texto), rótulo e regra.
- **FR-019**: Arquivos e textos de origem MUST ser guardados sem alteração,
  e a mesma origem para o mesmo perfil MUST NOT criar lote duplicado.
- **FR-020**: Ausência MUST NOT virar zero nem valor padrão.
- **FR-021**: Planilha e texto MUST ter limite de tamanho.

### Conferência

- **FR-022**: MUST aplicar as regras de CPF, valor, competência, turma,
  nomes, endereço, duplicata e tamanho da discriminação, com o catálogo de
  apontamentos de `data-model.md`.
- **FR-023**: Apontamento MUST ter nível aviso ou bloqueio; bloqueio MUST
  impedir a aprovação.
- **FR-024**: Duplicata MUST ser detectada no lote e contra lotes aprovados
  do mesmo perfil, com garantia do banco sob concorrência.
- **FR-025**: Cada conferência MUST ser guardada como rodada; reconferir MUST
  NOT apagar a rodada anterior.

### Revisão e aprovação

- **FR-026**: Correção MUST exigir motivo, preservar o valor de origem e
  gravar o evento na mesma transação.
- **FR-027**: Exclusão de linha MUST exigir motivo e ser reversível antes da
  aprovação.
- **FR-028**: Aprovação MUST exigir as condições do cenário 5 da história 6.
- **FR-029**: Aprovação MUST congelar o lote e registrar usuário, data e hash
  do conteúdo aprovado.
- **FR-030**: Operações concorrentes no mesmo lote MUST ser detectadas
  (revisão otimista) e responder 409, sem perder atualização.
- **FR-031**: Descarte MUST exigir motivo, ser terminal e manter o lote
  consultável.

### DPS

- **FR-032**: MUST gerar uma DPS por linha aprovada, na transação da
  aprovação, tudo ou nada.
- **FR-033**: Cada DPS MUST validar contra o XSD oficial fixado, sem editar
  os arquivos publicados pelo governo.
- **FR-034**: A mesma entrada MUST gerar o mesmo XML byte a byte.
- **FR-035**: A numeração MUST ser única por perfil, ambiente e série,
  garantida pelo banco, e nunca reutilizada.
- **FR-036**: Na Fase 1, o ambiente MUST ser produção restrita.
- **FR-037**: A DPS MUST ser gravada imutável, com SHA-256, versão do
  leiaute, versão do perfil e versão do gerador.
- **FR-038**: A Fase 1 MUST NOT abrir conexão de rede, ler certificado nem
  assinar XML.

### Saídas

- **FR-039**: MUST oferecer XML de uma DPS, zip do lote e planilha-resumo.
- **FR-040**: Texto exportado para Excel MUST ser protegido contra injeção de
  fórmula.
- **FR-041**: Falha de geração MUST NOT produzir arquivo parcial válido.
- **FR-042**: Downloads MUST ser auditados.

### Compatibilidade e dados

- **FR-043**: A ferramenta MUST NOT alterar o comportamento das sete
  existentes.
- **FR-044**: `nfse.db` e `dados_web/nfse/` MUST entrar no backup de
  `dados_web`.
- **FR-045**: Mudanças de schema MUST ser aditivas e idempotentes.
- **FR-046**: Dados reais MUST NOT ir para o Git; fixtures são sintéticas.

## Success Criteria

- **SC-001**: 100% das DPS geradas nos testes validam no XSD oficial fixado.
- **SC-002**: Nenhuma linha com bloqueio vira DPS (um teste por regra).
- **SC-003**: Nenhum valor ausente vira zero (teste por campo).
- **SC-004**: A mesma entrada gera o mesmo XML byte a byte.
- **SC-005**: Nenhum número de DPS se repete no teste de aprovação
  concorrente.
- **SC-006**: Nenhum acesso não autorizado dos testes passa.
- **SC-007**: O fluxo completo roda com a rede bloqueada.
- **SC-008**: A trilha geral não tem CPF nem nome em nenhum teste.
- **SC-009**: No teste de aceite, um lote fictício de 30 notas é importado,
  revisado e aprovado em até 10 minutos de trabalho da atendente, contra
  cerca de 60 minutos no fluxo do vídeo (2 minutos por nota)
  **[proposta; volume real: JB-4]**.
- **SC-010**: Um lote de 500 linhas é importado e conferido em até 5 s no
  servidor **[proposta; revisar com JB-4]**.
- **SC-011**: Toda a suíte existente continua passando.

## Pendências da JB

As dez primeiras são as perguntas da seção 5 do briefing. Nenhuma bloqueia a
implementação da Fase 1; elas bloqueiam o **perfil real** da creche e as
fases seguintes.

| # | Pergunta | Efeito na Fase 1 | Como a Fase 1 fica pronta sem a resposta |
|---|---|---|---|
| JB-1 | Certificado A1 ou A3; a escola autoriza guardar o A1? | Nenhum | A Fase 1 não lê nem guarda certificado |
| JB-2 | Endereço do tomador: o da escola ou o do cadastro da prefeitura? | Campo do perfil; regra de endereço da conferência; grupo de endereço da DPS | Campo sem padrão bloqueia a DPS; testes cobrem "informar" e "omitir" |
| JB-3 | Lista de turmas, quais são infantil e quais fundamental, códigos do fundamental | Tabela de turmas do perfil real | Turma sem código fica pendente e bloqueia as linhas dela |
| JB-4 | Notas por mês, dia do envio, formato das planilhas da escola | Importador do formato da escola; metas SC-009 e SC-010; formato real do texto | Planilha-modelo da JB; parser do texto testado com fixtures sintéticas e ajustado com mensagens reais anonimizadas |
| JB-5 | Quem aprova o lote e por onde a nota volta | Quem recebe `nfse.aprovar_emitir`; separação de funções | Nenhuma separação imposta; a trilha guarda importador e aprovador |
| JB-6 | O plano do Zappy tem API ou webhook? | Nenhum | Entrada automática fora do escopo |
| JB-7 | Cancelamento no Emissor Nacional com tomador pessoa física | Nenhum | Fora do escopo |
| JB-8 | Como informar alíquota e regime de ME/EPP na DPS | Alíquota na DPS, regime de apuração, regime especial, tributos aproximados e, se R3 deixar opcional, IBS/CBS | Campos sem padrão bloqueiam a DPS; testes cobrem cada opção do leiaute |
| JB-9 | Quais outros clientes do Simples entram no primeiro lote | Nenhum na estrutura | Perfil por cliente; nada fixo na creche |
| JB-10 | Acompanhar no Jira (AJB-1, legado) ou no Linear | Nome da branch e do PR | A branch segue o padrão Spec Kit do repositório; o ID entra no PR quando for decidido |

### Perguntas novas que esta spec levantou

| # | Pergunta | Por quê |
|---|---|---|
| JB-11 | Na discriminação da creche, o mês vai em número (`11/2026`) ou por extenso (`NOVEMBRO/2026`)? Os nomes vão em maiúsculas? | O briefing traz o modelo `{MÊS}/{ANO}`, não uma nota preenchida |
| JB-12 | Pode haver duas notas do mesmo aluno na mesma competência (matrícula e mensalidade, por exemplo)? | A regra de duplicata do briefing bloqueia esse caso |
| JB-13 | Por quanto tempo guardar as listas recebidas, que têm nomes de crianças e CPFs dos responsáveis? | A Fase 1 guarda a origem como fonte fiscal, sem prazo de descarte |

## Assumptions

- Uma NFS-e por aluno por competência **[confirmado]**.
- O tomador é o responsável, pessoa física, identificado por CPF
  **[confirmado]**.
- O serviço é prestado e tributado em Salvador **[confirmado]**.
- O leiaute oficial pode mudar. Cada DPS registra a versão usada, e mudança
  de leiaute é versão nova do gerador, com testes.
- Usar a ferramenta em produção com dados reais exige antes o endurecimento
  de segurança (Fase 0 do briefing). A produção atual roda sem cookie
  `Secure`, sem checagem de Origin/Host e sem limite de login (conferido em
  25/09), e a constituição pede essas proteções para exposição fora da rede
  interna.
- As listas trazem dados pessoais, inclusive nomes de crianças. Eles só
  aparecem para quem tem `aba.nfse`, nunca vão para a trilha geral nem para o
  Git.
- A Fase 2 decide se transmite o XML gerado aqui (depois de assinado) ou se
  o gera de novo com outra data de emissão. Por isso a DPS da Fase 1 é tratada
  como prévia, sem efeito fiscal.
