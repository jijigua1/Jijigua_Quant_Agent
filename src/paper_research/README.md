# paper_research：论文与研报理解工具包 v0.3

在本地把学术论文或研究报告（PDF、HTML、Markdown、DOCX）解析成**每一条都能溯源**的研究规格，供将来的编码 Agent 检查和使用。

本模块不计算因子，不做回测，也**不判断论文能否复现**：每份规格的 `reproduction_status` 固定为 `not_reproduced`。

```text
ingest_document  ->  extract_research_spec  ->  validate_research_spec  ->  export_research_spec
（本地解析，有路径白名单）  （A 原文 / B 推断 / C 缺失）   （Schema 加逐条引文核对）   （JSON 和 Markdown）
```

## v0.3：真实论文理解修复（公式、语义、表格、准入）

v0.3 针对两篇真实期刊论文（George & Hwang 2004、Amihud 2002）暴露的问题做了范围明确的修复，没有引入新依赖，也不调用语言模型。验收见 [PHASE3D_V03_REPORT.md](PHASE3D_V03_REPORT.md)。

- **公式（P0）**：新增 `layout_math.py`。
  - 根据 PDF 的矢量分数线和字号/基线，把叠放分式复原为 `\frac{…}{…}`，上下标复原为 `_{…}` / `^{…}`。
  - 不能可靠复原的情况记为 `FORMULA_UNRESOLVED`，附页码和区域，并阻止它进入任务。包括：没有分数线的叠放碎片、数学字体字形映射错误、未解码的负号。
  - 修复了 `parse_formula` 在下标 `k=0` 处误切等号的问题。
- **字段语义（P1）**：`task.interpret_definition` 解析每个符号定义里的聚合、窗口、取样点和复权。
  - "12 个月内最高价" 判为窗口聚合，永远不会映射到当日 `high`；宿主推导会被核对聚合方式和窗口长度。
  - 跨日期比较的价格必须声明复权。
  - "volume in dollars" 识别为成交额 `amount`，不会当成成交股数。
- **结果与表格（P2）**：
  - 新增 `numbers.py`：识别 en-dash 和 Unicode 负号、括号 t 值、无法解码的负号。
  - 指标词按完整单词匹配（"which" 不再被当成 IC）；跳过组合参数（"top 30%"）；引用他人的数字要求复核；区分买卖价差和收益价差。
  - 新增 `tables_text.py`：从文字坐标重建无框线表格和横排表格，支持跨列表头、层级行标签和行内 t 值，每个单元格都有坐标。
  - 修复：页边附近的数字单元格被当成页眉页脚删除；连字（ﬁ）破坏关键词匹配。
- **准入（P3）**：任务新增 `admission`，取值 `SEMANTICS_UNRESOLVED`、`MISSING_FIELDS`、`HOST_DECISION_REQUIRED`、`DATA_UNCERTIFIED`、`CANDIDATE_ONLY`、`READY_FOR_REVIEW_DSL`。
  - 每个状态都附各门的阻塞项和权限。`may_execute_candidate` 与 `may_backtest` 恒为 false。
  - 宿主可以声明 `data_certification`，复权、上市、交易状态等缺口会进入准入判断。
  - 没有指定因子时，按论文标题自动选择，并记录为推断。

## v0.2：从论文到研究任务和候选算法

v0.1 只负责“读懂并溯源”。v0.2 在它后面接上三步，仍然不调用语言模型、不执行任何生成的代码：

```text
spec ──build_research_task──> task（paper_research.task/1.0）──compile_ir──> 19 算子 DSL 表达式
                                                         └──build_candidate──> 不可信候选（文本，不执行）
```

