# Auto-deploy da main na arm07

O timer consulta o repositório público por HTTPS. Um merge em `main` pode
publicar a aplicação depois das verificações do executor. Branches de trabalho,
PRs e `dev` não são publicados. Não há webhook, porta adicional, segredo GitHub
ou chave SSH de CI.

Este mecanismo atende à instalação systemd existente na **arm07**. Não usar
`devops/ctl.sh` nessa VM. O serviço web continua com usuário `ubuntu`, um único
processo, diretório `/home/ubuntu/komunick/repos/auditoria-jb`, Python
`.venv/bin/python`, uvicorn em `127.0.0.1:8600` e dados em
`/home/ubuntu/komunick/data/auditoria-jb`. A instalação não altera SMTP, cofre,
catálogo, regras fiscais ou os outros serviços.

## Arquivos e privilégios

| Item | Local / modo |
|---|---|
| Executor instalado | `/usr/local/lib/auditoria-jb-autodeploy/runner.py`, root, `0755` |
| Configuração | `/etc/auditoria-jb/autodeploy.json`, root, `0600` |
| Estado e lock | `/var/lib/auditoria-jb-autodeploy/`, root, `0700`; `state.json`, `runner.lock`, `hold` |
| Backups novos | `/var/backups/auditoria-jb-autodeploy/`, root, `0700` |
| Cópias separadas de segredos | `/etc/auditoria-jb/autodeploy-backups/`, root, `0700` |
| Área isolada de testes | `/var/lib/auditoria-jb-check/`, root, `0711`; filhos `0700` do usuário de testes |
| Unidades | `/etc/systemd/system/auditoria-jb-autodeploy.service` e `.timer` |
| Proteção da aplicação | `/etc/systemd/system/auditoria-jb.service.d/90-autodeploy-hold.conf` |

O instalador cria `auditoria-jb-check` como conta de sistema, senha bloqueada,
sem shell interativo, sem grupos suplementares e sem diretório pessoal. Conta
preexistente incompatível é recusada. O candidato roda nessa identidade em uma
unit transitória isolada, sem rede ou capacidades, com `NoNewPrivileges`,
`ProtectSystem=strict`, `ProtectProc=invisible` e escrita somente em sua área de
trabalho. Os limites por execução isolada são `MemoryMax=2G`, `TasksMax=128` e
`CPUQuota=150%`. Dados e segredos de produção ficam inacessíveis aos testes. Git e
código da aplicação não são executados como root.

Executor, configuração e seus ancestrais precisam estar sob controle do root:
symlinks e diretórios graváveis por outros usuários são recusados. Backups
antigos em `/home/ubuntu/komunick/backups` permanecem intactos. Os backups novos
ficam fora de `/home/ubuntu`, cujo proprietário poderia substituir diretórios.

## Preparar a instalação

1. Revisar e aprovar um **SHA exato** e o pacote `devops/autodeploy` desse SHA.
   Obter seu OID de árvore, sem root, com `git rev-parse
   SHA_APROVADO:devops/autodeploy`. O OID fixa conteúdo, nomes e modos do mecanismo
   de deploy; não usar `main` móvel como aprovação.
2. Produzir o pacote com `git archive` desse SHA, transferir e conferir sua
   integridade, e extrair uma cópia revisada em staging privado do root. Não
   executar instalador diretamente do checkout gravável por `ubuntu`, nem por
   `curl | sh`. Preservar os modos do arquivo Git: usar `bash install.sh`, sem
   aplicar `chmod` aos arquivos do pacote. Não adicionar arquivos à pasta.
3. Conferir os arquivos adicionais que precisam acompanhar o backup, como a
   configuração do proxy e os agendamentos existentes. As units e os drop-ins
   efetivos da aplicação são descobertos automaticamente. Arquivos adicionais
   entram com `--configuration-path /caminho/absoluto/revisado`, repetível;
   precisam existir, pertencer ao root e não ser symlinks. Não passar o arquivo
   do cofre nessa opção. O crontab de `ubuntu` em `/var/spool/cron/crontabs` não
   atende à regra de ancestrais exclusivos do root: não passá-lo diretamente.
   O executor coleta `crontab -u ubuntu -l` no preflight, antes de criar o hold
   ou parar o serviço, e guarda essa captura em `crontab-ubuntu.txt`, com modo
   `0600`, na cópia separada de configuração sensível. Não imprime nem altera
   o agendamento. O manifesto registra `crontab_present` e `crontab_captured_at`:
   a mensagem exata de ausência do crontab é aceita como ausência, enquanto
   outros erros impedem o ciclo antes da manutenção. A referência acompanha
   `RECUPERACAO.md`. Arquivos como o Caddyfile podem entrar na lista adicional,
   desde que revisados e sem valores de segredos que pertençam à cópia separada.
