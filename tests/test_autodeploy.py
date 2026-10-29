"""Executor de deploy: falhas sinteticas; nunca acessa servico ou dados reais."""
import importlib.util
import hashlib
import io
import os
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ARQUIVO = Path(__file__).resolve().parents[1] / "devops" / "autodeploy" / "runner.py"
spec = importlib.util.spec_from_file_location("autodeploy_runner_test", ARQUIVO)
ad = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ad
spec.loader.exec_module(ad)


class HostFalso:
    def __init__(self, falha=None, *, atual="a" * 40, alvo="b" * 40, estado=None):
        self.falha, self.eventos = falha, []
        self.atual, self.alvo = atual, alvo
        self.estado = estado or {}
        self.held, self.ativo = False, True

    def evento(self, nome):
        self.eventos.append(nome)
        if self.falha == nome:
            raise ad.DeployError("falha_sintetica")

    def load_state(self): return self.estado.copy()
    def save_state(self, estado): self.estado = estado.copy()
    def has_hold(self): return self.held
    def preflight(self):
        self.evento("preflight")
        return dict(current_sha=self.atual, target_sha=self.alvo)
    def test_candidate(self, revisao):
        self.evento("tests")
        return {"passed": ["test_sintetico.py"], "skipped": []}
    def recheck(self, revisao): self.evento("recheck")
    def begin_maintenance(self): self.evento("maintenance")
    def set_hold(self): self.eventos.append("hold"); self.held = True
    def stop(self): self.eventos.append("stop"); self.ativo = False
    def backup(self, rotulo):
        self.evento("backup_" + rotulo)
        return "/backup/sintetico/" + rotulo
    def validate(self, copia, *, migrate): self.evento("migration" if migrate else "integrity_post")
    def fast_forward(self, revisao): self.evento("ff"); self.atual = self.alvo
    def start_and_health(self):
        self.eventos.append("start")
        self.held, self.ativo = False, True
        self.evento("health")


def test_fluxo_e_falhas():
    h = HostFalso()
    assert ad.Runner(h).run() == 0
    assert h.estado["status"] == "success" and h.estado["target_sha"] == "b" * 40
    assert h.estado["backups"] == ["/backup/sintetico/pre", "/backup/sintetico/post"]
    assert h.eventos == ["preflight", "tests", "recheck", "maintenance", "hold", "stop", "backup_pre",
        "migration", "ff", "start", "health", "hold", "stop", "backup_post", "integrity_post", "start", "health"]
    assert h.ativo and not h.held
    for falha in ("preflight", "tests", "recheck", "maintenance"):
        h = HostFalso(falha)
        assert ad.Runner(h).run() == 1
        assert "stop" not in h.eventos and h.ativo and not h.held
        assert h.estado["status"] == ("deferred" if falha == "preflight" else "rejected") and h.estado["error"] == "falha_sintetica"
    for falha in ("backup_pre", "migration", "ff", "health", "backup_post", "integrity_post"):
        h = HostFalso(falha)
        assert ad.Runner(h).run() == 1
        assert h.held and not h.ativo and h.estado["status"] == "blocked"
        assert h.eventos[-2:] == ["hold", "stop"]
        assert not any("restore" in e or "reset" in e for e in h.eventos)


def test_noop_check_e_interrupcao():
    h = HostFalso(atual="a" * 40, alvo="a" * 40, estado={"status": "success", "last_deploy": {"target_sha": "a" * 40}})
    assert ad.Runner(h).run() == 0 and h.eventos == ["preflight"]
    assert h.estado["result"] == "noop"
    h = HostFalso()
    assert ad.Runner(h).run(check=True) == 0 and h.eventos == ["preflight"]
    assert h.estado["result"] == "checked"
    for anterior in ({"status": "blocked"},):
        h = HostFalso(estado=anterior, atual="b" * 40, alvo="b" * 40)
        assert ad.Runner(h).run() == 1 and "preflight" not in h.eventos
    h = HostFalso(estado={"status": "running", "maintenance_started": True})
    assert ad.Runner(h).run() == 1 and h.held and not h.ativo
    h = HostFalso()
    h.held = True
    assert ad.Runner(h).run(check=True) == 1 and h.held and "preflight" not in h.eventos
    h = HostFalso()
    def interromper():
        raise KeyboardInterrupt("segredo nao deve aparecer")
    h.start_and_health = interromper
    assert ad.Runner(h).run() == 1 and h.held and not h.ativo
    assert "segredo" not in str(h.estado)
    ultimo = {"target_sha": "a" * 40, "backups": ["/backup/ultimo"], "tests": {"passed": ["test_a.py"]}}
    h = HostFalso(estado={"status": "success", "last_deploy": ultimo}, atual="a" * 40, alvo="a" * 40)
    assert ad.Runner(h).run() == 0 and h.estado["last_deploy"] == ultimo
    h = HostFalso()
    assert ad.Runner(h).run() == 0 and h.estado["last_deploy"]["backups"] == h.estado["backups"]
    h = HostFalso(atual="b" * 40, alvo="b" * 40, estado={"status": "success", "last_deploy": {"target_sha": "a" * 40}})
    assert ad.Runner(h).run() == 1 and h.estado["error"] == "unverified_noop_revision"
    assert h.ativo and not h.held and "stop" not in h.eventos


