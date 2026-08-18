# Registro de implementação e aceite

Preencher durante a execução. Não registrar CNPJ, razão social, valores fiscais,
credenciais ou caminhos privados das amostras.

## Contexto

- Branch: `003-conciliacao-fiscal`, criada a partir de `main`.
- Commit-base observado: `f86750007b13c7045eaff5e5b204457ec9b9076b` — idêntico
  ao commit-base da especificação. Nenhuma adaptação de caminho foi necessária.
- Divergências relevantes desde o commit-base da especificação:
  - **`origin/dev` está 3 commits à frente de `main`** (`3460c85`, `4d1df9f`,
    `54e8eeb`) e toca arquivos desta feature: `web/permissoes.py`,
    `web/auditoria.py`, `web/rotas_conferencia.py`, `tests/test_web_conferencia.py`,
    `webui/conferencia.js` e `README.md`; acrescenta `core/filtro_periodo.py` e
    a pasta `devops/`. A implementação seguiu o commit-base indicado no handoff
    (`main`), **não** `dev`. Risco de conflito registrado abaixo.
  - `.specify/memory/constitution.md` no clone era o **modelo vazio**, como o
    README do pacote previa; foi substituído pela constituição 1.0.0 do pacote
    sem merge humano necessário.
  - O `README.md` do pacote **não** foi copiado para a raiz: ele documenta como
    aplicar o pacote e sobrescreveria o README do projeto. Os demais arquivos
    entraram nos caminhos previstos.
  - `.specify/feature.json` continua apontando para `002-controle-acesso-historico`
    e não foi editado; a feature é ativada por
    `$env:SPECIFY_FEATURE_DIRECTORY = "specs/003-conciliacao-fiscal"`.
  - O clone não tinha `.venv`. Ambiente criado com Python 3.11.9 e
    `requirements.txt` sem fixação de versão — resolveu para FastAPI 0.141.1,
    Starlette 1.6.0, pandas 3.0.5, openpyxl 3.1.5, PySide6 6.11.1.
- Executor e data: Claude Code (Opus 5), 17/08/2026.

## Baseline

Suíte anterior, executada antes de qualquer alteração de código, com
`.venv\Scripts\python.exe tests\test_*.py` (padrão do repositório): **29 de 29
scripts com saída 0**, sendo 2 pulados por dependência de ambiente.

| Teste | Resultado | Observação |
|---|---|---|
| 27 scripts restantes de `tests/test_*.py` | OK | núcleo, ferramentas, UI e web |
| `test_fdb_reader.py` | PULADO | motor Firebird embedded ausente em `vendor/firebird25` (não versionado) |
| `test_web_produtos_fdb.py` | PULADO | mesma causa |

Nenhuma falha prévia a atribuir ou herdar.

## Checkpoints por fase

