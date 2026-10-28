#!/usr/bin/env python3
"""Controlador instalado por root; nenhum codigo do checkout e importado aqui.

Falhas de manutencao exigem intervencao. Nao restaura bancos, nao faz reset do
Git, nao instala dependencias e nao atualiza este proprio executor.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import build_opener, ProxyHandler, Request
import uuid

DATABASES = ("auditoria_web.db", "conferencia.db", "conciliacao.db", "patrimonio.db", "nfse.db", "clientes.db")
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_COMMAND_OUTPUT = 16 * 1024 * 1024
SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class DeployError(Exception):
    def __init__(self, code):
        self.code = code if re.fullmatch(r"[a-z0-9_]{1,80}", str(code)) else "invalid_error"
        super().__init__(self.code)


class Deferred(DeployError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def protected_window(now):
    now = now.astimezone(timezone.utc)
    minuto = now.hour * 60 + now.minute
    return 150 <= minuto < 270  # Antes dos jobs de backup03:30 e faxina04:00 UTC.


class Config:
    DEFAULTS = dict(deploy_user="ubuntu", check_user="auditoria-jb-check",
        check_work_dir="/var/lib/auditoria-jb-check", state_dir="/var/lib/auditoria-jb-autodeploy",
        backup_dir="/var/backups/auditoria-jb-autodeploy", secrets_backup_dir="/etc/auditoria-jb/autodeploy-backups",
        configuration_paths=[], secret_paths=[], health_url="http://127.0.0.1:8600",
        allowed_skips=[], command_timeout=300, test_timeout=600, total_test_timeout=3600,
        health_timeout=60, maintenance_timeout=900)

    @classmethod
    def from_dict(cls, data):
        required = {"schema_version", "repository", "repository_url", "venv", "data_dir", "service", "control_plane_digest"}
        if not isinstance(data, dict) or not required.issubset(data) or set(data) - (required | cls.DEFAULTS.keys()):
            raise DeployError("config_fields")
        obj = cls()
        obj.__dict__.update({**cls.DEFAULTS, **data})
        if type(obj.schema_version) is not int or obj.schema_version != 1:
            raise DeployError("config_version")
        for key in ("repository", "venv", "data_dir", "state_dir", "backup_dir", "secrets_backup_dir", "check_work_dir"):
            cls._path(getattr(obj, key))
        for key in ("configuration_paths", "secret_paths"):
            paths = getattr(obj, key)
            if not isinstance(paths, list) or len(paths) > 40:
                raise DeployError("config_paths")
            for path in paths:
                cls._path(path)
        repo = urlparse(obj.repository_url)
        if repo.scheme != "https" or repo.hostname != "github.com" or repo.username or repo.password or repo.query or repo.fragment or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", repo.path):
            raise DeployError("config_repository_url")
        if obj.deploy_user != "ubuntu" or obj.check_user in {"ubuntu", "root"} or not re.fullmatch(r"[a-z][a-z0-9-]{1,30}", obj.check_user):
            raise DeployError("config_users")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.service", obj.service) or not SHA.fullmatch(obj.control_plane_digest):
            raise DeployError("config_identity")
        health = urlparse(obj.health_url)
        if health.scheme != "http" or health.hostname != "127.0.0.1" or not health.port or health.path not in {"", "/"} or health.query or health.fragment or health.username:
            raise DeployError("config_health_url")
        if not isinstance(obj.allowed_skips, list) or any(not re.fullmatch(r"test_[a-zA-Z0-9_]+\.py", n) for n in obj.allowed_skips):
            raise DeployError("config_skips")
        for key in ("command_timeout", "test_timeout", "total_test_timeout", "health_timeout", "maintenance_timeout"):
            value = getattr(obj, key)
            if type(value) is not int or not 1 <= value <= (900 if key == "maintenance_timeout" else 7200):
                raise DeployError("config_timeout")
        return obj

    @staticmethod
    def _path(value):
        if not isinstance(value, str) or not value.startswith("/") or value == "/" or any(c.isspace() or c in ":%\\\x00" for c in value) or ".." in PurePosixPath(value).parts or str(PurePosixPath(value)) != value:
            raise DeployError("config_path")


def clean_environment(home, source=None):
    env = dict(PATH="/usr/sbin:/usr/bin:/sbin:/bin", HOME=str(home), LANG="C.UTF-8", LC_ALL="C.UTF-8",
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", TZ="America/Bahia")
    if source:
        env["PYTHONPATH"] = str(source)
        env["AUDITORIA_WEB_DADOS"] = str(Path(home).parent / "dados")
        env["TMPDIR"] = str(Path(home).parent / "tmp")
    return env


def sandbox_command(config, work, command, label, timeout, *, writable_candidate=False):
    work = str(work)
    unit = "auditoria-jb-check-" + re.sub(r"[^a-zA-Z0-9-]", "-", label)
    props = ["User=" + config.check_user, "NoNewPrivileges=yes", "CapabilityBoundingSet=",
             "AmbientCapabilities=", "PrivateNetwork=yes", "PrivateTmp=yes", "ProtectSystem=strict",
             "ProtectHome=yes", "ProtectProc=invisible", "RestrictSUIDSGID=yes", "RestrictNamespaces=yes",
             "LockPersonality=yes", "PrivateDevices=yes", "ProtectKernelTunables=yes", "ProtectKernelModules=yes",
             "MemoryMax=2G", "TasksMax=128", "CPUQuota=150%",
             "ProtectControlGroups=yes", "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
             "ReadWritePaths=" + work,
             "BindReadOnlyPaths=" + config.venv + ":" + work + "/runtime",
             "RuntimeMaxSec=" + str(timeout), "TimeoutStopSec=10", "KillMode=control-group",
             "WorkingDirectory=" + work + "/candidate"]
    if not writable_candidate:
        props.append("ReadOnlyPaths=" + work + "/candidate")
    for path in [config.data_dir, config.repository, config.state_dir, config.backup_dir,
                 config.secrets_backup_dir, "/etc/auditoria-jb", *config.secret_paths]:
        props.append("InaccessiblePaths=" + path)
    env = clean_environment(work + "/home", work + "/candidate/src")
    argv = ["/usr/bin/systemd-run", "--quiet", "--wait", "--pipe", "--collect", "--unit=" + unit]
    argv += ["--property=" + p for p in props]
    # env existe no host; Python do bind so passa a existir dentro do namespace.
    return argv + ["/usr/bin/env", "-i", *(k + "=" + v for k, v in env.items()), *map(str, command)]


def safe_extract(fileobj, destination):
    """Apenas arquivos regulares/diretorios; executado pelo usuario de verificacao."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or any(destination.iterdir()):
        raise DeployError("archive_destination")
    with tarfile.open(fileobj=fileobj, mode="r:") as archive:
        members = archive.getmembers()
        if len(members) > 50000 or sum(m.size for m in members) > MAX_ARCHIVE_BYTES:
            raise DeployError("archive_limit")
        seen = set()
        for member in members:
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or name in seen or not (member.isdir() or member.isfile()):
                raise DeployError("archive_unsafe")
            seen.add(name)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def validate_sqlite(directory):
    """Chamador fornece SOMENTE copia descartavel, nunca o backup original."""
    directory = Path(directory)
    for name in DATABASES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise DeployError("sqlite_missing")
        try:
            with closing(sqlite3.connect(path, timeout=10)) as conn:
                if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise DeployError("sqlite_integrity")
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise DeployError("sqlite_foreign_keys")
        except sqlite3.DatabaseError as exc:
            raise DeployError("sqlite_invalid") from exc


