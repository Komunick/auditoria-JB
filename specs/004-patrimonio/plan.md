# Implementation Plan: Patrimônio — Bens e Responsabilidade

**Branch**: `004-patrimonio` | **Base**: `003-conciliacao-fiscal` (aba 6)

A base é a branch da conciliação, não `main`: esta é a **aba 7**, e construí-la
sobre `main` produziria conflito garantido em `permissoes.py`, `auditoria.py`,
`servidor.py`, `index.html` e `app.js` quando o PR #2 entrar.

## Summary

Sétima ferramenta nativa, seguindo exatamente a arquitetura que a conciliação
já provou: núcleo puro em `core/`, persistência em `ferramentas/`, rotas em
`web/` e uma aba em `webui/`. SQLite próprio, RBAC por aba + ação, trilha geral
no `auditoria_web.db` e trilha de domínio append-only no banco da ferramenta.

## Technical Context

**Linguagem**: Python 3.11+. **Dependências**: nenhuma nova — `openpyxl` para
Excel e `fpdf2` (já presente via `brazilfiscalreport`) para o termo em PDF.

**Storage**: `dados_web/patrimonio.db`.

**Testing**: scripts com `main()` e saída `OK/FALHOU`, TestClient nos testes
web, fixtures sintéticas.

**Constraints**: sem Flask, iframe ou segunda porta; sem regressão nas seis
ferramentas; centavos inteiros no banco.

## Constitution Check

- **Correção/rastreabilidade**: PASS. Movimentação append-only com autor e
  motivo; situação e movimentação na mesma transação.
- **Núcleo independente**: PASS. `core/patrimonio.py` e
  `ferramentas/patrimonio_store.py` não importam FastAPI.
- **Autorização no servidor**: PASS. Seis slugs, cumulativos com a aba.
- **Imutabilidade/versionamento**: PASS. Etiqueta imutável, movimentação
  append-only, baixa em vez de exclusão, inventário congelado ao fechar.
- **Test-first**: PASS. Cada fase começa por teste.
- **Compatibilidade**: PASS. Mesmo processo e pasta de dados.

## Decisões

### Etiqueta imutável e sequencial

`JBF-000001` para bem, `PER-000001` para periférico. A sequência vem de
`MAX(numero)+1` dentro da transação de criação, e a coluna é protegida por
trigger contra `UPDATE`. A etiqueta é impressa e colada: renumerar significa
alguém ler a etiqueta física e achar outro bem.

### Um responsável por vez, garantido pelo banco

Índice parcial único `responsabilidade(bem_id) WHERE encerrada_em IS NULL`.
Verificar em Python e depois inserir deixaria janela para duas atribuições
simultâneas criarem dois donos — e aí ninguém sabe com quem está o
equipamento. O `IntegrityError` vira 409 com mensagem clara.

### Concorrência otimista no bem

`bem.revision` acompanha toda mutação. Duas pessoas editando o mesmo bem: a
segunda recebe 409 com a revision atual e recarrega, em vez de sobrescrever.

### Baixa é terminal

Não existe exclusão de bem. Baixa exige justificativa, grava movimentação e
bloqueia qualquer movimentação posterior. O bem some das listagens
operacionais por padrão (`incluir_baixados=false`) mas continua consultável.

### Inventário congela o universo

Ao abrir, `inventario_item` recebe uma linha por bem ativo, com a situação e o
local esperados. Bem cadastrado depois não entra — senão a taxa de localização
mudaria sozinha durante a conferência.

### Sanitização de Excel compartilhada

`sanitizar_texto` e o salvamento atômico saem de
`ferramentas/relatorio_conciliacao.py` para `core/planilha_segura.py`, e os
dois exportadores passam a importar de lá. Duplicar um controle de segurança é
como uma das cópias envelhece e vira vulnerabilidade.

### Permissões

- `aba.patrimonio` — portão da ferramenta
- `patrimonio.cadastrar` — bens, pessoas e locais
- `patrimonio.movimentar` — atribuir, devolver, manutenção, empréstimo
- `patrimonio.baixar` — baixa, separada por ser terminal e irreversível
- `patrimonio.inventariar` — abrir, conferir e fechar inventário
- `patrimonio.exportar` — Excel e termo em PDF

Usuário novo recebe, por sugestão da tela, apenas `aba.patrimonio`. Cadastrar,
movimentar e baixar exigem liberação explícita.

## Project Structure

```text
src/auditoria_fiscal/
├── core/
│   ├── planilha_segura.py       # novo (extraído da conciliação)
│   └── patrimonio.py            # novo: tipos, etiqueta, transições
├── ferramentas/
│   ├── patrimonio_store.py      # novo
│   └── relatorio_patrimonio.py  # novo: Excel + termo PDF
└── web/
    ├── rotas_patrimonio.py      # novo
    ├── servidor.py              # registrar router
    ├── permissoes.py            # 6 slugs
    ├── auditoria.py             # ações auditáveis
    └── infra.py                 # caminho_db_patrimonio()

webui/
├── index.html                   # botão, section e script
├── patrimonio.js                # novo
└── estilo.css                   # estilos pat-* necessários

tests/
├── test_patrimonio.py           # núcleo puro
├── test_patrimonio_store.py     # persistência
├── test_relatorio_patrimonio.py # Excel e PDF
└── test_web_patrimonio.py       # rotas
```

## Complexity Tracking

| Decisão | Por que é necessária | Alternativa rejeitada |
|---|---|---|
| Banco dedicado | Ciclo de vida e backup próprios | Misturar com conciliação acopla domínios sem relação |
| Índice parcial único | Garante um responsável por vez sob concorrência | Checagem em Python deixa janela de corrida |
| `planilha_segura` compartilhada | Um controle de segurança, uma implementação | Duplicar convida a divergência silenciosa |
