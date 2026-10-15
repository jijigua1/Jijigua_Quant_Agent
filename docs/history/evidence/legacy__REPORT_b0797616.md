> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-B 交付报告 — Research Agent v0.5.0

2026-10-12。已部署受控新因子构造、真实数值评价、事件驱动进度、实验比较和图表/报告交付。**正式账户回测仍 BLOCKED；长历史合格数据和真正独立盲测尚未建立。**

## 1. 实际使用

沿用 root SSH 登录，执行：

```sh
quant-agent chat
```

启动器内部切换为 quantagent（UID/GID 999），隐藏输入 DeepSeek Key。可直接输入“帮我研究一个五日反转因子，并生成完整分析报告。”，随后自然指代、改参数或询问报告位置。模型 Provider、Tool 白名单、独立授权、Skill Registry、SQLite 会话/实验账本继续使用原系统。

核心部署：`/opt/jijigua-quant-agent/research_agent/`；最终 wheel 指纹：`7ebfeb0b2ec500895092ce88eac33143c858e4c78c54cfa15b0787822b4459e3`。原源码备份：`dist/phase2b-before-0.4.0.zip`。数据合同、daily20/daily65、SQLite 原位保留；旧 task INTERNAL_RUN_ID_REDACTED 仍存在，status/result/logs 补验通过。

最终包的独立五日反转报告：`/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/92d5538c320b4218/reports/report.html`。窄视口494px时整页宽度仍494px，指标表内部滚动；5张内嵌图全部加载。

## 2. 实现与能力边界

| 文件/模块 | 本轮实际能力 |
|---|---|
| `src/research_agent/factor_expression.py` | 19 个白名单算子组成有向无环表达式；校验时间、量纲、节点和计算规模，不执行模型代码 |
| `src/research_agent/quant.py` | 新 `qrtk_expression_study`；复用受审 qrtk 数学；固定因子继续可用，父实验校验及参数比较 |
| `src/research_agent/research_report.py` | CSV 数值生成 PNG/SVG/PDF、Markdown、自包含 HTML；实际指标与数据合同、公式、局限、复现入口 |
| `src/research_agent/evidence.py` | 验证后摘要进入模型，完整结果留账本和文件，降低重复上下文 |
| `workflow.py` / `terminal.py` | 真实执行事件驱动动态阶段及状态；图表计数有分母时才显示百分比 |
| `conversation.py` / `runtime.py` | 同会话实验记忆、上下文上限、调用/Token 预算、未知用量预留及取消 |
| `data.py` | 可信清单可配置全局 `withheld_from`，别名与实际内容一起检查；未配置的旧曝光数据不能称盲测 |
| `artifacts.py` | 独立 task/run、parent 引用、SHA-256、文件清单、阶段日志和产物预算 |

Claude qrtk 0.2.0 的12个模块和47个源码/合同审查文件保持原字节；没有启动第二套 Runtime，没有另写生产 IC/RankIC 公式。独立标准库标量公式只用于测试交叉核验。

表达式支持 field/constant、neg/abs、cs_rank/cs_zscore、delay/diff/returns、rolling_mean/std/rank/corr、add/sub/mul/div/min/max；最多40节点、8层、窗口1—60、累计历史120、面板10万格。全窗口暖机，std ddof=1、并列秩平均、零分母及缺失为 NaN。任何未来偏移、任意代码/路径/回调、循环图、无用节点及非法量纲均拒绝。

每次登记公式、参数、算子版本、表达式/代码/数据指纹、可获得时间、假设与修改理由。CLI 展示程序登记的实际公式，模型解释应据此核对。

五个专业 Skills v0.2.0：data_research（质量/样本）、factor_research（固定及表达式因子评价）、research_diagnostics（诊断）、research_reporting（真实结果读取及自动报告）可用；strategy_backtest **仅准入诊断**，没有合格账户执行 Tool。

## 3. 真实 DeepSeek 六轮验收

主记录：`live-ssh-console.txt` / `live-session.json`，会话 `INTERNAL_RUN_ID_REDACTED`，六条原始短自然语言全部 COMPLETED，UID 999。

