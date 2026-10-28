#!/usr/bin/env bash
# Instalação administrativa explícita. Nunca execute com source ou shell -x.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec /usr/bin/python3 -I - "$SOURCE_DIR" "$@" <<'PY_INSTALL'
"""Instalador independente: nenhuma importação ou execução do checkout."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import uuid

REPOSITORY = "/home/ubuntu/komunick/repos/auditoria-jb"
PYTHON = REPOSITORY + "/.venv/bin/python"
APP_ARGV = [PYTHON, "-m", "uvicorn", "--factory", "auditoria_fiscal.web.servidor:criar_app",
            "--host", "127.0.0.1", "--port", "8600"]
SERVICE = "auditoria-jb.service"
CHECK_USER = "auditoria-jb-check"
PATHS = {
    "runner": Path("/usr/local/lib/auditoria-jb-autodeploy/runner.py"),
    "config": Path("/etc/auditoria-jb/autodeploy.json"),
    "state": Path("/var/lib/auditoria-jb-autodeploy"),
    "backup": Path("/var/backups/auditoria-jb-autodeploy"),
    "secrets_backup": Path("/etc/auditoria-jb/autodeploy-backups"),
    "check_work": Path("/var/lib/auditoria-jb-check"),
    "service": Path("/etc/systemd/system/auditoria-jb-autodeploy.service"),
    "timer": Path("/etc/systemd/system/auditoria-jb-autodeploy.timer"),
    "guard": Path("/etc/systemd/system/auditoria-jb.service.d/90-autodeploy-hold.conf"),
}
GUARD = "[Unit]\nConditionPathExists=!/var/lib/auditoria-jb-autodeploy/hold\n"


class InstallError(Exception):
    pass


def command(args):
    # Capturar saída impede expor argumentos, configurações ou segredos em erro.
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, check=False,
                            timeout=600, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
    if result.returncode:
        raise InstallError("Comando administrativo falhou; verifique o serviço e o journal privado.")
    return result.stdout.strip()


def property_of(name, service=SERVICE):
    return command(["/usr/bin/systemctl", "show", service, "--property=" + name, "--value"])


def verify_host_service():
    if os.geteuid() != 0:
        raise InstallError("Execute como root.")
    if socket.gethostname() != "arm07":
        raise InstallError("Instalação permitida somente no host arm07.")
    if property_of("User") != "ubuntu" or property_of("WorkingDirectory") != REPOSITORY:
        raise InstallError("Usuário ou diretório do serviço não corresponde à instalação esperada.")
    start = property_of("ExecStart")
    executable = re.search(r"(?:^|[\s{])path=([^;]+);", start)
    arguments = re.search(r"argv\[\]=([^;]+);", start)
    if (start.count("{") != 1 or start.count("}") != 1 or not executable or not arguments
            or executable.group(1).strip() != PYTHON
            or shlex.split(arguments.group(1)) != APP_ARGV):
        raise InstallError("ExecStart não corresponde ao Python, aplicação e loopback esperados.")


def secure_root_path(path):
    """Recusar symlink e qualquer ancestral substituível pelo usuário da app."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise InstallError("Caminho precisa ser absoluto e sem navegação relativa.")
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise InstallError("Caminho de controle não pertence exclusivamente ao root.")
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise InstallError("Ancestral de configuração não é diretório.")


def private_directory(path, mode=0o700, preserve=False):
    secure_root_path(path)
    existed = Path(path).exists()
    Path(path).mkdir(parents=True, exist_ok=True, mode=mode)
    if not (preserve and existed):
        Path(path).chmod(mode)


def verify_check_user(create=False):
    import grp
    import pwd
    try:
        user = pwd.getpwnam(CHECK_USER)
    except KeyError:
        if not create:
            raise InstallError("Usuário isolado de testes ausente; execute install primeiro.")
        command(["/usr/sbin/useradd", "--system", "--user-group", "--no-create-home",
                 "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin", CHECK_USER])
        user = pwd.getpwnam(CHECK_USER)
    if (not 0 < user.pw_uid < 1000 or user.pw_dir != "/nonexistent"
            or user.pw_shell != "/usr/sbin/nologin" or grp.getgrgid(user.pw_gid).gr_name != CHECK_USER
            or any(CHECK_USER in group.gr_mem for group in grp.getgrall())):
        raise InstallError("Conta de testes existente não é uma conta de sistema isolada.")
    status = command(["/usr/bin/passwd", "-S", CHECK_USER]).split()
    if len(status) < 2 or status[1] not in ("L", "LK"):
        raise InstallError("Conta de testes deve ter senha bloqueada.")


