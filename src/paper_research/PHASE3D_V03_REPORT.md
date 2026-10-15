# Phase 3-D v0.3：真实量化论文理解能力修复 — 最终报告

日期：2026-10-13。范围：`<LOCAL_RESEARCH_ROOT>\quant_toolkit\paper_research` 及其测试、示例和文档。

本轮工作的边界：

- 没有修改 ResearchAgent、GPUShare、`backtest.ipynb` 或 `core_backtest`；
- 没有读取任何行情数据，没有访问 2026 Holdout；
- 没有执行任何候选代码，没有新增依赖，也没有自动操作 Codex。

v0.2 的真实论文验收基线（`reports/paper_research/real_george_hwang_2004/` 下的 `auto/`、`corrected/`、`scoring/` 和报告）保持原样：这些文件的最后修改时间都早于 v0.3 工作开始。旧验收脚本已加上版本保护，无法再覆盖它们。

## 0. 结论

| 判断 | 结论 |
|---|---|
| George & Hwang 2004（原验收论文） | **部分支持，且从"静默错误"变成"正确理解或明确阻断"**。核心公式由版面自动复原；`high` 被正确识别为 12 个月最高价（窗口聚合），在宿主选定价格口径前任务一直阻塞；结果和表格的放行错误降为 0。 |
| Amihud 2002（外部验证，不同排版） | **阻断正确**。公式 (1) 的文字层字形错码，被识别为 `FORMULA_UNRESOLVED`，没有放行错误公式；人工重述一处后可以生成任务和候选。表格中无法解码的负号被扣留，没有被当成正数。正文结果放行了 1 个错误数字（作者的举例，不是研究结果）。 |
| 错误因子静默放行 | **0 次**。v0.2 中"`high` 映射到当日最高价 → 判为可表达 → 可送审"的路径已关闭；均值代替最大值、缩短窗口、不复权三种变体也都被阻断，或被要求由宿主做决定。 |
| A 股复现 | **NOT_RUN**。所有任务的 `may_compute_after_human_approval=false`、`may_backtest=false`。GPUShare 的六个字段属于 PROFILED_EXPLORATORY_ONLY，复权价格、上市状态、交易状态都没有认证，准入停在 `DATA_UNCERTIFIED`。 |
| 测试 | **232 passed**：原 209 项 + 新增 23 项回归测试。原有测试只改了一处断言（见第 6 节）。 |

## 1. 四类问题怎么修的（全部是通用规则，没有针对论文硬编码）

### P0 公式漏抽与数学语义（`layout_math.py`、`ingest_pdf.py`、`document.py`、`factor_ir.py`）

- **上下标**：按"比主体字号小，且基线相对**前一个主体字**更低或更高"的规则，写成 `_{…}` / `^{…}`。基线按局部比较，所以同一行多条基线的展示公式（GH p18 的 `R_t = V_{t−1}(1−V_t)P_{t−1}+…`）也能正确复原。
- **叠放分式**：PDF 中长 4–180pt、高不超过 1.2pt 的矢量横线视为分数线。线上方和下方、落在线宽范围内的文字分别是分子和分母，复原为 `\frac{…}{…}`，并按位置插回所在句子；被拆散的句子会重新接起来。GH 的核心公式 `\frac{P_{i,t-1}}{high_{i,t-1}}`（p5）以及 p7 的同一公式都复原了，分母定义也能从同一句话中读到。
- **明确阻断**：以下几种情况记为 `FORMULA_UNRESOLVED`，附页码和区域，并阻塞涉及的因子：
  - 分数线只有一侧有文字；
  - 没有分数线的小字号叠放碎片；
  - 数学字体解码成 `¼ ð Þ þ` 或控制字符（字形错码）。
- **脚注分隔线**：脚注分隔线不再被当成分数线（Amihud 中出现过误判）。
- **后备检查**：块末尾是 "ranked based on / defined as …" 而后面没有公式时，生成 `FORMULA_UNRESOLVED` 的 C 项。
- **修复 v0.2 的 bug**：`parse_formula` 在 `\sum_{k=0}` 的下标处误切等号，导致没有左边的窗口表达式无法解析。

### P1 字段映射与因子语义保护（`task.py`）

