> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-C momentum request failure repair

## Root cause

The SQLite record for task `INTERNAL_RUN_ID_REDACTED` shows that `factor_research` selected the authorized tool `qrtk_expression_study` for the authorized resource `gpushare:daily65`. The grant included that tool and resource, so this was not an authorization failure.

The model proposed `delay(close, 5) / delay(close, 65) - 1`, with `horizon=20`. The expression schema permits windows through 60 and horizons through 10. Thus `$.expression.nodes[2].window=65` exceeded its maximum 60, and `$.horizon=20` exceeded its maximum 10. Operators and z-score standardization were allowed. Industry/market neutralization was not requested and is not supported by this data contract; those were not the rejection cause.

The old event mapper incorrectly recorded this schema error as `AUTHORIZATION_DENIED`, followed by `TASK_AUTHORIZATION_DENIED`, despite `error.code=INVALID_PARAMETERS`. This repair gives schema failures their own `INVALID_PARAMETERS` status/event and reserves `AUTHORIZATION_DENIED` for policy denials. The rejection record retains the tool name, sanitized arguments, and exact failing schema paths; it does not execute the tool or widen policy.

## Behavior changes

- A data-only Skill now stays within its registered tools; a later factor request is handled as a separate user-authorized research turn.
- The router uses compact, verified session evidence for new research tasks. It avoids repeating data discovery when the data contract is already known and does not treat rejected output as evidence.
- It does not silently shorten a requested standard momentum definition. On this 65-observation daily sample (2026-07-03 through 2026-10-09; 50 fixed symbols; unadjusted prices), long-window momentum with skip-5 and horizon-20 cannot be validated. The registered expression bounds are window 1–60, cumulative history up to 120, horizon 1–10, groups 2–5.
- In the v0.6.5 live run, after the user said “默认设定，验证目标都需要”, the agent constructed the separately named `momentum_20d_skip5_exploratory`, using `delay(returns(close,20),5)`, horizon 5, cross-sectional z-score, and five groups. It labeled the result exploratory and evidence insufficient, but it **ran before** the user explicitly said “先完成能做的部分”. The strict consent-timing assertion in `live-momentum` therefore failed. This remains an acceptance limitation; the result must not be presented as the requested complete long-cycle momentum study.
- Parameter-validation failures are no longer described to users as authorization denials.

## Verification

- Windows full suite on v0.6.4: **261 passed, 1 skipped**. Skip: OS denied symbolic-link creation (Windows error 1314). JUnit: `momentum-repair-windows-v064.xml`. The v0.6.5 context-continuity patch has **28 targeted tests passed**; no second full suite was run.
- Linux full suite on v0.6.4: agent **261 passed, 1 skipped**; optional Parquet test skipped because `pyarrow` is absent. Candidate toolkit **135 passed**. The deployed v0.6.5 was exercised in the real CLI but not given a separate full Linux suite.
- The v0.6.5 real DeepSeek/SSH CLI run used the three requested natural-language inputs. It selected `data_research` first, then `factor_research` and the authorized `qrtk_expression_study` tool. Actual verified real-data artifacts were reported at `/srv/jijigua-quant-agent/research_runs/2026-10-12/14-13-49_momentum_20d_skip5_exploratory/`, including `data/factor.pkl` and `reports/report.html`. The tool result reports `delivery_status=VERIFIED`, `n_dates=65`, `evidence.verdict=insufficient`, and `formal_backtest_ready=false`. Full task receipt: `momentum-repair-live-session.json`; PTY output: `momentum-repair-live-ssh-console.txt`. The strict consent-timing assertion failed, so this run is **partial**, not a clean end-to-end pass.

## Deployment

Release target: `/opt/jijigua-quant-agent/research_agent/`, version 0.6.5, quantagent UID 999. Existing code backup: `dist/phase2c-before-0.5.0.zip`. Deployment receipt: `deployment.json`.

The successful exploratory result is not evidence that standard long-cycle momentum works. The published data remains a short, unadjusted research fixture; further data qualification and formal backtest remain separate gates.
