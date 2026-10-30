# Contratos

## Persistência

Tabela `importacao_base_fiscal` no `clientes.db`, com unicidade do par `hash_arquivo` e
`hash_correcoes`, identificação e data UTC, autor, contagens, resultado e
proveniência. Triggers impedem UPDATE/DELETE. Migração aditiva e idempotente,
sem rebaixar `user_version` compartilhado com Tarefas.

Novos clientes usam os campos e eventos existentes. Origem preserva valores,
decisões e células da fonte/revisão. As ocorrências preservadas e ignoradas
também constam no recibo. Tudo é confirmado na mesma transação `BEGIN IMMEDIATE`.

`ferramentas.importacao_base_fiscal` expõe:

- `assinatura_previa(previa)`: SHA-256 canônico dos hashes e das linhas,
  classificação, valores efetivos e snapshot cadastral (incluindo ausências).
  Exclui horário da consulta e nomes dos arquivos.
- `validar_apta(previa)`: recusa conflitos/pendências e lotes sem inclusões.
- `enriquecer_origens(previa, leitura)`: agrega proveniência celular da fonte.
- `importar_base_fiscal(store, previa_base, assinatura_esperada, *, nome_arquivo,
  nome_correcoes, usuario_id, usuario_login, revalidar=None)`: callback de
  autorização depois de adquirir a transação; recibo primeiro para repetição;
  senão consulta, compara, valida e grava atomicamente. A callback é injetada
  pela interface; o importador não importa FastAPI ou estado de requisição.

## HTTP

Todas as ações exigem `aba.clientes`, `clientes.importar` e
`clientes.importar_base_fiscal`, com identidade exclusivamente da sessão.

- `POST /api/clientes/base-fiscal/importacao/preparar`: multipart `arquivo`,
  `correcoes`, `hash_esperado`, `hash_correcoes_esperado`. Devolve
  `{formato: base_fiscal_confirmacao_v1, token, expira_em_minutos: 30, previa}`.
  `previa` preserva o formato 020 e contém a consulta mais recente.
- `POST /api/clientes/base-fiscal/importacao/{token}/confirmar`: multipart
  `arquivo`, `correcoes`, `confirmacao=IMPORTAR EMPRESAS`. Releitura e confirmação
  contra a assinatura guardada no servidor.
- `DELETE /api/clientes/base-fiscal/importacao/{token}`: descarta somente a
  preparação em memória, validando proprietário e sessão.

Resultado: `{formato: base_fiscal_resultado_v1, importacao_id, repetida,
contagens: {incluidas, existentes, ignoradas}, hash_arquivo, hash_correcoes,
criado_em}`. Em repetição, o identificador e resultado permanecem os mesmos.

Erros: 401/403 acesso; 404 token não pertencente à sessão/banco;
410 token ausente, descartado ou expirado;
409 hashes/cadastro divergentes; 413 tamanho; 422 pacote, confirmação ou lote
inapto; 503 banco indisponível. Todos os retornos novos são `no-store`.
Preparação não abre ClientesStore nem cria schema. Confirmação não aceita
payload de linhas/usuário como substituto dos arquivos e da sessão.
