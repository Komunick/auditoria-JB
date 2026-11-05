# Auditoria Fiscal Web — implantação no servidor

O site substitui a distribuição do `AuditoriaFiscal.exe`: os usuários acessam
pelo navegador na rede interna e **atualizar o sistema = atualizar o servidor
uma única vez**.

## Requisitos do servidor (Windows)

- Python 3.11+ no PATH (`python --version`)
- Git (para atualizar via `git pull`)

## Primeira instalação

```powershell
git clone <repositorio> C:\auditoria-fiscal
cd C:\auditoria-fiscal
.\servidor.ps1     # cria .venv, instala dependencias e sobe na porta 8600
```

Acesse `http://<ip-do-servidor>:8600`. No **primeiro acesso** o site pede a
criação do usuário administrador. A partir daí tudo é feito pela aba
**Administração** do próprio site — veja a seção abaixo.

## Clientes e cofre de senhas (aba 9)

Somente web. Cadastro dos clientes do escritório no lugar da planilha de
senhas, com as senhas de portais (SEFAZ, Prefeitura, código de acesso e
outros) num **cofre criptografado**, os certificados digitais e o aviso de
vencimento. Spec: `specs/012-cadastro-clientes-cofre/`.

**Chave do cofre (obrigatória para as senhas).** Gere uma vez, **no próprio
servidor**, e guarde (só precisa do Python, nada do projeto):

```
python3 -c "import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

(no Windows, `python` no lugar de `python3`). Sai uma linha de 44 caracteres
terminada em `=`. Não mande a chave por WhatsApp, e-mail ou chat.

Defina a saída na variável `AUDITORIA_COFRE_CHAVE` do serviço (na VM, no
drop-in do systemd, como as variáveis de segurança) e reinicie. Sem a chave o
cadastro e os vencimentos funcionam, mas as senhas não podem ser vistas nem
gravadas — nunca existe modo "sem criptografia".

- **Chave perdida = senhas perdidas.** Guarde uma cópia num lugar seguro.
- **Chave e backup nunca juntos.** O backup de `clientes.db` sem a chave não
  revela nada; com a chave ao lado, o cofre não protege nada.
- **Trocar de chave:** gere uma nova, ponha a antiga em
  `AUDITORIA_COFRE_CHAVES_ANTERIORES` (lista separada por vírgula) e a nova em
  `AUDITORIA_COFRE_CHAVE`. As senhas antigas continuam abrindo; cada senha
  regravada passa para a chave nova.

**Permissões.** Nenhuma entra no padrão de usuário novo. `aba.clientes` abre a
aba e **não mostra senha**; `cofre.ver` revela uma senha por vez, depois de a
pessoa confirmar a própria senha (vale 15 minutos naquela sessão), com limite
de 30 por hora; `cofre.editar` grava e troca senhas sem dar o direito de ver;
`clientes.editar`, `clientes.importar`, `clientes.exportar` (o Excel nunca traz
senha) e `vencimentos.configurar` completam. Administrador tem todas. Quem viu
cada senha fica em "Quem viu senhas" (exige `admin.historico`).

**Importar a planilha atual.** Aba 9 → Importar → planilha. A prévia mostra o
que entra, o que atualiza e o que precisa de atenção; nada é gravado antes de
confirmar, e o arquivo enviado é apagado assim que é lido. Depois de importar,
tire a planilha original de circulação: ela tem as senhas em texto aberto.

**Certificados da pasta da rede.** O servidor não enxerga a rede do escritório.
Num computador de lá, com o projeto e o `.venv`:

```powershell
.\.venv\Scripts\python.exe coletar-certificados.py "X:\CERTIFICADOS DIGITAIS ATUALIZADOS"
```

Ele lê cada `.pfx` com a senha do `_info`, grava `coleta-certificados-*.json`
**sem senha, chave nem certificado** e mostra um resumo. Envie o arquivo em
Importar → certificados e apague-o depois (ele tem nomes e CNPJs).

## Emissão de NFS-e (aba 8)

Somente web. A ferramenta importa a lista do cliente (planilha-modelo ou
texto colado da conversa), confere cada nota, mostra o lote para revisão e,
na aprovação, gera a DPS do padrão nacional validada no XSD oficial.

**Fase 2 (spec 008): transmissão à produção restrita, sem valor fiscal.** Num
lote aprovado, quem tem `nfse.transmitir` envia as DPS à produção restrita da
Sefin Nacional com o certificado A1 (.pfx + senha) da escola. O certificado vai
no próprio pedido, é usado só durante a transmissão e **não fica guardado**
(nem no banco, nem em disco). Cada tentativa fica registrada com o XML
assinado e a resposta oficial; resultado incerto (tempo esgotado, erro do
servidor) é consultado na Sefin antes de qualquer reenvio. Produção de verdade
continua desligada (Fase 3).

**Perfil pelo certificado (spec 009).** No formulário de perfil, o certificado
A1 da escola preenche sozinho o CNPJ e a razão social (lidos do próprio
certificado) e, consultando a parametrização do ADN do Sistema Nacional em
produção (só leitura, nada é emitido), se o convênio do município está ativo e a
alíquota dos códigos das turmas. Os campos preenchidos ficam marcados até a
pessoa salvar; nada é gravado na consulta e o certificado não fica guardado. O
resto do perfil (IM/CNC, regime do Simples, tributos aproximados, endereço do
tomador, série, modelo, turmas) não tem consulta por CNPJ e continua manual.

| Variável | Para quê |
|---|---|
| `AUDITORIA_NFSE_ASSINATURA` | `sha256` (padrão) ou `sha1`, se a Sefin recusar a assinatura com E0714 |
| `AUDITORIA_NFSE_TIMEOUT` | segundos de espera por resposta da Sefin (padrão 60) |
| `AUDITORIA_NFSE_CA_EXTRA` | arquivo PEM com AC extra, se o certificado do servidor da Sefin não estiver no sistema |
| `AUDITORIA_NFSE_SEFIN_URL` / `AUDITORIA_NFSE_ADN_URL` | só para testes; fora de `*.producaorestrita.nfse.gov.br` o servidor recusa |
| `AUDITORIA_NFSE_PARAMETROS_URL` | parametrização do ADN para o perfil pelo certificado; padrão `https://adn.nfse.gov.br/parametrizacao` (produção, só leitura); aceita só o ADN |

