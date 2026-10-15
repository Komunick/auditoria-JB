# Tasks: Emissão de NFS-e — Fase 1

**Input**: documentos em `/specs/006-emissao-nfse/`

**Tests**: obrigatórios. Em cada fatia, escrever o teste, rodar e ver falhar,
e só então implementar. Padrão `main()` + `OK/FALHOU` do repositório, dados
isolados por `AUDITORIA_WEB_DADOS`. Para cada teste, perguntar: "este teste
passaria com o comportamento errado?". Se passaria, ele não serve.

**Regra desta spec**: pendência da JB (JB-n) ou da documentação (Rn) nunca
vira valor padrão no código. Onde a decisão falta, o perfil fica pendente e a
DPS é recusada.

## Phase 0 — Pesquisa e fixtures

Nenhum código de produção nesta fase.

- [x] T001 **R1**: baixar de gov.br/nfse → Documentação atual o pacote
  `NFSe-ESQUEMAS_XSD-v1.01-20260209` e o
  `ANEXO_I-SEFIN_ADN-DPS_NFSe-SNNFSe-v1.01-20260209`; criar
  `specs/006-emissao-nfse/research.md` com URL, data e SHA-256 de cada
  arquivo; listar, para os grupos usados (`infDPS`, prestador, tomador,
  serviço, valores), tag, tipo, tamanho e obrigatoriedade; registrar a
  composição do identificador da DPS, o namespace, se `Signature` é
  obrigatória, os formatos de `dhEmi`, `dCompet` e decimais e o limite da
  discriminação. Atualizar a tabela "Da linha para a DPS" de
  `data-model.md` se algum nome diferir.
- [x] T002 **R2**: no Anexo B v1.01 e no Anexo I, achar o código de tributação
  nacional e o NBS que correspondem aos códigos do vídeo (item 08.01, CTISS
  0801-0/01, NBS 1.2201.11.00) e dizer se Salvador exige código municipal.
  Registrar a tabela de correspondência em `research.md`.
- [x] T003 **R3**: dizer se o grupo do IBS/CBS é obrigatório, opcional ou
  recusado na DPS de ME/EPP antes de 01/2027, e quais campos ele pede. Se
  for opcional, anotar a escolha como item de JB-8 em `research.md`.
- [x] T004 **R4**: registrar faixas e tamanhos da série e do número da DPS, a
  regra do `dCompet` (dia dentro do mês, limites passado e futuro) e o fuso
  de `dhEmi`. Se a proposta "primeiro dia do mês" não servir, corrigir
  `data-model.md` antes da Phase 2.
- [x] T005 Versionar os XSD em `dados/nfse/xsd/v1.01/` como foram
  publicados, com `LEIA-ME.txt` (URL, data do download, SHA-256 do zip).
- [ ] T006 Criar `tests/fixtures/nfse/` só com dados fictícios: perfil
  completo com `endereco_tomador = 'informar'`, perfil completo com
  `'omitir'`, perfil com cada pendência; planilha-modelo preenchida válida;
  planilha com um erro de cada regra; planilhas hostis (reaproveitar os
  geradores da conciliação); texto com três blocos; texto com prefixo de
  mensagem; texto com rótulo repetido e linha sem rótulo; texto com turma
  junto do aluno; texto com caracteres invisíveis. Nenhum dado do vídeo.

**Checkpoint**: leiaute fixado, correspondência de códigos registrada,
fixtures prontas.

---

## Phase 1 — Fundação compartilhada

- [x] T007 Criar `tests/test_documentos_br.py`: CPF (DV, repetidos, tamanho),
  CNPJ (DV, repetidos), decimal brasileiro (milhar, ambíguo recusado, fração
  de centavo, fórmula sem valor, célula numérica). Rodar e ver falhar.
