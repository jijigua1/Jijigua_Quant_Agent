> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

---
name: research_diagnostics
description: 检查未来函数、参数敏感性、训练/验证/测试隔离、样本外表现和证据是否充分；不得事后挑选最好的方向、窗口或参数。
---

# research_diagnostics

## 什么时候用

- 因子或策略结果"好得不正常"时，例如 |RankIC| 很高、回撤异常小。
- 写报告之前，判断证据能否支撑结论。
- 需要报告结果对参数有多敏感时。

## 需要的输入

- 价格面板，以及在数据目录中登记的**因子构造函数** `data:<builder>`。它的形式为 `builder(price) -> factor`，用于检查未来函数。
- factor_research 使用过的冻结 spec。做敏感性分析时，方向必须是已经确定的 +1 或 −1。
- 上游产物：`factor.evaluate` 的 `ref`；可选 `strategy.backtest` 和 `diag.lookahead_check` 的 `ref`。

## 工具

| 工具 | 用途 |
|---|---|
| `diag.lookahead_check` | 在多个截止日把价格截断后重新构造因子：截止日及之前的因子值必须完全不变，否则说明用到了未来数据 |
| `diag.sensitivity` | 只用训练段和验证段，在持有期 × 分组数的网格上计算 RankIC 和理论多空收益；标注哪一格是冻结选择。**只用于报告** |
| `diag.evidence_review` | 根据有效日数、训练与验证段的方向是否一致、可疑的高 RankIC、未来函数检查结果、是否有回测，给出 sufficient / insufficient / suspicious |

## 工作流程

1. `diag.lookahead_check`：不通过就**停止**，结果作废，先修因子定义。
2. `diag.sensitivity`：把整张网格写进报告，不要只挑最好的一格。冻结参数不随网格结果改变。
3. 确认训练、验证、测试段的隔离：spec 校验了日期不重叠，evaluate 对跨段标签做了 purge，测试段只揭示一次。
4. `diag.evidence_review`：判定为 insufficient 或 suspicious 时，报告只能写"证据不足"或"结果可疑"，不得写成有效结论。

## 禁止事项

- 用测试段或回测结果去选择方向、持有期、分组数、执行窗口或成本参数，再把这样得到的结果称为样本外。
- 删除不利的样本段或失败的实验。
- 把敏感性网格中最好的一格当作研究结论。

## 停止和拒绝结论的条件

- 未来函数检查不通过。
- 证据评估为 suspicious：先排查原因，不要报告收益。
- 证据评估为 insufficient：可以报告，但必须标明"证据不足"，并说明缺了什么。

## 错误处理

错误码有 `SCHEMA_INVALID`（例如敏感性分析时方向还没有确定）、`ARTIFACT_NOT_FOUND`、`DATA_NOT_REGISTERED`、`TOOL_FAILED`。诊断工具自身失败时，也要写进报告的"失败实验与异常"一节。

## 与其他 Skill 组合

本 Skill 只读取其他 Skill 的产物，不修改它们；敏感性分析的结果放进本 Skill 自己的产物，不会改变 factor_research 的 spec 或结果。