- **抽取增强（P0）**：新增 `evaluation_design`（训练/验证/样本外角色和年份）、`reported_results`（指标名和数值，数值必须逐字出现在引文里，校验器会复核）、`preprocessing.methods`（缩尾、标准化、排序、行业中性、市值中性、缺失值、异常值），以及预测期和样本划分的歧义检测。修复了 `$P$` 形式的变量定义、“daily closing prices”、“next 20 trading days”、中文“未来N个交易日”和以数字开头的因子名。
- **研究任务（P1）**：`task.py` 按“原文 / 推断 / 宿主选择 / 缺失”记录每一项：假设、因子 IR、符号到字段的映射、数据结构、时点约束、输入输出、预热、标签与成熟规则、样本划分、评估指标、限制、未解决事项和复现元数据。论文是月频而 DSL 是日频时不会悄悄换算；宿主只能显式换算，并标记为偏离原文。`validate_research_task` 会确定性地重建任务并比对，任何被改动的部分都会被报出来。
- **公式 IR 与 DSL（P1）**：`factor_ir.py` 是封闭语法的 LaTeX 解析器，只接受 `\frac`、`\sum/\max/\min` 加明确的上下界、`|x|`、`\log`、`\sqrt`、`\operatorname{std/mean/rank/zscore}` 以及 `t-k` 下标；其他写法报错，交给人工处理，不猜。`dsl.py` 固定描述主 Agent 的 19 个算子及其限制，把 IR 编译成 DSL，或者给出无法表达的准确原因。等价性用两个独立的可信求值器在合成面板上逐值比对。
- **候选算法（P2）**：`candidate.py` 为 DSL 无法表达的因子生成候选源码、契约、独立期望值测试规格（期望值由可信参考求值器计算）、假设清单、纯 AST 静态分析、失败报告和修复建议，全部带 SHA-256 指纹，状态固定为 `UNTRUSTED_NOT_EXECUTED`。也可以把外部（例如语言模型）给出的源码交给它做同样的分析。候选不会被导入或执行，也不能被提升为可信工具。

集成契约见 [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md)，验收脚本是 `examples/paper_to_factor_acceptance.py`。

## 与现有工具包的关系

| 复用的部分 | 位置 |
|---|---|
| Schema 校验器 | `qrtk_skills.runtime.validate` |
| Skill 运行时：能力、权限、数据目录、产物、审计 | `qrtk_skills`；本模块的 Skill 放在独立目录 `paper_research/skill/`，用 `create_paper_runtime` 和原有的 5 个 Skill 一起加载 |
| 错误风格 | 稳定的错误码加说明，与 `SkillError` 一致；在 Skill 里 `PaperError` 会被转换成 `SkillError` |

原有 5 个 Skill 及 `skills/manifest.json` 都没有改动。

## API

```python
from paper_research import ingest_document, extract_research_spec, validate_research_spec, export_research_spec

doc = ingest_document("D:/papers/momentum.pdf", allowed_roots=["D:/papers"])   # 只读白名单目录内的文件
spec = extract_research_spec(doc)
check = validate_research_spec(spec, doc)        # {"valid", "errors", "warnings"}；strict=True 时出错直接抛异常
paths = export_research_spec(spec, "out/momentum")   # research_spec.json（规范格式）和 research_spec.md
spec2 = load_research_spec(paths["json"])         # 读回时重新校验 Schema 版本和结构
```