| Fase | Tarefas | Testes executados | Resultado | Decisões/riscos |
|---|---|---|---|---|
| 1 | T001–T004 | suíte completa (baseline) | 29/29 OK, 2 pulados | Geradores sintéticos em `tests/fixtures/conciliacao/`; limites arquiteturais medidos e íntegros |
| 2 | T005–T011 | `test_web_permissoes.py`, todos os `test_web_*.py`, suíte completa | 29/29 OK, 2 pulados | Propriedade de sessão/job exigida por assinatura; 404 indistinguível; teto próprio de upload |
| 2+ | T069 | `test_web_permissoes.py`, todos os `test_web_*.py`, suíte completa, smoke de `esperarJob` no navegador | 29/29 OK, 2 pulados | Ferramenta obrigatória no polling; SEC003 fechado |
| 3 | T012–T019 | `test_web_conciliacao.py` (novo), `test_web_permissoes.py`, suíte completa, smoke da aba no navegador | 30/30 OK, 2 pulados | Catálogo com 8 slugs; router antes do mount estático; aba reusa `.cartoes`/`.cartao` |
| 4 | T020–T031 | `test_conciliacao_sefaz.py` e `test_conciliacao_store.py` (novos), `test_web_conciliacao.py`, suíte completa | 32/32 OK, 2 pulados | Parser puro com proveniência; store append-only; bug de trava do staging encontrado e corrigido |
| 5 | T032–T037 + T070 | `test_conciliacao_store.py`, `test_web_conciliacao.py`, suíte completa, smoke da lista/detalhe no navegador | 32/32 OK, 2 pulados | Filtros por allowlist; resumo e lista com o mesmo universo; SC-013 medido |
| 6 | T038–T042 | `test_conciliacao_store.py`, `test_web_conciliacao.py`, suíte completa | 33/33 OK, 2 pulados | Decisão = estado + revisão + evento na mesma transação |
| 7 | T043–T046 | idem | 33/33 OK, 2 pulados | Promover preserva a anterior; vigente alterada invalida decisão pendente |
| 8 | T047–T052 | `test_relatorio_conciliacao.py` (novo), `test_web_conciliacao.py` | 33/33 OK, 2 pulados | Injeção de fórmula neutralizada; salvamento atômico |
| 9 | T053–T059 | idem | 33/33 OK, 2 pulados | Modelo original intacto; pendentes com aba de aviso visível |
| 10 | T060–T061 | `test_web_conciliacao.py` | 33/33 OK, 2 pulados | Indicadores e lista sempre no mesmo universo |
| 11 | T062–T064, T066–T068 | suíte completa, benchmark, smoke no navegador, revisão de diff | 33/33 OK, 2 pulados | Índice de exceções corrigiu SC-011; T065 permanece pendente |

### Fase 1 — detalhamento

- **T001**: branch criada; pacote aplicado; divergências acima.
- **T002**: baseline acima.
- **T003**: `tests/fixtures/conciliacao/__init__.py` gera, em tempo de teste,
  Quadro 50-5, Quadro 50-3/DIMP (com instituição repetida e linha de outro
  CNPJ/período), planilha-mestre com duas seções anuais, e as variações
  inválidas (pacote falso, truncado, sem estrutura mínima, macro, vínculo
  externo, traversal, >5.000 entradas, razão de compressão insegura). Nenhum
  binário fiscal é versionado: só o gerador. CNPJ sintético com DV calculado.
- **T004** — baseline dos limites arquiteturais, medido por AST sobre
  `src/auditoria_fiscal/`:

  | Camada | Arquivos que importam framework de interface | Importa `web/` |
  |---|---|---|
  | `core/` | 0 de 12 | não |
  | `ferramentas/` | 0 de 13 | não |
  | `web/` | 10 de 12 (FastAPI/pydantic, esperado) | — |
  | `ui/` | 8 de 8 (PySide6, esperado) | não |

  Direção das dependências hoje: `web/ → ferramentas/ → core/`, sem retorno.
  O limite que a feature precisa preservar já está íntegro. O **teste
  executável** desse limite é T020, junto com os módulos novos.

### Fase 2 — detalhamento

- **T005**: `tests/test_web_permissoes.py` ganhou
  `propriedade_de_sessoes_e_jobs()`. Antes da correção o teste falhava no
  primeiro caso — um segundo usuário autenticado lia a sessão alheia com
  **HTTP 200 e o estado completo**. Casos cobertos: leitura, mutação, job,
  descarte destrutivo, sessão de outra ferramenta, ID inexistente e o próprio
  dono continuando a operar.
- **T006/T007**: `obter_sessao(sessao_id, usuario, ferramenta="")` e
  `obter_job(job_id, usuario, ferramenta="")`. `Job` passou a carregar
  `usuario` e `ferramenta`, copiados da sessão que o iniciou.
  `descartar_sessao(sessao_id, usuario)` valida o dono antes de apagar a pasta.
- **T008**: 28 pontos de chamada atualizados em `servidor.py` e nos cinco
  `rotas_*.py`, cada um passando também a ferramenta esperada.
- **T009**: nenhum `tests/test_web_*.py` precisou de ajuste — os fluxos
  existentes já usavam um usuário por sessão. Isolamento, fluxos e **polling de
  job** confirmados verdes nos cinco testes web.
- **T010**: `caminho_db_conciliacao()` e `pasta_origens_conciliacao()` em
  `web/infra.py`, ambos derivados de `pasta_dados_web()`.
