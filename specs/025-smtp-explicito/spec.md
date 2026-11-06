# Spec 025: preparação do SMTP com autorização explícita

O envio diário existe, mas o executor recusa qualquer variável SMTP. Preparar
uma autorização administrativa explícita, mantendo SMTP desligado por padrão.

## Requisitos e aceite

- `smtp_env: null` ou ausente mantém a rejeição de qualquer variável SMTP.
- Um caminho explícito autoriza somente o conteúdo de um arquivo privado do
  root, com seis variáveis conhecidas, autenticação e SSL/465 ou STARTTLS/587.
- O ambiente do processo deve coincidir com o arquivo autorizado. Configuração
  parcial, variável desconhecida, arquivo inseguro ou divergência bloqueiam o ciclo.
- O arquivo entra apenas no backup separado de segredos e fica inacessível ao
  candidato. Erros contêm códigos, nunca conteúdo do arquivo ou resposta SMTP.
- O instalador aceita `--smtp-env` somente em `install`; não ativa a aplicação,
  não envia mensagens e não inicia o timer automaticamente.
- Testes sintéticos cobrem autenticação, TLS, falhas, reserva e duplicação.
- Esta entrega é local. Ativação real depende de credencial privada, destinatário
  de teste autorizado e manutenção administrativa do executor.

## Cenários

1. Instalação sem opção mantém o contrato anterior.
2. Opção válida permite verificar saúde sem enviar e-mail.
3. Segredo exposto em backup comum, ambiente divergente ou TLS inválido impede
   prosseguimento antes de parar a aplicação.
4. Falha de autenticação/transporte não vaza credenciais nem repete o envio diário.
