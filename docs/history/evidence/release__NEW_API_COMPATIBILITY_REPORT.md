> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 新 API 独立兼容性验收（2026-10-12）

**归档状态：2026-10-12 用户决定停止逍遥 API 适配与迁移。下文为历史验收证据，切换计划已撤销。正式入口继续使用 DeepSeek 官方 API。**

**判定：PARTIALLY_COMPATIBLE；现有 Research Agent v0.6.8 不可直接切换。** 网关可完成中文聊天、上下文对话、原生 Tool Calling、工具结果回传与 SSE；但结构化 JSON 未通过现有 Provider 校验，实际 Agent 的第一轮 Mock 聊天即以 `INVALID_STRUCTURED_OUTPUT` 结束。生产配置、主 Agent、真实研究数据均未改动。

## 隔离方式与真实结果

测试端点为 `https://www.xiaoyaoapi.com/v1`，凭据只在本次交互式测试进程内输入；证据文件仅保存状态、模型标识、用量与安全错误码，不保存密钥、Authorization、请求正文或完整模型响应。最初已配置的 `deepseek-flash` 请求两次得到 HTTP 503；认证 `/models` 返回 200，并列出 `deepseek-v4-flash`、`deepseek-v4-pro` 等模型 ID。对 `deepseek-v4-flash` 的最小原生协议测试结果如下：

| 项目 | 实测 |
|---|---|
| 中文普通对话、多轮上下文 | HTTP 200，回答和上下文可用 |
| `response_format=json_object` | HTTP 200，但未通过所请求的结构化数值合同 |
| Tool Calling | HTTP 200；工具名、JSON 参数、`tool_call_id` 正确 |
| 工具结果回传 | HTTP 200，模型继续回答 |
| Token / 费用 | 返回 token 用量；费用未返回、不可推断 |

对**现有** `DeepSeekAdapter` 做进程内端点替换、保持 v0.6.8 源码不变，并选用它声明支持的 `deepseek-v4-pro`：聊天、Tool Calling、结果回传和流式事件通过；结构化输出返回 `INVALID_STRUCTURED_OUTPUT`（本地解析为 `invalid JSON`）。更严重的是，网关在该模型的成功响应中将实际模型标为 `claude-opus-4-8`，与请求的 `deepseek-v4-pro` 不一致，模型来源和研究账本不可准确追溯。在 `build_chat` + Mock Registry + 临时 SQLite 的一轮“你好”测试中，状态 `MODEL_ERROR`、错误 `INVALID_STRUCTURED_OUTPUT`、模型调用 1 次、未创建研究任务。

证据：`api_compat_evidence.json`（原内部附件未公开）、`api_compat_adapter_evidence.json`（原内部附件未公开）、`api_compat_agent_evidence.json`（原内部附件未公开）。第一次尝试的 503/超时见 `api_compat_evidence_attempt1.json`（原内部附件未公开）。测试脚本分别为 `api_compat_probe.py`（原内部附件未公开）、`api_compat_adapter_probe.py`（原内部附件未公开）、`api_compat_agent_probe.py`（原内部附件未公开）。仅使用 Mock Tools；**没有**向第三方网关传 GPUShare 行情、服务器秘密、研究记录，也没有做 `daily65` 或因子研究的真实网关调用。

## 对 v0.6.8 的具体影响

- `DeepSeekAdapter`（原内部附件未公开） 将官方 DeepSeek 端点写为模块常量；`agent.toml`（原内部附件未公开） 中没有 Base URL 配置，现有 Provider 模型为 `deepseek-flash`。仅更换环境变量的 Key 不会切换网关，直接换 URL 也不是已验收的配置操作。
- 该 Adapter 的能力表只为 `deepseek-flash` 和 `deepseek-v4-pro` 声明结构化输出与工具调用。网关 `deepseek-v4-flash` 的普通聊天通过，不等于当前模型无代码改动即可注册使用。
- 现有工作流依赖结构化计划与校验；JSON 失败会阻断 Mock 聊天，故数据研究 Skill、因子研究 Skill、DSL、替代确认门、默认 PKL、HTML/LaTeX、时间目录、预算与失败恢复的**新网关端到端验收均未达到**。这些既有功能在原 Provider 下的历史验收不受本次测试影响。
- 本轮没有制造 401/402/429/异常 HTTP JSON 的真实错误响应；客户端对应分类属于代码检查或旧测试证据，不能列为该网关实测。503、超时和 `INVALID_STRUCTURED_OUTPUT` 已实测。Token 数返回，费用未知。

## 最小切换计划（本轮不执行）

1. 供应商先书面明确模型 ID、实际模型映射与 JSON/tool 协议，并修复或解释请求 `deepseek-v4-pro` 却返回另一模型标识的问题；未澄清前不发送真实研究数据。
2. 用户重置已在聊天中披露的网关测试 Key，使用独立秘密引用注入新 Key。增加可审计的测试 Provider/端点配置，不改原 `deepseek` 默认项；端点必须固定在经批准的 HTTPS 主机，不能由模型或 Tool 指定。（此项现已取消。）
3. 先通过结构化输出、模型身份、Mock Tool/Skill、确认门与预算回归；再单独审批向第三方发送 `gpushare:daily65` 的数据范围与隐私影响。完整 Agent 流程通过后，才讨论生产入口切换。
4. 回滚：停止选择新测试 Provider，恢复原 `deepseek` Provider 与官方端点配置；SQLite 历史任务、原模型 Key 与数据资源保持原位。不得把新网关 Key 写入源码、命令行参数、日志或报告。

当前无需切换：原 Provider、主 Agent v0.6.8 与服务器运行入口均保持原状。
