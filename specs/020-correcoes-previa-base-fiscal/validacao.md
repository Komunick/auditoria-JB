# Validação da spec 020

Concluída em **30/10/2026**, branch `codex/020-correcoes-previa-base-fiscal`,
base `dev@844db6ffcea0141aeea0aef0e5073a99ee295486`. Implementação local,
sem commit, push, merge, deploy ou acesso à produção nesta entrega.

## Critério → verificação → resultado

| Critério | Verificação | Resultado |
|---|---|---|
| Origem imutável | Fonte relida, SHA da prévia/relatório, cabeçalhos, conjunto de IDs e A:F conferidos; reordenação/linhas ocultas | Aprovado |
| Propostas explícitas | Vazio preserva; inválidas não sofrem fallback/truncamento; original/proposta/efetivo/célula separados | Aprovado |
| Duplicidades | Recalculadas após correção; manter/ignorar justificados; grupo integralmente ignorado; colisões novas | Aprovado |
| ZERADAS | Ausência estrutural preservada; contato cadastrado não tratado como vazio a sobrescrever; sem movimento não inativa | Aprovado |
| Cadastro somente leitura | mode=ro, query_only, campos mínimos e lotes na mesma transação; WAL e alteração concorrente entre lotes | Aprovado |
| Banco ausente/inválido | Ausente não cria pasta/banco; ilegível/incompatível falha sem classificar todos como novos | Aprovado |
| Autorização | 401 sem sessão; 403 sem cada permissão cumulativa; usuário autorizado e administrador | Aprovado |
| Sem carga | Store migratório proibido no teste HTTP, nenhum token, histórico/schema/cadastro preservados | Aprovado |
| Uploads e privacidade | Dois arquivos fechados/removidos em sucesso/erros; no-store; auditoria apenas com contagens | Aprovado |
| XLSX não confiável | Limites físicos por aba, dimensões falsas, IDs/células duplicadas, fórmulas, erros, mesclagens, macros, vínculos e DTD | Aprovado |
| Interface | Cinco resultados, filtros/paginação, detalhes e texto literal; respostas antigas descartadas após arquivo/sessão/permissão mudar | Aprovado |
| Regressão | Todos os 88 scripts de teste, com manifesto antes/depois | 86 aprovados, 2 pulados, 0 falhas; arquivos estáveis |

## Testes antes da implementação

- `test_correcoes_base_fiscal.py`: RED por módulo inexistente; GREEN com origem,
  propostas, validação de campos, duplicidade e comparação sem mutar argumentos.
- `test_previa_cadastro_fiscal.py`: RED por módulo inexistente; GREEN com seleção
  mínima, parâmetros SQL, URI codificada, conexão fechada, ausência/incompatibilidade
  e snapshot consistente entre lotes mesmo com atualização concorrente no WAL.
- `test_web_base_fiscal_importacao.py`: RED por rota inexistente; GREEN com
  autenticação/autorização, fonte/relatório/hash, 409/413/422/503, falha inesperada,
  limpeza, no-store, auditabilidade mínima e ausência de escrita cadastral.
- `test_base_fiscal_importacao_ui.py`: RED pela ausência dos controles;
  GREEN com fluxo multipart, resposta JSON, filtros/detalhes, pedidos duplicados,
  retries, troca de ambos os arquivos, sessão/identidade/permissões e conteúdo literal.

Revisões e contraprovas corrigiram antes do aceite:

1. Busca por proposta inválida quando o valor efetivo está vazio: RED/GREEN;
   a busca também considera o conteúdo proposto.
2. Erro Excel da fonte preservado como texto em A:F: RED/GREEN e contraprova
   independente. Texto original como `#N/A` pode ser conservado enquanto o CNPJ
   é corrigido; fórmula/célula de erro efetiva continua recusada.
3. CNPJ numérico de 400 dígitos em XML: RED por OverflowError e GREEN; passa a
   pendência explícita, sem erro 500 nem recuperação inventada de zeros.
4. Data da consulta: RED/GREEN; apresentação pt-BR no horário de Salvador,
   com ausência/data inválida explicitamente indisponível.

Revisão independente final sem achados pendentes. Sintaxe JavaScript e
`git diff --check` aprovados. Checagem dos arquivos alterados/novos sem os dados
privados conhecidos do briefing; todas as fixtures são fictícias.

## Regressão completa

Executados os **88** scripts `tests/test_*.py` com o Python do venv do projeto:
**86 aprovados, 2 pulados, 0 falhas**. Os pulos são `test_fdb_reader.py` e
`test_web_produtos_fdb.py`, pela ausência do Firebird opcional. O teste desktop
e os testes Node passaram. `changed_during_run=[]`: nenhum arquivo funcional
ou de teste mudou entre o manifesto inicial e o final. Não foi necessário
repetir a suíte após esse resultado; somente documentação foi finalizada.

Logs e manifestos privados, fora do Git:
`tmp/validacao-spec020-20261030-083940/` na pasta de trabalho.

## Aceite no navegador local

Aplicação em `127.0.0.1:8620`, pasta de dados descartável e usuário fictício.
Fonte e relatório revisado com **7 registros** produziram:

- 3 novas empresas candidatas a inclusão;
- 1 já cadastrada;
- 1 conflito com o cadastro;
- 1 pendência;
- 1 ocorrência ignorada com justificativa.

Conferidos os detalhes de CNPJ/regime/responsável/contato antes e depois,
referências G3/I3/J3/K3, filtro de conflito, cadastro encontrado e sua revisão.
Sem erros/avisos no console e sem sobreposição na apresentação inspecionada.
O hash do dump lógico do banco de clientes ficou idêntico antes/depois, com
2 clientes, 2 eventos de alteração, 0 importações e schema 3 preservados.
Prévia limpa e servidor/aba de QA encerrados ao final.

Evidências privadas em `tmp/qa-spec020/`: `aceite-navegador.json`, snapshots
cadastrais antes/depois e `previa-importacao-020.jpg`.

## Limites

A entrega prepara e compara propostas; **não implementa carga efetiva**.
Não associa usuários/carteiras nem aplica regime, sem movimento ou obrigações.
Uma futura carga precisará de autorização, revalidação do cadastro e persistência
transacional com trilha. Sem migração, dependência ou processo produtivo novo.
