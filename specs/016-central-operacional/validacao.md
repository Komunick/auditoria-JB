# Validação — Central operacional

Executada em 28/10/2026, em ambiente local isolado, com dados exclusivamente
sintéticos. Base: `dev` em `7207040`. Nenhum banco de produção foi aberto ou
alterado. Não há migração de schema nem dependência nova nesta entrega.

## Testes antes da implementação

- Store: `test_painel_tarefas.py` falhou inicialmente por ausência de
  `painel_tarefas`; passou após implementação da consulta compartilhada.
- HTTP: `test_web_painel.py` recebeu 422 na rota ainda ausente `/painel`;
  passou após inclusão da rota e autorização.
- UI: `test_central_ui.py` falhou com `CentralUI` ausente; passou após
  implementação. Regressão adicional de troca de usuário falhou antes da
  vinculação das respostas à sessão e passou após a correção.

## Critério → verificação → resultado

| Critério | Verificação | Resultado |
|---|---|---|
| Totais independentes da página | Store com conjunto maior que a página e contagens por situação, prazo e conferência | Passou |
| Mesmo recorte entre painel, lista e Excel | HTTP percorre as nove filas e compara os IDs retornados/exportados | Passou |
| Escopo e substituições | Store e HTTP com pessoa, gestor, substituto, acesso global, acesso negado e anônimo | Passou |
| Data consistente | HTTP exige uma única captura de hoje; store compara limites de hoje/próximos dias e substituição | Passou |
| Consulta consistente | Transação de leitura começa antes do escopo; totais, distribuição, fila e DTO usam o mesmo snapshot dos dados de tarefas | Revisado |
| Busca e validação | Texto literal, escape de curingas, limite de 200 caracteres, filtros desconhecidos e paginação inválida | Passou |
| Navegação contextual | UI verifica filtros/filas/detalhe e impede acesso sem permissão | Passou |
| Respostas concorrentes | UI ignora resposta antiga, erro antigo e resposta de outra sessão | Passou |
| Confirmação de importação | UI só conclui após sucesso da API; rejeição não avança a etapa | Passou |
| Regressão completa | 76 scripts `tests/test_*.py`, cada um em subprocesso separado | 74 passaram; 2 pulados; 0 falhas |
| Sintaxe e diff | `node --check` nos três scripts JS alterados e `git diff --check` | Passou |

Os dois scripts pulados foram `test_fdb_reader.py` e
`test_web_produtos_fdb.py`: o motor opcional `vendor/firebird25` não está
instalado neste ambiente. Os testes de UI com Node executaram normalmente.

## Conferência no navegador

Servidor local em loopback, dados temporários e envio de e-mail desligado:

- Administrador visualizou 36 tarefas, 34 pendências e 9 atrasadas, mesmo com
  apenas 10 itens na primeira página. Competências anteriores permaneceram
  visíveis na entrada.
- Cartão Atrasadas abriu fila de 9 itens sem mudar os indicadores. A lista
  completa manteve o filtro; o detalhe abriu e o Excel baixado continha os
  mesmos 9 registros.
- Cliente fictício + busca reduziram painel e agenda a 2 tarefas. Retornar à
  Central preservou os filtros e atualizou os dados.
- Fila Sem vencimento apresentou 12 pendências em duas páginas, sem classificar
  essas ocorrências como atrasadas.
- Usuário executor viu apenas suas 18 tarefas, com 6 atrasadas. Usuário sem
  `aba.tarefas` viu somente seu atalho autorizado, sem os indicadores.
- Importação sintética percorreu Escolher arquivo, Conferir prévia e Concluído;
  esta última etapa apareceu após confirmação real do servidor local.
- Temas claro/escuro conferidos. Filtros recolhíveis funcionaram por teclado.
  Em viewport de 390 × 844, cartões e fila permaneceram acessíveis e não houve
  rolagem horizontal no documento (largura útil e conteúdo: 380 px).
- Nenhum erro ou aviso de console na conferência final. Servidor e aba de teste
  foram encerrados depois da validação.

## Revisão e limites

Revisão independente encontrou uma corrida na confirmação da importação:
trocar arquivo ou setor durante o envio poderia reaproveitar o resultado da
seleção anterior. Corrigido com bloqueio dos controles principais durante o
envio e validação de geração/sessão antes de sucesso, erro e desbloqueio.
Revisão final não identificou bloqueios restantes.

A distribuição representa pendências atuais, não produtividade histórica.
A inspiração vem das referências públicas registradas na spec; não representa
integração com fornecedores. A preparação/importação da carteira real e as
pendências do catálogo fiscal continuam separadas desta entrega.

O aceite cobre implementação e validação local. Merge para `dev`, promoção
para `main` e implantação exigem as etapas seguintes do fluxo do projeto.

## Correção local do catálogo após revisão — 28/10/2026

O catálogo era carregado somente na primeira montagem. Reabrir o Início ou
usar Atualizar consultava apenas o painel, deixando novos clientes, setores e
usuários ausentes dos filtros até um reload da página.

As duas ações agora renovam primeiro o catálogo e depois o painel. As opções e
os filtros aplicados ainda válidos permanecem; opções removidas ou inativas
deixam de filtrar. Catálogos antigos e respostas de sessão encerrada são
descartados, assim como respostas anteriores do painel durante a renovação.

- RED: `test_central_ui.py` reproduziu a ausência de consulta ao catálogo no
  evento de reabertura, antes de alterar `inicio.js`.
- GREEN: teste com DOM sintético e eventos reais confirma novos clientes sem
  reload nas duas ações, preservação dos filtros válidos, retirada dos inválidos,
  renovação do escopo sem opções duplicadas, catálogo concorrente e fim de sessão.
- Passaram: `test_central_ui.py`, `test_tarefas_ui.py`, `test_painel_tarefas.py`
  e `test_web_painel.py`; sintaxe JavaScript e `git diff --check` aprovados.

Esta rodada não executou suíte completa, navegador real, merge, push ou deploy.
Nenhum acesso à arm07 ou a seus dados/configurações foi realizado.
