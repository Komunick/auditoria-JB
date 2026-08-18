# Implementation Plan: Conciliação Fiscal — Receita e DIMP

**Branch**: `003-conciliacao-fiscal` | **Date**: 2026-08-13 | **Spec**:
[spec.md](./spec.md)

**Input**: Feature specification from
`/specs/003-conciliacao-fiscal/spec.md`

## Summary

Implementar a Conciliação Fiscal como sexta ferramenta nativa do Auditoria-JB.
O parser e as regras financeiras ficam em módulos
independentes de interface; persistência, conflitos, revisões e auditoria fiscal
ficam num SQLite dedicado; a API FastAPI, login, RBAC, histórico geral,
sessões/jobs e frontend estático existentes são reutilizados. Fontes XLSX são
validadas, identificadas por SHA-256 e preservadas fora das sessões temporárias.

Se o protótipo Flask estiver disponível no mesmo ambiente, seus algoritmos
puros podem servir como referência não normativa. Caso contrário, reimplementar
integralmente pelos contratos deste pacote. Em qualquer cenário, rotas,
templates, sessão, login e servidor Flask não são componentes da solução.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, uvicorn, python-multipart e openpyxl já
presentes; HTML, CSS e JavaScript puro sem build no frontend. Nenhuma dependência
nova é necessária.

**Storage**: SQLite `dados_web/conciliacao.db` e originais imutáveis em
`dados_web/conciliacao/origens/<sha256>.xlsx`; `auditoria_web.db` continua como
base de usuários, permissões e trilha geral.

**Testing**: padrão do repositório: scripts Python executáveis com `main()` e
saída `OK/FALHOU`, TestClient nos testes web e fixtures sintéticas. Os arquivos
reais são usados apenas na validação local, fora do Git.

**Target Platform**: servidor Windows na rede interna, uvicorn no processo e
porta atuais. Um único worker enquanto sessões/jobs forem globais em memória.

**Project Type**: aplicação web monolítica modular, backend FastAPI e frontend
estático servido pelo mesmo processo.

**Performance Goals**: lote de 30 arquivos de até 10 MB em até 120 s no ambiente
de referência; listagens p95 até 2 s para 10 mil conciliações; consolidado de
até 10 mil conciliações em até 60 s.

**Constraints**: precisão de centavos; fontes e trilha fiscal imutáveis; sem
Flask/iframe/segunda porta; sem dados reais no Git; sem regressão nas cinco
ferramentas; apenas um CNPJ por preenchimento de modelo.

**Scale/Scope**: equipe interna pequena, dezenas de usuários, até 10 mil
conciliações na meta inicial, duas famílias de layout de entrada e um modelo
Excel interno.

## Constitution Check

### Gate inicial

- **Correção/rastreabilidade**: PASS. O plano persiste fatos e proveniência e
  distingue ausência de zero.
- **Core independente**: PASS. Parser e exportadores não importam `web/`.
- **Autorização/menor privilégio**: PASS condicionado à conclusão da fase de
  ownership de sessões/jobs antes das histórias fiscais.
- **Imutabilidade/versionamento**: PASS. Fontes, versões substituídas, revisões
  e eventos são preservados.
- **Test-first**: PASS. Cada fase contém tarefas explícitas de teste anteriores
  à implementação.
- **Compatibilidade/implantação**: PASS. Mesmo processo, dependências e pasta de
  dados.

### Gate após o design

- Banco separado é justificado por ciclo de vida e trilha fiscal próprios; não
  mistura domínio fiscal em `auditoria_web.db` nem em `conferencia.db`.
- Store e exportador separados preservam testabilidade do domínio sem FastAPI.
- O modelo com `conciliacao` + `versao` é necessário para retificações sem
  perda; uma única linha atualizável foi rejeitada.
- Não há violação constitucional pendente.

## Arquitetura e fluxo

```text
Navegador / sexta aba
        |
        v
rotas_conciliacao.py -- auth/RBAC/auditoria geral
        |                |
        |                +--> sessoes.py / jobs com owner
        v
conciliacao_store.py <--> conciliacao.db
        |                       |
        |                       +--> revisões/eventos append-only
        v
conciliacao_sefaz.py       origens/<sha256>.xlsx
        |
        +--> Quadro 50-5
        +--> Quadro 50-3 + movimentos DIMP

relatorio_conciliacao.py --> consolidado / cópia do modelo
```

### Limites dos módulos

- `core/conciliacao_sefaz.py`: tipos puros, validação do pacote, parser,
  normalização, cálculos e validações de negócio extraíveis da fonte.
- `ferramentas/conciliacao_store.py`: schema, transações, importação,
  versionamento, consultas, conflitos, exceções, decisões e eventos fiscais.
- `ferramentas/relatorio_conciliacao.py`: geração de Excel sem FastAPI.
- `web/rotas_conciliacao.py`: modelos de entrada, dependências de acesso,
  jobs, serialização e respostas.
- `webui/conciliacao.js`: estado visual, upload, filtros, detalhes, decisões e
  downloads; nenhuma regra de autorização confiável fica somente aqui.

## Project Structure

### Documentation (this feature)

```text
specs/003-conciliacao-fiscal/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── implementation-log.md
├── tasks.md
├── acceptance/
│   └── security-data-integrity.md
├── contracts/
│   ├── openapi.yaml
│   ├── xlsx-inputs.md
│   └── xlsx-outputs.md
├── checklists/
│   └── requirements.md
└── references/
    └── source-inventory.md
```

### Source Code (repository root)