O administrador libera `aba.nfse` e, separadamente, `nfse.perfis`,
`nfse.importar`, `nfse.aprovar_emitir`, `nfse.exportar` e `nfse.transmitir`.
Usuário novo vem só com a aba. A aba mostra nomes de alunos e CPFs de
responsáveis: libere com o mesmo cuidado de qualquer dado pessoal.

O schema do `nfse.db` é criado sozinho na primeira abertura. Os XSD oficiais
ficam em `dados/nfse/xsd/v1.01` (no Git, sem alteração).

**Antes de usar com dados reais**, o endurecimento de segurança (cookie
`Secure`, checagem de Origin/Host, limite de tentativas de login) tem de estar
no ar — a constituição exige isso para exposição fora da rede interna.

## Patrimônio (aba 7)

Somente web. O administrador libera `aba.patrimonio` e, separadamente,
`patrimonio.cadastrar`, `.movimentar`, `.baixar`, `.inventariar` e
`.exportar`. A **baixa** tem permissão própria por ser irreversível.

O schema do `patrimonio.db` é criado e migrado sozinho na primeira abertura.
As etiquetas (`JBF-000001`) são sequenciais e **imutáveis** — o banco recusa
alteração por trigger, porque elas ficam coladas nos equipamentos.

## Conciliação Fiscal (aba 6)

A ferramenta é **somente web**. Depois de atualizar, o administrador precisa
liberar as permissões: `aba.conciliacao` é o portão, e cada ação exige
cumulativamente a aba e o slug próprio (`conciliacao.importar`,
`.revisar`, `.aprovar`, `.resolver_excecao`, `.exportar`,
`.preencher_modelo`, `.incluir_pendentes`).

Usuários **já existentes não recebem nada automaticamente** — a tabela de
permissões guarda só concessões explícitas. Para usuários novos, a tela de
administração pré-marca apenas *abrir a aba* e *importar*.

O schema do `conciliacao.db` é criado e migrado sozinho na primeira abertura;
não há passo manual de migração.

## Usuários, permissões e histórico

A aba **Administração** (visível para administradores) tem duas telas:

**Usuários e permissões.** O administrador cria usuários, troca senhas,
desativa e define, caixa por caixa, o que cada um alcança:

- **Abas**: quais das 5 ferramentas aparecem para a pessoa. Sem a aba, ela nem
  vê a ferramenta e o servidor recusa as rotas dela.
