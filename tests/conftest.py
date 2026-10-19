from dataclasses import replace
import hashlib
from pathlib import Path
import socket

import pytest

from research_agent.app import RESOURCES, build, load_policy
from research_agent.contracts import canonical, parse_json
from research_agent.skills import FILES, SkillRegistry
from research_agent.tools import mock_registry


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network is forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(scope='session')
def public_client_pdfs(tmp_path_factory):
    """Original tiny PDFs for transport checks, never substitutes for real-paper semantic replays."""
    import fitz
    root = tmp_path_factory.mktemp('original_public_client_pdfs')
    for name, title in [('amihud2002.pdf','Synthetic upload fixture A'), ('gh4-paper.pdf','Synthetic upload fixture B')]:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72,72),title + '\nOriginal engineering content. Not an academic paper.')
        doc.save(root/name)
        doc.close()
    return root


@pytest.fixture(autouse=True)
def public_client_inputs(request, monkeypatch):
    if request.module.__name__ in {'test_v1beta_quant_paper','test_v1beta_client_crossplatform','test_v1beta_upload_batch'}:
        monkeypatch.setattr(request.module,'FIX',request.getfixturevalue('public_client_pdfs'))


@pytest.fixture
def app(tmp_path):
    return build(tmp_path / "state")


@pytest.fixture
def skill_copy(tmp_path):
    root = tmp_path / "skills"
    target = root / "mock_research"
    target.mkdir(parents=True)
    for name in FILES:
        (target / name).write_bytes((RESOURCES / "skills" / "mock_research" / name).read_bytes())

    def reviewed_registry(policy=None):
        # Test-only publisher simulation. Runtime never auto-approves changed files.
        manifest = {"mock_research": {n: hashlib.sha256((target / n).read_bytes()).hexdigest() for n in FILES}}
        return SkillRegistry(root, manifest, mock_registry(), policy or load_policy())

    return target, reviewed_registry


@pytest.fixture
def amihud_250_carrier(monkeypatch):
    """C6R4 (records/TEST_CHANGES_CN.md): flow tests (gates, approvals, frozen definitions, planner arithmetic) that use the
    recorded Amihud reading with a fixed 250-day window only as a runnable carrier. The calendar-window check, which now
    blocks that reading, is switched off in them alone; its behaviour is covered by tests/test_recovery_c6r4.py."""
    import re
    from paper_agent import reconcile
    monkeypatch.setattr(reconcile, "CALENDAR_COUNT", re.compile(r"(?!x)x"))
