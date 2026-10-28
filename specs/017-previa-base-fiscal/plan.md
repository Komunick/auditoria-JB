# Plano

Branch `codex/017-previa-base-fiscal`, de `dev@7207040`. PR para dev, com evidências.

1. Especificar contrato e revisar requisitos antes de implementar.
2. Parser independente em `core/planilha_empresas.py`, com testes vermelhos de
   layout, fórmulas, documentos, mesclagens, duplicidades e origem.
3. Rota própria em `web/rotas_clientes.py`: autorização, upload temporário,
   resposta sem persistência e trilha sem conteúdo de origem. Testar antes.
4. Bloco independente em Clientes → Importar, sem controles de confirmação;
   busca, filtros, paginação local e origem por linha, dados por textContent.
5. Reutilizar a correção de troca de sessão da spec 016 em `app.js`, para que
   uma sessão seguinte não reaproveite dados do usuário anterior. Alteração
   idêntica àquela correção, sem incorporar o restante do PR 17.
6. Validar testes, leitura privada sem expor conteúdo, navegador com dados
   sintéticos e revisão independente; registrar evidências antes do PR.

Nenhuma chamada a ClientesStore é necessária na prévia. O único evento
persistente é a auditoria geral de uso, com metadados mínimos. Planilha real,
extrações e decisões particulares permanecem fora do Git.
