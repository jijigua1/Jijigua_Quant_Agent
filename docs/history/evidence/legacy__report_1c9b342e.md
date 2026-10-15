> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子探索性研究：reversal

报告状态：**incomplete**；证据评估：**insufficient**。 缺少：backtest。

## 1. 研究问题与假设

- 问题：研究五日反转因子：在已批准的历史日频研究样本上，计算5日反转因子（基于过去5日收益的反转信号），检验其IC/RankIC、分组毛收益，并生成完整分析报告（含图表与Markdown/HTML报告）。需先查询可用研究样本资源，再执行因子研究。
- 假设：direction +1 fixed; reversal; lookback=5

## 2. 数据来源与时间范围

| 数据 | 来源 | 合成 | 范围 | 行×列 | 缺失率 | 观察时点 | 质量 | SHA-256 |
|---|---|---|---|---|---|---|---|---|
| data:open | GPUShare published recent_days TRD_Dalyr.csv; reviewed production Tushare field conversion, some mixed-source publication | 否 | 2026-07-03 ~ 2026-10-09 | 65×50 | 2.68% | after T close; historical per-row fetched_at not fully verified; trade date is not availability time | ok | 2ca85ef86468 |
| data:close | GPUShare published recent_days TRD_Dalyr.csv; reviewed production Tushare field conversion, some mixed-source publication | 否 | 2026-07-03 ~ 2026-10-09 | 65×50 | 2.68% | after T close; historical per-row fetched_at not fully verified; trade date is not availability time | ok | 65c90a23a380 |
| data:volume | GPUShare published recent_days TRD_Dalyr.csv; reviewed production Tushare field conversion, some mixed-source publication | 否 | 2026-07-03 ~ 2026-10-09 | 65×50 | 2.68% | after T close; historical per-row fetched_at not fully verified; trade date is not availability time | ok | 565fa193ffc5 |


## 3. 因子与策略定义

- 因子：`reversal`；方向 1（来源：fixed）；分组 5，group 0 为方向调整后最好的一组。
- 策略：未生成订单计划；执行规则 `next_observed_open`。

## 4. 方法与时间语义

- 因子在 T 日收盘后可观察；标签 = price[T+1+5] / price[T+1] − 1。
- 每个样本段只使用信号日和标签出场日都在段内的日期（purge），段与段之间没有标签重叠。
- 订单在信号日之后的下一交易日执行；估值用收盘价，成交价与估值价是两个输入。
- 三类结果分开报告：预测性（IC/RankIC）、理论分组收益（毛收益，不可交易）、参考账本收益（在所列假设下的可交易收益估计）。

## 5. 实验参数（实验前冻结）

- spec 指纹：`0183d32c9a443549a6858d78d3d04fa75512a1e1bdba774e90af936ad22750b3`

| 参数 | 值 |
|---|---|
| factor_name | reversal |
| direction | 1 |
| horizon | 5 |
| train | ['2026-07-03', '2026-08-26'] |
| valid | ['2026-08-27', '2026-09-17'] |
| test | ['2026-09-18', '2026-10-09'] |
| lag | 1 |
| n_groups | 5 |
| min_obs | 10 |
| universe_name | fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe |
| execution_rule | next_observed_open |
| min_dates_per_split | 60 |

## 6. 因子研究结果

### 6.1 预测性（IC / RankIC）

| 样本段 | RankIC 均值 | RankICIR | IC 均值 | RankIC>0 比例 | 有效日数 | purge 日数 |
|---|---|---|---|---|---|---|
| train | 0.0257 | 0.0988 | 0.0498 | 57.14% | 28 | 6 |
| valid | 0.1498 | 0.8826 | 0.1568 | 70.00% | 10 | 6 |
| test | sealed（未揭示） |  |  |  |  |  |

ICIR 未年化；h>1 时标签重叠，日度 IC 不独立。

### 6.2 理论分组收益（毛收益，不含成本、不考虑成交——不是可交易收益）

