"""Root-owned Linux launcher: drop identity before importing/running Agent code."""

import getpass
import os
from pathlib import Path
import pwd
import grp
import sys

ROOT = Path("/opt/jijigua-quant-agent/research_agent")


def main():
    account = pwd.getpwnam("quantagent")
    if account.pw_uid == 0 or os.geteuid() not in {0, account.pw_uid}:
        raise SystemExit("Launcher identity denied")
    command = sys.argv[1:] or ["chat"]
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(ROOT / "var"),
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TERM": os.environ.get("TERM", "dumb")}
    if command[0] not in {"status", "logs", "result", "session", "history", "session_tasks"}:
        secret = os.environ.get("QRA_DEEPSEEK_API_KEY") or getpass.getpass("DeepSeek Key (not echoed): ")
        if not secret:
            raise SystemExit("DeepSeek Key required")
        environment["QRA_DEEPSEEK_API_KEY"] = secret
    arguments = [str(ROOT / ".venv/bin/python"), "-I", "-m", "research_agent",
                 "--state-dir", str(ROOT / "var/state"), "--profile", "development", "--provider", "deepseek"]
    manifest = ROOT / "config/resources.json"
    if manifest.exists():
        arguments += ["--skill", "data_query", "--resources-manifest", str(manifest)]
    research=ROOT/'config/research.json'
    if research.exists():
        arguments += ['--research-config',str(research)]
    environment.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                       MPLCONFIGDIR=str(ROOT/'var/matplotlib'))
    arguments += command
    os.umask(0o077)
    os.chdir(ROOT)
    if os.geteuid() == 0:
        os.setgroups([grp.getgrnam('quantdata').gr_gid])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    if os.geteuid() != account.pw_uid:
        raise SystemExit("Identity drop failed")
    os.execve(arguments[0], arguments, environment)


if __name__ == "__main__":
    main()
