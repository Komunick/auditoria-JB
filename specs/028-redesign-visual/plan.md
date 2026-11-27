# Implementation Plan: Redesign Visual e Arquitetura de Interface (JB Fraga)

**Branch**: `028-redesign-visual` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/028-redesign-visual/spec.md`

## Summary

Redesenhar integralmente a interface web (`webui/`) da plataforma Auditoria-JB para alinhá-la à identidade visual oficial da JB Fraga Contabilidade (`#060D28` navy, `#C9A227` dourado e ativos de marca transparentes), reestruturar a navegação para 13+ ferramentas com grupos mais claros, gaveta móvel e seletor rápido (`Ctrl+K`), refinar a Central operacional e unificar o sistema de componentes (cartões, tabelas, formulários, sub-abas, badges, modais e temas claro/escuro) em `estilo.css` e `qualidade.css`, mantendo zero etapa de build, zero CDN externo e 100% de compatibilidade com os contratos de DOM e segurança existentes.

## Technical Context

**Language/Version**: HTML5, CSS3 (Custom Properties, Grid, Flexbox, `color-mix`), Vanilla JavaScript ES2020+, Python 3.12 (testes e servidor local de verificação)  
**Primary Dependencies**: Nenhuma dependência nova; reutilização de ativos gráficos estáticos da marca (`jbfraga-site/assets/img/*.png`) copiados localmente para `webui/img/`  
**Storage**: `localStorage` no navegador apenas para preferências de UI (`tema`, `menuRecolhido`) — zero alteração de banco SQLite ou backend  
**Testing**: Scripts nativos `tests/test_*_ui.py` (Node `vm`), `tests/test_web_*.py` (`TestClient` FastAPI), novo `tests/test_redesign_ui.py` (contraste WCAG AA, integridade de ativos locais/sem CDN, contratos de shell/paleta/gaveta) e inspeção visual em navegador real via Playwright/Chromium  
**Target Platform**: Navegadores desktop e mobile acessando FastAPI + `WebuiSemCache` em LAN/HTTPS  
**Project Type**: Frontend estático integrado ao monolito FastAPI existente (`webui/`)  
**Constraints**:
- Sem etapa de build (`npm`/`vite`/`webpack` proibidos pela Constituição)
- Sem CDN externo (fontes, ícones SVG e imagens estritamente locais)
- Preservar integralmente invariantes de `app.js` e `clientes.js` verificadas por `tests/test_base_fiscal_ui.py` e seletores `#id` usados por `test_central_ui.py`, `test_tarefas_*_ui.py` e `test_qualidade_ui.py`
- Nenhum dado real de cliente, colaborador ou CNPJ no repositório

## Constitution Check

*GATE: Passed before design and implementation.*

1. **Correção fiscal e rastreabilidade integral**: Não altera cálculos, parsers ou proveniência fiscal; melhora legibilidade tabular (`tabular-nums`, contraste e alinhamento monetário).
2. **Núcleo independente das interfaces**: Nenhuma alteração em `core/` ou `ferramentas/`; mudanças restritas a `webui/` e `tests/`/`specs/`.
3. **Autorização no servidor e menor privilégio**: O seletor rápido (`Ctrl+K`), a gaveta e a navegação respeitam estritamente `Abas.permitida()` e `Sessao.pode()`; o servidor segue como única autoridade (401/403).
4. **Imutabilidade, versionamento e auditoria transacional**: Nenhuma mutação de domínio nem alteração de `/api/eventos/aba` ou fluxos de auditoria.
5. **Testes antes da implementação**: `tests/test_redesign_ui.py` será criado antes da implementação principal para validar tokens/WCAG AA, ausência de CDN, integridade de ativos, novos controles do shell (`app.js`) e regras de segurança em `webui/`.
6. **Compatibilidade e implantação simples**: Mantém entrega estática única em `webui/`, sem novas dependências Python/Node em runtime, sem portas novas e totalmente compatível com `WebuiSemCache` e `autodeploy`.

## Project Structure

### Documentation (this feature)

```text
specs/028-redesign-visual/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
webui/
├── img/
│   ├── favicon-64.png
│   ├── icon-192.png
│   ├── logo-horizontal-light.png
│   ├── logo-horizontal.png
│   └── symbol-256.png
├── index.html          # Shell redesenhado: login, gaveta, sidebar, topbar, paleta Ctrl+K
├── estilo.css          # Sistema visual JB Fraga (tokens claro/escuro, componentes, responsivo)
├── qualidade.css       # Alinhamento do módulo Gestão da Qualidade ao mesmo design system
├── app.js              # Suporte à gaveta mobile, paleta Ctrl+K, senha visível no login e título/breadcrumb
├── inicio.js           # Central redesenhada (capa com marca transparente, KPIs e cards refinados)
└── [módulos *.js]      # Ajustes pontuais de cabeçalho/estrutura onde necessário sem quebrar contratos

tests/
└── test_redesign_ui.py # Testes automatizados de contraste WCAG, ativos, sem CDN e shell UI
```

**Structure Decision**: Manter a organização plana de `webui/*.js` + `webui/img/` para compatibilidade imediata com `WebuiSemCache` e caminhos relativos em `index.html`.