- **T011**: `web/rotas_conciliacao.py` com `max_upload_mb()` /
  `max_upload_bytes()`. Sem router ainda — isso é T016/T017.

### T069 — amarração de ferramenta no job (fecha o achado C1)

Executada logo após a análise, por decisão do proprietário.

- **Teste primeiro**: `propriedade_de_sessoes_e_jobs()` ganhou os casos de
  ferramenta. Antes do código, o job próprio consultado com
  `ferramenta=produtos` respondia **200 e vazava a mensagem de erro do
  processamento** para o cliente da aba errada.
- **Servidor**: `GET /api/jobs/{job_id}` passou a exigir `ferramenta`, repassada
  a `obter_job()`. Ferramenta divergente, desconhecida, job alheio e job
  inexistente devolvem o **mesmo** corpo 404; ausência é 422.
- **Front**: `esperarJob(jobId, ferramenta)` em `webui/app.js` monta a query e
  **lança antes de qualquer requisição** se a ferramenta faltar — erro de
  programação aparece na primeira execução, não como 422 no meio de um
  processamento. Os cinco clientes de aba passaram a informar a própria
  ferramenta; `webui/conciliacao.js` já nasce assim (nota acrescentada em T031).
- **Testes**: os seis helpers `esperar_job()` receberam o parâmetro com default
  igual à ferramenta do arquivo.
- **Verificação no navegador**: servidor real na 8600, `esperarJob` chamada no
  contexto da página. Aridade 2; sem ferramenta lança
  `"esperarJob exige a ferramenta da aba."` sem emitir requisição alguma; com
  ferramenta emite exatamente
  `GET /api/jobs/job-de-teste?ferramenta=conferencia`. Nenhum erro de console
  além do 401 esperado por não haver login.
- **Artefatos**: `openapi.yaml` com `FerramentaQuery` `required: true` e resposta
  422 declarada; **SEC003 marcado** no gate de aceite.

Cache do navegador não é risco aqui: `WebuiSemCache` em `servidor.py` já força
revalidação de todo o `webui/`, exatamente para que um `git pull` + reinício não
deixe ninguém com `app.js` novo e cliente de aba velho.

### Fase 3 — detalhamento

- **T012/T013**: testes escritos antes. Dois achados corrigiram os **testes**,
  não o código: (1) o resumo tinha inventado `com_avisos`/`com_bloqueios`,
  enquanto o schema `Summary` do contrato usa `avisos`/`bloqueios`/`conflitos`
  mais `diferenca_total` como `Money` — o contrato prevaleceu; (2)
  `PADRAO_NOVO_USUARIO` **não** é default do servidor, é a sugestão que a tela
  de administração pré-marca, exposta em `padrao_novo` do
  `GET /api/admin/usuarios`. Criar usuário sem informar permissões concede
  nada, e o teste agora afirma exatamente isso.
- **T014**: 8 slugs no catálogo, `aba.conciliacao` como "6." logo após
  `aba.produtos` (a ordem do catálogo é a ordem de exibição, e inserir ali
  preserva as asserções de ordem dos testes existentes). No padrão entram
  somente `aba.conciliacao` e `conciliacao.importar`. Usuário existente não
  ganha nada: a tabela só guarda concessões explícitas, então não há migração
  a fazer — verificado por asserção sobre um usuário criado antes.
- **T015**: 9 ações auditáveis separando processamento (upload, processar),
  mutação (revisar, aprovar, resolver exceção, resolver conflito) e download
  (fonte, consolidado, modelo). `conciliacao.resolver_excecao` cobre exceção e
  conflito, como FR-003 agrupa. O download da fonte exige só a aba: não há
  slug próprio no catálogo de 8.
- **T016/T017**: router com `/resumo` na forma final do contrato, helpers de
  erro (`erro`, `nao_encontrado`, `desatualizado` com `current_revision`) e
  `dinheiro()` convertendo centavos em `Money` — `None` continua `None`,
  porque ausência não pode virar zero. Registrado **depois** dos outros
  routers e **antes** do mount estático: o mount é curinga em `/` e engoliria
  `/api/conciliacao/**` se viesse antes.
