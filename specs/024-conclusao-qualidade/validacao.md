# Validação — 05/11/2026

Base: `origin/dev` em `dc27ba382dbda3ca8e68ee045342709daa7a507e`.
Branch local: `codex/conclusao-pdf-qualidade`. O conjunto incorpora a correção do
semáforo proposta no PR #37, mantendo a quebra de texto das tabelas já publicada.
Nenhum dado real foi usado nos cenários abaixo.

## Cobertura do PDF

Referência: solicitação de TI de 27/10/2026, seis páginas, dez itens.

| Item | Cobertura e evidência | Estado |
|---|---|---|
| 1. Atividades por setor | Rotinas de Fiscal, Contábil, Departamento Pessoal, Legalização e Administrativo; agenda existente e cenário fictício nos cinco setores | Implementado; carteira real depende da JB |
| 2. Ocorrências | Oito tipos, campos, criticidade, responsável, prazo, situação e histórico; nove ocorrências sintéticas | Implementado e testado |
| 3. Tarefas e prazos | Recorrência, distribuição, consulta por setor, execução, autorização, conferência, vencimento e histórico; testes de tarefas/agendador/delegação | Implementado e testado |
| 4. Indicadores | Prazos, execuções, pendências, erros, reclamações, resolução, setores e não conformidades; acrescentado o total identificado | Implementado; total 2 = 1 aberta + 1 resolvida no exemplo |
| 5. Planos | Causa, ação corretiva/preventiva, responsável, prazo, evidências, transições e validação; fluxo executado pelo navegador local | Implementado e testado; armazenamento produtivo ainda não ativado |
| 6. Alertas | Sete categorias calculadas sobre registros autorizados e filtrados; testes de indicadores e HTTP | Alertas internos implementados; SMTP desligado |
| 7. Painel | Semáforo consistente entre painel/lista/detalhe, filtros, operação, risco, acompanhamento, progresso, horas e custo | Implementado e testado |
| 8. Relatórios | Excel/PDF usam o mesmo conjunto autorizado; filtros diário/semanal/mensal/personalizado | Exportações e recortes testados |
| 9. Acesso e histórico | Escopo por vínculo/setor, custos restritos, autoria e histórico preservados; anônimo e usuário externo bloqueados nos anexos | Implementado e testado; não foram concedidas permissões produtivas |
| 10. Integração e implantação | Reutilização de cadastros; roteiro de implantação, testes, recuperação e treinamento da spec 022 atualizado pela 024 | Proposta documentada; treinamento e piloto reais ainda não realizados |

## Testes automatizados

Suíte local completa: **111 scripts; 109 aprovados, 2 ignorados, 0 falhas**.
Ignorados: `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por ausência do motor
Firebird embedded. Fontes, testes e UI mantiveram os mesmos hashes durante a
execução. Os testes rodaram com configuração isolada e dados temporários.

O KPI e o armazenamento privado tiveram casos que falharam antes da implementação
e passaram depois. Cobertura adicional inclui quota exata, falta de espaço,
limite de objetos, arquivos inesperados, links, concorrência em threads e em
dois processos reais, cópia/restauração e compatibilidade com S3 falso e modo local.

Na camada HTTP: upload/download privado, erro 503 sem novo vínculo quando falta
quota, 401 para anônimo, 403 fora do escopo, revogação durante upload e
compensação. As validações de conteúdo e integridade permanecem ativas.

Ensaio Linux na arm07: somente fontes e arquivos sintéticos em diretório
temporário 0700; variáveis da aplicação removidas do ambiente do teste; sem
restart, deploy, abertura dos bancos produtivos ou mudança de configuração.
Trava POSIX, concorrência entre processos e cópia/restauração pelo `copy_tree`
real do autodeploy passaram. A área temporária foi removida ao encerrar.

## Navegador e documentos

Preview em `http://127.0.0.1:8631/`, isolado, com dados fictícios, SMTP/agendador
desligados e rede externa bloqueada pelo launcher de desenvolvimento.

