"""Length-prefixed JSON messages between the Agent (quantagent) and the root broker. Bounded, no objects/pickles."""
import json
import struct

MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 512 * 1024


class ProtocolError(ValueError):
    pass


def send(sock, value, limit):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
    if len(raw) > limit:
        raise ProtocolError('MESSAGE_TOO_LARGE')
    sock.sendall(struct.pack('>I', len(raw)) + raw)


def _exact(sock, n):
    chunks = []
    while n:
        block = sock.recv(min(n, 1 << 16))
        if not block:
            raise EOFError('PEER_CLOSED')
        chunks.append(block)
        n -= len(block)
    return b''.join(chunks)


def receive(sock, limit):
    (size,) = struct.unpack('>I', _exact(sock, 4))
    if size > limit:
        raise ProtocolError('MESSAGE_TOO_LARGE')
    value = json.loads(_exact(sock, size).decode('utf-8'),
                       parse_constant=lambda c: (_ for _ in ()).throw(ProtocolError('NON_FINITE')))
    if not isinstance(value, dict):
        raise ProtocolError('MESSAGE_NOT_OBJECT')
    return value


def check_request(value):
    """Only two operations; the Agent names a study it owns, never a path, definition, date or snapshot."""
    import re
    if value.get('op') == 'status' and set(value) == {'op'}:
        return value
    if (value.get('op') == 'evaluate' and set(value) == {'op', 'study_id', 'artifact_path'}
            and isinstance(value['study_id'], str) and re.fullmatch(r'[0-9a-f]{32}:[0-9a-f]{16}', value['study_id'])
            and isinstance(value['artifact_path'], str) and len(value['artifact_path']) < 512):
        return value
    raise ProtocolError('INVALID_REQUEST')