| 用户任务 | 真实行为 |
|---|---|
| 五日反转 + 完整报告 | 自主选资源与因子 Tool，计算并保存5类图及 MD/HTML |
| 画 IC 和分组图 | 使用已完成实验的真实图表路径，无须重复计算 |
| 放量滞涨构造 | 自主提交9节点表达式，真实计算价量组合 |
| 改10天并比较 | 新 task/run，引用父实验，记录窗口变化，生成第6张比较图 |
| 扣费回测 | 调用 qrtk_backtest_readiness，正确阻断，不生成虚构 NAV/Sharpe/回撤 |
| 报告位置 | 同会话引用实际成果目录，无须无关 Tool |

主六轮计算功能包 SHA 为 `3b89334824ae2b33cd2263acff7b413d1782214f231932aaf8fa7a4b4c256bd0`。最终包仅另修正 HTML 窄视口布局；`report-patch-live-*` 单独记录最终包的真实报告补验，避免将不同包的记录混称相同指纹。

实际受控公式：

```text
五日反转: -(close[T] / close[T-5] - 1)
价量5日: add(div(volume,delay(rolling_mean(volume,5),1)),neg(returns(close,5)))
价量10日: add(div(volume,delay(rolling_mean(volume,10),1)),neg(returns(close,10)))
```

这里是模型选择的一种价量代理，量比与价格变化直接相加的经济刻度未必最优；结果没有被包装成已经验证的“放量滞涨”策略。

| 因子 | 训练均值 RankIC | 验证均值 RankIC | 有效日期（训练/验证） |
|---|---:|---:|---:|
| 五日反转 | 0.025714 | 0.149846 | 28 / 10 |
| 价量5日 | -0.065897 | -0.066288 | 28 / 10 |
| 价量10日 | -0.076394 | -0.040175 | 23 / 10 |

10日验证较5日有所改善但仍为负；窗口暖机导致训练样本变化，比较不是同日期配对因果检验，也不是独立样本外。当前证据不足以支持原上涨假设，未根据收益反选方向。

## 4. 实际成果

所有主实验在：

```text
/srv/jijigua-quant-agent/research_runs/
  INTERNAL_RUN_ID_REDACTED/446a71952c2c4c6e/  # 五日反转
  INTERNAL_RUN_ID_REDACTED/eb7c1d4f20d84872/  # 价量5日
  INTERNAL_RUN_ID_REDACTED/fbebf6df75f84386/  # 价量10日
```

每个目录有 code、data、figures、reports、logs 和 manifest.json；`reports/report.html` 内嵌图片，可单文件下载打开，`reports/report.md` 保留文件引用。五类图：IC/RankIC 时间序列及分布、分组毛收益、因子覆盖率及分布；有父实验增加比较图/CSV。账户净值和风险图不生成。SVG/PDF 图是可编辑导出，**尚未实现完整 PDF 研究报告**。

`code/reproduce.py` 仅调用受审 DSL 复现因子值，不运行模型生成任意代码。三个主实验已在 Linux UID999 下逐文件验证 manifest SHA，再独立执行该脚本，全部通过；它不是一条重新查询上游、执行账户回测的完整市场复现命令。

最终测试证据发布到已批准的 `/srv/jijigua-quant-agent/integration_tests/phase2b/<run_id>/`，准确位置见 evidence-publication.json。新建 phase2b 目录为999:999/0700，仅该目录变更；父目录、其他研究项目与原数据权限不变。

## 5. 数据及回测状态

只使用此前批准的 daily65：2026-07-03—10-09，65观察日、50固定代码、3163行，缺87/3250条（2.68%），未复权，历史发布时间不完整。标签 open[T+1+H]/open[T+1]-1，T 是观察日期；不存在正式交易日历、公司行动、退市及执行日独立交易状态认证。理论毛分组不代表可执行组合收益。

训练/验证按标签退出日期清除跨边界样本，图表 CSV 的均值和数量与分段统计一致。测试统计仍 sealed，但 data_query 已能读同一原始价格，**不是独立盲测**。全局 withheld_from 防止未来新资源/别名跨越封存边界；独立数据保管与解封评测器尚未上线。

限定路径静态核验找到 adj/OHLCV/状态 pickle 和 EOD 候选；没有执行 pickle，没有扩大数据发布，也没读取88GiB矩阵。完整 calendar opcode 只证明1990—2040字面日历，不能据此声明实际行情历史。下一步由可信数据生产者核对生成代码后，申请精确日期/字段的小型非执行格式发布，详见 DATA_READINESS.md。