4. A partir desse staging aprovado, executar a preparação abaixo. As variáveis
   indicam o pacote e o OID **já conferidos pelo administrador**:

```bash
sudo bash "$PACOTE/install.sh" install --control-plane-digest "$OID_AUTODEPLOY"
```

O comando confere o host, `User`, `WorkingDirectory` e o `ExecStart` exato:

```text
/home/ubuntu/komunick/repos/auditoria-jb/.venv/bin/python -m uvicorn --factory auditoria_fiscal.web.servidor:criar_app --host 127.0.0.1 --port 8600
```

Também confere o OID do pacote em Python stdlib, sem executar Git ou importar
código do checkout como root. Copia os arquivos para os destinos protegidos e
faz `daemon-reload`. **Não inicia a aplicação, não executa o runner e não
habilita o timer.** A unit, seus drop-ins de cofre/segurança/SMTP e os cron jobs
existentes não são substituídos. Apenas o drop-in de manutenção é acrescentado.

O cofre padrão é `/etc/auditoria-jb/cofre.env`, privado do root. A opção
`--cofre-env` permite indicar outro arquivo absoluto igualmente protegido;
seu conteúdo não é lido pelo instalador nem impresso. Não usar `bash -x`,
`systemctl show` sem seleção de propriedades, nem publicar arquivos de ambiente.

Uma reinstalação exige timer pausado e executor encerrado. O lock recusa
concorrência. Antes de substituir arquivos instalados, suas versões anteriores
são copiadas para uma pasta única, datada, em
`/var/lib/auditoria-jb-autodeploy/install-backups/`. Arquivos idênticos não geram
nova cópia. Nenhum backup é apagado ou sobrescrito automaticamente.

## Configuração

Exemplo sem segredos; o OID deve ser substituído pelo valor aprovado. O instalador
produz os caminhos reais das units e dos drop-ins em `configuration_paths`.

```json
{
  "schema_version": 1,
  "control_plane_digest": "OID_DA_ARVORE_APROVADA_40_OU_64_HEX",
  "repository": "/home/ubuntu/komunick/repos/auditoria-jb",
  "repository_url": "https://github.com/Komunick/auditoria-JB.git",
  "deploy_user": "ubuntu",
  "service": "auditoria-jb.service",
  "venv": "/home/ubuntu/komunick/repos/auditoria-jb/.venv",
  "data_dir": "/home/ubuntu/komunick/data/auditoria-jb",
  "state_dir": "/var/lib/auditoria-jb-autodeploy",
  "backup_dir": "/var/backups/auditoria-jb-autodeploy",
  "secrets_backup_dir": "/etc/auditoria-jb/autodeploy-backups",
  "check_user": "auditoria-jb-check",
  "check_work_dir": "/var/lib/auditoria-jb-check",
  "configuration_paths": [
    "/etc/systemd/system/auditoria-jb.service",
    "/etc/systemd/system/auditoria-jb.service.d/90-autodeploy-hold.conf"
  ],
  "secret_paths": ["/etc/auditoria-jb/cofre.env"],
  "health_url": "http://127.0.0.1:8600",
  "allowed_skips": ["test_fdb_reader.py", "test_web_produtos_fdb.py"],
  "excluded_tests": ["test_ui_smoke.py"],
  "command_timeout": 300,
  "test_timeout": 600,
  "total_test_timeout": 3600,
  "health_timeout": 60
}
```

`allowed_skips` contém apenas `test_fdb_reader.py` e `test_web_produtos_fdb.py`,
pela indisponibilidade conhecida do motor Firebird nessa VM. Esses resultados
ficam registrados como pulados, sem contar como aprovação. Node está disponível;
os testes de interface web não têm exceção. Outra exceção precisa ser específica,
justificada e registrada pelo administrador. Não colocar
comandos, tokens, chaves ou valores de ambiente nesse JSON. Alterações manuais de
configuração exigem cópia prévia e modo `0600`; uma reinstalação produz novamente
a configuração a partir das opções fornecidas, preservando a anterior no backup.

