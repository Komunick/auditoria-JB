# Implantação e treinamento — Gestão da qualidade

Atualização de 05/11/2026: a [spec 024](../024-conclusao-qualidade/spec.md)
complementa este roteiro com armazenamento privado no servidor, quota e reserva
de disco, como alternativa explícita ao S3. A cobertura atual e o ensaio
sintético estão em [validação](../024-conclusao-qualidade/validacao.md); a
configuração e os cuidados de recuperação estão em
[operação](../024-conclusao-qualidade/operacao.md). As etapas de instalação inicial
e schema 4 abaixo são históricas: a 024 não muda dependências, schema ou executor.
Não reinstalar o controle de deploy apenas por causa dessa mudança.

Este roteiro atende ao item 10 da solicitação de TI descrita na
[spec 022](spec.md). É uma proposta de implantação para aprovação futura.
O software foi validado localmente com dados sintéticos. A autorização posterior
de 03/11/2026 inclui preparar o executor, promover o código pelo fluxo de PRs e
publicar na arm07 com backups e validação. Importação real, concessão de permissões,
configuração de S3 e treinamento/piloto continuam sujeitos às decisões próprias.

Os responsáveis são definidos por função: responsável técnico, gestor do
escritório, líderes de setor e colaboradores participantes. Datas, participantes,
orçamento e janela de manutenção dependem de confirmação do escritório.

## Etapas e cronograma sugerido

Os dias abaixo são relativos à aprovação da etapa correspondente, não datas
contratadas. Uma reprovação de aceite interrompe o avanço para a etapa seguinte.

| Etapa | Previsão sugerida | Responsável | Entrega e condição de avanço |
|---|---|---|---|
| Revisão e homologação local | Dias 1–2 | Técnico e gestor | Revisão do código, suíte sintética, preview e aceite dos dez itens; pendências registradas |
| Preparação operacional | Dia 3 | Técnico e gestor | Matriz de acessos, piloto escolhido, armazenamento privado configurado e recuperação ensaiada em ambiente isolado; custos e retenção definidos |
| Treinamento de colaboradores | Dia 4, 60–90 minutos | Líderes e técnico | Exercício completo com clientes e identidades fictícios, sem gravar em produção |
| Treinamento da gestão | Dia 4, 45–60 minutos | Gestor e técnico | Validação/devolução, leitura dos indicadores, exportações e conferência do acesso a custos |
| Publicação autorizada e conferência técnica | Janela a aprovar | Técnico | SHA aprovado, executor atualizado, backup verificado, schema 4 e aplicação saudável |
| Piloto acompanhado | Cinco dias úteis após liberação | Um setor e gestor | Amostra de operações autorizadas, revisão diária de ocorrências, planos, apontamentos e acesso |
| Ampliação e avaliação | Após aceite do piloto | Gestor e líderes | Liberação por setor, orientação dos demais usuários e revisão após duas semanas |

O piloto com registros reais só começa depois de autorização específica. Enquanto
ela não existir, os exercícios ficam no preview ou em homologação isolada. Não
criar empresas fictícias no cadastro produtivo para testar a interface.

## Preparação funcional e acessos

- Conferir os clientes, usuários ativos, setores, vínculos de equipe e carteira
  já existentes. Reutilizar seus identificadores; não duplicar o cadastro nem
  importar empresas como parte desta implantação.
- Revisar os modelos de atividades e relacioná-los às tarefas e obrigações já
  cadastradas. Os modelos são sugestões para personalizar na agenda, sem vencimentos fiscais
  presumidos. A aprovação do catálogo e das regras continua com o escritório.
- Definir quem registra, gere, valida, exporta e consulta valores de custo.
  Registrar o aceite da matriz antes de conceder acesso. Permissões novas não
  são distribuídas automaticamente aos usuários existentes; administradores
  seguem o modelo de acesso implícito já utilizado no sistema.
- Conferir `aba.qualidade`, `qualidade.registrar`, `qualidade.gerir`,
  `qualidade.validar`, `qualidade.todas`, `qualidade.exportar` e
  `qualidade.custos`. Liderança e vínculo de setor efetivo devem corresponder à
  função escolhida. A consulta global exige concessão explícita apropriada.
- Homologar colaborador, líder e gestão com contas sintéticas distintas:
  leitura, escrita, anexos, indicadores e exportações precisam respeitar o mesmo
  escopo. Ocultar um botão não substitui a autorização do servidor.

