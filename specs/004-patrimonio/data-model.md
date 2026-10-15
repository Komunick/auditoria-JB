# Data Model: Patrimônio

SQLite próprio em `dados_web/patrimonio.db`, pelo mesmo motivo do
`conciliacao.db`: domínio com ciclo de vida, trilha e backup próprios.

## Convenções

- IDs inteiros autoincrementais.
- Timestamps UTC ISO-8601; apresentação no fuso local.
- Dinheiro em **centavos `INTEGER`**; `NULL` significa não informado.
- Chaves estrangeiras habilitadas em toda conexão.
- Identidade de usuário é **snapshot** (`usuario_id` + `usuario_login`), sem FK
  entre bancos.

## 1. `local`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| nome | TEXT UNIQUE | obrigatório |
| descricao | TEXT | opcional |
| ativo | INTEGER | 1/0 |
| criado_em | TEXT | obrigatório |

## 2. `pessoa`

Colaborador que pode receber um bem.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| nome | TEXT | obrigatório |
| cpf | TEXT UNIQUE NULL | 11 dígitos quando informado |
| setor | TEXT | opcional |
| email | TEXT | opcional |
| ativo | INTEGER | desligado vira `ativo=0`, nunca DELETE |
| criado_em | TEXT | obrigatório |

Desativar pessoa **não** encerra responsabilidades automaticamente — quem tem
bem na mão continua respondendo por ele até a devolução ser registrada.

## 3. `bem`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| etiqueta | TEXT UNIQUE | `JBF-000001` ou `PER-000001`; **imutável** |
| pai_id | INTEGER FK NULL | periférico aponta para o bem pai |
| tipo | TEXT | notebook, monitor, impressora, mobiliário… |
| descricao | TEXT | obrigatório |
| marca | TEXT | opcional |
| modelo | TEXT | opcional |
| numero_serie | TEXT UNIQUE NULL | único quando informado |
| valor_aquisicao | INTEGER NULL | centavos |
| data_aquisicao | TEXT NULL | AAAA-MM-DD |
| nota_fiscal | TEXT | opcional |
| conservacao | TEXT | `novo`, `bom`, `regular`, `ruim` |
| situacao | TEXT | `disponivel`, `em_uso`, `manutencao`, `emprestado`, `baixado` |
| local_id | INTEGER FK NULL | |
| observacao | TEXT | |
| revision | INTEGER | concorrência otimista, inicia 1 |
| criado_em / atualizado_em | TEXT | obrigatórios |

**Etiqueta imutável**: ela é impressa e colada no equipamento. Renumerar
significaria alguém ler a etiqueta física e encontrar outro bem.

**Dois níveis**: `pai_id` só pode apontar para bem com `pai_id IS NULL`.
Garantido por trigger.

## 4. `responsabilidade`

Quem está com o bem. Append-only quanto ao início; a devolução preenche o fim.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| bem_id | INTEGER FK | obrigatório |
| pessoa_id | INTEGER FK | obrigatório |
| iniciada_em | TEXT | obrigatório |
| encerrada_em | TEXT NULL | `NULL` = responsabilidade ativa |
| observacao_inicio / observacao_fim | TEXT | |
| registrada_por_id / _login | INTEGER/TEXT | snapshots |
| encerrada_por_id / _login | INTEGER/TEXT | snapshots |

**Índice parcial único** `(bem_id) WHERE encerrada_em IS NULL`: o banco garante
no máximo um responsável ativo por bem. Sem isso, duas atribuições
simultâneas criariam dois donos e ninguém saberia com quem está o
equipamento.

## 5. `movimentacao`

Trilha append-only de tudo que aconteceu com o bem.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| bem_id | INTEGER FK | obrigatório |
| tipo | TEXT | `aquisicao`, `atribuicao`, `devolucao`, `manutencao`, `retorno_manutencao`, `emprestimo`, `retorno_emprestimo`, `baixa`, `transferencia` |
| situacao_anterior / situacao_nova | TEXT | |
| pessoa_id | INTEGER FK NULL | quando envolve alguém |
| local_id | INTEGER FK NULL | quando envolve lugar |
| observacao | TEXT | obrigatória na baixa |
| usuario_id / usuario_login | INTEGER/TEXT | snapshots |
| criada_em | TEXT | obrigatório |

Triggers impedem `UPDATE` e `DELETE`.

## 6. `inventario`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| estado | TEXT | `aberto`, `fechado` |
| aberto_em / fechado_em | TEXT | |
| aberto_por_login / fechado_por_login | TEXT | snapshots |
| observacao | TEXT | |

**Índice parcial único** `WHERE estado='aberto'`: uma sessão aberta por vez.

## 7. `inventario_item`

Congela o universo do inventário no instante da abertura.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| inventario_id | INTEGER FK | obrigatório |
| bem_id | INTEGER FK | obrigatório |
| situacao_esperada | TEXT | snapshot do momento da abertura |
| local_esperado_id | INTEGER FK NULL | idem |
| resultado | TEXT | `pendente`, `localizado`, `nao_localizado`, `divergente` |
| observacao | TEXT | |
| conferido_em / conferido_por_login | TEXT | |

`UNIQUE(inventario_id, bem_id)`. Bem cadastrado depois da abertura **não**
entra na sessão — o universo é congelado, senão a taxa de localização mudaria
sozinha.

## Transições de situação

```text
disponivel  --atribuicao-->      em_uso
em_uso      --devolucao-->       disponivel
disponivel  --manutencao-->      manutencao
em_uso      --manutencao-->      manutencao
manutencao  --retorno-->         disponivel
em_uso      --emprestimo-->      emprestado
emprestado  --retorno-->         em_uso
qualquer    --baixa-->           baixado   (TERMINAL)
```

`baixado` não sai: nenhuma movimentação nova é aceita, e o bem some das
listagens operacionais por padrão, mas continua consultável com todo o
histórico.

## Índices mínimos

- `bem(etiqueta)` unique
- `bem(situacao, tipo)`
- `bem(pai_id)`
- `bem(numero_serie)` unique parcial (quando não nulo)
- `responsabilidade(bem_id) WHERE encerrada_em IS NULL` unique parcial
- `responsabilidade(pessoa_id, encerrada_em)`
- `movimentacao(bem_id, id)`
- `inventario(estado)` unique parcial para `aberto`
- `inventario_item(inventario_id, resultado)`
