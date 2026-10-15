> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Research Agent v0.8.1 — Phase 3-C 最终修复候选



生产基线为v0.8.0；本目录是独立候选，正式替换及最新报告指针更新须获最终批准。



本补丁统一连续时间轴与两条分区竖线；累计IC/RankIC跨分区延续。无成熟标签的日期不生成数值，缺Test逐日分组数据时曲线止于Validation。PNG/SVG/PDF和离线交互HTML共用同一聚合CSV。



已有研究查询由模型路由到只读流程，权限仅允许qrtk_read_study；每次核验最新已认证revision，保留Test置信区间、月度观察日和标签成熟原因。原2026评价不重跑，不读取私有数据，不改变原定义、统计量或曝光预算。



仅接受已审定v0.8.0核心到当前核心的会话升级，Provider、配置、Skill及数据合同必须完全一致；旧任务授权不复用。



## 历史阶段说明



独立的量化研究 Agent 核心，可运行离线 Mock 或明确启用的真实 DeepSeek development profile。代码位于 `<ARCHIVE_ROOT>`，Linux 项目目录为 `/opt/jijigua-quant-agent/research_agent/`。旧 StratFlow、GeorgeResearch 和 Quanttrade 的原项目未修改；受审的 Claude quant_toolkit 0.2.0 计算模块以内容指纹快照导入本项目，不启动其独立 Runtime。



## Phase 2-C 默认因子资产与专业报告



每次固定因子或19算子表达式因子成功计算后，可信计算流程自动导出并验证 `factor.pkl`，不依赖模型另选导出工具。主格式为服务器实际消费的日期×股票 float64 面板：YYYYMMDD字符串日期、经过静态样本核对的交易所后缀代码、NaN原样保留。另有 `.pkl.zip`、六位代码面板及 Perry 字典适配文件；明确区分不同消费合同。固定协议4、原子写入、数值读回、SHA-256、元数据与manifest同时归档；失败为EXPORT_FAILED，保留计算值，不能宣称完整交付。不加载任何未知/外部pickle；读回仅接受与当前可信固定写入器字节完全一致的自产文件。



复用 qrtk 原IC/RankIC、分组及共同股票相关性公式，新增Lag1/5/10值与秩自相关、分段半窗稳定性、成熟标签预测期衰减、有效样本、偏度/超额峰度、分位数、MAD异常率与连续缺失。ICIR未年化；Bartlett HAC仅在完整序列及保守样本门槛满足时输出近似区间，daily65为insufficient。排序换手代理不是实际账户换手。



报告首页直接展示结论、样本与核心指标小表；每个专题都有程序数值表。7类图表，父子实验另加对照图；双栏布局、独立表格滚动、可展开附录、离线自包含HTML以及同步Markdown。优先适配 GeorgeResearch/backtest.ipynb 最后一个cell调用的 core_backtest.plotting.plot_final_result（配色、百分比标注、网格及图例）；Perry仅提供中文字体选择，英文图表采用DejaVu Sans，中文字体作备用；没有继承未准入账户收益公式。固定因子与表达式均支持parent_study_id；查询、复核或修复已有PKL不重新计算因子、不覆盖旧产物。



新成果采用 Asia/Shanghai 实际时间的 research_runs/YYYY-MM-DD/HH-MM-SS_factor_name，冲突自动加后缀；ID仍在账本与manifest，历史UUID目录不迁移。公式从校验后的AST/固定参数生成LaTeX，以Matplotlib mathtext内嵌SVG离线排版；Markdown与.tex保留数学源码。



SSH入口仍是 `quant-agent chat`。成功后自动显示PKL、HTML与成果目录。详细源码、PKL消费合同、数值与视觉验收见 Phase 2-C 交付报告（原内部附件未公开）。账本聚合上限独立为1MiB，模型/Tool JSON仍为64KiB；不扩大模型参数或文件权限。



### v0.6.6–0.6.8 研究定义确认门



