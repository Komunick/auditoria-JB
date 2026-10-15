# Data Model: Emissão de NFS-e — Fase 1

SQLite próprio em `dados_web/nfse.db`, pelo mesmo motivo do `conciliacao.db`
e do `patrimonio.db`: domínio com ciclo de vida, trilha e backup próprios.
Planilhas de origem em `dados_web/nfse/origens/<sha256>.xlsx`.

## Convenções

- IDs inteiros autoincrementais.
- Timestamps UTC ISO-8601; apresentação no fuso local.
- Dinheiro em **centavos `INTEGER`**; `NULL` significa não informado.
- Alíquota em **centésimos de ponto percentual `INTEGER`** (500 = 5,00%).
- Competência em texto `AAAA-MM`.
- Chaves estrangeiras habilitadas em toda conexão; WAL; `busy_timeout`.
- Identidade de usuário é **snapshot** (`*_por_id` + `*_por_login`), sem FK
  entre bancos.
- "Imutável" quer dizer: triggers recusam `UPDATE` e `DELETE`.
- Nos campos de decisão do perfil, `NULL` quer dizer **pendente**. Não há
  `DEFAULT` nesses campos.

## 1. `perfil`

Identidade do cliente prestador. Tudo que pode mudar fica na versão.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| cnpj | TEXT UNIQUE | 14 dígitos, DV conferido |
| criado_em | TEXT | obrigatório |
| criado_por_id / _login | INTEGER/TEXT | snapshot |

## 2. `perfil_versao`

Imutável. Alterar o perfil insere a versão seguinte.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| perfil_id | INTEGER FK | obrigatório |
| versao | INTEGER | 1, 2, 3…; `UNIQUE(perfil_id, versao)` |
| razao_social | TEXT | obrigatório |
| inscricao_municipal | TEXT NULL | como informada |
| informar_im | INTEGER NULL | 1 se a escola tem registro complementar no CNC do município emissor (a IM vai na DPS), 0 se não tem; **pendente: R5** |
| municipio_ibge | TEXT | 7 dígitos; município emissor (Salvador = 2927408) |
| municipio_prestacao_ibge | TEXT | 7 dígitos; local da prestação e da incidência |
| emissor | TEXT | `CHECK = 'nacional'` na Fase 1 |
| op_simp_nac | INTEGER | `CHECK = 3` (ME/EPP) na Fase 1 |
| reg_ap_trib_sn | INTEGER NULL | 1, 2 ou 3 (obrigatório para ME/EPP, E0166); **pendente: JB-8** |
| reg_esp_trib | INTEGER NULL | código do leiaute; tem de ser 0 se `reg_ap_trib_sn = 1` (E0175); **pendente: JB-8** |
| iss_retido | INTEGER | 0/1, obrigatório no cadastro |
| convenio_incidencia_ativo | INTEGER NULL | convênio do município de incidência ativo no Sistema Nacional; **pendente: R5**, exigido só quando muda a regra da alíquota |
| aliquota_centesimos | INTEGER NULL | até 500 (E0595); creche: 500 **[confirmado no portal]**; exigida só quando a regra manda informar `pAliq` |
| tributos_aprox | TEXT NULL | `pTotTribSN` ou `pTotTrib` (R1); **pendente: JB-8** |
| p_tot_trib_sn | INTEGER NULL | centésimos de ponto; exigido com `pTotTribSN` |
| p_tot_trib_fed / _est / _mun | INTEGER NULL | centésimos de ponto; exigidos com `pTotTrib` |
| endereco_tomador | TEXT NULL | `informar` ou `omitir`; **pendente: JB-2** |
| serie_dps | TEXT | obrigatória no cadastro, de 1 a 49999 (faixa de aplicativo próprio, E0010) |
| ambiente | INTEGER | `CHECK = 2` (produção restrita) na Fase 1 |
| modelo_discriminacao | TEXT | obrigatório; só campos de "Modelo da discriminação" |
| motivo | TEXT | por que a versão foi criada |
| criado_em | TEXT | obrigatório |
| criado_por_id / _login | INTEGER/TEXT | snapshot |