- **T018/T019**: sexta aba sem renumerar as cinco anteriores (verificado no
  DOM: ordem `comparador, diff, conferencia, extracao, produtos, conciliacao,
  admin`). O shell tem as quatro subtelas e expõe `container.conciliacao`
  (`estado`, `pode`, `garantirSessao`, `atualizarResumo`, `abrirSub`,
  `status`) para as fases seguintes não recriarem sessão nem permissões.
  Indicadores **reusam** `.cartoes`/`.cartao` das outras abas em vez de criar
  classes próprias (constituição, princípio II); de CSS novo entrou apenas a
  barra de subtelas.
- **Verificação no navegador** (servidor real na 8600, sem autenticar):
  `conciliacao.js` carrega sem erro, a aba registra, o botão lê
  "6. Conciliação Fiscal", as quatro subtelas alternam, e os estilos resolvem
  nos dois temas — escuro (fundo `#17171F`, subtela ativa dourada `#B8A166`) e
  claro (fundo `#FAF9F5`, ativa `#26263A` com sublinhado dourado). Em 375x812
  a página **não** rola horizontalmente e barra e cartões quebram linha.

### Fase 4 — detalhamento

- **T020/T021** (`tests/test_conciliacao_sefaz.py`): dois layouts, números
  BR/US, CNPJ e competência, vazio × zero, fórmula sem cache, cabeçalho
  deslocado, abas extras e ocultas, tolerância de R$ 0,01, fechamentos,
  proveniência, movimentos DIMP, linhas de outra chave, pacote inseguro e o
  teste executável dos limites arquiteturais que T004 havia adiado.
- **T024–T026** (`core/conciliacao_sefaz.py`): módulo puro, 0 imports de
  interface. Decisões que valem registro:
  - **Separador decimal ambíguo é recusado.** `1.234` pode ser mil duzentos e
    trinta e quatro ou um vírgula dois três quatro; escolher errado erra por
    1000× num número fiscal. Só passa quando o separador é inequívoco.
  - **Sub-centavo é recusado, não arredondado.** Arredondar inventaria
    precisão que a fonte não tem.
  - **Fórmula sem cache × célula vazia.** Com `data_only=True` o openpyxl
    devolve `None` nos dois casos, e o contrato exige códigos distintos
    (`FORMULA_SEM_VALOR` × `CAMPO_OBRIGATORIO_AUSENTE`) porque a correção é
    outra. Resolvido com uma segunda visão do arquivo (`data_only=False`)
    aberta **só** quando um campo obrigatório aparece vazio — o caminho normal
    continua com uma única carga.
  - **50-3 sem DIMP não vira 50-5.** Reinterpretar trocaria um bloqueio
    (`DIMP_OBRIGATORIA_AUSENTE`) por um aviso benigno, e a competência ficaria
    aprovável sem ninguém notar a falta. Este ponto corrigiu um **teste meu**
    que contrariava o contrato.
  - Severidades: erro fatal não deixa conciliação parcial; fechamento que não
    bate e DIMP acima da calculada são **bloqueio**; DIMP abaixo da calculada
    e 50-5 sem DIMP são **aviso**.
- **T027–T029** (`ferramentas/conciliacao_store.py`): schema do `data-model`,
  migrações idempotentes, WAL, `busy_timeout`, `BEGIN IMMEDIATE`. Imutabilidade
  garantida por **trigger no próprio SQL**, não só no Python: fonte, movimento,
  fato, revisão e evento recusam UPDATE/DELETE, e de uma versão só o `estado`
  muda. Confirmado por teste que ataca o banco direto com `sqlite3`.
  `UNIQUE(sha256)` transforma corrida em resultado idempotente — quatro
  threads importando o mesmo arquivo produzem uma fonte e três duplicados.
  Fonte promovida para `origens/<sha>.xlsx` por `os.replace` **antes** de o
  banco apontar para ela.
- **T030/T031**: upload em blocos com teto aplicado durante o streaming e
  parcial removido; staging por **id opaco** com o nome original num manifesto
  ao lado — o nome enviado nunca controla caminho, e dois arquivos homônimos
  convivem. Ator capturado da sessão autenticada e levado ao job como snapshot
  primitivo.

