> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# v1.0 Beta 隔离验收 · 第一轮真实对话缺陷记录（2026-10-13）

第一轮转录保留原样：`S1_new_paper.20261013_150926.txt`、`S2_known_papers.20261013_151228.txt`、`S3_user_factor_and_block.20261013_151532.txt`，以及 `live_summary.json`。诊断依据为隔离部署的只读账本（`tools/ledger_tail.py`，`/srv/jijigua-quant-agent/v1beta/state/research.sqlite3`）。以下缺陷已在开发副本中修复，并有离线回归测试覆盖；第二轮真实对话（`R2_*`）用于复验。

## 第一轮通过的部分

| 项目 | 结果 |
| --- | --- |
| Amihud ILLIQ（论文 → 口径确认 → 代码审核 → 计算） | 完成；IC 训练/验证 0.0133 / 0.0075，RankIC 0.0178 / 0.0057；新代码与可信 IR 逐格一致；报告一致性检查 PASSED；Test = NOT_AUTHORIZED，未读取任何 2026 数据 |
| 用户五日反转因子 | 完成；Train 0.0204 / 0.0264 / 959 天，Validation 0.0433 / 0.0463 / 479 天，与生产 r4 一致 |
| 两道人工闸门 | 口径与代码均由 Kevin 在终端亲自回复；程序没有自动替用户确认 |

## 缺陷与修复

| # | 现象 | 根因 | 修复 | 回归测试 |
| --- | --- | --- | --- | --- |
| D1 | “列出我上传的论文” 返回 RESULT_CONTRACT_FAILED | paper_research 输出 Schema 的 mode 枚举缺少 `catalog` | 已在第一轮中途修复（S2 起生效） | `test_list_and_ambiguous_paper_requests_answer_without_model_reading` |
| D2（严重） | 移动平均论文：确认的口径写的是 250 个交易日均值，实际审核的代码却是 1250 日窗口、5 日收益 | 窗口修复已按交易日写出 M=249，规划器又按周频把每个滞后乘以 5（重复换算）；修复提示没有告诉模型论文频率，也没有要求声明单位 | 修复回复必须声明 `window_unit`（paper_period / trading_day）；按交易日写出的公式不再换算；非日频论文没有声明单位时直接阻断（WINDOW_UNIT_AMBIGUOUS）；旧缓存中缺少单位的非日频理解会自动重读一次 | `test_trading_day_repair_of_a_weekly_paper_is_not_converted_twice`、`test_unstated_window_unit_on_a_non_daily_paper_blocks` |
| D3 | 确认口径时显示 249，代码实际为 1249；用户无法看出两者不一致 | 决定文本只显示论文层面的公式，不显示实际执行的公式 | 决定文本第一行为一句简短问题（如“该论文需要使用约251个交易日的回看窗口、未复权价格…进行探索性研究，是否继续？”），第二行为实际执行公式和所需历史天数（约多少年）；模型建议移到最后并截短，系统设置与数据行不再被截掉 | `test_daily_plan_question_comes_first_and_states_the_real_lookback` |
| D4 | 用户两次确认后才得到 INSUFFICIENT_RESEARCH_SAMPLE，提示只写“这次请求没有完成” | 样本长度检查只在计算前执行；失败信息没有翻译 | 规划阶段按已发布 Train 区间估计交易日数，回看超出时在任何确认之前阻断（LOOKBACK_EXCEEDS_SAMPLE）；常见失败代码有中文说明 | `test_paper_period_window_is_converted_and_an_unfittable_lookback_stops_before_any_gate`、`test_known_failures_explain_themselves` |
| D5 | 论文规划的频率说明与实际执行不一致的潜在情形（PDF 解析读作日频、模型读作周频） | 是否换算由 PDF 解析器决定，说明文字由模型频率决定 | 规划器按任务实际的 `time_basis` 改写频率说明 | `test_frequency_text_follows_what_the_task_executes` |
| D6 | 52 周高点：模型传入中文因子名“52周高点接近度”，工具崩溃（PlanError → TOOL_EXECUTION_FAILED） | 因子名只做英文子串匹配 | 按数字/英文词匹配，论文只有一个因子时直接映射并记录；仍无法匹配时返回论文中的因子列表，不再崩溃 | `test_a_translated_factor_name_maps_to_the_papers_only_factor` |
| D7（严重） | Heston 期权动量：把“一个月平值跨式期权收益”替换为股票收盘价收益，作为探索性替代请用户确认 | 规划器把任何 `returns` 字段都改由股票收盘价计算 | 符号含义为期权、跨式、期货、债券、外汇、商品等其他资产时直接阻断（INSTRUMENT_NOT_AVAILABLE），不作为可确认的替代 | `test_other_instruments_are_never_substituted_by_stock_prices` |
| D8 | “继续刚刚中断的论文研究” 没有找到论文 | 模型改写的查询中英混合，部分匹配命中多篇（AMBIGUOUS） | 部分匹配按命中词数取唯一最高者；“继续/中断/刚才”解析为最近研究过的论文（论文库记录研究时间） | `test_library_partial_match_and_continue_resolve_one_paper` |
| D9 | 没有研究时追问 Train/Validation/Test，只得到通用失败提示 | read_study 的 ARTIFACT_DIRECTORY_UNAVAILABLE 没有中文说明 | 说明“当前会话还没有可读取的已完成研究” | `test_known_failures_explain_themselves` |
| D10 | Amihud 经济逻辑：三条机制被正确降级为“Agent假设”，但正文仍写“Amihud 提出…/作者指出…”；`paper_cited` 为真 | 降级只改标签，不改正文；`paper_cited` 只表示提供了原文段落 | 降级或未核对的作者表述在正文前加“【作者归属未经原文核对，以下仅作为Agent假设】”，方向理由同样处理；`paper_cited` 改为“至少一条引文核对通过”，另设 `paper_passages_provided`；分析版本升到 `economic-rationale/2`，旧缓存会重新生成一次 | `test_unverified_author_wording_is_marked_not_only_relabelled` |

## 第一轮的审批记录（保留，不撤销）

- 移动平均论文的新代码 `4e0c2d862564` 已被批准并登记，但从未用于计算：样本检查拒绝了它。修复后，同一论文会生成新的规划，因此需要重新确认口径并重新审核代码；旧批准只绑定旧 SHA 和旧定义，不能覆盖新代码。
- Heston 论文的候选代码没有通过静态审核（UNGUARDED_DIVISION、WINDOW_SHORTER_THAN_DECLARED），没有执行。修复后，这类论文会在规划阶段就被阻断。
