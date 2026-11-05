# Plano

Manter a arquitetura atual e aplicar TDD. Implementar `web/versao.py` para identificação operacional, sem acoplar o núcleo fiscal ao Git. A leitura usa subprocesso sem shell, timeout curto e caminhos explícitos. Confirmar que a raiz retornada pelo Git corresponde ao projeto para não identificar um repositório pai por engano. Validar o SHA; não retornar stderr. Consultar HEAD antes e depois da leitura da árvore para detectar troca de checkout durante a captura.

Contrato de `identificar_versao(raiz)`: dicionário com `sha` (hexadecimal completo ou null), `origem` (`git` ou `indisponivel`) e `arvore` (`limpa`, `alterada` ou `desconhecida`). Sem variável manual que possa declarar um SHA diferente do checkout.

O lifespan captura esses metadados antes de iniciar o agendador, acrescenta `iniciado_em` em UTC e registra uma linha `aplicacao_inicio`. `/api/estado` acrescenta `operacao` apenas para administrador; antes de lifespan usa um estado explicitamente indisponível, sem consultar Git na requisição. Os dados são copiados para a resposta.

O agendador mantém `ultimo_resultado` no formato legado (`estado`, `em`, `envios` ou código de falha) e acrescenta propriedade separada `diagnostico`, um snapshot sanitizado do último ciclo. As rotas existentes continuam usando o campo legado. O diagnóstico é exposto somente na operação administrativa.

`diagnostico` contém `estado`, `em`, `competencia`, `duracao_ms`, `setores_ativos`, `geracoes`, `tarefas_criadas`, `envios` (somente as quatro contagens conhecidas, ou null antes do horário), `etapa` e `erro` em falha. Medir duração com relógio monotônico injetável; usar `contagens.criadas` e `len(geracao_ids)`, nunca candidatas como operações efetivadas.

Logger operacional sob `uvicorn.error` para herdar sua configuração padrão INFO sem handlers novos. Uma linha por ciclo a cada 15 minutos é o limite natural existente; não adicionar timer nem supressão que esconda ciclos. Falhas continuam uma linha por tentativa. Validar abertura, geração, configuração, alertas e fechamento; limpar conexões mesmo em erro, sem mascarar a etapa da falha inicial.

`TarefasStore.fechar_estrito()` propaga erro SQLite ao diagnóstico; o `fechar()` tolerante herdado continua preservado para os consumidores anteriores. O agendador usa a operação estrita quando disponível. A regressão usa o método real com conexão que falha, além de stores sintéticos, para não confundir falha simulada de um stub com o comportamento efetivo de produção.
