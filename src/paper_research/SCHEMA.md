# paper_research 数据结构（文档/规格 1.0，任务 1.0，候选清单 1）

两个带版本号的结构：

- `paper_research.document/1.0`：文档解析结果，由 `ingest_document` 产出。
- `paper_research.spec/1.0`：研究规格，由 `extract_research_spec` 产出。

机器可读的 Schema 定义在 [spec.py](spec.py) 的 `DOC_JSON_SCHEMA`、`SPEC_JSON_SCHEMA`、`ITEM`、`FORMULA` 中，由 `validate_document` 和 `validate_research_spec` 使用。格式不兼容的修改要提升主版本号；`load_research_spec` 遇到不认识的版本会报 `VERSION_UNSUPPORTED`。

## 1. 文档 `paper_research.document/1.0`

| 字段 | 内容 |
|---|---|
| `doc_id` | 文件 SHA-256 的前 16 位 |
| `source` | `filename`、`format`（pdf / html / markdown / docx）、`sha256`、`bytes`。只记录文件名，不记录完整路径 |
| `metadata` | `title`、`authors`、`year`、可选的 `file_author`。每项为 `{value, source, block_id, confidence}` 或 `null`。没有可靠来源时为 `null`，不做猜测 |
| `language` | `en` / `zh` / `mixed` / `unknown`，按字符构成判断 |
| `blocks[]` | 见下表 |
| `sections[]` | `{block_id, number, title, level, page, line}` |
| `formulas[]` | 见第 3 节 |
| `tables[]` | 表格块的 id 列表 |
| `figures[]` | `{block_id, number, caption, page}` |
| `references[]` | `{id, raw, year, label, block_id, page, parsed: false}`。`raw` 是逐字原文，不解析成作者、期刊等结构化字段，不补全，不编造 |
| `security` | `untrusted_content: true`、`executed: false`、`injection_findings[]`（`block_id, page, line, kind, patterns, excerpt`）、`hidden_text_blocks` |
| `extraction_report` | 解析器名称；PDF 另有总页数、已解析页、无法读取页、低置信页、隐藏文本数、检测到的表格数、移除的页眉页脚数、`ocr_attempted: false`；HTML 另有移除的脚本、注释和嵌入对象数；Markdown 另有未执行的代码块数；DOCX 另有 OMML 公式数和隐藏 run 数；以及 `warnings[]` |

**block**：`{id, kind, text, page, section, bbox, line, level, confidence, flags[], data{}, text_sha}`

| kind | 含义 | data |
|---|---|---|
| `title` | 题名 | — |
| `heading` | 章节标题 | `number`、`title` |
| `paragraph` | 正文段落 | 可选 `inline_math[]` |
| `formula` | 整行公式 | 可选 `latex`、`display`、`fonts` |
| `table` | 表格 | `caption, number, continued_marker, header[], rows[][], n_cols, notes[], units[], issues[], continuation_of, continued_in[]` |
| `caption` | 图题或表题 | `kind`（table / figure）、`number`、`continued` |
| `reference` | 参考文献段落 | — |
| `code` | 代码块，`flags` 含 `not_executed` | `language` |
| `hidden_text` | 不可见文字（白色、小于 2pt、`display:none`、Word 隐藏 run）；`flags` 含 `excluded` | — |
| `unreadable` | 没有文字层的页，`text` 为空 | `reason` |

**位置字段：**
- PDF：`page`（从 1 开始）加 `bbox`（单位为 pt）。
- HTML：`line`（源码行号）加 `data.path`（元素路径）。
- Markdown：`line`。
- DOCX：`line` 是段落序号，`data.location` 形如 "paragraph n" 或 "table n"；DOCX 没有固定页码，所以 `page` 为 `null`。

**置信度 `confidence`：** high / medium / low / none。

**常见 flags：** `garbled`、`suspect`、`multi_page`、`table_body_not_detected`、`injection_suspect`、`omml_linearized`、`image_not_loaded`、`unterminated_math`。

## 2. 研究规格 `paper_research.spec/1.0`

