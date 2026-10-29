# Validação — spec 018

## Correções locais após revisão — 28/10/2026

Os resultados operacionais históricos abaixo não validam estas correções na
VM. A rodada local parte de `dev@fd3b88d4f7a1bf31d20f7e56872659a0fad4239d`,
no branch `codex/correcoes-review-017-018`, sem push, merge ou implantação.

| Defeito | RED reproduzido | Correção e regressão sintética |
|---|---|---|
| Conteúdo do archive diferente do SHA | Substituir o tar regular após `git archive` permitia concluir o ciclo | Stdout binário recebido em pasta root; OID reconstruído de nomes, modos e blobs comparado com a árvore Git; tar substituído retorna `archive_mismatch` antes de manutenção/hold/parada |
| Trigger condicional tratado como imutabilidade total | UPDATE permitido por WHEN provocava `immutable_data_changed` | Somente bloqueio de UPDATE sem WHEN marca a tabela; atualização legal passa, alteração de segredo ou trilha incondicional continua recusada |
| Cron lido depois da parada | Backup chamava crontab com hold já criado | Captura no preflight; ausência registrada no manifesto; erro antes da parada; backup consome a captura sem consultar cron novamente |

Os testes usam seis bancos sintéticos, repositórios Git temporários e serviços
simulados. Passaram `test_autodeploy.py` e `test_autodeploy_install.py`;
revisão independente das três correções não identificou bloqueador concreto.
Nenhum instalador/controlador foi executado contra a arm07, nem foram lidos
segredos, crontab ou bancos de produção nesta rodada.

Regressão final local: 78 scripts independentes, 76 aprovados, 2 pulados
(`test_fdb_reader.py` e `test_web_produtos_fdb.py`, Firebird opcional ausente),
0 falhas e nenhum fonte/teste alterado durante a execução. Sintaxe JavaScript
e `git diff --check` aprovados. O OID recalculado do archive real da dev
conferiu com `995fcf119255e01d921d3e2a8b74ab7f608a559a`; o comando archive
desativa conversão automática de finais de linha somente nessa invocação,
sem mudar a configuração persistente do Git.

O pacote do controlador mudou: uma futura publicação exige manutenção e
reinstalação explícita do pacote aprovado. O executor instalado não se atualiza
sozinho. As hipóteses e limitações externas ao escopo da revisão permanecem
inalteradas.

## Validação histórica da primeira implantação

Validação encerrada em 28/10/2026, incluindo o primeiro deploy automático e
um ciclo posterior sem mudanças. Evidências operacionais detalhadas ficam em
área privada; este registro não publica dados de negócio ou segredos.

| Critério | Verificação | Resultado atual |
|---|---|---|
| Instalador antes da implementação | RED por arquivo ausente; testes sintéticos de host, unit, conta, caminhos e configuração | GREEN |
| Pacote de controle aprovado | Digest calculado sem Git privilegiado, comparado com árvore Git de fixture | GREEN |
| Ativação separada | Comandos simulados: install não habilita timer; enable exige check aprovado | GREEN |
| Sintaxe | bash -n e git diff --check | Aprovado |
| Executor antes da implementação | RED por módulo ausente; testes de etapas, falhas e interrupção | GREEN após correções da revisão |
| Isolamento Linux real | Unit transitória com UID sem privilégios, NoNewPrivileges, capabilities vazias, rede privada, home protegido e bind somente leitura do venv | Aprovado |
| Units no sistema real | systemd-analyze verify das units copiadas a diretório temporário, sem ativação | Exit 0; temporários removidos |
| Revisão independente | Limites de privilégio, links/TOCTOU, backups, inventários, prazo e estados de falha | Sem bloqueios conhecidos no código final |
| Regressão local final | 78 scripts executados individualmente; hashes de fontes/testes mantidos durante toda a execução | 76 aprovados, 2 pulados, 0 falhas |
| Privacidade | Revisão dos 14 arquivos novos/alterados, com fixtures e dados sintéticos | Nenhum conteúdo sensível identificado |