- [x] T008 Criar `src/auditoria_fiscal/core/documentos_br.py` com as funções
  extraídas de `core/patrimonio.py` (`normalizar_cpf`) e
  `core/conciliacao_sefaz.py` (`normalizar_cnpj`, `para_decimal`), com erro
  neutro; os módulos de origem delegam, mantendo nomes, mensagens e
  exceções. `test_patrimonio*.py` e `test_conciliacao*.py` continuam
  verdes.
- [x] T009 Mover `validar_pacote_xlsx` para `core/planilha_segura.py`, com o
  mesmo nome reexportado em `core/conciliacao_sefaz.py`; suíte da
  conciliação continua verde.
- [x] T010 Adicionar `caminho_db_nfse()` e `pasta_origens_nfse()` em
  `web/infra.py`, abaixo de `caminho_db_patrimonio()`.

**Checkpoint**: patrimônio e conciliação intactos; validadores prontos para
a NFS-e.

---

## Phase 2 — Núcleo puro

- [ ] T011 Criar `tests/test_nfse.py`: normalização (acento, caixa,
  invisíveis, espaço não separável); `pendencias_do_perfil` lista cada
  campo vazio com a origem certa (JB-2, JB-8, R5) e não lista nada no
  perfil completo; não existe valor padrão para esses campos;
  `regra_aliquota` segue cada linha da tabela de `research.md`; validação do
  perfil recusa série fora de 1 a 49999, alíquota acima de 5% e regime
  especial diferente de 0 com ISS pelo Simples; modelo da discriminação
  aceita só os campos da lista, respeita a caixa e recusa campo
  desconhecido; turma resolvida por nome e por apelido, sem busca
  aproximada; turma pendente sem `c_trib_nac` ou `c_nbs`; limites arquiteturais
  (nenhum `core/nfse*.py` importa FastAPI, `httpx`, `socket`, `urllib`,
  `requests` ou `ssl`).
- [ ] T012 Criar `src/auditoria_fiscal/core/nfse.py` com tipos puros,
  catálogo de apontamentos, normalização, leitura de competência,
  pendências do perfil e montagem da discriminação.
- [ ] T013 Criar `tests/test_nfse_entrada.py`. Planilha: colunas por rótulo
  em qualquer ordem; coluna obrigatória ausente recusa o arquivo; coluna
  desconhecida vira aviso; linha vazia ignorada e contada; linha parcial
  mantida; fórmula sem valor = ausente; CPF numérico sem zero inicial;
  competência como data; proveniência com célula, rótulo e regra. Texto:
  separação em blocos; rótulos com caixa, acento, `:` e `-` variados; turma
  junto do aluno só quando é turma do perfil; prefixo de mensagem;
  rótulo repetido; linha sem rótulo em `nao_reconhecido`; CEP extraído;
  limite de 256 KB; proveniência com bloco e linha.
- [ ] T014 Criar `src/auditoria_fiscal/core/nfse_entrada.py`, chamando
  `validar_pacote_xlsx` antes do openpyxl.
- [ ] T015 Criar `tests/test_nfse_conferencia.py` com um caso que dispara e
  um que não dispara para cada código do catálogo; irmãos com o mesmo CPF
  permitidos; duplicata no lote aponta a primeira linha; duplicata contra o
  conjunto de chaves aprovadas recebido como entrada; endereço como aviso ou
  bloqueio conforme o perfil; valor ausente nunca vira zero; linha excluída
  não gera bloqueio nem entra na duplicata.
- [ ] T016 Criar `src/auditoria_fiscal/core/nfse_conferencia.py` (função
  pura: versão do perfil + linhas efetivas + chaves aprovadas → valores
  normalizados + apontamentos).
