# paper_research 集成契约（v0.3，供主 Agent / Codex 集成使用）

本契约描述主 Agent **可以依赖什么、必须拒绝什么**。工具包不依赖主 Agent，也不修改主 Agent。主 Agent 目前只能执行受控的 19 算子 DSL，**不能**执行任意 Python。

**v0.3 的核心变化**：任务新增 `admission`（准入）。从现在起，"生成了任务 JSON"、"DSL 判为 expressible"、"status=ready_for_review" 都**不等于**可以计算或回测。主 Agent 只能依据 `admission` 做决定。

## 1. 调用链与产物

```text
ingest_document(path, allowed_roots)            -> document   paper_research.document/1.0
extract_research_spec(document)                 -> spec       paper_research.spec/1.0       （A 原文 / B 推断 / C 缺失；extractor 0.3.0）
validate_research_spec(spec, document)          -> {valid, errors, warnings}               （引文逐字核对；解析出的数字须在引文内）
build_research_task(spec, factor=, symbol_map=, choices=)
                                                -> task       paper_research.task/1.1       （新增 admission、data_requirements）
validate_research_task(task, spec)              -> {valid, errors[{code, detail}]}         （确定性重建比对 + 准入一致性）
build_candidate(task[, source=])                -> 不可信候选（只在 admission 允许时）
write_candidate_bundle / verify_candidate_bundle -> 目录 + manifest（SHA-256）
```

所有函数都是纯本地的：不联网，不调用语言模型，不执行文档内容，也不执行候选代码。

对应"读取这篇论文，提取因子，进行测试，输出报告"的用户请求，主 Agent 的标准流程是：

1. `ingest_document` → `extract_research_spec` → `validate_research_spec`（无效则停止）。
2. `build_research_task(spec)`，不传 `factor`：
   - 只有一个与公式关联的因子时，直接选用它；
   - 有多个时，选论文标题点名的那一个，并在 `unresolved` 中记录 `factor selection`（非阻塞）；
   - 都不满足时报错，需要用户选择。
3. 把 `admission` 和阻塞项原样展示给用户，收集宿主选择（`symbol_map`、`choices`）后重建任务。
4. 只按第 3 节的准入规则继续，不能替用户填写任何阻塞项。

## 2. 研究任务 `paper_research.task/1.1` 的关键字段

| 字段 | 含义 | 主 Agent 的用法 |
|---|---|---|
| `admission.state` | 最严重的准入状态（见第 3 节） | **唯一**的准入依据 |
| `admission.states` | 同时成立的全部状态，按严重度排序 | 全部展示给用户 |
| `admission.gates` | `formula / semantics / fields / host_choices / data` 各门的 `status` 和 `blocking_items` | 按门分组展示阻塞项 |
| `admission.permissions` | `may_generate_candidate`、`may_execute_candidate`（恒为 false）、`may_compute_after_human_approval`、`may_backtest`（恒为 false） | 不得越权 |
| `status` | `blocked` 或 `ready_for_review`；任何阻塞项（包括数据认证缺口）都会使它为 `blocked` | 兼容旧接口；不代表准入 |
| `unresolved[]` | `{item, question, blocking, source, gate, related}` | `blocking=true` 原样呈现，不能替用户填写 |
| `factor.symbols[]` | 见下表 | `basis=inference` 必须给用户确认 |
| `factor.timing` | `common_lag_removed`：论文写成 `P_{t-1}/high_{t-1}` 时，公共滞后会被移到标签时点中，因子按观测日索引（推断） | 把它展示给用户，确认建仓滞后 |
| `factor.ir` / `ir_execution` | 论文单位的表达式树 / 宿主换算到日频行之后的版本（标记为偏离原文） | 仅供审计 |
| `data_requirements` | `required`：本因子需要认证的数据属性（复权价格、上市状态、交易状态）；`declared`：宿主声明的数据认证；`status`：`pass` / `fail` / `not_assessed` | 数据层必须逐条证明 |
| `dsl.status` / `dsl.expression` | 与 v0.2 相同 | 仅当 `admission.state == READY_FOR_REVIEW_DSL` 时可用 |
| `reproducibility` | spec_id、文档 SHA、抽取器/构建器/IR 版本、DSL 目录指纹 | 写入实验记录 |

