# Evidências de validação

Data: 27/10/2026. Ambiente local isolado, dados sintéticos, SMTP desligado.

| Critério | Verificação | Resultado |
|---|---|---|
| Início fixo e calendário | `test_regras_vencimento.py`: fevereiro comum/bissexto, dezembro/janeiro, dias inexistentes, antecipar/adiar/manter, início posterior ao fim | Aprovado |
| Séries mensais | Núcleo/store: duas e três ocorrências, ordem estrita, identidade estável, intervalo até 30 sem extensão ao dia 31 | Aprovado |
| Ausência de vencimento | Núcleo/store/HTTP: competência, início, classificação, conclusão, filtros e avisos; anual/trimestral respeitam competências aplicáveis | Aprovado |
| Migração 2→3 | `test_tarefas_store.py`: preservação de IDs, eventos, rootpages, FK e integridade; troca transacional do índice e idempotência | Aprovado |
| Geração concorrente | Store e agendador: não duplicar ocorrências, preservar posições existentes e completar novas | Aprovado |
| Histórico e escopo HTTP | `test_web_agenda_periodos.py` e `test_web_tarefas.py`: autenticação/autorização, token de uso único, prévia desatualizada, edição sem reescrever tarefas/eventos | Aprovado |
| Alertas e exportação | `test_alertas_email.py`, `test_relatorio_tarefas.py`: sem atraso/prazo próximo fictício, manter espera/conferência, ocorrência e intervalo no Excel | Aprovado |
| Interface | `test_tarefas_ui.py`, `node --check webui/tarefas.js` e navegador local | Aprovado |
| Regressão completa | 73 scripts `tests/test_*.py`, em processos separados | 71 aprovados; 2 pulados por Firebird ausente; 0 falhas |
| Revisão final | `git diff --check`, inspeção dos contratos, migração, histórico e dados versionados | Aprovado |

Os testes de núcleo, store, classificação, alertas, relatório e interface falharam antes das respectivas implementações. A regressão HTTP nova também foi executada contra o código de `dev`, falhando com `REGRA_INVALIDA` ao tentar cadastrar períodos. A revisão independente encontrou uma conversão de vencimento vazio em `/api/tarefas/avisos`; a regressão HTTP reproduziu o erro 422 antes da correção e passou depois. Os dois scripts HTTP foram repetidos após essa correção. O teste de store foi repetido após permitir periodicidades anuais/trimestrais sem vencimento.

Na conferência visual, foram cadastradas pela interface uma obrigação sintética com três períodos e outra sem vencimento. A prévia exibiu quatro tarefas, início/fim no mês seguinte e os intervalos originais; a confirmação gerou a lista correspondente. A rotina sem prazo foi iniciada e concluída, com histórico e indicação "Sem vencimento", sem afirmar pontualidade. O ajuste de quebra de texto da prévia foi recarregado e verificado em viewport de 1270×714; datas e textos ficaram visíveis. Console sem erros/avisos no fluxo final.

Experimentos adicionais isolados verificaram rollback integral da migração sob falha forçada na criação do índice, idempotência do agendador com as novas regras e ajuste explícito de múltiplos períodos para regra simples preservando eventos anteriores.

## Limites da entrega

- A alteração depende de implantação e migração para schema 3. Não voltar a executar a versão anterior sobre a base migrada; seguir o procedimento de recuperação do ambiente.
- O catálogo real foi preparado fora do Git, inativo e com aplicabilidade pendente. T019 da spec 013 permanece aberta até carga e validação.
- Não houve deploy, ativação de SMTP, alteração de usuários ou carga de dados reais nesta entrega.
- Os dois testes de integração Firebird continuam condicionados à instalação do runtime correspondente.
