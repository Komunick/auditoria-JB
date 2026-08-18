# Tasks: Patrimônio — Bens e Responsabilidade

**Input**: documentos em `/specs/004-patrimonio/`

**Tests**: obrigatórios. Em cada fatia, escrever o teste, observar a falha e só
então implementar. Padrão `main()` + `OK/FALHOU` do repositório.

## Phase 1 — Fundação compartilhada

- [x] P001 Extrair `sanitizar_texto`, `FORMATO_MOEDA` e o salvamento atômico
  de `ferramentas/relatorio_conciliacao.py` para
  `src/auditoria_fiscal/core/planilha_segura.py`; fazer o exportador da
  conciliação importar de lá sem mudar comportamento; suíte da conciliação
  continua verde.
- [x] P002 Adicionar `caminho_db_patrimonio()` em `web/infra.py`, abaixo de
  `AUDITORIA_WEB_DADOS`.

**Checkpoint**: conciliação intacta, caminho de dados pronto.

---

## Phase 2 — Núcleo puro

- [x] P003 Criar `tests/test_patrimonio.py` com etiqueta, CPF, transições de
  situação válidas e inválidas, baixa terminal, dois níveis de hierarquia e o
  teste de limites arquiteturais.
- [x] P004 Criar `src/auditoria_fiscal/core/patrimonio.py` com tipos puros,
  formatação de etiqueta, validação de CPF, catálogo de tipos/conservação e a
  máquina de transições.

**Checkpoint**: regra de negócio testável sem servidor.

---

## Phase 3 — Persistência

- [x] P005 Criar `tests/test_patrimonio_store.py` com schema idempotente,
  etiqueta sequencial e imutável, série única, dois níveis, um responsável
  ativo por vez sob concorrência, movimentação append-only, baixa terminal e
  revision otimista.
- [x] P006 Criar `src/auditoria_fiscal/ferramentas/patrimonio_store.py` com o
  schema de `data-model.md`, migrações idempotentes, WAL, busy timeout,
  triggers de imutabilidade e o índice parcial único da responsabilidade.
- [x] P007 Implementar cadastro, atribuição, devolução, manutenção,
  empréstimo, transferência e baixa — cada uma gravando situação e
  movimentação na mesma transação.
- [x] P008 Implementar inventário: abrir congelando o universo, conferir,
  fechar e consultar sessões anteriores.
- [x] P009 Implementar consultas com filtros por allowlist, paginação e o
  detalhe com histórico de responsabilidades e movimentações.

**Checkpoint**: domínio completo e concorrência coberta.

---

## Phase 4 — API e portal

- [x] P010 Adicionar ao `tests/test_web_permissoes.py` o catálogo dos seis
  slugs, o padrão de usuário novo e a negação da aba.
- [x] P011 Criar `tests/test_web_patrimonio.py` com 401, 403, cadastro,
  movimentação, inventário, filtros e trilha.
- [x] P012 Adicionar `GRUPO_PATRIMONIO` e os seis slugs em `web/permissoes.py`;
  incluir apenas `aba.patrimonio` em `PADRAO_NOVO_USUARIO`.
- [x] P013 Adicionar as ações auditáveis em `web/auditoria.py`, separando
  cadastro, movimentação, baixa, inventário e download.
- [x] P014 Criar `web/rotas_patrimonio.py` com as rotas de leitura, cadastro,
  movimentação, inventário e saídas.
- [x] P015 Registrar o router antes do mount estático em `web/servidor.py`.
- [x] P016 Adicionar botão, section e script da sétima ferramenta em
  `webui/index.html`, sem renumerar as seis anteriores.
- [x] P017 Criar `webui/patrimonio.js` com as subtelas Bens, Responsáveis,
  Inventário e Relatórios, reusando os helpers de `webui/app.js`.

**Checkpoint**: a sétima ferramenta existe ponta a ponta.

---

## Phase 5 — Saídas

- [x] P018 Criar `tests/test_relatorio_patrimonio.py` para a relação em Excel
  (colunas, valores numéricos, texto perigoso, falha sem arquivo parcial) e
  para o termo em PDF.
- [x] P019 Criar `ferramentas/relatorio_patrimonio.py` com a relação em Excel
  e o termo de responsabilidade em PDF, ambos sem dependência de FastAPI.
- [x] P020 Implementar as rotas de exportação e emissão de termo, auditadas.
- [x] P021 Implementar a área de relatórios em `webui/patrimonio.js`.

**Checkpoint**: saídas prontas e auditadas.

---

## Phase 6 — Etiqueta, polish e aceite

- [ ] P022 Implementar a etiqueta com QR e a folha de etiquetas para
  impressão. A rota de **leitura por etiqueta** (`GET /api/patrimonio/
  etiqueta/{etiqueta}`) já existe e tolera caixa e espaço do leitor; falta o
  desenho do QR e a folha imprimível.
- [x] P023 Atualizar `README.md` e `README-servidor.md` com a sétima
  ferramenta, permissões, `patrimonio.db` e backup.
- [ ] P024 Benchmark de SC-005 com 5 mil bens; otimizar índices se necessário.
- [ ] P025 Smoke no navegador: dois perfis, temas, tela estreita, cadastro,
  atribuição, devolução, inventário e downloads.
- [x] P026 Rodar toda a suíte e revisar o diff (sem Flask, iframe, `mktemp`,
  credencial, banco ou dado real).

## Dependencies

```text
Fase 1 -> Fase 2 -> Fase 3 -> Fase 4 -> Fase 5 -> Fase 6
```

## Notes

- Não marcar tarefa concluída só porque o código existe; o teste tem de passar.
- A etiqueta é impressa e colada: qualquer mudança na numeração é quebra de
  contrato com o mundo físico.
