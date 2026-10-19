import io

import pytest

from research_agent.cli import check_connection, prompt_credential
from research_agent.security import Denied
from test_provider_contract import adapter, wire

KEY = 'sk-' + 'a' * 32


def test_hidden_key_rejects_paste_errors_and_trims_edges(monkeypatch, capsys):
    attempts = iter(['Bearer ' + KEY, '"' + KEY + '"', 'sk-' + 'a b' * 12, '  ' + KEY + '\t'])
    monkeypatch.setattr('research_agent.cli.getpass.getpass', lambda _: next(attempts))
    assert prompt_credential() == KEY
    out = capsys.readouterr().out
    assert out.count('格式检查失败') == 3
    assert '35 个字符' in out and '已去掉首尾空白' in out
    assert KEY not in out


def test_visible_key_requires_local_terminal(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO(KEY))
    with pytest.raises(Denied, match='VISIBLE_KEY_REQUIRES_TERMINAL'):
        prompt_credential(True)


def test_visible_confirmation_clears_screen_before_status(monkeypatch, capsys):
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    attempts = iter([KEY, ''])
    monkeypatch.setattr('builtins.input', lambda _: next(attempts))
    assert prompt_credential(True) == KEY
    out = capsys.readouterr().out
    assert out.startswith('\x1b[2J\x1b[3J\x1b[H')
    assert KEY not in out


def test_minimal_check_uses_same_adapter_and_cumulative_budget(tmp_path, monkeypatch, capsys):
    from research_agent.api_budget import create_campaign
    path = tmp_path / 'budget.sqlite3'
    create_campaign(path, 'diagnostic', max_requests=2, max_tokens=50000)
    monkeypatch.setenv('QRA_API_BUDGET_DB', str(path))
    monkeypatch.setenv('QRA_API_BUDGET_CAMPAIGN', 'diagnostic')
    provider, transport = adapter([wire({'content': 'OK'}, usage={'prompt_tokens': 8, 'completion_tokens': 1, 'total_tokens': 9})])
    assert check_connection(provider)
    assert len(transport.requests) == 1
    payload = transport.requests[0][0]
    assert payload['max_tokens'] == 32
    assert 'response_format' not in payload and 'tools' not in payload
    assert provider.budget.state()['used_requests'] == 1
    assert 'PASSED' in capsys.readouterr().out
