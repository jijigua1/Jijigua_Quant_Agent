> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 1-E 交付报告

完成日期：2026-10-12（Asia/Shanghai）。版本 **v0.2.1**。沿用 <ARCHIVE_ROOT>，未重新创建 Agent，也未继承旧 Step1–Step9 架构。

## 现在如何使用

已实际部署在 `/opt/jijigua-quant-agent/research_agent/`。你们继续原来的 root SSH 登录方式，不需要另开 SSH 用户会话或手工 su：

```sh
ssh -p 2222 root@gpu.example.org
quant-agent chat
```

在 `DeepSeek Key (not echoed):` 中输入 Key；输入不回显，不进入命令参数、提示词或账本。一段 chat 只在启动时输入一次。没有将 Key 保存在服务器上，也没有自动读取未知凭据文件。随后在 `research>` 输入：

```text
列出获准使用的日频资源，描述实际日期、字段、行数、缺失情况与复权和可获得时间口径，再读取5行样例并给出中文摘要。仅做数据描述，不运行回测。
```

输入 `/exit` 退出。启动器也支持 `quant-agent` 默认进入 chat，或一次性提交：

```sh
quant-agent ask '描述已授权日频资源的覆盖范围和字段，核验指纹，并读取5行样例。'
quant-agent status INTERNAL_RUN_ID_REDACTED
quant-agent result INTERNAL_RUN_ID_REDACTED
quant-agent logs INTERNAL_RUN_ID_REDACTED
```

status/result/logs 不要求 Key，也不调用模型。账本位于 `var/state/research.sqlite3`。任务 UUID、会话 UUID 与版本冲突校验避免互相覆盖；共用同一账号不提供使用者之间的隐私隔离。当前 chat 每条输入创建独立任务，没有跨任务对话记忆或后台持续执行。

## 两条真实端到端证据

两条均通过实际 HTTPS DeepSeek 调用，不使用测试假传输；Provider 配置为 deepseek-flash / phase1e-live-v2，temperature=0，单次输出上限2,048 tokens。实际模型标识、请求 ID、配置/代码/Skill/数据指纹、每轮理由和标准化模型/工具结果均在 JSON 账本记录中。

| 链路 | 任务 ID | 结果 | 模型 / Tool / 计划 | 返回 token 用量 |
|---|---|---|---|---|
| Linux CLI + 真实 DeepSeek + Mock Tools | INTERNAL_RUN_ID_REDACTED | COMPLETED，输入数据 synthetic | 7 / 3 / 4 | 输入10,166，输出2,034，合计12,200 |
| root Shell 的 quant-agent chat + 真实 DeepSeek + 只读服务器快照 | INTERNAL_RUN_ID_REDACTED | COMPLETED，输入数据 real_data | 7 / 3 / 4 | 输入12,330，输出1,982，合计14,312 |

Mock 链路查询固定量价数据，再计算3期、5期指标并比较：0.03167420814479627 与 0.04698774962241991。模型明确说明模拟性质，没有真实收益或有效性结论。实际调用记录见 linux-live-mock.json（原内部附件未公开）、CLI 输出（原内部附件未公开）。

真实数据链路依次调用 `list_resources`、`describe_resource`、`read_data_slice`。最终模型正确报告单日20行、7字段、全部缺失计数为0，并读取5行；标记复权/可获得时间 unknown、formal_backtest_ready=false。样例第一行证券000001，日期2026-10-09，开盘11.78、最高11.89、最低11.58、收盘11.59。只引用源字段，不把尚未核对的成交量单位当成正式定义。

证据：linux-live-data.json（原内部附件未公开）、root CLI 完整输出（原内部附件未公开）、两链路汇总（原内部附件未公开）。两条均为 UID/GID 999 的非 root 执行。此前的本地真实 API + Mock 成功记录另保留在 local-live-mock.json（原内部附件未公开），不与市场证据混用。

## 实际部署与权限

用户明确批准了 [最小部署范围](legacy__ADMIN_CHANGE_REQUEST_904330db.md)，没有再次等待不存在的普通用户名。新增 quantagent 系统账号，nologin，无附加管理员组；SSH 管理连接仍为 root，Agent 不继承其身份。