Os contratos de campos e transições estão em [contratos.md](contratos.md). A
matriz completa de capacidades pode ser conferida no
[catálogo de permissões](../../src/auditoria_fiscal/web/permissoes.py).

## Treinamento prático

### Colaboradores

1. Localizar atividades existentes e consultar o painel com filtros de período,
   cliente, setor, colaborador e situação. Diferenciar tarefa, ocorrência e plano.
2. Registrar uma ocorrência sintética com data, descrição, criticidade,
   responsável e prazo. Vincular tarefa somente quando ela pertence ao mesmo
   cliente e setor. Acrescentar comentário e consultar o histórico.
3. Criar plano corretivo ou preventivo, informar causa, ação, responsável e prazo;
   iniciar a execução e solicitar validação com comentário. A validação final é
   uma atividade da gestão autorizada.
4. Anexar evidência fictícia PDF, PNG, JPEG ou EML e conferir o download
   autenticado. Limite por arquivo: 10 MiB; imagens de até 25 megapixels, sem
   animação. O conteúdo é validado, mas isso não equivale a uma análise antivírus.
5. Registrar minutos efetivamente trabalhados. Corrigir erro cancelando o
   lançamento com motivo e criando outro; o original e o histórico permanecem.
   O total ativo por pessoa e dia não pode exceder 1.440 minutos.
6. Simular edição concorrente: diante de conflito de revisão, recarregar o
   registro e conferir a alteração anterior antes de reenviar.

### Líderes e gestão

1. Conferir a distribuição de responsabilidades, os prazos próximos, atrasos,
   espera por cliente, conferências pendentes e ausência de movimento.
2. Devolver um plano com comentário e validar a nova execução com evidências.
   Resolver e encerrar uma ocorrência apenas quando seus planos estiverem
   validados. Conferir que cada mudança preserva autoria e histórico.
3. Interpretar fórmulas, denominadores, período e ausência de dados dos KPIs.
   Conclusões, apontamentos e avanço são medidas operacionais; não constituem
   classificação automática de pessoas nem parecer fiscal.
4. Exportar relatórios diário, semanal, mensal e personalizado em Excel/PDF.
   Comparar o recorte com o painel e verificar que contas sem acesso a custos
   não recebem esses valores, inclusive no histórico e nas exportações.
5. Exercitar o custo autorizado: `minutos / 60 × custo/hora` informado no
   lançamento, com arredondamento decimal para centavos. Valor não informado
   permanece indisponível. O sistema não presume salário, honorário ou margem.

O aceite do treinamento registra participantes por função, cenários realizados,
dúvidas, responsáveis pelos ajustes e autorização para iniciar o piloto. Não
incluir credenciais, nomes reais ou conteúdo de clientes em evidências públicas.

## Pré-requisitos técnicos e de armazenamento

Usar o procedimento systemd existente de
[deploy automático](../../devops/autodeploy/README.md), as dependências da
[versão web](../../devops/requirements-web.txt) e a lista geral de
[requisitos](../../requirements.txt). Não usar o gerenciador legado `ctl.sh` na
instalação atual. Não alterar portas, quantidade de processos ou cron neste
trabalho.

O SMTP permanece desligado, com o drop-in atual preservado. Alertas internos
podem ser conferidos sem envio de e-mail. A autorização posterior para concluir
o PDF não fornece as credenciais da conta. A ativação também exige adequar o
contrato do executor, que hoje rejeita SMTP em produção. Não retirar essa
proteção para contornar o gate; seguir a dependência registrada na spec 024.

| Variável | Finalidade e regra |
|---|---|
| `AUDITORIA_WEB_DADOS` | Diretório persistente fora do repositório; preservar a configuração existente |
| `AUDITORIA_QUALIDADE_S3_BUCKET` | Bucket privado destinado às evidências |
| `AUDITORIA_QUALIDADE_S3_ENDPOINT` | Endpoint opcional, somente HTTPS, sem usuário/senha, query ou caminho adicional |
| `AUDITORIA_QUALIDADE_S3_REGION` | Região opcional do serviço de objetos |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Nomes reconhecidos pela cadeia padrão do SDK quando esse método de credencial for escolhido; não são os únicos métodos possíveis |
| `AUDITORIA_QUALIDADE_ANEXOS_LOCAL` | Habilitação explícita exclusivamente para desenvolvimento/teste; manter desabilitada em produção |
| `AUDITORIA_QUALIDADE_ANEXOS_PRIVADO` | Alternativa da spec 024: valor `1` habilita a pasta privada persistente; não combinar com modo local/S3 |
| `AUDITORIA_QUALIDADE_ANEXOS_LIMITE_MB`, `AUDITORIA_QUALIDADE_ANEXOS_RESERVA_MB` | Quota total e reserva livre no modo privado; padrão 1024 MiB cada |
| `AUDITORIA_SMTP_HOST`, `AUDITORIA_SMTP_PORTA`, `AUDITORIA_SMTP_USUARIO`, `AUDITORIA_SMTP_SENHA`, `AUDITORIA_SMTP_REMETENTE`, `AUDITORIA_SMTP_TLS` | Configuração já existente de envio; permanece inativa |

