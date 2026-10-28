# Contrato operacional

Sem alteração do schema da aplicação.

- Executor instalado: `/usr/local/lib/auditoria-jb-autodeploy/runner.py`, root.
- Configuração: JSON privado, versão 1, caminhos e nomes explícitos; nenhum
  comando arbitrário, token GitHub ou chave SSH.
- Estado: `state.json`, lock exclusivo e marcador persistente `hold` em diretório
  privado root. Campos incluem etapa, SHA anterior/alvo, caminho de backup,
  resultado e erro sanitizado.
- `hold`: impede inicialização da aplicação por ConditionPathExists enquanto
  há manutenção/falha. Não é removido em falha por rotina automática.
- Backup: novo diretório por execução, cópia inteira dos dados e materiais de
  recuperação, manifesto e procedimento escrito. Segredos em raiz separada.
- Comandos: `--check` confere preflight sem parada; `--once` executa um ciclo.
- Estados: sem mudança, candidato, testado, manutenção, copiado, atualizado,
  validado ou bloqueado. Sucesso só após a última verificação do serviço.

Detalhes da configuração e operação em `devops/autodeploy/README.md`.