```text
/opt/jijigua-quant-agent/
├── 既有旧 Agent 文件和目录          保留
└── research_agent/                 root:quantagent 0750
    ├── src/research_agent/          root 管理的源码 / 两个 Skills
    ├── tests/、deploy/、dist/       root 管理的测试、启动器和发布包
    ├── config/resources.json       root:quantagent 0640
    ├── data_readonly/daily20.csv    root:quantagent 0640
    ├── .venv/                      quantagent 的独立环境
    └── var/                        quantagent 的独立写区
        ├── state/                  实际数据查询账本
        ├── live-mock/              真实模型 + Mock 的独立账本
        ├── mock-smoke/             离线安装验收账本
        ├── tmp/                    安装临时目录
        └── linux-test-results.xml
/usr/local/bin/quant-agent          root:root 0755
```

可信启动器先清除无关环境、去除附加组、setgid/setuid，再用独立 Python 导入 Agent。未把 root SSH 密码或私钥传给 Agent。运行核验：UID/GID999，CapEff=0；源码、资源清单、只读快照对 quantagent 不可写，var 可写。见 runtime-audit.json（原内部附件未公开）、初始部署记录（原内部附件未公开）。

服务器环境为 Linux 5.4 / x86_64 / glibc2.35、Python3.11.10。venv 的 include-system-site-packages=false；运行包从本项目 venv 的 site-packages 导入。依赖版本见 runtime-audit.json 和 requirements.lock。

