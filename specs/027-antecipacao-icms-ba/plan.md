# Plano — Spec 027 (Antecipação e DIFAL do ICMS-BA)

## Arquitetura

Mesma forma das abas 6 a 9: núcleo puro, persistência em banco próprio, uma
camada web fina e uma tela estática. Nenhuma dependência nova, nenhum processo
novo, nenhuma variável de ambiente nova.

| Camada | Arquivo | Papel |
|---|---|---|
| Núcleo | `core/antecipacao_ba.py` | fórmulas, tabela por vigência, pendências, chave de acesso, escopo da nota, simulação |
| Núcleo | `core/antecipacao_nfe.py` | leitor do XML a partir dos bytes do upload (sem entidade externa, sem rede) |
| Persistência | `ferramentas/antecipacao_store.py` | SQLite `antecipacao.db`, revisão, aprovação, totais, trilha |
| Saída | `ferramentas/relatorio_antecipacao.py` | planilha com memória, totais e metadados |
| Web | `web/rotas_antecipacao.py` | única camada que conhece FastAPI |
| Tela | `webui/antecipacao.js` | só formata; não calcula |

O leitor geral `core/nfe_xml.py` não foi alterado: ele alimenta o Livro de
Conferência e não traz destinatário, origem da mercadoria, parcelas por item,
FCP nem CRT. Mexer nele arriscaria as abas 1 a 4.

## Modelo de dados (`antecipacao.db`, schema 1)

- `aliquota` — tipo (interna, interestadual), UF, prefixo de NCM, percentual,
  vigência, base legal, quem criou e quem encerrou. Trigger: percentual e
  alcance imutáveis; sem exclusão.
- `configuracao` — método sugerido, parcelas do valor da operação, percentual
  da redução simulada, dia do vencimento de referência.
- `empresa` — CNPJ destinatário, nome e regime tributário (informado por pessoa).
- `nota` — chave (UNIQUE), hash do XML, participantes, UF, emissão, competência,
  método, presunção, parcelas, estado, soma em centavos, `revision`.
- `item` — dados lidos da nota (centavos; ausência = NULL), finalidade,
  decisão (origem, motivo, autor, momento), pendências e memória (JSON),
  valor a recolher (NULL quando não há cálculo). Trigger: imutável enquanto a
  nota está aprovada.
- `evento` — trilha append-only, gravada na mesma transação da mudança.

Arquivos: `antecipacao/origens/<sha256>.xml`, imutáveis.

## Permissões e trilha de uso

Slugs: `aba.antecipacao`, `antecipacao.importar`, `.revisar`, `.aprovar`,
`.configurar`, `.exportar`. Ações de auditoria com os mesmos nomes, mais
`antecipacao.danfe`. O detalhe da trilha de uso leva id e contagem, não valor.

## Riscos e mitigação

- **Número errado com cara de certo.** Mitigado por: método explícito e
  comparativo na memória; nada aprovado sozinho; aviso de homologação na tela e
  na planilha; pendências P-01 a P-10 abertas na spec.
- **XML de terceiro.** Parser sem entidade externa, limite de 5 MB por arquivo
  e 200 arquivos por envio; texto escapado na tela e neutralizado no Excel.
- **Concorrência.** `revision` otimista em toda mutação de nota.
- **Tabela desatualizada.** Vigência por linha, base legal obrigatória e
  memória com a alíquota usada.

## Implantação

Código e tela apenas. O banco é criado na primeira abertura. Incluir
`antecipacao.db` e `antecipacao/origens/` no backup (README-servidor.md). Depois
do deploy, o administrador concede as permissões a quem for usar.
