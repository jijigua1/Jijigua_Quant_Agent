> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 1-D 交付与测试报告

报告日期：2026-10-11（Asia/Shanghai）。项目：`<ARCHIVE_ROOT>`，包：`wty-research-agent 0.1.0`。

## 结论

完成独立离线核心开发：模型无关协议、DeepSeek Adapter、Mock Provider、一个受审 Mock Skill、两个类型化 Mock Tools、独立程序授权、研究状态机、SQLite 账本与 CLI。最新自动化测试 **102 通过、1 跳过、0 失败、0 错误**；wheel 在另一个本地环境安装后，从源码目录外成功运行。

本轮验证的是协议、权限门禁和固定模拟闭环；没有调用真实 DeepSeek，没有访问 GPUShare、真实行情、Pyx 或 pickle，没有部署或调整系统权限。完整生产隔离不是后续所有开发的先决条件，但也没有被宣称已经实现。

## 1. 项目结构及实现文件

完整目录与运行命令见 README（原内部附件未公开）。源代码只有新项目目录下的独立 Python 包，与旧 StratFlow、Step1–Step9、YAML Skills、Streamlit 没有导入关系。

| 文件 / 模块 | 已实现的职责 | 验证证据 |
|---|---|---|
| `llm.py`、`contracts.py` | 标准消息、角色、Tool 请求/结果、能力、结构化输出、流事件、错误、用量、凭据引用、有界 JSON | Provider/Schema 回归 |
| `providers/deepseek.py` | 固定 HTTPS 端点、原生 Tool Calling、工具反馈、普通 JSON+本地 Schema、SSE 拼接、脱敏与错误映射 | 固定 HTTP/SSE 测试；完整七次假传输闭环 |
| `providers/mock.py` | 不依赖自然语言理解的确定性模拟 Provider | 可复现实验与配置替换 |
| `skills.py`、`resources/skills/mock_research/` | 元数据发现、按需方法加载、机器声明、Tool 版本、Schema、固定示例与批准文件哈希 | 越权声明、篡改文件、非法配置拒绝 |
| `tools.py`、`security.py` | 白名单、封闭参数、独立授权交集、版本/资源/审批门禁 | 伪造 Tool、自批授权、路径参数和真实 Runner 拒绝 |
| `workflow.py`、`acceptance.py` | 计划 → 工具选择 → 执行 → 反馈 → 下一计划；确定性验收、预算、失败分类和停止 | 完整流程、无穷计划、提前结束、恢复与审计失败回归 |
| `store.py` | 本地 SQLite 状态、实验、授权和事件；原子检查点、乐观版本校验 | 新进程恢复、陈旧写入、链接拒绝 |
| `app.py`、`cli.py` | 装配、创建/运行/查询/结果/日志/Mock 对话；统一 root 启动拒绝 | CLI 十项回归，安装包冒烟 |
| `scripts/verify_offline.py` | 用固定本地验收案例导出 JSON 证据，自带断言 | 正常运行、恢复、八类拒绝、预算与工具失败实际收据 |

当前 Skill 方法并非万能 Prompt：机器声明不能覆盖 Policy；验收器由受信代码登记，Skill 不能指定任意可执行模块。Discovery 尚不等于模型自主挑选 Skills；初版绑定一个 Mock Skill。

## 2. Mock Provider / Skill / Tools 实际例子

正常任务 ID：`INTERNAL_RUN_ID_REDACTED`，Provider `mock`，模型 `mock-research-v1`，Skill `mock_research@1.0.0`。

| 研究步骤 | 假设或修改理由 | 工具及实际返回 |
|---|---|---|
| 数据查询 | 先确认模拟量价输入 | `query_mock_data(mock:ohlcv-v1)`，固定 6 行，日期标签 2026-01-05 至 2026-01-12 |
| 实验一 | 联合量价指标是否对窗口敏感；先测 3 期 | `compute_mock_factor(..., lookback=3)` → 0.03167420814479627 |
| 实验二 | 将窗口从 3 改为 5，检验参数敏感性 | `compute_mock_factor(..., lookback=5)` → 0.04698774962241991 |
| 结束 | 两个窗口完成对照，停止追加 | 确定性验证来源及窗口，然后生成模拟摘要 |

指标公式是 `(last_close / first_close - 1) * (last_volume / mean_volume)`。固定数据指纹：`b37f193d587e75dbd0c6d13c69796a0d6c83b5d6f87455e2355d1cdd7d7beafc`。这些是虚构数据与演示指标，不是市场有效性证据。