- [ ] T017 Criar `tests/test_nfse_dps.py`: XML de referência para linhas
  fictícias com os dois perfis (com e sem endereço); validação no XSD
  oficial versionado, sem rede; identificador da DPS; mesma entrada, mesmos
  bytes (gerar duas vezes); escape de `&`, `<`, apóstrofo e acento; valores
  com centavos; ambiente sempre produção restrita; sem `Signature`;
  recusa para perfil com pendência, linha com bloqueio e turma pendente; o
  XML inválido é detectado (teste com um campo obrigatório removido); o
  arquivo oficial ainda tem o padrão `^0{0,4}\d{1,5}$` da série e só esse
  padrão é trocado em memória (achado de `research.md`).
- [ ] T018 Criar `src/auditoria_fiscal/core/nfse_dps.py` com o gerador e a
  validação no XSD (resolvedor só local, `no_network`, contorno do padrão
  da série em memória).

**Checkpoint**: regra de negócio testável sem servidor e sem rede.

---

## Phase 3 — Persistência

- [ ] T019 Criar `tests/test_nfse_store.py`: schema idempotente (criar duas
  vezes); versões de perfil imutáveis; origem com o mesmo SHA-256
  reaproveitada; lote duplicado recusado e permitido depois de descarte;
  linha, correção, rodada, apontamento, DPS e evento recusam `UPDATE` e
  `DELETE`; correção preserva o bruto e muda o efetivo; exclusão e
  reinclusão; nova rodada a cada correção; aprovação tudo ou nada (falha
  injetada na segunda DPS deixa zero DPS, zero chaves, zero números e o lote
  em revisão); dois lotes com a mesma chave aprovados em duas conexões, só
  um passa; numeração sem repetição em aprovações concorrentes; número não
  volta após descarte; descarte de lote aprovado libera as chaves; revisão
  desatualizada recusada; aprovação recusada com perfil desatualizado, com
  pendência, com bloqueio e com lote vazio.
- [ ] T020 Criar `src/auditoria_fiscal/ferramentas/nfse_store.py` com o
  schema de `data-model.md`, migrações idempotentes, FK, WAL,
  `busy_timeout`, triggers de imutabilidade e os índices únicos parciais.
- [ ] T021 Implementar perfis: criar, criar versão (com turmas e apelidos),
  consultar versões e pendências.
- [ ] T022 Implementar importação: origem (arquivo gravado por hash antes do
  `COMMIT`), lote, linhas e primeira rodada numa transação.
- [ ] T023 Implementar correção, exclusão, reinclusão e reconferência, cada
  uma com evento e rodada nova na mesma transação.
- [ ] T024 Implementar aprovação (`BEGIN IMMEDIATE`, chaves, numeração, DPS,
  hash de aprovação, eventos) e descarte.
- [ ] T025 Implementar consultas com filtros por allowlist e paginação, e o
  detalhe do lote com valores efetivos, apontamentos e totais.

**Checkpoint**: domínio completo, concorrência e imutabilidade cobertas.

---

## Phase 4 — API e portal

- [ ] T026 Adicionar ao `tests/test_web_permissoes.py` o catálogo com os
  cinco slugs, o padrão de usuário novo (só `aba.nfse`) e a negação da aba.
- [ ] T027 Criar `tests/test_web_nfse.py`: 401 e 403 em cada rota da tabela
  do `plan.md`; fluxo completo (perfil → planilha → texto → corrigir →
  reconferir → aprovar → baixar); 409 com revisão velha e na aprovação
  concorrente; 422 com pendência e com bloqueio; 413 com arquivo e texto
  grandes; identidade sempre da sessão (campo de usuário no corpo é
  ignorado); varredura da trilha geral sem nenhum CPF ou nome das
  fixtures; o fluxo completo roda com `socket.socket.connect` trocado por
  função que falha.
- [ ] T028 Adicionar `GRUPO_NFSE` e os cinco slugs em `web/permissoes.py`
  (rótulo `8. Emissao de NFS-e`); incluir só `aba.nfse` em
  `PADRAO_NOVO_USUARIO`.
- [ ] T029 Adicionar as ações auditáveis em `web/auditoria.py`, separando
  perfil, importação, correção, aprovação, descarte e download, com detalhe
  só de IDs e contagens.