`pendencias_do_perfil(versao, turmas)` devolve o que falta, com a origem
(JB-n ou Rn): cada campo marcado como pendente que esteja `NULL`; os
percentuais do modo de tributos escolhido; e, conforme a tabela de alíquota de
`research.md`, o convênio (quando a regra depende dele) e a alíquota (quando a
regra manda informá-la). Perfil com pendência não gera DPS. Turma pendente não
torna o perfil pendente: bloqueia só as linhas dela (`TURMA_PENDENTE`).

`regra_aliquota(versao)` aplica a tabela de `research.md` e devolve
`informar`, `nao_informar` ou `depende_do_convenio`. O perfil não tem campo
"informar alíquota": quem decide é a regra oficial.

## 3. `perfil_turma`

Uma linha por turma, por versão do perfil. Imutável junto da versão.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| perfil_versao_id | INTEGER FK | obrigatório |
| nome | TEXT | como aparece na discriminação |
| nome_normalizado | TEXT | ver "Normalização de nomes e turmas"; `UNIQUE(perfil_versao_id, nome_normalizado)` |
| categoria | TEXT NULL | `infantil` ou `fundamental` |
| c_trib_nac | TEXT NULL | 6 dígitos; berçário, infantil e fundamental: 080101 (R2) |
| c_nbs | TEXT NULL | 9 dígitos; creche: 122011100 (1.2201.11.00) **[confirmado]** |
| c_ind_op | TEXT NULL | indicador de operação IBS/CBS (creche: 030101 **[confirmado]**) |
| c_class_trib | TEXT NULL | classificação tributária IBS/CBS (creche: 200028 **[confirmado]**) |
| ref_cnae | TEXT NULL | referência do Nota Salvador (8511200 / 8513900) |
| ref_item_lista | TEXT NULL | referência do Nota Salvador (00801) |
| ref_ctiss | TEXT NULL | referência do Nota Salvador (0801-0/01) |

A turma é **pendente** quando falta `c_trib_nac` ou `c_nbs`. O NBS é
opcional no leiaute, mas a nota do vídeo levou NBS, e exigi-lo mantém a nota
igual **[proposta]**. `c_ind_op` e `c_class_trib` ficam guardados e não vão
para a DPS na Fase 1 (R3). O código municipal não é enviado (R2). Os campos
`ref_*` nunca vão para a DPS; servem para quem confere contra o Nota Salvador.

Na creche: berçário e infantil têm os códigos do vídeo. O fundamental usa o
mesmo `c_trib_nac` (080101); o NBS dele (o Anexo B tem 1.2201.20.00, ensino
fundamental) é escolha do contador (JB-3).

## 4. `perfil_turma_apelido`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| turma_id | INTEGER FK | obrigatório |
| apelido_normalizado | TEXT | ver "Normalização de nomes e turmas" |

Nome e apelidos são únicos dentro da versão do perfil (checado na criação da
versão). Exemplo: turma `Berçário` com apelidos `bercario i` e `bercario 1`.
Não há busca aproximada: sem nome ou apelido exato depois da normalização, a
turma é desconhecida.

## 5. `origem`

Fonte importada. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| tipo | TEXT | `planilha` ou `texto` |
| sha256 | TEXT UNIQUE | do arquivo ou do texto em UTF-8 |
| nome_arquivo | TEXT NULL | como enviado (só exibição) |
| tamanho_bytes | INTEGER | |
| arquivo_relativo | TEXT NULL | `origens/<sha256>.xlsx` para planilha |
| texto | TEXT NULL | conteúdo colado, sem alteração, para texto |
| importado_em | TEXT | |
| importado_por_id / _login | INTEGER/TEXT | snapshot |

O arquivo é gravado em `origens/` antes do `COMMIT`, com nome pelo hash: se a
transação falhar, sobra no máximo um arquivo idêntico ao que voltará na
próxima tentativa (o mesmo padrão da conciliação).

