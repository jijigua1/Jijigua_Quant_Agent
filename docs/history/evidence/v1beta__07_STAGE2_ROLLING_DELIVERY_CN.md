> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 第二阶段：2026 滚动 Test 交付修复 · 预发布验收报告（2026-10-15）

**状态：`IMPLEMENTED / OFFLINE_TESTED`（本地 + 预发布 Linux）。生产未改动；需要授权的生产验收项见第 4 节。**

依据：Codex 生产审计 `<ARCHIVE_ROOT>\production_audits\20261014_2322\QUANT_AGENT_PRODUCTION_AUDIT_CN.md` 与 `NEXT_UPGRADE_ACCEPTANCE_PLAN_CN.md`。审计已确认的事实不再重复审计（例如：生产滚动通道已授权并正常工作，动量研究 184 个有效日；三份回执签名有效；169 文件清单 `342a78a9…` 无漂移）。

全部验证都是合成工程数据上的离线测试，不是市场证据，也不是真实 2026 评价。

## 1. 逐项：根因、最小修复、测试、结果

| # | 问题 | 根因 | 最小修复 | 测试 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 普通回答说 2026 滚动 Test “还需要另行审批”，实际已授权 | 系统提示里只有一句静态说明，模型自行推断授权状态 | 新增 `test_access.describe()`：按可信的滚动评价器状态生成三种说明（已授权并自动执行 / 本环境未授权 / 未连接评价器），注入系统提示并要求“只能以此为准”。说明同时写清：原始 2026 行情和未来标签任何时候都不能由 Agent 读取；一次性独立测试是另一份合同；模型代码类算法返回 UNSUPPORTED_STUDY | `test_2026_access_is_stated_by_the_program`（3 种状态） | 通过 |
| 2 | 浏览第 1 版目录（Test 为 PENDING）找不到第 2 版 | 每个版本写在独立目录，原研究目录只有 `report_versions.json`，没有面向人的入口 | 原研究目录写入 `reports/LATEST_REPORT.html`（列出全部版本，指向最新一版），并登记进 manifest；`latest_report` 选“最新的 COMPLETED/INVALIDATED 版本”，后一次失败不会遮住前一次成功 | `test_the_original_study_directory_points_to_the_newest_report`、`test_a_failed_later_attempt_does_not_hide_an_earlier_success` | 通过 |
| 3 | 评价器已签发回执，但报告生成失败（审计 GH 20:14） | 失败版本只记录“FAILED”，没有记下已签发的回执编号，之后没有从回执补出报告的路径 | 失败版本记录 `receipt_evaluation_id`；`pending_receipts()` 找出有回执、无报告的情况；用户要求刷新时先用 `load_receipt` 读回执补出报告（`new_evaluation=false`），评价账本不新增记录；再次刷新不再产生版本（幂等） | `test_a_receipt_whose_report_failed_is_finished_without_a_new_evaluation` | 通过：账本行数不变，版本数恒为 3 |
| 4 | `qrtk_read_study` 只读查询却会触发评价、发布、写报告 | 读取和刷新是同一个入口 | `read_study(refresh=False)` 为纯读取；只有 `refresh=True`（工具参数 `refresh`）才恢复回执并刷新 | `test_reading_a_study_has_no_side_effect_unless_a_refresh_is_asked`：只读时评价请求 0 次、目录不变；刷新同一快照时复用，不新增版本 | 通过 |
| 5 | 刷新失败时静默返回旧报告 | 刷新结果没有状态字段 | 刷新返回状态与类别（NEW_REVISION / REUSED_NO_CHANGE / NOT_AUTHORIZED / EVALUATOR_UNAVAILABLE / FAILED / REPORT_FAILED）；`report_access` 和程序生成的中文说明写明“最新一次刷新未成功，下面展示的是第 N 版，不是本次刷新的结果” | `test_a_failed_refresh_says_so_and_keeps_showing_the_last_success` | 通过 |
| 6 | 新会话找不到其它会话的研究报告 | 研究按会话隔离（权限设计）；错误提示没说明怎么找回 | 不放宽权限，只改说明：`/session` 查看会话 ID、`quant-agent chat --resume <会话ID>` 恢复、直接打开 `reports/LATEST_REPORT.html`、需要时由管理员登记共享目录 | `test_a_study_from_another_session_is_explained_without_widening_access` | 通过 |
| 7 | 评价器实现版本与缓存；容差符号的版本影响 | 符号函数改为数值容差后，旧研究若按新语义重算会悄悄改变结果；冻结定义里没有语义版本 | 可信 IR 数值语义版本化：`trusted-ir-semantics/1`（numpy sign，旧研究默认）与 `/2`（`|a−b| ≤ 1e-12(|a|+|b|)` 视为 0）。研究冻结时记录版本，Agent 与评价器都按冻结版本重算；未知版本拒绝。旧定义不加字段，SHA 与既有回执不变；新版本定义 SHA 不同，缓存不会跨语义复用。门槛从“执行器文件字节不变”改为“记录的语义版本受支持”，结果仍与参考实现逐格比对 | `test_v1beta_stage2_versions.py` 4 项、`test_a_changed_executor_is_refused_for_an_existing_study`（改为语义合同） | 通过 |
| 8 | 暖机重叠核验只比较 count/sum/sum²，两只股票的值互换无法发现 | 聚合量对股票顺序不敏感 | 评价器对每个重叠日额外给出 3 个按股票代码哈希加权的投影（权重只取决于去掉交易所后缀的代码，与列顺序无关），broker 用研究方 CSV 逐日复算，容差 `1e-9·Σ|x| + 1e-12`。旧回执没有投影字段时仍按原规则核验 | `test_the_warm_up_check_is_per_stock_not_only_count_and_sum`、`test_a_crlf_study_file_gives_the_same_codes_to_the_warm_up_check` | 通过 |

