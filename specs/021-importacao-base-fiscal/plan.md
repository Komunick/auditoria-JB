# Plano

Implementação local sobre a spec 020 ainda não publicada, preservando suas
alterações na worktree `codex/020-correcoes-previa-base-fiscal`, baseada em
`origin/dev@844db6f`. Separação de commits e publicação ficam para outra rodada.

1. Fixar contratos e checklist antes do código; testes RED por camada.
2. Adicionar importador dedicado em `ferramentas/`, sem FastAPI, e recibo SQLite
   aditivo. Reutilizar classificação da 020 e transações do ClientesStore.
3. Acrescentar permissão e rotas separadas de preparação, confirmação e descarte.
   A consulta da 020 não inicializa stores nem muda seu contrato.
4. Integrar ações à interface estática e testar sessão, arquivos, respostas
   atrasadas e recuperação de falha de rede.
5. Revisar concorrência, rollback, proveniência e menor privilégio. Rodar os
   testes anteriores e novos; conferir o fluxo sintético em navegador local.
6. Registrar evidências e limitações, sem executar ações externas.

Não reutilizar o importador de senhas: ele possui política de atualização e
reativação incompatível com esta inclusão de novas empresas. Recibo separado
permite unicidade e imutabilidade sem alterar a semântica de importações legadas.
Não acrescentar dependência, processo ou porta de produção.