## 6. `lote`

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| perfil_id | INTEGER FK | obrigatório |
| origem_id | INTEGER FK | obrigatório |
| conferencia_atual_id | INTEGER FK NULL | rodada vigente |
| estado | TEXT | `em_revisao`, `aprovado`, `descartado` |
| revision | INTEGER | concorrência otimista, inicia 1 |
| criado_em / criado_por_id / _login | | snapshot |
| aprovado_em / aprovado_por_id / _login | NULL | preenchidos na aprovação |
| hash_aprovacao | TEXT NULL | SHA-256 do conteúdo aprovado (abaixo) |
| descartado_em / descartado_por_id / _login | NULL | |
| motivo_descarte | TEXT NULL | obrigatório no descarte |

Índice único parcial `(perfil_id, origem_id) WHERE estado <> 'descartado'`:
a mesma origem não abre dois lotes vivos do mesmo perfil, mas pode ser
reimportada depois de um descarte.

Trigger: lote `aprovado` só muda para `descartado`; lote `descartado` não
muda mais.

**Hash de aprovação**: SHA-256 de um JSON canônico (chaves ordenadas, sem
espaços) com o id da rodada, a versão do perfil e, por linha ativa, o id e os
valores normalizados de `conferencia_linha`.

## 7. `linha`

Valores **brutos**, como chegaram. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| lote_id | INTEGER FK | obrigatório |
| ordem | INTEGER | posição no lote; `UNIQUE(lote_id, ordem)` |
| aba | TEXT NULL | planilha |
| linha_planilha | INTEGER NULL | planilha |
| bloco | INTEGER NULL | texto |
| texto_linha_ini / texto_linha_fim | INTEGER NULL | texto |
| responsavel_nome | TEXT NULL | |
| responsavel_cpf | TEXT NULL | bruto (`123.456.789-09`, número da célula…) |
| responsavel_celular | TEXT NULL | |
| responsavel_email | TEXT NULL | |
| endereco_texto | TEXT NULL | texto livre (vindo do texto colado) |
| cep / logradouro / numero / complemento / bairro / municipio / uf / municipio_ibge | TEXT NULL | partes (vindas da planilha) |
| aluno_nome | TEXT NULL | |
| turma | TEXT NULL | bruta, sem resolver |
| competencia | TEXT NULL | bruta |
| valor | TEXT NULL | bruto |
| nao_reconhecido | TEXT NULL | linhas do bloco que não casaram com rótulo |
| proveniencia | TEXT | JSON por campo (abaixo) |

`NULL` = o campo não veio. Texto vazio também vira `NULL` na leitura.

**Proveniência** (exemplo fictício):

```json
{
  "responsavel_cpf": {"celula": "C5", "rotulo": "CPF do responsável",
                       "regra": "planilha.coluna_por_rotulo"},
  "valor": {"celula": "J5", "rotulo": "Valor (R$)",
            "regra": "planilha.coluna_por_rotulo", "tipo_celula": "numero"}
}
```

Para texto: `{"linha_texto": 14, "rotulo": "Valor", "regra":
"texto.rotulo"}`. A origem (SHA-256) vem de `lote.origem_id`.

## 8. `correcao`

Append-only. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| linha_id | INTEGER FK | obrigatório |
| campo | TEXT | um dos campos brutos de `linha` ou `excluida` |
| valor_anterior | TEXT NULL | valor efetivo antes da correção |
| valor_novo | TEXT NULL | `excluida`: `1` exclui, `0` reinclui |
| motivo | TEXT | obrigatório |
| criada_em | TEXT | |
| criada_por_id / _login | INTEGER/TEXT | snapshot |

**Valor efetivo** de um campo = `valor_novo` da última correção desse campo;
sem correção, o valor bruto da linha. Só aceita correção com o lote
`em_revisao`.

## 9. `conferencia`

Uma rodada. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| lote_id | INTEGER FK | obrigatório |
| perfil_versao_id | INTEGER FK | versão usada |
| versao_regras | TEXT | versão de `nfse_conferencia` |
| motivo | TEXT | `importacao`, `correcao` ou `reconferencia` |
| executada_em / executada_por_id / _login | | snapshot |

## 10. `conferencia_linha`