初次 venv 失败的原因是基础 Python 缺少 ensurepip。使用 `venv --without-pip` 与基础 pip 的 [--python 选项](https://pip.pypa.io/en/stable/topics/python-option/) 在 quantagent 身份下安装进新环境，没有修改系统 Python。在线下载较慢，改用经过核对的本地 Linux wheels；未安装可选 NumPy/PyArrow，未安装系统容器运行时或改动 cgroup。较大的未完成部署归档保留在新项目 dist 内，未解包执行。

## 数据访问范围

源：`/hy-tmp/update_data/today/TRD_Dalyr.csv`，核对时2,192,884 bytes。root 管理的发布流程仅选取前20行及 Stkcd、Trddt、Opnprc、Hiprc、Loprc、Clsprc、Dnshrtrd 七字段，发布资源 ID 为 **gpushare:daily20**。模型不能提供任意文件路径，也不能查询未登记的共享资源。

- 快照实际覆盖2026-10-09单日；不是完整日频库，也不是历史回测数据集。
- 原文件 SHA-256：4dfb30aa7cbfe7dffb6f9e598f0fd7d7a201ff97dff3a75e0be1b06cd972478f；发布前后与最终核验一致。
- 快照 SHA-256：2c02f2d19ec9608fbaebac13a24b17a26dd9364d2c55f0b0b7dac0a3bbc04a47。
- 来源为服务器既有日频流水线；上游许可/生成口径本阶段未重新验证。复权、可获得时间及量的单位未确认，只允许描述。
- 数据 Tool：单文件≤4MiB、输入≤10,000行、返回≤200行；首次演示只取5行。SHA不符、非法日期/字段、链接文件、额外路径或授权参数均拒绝。
- 其他已定位文件仅保留元数据预检证据，未登记给模型。88GiB因子矩阵未打开/复制；root 私有 pickle 未加载或转换。

真实数据快照和资源清单与本报告同目录保存用于核验；服务器真正运行使用 config/ 与 data_readonly/。详见 remote-preflight.json（原内部附件未公开） 与发布记录。

## 实现文件与模块

| 文件 / 模块 | 本轮完成 |
|---|---|
| llm.py / providers/deepseek.py | 模型无关消息/工具协议、显式能力、固定 HTTPS、原生 Tool Calling、JSON本地校验、用量和错误；未知模型能力拒绝 |
| app.py / cli.py | 可信 development profile、独立凭据引用/隐藏输入、自然语言 ask/chat；默认 Mock/离线保护保留 |
| workflow.py / store.py | 最多4个原生工具批次顺序执行、整批预算预检、工具结果回填、理由/实验/用量/会话/执行模式记录；未完成批次拒绝重放 |
| data.py / security.py | 清单资源 ID、指纹和读取界限、三项只读 Tool、Policy/Skill/任务授权交集 |
| resources/skills/data_query/ | 小型受审专业数据描述 Skill，方法、权限、Schema、例子和验收标准 |
| skills.py / acceptance.py | 小型元数据发现、所选 Skill 的权限检查、固定哈希准入与确定性结果验收 |
| deploy/launcher.py / quant-agent | root 管理的简易入口，切身份后运行；会话独立，Key不落盘 |
| tests/test_development_data.py / test_launcher.py | 真数据合同的固定 fixture、批次反馈/预算/中断、Key canary、会话不覆盖、身份降级与环境清理回归 |

发行包：wty_research_agent-0.2.1-py3-none-any.whl（原内部附件未公开），SHA-256 e3e1df82306e6c198de173322d37cf0f792c4e1903015be0c15385887f91731e。

## 测试与问题修复

| 环境 | 总数 | 通过 | 跳过 | 失败 |
|---|---:|---:|---:|---:|
| Windows / Python3.12.4 | 124 | 123 | 1：Windows拒绝实际符号链接创建，错误1314 | 0 |
| GPUShare Linux / 独立Python3.11.10 venv | 124 | 123 | 1：可选PyArrow未安装 | 0 |

Windows 跳过的 `test_database_symlink_refused` 已在 Linux 实际创建链接并验证拒绝；Linux 跳过的小型 Parquet 合同测试在本地通过（PyArrow14.0.2、NumPy1.26.4）。不能据此声称服务器 Parquet 已可用。旧离线回归保留通过；自动化 suite 本身阻断网络，真实 API 证据另外记录。

完整报告：test-summary.json（原内部附件未公开）、Windows JUnit（原内部附件未公开）、Linux JUnit（原内部附件未公开）。安全回归包含 Skill 越权/篡改、工具伪造、路径/额外参数、预算耗尽、错误分类、凭据脱敏、root拒绝、符号/硬链接、授权记录失败、假审批字段和在途批次恢复拒绝。它们是合同回归，不声称验证了生产隔离。

实际发现并修复的问题：

1. 首次本地真实调用一次返回多个合法 ToolCall，被旧“恰好一个调用”限制拒绝。改为最多4项有界批次，增加反馈、预算与不重放测试；随后完整真实链路通过。
2. 初次 Linux 数据链路已完成3项 Tool，最终摘要被1,024输出上限截断，停止为 MODEL_ERROR/OUTPUT_TRUNCATED。升级v0.2.1，将该 Provider 有界输出提高至2,048；未放宽权限或任务次数。重测完成。失败账本保留：linux-live-data-failed.json（原内部附件未公开），其缺失用量标记unknown_calls=1，不能把失败总费用当已知。
3. 缺少 ensurepip 和低速下载按上述独立安装方案解决。没有重启服务、更改生产环境或执行未知第三方研究代码。

## 已具备、未具备与下一步

已具备：实际 DeepSeek 对话任务、原生工具调用/结果反馈、多轮计划、Model-Agnostic协议、受审 Skill、类型化只读 Tools、任务预算、实验/授权分离记录、CLI状态/日志/结果、非root基础部署。

未具备：正式市场因子研究/回测、Pyx/Claude工具整合、生成代码执行、通用Runner、专业多Skill自动路由、跨任务长期记忆、后台Worker、断线持续运行、生产沙箱、整树CPU/内存/PID/磁盘硬限及累计token/费用硬限。SSE协议测试通过，CLI尚未逐字流式显示。

最少剩余事项：第一批可靠研究数据的口径/许可确认；Claude quant_toolkit v0.2 与专业Skills的具体代码及版本；合格回测引擎的规则/依赖审查。真实API和本轮基础部署已不存在账号/Key阻塞。实例重建后账号、venv和启动器持久性需另行核验，本轮未重启实例。

下一批明确入口与验收顺序见 [INTEGRATION.md](legacy__INTEGRATION_46042f7f.md)。不重复开发 Claude 的因子评价；通过 ToolSpec/Registry + 独立授权 + 确定性验收接入其固定函数，外部账本保留引用，不能直接充当 Agent 授权。

风险边界：现有容器、非root、venv和超时不等于正式沙箱；quantagent仍能读取其他world-readable文件，安装环境/账本非防篡改。Key仅供受审Adapter使用，当前同进程工具可信而非独立凭据隔离服务。仅适合当前小样本开发；正式长期自主运行前按已审核安全规划加固。未触碰旧项目、源数据权限、生产任务或交易系统，未提交/推送Git。
