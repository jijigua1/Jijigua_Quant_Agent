"""Old vs new paper-understanding flow on the same papers and the same user words (pre-release staging only).

Each case runs: library resolution of the user's words -> evidence -> the reader (real DeepSeek, the Agent's own adapter
and contracts) -> deterministic verification -> research plan. Nothing is computed, no study is written, the 2026 Test
is never touched. Each flow runs in its own process with its own source tree and its own scratch ledger/cache.

usage (on the staging host):
  python tools/paper_ab.py drive --old <old src> --new <new src> --library <papers root> --out <dir> [--cases dev,exposed,holdout2]
      asks once for the DeepSeek key (not echoed, never written), runs both flows, writes results_*.json and compare.md
  python tools/paper_ab.py run --label new --library <papers root> --out <dir> --cases dev   (child; key from the environment)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

# expected outcome per case (written before the run from the dev papers; holdout cases are judged after the run, by hand)
#   ready: a plan awaiting the user's decision whose executed formula matches `formula` (regex) and parameters `params`
#   block: a blocked plan (or a consent request) whose reasons include one of `codes` / an asset decision in `assets`
CASES = {
    "dev": [
        dict(id="D01", request="研究AQR那篇趋势跟踪论文的因子", file="AQR", expect="block", assets=["ASSET_CLASS_NOT_AVAILABLE"]),
        dict(id="D02", request="研究MACD那篇论文的MACD因子", file="2206.12282", expect="ready", factor="MACD",
             formula=r"ema\[N=12.*ema\[N=26|ema\}?_\{12\}.*ema\}?_\{26\}"),
        dict(id="D03", request="研究1110.3383那篇技术指标论文里的RSI因子", file="1110.3383", expect="block", factor="RSI",
             codes=["FREE_PARAMETER_UNBOUND", "PARAMETER_VALUE_UNVERIFIED", "FORMULA_UNPARSEABLE", "DERIVATION_UNPARSEABLE"],
             note="论文只写“X days”，没有给出 X；编造 14 属于错误"),
        dict(id="D03u", request="研究1110.3383那篇技术指标论文里的RSI因子，X=14", file="1110.3383", expect="ready", factor="RSI", formula=r"13|14",
             note="用户给出 X=14 后应可研究（参数记为用户指定）"),
        dict(id="D04", request="研究0212641那篇成交量风险论文里的经典动量指标CMI", file="0212641", expect="ready", factor="CMI", formula=r"\b2[01]\b",
             note="τ=21 在原文图注中给出"),
        dict(id="D05", request="研究0212641那篇成交量风险论文里的广义动量指标GMI", file="0212641", expect="manual", factor="GMI",
             note="m(t) 的定义在公式块中，文本层可能残缺"),
        dict(id="D06", request="研究moving average（移动平均）那篇论文的因子", file="ferreira", expect="block",
             assets=["ASSET_CLASS_NOT_AVAILABLE"], codes=["FREE_PARAMETER_UNBOUND", "CONSTANT_WITHOUT_SOURCE", "LOG_RETURN_READ_AS_SIMPLE"],
             note="论文只研究股票指数（需资产同意）；N 是扫描的自由参数"),
        dict(id="D07", request="研究Heston那篇期权动量论文的因子", file="HESTON", expect="block", assets=["ASSET_CLASS_NOT_AVAILABLE"]),
        dict(id="D08", request="研究华泰那份量化月报里的因子", file="华泰", expect="block",
             codes=["FIELD_NOT_IN_PANEL", "SYMBOL_UNDEFINED", "FIELD_MAPPING_UNSUPPORTED", "FORMULA_NOT_ESTABLISHED"],
             assets=["ASSET_CLASS_NOT_AVAILABLE"], note="PE_TTM 不在已发布行情中，择时对象为指数"),
        dict(id="D09", request="研究George和Hwang那篇52周最高价论文的因子", file="gh4", expect="ready", formula=r"max|252|251|250"),
        dict(id="D10", request="研究Amihud那篇非流动性论文的因子", file="amihud", expect="ready", formula=r"amount|volume"),
    ],
    "exposed": [dict(id=f"E{i:02d}", request=f"研究{n}那篇论文的因子", file=f, expect="manual") for i, (n, f) in enumerate([
        ("长城证券技术指标叠加", "greatwall"), ("湘财ETF趋势跟踪", "xiangcai"), ("hans择时", "hans"), ("CN03", "CN03"), ("CN12", "CN12"),
        ("CORE04", "CORE04"), ("CORE09", "CORE09"), ("CORE17", "CORE17"), ("ML03", "ML03"), ("ROOT08", "ROOT08")], 1)],
    "holdout2": [dict(id="N01", request="研究101 Formulaic Alphas那篇论文里的Alpha#12", file="alpha101", expect="manual", factor="Alpha#12"),
                 dict(id="N02", request="研究CN04那篇论文的因子", file="CN04", expect="manual"),
                 dict(id="N03", request="研究CORE05那篇论文的因子", file="CORE05", expect="manual"),
                 dict(id="N04", request="研究ML08那篇论文的因子", file="ML08", expect="manual"),
                 dict(id="N05", request="研究ROOT11那篇论文的因子", file="ROOT11", expect="manual")],
}
PROFILE = {"fields": ["open", "high", "low", "close", "volume", "amount"], "train_rows_estimate": 960,
           "status": "PROFILED_EXPLORATORY_ONLY", "adjustment": "none (raw unadjusted market prices)",
           "units": {"volume": "lots (100 shares)", "amount": "thousand CNY"},
           "splits": {"train": ["2020-01-02", "2023-12-29"], "valid": ["2024-01-02", "2025-12-31"], "test": ["2026-01-01", "2026-12-31"]},
           "holdout": "2026 evaluated only by the controlled rolling evaluator (aggregates)",
           "certification": {"source": "gpushare", "level": "PROFILED_EXPLORATORY_ONLY", "fields": [],
                             "certified": {"adjusted_prices": False, "listing_status": False, "trading_status": False}}}


def model_call_factory():
    """The Agent's own DeepSeek adapter and request/response contracts (same settings as the deployed agent.toml)."""
    from research_agent.llm import EnvironmentSecrets, ModelError, ProviderConfig, check_request, check_response
    from research_agent.providers.deepseek import DeepSeekAdapter, HTTPTransport
    cfg = ProviderConfig("deepseek", "deepseek-flash", version="v1beta-live-1", temperature=0.0, max_output_tokens=4096,
                         timeout_seconds=60.0, max_retries=1, credential_ref="env:QRA_DEEPSEEK_API_KEY")
    adapter = DeepSeekAdapter(cfg, EnvironmentSecrets({"env:QRA_DEEPSEEK_API_KEY"}), HTTPTransport(allow_live=True))

    def call(request):
        for attempt in range(2):
            try:
                check_request(adapter, request)
                r = adapter.complete(request)
                check_response(r, request)
                return r
            except ModelError as e:
                if not e.retryable or attempt:
                    raise
                time.sleep(1.0)
    return call