Valores normalizados de cada linha naquela rodada. Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| conferencia_id | INTEGER FK | obrigatório |
| linha_id | INTEGER FK | `UNIQUE(conferencia_id, linha_id)` |
| excluida | INTEGER | 0/1 (valor efetivo) |
| cpf | TEXT NULL | 11 dígitos se válido |
| competencia | TEXT NULL | `AAAA-MM` se válida |
| valor_centavos | INTEGER NULL | se válido |
| turma_id | INTEGER FK NULL | se resolvida |
| chave_duplicata | TEXT NULL | `cpf|aluno_normalizado|competencia`, se os três existem |
| discriminacao | TEXT NULL | montada, se possível |
| situacao | TEXT | `ok`, `aviso`, `bloqueio` ou `excluida` |

## 11. `apontamento`

Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| conferencia_linha_id | INTEGER FK | obrigatório |
| codigo | TEXT | ver "Catálogo de apontamentos" |
| nivel | TEXT | `aviso` ou `bloqueio` |
| campo | TEXT NULL | campo afetado |
| mensagem | TEXT | em português |
| referencia | TEXT NULL | JSON: linha ou lote em conflito, quando houver |

## 12. `chave_aprovada`

Garante pelo banco que a mesma nota não é aprovada duas vezes.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| perfil_id | INTEGER FK | |
| chave | TEXT | `chave_duplicata` |
| lote_id / linha_id | INTEGER FK | |
| reservada_em | TEXT | |
| liberada_em | TEXT NULL | preenchida quando o lote aprovado é descartado |

Índice único parcial `(perfil_id, chave) WHERE liberada_em IS NULL`. Trigger:
o único `UPDATE` aceito é preencher `liberada_em` uma vez; `DELETE` recusado.

## 13. `numeracao_dps`

| Campo | Tipo | Regra |
|---|---|---|
| perfil_id | INTEGER FK | PK composta |
| ambiente | INTEGER | PK composta |
| serie | TEXT | PK composta |
| ultimo_numero | INTEGER | só cresce (trigger) |

## 14. `dps`

Imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| lote_id | INTEGER FK | |
| linha_id | INTEGER FK | `UNIQUE` |
| conferencia_linha_id | INTEGER FK | valores usados |
| perfil_id | INTEGER FK | |
| perfil_versao_id | INTEGER FK | |
| ambiente | INTEGER | 2 na Fase 1 |
| serie | TEXT | |
| numero | INTEGER | `UNIQUE(perfil_id, ambiente, serie, numero)` |
| id_dps | TEXT UNIQUE | identificador do `infDPS` (R1) |
| dh_emi | TEXT | instante da aprovação, com fuso |
| d_compet | TEXT | `AAAA-MM-DD` (R4) |
| versao_leiaute | TEXT | `1.01` |
| versao_gerador | TEXT | constante de `core/nfse_dps.py` |
| xml | BLOB | UTF-8, sem assinatura |
| sha256 | TEXT | do `xml` |
| gerada_em / gerada_por_id / _login | | snapshot (quem aprovou) |

## 15. `evento`

Trilha de domínio. Append-only, imutável.

| Campo | Tipo | Regra |
|---|---|---|
| id | INTEGER PK | |
| tipo | TEXT | `perfil_criado`, `perfil_versionado`, `lote_importado`, `origem_reaproveitada`, `linha_corrigida`, `linha_excluida`, `linha_reincluida`, `lote_reconferido`, `lote_aprovado`, `dps_gerada`, `lote_descartado`, `exportacao` |
| perfil_id / lote_id / linha_id / dps_id | INTEGER NULL | |
| detalhe | TEXT | JSON; pode ter dado pessoal (fica no `nfse.db`) |
| usuario_id / usuario_login | INTEGER/TEXT | snapshot |
| criado_em | TEXT | |

A trilha **geral** (`auditoria_web.db`) recebe só ação, IDs e contagens.

## Estados do lote

```text
em_revisao --corrigir / excluir / reconferir--> em_revisao   (revision + 1)
em_revisao --aprovar (gera DPS)-------------->  aprovado
em_revisao --descartar (motivo)------------->   descartado   (TERMINAL)
aprovado   --descartar (motivo)------------->   descartado   (libera chaves; números não voltam)
```