Valores e credenciais ficam em configuração privada do ambiente, nunca no Git,
na issue, no relatório público ou em comandos registrados no chat. Qualquer
arquivo novo com credenciais precisa ter acesso restrito e cópia de recuperação
separada; não o incluir como configuração comum do autodeploy.

Quando S3 for o modo escolhido, o responsável técnico deve comprovar acesso privado ao bucket, TLS, permissões
restritas ao prefixo de evidências, versionamento, retenção e recuperação.
Autorizar somente as operações necessárias à aplicação e à compensação de uma
gravação que não chegou a ser vinculada ao banco. A interface não oferece
exclusão de evidências de negócio. Não conceder acesso anônimo ou publicar URLs
de objetos. O download passa pela autorização da aplicação e confere tamanho e
SHA-256 antes da entrega.

O indicador de disponibilidade de anexos verifica configuração e dependências;
não prova conectividade, credenciais válidas ou política privada do bucket. O
ensaio de S3 deve usar ambiente e objetos sintéticos autorizados. Os testes
locais usam cliente S3 falso e não comprovam uma configuração externa real.

### Backup dos objetos e dos metadados

No modo privado da spec 024, os bytes ficam na pasta persistente de dados e
entram na cópia integral do autodeploy com os bancos. É preciso preservar também
a configuração do modo e ensaiar a recuperação conjunta. Cópia no mesmo servidor
não equivale a backup externo. Não trocar o backend de uma instalação com
evidências sem migração e verificação dos objetos.

No modo S3, os bytes do anexo ficam no bucket; os vínculos, chave do objeto, tamanho e SHA-256
ficam em `qualidade_anexo`, no `clientes.db`. O backup atual do autodeploy copia
arquivos locais e **não inclui automaticamente os objetos S3**. Configurar e
ensaiar essa proteção é pré-requisito para liberar anexos reais.

Manter versionamento no armazenamento e uma cópia separada recuperável dos
objetos. Versionamento sozinho não substitui backup. Registrar no manifesto
privado as chaves, versões quando disponíveis, tamanhos, resumos e o snapshot
de banco correspondente. A aplicação usa chave opaca e SHA-256; não grava o
identificador da versão S3 no banco.

Definir um ponto de corte consistente, com gravações suspensas durante a captura
ou mecanismo de cópia que demonstre a correspondência com o snapshot escolhido.
Na validação, cada metadado deve localizar um objeto com os mesmos bytes. Cópias
de banco e objetos precisam ser recuperadas juntas em ambiente isolado, sem
abrir os bancos originais do backup. Definir retenção, localização, acesso,
responsável, frequência e ensaio periódico antes da operação real.

## Publicação futura e schema 4

O candidato introduz `QualidadeStore` no ensaio de migração do
[runner](../../devops/autodeploy/runner.py), além das novas dependências. Portanto,
o pacote de controle mudou: **a futura promoção não pode depender apenas do
merge em main**. O executor instalado não se atualiza sozinho e deve ser
reinstalado pelo procedimento atual antes de liberar o ciclo de autodeploy.

Somente após aprovação de publicação e do SHA exato:

1. Preparar a janela e avisar os usuários. Pausar o timer e aguardar o executor
   encerrar; pausar o timer não interrompe um ciclo em andamento.
2. Revisar o SHA candidato, seu OID de árvore `devops/autodeploy`, as dependências
   e o pacote completo. Preparar staging privado do root e seguir a seção
   “Preparar a instalação” do README do autodeploy, preservando as configurações
   adicionais e os segredos separados. Não executar instalador do checkout
   gravável pelo usuário da aplicação.