| 样本段 | G0 | G1 | G2 | G3 | G4 | G0−G末 | 单调性 |
|---|---|---|---|---|---|---|---|
| train | 0.0042 | 0.0052 | 0.0142 | 0.0110 | -0.0100 | 0.0142 | 0.0464 |
| valid | -0.0092 | -0.0144 | -0.0116 | -0.0150 | -0.0301 | 0.0210 | 0.3500 |

组收益为每个信号日的 5 日持有期毛收益均值。

### 6.3 因子衰减（仅训练+验证段）

| 持有期 | RankIC 均值 | IC 均值 | 有效日数 | 约独立样本 |
|---|---|---|---|---|
| 1 | 0.0404 | 0.0171 | 48 | 48.0 |
| 5 | 0.0331 | 0.0293 | 44 | 8.8 |

### 6.4 分布与覆盖

- 平均缺失率 9.42%，最大 100.00%；异常值 44 个（robust z > 5.0）；inf 0 个。
- 覆盖率均值 90.58%，最低 0.00%，低于 80.00% 的天数 5（最长连续 5 天）。

## 7. 策略参考回测（可交易收益估计）

**未生成可交易收益结论**：没有可用的回测结果。上文的理论分组收益不能替代账户收益。

## 8. 图表与数据依据

!逐日 RankIC 与 20 日均值；虚线为验证段起点（原内部附件未公开）

*逐日 RankIC 与 20 日均值；虚线为验证段起点。数据：`fig_rank_ic.csv`，来源产物 `art:0626636b5b09`。*

!理论分组累计毛收益（非重叠复利，不可交易）（原内部附件未公开）

*理论分组累计毛收益（非重叠复利，不可交易）。数据：`fig_groups.csv`，来源产物 `art:0626636b5b09`。*

!因子衰减（原内部附件未公开）

*因子衰减。数据：`fig_decay.csv`，来源产物 `art:84861880b194`。*

## 9. 诊断

- 未来函数检查：通过（factor values up to each cutoff do not depend on later data；2026-08-26: 0 格变化, 2026-09-17: 0 格变化）。
- 证据评估：**insufficient**
  - 不足：train: 28 RankIC dates < 60
  - 不足：valid: 10 RankIC dates < 60
  - 不足：no backtest result: no tradable-return conclusion

## 10. 失败实验与异常

无失败调用。

- 研究警告：labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5
- 研究警告：train: only 28 valid RankIC dates (< 60)
- 研究警告：valid: only 10 valid RankIC dates (< 60)

## 11. 局限与未验证事项

- 结果只覆盖所列数据与区间，未做真实市场验证。
- 参考账本不建模冲击成本、订单簿、公司行动和退市清算；费用为参数。
- IC 统计未做重叠修正或多重检验校正。
- 正式回测引擎、真实停牌/涨跌停数据和分钟执行价格尚未接入。
- 报告不完整或证据不足：不得据此得出可交易结论。

## 12. 可复现信息

```json
{
  "spec_fingerprint": "0183d32c9a443549a6858d78d3d04fa75512a1e1bdba774e90af936ad22750b3",
  "data_sha256": {
    "data:open": "2ca85ef8646842a42711e65adbdb54d7c5460b36c7ac2d2c0ef33adfd8f5eea6",
    "data:close": "65c90a23a380719db2ba8041b2151dc49ddb589b09516cc729c8270a60914692",
    "data:volume": "565fa193ffc5266df8141a28bf6f974aad44144cff22e016eda27804f6f4d309"
  },
  "artifacts": {
    "evaluation": "art:fd76c97dc66d",
    "decay": "art:84861880b194"
  },
  "python": "3.11.10",
  "pandas": "2.3.3",
  "numpy": "1.26.4",
  "qrtk": "0.2.0",
  "study_id": "INTERNAL_RUN_ID_REDACTED:ca951799d1b24473",
  "source_file_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
  "limitations": [
    "only 65 observed dates, each train/validation segment may have fewer than 60 mature labels",
    "unadjusted prices: corporate actions can distort returns; no strategy efficacy claim",
    "observed date union is not independently verified exchange calendar",
    "historical availability, suspension, limits, delisting and full universe not fully verified",
    "labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5",
    "train: only 28 valid RankIC dates (< 60)",
    "valid: only 10 valid RankIC dates (< 60)",
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