`factor.symbols[]` 的每个元素：

| 键 | 含义 |
|---|---|
| `paper_definition` | 原文定义句（含块 ID） |
| `interpretation` | 定义的解析结果：`kind` 取 `raw`（单一日期的字段）、`window_aggregate`（窗口聚合，例如"12 个月内最高价"）或 `ambiguous`；另有 `aggregate`、`window`、`base`、`sampling`、`adjustment`（adjusted / none / unstated） |
| `field` / `dsl_field` / `basis` | `basis` 取 `paper` / `inference` / `host_choice` / `derived_in_paper` / `missing` |
| `options` | 仅 `window_aggregate` 且宿主未推导时出现：可选的推导方式（例如"日收盘价最大值 / 日内最高价最大值 / 月末价格最大值"），均为建议，**不会自动采用** |
| `derived` / `derivation` | 宿主用 `symbol_map[sym].derive` 给出的推导（论文时间单位）及检查结果 |

### 宿主输入

| 输入 | 格式 | 说明 |
|---|---|---|
| `symbol_map[sym].field` | 字段名 | `adjustment` 取 `backward` / `total_return` / `none`；`deviates_from_paper` + `reason` 表示有意偏离原文 |
| `symbol_map[sym].derive` | LaTeX | 使用**论文的时间单位**；工具包会核对聚合方式和窗口长度（误差超过 10% 即阻塞） |
| `choices.data_certification` | `{source, level, fields[], certified{adjusted_prices, listing_status, trading_status}}` | GPUShare 当前应声明为：level `PROFILED_EXPLORATORY_ONLY`，fields 为六个字段，certified 三项全部为 false |
| `choices.horizon` / `splits` | 与 v0.2 相同 | 宿主的显式选择会把论文中"多个持有期 / 多套样本划分"的歧义转为已记录的宿主决定 |

## 3. 准入状态（从最严重到最宽松）

| 状态 | 含义 | 主 Agent 可以做什么 |
|---|---|---|
| `SEMANTICS_UNRESOLVED` | 公式未复原（FORMULA_UNRESOLVED）、无法解析，或论文关键语义未定：窗口聚合输入未推导、宿主映射与原文冲突、聚合方式或窗口不符、定义缺失 | 只能向用户提问；不得生成候选，不得计算 |
| `MISSING_FIELDS` | 声明的数据源没有发布所需字段 | 报告缺口 |
| `HOST_DECISION_REQUIRED` | 需要宿主做出实质性选择：复权口径、标签时点、预测期、样本划分、股票池、频率换算 | 向用户收集选择 |
| `DATA_UNCERTIFIED` | 没有声明数据认证，或声明的数据源不能证明所需属性 | 可以生成候选（如果允许），但不得计算 |
| `CANDIDATE_ONLY` | 语义清楚，但 DSL 无法表达：只能生成不可信候选，不能执行 | 调用 `build_candidate`；产物交给另行批准的执行环境 |
| `READY_FOR_REVIEW_DSL` | 所有门通过，DSL 可表达，数据已认证 | 人工审批后，可以把 `dsl.expression` 交给 `qrtk_expression_study` |

`may_compute_after_human_approval` 只在 `states == ["READY_FOR_REVIEW_DSL"]` 时为 true。`may_execute_candidate` 和 `may_backtest` 恒为 false：回测是宿主的独立决定，任务不授予这项权限。`validate_research_task` 遇到被篡改的权限，会返回 `ADMISSION_INVALID`。

## 4. 字段语义保护（P1）

