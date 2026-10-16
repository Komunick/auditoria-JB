#!/usr/bin/env bash
# Controle do serviço numa VM Linux — instalar, subir, parar, atualizar, diagnosticar.
#
#   ./devops/ctl.sh {install|ensure|start|stop|restart|status|logs|update}
#
# Python (FastAPI + uvicorn): o `install` cria um ambiente virtual dentro do
# próprio repositório e instala o requirements.txt — não precisa de sudo nem
# systemd. O serviço sobe com setsid (sobrevive ao fim da sessão SSH) e o cron
# o ressobe sozinho a cada 2 minutos se ele cair (subcomando `ensure`).
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/.." && pwd)"
# shellcheck source=config.env
. "$AQUI/config.env"

# O cron roda com PATH mínimo e em algumas distros ss/setsid moram em sbin.
PATH="$PATH:/usr/local/bin:/usr/sbin:/sbin"

# ---------------------------------------------------------------------------
# Configuração efetiva (ambiente > config.env > padrão).
# ---------------------------------------------------------------------------
BASE="${KOMUNICK_BASE:-$HOME/komunick}"
ENTRADA="$REPO/$ENTRADA_REL"
REQUISITOS="$REPO/$REQUISITOS_REL"
VENV="${VENV_DIR:-$REPO/.venv}"
PY="$VENV/bin/python"
PORTA="${PORT:-$PORTA_PADRAO}"
DADOS="${DATA_DIR:-$BASE/data/$DATA_SUBDIR}"
LOG_DIR="${LOG_DIR:-$BASE/logs}"
LOG="$LOG_DIR/$SERVICO.log"
MARCA="# devops:$SERVICO"
# Impressão digital do requirements.txt já instalado — é o que faz o `update`
# reinstalar as dependências só quando elas realmente mudam.
SELO="$VENV/.devops-requisitos"

msg() { printf '%s\n' "$*"; }
erro() { printf 'ERRO: %s\n' "$*" >&2; }

# Acha o Python BASE, usado só para criar o venv. O cron roda com PATH mínimo,
# então os caminhos absolutos vêm antes de confiar no PATH. Exige 3.11+ (é o
# piso do projeto).
achar_python_base() {
  if [ -n "${PYTHON_BIN:-}" ]; then
    [ -x "$PYTHON_BIN" ] && { printf '%s' "$PYTHON_BIN"; return 0; }
    erro "PYTHON_BIN aponta para algo que não é executável: $PYTHON_BIN"; return 1
  fi
  local p
  for p in /usr/bin/python3 /usr/local/bin/python3 \
           "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)"; do
    [ -n "$p" ] && [ -x "$p" ] || continue
    "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || continue
    printf '%s' "$p"; return 0
  done
  erro "Python 3.11+ não encontrado. Instale (apt install python3) ou preencha PYTHON_BIN no devops/config.env."
  return 1
}

pid_do_servico() { pgrep -f "^.*[ ]$ENTRADA$" 2>/dev/null | head -1; }
esta_no_ar() { [ -n "$(pid_do_servico)" ]; }

porta_ocupada() {
  if command -v ss >/dev/null 2>&1; then ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORTA$"
  else netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORTA$"; fi
}

# ---------------------------------------------------------------------------
# Ambiente virtual e dependências.
# ---------------------------------------------------------------------------

# Cria o .venv. Em Debian/Ubuntu/Mint o pacote python3-venv costuma faltar (e
# sem sudo não dá para instalar): o módulo venv existe, mas o ensurepip não,
# então o venv nasce sem pip. Nesse caso recriamos com --without-pip e trazemos
# o pip da rede com o get-pip.py oficial. É exatamente o caso da mint-vm.
criar_venv() {
  [ -x "$PY" ] && return 0
  local base; base=$(achar_python_base) || return 1
  msg "  criando ambiente virtual em $VENV ($("$base" -V 2>&1))"
  if "$base" -m venv "$VENV" >/dev/null 2>&1 && [ -x "$VENV/bin/pip" ]; then
    return 0
  fi
  msg "  venv veio sem pip (falta o pacote python3-venv): recriando com --without-pip"
  if [ -e "$VENV" ] && [ ! -f "$VENV/pyvenv.cfg" ]; then
    erro "$VENV existe e não parece um ambiente virtual — confira e remova à mão."; return 1
  fi
  rm -rf "$VENV"
  "$base" -m venv --without-pip "$VENV" || {
    erro "não consegui criar o ambiente virtual com $base."; return 1; }
  instalar_pip
}

