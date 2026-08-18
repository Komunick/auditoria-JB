# Data Model: Conciliação Fiscal

## Convenções

- IDs inteiros autoincrementais.
- Timestamps UTC ISO-8601 no banco; apresentação no fuso do Auditoria-JB.
- Dinheiro em centavos `INTEGER`; `NULL` significa não informado.
- CNPJ com 14 dígitos; competência em `AAAAMM`.
- Nomes de usuário e IDs são snapshots; não criar FK entre bancos SQLite.
- Chaves estrangeiras habilitadas em toda conexão.

## 1. `lote_importacao`

Representa uma operação de envio e processamento de um ou vários arquivos.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| sessao_id | TEXT | sessão de staging |
| usuario_id | INTEGER | snapshot do usuário |
| usuario_login | TEXT | obrigatório |
| estado | TEXT | `recebido`, `processando`, `concluido`, `interrompido` |
| total_arquivos | INTEGER | >= 0 |
| processados | INTEGER | >= 0 |
| duplicados | INTEGER | >= 0 |
| conflitantes | INTEGER | >= 0 |
| rejeitados | INTEGER | >= 0 |
| criado_em | TEXT | obrigatório |
| iniciado_em | TEXT | opcional |
| concluido_em | TEXT | opcional |

## 2. `fonte_fiscal`

Arquivo XLSX imutável e globalmente deduplicado.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| sha256 | TEXT UNIQUE | 64 hex |
| nome_original | TEXT | texto neutralizado somente na exportação |
| caminho_relativo | TEXT UNIQUE NOT NULL | `conciliacao/origens/<sha>.xlsx` |
| tamanho_bytes | INTEGER | > 0 |
| layout | TEXT | `quadro_50_5` ou `quadro_50_3_dimp` quando reconhecido |
| versao_parser | TEXT | obrigatório |
| resultado | TEXT | constante `processada` |
| mensagem | TEXT | observação não sensível |
| enviada_por_id | INTEGER | snapshot |
| enviada_por_login | TEXT | obrigatório |
| recebida_em | TEXT | obrigatório |

Somente uma fonte validada e com binário durável entra nesta tabela. Tentativas
rejeitadas ficam em `item_lote`, com seu hash e versão do parser, e podem ser
reprocessadas no futuro sem colidir com a deduplicação definitiva.

## 3. `item_lote`

Relaciona cada nome enviado ao lote e ao resultado, inclusive duplicatas.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| lote_id | INTEGER FK | obrigatório |
| fonte_id | INTEGER FK | opcional em falha anterior ao hash |
| nome_recebido | TEXT | obrigatório |
| sha256_tentativa | TEXT | opcional se a leitura falhou antes do hash |
| tamanho_bytes | INTEGER | opcional |
| versao_parser | TEXT | obrigatório |
| codigo_erro | TEXT | opcional |
| ordem | INTEGER | obrigatório |
| resultado | TEXT | `processado`, `duplicado`, `conflitante`, `rejeitado` |
| mensagem | TEXT | obrigatório |
| criado_em | TEXT | obrigatório |

## 4. `conciliacao`

Unidade lógica CNPJ + competência.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| cnpj | TEXT | obrigatório |
| competencia | TEXT | obrigatório |
| razao_social | TEXT | cache da versão vigente para busca/lista |
| versao_vigente_id | INTEGER FK diferida | obrigatório após criação |
| estado | TEXT | `em_revisao`, `aprovada`, `rejeitada` |
| revision | INTEGER | concorrência otimista, inicia 1 |
| criada_em | TEXT | obrigatório |
| atualizada_em | TEXT | obrigatório |

`UNIQUE(cnpj, competencia)`.

## 5. `versao_conciliacao`

Snapshot completo extraído de uma fonte.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| conciliacao_id | INTEGER FK | obrigatório |
| fonte_id | INTEGER FK UNIQUE | uma fonte gera no máximo uma versão |
| numero | INTEGER | sequencial por conciliação |
| estado | TEXT | `vigente`, `candidata`, `substituida`, `descartada` |
| razao_social | TEXT | snapshot extraído desta fonte |
| receita_declarada | INTEGER | obrigatório |
| declarada_com_st | INTEGER | obrigatório |
| declarada_sem_st | INTEGER | obrigatório |
| receita_calculada | INTEGER | obrigatório |
| calculada_com_st | INTEGER | obrigatório |
| calculada_sem_st | INTEGER | obrigatório |
| diferenca_receita | INTEGER | obrigatório |
| diferenca_com_st | INTEGER | obrigatório |
| diferenca_sem_st | INTEGER | obrigatório |
| total_pix | INTEGER NULL | nulo no 50-5 |
| total_nao_pix | INTEGER NULL | nulo no 50-5 |
| aba_origem | TEXT | obrigatório |
| linha_resumo | INTEGER | obrigatório |
| criada_em | TEXT | obrigatório |

`UNIQUE(conciliacao_id, numero)`.

## 6. `movimento_dimp`

Preserva cada linha DIMP, mesmo quando a UI agrega instituições.

| Campo | Tipo |
|---|---|
| id | INTEGER PK |
| versao_id | INTEGER FK |
| instituicao | TEXT |
| linha_origem | INTEGER |
| debito | INTEGER |
| credito | INTEGER |
| transferencia | INTEGER |
| pix | INTEGER |
| voucher | INTEGER |
| outras | INTEGER |
| total_dimp | INTEGER |
| total_nao_pix | INTEGER |

Todos os componentes são centavos e obrigatórios para uma linha existente.

