> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 五日反转因子研究（合成数据）



> **数据声明：本报告全部使用合成数据。** 所有数值只验证研究流程与计算实现，不构成任何真实市场证据。



报告状态：**complete**；证据评估：**sufficient**。



## 1. 研究问题与假设



- 问题：过去 5 个交易日跌得多的股票，之后 5 个交易日是否相对跑赢？

- 假设：短期反转：因子 = −(5 日收益)，方向 +1（事先设定，未从数据中选择）。



## 2. 数据来源与时间范围



| 数据 | 来源 | 合成 | 范围 | 行×列 | 缺失率 | 观察时点 | 质量 | SHA-256 |

|---|---|---|---|---|---|---|---|---|

| data:open | synthetic generator (seed=7, injected 5-day reversal) | 是 | 2021-01-04 ~ 2022-12-30 | 520×60 | 0.26% | open T (09:25 auction) | ok | 0fc11472338a |

| data:close | synthetic generator (seed=7, injected 5-day reversal) | 是 | 2021-01-04 ~ 2022-12-30 | 520×60 | 0.26% | close T (15:00) | ok | a759d523dbdd |

| data:reversal_5d | builder reversal_5d(close) | 是 | 2021-01-04 ~ 2022-12-30 | 520×60 | 1.26% | after close T | ok | 935a5d458df0 |





## 3. 因子与策略定义



- 因子：`reversal_5d`；方向 1（来源：fixed）；分组 5，group 0 为方向调整后最好的一组。

- 策略：top 10, direction 1, hold 5 sessions, non-overlapping；执行规则 `next_open`。



## 4. 方法与时间语义



- 因子在 T 日收盘后可观察；标签 = price[T+1+5] / price[T+1] − 1。

- 每个样本段只使用信号日和标签出场日都在段内的日期（purge），段与段之间没有标签重叠。

- 订单在信号日之后的下一交易日执行；估值用收盘价，成交价与估值价是两个输入。

- 三类结果分开报告：预测性（IC/RankIC）、理论分组收益（毛收益，不可交易）、参考账本收益（在所列假设下的可交易收益估计）。



## 5. 实验参数（实验前冻结）



- spec 指纹：`fa6e1d8b3b10b40a7277c99dd58ce61a5bc48e28aef6ca72041e1b4d2a6fb081`



| 参数 | 值 |

|---|---|

| factor_name | reversal_5d |

| direction | 1 |

| horizon | 5 |

| train | ['2021-01-04', '2021-12-31'] |

| valid | ['2022-01-03', '2022-06-30'] |

| test | ['2022-07-01', '2022-12-30'] |

| lag | 1 |

| n_groups | 5 |

| min_obs | 20 |

| universe_name | synthetic_all |

| execution_rule | next_open |

| min_dates_per_split | 60 |



## 6. 因子研究结果



### 6.1 预测性（IC / RankIC）



| 样本段 | RankIC 均值 | RankICIR | IC 均值 | RankIC>0 比例 | 有效日数 | purge 日数 |

|---|---|---|---|---|---|---|

| train | 0.0455 | 0.3541 | 0.0513 | 65.06% | 249 | 6 |

| valid | 0.0522 | 0.3992 | 0.0617 | 62.60% | 123 | 6 |

| test | 0.0687 | 0.6441 | 0.0710 | 72.80% | 125 | 6 |



ICIR 未年化；h>1 时标签重叠，日度 IC 不独立。



### 6.2 理论分组收益（毛收益，不含成本、不考虑成交——不是可交易收益）



| 样本段 | G0 | G1 | G2 | G3 | G4 | G0−G末 | 单调性 |

|---|---|---|---|---|---|---|---|

| train | 0.0026 | 0.0017 | 0.0028 | -0.0008 | -0.0034 | 0.0059 | 0.1365 |

| valid | 0.0033 | 0.0005 | -0.0015 | -0.0002 | -0.0038 | 0.0071 | 0.1878 |

| test | 0.0066 | 0.0032 | 0.0003 | -0.0027 | -0.0011 | 0.0077 | 0.2368 |



组收益为每个信号日的 5 日持有期毛收益均值。



### 6.3 因子衰减（仅训练+验证段）



| 持有期 | RankIC 均值 | IC 均值 | 有效日数 | 约独立样本 |

|---|---|---|---|---|

| 1 | 0.0324 | 0.0373 | 382 | 382.0 |

| 5 | 0.0473 | 0.0549 | 378 | 75.6 |

| 10 | 0.0460 | 0.0550 | 373 | 37.3 |

| 20 | 0.0298 | 0.0327 | 363 | 18.1 |



### 6.4 分布与覆盖



- 平均缺失率 1.61%，最大 100.00%；异常值 0 个（robust z > 5.0）；inf 0 个。

- 覆盖率均值 98.39%，最低 0.00%，低于 80.00% 的天数 5（最长连续 5 天）。



## 7. 策略参考回测（可交易收益估计）



- 引擎：`qrtk_reference`（本地参考账本，不是唯一或正式引擎）；区间 2022-07-01 ~ 2022-12-30；对账：通过。



| 指标 | 值 |

|---|---|

| 累计收益 | 0.1688 |

| 年化收益 | 0.3498 |

| 年化波动率 | 0.0900 |