# Instala o pip DENTRO do venv a partir do get-pip.py oficial (não precisa de
# sudo nem de pacote do sistema; precisa de saída para a internet).
instalar_pip() {
  local get="$VENV/get-pip.py" url="https://bootstrap.pypa.io/get-pip.py"
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$url" -o "$get"
  elif command -v wget >/dev/null 2>&1; then wget -qO "$get" "$url"
  else erro "sem curl e sem wget para baixar o pip."; return 1; fi
  [ -s "$get" ] || { erro "download do get-pip.py falhou — a VM tem saída para a internet?"; return 1; }
  "$PY" "$get" >/dev/null 2>&1 || { erro "get-pip.py falhou."; rm -f "$get"; return 1; }
  rm -f "$get"
  "$PY" -m pip --version >/dev/null 2>&1 || { erro "o pip continua indisponível dentro do venv."; return 1; }
  msg "  pip instalado no venv ($("$PY" -m pip --version 2>/dev/null))"
}

hash_requisitos() {
  [ -f "$REQUISITOS" ] || { printf 'sem-arquivo'; return 0; }
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$REQUISITOS" | awk '{print $1}'
  elif command -v md5sum >/dev/null 2>&1; then md5sum "$REQUISITOS" | awk '{print $1}'
  else cksum "$REQUISITOS" | awk '{print $1 "-" $2}'; fi
}

# Verdadeiro quando nunca instalamos ou quando o arquivo de requisitos mudou.
deps_desatualizadas() {
  [ -s "$SELO" ] || return 0
  [ "$(cat "$SELO" 2>/dev/null)" != "$(hash_requisitos)" ]
}

instalar_deps() {
  [ -f "$REQUISITOS" ] || { erro "não achei $REQUISITOS — o repositório está completo?"; return 1; }
  [ -x "$PY" ] || { erro "ambiente virtual ausente em $VENV."; return 1; }
  msg "  instalando dependências de $REQUISITOS_REL (na primeira vez demora alguns minutos)"
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
  "$PY" -m pip install --no-cache-dir -r "$REQUISITOS" || { erro "pip install falhou (o erro está acima)."; return 1; }
  hash_requisitos > "$SELO"
  msg "  dependências em dia"
}

