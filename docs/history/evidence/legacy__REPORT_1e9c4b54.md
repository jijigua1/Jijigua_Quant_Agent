> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 1-F 交付：真正的自然语言交互

日期：2026-10-12。版本：**v0.3.2**。

沿用 `<ARCHIVE_ROOT>`，已更新 GPUShare `/opt/jijigua-quant-agent/research_agent/`。真实 DeepSeek、自然语言回复、澄清、受控 Skill 路由和同一会话的指代已通过真实 SSH 前台验收。本轮没有重建 Agent，也没有导入旧 Step1–Step9。

## 立即使用

你们仍以原来的 root SSH 方式登录，在任何目录执行：

```sh
quant-agent chat
```

启动时隐藏输入 DeepSeek Key，随后直接输入普通中文。启动器在导入 Agent 前切换为 quantagent；不需要手动切换用户。Key 不写入源码、配置文件、账本、报告或命令参数。

```text
你> 你好
你> 服务器有什么行情数据？
你> 这个数据最新到什么时候？
你> 它能拿来回测吗？
你> 我觉得成交量突然放大但股价没怎么涨，后面可能会涨。
你> 按照这个想法帮我设计一个因子。
```

`/skills` 查看已部署能力；`/tasks` 查看本会话任务、实验和错误；`/history` 查看历史；`/session` 查看会话 ID；`/help` 帮助；`/exit` 退出。Ctrl+C 取消输入或当前请求，EOF 退出。终端支持 Ctrl+H、DEL 退格和带括号的复制粘贴。

```sh
quant-agent chat --resume <session_id>
quant-agent session <session_id>
quant-agent history <session_id>
quant-agent session_tasks <session_id>
quant-agent status <task_id>
quant-agent result <task_id>
quant-agent logs <task_id>
```

诊断命令继续提供结构化 JSON，chat 默认只显示中文回复和简洁的工具状态提示，不显示完整 JSON、转义换行或每轮 Token 表。

## 真实人类输入验收

主会话：`INTERNAL_RUN_ID_REDACTED`。每条是实际 SSH PTY 中的短句，不是长工程提示词。八轮都为 COMPLETED，路由各使用一次真实模型请求；没有格式重试。

| 实际输入 | DeepSeek 决策 | 实际工具 | 结果 |
|---|---|---|---|
| 你好 | reply | 无 | 中文回应与能力说明 |
| 你能帮我做什么？ | reply | 无 | 说明已部署能力和限制 |
| asdfghjkl | clarify | 无 | 追问需求，没有擅自查询数据 |
| 服务器有什么行情数据？ | skill: data_query | list_resources、describe_resource | 自主发现并核验授权快照 |
| 这个数据最新到什么时候？ | reply | 无 | 沿用刚才的证据，回答 2026-10-09 |
| 它能拿来回测吗？ | reply | 无 | 解释单日样本、未知口径和未就绪限制 |
| 我觉得成交量突然放大但股价没怎么涨，后面可能会涨。 | reply | 无 | 提出可检验的量价假设，说明尚未计算 |
| 按照这个想法帮我设计一个因子。 | reply | 无 | 理解上一轮想法，给出定义和验证方案，不编造 IC/收益 |

研究任务为 `INTERNAL_RUN_ID_REDACTED`，关联同一个 session，但 ID 与会话、路由任务分别独立。研究执行有3轮计划、5次模型请求、2次只读工具调用。普通对话的授权工具集合为空；模型选择 Skill 后，研究任务另行从现有 Policy、Skill 和资源范围生成权限交集。

退出后通过 `quant-agent chat --resume` 恢复同一会话，再粘贴“刚刚那个因子，用五日窗口可以吗？”。模型理解为此前的量价因子，讨论五日定义与对照，明确单日快照不能计算，也没有调用工具。恢复后的会话共9轮。