| 函数 | 签名 | 失败时 |
|---|---|---|
| `ingest_document` | `(path, *, allowed_roots, max_bytes=80MB, max_pages=400) -> document dict` | `PaperError`，错误码见 [SCHEMA.md](SCHEMA.md#5-错误码) |
| `extract_research_spec` | `(document, max_items_per_field=6) -> spec dict` | — |
| `validate_research_spec` | `(spec, document=None, *, strict=False) -> dict` | strict 模式下抛 `PROVENANCE_INVALID`、`SCHEMA_INVALID` 或 `VERSION_UNSUPPORTED` |
| `export_research_spec` | `(spec, out_dir, basename="research_spec") -> {"json", "markdown"}` | 规格不合法时抛 `SCHEMA_INVALID` |
| `load_research_spec` | `(path) -> spec` | `PARSE_FAILED`、`VERSION_UNSUPPORTED` |
| `validate_document` | `(document) -> [errors]` | — |

结构的完整说明见 [SCHEMA.md](SCHEMA.md)。

**作为 Skill 使用：** `paper_research.skill_tools.create_paper_runtime(catalog, granted, artifact_dir)`。宿主用 `DocumentRef(path, allowed_root)` 把文档登记到 `DataCatalog`，模型只能引用 `data:<name>`。工具有 `paper.ingest`、`paper.extract_spec`、`paper.validate_spec`、`paper.export_spec`，方法说明见 [skill/paper_research/SKILL.md](skill/paper_research/SKILL.md)。

## 各格式能抽到什么

| 格式 | 解析器 | 位置信息 | 公式 | 表格 |
|---|---|---|---|---|
| PDF | PyMuPDF，只读文字层 | 页码、bbox、章节 | 按行识别（数学字体、等号、方程编号）；乱码字形标为 unresolved | `find_tables`（适用于有表格线的表）；跨页表只做保守关联，不合并；有表题但检测不到表体时会明确标出 |
| HTML | BeautifulSoup | 源码行号、元素路径 | MathJax TeX、MathML 中的 TeX 注释、`$…$` | `<table>` 加 `<caption>`、`<tfoot>` |
| Markdown | 内置解析 | 行号 | `$$…$$`、`\[…\]`、```math 代码块、行内 `$…$` | pipe 表格，加前一行表题和后一行注释 |
| DOCX | python-docx 加 OOXML | 段落或表格序号（DOCX 没有页码） | OMML 线性化文本（置信度 medium） | Word 表格，加前一段表题 |

## 安全与研究诚信

- **白名单读取：** 只读 `allowed_roots` 内的本地文件。URL、宏文档、超过大小上限的文件一律拒绝。
- **不执行任何内容：** HTML 的 `<script>`、`<iframe>`、`<object>`、表单和注释都被移除；代码块只记录不执行；不加载图片或链接；不做 OCR。
- **注入防护：** 文中像是对 AI 下指令的文字（中英文模式）和隐藏文字（白色、极小字号、`display:none`、Word 隐藏 run）都记入 `security`，所在块不参与抽取，校验器也不允许引文来自这些块。
- **不编造：**
  - 读不出的页面输出空的 `unreadable` 块并说明原因；
  - 参考文献只保留原文，不结构化补全；
  - 元数据没有可靠来源时为 `null`；
  - 原文缺失的方法细节一律列入 C，不填默认值；
  - B 类每条都标 `requires_confirmation`，而且不写具体数值。
- **诚信风险：** 每份规格都检查六类风险——未来信息泄漏、幸存者偏差、公司行动、财务数据披露滞后、标签对齐、事后选参——给出原文是否提及以及需要追问的问题。"提及"不代表"已经正确处理"。

## 依赖与运行

Python ≥ 3.11，加 PyMuPDF ≥ 1.23（PDF）、beautifulsoup4 ≥ 4.11（HTML）、python-docx ≥ 1.0（DOCX）。生成测试样本还需要 reportlab 和 Pillow。本机已验证的版本是 PyMuPDF 1.24.14、bs4 4.12.3、python-docx 1.2.0、reportlab 5.0.1。

不需要网络、GPU 或语言模型。在本机上，45 页的真实论文解析加抽取约 5–6 秒。

```powershell
cd <LOCAL_RESEARCH_ROOT>\quant_toolkit
python -X utf8 -m pytest tests/test_paper_research.py -v -W error::FutureWarning
python -X utf8 examples/paper_example.py "D:\path\to\paper.pdf"     # 输出到 reports/paper_research/<name>/
```

**部署：** 这是一个纯 Python 包，放在 `quant_toolkit/` 下，没有服务进程，也没有安装脚本。本阶段**没有**集成到主 Agent，也没有部署到 GPUShare。

## 已知限制

v0.3 仍然存在的限制（详见 PHASE3D_V03_REPORT.md）：

- 公式复原只依赖矢量分数线、字号和基线。图片公式、Type3 字体、没有分数线的多行公式只能标记为 unresolved；字形映射错误只能在同一行出现可疑字符时被发现，如果错码恰好落成看似正常的 ASCII（例如用 `=` 表示 `/`），单靠这一行无法发现。
- 表格重建依据对齐关系推断，单元格标为 `unverified_layout_parse`；含字形错码的表格整体要求复核。表头可能混入表题说明。
- 正文结果只抽取"指标词 + 数字"同句出现的情况，没有指标词的句子（例如 "the strategy earns 0.86%"）会漏抽；数字的限定条件（例如"不含 1 月"）不会被结构化。
- 组合规则（重叠持有、30% 分组）不进入因子定义，任务中也没有结构化表示。
- 真值由人工逐条核对，只覆盖两篇论文，样本小。

v0.2 新增的限制：

- 公式 IR 只覆盖常见因子写法。条件分支、回归残差、积分、指数加权、横截面回归中性化、分组运算都会报 `UNSUPPORTED_*`，由人来重述。
- 符号到字段的映射用定义句中的关键词推断（basis=`inference`），一律需要确认。
- 候选代码的静态分析只能发现常见模式，不能证明代码正确或安全。它对外部源码只做文本层面的检查。
- 候选测试规格里的期望值来自工具包自己的参考求值器。它保证“与论文公式（按本包的理解）一致”，不保证论文公式本身被理解对了。
- `reported_results` 只抽取正文句子里的“指标 + 数字”，不抽取表格中的数值。

v0.1 的限制：


1. **抽取基于规则。** 用关键词和句式匹配，只能找到用常见说法写出的内容；换一种措辞就可能漏掉。A 类只保证"这句话确实在原文这个位置"，不保证分类一定正确。
2. **PDF 中的数学公式。** 期刊 PDF 的数学字体经常无法解码成文字（本机测试的真实论文中，97 个公式里有 38 个被标为 unresolved）。上下标会被压平成 `Rt+1` 这样的形式；没有做版面级的公式重建，也没有做 OCR。
3. **没有表格线的表格。** 多数期刊表格没有表格线，PyMuPDF 检测不到表体，这时只会标记 `table_body_not_detected`。跨页表只做关联不合并，不规则表格会标为 suspect。
4. **双栏排版。** 阅读顺序按纵坐标排序，双栏论文的段落顺序可能交错（每个块的位置信息仍然准确）。
5. **作者和年份。** 作者只取标题下一行，置信度为 low；年份只从 HTML 的 meta 信息读取，PDF 一般为空。PDF 的创建日期不当作发表年份。
6. **语言。** 只对中文和英文做了模式适配；其他语言只能完成解析和溯源，字段抽取基本会落入 C。
7. **因子识别。** 依赖"名称 (缩写)"、"X 因子"和公式左侧符号这几种写法，非因子类论文（例如本机测试的 ML 择时论文）只能识别出少量名称。
8. **参考文献。** 按悬挂缩进和"作者, 首字母."的格式切分，不同期刊格式的切分可能有误差。条目只保留原文，不做结构化解析。

## 下一阶段集成说明（等你安排）

1. 主 Agent 通过 `create_paper_runtime` 或直接调用上面的 API 使用本模块；工具输入输出 Schema 见 `skill/paper_research/schemas.json`。
2. 宿主负责把用户提供的论文登记成 `DocumentRef`，并决定 `allowed_roots`；不要让模型传入路径。
3. 规格中的 C 项和歧义交给人确认后，再由人或者受控的流程填写 `qrtk.ResearchSpec`，不要从规格自动生成。
4. 如果要接入 LLM 辅助抽取，建议只让它在 A 类引文的范围内做归类和解释，再用 `validate_research_spec` 核对每一处引文，不允许它产生没有出处的事实。
5. 扫描件需要另接一个本地 OCR，结果要带 `ocr_attempted=true` 和逐字置信度，不能和文字层的结果混在一起。
