# Validação — Spec 027

Data: 26/11/2026. Base: `origin/dev` em `de9a20a`. Ambiente: Windows 11,
Python 3.11.9, dados sintéticos.

## Suíte

| Momento | OK | Pulados | Falhas |
|---|---|---|---|
| Antes (base) | 112 | 2 | 0 |
| Depois | 115 | 2 | 0 |

Os três arquivos novos: `test_antecipacao_ba.py`, `test_antecipacao_store.py` e
`test_web_antecipacao.py`. Os dois pulados são os mesmos da base (Firebird e
interface Qt).

## Critérios de aceite

| Critério | Verificação | Resultado |
|---|---|---|
| CA-01 exemplos da Fonte A | `test_antecipacao_ba.py`, pelo cálculo direto e pelo XML; `test_web_antecipacao.py`, pela API | Passou: 169,81, 106,92 e 207,55, com todas as linhas da memória |
| CA-02 exemplo da Fonte B | `test_antecipacao_ba.py` | Passou: 1.650,00, 1.350,00, 850,00; total 3.770,00; redução 754,00; 3.016,00 |
| CA-03 duplicidade | store e web | Passou: segunda importação volta "duplicada" e o método da primeira não muda |
| CA-04 escopo | núcleo, store e web | Passou: origem BA, destino fora da BA, cancelada, NFC-e, nota de entrada, sem itens e destinatário pessoa física |
| CA-05 sem crédito não vira zero | núcleo e store | Passou: valor fica nulo e o item sem decisão |
| CA-06 exceção exige decisão | núcleo, store e web | Passou: ST, isento, redução de base, diferimento, FCP, CFOP interno, alíquota divergente e NF-e não normal; motivo obrigatório; aprovação barrada |
| CA-07 permissões | web | Passou: 401 sem login; 403 sem a aba e sem o slug; negativa na trilha de uso |
| CA-08 trilha e imutabilidade | store | Passou: evento na mesma transação (falha no segundo item desfaz o primeiro); SQL direto de UPDATE/DELETE recusado em evento, alíquota e item de nota aprovada |
| CA-09 tabela não altera aprovado | store e web | Passou |
| CA-10 fórmula no Excel | web | Passou: descrição iniciada por `=` sai com apóstrofo |

## Os testes pegam o erro?

Seis alterações erradas foram aplicadas ao núcleo, uma por vez, e os testes
rodados em seguida. As seis foram detectadas:

1. base sem abater o crédito;
2. item com exceção proposto automaticamente;
3. crédito de referência arredondado antes da conta;
4. ausência de destaque tratada como crédito zero;
5. origem 6 (importado sem similar) calculada a 4%;
6. meio centavo arredondado para baixo.

A sexta só passou a ser detectada depois de um teste acrescentado para isso.

## Tela

Fluxo exercitado em Chromium sem interface gráfica, contra o servidor local
(127.0.0.1) com dados sintéticos: abrir a aba, abrir uma nota com seis itens em
seis grupos de CFOP e alíquota, definir o regime, tentar aprovar com item
pendente (barrado), tentar excluir sem motivo (barrado), decidir as exceções,
trocar o método e ver o valor mudar (R$ 4.075,47 para R$ 3.240,00) e voltar,
aprovar, ver os totais, exportar a planilha, usar a calculadora, conferir
chaves, abrir a tabela de alíquotas e a Central. Nenhum erro de JavaScript; as
duas únicas mensagens de console são as respostas 409 e 422 provocadas de
propósito. Temas claro e escuro.

## Integração com o redesign (27/11/2026)

Base: `origin/dev` em `65458ec` (redesign da spec 028), juntada à branch por
merge. Mesmo ambiente.

| Critério | Verificação | Resultado |
|---|---|---|
| Suíte depois do merge | 118 scripts `tests/test_*.py` | 116 OK, 2 pulados (Firebird), 0 falhas |
| Aba 11 no menu novo | `test_web_antecipacao.py`: grupo fiscal, `data-numero="11"`, selo `11` e palavras-chave em `app.js` | Passou; o teste falha com o botão em outro grupo e sem as palavras-chave |
| Tela no visual novo | Chromium sem interface gráfica, servidor local (127.0.0.1), três notas sintéticas: lista, memória de cálculo, tema escuro, busca "icms" e gaveta em 390 px | Título "Antecipação ICMS-BA" no cabeçalho, botão ativo no grupo "Fiscal & Emissão", busca acha a aba 11, sem rolagem horizontal da página, nenhum erro de console |
| Ajustes visuais | Mesma conferência, antes e depois do CSS | Títulos internos com espaço acima; pendências e botão "Selecionar itens" na fonte da interface |

A tela de celular passou a ser conferida (390 px); a tabela de notas rola na
horizontal dentro do próprio quadro.

## Não testado

- **XML reais.** Tudo foi feito com XML sintético. Notas reais têm variações de
  leiaute (grupos de ICMS menos comuns, vários itens com rateio de frete,
  notas com IPI) que precisam de uma conferência com arquivos de clientes,
  fora do Git, antes do uso.
- **Correção fiscal da regra.** Os testes provam que o programa faz as contas
  pedidas nos dois documentos, não que elas são as devidas. Isso é a
  homologação da equipe fiscal (P-01 a P-08).
- **Volume.** Não houve medição com centenas de notas grandes num envio.
- **Navegador do usuário.** A conferência foi em Chromium; não houve teste em
  outro navegador nem em celular de verdade (só na largura de 390 px).
- **Servidor de produção.** Nada foi implantado.

## Observação sobre a ordem dos testes

A constituição pede o teste antes da implementação. Nesta entrega os testes de
cada camada foram escritos logo depois do módulo correspondente, na mesma
sessão, e não houve o registro de uma falha anterior à implementação. A
verificação por mutação acima foi feita para compensar essa ordem.