A Fase 2 acrescenta a transmissão a partir de `aprovado`.

**Condições para aprovar** (todas, dentro da transação): lote `em_revisao`;
`revision` igual à enviada; rodada atual feita com a versão vigente do
perfil; perfil sem pendência; nenhuma linha com `bloqueio`; pelo menos uma
linha não excluída; nenhuma chave já reservada.

## Formatos de entrada

### Planilha-modelo

Aba `Notas`, linha 1 com os rótulos abaixo, dados a partir da linha 2. Aba
`Instruções` só com texto. Os rótulos são comparados depois da normalização.

| Rótulo | Campo | Obrigatória |
|---|---|---|
| Competência (MM/AAAA) | competencia | sim |
| Nome do responsável | responsavel_nome | sim |
| CPF do responsável | responsavel_cpf | sim (coluna formatada como texto) |
| Celular | responsavel_celular | não |
| E-mail | responsavel_email | não |
| Nome do aluno | aluno_nome | sim |
| Turma | turma | sim |
| Valor (R$) | valor | sim |
| CEP | cep | não (JB-2) |
| Logradouro | logradouro | não (JB-2) |
| Número | numero | não (JB-2) |
| Complemento | complemento | não |
| Bairro | bairro | não (JB-2) |
| Município | municipio | não |
| UF | uf | não |
| Código IBGE do município | municipio_ibge | não (JB-2); Salvador = 2927408 |

O código IBGE está na planilha porque a DPS identifica o município pelo
código, não pelo nome (R1), e a Fase 1 não tem a tabela de municípios.

Coluna obrigatória ausente recusa o arquivo. Coluna desconhecida é ignorada e
listada como aviso do lote. Formato da planilha da própria escola: JB-4.

### Texto colado

Rótulos (antes de `:` ou `-`, sem diferenciar caixa e acento):

| Rótulo | Campo |
|---|---|
| Competência | competencia |
| Responsável | responsavel_nome |
| CPF | responsavel_cpf |
| Celular, Telefone, Fone | responsavel_celular |
| E-mail, Email | responsavel_email |
| Endereço | endereco_texto (CEP extraído por `\d{5}-?\d{3}`) |
| Aluno | aluno_nome, e turma se o fim do campo for nome ou apelido de turma do perfil, separado por `-`, `–` ou `/` |
| Turma | turma |
| Valor | valor |

Um bloco novo começa em `Competência` ou `Responsável` quando o bloco atual
já tem esse rótulo, ou depois de uma linha em branco seguida de um desses
rótulos. Linha sem rótulo dentro de um bloco vai para `nao_reconhecido`.
Prefixo de mensagem copiada (data, hora e remetente antes do texto) é
removido quando reconhecido; o formato real é JB-4. Limite: 256 KB
**[proposta]**.

### Competência

Aceitos, sem diferenciar caixa e acento, normalizados para `AAAA-MM`:

- `MM/AAAA` e `M/AAAA` (`11/2026`, `1/2027`);
- `AAAA-MM` (`2026-11`);
- mês por extenso ou abreviado com `/` ou ` de ` (`NOVEMBRO/2026`,
  `nov/2026`, `novembro de 2026`, `março`/`marco`);
- célula de data da planilha → mês e ano da data.

Qualquer outra coisa (`11/26`, `2026`, `novembro`) é `COMPETENCIA_INVALIDA`.

### Valor

Prefixo `R$` e espaços removidos; o resto segue `para_decimal` (extraído para
`core/documentos_br.py`): separador decimal tem de ser inequívoco, fração de
centavo é recusada, fórmula sem valor é ausente. Célula numérica é lida como
número exato.

### CPF

Só dígitos; 11 dígitos com DV conferido (função extraída de
`core/patrimonio.py`). Célula **numérica** com menos de 11 dígitos é
completada com zeros à esquerda e recebe `CPF_COMPLETADO` (aviso). Texto com
menos de 11 dígitos é `CPF_INVALIDO`.

### Normalização de nomes e turmas