def test_politica_falha_e_candidato_rejeitado():
    h = HostFalso("tests")
    assert ad.Runner(h).run() == 1 and h.estado["status"] == "rejected"
    first_failure = h.estado["last_failure"].copy()
    h.falha = None
    h.eventos = []
    assert ad.Runner(h).run() == 1 and h.eventos == ["preflight"]
    assert h.estado["last_failure"] == first_failure and h.ativo and not h.held
    h.alvo = "c" * 40
    h.eventos = []
    assert ad.Runner(h).run() == 0 and "tests" in h.eventos and h.estado["status"] == "success"
    h = HostFalso("preflight")
    assert ad.Runner(h).run() == 1 and h.estado["status"] == "deferred"
    h.falha = None
    assert ad.Runner(h).run() == 0
    anterior = {"status": "blocked", "stage": "migration", "error": "sqlite_foreign_keys", "maintenance_started": True}
    h = HostFalso(estado=anterior)
    assert ad.Runner(h).run() == 1 and h.estado["stage"] == "migration" and h.estado["error"] == "sqlite_foreign_keys"
    assert h.eventos == [], "Bloqueio persistente nao repete operacoes nem apaga diagnostico"


def test_janela_temporal():
    for hora, minuto, bloqueia in [(2, 29, False), (2, 30, True), (3, 59, True), (4, 29, True), (4, 30, False)]:
        assert ad.protected_window(datetime(2026, 10, 29, hora, minuto, tzinfo=timezone.utc)) is bloqueia
    h = HostFalso()
    def janela(): raise ad.Deferred("janela_protegida")
    h.preflight = janela
    assert ad.Runner(h).run() == 0 and h.estado["status"] == "deferred" and not h.held


def test_archive_sem_links_ou_escape(pasta):
    def arquivo(nome, tipo=tarfile.REGTYPE):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            item = tarfile.TarInfo(nome)
            item.type = tipo
            item.linkname = "/fora"
            item.size = 3 if tipo == tarfile.REGTYPE else 0
            tar.addfile(item, io.BytesIO(b"abc") if item.size else None)
        stream.seek(0)
        return stream
    for nome, tipo in [("../fora", tarfile.REGTYPE), ("/fora", tarfile.REGTYPE), ("x", tarfile.SYMTYPE),
                       ("x", tarfile.LNKTYPE), ("x", tarfile.FIFOTYPE), ("x\\..\\fora", tarfile.REGTYPE)]:
        try:
            ad.safe_extract(arquivo(nome, tipo), Path(pasta) / "recusado")
        except ad.DeployError:
            pass
        else:
            raise AssertionError("Arquivo inseguro aceito")
    destino = Path(pasta) / "aceito"
    ad.safe_extract(arquivo("src/arquivo.py"), destino)
    assert (destino / "src/arquivo.py").read_bytes() == b"abc"


def test_sqlite_so_copia_e_integridade(pasta):
    dados = Path(pasta) / "dados"
    dados.mkdir()
    for nome in ad.DATABASES:
        with closing(sqlite3.connect(dados / nome)) as c, c:
            c.executescript("CREATE TABLE pai(id PRIMARY KEY); CREATE TABLE filho(id REFERENCES pai(id)); INSERT INTO pai VALUES(1);")
    antes = {p.name: p.read_bytes() for p in dados.iterdir()}
    ad.validate_sqlite(dados)
    assert antes == {p.name: p.read_bytes() for p in dados.iterdir()}
    with closing(sqlite3.connect(dados / ad.DATABASES[0])) as c, c:
        c.execute("INSERT INTO filho VALUES(999)")
    try:
        ad.validate_sqlite(dados)
    except ad.DeployError as exc:
        assert exc.code == "sqlite_foreign_keys"
    else:
        raise AssertionError("Chave estrangeira invalida passou")