- **Ações sensíveis**: dentro de uma aba liberada, o que ela pode de fato
  fazer — marcar conferência, corrigir campo fiscal, corrigir **em lote**,
  editar a composição, gerar Livro Fiscal/Inconsistências/**SPED corrigido**,
  exportar as planilhas, corrigir produtos e gerar a nova base.

Quem é **administrador** tem todas as permissões automaticamente (as caixas
somem, porque não recortam nada) e administra os demais. Um usuário novo já
vem com uma sugestão marcada: vê todas as ferramentas e trabalha nelas, mas as
ações que mudam número fiscal ou geram a saída oficial ficam de fora até o
administrador liberar.

Duas travas de segurança: o **último administrador ativo** não pode ser
rebaixado nem desativado (senão ninguém mais criaria usuários), e desativar
alguém ou trocar a senha dele **encerra as sessões abertas** na hora.

**Histórico de acessos.** Responde, para qualquer pessoa e período: **quando
acessou, o que acessou, o que fez e quando saiu.** Registra entrada e saída
(inclusive sessão expirada por tempo e tentativa de login sem sucesso),
navegação por aba, uploads e processamentos, mutações fiscais (com o valor de
antes e depois), downloads gerados e ações administrativas — sempre com
usuário, data/hora, IP e o resultado (`ok`, `negado` ou `erro`, de modo que
uma tentativa barrada por falta de permissão também fica registrada). Tem
filtros por usuário, categoria, ação, período e texto, e exporta em CSV.

Esse histórico é a trilha de **uso do sistema**; ele não substitui a trilha
**fiscal** que continua em `conferencia.db` (a correção em si, para o Fisco).

## Atualização

```powershell
cd C:\auditoria-fiscal
git pull
# reinicie o servidor.ps1 (Ctrl+C e rodar de novo, ou reiniciar o servico)
```

Os usuários não precisam limpar o cache do navegador: o site é servido com
`Cache-Control: no-cache`, então cada carga confere com o servidor se o
arquivo mudou (na rede interna isso custa um `304`). Sem isso, alguém poderia
ficar com metade do sistema velho depois de uma atualização.

As tabelas novas (permissões e histórico) entram sozinhas na primeira
execução — o banco existente não perde nada.

### Conferir a versão e os ciclos do agendador (spec 015)

No início do processo, a linha INFO `aplicacao_inicio` registra o SHA Git
completo observado, sua origem e o estado da árvore. Compare esse SHA com o
commit autorizado para o deploy e confira o horário da inicialização. A
captura acontece uma única vez: atualizar o checkout com o processo ligado
não muda o valor anunciado. Reinicie o mesmo serviço após atualizar o código.

Com uma sessão de **administrador autenticado**, `GET /api/estado` acrescenta
o objeto `operacao`. Não é uma rota separada. Seus campos são:

- `versao.sha`: SHA completo ou `null` quando indisponível;
- `versao.origem`: `git` ou `indisponivel`;
- `versao.arvore`: `limpa`, `alterada` ou `desconhecida`;
- `versao.iniciado_em`: instante UTC da inicialização;
- `agendador`: diagnóstico agregado do último ciclo, inicialmente em estado
  `aguardando`.

A resposta de usuários comuns ou anônimos conserva os campos anteriores e
não inclui `operacao`. Não forneça senha, cookie ou token de administrador em
comandos compartilhados. A versão e o diagnóstico não expõem caminhos,
branches, remotes, ambiente, destinatários ou dados de clientes.

Cada ciclo do agendador registra uma linha INFO de sucesso, **inclusive com
zero setores ou tarefas**, com horário, competência, duração e contagens
agregadas de gerações, tarefas criadas e resultados de envio. O intervalo
continua sendo de 15 minutos, com no máximo quatro resumos por hora por
processo. Antes do horário de envio, `envios` pode ser `null`. Falhas registram
somente horário, etapa controlada e código fixo; não há mensagem da exceção
ou traceback. Falha ao fechar a conexão também impede anunciar sucesso.
O diagnóstico administrativo mostra o último ciclo, enquanto o histórico de
ciclos fica nos logs do serviço.

Na instalação com systemd, consulte o journal da unidade efetivamente usada,
desde a inicialização verificada; na execução manual, veja a saída do Uvicorn.
A configuração padrão INFO do Uvicorn já recebe essas linhas. Não é preciso
criar variável de ambiente, handler, timer, cron, serviço ou porta. A frequência
do agendador e as regras de geração e envio permanecem as mesmas.

**Limites da verificação.** O SHA identifica o checkout observado na
inicialização; não é uma atestação criptográfica dos módulos em memória.
Árvore `alterada` ou `desconhecida` não comprova execução exata de um commit.
Sem Git, sem repositório válido ou diante de timeout, a versão fica
`indisponivel` e a aplicação continua iniciando. Não substitua essa ausência
por um SHA informado manualmente. Os logs não comprovam entrega ou leitura
de e-mails e não substituem a auditoria do domínio.

## Dados do servidor

Tudo em `dados_web\` (fora do git):

- `auditoria_web.db` — usuários, sessões de login, permissões e o histórico de
  acessos
- `conferencia.db` — conferências, correções e sobrescritas (o MESMO formato
  do desktop; um banco único compartilhado pela equipe)
- `sessoes\<id>\` — uploads das sessões de trabalho (SPED/XMLs/planilhas);
  podem ser limpos periodicamente sem perder conferências
- `historico_produtos.csv` — trilha das correções de produtos
- `conciliacao.db` — Conciliação Fiscal: conciliações, versões, movimentos
  DIMP, proveniência, exceções, conflitos, revisões e a **trilha fiscal**
  (append-only, protegida por trigger no próprio SQLite)
- `patrimonio.db` — Patrimônio: bens, pessoas, locais, responsabilidades,
  movimentações (append-only) e inventários
- `nfse.db` — Emissão de NFS-e: perfis versionados, lotes, linhas recebidas,
  correções, rodadas de conferência, DPS geradas, tentativas de transmissão
  (com o XML assinado), NFS-e e DANFSe da produção restrita e a trilha do
  domínio (append-only, protegida por trigger). **Tem dados pessoais** (nomes
  de alunos, CPFs de responsáveis). Não guarda certificado nem senha
- `nfse\origens\<sha256>.xlsx` — as planilhas recebidas, imutáveis (o texto
  colado fica dentro do `nfse.db`)
- `clientes.db` — Clientes: cadastro, licenças, certificados, a trilha de
  alterações e a de **quem viu cada senha** (append-only, por trigger) e as
  senhas **cifradas**. A chave fica fora desta pasta (`AUDITORIA_COFRE_CHAVE`)
  Também guarda setores, carteira, obrigações, tarefas, eventos, gerações e
  registros dos resumos por e-mail (spec 013), com ocorrências de tarefas
  introduzidas pela spec 014, no schema 3.
- `conciliacao\origens\<sha256>.xlsx` — os relatórios da SEFAZ **originais**,
  imutáveis, nomeados pelo hash do conteúdo. São a evidência de cada número
  exibido: sem eles, a proveniência aponta para o vazio

### Backup

Copiar a pasta `dados_web\` inteira — **com o servidor parado**.

Os bancos rodam em modo **WAL**: parte das transações confirmadas vive no
arquivo `-wal` até o checkpoint. Copiar `dados_web\` com o site no ar pode
produzir um conjunto que abre sem erro e **está incompleto**, o que é pior que
uma falha visível. Duas formas seguras:

1. Parar o `servidor.ps1`, copiar a pasta, subir de novo (mais simples); ou
2. Com o site no ar, usar a API de backup do SQLite em cada `.db`:
   `.\.venv\Scripts\python.exe -c "import sqlite3; o=sqlite3.connect(r'dados_web\conciliacao.db'); d=sqlite3.connect(r'backup\conciliacao.db'); o.backup(d); d.close(); o.close()"`
   (o mesmo para `patrimonio.db`, `nfse.db` e `clientes.db`) e copiar `conciliacao\origens\`
   e `nfse\origens\` normalmente (os arquivos lá nunca mudam depois de
   criados).

Backup online automatizado é uma feature à parte; não presuma que a cópia
simples do diretório dá um snapshot consistente. Backups online de bancos
separados também não representam necessariamente o mesmo instante entre
eles. Para implantação com migração, prefira parar o serviço e copiar a pasta
inteira, com os seis bancos, arquivos `-wal`/`-shm` presentes e demais arquivos.
Preserve código, venv e configuração anteriores; arquivos com a chave do cofre
devem ter cópia protegida separada dos dados.

Valide a recuperação em uma **cópia de trabalho do backup**, mantendo o
original preservado. Construtores de Stores podem migrar bancos ao abrir;
não os use para apenas inspecionar produção ou o backup original. Verifique
integridade e chaves estrangeiras dos seis bancos e compare contagens
agregadas, sem expor registros ou valores do cofre.

## Variáveis de ambiente (opcionais)

- `AUDITORIA_WEB_PORTA` — porta do site (padrão 8600)
- `AUDITORIA_WEB_DADOS` — pasta de dados (padrão `dados_web\` no projeto)
- `AUDITORIA_WEB_MAX_UPLOAD_MB` — limite por arquivo enviado (padrão 2048; alto
  porque bancos Firebird `.fdb` de ERP passam de 300 MB)
- `AUDITORIA_COFRE_CHAVE` — chave do cofre de senhas da aba 9 (sem ela, o cofre
  fica desligado); `AUDITORIA_COFRE_CHAVES_ANTERIORES` — chaves antigas, só
  para decifrar depois de uma troca
- `AUDITORIA_CONCILIACAO_MAX_UPLOAD_MB` — limite **só** da Conciliação Fiscal
  (padrão 50). Relatório da SEFAZ tem poucos MB; um teto próprio e baixo reduz
  a superfície de zip bomb e de negação de serviço nessa porta. Valor inválido
  volta ao padrão — nunca vira "sem limite".

### Um worker, por enquanto

Sessões de trabalho e jobs vivem **em memória do processo**. Rodar o uvicorn
com mais de um worker faria um pedido cair num processo que não conhece a
sessão do outro. Mantenha um worker até que a fila seja externalizada.

## Tarefas e prazos (aba 10)

A primeira inicialização migra `clientes.db` para o **schema 3**, de forma
aditiva e transacional, preservando clientes, certificados, cofre, IDs e
trilhas existentes. A migração da spec 013 cria as tabelas de tarefas; a spec
014 acrescenta `tarefa.ocorrencia`, conserva tarefas anteriores como ocorrência
1 e amplia o índice de unicidade para cliente, obrigação, competência e
ocorrência. `auditoria_web.db` conserva a migração da spec 013 que acrescenta
o e-mail opcional dos usuários. Não altere os schemas manualmente.

Antes de atualizar, faça o backup consistente da pasta completa descrito
acima, incluindo os seis bancos. Instale os requisitos atualizados:
`xlrd>=2.0` permite ler as carteiras antigas em `.xls`; `.xlsx` continua usando
openpyxl. A spec 014 não exige novas dependências.

Se houver falha após iniciar a versão nova, pare o serviço e preserve também
uma cópia consistente desse estado antes de recuperar. **Não volte a executar
o código da spec 013 sobre `clientes.db` já migrado para schema 3.** Não faça
downgrade manual nem restauração cega: o agendador ou os usuários podem ter
gravado dados desde o backup. A recuperação precisa considerar em conjunto
código, venv, configuração e dados compatíveis; qualquer restauração que
descarte gravações posteriores exige avaliação e autorização específica.

Primeiro uso, pela administração e pela configuração da aba 10:

1. Cadastre **setores**, seus membros e responsáveis. Os membros precisam ser
   usuários ativos. Cadastre substituições com início, fim e motivo.
2. Cadastre **características**, escolhendo grupos exclusivos ou múltiplos,
   e marque os clientes. A marcação em lote substitui a seleção anterior.
3. Cadastre **obrigações** com as regras e os prazos fornecidos pelo escritório.
   O catálogo começa vazio: nenhum prazo fiscal é presumido pelo sistema.
4. Monte a **carteira**, manualmente ou importando `.xls`/`.xlsx`. Na prévia,
   confirme o cliente de cada linha, os contatos e as características sugeridas.
   Colunas de checklist não são importadas. O upload é apagado depois da leitura.
5. Confira os **feriados** e os ajustes por cliente. A validade dos ajustes é
   comparada ao primeiro dia da competência; início e fim são inclusivos.
6. Gere a competência pela **prévia**. Após a primeira configuração ou após
   mudanças de cadastro, use a geração manual para completar o mês corrente:
   tarefas já existentes não serão duplicadas nem alteradas.

As sete permissões da ferramenta não entram no padrão de novos usuários.
Os atalhos de perfil na administração ajudam a selecionar colaborador,
responsável e diretoria; revise as caixas antes de salvar. `tarefas.todas`
permite consulta geral. Para agir sobre um setor, o responsável precisa de
`tarefas.setor` e deve ser seu titular efetivo ou substituto vigente.
Administradores mantêm o acesso implícito. Atribuições, configurações, estados
e comentários ficam na trilha do domínio; eventos de tarefas não podem ser
alterados nem excluídos.

### Agendador e resumos internos

Uma thread começa com o FastAPI e verifica a geração do mês e os alertas a
cada 15 minutos. Usa a data de Salvador (UTC−3), grava carimbos em UTC e
retoma na próxima inicialização se o servidor estava desligado. Não requer
novo serviço nem nova porta. A geração automática é única por setor e
competência; o resumo é reservado no banco por pessoa e dia antes de enviar.
O reinício diário não repete operações já registradas.

Padrões: resumo a partir das **07:00**, aviso **3 dias** antes do vencimento
e inclusão de tarefas aguardando cliente há **mais de 5 dias**. Os valores
ficam na configuração da aba 10. A substituição resolve os destinatários e
as conferências de cada setor, sem reescrever a autoria das tarefas.

Cadastre o e-mail de cada pessoa em **Administração → Usuários**. Esta fase
envia somente para usuários internos ativos com acesso à aba 10; o e-mail
do cliente é cadastrado, mas não recebe resumo.

| Variável | Uso |
|---|---|
| `AUDITORIA_SMTP_HOST` | Servidor SMTP |
| `AUDITORIA_SMTP_PORTA` | Padrão 587 com STARTTLS ou 465 com SSL |
| `AUDITORIA_SMTP_USUARIO` | Usuário de autenticação, quando exigido |
| `AUDITORIA_SMTP_SENHA` | Senha, somente em variável de ambiente |
| `AUDITORIA_SMTP_REMETENTE` | Endereço de e-mail do remetente |
| `AUDITORIA_SMTP_TLS` | `starttls` (padrão) ou `ssl`; envio sem TLS não é aceito |

Na VM, guarde a configuração num `EnvironmentFile` fora do repositório, com
permissão `600`, como a configuração do cofre. A senha nunca vai para banco,
resposta HTTP ou log. Sem configuração válida, a tela informa **e-mail
desligado**, e os alertas no sistema continuam funcionando.

`envio_alerta` registra destino, contagens, resultado e um código de erro
sem credenciais. Reservas impedem reenvio automático no mesmo dia, inclusive
após falha ou desligamento do SMTP. Se houver queda entre a reserva e a
confirmação do envio, o registro permanece `em_envio`; confira a entrega antes de
qualquer ação operacional. SMTP não oferece confirmação transacional com
SQLite, por isso o sistema prioriza não duplicar mensagens. O próximo dia
tem uma nova tentativa. O resumo não confirma que a pessoa leu o e-mail.

Prévia de importação ou geração expira após 30 minutos, pertence a quem a
criou e é de uso único. Se a confirmação falhar ou a agenda mudar, gere uma
nova prévia. Apenas dados sintéticos devem entrar nos testes e no Git.

## Rodar como serviço (opcional)

Agendador de Tarefas → nova tarefa "Ao iniciar o computador" executando
`powershell -ExecutionPolicy Bypass -File C:\auditoria-fiscal\servidor.ps1`
com "Executar estando o usuário conectado ou não".

## Observações

- Rede interna (mesmo pressuposto dos demais sistemas). Exposição externa
  exige HTTPS/proxy na frente. O servidor já traz as defesas para isso
  (Origin nas mutações, cookie `Secure` atrás de HTTPS, limite de tentativas
  de login, `X-Forwarded-For` só do proxy declarado, nosniff/CSP na API); o
  endereço público e o IP do proxy entram pelas variáveis
  `AUDITORIA_HOSTS_CONFIAVEIS` e `AUDITORIA_PROXIES_CONFIAVEIS` (no
  serviço systemd, por `Environment=`) — o que cada uma faz está em
  `src/auditoria_fiscal/config.py`.
- O desktop (`dist\AuditoriaFiscal.exe`) continua funcionando durante a
  transição — mas conferências feitas no exe ficam no banco LOCAL da máquina
  (`%LOCALAPPDATA%\AuditoriaFiscal`), não no banco do servidor.