```text
src/auditoria_fiscal/
├── core/
│   └── conciliacao_sefaz.py             # novo
├── ferramentas/
│   ├── conciliacao_store.py             # novo
│   └── relatorio_conciliacao.py         # novo
└── web/
    ├── rotas_conciliacao.py             # novo
    ├── servidor.py                      # registrar router e owner dos jobs
    ├── permissoes.py                    # catálogo da sexta ferramenta
    ├── auditoria.py                     # ações auditáveis
    ├── infra.py                         # DB/pasta de origens
    └── sessoes.py                       # ownership de sessões/jobs

webui/
├── index.html                            # menu, section e script
├── conciliacao.js                        # novo
└── estilo.css                            # estilos conc-* necessários

tests/
├── fixtures/conciliacao/                 # XLSX sintéticos
├── test_conciliacao_sefaz.py             # novo
├── test_conciliacao_store.py             # novo
├── test_relatorio_conciliacao.py         # novo
├── test_web_conciliacao.py               # novo
├── test_web_permissoes.py                # sexta aba + isolamento
└── test_web_*.py                         # ajustes de owner onde necessário
```

**Structure Decision**: manter a estrutura monolítica modular do Auditoria-JB.
Não criar subaplicação nem pacote Flask. O core continua compartilhável pelo
desktop; a nova interface inicialmente é web apenas.

## Decisões detalhadas

### Persistência e concorrência

- Uma conexão SQLite por thread/operação, `row_factory`, `foreign_keys=ON`,
  `busy_timeout=5000` e WAL.
- Dedupe e criação de versão em `BEGIN IMMEDIATE`, com tratamento de
  `IntegrityError` como resultado idempotente, não erro 500.
- Importação parseia antes da transação longa; ao persistir, confere novamente
  SHA e chave lógica.
- `conciliacao.revision` é usado para concorrência otimista de decisões.
- Arquivo é gravado primeiro em staging da sessão, validado e hasheado; a cópia
  persistente usa nome pelo hash e criação atômica. Banco só aponta para fonte
  cuja cópia durável foi confirmada.

### Estados e versões

- Conciliação: `em_revisao`, `aprovada`, `rejeitada`.
- Versão: `vigente`, `candidata`, `substituida`, `descartada`.
- Exceção: `aberta`, `resolvida` e severidade `aviso`/`bloqueio`.
- Conflito: `aberto`, `mantida_vigente`, `promovida_candidata`.
- Promover candidata atualiza os estados das duas versões, define a vigente,
  volta a conciliação para `em_revisao`, incrementa `revision` e grava evento,
  tudo na mesma transação.

### Permissões

- `aba.conciliacao`
- `conciliacao.importar`
- `conciliacao.revisar`
- `conciliacao.aprovar`
- `conciliacao.resolver_excecao`
- `conciliacao.exportar`
- `conciliacao.preencher_modelo`
- `conciliacao.incluir_pendentes`

Administradores recebem todas implicitamente. Novos usuários comuns recebem
exatamente `aba.conciliacao` e `conciliacao.importar` pelo padrão; os outros
seis slugs exigem concessão explícita. Usuários já existentes não recebem novos
slugs por migração silenciosa. Toda ação exige cumulativamente
`aba.conciliacao` e sua permissão específica.

No backend, toda rota de ação usa cumulativamente o gate da aba e o slug da
ação; declarar apenas o slug em um resumo de rota nunca elimina o gate da aba.

### Auditoria

A trilha geral registra uso, tentativa negada e resultado HTTP. O banco do
domínio registra importação, duplicidade, rejeição, conflito, revisão,
aprovação, rejeição, resolução, promoção, download de fonte e geração de
documento. A trilha geral é fail-open por desenho existente; portanto não pode
ser a única trilha de uma mutação fiscal.

### Upload e XLSX

- Aceitar somente `.xlsx`, limite padrão 50 MB configurável por
  `AUDITORIA_CONCILIACAO_MAX_UPLOAD_MB`.
- Conferir pacote ZIP, estrutura mínima, quantidade de entries, tamanho
  descompactado, razão de compressão, traversal, macro e external links antes
  de `load_workbook`.
- Não reutilizar a expansão ZIP genérica de sessões para esse formato.
- `data_only=True` lê o valor armazenado; campo obrigatório com fórmula sem
  cache válido gera erro explícito.
- Limites de lote: no máximo 100 arquivos e 500 MB de staging por sessão, além
  do teto por arquivo; ambos configuráveis somente com limites máximos seguros.

### Downloads

Preferir `BytesIO` quando o tamanho esperado for moderado. Se for necessário
arquivo temporário, usar criação segura e tarefa de limpeza após a resposta,
nunca `mktemp`. O modelo recebido também é validado e temporário; a fonte
original do usuário não é alterada.

## Migração e implantação

- Schema criado por migração aditiva idempotente ao abrir o store.
- Não há migração obrigatória de produção, pois o protótipo ainda é separado.
- Se existir `fiscal.db` com dados que devam ser preservados, executar um
  migrador explícito e testado em etapa separada; não importar automaticamente
  na inicialização.
- Atualização continua sendo `git pull` + reiniciar um único `servidor.ps1`.
- Backup passa a incluir `conciliacao.db` e `conciliacao/origens`. Para SQLite
  em WAL, documentar parada/checkpoint ou backup online; cópia ingênua durante
  escrita não é garantia de consistência.

## Complexity Tracking

| Decisão | Por que é necessária | Alternativa rejeitada |
|---|---|---|
| Banco dedicado | Domínio fiscal versionado e trilha imutável têm ciclo próprio | Misturar com autenticação ou conferência aumenta acoplamento e risco de backup/migração |
| Entidades Conciliação + Versão | Relatórios retificados devem ser comparados e preservados | Sobrescrever linha única elimina evidência e aprovação anterior |
| Auditoria geral + fiscal | Trilha HTTP existente pode falhar sem derrubar a ação e não é transacional | Usar apenas `evento` não garante prova da mutação fiscal |
