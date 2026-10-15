> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 下一批集成入口

2026-10-12，当前 v0.2.1。以下为待确认的下一阶段任务，本轮未合并 Claude 工具包，也未接入真实回测。

## 1. Claude quant_toolkit v0.2

保留其现有固定计算与数值验证实现，不复制因子评价算法。先提供具体代码/版本、依赖、输入输出示例、独立测试记录与账本定义，再选择一个最小因子评价入口。

| 当前接口 | 接入方法 | 必须验收 |
|---|---|---|
| `tools.ToolSpec` / `ToolRegistry.register` | 用受审 Python handler 包装固定函数，声明工具 ID/版本、封闭输入输出 Schema、risk、资源模式和写区 | 不接受任意代码、命令、模块名或路径；逐项参数验证；固定小样本数值基准 |
| `ToolRegistry.context` | 记录外部实现、依赖和配置指纹 | 实现变化后不能继续旧任务；不得只依赖函数名/Schema 版本 |
| `security.authorize` | Policy、任务授权、Skill 取交集 | 当前只开放 mock / data_readonly；新增固定计算 kind 必须明确增加受控分支及拒绝测试，不能假装是 Mock |
| `workflow` + `store` | 返回标准化 ToolResult；记录假设、理由、参数、输入/结果/代码指纹 | 科学失败与程序失败分开；授权事件先于执行；非法输出不能进入下一步 |

Claude 的独立账本继续作为外部证据，不直接当成 Agent 的授权。通过外部 experiment ID、代码/输入指纹、结果类型建立引用；它的测试通过不等于真实市场有效。大型或后台计算不在同步 handler 内启动未知子进程。

## 2. 专业 Skills

现有注册入口是 `skills.SkillRegistry`，项目格式为 `SKILL.md + skill.toml + input/output.schema.json + example.json`。登记 Tool 版本、资源范围、写区、网络、风险、预算及验收器。新 Skill 需要固定示例、安全测试、人工审阅后写入 `approved_skills.json` 的固定文件哈希；运行时不能自动批准。

验收器通过 `acceptance.VALIDATORS` 中受审确定性函数登记，不从 Markdown/TOML 导入任意代码。CLI 当前显式选择 Skill；增加专业 Skill 时更新 CLI 选项、装配配置与回归，后续再增加小型能力目录及模型选择。不要将旧 Step1–Step9 包装成新 Skills，也不假设 Claude/Codex/旧 YAML Skills 自动兼容。

首批建议顺序：数据口径检查 → 固定因子评价（复用 quant_toolkit）→ 研究诊断 → 回测诊断。前置条件是数据合同与确定性计算基准，不能靠提示词补足。

## 3. 真实数据与合格回测引擎

当前 `data.ResourceCatalog` 从 root 管理的 `config/resources.json` 读取已授权小文件，模型只传 resource_id。当前真实资源为单日20行；复权、可获得时间与成交量单位尚未确认，因此只做描述。

下次发布研究样本前确认：来源/许可、字段单位、交易日/时区、复权机制、可获得时间、证券唯一性、停牌/可买可卖规则、标签成熟约束。CSV 上限4 MiB，先小切片；Parquet 在服务器安装可选依赖并补测后再启用。不扫描/复制88 GiB矩阵，不自动转换 pickle。

回测适配器只包裹经审阅固定入口和最小依赖。至少用合成规则案例核验下一交易日执行、退出时点、成本、复权份额、拒单现金/持仓、停牌、未来数据与收益计算。通过后才登记受控 `backtest` Tool；旧项目代码不在原地修改。

## 4. Provider / Worker

新增模型仅实现 `llm.Provider` 协议，并由 `app.build` 装配、`cli` 暴露可信配置；Skills、业务 Tools、权限和账本继续使用统一消息/ToolCall/ToolResult。显式声明原生工具调用、JSON/严格 Schema/流式能力；缺少必需能力时拒绝，凭据仅由 SecretStore 引用。模型切换运行 Provider、安全与研究任务回归。

Worker 后续消费固定任务合同、授权引用和预算，使用租约、幂等结果提交、取消与恢复协议；不引入通用 Shell。先补累计 token/费用准入、大小/保留策略，再实现后台持续任务。当前 foreground CLI 和 `PAUSED` 检查点不等于 SSH 断线持久执行。
