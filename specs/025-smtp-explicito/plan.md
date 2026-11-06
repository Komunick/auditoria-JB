# Plano

Alterar apenas o controlador instalado e seu instalador. Reutilizar o emissor e
a reserva transacional existentes. Nenhuma migração, biblioteca, serviço ou cron.

Contrato: `smtp_env` opcional em schema 1, caminho absoluto em `secret_paths`,
fora das árvores de dados, código e backup comum. Arquivo root 0600, diretório
imediato root 0700 e ancestrais sem escrita de terceiros ou symlinks. Formato
restrito de EnvironmentFile: seis linhas NAME=valor, sem aspas, espaços ou escapes.
Comparar todos os valores com `/proc/PID/environ`, sem registrar valores.

O instalador lê o pacote aprovado como bytes; não importa código candidato.
Valida o arquivo e separação dos backups. A validação completa ocorre no preflight
do controlador instalado. A atualização exige novo OID do control plane.

Validar primeiro contratos negativos e depois suíte completa local. Não conectar
ao SMTP real, não instalar o controlador na VM e não alterar configurações reais.
