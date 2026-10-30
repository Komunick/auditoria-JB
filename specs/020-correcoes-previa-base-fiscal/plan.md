# Plano

Branch `codex/020-correcoes-previa-base-fiscal` a partir de `origin/dev@844db6f`.

1. Contrato, checklist e testes RED antes de implementar cada camada.
2. Núcleo puro de leitura das correções e classificação em `core/`.
3. Leitura cadastral dedicada, explicitamente somente leitura, em `ferramentas/`.
4. Rota multipart no processo existente; arquivos temporários privados e limpeza.
5. Interface estática integrada à conferência existente, com proteção de sessão.
6. Testes específicos, regressão integral, revisão independente e navegador local.
7. Documentar evidências e limites. Sem commit/push/merge/deploy nesta rodada.

Sem dependência, processo produtivo, schema ou permissão nova. O núcleo recebe
um snapshot mínimo por injeção e não conhece FastAPI nem SQLite. O store atual
não serve à consulta, pois seu construtor executa migrações.
