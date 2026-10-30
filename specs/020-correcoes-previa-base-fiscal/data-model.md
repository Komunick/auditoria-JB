# Contratos

## Núcleo

`core.correcoes_base_fiscal.preparar_previa(leitura, caminho_correcoes) -> dict`
valida o relatório e devolve propostas/classificação sem consulta ao cadastro.
`comparar_cadastro(previa, clientes) -> dict` compara contra uma lista mínima
de clientes, sem alterar os argumentos. Nenhuma função grava arquivos ou banco.

Resposta: `formato=base_fiscal_importacao_v1`, `somente_leitura=true`,
`hash_arquivo`, `hash_correcoes`, `avisos`, `contagens` (linhas, incluir, existente,
conflito, pendente, ignorar, alteradas) e `linhas`.

Cada linha: `id`, `aba`, `linha`, `original`, `proposto`, `efetivo`, `alteracoes`,
`decisao`, `observacao`, `status`, `pendencias`, `avisos`, `cadastro` (ou null).
Campos de original/proposto/efetivo: nome, documento, regime, responsavel_fiscal,
contato_nome; efetivo também possui sem_movimento. Alterações são objetos
`campo, antes, depois, celula`. Cadastro: id, nome, documento, contato_nome,
situacao, revision. Proposto contém os textos das cinco células G:K; não inclui
identidade de conta. Status: incluir|existente|conflito|pendente|ignorar.

Vazio em G:K preserva a fonte. `ignorar` exige justificativa em M e conserva
eventuais pendências de dados para consulta. Um grupo pode ser integralmente
ignorado mediante decisões explícitas em todas as ocorrências; se houver uma
ocorrência para incluir, ela exige `manter` e as restantes `ignorar` justificado.

## HTTP

`POST /api/clientes/base-fiscal/importacao/previa`, multipart obrigatório:
`arquivo` original, `correcoes` relatório revisado, `hash_esperado` da prévia.
Autorização cumulativa `aba.clientes` + `clientes.importar`. Sucesso JSON 200,
no-store, nomes base limitados e `cadastro_consultado_em` UTC e
`cadastro_disponivel` (false apenas se o arquivo do banco não existe).
Não criar token, sessão de importação, endpoint de confirmação ou arquivo durável.
Erros: 401/403 acesso, 409 fonte/relatório divergentes, 413 tamanho,
422 pacote/estrutura/propostas estruturalmente inválidos, 503 cadastro indisponível.
Erros por campo são pendências da linha na resposta 200, sem aptidão para incluir.

## Consulta mínima

`ferramentas.previa_cadastro_fiscal.consultar_cadastro(caminho, documentos)`
retorna `{disponivel: bool, consultado_em: ISO UTC, clientes: [...]}`.
Só consulta CNPJs efetivos válidos por lotes parametrizados na mesma transação
de leitura. Não usa immutable=1 (precisa enxergar WAL), não abre ClientesStore,
não cria diretório, banco, tabelas, schema ou dados cadastrais.
