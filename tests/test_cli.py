import json
import os

import pytest

from research_agent.cli import main


def test_cli_create_run_status_result_and_logs(tmp_path, capsys):
    base = ["--state-dir", str(tmp_path)]
    assert main(base + ["create", "查询模拟量价数据"]) == 0
    task = json.loads(capsys.readouterr().out)["task_id"]
    assert main(base + ["run", task, "--max-steps", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PAUSED"
    assert main(base + ["run", task]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETED"
    assert main(base + ["status", task]) == 0
    assert json.loads(capsys.readouterr().out)["counters"]["tool_calls"] == 3
    assert main(base + ["result", task]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "synthetic"
    assert main(base + ["logs", task]) == 0
    assert json.loads(capsys.readouterr().out)[0]["kind"] == "AUTHORIZATION_ISSUED"


def test_cli_demo_alt_provider(tmp_path, capsys):
    assert main(["--state-dir", str(tmp_path), "--provider", "mock_alt", "demo"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "COMPLETED" and value["mode"] == "synthetic"


def test_cli_invalid_task_returns_error(tmp_path, capsys):
    assert main(["--state-dir", str(tmp_path), "status", "../bad"]) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "INVALID_TASK_ID"


def test_cli_budget_failure_has_nonzero_exit(tmp_path, capsys):
    base = ["--state-dir", str(tmp_path)]
    main(base + ["create", "mock", "--max-model-calls", "1"])
    task = json.loads(capsys.readouterr().out)["task_id"]
    assert main(base + ["run", task]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BUDGET_EXHAUSTED"


def test_cli_chat_is_explicitly_mock(tmp_path, monkeypatch, capsys):
    inputs = iter(["研究模拟量价指标", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    assert main(["--state-dir", str(tmp_path), "chat"]) == 0
    output = capsys.readouterr().out
    assert "离线 Mock" in output and '"mode":"synthetic"' in output


@pytest.mark.parametrize("command", ["status", "logs", "result", "demo", "chat"])
def test_cli_root_refused_before_any_state_access(tmp_path, monkeypatch, capsys, command):
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    directory = tmp_path / "must_not_exist"
    arguments = ["--state-dir", str(directory), command]
    if command in {"status", "logs", "result"}:
        arguments.append("0" * 32)
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "ROOT_AGENT_DENIED"
    assert not directory.exists()
