# Gate de aceite — segurança e integridade fiscal

**Purpose**: evidências obrigatórias para revisão da implementação e aceite.

**Feature**: [spec.md](../spec.md)

Este arquivo fica em `acceptance/`, não em `checklists/`: no Spec Kit,
checklists avaliam a qualidade dos requisitos antes da implementação. Marque
os itens abaixo somente com evidência de código, teste ou documentação. Eles
ainda não estão concluídos porque este pacote contém a especificação, não a
implementação.

## Autenticação e autorização

- [x] SEC001 Toda rota exige autenticação ou é leitura pública deliberadamente documentada (não se espera nenhuma nesta feature).
- [x] SEC002 Toda rota exige `aba.conciliacao` e ações sensíveis exigem o slug adicional correto.
- [x] SEC003 Sessão e job validam proprietário e ferramenta; recurso alheio não é revelado.
  - Sessão: proprietário e ferramenta (T006/T008), com os testes de T005.
  - Job: proprietário (T007) e ferramenta obrigatória na rota de polling
    (T069). Evidência em `tests/test_web_permissoes.py`,
    `propriedade_de_sessoes_e_jobs()`: job alheio, job de outra aba e
    ferramenta desconhecida devolvem o **mesmo corpo** de um job inexistente;
    omitir a ferramenta é 422.
- [x] SEC004 Remoção de permissão vale na próxima ação sem novo login.
- [x] SEC005 IDs/nomes de ator não são aceitos do cliente em mutações.
- [x] SEC006 Usuário sem permissão gera 403 e evento geral `negado`.

## Upload e armazenamento

- [x] SEC007 Apenas `.xlsx` dentro do limite específico é aceito.
- [x] SEC008 O contêiner é validado antes do openpyxl.
- [x] SEC009 Macro, external link, traversal, zip bomb, pacote falso e truncado têm testes de rejeição.
- [x] SEC010 SHA-256 identifica a fonte independentemente do nome.
- [x] SEC011 Fonte aceita é persistida fora da sessão e não pode ser sobrescrita.
- [x] SEC012 Banco nunca aponta para arquivo de evidência ausente.
- [x] SEC013 Nome de arquivo do usuário não controla caminho de destino.
- [x] SEC014 Fontes reais, uploads e bancos permanecem fora do Git.

## Integridade financeira

- [x] INT001 Domínio usa Decimal e banco usa centavos INTEGER.
- [x] INT002 Ausência e zero permanecem distintos.
- [x] INT003 Fechamentos de receita e DIMP usam tolerância documentada.
- [x] INT004 Total não-PIX é Total DIMP menos PIX e não é tratado como cartão puro.
- [x] INT005 Todo fato tem célula ou fórmula e versão do parser.
- [x] INT006 DIMP de outra competência/CNPJ não é misturado silenciosamente.
- [x] INT007 Erro fatal não deixa conciliação parcial.

## Versionamento e concorrência

- [x] CON001 Mesmo SHA é idempotente sob requisições concorrentes.
- [x] CON002 Outro SHA para a mesma chave cria candidata e conflito.
- [x] CON003 Nenhum conflito sobrescreve a vigente automaticamente.
- [x] CON004 Promoção preserva a versão anterior e volta para Em revisão.
- [x] CON005 `BEGIN IMMEDIATE`, busy timeout, WAL e tratamento de IntegrityError estão cobertos.
- [x] CON006 Revision otimista impede perda silenciosa de decisão concorrente.
- [x] CON007 Reinício não deixa lote persistente eternamente em processamento.
- [x] CON008 Nova candidata faz decisão anterior voltar a Em revisão e
  múltiplas candidatas nunca são promovidas contra uma vigente alterada.

## Revisão e auditoria

- [x] AUD001 Bloqueio ou conflito aberto impede aprovação.
- [x] AUD002 Justificativa é obrigatória em revisão, aprovação e resolução.
- [x] AUD003 Mutação e evento fiscal são atômicos.
- [x] AUD004 Revisões e eventos fiscais rejeitam UPDATE/DELETE.
- [x] AUD005 Trilha geral registra ok, negado e erro sem substituir a fiscal.
- [x] AUD006 Download de fonte e exportações são auditados.
- [x] AUD007 Detalhes da trilha geral evitam valores fiscais desnecessários.

## Excel de saída

- [x] XLS001 Dados textuais perigosos são neutralizados contra fórmula.
- [x] XLS002 Valores monetários são células numéricas formatadas.
- [x] XLS003 Quadro 50-5 exporta PIX/não-PIX vazios, não zero.
- [x] XLS004 Consolidado inclui dados, movimentos, proveniência, exceções, revisões e metadados.
- [x] XLS005 Modelo é validado antes de escrever e original nunca é alterado.
- [x] XLS006 Um único CNPJ é obrigatório no preenchimento.
- [x] XLS007 Somente vigente/aprovada entra por padrão; rejeitada nunca entra.
- [x] XLS008 Pendentes exigem permissão cumulativa, confirmação e sinalização visível.
- [x] XLS009 Células fora do mapeamento são preservadas.
- [x] XLS010 Falha não produz download parcial válido.
- [x] XLS011 Temporários são criados com segurança e removidos após a resposta.
- [x] XLS012 Consolidado inclui histórico de versões e conflitos, não apenas a
  visão vigente.

## Operação e regressão

- [x] OPS001 O processo e a porta existentes são mantidos; não há Flask/iframe.
- [x] OPS002 O core não importa a camada web.
- [x] OPS003 O servidor permanece com um worker enquanto jobs forem em memória.
- [x] OPS004 Backup inclui DB e origens e documenta consistência com WAL.
- [x] OPS005 Toda a suíte anterior e a nova passam.
- [ ] OPS006 Metas de desempenho foram medidas e registradas.
- [ ] OPS007 Smoke test cobre dois perfis, temas, tela estreita e downloads.


## Itens que dependem de material externo

- **OPS006** — o benchmark roda e passa nesta máquina (12 núcleos), mas
  as metas do spec só valem no servidor de referência (4 núcleos, 8 GB,
  disco local). Rode `tests/benchmark_conciliacao.py` lá antes de marcar.
- **OPS007** — o smoke automatizado cobre estrutura, temas e tela
  estreita. A passada manual com dois perfis reais, prevista em T066,
  precisa de alguém logado na aplicação.
- **T065** (validação privada com os 12 relatórios reais) permanece
  pendente: `AUDITORIA_CONCILIACAO_AMOSTRAS` não está configurada neste
  ambiente e os arquivos não entram no repositório.