# ---------------------------------------------------------------------------
# Subcomandos.
# ---------------------------------------------------------------------------
cmd_start() {
  if esta_no_ar; then msg "$NOME_LONGO já está no ar (PID $(pid_do_servico))."; return 0; fi
  if porta_ocupada; then erro "a porta $PORTA já está ocupada por outro processo."; return 1; fi
  [ -f "$ENTRADA" ] || { erro "não achei $ENTRADA — o repositório está completo?"; return 1; }
  [ -x "$PY" ] || { erro "sem ambiente virtual em $VENV. Rode: bash devops/ctl.sh install"; return 1; }
  mkdir -p "$DADOS" "$LOG_DIR"
  # PYTHONUNBUFFERED=1 senão a saída do uvicorn fica presa no buffer quando o
  # destino é arquivo, e `logs` mostraria um log sempre atrasado.
  local -a AMBIENTE=(PYTHONUNBUFFERED=1 "$PORTA_ENV=$PORTA" "$DATA_ENV=$DADOS")
  [ -n "${MAX_UPLOAD_MB:-}" ] && AMBIENTE+=("AUDITORIA_WEB_MAX_UPLOAD_MB=$MAX_UPLOAD_MB")
  # A subshell inteira vai para /dev/null e só depois o exec assume o log: sem
  # isso ela herda o canal do SSH e `ctl.sh start` remoto fica pendurado até o
  # serviço morrer. O setsid destaca o processo da sessão que o iniciou.
  (
    cd "$REPO" || exit 1
    exec env "${AMBIENTE[@]}" setsid "$PY" "$ENTRADA" >>"$LOG" 2>&1 </dev/null
  ) >/dev/null 2>&1 </dev/null &
  disown 2>/dev/null || true
  # Importar pandas/lxml/fastapi leva alguns segundos: espera a porta abrir em
  # vez de dar um veredito cedo demais.
  local _i
  for _i in $(seq 1 40); do
    esta_no_ar || break
    porta_ocupada && break
    sleep 0.5
  done
  if esta_no_ar && porta_ocupada; then
    msg "$NOME_LONGO subiu (PID $(pid_do_servico)) na porta $PORTA."
    printf '%s iniciado %s\n' "$(date '+%F %T')" "$SERVICO" >> "$LOG_DIR/devops.log"
  elif esta_no_ar; then
    msg "$NOME_LONGO iniciou (PID $(pid_do_servico)) mas ainda não abriu a porta $PORTA — acompanhe com 'logs'."
  else
    erro "não subiu. Últimas linhas do log:"; tail -15 "$LOG" >&2; return 1
  fi
}

# Idempotente e silencioso quando já está no ar — é isto que o cron chama.
cmd_ensure() { esta_no_ar && return 0; cmd_start; }

cmd_stop() {
  local pid; pid=$(pid_do_servico)
  if [ -z "$pid" ]; then msg "$NOME_LONGO já estava parado."; return 0; fi
  kill "$pid" 2>/dev/null
  for _ in $(seq 1 20); do esta_no_ar || break; sleep 0.25; done
  if esta_no_ar; then kill -9 "$(pid_do_servico)" 2>/dev/null; sleep 0.5; fi
  esta_no_ar && { erro "não consegui parar o processo."; return 1; }
  msg "$NOME_LONGO parado."
}

cmd_restart() { cmd_stop; cmd_start; }

cmd_status() {
  local pid; pid=$(pid_do_servico)
  msg "$NOME_LONGO"
  msg "  repositório : $REPO"
  msg "  branch      : $(git -C "$REPO" branch --show-current 2>/dev/null || echo '(sem git)')  $(git -C "$REPO" log --oneline -1 2>/dev/null)"
  msg "  dados       : $DADOS"
  msg "  log         : $LOG"
  if [ -x "$PY" ]; then
    msg "  python      : $("$PY" -V 2>&1) ($PY)"
    msg "  dependências: $(deps_desatualizadas && echo "DESATUALIZADAS ($REQUISITOS_REL mudou, ou nunca foram instaladas por aqui) — rode update" || echo 'em dia')"
  else
    msg "  python      : SEM AMBIENTE VIRTUAL em $VENV — rode install"
  fi
  if [ -n "$pid" ]; then
    msg "  processo    : NO AR (PID $pid, desde $(ps -o lstart= -p "$pid" 2>/dev/null | sed 's/^ *//'))"
  else
    msg "  processo    : PARADO"
  fi
  msg "  porta $PORTA   : $(porta_ocupada && echo 'escutando' || echo 'fechada')"
  if command -v curl >/dev/null 2>&1; then
    local code; code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORTA$CAMINHO_SAUDE" 2>/dev/null)
    msg "  HTTP        : ${code:-sem resposta} em $CAMINHO_SAUDE$([ "${code:-0}" = 200 ] && echo ' (ok)')"
  fi
}

cmd_logs() { local n="${1:-40}"; [ -f "$LOG" ] || { msg "(sem log ainda em $LOG)"; return 0; }; tail -n "$n" "$LOG"; }