def configuration_sources(additional):
    fragment = property_of("FragmentPath")
    if not fragment:
        raise InstallError("Unit da aplicação não foi localizada.")
    paths = [Path(fragment), *map(Path, shlex.split(property_of("DropInPaths"))), *map(Path, additional)]
    for path in paths:
        secure_root_path(path)
        if not path.is_file():
            raise InstallError("Arquivo de configuração esperado não foi localizado.")
    return list(dict.fromkeys(paths))


def verify_controller_stopped():
    if PATHS["service"].exists():
        for name in ("auditoria-jb-autodeploy.service", "auditoria-jb-autodeploy.timer"):
            if property_of("ActiveState", name) not in ("inactive", "failed"):
                raise InstallError("Pause o timer e aguarde o executor encerrar antes de reinstalar.")


@contextmanager
def controller_lock():
    import fcntl
    path = PATHS["state"] / "runner.lock"
    secure_root_path(path)
    with path.open("a", encoding="utf-8") as lock:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("O executor está em uso; aguarde antes de reinstalar.") from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def atomic_write(path, data, mode):
    secure_root_path(path)
    fd, name = tempfile.mkstemp(prefix=".autodeploy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.chmod(name, mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_source(source, name):
    path = source / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise InstallError("Pacote do executor ausente, irregular ou acima do limite.")
    return path.read_bytes()


def package_digest(source, oid_length):
    """OID Git da árvore usando só bytes, nomes e modos; nunca executar Git/root."""
    algorithm = "sha1" if oid_length == 40 else "sha256"
    remaining = 100
    def object_id(kind, data):
        return hashlib.new(algorithm, kind + b" " + str(len(data)).encode() + b"\0" + data).digest()
    def tree(path, depth=0):
        nonlocal remaining
        if depth > 4:
            raise InstallError("Pacote de controle excede os limites previstos.")
        entries = []
        for item in path.iterdir():
            remaining -= 1
            if remaining < 0:
                raise InstallError("Pacote de controle excede os limites previstos.")
            secure_root_path(item)
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise InstallError("Pacote de controle não admite links simbólicos.")
            if stat.S_ISDIR(info.st_mode):
                mode, digest, suffix = b"40000", tree(item, depth + 1), b"/"
            elif stat.S_ISREG(info.st_mode) and info.st_size <= 2 * 1024 * 1024:
                mode = b"100755" if info.st_mode & stat.S_IXUSR else b"100644"
                digest, suffix = object_id(b"blob", item.read_bytes()), b""
            else:
                raise InstallError("Pacote de controle contém arquivo irregular.")
            name = item.name.encode("utf-8")
            entries.append((name + suffix, mode + b" " + name + b"\0" + digest))
        return object_id(b"tree", b"".join(value for _, value in sorted(entries)))
    return tree(source).hex()


def install(source, cofre_env, additional, control_plane_digest):
    if not isinstance(control_plane_digest, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", control_plane_digest):
        raise InstallError("Informe o OID da árvore devops/autodeploy explicitamente revisada.")
    verify_host_service()
    verify_controller_stopped()
    secure_root_path(source)
    if package_digest(source, len(control_plane_digest)) != control_plane_digest:
        raise InstallError("O pacote de instalação não corresponde à árvore explicitamente aprovada.")
    cofre_env = Path(cofre_env)
    secure_root_path(cofre_env)
    if not cofre_env.is_file() or stat.S_IMODE(cofre_env.stat().st_mode) & 0o077:
        raise InstallError("Arquivo do cofre precisa existir e ser privado do root (0600).")
    configuration = configuration_sources(additional)
    if cofre_env in configuration:
        raise InstallError("O arquivo do cofre deve ficar apenas na lista de segredos.")
    for destination in PATHS.values():
        secure_root_path(destination)
    # Ler como bytes: o install não importa nem executa o runner fornecido.
    sources = {"runner": read_source(source, "runner.py"),
               "service": read_source(source, "auditoria-jb-autodeploy.service"),
               "timer": read_source(source, "auditoria-jb-autodeploy.timer")}
    verify_check_user(create=True)
    private_directory(PATHS["runner"].parent, 0o755)
    private_directory(PATHS["config"].parent)
    for key in ("state", "backup", "secrets_backup"):
        private_directory(PATHS[key])
    private_directory(PATHS["check_work"], 0o711)
    private_directory(PATHS["guard"].parent, 0o755, preserve=True)
    # /etc/systemd/system já existe no host; estes mkdirs também permitem testes isolados.
    for key in ("service", "timer"):
        PATHS[key].parent.mkdir(parents=True, exist_ok=True)
    config = {
        "schema_version": 1, "control_plane_digest": control_plane_digest, "repository": REPOSITORY,
        "repository_url": "https://github.com/Komunick/auditoria-JB.git",
        "deploy_user": "ubuntu", "service": SERVICE, "venv": REPOSITORY + "/.venv",
        "data_dir": "/home/ubuntu/komunick/data/auditoria-jb",
        "state_dir": str(PATHS["state"]), "backup_dir": str(PATHS["backup"]),
        "secrets_backup_dir": str(PATHS["secrets_backup"]),
        "check_user": CHECK_USER, "check_work_dir": str(PATHS["check_work"]),
        "configuration_paths": list(dict.fromkeys([*map(str, configuration), str(PATHS["guard"])])),
        "secret_paths": [str(cofre_env)], "health_url": "http://127.0.0.1:8600",
        "allowed_skips": ["test_fdb_reader.py", "test_web_produtos_fdb.py"],
        "command_timeout": 300, "test_timeout": 600,
        "total_test_timeout": 3600, "health_timeout": 60,
    }
    sources["config"] = (json.dumps(config, indent=2, sort_keys=True) + "\n").encode()
    sources["guard"] = GUARD.encode()
    with controller_lock():
        changed = {key: data for key, data in sources.items()
                   if not PATHS[key].exists() or PATHS[key].read_bytes() != data}
        old = {key: PATHS[key].read_bytes() for key in changed if PATHS[key].exists()}
        if old:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
            backup = PATHS["state"] / "install-backups" / stamp
            private_directory(backup)
            for key, content in old.items():
                atomic_write(backup / key, content, 0o600)
        for key, content in changed.items():
            atomic_write(PATHS[key], content, 0o600 if key == "config" else 0o755 if key == "runner" else 0o644)
        # Mesmo uma instalação idempotente deve manter as permissões previstas.
        for key in sources:
            PATHS[key].chmod(0o600 if key == "config" else 0o755 if key == "runner" else 0o644)
        command(["/usr/bin/systemctl", "daemon-reload"])
    print("Instalado. Timer permanece sem ativação por este comando; execute enable após conferir a configuração.")


def enable():
    verify_host_service()
    verify_check_user()
    for key in ("runner", "config", "service", "timer", "guard", "state", "check_work"):
        secure_root_path(PATHS[key])
        if not PATHS[key].exists():
            raise InstallError("Instalação incompleta; execute install primeiro.")
    if stat.S_IMODE(PATHS["config"].stat().st_mode) != 0o600:
        raise InstallError("Configuração deve ter modo 0600.")
    if PATHS["guard"].read_text() != GUARD:
        raise InstallError("Proteção de manutenção da aplicação está diferente do esperado.")
    command(["/usr/bin/python3", "-I", str(PATHS["runner"]), "--config", str(PATHS["config"]), "--check"])
    command(["/usr/bin/systemctl", "enable", "--now", "auditoria-jb-autodeploy.timer"])
    print("Preflight aprovado e timer habilitado. Confirme o primeiro ciclo no estado privado e no journal.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preparar ou ativar auto-deploy na arm07.")
    parser.add_argument("source", type=Path)
    parser.add_argument("action", choices=("install", "enable"))
    parser.add_argument("--control-plane-digest", help="OID Git da árvore devops/autodeploy explicitamente aprovada.")
    parser.add_argument("--cofre-env", type=Path, default=Path("/etc/auditoria-jb/cofre.env"))
    parser.add_argument("--configuration-path", action="append", default=[], type=Path,
                        help="Arquivo adicional root-owned a incluir no backup de configuração; repetível.")
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.action == "install":
        install(args.source, args.cofre_env, args.configuration_path, args.control_plane_digest)
    elif args.control_plane_digest or args.configuration_path or args.cofre_env != Path("/etc/auditoria-jb/cofre.env"):
        raise InstallError("Argumentos de configuração só se aplicam a install.")
    else:
        enable()


if __name__ == "__main__":
    try:
        main()
    except InstallError as error:
        print("ERRO: " + str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Nunca imprimir conteúdo ou comando que possa carregar segredos.
        print("ERRO: instalação ou preflight recusado; confira host, unit, caminhos, permissões e estado privado.", file=sys.stderr)
        sys.exit(1)
PY_INSTALL
