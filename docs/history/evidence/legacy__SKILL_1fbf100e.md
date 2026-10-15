> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

---
name: factor_research
description: 在冻结的研究参数下评价横截面因子：IC、RankIC、ICIR、分层收益、衰减、换手、覆盖率与稳定性；严格区分预测性、理论分组收益和可交易收益。
---

# factor_research

## 什么时候用

- 有一个明确定义的因子（T 日收盘后可以计算），要判断它是否预测未来横截面收益。
- 比较同一因子在训练、验证、测试段的表现。

**不适用：** 估计账户收益（用 strategy_backtest），在看过结果后挑方向或挑参数（这是禁止的做法）。

## 需要的输入

- `factor`：日期 × 股票的因子面板，`data:` 引用，T 行只使用 T 日收盘前可得的信息。
- `price`：计算未来收益用的价格面板，必须包含每一个交易日。日频策略通常用复权开盘价，与"T+1 开盘执行"一致。
- `spec`：**在看任何结果之前冻结**的研究参数：因子名、方向（+1、−1 或 `"train"`）、持有期、lag、分组数、训练/验证/测试三段日期、执行规则名。修改任何一项都会得到不同的 spec 指纹。
- 可选：`universe`，T 日已知的股票池。

## 工具（计算全部来自 qrtk，不重新实现）

| 工具 | 用途 |
|---|---|
| `factor.evaluate` | `qrtk.evaluate_splits`：每段的 IC/RankIC 汇总、理论分组收益、单调性、覆盖率、purge 日数和警告。测试段默认封存 |
| `factor.decay` | `qrtk.multi_horizon`：只用训练和验证段数据，比较各持有期的 RankIC |
| `factor.profile` | `qrtk.factor_distribution` 与 `coverage_stability`：缺失、异常值、分位数、覆盖稳定性 |

## 工作流程

1. 先由 data_research 确认数据可用。
2. 冻结 spec，记录指纹。
3. `factor.profile`：分布和覆盖率有问题时先解释原因。
4. `factor.evaluate`，保持 `reveal_test=false`：查看训练段和验证段。
5. `factor.decay`：只作描述，不据此改动已冻结的持有期。
6. 只有在所有参数确定、验证段已经看完之后，才用同一个 spec 调用一次 `reveal_test=true`。

## 怎样解释结果

三类结果分开写，不能互相替代：

| 类别 | 来源 | 能说明什么 | 不能说明什么 |
|---|---|---|---|
| 预测性 | RankIC/IC 均值、ICIR、RankIC>0 的比例 | 因子排序和未来收益排序的关系 | 能不能赚钱 |
| 理论分组收益 | `theoretical_groups`，等权毛收益 | 分组之间的收益差异和单调性 | 可交易收益：没有成本、没有成交约束，也没有资金账本 |
| 可交易收益 | 只能来自 strategy_backtest | 模拟账户在所列假设下的表现 | 不属于本 Skill 的输出 |

- ICIR 不年化。h > 1 时标签相互重叠，有效样本约为 n/h。
- 训练段和验证段 RankIC 方向相反，说明因子不稳定，不能挑方向较好的那一段来报告。
- |RankIC| 异常高（例如 > 0.3）时，先怀疑未来函数，交给 research_diagnostics 检查。

## 停止和拒绝结论的条件

- spec 不合法，或训练、验证、测试段重叠（`SCHEMA_INVALID`）。
- 有效日数太少：evaluate 会给出警告，evidence_review 会判定为 insufficient。这时只报告"证据不足"。
- 不允许看过测试段之后修改 spec 再报告，否则测试段就不再是样本外结果。

## 错误处理

错误码有 `DATA_NOT_REGISTERED`、`DATA_MISSING`、`SCHEMA_INVALID`、`TOOL_FAILED`。失败时不要换别的数据或别的参数重试来"凑出"结果；把失败记录下来，交给报告。

## 与其他 Skill 组合

`factor.evaluate` 输出的 `ref` 和 `series_ref` 会被 research_diagnostics（evidence_review）和 research_reporting 读取。冻结的 spec 原样传给 diagnostics。diagnostics 改动参数做敏感性分析时，只写入它自己的产物，不会覆盖本 Skill 的结果。
