import io
import gzip
import json
import urllib.error

import pytest

from research_agent.llm import ModelError
from research_agent.providers.deepseek import HTTPTransport


@pytest.mark.parametrize('body,expected', [
    (json.dumps({'error': {'message': 'Last message must be user. Bearer secret-canary sk-test-hidden'}}).encode(),
     'Last message must be user. [REDACTED] [REDACTED]'),
    (b'not-json secret-canary', 'not-json [REDACTED]'),
    (json.dumps({'error': 'Bad message order sk-test-hidden'}).encode(), 'Bad message order [REDACTED]'),
    (gzip.compress(b'{"error":{"message":"Invalid request secret-canary"}}'), 'Invalid request [REDACTED]'),
    (gzip.compress(b'x' * 20000), None),
    (b'x' * 16385, None),
    (b'[]', None),
], ids=['json_redacted', 'plain_redacted', 'string_error', 'gzip_error', 'gzip_oversize', 'raw_oversize', 'non_object'])
def test_http_error_diagnostic_is_bounded_and_redacted(monkeypatch, body, expected):
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 400, 'Bad Request', {}, io.BytesIO(body))
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    with pytest.raises(ModelError) as caught:
        list(HTTPTransport(allow_live=True).send({}, {'Authorization': 'Bearer secret-canary'}, 10, False))
    assert caught.value.http_status == 400
    assert not caught.value.retryable
    assert caught.value.provider_detail == expected
    assert 'secret-canary' not in str(vars(caught.value))
    assert 'sk-test-hidden' not in str(vars(caught.value))