- 定义中出现窗口和聚合（"highest price … during the 12-month period"、"过去250个交易日的最高价"）时，该输入判为 `window_aggregate`，**永远不会**被推断映射到当日的 `high`、`low`、`close` 字段。
- 宿主把它映射到单一日期字段，或用不同的聚合（如 mean 代替 max）、不同长度的窗口推导，都会以 `source=conflict` 阻塞。只有标记 `deviates_from_paper` 并给出理由，才会作为有记录的偏离放行。
- 价格在不同日期之间比较时（包括窗口聚合价格），必须声明复权：
  - 论文写了复权、宿主未选 `backward` → 阻塞；
  - 论文没写、宿主未选或选了 `none` → 阻塞（`HOST_DECISION_REQUIRED`）。
- 金额与成交量分开识别："volume in dollars"、"dollar volume"、"成交额" 映射为 `amount`，不会映射为股数 `volume`。

## 5. 公式、结果与表格（P0 / P2）

- **公式**：
  - 带分数线的叠放分式按版面复原为 `\frac{…}{…}`，上下标复原为 `_{…}` / `^{…}`（`source_kind = pdf_layout_fraction`，并带 `layout.regions` 页面区域）。
  - 不能可靠复原的公式记为 `status=unresolved`，并生成 C 项 `code=FORMULA_UNRESOLVED`（含页码和区域）。这类情况包括：没有分数线的叠放碎片，以及数学字体字形映射错误（如 Elsevier Adv 字体把 `=` 显示为 `¼`）。
  - 涉及所选因子的 `FORMULA_UNRESOLVED` 一律阻塞。
- **正文结果** `A_supported.reported_results[].results[]`：
  - 字段：`value`（逐字）、`number`（带符号，能识别 en-dash 和 Unicode 负号）、`unit`、`metric_normalized`、`t_stat`、`review`（`auto_parsed` / `needs_review`）、`verification`（恒为 `unverified`）。
  - 引用其他文献的句子标为 `attribution=cited_literature` 并要求复核；负号字形无法解码时标 `sign_unresolved`，`number=null`。
- **表格** `spec.table_results[]`：无框线表格和横排表格从文字坐标重建。每个单元格都有页面坐标和 `verification=unverified_layout_parse`；只有结构完整、语义明确、符号已解码的单元格才是 `auto_parsed`。
- `auto_parsed` **不是**"已验证"。论文数字只能用来对照，不能当作目标，也不能用来调参。

## 6. 候选实现（不可信产物）

与 v0.2 相同，另加一条：`build_candidate` 先检查 `admission`，`formula` 或 `semantics` 门未通过时拒绝。产物以 `candidate.py.txt` 保存，`manifest.status = UNTRUSTED_NOT_EXECUTED`，`promote_candidate` 总是拒绝。本包不提供、也不声称提供安全沙箱。**静态检查通过不代表代码正确。**

## 7. 错误码（新增）

| 位置 | 错误码 |
|---|---|
| 规格 C 项 | `FORMULA_UNRESOLVED`（带 `page`、`region`） |
| 任务校验 | `ADMISSION_INVALID`，以及 v0.2 的全部错误码 |
| 其余 | 见 v0.2：`UNSUPPORTED_*`、`FIELD_NOT_IN_DSL`、`WINDOW_ABOVE_LIMIT`、`FREQUENCY_MISMATCH`、`REBUILD_MISMATCH` 等 |

## 8. 版本

- 任务结构 `paper_research.task/1.0` → `1.1`：新增必需字段 `admission` 和 `data_requirements`，读取方遇到 1.0 任务应重建。
- 抽取器 0.3.0、构建器 0.2.0、包版本 0.3.0；文档和规格的结构版本不变。
- DSL 目录指纹 `dsl.catalog_sha256` 一旦与主 Agent 实际使用的 DSL 不一致，所有 `expressible` 判断都要重新计算。
