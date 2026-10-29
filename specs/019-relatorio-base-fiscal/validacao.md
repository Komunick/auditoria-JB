# Validação

Implementação validada em 29/10/2026 no branch
`codex/019-relatorio-base-fiscal`, a partir de `dev@76dd669`.

## TDD e testes específicos

- `test_relatorio_base_fiscal.py`: RED por módulo inexistente; GREEN com
  fidelidade de valores/contagens, propostas vazias, origem, mesclagens, linhas
  ocultas, ZERADAS, zero inicial, texto literal e fórmulas não lidas. Cobre limites
  de texto em UTF-16, caracteres XML inválidos, base vazia e 316 ocorrências
  duplicadas sem expansão quadrática.
- `test_web_base_fiscal_relatorio.py`: RED por endpoint inexistente; GREEN com
  401, cada permissão cumulativa ausente, administrador/importador autorizado,
  hash inválido/divergente, extensão/pacote/tamanho, exceções do parser/gerador,
  cache e conteúdo XLSX. Store proibido durante o teste; nenhum token nem banco
  cadastral criado. Uploads fechados, pastas removidas e auditoria mínima.
- `test_base_fiscal_relatorio_ui.py`: RED por botão inexistente; GREEN com
  permissões, fonte/hash originais, filtros, pedido repetido, retry, erro de hash
  e respostas obsoletas após arquivo, leitura, identidade, sessão ou permissão
  mudar. Verifica também mudança durante o await do blob e revogação da URL.
- `test_base_fiscal_ui.py` anterior aprovado; `node --check webui/clientes.js`
  e `git diff --check` aprovados.

## Revisão independente e tratamento de falhas

Revisão da rota/contrato: sem bloqueio de autorização, integridade ou ciclo de
vida. Revisão do gerador identificou uma falha de limpeza quando a finalização
XML do openpyxl levantava erro persistente; a reprodução deixou cinco arquivos
temporários sintéticos. Corrigido com RED/GREEN: fechar streams e remover cada
XML independentemente de erro secundário, preservar a exceção original e fechar
o ZIP por contexto. O reteste verificou cinco fechamentos, zero resíduos e ZIP
fechado. A revisão final aprovou a correção, sem novos achados.

## Regressão

Executados os 84 scripts `tests/test_*.py`: **82 aprovados, 2 pulados, 0 falhas
de teste**. Os pulos são `test_fdb_reader.py` e `test_web_produtos_fdb.py`, por
ausência do Firebird opcional. O teste desktop/PySide6 passou.

A correção de limpeza acima foi concluída durante a suíte. O verificador de
hashes detectou apenas `relatorio_base_fiscal.py` e seu teste alterados e, por
isso, encerrou com código 1 apesar dos testes aprovados. Após congelar esses
arquivos, os scripts do gerador e da rota HTTP foram reexecutados e passaram.
O manifesto final confirmou que todos os demais arquivos testados permanecem
idênticos. A suíte inteira não foi repetida depois dessa correção localizada.

Evidências privadas fora do Git: `tmp/validacao-spec019-20261029-170346/`, com
logs por script, `resumo.json`, manifestos inicial/final, `reteste-final.json`
e logs `*-final.log`. Nenhuma planilha real foi usada ou versionada.

## Navegador

Servidor local em loopback, porta 8619, pasta de dados descartável e perfil
sintético. Fluxo real: login → Clientes → Importar → conferir XLSX → filtrar
uma empresa → baixar relatório. O arquivo baixado continha as cinco abas e os
quatro registros da fonte, embora a tela exibisse um só; três ocorrências de
um CNPJ repetido, SHA-256 correto, propostas vazias e nenhuma fórmula.
Tela inspecionada em viewport estreito, sem sobreposição no novo controle.
Captura privada: `tmp/previa-relatorio-base-fiscal-019.jpg`.
Servidor e aba de teste encerrados após a conferência.

## Limites da entrega

Relatório de revisão, sem reimportação das propostas ou carga cadastral. As
decisões sobre documentos, duplicidades, vínculos de responsáveis e aplicação
de obrigações continuam exigindo conferência do escritório antes da carga.
Sem migração ou nova dependência. Após a validação, o usuário autorizou commit,
push e PR para `dev` em 29/10/2026. Merge e deploy não fazem parte desta entrega.
