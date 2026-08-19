# Contrato de saída XLSX

## Regras compartilhadas

- Resposta MIME:
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- O arquivo só é apresentado depois de salvo integralmente com sucesso.
- Valores monetários são células numéricas com formato monetário brasileiro,
  não strings.
- CNPJ é texto formatado para preservar zeros.
- Texto vindo de fonte ou usuário iniciado por `=`, `+`, `-` ou `@` recebe
  prefixo de apóstrofo antes de ser escrito como dado.
- Cabeçalhos têm autofiltro; tabelas congelam a primeira linha; larguras devem
  permitir leitura razoável.
- O workbook contém uma aba `Metadados` ou bloco equivalente com data/hora,
  usuário, filtros, versão do parser e quantidade exportada.

## Consolidado auditável

Nome sugerido: `conciliacao_fiscal_YYYYMMDD_HHMM.xlsx`.

### Aba `Conciliações`

Uma linha por versão vigente que atende aos filtros.

Colunas mínimas:

1. Competência
2. CNPJ
3. Razão social
4. Estado da revisão
5. Número/ID da versão
6. Layout
7. Receita declarada
8. Declarada com ST
9. Declarada sem ST
10. Receita calculada
11. Calculada com ST
12. Calculada sem ST
13. Diferença de receita
14. Diferença com ST
15. Diferença sem ST
16. PIX
17. Cartão/outros (não PIX)
18. Avisos abertos
19. Bloqueios abertos
20. Conflitos abertos
21. Arquivo-fonte
22. SHA-256

Para Quadro 50-5, PIX e não-PIX ficam vazios, nunca `0,00`.

### Aba `Movimentos DIMP`

Uma linha por movimento original, sem perder duplicidade de instituição:

- competência, CNPJ, versão, instituição, linha de origem;
- débito, crédito, transferência, PIX, voucher, outras;
- total DIMP e total não-PIX;
- arquivo, SHA-256, aba e célula do total.

### Aba `Proveniência`

Uma linha por fato:

- competência, CNPJ, versão, métrica, valor;
- tipo de origem, arquivo, SHA-256, aba, célula e rótulo;
- regra do parser, versão do parser, fórmula e fatos de origem.

### Aba `Exceções`

- competência, CNPJ, versão, código, severidade, mensagem, estado;
- resolução, responsável e timestamps.

### Aba `Revisões`

- competência, CNPJ, versão, revision anterior;
- estado anterior, estado novo, justificativa, usuário e timestamp.

### Aba `Versões`

Uma linha por versão vigente, candidata, substituída ou descartada, com todos
os valores financeiros, fonte, estado, número da versão e timestamps. As abas
`Movimentos DIMP` e `Proveniência` abrangem todas essas versões e sempre
incluem `versao_id`; a aba `Conciliações` permanece a visão corrente.

### Aba `Conflitos`

Uma linha por conflito aberto ou resolvido, com versão vigente/candidata no
instante de criação, diferenças tipadas, decisão, justificativa, responsável e
timestamps.

### Aba `Metadados`

- gerado em;
- gerado por;
- filtros;
- total de conciliações, versões, movimentos, fatos, exceções, conflitos e
  revisões;
- versão do sistema/parser;
- aviso de que o consolidado pode conter estados não aprovados conforme filtro.

## Cópia da planilha-mestre

Nome sugerido:
`planilha_mestre_<CNPJ>_preenchida_YYYYMMDD_HHMM.xlsx`.

### Seleção de registros

- Um CNPJ obrigatório.
- Versão vigente apenas.
- Aprovada por padrão.
- `em_revisao` apenas com permissão `conciliacao.incluir_pendentes`, flag e
  confirmação explícitas.
- Rejeitada nunca entra.
- Bloqueio ou conflito aberto nunca entra, mesmo se o estado persistido estiver
  inconsistente.

### Mapeamento mensal inicial

Na linha do mês:

| Coluna | Conteúdo |
|---|---|
| C | receita declarada |
| D | declarada com ST |
| E | declarada sem ST |
| G | receita calculada |
| H | fórmula `=Glinha-Clinha` |
| I | calculada com ST |
| J | fórmula `=Glinha-Ilinha` conforme legado |
| L | detalhes PIX por instituição |
| M | detalhes não-PIX por instituição |

O campo M deve ser apresentado como “Cartão/outros” quando houver cabeçalho sob
controle da aplicação; em modelo legado, manter a coluna e registrar a
semântica nos metadados.

Detalhes L/M usam `Instituição: R$ 1.234,56`, separados por quebra de linha ou
` | `, com wrap-text. Linhas originais continuam no consolidado; o modelo pode
agregar por instituição para leitura.

### Totais anuais

Quando a seção contiver 12 meses e uma linha TOTAL, escrever fórmulas `SUM` nas
colunas C, D, E, G, H, I e J. Configurar recálculo completo ao abrir no Excel.

### Preservação

- Não alterar outras células, fórmulas, estilos, larguras, mesclagens ou abas.
- Não preencher anos/meses não selecionados.
- Produzir erro antes do download se o modelo não puder ser mapeado sem
  ambiguidade.
- Se pendentes forem incluídos, criar aba `Metadados da automação` ou aviso
  visível informando competências e estado; não inserir comentário oculto como
  única sinalização.

## Critério de comparação nos testes

- Conferir valores e fórmulas das células mapeadas.
- Comparar células fora do mapeamento entre original e cópia.
- Reabrir o workbook gerado com openpyxl.
- Confirmar que nenhum dado textual perigoso virou fórmula.
- Confirmar que falhas não retornam bytes iniciados por `PK` como se fossem
  saída válida.