def run_case(case, library, out, label):
    from paper_agent.evidence import PaperEvidence
    from paper_agent.ledger import TaskLedger
    from paper_agent.planner import PlanError, plan
    from paper_agent.understanding import understand
    from research_agent.paper_library import PaperLibrary
    from research_agent.paper_tools import RuntimeClient, named_factor
    rec = dict(id=case["id"], label=label, request=case["request"], expect=case["expect"])
    t0 = time.time()
    lib = PaperLibrary(Path(library))
    found = lib.resolve(case["request"])
    rec["resolve_status"] = found["status"]
    entry = found.get("paper")
    rec["paper"] = entry and entry["name"]
    rec["paper_sha256"] = entry and entry.get("sha256")
    rec["located_correctly"] = bool(entry and case["file"].lower() in entry["name"].lower())
    if not entry:
        rec.update(outcome="LOCATION_FAILED", seconds=round(time.time() - t0, 1))
        return rec
    ledger = TaskLedger(out / "ledgers" / label, goal=case["id"], budget=dict(model_calls=40, total_tokens=2_000_000,
                                                                            wall_seconds=10 ** 7, design_revisions=2, orchestration_turns=0))
    rec["ledger"] = str(ledger.dir)
    try:
        ev = PaperEvidence.build(lib.path(entry), cache_dir=out / "cache" / label, allowed_roots=[Path(library) / "files"])
        client = RuntimeClient(model_call_factory())
        kw = {}
        typed = {}
        try:
            from research_agent.paper_tools import user_parameters          # new flow only
            typed = user_parameters(case["request"])
        except ImportError:
            pass
        if typed:
            kw["user_params"] = typed
        # as in production: the factor the user named reaches the reader as its focus and the planner as the factor;
        # with none named and several read, the user's own words may name one (paper_tools.named_factor)
        factor = case.get("factor") or ""
        u = understand(ev, client, ledger, focus=factor, **kw)
        names = [f["name"] for f in u["factors"]]
        rec["factors_read"] = names
        if not factor and len(names) > 1:
            factor = named_factor(names, case["request"])
        rec["factor_chosen"] = factor
        try:
            p, _, _ = plan(ev, u, PROFILE, factor=factor or None)
        except PlanError as e:
            rec.update(outcome="PLAN_" + e.code, plan_status=e.code)
        else:
            fac = next((f for f in u["factors"] if f["name"] == p["factor"]), {})
            rec.update(plan_status=p["status"], factor=p["factor"], route=p.get("route"), mode=p.get("mode"),
                       executed=p.get("ir_execution"), formula_read=(fac.get("formula") or {}).get("latex"),
                       formula_as_written=(fac.get("formula") or {}).get("latex_as_written"),
                       parameters=[{k: x.get(k) for k in ("symbol", "value", "status", "paper_values")} for x in fac.get("parameters") or []],
                       hard_codes=[h["code"] for h in p.get("hard_stops") or []],
                       hard=[{k: h.get(k) for k in ("code", "symbol", "source_cn", "detail")} for h in p.get("hard_stops") or []][:8],
                       substitutions=[s["kind"] for s in p.get("substitutions") or []],
                       asset_decision=(p.get("assets") or {}).get("decision"), asset_summary=(p.get("assets") or {}).get("summary_cn"),
                       asset_consent_required=bool(p.get("asset_consent_required")),
                       conflicts=[{k: c.get(k) for k in ("code", "blocking", "source")} for c in fac.get("conflicts") or []])
            rec["outcome"] = p["status"]
        rec["investigations"] = [{k: r.get(k) for k in ("attempt", "rounds", "conflicts_before", "conflicts_after", "pages_consulted", "changed")}
                                 for r in u.get("investigations") or u.get("semantic_repairs") or []]
    except Exception as e:  # noqa: BLE001 -- every failure is a result, with its code
        rec.update(outcome="ERROR", error=f"{type(e).__name__}: {str(e)[:300]}", trace=traceback.format_exc()[-1500:])
    events = ledger.events()
    calls = [e["payload"] for e in events if e["kind"] == "MODEL_CALL"]
    rec.update(model_calls=len(calls), tokens=sum(c.get("tokens") or 0 for c in calls),
               json_errors=sum(1 for c in calls if any("invalid JSON" in s for s in c.get("schema_errors") or [])),
               schema_errors=sum(1 for c in calls if c.get("schema_errors")),
               by_purpose={k: sum(1 for c in calls if c["purpose"] == k) for k in sorted({c["purpose"] for c in calls})},
               model_errors=[e["payload"].get("code") for e in events if e["kind"] == "MODEL_ERROR"],
               seconds=round(time.time() - t0, 1))
    rec["verdict"] = judge(case, rec)
    return rec


