# Tasks: Cadastro de Clientes, Cofre de Senhas e Vencimentos

Testes antes da implementação em cada fase. `[US#]` = história da spec.

## Fase 1 — Núcleo

- [x] T001 [US2] `tests/test_clientes.py`: documento (CNPJ/CPF, número de célula com zeros à esquerda), situação de campo e variações de grafia, faixas de vencimento.
- [x] T002 [US2] `core/clientes.py`.
- [x] T003 [US4] `tests/test_cofre.py`: ida e volta, nonce único, AAD trocado falha, chave errada falha, chave antiga decifra, sem chave = indisponível, chave fraca recusada.
- [x] T004 [US4] `core/cofre.py`.
- [x] T005 [US3] `tests/test_planilha_clientes.py`: planilha sintética com cabeçalho na linha 2, cores, linhas ocultas, colunas sem cabeçalho, duplicados, datas impossíveis.
- [x] T006 [US3] `core/planilha_clientes.py`.
- [x] T007 [US6] `tests/test_certificados.py`: `.cer` DER/PEM e `.pfx` sintéticos (CN no padrão ICP-Brasil), senha errada.
- [x] T008 [US6] `core/certificados.py`.
- [x] T009 [US8] `tests/test_coletor_certificados.py`: pasta sintética com os casos do relatório; a saída não contém senha.
- [x] T010 [US8] `core/coletor_certificados.py` + `coletar-certificados.py`.

## Fase 2 — Persistência

- [x] T011 `tests/test_clientes_store.py`: cadastro, revision, trilha append-only, segredo cifrado no disco, revelação com trilha na mesma transação, limite por hora, importação em transação, coleta casando por CNPJ, renovação, vencimentos.
- [x] T012 `ferramentas/clientes_store.py`.
- [x] T013 `ferramentas/relatorio_clientes.py` (exportação sem senhas).

## Fase 3 — Web

- [x] T014 `tests/test_web_clientes.py`: 401/403, slugs fora do padrão, desbloqueio, revelação auditada, 503 sem chave, prévia e confirmação, coleta, exportação sem senha, nenhuma senha em arquivo da pasta de dados.
- [x] T015 Permissões, ações da trilha, `caminho_db_clientes`, rotas e registro no servidor.
- [x] T016 `webui/clientes.js`, aba na lateral, aviso de vencimentos no topo, resumo no Início.

## Fase 4 — Fechamento

- [x] T017 Suíte inteira; conferência no navegador com dados sintéticos (porta 8612, pasta descartável).
- [x] T018 README-servidor: chave do cofre, backup separado, coletor.
- [x] T019 `requirements.txt` com `cryptography`.
