# Plano

1. Especificar contrato e semântica antes do código.
2. Escrever regressões vermelhas de agregação, filtros, datas e autorização.
3. Extrair predicado SQL compartilhado do store e implementar resumo/fila no
   mesmo snapshot. Expor painel e filtros equivalentes em lista/exportação.
4. Escrever verificações de interação e implementar Central, navegação contextual,
   filtros rápidos e etapas de importação sem alterar suas mutações.
5. Executar testes afetados, suíte completa e conferência visual local com dados
   sintéticos. Revisar segurança/escopo e registrar evidência antes do PR para dev.

Branch: `codex/016-central-operacional`, criado de `origin/dev` em 7207040.
Spec 015/PR 16 permanece separada, sem dependência desta entrega.

## Arquitetura

- `ferramentas/tarefas_store.py`: seleção parametrizada compartilhada, agregação
  SQL e ordenação/paginação; evitar materializar o universo por `_tarefa_dict`.
- `web/rotas_tarefas.py`: escopo existente e DTO, captura única de data, nomes de
  responsáveis, contrato HTTP. Nada de regra de autorização apenas no navegador.
- `webui/inicio.js`, `tarefas.js`: leitura e interação, estados de consulta e
  reaproveitamento de detalhe/exportação. Textos externos entram por textContent.
- `webui/index.html`, `app.js`, `estilo.css`: navegação em grupos, acesso e visual
  responsivo com tokens JB existentes; sem CDN ou etapa de build.

## Verificação

Testes de totais acima de uma página, todos os estados, prazo ausente, fronteiras
de datas, conferência, substituição, acesso individual/gestor/global/anônimo,
filtro por cliente/competência/responsável/texto, fila e exportação equivalentes.
UI: navegação preservando filtros, abrir detalhe, atraso de resposta, erro, vazio,
permissões, importação só concluída após confirmação e dados como texto.
Smoke visual: desktop e tela estreita, temas claro/escuro, usuário comum e admin.