`normalizar(texto)`: NFKC, remove caracteres de controle e invisíveis (com
aviso `CARACTERE_REMOVIDO` quando havia), troca espaço não separável por
espaço, junta espaços repetidos e apara. Para **comparar** (turma, chave de
duplicata) também aplica `casefold` e remove acentos. O nome exibido e o que
vai para a DPS mantêm a grafia original normalizada, sem tirar acento.

## Modelo da discriminação

Campos permitidos. A caixa do nome do campo escolhe a caixa do valor: em
maiúsculas devolve o valor em maiúsculas; em minúsculas, como está.

| Campo | Valor | Exemplo fictício |
|---|---|---|
| `{TURMA}` / `{turma}` | nome da turma no perfil | `BERÇÁRIO` / `Berçário` |
| `{ALUNO}` / `{aluno}` | nome do aluno | `PEDRO EXEMPLO` / `Pedro Exemplo` |
| `{RESPONSAVEL}` / `{responsavel}` | nome do responsável | `ANA EXEMPLO` |
| `{MES}` / `{mes}` | mês com dois dígitos | `11` |
| `{MES_EXTENSO}` / `{mes_extenso}` | mês por extenso | `NOVEMBRO` / `novembro` |
| `{ANO}` / `{ano}` | ano com quatro dígitos | `2026` |
| `{COMPETENCIA}` / `{competencia}` | `MM/AAAA` | `11/2026` |

Campo fora da lista recusa o modelo ao salvar. Discriminação montada maior
que o limite do campo da DPS (R1) é `DISCRIMINACAO_LONGA`. Qual variante do
mês a creche usa: JB-11.

## Catálogo de apontamentos

| Código | Nível | Quando |
|---|---|---|
| `CPF_AUSENTE` | bloqueio | CPF não veio |
| `CPF_INVALIDO` | bloqueio | tamanho errado, dígitos repetidos ou DV não confere |
| `CPF_COMPLETADO` | aviso | célula numérica completada com zeros |
| `VALOR_AUSENTE` | bloqueio | valor não veio ou fórmula sem valor |
| `VALOR_INVALIDO` | bloqueio | não é número, ambíguo ou com fração de centavo |
| `VALOR_NAO_POSITIVO` | bloqueio | zero ou negativo |
| `COMPETENCIA_AUSENTE` | bloqueio | não veio |
| `COMPETENCIA_INVALIDA` | bloqueio | fora dos formatos aceitos |
| `COMPETENCIA_DIVERGENTE` | aviso | diferente da competência mais frequente do lote |
| `COMPETENCIA_FUTURA` | bloqueio | primeiro dia da competência depois de hoje: a DPS seria recusada (E0015) |
| `TURMA_AUSENTE` | bloqueio | não veio nem dá para separar do aluno |
| `TURMA_DESCONHECIDA` | bloqueio | não é nome nem apelido de turma do perfil |
| `TURMA_PENDENTE` | bloqueio | turma sem código obrigatório (JB-3) |
| `RESPONSAVEL_AUSENTE` | bloqueio | nome do responsável não veio |
| `ALUNO_AUSENTE` | bloqueio | nome do aluno não veio |
| `ENDERECO_INCOMPLETO` | aviso, ou bloqueio se `endereco_tomador = 'informar'` | falta CEP, logradouro, número, bairro ou código IBGE do município |
| `ENDERECO_NAO_ESTRUTURADO` | bloqueio se `endereco_tomador = 'informar'` | endereço só em texto livre |
| `DUPLICATA_NO_LOTE` | bloqueio | chave repetida no lote (aponta a primeira linha) |
| `DUPLICATA_APROVADA` | bloqueio | chave já reservada por lote aprovado (aponta o lote) |
| `DISCRIMINACAO_LONGA` | bloqueio | passou do limite do campo (R1) |
| `ROTULO_REPETIDO` | bloqueio | mesmo rótulo duas vezes no bloco |
| `TEXTO_NAO_RECONHECIDO` | aviso | linha do bloco sem rótulo |
| `CARACTERE_REMOVIDO` | aviso | caractere de controle ou invisível removido |