| 字段 | 内容 |
|---|---|
| `spec_id` | 规格内容的哈希；相同输入总是得到相同的 id |
| `generated_from` | `doc_id` 和 `source` |
| `extractor` | 名称、版本、方法（基于规则，不使用语言模型） |
| `paper` | `title`、`authors`、`year`（来自文档 metadata）、`language` |
| `A_supported` | `{字段: [item]}`，见下文 |
| `factors[]` | `{name, aliases[], mentions, first_mention(evidence 或 null), definition_evidence[], formula_ids[], status}`。`status` 取值：`defined_in_source`、`formula_unresolved`、`named_only` |
| `formulas[]` | 同第 3 节 |
| `tables[]` | `{block_id, page, caption, header, n_rows, units, notes, issues, continuation_of, continued_in}` |
| `B_deductions[]` | `{type: deduction 或 proposal, statement, basis[], requires_confirmation: true}` |
| `C_missing[]` | `{item, question, related[], optional?}` |
| `ambiguities[]` | `{topic, detail, evidence[], question}` |
| `integrity_risks[]` | `{risk, status: mentioned_in_source 或 not_mentioned, evidence[], question, note}`。`risk` 共六项：`future_information_leakage`、`survivorship_bias`、`corporate_actions`、`fundamental_reporting_lag`、`label_alignment`、`parameter_selection` |
| `security` | `injection_findings`、`hidden_text_blocks`、`excluded_from_extraction[]` |
| `extraction_quality` | `pages_unreadable`、`pages_low_confidence`、`formulas_unresolved`、`formulas_suspect`、`tables_suspect`、`table_captions_without_body`、`warnings` |
| `reproduction_status` | 固定为 `"not_reproduced"` |
| `disclaimer` | 固定声明：引文不是解释，公式不可直接执行，规格不代表论文已被复现 |

**A 类 item：** `{field, status: "supported", value（逐字句子，最长 400 字符）, matched, evidence: [{location, quote}], confidence: medium 或 low, parsed?, data_field?}`

**location：** `{doc_id, block_id, page, section, line, char_start, char_end}`。`quote` 必须严格等于 `block.text[char_start:char_end]`，这一点由校验器检查。

**A 类字段：**
- 必需（找不到就进入 C）：`research_objective`、`factor_definition`、`data_fields`、`frequency`、`lookback`、`universe`、`signal_timing`、`holding_horizon`、`evaluation_metrics`、`sample_periods`。
- 可选（找不到也进入 C，但标记为 optional）：`economic_intuition`、`sample_selection`、`preprocessing`、`portfolio_construction`、`costs_execution`、`limitations`。

## 3. 公式记录

`{id, raw, latex, readable, output_symbol, equation_number, source_kind, symbols[], defined_variables{符号: {definition, block_id}}, undefined_variables[], issues[], status, executable: false, requires_human_check: true, block_id, page, section, line}`

- `source_kind` 取值：`latex`、`inline_latex`、`pdf_text`、`omml_linearized`、`text`。
- `status` 取值：
  - `extracted`：未发现问题。
  - `suspect`：括号不配对、下标可能被压平、有变量找不到定义。
  - `unresolved`：出现无法映射的字形或缺少等式一侧，必须回看原文。
- 下标中的字母（i, t, d, k, n …）和函数名（log, sum, max …）不算作变量。
- 公式左侧的量视为由该公式定义；在别的公式左侧出现过的符号，视为由那个公式定义。

## 4. 校验 `validate_research_spec(spec, document=None, strict=False)`

返回 `{valid, errors[], warnings[]}`；`strict=True` 时出错直接抛异常。检查内容：

1. 结构符合 Schema，A 类每条 item 都合规，所有公式的 `executable` 为 `false`，`reproduction_status` 为 `not_reproduced`。
2. 如果同时提供了 document，还检查：
   - `doc_id` 与文档一致；
   - 每段引文都与所引的块和字符区间逐字一致；
   - 页码一致；
   - 引文不能来自被排除的块（疑似注入或隐藏文本）；
   - 每个公式引用的块都存在。

## 5. 错误码

| 错误码 | 含义 |
|---|---|
| `PATH_NOT_ALLOWED` | 路径不在调用方允许的根目录下 |
| `REMOTE_NOT_ALLOWED` | 输入是 URL，不抓取远程文件 |
| `FILE_NOT_FOUND` | 文件不存在 |
| `FILE_TOO_LARGE` | 文件超过大小上限（默认 80 MB） |
| `UNSUPPORTED_FORMAT` | 没有对应格式的解析器 |
| `MACRO_DOCUMENT_REFUSED` | 宏文档（.docm 等）不打开 |
| `ENCRYPTED` | 文档已加密 |
| `PARSE_FAILED` | 文件损坏或无法解析 |
| `NO_TEXT_LAYER` | 没有可提取的文字（例如扫描件），不做 OCR |
| `SCHEMA_INVALID` | 结构不符合 Schema |
| `PROVENANCE_INVALID` | 引文在所引位置找不到 |
| `VERSION_UNSUPPORTED` | 不支持的 Schema 版本 |

## 6. v0.2 新增的 A 类字段与解析值

