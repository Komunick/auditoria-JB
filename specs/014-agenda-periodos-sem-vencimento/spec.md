# Extensão da agenda: períodos, início fixo e rotina sem vencimento

Extensão da spec 013, autorizada em 27/10/2026 a partir das regras operacionais fornecidas pelo escritório. O catálogo real e os contatos permanecem fora deste repositório público. Esta mudança implementa a representação, sem presumir a aplicabilidade de uma obrigação a clientes.

## Requisitos e aceite

1. Uma obrigação mensal pode produzir várias ocorrências na mesma competência. Cada período possui início e fim expressos como dias do mês seguinte à competência; preservar literalmente os intervalos cadastrados, sem estendê-los ao dia 31. Limitar dias inexistentes ao último dia do mês, conforme o comportamento já existente para vencimentos. Antecipar/adiar o fim somente conforme a política cadastrada. Cada ocorrência mantém identidade estável por posição e é apresentada na prévia, lista, detalhe e exportação.
2. Uma regra de dia fixo no mês seguinte pode ter um dia de início fixo independente do vencimento ajustado. O início não muda quando o prazo é antecipado ou adiado. Uma configuração que resulte em início posterior ao fim é recusada explicitamente, sem inventar outra data.
3. Uma obrigação pode gerar tarefa sem vencimento. A competência, autoria, situações, comentários, responsável e conferência continuam existindo. Sem vencimento não significa atraso, prazo próximo ou conclusão fora do prazo. Alertas de espera por cliente e conferência continuam obedecendo às regras existentes. A interface e o Excel mostram "Sem vencimento"; a conclusão não afirma estar dentro ou fora de um prazo inexistente.
4. Geração manual e automática são idempotentes por cliente, obrigação, competência e ocorrência, inclusive sob concorrência. Prévia desatualizada continua recusada. Alterar a regra nunca reescreve as tarefas e eventos já gerados. Uma posição existente é preservada; posições novas podem ser completadas por geração manual com nova prévia.
5. Migração aditiva para schema 3 preserva tarefas antigas como ocorrência 1, dados, IDs, cifras, eventos, triggers e chaves estrangeiras. Não recriar as tabelas de domínio ou apagar registros. Atualizar somente as colunas/índices necessários, de modo transacional e idempotente.
6. Todas as permissões e os limites de escopo da spec 013 permanecem. Nenhum catálogo, contato real ou credencial é incluído em código/testes. Obrigações sem aplicabilidade definida devem permanecer inativas no catálogo preparado, até serem configuradas pelo escritório.

## Fora do escopo

Validação de legislação fiscal, envio real de e-mail, importação de clientes reais, configuração de produção e dedução de quem deve cumprir cada obrigação. T019 da spec 013 só se encerra após carregar e conferir o catálogo na versão adequada.

## Verificações obrigatórias

- Fevereiro comum e bissexto, dezembro/janeiro, dia 31 e política de expediente.
- Início fixo preservado diante de adiantamento/adiamento do vencimento; conflito de intervalo recusado.
- Duas/três ocorrências, repetição e concorrência sem duplicação; migração de base schema 2 com tarefas/eventos existentes.
- Rotina sem vencimento listada, concluída e exportada, sem alerta indevido de atraso; filtros por vencimento excluem tarefas sem data.
- HTTP autorizado/negado, prévia e confirmação, edição de regra preservando histórico, interface e regressão da suíte anterior.