- 用 `interpret_definition` 解析每个符号定义里的聚合方式、窗口、基础量、取样点和复权：
  - 窗口聚合（`window_aggregate`）永远不会推断为单一日期字段；
  - 只有出现聚合词、没有窗口时判为 `ambiguous`；
  - 当日最高价、"日内"等表述才映射为 `high`。
- 宿主推导（`symbol_map.derive`，使用论文时间单位）会被核对聚合方式和窗口长度（容差 10%）。不一致即阻塞，除非显式标记 `deviates_from_paper` 并给出理由。
- 价格在不同日期之间比较时（包括窗口聚合价格），必须声明复权。
- 所有输入共用同一个滞后时（例如 `P_{t−1}/high_{t−1}`），把滞后移到标签时点，因子按观测日索引；记录在 `factor.timing`，标为推断。
- "volume in dollars" 映射为 `amount`，不再当作股数 `volume`（外部验证时发现的同类陷阱）。

### P2 结果与表格（`numbers.py`、`tables_text.py`、`extract.py`）

- **数字**：能识别 en-dash、Unicode 负号和 `−(15.22)` 写法；控制字符 + 数字时标 `sign_unresolved`，数值置空，不猜正负号。
- **指标**：
  - 按完整单词匹配，"which" 不再被当作 IC；
  - 没有指标词时，只在对比句中从已放行的前一个数字继承；
  - 买卖价差单独标注；
  - 句中引用他人文献时标 `cited_literature`，要求复核；
  - 组合参数（"top 30% of stocks"、"30% of top performing"）和方法参数（"is assigned"）跳过。
- **表格**：在表题下方，用行聚类加数字右对齐列聚类重建表格，支持：
  - 跨列分组表头、层级行标签；
  - 行内 t 值（"0.46% (2.15)"）和单独的 t 值行；
  - 占位符（"–"、"<−100%"）；
  - 横排表格（坐标旋转后同样处理）。

  每个单元格都带页面坐标，并标为 `unverified_layout_parse`。
- **复核标记**：只有结构完整、表题语义明确、负号已解码的单元格是 `auto_parsed`，其余为 `needs_review`。
- **修复 v0.1 的问题**：页边附近反复出现的纯数字被当成页眉页脚删除（横排表格因此丢了一半列）；连字 ﬁ/ﬂ 破坏关键词匹配；引文截断到 400 字后年份校验失败；每个字段最多 6 条导致后文结果被截掉（上限提高到 40）。

### P3 研究任务准入（`task.py`、`candidate.py`）

`admission` 有五道门：formula、semantics、fields、host_choices、data。准入状态从严重到宽松依次为：

```text
SEMANTICS_UNRESOLVED > MISSING_FIELDS > HOST_DECISION_REQUIRED > DATA_UNCERTIFIED > CANDIDATE_ONLY > READY_FOR_REVIEW_DSL
```

权限中 `may_execute_candidate` 和 `may_backtest` 恒为 false。`may_compute_after_human_approval` 只在唯一状态是 `READY_FOR_REVIEW_DSL` 时为 true，这要求宿主声明的数据认证覆盖复权、上市状态和交易状态。`build_candidate` 在公式门或语义门未通过时拒绝生成。

## 2. George & Hwang 2004：新旧版本逐项对照

### 2.1 20 项方法真值（与 v0.2 相同的 20 项）

| 指标 | v0.2 原始自动 | v0.3 原始自动 |
|---|---|---|
| 自动正确 | 7 | **14** |
| 找到但字段归错 | 5 | 1 |
| 部分正确 | 2 | 1 |
| 正确标为不确定或缺失 | 4 | 4 |
| 漏抽（含静默漏抽） | 2（核心公式静默漏抽） | **0** |
| 错误（放行了错误内容） | 0 | 0 |
| **有效自动完成率**（只算 CORRECT，标记不算） | 35% | **70%** |
| 仍需人工 | 13 | 6 |

逐项变化：