**Bug encontrado e corrigido durante a fase**: a trava de "um processamento
por sessão" era liberada **antes** de o staging ser removido. Na janela entre
as duas coisas, um segundo pedido encontrava a trava livre e o staging ainda
de pé, abrindo um lote duplicado sobre arquivos prestes a sumir — o segundo
job leria staging meio apagado e produziria rejeições falsas. Apareceu como
teste intermitente (passava sozinho, falhava na suíte). A limpeza passou para
dentro da região travada; 5 execuções seguidas verdes depois disso.

### Fase 5 — detalhamento

- **T034**: filtros por **allowlist** — nome de campo nunca viaja do cliente
  para dentro do SQL e valor de enum é conferido contra o conjunto conhecido;
  `LIKE` usa `ESCAPE` para que `%` e `_` digitados sejam texto, não curinga.
  `_condicoes()` é **compartilhada** por resumo e listagem: indicador contando
  um universo e tabela mostrando outro é o jeito mais rápido de alguém decidir
  sobre um número que não existe. Só exceções da versão **vigente** contam
  para o estado corrente; as de versões substituídas ficam no histórico.
  Página absurda é presa à última em vez de estourar o inteiro do SQLite.
- **`instituicoes()`**: agrega para leitura mas devolve `linhas`, o número de
  movimentos somados — agregar não pode dar a impressão de que a fonte trazia
  um lançamento só. As linhas originais e a proveniência seguem intactas.
- **T035**: `Money` em toda saída monetária (centavos exatos + texto pronto);
  `None` continua `None`, então no Quadro 50-5 o PIX chega nulo e a tela
  mostra "—", nunca "R$ 0,00". Download da fonte serve o binário imutável de
  `origens/` e é auditado; banco apontando para arquivo ausente responde 500
  com código próprio, porque é incidente, não "não achei".
- **T036/T037**: lista com filtros, ordenação e paginação; detalhe com
  declarado × calculado × diferença, DIMP agregada por instituição mais as
  linhas originais com a célula de origem, proveniência de cada fato e
  histórico. CSS novo só o necessário, tudo prefixado `conc-`.
- **T070 — SC-013 medido**: com um lote de 12 arquivos em processamento,
  `/resumo`, `/conciliacoes` e `/excecoes` do mesmo usuário responderam
  **9 vezes**, pior tempo **0,032 s** (orçamento do teste: 2 s), e o polling
  do job nunca travou. A propriedade que sustenta isso: o parse acontece
  **fora** da transação e `sessao.trava` só é tomada no update final de
  estado — padrão herdado das cinco ferramentas anteriores e preservado de
  propósito.

## Decisões tomadas

1. **Dono obrigatório por assinatura.** `usuario` não tem default em
   `obter_sessao`/`obter_job`. Uma rota nova que esquecesse o dono quebra na
   hora, em vez de nascer com o furo. Alternativa rejeitada: parâmetro opcional.
2. **404, nunca 403, e com a mesma mensagem** do recurso inexistente
   (research R7). Um 403 confirmaria que aquele ID existe. O teste compara os
   dois corpos de resposta para garantir que são idênticos.
3. **A regra vale também para administrador.** Sessão de trabalho é estado
   transitório de uma pessoa, não recurso administrado; nenhuma rota
   administrativa precisa dela. Ponto a confirmar com o proprietário caso ele
   espere que o admin possa encerrar sessão de terceiros.
4. **A sessão carrega a ferramenta.** Uma sessão de `produtos` não é passe para
   as rotas de `conferencia`, mesmo sendo do próprio usuário.
5. **`descartar_sessao` valida sozinha**, sem depender de a rota ter chamado
   `obter_sessao` antes.
6. **Teto de upload lido do ambiente a cada chamada**, e valor inválido
   (vazio, não numérico, zero, negativo) volta ao default de 50 MB — um teto
   inválido nunca pode virar "sem teto". O teto genérico de 2048 MB das bases
   FDB fica intacto; foi verificado por asserção.
