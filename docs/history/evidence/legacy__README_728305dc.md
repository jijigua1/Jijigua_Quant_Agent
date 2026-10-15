> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Skills Manifest 与工具依赖

五个 Skill 相互独立，可以组合使用，没有固定的先后流程。每个 Skill 目录包含 `SKILL.md`（研究方法）、`skill.toml`（能力声明）和 `schemas.json`（每个工具的输入输出 Schema）。机器可读的汇总见 manifest.json（原内部附件未公开），由 `qrtk_skills.runtime.manifest_index` 生成，并有测试保证它与各目录的声明一致。

| Skill | 工具 | 请求的权限 | 资源（内存 / 超时） | 底层 qrtk 函数 |
|---|---|---|---|---|
| [data_research](legacy__SKILL_4559a5f9.md) | `data.profile_panel`、`data.minute_quality` | read:catalog, compute | 2 GB / 300 s | `normalize_minute_bars`、`aggregate_daily` |
| [factor_research](legacy__SKILL_fa43a1a7.md) | `factor.evaluate`、`factor.decay`、`factor.profile` | read:catalog, compute | 4 GB / 900 s | `evaluate_splits`、`evaluate_factor`、`multi_horizon`、`factor_distribution`、`coverage_stability` |
| [strategy_backtest](legacy__SKILL_48ee3863.md) | `strategy.signal_to_orders`、`strategy.backtest` | read:catalog, compute | 4 GB / 1800 s | 引擎表 `ENGINES`，默认 `run_backtest`，另用 `reconcile`、`performance_metrics` |
| [research_diagnostics](legacy__SKILL_ed12677d.md) | `diag.lookahead_check`、`diag.sensitivity`、`diag.evidence_review` | read:catalog, compute | 4 GB / 1800 s | `evaluate_factor` |
| [research_reporting](legacy__SKILL_9295bd33.md) | `report.render` | compute, write:artifacts | 1 GB / 300 s | `cumulative_returns`；matplotlib |

**权限：** `skill.toml` 中的权限只是请求。只有同时满足"Skill 请求了"和"宿主授予了"，调用才能执行。

**数据访问：** 工具只能通过 `data:<name>` 引用读取宿主登记的数据，不接受文件路径。工具之间通过不可变的 `art:<id>` 产物传递结果。只有获得 `write:artifacts` 权限的工具，才能写入宿主指定的目录。

**Python 依赖：** qrtk ≥ 0.2.0、pandas ≥ 2.0、numpy ≥ 1.24；research_reporting 还需要 matplotlib ≥ 3.7。Schema 校验和 TOML 解析使用标准库（Python ≥ 3.11 的 `tomllib`），不需要 jsonschema。