- 核心公式 GT03：MISSED_SILENTLY → CORRECT（版面复原）；
- 分母定义 GT04：归错到 signal_timing → CORRECT（窗口聚合，12 个月）；
- 文字定义 GT02、跳月 GT12、Fama–MacBeth GT13：归错 → CORRECT；
- 风险调整截距 GT14、(6,12)/(12,12) 稳健性 GT15：漏抽 → CORRECT；
- 价格口径 GT05：部分 → 正确标记（三种推导选项 + 复权，两者都阻塞）；
- 表格 GT18：只标表题 → CORRECT（65/65 个单元格正确，见 2.3）。

仍需人工的 6 项：

| 项 | 状态 | 原因 |
|---|---|---|
| GT11 | PARTIAL | 6 个月持有期正确；正文中的 1 个月、12 个月等期限被正确列为歧义；6 组重叠持有的结构没有表达 |
| GT17 | 归错 | "长期不反转"这句话仍归在 holding_horizon 下，但不再被解析成期限 |
| GT05 | 正确标记 | 价格口径必须由人决定 |
| GT09 | 正确标记 | 论文没有写筛选条件 |
| GT19 | 正确标记 | 回归方程只剩碎片 |
| GT20 | 正确标记 | 论文没有局限性章节 |

### 2.2 正文中的结果数字

| 指标 | v0.2 | v0.3 |
|---|---|---|
| 9 个关键结果中自动正确 | 3（另有错标 1、符号丢失 1） | **7** |
| 漏抽 | 4 | 2（R02：只有 "profits" 和区间写法；R08：句中没有指标词） |
| 不带复核标记直接放行的数字 | 8 | 25 |
| 放行数字中的错误（逐条人工核对） | **4（错误放行率 50%）** | **0（0%）** |
| 送人工复核的数字 | 0（v0.2 没有复核机制） | 有，例如 MG −0.11% 的指标不明确 |

25 个放行数字的逐条判定见 `v03_acceptance/george_hwang_2004/scoring/scores.json` 的 `released_prose_verdicts`。其中两个数字（1.11%、0.98%）的值正确，但"不含 1 月"这个限定条件没有被结构化。

### 2.3 表格

v0.2 一个表体都没有识别出来。v0.3 重建了 11 个表格（含 7 个横排表）。用 65 个单元格核对，来源是原始文字层和页面渲染图：Table I 全部、Table II 全部、Table V 的截距和 JT 赢家虚拟变量两行，各含估计值和 t 值。结果：**65/65 正确**，包括 −6.29%、(−4.48) 等负号。

### 2.4 因子、IR、DSL、任务

| 项 | v0.2 自动 | v0.3 自动 |
|---|---|---|
| 识别出的因子 | 无 | "52-week high"（按标题从两个候选中选出；另一个是 GH capital gain，记为推断） |
| 公式 / IR | 无 | `\frac{P_{i,t-1}}{high_{i,t-1}}` → `P[t]/high[t]`，公共滞后 1 个月移到标签时点 |
| `high` 的语义 | — | max，窗口 12 个月，价格口径未说明；给出三种推导选项：日收盘价最大值 / 日内最高价最大值 / 月末价格最大值 |
| 自动任务 | 构建失败 | `blocked`；`SEMANTICS_UNRESOLVED`，同时 `HOST_DECISION_REQUIRED`、`DATA_UNCERTIFIED`。阻塞项：`input high`、`price adjustment for P`、标签时点、样本划分、预测期歧义 |
| DSL | — | 论文原意任务：`contract_limit_exceeded`（FREQUENCY_MISMATCH） |

A 股拟复现任务的设计（**我们的设计，不是作者的方法**）：

- 输入：P = 日收盘价，按后复权口径申请；high = `\max_{0≤k≤11} P`（论文单位），每月按 21 个交易日换算，即 252 个日频行；
- 样本划分：训练 2020–2023，验证 2024–2025，2026 年封存；
- 数据声明：GPUShare 六个字段，PROFILED_EXPLORATORY_ONLY。

结果：

- 准入为 `DATA_UNCERTIFIED + CANDIDATE_ONLY`，三项数据认证缺口全部阻塞；
- DSL 为 `requires_new_implementation`：缺少 rolling_max；即使有这个算子，252 行也超过窗口上限 60 和历史上限 120；
- 候选代码 `candidate_ashare_PTH` 已生成：静态检查通过，最大滞后 251，`UNTRUSTED_NOT_EXECUTED`；生成过程中执行陷阱调用次数为 0，哨兵文件不存在，指纹校验通过。

