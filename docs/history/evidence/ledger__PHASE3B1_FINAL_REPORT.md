> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B1 最终报告

**交付状态：独立合成账本验收完成；正式真实回测仍为 BLOCKED。** 2026-10-12 在 `<ARCHIVE_ROOT>\phase3b_backtest` 建立了不读取市场文件的候选适配测试、手录数字 oracle、故障注入和可复核的逐日输出。没有修改 `<LOCAL_RESEARCH_ROOT>`、Phase 3-A 数据工作区或冻结的主 Agent v0.6.8；没有服务器部署、真实账户回测或使用 2026 Holdout 表现。

## 核心结论

**最值得复用的是 GeorgeResearch 最后 notebook cell 实际调用的 `core_backtest` raw-price 账本。** 它在受控合成输入中通过了下一交易日开盘成交、常规整手、现金不足/拒单、双资产交易、卖出失败续持、明确停牌旧价估值、整倍送股和现金分红、逐日现金/持仓/NAV 对账。其 `adjusted_units` 默认模式仍是复权份额研究口径，不能用作真实 A 股股数。Pyx 有可参考的订单执行实现，Perry 强依赖次日 VWAP 的规划接口，Gyc 是理论收益汇总；详情见 [BACKTEST_ENGINE_REVIEW.md](ledger__BACKTEST_ENGINE_REVIEW.md)。

**正式回测未过关。** 引擎把卖出税与最低费折成 `max(rate×amount,min_fee)`，无法按真实分项相加；拒单没有完整订单数量/资金预留轨迹；小数股公司行动缺内部拒绝；退市/长期停牌估值、真实公司行动时点和停牌/ST/涨跌停来源未认证。Phase 3-A 文档还确认 Train/Validation 未单独发布、Holdout 尚无系统级隔离。故不能输出真实账户绩效或解除 Backtest Tool 的 BLOCKED。

## 本轮可交付文件

| 交付 | 内容 |
|---|---|
| [BACKTEST_ENGINE_REVIEW.md](ledger__BACKTEST_ENGINE_REVIEW.md) | notebook 最后入口、真实调用链、候选对比和源代码缺口 |
| [EXECUTION_CONTRACT.md](ledger__EXECUTION_CONTRACT.md) | T/T+1、报价/成交、订单、费用、公司行动、估值、审计和分区合同 |
| [SYNTHETIC_MARKET_SPEC.md](ledger__SYNTHETIC_MARKET_SPEC.md) | 11 类合成输入、10 组成功 oracle、未知缺价阻断及故障注入 |
| [LEDGER_RECONCILIATION.md](ledger__LEDGER_RECONCILIATION.md) | 独立手算经济收益、每日现金/仓位/NAV 守恒 |
| [TEST_RESULTS.md](ledger__TEST_RESULTS.md) | 本轮测试命令、结果、警告和未验证范围 |
| [PHASE3B2_HANDOFF.md](ledger__PHASE3B2_HANDOFF.md) | 后续集成所需最小修改和准入闸门；未启动 3-B2 |
| synthetic_acceptance.py（原内部附件未公开） / expected.json（原内部附件未公开） | 可直接运行的候选适配与独立手工预期数字 |
| evidence/run_20261012_1720（原内部附件未公开） | 每案信号、目标、成交、拒单、持仓、公司行动、逐日账本、SHA manifest |

执行 `python -X utf8 <ARCHIVE_ROOT>\phase3b_backtest\synthetic_acceptance.py --core-root <LOCAL_RESEARCH_ROOT> --phase3a-root <ARCHIVE_ROOT>\phase3a_data` 可重复测试。7 个专项测试方法（含 10 案例、5 项故障注入）通过，现有 `test_backtest_final.py` 76 项合成回归通过；Windows 环境和指纹见 [TEST_RESULTS.md](ledger__TEST_RESULTS.md)。本轮报告的验证等级是**软件工程合成验收**，不是研究统计或市场有效性验证。

数据边界沿用 Phase 3-A [最终报告](data-audit__PHASE3A_FINAL_REPORT.md)、[分区合同](data-audit__DATA_SPLIT_CONTRACT.md) 和 [数据前置项](data-audit__PHASE3B_PREREQUISITES.md)。测试只构造 2027 虚构四行日历，不读 2026 真实目标收益、IC 或策略表现；`SplitReader` 边界测试不等于服务器物理隔离。