| 字段 | 附加的解析值 | 说明 |
|---|---|---|
| `evaluation_design` | `splits: [{role, start_year, end_year, text}]` | `role` 取 `in_sample` / `validation` / `out_of_sample` / `unlabelled`，取年份区间前面最近的关键词；前面没有关键词时才看后面。`text` 必须是引文的子串 |
| `sample_periods` | 同上（如果能解析） | — |
| `reported_results` | `results: [{metric, value, unit}]` | `value` 必须逐字出现在引文中；只抽取正文句子，不抽表格 |
| `preprocessing` | `methods: [...]` | 取值见 `extract.PREPROCESS_TAGS` |
| `holding_horizon` | `parsed: {n, unit}` | 支持 “next 20 trading days” 和 “未来5个交易日” |

新增的歧义主题：`holding_horizon`（出现多个预测期）、`evaluation_design`（同一角色有多个年份区间）。

## 7. 研究任务 `paper_research.task/1.1`（v0.3；1.0 为 v0.2）

字段清单和用法见 [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md) 第 2 节。机器可读的结构定义是 `task.TASK_JSON_SCHEMA`。

- 每一项都带 `basis`，取值 `paper` / `inference` / `host_choice` / `missing`。
- `status` 只有 `blocked` 和 `ready_for_review` 两种取值。
- `task_id` 是去掉 `task_id` 字段后内容的哈希。

`validate_research_task(task, spec)` 会检查：

- 结构；
- `task_id` 与内容一致；
- 引文是否在规格里出现过；
- 用规格和 `host_choices` 重建任务，结果是否逐段相同；
- IR、DSL、预热的重新计算结果；
- 样本划分的顺序；
- 是否给出预测期以便 purge；
- 状态与阻塞项是否一致；
- 准入权限是否被篡改（`ADMISSION_INVALID`）。

## 8. 因子 IR `paper_research.factor_ir/1.0`

IR 节点的定义见 `factor_ir.py` 开头的说明。字段的滞后写成 `{"base": c, "var": k|null}`，`base < 0` 表示未来数据。`warmup(ir)` 返回 `min_lag`、`max_lag`、`observations_required`、`uses_future`。

## 9. 候选产物清单

`manifest.json` 包含：

- `status: "UNTRUSTED_NOT_EXECUTED"`、`executed: false`、`trusted: false`、`promotion`；
- `origin`、`generator`、`task_id`、`spec_id`、`document_sha256`、`factor`；
- `files`：文件名到 SHA-256 的映射；
- `candidate_id`。

源码以 `candidate.py.txt` 保存。`verify_candidate_bundle` 会重新计算指纹。

## 10. v0.3 新增字段

### 文档

| 位置 | 字段 | 说明 |
|---|---|---|
| `extraction_report` | `layout_fractions_reconstructed`、`formula_regions_unresolved[{page,bbox,method}]`、`tables_from_text_layout` | 版面复原统计 |
| 段落/公式块 `data` | `layout_math[{latex,status,method,numerator_text,denominator_text,bbox}]` | `status` 取 `reconstructed` / `unresolved`；`method` 取 `fraction_rule` / `stacked_fragments_without_rule` |
| 块 `flags` | `layout_math`、`glyph_substitution`、`text_layout` | 字形错码与版面重建的标记 |
| 表格块 `data` | `method: text_layout`、`reliability: structured/partial`、`cells[{panel,row,column,column_index,text,value,unit,kind,bbox,verification,sign_unresolved}]`、`caption_context` | `kind` 取 `estimate` / `statistic_in_parentheses` / `bound` / `not_available` |

段落文本中的复原公式直接写成 LaTeX（例如 `\frac{P_{i,t-1}}{high_{i,t-1}}`），无法复原的写成 `[FORMULA_UNRESOLVED]`。引文以这段规范化后的文本为准，并逐字核对。

### 规格

| 字段 | 说明 |
|---|---|
| `formulas[].layout` | `{page, regions, method}` |
| `C_missing[].code` | `FORMULA_UNRESOLVED`（附 `page`、`region`） |
| `reported_results[].results[]` | 新增 `number`（带符号）、`metric_normalized`、`metric_basis`、`t_stat`、`unit_inferred`、`subject_hint`、`attribution`、`sign_unresolved`、`review`、`review_reason`、`verification` |
| `table_results[]` | `{table_block, table_number, page, panel, row, column, value, number, unit, kind, metric_normalized, bbox, verification, review}` |
| `tables[]` | 新增 `method`、`reliability` |

### 任务（1.1）

`admission`、`data_requirements`、`factor.selection`、`factor.timing`、`factor.symbols[].interpretation/options/derived/derivation`、`unresolved[].gate`。含义见 [INTEGRATION_CONTRACT.md](INTEGRATION_CONTRACT.md) 第 2–3 节。