陷阱探针（`tasks/trap_probes.json`）：

| 宿主的错误做法 | v0.2 | v0.3 |
|---|---|---|
| `high` 映射到当日最高价 | ready_for_review + expressible（**放行了错误因子**） | blocked，`SEMANTICS_UNRESOLVED`，拒绝生成候选 |
| 用 12 期均值代替最大值 | 没有检查 | blocked，聚合方式冲突 |
| 窗口缩短到 3 个月 | 没有检查 | blocked，窗口冲突 |
| 用不复权的收盘价 | 没有检查 | blocked，`HOST_DECISION_REQUIRED`（可以生成候选，不可计算） |

### 2.5 三层结果分开报告

| 层 | 内容 |
|---|---|
| 作者报告的结果 | 与 v0.2 报告相同（R01–R09 和表格数值），见 `scoring/ground_truth.json` |
| 工具包是否正确抽取和引用 | 见 2.2 和 2.3 |
| 我们的 A 股复现 | **NOT_RUN**：没有 IC、RankIC、收益率、Sharpe 或任何回测指标 |

## 3. 外部验证：Amihud (2002)

### 3.1 来源

| 项 | 值 |
|---|---|
| 论文 | Journal of Financial Markets 5 (2002) 31–56，"Illiquidity and stock returns: cross-section and time-series effects"，Yakov Amihud |
| DOI | 10.1016/S1386-4181(01)00024-6 |
| 文件 | 26 页；SHA-256 `349823bb…7118b` |
| 获取方式 | 宾夕法尼亚大学公开托管的副本（`https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf`），不是作者主页 |
| 排版 | Elsevier + Acrobat Distiller 4.05，Adv 系列数学字体字形映射错误，展示公式，横排表格。与 GH 完全不同，选它正是为了检验 v0.3 是否对 GH 过拟合 |

### 3.2 14 项方法真值（人工从原文逐条核对）

| 指标 | v0.3 原始自动 | 人工重述 1 处后 |
|---|---|---|
| 自动正确 | 9 | 10 |
| 正确标为不确定 | 3 | 2 |
| 部分正确 | 1（4 项筛选条件找到 3 项） | 1 |
| 漏抽 | 1（年度窗口 D_iy） | 1 |
| 错误放行 | 0 | 0 |
| 有效自动完成率 | 64% | 71% |

- **公式 (1)**：文字层为 `ILLIQ_{iy} ¼ 1=D_{iy} jR_{iyd}j=VOLD_{ivyd}`，求和号和下限都丢失，被正确判为 `FORMULA_UNRESOLVED`。如果按 v0.2 的流程，"`AILLIQ_y ¼ 1=N_y`" 这类公式会被判为 extracted，切开等号后会得到错误的 IR。
- **自动任务**：`blocked`，准入为 `SEMANTICS_UNRESOLVED`（公式不可读），没有 IR，没有候选。
- **人工重述**（`corrected/corrections.json`，单独存放，计数分开）：`ILLIQ = mean_{k=0..249} |R|/VOLD`。论文是按自然年平均、只用 D_iy 个有数据的日子，重述成滚动 250 个交易日窗口属于宿主近似，已标为 B 类。
- **重述后的 A 股拟复现**：
  - R 由后复权收盘价推导，VOLD 映射为 amount（六个字段之一）；
  - 准入为 `DATA_UNCERTIFIED + CANDIDATE_ONLY`；
  - DSL 为 `requires_new_implementation`（成交额不在 DSL 的字段里）；
  - 生成了从未执行的候选 `candidate_ashare_ILLIQ`。

### 3.3 表格与正文结果

- **表格**：重建出 Table 2 的 8 列。逐个单元格核对了 Constant、ILLIQMA、LnSIZE 三行，共 40 个单元格：
  - 7 个负数的负号是无法解码的字形，全部标为 `sign_unresolved`，数值扣留，**没有一个被当成正数**；
  - 整张表因字形错码被标为 partial，所有单元格要求复核，自动正确数为 0。这是保守的结果，代价是 0 自动完成。