- [ ] T030 Criar `web/rotas_nfse.py` com as rotas do `plan.md`.
- [ ] T031 Registrar o router antes do mount estático em `web/servidor.py`.
- [ ] T032 Adicionar botão, section e script da oitava ferramenta em
  `webui/index.html`, sem renumerar as sete anteriores.
- [ ] T033 Criar `webui/nfse.js` com as subtelas Perfis, Importar e Lotes
  (revisão com apontamentos, correção com motivo, confirmação dos avisos,
  aprovação e descarte), reusando os helpers de `webui/app.js`.

**Checkpoint**: a oitava ferramenta existe de ponta a ponta.

---

## Phase 5 — Saídas

- [ ] T034 Criar `tests/test_relatorio_nfse.py`: planilha-modelo (abas,
  rótulos, CPF como texto, nenhum dado); resumo (colunas, moeda numérica,
  texto com `=`, `+`, `-` e `@` neutralizado, marca "DPS NÃO TRANSMITIDA");
  zip (um XML por DPS, nomes com a marca, SHA-256 de cada XML igual ao
  gravado); falha no meio não deixa arquivo parcial.
- [ ] T035 Criar `ferramentas/relatorio_nfse.py` com planilha-modelo,
  resumo e zip, sem dependência de FastAPI, usando `core/planilha_segura.py`.
- [ ] T036 Implementar as rotas de download auditadas e a área de downloads
  em `webui/nfse.js`.

**Checkpoint**: saídas prontas e auditadas.

---

## Phase 6 — Documentação e aceite

- [ ] T037 Atualizar `README.md` (oitava ferramenta, o que ela não faz:
  transmitir; permissões; `nfse.db`; origens) e `README-servidor.md`
  (backup de `nfse.db` e `dados_web/nfse/`).
- [ ] T038 Benchmark de SC-010: lote fictício de 500 linhas importado e
  conferido; otimizar índices se necessário.
- [ ] T039 Aceite de SC-009: lote fictício de 30 notas importado, revisado e
  aprovado por uma pessoa, cronometrado; registrar o tempo no PR.
- [ ] T040 Smoke no navegador: usuário com e sem cada permissão, temas, tela
  estreita, importação pelos dois caminhos, correção, aprovação, descarte e
  downloads.
- [ ] T041 Rodar a suíte inteira e revisar o diff (sem Flask, iframe, porta
  nova, credencial, banco, dado real ou chamada de rede).
- [ ] T042 Portão de produção: antes de usar com dados reais, confirmar que
  o endurecimento de segurança (Fase 0 do briefing) está no ar. Esta tarefa
  verifica; não implementa o endurecimento.

## Dependencies

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6
```

- T017/T018 dependem de T001–T005 (leiaute e códigos fixados).
- T013–T016 podem andar em paralelo com T001–T004, porque não dependem do
  leiaute.
- T028–T033 dependem do store (Phase 3).

## Depois da Fase 1 (não entra no aceite)

Dependem de respostas da JB e não bloqueiam este PR:

- Cadastrar o perfil real da creche: JB-2, JB-3, JB-8 e JB-11.
- Importador do formato de planilha da escola: JB-4.
- Decidir quem recebe `nfse.aprovar_emitir` e se há separação de funções:
  JB-5.
- Ajustar a regra de duplicata se a resposta de JB-12 permitir duas notas do
  mesmo aluno no mês.
- Definir o prazo de guarda das listas: JB-13.
- Nome da branch e do PR no Jira (AJB-1) ou no Linear: JB-10.

## Notes

- Não marcar tarefa concluída só porque o código existe; o teste tem de
  passar.
- Nenhuma fixture, exemplo ou mensagem de teste usa nome, CPF, endereço ou
  valor do vídeo.
- Nenhum código da Fase 1 transmite, assina ou lê certificado. Se uma
  tarefa parecer exigir isso, ela é da Fase 2.
