# Data Model: Fase 2 — transmissão

Mesmo `nfse.db` da Fase 1. Schema 2, mudança **aditiva**: tabelas novas, nada
alterado nas antigas. As convenções da spec 006 valem (UTC ISO-8601, snapshot
de identidade, imutável = triggers recusam UPDATE e DELETE).

## `dps_situacao`

Uma linha por DPS que já passou por transmissão. Sem linha = `gerada`.

| Campo | Tipo | Regra |
|---|---|---|
| dps_id | INTEGER PK FK | |
| situacao | TEXT | `gerada`, `enviando`, `autorizada`, `rejeitada`, `incerta` |
| chave_acesso | TEXT NULL | preenchida em `autorizada` |
| desde | TEXT | quando entrou na situação atual |
| tentativas | INTEGER | envios feitos (consultas não contam) |

Trigger: `autorizada` é terminal. Índice único parcial em `chave_acesso`.
`enviando` com `desde` há mais de 10 minutos é lida como `incerta`.

## `transmissao`

Uma linha por tentativa, imutável, gravada junto com a mudança de situação.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| dps_id | INTEGER FK | |
| operacao | TEXT | `envio` ou `consulta` |
| resultado | TEXT | `autorizada`, `rejeitada`, `incerta`, `ja_existia`, `nao_existe`, `certificado_recusado` |
| http_status | INTEGER NULL | NULL = sem resposta |
| chave_acesso | TEXT NULL | |
| erros / alertas | TEXT | JSON da Sefin (código, descrição, complemento) |
| mensagem | TEXT | para quem lê (ex.: "tempo esgotado") |
| xml_assinado | BLOB NULL | exatamente o que foi enviado (só em `envio`) |
| xml_assinado_sha256 | TEXT NULL | |
| algoritmo | TEXT NULL | `sha256` ou `sha1` |
| certificado_cnpj / _titular / _validade / _impressao | TEXT | sem chave nem senha |
| destino | TEXT | host chamado |
| versao_aplicativo / dh_processamento | TEXT NULL | da resposta |
| iniciada_em / concluida_em | TEXT | |
| usuario_id / usuario_login | INTEGER/TEXT | snapshot |

## `nfse`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| dps_id | INTEGER UNIQUE FK | |
| chave_acesso | TEXT UNIQUE | |
| ambiente | INTEGER | `CHECK = 2` nesta fase |
| xml | BLOB | NFS-e como veio (descompactada) |
| sha256 | TEXT | |
| origem | TEXT | `envio` ou `consulta` |
| recebida_em | TEXT | |

Imutável.

## `danfse`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| nfse_id | INTEGER UNIQUE FK | |
| pdf | BLOB | |
| sha256 / recebido_em | TEXT | |

Imutável.

## Eventos novos na trilha de domínio

`transmissao_iniciada`, `dps_autorizada`, `dps_rejeitada`, `dps_incerta`,
`transmissao_interrompida`, `transmissao_concluida` — com IDs, contagens,
chave de acesso e códigos de erro; nunca nome nem CPF.

## Regras que mudam na Fase 1

- `descartar` recusa lote com DPS `autorizada`, `enviando` ou `incerta`
  (`LOTE_COM_NFSE`).
