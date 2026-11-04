# Validação local — 04/11/2026

Entrega implementada no branch local `codex/recorrencia-distribuicao-tarefas`,
base `101fe047908c7e580bcaff3013e4b6b3526e7e55`. A implementação e a validação
ocorreram sem commit, push, merge, deploy, acesso à produção ou alteração no
Linear. Após esse aceite, o usuário autorizou commit, push e abertura de PR para
a `dev`, em 04/11/2026, mantendo as demais restrições.

## Resultados

| Verificação | Resultado |
| --- | --- |
| Recorrência e carteira | Uma obrigação gerou 3 tarefas em novembro e 3 em dezembro de 2026. Repetir automático/manual não duplicou; avulsa não se repetiu. |
| Mês já processado | Automática vazia preservada; complementação manual exige prévia atual, rejeitando carteira alterada depois da simulação. |
| Consulta por setor | Permissão explícita libera leitura dos setores de vínculo atual; não libera gestão, Clientes, cofre ou Qualidade. |
| Autorização direta | Responsável efetivo autoriza colega ativo elegível do mesmo setor; carteira e titular permanecem iguais. |
| Solicitação e decisão | Pedido fica pendente sem executar; somente responsável efetivo aprova, recusa ou revoga. |
| Execução | Colega autorizado inicia e conclui; `concluida_por` registra o executor real. |
| Revogação e contexto | Ações bloqueadas após revogação, mudança de carteira/vínculo, substituição ou reabertura. Não há concessão herdada no mês seguinte. |
| Concorrência | Revisão obsoleta recusada; início concorrente com revogação serializado; falha de evento reverte a escrita. |
| Migração | Adição idempotente preserva registros e versão superior existente. Revisão independente ensaiou schema anterior e preservou sete tabelas com dados. |
| Integridade da demonstração | `integrity_check=ok`, zero violações de FK, zero envios de e-mail. |

## Testes e revisão

- TDD registrado para persistência, rotas e interface; oito cenários de delegação
  no teste do store, incluindo substituições fora da ordem de cadastro.
- Regressão completa: **110 scripts, 108 aprovados, 2 pulados e nenhuma falha**.
  Os dois pulados são `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por ausência
  do motor embedded em `vendor/firebird25`. O teste de desktop passou em modo
  offscreen. Os arquivos de código/testes permaneceram iguais durante a suíte.
- Após a regressão, um ajuste de redação da UI passou em três testes: delegação,
  ações e Central. O bloco passou a dizer “Registrado por” e não repete o motivo
  quando o texto de concessão direta e decisão é idêntico. Backend inalterado.
- Revisão independente de autorização, identidade, contexto, transação e
  migração concluída sem defeitos bloqueantes restantes.
- Os 17 arquivos previamente alterados do checkout `implementation`, seu branch
  e HEAD foram conferidos e permaneceram intactos.

## Demonstração no navegador

Endereço local: `http://127.0.0.1:8628/`. Guia: `http://127.0.0.1:8628/demo`.
Contas fictícias: `responsavel.demo`, `colega.demo`, `gestor.demo` e
`outrosetor.demo`; a senha de demonstração fica no guia local, fora do repositório.
Dados em diretório próprio; e-mail, S3 e agendador de fundo desabilitados.

Fluxos observados pela interface:

1. Colega consulta a tarefa da Aurora e pede execução; pedido fica pendente.
2. Responsável aprova; tarefa aparece em Minhas tarefas do colega.
3. Colega inicia e conclui; tela conserva Responsável Demo como titular e mostra
   Colega Demo na conclusão e no histórico.
4. Responsável concede diretamente a tarefa da Horizonte.
5. Outra autorização é concedida e revogada; colega mantém consulta pelo setor,
   mas perde os botões de execução.
6. Pessoa de outro setor consulta somente sua tarefa e não vê o setor Fiscal.

O cenário final tem oito tarefas: seis recorrentes, uma avulsa para revogação e
uma de outro setor. A recorrente da Aurora em novembro está concluída. A tarefa
da Horizonte permanece aberta e autorizada para experimentar. Datas de geração
foram simuladas; a obrigação fictícia usa dia 20 do mês seguinte sem ajuste de
expediente, como informado no guia. Não representa validação de calendário fiscal.

## Evidências e limites

Arquivos de apoio ficam fora do Git em `tmp/recorrencia-tarefas-20261104/` no
workspace: `regressao/resumo.json`, logs individuais, `final-ui/resumo.json`,
`delegacao-store-tdd.log`, `delegacao-store-regressao.json` e
`demo/validacao.json`. O preview e seus dados são descartáveis e exclusivamente
locais; esta validação não comprova implantação em produção.

A permissão de consulta compartilhada exige concessão administrativa explícita
em uma futura configuração autorizada. Não houve alteração de usuários reais.
Atividade e permissões de usuário são avaliadas no estado atual; o limite de
remoção/reconcessão entre consultas está descrito em [data-model.md](data-model.md).
