# Operação das evidências e dos avisos

## Armazenamento privado no servidor

A spec 024 permite guardar evidências na pasta persistente da aplicação, sem
contratar um bucket. Não há fallback automático nem migração entre modos.

Configuração explícita no ambiente do serviço:

```ini
AUDITORIA_QUALIDADE_ANEXOS_PRIVADO=1
AUDITORIA_QUALIDADE_ANEXOS_LIMITE_MB=1024
AUDITORIA_QUALIDADE_ANEXOS_RESERVA_MB=1024
```

Preservar o `AUDITORIA_WEB_DADOS` absoluto já utilizado. Os arquivos ficam em
`AUDITORIA_WEB_DADOS/qualidade/anexos`. Desabilitar o modo de desenvolvimento
`AUDITORIA_QUALIDADE_ANEXOS_LOCAL` e não combinar a configuração privada com
bucket, endpoint ou região S3. Configurações conflitantes recusam a operação.

- Limite padrão total: 1.024 MiB. Reserva mínima de disco livre: 1.024 MiB.
  As duas variáveis aceitam inteiros de 1 a 102.400 MiB.
- Limites por arquivo: 10 MiB; PNG/JPEG até 25 megapixels. PDF e EML também
  são aceitos após validação estrutural. Não é uma análise antivírus.
- Máximo de 10.000 objetos. A quota conta os arquivos existentes, incluindo
  eventuais objetos sem vínculo, e não remove evidências para liberar espaço.
- Diretório POSIX 0700, arquivos 0600, nomes aleatórios sem o nome original.
  No Windows, a proteção adicional depende das ACLs da pasta de dados.
- Trava entre threads e processos cobre contagem, espaço livre e escrita.
  Uma segunda gravação não pode consumir a mesma quota disponível. A reserva
  não impede que outros serviços preencham o disco: monitorar espaço continua
  necessário.
- Falha de configuração, quota, reserva ou armazenamento retorna erro controlado;
  não cria vínculo de anexo bem-sucedido. O download exige autorização e confere
  tamanho e SHA-256 antes de entregar o conteúdo.

Antes de habilitar em produção, conferir o backend atual e se há linhas em
`qualidade_anexo`. Se houver evidências em outro backend, não trocar a variável
diretamente: planejar migração consistente, preservar as chaves e verificar todos
os hashes e tamanhos. O banco não registra um backend separado para cada objeto.

Não publicar a pasta no proxy, criar URLs públicas ou ampliar permissões dos
usuários. A rota de download mantém o escopo do registro associado.

## Backup e recuperação

O autodeploy copia a pasta de dados inteira com serviço parado e hold ativo.
Nesse modo, a cópia inclui bytes das evidências e seus metadados no `clientes.db`.
O ensaio POSIX da spec 024 usou a função real `copy_tree` do executor e recuperou
um objeto sintético, verificando conteúdo e hash.

Ao criar um novo drop-in ou arquivo de ambiente, incluí-lo no inventário de
configuração do executor (`configuration_paths`) antes da implantação. Não
confundir backup do diretório de dados com backup automático de arquivos novos
em `/etc`. Credenciais continuam em cópia privada separada.

Em uma recuperação autorizada, usar bancos, objetos e configuração do mesmo
ponto de corte. Abrir somente cópias de trabalho dos backups. Conferir os
manifestos, integridade e chaves estrangeiras dos bancos e a correspondência
de cada metadado com os bytes recuperados. Ensaiar o download autenticado em
ambiente isolado antes de reabrir o serviço. Não restaurar bancos às cegas.

Backups e anexos no mesmo servidor não protegem contra perda completa da VM ou
da conta. Uma cópia externa continua sendo uma decisão de infraestrutura e
retenção; esta mudança não cria nem comprova backup externo. O modo S3 permanece
compatível, mas seus objetos precisam de backup próprio conforme a spec 022.

## E-mail e alertas internos

Os alertas internos funcionam sem SMTP. O endereço de envio informado pelo
responsável fica na configuração privada, fora dos arquivos versionados.

Para uma conta Yandex 360, a documentação oficial informa `smtp.yandex.com`,
porta 465 com SSL ou 587 com STARTTLS, usuário com endereço completo e senha de
aplicativo. Fonte: [configuração oficial do cliente de e-mail](https://yandex.com/support/yandex-360/business/mail/en/mail-clients/others).
O provedor e a disponibilidade de autenticação precisam ser confirmados na conta;
o domínio MX sozinho não comprova que o SMTP está autorizado.

O executor atualmente rejeita variáveis `AUDITORIA_SMTP_*` no processo de
produção. Portanto, não basta remover `smtp-desligado.conf` ou acrescentar a
senha: a ativação exige uma evolução explícita e testada desse contrato, com
configuração privada, cópia de recuperação separada e proteção contra envio
involuntário. A spec 024 não modifica esse gate nem envia mensagens.

Não pedir senha pelo chat, registrá-la em comandos ou versionar credenciais.
Depois da configuração privada e da adequação operacional, validar primeiro
com destinatário de teste autorizado. Reservas diárias de envio existentes
devem continuar impedindo duplicações após reinício ou falha.
