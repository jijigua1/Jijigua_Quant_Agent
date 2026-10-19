"""Candidate6 recovery, design D: a 2026 rolling Test is shown only when its receipt equals the broker's registry copy.

Codex C9 audit (receipt_probe.py): with a self-consistent, research-writable revision (analysis, receipt with a
DELIBERATELY INVALID signature, manifest, index) C6/C9 returned a fake COMPLETED Test when the registry variable was
missing, when the registry was writable by the research process, and when evaluation_id was an absolute path.
Positive control: the real in-process broker's receipt (test_v1beta_rolling.three_stage) is still read.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from research_agent.report_versions import latest_report
from research_agent.rolling_client import RollingClient, registered_receipt
from research_agent.security import Denied

SID, EID = "synthetic-study", "0123456789abcdef0123456789abcdef"


def put(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def forged(root, eid=EID):
    """A revision the research process could write itself: every local SHA agrees, the signature is invalid."""
    original, rev = root / "original", root / "revision2"
    metric = {"professional": {"test": {"status": "COMPLETED", "monthly": [], "daily": [], "summary": {"rank_ic_mean": 0.987654}}}}
    a = put(rev / "data/analysis.json", {"metrics": metric, "figure_paths": []})
    receipt = {"result": {"evaluation_type": "ROLLING_EXPOSED_TEST", "study_id": SID, "evaluation_id": eid,
                          "maturity": {"immature_signal_dates": []}}, "signature": "DELIBERATELY_INVALID_SIGNATURE"}
    r = put(rev / "data/test_receipt.json", receipt)
    m = put(rev / "manifest.json", {"study_id": SID, "files": [{"path": "data/analysis.json", "sha256": a},
                                                                {"path": "data/test_receipt.json", "sha256": r}]})
    idx = put(original / "reports/report_versions.json", [{"revision": 1}, {"revision": 2, "rolling_status": "COMPLETED",
              "artifact_path": str(rev), "manifest_sha256": m, "evaluation_id": eid, "html": "x.html", "markdown": "x.md"}])
    put(original / "manifest.json", {"files": [{"path": "reports/report_versions.json", "sha256": idx}]})

    class Artifacts:
        def checked_run(self, p):
            p = Path(p).resolve()
            assert p.is_relative_to(root.resolve())
            return p
    return Artifacts(), original, receipt


def test_no_trusted_registry_means_no_test_result_even_without_the_old_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("QRA_ROLLING_RECEIPTS", raising=False)
    arts, original, _ = forged(tmp_path)
    for client in (None, RollingClient()):
        with pytest.raises(Denied, match="REPORT_RECEIPT_UNVERIFIED"):
            latest_report(arts, original, {"study_id": SID}, client)


def test_an_empty_registry_rejects(tmp_path):
    arts, original, _ = forged(tmp_path)
    (tmp_path / "registry").mkdir()
    with pytest.raises(Denied, match="REPORT_RECEIPT_NOT_REGISTERED"):
        latest_report(arts, original, {"study_id": SID}, RollingClient(receipt_dir=tmp_path / "registry"))


@pytest.mark.skipif(os.name != "posix", reason="registry ownership is a POSIX property (production is Linux)")
def test_a_registry_copy_written_by_the_research_process_itself_is_rejected(tmp_path):
    arts, original, receipt = forged(tmp_path)
    reg = tmp_path / "agent_registry"
    reg.mkdir()
    (reg / (EID + ".json")).write_bytes((tmp_path / "revision2/data/test_receipt.json").read_bytes())
    with pytest.raises(Denied, match="ROLLING_RECEIPT_NOT_BROKER_CONTROLLED"):
        latest_report(arts, original, {"study_id": SID}, RollingClient(receipt_dir=reg))


@pytest.mark.parametrize("eid", ["0" * 64, "../../outside", "/tmp/untrusted_receipt", "ABCDEF0123456789ABCDEF0123456789",
                                 "0123456789abcdef0123456789abcde", "0123456789abcdef0123456789abcdef\n"])
def test_an_evaluation_id_outside_the_broker_syntax_is_rejected_before_any_path(tmp_path, eid):
    arts, original, _ = forged(tmp_path, eid)
    reg = tmp_path / "registry"
    reg.mkdir()
    with pytest.raises(Denied, match="REPORT_RECEIPT_ID"):
        latest_report(arts, original, {"study_id": SID}, RollingClient(receipt_dir=reg))
    with pytest.raises(Denied, match="ROLLING_RECEIPT_ID"):
        registered_receipt(reg, eid)


def test_a_registry_copy_that_differs_from_the_studys_receipt_is_rejected(tmp_path):
    arts, original, receipt = forged(tmp_path)
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / (EID + ".json")).write_text(json.dumps(dict(receipt, signature="the broker's real signature")), encoding="utf-8")
    client = RollingClient(receipt_dir=reg, require_foreign_owner=False)          # engineering client: ownership relaxed
    with pytest.raises(Denied, match="REPORT_RECEIPT_NOT_REGISTERED"):
        latest_report(arts, original, {"study_id": SID}, client)


def test_the_real_brokers_receipt_is_still_read(tmp_path):
    """The positive control: the synthetic in-process broker of test_v1beta_rolling issues and registers a receipt; the
    study's report is read through the backend's own client."""
    from v1beta_fixtures import REVERSAL, TRAIN, broker, build, context
    from test_v1beta_stage2_access import readable
    from research_agent.data import ResourceCatalog
    from research_agent.quant import QuantBackend
    fx = build(tmp_path)
    backend = QuantBackend(ResourceCatalog(fx["manifest"]), fx["config"])
    client, _ = broker(fx)
    backend.rolling = client
    result = backend.expression_study(TRAIN, REVERSAL, "短期反转", "合成工程验收", 5, 5, "raw", context())
    readable(backend, result)
    out = backend.read_study(TRAIN, result["study_id"], context())
    assert out["metrics"]["professional"]["test"]["status"] == "COMPLETED"
    backend.rolling = RollingClient()                                         # the same study read without a registry
    with pytest.raises(Denied, match="REPORT_RECEIPT_UNVERIFIED"):
        backend.read_study(TRAIN, result["study_id"], context())
