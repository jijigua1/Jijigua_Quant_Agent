> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-A：量化能力集成与真实数据适配

日期：2026-10-12。版本 v0.4.0，部署根目录 `/opt/jijigua-quant-agent/research_agent/`。沿用主 Agent 的 Conversation、Workflow、Provider、Registry、security.authorize 和 SQLite；没有引入第二套 Agent。通用 Runner、动态代码和真实交易仍未开放。

## 1. 实际检查与集成

`<ARCHIVE_ROOT>` 与 `<LOCAL_RESEARCH_ROOT>/quant_toolkit` 均真实可读。Claude 候选版本为 **0.2.0**，47份源码/合同/方法/测试文件有逐文件指纹，其中12个 Python计算和支持模块以原内容快照导入。启动时复核这些模块的 SHA-256。候选原目录未改动；未复制候选独立调度系统的启动路径。

具体数值与边界审查见 [SOURCE_REVIEW.md](legacy__SOURCE_REVIEW_5d9b5f8e.md)，源码清单见 candidate-source.json（原内部附件未公开）。135项候选合成测试独立重跑，不将其视为市场有效性证据。

| Skill | 实际 Tools，版本均0.1.0 | 状态 |
|---|---|---|
| data_research | list_research_resources / qrtk_data_quality | 已注册受审数据质量工具 |
| factor_research | list_research_resources / qrtk_factor_study / qrtk_read_study | 固定反转、放量滞涨；训练验证IC/RankIC、毛分组、衰减和覆盖；测试封存 |
| strategy_backtest | list_research_resources / qrtk_backtest_readiness | 受限准入检查，**没有启用真实账户引擎** |
| research_diagnostics | qrtk_diagnose_study | 读取本会话真实实验的既有质量/截断重算/证据诊断，未实现完整稳健性搜索 |
| research_reporting | qrtk_export_report | 查看受审固定计算已生成的报告与成果路径；不接受模型捏造数值 |

计算直接复用 qrtk 的因子评价、诊断和报告 handlers。主 Agent 只增加数据合同、两个固定因子构造、受控适配、持久化成果和数值基准。保留原 data_query、Mock、中文聊天及多轮会话。训练60%/验证25%/测试15%、方向+1、lag=1和60个成熟有效日最低标准由主代码冻结，模型不能解封测试段。

## 2. 安全与接口

仅注册7个固定新Tool；参数Schema封闭，资源只用可信resource_id，已有研究只用本会话study_id。Skill权限与系统Policy取交集，不接受code、Shell、path、workspace、reveal_test、额外参数或伪造任务上下文。量化实验的授权类型是 development_research_policy，与模型研究计划及只读数据授权分开记录。

Tool结果包含实现版本/指纹、数据合同/指纹、冻结参数、分段、封存状态、计算证据和成果路径；IC/RankIC/分组统计也有显式输出类型。验证失败停止任务；计算失败保留失败manifest，成果最终化失败标记AUDIT_ERROR，不能留下已完成状态。最近的完整实验引用优先进入有界上下文，避免长JSON截断。

固定入口有数据规模和参数边界：输入≤4MiB/10000行，≤100股票/1000日期，窗口2—20、标签1—10、分组2—5；单次任务≤4轮、8次模型、6次工具，单run产物≤20MiB/100文件，BLAS线程1。Skill中的1CPU/1GiB/PID1/30秒是开发目标声明，**当前没有OS硬配额或通用计算硬超时**；固定小样本实测才是本阶段运行范围，不能称正式沙箱。

## 3. 测试

| 环境 | 主 Agent | Claude 候选 |
|---|---|---|
| Windows Python3.12.4，NumPy1.26.4/Pandas2.3.3/Matplotlib3.8.4 | 178通过、1跳过，39.50秒 | 135通过，17.84秒 |
| GPUShare Linux Python3.11.10，相同三项数值依赖 | 178通过、1跳过，25.97秒 | 135通过，20.59秒 |

Windows跳过：OS拒绝创建符号链接；**Linux此测试实际通过**。Linux跳过：未安装可选PyArrow，Parquet分支未执行；真实发布与计算使用CSV。JUnit文件为 agent-windows.xml、agent-linux.xml、candidate-windows.xml、candidate-linux.xml。没有测试失败。

新增基准覆盖手算Pearson/并列秩Spearman、下一日开盘与成熟标签、固定因子公式/标准化/截断一致性、现金费用和NAV对账；权限、非法参数/路径/代码/解封、跨会话访问、证据篡改、失败manifest和账本状态也经回归。参考账本手算：初始现金2000，买入100×10并付费用5，现金995；卖出100×11、费用5和税1.1，最终2088.9。此案例为合成代码验收。

## 4. 真实数据与部署

获用户分别批准后，只新增成果子目录，并从既有CSV发布固定小样本。批准文件为 ADMIN_CHANGE_REQUEST.md 和 DATA_PUBLICATION_REQUEST.md；执行回执为 data-publication.json。

