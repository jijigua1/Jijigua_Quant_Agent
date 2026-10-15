# Phase 3-D：paper_research v0.2 交付报告

日期：2026-10-12。范围仅限 `<LOCAL_RESEARCH_ROOT>\quant_toolkit`。没有修改 `<ARCHIVE_ROOT>`、GPUShare、`backtest.ipynb` 或 `core_backtest`，没有访问任何 Holdout 数据，没有新增依赖，也没有执行任何生成的候选代码。

## 1. 完成的能力

| 优先级 | 能力 | 实现 | 证据 |
|---|---|---|---|
| P0 | 抽取研究假设、经济直觉、因子定义与公式、输入字段、频率、回看窗口、预测期、预处理/标准化/中性化、训练/验证/样本外设计、已报告结果、限制与歧义。每条都逐字溯源，A 原文、B 推断、C 缺失分开记录 | 在 `extract.py` 上增量扩展；`spec.py` 要求解析出的数字和年份必须是引文子串 | 52 周高点文档真值召回 26/26；篡改数字或年份能被发现 |
| P1 | 研究任务中间表示：假设、因子 IR、数据结构、时点约束、输入输出、预热、标签与成熟规则、划分边界、评估指标、限制、未解决事项、复现元数据，以及 JSON + Markdown 输出和带错误码的校验 | `task.py`、`factor_ir.py`、`dsl.py` | 样例：`reports/paper_research/acceptance/week52_md/research_task_PTH.{json,md}` |
| P1 | 19 算子 DSL 兼容性分类，不改变研究定义 | `dsl.compile_ir`：`expressible` / `contract_limit_exceeded` / `requires_new_implementation` / `not_assessed` 四类，每类附准确原因 | 5 个可表达公式的 DSL 计算结果与论文公式的参考求值逐值一致；5 类不可表达原因全部测到 |
| P2 | 候选算法：源码、契约、时间对齐、独立数值测试（期望值来自可信参考求值器）、AST 静态分析、前视/形状/单位/NaN/边界检查、失败报告与修复建议、指纹 | `candidate.py` | 18 类植入缺陷全部检出；能分析外部（例如语言模型）提供的源码；候选不被执行（哨兵文件和 exec/eval/import 陷阱双重验证） |

## 2. 验收（`examples/paper_to_factor_acceptance.py`，详见 ACCEPTANCE.md（未公开的原内部附件））

| 文档 | 因子 | 结果 | 分类 |
|---|---|---|---|
| 52 周高点（Markdown + LaTeX，合成，已知真值） | PTH | 引文全部有效；需要滚动最大值，DSL 没有对应算子；生成了候选，静态分析通过，测试规格 5 项 | **部分支持**：需要经批准的执行环境 |
| Amihud 非流动性（HTML + MathJax，合成） | ILLIQ | 成交额和收益率不在 DSL 的五个字段里；缺失的信号时点、评估指标、样本期都被列为待澄清 | **部分支持**，任务仍有阻塞项 |
| 五日反转（中文 Markdown，合成） | REV5 | 可以映射到 DSL；宿主补齐选择后可转成 `qrtk.ResearchSpec` | **完全支持（DSL）** |
| 合成因子论文（PDF，v0.1 夹具） | MOM、REV | 论文是月频，标为 `FREQUENCY_MISMATCH`，不悄悄换算；宿主按每月 21 天换算后得到 252 天，超出窗口上限，不截短 | 部分支持，任务有阻塞项 |
|  | IVOL | `sum_d` 没有上下界，IR 拒绝解析 | **阻塞**：需要人工重述 |
|  | BETA | 公式字形乱码 | **阻塞** |
| 真实论文 *The Virtue of Complexity in Return Prediction*（本地只读） | SR 等 | 引文有效；97 个公式中多数无法可靠解析；非因子类论文 | **阻塞**：如实报告，没有编造因子 |

测试：全量 **209 passed**，其中新增 44 项，原有 165 项不变，见 TEST_REPORT.md（未公开的原内部附件）。

## 3. 安全边界（已验证）

- 候选源码以 `candidate.py.txt` 文本保存，只经过 `ast.parse`；`manifest.status = UNTRUSTED_NOT_EXECUTED`；`promote_candidate` 总是拒绝。
- 测试里把 `exec`、`eval`、`importlib.import_module`、`runpy.run_path` 都换成会报错的陷阱，候选源码在导入时和调用时都会写哨兵文件。整条流程跑完后，哨兵文件不存在，陷阱也没有被触发。
- 期望值只由工具包里手写的参考求值器计算，而这个求值器本身有手算算例校验。
- 本包不提供沙箱，也不声称提供沙箱。

## 4. 已知限制

1. 公式 IR 是封闭语法，回归残差、条件分支、指数加权、横截面回归中性化、积分等写法都会报错，需要人工重述。PDF 的数学字体经常无法解码，这一点与 v0.1 相同。
2. 符号到字段的映射靠关键词推断，必须确认；论文"调整后价格"与数据源的复权口径能否对应，需要宿主确认。
3. `reported_results` 不抽表格中的数值；拆分训练/验证/测试时只看年份区间，不处理精确到日的边界。
4. 静态分析只覆盖常见模式，不能证明代码正确或安全。
5. 测试的期望值反映的是"本包对论文公式的理解"，不能证明这种理解本身是对的，仍然需要人工对照原文。
6. 验收用的 3 份真值文档是我编写的合成文档，复述的是公开方法，不能代表真实期刊排版的难度；真实论文只有 1 篇，而且不是因子类论文。（2026-10-12 补充：已用真实因子论文 George & Hwang (2004) 做了端到端验收，结论为部分支持，并发现 1 个 P0 缺陷，即 `high` 被推断映射为日内最高价。详见 ACCEPTANCE_REPORT.md（未公开的原内部附件）。）

## 5. 剩余工作（需另行安排）

- 一个经批准的执行环境，用 `tests.json` 实际验证候选代码，并接入人工审批和提升流程。
- 在主 Agent 中接入：只把 `expressible` 且经过人工确认的 `dsl.expression` 交给现有的 `qrtk_expression_study`，未解决事项交给研究定义确认门。这项工作应由 Codex 按 [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md) 完成。
- 更多真实因子论文的回归集，最好带人工标注的真值。
- 如果引入语言模型辅助抽取，只允许它在 A 类引文范围内归类，并继续用 `validate_research_spec` 和 `validate_research_task` 把关。