### 1.1 第 8 项开发中发现的缺陷（已修）

加入逐股票投影后，合成三阶段研究被判为 `HISTORY_MISMATCH`。逐股票比对 40 只股票的因子值完全相同，但投影不同。原因：研究方 `factor_values.csv` 为 CRLF 换行时，broker 读表头 `head.split(b'\n')` 后最后一个代码仍带 `\r`，这只股票拿到了另一组权重。修复：表头去掉 `\r`（`broker.py` 一行）。没有放宽容差。旧的 count/sum 核验之所以没暴露，是因为 `float('x\r')` 能正常解析。Linux 生产写出的是 LF 文件，因此生产不受影响；修复后 Windows 与 Linux 一致。

## 2. 兼容性

- **旧会话与旧研究**：没有 `ir_semantics` 的定义按版本 1 重算，定义 SHA 不变，既有回执可继续复用；没有投影字段的旧回执按原 count/sum 规则核验；没有 `receipt_evaluation_id` 的旧失败版本不会触发恢复。
- **工具接口**：`qrtk_read_study` 新增可选布尔参数 `refresh`，默认 false；旧调用含义从“读并刷新”变为“只读”，这是本阶段要修正的行为。
- **报告 schema**：`test` 下新增可选字段 `receipt_evaluation_id`（32 位十六进制）。

## 3. 语义版本的影响范围

- 只影响含 `sign` 且参数在理论上可能相等的定义（例如 `sign(MA20 − MA30)` 在停牌期间）。版本 1 下这类格子是 ±1 的浮点噪声，版本 2 下为 0。
- 已登记的生产研究全部是版本 1，继续按版本 1 计算，不重新签名，不修改既有回执定义。
- 新研究冻结为版本 2，得到新的定义 SHA，评价器会作为新定义评价。

## 4. 需要授权后在生产验收的项目（本轮未执行）

| 项目 | 原因 |
| --- | --- |
| 部署新代码到生产 Agent 与 root broker | 第一阶段真实验收通过前不申请整体部署 |
| 生产评价器增加逐股票投影 | 改动 root 评价器 |
| 用生产已签发的回执验证“回执补报告”（GH 20:14 那次） | 需要在生产研究目录写新版本 |
| 评价器缓存键加入评价器实现版本 | 目前键为（定义 SHA，快照版本，合同版本）。本轮的做法是：任何改变数值的评价器改动都必须升级合同版本；把实现 SHA 写进键需要改动账本结构，留待生产审批 |

预发布环境的 rolling 状态为 NOT_AUTHORIZED，这不代表真实 2026 通过，也不代表生产不可用。

## 5. 未触碰

生产代码与配置、root broker 与代理、私有 2026 数据与权限、cron、签名密钥、评价账本、历史签名回执、冻结的 candidate4、Codex 目录。

## 6. 回归结果（含第三阶段与上传改动的最终代码）

| 环境 | 结果 |
| --- | --- |
| 本地 Windows 全量 | 481 通过，3 跳过，4 失败。失败全部是既有问题：2 项 launcher 测试需要 Linux 的 `grp` 模块；phase2b 表达式 handler、phase2c 导出一致性在修改前就失败 |
| 预发布 Linux 全量（quantagent，临时目录在 `/srv/jijigua-quant-agent/ab/qa_tests`，结束后已删除） | 485 通过，1 跳过，2 失败（同上两项既有失败） |
| 预发布 Linux，最终代码重跑新增测试 | 第二阶段、第三阶段、上传共 31 项全部通过 |
| 源码指纹（`tools/src_fingerprint.py src`） | 本地 = v1rc：109 个 .py，`322ca59aa1b79a90cba82eb21adf0c8214e679fa28a812ecde2ec3dfa8e74217` |

根分区使用率测试前后都是 92%（2.7 GiB 可用），测试没有占用根分区。