def test_config_ambiente_e_sandbox():
    base = dict(schema_version=1, repository="/srv/app", repository_url="https://github.com/test/example.git",
        venv="/srv/app/.venv", data_dir="/srv/data", service="auditoria-jb.service", control_plane_digest="a" * 40)
    c = ad.Config.from_dict(base)
    ambiente = ad.clean_environment("/tmp/sintetico", "/tmp/candidate/src")
    assert "AUDITORIA_COFRE_CHAVE" not in ambiente and not any("SMTP" in k for k in ambiente)
    assert ambiente["HOME"] == "/tmp/sintetico" and ambiente["PYTHONNOUSERSITE"] == "1"
    comando = ad.sandbox_command(c, "/var/lib/auditoria-jb-check/run1", ["/usr/bin/true"], "probe", 30)
    texto = " ".join(comando)
    for esperado in ("NoNewPrivileges=yes", "CapabilityBoundingSet=", "PrivateNetwork=yes", "PrivateTmp=yes", "MemoryMax=2G", "TasksMax=128", "CPUQuota=150%",
                     "ProtectSystem=strict", "ProtectProc=invisible", "User=auditoria-jb-check", "BindReadOnlyPaths="):
        assert esperado in texto, esperado
    assert "InaccessiblePaths=/srv/data" in texto and "ReadWritePaths=/var/lib/auditoria-jb-check/run1" in texto
    assert "ReadOnlyPaths=/var/lib/auditoria-jb-check/run1/candidate" in texto
    extracao = ad.sandbox_command(c, "/var/lib/auditoria-jb-check/run1", ["/usr/bin/true"], "extract", 30, writable_candidate=True)
    assert "ReadOnlyPaths=/var/lib/auditoria-jb-check/run1/candidate" not in " ".join(extracao)
    for campo, valor in (("repository_url", "file:///tmp/repo"), ("service", "app; touch arquivo"),
                         ("control_plane_digest", "main"), ("check_user", "root")):
        try:
            ad.Config.from_dict({**base, campo: valor})
        except ad.DeployError:
            pass
        else:
            raise AssertionError("Configuracao insegura aceita")


def test_exclusao_desktop_explicita_e_restrita(pasta):
    expected_tree, payload = fixture_git_archive(pasta)
    base = dict(schema_version=1, repository="/srv/app", repository_url="https://github.com/test/example.git",
        venv="/srv/app/.venv", data_dir="/srv/data", service="auditoria-jb.service", control_plane_digest="a" * 40,
        allowed_skips=["test_fdb_reader.py"])
    assert ad.Config.from_dict(base).excluded_tests == []
    for invalidos in (["test_web_tarefas.py"], ["test_ui_smoke.py", "test_ui_smoke.py"], "test_ui_smoke.py", [None]):
        try:
            ad.Config.from_dict({**base, "excluded_tests": invalidos})
        except ad.DeployError as exc:
            assert exc.code == "config_excluded_tests"
        else:
            raise AssertionError("Exclusao fora da lista estrita foi aceita")
    def preparar(excluir, falhar_web=False):
        root = Path(tempfile.mkdtemp(dir=pasta, prefix="exclusao_"))
        h = ad.Host.__new__(ad.Host)
        h.c = ad.Config.from_dict({**base, "excluded_tests": ["test_ui_smoke.py"] if excluir else []})
        h.work, h.gitwork = root / "work", root / "git"
        h.state_dir, h.run_id = root / "root", "exclusao-sintetica"
        h.state_dir.mkdir()
        (h.work / "candidate" / "tests").mkdir(parents=True)
        h.gitwork.mkdir()
        for nome in ("test_a_web.py", "test_fdb_reader.py", "test_ui_smoke.py"):
            (h.work / "candidate" / "tests" / nome).write_text("# sintetico", encoding="utf-8")
        h.create_work = lambda: None
        h.uid = h.gid = 1
        def git(args, *, stdout_path=None):
            if args[0] == "rev-parse":
                return expected_tree
            Path(stdout_path).write_bytes(payload)
            return ""
        h.git = git
        chamados = []
        def sandbox(args, **kwargs):
            if "--helper-extract" in args:
                return ""
            nome = Path(args[-1]).name
            chamados.append(nome)
            if nome == "test_ui_smoke.py":
                raise ad.DeployError("qt_indisponivel")
            if nome == "test_a_web.py" and falhar_web:
                raise ad.DeployError("teste_web_falhou")
            return "PULADO - Firebird sintetico" if nome == "test_fdb_reader.py" else "OK"
        h.sandbox = sandbox
        return h, chamados
    h, chamados = preparar(True)
    with patch.object(ad.os, "chown", create=True):
        result = h.test_candidate({"target_sha": "b" * 40})
    assert result["passed"] == ["test_a_web.py"]
    assert result["skipped"] == ["test_fdb_reader.py"]
    assert result["not_applicable"] == [{"test": "test_ui_smoke.py", "reason": "desktop/PySide6"}]
    assert chamados == ["test_a_web.py", "test_fdb_reader.py"]
    for excluir, falhar, erro in [(False, False, "qt_indisponivel"), (True, True, "teste_web_falhou")]:
        h, _ = preparar(excluir, falhar)
        with patch.object(ad.os, "chown", create=True):
            try:
                h.test_candidate({"target_sha": "b" * 40})
            except ad.DeployError as exc:
                assert exc.code == erro
            else:
                raise AssertionError("Falha foi convertida indevidamente em exclusao")