- **正文结果**：放行 1 个数字，错误（"0.25%" 是作者对最小报价单位的举例，不是研究结果）。另有 9 个送人工复核，包括 3 个引用其他文献的买卖价差。错误放行率 1/1，这是本轮发现但**未修复**的剩余问题。

## 4. 错误案例分析

### 公式

| # | 案例 | v0.2 | v0.3 |
|---|---|---|---|
| F1 | GH p5：分式被拆到两个文本块 | 静默漏抽 | 按分数线复原 |
| F2 | GH p7：分母被文字层归入下一行正文 | 判为 unresolved | 识别正文行中的小字号片段，复原成功 |
| F3 | 只有一侧有文字的分数线 / 没有分数线的叠放碎片 | — | 标记 `FORMULA_UNRESOLVED` 并附区域（合成 PDF 测试） |
| F4 | Amihud：脚注分隔线被当成分数线 | — | 识别"短线 + 脚注编号 + 正文"的模式后跳过 |
| F5 | Amihud：Adv 字体字形错码 | 判为 extracted，会生成错误的 IR | 标记 `FORMULA_UNRESOLVED`，阻塞任务 |
| F6 | GH p18：同一行多条基线，下标被误判为上标 | — | 改为按局部基线判断 |
| F7 | `parse_formula` 在下标 `k=0` 处误切等号 | 报错 | 只在花括号外切分 |

### 表格

| # | 案例 | v0.2 | v0.3 |
|---|---|---|---|
| T1 | 期刊无框线表格 | 0 张 | 从文字坐标重建 |
| T2 | 横排表格（GH 有 7 张） | — | 旋转坐标后同样重建 |
| T3 | 页边数字被当作页眉页脚删除 | v0.1 起就存在 | 只把含字母的重复文本或页码当作页眉页脚 |
| T4 | 负号是未解码字形 | 会当成正数 | 标 `sign_unresolved`，数值扣留 |
| T5 | 行内 t 值、层级行标签、跨列表头 | — | 按位置正确归属 |
| T6 | 表题说明里出现数字（"1% tails"）被当成第一行数据 | — | 文字占多数的行不算数据行 |
| T7 | 剩余问题 | — | 表头偶尔混入表题说明文字；表格出现字形错码时整表要求复核 |

### 正文结果

| # | 案例 | v0.2 | v0.3 |
|---|---|---|---|
| R1 | "which" 被匹配成 IC | 错标 | 按完整单词匹配 |
| R2 | –0.15% 用的是 en-dash | 符号丢失 | 正确识别负号 |
| R3 | "greater than 0.38% for JT" 句中没有指标词 | 错标 | 从对比句的上一个已放行数字继承指标 |
| R4 | "30% of top performing stocks" | — | 识别为组合参数，跳过 |
| R5 | 引用他人文献的数字、买卖价差 | — | 标记并送复核 |
| R6 | 剩余问题 | — | Amihud 的举例数字被放行；没有指标词的句子仍然漏抽；限定条件没有结构化 |

### 研究任务状态

| # | 案例 | v0.2 | v0.3 |
|---|---|---|---|
| S1 | `high` → 当日最高价 | 判为可表达并可送审 | SEMANTICS_UNRESOLVED |
| S2 | 用均值代替最大值、缩短窗口 | 没有检查 | 阻塞 |
| S3 | 不复权价格跨日期比较 | 没有检查 | HOST_DECISION_REQUIRED |
| S4 | 数据缺口不影响状态（v0.2 报告中的 P1） | ready_for_review | 声明 GPUShare 后进入 DATA_UNCERTIFIED 并阻塞；不声明数据认证时也只到 DATA_UNCERTIFIED |
| S5 | "volume in dollars" | 映射为股数 volume | 映射为 amount |
| S6 | 论文同时写了 6 个月和 12 个月持有期 | 永久阻塞 | 宿主显式选择后，记录为宿主决定 |
| S7 | 多个公式关联的因子 | 只能报错，要求指定 | 按论文标题自动选择并记录为推断；标题没有点名时仍要求指定 |

## 5. 可供 Codex 集成的接口