原始证据：完整 SSH 终端记录（原内部附件未公开）、模型决策/授权/工具/实验记录（原内部附件未公开）、恢复与粘贴记录（原内部附件未公开）、恢复账本（原内部附件未公开）。模型提出的因子设计是未计算的候选方案，不是已验证的金融研究成果；真实模型文本也不保证重放时逐字一致。

## 会话记忆及实现

| 文件 | 实际改动 |
|---|---|
| `conversation.py` | 模型选择 reply / clarify / skill；封闭决策 Schema；独立会话；显式恢复；模型输出不能生成授权 |
| `runtime.py` | 会话和研究共用模型预算、重试、错误分类、用量及审计，避免第二套执行循环 |
| `store.py` | 增量增加 sessions / conversation_turns；原任务、授权与实验保留；修订号比较防止覆盖 |
| `skills.py`、`tools.py` | 发现受审元数据和实际工具输入约束；选择后才加载完整 Skill 与合同 |
| `app.py` | 根据可信配置组装可用 Skill；普通聊天不加载研究方法、不读取 CSV |
| `workflow.py` | 复用已有授权执行；接收会话上下文、关联 session、发送简洁状态；保留错误与预算边界 |
| `terminal.py`、`cli.py` | 中文交互、编辑/退出处理、会话命令；原 status/result/logs 兼容 |
| `llm.py`、`providers/deepseek.py` | 模型无关错误/用量，HTTP 分类，JSON 合同及安全的格式失败诊断 |
| `deploy/launcher.py` | 保留身份切换和环境清理；新增只读会话命令不索要 Key |

每次启动默认新建随机会话，不自动混入其他 SSH 会话。传给模型的是最近六轮有界对话和最多六条经过工具验证的实验摘要，后者保留任务 ID、假设、修改理由、参数、结果/数据指纹和关键口径。完整对话、模型决策、工具结果与授权事件仍留在 SQLite，可追溯；不是把全文无限塞进 Prompt。

历史上下文约16KB上限（不含当前系统合同、能力目录和新输入）；每会话最多50轮、100次模型尝试，单轮路由最多2次。研究调用继续受 Policy / Skill / 任务交集限制。模型请求当前最多2048输出 tokens、20秒超时、1次重试。重试计入预算，不能无限循环。累计 Token/费用硬限、自动长期记忆检索和后台 Worker 尚未实现。

仅显式恢复指定会话；Provider 配置、代码、Skill 或数据清单变化时拒绝跨版本继续执行。异常遗留 busy 会话不自动接管或重放。共同使用 quantagent 的人可以查看共同账本，不提供人员之间的隐私隔离。

## HTTP_ERROR 排查与恢复

已读取历史任务 `INTERNAL_RUN_ID_REDACTED` 的脱敏账本：原始证据（原内部附件未公开）。当时在第一条模型请求失败，工具调用为0；旧日志只有 HTTP_ERROR、retryable=false、usage=null，没有 HTTP 状态码。**无法据此确定是鉴权、余额、参数、限流还是服务端错误；原始具体原因仍未知。**

