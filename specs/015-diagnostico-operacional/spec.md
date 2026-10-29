# Diagnóstico da versão e do agendador

Continuação das pendências técnicas da auditoria pós-deploy: o processo não identificava sua revisão e ciclos sem setores não deixavam evidência de execução. A mudança deve permitir conferir esses dois fatos, sem configurar dados de negócio ou alterar a agenda.

## Requisitos e aceite

1. Capturar a revisão Git e o estado da árvore uma única vez por inicialização do app. O valor fica estável durante aquela execução; mudar o checkout depois não deve fazer o processo anunciar outra revisão.
2. Registrar no startup o SHA completo, a origem da identificação e se a árvore estava limpa, alterada ou não verificável. Sem Git/repositório válido ou em caso de timeout, registrar versão indisponível e permitir que a aplicação inicie. Não presumir uma revisão nem usar data como versão.
3. Disponibilizar os mesmos metadados e o instante UTC da inicialização em `/api/estado` somente para administrador autenticado. Preservar os campos existentes e não expor caminhos, branch, remotes, arquivos alterados, ambiente, credenciais ou dados pessoais.
4. Registrar uma linha de sucesso por ciclo do agendador, inclusive com zero setores/tarefas. Com o intervalo atual, são no máximo quatro resumos por hora por processo. Incluir somente horário, competência, duração e contagens agregadas de operações efetivadas.
5. Registrar falha com carimbo, etapa controlada e código fixo, sem texto da exceção, traceback ou conteúdo dos dados. Não anunciar sucesso se fechar a conexão falhar. A próxima execução continua podendo retomar conforme o comportamento atual.
6. Os logs INFO devem aparecer com a configuração padrão do Uvicorn, sem instalar handlers repetidos nem alterar o logger global. Nenhuma nova dependência, serviço, porta, schema, worker, frequência de geração ou regra de envio.
7. Preservar a resposta histórica do agendador nas rotas de tarefas para não ampliar detalhes operacionais globais entregues a colaboradores. O diagnóstico ampliado é reservado ao administrador em `/api/estado`.

## Limites

O SHA identifica o checkout observado na inicialização, não uma atestação criptográfica dos módulos em memória. A árvore alterada ou desconhecida é exibida explicitamente. Logs não comprovam entrega/leitura de e-mails nem substituem auditoria de domínio. Deploy na VM, cadastro real, aplicabilidade por cliente e SMTP não fazem parte da implementação.
