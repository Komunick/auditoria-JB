# Data Model: clientes.db

Banco próprio em `dados_web/clientes.db`. Schema aditivo e idempotente
(`CREATE ... IF NOT EXISTS`), `PRAGMA user_version = 1`.

## cliente

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| nome | TEXT | obrigatório, até 160 |
| documento | TEXT NULL | só dígitos, CNPJ (14) ou CPF (11) com DV válido; único quando presente |
| documento_informado | TEXT | como veio, para pendência de documento inválido |
| ie, ie_situacao | TEXT | valor **ou** situação (`nao_tem`, `pendente`, `baixada`, `nao_se_aplica`) |
| im, im_situacao | TEXT | idem |
| iptu, iptu_situacao | TEXT | idem |
| municipio | TEXT | |
| situacao | TEXT | `ativo`, `inativo`, `baixado`, `nao_cliente` |
| observacao | TEXT | |
| pendencias | TEXT | JSON com a lista de pendências abertas (importação) |
| origem | TEXT | JSON: arquivo (hash), linha |
| revision | INTEGER | concorrência otimista |
| criado_em, atualizado_em | TEXT | ISO UTC |

## licenca

Uma linha por cliente e tipo (`tvl`, `alvara`, `alvara_saude`, `publicidade`).
`numero`, `vencimento` (ISO data ou vazio), `situacao` (`definitivo`,
`nao_tem`, `pendente`, `vencido`, `ok`, `renovando`, `data_invalida`),
`texto_original`. Único (cliente_id, tipo).

## segredo

| Campo | Regra |
|---|---|
| id, cliente_id | |
| campo | `sefaz`, `prefeitura`, `codigo_acesso`, `outro` |
| portal, usuario | só para `outro` |
| uid | aleatório, entra no AAD (`cliente_id:campo:uid`) |
| cifra, nonce | BLOB; NULL quando a situação dispensa valor |
| chave_id | impressão da chave que cifrou |
| situacao | `definida`, `pendente`, `aguardando_certificado`, `nao_tem` |
| atualizado_por_login, atualizado_em | |

Único (cliente_id, campo) quando `campo <> 'outro'`.

## acesso_cofre (append-only por trigger)

`usuario_id`, `usuario_login`, `cliente_id`, `segredo_id`, `campo`, `acao`
(`revelar`, `gravar`, `remover`), `resultado` (`ok`, `negado`, `limite`),
`ip`, `criado_em`. Nunca guarda valor.

## certificado

`cliente_id` (NULL quando a coleta não casou), `tipo` (`A1`, `A3`, `outro`),
`titular_nome`, `titular_documento`, `emissor`, `inicio`, `fim` (ISO data),
`serie` (único quando presente), `local_guarda`, `origem` (`manual`,
`arquivo`, `coleta`), `hash_arquivo`, `coletado_em`, `situacao` (`vigente`,
`substituido`, `nao_renovar`), `substituido_por_id`, `renovacao_em_andamento`
(0/1, com autor e data), `observacao`, `revision`.

## alteracao (append-only por trigger)

`entidade`, `entidade_id`, `campo`, `antes`, `depois`, `usuario_id`,
`usuario_login`, `criada_em`. Valores de segredo nunca entram.

## importacao

`tipo` (`planilha`, `coleta`), `hash_arquivo`, `nome_arquivo`,
`usuario_login`, `criada_em`, `contagens` (JSON), `ignoradas` (JSON com as
linhas e o motivo).

## configuracao

Chave/valor. `faixas_vencimento` = JSON `[15, 20, 30]`.
