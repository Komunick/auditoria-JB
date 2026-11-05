# Implementação

Usar o branch atualizado de dev, preservando os checkouts anteriores. Reaplicar a correção do semáforo sem perder o ajuste de quebra de texto das tabelas.

O KPI novo deriva exclusivamente das ocorrências já autorizadas e filtradas. Não há tabela, migração ou permissão nova; os relatórios consomem o mesmo painel.

Armazenamento privado: `AUDITORIA_QUALIDADE_ANEXOS_PRIVADO=1`, arquivos em `AUDITORIA_WEB_DADOS/qualidade/anexos`. Quota padrão de 1024 MiB e reserva de 1024 MiB livres, configuráveis por `AUDITORIA_QUALIDADE_ANEXOS_LIMITE_MB` e `AUDITORIA_QUALIDADE_ANEXOS_RESERVA_MB`. Limite de 10.000 objetos, 10 MiB por arquivo. Somente nomes internos aleatórios, permissões POSIX 0700/0600, validação de conteúdo e SHA-256 já existentes.

Trava de arquivo entre processos e trava entre threads abrangem contagem, espaço livre e escrita. Nenhum processo ou serviço persistente novo. Recusar mistura de modos, diretórios/arquivos inesperados e links simbólicos. Não migrar nem trocar backend silenciosamente quando houver evidências.

Testar antes de implementar: limites inclusivos, concorrência, falta de espaço, integridade, cópia/restauração isolada e compatibilidade S3/local. Em HTTP, manter autenticação, escopo, revogação durante upload, compensação e download attachment/no-store.
