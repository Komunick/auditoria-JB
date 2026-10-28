"""Executor de deploy: falhas sinteticas; nunca acessa servico ou dados reais."""
import importlib.util
import hashlib
import io
import os
import sqlite3
import stat
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


def main():
    test_fluxo_e_falhas()
    test_noop_check_e_interrupcao()
    test_politica_falha_e_candidato_rejeitado()
    test_janela_temporal()
    test_config_ambiente_e_sandbox()
    test_saude_urls_e_ambiente()
    test_abertura_por_ancestrais()
    with tempfile.TemporaryDirectory(prefix="autodeploy_sintetico_") as pasta:
        test_archive_sem_links_ou_escape(pasta)
        test_sqlite_so_copia_e_integridade(pasta)
        test_inventario_preserva_ids_eventos_e_cifras(pasta)
        test_recuperacao_e_cleanup_limitado(pasta)
        test_deadline_parada_e_copia(pasta)
        test_baseline_nao_segue_link_do_candidato(pasta)
        test_manifesto_recuperavel_sem_seguir_links(pasta)
    print("OK - autodeploy: fluxo, falhas, interrupcao, no-op, sandbox, arquivo e SQLite sinteticos")


if __name__ == "__main__":
    main()
