"""Entry of the root broker process for one CLI session (exec'd by the launcher). Never imports Agent code."""
import json
import os
import signal
import socket
import stat
import sys
from pathlib import Path


def main(fd, child_pid, config_path):
    signal.signal(signal.SIGINT, signal.SIG_IGN)       # Ctrl+C belongs to the Agent; the broker stays to answer
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    path = Path(config_path)
    st = os.stat(path, follow_symlinks=False)
    if os.geteuid() != 0 or not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o077:
        raise SystemExit('broker configuration must be root-private')
    from rolling_test.broker import Broker, serve
    sock = socket.socket(fileno=fd)
    try:
        serve(sock, Broker(json.loads(path.read_text(encoding='utf-8'))))
    finally:
        sock.close()
    _, status = os.waitpid(child_pid, 0)
    sys.exit(os.waitstatus_to_exitcode(status) if hasattr(os, 'waitstatus_to_exitcode') else 0)
