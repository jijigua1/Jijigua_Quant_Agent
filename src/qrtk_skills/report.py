"""report.render: Markdown research report + PNG charts built only from stored artifacts."""
from __future__ import annotations

import json
import platform
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import qrtk  # noqa: E402

from .runtime import SkillError  # noqa: E402
from .tools import j  # noqa: E402


def f4(x):
    return "n/a" if x is None else f"{x:.4f}"


def pct(x):
    return "n/a" if x is None else f"{100 * x:.2f}%"


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _save(fig, folder, name):
    fig.savefig(folder / name, dpi=110, metadata={"Software": None})
    plt.close(fig)


def report_render(ctx, title: str, slug: str, question: str, hypothesis: str, evaluation: str,
                  data_profiles: list, order_plan: str | None = None, backtest: str | None = None,
                  decay: str | None = None, profile: str | None = None, sensitivity: str | None = None,
                  lookahead: str | None = None, evidence: str | None = None, failures: list | None = None,
                  next_steps: list | None = None, reproducibility: dict | None = None):
    if ctx.artifact_dir is None:
        raise SkillError("PERMISSION_DENIED", "no writable artifact directory granted")
    if not re.fullmatch(r"[a-z0-9_]+", slug):
        raise SkillError("SCHEMA_INVALID", "slug must be lowercase letters, digits, underscore")
    A = ctx.artifacts
    ev = A.get(evaluation, "factor_evaluation")
    series = A.get(ev["series_ref"], "factor_series")
    profs = [A.get(r, "data_profile") for r in data_profiles]
    plan = A.get(order_plan, "order_plan") if order_plan else None
    bt = A.get(backtest, "backtest_summary") if backtest else None
    dec = A.get(decay, "factor_decay") if decay else None
    fp = A.get(profile, "factor_profile") if profile else None
    sens = A.get(sensitivity, "sensitivity") if sensitivity else None
    la = A.get(lookahead, "lookahead_check") if lookahead else None
    evd = A.get(evidence, "evidence_review") if evidence else None
    failures = failures or []
    folder = ctx.artifact_dir / slug
    folder.mkdir(parents=True, exist_ok=True)
    spec = ev["spec"]
    values = {}          # every number quoted in the text, for consistency checks
    figs = []

    missing = [n for n, v in (("backtest", bt), ("evidence review", evd)) if v is None]
    synthetic = any(p["synthetic"] for p in profs)
    verdict = evd["verdict"] if evd else "not reviewed"
    complete = not missing and verdict == "sufficient"

    L = [f"# {title}", ""]
    if synthetic:
        L += ["> **数据声明：本报告全部使用合成数据。** 所有数值只验证研究流程与计算实现，"
              "不构成任何真实市场证据。", ""]
    L += [f"报告状态：**{'complete' if complete else 'incomplete'}**；证据评估：**{verdict}**。"
          + (f" 缺少：{', '.join(missing)}。" if missing else ""), ""]

    L += ["## 1. 研究问题与假设", "", f"- 问题：{question}", f"- 假设：{hypothesis}", ""]

    L += ["## 2. 数据来源与时间范围", "",
          _table(["数据", "来源", "合成", "范围", "行×列", "缺失率", "观察时点", "质量", "SHA-256"],
                 [[p["panel"], p["source"], "是" if p["synthetic"] else "否", f"{p['start']} ~ {p['end']}",
                   f"{p['rows']}×{p['cols']}", pct(p["missing_rate"]), p["timing"]["observed_at"], p["status"],
                   p["sha256"][:12]] for p in profs]), ""]
    for p in profs:
        if p["issues"]:
            L.append(f"- {p['panel']} 问题：{'; '.join(p['issues'])}")
    L.append("")

    L += ["## 3. 因子与策略定义", "",
          f"- 因子：`{spec['factor_name']}`；方向 {ev['direction']}（来源：{ev['direction_source']}）；"
          f"分组 {spec['n_groups']}，group 0 为方向调整后最好的一组。",
          f"- 策略：{plan['rule'] if plan else '未生成订单计划'}；执行规则 `{spec['execution_rule']}`。", ""]

    L += ["## 4. 方法与时间语义", "",
          f"- 因子在 T 日收盘后可观察；标签 = price[T+{spec['lag']}+{spec['horizon']}] / price[T+{spec['lag']}] − 1。",
          "- 每个样本段只使用信号日和标签出场日都在段内的日期（purge），段与段之间没有标签重叠。",
          "- 订单在信号日之后的下一交易日执行；估值用收盘价，成交价与估值价是两个输入。",
          "- 三类结果分开报告：预测性（IC/RankIC）、理论分组收益（毛收益，不可交易）、"
          "参考账本收益（在所列假设下的可交易收益估计）。", ""]

    L += ["## 5. 实验参数（实验前冻结）", "", f"- spec 指纹：`{ev['spec_fingerprint']}`", "",
          _table(["参数", "值"], [[k, v] for k, v in spec.items()]), ""]

    L += ["## 6. 因子研究结果", "", "### 6.1 预测性（IC / RankIC）", ""]
    rows = []
    for name in ("train", "valid", "test"):
        sp = ev["splits"].get(name)
        if not isinstance(sp, dict):
            rows.append([name, "sealed（未揭示）" if sp == "sealed" else "n/a", "", "", "", "", ""])
            continue
        r, i = sp["predictive"]["rank_ic"], sp["predictive"]["ic"]
        for k, v in (("rank_ic_mean", r["mean"]), ("rank_icir", r["icir"]), ("ic_mean", i["mean"])):
            values[f"{name}.{k}"] = f4(v)
        rows.append([name, f4(r["mean"]), f4(r["icir"]), f4(i["mean"]), pct(r["positive_ratio"]),
                     r["n_dates"], sp["n_purged"]])
    L += [_table(["样本段", "RankIC 均值", "RankICIR", "IC 均值", "RankIC>0 比例", "有效日数", "purge 日数"], rows),
          "", "ICIR 未年化；h>1 时标签重叠，日度 IC 不独立。", ""]

    L += ["### 6.2 理论分组收益（毛收益，不含成本、不考虑成交——不是可交易收益）", ""]
    rows = []
    for name in ("train", "valid", "test"):
        sp = ev["splits"].get(name)
        if isinstance(sp, dict):
            tg = sp["theoretical_groups"]
            g = tg["mean_group_return_gross"]
            values[f"{name}.long_short_gross"] = f4(tg["long_short_mean_gross"])
            rows.append([name] + [f4(g.get(str(k))) for k in range(spec["n_groups"])]
                        + [f4(tg["long_short_mean_gross"]), f4(tg["monotonicity"]["daily_mean"])])
    L += [_table(["样本段"] + [f"G{k}" for k in range(spec["n_groups"])] + ["G0−G末", "单调性"], rows),
          "", f"组收益为每个信号日的 {spec['horizon']} 日持有期毛收益均值。", ""]

    if dec:
        L += ["### 6.3 因子衰减（仅训练+验证段）", "",
              _table(["持有期", "RankIC 均值", "IC 均值", "有效日数", "约独立样本"],
                     [[r["horizon"], f4(r["rank_ic_mean"]), f4(r["ic_mean"]), int(r["n_dates"]),
                       f"{r['approx_independent']:.1f}"] for r in dec["rows"]]), ""]
    if fp:
        d, c = fp["distribution"], fp["coverage"]
        L += ["### 6.4 分布与覆盖", "",
              f"- 平均缺失率 {pct(d['mean_missing_rate'])}，最大 {pct(d['max_missing_rate'])}；"
              f"异常值 {d['total_outliers']} 个（{d['outlier_rule']}）；inf {d['total_inf']} 个。",
              f"- 覆盖率均值 {pct(c['mean'])}，最低 {pct(c['min'])}，低于 {pct(c['threshold'])} 的天数 "
              f"{c['days_below']}（最长连续 {c['longest_run_below']} 天）。", ""]

    L += ["## 7. 策略参考回测（可交易收益估计）", ""]
    if bt:
        m = bt["metrics"]
        for k in ("cumulative_return", "annual_return", "annual_volatility", "sharpe", "max_drawdown", "turnover"):
            values[f"bt.{k}"] = f4(m[k])
        values["bt.total_fees"] = f"{m['total_fees']:.2f}"
        L += [f"- 引擎：`{bt['engine']}`（本地参考账本，不是唯一或正式引擎）；区间 {bt['start']} ~ {bt['end']}；"
              f"对账：{'通过' if bt['reconcile_ok'] else '失败'}。", "",
              _table(["指标", "值"], [["累计收益", f4(m["cumulative_return"])], ["年化收益", f4(m["annual_return"])],
                                     ["年化波动率", f4(m["annual_volatility"])], ["Sharpe", f4(m["sharpe"])],
                                     ["最大回撤", f4(m["max_drawdown"])], ["日均单边换手", f4(m["turnover"])],
                                     ["总费用", f"{m['total_fees']:.2f}"], ["成交笔数", bt["n_trades"]],
                                     ["拒单笔数", bt["n_rejections"]]]), "",
              f"- 拒单按类别：{bt['rejections_by_category'] or '无'}；按原因：{bt['rejections_by_reason'] or '无'}", "",
              "账本假设：", ""] + [f"- {a}" for a in bt["assumptions"]] + [""]
    else:
        L += ["**未生成可交易收益结论**：没有可用的回测结果。上文的理论分组收益不能替代账户收益。", ""]

    # ---- charts, each from an artifact, with its data saved next to it ----
    ric = series["rank_ic"]
    if ric.notna().sum() > 1:
        df = pd.DataFrame({"rank_ic": ric, "rolling_20": ric.rolling(20, min_periods=10).mean()})
        df.to_csv(folder / "fig_rank_ic.csv")
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.bar(df.index, df["rank_ic"], color="#9bb7d4", width=1.0, label="daily RankIC")
        ax.plot(df.index, df["rolling_20"], color="#1f4e79", label="20-day mean")
        ax.axvline(pd.Timestamp(series["splits"]["valid"][0]), color="grey", ls="--", lw=1)
        ax.axhline(0, color="black", lw=0.5)
        ax.set_title("Daily RankIC (train | valid)")
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        _save(fig, folder, "fig_rank_ic.png")
        figs.append(("fig_rank_ic.png", "fig_rank_ic.csv", ev["series_ref"], "逐日 RankIC 与 20 日均值；虚线为验证段起点"))
    gr = series["group_returns"]
    first = gr.dropna(how="all").index.min()           # skip factor warm-up rows only;
    gr = gr.loc[first:] if pd.notna(first) else gr     # later gaps still break the path (NaN)
    cum = qrtk.cumulative_returns(gr, series["horizon"]).dropna(how="all")
    if len(cum) > 1:
        cum.to_csv(folder / "fig_groups.csv")
        fig, ax = plt.subplots(figsize=(8, 3))
        for g in cum.columns:
            ax.plot(cum.index, cum[g], label=f"G{g}")
        ax.set_title(f"Theoretical cumulative group return, gross, non-overlapping (h={series['horizon']}) - NOT tradable")
        ax.legend(fontsize=7, ncol=len(cum.columns))
        fig.tight_layout()
        _save(fig, folder, "fig_groups.png")
        figs.append(("fig_groups.png", "fig_groups.csv", ev["series_ref"], "理论分组累计毛收益（非重叠复利，不可交易）"))
    if bt:
        daily = A.get(bt["daily_ref"], "ledger_daily")
        nav = daily["nav"]
        dd = nav / nav.cummax() - 1
        pd.DataFrame({"nav": nav, "drawdown": dd}).to_csv(folder / "fig_nav.csv")
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4), sharex=True, height_ratios=[2, 1])
        a1.plot(nav.index, nav, color="#1f4e79")
        a1.set_title(f"Reference ledger NAV ({bt['engine']}, simulated)")
        a2.fill_between(dd.index, dd, 0, color="#c0504d")
        a2.set_title("Drawdown")
        fig.tight_layout()
        _save(fig, folder, "fig_nav.png")
        figs.append(("fig_nav.png", "fig_nav.csv", bt["daily_ref"], "参考账本 NAV 与回撤"))
    if dec:
        t = pd.DataFrame(dec["rows"]).set_index("horizon")
        t[["rank_ic_mean", "ic_mean"]].to_csv(folder / "fig_decay.csv")
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.bar(t.index.astype(str), t["rank_ic_mean"].astype(float), color="#4f81bd")
        ax.axhline(0, color="black", lw=0.5)
        ax.set_title("RankIC by holding period (train+valid)")
        fig.tight_layout()
        _save(fig, folder, "fig_decay.png")
        figs.append(("fig_decay.png", "fig_decay.csv", decay, "因子衰减"))

    L += ["## 8. 图表与数据依据", ""]
    for png, csv, ref, cap in figs:
        L += [f"![{cap}]({png})", "", f"*{cap}。数据：`{csv}`，来源产物 `{ref}`。*", ""]

    L += ["## 9. 诊断", ""]
    if la:
        L.append(f"- 未来函数检查：{'通过' if la['passed'] else '**未通过**'}（{la['meaning']}；"
                 + ", ".join(f"{c['cutoff']}: {c['changed_cells']} 格变化" for c in la["checks"]) + "）。")
    if sens:
        L += ["- 参数敏感性（仅训练+验证段，只作报告，不据此替换冻结参数）：", "",
              _table(["持有期", "分组", "RankIC 均值", "G0−G末 毛收益", "冻结选择"],
                     [[r["horizon"], r["n_groups"], f4(r["rank_ic_mean"]), f4(r["long_short_mean_gross"]),
                       "是" if r["is_frozen_choice"] else ""] for r in sens["rows"]]), ""]
    if evd:
        L += [f"- 证据评估：**{evd['verdict']}**"] + [f"  - 不足：{r}" for r in evd["reasons"]] \
             + [f"  - 可疑：{r}" for r in evd["suspicious"]] + [""]

    L += ["## 10. 失败实验与异常", ""]
    if failures:
        L += [_table(["调用", "错误码", "说明"], [[f["tool"], f["code"], f["message"]] for f in failures]), ""]
    else:
        L += ["无失败调用。", ""]
    L += [f"- 研究警告：{w}" for w in ev["warnings"]] + [""]

    L += ["## 11. 局限与未验证事项", ""]
    lim = ["结果只覆盖所列数据与区间，未做真实市场验证。" if not synthetic else
           "数据为合成数据，结论不外推到任何真实市场。",
           "参考账本不建模冲击成本、订单簿、公司行动和退市清算；费用为参数。",
           "IC 统计未做重叠修正或多重检验校正。",
           "正式回测引擎、真实停牌/涨跌停数据和分钟执行价格尚未接入。"]
    if not complete:
        lim.append("报告不完整或证据不足：不得据此得出可交易结论。")
    L += [f"- {x}" for x in lim] + [""]

    repro = {"spec_fingerprint": ev["spec_fingerprint"],
             "data_sha256": {p["panel"]: p["sha256"] for p in profs},
             "artifacts": {k: v for k, v in (("evaluation", evaluation), ("backtest", backtest),
                                             ("order_plan", order_plan), ("decay", decay)) if v},
             "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
             "qrtk": qrtk.__version__, **(reproducibility or {})}
    L += ["## 12. 可复现信息", "", "```json", json.dumps(repro, indent=2, ensure_ascii=False), "```", ""]

    L += ["## 13. 后续研究建议", ""] + [f"- {s}" for s in (next_steps or ["无"])] + [""]

    text = "\n".join(L)
    (folder / "report.md").write_text(text, encoding="utf-8")
    data = j({"status": "complete" if complete else "incomplete", "verdict": verdict, "values": values,
              "figures": [f[0] for f in figs], "reproducibility": repro, "synthetic": synthetic})
    (folder / "report_data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    out = {"status": data["status"], "verdict": verdict, "folder": slug, "files": ["report.md", "report_data.json"]
           + [f[0] for f in figs] + [f[1] for f in figs], "values": values, "missing": missing}
    out["ref"] = ctx.put(out, "report")
    return out
