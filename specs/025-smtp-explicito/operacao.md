# Preparação e futura ativação de e-mail

Esta entrega não ativa SMTP. Não há credencial no repositório nem envio real nos
testes. A confirmação do provedor por DNS não comprova acesso à conta.

## Provedor

A documentação oficial da [Yandex 360](https://yandex.com/support/yandex-360/business/mail/en/mail-clients/others),
consultada em 05/11/2026, orienta usar `smtp.yandex.com`, SSL na porta 465,
endereço completo como usuário empresarial e senha de aplicativo do tipo Mail.
É necessário permitir clientes e senhas de aplicativo nas configurações da conta.
O sistema também aceita STARTTLS na porta 587 com validação de certificado,
sem fallback para texto aberto. Preferir SSL/465 na primeira ativação.

## Configuração privada, durante manutenção autorizada

1. Confirmar conta, acesso administrativo e destinatário de teste autorizado.
   Criar senha de aplicativo pelo painel do provedor. Configurá-la diretamente
   na VM por canal privado, sem chat, clipboard compartilhado, Git, argumento
   de comando ou histórico do shell. Nunca publicar conteúdo de `Environment`,
   `/proc/PID/environ` ou arquivo de segredos.
2. Preservar os arquivos e hashes da configuração vigente, incluindo
   `smtp-desligado.conf`, unit, drop-ins dos anexos, cofre, crontab e configuração
   do executor. Guardar credenciais somente em cópia separada root 0700/0600.
3. Preparar `/etc/auditoria-jb/smtp.env`, root 0600, diretório root 0700. Sem
   symlink ou hardlink. Usar seis linhas `NOME=valor`, sem aspas, espaços,
   escapes ou variáveis adicionais. Exemplo **fictício**, não operacional:

   ```text
   AUDITORIA_SMTP_HOST=smtp.yandex.com
   AUDITORIA_SMTP_PORTA=465
   AUDITORIA_SMTP_USUARIO=sender@example.invalid
   AUDITORIA_SMTP_SENHA=SUBSTITUIR_EM_CANAL_PRIVADO
   AUDITORIA_SMTP_REMETENTE=sender@example.invalid
   AUDITORIA_SMTP_TLS=ssl
   ```

   Não reutilizar `cofre.env`, `data/secrets.env` ou diretório de dados. Não pôr
   valores SMTP em drop-ins: eles entram no backup comum. O drop-in deve conter
   apenas `EnvironmentFile=/etc/auditoria-jb/smtp.env`.
4. Antes de ligar o agendador, testar a conta em procedimento isolado, com uma
   única mensagem sintética ao destinatário autorizado. Esse teste é uma etapa
   futura, não executada nesta entrega. Não chamar o envio de resumos usando o
   banco de produção para testar credenciais.
5. Pausar o timer e aguardar o executor encerrar. Instalar o pacote revisado a
   partir de staging root, com OID aprovado e `--smtp-env` explícito. Preservar
   todos os `--configuration-path` necessários. O instalador copia o pacote
   como bytes; não executa código do checkout. O arquivo SMTP deve aparecer
   em `secret_paths`, nunca em `configuration_paths`. A instalação não inicia
   a aplicação ou o timer e não envia e-mails.
6. Revisar `smtp-desligado.conf`: um `UnsetEnvironment` ainda ativo remove as
   variáveis mesmo quando existe EnvironmentFile. Alterá-lo somente na ativação
   autorizada. Conferir destinatários, permissões e horário do resumo antes
   do reinício: o agendador pode enviar no primeiro ciclo elegível.
7. Reiniciar a aplicação na janela aprovada, validar serviço, SHA, saúde HTTP,
   cofre e anexos. Executar o preflight do controlador instalado e reativar o
   timer por último. O health check SMTP apenas confere arquivo e ambiente;
   ele não autentica no provedor e não envia mensagens.

O remetente e a autenticação são obrigatórios no contrato do executor. O envio
continua limitado aos usuários internos ativos com as permissões existentes.
Configurar SMTP não concede acesso nem envia mensagens a clientes.

## Falhas, duplicação e recuperação

O resumo reserva usuário/dia no SQLite antes de contatar SMTP. Falha de TLS,
autenticação, transporte ou encerramento recebe apenas `FALHA_SMTP`, sem texto
do servidor. A reserva persiste após reinício; não há tentativa automática no
mesmo dia. Inclusive um registro `desligado` já reservado impede envio nesse dia.
No dia seguinte há uma nova chave de reserva.

Uma falha depois de o provedor aceitar a mensagem pode ter entrega incerta.
Verificar o provedor antes de intervenção; não apagar reservas nem marcar envio
como não realizado apenas porque o processo não confirmou o resultado.

O backup pré-deploy copia `smtp.env` para a área separada de segredos. O backup
comum contém somente o caminho e os drop-ins sem credenciais. Preservar essa
separação em cópias externas e validar checksums sem imprimir conteúdo.

Para recuperar configuração, pausar o timer, comparar os arquivos atuais com
o backup e preservar gravações posteriores. Repor a senha somente pela cópia
separada, com permissões originais. A troca de senha exige atualizar arquivo e
reiniciar o serviço na mesma manutenção; valores divergentes bloqueiam o runner.

Para desligar ou voltar ao executor anterior: restaurar a política de SMTP
desligado, retirar o EnvironmentFile SMTP do serviço e garantir ausência das
seis variáveis após reinício. Só então instalar configuração sem `smtp_env`,
validar saúde e reativar o timer. Não restaurar bancos ou remover anexos para
desfazer uma configuração SMTP. Revogar a senha no provedor se houver exposição.

## Pendências para ativação

- Credencial de aplicativo configurada privadamente e acesso à conta confirmado.
- Destinatário e teste real autorizados, com entrega verificada.
- Publicação e manutenção do controlador aprovadas em etapa própria.
- Conferência da lista de destinatários e observação do primeiro ciclo real.
