# Inventário das amostras analisadas

Este documento registra apenas características estruturais necessárias para a
implementação. Valores fiscais, CNPJ, razão social e arquivos originais não
devem ser adicionados ao Git.

## Conjunto de entrada

Foram fornecidos 12 nomes de relatórios-fonte, correspondentes a 10 conteúdos
únicos e 10 competências únicas:

| Arquivo fornecido | Competência | Layout detectado | DIMP detalhada | Observação |
|---|---:|---|---|---|
| `02.2024(1).xlsx` | 02/2024 | Quadro 50-5 | não | fonte única |
| `06.2024.xlsx` | 06/2024 | Quadro 50-5 | não | fonte única |
| `11.2024.xlsx` | 11/2024 | Quadro 50-5 | não | fonte única |
| `12.2024.xlsx` | 12/2024 | Quadro 50-5 | não | duplicata exata de `12.2024(1).xlsx` |
| `12.2024(1).xlsx` | 12/2024 | Quadro 50-5 | não | duplicata exata de `12.2024.xlsx` |
| `03.2025(1).xlsx` | 03/2025 | Quadro 50-5 | não | duplicata exata de `03.2025(2).xlsx` |
| `03.2025(2).xlsx` | 03/2025 | Quadro 50-5 | não | duplicata exata de `03.2025(1).xlsx` |
| `04.2025(1).xlsx` | 04/2025 | Quadro 50-5 | não | fonte única |
| `05.2025.xlsx` | 05/2025 | Quadro 50-3 | sim | cinco instituições/movimentos úteis |
| `08-2025.xlsx` | 08/2025 | Quadro 50-3 | sim | cinco instituições/movimentos úteis |
| `09.2025.xlsx` | 09/2025 | Quadro 50-3 | sim | cinco instituições/movimentos úteis |
| `12.2025.xlsx` | 12/2025 | Quadro 50-3 | sim | cinco instituições/movimentos úteis |

As duas duplicidades foram confirmadas por igualdade integral do SHA-256, não
apenas por nome ou competência. O teste local deve recalcular os hashes e
confirmar essa relação sem gravar os valores no repositório.

## Layout compacto — Quadro 50-5

Nos seis conteúdos únicos compactos, o resumo válido está em `A10:K10`. O
parser não deve depender somente dessas posições: deve primeiro reconhecer os
rótulos e registrar a célula efetivamente usada como proveniência.

Mapeamento observado:

| Fato normalizado | Campo/célula observada |
|---|---|
| faturamento declarado | Receita Total Informada, coluna C |
| vendas declaradas com ST | coluna E |
| vendas declaradas sem ST | coluna F |
| faturamento calculado | Receita Total Calculada, coluna G |
| diferença de faturamento | `calculado - declarado` |
| vendas calculadas com ST | coluna I |
| vendas calculadas sem ST | coluna J |

Esses relatórios não contêm o bloco detalhado de DIMP. A ausência deve gerar
aviso informativo, não erro de fechamento.

## Layout estendido — Quadro 50-3 com DIMP

Nos quatro conteúdos únicos estendidos:

- o resumo do estabelecimento está em `A16:K16`, com o mesmo mapeamento lógico
  do layout compacto;
- o cabeçalho DIMP está em `A39:J39`;
- as linhas úteis iniciam na linha 40;
- as colunas são período, CNPJ, instituição, débito, crédito, transferência,
  PIX, voucher, outras operações e total.

Para cada instituição:

```text
total_não_pix = total_DIMP - PIX
```

Esse valor inclui débito, crédito, transferência, voucher e outras operações.
Portanto, a interface pode exibir **Cartão/outros**, mas o modelo interno não
deve chamá-lo apenas de cartão. Há voucher nas amostras, o que torna esse teste
obrigatório.

## Planilha mestre fornecida

Alias usado neste documento: `planilha-mestre-fornecida.xlsx`. O nome real do
arquivo permanece somente no diretório privado de amostras.

- folha única: `2022-2025`;
- área utilizada: `A1:T53`;
- bloco 2024: título na linha 9, cabeçalho na linha 10, meses nas linhas 12 a
  23 e total na linha 24;
- bloco 2025: título na linha 28, cabeçalho na linha 29, meses nas linhas 31 a
  42 e total na linha 43;
- colunas alimentadas pelos relatórios analisados: `C`, `D`, `E`, `G`, `H`,
  `I`, `J`, `L` e `M`.

As fórmulas existentes são incompletas e inconsistentes entre linhas; não são
a autoridade de cálculo. A exportação deve recalcular no backend, preencher
somente uma cópia e preservar as regiões sem mapeamento.

Os 10 conteúdos únicos reconciliaram os campos observados com as respectivas
linhas da planilha mestre. Essa comparação deve ser repetida apenas na
validação local privada, nunca transformada em fixture com dados reais.

## Uso seguro das amostras

- Definir o diretório por `AUDITORIA_CONCILIACAO_AMOSTRAS` fora do código.
- Pular a validação privada quando a variável não estiver configurada.
- Nunca registrar valores, CNPJ, razão social ou caminhos absolutos nos logs de
  CI.
- Criar fixtures sintéticas equivalentes para todos os testes versionados.
- Escrever resultados em diretório temporário e nunca sobrescrever a planilha
  mestre ou as fontes.