`excluded_tests` contém somente `test_ui_smoke.py`, teste da interface desktop
Qt/PySide6 que não é publicada pelo serviço web. O venv web exclui Qt por desenho;
esse teste não é executado nem tratado como aprovado ou pulado. O resultado o
registra em `not_applicable`, com o motivo desktop/PySide6, separado de `passed`
e `skipped`. A configuração recusa qualquer outro nome nessa lista. Essa
classificação é definida antes da execução e não converte uma falha em sucesso;
os demais testes continuam obrigatórios, respeitadas apenas as duas limitações
Firebird já descritas.

## Conferir e ativar

Para conferir sem parar a aplicação, copiar dados ou avançar o checkout:

```bash
sudo /usr/bin/python3 -I /usr/local/lib/auditoria-jb-autodeploy/runner.py --config /etc/auditoria-jb/autodeploy.json --check
```

Depois, a ativação repete o preflight antes de habilitar o timer:

```bash
sudo bash "$PACOTE/install.sh" enable
sudo systemctl list-timers auditoria-jb-autodeploy.timer --all
sudo systemctl is-active auditoria-jb-autodeploy.timer
```

O timer usa `OnBootSec=2min` e `OnUnitInactiveSec=2min`: novo ciclo dois minutos
após terminar o anterior, sem sobreposição. Em uma VM ligada há mais de dois
minutos, ativá-lo pode iniciar o primeiro ciclo imediatamente. `enable` só deve
ser usado quando esse primeiro ciclo estiver autorizado. A instalação não é
considerada validada apenas porque o timer está ativo: conferir o primeiro ciclo,
o SHA, o estado e a aplicação em funcionamento.

Na primeira instalação, manter o checkout em uso na versão anterior e deixar o
runner realizar o avanço para o candidato aprovado. Um `--once` sem mudança de
SHA só é aceito quando `last_deploy` já registra uma implantação validada daquele
SHA. Avançar o checkout manualmente antes do primeiro ciclo não cria essa prova
e resulta em `unverified_noop_revision`.

## Operação e horários preservados

O executor confirma origem, branch, checkout limpo, fast-forward, dependências,
espaço e saúde; fixa o candidato por SHA. Recebe o `git archive` pelo stdout em
arquivo privado do root, com `core.autocrlf=false`, e
recalcula o OID da árvore Git a partir dos nomes, modos e bytes do tar. Esse OID
precisa corresponder a `SHA^{tree}`; divergência termina em `archive_mismatch`
antes da manutenção. O Git continua rodando como `ubuntu`, sem receber caminho
gravável para o archive. Transformações por `export-ignore` ou `export-subst`
que alterem a árvore exportada são recusadas; links continuam fora do contrato
do extrator. Somente o conteúdo conferido segue para o sandbox de testes.

Depois dos testes e antes de mudar o checkout, cria `hold`, para a aplicação e
faz cópias recuperáveis de dados,
código, venv e configuração. Os seis bancos são verificados em cópias de trabalho,
incluindo integridade e chaves estrangeiras. O ensaio de migração atual abre
`TarefasStore` sobre a cópia de `clientes.db`, sem servidor, agendador ou envio de
e-mail. Migrações em outros stores exigem revisão explícita desse ensaio. Os
backups originais não são abertos para validação.

Os inventários privados conferem a preservação de identificadores existentes e
de registros protegidos contra alteração, incluindo o conteúdo cifrado do cofre.
Uma tabela só é considerada integralmente imutável por gatilho quando este
impede UPDATE sem cláusula `WHEN`; gatilhos condicionais não proíbem todas as
alterações legítimas. `segredo` permanece protegido explicitamente, assim como
as trilhas com gatilho incondicional.
Após o primeiro início, o executor para novamente a aplicação para obter o
snapshot consistente de pós-inicialização, valida essa cópia e inicia o serviço
pela segunda vez. O ciclo só termina com sucesso depois da verificação final de
processo, HTTP, bootstrap ausente e catálogos protegidos.

O drop-in contém `ConditionPathExists=!/var/lib/auditoria-jb-autodeploy/hold`.
Enquanto `hold` existir, nem o reinício diário das **07:45 UTC / 04:45 de
Salvador** inicia a aplicação. A condição impede novos starts; não interrompe
sozinha um processo já ativo. O executor controla a parada e as verificações de
saúde, inclusive a validação consistente após a inicialização.