总计 **4 轮计划、7 次模型尝试、3 次 Tool 尝试、2 次因子窗口实验**。查询也记录为一个有输入输出的实验事件。账本保留每轮理由、参数、返回值及代码、数据、Skill、Provider 配置指纹。

最终摘要：

> 仅模拟研究：完成3期与5期量价指标对照；数值随窗口变化。没有真实行情、回测收益或有效性结论。

原始结构化证据：mock-run.json（原内部附件未公开）、mock-events.json（原内部附件未公开）。

## 3. 完整测试报告

实测环境：Windows 11 10.0.26200、Anaconda 提供的 CPython 3.12.4、本项目 `.venv`、pytest 7.4.4、jsonschema 4.19.2。`.venv` 继承系统已安装依赖，未改变全局 Python 包。依赖实际版本见 test-summary.json（原内部附件未公开）；重建安装版本见 requirements.lock（原内部附件未公开）。

命令：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml
```

| 测试模块 | 用例数 | 通过 | 跳过 | 主要覆盖 |
|---|---:|---:|---:|---|
| `test_cli.py` | 10 | 10 | 0 | 创建、暂停、运行、状态、结果、日志、Mock 对话、替换配置、root 查询拒绝 |
| `test_provider_contract.py` | 16 | 16 | 0 | DeepSeek 消息/工具合同、JSON、能力拒绝、SSE、用量、错误、禁止网络、完整替换闭环 |
| `test_security_skills.py` | 42 | 41 | 1 | Skill、Schema、工具/资源/版本授权、路径、硬链接、状态版本冲突 |
| `test_workflow.py` | 35 | 35 | 0 | 多轮计划、预算、失败分类、恢复、审计失败、Provider 替换、秘密 canary |
| **总计** | **103** | **102** | **1** | **0 failures / 0 errors** |

JUnit 记录时长 10.374 秒。唯一跳过是 `test_database_symlink_refused`：Windows 返回 1314，无法创建测试符号链接；没有提升权限或更改 Developer Mode。实际硬链接拒绝用例通过。不能把跳过的符号链接用例算作通过；Linux 真链接/竞争场景尚未验证。

测试网络连接由 autouse fixture 阻断，所有 HTTP/SSE 都是注入式固定字节。故不会误将 HTTP 合同通过写成真实 API 可用。Mock/Mock-alt 完整实验结构和摘要相同；DeepSeek Adapter 也在七个固定响应下替换 Mock 完成同一 Workflow，业务状态机未修改。

安全检查点恢复：任务 `INTERNAL_RUN_ID_REDACTED` 执行一次工具后 `PAUSED`，新 Engine 加载后完成，最终仍为 3 次工具尝试。配置/代码/Skill 指纹变化拒绝恢复；未知在途工具不重放，遗留 `RUNNING` 不自动接管。

全部逐项结果在 test-results.xml（原内部附件未公开）。额外验收证据脚本通过自身断言，结果在上述 JSON 中；不把脚本断言另计入 pytest 的 102 项。

### 安装包验证

本地构建命令：

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
```

wheel 大小 28,884 bytes；SHA-256 为 `16e23490f353caba1b53604eb545479d143175cee0dce13c18d62a07ec78cc3f`。在 `.venv-wheel` 用 `--no-index --no-deps` 安装，并在 `.qra-state/wheel-smoke` 运行。

实际导入路径是 `<ARCHIVE_ROOT>/.venv-wheel/Lib/site-packages/research_agent/__init__.py`；安装包任务 `INTERNAL_RUN_ID_REDACTED` 完成。源码与安装包的执行绑定指纹一致，说明所需资源已经打包。Linux 安装和执行尚未验证。

## 4. 安全拒绝与失败记录

以下为 `scripts/verify_offline.py` 实际产生的记录，完整请求状态和事件见 security-refusals.json（原内部附件未公开）。测试假传输和案例字符串均为本地受审 fixtures，没有执行字符串中的命令。

| 案例 | 实际结果 | 未发生的效果 |
|---|---|---|
| 伪造 `shell` 工具 | `AUTHORIZATION_DENIED / UNKNOWN_TOOL` | 无 Shell 执行 |
| 参数添加 `approved=true` | `AUTHORIZATION_DENIED / INVALID_PARAMETERS` | 模型未取得授权 |
| `../../private` 冒充资源 ID | `AUTHORIZATION_DENIED / INVALID_PARAMETERS` | 无路径读取 |
| 因子参数夹带 `python` | `AUTHORIZATION_DENIED / INVALID_PARAMETERS` | 无代码执行 |
| Policy 要求审批，Skill 说无需审批 | `INDEPENDENT_APPROVAL_REQUIRED` | 没有被模型或 Skill 批准 |
| 已重新固定哈希的测试 Skill 声明生产目录 | `SKILL_SCOPE_DENIED` | 即便文件被视为已审阅，Policy 仍不放行 |
| 登记未来 Runner 类型工具 | `BLOCKED_SECURITY` | 处理器调用数 0 |
| CLI 装配真实 DeepSeek | `LIVE_PROVIDER_NOT_ENABLED_IN_PHASE1_D` | 没有 HTTP 请求 |
| 任务只允许 1 次模型尝试 | `BUDGET_EXHAUSTED` | 模型计数 1，工具计数 0 |
| 固定工具处理器注入失败 | `TOOL_ERROR / TOOL_EXECUTION_FAILED` | 不继续实验，不泄漏异常原文 |