资源 `gpushare:daily65`：2026-07-03—2026-10-09，65个观察日期、首日排序前50只股票、3163行九字段；CSV 202977字节。SHA-256 `d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8`。OHLC未复权，量为股、额为元；逐行历史可获得时间、交易所日历、停牌/退市/单边限制和公司行动未全部验证。**只允许探索性原始价格统计，不是合格回测输入。** 缺失日期/股票保持NaN，模型不获取任意源路径。

原20行资源指纹保持 `2c02f2d19ec9608fbaebac13a24b17a26dd9364d2c55f0b0b7dac0a3bbc04a47`。原始行情与其他研究员权限不变；未读/转大型pickle，未读/复制88GiB矩阵。配置和发布CSV为root:quantagent 0640，Agent不可写。运行UID=999；原历史错误task仍在原SQLite位置。部署前代码备份在 `dist/phase2a-before-0.3.2.zip`，v0.4.0 wheel与部署指纹见 deployment.json。

## 5. 使用与成果目录

SSH登录后仍直接运行：

```sh
quant-agent chat
# 隐藏输入DeepSeek Key，然后自然语言提问
# 例如：帮我做一个五日反转因子，看看它有没有预测能力。
quant-agent status <task_id>
quant-agent result <task_id>
quant-agent logs <task_id>
```

同一会话可继续问IC、分组收益、诊断和报告，优先读取已计算实验，避免不必要重复计算。新版本改变执行绑定，旧会话可查历史，不自动在新配置下恢复；请新建chat。旧SQLite不迁移。

```text
/opt/jijigua-quant-agent/research_agent/
├── src/研究核心与受审qrtk快照
├── config/resources.json、research.json（root管理）
├── data_readonly/daily20.csv、daily65.csv
├── .venv/
└── var/state/research.sqlite3（原位置）

/srv/jijigua-quant-agent/
├── integration_tests/phase2a/<验收run_id>/
├── research_runs/<task_id>/<run_id>/
│   ├── code/quant_factors.py
│   ├── data/冻结参数、输入切片、因子值、IC和毛分组收益
│   ├── figures/（Phase2B统一布局预留）
│   ├── reports/factor_report/（复用已有MD/JSON/PNG/CSV）
│   ├── logs/task.json
│   └── manifest.json
└── shared_reports/
```

既有 `/srv/jijigua-quant-agent` root755不改，新增直接子目录及phase2a子目录按批准范围设置quantagent权限。每个run使用独立ID；manifest关联task、session、原账本、代码/数据/参数指纹、模型配置、状态、用量和所有产物哈希。CLI返回实际成果及报告路径。