def sqlite_inventory(directory, baseline=None):
    """Hashes privados de identidades/imutaveis, calculados apenas em copias."""
    result = {}
    def quote(name):
        return '"' + name.replace('"', '""') + '"'
    def digest(row):
        data = [({"blob": v.hex()} if isinstance(v, bytes) else v) for v in row]
        return hashlib.sha256(json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    for name in DATABASES:
        path = Path(directory) / name
        if path.is_symlink() or not path.is_file():
            raise DeployError("sqlite_missing")
        with closing(sqlite3.connect(path, timeout=10)) as conn:
            tables = {}
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            triggers = conn.execute("SELECT tbl_name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
            protected = {table for table, sql in triggers if re.search(r"BEFORE\s+UPDATE", sql or "", re.I) and "RAISE" in (sql or "").upper()}
            protected.add("segredo")
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                if table in {"sessao_login", "tentativa_login", "sessao"}:
                    continue
                info = conn.execute("PRAGMA table_info(" + quote(table) + ")").fetchall()
                columns = [r[1] for r in info]
                old = (baseline or {}).get(name, {}).get("tables", {}).get(table)
                selected = old["columns"] if old else columns
                if not set(selected).issubset(columns):
                    raise DeployError("existing_columns_missing")
                pk = old["pk"] if old else [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
                immutable = old["immutable"] if old else table in protected
                ids = []
                rows = []
                indices = [selected.index(k) for k in pk]
                for row in conn.execute("SELECT " + ",".join(quote(c) for c in selected) + " FROM " + quote(table)):
                    if indices:
                        ids.append(digest([row[i] for i in indices]))
                    if immutable:
                        rows.append(digest(row))
                tables[table] = dict(columns=selected, pk=pk, immutable=immutable, ids=sorted(ids), rows=sorted(rows))
            result[name] = dict(schema=version, tables=tables)
    return result


def compare_inventory(before, after, *, exact_schema=False):
    for name, previous in before.items():
        current = after.get(name)
        if not current or current["schema"] < previous["schema"] or (exact_schema and current["schema"] != previous["schema"]):
            raise DeployError("schema_changed")
        for table, old in previous["tables"].items():
            new = current["tables"].get(table)
            if not new or not set(old["ids"]).issubset(new["ids"]):
                raise DeployError("existing_ids_missing")
            if old["immutable"] and not set(old["rows"]).issubset(new["rows"]):
                raise DeployError("immutable_data_changed")


def write_recovery(destination, revision, secrets):
    text = ("# Recuperação administrativa\n\n"
        "Este snapshot não é restaurado automaticamente. Preserve os dois snapshots e o estado mais recente antes de decidir qualquer recuperação.\n\n"
        "1. Pare o timer auditoria-jb-autodeploy.timer; mantenha o marcador hold e a aplicação parada.\n"
        "2. Examine state.json e os logs privados. Trabalhe em NOVAS cópias dos backups; nunca abra os bancos originais do backup.\n"
        "3. Confira manifest.json, inventory-before.json/inventory-after.json quando presentes, integridade e chaves estrangeiras das cópias.\n"
        "4. repository.bundle recupera código e refs; venv conserva dependências e symlinks. configuration conserva unit/drop-ins/Caddy/cron. "
        "Compare a configuração atual antes de aplicar alterações. Segredos e crontab-ubuntu.txt estão na cópia protegida separada.\n"
        "5. Um banco já migrado não deve receber código antigo sem análise específica. Não restaure o snapshot anterior sobre gravações mais recentes.\n"
        "6. Depois do reparo aprovado, com o timer ainda parado, abra uma janela administrativa controlada: remova o hold e inicie a aplicação. "
        "Valide serviço, catálogos protegidos, cofre, SMTP desligado, dados e SHA; se falhar, recoloque hold e pare a aplicação. "
        "Somente após validação libere explicitamente o estado bloqueado; reative o timer por último.\n\n"
        "SHA observado: " + revision + "\nCópia de segredos: " + str(secrets) + "\n")
    (Path(destination) / "RECUPERACAO.md").write_text(text, encoding="utf-8")


def check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise DeployError("maintenance_timeout")


def copy_regular(source, destination, *, deadline=None, max_bytes=None):
    check_deadline(deadline)
    try:
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise DeployError("source_open_failed") from exc
    with os.fdopen(fd, "rb") as src:
        info = os.fstat(src.fileno())
        if not stat.S_ISREG(info.st_mode) or (max_bytes is not None and info.st_size > max_bytes):
            raise DeployError("source_not_regular")
        with Path(destination).open("xb") as dst:
            while True:
                check_deadline(deadline)
                data = src.read(1024 * 1024)
                if not data:
                    break
                dst.write(data)
            dst.flush()
            os.fsync(dst.fileno())


def write_new_private(path, text, *, uid=None, gid=None):
    """Destino em work pode ter sido preparado pelo candidato: nunca reutilizar."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise DeployError("private_destination_exists") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        if uid is not None and gid is not None:
            os.fchown(output.fileno(), uid, gid)
            os.fchmod(output.fileno(), 0o400)
        output.write(text)
        output.flush()
        os.fsync(output.fileno())


def reject_links(path, *, allow_links=False, deadline=None):
    path = Path(path)
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise DeployError("source_symlink")
    if not path.exists():
        raise DeployError("source_missing")
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            check_deadline(deadline)
            p = Path(base) / name
            mode = p.lstat().st_mode
            if stat.S_ISLNK(mode):
                if not allow_links:
                    raise DeployError("source_symlink")
            elif stat.S_ISREG(mode):
                total += p.stat().st_size
            elif not stat.S_ISDIR(mode):
                raise DeployError("source_special")
    return total


def private_directory(path):
    path = Path(path)
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise DeployError("private_path_symlink")
        if parent.exists() and (parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022):
            raise DeployError("private_path_owner")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def open_directory_nofollow(path):
    parts = PurePosixPath(str(path)).parts
    if not parts or parts[0] != "/" or ".." in parts:
        raise DeployError("source_directory_unsafe")
    fd = None
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        raise DeployError("source_directory_unsafe") from exc


def copy_tree(source, destination, *, allow_links=False, deadline=None):
    """Copia por descritores: O_NOFOLLOW tambem nas pastas de origem mutaveis."""
    destination = Path(destination)
    def copy_dir(fd, dest):
        for entry in os.scandir(fd):
            if deadline is not None and time.monotonic() >= deadline:
                raise DeployError("maintenance_timeout")
            info = entry.stat(follow_symlinks=False)
            target = dest / entry.name
            if stat.S_ISDIR(info.st_mode):
                target.mkdir(mode=0o700)
                child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    copy_dir(child, target)
                finally:
                    os.close(child)
            elif stat.S_ISLNK(info.st_mode) and allow_links:
                os.symlink(os.readlink(entry.name, dir_fd=fd), target)
            elif stat.S_ISREG(info.st_mode):
                child = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                with os.fdopen(child, "rb") as src, target.open("xb") as dst:
                    while True:
                        if deadline is not None and time.monotonic() >= deadline:
                            raise DeployError("maintenance_timeout")
                        data = src.read(1024 * 1024)
                        if not data:
                            break
                        dst.write(data)
                    dst.flush()
                    os.fsync(dst.fileno())
                target.chmod(stat.S_IMODE(info.st_mode) & 0o777)
            else:
                raise DeployError("source_special")
    fd = open_directory_nofollow(source)
    try:
        destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        copy_dir(fd, destination)
    finally:
        os.close(fd)


class Runner:
    """Ordem auditavel, injetavel para testar falhas sem sistema operacional real."""
    def __init__(self, host):
        self.host = host
        self.state = {}

    def stage(self, stage, **values):
        self.state.update(stage=stage, updated_at=utcnow().isoformat(), **values)
        if self.state.get("status") != "running":
            self.state["last_attempt"] = self.attempt()
        self.host.save_state(self.state)

    def attempt(self):
        return {k: v for k, v in self.state.items() if k not in {"last_deploy", "last_attempt", "last_failure"}}

    def run(self, *, check=False):
        h = self.host
        previous = h.load_state()
        if previous.get("status") == "blocked":
            return 1  # Conserva a primeira causa; nao repete manutencao.
        if h.has_hold() or (previous.get("status") == "running" and previous.get("maintenance_started")):
            self.state = previous.copy()
            if previous.get("maintenance_started") and not check:
                return self.fail(DeployError("interrupted_previous_run"))
            self.stage(previous.get("stage", "blocked"), status="blocked", error=previous.get("error") or "manual_intervention_required")
            return 1
        last_failure = previous.get("last_failure")
        if previous.get("status") == "running":
            last_failure = {k: v for k, v in previous.items() if k not in {"last_deploy", "last_attempt", "last_failure"}}
            last_failure.update(status="rejected" if previous.get("target_sha") else "deferred", error="interrupted_previous_run")
        self.state = dict(status="running", maintenance_started=False, backups=[], tests={},
                          last_deploy=previous.get("last_deploy"), last_failure=last_failure)
        try:
            self.stage("preflight")
            revision = h.preflight()
            self.stage("preflight", **revision)
            if last_failure and last_failure.get("status") == "rejected" and last_failure.get("target_sha") == revision["target_sha"]:
                self.stage(last_failure.get("stage", "tests"), status="rejected", result="rejected_unchanged", error=last_failure["error"])
                return 1
            if check or revision["current_sha"] == revision["target_sha"]:
                if not check and (previous.get("last_deploy") or {}).get("target_sha") != revision["current_sha"]:
                    raise DeployError("unverified_noop_revision")
                self.stage("complete", status="success", result="checked" if check else "noop")
                return 0
            self.stage("tests")
            tests = h.test_candidate(revision)
            self.stage("tested", tests=tests)
            h.recheck(revision)
            h.begin_maintenance()
            self.stage("maintenance", maintenance_started=True)
            h.set_hold()
            h.stop()
            self.stage("backup_pre")
            backup = h.backup("pre")
            self.stage("migration", backups=[backup])
            h.validate(backup, migrate=True)
            self.stage("fast_forward")
            h.fast_forward(revision)
            self.stage("health_first")
            h.start_and_health()
            self.stage("backup_post")
            h.set_hold()
            h.stop()
            after = h.backup("post")
            self.stage("integrity_post", backups=[backup, after])
            h.validate(after, migrate=False)
            self.stage("health_final")
            h.start_and_health()
            last_deploy = self.attempt()
            last_deploy.update(status="success", result="deployed", completed_at=utcnow().isoformat(), maintenance_started=False)
            self.stage("complete", status="success", result="deployed", maintenance_started=False, error=None, last_deploy=last_deploy)
            return 0
        except Deferred as exc:
            if self.state.get("maintenance_started"):
                return self.fail(exc)
            self.stage("deferred", status="deferred", error=exc.code)
            return 0 if not check else 1
        except BaseException as exc:
            return self.fail(exc)

    def fail(self, exc):
        code = exc.code if isinstance(exc, DeployError) else "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "internal_error"
        if self.state.get("maintenance_started"):
            try:
                self.host.set_hold()
                getattr(self.host, "emergency_stop", self.host.stop)()
            except BaseException:
                code = "stop_failed_requires_immediate_attention"
        status = "blocked" if self.state.get("maintenance_started") else "rejected" if self.state.get("target_sha") else "deferred"
        failure = self.attempt()
        failure.update(status=status, error=code, failed_at=utcnow().isoformat())
        self.stage(self.state.get("stage", "unknown"), status=status, error=code, last_failure=failure)
        return 1


class Host:
    def __init__(self, config):
        import pwd
        self.c = config
        self.state_dir = private_directory(config.state_dir)
        self.logs = private_directory(self.state_dir / "logs")
        private_directory(config.backup_dir)
        private_directory(config.secrets_backup_dir)
        self.run_id = utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        self.counter = 0
        self.deadline = None
        self.uid = pwd.getpwnam(config.check_user).pw_uid
        self.gid = pwd.getpwnam(config.check_user).pw_gid
        self.deploy_uid = pwd.getpwnam(config.deploy_user).pw_uid
        self.deploy_gid = pwd.getpwnam(config.deploy_user).pw_gid
        if self.uid in {0, self.deploy_uid}:
            raise DeployError("check_user_privileged")
        parent = Path(config.check_work_dir)
        for ancestor in [parent, *parent.parents]:
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise DeployError("work_parent_owner")
        self.work = parent / ("check-" + self.run_id)
        self.gitwork = parent / ("git-" + self.run_id)
        self.gitwork.mkdir(mode=0o700)
        os.chown(self.gitwork, self.deploy_uid, self.deploy_gid)
        self.original_pid = 0
        self.last_pid = 0
        self.revision = None

    def load_state(self):
        path = self.state_dir / "state.json"
        if not path.exists():
            return {}
        if path.is_symlink():
            raise DeployError("state_symlink")
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, OSError) as exc:
            raise DeployError("state_invalid") from exc

    def save_state(self, state):
        path = self.state_dir / ("state-" + self.run_id + ".tmp")
        with path.open("x", encoding="utf-8") as output:
            os.chmod(path, 0o600)
            json.dump(state, output, ensure_ascii=True, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(path, self.state_dir / "state.json")
        fd = os.open(self.state_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def has_hold(self):
        return (self.state_dir / "hold").exists()

    def set_hold(self):
        path = self.state_dir / "hold"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def command(self, argv, *, timeout=None, acceptable=(0,), label="command"):
        timeout = timeout or self.c.command_timeout
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise DeployError("maintenance_timeout")
        self.counter += 1
        log = self.logs / (self.run_id + "-" + str(self.counter) + ".log")
        with log.open("xb") as output:
            log.chmod(0o600)
            proc = subprocess.Popen(list(map(str, argv)), stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                env=clean_environment("/nonexistent"), shell=False, start_new_session=True)
            started = time.monotonic()
            reason = None
            try:
                while proc.poll() is None:
                    if time.monotonic() - started > timeout:
                        reason = "command_timeout"
                        break
                    if output.tell() > MAX_COMMAND_OUTPUT:
                        reason = "command_output_limit"
                        break
                    time.sleep(.1)
                if reason:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
                    raise DeployError(reason)
            except BaseException:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
                raise
        result = log.read_bytes()
        if len(result) > MAX_COMMAND_OUTPUT:
            raise DeployError("command_output_limit")
        if proc.returncode not in acceptable:
            raise DeployError(label + "_failed")
        return result.decode("utf-8", errors="replace").strip()

    def git(self, arguments, *, acceptable=(0,)):
        env = clean_environment(self.gitwork)
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
        argv = ["/usr/sbin/runuser", "-u", self.c.deploy_user, "--", "/usr/bin/setpriv", "--no-new-privs",
                "/usr/bin/env", "-i", *(k + "=" + v for k, v in env.items()), "/usr/bin/git",
                "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "protocol.file.allow=never",
                "-c", "protocol.ext.allow=never", "-C", self.c.repository, *arguments]
        return self.command(argv, acceptable=acceptable, label="git")

    def sandbox(self, command, *, timeout=None, writable_candidate=False):
        timeout = timeout or self.c.test_timeout
        label = self.run_id + "-" + str(self.counter + 1)
        argv = sandbox_command(self.c, self.work, command, label, timeout, writable_candidate=writable_candidate)
        try:
            return self.command(argv, timeout=timeout + 15, label="sandbox")
        finally:
            # Tambem encerra o cgroup se o cliente systemd-run sofreu timeout.
            subprocess.run(["/usr/bin/systemctl", "stop", "auditoria-jb-check-" + label + ".service"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False,
                env=clean_environment("/nonexistent"))

    def service(self):
        output = self.command(["/usr/bin/systemctl", "show", self.c.service, "--no-pager",
            "--property=ActiveState,SubState,MainPID,ExecStart,User,WorkingDirectory,ExecMainStartTimestampMonotonic"], label="service")
        props = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if props.get("User") != self.c.deploy_user or props.get("WorkingDirectory") != self.c.repository:
            raise DeployError("service_configuration")
        start = props.get("ExecStart", "")
        port = str(urlparse(self.c.health_url).port)
        if ("path=" + self.c.venv + "/bin/python") not in start or "auditoria_fiscal.web.servidor:criar_app" not in start or "--host 127.0.0.1" not in start or ("--port " + port) not in start or "--workers" in start:
            raise DeployError("service_configuration")
        return props

    def health(self):
        props = self.service()
        pid = int(props.get("MainPID", "0"))
        if props.get("ActiveState") != "active" or props.get("SubState") != "running" or pid <= 0:
            raise DeployError("service_inactive")
        environment = Path("/proc") / str(pid) / "environ"
        entries = environment.read_bytes().split(b"\0")
        values = dict(item.split(b"=", 1) for item in entries if b"=" in item)
        if (not values.get(b"AUDITORIA_COFRE_CHAVE", b"").strip()
                or values.get(b"AUDITORIA_WEB_DADOS") != self.c.data_dir.encode()
                or any(k.startswith(b"AUDITORIA_SMTP_") for k in values)):
            raise DeployError("service_environment")
        opener = build_opener(ProxyHandler({}))
        for route, expected in (("/api/estado", 200), ("/api/tarefas/catalogo", 401), ("/api/clientes/catalogo", 401)):
            try:
                with opener.open(Request(self.c.health_url.rstrip("/") + route), timeout=5) as response:
                    status, body = response.status, response.read(65537)
            except HTTPError as exc:
                status, body = exc.code, b""
            if status != expected:
                raise DeployError("http_health")
            if route == "/api/estado":
                if len(body) > 65536 or json.loads(body).get("precisa_bootstrap") is not False:
                    raise DeployError("http_bootstrap")
        after = self.service()
        if after.get("MainPID") != str(pid) or after.get("ExecMainStartTimestampMonotonic") != props.get("ExecMainStartTimestampMonotonic"):
            raise DeployError("service_changed_during_health")
        return pid

    def space(self):
        data_size = reject_links(self.c.data_dir)
        venv_size = reject_links(self.c.venv, allow_links=True)
        git_size = reject_links(Path(self.c.repository) / ".git")
        required = 2 * (data_size + venv_size + git_size) + data_size + MAX_ARCHIVE_BYTES + 64 * 1024 * 1024
        for path in (self.c.backup_dir, self.c.check_work_dir, self.c.secrets_backup_dir):
            if shutil.disk_usage(path).free < required:
                raise DeployError("disk_space")

    def clean_checkout(self):
        if self.git(["symbolic-ref", "--short", "HEAD"]) != "main" or self.git(["status", "--porcelain=v1", "--untracked-files=normal"]):
            raise DeployError("checkout_not_clean_main")
        if self.git(["remote", "get-url", "origin"]) != self.c.repository_url:
            raise DeployError("repository_origin")
        return self.git(["rev-parse", "HEAD"])

    def preflight(self):
        if protected_window(utcnow()):
            raise Deferred("janela_protegida")
        self.original_pid = self.health()
        current = self.clean_checkout()
        self.git(["fetch", "--no-tags", "--no-recurse-submodules", self.c.repository_url,
                  "+refs/heads/main:refs/remotes/origin/main"])
        target = self.git(["rev-parse", "refs/remotes/origin/main"])
        if not SHA.fullmatch(current) or not SHA.fullmatch(target):
            raise DeployError("invalid_revision")
        self.git(["merge-base", "--is-ancestor", current, target])
        control = self.git(["rev-parse", target + ":devops/autodeploy"])
        if control != self.c.control_plane_digest:
            raise DeployError("control_plane_requires_install")
        changes = self.git(["diff", "--no-ext-diff", "--no-textconv", "--name-only", current, target, "--"]).splitlines()
        names = {"pyproject.toml", "setup.py", "setup.cfg", "poetry.lock", "uv.lock", "Pipfile", "Pipfile.lock", "package.json", "package-lock.json"}
        if any(PurePosixPath(n).name in names or re.fullmatch(r"requirements[^/]*\.txt", PurePosixPath(n).name) for n in changes):
            raise DeployError("dependencies_require_maintenance")
        self.space()
        self.revision = dict(current_sha=current, target_sha=target)
        return self.revision

    def create_work(self):
        self.work.mkdir(mode=0o700)
        for name in ("candidate", "runtime", "home", "dados", "tmp"):
            (self.work / name).mkdir(mode=0o700)
        self.chown(self.work)

    def chown(self, path):
        for base, dirs, files in os.walk(path, followlinks=False):
            os.chown(base, self.uid, self.gid)
            for name in files:
                os.chown(Path(base) / name, self.uid, self.gid, follow_symlinks=False)

    def test_candidate(self, revision):
        self.create_work()
        archive = self.gitwork / "candidate.tar"
        self.git(["archive", "--format=tar", "--output=" + str(archive), revision["target_sha"]])
        if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise DeployError("archive_unsafe")
        destination = self.work / "candidate.tar"
        copy_regular(archive, destination, max_bytes=MAX_ARCHIVE_BYTES)
        os.chown(destination, self.uid, self.gid)
        # Extracao e feita por este arquivo INSTALADO, sob UID sem privilegios.
        self.sandbox(["/usr/bin/python3", "-I", str(Path(__file__).resolve()), "--helper-extract", str(destination), str(self.work / "candidate")], writable_candidate=True)
        scripts = sorted((self.work / "candidate" / "tests").glob("test_*.py"))
        if not scripts or any(p.is_symlink() for p in scripts):
            raise DeployError("tests_missing")
        started = time.monotonic()
        results = dict(passed=[], skipped=[])
        for path in scripts:
            remaining = self.c.total_test_timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise DeployError("tests_total_timeout")
            output = self.sandbox([str(self.work / "runtime/bin/python"), "-B", str(path)], timeout=min(self.c.test_timeout, int(remaining)))
            skipped = bool(re.search(r"\b(?:SKIP|SKIPPED|PULADO|IGNORADO)\b", output, re.IGNORECASE))
            if skipped and path.name not in self.c.allowed_skips:
                raise DeployError("test_unapproved_skip")
            results["skipped" if skipped else "passed"].append(path.name)
        if Path("/usr/bin/node").is_file():
            for path in sorted((self.work / "candidate" / "webui").glob("*.js")):
                self.sandbox(["/usr/bin/node", "--check", str(path)], timeout=30)
            results["node"] = "passed"
        else:
            results["node"] = "unavailable"
        return results

    def recheck(self, revision):
        if protected_window(utcnow()):
            raise Deferred("janela_protegida")
        if self.clean_checkout() != revision["current_sha"] or self.git(["rev-parse", "refs/remotes/origin/main"]) != revision["target_sha"]:
            raise DeployError("revision_changed")
        remote = self.git(["ls-remote", self.c.repository_url, "refs/heads/main"]).split()
        if not remote or remote[0] != revision["target_sha"]:
            raise DeployError("remote_changed")
        if self.health() != self.original_pid:
            raise DeployError("service_changed")
        self.space()

    def begin_maintenance(self):
        if protected_window(utcnow()):
            raise Deferred("janela_protegida")
        self.deadline = time.monotonic() + self.c.maintenance_timeout

    def stop(self):
        props = self.service()
        self.last_pid = int(props.get("MainPID", "0")) or self.last_pid
        self.command(["/usr/bin/systemctl", "stop", self.c.service], timeout=60, label="service_stop")
        props = self.service()
        if props.get("MainPID") != "0" or props.get("ActiveState") not in {"inactive", "failed"}:
            raise DeployError("service_not_stopped")

    def emergency_stop(self):
        # Em falha, assegurar parada ainda e necessario depois do limite normal.
        deadline, self.deadline = self.deadline, time.monotonic() + 90
        try:
            self.stop()
        finally:
            self.deadline = deadline

    def backup(self, label):
        if self.service().get("MainPID") != "0" or not self.has_hold():
            raise DeployError("backup_requires_stopped_hold")
        target = Path(self.c.backup_dir) / (self.run_id + "-" + label)
        target.mkdir(mode=0o700)
        copy_tree(self.c.data_dir, target / "data", deadline=self.deadline)
        if label == "pre":
            copy_tree(self.c.venv, target / "venv", allow_links=True, deadline=self.deadline)
            bundle = self.gitwork / "repository.bundle"
            self.git(["bundle", "create", str(bundle), "--all"])
            if bundle.is_symlink() or not bundle.is_file():
                raise DeployError("bundle_invalid")
            copy_regular(bundle, target / "repository.bundle", deadline=self.deadline)
            secrets = Path(self.c.secrets_backup_dir) / self.run_id
            secrets.mkdir(mode=0o700)
            self.copy_config(self.c.configuration_paths, target / "configuration")
            self.copy_config(self.c.secret_paths, secrets)
            cron = self.command(["/usr/bin/crontab", "-u", "ubuntu", "-l"], label="crontab_backup")
            cron_path = secrets / "crontab-ubuntu.txt"
            cron_path.write_text(cron + "\n", encoding="utf-8")
            cron_path.chmod(0o600)
            secret_manifest = dict(created_at=utcnow().isoformat(), files=self.manifest(secrets, source="/"),
                                   crontab_source="crontab -u ubuntu -l")
            (secrets / "manifest.json").write_text(json.dumps(secret_manifest, sort_keys=True), encoding="utf-8")
        manifest = dict(label=label, sha=self.git(["rev-parse", "HEAD"]), created_at=utcnow().isoformat(),
                        data_files=self.manifest(target / "data", source=self.c.data_dir), secrets_backup=self.run_id if label == "pre" else None,
                        contents=[p.name for p in target.iterdir()], configuration_sources=self.c.configuration_paths if label == "pre" else [])
        if label == "pre":
            manifest.update(venv_files=self.manifest(target / "venv", source=self.c.venv),
                code_files=self.manifest(target / "repository.bundle", source=bundle),
                configuration_files=self.manifest(target / "configuration", source="/"))
        (target / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        write_recovery(target, manifest["sha"], Path(self.c.secrets_backup_dir) / self.run_id)
        return str(target)

    def copy_config(self, sources, destination):
        destination = Path(destination)
        destination.mkdir(mode=0o700, exist_ok=True)
        for source in sources:
            src = Path(source)
            for parent in [src, *src.parents]:
                if parent.is_symlink():
                    raise DeployError("configuration_symlink")
            target = destination / source.lstrip("/")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if src.is_dir():
                copy_tree(src, target, deadline=self.deadline)
            elif src.is_file():
                copy_regular(src, target, deadline=self.deadline)
                target.chmod(0o600)
            else:
                raise DeployError("configuration_missing")

    def manifest(self, directory, *, source=None):
        directory = Path(directory)
        result = {}
        paths = [directory]
        if directory.is_dir() and not directory.is_symlink():
            for base, dirs, files in os.walk(directory, followlinks=False):
                paths.extend(Path(base) / name for name in dirs + files)
        for path in sorted(paths):
            check_deadline(self.deadline)
            key = path.relative_to(directory).as_posix() if path != directory else "."
            info = path.lstat()
            entry = dict(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
            if source is not None:
                original = Path(source) if key == "." else Path(source) / key
                try:
                    old = original.lstat()
                    entry["source"] = dict(mode=stat.S_IMODE(old.st_mode), uid=old.st_uid, gid=old.st_gid)
                except FileNotFoundError:
                    entry["source"] = None
            if stat.S_ISLNK(info.st_mode):
                entry.update(type="symlink", target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                entry["type"] = "directory"
            elif stat.S_ISREG(info.st_mode):
                entry.update(type="file", size=info.st_size)
                with path.open("rb") as content:
                    digest = hashlib.sha256()
                    while True:
                        check_deadline(self.deadline)
                        data = content.read(1024 * 1024)
                        if not data:
                            break
                        digest.update(data)
                    entry["sha256"] = digest.hexdigest()
            else:
                raise DeployError("manifest_special_file")
            result[key] = entry
        return result

    def validate(self, snapshot, *, migrate):
        name = "migration" if migrate else "post-integrity"
        working = self.work / name
        copy_tree(Path(snapshot) / "data", working, deadline=self.deadline)
        self.chown(working)
        self.sandbox(["/usr/bin/python3", "-I", str(Path(__file__).resolve()), "--helper-integrity", str(working)], timeout=120)
        def inventory(baseline=None):
            command = ["/usr/bin/python3", "-I", str(Path(__file__).resolve()), "--helper-inventory", str(working)]
            if baseline is not None:
                baseline_path = self.work / (name + "-baseline.json")
                write_new_private(baseline_path, json.dumps(baseline), uid=self.uid, gid=self.gid)
                command += ["--inventory-baseline", str(baseline_path)]
            return json.loads(self.sandbox(command, timeout=120))
        if migrate:
            original = inventory()
            (Path(snapshot) / "inventory-before.json").write_text(json.dumps(original), encoding="utf-8")
            # Apenas o store, sem importar servidor, lifespan, agendador ou cofre.
            code = ("import sqlite3; from auditoria_fiscal.ferramentas.tarefas_store import TarefasStore; "
                    "s=TarefasStore(__import__('sys').argv[1]); s.fechar()")
            self.sandbox([str(self.work / "runtime/bin/python"), "-B", "-c", code, str(working / "clientes.db")], timeout=120)
            self.sandbox(["/usr/bin/python3", "-I", str(Path(__file__).resolve()), "--helper-integrity", str(working)], timeout=120)
            expected = inventory(original)
            compare_inventory(original, expected)
            self.expected_inventory = expected
            (Path(snapshot) / "inventory-after.json").write_text(json.dumps(expected), encoding="utf-8")
        else:
            current = inventory(self.expected_inventory)
            compare_inventory(self.expected_inventory, current, exact_schema=True)
            (Path(snapshot) / "inventory-after.json").write_text(json.dumps(current), encoding="utf-8")

    def cleanup(self, *, keep_logs=True):
        parent = Path(self.c.check_work_dir).resolve()
        for path, prefix in ((self.work, "check-"), (self.gitwork, "git-")):
            path = Path(path)
            if path.is_symlink() or path.parent.resolve() != parent or path.name != prefix + self.run_id:
                raise DeployError("workspace_cleanup_bounds")
            if path.exists():
                shutil.rmtree(path)
        if not keep_logs:
            for path in self.logs.glob(self.run_id + "-*.log"):
                if path.is_symlink() or path.parent.resolve() != self.logs.resolve():
                    raise DeployError("log_cleanup_bounds")
                path.unlink()

    def fast_forward(self, revision):
        if self.clean_checkout() != revision["current_sha"] or self.git(["rev-parse", "refs/remotes/origin/main"]) != revision["target_sha"]:
            raise DeployError("revision_changed")
        self.git(["merge", "--ff-only", "--no-edit", revision["target_sha"]])
        if self.clean_checkout() != revision["target_sha"]:
            raise DeployError("revision_after_ff")

    def start_and_health(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise DeployError("maintenance_timeout")
        (self.state_dir / "hold").unlink()
        self.command(["/usr/bin/systemctl", "start", self.c.service], timeout=60, label="service_start")
        until = min(time.monotonic() + self.c.health_timeout, self.deadline or float("inf"))
        while time.monotonic() < until:
            try:
                pid = self.health()
                if pid == self.last_pid:
                    raise DeployError("service_pid_not_new")
                return
            except (DeployError, OSError, ValueError):
                time.sleep(1)
        raise DeployError("health_timeout")


@contextmanager
def locked(state_dir):
    import fcntl
    path = private_directory(state_dir) / "runner.lock"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Deferred("already_running") from exc
        yield
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Atualizacao conservadora da main")
    parser.add_argument("--config", default="/etc/auditoria-jb/autodeploy.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--once", action="store_true")
    group.add_argument("--helper-extract", nargs=2, metavar=("ARCHIVE", "DESTINATION"))
    group.add_argument("--helper-integrity", metavar="COPY")
    group.add_argument("--helper-inventory", metavar="COPY")
    parser.add_argument("--inventory-baseline")
    args = parser.parse_args(argv)
    try:
        if args.helper_extract or args.helper_integrity or args.helper_inventory:
            if os.geteuid() == 0:
                raise DeployError("helper_refuses_root")
            if args.helper_extract:
                with open(args.helper_extract[0], "rb") as source:
                    safe_extract(source, args.helper_extract[1])
            elif args.helper_integrity:
                validate_sqlite(args.helper_integrity)
            else:
                baseline = json.loads(Path(args.inventory_baseline).read_text()) if args.inventory_baseline else None
                print(json.dumps(sqlite_inventory(args.helper_inventory, baseline)))
            return 0
        if sys.platform != "linux" or os.geteuid() != 0:
            raise DeployError("linux_root_required")
        os.umask(0o077)
        path = Path(args.config)
        for parent in [path, *path.parents]:
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise DeployError("config_owner")
        config = Config.from_dict(json.loads(path.read_text()))
        def interrupted(*_):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupted)
        with locked(config.state_dir):
            host = Host(config)
            try:
                result = Runner(host).run(check=args.check)
            finally:
                state = host.load_state()
                host.cleanup(keep_logs=state.get("result") not in {"noop", "checked"})
            print("autodeploy status=" + str(state.get("status", "unknown")) + " stage=" + str(state.get("stage", "unknown")) + " error=" + str(state.get("error") or "none"))
            return result
    except Deferred as exc:
        print("autodeploy deferred=" + exc.code)
        return 0
    except BaseException as exc:
        print("autodeploy blocked=" + (exc.code if isinstance(exc, DeployError) else "controller_failure"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
