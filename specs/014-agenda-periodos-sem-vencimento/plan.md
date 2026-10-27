# Plano

Manter o mesmo processo, banco e arquitetura da spec 013. Escrever regressões vermelhas antes de cada implementação. Usar dados sintéticos e não operar produção.

## Contrato de regras

- `dia_mes_seguinte` passa a aceitar `inicio_dia` opcional (1..31, não maior que `dia`). Ausência mantém a antecedência/data de geração anterior. Presença conflita com `inicio_antecedencia_dias` preenchido: recusar a combinação ambígua.
- Nova regra `periodos_mes_seguinte`: `periodos` é lista ordenada de objetos `{inicio, fim}` com inteiros 1..31, início <= fim, sem sobreposição e sem campos extras. `sem_expediente` é `manter`, `antecipar` ou `adiar`. A ordem deve ser cronológica, não reordenar silenciosamente entradas inválidas.
- Nova regra `sem_vencimento`, sem campos de prazo ou expediente. Vencimento persistido/retornado como string vazia, sem quebrar o `NOT NULL` legado. Nenhum vencimento fictício. Respeita a periodicidade e as competências cadastradas, inclusive anual e trimestral; somente `periodos_mes_seguinte` exige periodicidade mensal.
- Núcleo expõe `calcular_ocorrencias(competencia, regra, feriados=())`: lista de dicionários com `ocorrencia` (1..N), `inicio` (date ou None), `vencimento` (date ou None) e `rotulo` (texto vazio na ocorrência simples; intervalo original nas múltiplas). Regras antigas retornam uma ocorrência. `calcular_vencimento` conserva o contrato antigo e não reduz silenciosamente uma regra de múltiplas ocorrências a uma única data.
- Uma rotina sem vencimento retorna uma ocorrência com início no primeiro dia do mês seguinte, para manter a referência mensal. Nas regras antigas sem início fixo, o store conserva a data de geração/antecedência.
- Para cada período, a limitação dos dias inexistentes ocorre antes do ajuste de expediente; início posterior ao vencimento ajustado é erro explícito. Identidade 1..N não muda quando o prazo cai em feriado.

## Persistência e apresentação

Schema 3 adiciona `tarefa.ocorrencia INTEGER NOT NULL DEFAULT 1` e substitui, na mesma transação de migração, o índice único de três campos por quatro campos. Incluir ocorrência e intervalo em `origem`. A inserção da tarefa e evento continua atômica. Não remover colunas nem reconstruir tabela.

Editar uma regra afeta somente novas gerações. A ocorrência simples histórica equivale à posição 1; posições adicionais são completadas manualmente. Ajuste de vencimento do cliente continua documentado em origem e segue a regra efetiva, sem alteração retroativa. Uma substituição explícita de múltiplos períodos por regra simples mantém as ocorrências antigas; a próxima competência usa a regra substituta. Não apagar posições ou eventos para fazer o histórico caber no novo formato.

Interface usa os contratos JSON acima, identifica ocorrências e mostra "Sem vencimento". Entrada de tarefa avulsa mantém o contrato existente; a nova ausência de prazo vem da regra explícita de obrigação. Exportação e alertas devem tolerar essa ausência sem convertê-la em data ou atraso.
