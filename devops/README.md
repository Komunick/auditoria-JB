# devops — deploy da Auditoria Fiscal Web numa VM Linux

Tudo que é preciso para colocar este sistema no ar numa VM, versionado junto com
o código: quem clona o repositório já leva o deploy junto. O `ctl.sh` tem a
mesma interface dos outros sistemas da Komunick — muda só o que está por baixo.

| | |
|---|---|
| Runtime | **Python 3.11+** com ambiente virtual em `.venv/` (criado pelo `install`) |
| Servidor | `servidor.py` → uvicorn + FastAPI (`src/auditoria_fiscal/web`) |
| Porta padrão | **8600** |
| Dados | `~/komunick/data/auditoria-data` (fora do repositório, nunca versionado) |
| Auto-início | **cron do usuário** — sem `sudo`, sem `systemd` |
| Log | `~/komunick/logs/auditoria-fiscal.log` |

Diferente dos sistemas em Node puro, aqui existe uma etapa de dependências: o
`install` cria o `.venv` e roda o `pip install -r requirements.txt`. O `update`
refaz isso **só quando o arquivo de requisitos muda**.

## Instalar numa VM nova

```bash
# 1. Python 3.11+ (o Mint 22 já vem com 3.12) e git
python3 --version

# 2. Clonar e instalar
mkdir -p ~/komunick/repos && cd ~/komunick/repos
git clone -b dev https://github.com/Komunick/auditoria-JB.git auditoria-fiscal
cd auditoria-fiscal
bash devops/ctl.sh install
```

O `install` cria as pastas de dados e log, monta o `.venv`, instala as
dependências, sobe o serviço e instala o cron (`@reboot` + a cada 2 minutos,
que ressobe se cair). A primeira instalação demora alguns minutos (pandas,
lxml e companhia baixam algumas centenas de MB). Ao final ele imprime o
endereço. Se a VM tiver firewall: `sudo ufw allow 8600/tcp`.

No **primeiro acesso** o site pede a criação do usuário administrador. Dali em
diante, usuários, permissões e histórico saem da aba **Administração** do
próprio site (veja o `README-servidor.md` na raiz).

### Se a VM não tiver o pacote `python3-venv`

É o caso da `mint-vm`: o módulo `venv` existe, mas o `ensurepip` não vem
(Debian/Ubuntu/Mint separam isso no pacote `python3-venv`) e não há `sudo` para
instalá-lo. O `ctl.sh` já trata: percebe que o venv nasceu sem `pip`, refaz com
`--without-pip` e busca o `pip` na rede pelo `get-pip.py` oficial — tudo dentro
do `.venv`, sem tocar no Python do sistema. O único requisito é a VM ter saída
para a internet (`pypi.org` e `bootstrap.pypa.io`).

Se a saída para a internet for bloqueada, a alternativa é gerar o venv em outra
máquina igual e copiar a pasta — ou instalar o `uv` (`curl -LsSf
https://astral.sh/uv/install.sh | sh`, também sem sudo) e montar o ambiente com
`uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python`;
o `ctl.sh` usa o `.venv` que encontrar, não importa quem o criou.

## Dia a dia

```bash
bash devops/ctl.sh status      # porta, PID, commit, venv e resposta HTTP
bash devops/ctl.sh logs 60     # últimas 60 linhas do log
bash devops/ctl.sh update      # git pull + dependências (se mudaram) + reinicia
bash devops/ctl.sh restart
```

**`update` é o comando de deploy.** `git pull` sozinho não basta: o Python
mantém o código já carregado em memória, então sem reiniciar a VM continua
servindo a versão antiga. O `update` faz as duas coisas — e ainda compara a
impressão digital do `requirements.txt` (guardada em `.venv/.devops-requisitos`)
para reinstalar as dependências quando alguém acrescenta uma biblioteca.

Reiniciar **perde as sessões de trabalho em andamento** (uploads carregados,
comparação em tela) — é assim por projeto, o estado das abas vive em memória.
Os arquivos já enviados e tudo que foi gravado em banco continuam lá. Prefira
atualizar fora do horário de uso.

## Ajustar portas e caminhos

Os valores ficam em [`config.env`](config.env) e podem ser sobrescritos por
variável de ambiente sem editar arquivo nenhum:

```bash
PORT=9600 DATA_DIR=/dados/auditoria bash devops/ctl.sh start
KOMUNICK_BASE=/srv/komunick bash devops/ctl.sh install
```

| Variável | Para quê |
|---|---|
| `PORT` | porta HTTP (padrão 8600) |
| `DATA_DIR` | pasta dos dados (padrão `$KOMUNICK_BASE/data/auditoria-data`) |
| `LOG_DIR` | pasta dos logs (padrão `$KOMUNICK_BASE/logs`) |
| `KOMUNICK_BASE` | raiz de dados e logs (padrão `~/komunick`) |
| `PYTHON_BIN` (config.env) | fixa o Python usado para criar o venv |
| `VENV_DIR` (config.env) | põe o ambiente virtual fora do repositório |
| `MAX_UPLOAD_MB` (config.env) | teto por arquivo enviado (padrão do código: 2048 MB) |
| `REQUISITOS_REL` (config.env) | qual lista de dependências instalar |

Não existe variável de interface (`HOST`): o `servidor.py` escuta em `0.0.0.0`
de propósito, para atender a rede interna.

