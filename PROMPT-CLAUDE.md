# Prompt pronto para enviar ao Claude

Implemente a feature **003-conciliacao-fiscal** neste repositório, seguindo
integralmente o Spec Kit existente.

Antes de codificar, leia `HANDOFF-CLAUDE.md`, a constituição e todos os artefatos
de `specs/003-conciliacao-fiscal/`. Defina
`$env:SPECIFY_FEATURE_DIRECTORY = "specs/003-conciliacao-fiscal"` no
PowerShell, execute a suíte atual para obter o baseline e rode
`/speckit-analyze`.

Implemente primeiro **somente T001 a T011** de `tasks.md`: preparação, baseline,
segurança de propriedade das sessões/jobs e infraestrutura de caminhos/limite.
Não inicie T012. Escreva os testes previstos nessa faixa antes do código,
execute os testes afetados e pare para relatar:

1. arquivos alterados;
2. testes executados e resultados;
3. decisões tomadas;
4. riscos ou divergências encontradas em relação ao commit-base;
5. próximas tarefas ainda não implementadas.

Não crie servidor Flask, segunda porta, iframe, login próprio ou dependência do
core em FastAPI. Não envie dados fiscais reais ao Git. Não faça push, merge ou
PR sem minha autorização.