Apontamentos do **lote** (não da linha), calculados na hora e devolvidos pela
API, sem tabela própria: `PERFIL_COM_PENDENCIA`, `PERFIL_DESATUALIZADO`
(rodada feita com versão antiga), `LOTE_VAZIO` (todas as linhas excluídas) e
`COLUNA_DESCONHECIDA` (aviso da planilha).

## Da linha para a DPS

Leiaute v1.01 conferido no XSD e no Anexo I (`research.md`). A ordem da
tabela é a ordem dos elementos no XML.

| Campo da DPS | Origem | Regra |
|---|---|---|
| `DPS/@versao` | constante | `1.01` |
| `infDPS/@Id` | perfil + numeração | `DPS` + `cLocEmi` + `2` (CNPJ) + CNPJ + série (5) + número (15) |
| `tpAmb` | constante da Fase 1 | `2` (produção restrita) |
| `dhEmi` | instante da aprovação | `AAAA-MM-DDThh:mm:ss-03:00` |
| `verAplic` | `versao_gerador` | `auditoriaJB-nfse-1` (até 20 caracteres) |
| `serie`, `nDPS` | `numeracao_dps` | série sem zeros à esquerda; número a partir de 1 |
| `dCompet` | competência | primeiro dia do mês **[proposta]**; não pode passar da data de `dhEmi` |
| `tpEmit` | constante | `1` (prestador) |
| `cLocEmi` | `municipio_ibge` | |
| `prest/CNPJ` | perfil | |
| `prest/IM` | `inscricao_municipal` | só com `informar_im = 1` (R5) |
| `prest/regTrib/opSimpNac` | `op_simp_nac` | `3` |
| `prest/regTrib/regApTribSN` | `reg_ap_trib_sn` | JB-8 |
| `prest/regTrib/regEspTrib` | `reg_esp_trib` | JB-8 |
| `toma/CPF`, `toma/xNome` | linha | |
| `toma/end` | linha (`municipio_ibge`, CEP, logradouro, número, complemento, bairro) | só com `endereco_tomador = 'informar'` (JB-2) |
| `serv/locPrest/cLocPrestacao` | `municipio_prestacao_ibge` | |
| `serv/cServ/cTribNac` | turma | |
| `serv/cServ/xDescServ` | discriminação montada | 1 a 2000 caracteres |
| `serv/cServ/cNBS` | turma | |
| `valores/vServPrest/vServ` | `valor_centavos` | ponto decimal, duas casas |
| `valores/trib/tribMun/tribISSQN` | constante da Fase 1 | `1` (operação tributável) **[confirmado: "Tributado em Salvador"]** |
| `valores/trib/tribMun/tpRetISSQN` | `iss_retido` | `1` não retido (creche **[confirmado]**), `2` retido pelo tomador |
| `valores/trib/tribMun/pAliq` | `aliquota_centesimos` | só quando `regra_aliquota` = `informar` |
| `valores/trib/totTrib` | `tributos_aprox` | `pTotTribSN` ou `pTotTrib` com os percentuais do perfil (JB-8) |

Não vão para a DPS na Fase 1: `prest/xNome` e `prest/end` (proibidos quando o
emitente é o prestador), `cTribMun` (R2), o grupo `IBSCBS` (R3), telefone e
e-mail do tomador (ficam na linha para a devolução da nota, Fase 3, JB-5).

## Índices mínimos

- `perfil(cnpj)` unique
- `perfil_versao(perfil_id, versao)` unique
- `perfil_turma(perfil_versao_id, nome_normalizado)` unique
- `origem(sha256)` unique
- `lote(perfil_id, origem_id) WHERE estado <> 'descartado'` unique parcial
- `lote(perfil_id, estado, criado_em)`
- `linha(lote_id, ordem)` unique
- `correcao(linha_id, campo, id)`
- `conferencia(lote_id, id)`
- `conferencia_linha(conferencia_id, linha_id)` unique
- `apontamento(conferencia_linha_id)`
- `chave_aprovada(perfil_id, chave) WHERE liberada_em IS NULL` unique parcial
- `dps(linha_id)` unique; `dps(id_dps)` unique;
  `dps(perfil_id, ambiente, serie, numero)` unique; `dps(lote_id)`
- `evento(lote_id, id)`; `evento(perfil_id, id)`