Pyx/Perry 源码复核与独立副本交叉测试见 SOURCE_REVIEW.md。Pyx受审三个函数在手工2000→2096.8费用账本案例及拒单/保留持仓/时间对齐测试通过；**整个引擎未认证**。Pyx的VWAP、独立买卖状态、复权/公司行动、费用日程，以及Perry的外部planner、默认交易状态、成交/估值与首日费用仍待验收。正式回测保持 BLOCKED_DATA_CONTRACT / BLOCKED_ENGINE_QUALIFICATION。

## 6. 运行预算、安全和未完成项

每任务最多4轮、8模型调用、6 Tool 调用、40阶段；Token 60k保守请求预留/实际统计，会话累计300k。上下文最近6轮、最多6条实验摘要和16KB；大 JSON 不反复灌入模型。工具输入≤10000行/100代码，BLAS单线程，产物≤20MiB/100文件。权限白名单、内容指纹、越权/额外参数/路径/链接拒绝与凭据隔离保留。

600秒任务/120秒 Tool 是合作式边界检查，**不能抢占正卡在计算中的进程，也不是 CPU/内存/PID 硬配额或正式沙箱**。Ctrl+C 可取消并记 INTERRUPTED，后台持久 Worker 未实现，SSH断线不保证继续。没有任意代码入口、生产交易、系统提权或未审查第三方执行。

真实六轮主验收111,336已知 tokens、未知调用0；两次较早完整迭代另用110,382及93,666 tokens。预算和摘要机制已实现，但没有获得可比任务的稳定降费百分比，不能宣称成本目标已解决；金额仍以 Provider 实际账单为准。

最终报告补验额外17,155 tokens；本轮三次六轮加单轮累计332,539已知 tokens。主六轮记录22次模型请求、6次研究 Tool 调用、86条真实 RESEARCH_STAGE 事件。图表/报告路径提问复用已验证成果，不重复数值计算。

下一批工作：可信更长历史数据合同及最小发布、完整账户引擎准入与公司行动、真正独立持出评测、相同日期实验比较、可配置更低模型预算与实测、后台任务/生产隔离。当前仍提供前台探索性研究，不将其作为已验证策略。

`/hy-tmp` 为临时存储，关机24小时后及迁移存在清理风险；重要成果请自行备份。本轮没有自动外传。[GPUShare存储说明](https://gpushare.com/docs/data/storage/)。

## 7. 测试、视觉核验及最终证据

精确汇总见 test-summary.json、real-acceptance.json、figure-validation.json、final-integrity.json。Windows符号链接测试因权限1314跳过；Linux补验通过，Linux另跳过未安装PyArrow的可选Parquet测试。没有引入新依赖，合成案例仅证明实现，不证明市场有效性。

| 测试 | Windows | Linux |
|---|---:|---:|
| Agent 全部回归 | 230通过 / 1跳过 / 0失败，69.06秒 | 230通过 / 1跳过 / 0失败，48.00秒 |
| Claude 原工具包 | 135通过 / 0失败，16.51秒 | 135通过 / 0失败，20.63秒 |

Windows Python3.12（Anaconda）；Linux Python3.11.10，numpy1.26.4/pandas2.3.3/matplotlib3.8.4；现有锁定依赖不新增。Windows已有fontTools弃用提示不影响数值或导出。

四个最终实验的22张PDF均通过文本/碰撞核验，最小字号8pt，碰撞0失败/0警告；主六轮17张PNG逐图视觉检查，补验5张PNG与已经检查的反转图逐字节相同。静态图表检查17项通过、4项已解释警告（研究报告采用300dpi/非期刊尺寸/不要求TIFF，缺失及暖机数量另在CSV和正文列示），0失败。

10个历史及最终真实实验由独立标准库CSV/math重算因子、IC、RankIC与分组均值，最大误差2.220446049250313e-16；最后4个的图表CSV均核对了跨分段标签清除。早期6个兼容图表口径已在最终版修正，不能用旧图替代最新报告。

关键记录：deployment.json / deployment-verification.json、四份JUnit、live-ssh-console.txt / live-session.json、report-patch-live-*、real-numerical-baselines.json、linux-reproduction.json、calendar-static.json、SOURCE_REVIEW.md、DATA_READINESS.md。较早 attempt1/attempt2 保留审计原貌，最终图表口径以主六轮和最终补验为准。