7. **Dinheiro lido do XLSX via `Decimal(str(valor))`.** Verificado nas
   fixtures: o openpyxl grava `40000.01` exato no XML mas devolve `float`;
   `Decimal(str(v))` recupera o valor, enquanto `Decimal(v)` traz
   `40000.0100000000020372681319713592529296875`. Restrição para o parser T024.

### Fases 6 a 11 — detalhamento

- **T040/T044**: toda decisão grava, **na mesma transação**, o novo estado, a
  revisão (append-only) e o evento fiscal. A checagem de bloqueio/conflito
  acontece **dentro** da transação: conferir antes e gravar depois deixaria
  espaço para uma candidata chegar no meio e a aprovação valer sobre outros
  números. `ConcorrenciaError` carrega a revision atual, para o cliente
  recarregar em vez de sobrescrever a decisão de outra pessoa.
- **Promoção de candidata** não apaga nada: a vigente anterior vira
  `substituida` e continua consultável com movimentos, fatos e proveniência. E
  a vigente do instante em que o conflito nasceu é comparada com a vigente
  **atual** — com duas candidatas, promover uma invalida a decisão pendente da
  outra (`VIGENTE_ALTERADA`), porque a base de comparação mudou.
- **T049/T050**: `sanitizar_texto` prefixa apóstrofo em texto que começa por
  `=`, `+`, `-` ou `@`. O apóstrofo não aparece na célula e não altera o
  conteúdo lido — apagar o caractere perderia dado da fonte. Salvamento é
  atômico (temporário + `os.replace`): falha no meio não deixa arquivo com
  cara de planilha válida.
- **T056/T058**: o modelo enviado **nunca** é alterado; tudo acontece numa
  cópia. Meses reconhecidos pelo **texto**, nunca por linha fixa. `SUM` só
  quando a seção tem os 12 meses e uma linha TOTAL — somar seção incompleta
  produziria um total que não é total. Competência rejeitada nunca entra, e
  com bloqueio ou conflito aberto também não, **mesmo que o estado persistido
  diga "aprovada"**: o estado pode ter sido gravado antes de a pendência
  aparecer. Incluir pendentes exige permissão adicional **e** confirmação
  explícita, e o arquivo sai com uma aba de aviso como **primeira** aba.
- **Defeito encontrado e corrigido na fase 8**: as rotas da conciliação
  devolvem erro estruturado `{detail, code}`, mas o helper `api()` de
  `webui/app.js` fazia `new Error(objeto)` — **toda** mensagem de erro da aba
  apareceria como `[object Object]`. `api()` passou a entender as duas formas
  (texto simples das rotas antigas e objeto do contrato novo) e a expor
  `codigo`, `status` e `revisionAtual` no erro. Verificado no navegador.
- **T068 — revisão do diff**: zero ocorrências reais de Flask, iframe,
  segunda porta, `mktemp`, credencial, banco ou planilha fiscal. Os três
  falsos positivos: `flask` é o literal da lista de proibidos no teste de
  arquitetura, `mktemp` aparece só num comentário explicando por que **não** é
  usado, e o padrão de credencial casou com `secrets.token_urlsafe` e com
  "SECRETARIA da Fazenda". `requirements.txt` intacto — nenhuma dependência
  nova.

## Desempenho

Medido por `tests/benchmark_conciliacao.py` (T064), que não faz parte da
suíte porque mede tempo.

- **Hardware/ambiente**: Intel64 Family 6 Model 186 (12 núcleos), Windows,
  Python 3.11.9, disco local. **Não é o servidor de referência** (4 núcleos,
  8 GB) — os números abaixo são indicativos e mais otimistas que a produção.
- **Dataset sintético**: 30 arquivos dos dois layouts para SC-010; 10.000
  conciliações com exceção e fato para SC-011 e SC-012.

| Critério | Medido | Meta | Situação |
|---|---:|---:|---|
| SC-010 lote de 30 arquivos | 0,61 s | 120 s | dentro |
| SC-011 p95 das listagens | 0,02 s | 2 s | dentro |
| SC-012 exportação completa | 10,18 s | 60 s | dentro |

