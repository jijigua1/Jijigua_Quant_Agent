> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B1 回测引擎源码审查

审查日：2026-10-12。只读审查本地 `<LOCAL_RESEARCH_ROOT>` 当前源码，以及该项目保存的 Pyx/Perry/Gyc **历史只读源码快照**；未连接 GPUShare 复核快照是否仍与服务器一致。所有结论只覆盖被审查的源码版本和本轮合成输入。notebook、当前入口和三份候选快照的 SHA-256 见 reviewed_source_hashes.json（原内部附件未公开）。

## 正式入口与实际调用链

`backtest.ipynb` 共 5 个 cell。最后一个 cell 设定 `CONFIG_FINAL`，调用 `from core_backtest.api import *`、`run_final_notebook(CONFIG_FINAL)`。前 4 个 cell 是历史记录，本轮未执行。实际链路：

`api.run_final_notebook → config.resolve_optional → data.load_final_data → portfolio.run_final_backtest → signal.align_signal/select_candidates → execution.buy_quote/sell_quote → benchmark.finalize_result → metrics.final_metrics → analysis.final_factor_analysis → plotting.plot_final_result → reporting.save_final_result`。

本轮只在内存中构造合成 `data` 调用 `portfolio.run_final_backtest`，未调用 `load_final_data`、notebook、`analysis`、绘图或研究文件读取。当前合成账本源文件完整 SHA-256 在 manifest.json（原内部附件未公开）；其中 `portfolio.py=c1eabe81…`、`execution.py=81748744…`、`signal.py=005568af…`。运行环境 Python 3.12.4（精确版本见 manifest）、pandas 2.3.3、NumPy 1.26.4。完整现有框架回归为 76 项合成检查通过，原 notebook 历史 cell 不变。

## 候选比较

| 候选 | 实际审查范围 | 可复用处 | 正式账本缺口 | 判断 |
|---|---|---|---|---|
| GeorgeResearch `core_backtest` | 当前 `api/data/signal/portfolio/execution/benchmark/metrics` 与合成测试 | T 收盘 score 向下一行开盘移位；raw 模式整手、现金槽位、成交/拒单、持仓续持、分红/送股事件、逐日现金/市值/NAV/PnL；可直接注入受控内存数据 | 默认 adjusted_units 是复权份额；打包卖出费率不能同时正确表示最低佣金＋印花税；拒单无完整委托数量；未验证真实停牌/涨跌停、税/分红时点、退市估值 | **B：最值得复用，先做最小合同适配** |
| Pyx `score_backtest.py` | `docs/research_wty_agent_phase1_0_20261011/pyx_readonly_source/backtest_optimization` 快照及测试 | 整数股数、T 计划/T+1 VWAP、拒单、现金/NAV、成交轨迹 | 依赖 EOD `mask_trade`、VWAP、规划器；无完整公司行动/分项费用合同；目标价含 T+1 VWAP，须保证仅执行侧看到 | 候选补充参照，不优先直接接入 |
| Perry `run_position_backtest.py` | `docs/research_wty_agent_plan_20261011/revision_v2_sources/opt/external-research` 快照 | 多 score 合并、仓位规划、次日 VWAP 和非交易持仓留存 | 规划时可能用下一日 VWAP/close；核心账本是 planner 的 `estimated_cash` 与 `portfolio_value`，本轮没有独立实际成交/公司行动交叉验证；强依赖其 apps/EOD | 不作为当前正式执行内核 |
| Gyc `evaluate_three_models_top300_backtest_2026.py` | `docs/research_wty_agent_plan_20261011/server_source/opt/external-research` 快照 | 排名和分组探索思路 | `shift(-2)/shift(-1)` 得理论未来收益、`fillna(0)` 汇总；无订单、真实股数、现金或公司行动账本；历史来源依赖 2026 数据 | 只能作研究统计参考，**不得作为账户回测**；本轮未运行其代码或读取相关数据 |

Pyx/Perry/Gyc 是已有的**本地快照**，不是当前服务器状态认证；本轮没有动态加载其 EOD/PKL，也没有执行它们的回测。

## GeorgeResearch 的真实边界

- `signal.align_signal` 把 T 日 score 与资格移到下一交易行，执行价由当日 open 加/减滑点得到；本轮周五信号、周一成交与未来行扰动测试通过。
- `portfolio` 的 H 槽位在拒卖时保留仓位和占槽，拒买时原预算留现金。它没有单独的“冻结金额/释放金额”流水，只有槽位现金；不能宣称已支持券商级冻结。
- raw 模式用整数买入手数，但仅 `.SH/.SZ`，科创板以 200 股起买；其它板块/历史规则未逐时点认证。卖出可以整仓，送股倍率可能产生小数股，**实际股数约束未在引擎内部兜底**。
- `sell_quote` 当前费用为 `max(gross*sell_cost_rate, min_sell_fee)`。若最低佣金 5 元、卖出税率 0.1%、卖出额 1100 元，引擎扣 5 元；分项应为 5+1.1=6.1 元。合成测试确认此差异，P1。
- 公司行动输入是上游已规范的 `share_multiplier/cash_per_share`；引擎于开盘前更新份额、现金和旧估值。登记日、除权日、到账日、送配股零股、税与现金替代均尚无上游合同。不能由复权因子推导为真实事件。
- `load_final_data` 可 `pd.read_pickle`，且缺少可买/可卖/停牌文件时默认为有效 open 可成交；只适用于可信研究上游。**未来 Agent 不能直接调用该宽权限加载入口**，应把认证后的分区适配器结果注入内存合同。
- 引擎有 `trades/positions/events/corporate_actions/curve`，但 `events` 对拒单用泛化原因，缺 `requested_shares` 与订单生命周期；本轮生成的 `signal_targets.csv` 是审计辅助，不能冒充完整委托记录。

**结论：**现有 `core_backtest` raw 模式是最小改造的首选候选，已通过本轮限定合成账本；离“正式可执行股票账户回测”仍有代码与数据双重缺口。继续保持 BLOCKED。


