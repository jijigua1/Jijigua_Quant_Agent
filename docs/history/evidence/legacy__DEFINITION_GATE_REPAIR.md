> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-C 研究定义确认门：最终交付（v0.6.8）

**结论：v0.6.8 真实 DeepSeek CLI 验收通过（未确认、明确同意、明确拒绝三个场景），Phase 2-C 冻结。**

## 1. 缺陷与根因

- **v0.6.5**：用户只说“默认设定”，`factor_research` 的规划步骤就自行改用 `momentum_20d_skip5_exploratory` 并执行。约束只写在提示词里，代码没有拦截。
- **v0.6.6–0.6.7**：确认门本身成立，但能计算的 Skill 在判定原定义不可执行后，没有确定性的退出路径。v0.6.7 的日志显示，规划已经写出具体替代，工具选择却一直挑 `list_research_resources`，直到 `BUDGET_EXHAUSTED`。

## 2. v0.6.8 的确定性状态机（只改核心链路）

| 状态或事件 | 触发 | 程序行为 |
|---|---|---|
| `DEFINITION_RESOLUTION_REQUIRED` | 能计算的 Skill 在规划中声明 `definition_change`，且本任务没有用户授权 | 关闭数据探查；工具选择只开放计算工具，结果只能是“一个替代调用”或“不调用” |
| `DEFINITION_ALTERNATIVE_VALIDATED` → `AWAITING_CONFIRMATION` | 替代调用依次通过 Schema、策略、数据合同和样本长度检查。检查由计算工具以只读的 validate-only 模式完成，在加载与检查后、计算前停止，不写任何文件 | 生成由程序渲染的方案和 `definition_sha256`，保存提案，结束本轮 |
| `DEFINITION_BLOCKED` → `BLOCKED_UNSUPPORTED` | 模型不提交替代，或替代没通过任一检查 | 说明受阻原因、缺少的能力和被拒的检查项；不保存、不编造方案 |
| `REPEATED_CALL_STOPPED` → `BLOCKED_NO_PROGRESS` | 同一任务里出现相同工具、相同参数的调用（兜底） | 不再执行，也不生成方案 |
| `DEFINITION_CHANGE_CONFIRMED` | 模型判定为 accept，且用户原话为明确同意 | 程序直接执行已保存的同一份参数，不再由模型重新生成；执行前核对指纹 |
| `DEFINITION_CHANGE_REJECTED` | 模型判定为 reject，或用户原话含明确拒绝 | 清除提案，保留原研究定义 |

所有提案都绑定 Tool 参数，不再存在只有文字的提案。`INVALID_PARAMETERS` 与 `AUTHORIZATION_DENIED` 仍按原分类处理；权限、Schema、数据合同、默认 PKL 与报告交付没有改动。

修改的文件：`definition_gate.py`、`workflow.py`、`conversation.py`、`quant.py`（只在样本检查之后加了 validate-only 停止点）、`contracts.py`、`factor_research` 的 Skill 文件与清单哈希、测试文件，以及 `scripts/phase2b_server.py` 与 `package_phase2b.py`。

## 3. 本地确定性证据（不调用 DeepSeek API）

- `tests/test_definition_resolution.py` 用 65 日样本的合成数据重放 v0.6.7 的模型行为。修复前 8 项全部以 `BUDGET_EXHAUSTED` 结束（`v068-reproduction-before-fix.txt`），修复后 8 项全部通过（`v068-reproduction-after-fix.txt`）。覆盖：
  - 有可用替代时进入 `AWAITING_CONFIRMATION`，参数指纹绑定；
  - 没有合法替代时进入 `BLOCKED_UNSUPPORTED`；
  - 替代未通过 Schema 检查（horizon=20）时进入 `BLOCKED_UNSUPPORTED`；
  - 替代未通过样本检查（暖机 65 日）时进入 `BLOCKED_UNSUPPORTED`；
  - 相同参数重复调用时进入 `BLOCKED_NO_PROGRESS`；
  - 对话中确认后按保存的参数执行，产出 PKL 和 HTML；
  - 对话中拒绝后清除提案；
  - 对话中没有合法替代时如实报告阻塞。