| Sharpe | 3.3795 |

| 最大回撤 | -0.0312 |

| 日均单边换手 | 0.1509 |

| 总费用 | 23515.96 |

| 成交笔数 | 455 |

| 拒单笔数 | 1 |



- 拒单按类别：{'not_executable': 1}；按原因：{'suspended': 1}



账本假设：



- fills at the execution price +/- slippage with unlimited liquidity unless a capacity panel is given

- unadjusted prices and real share counts; dividends, splits and other corporate actions NOT modelled

- delisting liquidation NOT modelled: a position without prices keeps its last mark (stale)

- buys in lots of 100; board-specific rules (e.g. STAR 200-share minimum then 1-share steps) NOT modelled

- fees are configuration parameters, not historical fee schedules

- T+1 enforced

- orders within a session processed in sells_first order

- price-limit rules NOT modelled for the side(s) without a limit panel



## 8. 图表与数据依据



!逐日 RankIC 与 20 日均值；虚线为验证段起点（原内部附件未公开）



*逐日 RankIC 与 20 日均值；虚线为验证段起点。数据：`fig_rank_ic.csv`，来源产物 `art:b241a1ba13bb`。*



!理论分组累计毛收益（非重叠复利，不可交易）（原内部附件未公开）



*理论分组累计毛收益（非重叠复利，不可交易）。数据：`fig_groups.csv`，来源产物 `art:b241a1ba13bb`。*



!参考账本 NAV 与回撤（原内部附件未公开）



*参考账本 NAV 与回撤。数据：`fig_nav.csv`，来源产物 `art:2338e7bf0369`。*



!因子衰减（原内部附件未公开）



*因子衰减。数据：`fig_decay.csv`，来源产物 `art:eb332911969a`。*



## 9. 诊断



- 未来函数检查：通过（factor values up to each cutoff do not depend on later data；2021-06-30: 0 格变化, 2021-12-31: 0 格变化, 2022-06-30: 0 格变化）。

- 参数敏感性（仅训练+验证段，只作报告，不据此替换冻结参数）：



| 持有期 | 分组 | RankIC 均值 | G0−G末 毛收益 | 冻结选择 |

|---|---|---|---|---|

| 1 | 5 | 0.0324 | 0.0022 |  |

| 1 | 10 | 0.0324 | 0.0033 |  |

| 5 | 5 | 0.0473 | 0.0064 | 是 |

| 5 | 10 | 0.0473 | 0.0092 |  |

| 10 | 5 | 0.0460 | 0.0089 |  |

| 10 | 10 | 0.0460 | 0.0135 |  |



- 证据评估：**sufficient**



## 10. 失败实验与异常



| 调用 | 错误码 | 说明 |

|---|---|---|

| data_research/data.profile_panel | DATA_MISSING | data:fundamentals is registered but has no data |

| factor_research/strategy.backtest | CAPABILITY_DENIED | skill factor_research does not declare tool strategy.backtest |

| factor_research/factor.magic_alpha | UNKNOWN_TOOL | tool factor.magic_alpha is not registered |

| factor_research/factor.evaluate | SCHEMA_INVALID | $.factor: expected data_ref, got 'D:/secret/factor.pkl' |

| strategy_backtest/strategy.backtest | ENGINE_UNAVAILABLE | engine server_engine not registered; available ['qrtk_reference'] |

| research_reporting/report.render (read-only host) | PERMISSION_DENIED | host did not grant ['write:artifacts'] |



- 研究警告：labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5



## 11. 局限与未验证事项



- 数据为合成数据，结论不外推到任何真实市场。

- 参考账本不建模冲击成本、订单簿、公司行动和退市清算；费用为参数。

- IC 统计未做重叠修正或多重检验校正。

- 正式回测引擎、真实停牌/涨跌停数据和分钟执行价格尚未接入。



## 12. 可复现信息



```json

{

  "spec_fingerprint": "fa6e1d8b3b10b40a7277c99dd58ce61a5bc48e28aef6ca72041e1b4d2a6fb081",

  "data_sha256": {

    "data:open": "0fc11472338ab56a56ddeeff81ea4343552f242a016a22baffa9f5c07c63274f",

    "data:close": "a759d523dbddaf87cdbe898744caf2cef22dbdedd89661e51257bc63d5781c04",

    "data:reversal_5d": "935a5d458df07467c280798075555d508b32bb80b34e00cebdff2bbff84a54a3"

  },

  "artifacts": {

    "evaluation": "art:c23eb1232666",

    "backtest": "art:7de043fa0633",

    "order_plan": "art:379705e27bc4",

    "decay": "art:eb332911969a"

  },

  "python": "3.12.4",

  "pandas": "2.3.3",

  "numpy": "1.26.4",

  "qrtk": "0.2.0",

  "seed": 7,

  "command": "python -X utf8 examples/reversal_study.py",

  "frozen_spec_file": "frozen_spec.json"

}

```



## 13. 后续研究建议



- 接入 GPUShare 真实日频数据，先完成 data_research 的字段与口径确认

- 在真实停牌、涨跌停面板下重跑参考账本，并与服务器正式引擎用同一订单交叉验证

- 加入行业/市值中性化后比较预测性变化

- 冻结新的 spec 后，用尚未使用过的时间段做下一次样本外检验