见更新后的 [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md)，其中第 1 节给出"读取论文 → 提取因子 → 测试 → 报告"的标准流程，第 3 节是准入规则。Codex 集成时必须遵守的要点：

1. 只看 `admission.state`，不看 `status`、`dsl.status` 或"任务已生成"。
2. `inference` 的映射、`window_aggregate` 的推导选项、`FORMULA_UNRESOLVED` 的页码和区域，都要原样展示给用户。
3. 数据层提供 `data_certification`；GPUShare 当前只能声明 PROFILED_EXPLORATORY_ONLY。
4. 结果数字中只有 `auto_parsed` 可以当作对照参考，且始终是 `unverified`。
5. 候选代码只能交给另行批准的执行环境。

## 6. 测试

| 项 | 结果 |
|---|---|
| 全量测试 | **232 passed**（`-W error::FutureWarning`），见 TEST_REPORT.md（未公开的原内部附件） |
| 新增 `tests/test_paper_v03.py`（23 项） | 合成 PDF 的分式复原和无分数线阻断；裸窗口公式解析；字形错码；7 种定义语义；窗口输入的阻塞与三种陷阱；不复权跨期价格；负号、指标与参数；52 周不是持有期；无框线表格的数值、符号和 t 值；连字、未解码负号、引用、组合参数；页边数字不被删除；宿主选择消除歧义；准入状态与权限篡改；候选只读状态与公共滞后；两篇真实论文的只读检查 |
| 原有 209 项 | 全部通过 |
| 修改的原有断言（1 处） | `test_real_paper_read_only` 原来断言"无框线表格只报告表题"。v0.3 会重建这些表格，所以改为断言"重建的表格被标为 suspect/text_layout，且每个单元格逐字出现在该页 PDF 文本中"，原意"报告而不编造"保留，并且更严格 |

## 7. 交付物

| 内容 | 位置 |
|---|---|
| 代码（新增） | `paper_research/layout_math.py`、`numbers.py`、`tables_text.py` |
| 代码（修改） | `ingest_pdf.py`、`document.py`、`extract.py`、`task.py`、`candidate.py`、`factor_ir.py`、`formulas.py`、`common.py`、`__init__.py`（0.3.0） |
| 测试 | `tests/test_paper_v03.py`；`tests/test_paper_research.py`（改了 1 处断言） |
| 验收脚本 | `examples/real_paper_v03_acceptance.py`（新增）；`examples/real_paper_gh2004_acceptance.py`（加了版本保护） |
| GH 验收产物 | `reports/paper_research/v03_acceptance/george_hwang_2004/`：`auto/`、`tasks/`、`factor_ir.json`、`dsl_diagnostics.json`、`candidate_ashare_PTH/`、`scoring/` |
| Amihud 验收产物 | `reports/paper_research/v03_acceptance/amihud_2002/`：`auto/`、`tasks/`、`corrected/`（含候选）、`scoring/`；PDF 在 `reports/paper_research/real_amihud_2002/source/` |
| 汇总 | `reports/paper_research/v03_acceptance/acceptance_summary.json` |
| 文档 | `paper_research/README.md`、`SCHEMA.md`、`INTEGRATION_CONTRACT.md`、`CHANGELOG.md`、`TEST_REPORT.md`、本报告 |

## 8. 仍需人工的地方与后续建议

- **公式**：图片公式、Type3 字体、没有分数线的多行公式，仍然只能阻断，需要人工重述（Amihud 就是这样）。如果要提高自动化程度，可以引入一个本地的公式识别器，但它的输出同样要经过 `FORMULA_UNRESOLVED` 规则把关。
- **组合规则**：重叠持有、分组比例等组合规则没有结构化，宿主必须在回测层另行定义。
- **正文结果的边界**：没有指标词的结果句会漏抽，举例性质的数字可能被误放行，限定条件没有被结构化。目前只能依赖人工复核。
- **真值规模**：只有两篇论文，真值由单人标注，统计意义有限；建议继续增加带人工真值的真实论文回归集。
- **数据层**：在复权价格、上市状态、交易状态经过认证之前，任何因子都停在 `DATA_UNCERTIFIED`。这是 Phase 3-A 数据工作的范畴，不属于本工具包。
