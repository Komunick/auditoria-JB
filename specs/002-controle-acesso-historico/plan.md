# Implementation Plan: Controle de acesso por usuário e histórico de acessos

**Branch**: `main` | **Date**: 2026-07-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/002-controle-acesso-historico/spec.md`

## Summary

Acrescentar à Auditoria Fiscal Web (já um site interno) o controle de acesso por
usuário — abas e ações sensíveis recortáveis, administrado pelo `adm` e pela
Carol como administradores plenos — e uma trilha de acessos que responde quando
cada usuário entrou, o que acessou, o que fez e quando saiu. Reaproveita a
camada web existente; o core fiscal (parser SPED, XML, composição, correções,
livros PDF, relatórios) não é tocado. A checagem de permissão é feita no
servidor (dependency por rota); o frontend apenas deixa de desenhar o que o
usuário não alcança.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: FastAPI, uvicorn, python-multipart (backend); HTML +
CSS + JavaScript puro, sem framework nem build (frontend) — padrão da casa.

**Storage**: SQLite. `auditoria_web.db` (usuários, sessões de login, permissões,
histórico) e `conferencia.db` (trilha fiscal, compartilhada com o desktop),
ambos em `dados_web/` fora do git; caminho sobrescrevível por
`AUDITORIA_WEB_DADOS`.

**Testing**: scripts standalone com `main()` e saída `OK/FALHOU`, rodados um a um
(`.\.venv\Scripts\python.exe tests\test_web_*.py`) — sem pytest, conforme a casa.

**Target Platform**: servidor Windows na rede interna (uvicorn, porta 8600).
Acesso remoto por Tailscale/HTTPS é camada à frente, fora do escopo.

**Project Type**: web (backend FastAPI + frontend estático servido pelo mesmo
processo).

**Performance Goals**: equipe pequena; consultas do histórico paginadas e
indexadas; sem meta de throughput específica.

**Constraints**: o core não pode ganhar dependência de framework web; a
semântica fiscal não muda; a checagem de acesso real é no servidor; frontend
servido com revalidação de cache para não misturar versões após atualização.

**Scale/Scope**: dezenas de usuários; histórico crescente com índices por
data e por usuário; 21 permissões no catálogo.

## Constitution Check

O projeto ainda usa a constituição-modelo (não ratificada). Princípios de fato
seguidos nesta feature, herdados do restante do sistema:

- **Core isolado**: a camada web importa o core; o core nunca importa a web
  (mantido — os módulos novos só vivem em `web/`).
- **Frontend sem build**: mantido (vanilla JS + fetch).
- **Migração aditiva de dados**: tabelas novas por `CREATE TABLE IF NOT EXISTS`,
  sem perder o que já existe.
- **Segurança no servidor**: a permissão é imposta por dependency de rota; a UI
  é conveniência.

Sem violações que exijam registro na Complexity Tracking.

## Project Structure

### Documentation (this feature)

```
specs/002-controle-acesso-historico/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```
src/auditoria_fiscal/
├── core/            # inalterado (semântica fiscal)
├── ferramentas/     # inalterado
└── web/
    ├── permissoes.py     # NOVO — catálogo e concessões por usuário
    ├── auditoria.py      # NOVO — registro de ações, dependency acesso(),
    │                     #        middleware do histórico, consulta e export
    ├── rotas_admin.py    # NOVO — API /api/admin/* (usuários, permissões,
    │                     #        histórico, CSV)
    ├── auth.py           # ALTERADO — conexão pública, gestão de usuários,
    │                     #            guarda do último admin, sessão expirada
    ├── servidor.py       # ALTERADO — middleware, login/logout auditados,
    │                     #            navegação por aba, cache-control
    └── rotas_*.py        # ALTERADO — cada rota das 5 ferramentas passa a
                          #            exigir permissão e a auditar

webui/
├── app.js           # ALTERADO — Sessão/permissões, filtro de abas, esc()
├── admin.js         # NOVO — tela de Administração
├── index.html       # ALTERADO — aba Administração + aviso "sem acesso"
├── estilo.css       # ALTERADO — sub-abas, permissões, realces herdados
└── conferencia.js / produtos.js / diff.js / comparador.js / extracao.js
                     # ALTERADO — esconder ações sem permissão; escapar dados

tests/
└── test_web_permissoes.py   # NOVO — permissões + histórico ponta a ponta
```

**Structure Decision**: web application — backend FastAPI em
`src/auditoria_fiscal/web/` e frontend estático em `webui/`, servidos pelo mesmo
processo uvicorn, exatamente como a spec 001 estabeleceu. Esta feature adiciona
três módulos web e um arquivo de frontend, e ajusta os pontos de entrada.

## Design Decisions

- **Administrador implícito**: a tabela `permissao_usuario` só guarda concessões
  de não-admins; administrador recebe o catálogo inteiro. Assim, uma permissão
  nova nasce disponível para admins e promover alguém nunca depende da tabela
  estar completa.
- **Uma dependency por rota**: `Depends(acesso("<slug>"))` autentica, exige a
  permissão da aba e a da ação, e marca a requisição para o histórico. Rotas de
  leitura usam `Depends(exigir_aba("<aba>"))` (não auditam, para não afogar a
  trilha com recarregamentos de tabela).
- **Histórico gravado pelo middleware, após a resposta**: o status real entra na
  linha; 403 vira "negado", ≥400 vira "erro", e uma exceção inesperada (500)
  também deixa rastro. Rotas de polling (jobs, estado) ficam fora de propósito.
- **Correção em lote com permissão extra**: só o corpo da requisição revela que
  é lote, então a rota checa `conferencia.corrigir_lote` internamente.
- **Trilha de uso separada da fiscal**: `evento` (uso) em `auditoria_web.db`;
  `correcao`/`conferencia`/`composicao_override` (fiscal) em `conferencia.db`.
- **Cache do frontend**: servido com `Cache-Control: no-cache` para que, após um
  `git pull` + reinício, o navegador não misture app.js novo com módulo antigo.

## Complexity Tracking

Sem desvios que exijam justificativa: a feature reusa a arquitetura existente e
não introduz novas dependências nem novos processos.