cmd_update() {
  msg "== git pull =="
  git -C "$REPO" pull --ff-only || { erro "pull falhou (há alteração local?). Resolva e rode de novo."; return 1; }
  if [ ! -x "$PY" ]; then
    msg "== sem ambiente virtual: criando =="
    criar_venv || return 1
    instalar_deps || return 1
  elif deps_desatualizadas; then
    msg "== $REQUISITOS_REL mudou: reinstalando dependências =="
    instalar_deps || return 1
  else
    msg "== dependências sem mudança =="
  fi
  msg "== reiniciando (o Python guarda o código em memória) =="
  cmd_restart
}

# Cria as pastas, o venv, sobe pela primeira vez e deixa o cron cuidando.
cmd_install() {
  msg "Instalando $NOME_LONGO a partir de $REPO"
  mkdir -p "$DADOS" "$LOG_DIR"
  criar_venv || return 1
  if deps_desatualizadas; then instalar_deps || return 1; else msg "  dependências em dia"; fi
  msg "  python: $("$PY" -V 2>&1) ($PY)"
  msg "  dados : $DADOS"
  cmd_start || return 1
  cmd_install_cron
  msg ""
  msg "Pronto. Acesse http://<ip-da-vm>:$PORTA"
  msg "No primeiro acesso o site pede a criação do usuário administrador."
  msg "Se a VM tiver firewall: sudo ufw allow $PORTA/tcp"
}

# Cron do usuário (sem sudo): sobe no boot e a cada 2 min se tiver caído.
# Chamamos com `bash` na frente para não depender do bit de execução, que se
# perde com facilidade em clone feito a partir do Windows.
cmd_install_cron() {
  command -v crontab >/dev/null 2>&1 || { erro "crontab não existe nesta VM; pule esta etapa."; return 1; }
  if [ -x "$BASE/bin/ensure.sh" ] && grep -q "$SERVICO" "$BASE/bin/ensure.sh" 2>/dev/null; then
    msg "  aviso: $BASE/bin/ensure.sh (legado) já cuida deste serviço — não instalei cron para não duplicar."
    return 0
  fi
  local atual novo
  atual=$(crontab -l 2>/dev/null | grep -v "$MARCA")
  novo=$(printf '%s\n@reboot bash %s/devops/ctl.sh ensure >/dev/null 2>&1 %s\n*/2 * * * * bash %s/devops/ctl.sh ensure >/dev/null 2>&1 %s\n' \
    "$atual" "$REPO" "$MARCA" "$REPO" "$MARCA")
  printf '%s\n' "$novo" | grep -v '^$' | crontab - && msg "  cron instalado (@reboot + a cada 2 min)."
}

cmd_uninstall_cron() {
  crontab -l 2>/dev/null | grep -v "$MARCA" | crontab - && msg "cron removido."
}

case "${1:-}" in
  install)        cmd_install ;;
  ensure)         cmd_ensure ;;
  start)          cmd_start ;;
  stop)           cmd_stop ;;
  restart)        cmd_restart ;;
  status)         cmd_status ;;
  logs)           shift; cmd_logs "${1:-40}" ;;
  update)         cmd_update ;;
  install-cron)   cmd_install_cron ;;
  uninstall-cron) cmd_uninstall_cron ;;
  *)
    cat <<AJUDA
$NOME_LONGO — controle do serviço na VM

  ./devops/ctl.sh install         instala do zero (venv, dependências, primeira subida e cron)
  ./devops/ctl.sh start|stop|restart
  ./devops/ctl.sh status          porta, PID, commit, venv e resposta HTTP
  ./devops/ctl.sh logs [n]        últimas n linhas do log (padrão 40)
  ./devops/ctl.sh update          git pull + dependências (se mudaram) + reinicia
  ./devops/ctl.sh ensure          sobe se estiver caído (é o que o cron chama)
  ./devops/ctl.sh install-cron | uninstall-cron

Ajuste os valores em devops/config.env. Detalhes em devops/README.md.
AJUDA
    exit 1 ;;
esac
