# Spec 027 — Antecipação e DIFAL do ICMS-BA (aba 11)

Pedido da direção da Komunick em 26/11/2026: transformar em funcionalidade do
Auditoria-JB dois documentos recebidos da JB Fraga. As fontes ficam fora do
repositório público:

- **Fonte A** — "Sistema de cálculo do DIFAL — Bahia. Especificação funcional
  para desenvolvimento, versão 1.0", do Departamento Fiscal (3 páginas).
- **Fonte B** — conversa de prototipação "Aplicativo de Antecipação Tributária —
  Bahia" (pedido original do setor e protótipo de simulação).

Trilha B do Komunick Patterns (funcionalidade em projeto existente). Sem ticket
no Linear nesta entrega.

## O problema

Empresa estabelecida na Bahia que compra mercadoria de outro estado recolhe ICMS
para a Bahia na entrada. Hoje o Fiscal abre cada nota, separa os produtos por
CFOP e alíquota e faz a conta à mão. O pedido é: ler várias notas de uma vez,
separar os produtos por CFOP e alíquota, calcular o valor a pagar comparando a
alíquota da nota com a interna da Bahia (20,5%), guardar a memória de cálculo e
somar por empresa e período.

## Achado que orienta o desenho: as duas fontes pedem contas diferentes

Para a mesma nota de R$ 1.000,00 vinda de SP com R$ 70,00 de ICMS destacado:

| | Fonte A (base por dentro) | Fonte B (diferença simples) |
|---|---|---|
| Conta | (1.000 − 70) ÷ 0,795 × 20,5% − 70 | 1.000 × 20,5% − 70 |
| A recolher | **R$ 169,81** | **R$ 135,00** |

Nenhuma das duas é escolhida pelo programa. O método é parâmetro explícito de
cada nota, fica gravado, e a memória de cada item mostra quanto daria pelo
outro. O método sugerido na importação nasce como o da Fonte A, por ser o
documento formal do setor, e é configurável.

**Observação do sistema atual, não homologada:** o art. 12-A da Lei 7.014/1996
descreve a antecipação parcial como "aplicação da alíquota interna sobre a base
de cálculo prevista no inciso III do art. 23, deduzido o valor do imposto
destacado", e o art. 23, III define essa base como "o valor da operação
interestadual constante no documento fiscal de aquisição" — a conta da Fonte B.
A Fonte A declara que "reproduz a solicitação, sem homologação jurídica
independente". Ver P-01.

## Escopo desta entrega

1. **Importação em lote de XML de NF-e** (até 200 por envio). Cada arquivo tem o
   seu resultado: importada, já existente, fora do escopo ou inválido.
2. **Sem duplicidade pela chave de acesso.** A segunda importação da mesma
   chave não altera nada.
3. **Escopo da nota:** modelo 55, autorizada, de saída, destino BA, origem em
   outra UF, destinatário com CNPJ. O resto é recusado com o motivo.
4. **Cálculo por item**, com os dois métodos, alíquota interna por NCM e
   vigência, crédito destacado ou crédito de referência (presunção) quando uma
   pessoa autoriza. Precisão intermediária preservada; arredondamento a duas
   casas só no resultado.
5. **Agrupamento por CFOP e alíquota** em cada nota.
6. **Nada é liberado automaticamente.** Toda nota nasce em revisão. Item com
   exceção fica sem decisão até alguém decidir, com motivo. Só nota aprovada
   entra no total a recolher.
7. **Memória de cálculo** por item (seção 7 da Fonte A): valor da operação e
   parcelas, alíquota interestadual, tipo e valor do crédito, alíquota interna,
   divisor, base, ICMS interno, valor a recolher, o comparativo com o outro
   método, pendências, decisão, quem decidiu e por quê.
8. **Totais por empresa e competência**, com vencimento de referência e
   simulação da redução.
9. **Tabela de alíquotas editável por vigência, UF e produto.**
10. **Exportação em Excel** com a memória completa.
11. **Lançamento manual para conferência** (calculadora; não grava).
12. **Conferência de várias chaves coladas:** valida os 44 dígitos e o dígito
    verificador, aponta repetidas, já importadas e as que ainda precisam do XML.
13. **DANFE** da nota, gerado do XML guardado.

## Fora do escopo

- **Buscar a nota na SEFAZ pela chave.** A chave não traz os produtos; o XML só
  sai pela distribuição de DF-e com o certificado A1 do destinatário. É uma
  entrega própria (certificado, mTLS, armazenamento) e não foi feita.
- **Antecipação total / substituição tributária com MVA.** Item com indício de
  ST vai para decisão humana e, na prática, fica fora do cálculo.
- Emissão de DAE ou guia; escrituração; cruzamento com o Anexo 1 do RICMS/BA.
- Lançamento manual gravado; importação de .zip.
- Acesso de clientes: a ferramenta é da equipe fiscal (opção marcada na Fonte B).

## Regras implementadas

### Crédito

- Há ICMS próprio destacado (`vICMS` > 0): usa o valor da nota.
- Não há destaque e a presunção **não** foi autorizada para a nota: o item não
  tem cálculo. Fica sem valor — não vira zero.
- Não há destaque e a presunção foi autorizada: crédito = valor da operação ×
  alíquota interestadual de referência (4% para origem da mercadoria 1, 2, 3
  ou 8; senão a da UF de origem). O crédito de referência não é arredondado
  antes da conta (P-08).

### Pendências do item

