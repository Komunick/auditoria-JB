# Validação e cobertura do pedido

Fonte: solicitação privada da diretoria de 27/10/2026, PDF de seis páginas e dez
itens, localizada na pasta Briefing do cliente. Fonte e dados privados não foram
copiados ao repositório. Exercícios usaram pessoas e empresas fictícias.

## Correspondência entre requisito, entrega e evidência

| Item do PDF | Implementação | Verificação |
|---|---|---|
| 1. Atividades por setor | Referências para Fiscal, Contábil, DP, Legalização e Administrativo; acesso à agenda existente | `test_qualidade_ui.py`, `test_web_qualidade.py`; cinco setores no preview |
| 2. Ocorrências | Oito tipos, criticidade, cliente, setor, responsável, datas, prazo e histórico | `test_qualidade.py`, `test_qualidade_store.py`, `test_web_qualidade.py`; ocorrência criada pela UI |
| 3. Prazos e produtividade | Agenda existente integrada; vínculo com tarefa e apontamento de minutos | Regressão `test_tarefas*`; apontamento de 90 min a 120/h = 180 pela UI |
| 4. Indicadores | Entregas, pendências, erros/retrabalho, reclamações, solução e não conformidades | `test_qualidade_indicadores.py`; fórmulas, autoria histórica, fuso, amostra e ausência de dados |
| 5. Planos de ação | Causa, ação, tipo, responsável, prazo, comentários, evidência e validação | Store/HTTP/UI; plano criado, enviado à conferência e validado no preview |
| 6. Alertas | Sete classes no painel e no resumo SMTP diário existente | `test_qualidade_alertas.py`, `test_alertas_email.py`; idempotência, substituições e bloqueio por aba |
| 7. Dashboard | Semáforo, quatro dimensões observáveis e filtros por cliente/setor/pessoa/período/status | Testes de indicadores/HTTP/UI; desktop e celular de 390 px, claro/escuro |
| 8. Relatórios | Recortes diário/semanal/mensal/personalizado; XLSX e PDF | `test_relatorio_qualidade.py`; nove abas, PDF paginado, downloads reais no preview |
| 9. Acesso e histórico | Permissões explícitas, escopo, revisão e eventos imutáveis | `test_web_qualidade.py`, `test_qualidade_seguranca.py`; 401/403/409/422 e redaction de custos |
| 10. Integração/implantação | Cadastro compartilhado, migração aditiva e roteiro de implantação/treinamento | `test_qualidade_migracao.py`, [roteiro](implantacao-treinamento.md) |

## Evidências funcionais adicionais

- Testes RED de módulos/rotas ausentes antes de implementar. Revisão adicional
  reproduziu e corrigiu comentários em registros encerrados, tipos JSON inválidos,
  comentário opcional nulo, migração parcial, sessão revogada/despromoção durante
  upload e legenda de média sem numerador. Regressões específicas aprovadas.
- Duas conexões SQLite competindo por edição e por apontamento: uma revisão vence,
  sem ultrapassar o limite diário. Trilha e mutação permanecem atômicas.
- Anexo EML sintético enviado e baixado pela UI. SHA-256 antes/depois idêntico:
  `93fa75f60e1dd563ce3c46be4ab22e68a90f26b805b56d564ef9bb1d9e13ac9d`.
- S3 testado com cliente falso (sem rede), incluindo falhas, integridade,
  colisão e compensação. Não houve validação contra bucket real.
- PDF do preview extraído e primeira página renderizada; fixture extensa de
  relatório também renderizada na revisão. Planilha conferida com nove abas;
  linha do exercício conserva pessoa, 90 minutos, custo/hora 120 e custo 180.
- Preview loopback em `http://127.0.0.1:8623/`, dados sintéticos separados do
  checkout. Nenhum erro JavaScript capturado na navegação final.

## Regressão completa

Primeira execução: 101 scripts, 99 aprovados, dois ignorados (motor Firebird
embedded indisponível), zero falhas funcionais. O manifesto acusou a correção
de legenda da UI feita durante essa execução; ela não foi usada como gate final.

