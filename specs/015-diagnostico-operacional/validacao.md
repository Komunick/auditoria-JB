# Evidências e limites

Validação local em 28/10/2026, com dados sintéticos e SMTP desligado.

| Critério | Verificação | Resultado |
|---|---|---|
| Identificação de revisão | `test_versao.py`: repositório limpo/alterado, arquivos ignorados, worktree, raiz incorreta, ausência de Git, falhas, timeout e mudança de HEAD | Aprovado |
| Captura única e estabilidade | `test_web_diagnostico.py`: lifespan captura uma vez; requisições e mudança posterior do objeto de origem não alteram a versão anunciada | Aprovado |
| Acesso administrativo | HTTP: `operacao` somente para administrador; usuário comum/anônimo não recebem diagnóstico; avisos de tarefas mantêm formato legado | Aprovado |
| Ciclos e contagens | `test_agendador.py`: ciclo vazio, operações efetivadas, repetição idempotente, duração monotônica e snapshot independente | Aprovado |
| Logs utilizáveis e sanitizados | Configuração real padrão INFO do Uvicorn; nenhuma configuração global/handler repetido; exceções e conteúdo sensível não aparecem | Aprovado |
| Falha e retomada | Abertura, geração, configuração, alertas, fechamento e recuperação no próximo ciclo; não duplicar log nem esconder a primeira falha | Aprovado |
| Fechamento SQLite real | Regressão com `TarefasStore` e conexão que lança `sqlite3.OperationalError`; fechamento estrito preserva o fechamento tolerante legado | Aprovado |
| Smoke com HTTP real | Processo Uvicorn em loopback, dados temporários, zero setores: startup com SHA/árvore alterada, ciclo `ok` com contagens zero; API administrativa consistente e ausência no acesso anônimo | Aprovado |
| Regressão completa | 75 scripts `tests/test_*.py`, em processos separados | 73 aprovados, 2 pulados por Firebird ausente, 0 falhas |
| Verificação final | Inspeção de permissões, dados versionados e `git diff --check` | Aprovado |

Testes vermelhos foram observados antes da implementação do módulo de versão, diagnóstico/log do agendador e integração do lifespan. A revisão independente encontrou que o fechamento herdado do store suprimia erros SQLite; a regressão usando o método real reproduziu o falso sucesso antes da correção. Após adicionar fechamento estrito para o agendador, foram repetidos com sucesso os scripts de agendador, tarefas_store, web_diagnostico, web_agenda_periodos e web_tarefas. A revisão do achado confirmou seu encerramento. A suíte completa foi executada antes desse último ajuste; os demais arquivos de comportamento não mudaram depois.

Não houve mudança visual: a verificação de entrega é via HTTP e logs. O smoke foi executado com a árvore de desenvolvimento alterada, condição anunciada corretamente, e o servidor temporário foi encerrado. Não foram usados dados, credenciais ou serviços de produção.

## Limites operacionais

- O SHA é o checkout observado na inicialização, não uma atestação criptográfica dos módulos em memória.
- O diagnóstico não altera o agendamento e não comprova entrega/leitura de e-mails. Um ciclo concluído pode conter contagens de envios com falha; elas devem ser examinadas.
- Esta implementação não executa deploy nem carrega o catálogo fiscal. Aplicabilidade, carteira e SMTP continuam pendentes.
- Nenhum schema, dependência, serviço, worker ou porta de produção foi acrescentado.
