"""Phase 3-A research-facing split prototype; no holdout evaluation endpoint exists yet."""

import hashlib
import json
from datetime import datetime

from .adapter import Refused


CONTRACT_VERSION = "qra-split/1.0.0"
SAFE_RAW_FIELDS = frozenset({"open", "high", "low", "close", "volume", "amount"})
SAFE_SPLITS = {"train": ("20200101", "20231231"),
               "validation": ("20240101", "20251231"),
               "holdout": ("20260101", "20261009")}
SAFE_ACCESS = {"train": {"read_exploratory", "NOT_PUBLISHED"},
               "validation": {"read_exploratory", "NOT_PUBLISHED"}, "holdout": {"DENIED"}}


def manifest_digest(manifest):
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _date_ok(value):
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


class SplitReader:
    """Limit an existing pinned reader to exploratory train/validation raw data.

    The caller identity and contract must be supplied by trusted code, never by a model.
    shortcut: this is an API gate, not process/filesystem isolation; publish separate
    read-only train/validation snapshots before connecting it to an Agent.
    """

    def __init__(self, reader, contract, *, role, audit):
        if contract.get("version") != CONTRACT_VERSION or role != "research_agent" or not callable(audit):
            raise Refused("INVALID_SPLIT_CONTRACT")
        if (set(contract.get("splits", {})) != set(SAFE_SPLITS) or
                any((contract["splits"][name].get("start"), contract["splits"][name].get("end")) != bounds or
                    contract["splits"][name].get("version") != "1.0.0" or
                    contract["splits"][name].get("research_api") not in SAFE_ACCESS[name] or
                    (name != "holdout" and
                     (contract["splits"][name].get("publication_status") == "PUBLISHED") !=
                     (contract["splits"][name].get("research_api") == "read_exploratory"))
                    for name, bounds in SAFE_SPLITS.items()) or
                contract["splits"]["holdout"].get("evaluation_api", "NOT_IMPLEMENTED") != "NOT_IMPLEMENTED"):
            raise Refused("INVALID_SPLIT_CONTRACT")
        if (contract.get("resource_id") != "daily_update_core" or
                contract.get("status") != "PROFILED_EXPLORATORY_ONLY" or
                not set(contract.get("exploratory_fields", [])) <= SAFE_RAW_FIELDS or
                contract.get("source_manifest_sha256") != manifest_digest(reader.manifest)):
            raise Refused("INVALID_SPLIT_CONTRACT")
        self.reader, self.contract, self.role, self.audit = reader, contract, role, audit

    def read(self, split, fields, start, end, *, codes=None):
        event = {"role": self.role, "split": split if isinstance(split, str) else None,
                 "fields": fields if isinstance(fields, (list, tuple)) else [],
                 "start": start, "end": end}
        try:
            if not isinstance(split, str):
                raise Refused("UNKNOWN_SPLIT")
            if split == "holdout":
                raise Refused("HOLDOUT_NOT_PUBLISHED")
            spec = self.contract["splits"].get(split)
            if spec is None:
                raise Refused("UNKNOWN_SPLIT")
            if spec.get("publication_status") != "PUBLISHED":
                raise Refused("SPLIT_RESOURCE_NOT_PUBLISHED")
            if manifest_digest(self.reader.manifest) != self.contract["source_manifest_sha256"]:
                raise Refused("SOURCE_MANIFEST_CHANGED")
            if not all(_date_ok(d) for d in (start, end)):
                raise Refused("INVALID_DATE")
            if not spec["start"] <= start <= end <= spec["end"]:
                raise Refused("CROSS_SPLIT_OR_OUTSIDE_SCOPE")
            if (not isinstance(fields, (list, tuple)) or not fields or
                    any(not isinstance(name, str) for name in fields) or
                    len(fields) != len(set(fields)) or not set(fields) <= set(self.contract["exploratory_fields"])):
                raise Refused("FIELD_NOT_EXPLORATORY")
            if codes is not None and (not isinstance(codes, (list, tuple)) or
                                      any(not isinstance(code, str) for code in codes)):
                raise Refused("INVALID_CODES")
            resource_id = spec.get("resource_id")
            dataset = self.reader.manifest["datasets"].get(resource_id)
            if resource_id == self.contract["resource_id"] or dataset is None:
                raise Refused("UNPARTITIONED_SOURCE")
            scope = dataset.get("certification", {})
            original = self.reader.manifest["datasets"][self.contract["resource_id"]]["fields"]
            if (scope.get("start", "") < spec["start"] or scope.get("end", "99999999") > spec["end"] or
                    any(dataset["fields"].get(name, {}).get("sha256") == original.get(name, {}).get("sha256")
                        for name in fields)):
                raise Refused("UNPARTITIONED_SOURCE")
            result = self.reader.read(resource_id, fields, start, end,
                                      codes=codes, purpose="profile")
            if not result.dates:
                raise Refused("NO_TRADING_DAYS")
            for item in result.provenance:
                item["source_manifest_claim"] = item.pop("certification")
                item["split_certification"] = "PROFILED_EXPLORATORY_ONLY"
                item["split_contract"] = CONTRACT_VERSION
            result.warnings.append({"scope": "exploratory factor research only; no formal backtest or holdout"})
            event.update(outcome="ALLOWED", rows=len(result.dates), columns=len(result.codes))
            return result
        except Refused as exc:
            event.update(outcome="DENIED", reason=exc.code)
            raise
        finally:
            self.audit(event)

    def eligible_signal_dates(self, split, sessions, *, lookback, execution_lag, holding_days, embargo=0):
        """Only labels fully matured inside a partition are eligible; no cross-boundary labels."""
        if split == "holdout":
            raise Refused("HOLDOUT_NOT_PUBLISHED")
        spec = self.contract["splits"].get(split)
        if spec is None:
            raise Refused("UNKNOWN_SPLIT")
        if (not sessions or sessions != sorted(set(sessions)) or
                sessions[0] < spec["start"] or sessions[-1] > spec["end"]):
            raise Refused("CROSS_SPLIT_OR_OUTSIDE_SCOPE")
        if any(type(n) is not int or n < minimum for n, minimum in
               ((lookback, 1), (execution_lag, 1), (holding_days, 1), (embargo, 0))):
            raise Refused("INVALID_LABEL_PARAMETERS")
        stop = len(sessions) - execution_lag - holding_days - embargo
        return sessions[lookback - 1:max(lookback - 1, stop)]