- Painel mensal de novembro/2026: 2 não conformidades identificadas, 1 aberta,
  1 resolvida; 90 minutos a R$ 120/h resultaram em R$ 180,00.
- Plano corretivo: evidência EML anexada; transições para em andamento,
  aguardando validação e validado; autoria, comentários e datas no histórico.
- Download da evidência idêntico ao upload. SHA-256:
  `db779d2700a5500dee44cf7056e73f3192aba3db64f30e58335a7bfd38440cd0`.
- Excel mensal com nove abas e o novo KPI; PDF mensal com nove páginas,
  renderizado e inspecionado, sem cortes ou sobreposições. Mantida a limitação
  já documentada das fontes core para caracteres fora de Latin-1.
- Diário em 05/11/2026, semanal de 02 a 08/11/2026 e mensal de 01 a 30/11/2026
  conferidos pela interface. PDF diário e Excel semanal também baixados.
- Rotinas dos cinco setores visíveis. Testes em viewports de 390 e 1.280 pixels
  sem transbordamento horizontal do documento; override removido ao concluir.
- Nenhum erro ou aviso no console capturado durante essa validação.

As evidências locais, manifesto, resumo da suíte, logs, renders e screenshot
ficam fora do Git em `tmp/conclusao-pdf-20261105` no workspace de trabalho.

## O que ainda exige ação operacional

Esta validação não declara publicação em produção. Ainda é necessário integrar
o código pelo fluxo de PRs e conferir o deploy, habilitar o armazenamento privado
com inventário de configuração/backup e validar a disponibilidade autenticada.
Não inserir registros fictícios em produção para isso.

SMTP depende de autenticação privada da conta e adequação do contrato do executor,
conforme [operacao.md](operacao.md). Matriz de pessoas/acessos, catálogo e carteiras
reais, retenção externa, participantes do treinamento e piloto são decisões da JB.
O software e os testes não substituem essas decisões nem comprovam que ocorreram.

## Preparação do PR para dev — 05/11/2026

Commit, push e abertura de PR autorizados pelo responsável, sem merge, deploy ou
alterações no Linear. A base remota de dev foi atualizada e permanece em
`dc27ba382dbda3ca8e68ee045342709daa7a507e`. Os 242 arquivos Python, JavaScript e
CSS conferem com o manifesto da suíte aprovada; não houve mudança funcional
posterior que exigisse repetir os testes. `git diff --check` aprovado.

Este conjunto incorpora a correção ainda aberta no PR #37. A sobreposição é
registrada no novo PR para orientar a integração; o PR #37 não foi fechado nem
alterado nesta preparação. Dados da demonstração, downloads, configuração do
remetente e evidências locais continuam fora do Git.

## Correção do teste no sandbox do deploy — 05/11/2026

A promoção #43 foi integrada, mas o candidato `2a671617aea56ad2c95bc0c932d5736f644707e7`
foi recusado em `tests` com `sandbox_failed`, antes de iniciar manutenção.
O serviço continuou na versão anterior, sem hold. A causa foi o ensaio de
`copy_tree`: seu acesso seguro abre cada ancestral com `O_RDONLY/O_DIRECTORY`,
enquanto o `TMPDIR` do sandbox passa por um diretório 0711 do root, atravessável
mas não legível pela conta restrita de testes.

O teste agora usa `/tmp` em POSIX, que a unit já isola com `PrivateTmp=yes`,
mantendo o comportamento padrão no Windows. A pasta criada permanece exclusiva
e temporária. Nenhuma regra da aplicação, permissão de diretório, verificação
do backup, configuração do executor ou exceção de teste foi alterada.

Ensaio RED/GREEN na arm07 com o `sandbox_command` do executor instalado, a mesma
conta restrita e todas as proteções: versão anterior reproduziu
`source_directory_unsafe`; versão corrigida passou em quota, reserva,
concorrência, integridade e restauração. A área sintética foi removida ao fim.
O teste também passou no Windows e `git diff --check` foi aprovado. A nova
promoção deve executar novamente toda a suíte do candidato antes de manutenção.