def test_saude_urls_e_ambiente():
    h = ad.Host.__new__(ad.Host)
    h.c = SimpleNamespace(health_url="http://127.0.0.1:8600", data_dir="/srv/dados")
    h.service = lambda: dict(MainPID="123", ActiveState="active", SubState="running", ExecMainStartTimestampMonotonic="12345")
    rotas = []
    class Resposta:
        def __init__(self, url):
            self.status = 200 if url.endswith("/api/estado") else 401
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, _): return b'{"precisa_bootstrap":false}'
    class Opener:
        def open(self, request, timeout):
            rotas.append(request.full_url)
            return Resposta(request.full_url)
    with patch.object(ad, "build_opener", return_value=Opener()):
        with patch.object(ad.Path, "read_bytes", return_value=b'AUDITORIA_COFRE_CHAVE=valor-sintetico\0AUDITORIA_WEB_DADOS=/srv/dados\0'):
            assert h.health() == 123
        assert rotas == ["http://127.0.0.1:8600/api/estado", "http://127.0.0.1:8600/api/tarefas/catalogo", "http://127.0.0.1:8600/api/clientes/catalogo"]
        for ambiente in (b'AUDITORIA_COFRE_CHAVE=\0AUDITORIA_WEB_DADOS=/srv/dados\0',
                         b'AUDITORIA_COFRE_CHAVE=teste\0AUDITORIA_WEB_DADOS=/srv/outro\0'):
            with patch.object(ad.Path, "read_bytes", return_value=ambiente):
                try:
                    h.health()
                except ad.DeployError as exc:
                    assert exc.code == "service_environment"
                else:
                    raise AssertionError("Saude aceita ambiente divergente")


def test_inventario_preserva_ids_eventos_e_cifras(pasta):
    dados = Path(pasta) / "inventario"
    dados.mkdir()
    for nome in ad.DATABASES:
        with closing(sqlite3.connect(dados / nome)) as conn, conn:
            conn.executescript("PRAGMA user_version=3; CREATE TABLE cliente(id INTEGER PRIMARY KEY,nome TEXT);"
                "CREATE TABLE segredo(id INTEGER PRIMARY KEY,cifra BLOB,nonce BLOB);"
                "CREATE TABLE evento(id INTEGER PRIMARY KEY,acao TEXT);"
                "CREATE TRIGGER cliente_sem_delete BEFORE DELETE ON cliente BEGIN SELECT RAISE(ABORT,'sem delete'); END;"
                "CREATE TRIGGER evento_imutavel BEFORE UPDATE ON evento BEGIN SELECT RAISE(ABORT,'imutavel'); END;"
                "INSERT INTO cliente VALUES(1,'Original'); INSERT INTO segredo VALUES(1,X'0102',X'0304'); INSERT INTO evento VALUES(1,'original');")
    antes = ad.sqlite_inventory(dados)
    with closing(sqlite3.connect(dados / "clientes.db")) as conn, conn:
        conn.executescript("UPDATE cliente SET nome='Editavel' WHERE id=1; INSERT INTO cliente VALUES(2,'Novo'); INSERT INTO evento VALUES(2,'novo');")
    depois = ad.sqlite_inventory(dados, antes)
    ad.compare_inventory(antes, depois)
    with closing(sqlite3.connect(dados / "clientes.db")) as conn, conn:
        conn.execute("UPDATE segredo SET cifra=X'0909' WHERE id=1")
    try:
        ad.compare_inventory(antes, ad.sqlite_inventory(dados, antes))
    except ad.DeployError as exc:
        assert exc.code == "immutable_data_changed"
    else:
        raise AssertionError("Cifra alterada passou")
    with closing(sqlite3.connect(dados / "clientes.db")) as conn, conn:
        conn.executescript("UPDATE segredo SET cifra=X'0102' WHERE id=1; DROP TRIGGER cliente_sem_delete; DELETE FROM cliente WHERE id=1;")
    try:
        ad.compare_inventory(antes, ad.sqlite_inventory(dados, antes))
    except ad.DeployError as exc:
        assert exc.code == "existing_ids_missing"
    else:
        raise AssertionError("Identidade antiga removida passou")