Execução final com arquivos congelados em 30/10/2026: **101 scripts, 99 aprovados,
dois ignorados, zero falhas; nenhuma alteração funcional durante a suíte**.
Ignorados: `test_fdb_reader.py` e `test_web_produtos_fdb.py`, ambos porque o motor
Firebird embedded não está instalado no ambiente local.

Evidências privadas fora do checkout: pasta
`tmp/validacao-spec022-20261030-173605` no workspace, com resumo JSON, log por
script e manifestos SHA-256 inicial/final; preview e downloads sintéticos em
`tmp/qa-qualidade-022`. `git diff --check` também aprovado.

## Preparação do PR em 03/11/2026

Os 238 arquivos funcionais foram reconferidos com o manifesto final da suíte de
30/10/2026: nenhum arquivo alterado, acrescentado ou removido nesse conjunto.
Na revisão de empacotamento, `boto3>=1.35` e `Pillow>=10.4` foram incluídos também
em `devops/requirements-web.txt`, em conformidade com o manifesto geral.
O teste `test_qualidade_anexos.py` passou novamente; a comparação dos manifestos
confirmou as mesmas dependências, exceto PySide6, fdb e httpx, excluídas
intencionalmente da instalação web. A suíte completa não foi repetida: os ajustes
desta preparação se limitaram ao manifesto de dependências e à documentação.

## Limites da entrega

Software validado localmente com dados sintéticos. A autorização de 03/11/2026
abrange commit, push do branch e PR para `dev`; exclui merge, deploy, alterações
em produção e no Linear.
As regras reais da carteira, concessão de acessos, configuração do S3/backup de
objetos e ativação de SMTP dependem da implantação aprovada e das definições do
escritório. Validação estrutural de anexos não é análise antimalware. A janela
administrativa de reinstalação do executor foi autorizada posteriormente, conforme
a seção seguinte; o registro anterior descreve o estado ao preparar o PR inicial.

## Correção do executor para publicação — 03/11/2026

O gate original recusava toda mudança de manifests, mesmo após a instalação
administrativa de pacotes. A autorização opcional `dependency_transition` fixa
SHA de origem e árvore completa do candidato. Os dois valores são obrigatórios,
validados e registrados pelo instalador em configuração privada; outro par
continua recusado. Não há instalação automática, alteração de estado para simular
sucesso ou remoção dos testes, backups, ensaio de migração e verificações de saúde.

RED reproduzido nos dois testes do executor antes da alteração. GREEN em
`test_autodeploy.py` e `test_autodeploy_install.py`, repetido por revisão
independente sem achados bloqueantes. Casos cobrem ausência/par inválido, origem
ou árvore divergente, merge com SHA diferente e mesma árvore, recusa de alvo
futuro, check/no-op, registro da transição e backup da configuração anterior.

Regressão completa posterior à correção: **101 scripts, 99 aprovados, 2 ignorados
por Firebird indisponível, zero falhas e nenhuma alteração funcional durante a
execução**. Logs e manifestos privados em
`tmp/validacao-spec022-20261103-101204`, fora do Git. `git diff --check` aprovado.

A sequência operacional foi corrigida: timer pausado, backup do runtime anterior,
resolução isolada de dependências, instalação administrativa conferida, promoção
da árvore aprovada e somente depois preflight/ativação. Na preparação da arm07,
cinco pacotes foram resolvidos por versão/hash em cópia do venv, sem atualizar ou
remover pacotes anteriores; `pip check` aprovado. S3 real continua não configurado.

## Revisão do pedido e semáforo — 04/11/2026

A revisão encontrou uma divergência na UI: ocorrências resolvidas/encerradas e
planos validados eram verdes mesmo após o prazo; não conformidades abertas
podiam ficar amarelas. Painel, API, lista e detalhe agora reutilizam a mesma
classificação do núcleo, com datas de Salvador e resultado neutro quando não
há evidência suficiente de prazo/conclusão.

RED registrado antes da correção em testes de núcleo, HTTP e UI. Baseline e
regressão final: **19 scripts aprovados, zero pulados, zero falhas**, manifestos
funcionais inalterados em cada execução. Revisão independente do patch sem
achados bloqueantes. Nenhuma migração ou mudança de permissões.

