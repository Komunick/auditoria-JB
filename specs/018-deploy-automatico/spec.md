# Spec 018 — Deploy automático da main

## Pedido e escopo

O proprietário solicitou configurar o deploy automático depois de promover a
spec 017 para main. A instalação existente usa systemd e um único processo web.
Esta entrega acrescenta um verificador periódico de atualização, sem criar
outro servidor web ou substituir o serviço da aplicação.

O repositório é público. A VM consulta main por HTTPS; não precisa receber
conexões de CI nem guardar chave privada da VM no GitHub. Merge em main é o
gatilho de publicação. Dev, branches e PRs abertos não são implantados.

## Critérios de aceite

1. Timer systemd consulta main a cada dois minutos. A execução é serializada;
   HEAD já implantado e saudável é no-op, sem reinício ou novo backup.
2. Executor e configuração pertencem ao root e ficam fora do checkout. Código
   da aplicação, Git e testes não são executados como root. O executor não se
   atualiza automaticamente a partir do Git.
3. Preflight confirma instalação, origem pública esperada, branch main,
   checkout limpo, avanço por fast-forward, espaço e saúde anterior. Requisitos
   alterados exigem manutenção específica antes da atualização automática.
4. Candidato é fixado por SHA e testado fora do checkout em uso, com ambiente
   limpo e dados sintéticos. Falha de teste bloqueia antes de parar a aplicação;
   teste pulado não é contado como aprovado. O mesmo SHA reprovado não repete
   testes; um SHA novo pode ser avaliado. Erro antes de conhecer o alvo é
   reavaliado em ciclo posterior, preservando o serviço em uso.
5. Antes de alterar o código, impedir o cron de reiniciar a aplicação durante
   a manutenção, parar a unit e copiar a pasta inteira de dados, inclusive WAL,
   SHM, origens e sessões, além de código, venv e configuração recuperáveis.
   Segredos ficam em cópia protegida separada. Backups nunca são sobrescritos
   nem apagados automaticamente.
6. Validar integridade e chaves estrangeiras dos seis bancos apenas em cópias
   de trabalho. Ensaiar migração na cópia isolada, sem servidor, agendador ou
   envio de e-mail. Rejeitar symlinks e arquivos especiais na fonte de dados.
7. Atualizar main para o SHA aprovado por fast-forward e iniciar a mesma unit.
   Verificar processo e HTTP, bootstrap ausente e APIs protegidas. Preservar
   dados, chave do cofre, SMTP desligado, loopback e worker único.
8. Verificar integridade pós-inicialização em snapshot consistente separado,
   sem abrir backups originais. Registrar versão, backups e resultado em estado
   privado e journal sanitizado.
9. Em falha depois de iniciar a manutenção, preservar o estado e bloquear novas
   tentativas. Não executar rollback de banco, downgrade de schema, restauração
   ou descarte automático de gravações. A falha e a indisponibilidade devem ser
   explícitas; retomada exige diagnóstico e ação administrativa.
10. Manter reinício diário às 04:45 de Salvador (07:45 UTC), e os demais serviços
    e agendamentos. O mecanismo de manutenção deve impedir corrida com esse
    reinício, inclusive após interrupção do executor.
11. Instalador idempotente, validação antes da ativação, documentação para pausar,
    consultar e recuperar. Mudanças do mecanismo de deploy exigem reinstalação
    explícita, não execução privilegiada de arquivos recém-baixados.
12. Testes sintéticos antes do código, revisão independente e execução real do
    primeiro ciclo na VM. Só declarar ativo após timer, atualização, serviço e
    estado final serem confirmados.

## Limites

Não altera regras fiscais, carteira, catálogo, credenciais ou permissões de
usuários. Não ativa SMTP. Não transforma merge de dev em publicação. Mudança
de dependências ou do mecanismo de deploy requer manutenção específica. Não
implementa exclusão automática de backups nem rollback destrutivo.

O timer é infraestrutura expressamente necessária ao pedido de automação.
Conserva o processo web existente; não usa o ctl.sh da instalação legada.