新实现记录安全的状态码与分类：400 BAD_REQUEST；401 AUTHENTICATION；402 INSUFFICIENT_BALANCE；403 PERMISSION_DENIED；422 INVALID_REQUEST；429 RATE_LIMIT；5xx SERVER_ERROR。超时、网络中断、非法响应与输出截断分别记录。429/5xx/超时/网络可有限重试，鉴权和余额等错误不盲目重试；不记录 HTTP 错误正文或 Authorization Header。分类参考 [DeepSeek 官方错误说明](https://api-docs.deepseek.com/quick_start/error_codes/)。

本轮首次真实验收还暴露了独立的 JSON 格式问题和不完整的能力发现信息，失败记录保留：初次失败账本（原内部附件未公开）、安全格式诊断（原内部附件未公开）。随后调整了 JSON 合同位置、完整字段示例、字符串转义约束和带预算的格式修复；无效结果始终不执行工具。已返回的 Token 用量保留，未返回的请求标为 unknown_calls，不把未知费用当作0。实际费用未计算。DeepSeek 官方也说明 JSON 模式偶尔可能返回空内容，见 [JSON 输出说明](https://api-docs.deepseek.com/guides/json_mode/)。这些观察不能反推历史 HTTP_ERROR 的原因。

错误恢复会话：`INTERNAL_RUN_ID_REDACTED`。仅在可信操作者测试进程中注入第一轮两次 TIMEOUT，未发出这两次 API 请求；第一轮 MODEL_ERROR / TIMEOUT、unknown_calls=2。**同一会话第二条输入恢复真实 HTTP，DeepSeek 正常回答**。随后 Ctrl+C 取消输入，EOF 正常退出。未加入生产故障开关或改变服务器配置。

证据：恢复终端记录（原内部附件未公开）、恢复请求与用量记录（原内部附件未公开）。鉴权、余额、限流和5xx分类由离线 HTTP fixtures 验证，没有刻意触发真实账户错误。

## 回归与部署证据

| 环境 | 结果 | 跳过 |
|---|---|---|
| Windows 11 / Python 3.12.4 | 152 passed、1 skipped，20.15秒 | OS 拒绝创建符号链接，错误1314 |
| GPUShare Linux / Python 3.11.10 | 152 passed、1 skipped，6.72秒 | 未安装可选 PyArrow；CSV实际路径已验证 |

Linux 的实际符号链接测试通过。原有测试保持通过；新增覆盖普通回复/澄清无工具、会话隔离/恢复/CAS、非法 Skill/伪造批准、格式修复与用量、上下文/预算、工具失败分类、HTTP状态、超时后继续、终端输出和数据指代。全部自动化回归阻断网络，不需要真实 Key；真人场景是另外的真实 API 验收。

证据：汇总（原内部附件未公开）、Windows JUnit（原内部附件未公开）、Linux JUnit（原内部附件未公开）、本地环境（原内部附件未公开）、部署记录（原内部附件未公开）、服务器身份/权限/原有命令检查（原内部附件未公开）、已知 Key 扫描（原内部附件未公开）。

wheel：`dist/wty_research_agent-0.3.2-py3-none-any.whl`，SHA-256：`8c1c4350634c0aa0b6596ded073d0b5fe801f3cf5dfeb31320b7768f55cf4432`。无新增运行时依赖。安装和 Linux 测试均以 quantagent 执行；Agent UID/GID 为999，CapEff=0，无附加管理员组。程序/配置/快照由 root 管理，quantagent 只能写既有 var 工作区。

只读核对确认原始已知 CSV 与20行发布快照的内容指纹未改变。原有 status/result/logs 与新增 session/history/session_tasks 均可从 root 启动器读取，不请求 Key。没有创建用户、改变共享目录权限、操作其他研究员项目、修改生产服务/定时任务或交易系统。旧版本 wheel 与历史账本保留；回退由可信操作者处理，不自动删除会话表或实验。

## 当前能力与下一步

已具备：真正的 DeepSeek 自然语言入口、连续会话、澄清、按需 Skill/Tool 选择、只读资源发现/描述、预算内重试、实验关联和历史查看。当前真实资源仅 `gpushare:daily20`：2026-10-09、20行、7字段；复权、可获得时间和成交量单位未确认，formal_backtest_ready=false。它不代表服务器全量行情。

尚未具备：任意新因子的实际计算、真实回测、Claude五个专业 Skills/工具包、长期自主后台研究、生产沙箱和整作业树资源硬限制。Mock 仍只计算固定公式，不能替代自定义因子。会话回复是模型推理，工具结果是确定性数据核验；两者在账本中分别记录。

下一批按 [集成入口](legacy__INTEGRATION_f031b0ae.md) 接入 Claude 的受审固定计算函数和专业 Skills，复用现有 Workflow/授权/账本；优先补齐可研究的数据合同与数值对照。不重复开发其因子评价，也不引入第二套 Agent 调度器。非 root、venv、白名单和超时属于开发保护，不能称为正式安全沙箱。