**O benchmark encontrou um problema real e ele foi corrigido.** Na primeira
execução, `resumo` levava **3,2 s** e o filtro por exceção **7,9 s** com 10 mil
conciliações — acima da meta de 2 s, numa máquina com o triplo dos núcleos do
servidor de referência. Causa: o resumo e o filtro perguntam, para **cada**
conciliação, "existe exceção aberta desta severidade na versão vigente?", e o
índice existente (`estado, severidade`) não cobria a pergunta, então cada linha
virava varredura da tabela de exceções. Com o índice
`excecao_conciliacao(conciliacao_id, versao_id, estado, severidade)`:

| Consulta | Antes | Depois |
|---|---:|---:|
| resumo sem filtro | 3,217 s | 0,008 s |
| filtro por exceção | 7,859 s | 0,064 s |
| p95 geral | 7,15 s | 0,02 s |
| exportação completa | 44,41 s | 10,18 s |

- **Aceite no servidor de referência**: **pendente**. As metas só podem ser
  declaradas atingidas depois de rodar o mesmo benchmark na máquina de
  produção (4 núcleos, 8 GB, disco local).

## Validação privada das amostras

- `AUDITORIA_CONCILIACAO_AMOSTRAS` disponível: não (não configurada neste ambiente)
- 12 relatórios processados: —
- 10 conteúdos únicos confirmados: —
- 2 pares de duplicatas confirmados: —
- planilha-mestre preenchida somente em cópia: —
- resultado T065: **pendente** — gate de aceite do proprietário, conforme a
  definição de concluído do handoff.

## Smoke e regressão

- **Perfis/permissões**: automatizado. Quatro perfis distintos em
  `test_web_conciliacao.py` — importador (só envia), revisor (decide, não
  importa), exportador (gera saída, não decide) e admin — cada um recebendo
  403 no que não alcança, com a tentativa registrada na trilha.
- **Temas e tela estreita** (T066, navegador real na 8600): as quatro
  subtelas alternam; importação, exportação e planilha-mestre aparecem
  conforme a permissão; tema claro (`#FAF9F5`) e escuro (`#17171F`) corretos;
  em 375×812 a página **não** rola horizontalmente e as tabelas rolam dentro
  do próprio contêiner.
- **Upload/job/reinício**: cobertos por T023 (teto, parcial removido, staging
  por id opaco, um processamento por sessão) e pelo teste de lote interrompido
  no reinício.
- **Revisão/conflito**: cobertos por T038/T039/T043 no store e na API.
- **Downloads**: fonte original, consolidado e planilha-mestre, todos com MIME
  e nome conferidos, e todos auditados.
- **SC-013**: 6 a 9 leituras respondendo durante um lote em processamento,
  pior tempo 0,078 s contra orçamento de 2 s.
- **Suíte completa**: **33/33 com saída 0**, mesmos 2 pulados do baseline
  (Firebird embedded ausente). Nenhuma regressão nas cinco ferramentas
  anteriores.

## `/speckit-analyze`

Executado após as fases 1 e 2 — o handoff pedia antes da implementação, e essa
inversão fica registrada. Resultado: **0 questões críticas**, nenhuma violação
constitucional, 100% dos FR com tarefa, 93% dos SC (14/15). Achados: 2 HIGH,
2 MEDIUM, 2 LOW.

Correções documentais aplicadas com aprovação do proprietário, todas
fortalecendo requisitos:

- **F1** (HIGH) — T006 dizia "opcionalmente ferramenta" enquanto FR-005 e SEC003
  exigem a validação (MUST). Texto de T006/T007 alinhado ao MUST e o checkpoint
  da fase 2 passou a conferir que nenhuma rota consumidora de sessão omitiu a
  ferramenta.
- **C1** (HIGH) — `POST /processar` devolvia `job_id` sem que o contrato
  descrevesse o endpoint de polling. `GET /api/jobs/{job_id}` foi promovido a
  rota documentada no `openapi.yaml`, com os parâmetros `JobId` e
  `FerramentaQuery` e a semântica de 404 indistinguível. Criada **T069** para
  concluir a amarração de ferramenta do job nas seis interfaces; até lá o
  parâmetro é opcional, para não regredir as cinco ferramentas (FR-049).
  SEC003 recebeu a nota de que não pode ser marcado antes de T069.
