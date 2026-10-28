# Plano

Branch `codex/018-deploy-automatico`, criado de dev após PR #18. Fluxo por PR
para dev e promoção para main, com merge commits. A solicitação de configurar
a automação autoriza instalar e ativar o mecanismo depois da validação.

1. Especificar executor, estados, instalação e tratamento de falhas.
2. Escrever testes RED do executor e instalador com sistema/serviços simulados.
3. Implementar runner Python stdlib, configuração JSON e units systemd.
4. Revisar limites de privilégio, backup, SQLite, cron e recuperação.
5. Validar localmente e no Linux real em modo de conferência, sem dados reais
   nos testes. Registrar evidências antes da publicação.
6. Publicar por PRs, instalar uma versão fixa do executor fora do checkout e
   ativar o timer somente após preflight. Acompanhar o primeiro ciclo completo.

Dados e evidências operacionais da VM permanecem fora do repositório público.
O runner usa Git público e testes locais; não depende de SSH no GitHub Actions
nem de um runner de CI hospedado na VM produtiva.