| Tipo | Efeito | Casos |
|---|---|---|
| Impede | Não há como mandar calcular enquanto durar | finalidade não informada; sem destaque e sem presunção; sem alíquota interna ou interestadual vigente; NCM, CFOP, CST, origem ou valor faltando; valor da operação ≤ 0; resultado negativo |
| Decisão | Há número, mas uma pessoa decide se vale, com motivo | indício de ICMS-ST (CST 10, 30, 60, 70; CSOSN 201, 202, 203, 500; ST destacada); isento, não tributado ou suspensão (CST 40, 41, 50; CSOSN 103, 300, 400); redução de base (CST 20); diferimento (CST 51); monofásico ou "outras" (CST 02, 15, 53, 61, 90; CSOSN 900); FCP; CFOP que não começa por 6; alíquota destacada diferente da de referência; NF-e complementar, de ajuste ou devolução |
| Aviso | Só informa | crédito de referência calculado; fornecedor do Simples Nacional ou MEI |

Item sem pendência de bloqueio é **proposto** como "calcular". A nota continua
em revisão até alguém aprovar.

### Aprovação

Exige: regime tributário da empresa informado (a nota não traz esse dado) e
nenhum item sem decisão. A aprovação reconfere a nota com a tabela vigente.
Nota aprovada é imutável; para mudar, reabre-se com motivo.

### Totais

Soma, em centavos, dos itens com decisão "calcular" de notas aprovadas. O que
está em revisão aparece à parte. A redução (20%, parâmetro) é **simulação**:
só para empresa marcada como Simples Nacional e só sobre itens de revenda; o
sistema não verifica elegibilidade nem pagamento no prazo.

## Decisões de projeto

- **D-01** Os dois métodos convivem e o escolhido é sempre explícito (acima).
- **D-02** Resultado negativo nunca entra na soma: o item só pode ficar fora do
  cálculo. A Fonte A pede "sinalizar valores negativos; não liberar".
- **D-03** A soma do grupo e da nota é a soma dos itens, não uma conta refeita
  sobre a base agrupada (pode diferir em centavos).
- **D-04** Competência = mês da emissão, editável por nota (P-07).
- **D-05** Permissões separadas para importar, revisar, aprovar, configurar e
  exportar; nenhuma entra no padrão de usuário novo (constituição, III).
- **D-06** Linha de alíquota não muda de valor: nova vigência encerra a
  anterior na véspera. Nota aprovada guarda a alíquota usada e não muda.

## Pendências para a equipe fiscal da JB

Nada abaixo foi decidido pelo desenvolvimento. O sistema funciona com os
padrões descritos, todos alteráveis, e marca os números como cálculo de apoio.

- **P-01 Método.** Qual fórmula vale, e para quê? Base por dentro para tudo
  (Fonte A), diferença simples para revenda (Fonte B e redação do art. 12-A),
  ou uma por finalidade? A diferença no exemplo é de R$ 34,81 por R$ 1.000,00.
- **P-02 Crédito de referência.** Em quais hipóteses a presunção é autorizada
  (fornecedor do Simples, qualquer nota sem destaque, nunca)? Hoje quem importa
  ou revisa autoriza nota a nota e isso fica na trilha.
- **P-03 Valor da operação.** Entram frete, seguro, outras despesas e IPI, e sai
  o desconto? É o padrão atual, por parâmetro.
- **P-04 Redução de 20% e vencimento no dia 25.** Condições do art. 274 e do
  art. 332 do RICMS/BA: sobre o que incide, limites e exceções. Hoje é
  simulação sobre itens de revenda de empresas do Simples.
- **P-05 Uso e consumo e ativo imobilizado.** Há parecer da DITRI (23.764/2012)
  citando o art. 272 do RICMS/BA sobre dispensa do diferencial de alíquotas
  para ME e EPP. Esses itens devem ser calculados, e por qual método? Hoje a
  finalidade só classifica o item.
- **P-06 Tabela de alíquotas.** Validar a carga inicial (7% Sul e Sudeste menos
  ES, 12% demais, 4% importados, 20,5% interna geral desde 07/02/2024) e
  informar os produtos com alíquota interna diferente.
- **P-07 Competência.** Mês da emissão ou da entrada da mercadoria?
- **P-08 Arredondamento do crédito de referência.** Mantida a precisão
  intermediária pedida na Fonte A; arredondar o crédito a centavos antes da
  conta muda o resultado em um centavo em cerca de um terço dos casos.
- **P-09 Antecipação total / ST.** É a próxima etapa desejada?
- **P-10 Consulta à SEFAZ pela chave.** Depende do certificado A1 de cada
  empresa. Há interesse, e de quais clientes?

## Critérios de aceite

- CA-01 Os três exemplos da seção 5 da Fonte A reproduzem todas as linhas da
  memória (169,81; 106,92; 207,55).
- CA-02 O exemplo da Fonte B reproduz 1.650,00, 1.350,00 e 850,00, o total de
  3.770,00, a redução de 754,00 e o total de 3.016,00.
- CA-03 Reimportar a mesma chave não altera a nota existente.
- CA-04 Nota de origem BA, cancelada, de entrada ou que não seja modelo 55 não
  é gravada.
- CA-05 Item sem crédito fica sem valor (não zero) e sem decisão.
- CA-06 Item com exceção não é proposto; decidir exige motivo; a aprovação é
  barrada enquanto houver item sem decisão ou regime não informado.
- CA-07 Quem só consulta não importa, não revisa e não exporta; quem revisa
  não aprova nem altera a tabela. Tentativa negada fica na trilha de uso.
- CA-08 Mudança de parâmetro, decisão, aprovação, reabertura e exclusão gravam
  o evento na mesma transação; o banco recusa alterar evento, alíquota e item
  de nota aprovada.
- CA-09 Mudar a tabela não altera nota aprovada.
- CA-10 Texto vindo do XML não vira fórmula na planilha exportada.
