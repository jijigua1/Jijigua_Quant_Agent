import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX privilege launcher requires grp/pwd')


def load_launcher(monkeypatch):
    monkeypatch.setitem(sys.modules, "pwd", SimpleNamespace(getpwnam=lambda name: SimpleNamespace(pw_uid=1234, pw_gid=1234)))
    path = Path(__file__).parents[1] / "deploy" / "launcher.py"
    spec = importlib.util.spec_from_file_location("tested_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_drops_root_and_clears_environment_before_exec(tmp_path, monkeypatch):
    launcher = load_launcher(monkeypatch)
    launcher.ROOT = tmp_path
    order = []
    identity = [0]
    monkeypatch.setattr(os, "geteuid", lambda: identity[0], raising=False)
    monkeypatch.setattr(os, "setgroups", lambda groups: order.append(("groups", groups)), raising=False)
    monkeypatch.setattr(os, "setgid", lambda gid: order.append(("gid", gid)), raising=False)
    def setuid(uid):
        identity[0] = uid
        order.append(("uid", uid))
    monkeypatch.setattr(os, "setuid", setuid, raising=False)
    monkeypatch.setattr(os, "chdir", lambda p: None)
    monkeypatch.setattr(os, "umask", lambda v: None)
    monkeypatch.setenv("QRA_DEEPSEEK_API_KEY", "DUMMY_LAUNCH_KEY")
    monkeypatch.setenv("SSH_AUTH_SOCK", "must_not_inherit")
    monkeypatch.setenv("PYTHONPATH", "must_not_inherit")
    monkeypatch.setattr(sys, "argv", ["quant-agent", "chat"])
    def execute(path, args, environment):
        assert identity[0] == 1234 and args[-1] == "chat" and "-I" in args
        assert "SSH_AUTH_SOCK" not in environment and "PYTHONPATH" not in environment
        assert "DUMMY_LAUNCH_KEY" not in str(args)
        order.append(("exec", path))
    monkeypatch.setattr(os, "execve", execute)
    launcher.main()
    assert [x[0] for x in order] == ["groups", "gid", "uid", "exec"]


def test_launcher_read_commands_do_not_require_or_forward_key(tmp_path, monkeypatch):
    launcher = load_launcher(monkeypatch)
    launcher.ROOT = tmp_path
    monkeypatch.setattr(os, "geteuid", lambda: 1234, raising=False)
    monkeypatch.setattr(os, "chdir", lambda p: None)
    monkeypatch.setattr(os, "umask", lambda v: None)
    monkeypatch.setenv("QRA_DEEPSEEK_API_KEY", "DUMMY_SHOULD_NOT_FORWARD")
    monkeypatch.setattr(launcher.getpass, "getpass", lambda *args: pytest.fail("Key prompt for status"))
    monkeypatch.setattr(sys, "argv", ["quant-agent", "status", "0" * 32])
    monkeypatch.setattr(os, "execve", lambda p, a, e: e.get("QRA_DEEPSEEK_API_KEY") is None or pytest.fail("Key forwarded"))
    launcher.main()