3. Conservar backup do venv e `pip freeze` anteriores à instalação de dependências.
   Resolver os novos pacotes em ambiente isolado, revisar diferenças e conferir
   versões e `pip check`. Preparar o runtime e reinstalar o executor a partir do
   pacote conferido, com o timer ainda parado. A mudança de manifests requer a
   transição administrativa do README: SHA atual e árvore candidata exatos,
   informados juntos por `--dependencies-from-sha` e `--dependencies-target-tree`.
   Não contornar os gates nem alterar o digest para simular uma instalação.
4. Promover a versão aprovada pelo fluxo de PR/merge commit do projeto e
   conferir o candidato efetivo e sua árvore aprovada. Só então executar
   `--check` e `enable`: antes do merge, o digest novo pode não corresponder ao
   pacote da main antiga. Reativar o timer somente quando o primeiro ciclo
   estiver autorizado. Deixar o executor avançar o checkout; não fazer
   avanço manual para produzir um no-op aparente.
5. Acompanhar testes isolados, backup anterior, migração de cópia de trabalho,
   preservação dos inventários, atualização, backup posterior e saúde final.
   Conferir `clientes.db` no schema 4, objetos e gatilhos esperados e integridade
   dos seis bancos. A migração acrescenta as tabelas de qualidade e preserva
   os registros existentes; não carrega clientes ou catálogo automaticamente.
6. Verificar SHA do checkout, candidato do executor, momento de início do
   processo, HTTP local/HTTPS, proteção dos catálogos, logs e ausência de hold.
   Registrar separadamente o que é correlação do processo, sem declarar uma
   atestação criptográfica da memória.
7. Conferir acesso autenticado com perfis aprovados e consultar os dados
   existentes sem mutá-los. Escritas de piloto só ocorrem após aceite específico.
   Confirmar um ciclo posterior saudável/no-op e preservar SMTP, cofre e o
   reinício diário existente às 04:45 de Salvador.

O cronograma não promete duração de indisponibilidade. A janela depende do volume
real de testes, bancos, arquivos, objetos e recursos da VM. Registrar tempos e
qualquer erro observado; saúde pública isolada não prova recuperação nem aceite
dos fluxos autenticados.

## Recuperação e critérios de interrupção

Falha de testes, preservação de dados, integridade, escopo de acesso, dependências
ou recuperação impede a liberação. Em falha após início da manutenção, preservar
`hold`, diagnóstico, SHA, inventários e backups; não apagar o marcador apenas
para forçar o serviço a iniciar. Seguir “Pausar, retomar e tratar falhas” no
README do autodeploy e o `RECUPERACAO.md` do backup correspondente.

O schema 4 é aditivo, mas isso não comprova compatibilidade do código anterior
com os novos dados. Não rebaixar `user_version`, apagar tabelas ou executar
rollback cego de código ou banco. Preferir correção adiante quando ela preservar
os registros; qualquer retorno exige ensaio sobre cópias isoladas. Restaurar
banco pode perder gravações posteriores e exige autorização específica.

Se houver restauração aprovada, recuperar o conjunto consistente de código,
venv, configurações, bancos e objetos S3 correspondentes. Não combinar `.db` e
`-wal` de cópias diferentes. Restaurar objetos pelas chaves esperadas e conferir
SHA/tamanho contra os metadados antes da reabertura. Repetir integridade, FK,
permissões, fluxo autenticado e saúde; reativar a automação por último.

## Custos e aceite operacional

Separar custo de trabalho do custo de infraestrutura. O sistema calcula o
primeiro pelos minutos registrados e custo/hora informado; esses valores exigem
permissão e não substituem orçamento ou dados financeiros do escritório.

Para infraestrutura, orçar armazenamento primário, versões, cópia separada,
requisições, transferência, retenção, espaço dos backups locais e tempo de
suporte/treinamento. Estimar volume pela quantidade e tamanho dos anexos e pela
retenção aprovada, sem inserir preços ou salários presumidos. Definir responsável
e acompanhamento de consumo antes de liberar anexos reais.

O aceite final registra: dez itens homologados, testes e preview aprovados,
matriz de acessos conferida, usuários treinados, backup e recuperação ensaiados,
SHA publicado e ciclo do executor validados, S3 privado e recuperável quando
utilizado, SMTP preservado e resultados do piloto. Implementação concluída não
significa configuração operacional, treinamento ou deploy já executados.