## 7. `fato_extraido`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| versao_id | INTEGER FK | obrigatório |
| metrica | TEXT | obrigatório |
| valor_numerico | INTEGER NULL | centavos |
| valor_texto | TEXT NULL | |
| tipo_origem | TEXT | `celula`, `formula` |
| aba | TEXT NULL | obrigatório para célula |
| celula | TEXT NULL | obrigatório para célula |
| rotulo | TEXT | |
| regra_parser | TEXT | obrigatório |
| formula | TEXT NULL | obrigatório para derivado |
| fatos_origem_json | TEXT | IDs/métricas de origem |

## 8. `excecao_conciliacao`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| conciliacao_id | INTEGER FK | obrigatório |
| versao_id | INTEGER FK | obrigatório |
| codigo | TEXT | obrigatório |
| severidade | TEXT | `aviso`, `bloqueio` |
| mensagem | TEXT | obrigatório |
| estado | TEXT | `aberta`, `resolvida` |
| resolucao | TEXT | obrigatório ao resolver |
| resolvida_por_id/login | INTEGER/TEXT | snapshots |
| criada_em/resolvida_em | TEXT | |

Uma exceção resolvida não é apagada nem reaberta por UPDATE; uma nova detecção
gera novo registro. Se a interface precisar representar reabertura, cria evento
e nova exceção.

## 9. `conflito_importacao`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| conciliacao_id | INTEGER FK | obrigatório |
| versao_vigente_id | INTEGER FK | snapshot ao criar |
| versao_candidata_id | INTEGER FK UNIQUE | obrigatório |
| estado | TEXT | `aberto`, `mantida_vigente`, `promovida_candidata` |
| justificativa | TEXT | obrigatório ao resolver |
| resolvido_por_id/login | INTEGER/TEXT | snapshots |
| criado_em/resolvido_em | TEXT | |

## 10. `revisao_conciliacao`

Evento append-only de decisão.

| Campo | Tipo |
|---|---|
| id | INTEGER PK |
| conciliacao_id | INTEGER FK |
| versao_id | INTEGER FK |
| revision_anterior | INTEGER |
| estado_anterior | TEXT |
| estado_novo | TEXT |
| justificativa | TEXT |
| usuario_id | INTEGER |
| usuario_login | TEXT |
| criada_em | TEXT |

Triggers impedem `UPDATE` e `DELETE`.

## 11. `evento_fiscal`

Evento append-only para importações, duplicidades, conflitos, resolução,
download e exportação.

| Campo | Tipo |
|---|---|
| id | INTEGER PK |
| conciliacao_id | INTEGER FK NULL |
| versao_id | INTEGER FK NULL |
| fonte_id | INTEGER FK NULL |
| acao | TEXT |
| detalhes_json | TEXT |
| usuario_id | INTEGER |
| usuario_login | TEXT |
| criada_em | TEXT |

Triggers impedem `UPDATE` e `DELETE`.

## Imutabilidade SQL

- `fonte_fiscal` validada não aceita `UPDATE` nem `DELETE`.
- Campos financeiros, fonte, CNPJ, competência, razão social e proveniência de
  uma `versao_conciliacao` não aceitam alteração; somente a transição de
  `estado` definida abaixo é permitida pela API transacional.
- Movimentos e fatos não aceitam `UPDATE` nem `DELETE`.
- Revisões e eventos fiscais são integralmente append-only.
- Exceções e conflitos têm somente as transições de resolução tipadas; seus
  snapshots originais não são editáveis.

## Relacionamentos

```text
lote_importacao 1---N item_lote N---0..1 fonte_fiscal
fonte_fiscal    1---0..1 versao_conciliacao
conciliacao     1---N versao_conciliacao
conciliacao     1---1 versao vigente (ponteiro)
versao          1---N movimento_dimp
versao          1---N fato_extraido
versao          1---N excecao_conciliacao
conciliacao     1---N conflito_importacao
conciliacao     1---N revisao_conciliacao
conciliacao     1---N evento_fiscal
```

## Transições

### Conciliação

```text
em_revisao --> aprovada
em_revisao --> rejeitada
aprovada   --> em_revisao  (nova vigente promovida ou decisão explícita)
rejeitada  --> em_revisao
```

`aprovada` exige: versão vigente, zero bloqueio aberto da versão vigente e zero
conflito aberto da conciliação. Bloqueios de versões substituídas/descartadas
permanecem históricos, mas não contaminam o estado corrente.

Uma nova candidata faz conciliação aprovada ou rejeitada voltar imediatamente
a `em_revisao`, incrementa `revision` e grava revisão/evento. Exceções e
movimentos de candidatas não entram nos indicadores correntes até promoção.
Aprovar só é válido a partir de `em_revisao`; para trocar uma decisão anterior,
primeiro ocorre transição explícita de volta a `em_revisao`. Transição inválida
responde 409.

### Versão

```text
primeira fonte: vigente
nova fonte para a chave: candidata
candidata --promover--> vigente
vigente anterior ------> substituida
candidata --manter-----> descartada
```

Pode haver várias candidatas. Cada conflito preserva os IDs da vigente e da
candidata no instante de criação. Uma decisão usa `revision` otimista e compara
novamente com a vigente atual. Se ela mudou, responde 409 para nova análise;
nenhuma candidata antiga é promovida contra uma base diferente silenciosamente.

Toda mutação de revisão, resolução, promoção, chegada de candidata ou retorno a
`em_revisao` incrementa `conciliacao.revision` exatamente uma vez.

## Índices mínimos

- `conciliacao(cnpj, competencia)` unique.
- `conciliacao(estado, competencia)`.
- `fonte_fiscal(sha256)` unique.
- `versao_conciliacao(conciliacao_id, estado)`.
- `excecao_conciliacao(estado, severidade)`.
- `movimento_dimp(versao_id, instituicao)`.
- `evento_fiscal(conciliacao_id, id)`.
- `lote_importacao(usuario_login, criado_em)`.