- `tests/test_definition_gate.py` 25 项。`test_workflow.py` 中原有的“无限循环靠预算终止”测试拆成两种情况：参数每步都变化时仍以 `BUDGET_EXHAUSTED` 结束；参数完全相同时以 `BLOCKED_NO_PROGRESS` 结束。
- Windows：295 passed，1 skipped（系统拒绝创建符号链接，错误 1314），JUnit 文件为 `gate-windows-v068.xml`。
- Linux，以 quantagent（uid 999）运行：agent 295 passed，1 skipped（缺少 pyarrow 的可选测试）；candidate 135 passed。

## 4. 部署

`/opt/jijigua-quant-agent/research_agent/`，版本 0.6.8，wheel SHA-256 `8752477363bdf6a186a1aee045c2b443b98607a177dfe467905592096db1ecf5`，release `d3312a80…`，candidate 沿用 `b77366c6…`（未带入 quant_toolkit 中的 Phase 3 改动）。部署沿用原运维流程：root 只负责解包，安装和测试以 quantagent 身份运行。回滚点：服务器 `dist/claude-checkpoint-0.6.5-*.zip` 与历史 wheel；本地 `dist/claude-checkpoint-0.6.5-20261012T142912.zip`。

## 5. 真实 DeepSeek CLI 验收（v0.6.8，仅依据 SQLite 事件）

证据：`gate-v068-{confirm,reject}-live-{session.json,ssh-console.txt}`，汇总在 `gate-v068-live-acceptance.json`。

| 场景 | 会话 | 实际事件与产物 | 结果 |
|---|---|---|---|
| A 未经确认 | 两个会话的第二轮 | `data_research` COMPLETED → 同轮生成替代方案 → `factor_research` 进入 AWAITING_CONFIRMATION（替代通过检查并被拦截）；`qrtk_*_study` 实验 0 个 | ✅ |
| B 明确同意 | 确认会话 `160648e9…` | 记录 `DEFINITION_CHANGE_CONFIRMED`（提案 `02f8261c…`）→ 执行调用 ID 为程序生成的 `confirmed_02f8261c…`，执行参数与保存参数逐字段一致，指纹 `c7afcc84…` 相同；记录 `DEFINITION_CHANGE_AUTHORIZED`；真实数据，PKL 状态 VERIFIED | ✅ |
| C 明确拒绝 | 拒绝会话 `bbec23dd…` | 记录 `DEFINITION_CHANGE_REJECTED`；全会话 0 个研究实验；会话中不再有待确认提案；回答注明已保留原研究定义 | ✅ |
| 全局 | 两个会话 | 所有轮次 COMPLETED；`BUDGET_EXHAUSTED` 0 次，`AUTHORIZATION_DENIED` 0 次，`REPEATED_CALL_STOPPED` 0 次 | ✅ |

场景 B 的成果目录 `/srv/jijigua-quant-agent/research_runs/2026-10-12/15-33-27_momentum_20d_exploratory/`。以 uid 999 核对：52 个文件的 SHA-256 与 manifest 全部一致，包含 `data/factor.pkl`、`data/factor_dict.pkl`、元数据、`factor_metrics.csv`、`reports/report.html` 与 `.md`、21 个图表文件、`code/factor_formula.tex`。证据强度为 insufficient，`formal_backtest_ready=false`。

## 6. 剩余限制

- 两个真实会话都走“先做数据核验，同轮生成提案”这条路径。路由层直接进入 `factor_research` 时的 `DEFINITION_RESOLUTION_REQUIRED` 路径（即 v0.6.7 的故障路径）只在确定性模拟中验证过，真实会话没有走到。
- 每次运行中模型提出的替代方案不同（本次是 20 日、预测期 5、5 组；拒绝会话中是预测期 1、2 组）。方案描述与指纹由程序根据实际参数生成，内容准确，但方案质量取决于模型。
- 判断“是否改变研究定义”仍依赖模型如实填写 `definition_change`，或使用替代标记的因子名。程序保证的是：一旦声明或被标记，后续流程完全确定，而且未经确认的参数不会被执行。
- daily65 只是 65 日、未复权、固定 50 只股票的研究样本，所有结果都只是探索性统计；正式回测仍未准入。`/hy-tmp` 是临时存储，重要成果需要另行备份。

## 7. 冻结

Phase 2-C 在 v0.6.8 冻结。之后的变更（包括 Phase 3）需要另行立项。