Sem `PYTHON_BIN`, o script procura nesta ordem: `/usr/bin/python3` →
`/usr/local/bin/python3` → `python3` do `PATH` → `python`, aceitando só 3.11+.
Os caminhos absolutos vêm primeiro de propósito: o cron roda com `PATH` mínimo.
Esse Python é usado **só para criar o venv** — depois quem roda tudo é o
`.venv/bin/python`.

### Instalação enxuta (disco apertado)

O `requirements.txt` da raiz serve às duas versões do sistema e traz o
**PySide6** (interface desktop, centenas de MB) e o **fdb**, que o site nunca
importa. Se o disco da VM apertar, aponte o `config.env` para a lista reduzida
que já vem aqui:

```bash
REQUISITOS_REL="devops/requirements-web.txt"
```

Ela é uma cópia manual e **não se atualiza sozinha**: ao mexer no
`requirements.txt` da raiz, confira se a mudança precisa vir para
[`requirements-web.txt`](requirements-web.txt). Enquanto o `config.env` apontar
para ela, é o *hash dela* que o `update` vigia — mudanças no `requirements.txt`
da raiz passam despercebidas.

## Dados e backup

Os dados vivem **fora** do repositório, em `~/komunick/data/auditoria-data`
(é o `dados_web/` da documentação da raiz, realocado pela variável
`AUDITORIA_WEB_DADOS`):

| | |
|---|---|
| `auditoria_web.db` | usuários, sessões de login, permissões e histórico de acessos |
| `conferencia.db` | conferências, correções e sobrescritas — a trilha fiscal |
| `sessoes/<id>/` | uploads das sessões de trabalho (SPED, XMLs, planilhas) |
| `historico_produtos.csv` | trilha das correções de produtos |

**Backup = copiar a pasta inteira**, com o serviço parado. Atualizar o código
nunca toca nesses arquivos.

As **bases legais** (`anexo1_ba.csv`, `monofasico.csv`, `ncm_tipi.csv`,
`parametros.json`…) vêm da pasta `dados/` do próprio repositório, que é
versionada — atualizar o sistema atualiza as tabelas. Para usar uma versão
própria sem mexer no repositório, crie `~/komunick/data/auditoria-data/dados/`:
existindo, ela tem prioridade.

**Os uploads se acumulam.** Cada sessão de trabalho grava em `sessoes/<id>/` e
só some quando a pessoa fecha a sessão na tela; reiniciar o servidor descarta a
sessão da memória mas deixa os arquivos. Com SPED e `.FDB` grandes isso enche
disco depressa (a `mint-vm` tinha 4,2 GB livres na última medição). Limpeza
periódica, com o serviço parado:

```bash
bash devops/ctl.sh stop
find ~/komunick/data/auditoria-data/sessoes -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
bash devops/ctl.sh start
```

## O que não funciona em Linux

- **Importar cadastro de produtos de banco Firebird (`.FDB`)**: o motor
  embedded fica em `vendor/firebird25`, que é binário Windows e nem é
  versionado. O sistema não quebra — a tela avisa que o motor não está
  disponível. Quem precisar disso continua usando o desktop no Windows, ou
  exporta a base em `.xlsx`/`.csv` e envia pelo site.
- **Empacotamento em `.exe`** (`empacotar.ps1`, PyInstaller, PySide6): é do
  fluxo Windows e não tem nada a ver com a VM.

## Se algo der errado

| Sintoma | O que olhar |
|---|---|
| `install` reclama do venv sem pip | é o caminho normal em Mint/Ubuntu; ele se recria sozinho. Se falhar, o download do `get-pip.py` foi bloqueado — veja a saída para a internet |
| `pip install` falha em `lxml`/`pandas` | quase sempre disco cheio (`df -h /home`) ou versão de Python fora do 3.11+ |
| `install` diz que a porta está ocupada | `ss -ltnp \| grep 8600` — outro serviço ou uma instância antiga |
| Processo sobe mas a porta não abre | `logs 60`: erro de import (dependência faltando) ou de permissão na pasta de dados |
| Serviço cai sozinho e volta | é o cron fazendo o trabalho dele; veja o motivo em `logs` |
| Cron não sobe no boot | `crontab -l` deve ter duas linhas com `# devops:auditoria-fiscal` |
| Python não encontrado pelo cron | preencha `PYTHON_BIN` no `config.env` com o caminho absoluto |
| Site abre mas as telas somem/quebram | é permissão, não deploy: confira a aba Administração |
| Site responde mas sem os dados certos | confira `status`: a linha `dados` aponta para a pasta esperada? |
| `update` não pegou uma biblioteca nova | `status` mostra as dependências como "em dia"? Apague `.venv/.devops-requisitos` e rode `update` de novo |

## Convivência com a instalação legada

A VM atual (`mint-vm`) roda três sistemas Node por um script antigo em
`~/komunick/bin/ensure.sh` (patrimônio 8080, chamados financeiros 8090, TI
8085) e o brazil-tms em Docker. Este sistema **não** está nesse script, então o
`install` instala o cron normalmente, com a marca `# devops:auditoria-fiscal` —
sem conflito com as duas linhas `# komunick` que já existem. Se um dia o
`ensure.sh` legado passar a cuidar deste serviço, o `install` percebe, avisa e
não instala o cron, para não haver dois donos do mesmo processo.