def test_recuperacao_e_cleanup_limitado(pasta):
    backup = Path(pasta) / "backup"
    backup.mkdir()
    ad.write_recovery(backup, "a" * 40, "/etc/segredos/copia")
    texto = (backup / "RECUPERACAO.md").read_text(encoding="utf-8")
    assert "hold" in texto and "autom" in texto and "repository.bundle" in texto and "venv" in texto
    parent = Path(pasta) / "work"
    parent.mkdir()
    h = ad.Host.__new__(ad.Host)
    h.run_id = "sintetico"
    h.c = SimpleNamespace(check_work_dir=str(parent))
    h.work, h.gitwork = parent / "check-sintetico", parent / "git-sintetico"
    h.work.mkdir(); h.gitwork.mkdir()
    h.logs = Path(pasta) / "logs"
    h.logs.mkdir()
    (h.logs / "sintetico-1.log").write_text("teste")
    (h.logs / "outro-1.log").write_text("preservado")
    h.cleanup(keep_logs=False)
    assert not h.work.exists() and not h.gitwork.exists()
    assert (h.logs / "outro-1.log").exists() and backup.exists()


def test_deadline_parada_e_copia(pasta):
    h = ad.Host.__new__(ad.Host)
    h.deadline = time.monotonic() + 100
    original = h.deadline
    h.last_pid = 0
    h.c = SimpleNamespace(service="sintetico.service")
    estados = iter([dict(MainPID="123", ActiveState="active"), dict(MainPID="0", ActiveState="inactive")])
    h.service = lambda: next(estados)
    def comando(*args, **kwargs):
        assert h.deadline == original, "Parada normal desativou limite global"
    h.command = comando
    h.stop()
    origem, destino = Path(pasta) / "origem", Path(pasta) / "destino"
    origem.write_bytes(b"dado sintetico")
    try:
        ad.copy_regular(origem, destino, deadline=time.monotonic()-1)
    except ad.DeployError as exc:
        assert exc.code == "maintenance_timeout"
    else:
        raise AssertionError("Copia ignorou deadline")
    assert not destino.exists()


def test_abertura_por_ancestrais():
    calls, closed = [], []
    def abrir(path, flags, *, dir_fd=None):
        calls.append((path, dir_fd))
        if path == "fonte":
            raise OSError("symlink sintetico em ancestral")
        return 100 + len(calls)
    with patch.object(ad.os, "open", side_effect=abrir), patch.object(ad.os, "close", side_effect=closed.append), \
         patch.object(ad.os, "O_DIRECTORY", 0x10000, create=True), patch.object(ad.os, "O_NOFOLLOW", 0x20000, create=True):
        try:
            ad.open_directory_nofollow("/home/usuario/fonte/dados")
        except ad.DeployError as exc:
            assert exc.code == "source_directory_unsafe"
        else:
            raise AssertionError("Ancestral inseguro aceito")
    assert [p for p, _ in calls] == ["/", "home", "usuario", "fonte"]
    assert all(fd is not None for _, fd in calls[1:]) and len(closed) == 3


def test_baseline_nao_segue_link_do_candidato(pasta):
    alvo = Path(pasta) / "configuracao-protegida"
    alvo.write_text("preservar", encoding="utf-8")
    baseline = Path(pasta) / "migration-baseline.json"
    # Hardlink funciona tambem no Windows e reproduz a mesma sobrescrita por
    # write_text; O_EXCL deve recusar qualquer destino previamente existente.
    os.link(alvo, baseline)
    try:
        ad.write_new_private(baseline, '{"substituir":true}')
    except ad.DeployError as exc:
        assert exc.code == "private_destination_exists"
    else:
        raise AssertionError("Baseline preexistente foi sobrescrito")
    assert alvo.read_text(encoding="utf-8") == "preservar"
    novo = Path(pasta) / "baseline-novo.json"
    ad.write_new_private(novo, '{}')
    assert novo.read_text() == '{}'
    if os.name == "posix":
        symlink = Path(pasta) / "post-integrity-baseline.json"
        symlink.symlink_to(alvo)
        try:
            ad.write_new_private(symlink, "substituir")
        except ad.DeployError:
            pass
        else:
            raise AssertionError("Symlink do candidato foi seguido")
        assert alvo.read_text() == "preservar"


