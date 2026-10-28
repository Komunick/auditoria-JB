# Validação — spec 017

Executada em 28/10/2026 no branch `codex/017-previa-base-fiscal`, criado de
`dev@7207040`. Nenhuma migração, carga de dados reais ou implantação.

## Critérios e evidências

| Critério | Verificação | Resultado |
|---|---|---|
| Testes antes do código | Parser inicialmente sem módulo; UI sem `BaseFiscalUI`; HTTP sem a rota nova | RED observado nas três camadas; GREEN após implementação |
| Leitura e rastreabilidade | `tests/test_planilha_empresas.py`: 15 grupos sintéticos; layouts, origem, linhas ocultas, mesclagem de contato, regimes e duplicidades | Aprovado |
| Documentos sem correção silenciosa | Texto com separadores permitidos, caracteres extras, DV, zero inicial condicionado à máscara, números inválidos e fórmulas | Aprovado; origem conservada e pendências explícitas |
| Limites antes da expansão | Pacote XLSX seguro, XML com dimensões falsas, células fora da estrutura, alvo de worksheet sem extensão XML, limites físicos e referências cruzadas | Aprovado; recusa integral sem resultado parcial |
| Autorização no servidor | `tests/test_web_base_fiscal.py`: anônimo 401; cada permissão isolada 403; ambas 200; parser não chamado quando negado | Aprovado |
| Prévia sem cadastro | Store substituído por implementação que falha se chamado; ausência de token e de registro nas prévias de importação | Aprovado; única escrita é a auditoria geral de metadados |
| Upload e auditoria | Fechamento e remoção do temporário em sucesso e erros 422/413/500; auditoria sem conteúdo ou nome do arquivo; resposta com `Cache-Control: no-store` | Aprovado |
| Interface e sessão | `tests/test_base_fiscal_ui.py`: 360 linhas sintéticas, busca/filtros/páginas, totais invariantes, origem, texto não confiável e invalidação de respostas antigas | Aprovado |
| Troca de usuário | Logout limpa prévia; nova autenticação recarrega documento; usuário sem permissão não dispõe do upload | Aprovado em teste e navegador |
| Compatibilidade | Todos os `tests/test_*.py` executados individualmente com o venv do projeto | 74 aprovados, 2 pulados, 0 falhas, em 76 scripts |
| Revisão independente | Contrato, parser, rota, interface e limites revisados após ajustes | Sem bloqueios identificados |

Os dois scripts pulados foram `test_fdb_reader.py` e
`test_web_produtos_fdb.py`, por ausência do motor Firebird opcional no ambiente.
Hashes dos fontes e testes permaneceram iguais durante toda a suíte. Também
passaram `node --check` dos JavaScripts alterados e `git diff --check`.

## Conferência no navegador

Servidor local com dados descartáveis, usuários sintéticos e planilha sintética
de 34 linhas em duas abas. Nenhum arquivo real foi enviado ao servidor de teste.

- Prévia em Clientes → Importar, separada do importador anterior.
- Totais gerais preservados ao filtrar duplicidades, documentos pendentes e
  empresas sem movimento; busca e paginação conferidas.
- Origem expandida por teclado, distinguindo responsável Fiscal e contato,
  células e referências de duplicidade entre abas.
- Limpar prévia apaga resultado e seleção do arquivo.
- Temas claro/escuro conferidos. Em 390 × 844, a página não transbordou;
  a tabela larga permanece rolável dentro do próprio contêiner.
- Sessão encerrada e acesso com usuário restrito conferidos. Sem erros ou
  avisos no console ao final.
- Servidor temporário encerrado, aba fechada e viewport restaurado após o QA.

A leitura da fonte real ocorreu separadamente, em área privada, com reconciliação
por aba/linha e SHA-256 antes/depois. A fonte não foi alterada. Conteúdo, nomes,
documentos, decisões particulares e resultados dessa leitura ficam fora do Git.
As fixtures versionadas são sintéticas.

## Limites e integração

Esta entrega permite conferir a origem; ainda não cadastra clientes, resolve
duplicidades, associa nomes a contas nem atribui carteiras. Não gera tarefas ou
ativa o catálogo de obrigações. Essas decisões pertencem à etapa de carga.

O ajuste de autenticação em `webui/app.js` repete os mesmos três trechos da
spec 016/PR #17 para impedir reaproveitamento de DOM entre sessões. O restante
da Central não faz parte deste branch. A suíte acima cobre esta feature sobre
`dev@7207040`, sem incorporar as specs 015/016.

A simulação de integração por `git merge-tree --write-tree`, entre o commit
`cc93761` da spec 016 e o commit `2d98dc7` desta implementação, terminou sem
conflitos. Isso verifica compatibilidade textual; a combinação não foi
executada nem usada para substituir a suíte deste branch.

Firebird e produção não foram verificados nesta etapa. A publicação é por PR
para `dev`; merge e deploy seguem o fluxo do projeto.