def judge(case, r):
    """Automatic classification for cases with a written expectation; 'manual' cases are classified by a reviewer."""
    if r.get("outcome") == "ERROR" and re.search(r"MODEL_ERROR: (TIMEOUT|NETWORK_ERROR|TRANSPORT_ERROR|SERVER_ERROR|RATE_LIMIT|"
                                                 r"INCOMPLETE_STREAM|PROVIDER_RESOURCE_ERROR)", r.get("error") or ""):
        return "服务商故障（不计入）"              # the model provider did not answer: not a Quant-Agent outcome
    if r.get("outcome") in ("ERROR", "LOCATION_FAILED"):
        return "工程失败"
    if (r.get("outcome") or "").startswith("PLAN_FACTOR_CHOICE"):
        return "需用户选择因子" if case.get("expect") in ("manual", "block") or not case.get("factor") else "工程失败"
    if case["expect"] == "manual":
        return "待人工判定"
    blocked = r.get("outcome") == "BLOCKED" or r.get("asset_consent_required")
    reasons = set(r.get("hard_codes") or [])
    if case["expect"] == "block":
        ok = (set(case.get("codes") or []) & reasons) or (r.get("asset_decision") in (case.get("assets") or []))
        if blocked and ok:
            return "正确阻断"
        if r.get("outcome") == "AWAITING_USER_DECISION" and not r.get("asset_consent_required"):
            return "错误放行"
        return "阻断原因不符"
    if r.get("outcome") == "AWAITING_USER_DECISION":
        text = " ".join(str(r.get(k) or "") for k in ("executed", "formula_read"))
        return "真实成功（待执行）" if re.search(case.get("formula") or ".", text) else "放行但公式不符"
    return "不必要阻断"