Os pulos são `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por ausência do
motor Firebird opcional. A execução final ocorreu após as correções da revisão;
uma execução anterior também passou, mas foi substituída como evidência final
porque o executor e seu teste mudaram durante aquela rodada.

O primeiro ensaio do candidato no sandbox da VM chegou ao teste desktop e
recusou sua execução por ausência de PySide6. Esse pacote é deliberadamente
excluído de `requirements-web.txt`. O serviço produtivo manteve o mesmo PID e
o timer permaneceu desabilitado. Após RED específico, o instalador passou a
configurar somente `test_ui_smoke.py` como `not_applicable` (desktop/PySide6),
separado de aprovação e de pulo. Os testes do runner e instalador foram
reexecutados e passaram após esse ajuste; nenhuma falha web é convertida em
pulo. O smoke desktop continuou coberto pela suíte local completa acima.

## Ensaio completo no Linux

O candidato `0d23882463266afb078f6fe475957238aa38b870` foi testado na VM pelo
executor instalado fora do checkout, usando a conta isolada e suas restrições
reais. Resultado: **75 aprovados, 2 pulados por Firebird, 1 não aplicável
(desktop/PySide6)**. A verificação Node de todos os JavaScripts também passou.
HEAD e PID da aplicação permaneceram iguais durante o ensaio; não houve parada,
backup de produção, migração ou atualização do checkout nessa verificação.

O instalador preparou arquivos root, conta isolada e drop-in de manutenção;
o timer permaneceu desabilitado durante o ensaio. Seu pacote foi transferido
com SHA-256 conferido e validado contra o OID da árvore Git antes da instalação.
Resultados operacionais e logs ficam em área privada da VM.

## Publicação e primeiro ciclo automático

- [PR #20](https://github.com/Komunick/auditoria-JB/pull/20) integrado à dev por
  merge commit `606caaee7ff112592a17465f50591c9d24aacd3c`.
- [PR #21](https://github.com/Komunick/auditoria-JB/pull/21) promoveu a main por
  merge commit `a23d123aaa95d3ae67593a7880fa48a74d0d8f87`.
- Preflight aprovado e timer habilitado às 19:16 UTC. A própria automação
  atualizou o checkout produtivo anterior; não houve fast-forward manual para
  simular sucesso do primeiro ciclo.
- O ciclo executou novamente a suíte em sandbox: 75 aprovados, 2 pulados,
  1 desktop não aplicável, Node aprovado. Backups completos anterior/posterior,
  ensaio da migração e verificações dos seis bancos concluídos.
- Deploy registrado como `success/deployed` às 19:21:03 UTC. Serviço ativo,
  novo processo iniciado às 19:21:01 UTC, checkout limpo no SHA promovido,
  HTTP local saudável e HTTPS `/api/estado` 200 sem necessidade de bootstrap.
- Auditoria independente do resultado conferiu hashes e metadados dos
  manifestos de dados, venv, bundle e configuração, e o manifesto separado de
  segredos/cron. Nenhum banco original de backup foi aberto nessa auditoria.
  Integridade/FK e preservação de identidades/imutáveis já haviam sido
  verificadas pelo executor em cópias de trabalho. `clientes.db` permaneceu
  no schema 3; os outros bancos conservaram suas versões próprias.
- Chave do cofre e cron preservados, SMTP desligado, nenhum processo filho do
  servidor e marcador de manutenção ausente ao final.
- Ciclo seguinte às 19:23:11 UTC: `success/noop`, sem novo backup ou reinício,
  preservando último deploy, suas evidências e o PID da aplicação. Timer
  `enabled/active`, executor oneshot sem falha e aguardando a próxima execução.

O SHA é comprovado no checkout e correlacionado ao processo reiniciado pelo
executor. Isso não constitui atestação criptográfica dos módulos Python em
memória. As specs 015/016 não fazem parte desta implantação. Teste autenticado
manual com usuário de produção não foi executado; fluxos foram cobertos pela
suíte sintética. Nenhuma carteira, obrigação, usuário ou credencial foi
cadastrada por esta execução.

As regressões específicas incluem criação exclusiva de baseline em diretório
controlado pelo usuário de teste, transporte sem seguir links, rejeição por SHA,
preservação do diagnóstico original e último deploy, schema esperado obtido do
candidato, preservação de identidades e conteúdo imutável, limites do sandbox e
prazo global da manutenção. A parada de emergência tem orçamento próprio de
90 segundos após falha; o prazo normal de 900 segundos não promete recuperação
nem disponibilidade dentro desse intervalo.

No canário Linux, o UID foi 65534 e NoNewPrivs foi 1. O processo carregou
FastAPI, httpx e openpyxl pelo bind do venv; acesso aos dados produtivos e ao
arquivo do cofre foi negado. A conexão externa retornou ENETUNREACH. Nenhum
conteúdo protegido foi lido. Unit transitória e diretório do canário foram
encerrados e removidos. Esse ensaio precede a validação do runner completo.

O canário identificou que o executável do bind não existe no host quando o
cliente systemd-run resolve o comando. A execução usa `/usr/bin/env` como
entrada e resolve o Python após a montagem no namespace.

## Referências de infraestrutura

- [Ambiente e isolamento de processos no systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).
- [Agendamento de timers no systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).

Comportamento deve ser validado no systemd instalado na VM; documentação da
versão mais recente não substitui o ensaio no ambiente real.