O backup externo das **03:30 UTC** e a faxina das **04:00 UTC** continuam como
estão. Para evitar corrida com esses trabalhos, o executor adia a implantação
entre **02:30 e 04:30 UTC**, verifica novamente o horário depois dos testes e
limita a manutenção normal a 900 segundos. Em falha, há uma janela adicional de
até 90 segundos para a parada de emergência. O drop-in não bloqueia processos externos
que alterem arquivos; mudar esses agendamentos exige rever essa coordenação.

Para consultar o estado e o diário sanitizado, somente com acesso administrativo:

```bash
sudo cat /var/lib/auditoria-jb-autodeploy/state.json
sudo journalctl -u auditoria-jb-autodeploy.service --since today --no-pager
sudo systemctl is-active auditoria-jb.service
```

O estado inclui etapa, resultado, SHAs e referências de backup; não contém o
cofre. `last_deploy` preserva a última implantação concluída, `last_attempt` a
última tentativa relevante e `last_failure` a causa da falha anterior. Os ciclos
posteriores não apagam esse diagnóstico. Um SHA já validado em `last_deploy`,
com serviço saudável, é no-op, sem parada ou backup novo. Áreas temporárias são
limpas ao encerrar a execução; logs de comandos de checks e no-ops também são
removidos. Logs de implantação/falha e backups permanecem para diagnóstico.

Antes da manutenção, uma falha sem SHA de candidato registrado fica `deferred`
e pode ser reavaliada pelo timer. Uma falha com candidato conhecido fica
`rejected`: esse SHA não repete os testes; uma nova main pode ser avaliada. A
aplicação segue disponível. Falta de espaço, testes reprovados e modificações
locais impedem publicação. O mecanismo não faz `reset --hard`, rebase nem
descarte de alterações locais.

## Pausar, retomar e tratar falhas

Para impedir novos ciclos:

```bash
sudo systemctl disable --now auditoria-jb-autodeploy.timer
sudo systemctl is-active auditoria-jb-autodeploy.service
```

Pausar o timer não cancela um ciclo já iniciado. Aguardar o executor terminar
antes de reinstalar ou fazer manutenção. Interrompê-lo durante a manutenção pode
deixar a aplicação indisponível e a proteção persistente ativa.

Para retomar uma pausa normal, com estado saudável, usar o comando `enable` do
pacote aprovado: ele executa `--check` antes de reativar o timer. `hold` ou estado
`blocked` impedem a retomada automática. O bloqueio persistente se aplica à falha
depois de iniciada a manutenção e à recuperação de uma manutenção interrompida;
ele conserva o marcador e o diagnóstico. Consultar etapa, SHAs, backups e saúde
antes de qualquer intervenção. A rejeição prévia de um candidato não exige
reiniciar o serviço nem remover um marcador de manutenção.

**Não basta apagar `hold` para recuperar uma falha.** O checkout pode ter
avançado e o schema pode ter mudado. Preservar o diagnóstico e os backups;
verificar código, dados e versão em cópias isoladas. Decidir explicitamente se
a recuperação será uma correção adiante ou uma restauração consistente. A
restauração de dados pode descartar gravações posteriores e exige uma decisão
administrativa própria. Depois do reparo aprovado, com o timer ainda parado, o
administrador abre uma janela controlada: retira `hold`, inicia a aplicação e
valida serviço, dados, SHA e proteções. Se falhar, repõe `hold` e para a aplicação.
Somente após validação resolve explicitamente o estado bloqueado, repete
`--check` e reativa o timer por último. Cada backup contém `RECUPERACAO.md` com
as referências necessárias. Não há rollback de banco ou downgrade automático.

## Limites e manutenção do mecanismo

Mudanças de requisitos ou do conteúdo/modos de `devops/autodeploy` bloqueiam o
deploy automático até manutenção explícita. O executor instalado não se troca
pela versão recebida do Git. Para atualizar o mecanismo, pausar, revisar um novo
SHA e OID, preparar novo pacote protegido e repetir `install` e `enable`.

O OID fixa o pacote aprovado; não constitui atestação criptográfica da memória
do processo em execução. A segurança da publicação também depende do controle de
acesso e da revisão dos merges em `main`. O mecanismo requer rede de saída para
o Git público, systemd com os recursos de isolamento usados e espaço para
backups completos. Não cria novos serviços web, não instala dependências
automaticamente e não faz retenção ou limpeza de backups.
