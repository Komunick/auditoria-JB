# Validação da implementação 013

Data: 27/10/2026. Ambiente local Windows, Python 3.11.9. Todos os dados de
testes e de conferência visual são sintéticos. Nenhum acesso à produção.

Estado final dos 72 scripts: **70 aprovados, 2 pulados, nenhuma falha
pendente**. Os pulados são `test_fdb_reader.py` e `test_web_produtos_fdb.py`,
por ausência do motor Firebird. A repetição completa encontrou uma disputa
preexistente entre a leitura e a limpeza do staging da Conciliação Fiscal.
O cenário ganhou regressão determinística, a reserva passou a ser verificada
antes de tocar nos arquivos, e o script completo `test_web_conciliacao.py`
foi repetido e aprovado após a correção. Os demais scripts da rodada final
passaram sem falhas. `git diff --check` e a sintaxe dos JavaScripts passaram.

Os testes de cada módulo foram executados antes de sua implementação e
falharam pela ausência do comportamento. As correções encontradas na revisão
ganharam regressões antes do ajuste, incluindo concorrência e arquivos XLS.

| Critério | Verificação | Resultado |
|---|---|---|
| Competência, vencimento, fevereiro, feriados e Páscoa 2026–2030 | `test_regras_vencimento.py`, datas esperadas independentes | aprovado |
| Aplicabilidade, transições, prazo e cores | `test_tarefas.py`, relógio fixo de Salvador | aprovado |
| Carteiras XLS e XLSX sem executar fórmulas | `test_planilha_carteira.py`, arquivos sintéticos BIFF e OOXML, limites e proveniência | aprovado |
| Migração aditiva sem perda de cadastro, certificado ou cifra | `test_tarefas_store.py`, banco legado schema 1 e reabertura | aprovado |
| Geração sem duplicação, inclusive concorrente | `test_tarefas_store.py` e `test_agendador.py`, conexões SQLite independentes | aprovado |
| Carteira, substituições, ajustes e tarefas sem responsável | `test_tarefas_store.py`, antes/durante/depois e usuários inativos | aprovado |
| Revisão otimista e histórico na mesma transação | falha forçada do evento, rollback externo/savepoint, conflito em lote | aprovado |
| Edição de exceções permanentes | editar ajuste com `revision`; tarefa anterior mantém origem e vencimento | aprovado |
| Resumo único, destinatários efetivos e falhas sem segredo | `test_alertas_email.py`, SMTP local em socket/thread e reservas concorrentes reais | aprovado |
| Retomada no mês e no horário de Salvador | `test_agendador.py`, relógio injetado, reinício e dois ciclos concorrentes | aprovado |
| Acesso por pessoa/setor/data, consulta geral sem poder de execução | `test_web_tarefas.py`, 401/403, titular/substituto/diretoria | aprovado |
| Troca de responsável não atravessa autorização/gravação | teste com segunda conexão/thread e revogação concorrente | aprovado |
| Catálogo não vaza ajustes de setor em que o gestor é apenas membro | regressão HTTP com dois setores | aprovado |
| Migração de e-mail suporta primeiros acessos concorrentes | banco de usuários legado, duas threads e preservação de identidade/hash | aprovado |
| Prévia privada, uso único e geração vinculada ao que foi conferido | testes HTTP e comparação dentro da transação de geração | aprovado |
| Exportação filtrada e texto seguro | `test_relatorio_tarefas.py` e teste HTTP de escopo | aprovado |
| Interface e contratos com backend | `test_tarefas_ui.py`, `node --check`, navegador local | aprovado |

## Conferência no navegador

Instância local temporária, mesma aplicação FastAPI, dados descartáveis e SMTP
desligado. Verificados: login, aba 10, cores, filtros, geração com prévia,
execução/conclusão/conferência, comentários com caracteres HTML exibidos como
texto, redistribuição/dispensa em lote, tarefa sem responsável, importação XLSX
com escolha explícita de cliente, exportação Excel (16 colunas), contatos e
histórico na aba 9, feriados, configuração de alertas e atalhos de perfil.

A criação e a edição de ajustes foram repetidas após reiniciar o backend:
exclusão permanente recebeu fim de validade e depois outra regra de
vencimento, com revisão atualizada. Console do navegador sem erros ou avisos
na conferência final. A revisão corrigiu a atualização da lista após geração
pela tela de configuração e a revisão da ficha após alterações embutidas.

## Limites e pendências

- T019 permanece pendente da P-01: lista de obrigações e regras fornecida pela
  JB. O catálogo inicial fica vazio; não foram inventados prazos fiscais.
- SMTP real e entrega pelo provedor do escritório: **não testados**. O envio
  foi recebido por SMTP local sintético. A reserva prioriza não duplicar;
  queda após a reserva pode deixar resultado indeterminado em `em_envio`.
- Planilhas reais do Fiscal, credenciais, usuários reais e produção: **não
  utilizados**. Python 3.12 da VM: **não testado neste ambiente**.
- A base `dev` do PR estava atrás de `main`. O avanço da base e o merge por
  merge commit continuam a cargo do dono. Não houve push em `dev`/`main`.
