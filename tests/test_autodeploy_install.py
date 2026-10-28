"""Instalador auto-deploy: comandos simulados e arquivos temporários, sem VM."""
from pathlib import Path
from contextlib import nullcontext
import json
import os
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import types
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def main():
    script = ROOT / "devops/autodeploy/install.sh"
    assert script.is_file(), "Instalador ainda não implementado"
    text = script.read_text(encoding="utf-8")
    code = text.split("<<'PY_INSTALL'\n", 1)[1].rsplit("\nPY_INSTALL", 1)[0]
    module = types.ModuleType("autodeploy_installer_test")
    exec(compile(code, str(script), "exec"), module.__dict__)
    bash = shutil.which("bash")
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if os.name == "nt" and git_bash.is_file():
        bash = str(git_bash)
    if bash:
        subprocess.run([bash, "-n", str(script)], check=True)
    else:
        print("PULADO - bash -n indisponível; contrato Python segue testado")

    calls = []
    values = {"User": "ubuntu", "WorkingDirectory": module.REPOSITORY,
              "ExecStart": "{ path=" + module.PYTHON + " ; argv[]=" + " ".join(module.APP_ARGV) + " ; ignore_errors=no ; }",
              "FragmentPath": "/etc/systemd/system/auditoria-jb.service", "DropInPaths": "", "ActiveState": "inactive"}
    def command(args):
        calls.append(args)
        if args[:2] == ["/usr/bin/systemctl", "show"]:
            return values[args[3].split("=", 1)[1]]
        return ""

    with patch.object(module, "command", command), patch.object(module.socket, "gethostname", return_value="arm07"), \
         patch.object(module.os, "geteuid", return_value=0, create=True):
        module.verify_host_service()
        for key, bad in [("User", "root"), ("WorkingDirectory", "/tmp/other"),
                         ("ExecStart", values["ExecStart"].replace("127.0.0.1", "0.0.0.0")),
                         ("ExecStart", values["ExecStart"].replace("8600", "8601")),
                         ("ExecStart", values["ExecStart"].replace("--factory", "--workers 2 --factory"))]:
            old = values[key]; values[key] = bad
            try:
                try: module.verify_host_service()
                except module.InstallError: pass
                else: raise AssertionError(f"Aceitou serviço incompatível: {key}")
            finally: values[key] = old
        with patch.object(module.socket, "gethostname", return_value="another-host"):
            try: module.verify_host_service()
            except module.InstallError: pass
            else: raise AssertionError("Aceitou host diferente")
        with patch.object(module.os, "geteuid", return_value=1000, create=True):
            try: module.verify_host_service()
            except module.InstallError: pass
            else: raise AssertionError("Aceitou usuário sem root")

    # Não confiar só no arquivo final: um ancestral gravável permite substituí-lo.
    absolute = Path(tempfile.gettempdir()).resolve() / "controller" / "runner.py"
    root_stat = types.SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)
    with patch.object(Path, "lstat", return_value=root_stat):
        module.secure_root_path(absolute)
    for mode, uid in [(stat.S_IFDIR | 0o775, 0), (stat.S_IFDIR | 0o755, 1000), (stat.S_IFLNK | 0o777, 0)]:
        bad_stat = types.SimpleNamespace(st_uid=uid, st_mode=mode)
        with patch.object(Path, "lstat", return_value=bad_stat):
            try: module.secure_root_path(absolute)
            except module.InstallError: pass
            else: raise AssertionError("Aceitou caminho não controlado pelo root")

    # A conta do sandbox nunca pode coincidir com root/ubuntu ou ganhar grupos.
    check_user = types.SimpleNamespace(pw_uid=997,pw_gid=997,pw_dir="/nonexistent",pw_shell="/usr/sbin/nologin")
    fake_pwd = types.SimpleNamespace(getpwnam=Mock(return_value=check_user))
    fake_grp = types.SimpleNamespace(getgrgid=Mock(return_value=types.SimpleNamespace(gr_name="auditoria-jb-check")),
                                    getgrall=Mock(return_value=[]))
    user_calls = []
    def user_command(args):
        user_calls.append(args)
        return "auditoria-jb-check L synthetic" if "-S" in args else ""
    with patch.dict(sys.modules, {"pwd":fake_pwd,"grp":fake_grp}), patch.object(module,"command",user_command):
        module.verify_check_user()
        check_user.pw_uid=0
        try: module.verify_check_user()
        except module.InstallError: pass
        else: raise AssertionError("Aceitou conta root para testes")
        check_user.pw_uid=997
        fake_grp.getgrall.return_value=[types.SimpleNamespace(gr_mem=["auditoria-jb-check"])]
        try: module.verify_check_user()
        except module.InstallError: pass
        else: raise AssertionError("Aceitou conta de testes com grupo suplementar")
        fake_grp.getgrall.return_value=[]
        fake_pwd.getpwnam.side_effect=[KeyError(),check_user]
        module.verify_check_user(create=True)
        creation=next(c for c in user_calls if c[0]=="/usr/sbin/useradd")
        assert "--system" in creation and "--no-create-home" in creation and "/usr/sbin/nologin" in creation

    with tempfile.TemporaryDirectory(prefix="autodeploy_install_synthetic_") as folder:
        base = Path(folder)
        source = base / "source"; source.mkdir()
        for name in ("runner.py", "auditoria-jb-autodeploy.service", "auditoria-jb-autodeploy.timer"):
            (source / name).write_text("# synthetic " + name, encoding="utf-8")
        paths = {key: base / key / Path(value).name for key, value in module.PATHS.items()}
        cofre = base / "cofre.env"; cofre.write_text("SYNTHETIC_SECRET_DO_NOT_PRINT", encoding="utf-8"); cofre.chmod(0o600)
        unit = base / "application.service"; unit.write_text("# synthetic existing unit", encoding="utf-8")
        calls.clear()
        with patch.object(module, "PATHS", paths), patch.object(module, "command", command), \
             patch.object(module, "verify_host_service"), patch.object(module, "secure_root_path"), \
             patch.object(module, "verify_check_user"), patch.object(module, "configuration_sources", return_value=[unit]), \
             patch.object(module, "controller_lock", nullcontext), \
             (patch.object(module.stat, "S_IMODE", return_value=0o600) if os.name == "nt" else nullcontext()):
            empty = base / "empty"; empty.mkdir()
            assert module.package_digest(empty, 40) == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            digest = module.package_digest(source, 40)
            # Comparar o cálculo próprio com Git real, só em fixture sintética,
            # com índice/objetos fora do pacote; o instalador nunca invoca Git.
            git = shutil.which("git")
            if git:
                objects = base / "objects.git"
                subprocess.run([git,"init","--bare",str(objects)],check=True,capture_output=True)
                git_args=[git,"--git-dir="+str(objects),"--work-tree="+str(source),"-c","core.autocrlf=false"]
                subprocess.run([*git_args,"add","--all"],check=True,capture_output=True)
                expected=subprocess.check_output([*git_args,"write-tree"],text=True).strip()
                assert digest==expected, "OID do pacote diverge do Git"
            for invalid in (None, "main", "a" * 40):
                try: module.install(source, cofre, [], invalid)
                except module.InstallError: pass
                else: raise AssertionError("Aceitou pacote sem OID aprovado correspondente")
            assert not paths["config"].exists()
            module.install(source, cofre, [], digest)
            config = json.loads(paths["config"].read_text())
            assert config["schema_version"] == 1
            assert config["control_plane_digest"] == digest
            assert config["repository"] == module.REPOSITORY
            assert config["health_url"] == "http://127.0.0.1:8600"
            assert config["check_user"] == "auditoria-jb-check"
            assert config["check_work_dir"] == str(paths["check_work"])
            assert str(cofre) in config["secret_paths"] and str(cofre) not in config["configuration_paths"]
            assert str(unit) in config["configuration_paths"]
            assert config["allowed_skips"] == ["test_fdb_reader.py", "test_web_produtos_fdb.py"]
            assert config["excluded_tests"] == ["test_ui_smoke.py"]
            assert "ConditionPathExists=!/var/lib/auditoria-jb-autodeploy/hold" in paths["guard"].read_text()
            assert not any("enable" in c or "--check" in c or "--once" in c for c in calls), calls
            first = paths["config"].read_bytes()
            values["ActiveState"]="active"
            try: module.install(source, cofre, [], digest)
            except module.InstallError: pass
            else: raise AssertionError("Reinstalou com timer/executor ativo")
            values["ActiveState"]="inactive"
            assert paths["config"].read_bytes()==first
            module.install(source, cofre, [], digest)
            assert paths["config"].read_bytes() == first
            # O upgrade salva a configuração anterior antes de substituí-la.
            paths["config"].write_text('{"previous":"synthetic"}', encoding="utf-8")
            module.install(source, cofre, [], digest)
            copies = list(paths["state"].glob("install-backups/*/config"))
            assert copies and any(p.read_text() == '{"previous":"synthetic"}' for p in copies)
            assert all("SYNTHETIC_SECRET_DO_NOT_PRINT" not in p.read_text() for p in paths["state"].rglob("*") if p.is_file())
            # --check rejeitado nunca habilita timer.
            calls.clear()
            def reject_check(args):
                calls.append(args)
                if "--check" in args: raise module.InstallError("synthetic preflight failure")
                return ""
            with patch.object(module, "command", reject_check):
                try: module.enable()
                except module.InstallError: pass
                else: raise AssertionError("Ativou sem preflight")
            assert not any("enable" in c for c in calls)
            calls.clear(); module.enable()
            check_index = next(i for i,c in enumerate(calls) if "--check" in c)
            enable_index = next(i for i,c in enumerate(calls) if "enable" in c)
            assert check_index < enable_index
            assert str(paths["runner"]) in calls[check_index] and str(source / "runner.py") not in calls[check_index]

    service = (ROOT / "devops/autodeploy/auditoria-jb-autodeploy.service").read_text()
    timer = (ROOT / "devops/autodeploy/auditoria-jb-autodeploy.timer").read_text()
    assert "User=root" in service and "UMask=0077" in service
    assert "/usr/bin/python3 -I /usr/local/lib/auditoria-jb-autodeploy/runner.py" in service
    assert "--once" in service and "Restart=no" in service
    assert "OnBootSec=2min" in timer and "OnUnitInactiveSec=2min" in timer
    assert "Persistent=true" not in timer
    assert "ctl.sh" not in text and "crontab" not in text
    # O exemplo operacional precisa continuar aceito pelo contrato real do runner.
    readme = (ROOT / "devops/autodeploy/README.md").read_text(encoding="utf-8")
    example = json.loads(readme.split("```json\n", 1)[1].split("```", 1)[0])
    example["control_plane_digest"] = "a" * 40
    runner = runpy.run_path(str(ROOT / "devops/autodeploy/runner.py"))
    parsed = runner["Config"].from_dict(example)
    assert parsed.maintenance_timeout == 900
    assert parsed.allowed_skips == ["test_fdb_reader.py", "test_web_produtos_fdb.py"]
    assert parsed.excluded_tests == ["test_ui_smoke.py"]
    assert parsed.health_url == "http://127.0.0.1:8600"
    print("OK - auto-deploy install: host, serviço, paths root, config, backup e ativação condicionada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
