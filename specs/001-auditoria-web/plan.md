# Plano — Auditoria Fiscal Web

**Data**: 2026-07-14 · **Spec**: [spec.md](./spec.md)

## Arquitetura

- **Backend**: FastAPI + uvicorn (novas deps: fastapi, uvicorn, python-multipart;
  httpx só para testes). Pacote novo `src/auditoria_fiscal/web/` que IMPORTA o
  core/ferramentas existentes — o core não conhece a web (spec FR-010).
- **Frontend**: estático sem build em `webui/` (HTML + CSS com variáveis +
  JS vanilla, fetch/polling), servido pelo próprio FastAPI. Tema claro/escuro
  com as cores mapeadas de `ui/tema.py` (claro: fundo #FFFFFF, texto #23232F,
  destaque #26263A, dourado-texto #9C874F; escuro: fundo #17171F, papel
  #1E1E29, texto #E8E6F0, destaque/dourado #B8A166; marca TINTA #26263A,
  DOURADO #B8A166), preferência em localStorage + prefers-color-scheme.
  Logo JPEG base64 de `ui/logo.py` vira data-URI/arquivo estático + favicon.
- **Dados do servidor**: pasta `dados_web/` (gitignored): `auditoria_web.db`
  (usuários + sessões de login), `conferencia.db` (o MESMO ConferenciaStore,
  com `caminho_db` apontado para cá — passa a ser compartilhado no servidor),
  `sessoes/<id>/` (uploads por sessão de trabalho), `historico_produtos.csv`.
- **Autenticação**: usuários em SQLite (hash PBKDF2 + salt, stdlib), cookie
  HttpOnly com token aleatório; bootstrap do primeiro admin quando não há
  usuário. O usuário logado substitui o `getpass.getuser()` nas correções/
  sobrescritas/conferências.
- **Sessões de trabalho + jobs**: registro em memória {id → estado} com
  uploads em disco; processamento em `threading.Thread`, status por polling
  (`GET /api/jobs/{id}`). Estados pesados (ResultadoComparacao, linhas de
  extração, BaseProdutos+resultados) vivem no registro da sessão — mesmo
  papel do estado dos widgets no desktop.
- **Serialização**: helpers Decimal→str formatada pt-BR / date→dd/mm/aaaa
  (reusar utils `formatar_moeda` etc. no servidor; o front só exibe).
- **Downloads**: PDFs/Excel/SPED gerados em arquivo temporário por requisição
  → FileResponse com nome sugerido (DANFE: `gerar_danfe_pdf` apenas — nunca
  `abrir_arquivo`, que abriria no servidor).

## Superfície da API (por ferramenta — mapa completo no resultado do
mapeamento; endpoints seguem o mesmo shape)

- `POST /api/login`, `POST /api/logout`, `GET /api/me`, bootstrap admin.
- `POST /api/sessoes` (cria sessão de trabalho por ferramenta) +
  `POST /api/sessoes/{id}/arquivos` (multipart: .txt/.xml múltiplos/.zip —
  zip expandido no servidor; XMLs deduplicados por chave na carga).
- Conferência: carregar (fonte xml/sped + filtro entradas), listar notas,
  conferir/observação, correções (individual/lote/reverter), composição
  (grupos + sobrescritas), DANFE por chave, gerar livro/inconsistências/SPED
  corrigido (downloads).
- Comparador SEFAZ: comparar (2 uploads + apenas_entradas) → resumo/4 listas
  + diagnóstico; exportar Excel. Diff SPED: idem com 2 SPEDs.
- Extração: extrair (fonte + operação) → prévia 2000 + total; exportar Excel
  completo (estado completo fica na sessão).
- Produtos: auditar (upload cadastro) → indicadores + prévia 5000 filtrável;
  corrigir selecionados (índices estáveis `produto.indice`)/alta confiança;
  relatório Excel; nova base corrigida (mantém o upload original vivo na
  sessão — `gerar_nova_base` reabre o arquivo).

## Fases

- **P0 plataforma**: deps, pacote web, auth+bootstrap, sessões/jobs/upload,
  shell estático (login, header JB Fraga, abas, tema), `servidor.ps1`.
- **P1 conferência** (paridade total, inclusive sobrescritas no PDF).
- **P2 comparadores** (SEFAZ + diff) — paralelizável por agentes (arquivos
  disjuntos: router + js próprios).
- **P3 extração + produtos** — idem.
- **P4 acabamento**: testes (scripts estilo casa com TestClient), README de
  implantação, commit.

## Decisões

- D1: SQLite/WAL e registro de jobs em memória bastam para equipe pequena
  (mesma premissa dos outros sistemas); reiniciar o servidor perde jobs em
  andamento, não os uploads (edge case da spec).
- D2: `ConferenciaStore` ganha apenas parametrização de caminho já existente;
  zero mudança de esquema.
- D3: desktop continua funcionando (nada do core muda); o exe morre quando o
  site cobrir o uso real.
- D4: tabelas grandes: prévia limitada como no desktop (2000/5000) com
  paginação client-side simples; export leva tudo.
