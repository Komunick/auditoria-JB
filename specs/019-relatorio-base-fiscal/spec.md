# Spec 019 — Relatório de conferência da Base Fiscal

## Objetivo

Continuar a preparação da base de clientes com um relatório XLSX completo que
permita ao escritório localizar pendências, comparar ocorrências duplicadas e
anotar as correções propostas. A fonte permanece separada das decisões humanas.

## Cenários e aceite

1. Após conferir um arquivo em Clientes → Importar → Base Fiscal, a pessoa com
   `aba.clientes`, `clientes.importar` e `clientes.exportar` pode baixar o relatório
   completo. O servidor exige as três permissões antes de analisar o arquivo.
2. O navegador reenvia o arquivo original e o SHA-256 recebido na prévia. O
   servidor relê a fonte pelo parser da spec 017 e recusa hash divergente com
   409. Não aceita linhas JSON do navegador como fonte de dados.
3. O download inclui todas as linhas, inclusive ocultas, independentemente de
   busca, filtros ou paginação. Mantém IDs, abas, linhas e SHA-256 da fonte.
4. O XLSX contém Resumo (instruções, contagens, avisos e abas), Conferência
   (valores lidos e pendências), Duplicidades (uma linha por ocorrência de CNPJ
   repetido), Correções (identificação da origem e campos vazios para propostas)
   e Origens (célula, valor informado, formato, mesclagem e propagação).
5. A aba Correções distingue os valores originais das propostas. Não preenche
   decisões, não escolhe responsáveis nem funde duplicidades. Informa que o
   relatório serve à revisão e ainda não é aceito como arquivo de importação.
6. Colunas inexistentes em ZERADAS continuam explicitamente identificadas, sem
   criar pendências falsas. Sem movimento não significa inatividade; `null`
   aparece como não informado. Fórmulas permanecem como marcador não lido.
7. Todo texto é gravado como texto no Excel, inclusive CNPJs e conteúdo iniciado
   por sinais de fórmula. Não cria fórmulas, vínculos ou macros. Valores acima
   dos limites de célula ou não representáveis são recusados, sem truncar.
8. Botão indisponível antes da prévia ou sem permissão de exportação. Durante o
   download impede pedidos repetidos. Troca de arquivo, limpeza, nova leitura,
   encerramento/troca de sessão invalidam respostas e downloads atrasados.
   Erros são explícitos e permitem repetir quando a prévia continua válida.
9. Upload temporário fechado e removido em sucesso/erro. Saída retornada em
   memória, sem arquivo persistente, com `Cache-Control: no-store` e nome fixo.
   Auditoria geral registra apenas ação, resultado e quantidade de linhas.
10. Nenhum cadastro, carteira, obrigação, token de confirmação ou schema é
    criado. Importadores existentes e o relatório cadastral continuam intactos.

## Limites e fora de escopo

Reutiliza os limites e a validação de pacotes da spec 017, sem dependência nova.
Duplicidades são listadas por ocorrência, evitando texto quadrático em células.
Não lê dados reais nos testes. Não implementa reimportação das propostas,
associação automática de contas, carga de produção, merge ou deploy.

## Resultado mensurável

Para toda prévia aceita, o relatório conserva o mesmo número de linhas e
contagens, ou recusa explicitamente a geração se um valor não for representável.
Testes sintéticos cobrem conteúdo, autorização, limpeza, sessão e regressão.
