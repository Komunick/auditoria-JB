# Contrato de leitura

`ler_planilha_empresas(caminho, *, max_bytes=20*1024*1024)` retorna objeto com
`resumo()` serializável. Não conhece FastAPI ou banco. Erros usam ErroClientes
com código PLANILHA_INVALIDA e mensagem compreensível.

`POST /api/clientes/base-fiscal/previa`, multipart `arquivo`, depende de
`acesso('clientes.importar')` (aba cumulativa), retorna:

```text
somente_leitura: true
nome_arquivo: basename limitado
formato: base_fiscal_v1
hash_arquivo: SHA-256
avisos: [texto]
abas: [{nome, tipo: principal|zeradas, linha_cabecalho, total, oculta}]
contagens: {linhas, documentos_validos, cnpjs_distintos, documentos_pendentes,
            grupos_duplicados, linhas_duplicadas, sem_movimento,
            sem_responsavel, sem_regime, com_pendencias}
linhas: [{id, aba, linha, nome, documento, documento_informado,
          documento_status: valido|zero_inicial_recuperado|ausente|invalido|formula,
          regime, regime_informado, responsavel_fiscal_informado, contato_nome,
          sem_movimento: true|null, duplicado: boolean, duplicado_em: [id],
          pendencias: [texto], oculta, aba_oculta,
          origem: {campo: {celula, celula_origem, valor_informado, formato,
                           intervalo_mesclado: texto|null, propagado: boolean,
                           formula: boolean}}}]
```

Campos de origem: nome, documento, regime, responsavel_fiscal, contato_nome;
os ausentes no layout podem ser omitidos. `id` é estável no arquivo e único
entre abas (p.ex. `1:3`). `documento` é string de 14 dígitos ou vazia. Regime
normalizado é Simples Nacional, Lucro Real, Lucro Presumido ou vazio.
`valor_informado` é texto, mas fórmula vira `[fórmula não lida]`.
O texto integral fica em `origem.valor_informado`; nome, contato e responsável
exibidos têm espaços nas extremidades aparados. Isso não associa identidades.
`duplicado_em` contém os demais IDs do mesmo CNPJ. A soma das referências
cruzadas é limitada a 100 mil no arquivo; excesso recusa a leitura inteira,
antes de construir a resposta, sem suprimir linhas ou referências.

`documentos_validos` conta linhas com documento válido (inclui zero recuperado);
`cnpjs_distintos` conta seus valores únicos; `grupos_duplicados` conta chaves com
mais de uma ocorrência; `linhas_duplicadas` conta todas as suas ocorrências.
`com_pendencias` é união, não soma de categorias. Pendências incluem documento,
nome, responsável/regime ausentes, fórmula e duplicidade. Recuperação válida de
zero é indicada pelo status/origem, sem impedir leitura.

Respostas com dados são privadas (`Cache-Control: no-store`). Sem token,
download ou endpoint de confirmação. Erros: 401/403 acesso, 413 tamanho,
422 extensão/layout/pacote inválido. Auditoria registra somente contagem.