def test_manifesto_recuperavel_sem_seguir_links(pasta):
    origem = Path(pasta) / "manifesto-origem"
    destino = Path(pasta) / "manifesto-copia"
    origem.mkdir(); destino.mkdir()
    (origem / "arquivo").write_bytes(b"conteudo sintetico")
    (destino / "arquivo").write_bytes(b"conteudo sintetico")
    h = ad.Host.__new__(ad.Host)
    h.deadline = None
    registros = h.manifest(destino, source=origem)
    registro = registros["arquivo"]
    assert registro["type"] == "file" and registro["sha256"] == hashlib.sha256(b"conteudo sintetico").hexdigest()
    info = (origem / "arquivo").stat()
    assert registro["source"] == dict(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
    assert registros["."]["type"] == "directory"
    if os.name == "posix":
        (origem / "python").symlink_to("/arquivo-externo-inexistente")
        (destino / "python").symlink_to("/arquivo-externo-inexistente")
        item = h.manifest(destino, source=origem)["python"]
        assert item["type"] == "symlink" and item["target"] == "/arquivo-externo-inexistente" and "sha256" not in item


def fixture_git_archive(pasta, *, attributes=None):
    repo = Path(tempfile.mkdtemp(dir=pasta, prefix="git_archive_"))
    (repo / "tests").mkdir()
    (repo / "tests/test_sintetico.py").write_bytes(b"assert False, 'suite original reprova'\n")
    (repo / "executavel.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    (repo / "a.c").write_bytes(b"arquivo antes de diretorio\n")
    (repo / "a").mkdir()
    (repo / "a/acentuado-ç.txt").write_bytes(b"conteudo sintetico\n")
    if attributes:
        (repo / ".gitattributes").write_text(attributes, encoding="utf-8")
    def git(*args):
        return subprocess.check_output(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args])
    git("init", "--quiet")
    git("add", ".")
    git("update-index", "--chmod=+x", "executavel.sh")
    tree = git("write-tree").decode().strip()
    return tree, git("archive", "--format=tar", tree)


def alterar_archive(payload, mutacao="conteudo"):
    output = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as src, tarfile.open(fileobj=output, mode="w") as dst:
        for item in src:
            if mutacao == "ausente" and item.name == "a.c":
                continue
            data = src.extractfile(item).read() if item.isfile() else None
            if mutacao == "modo" and item.name == "executavel.sh":
                item.mode = 0o644
            if mutacao == "conteudo" and item.name == "tests/test_sintetico.py":
                data = b"print('OK - conteudo substituido')\n"
                item.size = len(data)
            dst.addfile(item, io.BytesIO(data) if data is not None else None)
    return output.getvalue()


def test_archive_adulterado_falha_antes_da_manutencao(pasta):
    expected, original = fixture_git_archive(pasta)
    h = HostFalso()
    root = Path(tempfile.mkdtemp(dir=pasta, prefix="archive_host_"))
    h.state_dir, h.gitwork, h.work = root / "root", root / "ubuntu", root / "check"
    h.state_dir.mkdir(); h.gitwork.mkdir()
    h.run_id = "archive-sintetico"
    h.uid = h.gid = 1
    h.c = SimpleNamespace(excluded_tests=[], allowed_skips=[], total_test_timeout=20, test_timeout=10)
    def create_work():
        (h.work / "candidate").mkdir(parents=True)
    h.create_work = create_work
    destinations = []
    def git(args, *, stdout_path=None, **kwargs):
        if args[0] == "rev-parse":
            assert args[1] == h.alvo + "^{tree}"
            return expected
        assert args[0] == "archive"
        if stdout_path is not None:
            assert not any(a.startswith("--output") for a in args), "Caminho privado exposto ao Git"
        path = Path(stdout_path) if stdout_path else Path(next(a.split("=", 1)[1] for a in args if a.startswith("--output=")))
        destinations.append(path)
        path.write_bytes(original)
        # Reproduz substituicao por outro tar REGULAR depois de git archive.
        path.write_bytes(alterar_archive(original))
        return ""
    h.git = git
    def sandbox(args, **kwargs):
        if "--helper-extract" in args:
            with Path(args[-2]).open("rb") as payload:
                ad.safe_extract(payload, args[-1])
        return "OK - teste sintetico"
    h.sandbox = sandbox
    h.test_candidate = lambda revision: ad.Host.test_candidate(h, revision)
    with patch.object(ad.os, "chown", create=True):
        assert ad.Runner(h).run() == 1, "Tar substituido foi testado e SHA original foi implantado"
    assert h.estado["error"] == "archive_mismatch", h.estado
    assert h.ativo and not h.held and "maintenance" not in h.eventos and "stop" not in h.eventos
    assert destinations and destinations[0].is_relative_to(h.state_dir)


def test_archive_oid_git_real_e_export_ignore(pasta):
    expected, payload = fixture_git_archive(pasta)
    assert ad.archive_tree_oid(io.BytesIO(payload), len(expected)) == expected
    for mutacao in ("conteudo", "modo", "ausente"):
        assert ad.archive_tree_oid(io.BytesIO(alterar_archive(payload, mutacao)), len(expected)) != expected
    expected, exported = fixture_git_archive(pasta, attributes="tests/test_sintetico.py export-ignore\n")
    assert ad.archive_tree_oid(io.BytesIO(exported), len(expected)) != expected


def test_stdout_binario_separado_do_log(pasta):
    root = Path(pasta) / "stdout_root"
    root.mkdir()
    h = ad.Host.__new__(ad.Host)
    h.c = SimpleNamespace(command_timeout=10)
    h.deadline, h.counter, h.run_id, h.logs = None, 0, "stdout-sintetico", root
    destination = root / "candidate.tar"
    output = h.command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\x00bytes-do-tar'); sys.stderr.write('diagnostico')"], stdout_path=destination)
    assert destination.read_bytes() == b"\x00bytes-do-tar"
    assert output == "diagnostico"
    assert b"bytes-do-tar" not in (root / "stdout-sintetico-1.log").read_bytes()
    h.gitwork = root / "ubuntu"
    h.c = SimpleNamespace(deploy_user="ubuntu", repository="/repo/sintetico")
    with patch.object(h, "command", return_value="") as command:
        h.git(["archive", "--format=tar", "b" * 40], stdout_path=destination)
    argv = command.call_args.args[0]
    assert "core.autocrlf=false" in argv
    assert not any(arg.startswith("--output") for arg in argv)
    assert str(destination) not in argv and command.call_args.kwargs["stdout_path"] == destination


def test_inventario_atualizacao_condicional_legal(pasta):
    directory = Path(pasta) / "inventario_condicional"
    directory.mkdir()
    for name in ad.DATABASES:
        with closing(sqlite3.connect(directory / name)) as conn, conn:
            conn.executescript("CREATE TABLE numeracao(id INTEGER PRIMARY KEY,proximo INTEGER);"
                "CREATE TRIGGER so_cresce BEFORE UPDATE ON numeracao WHEN NEW.proximo < OLD.proximo "
                "BEGIN SELECT RAISE(ABORT,'nao pode diminuir'); END;"
                "CREATE TABLE evento(id INTEGER PRIMARY KEY,acao TEXT);"
                "CREATE TRIGGER evento_imutavel BEFORE UPDATE ON evento BEGIN SELECT RAISE(ABORT,'imutavel'); END;"
                "CREATE TABLE segredo(id INTEGER PRIMARY KEY,cifra BLOB);"
                "INSERT INTO numeracao VALUES(1,1); INSERT INTO evento VALUES(1,'original'); INSERT INTO segredo VALUES(1,X'0102');")
    before = ad.sqlite_inventory(directory)
    with closing(sqlite3.connect(directory / "nfse.db")) as conn, conn:
        conn.execute("UPDATE numeracao SET proximo=2")
    ad.compare_inventory(before, ad.sqlite_inventory(directory, before))
    for table, sql, undo in [("segredo", "UPDATE segredo SET cifra=X'0304'", "UPDATE segredo SET cifra=X'0102'"),
                             ("evento", "DROP TRIGGER evento_imutavel; UPDATE evento SET acao='alterado'", "")]:
        with closing(sqlite3.connect(directory / "nfse.db")) as conn, conn:
            conn.executescript(sql)
        try:
            ad.compare_inventory(before, ad.sqlite_inventory(directory, before))
        except ad.DeployError as exc:
            assert exc.code == "immutable_data_changed"
        else:
            raise AssertionError("Alteracao imutavel aceita: " + table)
        if undo:
            with closing(sqlite3.connect(directory / "nfse.db")) as conn, conn:
                conn.executescript(undo)


def test_crontab_preflight_sem_cron_e_falha(pasta):
    def host(status, text):
        h = HostFalso()
        h.original_pid = 123
        h.health = lambda: 123
        h.clean_checkout = lambda: h.atual
        h.space = lambda: None
        h.c = SimpleNamespace(repository_url="https://github.com/test/example.git", control_plane_digest="c" * 40)
        h.crontab_snapshot = None
        h.git = lambda args: "c" * 40 if args[0] == "rev-parse" and ":" in args[1] else h.alvo if args[0] == "rev-parse" else ""
        def command(args, **kwargs):
            assert args == ["/usr/bin/crontab", "-u", "ubuntu", "-l"]
            assert not h.held and h.ativo
            h.eventos.append("read_cron")
            return status, text
        h.command = command
        h.capture_crontab = lambda: ad.Host.capture_crontab(h)
        h.preflight = lambda: ad.Host.preflight(h)
        return h
    with patch.object(ad, "protected_window", return_value=False):
        h = host(1, "no crontab for ubuntu\n")
        assert ad.Runner(h).run() == 0
        assert h.crontab_snapshot["present"] is False and h.crontab_snapshot["content"] == ""
        assert h.eventos.index("read_cron") < h.eventos.index("maintenance")
        h = host(1, "crontabs: Permission denied\n")
        assert ad.Runner(h).run() == 1, "Falha do cron deveria ser detectada antes da parada"
        assert h.estado["error"] == "crontab_preflight_failed"
        assert h.ativo and not h.held and "maintenance" not in h.eventos
        h = host(0, "45 7 * * * comando-sintetico\n")
        assert ad.Runner(h).run() == 0 and h.crontab_snapshot["present"] is True
        assert h.crontab_snapshot["content"] == "45 7 * * * comando-sintetico\n"


def test_backup_sem_crontab_usa_captura_previa(pasta):
    root = Path(pasta) / "backup_sem_cron"
    root.mkdir()
    h = ad.Host.__new__(ad.Host)
    h.run_id, h.deadline = "sintetico", None
    h.c = SimpleNamespace(backup_dir=str(root / "backups"), secrets_backup_dir=str(root / "secrets"),
        data_dir=str(root / "data"), venv=str(root / "venv"), configuration_paths=[], secret_paths=[])
    Path(h.c.backup_dir).mkdir(); Path(h.c.secrets_backup_dir).mkdir()
    h.gitwork = root / "git"
    h.gitwork.mkdir()
    h.has_hold = lambda: True
    h.service = lambda: dict(MainPID="0")
    h.copy_config = lambda sources, dest: Path(dest).mkdir(exist_ok=True)
    h.manifest = lambda *args, **kwargs: {}
    h.crontab_snapshot = dict(present=False, content="", captured_at="2026-10-28T12:00:00+00:00")
    def git(args):
        if args[0] == "bundle":
            Path(args[2]).write_bytes(b"bundle sintetico")
            return ""
        return "a" * 40
    h.git = git
    def forbidden(*args, **kwargs):
        raise AssertionError("Backup leu crontab depois de parar o servico")
    h.command = forbidden
    with patch.object(ad, "copy_tree", side_effect=lambda src, dst, **kwargs: Path(dst).mkdir()):
        target = Path(h.backup("pre"))
    secret = Path(h.c.secrets_backup_dir) / h.run_id
    meta = __import__('json').loads((secret / "manifest.json").read_text())
    assert meta["crontab_present"] is False and meta["crontab_captured_at"] == h.crontab_snapshot["captured_at"]
    assert (secret / "crontab-ubuntu.txt").read_text() == ""
    assert (target / "RECUPERACAO.md").is_file()


def main():
    test_fluxo_e_falhas()
    test_noop_check_e_interrupcao()
    test_politica_falha_e_candidato_rejeitado()
    test_janela_temporal()
    test_config_ambiente_e_sandbox()
    test_saude_urls_e_ambiente()
    test_abertura_por_ancestrais()
    with tempfile.TemporaryDirectory(prefix="autodeploy_sintetico_") as pasta:
        test_archive_adulterado_falha_antes_da_manutencao(pasta)
        test_archive_oid_git_real_e_export_ignore(pasta)
        test_stdout_binario_separado_do_log(pasta)
        test_inventario_atualizacao_condicional_legal(pasta)
        test_crontab_preflight_sem_cron_e_falha(pasta)
        test_backup_sem_crontab_usa_captura_previa(pasta)
        test_archive_sem_links_ou_escape(pasta)
        test_sqlite_so_copia_e_integridade(pasta)
        test_inventario_preserva_ids_eventos_e_cifras(pasta)
        test_recuperacao_e_cleanup_limitado(pasta)
        test_deadline_parada_e_copia(pasta)
        test_baseline_nao_segue_link_do_candidato(pasta)
        test_manifesto_recuperavel_sem_seguir_links(pasta)
        test_exclusao_desktop_explicita_e_restrita(pasta)
    print("OK - autodeploy: fluxo, falhas, interrupcao, no-op, sandbox, arquivo e SQLite sinteticos")


if __name__ == "__main__":
    main()
