> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子探索性研究：reversal



> **数据声明：本报告全部使用合成数据。** 所有数值只验证研究流程与计算实现，不构成任何真实市场证据。



报告状态：**incomplete**；证据评估：**insufficient**。 缺少：backtest。



## 1. 研究问题与假设



- 问题：图表最终排版检查

- 假设：direction +1 fixed; reversal; lookback=5



## 2. 数据来源与时间范围



| 数据 | 来源 | 合成 | 范围 | 行×列 | 缺失率 | 观察时点 | 质量 | SHA-256 |

|---|---|---|---|---|---|---|---|---|

| data:open | fixed seeded synthetic fixture | 是 | 2023-01-02 ~ 2024-05-17 | 360×20 | 0.00% | synthetic after close | ok | 2d682b0309ce |

| data:close | fixed seeded synthetic fixture | 是 | 2023-01-02 ~ 2024-05-17 | 360×20 | 0.00% | synthetic after close | ok | e8c60c74ae98 |

| data:volume | fixed seeded synthetic fixture | 是 | 2023-01-02 ~ 2024-05-17 | 360×20 | 0.00% | synthetic after close | ok | 688a65c89da1 |





## 3. 因子与策略定义



- 因子：`reversal`；方向 1（来源：fixed）；分组 5，group 0 为方向调整后最好的一组。

- 策略：未生成订单计划；执行规则 `next_observed_open`。



## 4. 方法与时间语义



- 因子在 T 日收盘后可观察；标签 = price[T+1+5] / price[T+1] − 1。

- 每个样本段只使用信号日和标签出场日都在段内的日期（purge），段与段之间没有标签重叠。

- 订单在信号日之后的下一交易日执行；估值用收盘价，成交价与估值价是两个输入。

- 三类结果分开报告：预测性（IC/RankIC）、理论分组收益（毛收益，不可交易）、参考账本收益（在所列假设下的可交易收益估计）。



## 5. 实验参数（实验前冻结）



- spec 指纹：`7579c465a177534b3f72c343ee51297c15d0032eedb44729c8c44f13343f3c95`



| 参数 | 值 |

|---|---|

| factor_name | reversal |

| direction | 1 |

| horizon | 5 |

| train | ['2023-01-02', '2023-10-30'] |

| valid | ['2023-10-31', '2024-03-04'] |

| test | ['2024-03-05', '2024-05-17'] |

| lag | 1 |

| n_groups | 5 |

| min_obs | 10 |

| universe_name | synthetic fixed twenty codes |

| execution_rule | next_observed_open |

| min_dates_per_split | 60 |



## 6. 因子研究结果



### 6.1 预测性（IC / RankIC）



| 样本段 | RankIC 均值 | RankICIR | IC 均值 | RankIC>0 比例 | 有效日数 | purge 日数 |

|---|---|---|---|---|---|---|

| train | 0.0050 | 0.0205 | 0.0066 | 50.73% | 205 | 6 |

| valid | 0.0239 | 0.1179 | 0.0207 | 54.76% | 84 | 6 |

| test | sealed（未揭示） |  |  |  |  |  |



ICIR 未年化；h>1 时标签重叠，日度 IC 不独立。



### 6.2 理论分组收益（毛收益，不含成本、不考虑成交——不是可交易收益）



| 样本段 | G0 | G1 | G2 | G3 | G4 | G0−G末 | 单调性 |

|---|---|---|---|---|---|---|---|

| train | -0.0027 | 0.0023 | 0.0009 | 0.0003 | -0.0017 | -0.0010 | -0.0273 |

| valid | -0.0045 | 0.0030 | -0.0000 | 0.0005 | -0.0045 | -0.0000 | 0.0298 |



组收益为每个信号日的 5 日持有期毛收益均值。



### 6.3 因子衰减（仅训练+验证段）



| 持有期 | RankIC 均值 | IC 均值 | 有效日数 | 约独立样本 |

|---|---|---|---|---|

| 1 | -0.0030 | -0.0010 | 299 | 299.0 |

| 5 | 0.0083 | 0.0075 | 295 | 59.0 |



### 6.4 分布与覆盖



- 平均缺失率 1.63%，最大 100.00%；异常值 1 个（robust z > 5.0）；inf 0 个。

- 覆盖率均值 98.37%，最低 0.00%，低于 80.00% 的天数 5（最长连续 5 天）。



## 7. 策略参考回测（可交易收益估计）



**未生成可交易收益结论**：没有可用的回测结果。上文的理论分组收益不能替代账户收益。



## 8. 图表与数据依据



!逐日 RankIC 与 20 日均值；虚线为验证段起点（原内部附件未公开）



*逐日 RankIC 与 20 日均值；虚线为验证段起点。数据：`fig_rank_ic.csv`，来源产物 `art:85d179860c67`。*



!理论分组累计毛收益（非重叠复利，不可交易）（原内部附件未公开）



*理论分组累计毛收益（非重叠复利，不可交易）。数据：`fig_groups.csv`，来源产物 `art:85d179860c67`。*



!因子衰减（原内部附件未公开）



*因子衰减。数据：`fig_decay.csv`，来源产物 `art:8b6d1e85df39`。*



## 9. 诊断



- 未来函数检查：通过（factor values up to each cutoff do not depend on later data；2023-10-30: 0 格变化, 2024-03-04: 0 格变化）。

- 证据评估：**insufficient**

  - 不足：no backtest result: no tradable-return conclusion



## 10. 失败实验与异常



无失败调用。



- 研究警告：labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5



## 11. 局限与未验证事项



- 数据为合成数据，结论不外推到任何真实市场。

- 参考账本不建模冲击成本、订单簿、公司行动和退市清算；费用为参数。

- IC 统计未做重叠修正或多重检验校正。

- 正式回测引擎、真实停牌/涨跌停数据和分钟执行价格尚未接入。

- 报告不完整或证据不足：不得据此得出可交易结论。



## 12. 可复现信息



```json

{

  "spec_fingerprint": "7579c465a177534b3f72c343ee51297c15d0032eedb44729c8c44f13343f3c95",

  "data_sha256": {

    "data:open": "2d682b0309ced82ec7bf243c61981b986b5cc6a45c60277664bcac76571cbae6",

    "data:close": "e8c60c74ae983c1b56396d24d17d5bae58a3a02cd1f97d0d67332a77e6af5357",

    "data:volume": "688a65c89da10b348ea46e7870cdc56b7a791ed08ef1d9c5b2e5e820840061ed"

  },

  "artifacts": {

    "evaluation": "art:c495e64324f7",

    "decay": "art:8b6d1e85df39"

  },

  "python": "3.12.4",

  "pandas": "2.3.3",

  "numpy": "1.26.4",

  "qrtk": "0.2.0",

  "study_id": "INTERNAL_RUN_ID_REDACTED:ab32bbd950fe4fcd",

  "source_file_sha256": "43af39978676e44bc4e20e6f982a307d902e42c05261935107497b56ef7a0901",

  "limitations": [

    "synthetic only",

    "labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5",

    "test is sealed; no independent test claim",

    "IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores",

    "group returns are gross, equal weight, missing labels excluded; not account returns",

    "no industry/size neutralisation, HAC or multiple-testing adjustment",

    "positive observed volume is sample eligibility, not permission to buy/sell",

    "all parameter changes after seeing validation are exploratory; no certified out-of-sample performance"

  ]

}

```



## 13. 后续研究建议



- 补齐数据口径与更长历史，独立检验；此处不宣称可交易。

