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
   e copiar `conciliacao\origens\` normalmente (os arquivos lá nunca mudam
   depois de criados).

Backup online automatizado é uma feature à parte; não presuma que a cópia
simples do diretório dá um snapshot consistente.

## Variáveis de ambiente (opcionais)

- `AUDITORIA_WEB_PORTA` — porta do site (padrão 8600)
- `AUDITORIA_WEB_DADOS` — pasta de dados (padrão `dados_web\` no projeto)
- `AUDITORIA_WEB_MAX_UPLOAD_MB` — limite por arquivo enviado (padrão 2048; alto
  porque bancos Firebird `.fdb` de ERP passam de 300 MB)
- `AUDITORIA_CONCILIACAO_MAX_UPLOAD_MB` — limite **só** da Conciliação Fiscal
  (padrão 50). Relatório da SEFAZ tem poucos MB; um teto próprio e baixo reduz
  a superfície de zip bomb e de negação de serviço nessa porta. Valor inválido
  volta ao padrão — nunca vira "sem limite".

### Um worker, por enquanto

Sessões de trabalho e jobs vivem **em memória do processo**. Rodar o uvicorn
com mais de um worker faria um pedido cair num processo que não conhece a
sessão do outro. Mantenha um worker até que a fila seja externalizada.

## Rodar como serviço (opcional)

Agendador de Tarefas → nova tarefa "Ao iniciar o computador" executando
`powershell -ExecutionPolicy Bypass -File C:\auditoria-fiscal\servidor.ps1`
com "Executar estando o usuário conectado ou não".

## Observações

- Rede interna (mesmo pressuposto dos demais sistemas). Exposição externa
  exige HTTPS/proxy na frente.
- O desktop (`dist\AuditoriaFiscal.exe`) continua funcionando durante a
  transição — mas conferências feitas no exe ficam no banco LOCAL da máquina
  (`%LOCALAPPDATA%\AuditoriaFiscal`), não no banco do servidor.