- **C2** (MEDIUM) — SC-013 era o único critério de sucesso sem tarefa. T066
  passou a cobri-lo no smoke manual e criada **T070** para a verificação
  automatizável do lado servidor (leituras e polling respondem com o lote em
  processamento).

Achados registrados e **não** corrigidos, por não afetarem execução: I1 (coluna
J da planilha-mestre é derivada por `=G-I`, ou seja, calculada sem ST, com
rótulo legado que sugere "diferença" — o contrato já manda registrar a
semântica nos metadados), D1 (checkpoints das fases 6 e 7 com texto quase
idêntico) e L1 (FR-050/FR-051 fora da ordem numérica; renumerar quebraria
referências cruzadas).

## Riscos residuais e pendências

1. **`origin/dev` à frente de `main`.** Os 3 commits de `dev` alteram
   `web/permissoes.py`, `web/auditoria.py` e `web/rotas_conferencia.py` — os
   mesmos arquivos das fases 2 e 3. Quanto mais tarde `dev` for integrado, mais
   caro o conflito. Decisão do proprietário: integrar `dev` em `main` antes de
   seguir, ou rebasear esta branch sobre `dev`.
2. **T010 e T011 ainda sem teste versionado.** Foram verificados por script
   fora do repositório (caminhos abaixo de `AUDITORIA_WEB_DADOS`, criação da
   pasta de origens, os seis casos do limite e a preservação do teto FDB). O
   `tasks.md` agenda a cobertura automatizada para T022 e T023; até lá, código
   novo sem teste versionado é uma exceção temporária ao princípio V, com
   correção prevista nessas tarefas.
3. **Limite arquitetural sem teste executável** até T020, conforme a própria
   redação de T004.
4. **`requirements.txt` sem versões fixadas.** O baseline foi obtido com
   FastAPI 0.141.1/Starlette 1.6.0; o TestClient já emite
   `StarletteDeprecationWarning` sobre `httpx`. Uma resolução futura diferente
   pode mover o baseline sem nenhuma mudança no repositório.
5. **Firebird embedded ausente** neste ambiente: 2 testes permanecem pulados,
   igual ao baseline. Nenhuma conclusão desta feature depende deles.
6. **`tempfile.mktemp` pré-existente em 10 pontos** — `rotas_comparador.py`,
   `rotas_conferencia.py` (5x), `rotas_diff.py`, `rotas_extracao.py` e
   `rotas_produtos.py` (2x), todos presentes no commit-base e **não** tocados
   por esta entrega. `mktemp` só devolve um nome: entre a escolha do nome e a
   abertura do arquivo existe uma janela de corrida em diretório temporário
   compartilhado. O `plan.md` proíbe `mktemp` para os downloads da conciliação
   ("nunca `mktemp`") e T068 manda conferir a ausência dele no diff — o novo
   módulo nasce limpo, mas as cinco ferramentas anteriores continuam com o
   padrão antigo. Correção fora do escopo de T001–T011; decisão do
   proprietário sobre quando tratar.
7. ~~**FR-005 fechado pela metade para jobs.**~~ **Resolvido por T069**: a
   ferramenta é obrigatória no polling e as cinco interfaces existentes foram
   migradas sem regressão. FR-005 e SEC003 estão fechados para sessões e jobs.

## Convergência final

- Resultado de `/speckit-converge`: não executado. As 70 tarefas foram
  percorridas em ordem de fase, com a suíte verde em cada checkpoint; resta
  T065, que depende de material fora do repositório.
- Tarefas acrescentadas: **T069** (amarração de ferramenta no job, achado C1) e
  **T070** (cobertura automatizada de SC-013, achado C2), ambas por
  `/speckit-analyze`, não por `/speckit-converge`.
- Gate de aceite concluído: **não** — falta T065 (validação privada com os
  relatórios reais) e o aceite das metas de desempenho no servidor de
  referência. Todos os demais itens de `acceptance/security-data-integrity.md`
  têm evidência de teste automatizado.
