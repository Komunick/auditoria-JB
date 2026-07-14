# Tasks — Auditoria Fiscal Web

## P0 — Plataforma
- [X] T001 requirements.txt: fastapi, uvicorn[standard], python-multipart (httpx p/ testes)
- [X] T002 web/infra.py: pasta dados_web, helpers de serialização (Decimal/date → pt-BR)
- [X] T003 web/auth.py: usuários SQLite (PBKDF2+salt), sessões por cookie, bootstrap admin, dependency exigir_usuario
- [X] T004 web/sessoes.py: sessões de trabalho (uploads + zip), registro de jobs em thread
- [X] T005 web/servidor.py: app factory, rotas de login/me/logout/bootstrap, static webui/, include routers
- [X] T006 webui/: index.html (login + shell 5 abas), estilo.css (tema JB Fraga claro/escuro variáveis), app.js (tema, sessão, tabs, fetch helper, jobs polling)
- [X] T007 servidor.py raiz + servidor.ps1 + .gitignore dados_web/

## P1 — Livro de Conferência (paridade)
- [X] T010 web/rotas_conferencia.py: carregar (xml/sped, zip, filtro entradas), notas JSON, conferir, correções (individual/lote), composição (grupos+sobrescritas via chave_grupo), DANFE, livro PDF, inconsistências PDF, SPED corrigido
- [X] T011 webui/conferencia.js + seção no index

## P2 — Comparadores (paralelizável)
- [X] T020 web/rotas_comparador.py + webui/comparador.js (SPED×SEFAZ: resumo 6 cartões, 4 tabelas, diagnóstico, Excel 5 abas)
- [X] T021 web/rotas_diff.py + webui/diff.js (SPED×SPED + Excel)

## P3 — Extração e Produtos (paralelizável)
- [X] T030 web/rotas_extracao.py + webui/extracao.js (prévia 2000, Excel completo)
- [X] T031 web/rotas_produtos.py + webui/produtos.js (indicadores, prévia 5000, filtros, correções por indice, relatório, nova base)

## P4 — Acabamento
- [X] T040 tests/test_web_plataforma.py + test_web_conferencia.py (+ por ferramenta) — estilo casa (script com main())
- [X] T041 README-servidor.md (implantação/atualização) 
- [X] T042 Rodar todos os testes + smoke manual (uvicorn local) + commit dev (e main se pedido)