def run_meta(a):
    """What this result set was produced with: the source tree actually imported, reader/planner versions, arguments."""
    import hashlib
    import paper_agent
    import research_agent.paper_tools as pt
    from paper_agent.understanding import VERSION
    root = Path(paper_agent.__file__).resolve().parents[1]
    h = hashlib.sha256()
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" not in f.parts:
            h.update(str(f.relative_to(root)).encode() + b"\0" + f.read_bytes())
    return {"label": a.label, "src_root": str(root), "src_sha256": h.hexdigest(), "understanding_version": VERSION,
            "planner_rev": getattr(pt, "PLANNER_REV", None), "cases": a.cases, "only": a.only, "repeat": a.repeat,
            "model": "deepseek-flash", "started": time.strftime("%Y-%m-%d %H:%M:%S")}


def cmd_run(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"run_meta_{a.label}.json").write_text(json.dumps(run_meta(a), ensure_ascii=False, indent=1), encoding="utf-8")
    results = []
    for rep in range(a.repeat):                    # the reader is not deterministic across calls: repeat every case
      for group in a.cases.split(","):
        for case in CASES[group]:
            if a.only and case["id"] not in a.only.split(","):
                continue
            case = dict(case, id=case["id"] + (f"#r{rep + 1}" if rep else ""))
            print(f"[{a.label}] {case['id']} {case['request']}", flush=True)
            r = run_case(case, a.library, out, a.label)
            print(f"[{a.label}] {case['id']} -> {r.get('outcome')} / {r.get('verdict')} calls={r.get('model_calls')} tokens={r.get('tokens')}", flush=True)
            results.append(r)
            (out / f"results_{a.label}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def compare(out):
    old = {r["id"]: r for r in json.loads((out / "results_old.json").read_text(encoding="utf-8"))}
    new = {r["id"]: r for r in json.loads((out / "results_new.json").read_text(encoding="utf-8"))}
    lines = ["| 案例 | 旧流程结果 | 旧判定 | 新流程结果 | 新判定 | 调用 旧/新 | Token 旧/新 | JSON错误 旧/新 |", "|---|---|---|---|---|---|---|---|"]
    for k in new:
        o, n = old.get(k, {}), new[k]
        fmt = lambda r: f"{r.get('outcome')}" + (f"（{','.join(r.get('hard_codes') or [])[:80]}）" if r.get("hard_codes") else "")  # noqa: E731
        lines.append(f"| {k} | {fmt(o)} | {o.get('verdict')} | {fmt(n)} | {n.get('verdict')} | {o.get('model_calls')}/{n.get('model_calls')} | "
                     f"{o.get('tokens')}/{n.get('tokens')} | {o.get('json_errors')}/{n.get('json_errors')} |")
    (out / "compare.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def _factor_key(name):
    """A factor's identity, not its wording: the acronym in parentheses, else the name before them (alphanumerics)."""
    name = str(name or "")
    acr = re.findall(r"[\(（]\s*([A-Za-z][A-Za-z0-9#^+-]{1,9})\s*[\)）]", name)
    base = re.split(r"\s*[\(（]", name)[0]
    return re.sub(r"[^a-z0-9#]", "", (acr[0] if acr else base).lower())


def _norm_formula(text):
    """Executed formula without cosmetic differences (spaces, EMA truncation annotations)."""
    t = re.sub(r"\s+", "", str(text or ""))
    return re.sub(r",W=\d+", "", t)


def consistency(out):
    """Repeat-run agreement per case and label: paper, factor, executed formula, parameters, asset decision, outcome and
    block reasons. Wording of explanations is not compared; a change in identity, definition or outcome is a drift."""
    lines = ["| 流程 | 案例 | 论文 | 因子 | 执行公式 | 参数 | 资产判断 | 结论状态 | 阻断原因 | 判定 |", "|---|---|---|---|---|---|---|---|---|---|"]
    summary = {}
    for label in ("old", "new"):
        path = out / f"results_{label}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        first = {r["id"]: r for r in rows if "#r" not in r["id"]}
        n = drift = 0
        for r in rows:
            if "#r" not in r["id"]:
                continue
            base = first.get(r["id"].split("#r")[0])
            if not base:
                continue
            n += 1
            checks = {"论文": base.get("paper") == r.get("paper"),
                      "因子": _factor_key(base.get("factor")) == _factor_key(r.get("factor")),
                      "执行公式": _norm_formula(base.get("executed")) == _norm_formula(r.get("executed")),
                      "参数": json.dumps(base.get("parameters"), sort_keys=True) == json.dumps(r.get("parameters"), sort_keys=True),
                      "资产判断": base.get("asset_decision") == r.get("asset_decision"),
                      "结论状态": base.get("outcome") == r.get("outcome"),
                      "阻断原因": sorted(set(base.get("hard_codes") or [])) == sorted(set(r.get("hard_codes") or []))}
            identity = all(checks[k] for k in ("论文", "因子", "执行公式", "资产判断", "结论状态"))
            drift += not identity
            lines.append(f"| {label} | {base['id']} | " + " | ".join("一致" if checks[k] else "**不同**" for k in checks)
                         + f" | {'一致' if identity else '漂移'} |")
        summary[label] = {"pairs": n, "identity_drift": drift}
    text = "\n".join(lines) + "\n\n" + json.dumps(summary, ensure_ascii=False) + "\n"
    (out / "consistency.md").write_text(text, encoding="utf-8")
    print(text)
    return summary


def cmd_health(a):
    """Minimal provider health probe before any large run: 3 tiny structured calls through the Agent's own adapter.
    Healthy = all 3 answer valid JSON within 20 s each. Prints latency and tokens; nothing else is called."""
    key = sys.stdin.readline().strip()
    if not key:
        raise SystemExit("no key")
    os.environ["QRA_DEEPSEEK_API_KEY"] = key
    from research_agent.llm import Message, ModelError, ModelRequest, Role
    call = model_call_factory()
    ok = 0
    for i in range(3):
        t0 = time.time()
        try:
            r = call(ModelRequest((Message(Role.USER, 'Reply with the JSON object {"ok": true} and nothing else.'),),
                                  json_object=True))
            good = json.loads(r.content).get("ok") is True
            ok += good and (time.time() - t0) < 20
            print(f"probe {i + 1}: {'OK' if good else 'BAD_CONTENT'} {time.time() - t0:.1f}s tokens={r.usage.total_tokens}", flush=True)
        except ModelError as e:
            print(f"probe {i + 1}: {e.code} after {time.time() - t0:.1f}s", flush=True)
    print("PROVIDER_HEALTHY" if ok == 3 else "PROVIDER_NOT_HEALTHY", flush=True)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def cmd_drive(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    # one comparison at a time on the host: a second start (e.g. after a local Ctrl+C) would double the model cost
    lock = out.parent / "locks" / "AB_RUNNING.lock"          # the operator's driver creates locks/ for quantagent
    lock.parent.mkdir(exist_ok=True)
    if lock.exists():
        held = json.loads(lock.read_text(encoding="utf-8") or "{}")
        if _alive(int(held.get("pid") or 0)):
            print(f"ABORT: another comparison is running ({held.get('out')}, pid {held.get('pid')}); not started", flush=True)
            raise SystemExit(3)
    lock.write_text(json.dumps({"pid": os.getpid(), "out": str(out), "started": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    try:
        _drive(a, out)
    finally:
        lock.unlink(missing_ok=True)


def _drive(a, out):
    key = (sys.stdin.readline().strip() if a.key_stdin else
           os.environ.get("QRA_DEEPSEEK_API_KEY") or getpass.getpass("DeepSeek Key (not echoed, not stored): ").strip())
    if not key:
        raise SystemExit("no key")
    env = dict(os.environ, QRA_DEEPSEEK_API_KEY=key, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONIOENCODING="utf-8")
    me = Path(__file__).resolve()
    procs = []
    for label, src in (("old", a.old), ("new", a.new)):
        if a.labels and label not in a.labels.split(","):
            continue
        log = open(out / f"run_{label}.log", "w", encoding="utf-8")
        procs.append(subprocess.Popen([sys.executable, "-X", "utf8", str(me), "run", "--label", label, "--library", a.library,
                                       "--out", str(out), "--cases", a.cases, "--repeat", str(a.repeat)] + (["--only", a.only] if a.only else []),
                                      env=dict(env, PYTHONPATH=src), stdout=log, stderr=subprocess.STDOUT, cwd=str(out)))
    # progress: every finished case is echoed as it happens (the operator's window used to stay silent for 30 minutes)
    seen = {}
    while any(p.poll() is None for p in procs) or seen.get("_final") is None:
        if all(p.poll() is not None for p in procs):
            seen["_final"] = True
        for log in sorted(out.glob("run_*.log")):
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[seen.get(log.name, 0):]:
                if " -> " in line or "Traceback" in line or "Error" in line:
                    print(time.strftime("%H:%M:%S"), line, flush=True)
            seen[log.name] = len(lines)
        time.sleep(3)
    if (out / "results_old.json").exists() and (out / "results_new.json").exists():
        compare(out)
    consistency(out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("drive")
    d.add_argument("--old", required=True)
    d.add_argument("--new", required=True)
    d.add_argument("--labels", default="")
    d.add_argument("--key-stdin", action="store_true", help="read the key from the first stdin line (operator's local driver)")
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    for p in (d, r):
        p.add_argument("--library", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--cases", default="dev")
        p.add_argument("--only", default="")
        p.add_argument("--repeat", type=int, default=2)
    c = sub.add_parser("compare")
    c.add_argument("--out", required=True)
    k = sub.add_parser("consistency")
    k.add_argument("--out", required=True)
    sub.add_parser("health")
    a = ap.parse_args()
    {"drive": cmd_drive, "run": cmd_run, "compare": lambda a: compare(Path(a.out)),
     "consistency": lambda a: consistency(Path(a.out)), "health": cmd_health}[a.cmd](a)


if __name__ == "__main__":
    main()
