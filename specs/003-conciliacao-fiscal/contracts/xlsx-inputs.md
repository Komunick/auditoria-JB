# Contrato de entrada XLSX

## Regras gerais

- Extensão aceita: `.xlsx`.
- O arquivo deve ser um pacote Open XML válido, sem macro e sem vínculo externo.
- O nome do arquivo nunca determina CNPJ, competência ou layout.
- O parser busca uma planilha com a identificação da Secretaria da Fazenda do
  Estado da Bahia e reconhece os blocos por rótulos normalizados.
- Acentos, capitalização e espaços repetidos não alteram o reconhecimento.
- Deslocamento de linhas é aceito dentro dos limites de busca; troca arbitrária
  de colunas não é aceita sem um adaptador de layout explicitamente testado.
- Campos obrigatórios vazios ou fórmulas sem valor calculado armazenado causam
  erro. Zero numérico é distinto de vazio.
- A planilha deve conter um CNPJ válido. Se cabeçalho e linha mensal contiverem
  CNPJ, ambos devem coincidir.
- Competência deve ser `AAAAMM` e o mês deve estar entre 01 e 12.
- Cada arquivo representa exatamente um relatório, um CNPJ, uma competência e
  uma linha-resumo. Duas abas ou linhas-resumo reconhecidas tornam o arquivo
  ambíguo e geram `RELATORIO_AMBIGUO`; não desmembrar silenciosamente.
- Valores aceitos: células numéricas; ou texto sem símbolo de moeda nos
  formatos `1234,56`, `1.234,56`, `1234.56` e `1,234.56`, após determinar de
  forma inequívoca o separador decimal. Formatos ambíguos são rejeitados.

## Segurança do pacote

Antes de `openpyxl`, validar:

- presença de `[Content_Types].xml` e `xl/workbook.xml`;
- no máximo 5.000 entradas ZIP;
- no máximo 120 MB descompactados;
- razão descompactado/comprimido no máximo 120:1;
- nenhum caminho absoluto ou com `..`;
- ausência de `vbaProject.bin`;
- ausência de `xl/externalLinks/`;
- tamanho do upload dentro de `AUDITORIA_CONCILIACAO_MAX_UPLOAD_MB`, padrão
  50 MB.
- no máximo 100 arquivos e 500 MB acumulados no staging de uma sessão.

Os limites são defaults da feature e podem ser parametrizados somente mantendo
testes de rejeição e limites seguros.

## Layout Quadro 50-5

Reconhecimento pelo mesmo cabeçalho contendo, no mínimo:

- `Receita Total Informada`
- `Receita Total calculada`

A linha de dados é a primeira linha mensal válida imediatamente abaixo do
cabeçalho reconhecido.

| Campo canônico | Coluna esperada na família inicial | Rótulo/proveniência |
|---|---:|---|
| competência | A | período mensal |
| CNPJ | B | CNPJ da linha |
| receita declarada | C | Receita Total Informada |
| declarada com ST | E | Receita com substituição tributária de ICMS |
| declarada sem ST | F | Receita sem substituição tributária |
| receita calculada | G | Receita Total calculada |
| calculada com ST | I | Receita calculada com ST |
| calculada sem ST | J | Receita calculada sem ST |

O layout não fornece DIMP detalhado. `total_pix` e `total_nao_pix` são `NULL` e
gera-se aviso informativo.

## Layout Quadro 50-3/DIMP

O bloco-resumo é reconhecido pelos rótulos de receita total e receita sem
substituição tributária. O mapeamento financeiro do resumo é o mesmo:

| Campo canônico | Coluna esperada |
|---|---:|
| competência | A |
| CNPJ | B |
| receita declarada | C |
| declarada com ST | E |
| declarada sem ST | F |
| receita calculada | G |
| calculada com ST | I |
| calculada sem ST | J |

O bloco DIMP é reconhecido pelo cabeçalho que contém `Instituição Financeira` e
`Total DIMP`.

Quadro 50-3 reconhecido sem bloco DIMP válido gera bloqueio
`DIMP_OBRIGATORIA_AUSENTE`; não é reinterpretado como Quadro 50-5.

| Campo de movimento | Coluna esperada |
|---|---:|
| competência | A |
| CNPJ | B |
| instituição | C |
| débito | D |
| crédito | E |
| transferência | F |
| PIX | G |
| voucher | H |
| outras | I |
| total DIMP | J |

Somente linhas com a competência e o CNPJ do resumo entram na versão atual.
Linha plenamente identificada como outro CNPJ ou período é excluída com aviso
e proveniência. Linha com CNPJ/período ausente, inválido ou ambíguo em meio ao
bloco gera bloqueio. Nenhuma delas é incorporada silenciosamente.

`total_nao_pix = total_dimp - pix`. Não chamar esse valor simplesmente de
cartão no domínio.

## Regras de validação financeira

- `declarada_com_st + declarada_sem_st = receita_declarada`, tolerância R$ 0,01.
- `calculada_com_st + calculada_sem_st = receita_calculada`, tolerância R$ 0,01.
- Por movimento, soma de débito, crédito, transferência, PIX, voucher e outras
  deve fechar com total DIMP, tolerância R$ 0,01.
- DIMP total acima da receita calculada por mais de R$ 0,01 gera bloqueio.
- DIMP total abaixo da receita calculada por mais de R$ 0,01 gera aviso.
- Diferenças são calculadas como calculado menos declarado.

## Proveniência obrigatória

Cada fato de célula registra:

- SHA-256 e ID da fonte;
- nome da planilha;
- referência A1 da célula;
- rótulo reconhecido;
- identificador estável da regra/adaptador;
- versão do parser.

Cada derivado registra a fórmula canônica e as métricas de origem.

## Planilha-mestre recebida para preenchimento

- Deve passar pela mesma validação segura de pacote.
- Deve possuir seções anuais identificáveis por `RELATÓRIO AAAA` e exatamente
  uma linha para cada mês que será preenchido.
- Meses são reconhecidos pelo texto, não por número fixo de linha.
- Se existir CNPJ identificável no modelo, deve coincidir com o CNPJ escolhido.
- Mês ausente, duplicado ou ambíguo é erro de contrato.
- A aplicação trabalha numa cópia; nunca modifica o upload original.

## Erros estáveis recomendados

- `XLSX_INVALIDO`
- `XLSX_MACRO_NAO_PERMITIDA`
- `XLSX_VINCULO_EXTERNO`
- `XLSX_COMPACTACAO_INSEGURA`
- `LAYOUT_NAO_RECONHECIDO`
- `RELATORIO_AMBIGUO`
- `CNPJ_INVALIDO`
- `CNPJ_DIVERGENTE`
- `COMPETENCIA_INVALIDA`
- `CAMPO_OBRIGATORIO_AUSENTE`
- `FORMULA_SEM_VALOR`
- `FECHAMENTO_RECEITA`
- `FECHAMENTO_DIMP`
- `DIMP_OBRIGATORIA_AUSENTE`
- `MODELO_INCOMPATIVEL`