实际挂载：XFS、`/dev/nvme0n1`，容量约300GiB，检查时空闲约73.8GiB。按 [GPUShare官方存储说明](https://gpushare.com/docs/data/storage/)，`/hy-tmp` 为临时实例存储，关机超过24小时会清理，迁移不自动复制。重要成果需下载或另行授权持久备份，本轮未自动上传第三方存储。

## 6. 服务器引擎与 Phase 2-B

Pyx/Perry 当前源码已只读核对，详见 SOURCE_REVIEW.md。尚未完成确定性执行及依赖、复权/公司行动、买卖状态、成交规则和独立NAV对账验收，因此不开放真实回测。qrtk参考账本同样不作为真实市场回测工具。

下一批准确工作：

1. 发布更长、复权和可获得时间可证实的日频历史，补齐交易日历、停牌/单边限制和退市合同；范围超过已批快照时另行批准。
2. 在独立副本验收优先候选Pyx：定义snapshot输入、成交代理/开盘语义、现金/持仓/费用/NAV输出合同，补拒单续持和公司行动案例；跨引擎数值一致后登记固定Tool。
3. 复用已有RESEARCH_STAGE事件做真实进度，禁止伪造百分比。复用本轮结构化IC/分组/账本输出，统一图表和Markdown/HTML报告（PDF可选），不重复实现因子统计。
4. 为每个run增加固定复现命令、实验比较/参数变更理由、验证数据泄漏账本；所有产物沿用当前工作区和manifest。测试段当前持续封存，未来解封需预先设计独立实验验收，不由模型自己请求提升权限。
5. 后台Worker/任务租约/资源硬限制和生产加固仍属后续范围；当前SSH前台不会保证断线后继续研究。

现有基础PNG已查看；日期轴有重叠，Phase2B统一图表布局时修复。本轮没有另写绘图系统，也不将候选基础图称作完整专业图表交付。

`test=sealed` 的准确范围是计算Tool不返回测试绩效、成果切片不导出测试价格/因子；**不是盲测环境或全系统数据封锁**。保留的data_query仍可读取已获准快照的原始日期，跨任务也没有一次性测试解封账本。本样本始终仅作探索，不能声称独立样本外验证。Phase2B需要另外冻结不可供模型查看的独立holdout和访问合同。

## 7. 真实模型验收证据

最终真实SSH会话 `INTERNAL_RUN_ID_REDACTED`：**11轮全部COMPLETED**，UID999，真实返回模型 deepseek-flash，32次模型调用、8次Tool调用；211228 tokens（输入197057、输出14171），unknown_calls=0，实际账单费用未知。完整脱敏原始记录 `live-ssh-console.txt`，便于阅读版 live-ssh-console-clean.txt（原内部附件未公开），原生请求/结果/授权/事件见 `live-session.json`，摘要 `live-verification.json`。

| 实际短输入 | 实际行为 |
|---|---|
| 你好 | 直接回答，0工具调用 |
| 服务器目前有什么适合因子研究的历史行情数据？ | data_research → list_research_resources；说明已批准固定样本，结果标catalog，不冒充全服务器扫描或行情计算 |
| 帮我做一个五日反转因子，看看它有没有预测能力。 | factor_research → qrtk_factor_study，L5/H5/5组/raw；实际计算并保存报告 |
| 给我看它的 IC 和 RankIC。 | 同一会话使用已验证实验摘要回答，未无故重复计算 |
| 这个因子的分组收益怎么样？ | 同一会话读取既有结果语义，解释毛收益，未声称账户净值 |
| 我觉得放量滞涨可能预测上涨，帮我设计并尝试验证一下。 | factor_research → qrtk_factor_study，固定volume_stall，L5/H5/5组/raw |
| 诊断刚刚这个因子的研究结果。 | research_diagnostics → qrtk_diagnose_study，重新授权并验证本会话产物指纹 |
| 给我看刚刚的研究报告。 | research_reporting → qrtk_export_report，实际报告路径 |
| 这个数据现在能做正式回测吗？ | 依据已验证限制回答不能，没有伪造回测 |
| 检查这份数据的数据质量。 | 模型选择研究诊断，读取刚刚因子的既有覆盖/证据；未谎称新建数据样本 |
| 请检查这份数据的回测准入条件。 | strategy_backtest → list_research_resources + qrtk_backtest_readiness，实际读取和校验五个OHLCV面板，返回BLOCKED_DATA_CONTRACT |

五个Skills都在本会话真实选中并调用合法工具。原始行情面板整体缺失率为2.6769%，最高单列缺失率89.2308%；不能据此推断这些缺失一定是停牌。工具未发现已发布行的非正价格或infinity；该检查不证明公司行动或历史可获得时间正确。

### 实际数值（不是模型计算）

训练范围2026-07-03—08-26，验证08-27—09-17，测试09-18—10-09封存。两次实验均固定方向+1、T收盘因子→T+1开盘至T+6开盘的5期标签。每段末6个信号日期purge，因子热身后训练28个有效日，验证仅10个。

| 因子 | 训练IC / RankIC | 验证IC / RankIC | 训练 / 验证 G0−G4平均5期毛收益 |
|---|---|---|---|
| 五日反转 | 0.04977170 / 0.02571445 | 0.15683502 / 0.14984587 | 0.01420202 / 0.02097818 |
| 放量滞涨 | -0.00621975 / -0.04796820 | 0.01976376 / -0.01511167 | 0.00720401 / -0.00642962 |

训练/验证不足60个成熟日，分组非严格单调；未复权、成本与公司行动未建模。两份证据均为 **insufficient**，报告为 incomplete；不能将正IC或正分组毛收益升级为策略有效性或可交易结论。验证段是探索性验证，不是独立样本外测试。

独立 `scripts/verify_real_studies.py` 仅用CSV和Python标准库math重新构造因子、并列秩、IC/RankIC及分组毛收益，**不导入qrtk或Agent计算模块**。两份实际产物哈希通过，全部数值对比最大绝对误差 **1.1102230246251565e-16**，低于1e-12验收阈值。证据见 `real-numerical-baselines.json`。

实际成果：

```text
/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7bf60c1db51b48e1/
/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/957841749d354932/
```

### 首轮失败与修复

首轮会话 `INTERNAL_RUN_ID_REDACTED` 的真实计算成功，但有3次验收失败：资源清单被错误要求含计算证据；诊断/报告任务被模型在没有当前Tool读取时直接complete。原始终端、任务/事件记录保留在 `attempt1/`，未改写为通过。

修复：数据清单按catalog语义验收；计算/读取Skill若缺少当前受授权证据，则记录EVIDENCE_REQUIRED并继续合法原生工具选择，预算和权限仍有效。重新读取验证产物SHA、会话范围，不能用历史模型摘要替代研究验收。补充两项回归后重跑Windows/Linux，再进行上述11轮真实SSH验收全部通过。最终wheel SHA-256 `d41de344780ef9cfeda18e9237ad69ab1e009bd4ccec20bf6564290710d0f9ec`。