用户的研究定义（窗口、跳过期、预测期、频率、数据范围、股票池、公式或因子族）受数据或工具限制时，Agent 不得自行改用替代定义。工作流在调用新建研究的 Tool（`qrtk_factor_study`、`qrtk_expression_study`）前执行确定性检查：规划声明了 `definition_change`，或因子名带 exploratory/substitute/proxy 等替代标记，程序随即关闭数据探查，只允许提交一个替代计算或不提交：替代参数通过 Schema、策略、数据合同和样本检查（只读 validate-only，不计算）后进入 `AWAITING_CONFIRMATION`，否则进入 `BLOCKED_UNSUPPORTED` 并说明缺少的能力；相同参数的重复调用作为兜底进入 `BLOCKED_NO_PROGRESS`。路由层也可用 `action=propose` 提出替代方案；程序随即以提案模式运行计算 Skill，只生成并拦截具体 Tool 参数，不计算。数据核验（`data_research`）完成的同一轮，路由层再判断一次原定义是否受阻，受阻时同样给出带参数指纹的具体方案。



提案保存在会话中。只有模型判定用户同意（`consent=accept`）且用户原话也是明确肯定时，程序才执行已保存的方案；确认后程序直接执行已保存的参数（不再由模型重新生成），定义指纹必须一致；只有指纹的授权遇到不同参数会再次拦截。用户在没有提案时先拒绝替代，也不保存任何提案。用户拒绝时清除提案、保留原研究定义，不运行替代实验。确认后的成果照常生成 PKL、HTML、图表和指标表，并在回答中注明原定义尚未完成。参数 Schema 错误仍为 `INVALID_PARAMETERS`，策略拒绝仍为 `AUTHORIZATION_DENIED`；确认门在两者之后执行，不放宽 Schema 或权限。详见 确认门修复报告（原内部附件未公开）。



## 保留的研究能力与边界



五个专业 Skills 通过现有 Skill Registry 和授权系统接入。保留反转/放量滞涨固定因子；`qrtk_expression_study` 接收受控算子 DAG，由程序计算新因子、IC/RankIC、分组毛收益和图表报告。`parent_study_id` 关联同一会话父实验并比较参数；历史成果不覆盖。`strategy_backtest` 仍只检查准入，不执行未验收账户引擎。没有动态代码、路径或子进程入口。



表达式允许 OHLCV、常数、历史 delay/diff/returns、rolling mean/std/rank/corr、横截面 rank/zscore、受限四则及 min/max/abs/neg。最多40个节点、8层、窗口1—60、累计历史120；算子检查量纲、先前节点、零分母/缺失和全窗口暖机。参数与生成理由记录在 manifest 和 code/factor_definition.json；code/reproduce.py 用已发布切片交叉复现因子值。



真实发布资源 `gpushare:daily65` 为 2026-07-03—2026-10-09 的 50 只股票、3163 行原始未复权行情。公司行动、完整交易日历和历史可获得时间尚未验证，只允许探索性计算。`sealed` 只隐藏本计算工具测试统计：原始数据仍在其他授权路径，**不是全系统独立盲测**。未来可信资源清单可设置全局 `withheld_from`，拒绝所有别名/工具发布或读取该日期后的数据；尚未发布真正独立样本外资源，也未启用解封评测。



启动仍为 `quant-agent chat`。事件驱动的终端展示真实阶段、状态和耗时；只有实际图表计数等分母明确时显示百分比。新成果保存在 `/srv/jijigua-quant-agent/research_runs/<task_id>/<run_id>/` 的 code/data/figures/reports/logs 和 manifest.json。原 SQLite 不迁移；旧会话可查看，版本变化后请新建执行会话。



固定白名单计算保持小样本、BLAS单线程、20MiB/100文件产物边界。任务最多4轮/8模型/6工具；模型使用60k token保守预留及实际统计，会话累计300k，未知调用使用请求大小预留但费用未知。阶段40次、前台600秒/单工具120秒在执行边界检查，**不是OS硬隔离或抢占式计算超时**。Ctrl+C 取消；SSH 断线不保证任务继续。完整工具结果留账本，模型只接收必要摘要；路由不重复传详细工具Schema。