Preview sintético autenticado em loopback 8626: cores verificadas no painel,
nas listas de ocorrências/planos e nos detalhes; histórico de resolução e
validação preservado. Evidências privadas em `tmp/revisao-pdf-20261104`.
O [relatório de cobertura](revisao-pdf-20261104.md) registra também uma
sobreposição visual do menu, corrigida na etapa autorizada abaixo. Essa etapa
local ocorreu sem commit, push, merge, deploy, acesso a produção ou alteração
no Linear; as publicações posteriores são registradas separadamente.

## Correção do menu lateral — 04/11/2026

Reproduzida a sobreposição em 1280 × 738 px antes da alteração. A navegação
agora rola no espaço disponível, com marca e botão de minimizar reservados
fora dessa área. A mudança se limita ao CSS de desktop; o layout móvel mantém
seu comportamento anterior.

Validação no navegador, com dados fictícios e as 13 abas do administrador:

- 1280 × 738, 1024 × 600 e 960 × 480 px: menu aberto e recolhido, sem
  sobreposição entre os controles visíveis; Administração abre a tela correta.
- Minimizar e expandir preservam a aba atual. Tab e Shift+Tab percorrem as
  abas e o botão, com foco visível e rolagem automática; Enter e Espaço funcionam.
- 920 × 600 e 390 × 844 px: abas acessíveis, sem corte horizontal; botão de
  minimizar oculto, conforme o layout móvel existente.

Revisão independente do CSS sem achados bloqueantes. Evidências de antes e
depois, medidas e resultados em `tmp/validacao-menu-20261104`, fora do Git.
Preview: `http://127.0.0.1:8626/`. O tamanho temporário do navegador foi
restaurado ao final. A suíte de 19 scripts do semáforo não foi repetida nesta
etapa, limitada ao CSS; foram executadas as verificações visuais e de interação
descritas acima. A implementação local ocorreu sem commit, push, merge,
deploy, produção ou Linear.

Posteriormente, o menu foi integrado pelo [PR #34](https://github.com/Komunick/auditoria-JB/pull/34)
e publicado pela promoção [#36](https://github.com/Komunick/auditoria-JB/pull/36),
merge `ef80d37c56a66f03689973958db60fa30ca80c8f`. A validação autenticada
em 04/11/2026 confirmou Administração acessível, ausência de sobreposição em
1002 × 884 e 1280 × 738 px e preservação da aba ao minimizar/expandir.
O semáforo permanece separado dessa publicação.

## Preparação do PR do semáforo — 04/11/2026

Branch `codex/correcao-semaforo-qualidade`, em checkout separado da implementação
local, baseado em `origin/dev` no SHA
`101fe047908c7e580bcaff3013e4b6b3526e7e55`. O diff contém três arquivos
funcionais, três testes e três documentos da spec 022. Menu lateral e ações
de tarefas já fazem parte da base e não são reaplicados neste patch.

Os seis arquivos de código e testes coincidem com os hashes da correção local
anteriormente validada. A regressão no novo checkout passou em **21 scripts,
zero falhas e zero pulados**: os 19 da suíte do semáforo, mais
`test_tarefas_reativacao_prazo.py` e `test_tarefas_acoes_ui.py`, presentes na
dev atual. Os manifestos de fontes, interface e testes permaneceram idênticos
antes e depois da execução. Revisão independente sem achados bloqueantes.

Os testes usam dados sintéticos; variáveis `AUDITORIA_*` e `AWS_*` são removidas
do ambiente herdado, o SMTP do teste usa loopback e o S3 usa cliente falso.
Evidências privadas em `tmp/publicacao-semaforo-20261104/regressao`, fora do Git.
Não houve nova sessão de preview nesta preparação; a conferência visual anterior
usa os mesmos arquivos funcionais. Nenhuma nova dependência, migração ou
alteração de permissões.

Esta etapa contempla commit, push do branch e PR para `dev`. Merge e deploy
dependem de aprovação posterior. Não houve alteração em produção ou no Linear.