另外回归覆盖：恶意 Skill 文本不能授予 Shell 权限；未批准文件变化拒绝；超预算无穷计划终止；超权限工具登记拒绝；Key canary 不进入目标、状态、错误、Tool ID 或跨片流输出；拒绝审计落盘失败后不执行工具。

**有效边界**：模型只有两个纯内存 Mock Tools，无文件/系统/交易入口；代码级授权会在 Tool 调用前校验，Registry 执行时再次校验。

**边界限制**：同一开发账号拥有代码/SQLite；未实现独立授权服务、签名 Grant、防篡改日志或恶意代码沙箱。模型输出不是授权记录，但有权编辑本机文件的人仍能改变程序。脱敏保障依赖已知凭据引用及 canary，不承诺识别任意未知秘密。结果验收检查结构、来源和必要实验，不是所有自然语言结论的自动事实核验。

## 5. 已具备 / 尚未具备

| 已具备且离线验证 | 尚未具备或未验证 |
|---|---|
| 标准 LLM 协议和 Provider 替换 | 真实 DeepSeek 连通性、账号模型权限及真实费用 |
| DeepSeek 非思考模式 Tool/JSON/SSE Adapter | beta 严格 Schema、实时逐字 CLI |
| 单 Mock Skill 的受审注册、元数据发现、按需加载 | 多 Skill 任务选择、完整专业研究方法库 |
| Tool 白名单、Schema、资源和版本校验、默认拒绝 | 真实数据、Pyx、回测、生成代码执行 |
| 有理由的模拟迭代、结果验证、预算、状态恢复 | 真实自主研究价值、稳健性/风险分析、多任务后台 Worker |
| SQLite 任务历史、实验和独立授权事件 | 跨任务长期经验检索、生产审计隔离与篡改检测 |
| 本地 CLI 和 wheel 运行 | Linux 实测、服务器部署、OS 硬资源限制 |

当前 CLI 的自然语言输入入口已经存在，但 Mock 不理解任务。没有把“可以输入文字”当成真实研究智能；这项能力要由下一阶段真实 Provider 的端到端实验验证。

## 6. 未来接口与第一批开发任务

1. **真实 DeepSeek + Mock Tools**：在装配层增加可信操作者启用的 development profile，独立 SecretStore 引用、小预算真实 Tool Calling 回归。模型不能自行启用网络或换 Key。
2. **服务器开发接入**：确认已有非 root 身份和本项目写区，提出准确部署范围；只部署独立新项目，不覆盖旧 Agent，不自行建立用户或改权限。
3. **数据资源合同**：来源、覆盖、频率、可获得时间、复权、Schema、内容指纹和允许切片范围；封闭 `describe_resource/read_data_slice` 工具。
4. **固定因子研究 Tool**：经审查的代码实现和版本，通过小样本统计基准；指标由程序算，模型负责假设、诊断和有依据的下一轮选择。
5. **Worker / Runner 接口**：结构化授权任务、状态/取消、幂等提交、清空凭据环境、结果合同和不确定状态恢复。未知代码执行维持禁止。

详细预算、目录、依赖关系与后续确认事项见 [NEXT_INTEGRATION.md](legacy__NEXT_INTEGRATION.md)。不需要重新做 Phase 0，也不要求先购买独立 CPU VM。

## 7. 最新开发策略及验收点

最新策略已写入 [DEVELOPMENT_STRATEGY.md](legacy__DEVELOPMENT_STRATEGY.md) 与项目 `AGENTS.md`，后续排序以 Development First, Production Hardening Later 为准。

建议本轮验收：在本地运行 `demo`、`chat`、一次 `--max-steps 1` 暂停/恢复，检查模拟结果和拒绝证据。审核通过后，下一阶段先做真实 DeepSeek 与 Mock Tools 的接入；服务器真实研究需要另行确认身份、数据发布和程序范围。本轮没有进入这个阶段。
