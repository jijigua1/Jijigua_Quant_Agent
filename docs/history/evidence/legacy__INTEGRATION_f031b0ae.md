> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 1-F 后续集成入口

当前版本 v0.3.2。本轮没有导入 Claude quant_toolkit、五个专业 Skills、Pyx 或其他研究员程序。

## 一个调度系统

`Conversation` 负责模型判断回答、澄清或选择 Skill；实际研究继续交给现有 `Workflow`，其调用仍经过 `security.authorize`。外部计算程序只能作为受审 Tool handler，不能把另一套 Agent 调度器装进来。

| 入口 | 后续需要做的事 | 当前约束 |
|---|---|---|
| `tools.ToolSpec` / `ToolRegistry.register` | 包装 Claude 的固定计算函数，登记版本、封闭输入输出 Schema、资源模式和实现指纹 | 不接受任意代码、模块名、Shell 或服务器路径；不重复编写因子评价算法 |
| `ToolRegistry.discover()` | 对模型公开工具说明和输入约束 | 返回元数据，不执行处理器，不授予调用权限 |
| `skills.SkillRegistry` | 审阅 SKILL.md、skill.toml、输入输出 Schema、固定例子，登记文件哈希 | 新 Skill 的网络、目录、工具和预算不能扩大系统 Policy |
| `app.build` / `app.build_chat` | 为新 Skill 明确绑定注册工具、Policy 和资源配置，再加入可用目录 | 当前只绑定 mock_research 和配置可用的 data_query；仅放入文件不会自动启用 |
| `acceptance.VALIDATORS` | 登记受审的确定性结果验收器 | 不从 Skill 文本动态导入 Python；坏结果不能进入后续实验 |
| `security.authorize` | 新增固定计算工具种类时明确审查允许范围、参数与写区 | 当前仅开放 mock / data_readonly；不能把真实计算冒充 Mock |
| `Workflow` / `TaskStore` | 保存实际参数、假设、修改理由、输入/代码/输出指纹，与同一 session 关联 | 外部账本仅是证据引用，不能冒充本系统授权 |

模型选择新 Skill 后才加载完整方法和合同。会话决策使用封闭 Schema，只允许程序登记的 ID；非法选择不会启动研究。新增专业 Skill 要同步注册合同与验收器、装配绑定、旧 CLI 显式 Skill 选项及安全/数值/路由回归。

## 推荐顺序

1. 取得 Claude 工具包代码版本、依赖、固定输入输出和独立账本定义。
2. 核对来源、复权、成交量单位、可获得时间和交易日，发布适合研究的小型数据合同。
3. 接入一个固定因子评价入口，先做数值对照和拒绝测试，再做小规模真实研究。
4. 按实际工具能力接入五个专业 Skills；没有对应工具的部分仅作方法说明，不能宣称计算已实现。
5. 回测引擎单独验收下一交易日执行、成熟标签、交易资格、费用、停牌/拒单及现金/持仓/NAV，再绑定固定 Tool。

当前单日20行快照只能核验基础数据描述。不能靠新增 Markdown 填补历史跨度、复权或执行口径。

## Provider 与后台执行

业务层仍只使用 `llm.Provider`、统一 Message / ToolCall / ToolResult / ModelResponse。新 Provider 在装配层明确注册，并声明工具调用、JSON、严格 Schema、流式能力；不能默认假装兼容。凭据留在独立 SecretStore，模型和 Tools 不得访问。模型切换需重跑路由、授权和研究任务回归。

后台 Worker 后续通过固定任务合同、授权引用、预算、租约和幂等提交接入 Workflow。当前前台 CLI、调用超时与 venv 不等于 Worker 或安全沙箱。本轮不增加后台进程或生产服务。