本地安装计算依赖使用 `requirements-research.lock`；可信配置通过 `--resources-manifest` 和 `--research-config` 指定。服务器启动器自动使用已批准的配置。`/hy-tmp` 的保存期限见 [GPUShare 存储说明](https://gpushare.com/docs/data/storage/)；重要成果需要另行备份。详细验收与边界见 Phase 2-B 报告（原内部附件未公开），原 Phase 2-A 报告（原内部附件未公开） 保留。



默认 Provider 仍是固定脚本式 Mock，输入任意研究任务仍运行同一个模拟例子；它不具备自然语言研究理解能力。development profile 的 DeepSeek 原生工具循环已在真实 API 上运行成功。真实数据使用可信清单、小型只读 CSV/Parquet 和资源 ID；通用研究 Runner 仍未开放。



## 真实模型与 Linux 入口



本地真实 DeepSeek（隐藏输入 Key，或仅使用明确的 `QRA_DEEPSEEK_API_KEY` 环境引用）：



```powershell

.\.venv\Scripts\python.exe -m research_agent --profile development --provider deepseek --prompt-key ask "比较模拟数据的3期和5期指标，给出模拟摘要。"

.\.venv\Scripts\python.exe -m research_agent --profile development --provider deepseek --prompt-key chat

```



服务器已完成 Linux 安装和 Mock 回归；你们沿用 root SSH 登录方式，直接执行：



```sh

quant-agent chat

quant-agent ask '描述已授权日频资源的日期、字段和缺失情况，并读取5行示例。'

quant-agent status <task_id>

quant-agent logs <task_id>

quant-agent result <task_id>

```



root 管理的启动脚本在导入 Agent 前自动切换至 `quantagent`、清除附加组和无关环境。Key 通过隐藏输入进入进程，不写入服务器文件或命令参数。真实 `chat` 由模型自主判断回答、澄清或选择受审 Skill；问候不强制查数据。默认打印中文回答，状态提示在 stderr，诊断 JSON 仍通过 status/result/logs 查看。同一账号不提供不同使用者之间的隐私隔离。



同一个 chat 保存独立会话，多个研究任务/实验关联同一 session。使用 `/skills`、`/tasks`、`/history`、`/session`、`/help`、`/exit`；用 `quant-agent chat --resume <session_id>` 显式恢复。默认新会话不混入其他会话历史。最近六轮对话与最多六条经过工具验证的实验摘要作为上下文，完整对话和实验留在 SQLite 供查看；总上下文控制在约16KB，会话最多50轮/100次模型尝试。长期经验检索和自动崩溃接管尚未实现，异常在途会话拒绝自动恢复。



真实调用与模拟输入分别记录 `execution_mode=live_api` 和 `result.mode=synthetic`；真实数据返回 `mode=real_data`，普通回复记录 `mode=conversation` 并关联独立 route_task_id。不能仅凭模型名字判定真实调用成功。验收结果见 Phase 1-F 报告（原内部附件未公开），Phase 1-E 历史报告（原内部附件未公开）保留。



## 立即运行



此工作区已安装本地开发环境。在 PowerShell 中：



```powershell

cd <ARCHIVE_ROOT>

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\demo demo

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\chat chat

```



上述不指定 Provider 的 chat 是历史离线 Mock：返回固定模拟任务结果，不代表模型理解。真实模型聊天请使用前面的 development / deepseek / --prompt-key 命令；输入 `/exit` 退出。



任务创建、暂停、恢复与查询：



```powershell

$task = (.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\manual create "查询模拟量价数据并比较两个窗口" | ConvertFrom-Json).task_id

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\manual run $task --max-steps 1

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\manual status $task

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\manual run $task

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\manual result $task

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\manual logs $task

```



全局参数 `--state-dir`、`--provider` 必须放在子命令前。`qra.exe` 与 `python -m research_agent` 等价。`--state-dir` 由可信操作者选择，必须使用自己的独立工作区；模型没有文件写入工具，不能选择这个目录。



替换 Provider 配置进行相同模拟研究：



```powershell

.\.venv\Scripts\python.exe -m research_agent --state-dir .qra-state\alternate --provider mock_alt demo

```



## 安装与复现



支持的语言基线为 Python 3.11+；实际验证 Python 3.12.4 / Windows 11 和 GPUShare Linux Python 3.11.10。当前本地 `.venv` 与打包验证用 `.venv-wheel` 继承本机依赖；服务器 `.venv` 不继承系统 site-packages。两者都不是安全沙箱。



在新的 Python 3.12 环境安装：



```powershell

python -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements.lock

.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .

$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'

.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml

```



安装依赖可能需要包源网络。测试本身不需要网络，`tests/conftest.py` 阻断 socket 连接；禁用第三方 pytest 自动插件，避免运行与项目无关的插件。



Linux 以 root 直接启动引擎或 CLI 会在访问账本前被拒绝；应使用可信 `quant-agent` 启动器。GPUShare 基础 Python 缺少 ensurepip，部署脚本使用 `venv --without-pip` 和 pip `--python` 将依赖装进独立 venv，保持安装过程为 quantagent，未修改系统 Python。Windows 不用 `geteuid` 判断管理员身份，没有宣称 Windows 身份隔离。



当前 wheel 在 `dist/wty_research_agent-0.3.2-py3-none-any.whl`，包含两个 Skill、Policy 和配置资源。旧版本和历史报告保留用于对照与回退。包外文档、部署脚本和测试不包含在 wheel 中。服务器使用 CSV，未安装可选 PyArrow；本地小型 Parquet 合同测试通过，服务器 Parquet 尚未验证。



## 项目结构



```text

ResearchAgent/

├── AGENTS.md                     当前开发范围与边界

├── CONTEXT.md                    领域术语

├── pyproject.toml                包、依赖、CLI 入口

├── requirements.lock             本轮环境版本记录

├── src/research_agent/

│   ├── llm.py                    模型无关协议、能力、凭据引用、脱敏

│   ├── providers/

│   │   ├── mock.py               固定、可复现的模拟决策

│   │   └── deepseek.py           DeepSeek HTTP/SSE Adapter，真实网络默认关闭

│   ├── contracts.py              有界 JSON、Schema 与指纹

│   ├── skills.py                 元数据发现、按需加载、权限及哈希检查

│   ├── tools.py                  类型化白名单与两个 Mock Tools

│   ├── data.py                   清单、指纹、只读 CSV/Parquet、三项资源 Tools

│   ├── security.py               Policy / Authorization / Skill 权限交集

│   ├── workflow.py               有预算的规划、调用、反馈状态机

│   ├── runtime.py                会话与研究共用的模型调用/重试/审计

│   ├── conversation.py           模型驱动回复/澄清/Skill路由和有界记忆

│   ├── terminal.py               中文聊天、终端编辑、会话命令

│   ├── acceptance.py             经登记的确定性 Skill 结果验证器

│   ├── store.py                  SQLite 检查点、实验、独立授权事件

│   ├── app.py                    配置装配，不含量化业务决策

│   ├── cli.py                    create/run/status/logs/result/demo/ask/chat

│   └── resources/                mock_research / data_query 两个受审 Skills

│       ├── agent.toml

│       ├── policy.toml

│       ├── approved_skills.json   审阅后的固定文件哈希

│       └── skills/mock_research/

│           ├── SKILL.md

│           ├── skill.toml

│           ├── input.schema.json

│           ├── output.schema.json

│           └── example.json

├── tests/                        Provider、安全、状态机、CLI 回归

├── scripts/verify_offline.py      Phase 1-D 历史验收脚本，绑定 v0.1.0

├── scripts/verify_remote_live.py  两条真实 API 链路与脱敏证据导出

├── deploy/                       可信 root 启动器，切换身份后执行 Agent

├── docs/                         报告、最新策略、下一阶段计划、JSON/XML 证据

└── .qra-state/                   本地开发任务状态；不随包发布

```



## 模块如何协作



Workflow 先请求符合 Schema 的研究计划，再请求原生 Tool Calling；最多四个调用逐项授权、顺序执行，并在预算不足时整批拒绝。模型可以选择工具与参数，不能改变权限。JSON 计划与 Provider 专有工具返回结构互不混用；研究模块只使用统一协议。



Skill 定义方法、Tool 版本、资源范围、预算与验收；Tool 提供确定性接口；Policy 和任务 Authorization 决定是否允许调用；Workflow 决定执行顺序；SQLite 保存状态和证据。模型计划中的 `approved` 不构成授权，也不允许出现在封闭计划 Schema 中。



SkillRegistry 先发现受审小型元数据，真实 chat 让模型从批准且配置可用的目录自主选择；选中后才加载方法、合同、Tool与权限。普通聊天不加载研究方法。直接 ask/demo/run 仍保留显式 Skill 方式。它是本项目的 Skill 格式，不声称与 Codex Skills、旧 YAML Skills、Plugins 或 MCP 自动兼容。



新 Skill 需要人工审阅、登记文件哈希、绑定已注册 Tool 与确定性验收器、增加固定示例和安全回归。不能从 Skill 导入任意 Python 验证器，也不能通过修改声明获得额外权限。



## Mock 研究示例



输入：查询模拟量价数据，计算模拟因子指标，判断是否需要进一步实验，并生成模拟研究摘要。



| 步骤 | 实际行为 | 可检查证据 |

|---|---|---|

| 1 | 计划查询固定 6 行模拟数据，调用 `query_mock_data` | 资源 ID、数据 SHA-256、来源标记 `synthetic` |

| 2 | 假设联合指标对窗口敏感，调用 `compute_mock_factor(lookback=3)` | 指标 0.03167420814479627 |

| 3 | 解释将窗口从 3 改为 5，再调用同一 Tool | 指标 0.04698774962241991 |

| 4 | 检查两个窗口和来源，输出模拟摘要，结束 | `COMPLETED`，4 轮计划、7 次模型尝试、3 次工具尝试 |



模拟指标为 `(last_close / first_close - 1) * (last_volume / mean_volume)`，仅演示参数对照和流程，不是已验证金融因子。数值、理由、代码/数据/Skill 指纹和 Provider 配置见 mock-run.json（原内部附件未公开） 与 mock-events.json（原内部附件未公开）。



## 状态、预算与恢复



默认上限：4轮计划、8次模型尝试、6次工具尝试；重试和拒绝也计数。真实模型单次输出至多2,048 tokens、请求超时20秒、至多1次重试。研究任务累计模型预算60,000 tokens，会话累计300,000；未知用量按请求UTF-8字节和输出上限保守预留，不称实际费用。请求前检查预算，实际响应超限即停止；没有金额硬限。用户只能缩小任务预算，Policy、Skill 与任务预算取交集。



`MODEL_ERROR`、`TOOL_ERROR`、`EXPORT_FAILED`、`AUTHORIZATION_DENIED`、`BUDGET_EXHAUSTED`、`INVALID_RESULT`、`AUDIT_ERROR` 分开记录。PKL失败保留计算结果，可在新任务目录修复。失败任务停止，不会假装实验无效后继续盲目调参。未知用量为 `null`；Mock 用量是固定合成记录，不代表 API 费用。



`run --max-steps 1` 在完整工具批次结果落盘后停为 `PAUSED`，可以新进程恢复，预算不重置。配置、代码、Skill 或资源清单改变后拒绝继续旧任务。未知在途操作、未完成批次拒绝重放；遗留 `RUNNING` 不自动接管。没有后台 Worker、租约、自动崩溃修复或长期经验检索。



## 当前安全边界



所有模型工具请求通过程序授权和封闭 Schema；只接受清单资源 ID，不接收任意路径、Shell、Python、交易参数。Data Tools 单文件最多4 MiB、最多10,000输入行、最多200返回行；首次样例取5行。输入指纹不一致、链接文件、额外参数或越权范围均拒绝。Tool 请求和许可先落盘，再执行处理器；账本不可写时停止。授权与实验记录分表，模型不能自行生成授予记录。



无子进程研究执行器、任意代码执行器或未知pickle加载。唯一读回例外为与同进程固定写入器序列化字节完全一致的自产数值因子文件。通用 Runner 返回 `BLOCKED_SECURITY`；离线 profile 仍拒绝真实 Provider。只有可信操作者明确选择 development profile 后，Adapter 才能请求固定 HTTPS 端点；模型没有这个配置入口。部署/预检脚本是独立管理工具，不注册为 Agent Tools。



CPU/内存/PID字段是声明，未实施操作系统硬配额。程序执行调用/Token/输入行数/文件大小/表达式规模上限；任务600秒、工具120秒及40阶段限制在合作式边界检查，不是进程树硬超时。终端渲染线程不执行后台研究，SSH断线不保证继续。本地同一账号可以编辑代码和账本，当前日志不是生产级防篡改审计；链接检查也不是恶意进程竞争下的文件系统隔离。正式生产加固后续完成。



## 交付与后续



- Phase 2-C 交付报告（原内部附件未公开）、服务器源码与消费合同（原内部附件未公开）、指标合同（原内部附件未公开）

- Phase 1-F 交付报告（原内部附件未公开）

- Phase 1-E 历史交付报告（原内部附件未公开）

- Phase 1-D 历史报告（原内部附件未公开）

- Phase 1-F 测试结果（原内部附件未公开）、Windows JUnit（原内部附件未公开）、Linux JUnit（原内部附件未公开）

- 实际拒绝及失败证据（原内部附件未公开）

- 最新开发策略（原内部附件未公开）

- Claude Tools、专业 Skills 与回测引擎接入入口（原内部附件未公开）



采用 Development First, Production Hardening Later：真实模型与只读数据开发优先。生产沙箱、整树资源硬限及后台持久任务另行建设；不把当前开发部署称为生产加固完成。

# Phase 3-B2-C v0.7.0



此工作区保留独立 v0.6.8 源码 ZIP 和逐文件指纹。用户批准后已完成GPUShare生产入口更新及真实SSH PTY验收；原Windows主项目基线保留，新实现位于本工作区。



- 通过已有发布读取器使用固定 Train2020–2023 与 Validation2024–2025；不打开原始 PKL。

- 完整 5427 股票轴；19 算子受控 DAG，最大 800 万单元、120 观察日累计历史。

- Train 因子研究、受控 Train 暖机、冻结定义后的 Validation 评价；标签退出跨分区时剔除。

- 默认全轴服务器兼容 PKL、指标 CSV、离线公式、PNG/SVG/PDF 图表和 HTML/Markdown。

- 已曝光 Validation 记账；2026 不发布，新 profile 拒绝旧 daily65/daily20 读取。旧资源登记与历史记录保留。

- 六字段仅 PROFILED_EXPLORATORY_ONLY：原始未复权收益不是总收益、数据未获账户回测准入。

- 每个计算最多 512 MiB 成果，工具阶段检查最多 600 秒；这是开发预算与规模控制，不是硬沙箱。



交付证据与最终审批清单：`docs/phase3b2c/`。主 Agent 官方 DeepSeek Provider 与秘密输入方式保持不变。







## v0.8.2 定向收尾



可选的操作者配置 `config/report_catalog.json` 只登记明确共享的研究报告；文件与研究配置属于同一可信配置边界。Linux文件须与研究配置同一所有者且组/其他用户不可写。新会话通过原只读工具访问已登记报告，不自动导入聊天历史。Test普通行情资源仍封闭。

