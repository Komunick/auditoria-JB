# Dados operacionais

Não há migração ou tabela nova. Os metadados existem apenas na memória do processo e em linhas sanitizadas do log.

`app.state.versao_execucao`:

- `sha`: string hexadecimal completa ou null.
- `origem`: `git` ou `indisponivel`.
- `arvore`: `limpa`, `alterada` ou `desconhecida`.
- `iniciado_em`: instante UTC ISO 8601 ou null se o lifespan ainda não iniciou.

Resposta administrativa `/api/estado.operacao`:

- `versao`: cópia de `versao_execucao`.
- `agendador`: cópia do diagnóstico sanitizado do último ciclo, ou `estado=aguardando`.

O diagnóstico agregado do agendador não inclui IDs, nomes, destinatários, mensagens SMTP, SQL, paths ou exceções. O campo legado `ultimo_resultado` permanece compatível com `/api/tarefas/avisos` e catálogo.
