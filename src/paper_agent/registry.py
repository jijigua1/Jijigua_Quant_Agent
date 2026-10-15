"""Human approval of an exact candidate, post-approval known-truth tests, and the trusted implementation registry.

Flow:  READY_FOR_REVIEW candidate  ->  request (no execution)
       -> human types "APPROVE <first 12 hex of the source SHA-256>" in the CLI (program-checked; the model has no
          approval tool and cannot write approval records)
       -> approval record (write-once file, exact SHA-256, approver channel, time)
       -> the approved source is run ONLY on the stored synthetic test fixtures (expected values from the trusted
          reference evaluator); any failure -> REJECTED_AFTER_TESTS, never registered
       -> TRUSTED_REGISTERED entry; loads verify the source hash, the approval and the passed tests every time.

This is a review-and-registration mechanism, not a sandbox: approved code runs in the Agent's own (non-root) process
with the Agent's permissions. Execution is refused as root and for any source whose hash has no approval.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .ledger import canonical, sha256_text


class RegistryError(RuntimeError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def approval_phrase(source_sha256):
    return f"APPROVE {source_sha256[:12]}"


def _frame(js):
    idx = pd.to_datetime(js["index"])
    return pd.DataFrame(np.array([[np.nan if v is None else v for v in row] for row in js["values"]], dtype=float),
                        index=idx, columns=js["columns"])


def _close(a, b, tol):
    if a.shape != b.shape or list(a.columns) != list(b.columns) or not a.index.equals(b.index):
        return False
    x, y = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
    return bool(np.allclose(x, y, rtol=tol.get("rel", 1e-9), atol=tol.get("abs", 1e-9), equal_nan=True))


class TrustedRegistry:
    def __init__(self, root, channels=("cli_human_input",)):
        self.root = Path(root)
        self.channels = tuple(channels)          # the acceptance registry accepts only the CLI human-input channel
        for d in ("requests", "approvals", "sources", "entries"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- review request (no execution)
    def request(self, candidate, *, task_id, plan_sha256, bundle_dir):
        src = candidate["files"]["candidate.py"]
        sha = sha256_text(src)
        if candidate["status"] != "READY_FOR_REVIEW":
            raise RegistryError("NOT_REVIEWABLE", candidate["status"])
        rec = {"source_sha256": sha, "candidate_id": candidate["manifest"]["candidate_id"], "task_id": task_id,
               "plan_definition_sha256": plan_sha256, "bundle_dir": str(bundle_dir), "origin": candidate["manifest"]["origin"],
               "tests_sha256": sha256_text(json.dumps(candidate["tests"], sort_keys=True, default=str)),
               "contract_sha256": sha256_text(canonical(candidate["contract"])), "static_analysis_passed": candidate["analysis"]["passed"],
               "requested_at": datetime.now().astimezone().isoformat(), "phrase": approval_phrase(sha)}
        (self.root / "sources" / f"{sha}.py.txt").write_text(src, encoding="utf-8")
        (self.root / "requests" / f"{sha}.json").write_text(json.dumps(rec | {"tests": candidate["tests"], "contract": candidate["contract"]},
                                                                       default=str), encoding="utf-8")
        return rec

    # ---------------------------------------------------------------- human approval
    def approve(self, typed_text, *, channel, approver, user_words=None):
        """`typed_text` must be the user's own input line; `channel` must be the CLI human-input channel."""
        if channel not in self.channels:
            raise RegistryError("APPROVAL_CHANNEL_DENIED", channel)
        text = typed_text.strip()
        matches = [p for p in (self.root / "requests").glob("*.json") if approval_phrase(p.stem) == text]
        if len(matches) != 1:
            raise RegistryError("APPROVAL_PHRASE_UNKNOWN", text[:40])
        sha = matches[0].stem
        req = json.loads(matches[0].read_text(encoding="utf-8"))
        src = (self.root / "sources" / f"{sha}.py.txt").read_text(encoding="utf-8")
        if sha256_text(src) != sha:
            raise RegistryError("SOURCE_TAMPERED", sha)
        rec = {"source_sha256": sha, "approved_text": text, "channel": channel, "approver": approver,
               "user_words": (user_words or text)[:500],
               "approved_at": datetime.now().astimezone().isoformat(), "task_id": req["task_id"],
               "plan_definition_sha256": req["plan_definition_sha256"]}
        path = self.root / "approvals" / f"{sha}.json"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError:
            raise RegistryError("ALREADY_APPROVED", sha[:12]) from None
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rec))
        return rec

    # ---------------------------------------------------------------- post-approval tests and registration
    def _load_module(self, sha):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            raise RegistryError("ROOT_EXECUTION_REFUSED", "approved implementations never run as root")
        if not (self.root / "approvals" / f"{sha}.json").exists():
            raise RegistryError("NOT_APPROVED", sha[:12])
        src = (self.root / "sources" / f"{sha}.py.txt").read_text(encoding="utf-8")
        if sha256_text(src) != sha:
            raise RegistryError("SOURCE_TAMPERED", sha[:12])
        namespace = {"__name__": f"approved_{sha[:12]}"}
        exec(compile(src, f"<approved {sha[:12]}>", "exec"), namespace)   # noqa: S102 -- human-approved exact hash only
        if not callable(namespace.get("compute")):
            raise RegistryError("NO_ENTRYPOINT", sha[:12])
        return namespace

    def _load_compute(self, sha):
        return self._load_module(sha)["compute"]

    def _run_pair_tests(self, sha, spec):
        """compute() vs the independently written reference() on stored fixtures, a perturbed future, a missing input and a
        zero; both must be causal and agree cell by cell (NaN pattern included)."""
        ns = self._load_module(sha)
        fn, ref = ns["compute"], ns.get("reference")
        if not callable(ref):
            raise RegistryError("NO_ENTRYPOINT", "reference() missing")

        def run(f, panels):
            out = f({k: v.copy() for k, v in panels.items()})
            if not isinstance(out, pd.DataFrame):
                raise RegistryError("NOT_A_FRAME", type(out).__name__)
            return out.astype(float).replace([np.inf, -np.inf], np.nan)
        tol = {"abs": 1e-9, "rel": 1e-9}
        results = []
        try:
            for case in spec["cases"]:
                base = {k: _frame(v) for k, v in case["inputs"].items()}
                a, b = run(fn, base), run(ref, base)
                results.append({"name": case["name"], "passed": _close(a, b, tol)})
                results.append({"name": case["name"] + "_shape", "passed": a.index.equals(base[next(iter(base))].index)
                                and list(a.columns) == list(base[next(iter(base))].columns)})
                k = spec["warmup_rows"]
                results.append({"name": case["name"] + "_warmup_nan", "passed": bool(b.iloc[:k].isna().all().all()) and bool(b.iloc[k:].notna().any().any())})
                cut = a.index[spec["perturb_after_row"]]
                pert = {kk: v.copy() for kk, v in base.items()}
                for v in pert.values():
                    v.loc[v.index > cut] = v.loc[v.index > cut] * 1.7 + 0.3
                results.append({"name": case["name"] + "_no_lookahead", "passed": _close(run(fn, pert).loc[:cut], a.loc[:cut], tol)
                                and _close(run(ref, pert).loc[:cut], b.loc[:cut], tol)})
                for key, value in (("set_nan", np.nan), ("set_zero", 0.0)):
                    m = {kk: v.copy() for kk, v in base.items()}
                    s = spec[key]
                    m[s["field"]].iloc[s["row"], s["column"]] = value
                    results.append({"name": case["name"] + "_" + key, "passed": _close(run(fn, m), run(ref, m), tol)})
        except RegistryError:
            raise
        except Exception as e:  # noqa: BLE001 -- a crash is a failed test, recorded with its type
            results.append({"name": "execution", "passed": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        return results

    def load_reference(self, implementation_id):
        entry, _ = self.load(implementation_id)
        ref = self._load_module(entry["source_sha256"]).get("reference")
        if not callable(ref):
            raise RegistryError("NO_ENTRYPOINT", "reference() missing")
        return ref

    def run_tests(self, sha):
        req = json.loads((self.root / "requests" / f"{sha}.json").read_text(encoding="utf-8"))
        if (req.get("tests") or {}).get("mode") == "pair":
            return self._run_pair_tests(sha, req["tests"])
        fn = self._load_compute(sha)
        results = []
        cases = {c["name"]: c for c in req["tests"]["cases"]}
        ref = cases["reference_values"]
        base = {k: _frame(v) for k, v in ref["inputs"].items()}
        expected = _frame(ref["expected"])

        def run(panels):
            out = fn({k: v.copy() for k, v in panels.items()})
            if not isinstance(out, pd.DataFrame):
                raise RegistryError("NOT_A_FRAME", type(out).__name__)
            return out.replace([np.inf, -np.inf], np.nan)
        try:
            got = run(base)
            results.append({"name": "reference_values", "passed": _close(got, expected, ref["tolerance"])})
            k = cases["warmup_rows_are_nan"]["expected_nan_rows"]
            results.append({"name": "warmup_rows_are_nan", "passed": bool(got.iloc[:k].isna().all().all()) and bool(got.iloc[k:].notna().any().any())})
            results.append({"name": "shape_and_alignment", "passed": got.index.equals(expected.index) and list(got.columns) == list(expected.columns)})
            c = cases["no_lookahead_perturbation"]
            cut = pd.Timestamp(c["perturb"]["rows_after"])
            pert = {k2: v.copy() for k2, v in base.items()}
            for v in pert.values():
                v.loc[v.index > cut] = v.loc[v.index > cut] * c["perturb"]["multiply"]
            gp = run(pert)
            results.append({"name": "no_lookahead_perturbation", "passed": _close(gp.loc[:cut], expected.loc[:cut], {"abs": 1e-9, "rel": 1e-9})})
            c = cases["missing_input_propagates"]
            miss = {k2: v.copy() for k2, v in base.items()}
            miss[c["set_nan"]["field"]].loc[pd.Timestamp(c["set_nan"]["row"]), c["set_nan"]["column"]] = np.nan
            results.append({"name": "missing_input_propagates", "passed": _close(run(miss), _frame(c["expected"]), {"abs": 1e-9, "rel": 1e-9})})
            if "zero_denominator_is_nan" in cases:
                c = cases["zero_denominator_is_nan"]
                z = {k2: v.copy() for k2, v in base.items()}
                z[c["set_zero"]["field"]].loc[pd.Timestamp(c["set_zero"]["row"]), c["set_zero"]["column"]] = 0.0
                results.append({"name": "zero_denominator_is_nan", "passed": _close(run(z), _frame(c["expected"]), {"abs": 1e-9, "rel": 1e-9})})
        except RegistryError:
            raise
        except Exception as e:  # noqa: BLE001 -- a crash is a failed test, recorded with its type
            results.append({"name": "execution", "passed": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        return results

    def register(self, sha):
        """Run the known-truth tests (allowed only after approval) and register on success."""
        results = self.run_tests(sha)
        approval = json.loads((self.root / "approvals" / f"{sha}.json").read_text(encoding="utf-8"))
        req = json.loads((self.root / "requests" / f"{sha}.json").read_text(encoding="utf-8"))
        ok = bool(results) and all(r["passed"] for r in results)
        entry = {"implementation_id": f"approved_{sha[:12]}", "source_sha256": sha, "status": "TRUSTED_REGISTERED" if ok else "REJECTED_AFTER_TESTS",
                 "approval": approval, "tests": results, "contract": req["contract"], "origin": req["origin"],
                 "task_id": req["task_id"], "plan_definition_sha256": req["plan_definition_sha256"],
                 "registered_at": datetime.now().astimezone().isoformat(),
                 "boundary": "human-approved code run in the Agent process (non-root); not a sandbox"}
        (self.root / "entries" / f"{sha}.json").write_text(json.dumps(entry, default=str, indent=1), encoding="utf-8")
        if not ok:
            raise RegistryError("REJECTED_AFTER_TESTS", json.dumps([r for r in results if not r["passed"]])[:300])
        return entry

    def registered(self, source_sha256):
        """The registry entry for an exact source hash, if it was approved and passed its tests."""
        p = self.root / "entries" / f"{source_sha256}.json"
        if not p.exists():
            return None
        entry = json.loads(p.read_text(encoding="utf-8"))
        return entry if entry["status"] == "TRUSTED_REGISTERED" else None

    def load(self, implementation_id):
        sha_prefix = implementation_id.replace("approved_", "")
        files = [p for p in (self.root / "entries").glob(f"{sha_prefix}*.json")]
        if len(files) != 1:
            raise RegistryError("NOT_REGISTERED", implementation_id)
        entry = json.loads(files[0].read_text(encoding="utf-8"))
        if entry["status"] != "TRUSTED_REGISTERED":
            raise RegistryError("NOT_REGISTERED", entry["status"])
        return entry, self._load_compute(entry["source_sha256"])
