"""Agent side of ROLLING_EXPOSED_TEST. Holds no 2026 file, path, FD or key; only an inherited socket to the broker.

The broker returns a receipt path inside the root-owned receipt registry; a receipt is accepted only if the registry
copy is a single-link regular file not writable by this process' user, and its bytes parse to the expected study.
"""
import hashlib
import json
import os
import re
import socket
import stat
from pathlib import Path

from .security import Denied

# the broker's evaluation ids: uuid4().hex or a sha256 prefix of 32 characters (rolling_test/evaluator.py)
EVALUATION_ID = re.compile(r'[0-9a-f]{32}')

ENV_FD = 'QRA_ROLLING_FD'
ENV_RECEIPTS = 'QRA_ROLLING_RECEIPTS'


class RollingClient:
    def __init__(self, sock=None, receipt_dir=None, *, require_foreign_owner=True):
        self.sock, self.receipt_dir = sock, Path(receipt_dir) if receipt_dir else None
        # Production: the registry copy must belong to the root broker. Only in-process engineering tests relax this.
        self.require_foreign_owner = require_foreign_owner

    @classmethod
    def from_environment(cls):
        fd = os.environ.get(ENV_FD)
        receipts = os.environ.get(ENV_RECEIPTS)
        if not fd or not receipts or not fd.isdigit():
            return cls()
        return cls(socket.socket(fileno=int(fd)), receipts)

    @property
    def available(self):
        return self.sock is not None and self.receipt_dir is not None

    def _call(self, request):
        from rolling_test.protocol import MAX_REQUEST, MAX_RESPONSE, receive, send
        send(self.sock, request, MAX_REQUEST)
        return receive(self.sock, MAX_RESPONSE)

    def status(self):
        if not self.available:
            return dict(status='NOT_EVALUATED', reason='EVALUATOR_UNAVAILABLE')
        return self._call({'op': 'status'})

    def evaluate(self, study_id, artifact_path):
        if not self.available:
            return dict(status='NOT_EVALUATED', reason='EVALUATOR_UNAVAILABLE',
                        detail='no rolling evaluation broker in this process')
        try:
            answer = self._call({'op': 'evaluate', 'study_id': study_id, 'artifact_path': str(artifact_path)})
        except (OSError, EOFError, ValueError) as exc:
            return dict(status='NOT_EVALUATED', reason='EVALUATOR_UNAVAILABLE', detail=type(exc).__name__)
        if answer.get('status') != 'COMPLETED':
            return answer
        answer['receipt'] = self.load_receipt(answer['receipt_path'], study_id)
        return answer

    def load_receipt(self, path, study_id):
        path = Path(path)
        if self.receipt_dir is None or path.parent != self.receipt_dir or path.is_symlink():
            raise Denied('ROLLING_RECEIPT_OUTSIDE_REGISTRY')
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > 512 * 1024:
            raise Denied('ROLLING_RECEIPT_FILE')
        if os.name == 'posix' and self.require_foreign_owner and (st.st_uid == os.geteuid() or st.st_mode & 0o022):
            raise Denied('ROLLING_RECEIPT_NOT_BROKER_CONTROLLED')
        raw = path.read_bytes()
        receipt = json.loads(raw)
        result = receipt['result']
        if result['study_id'] != study_id or result['evaluation_type'] != 'ROLLING_EXPOSED_TEST':
            raise Denied('ROLLING_RECEIPT_STUDY')
        receipt['registry_sha256'] = hashlib.sha256(raw).hexdigest()
        return receipt


def registered_receipt(receipt_dir, evaluation_id):
    """Re-read a registered receipt by its broker id (32 lower-case hex) inside the registry directory only."""
    if not isinstance(evaluation_id, str) or not EVALUATION_ID.fullmatch(evaluation_id):
        raise Denied('ROLLING_RECEIPT_ID')
    directory = Path(receipt_dir)
    path = directory / (evaluation_id + '.json')
    if path.parent != directory or path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise Denied('ROLLING_RECEIPT_NOT_REGISTERED')
    return path.read_bytes()
