> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Quant-Agent 生产环境独立只读审计

**结论：审计完成；当前生产2026滚动评价通道已开启且近期真实成功，不能将“用户没看到Test”解释为评价器整体停用。用户最近具体哪一份报告/会话发生遗漏尚未唯一定位，真实入口复现留待批准。根分区92%是下一次升级前的优先运维风险。**

采集时间：北京时间 **2026-10-14 23:24—23:51**。生产代码、配置、研究数据、报告、账本、cron、权限均未修改；未联系Claude，未操作预发布实验。DeepSeek调用0，新评价器调用0，新回执/研究登记0。证据仅保存到本地本审计目录，未上传或写入生产。

## 1. 范围与证据等级

| 标记 | 含义 |
|---|---|
| 已验证 | 当前文件、进程、配置、哈希、账本或独立数值检查支持 |
| 日志推断 | 有历史事件支持，但缺少完整异常堆栈或精确用户复现 |
| 尚未验证 | 当前证据不足，不能补成事实 |
| 待授权 | 将触发真实模型/研究/评价或生产写入，未在本轮执行 |

检查以已有P1交付、生产源树、固定六源文件、既有三张滚动签名回执、两个快照、8份研究版本索引、生产SQLite和日志为限。不进行全服务器源码调查或完整根目录清理调查。v1rc只读采集代码/配置元数据，不读取其A/B实验产物，不运行代码或改变工作区。

读取使用标准库、固定路径、只读FD和尽可能O_NOATIME；生产SQLite使用`mode=ro&immutable=1`，采集时没有WAL/SHM/journal，读取前后文件大小/mtime稳定。没有用ORM或启动Agent来查询。正常SSH登录可能产生系统认证日志；这不等于审计脚本写生产应用。

## 2. 真实生产入口与身份

| 项目 | 当前已验证事实 |
|---|---|
| 正式入口 | `/usr/local/bin/quant-agent`，root:root 0755 |
| 外部入口SHA | `05042b3b85c4ab4050d70ac0e338f7334a73305707070d245b8960906c11de6a` |
| 启动链 | `/usr/bin/python3 -I /opt/jijigua-quant-agent/v1beta/deploy/launcher_v1.py` |
| 无参数调用 | launcher把`quant-agent`等同于`quant-agent chat` |
| Agent运行 | `/opt/jijigua-quant-agent/v1beta/.venv/bin/python -I .../deploy/run_v1.py` |
| 状态目录 | `/srv/jijigua-quant-agent/v1beta/state` |
| 成果目录 | `/srv/jijigua-quant-agent/v1beta/research_runs`；不是旧v0.8.2的research_runs目录 |
| 活跃进程 | root broker PID 601847；Agent PID 601873，UID/GID均999 |
| 账户 | quantagent 999，quantdata组；quantpub 998；quanteval 997，各为nologin，quantagent不属于quanteval组 |
| 回退入口 | `/usr/local/bin/quant-agent-v082`保留；旧核心目录独立存在 |
| 模型 | 近期任务记录provider=deepseek、model=deepseek-flash；本轮没有API请求 |

产品名为**v1.0 Beta**，但包源码`research_agent.__version__`和pyproject仍写0.8.2。因此不能仅凭这一版本字符串判断是否回到了旧Agent；应同时核对真实启动器、runner和完整发布SHA。

chat通过root launcher读取Key后fork，子进程降权为quantagent，只有继承的socket用于评价请求；父进程成为本会话root broker。当前观察到的真实进程与该调用链一致。评价器quanteval按需启动，评价完成后退出；没有常驻quanteval进程不能据此判为服务宕机。

`status/logs/result/session/history/session_tasks`走另外的无Key分支，不创建broker；不等同于一次带最新评价刷新能力的chat。未运行任何这些生产命令，避免初始化状态或隐藏副作用。

## 3. 2026 Test触发规则与算法范围

当前`deploy/rolling/broker.json`：`authorized=true`，`synthetic=false`，审批编号`KEVIN-20261013-V1-PROD-2`。SHA：`d974591df70438372be94aba505ace7b32d2c9267aa23467850b502881788bc2`。

自动评价不是普通2026资源读取。必要条件：root日常入口创建broker，真实已发布Train及其Validation配对研究完成，因子交付VERIFIED，冻结定义可由可信代码表达，参数及快照质量合同通过。默认计算后请求评价；普通聊天不会单独计算Test。

当前可信范围：

- 固定reversal、volume_stall；经过白名单的表达式DSL；`approved_implementation`且包含可信IR和symbols的已审核实现。
- H限定1—10，分组2—5，standardization仅raw/zscore；lag=1、direction=+1固定，不能用Test重新选方向。
- 字段限固定六字段，暖机最大330个观察日；股票轴5427，单位价格元/股、volume手（100股）、amount千元。
- 生产可信IR只支持既有算术、部分一元操作、横截面rank/zscore与ts_sum/mean/std/max/min等审核范围；并非任意Python，EMA、递归或新增算子不因本轮审计获得许可。
- 当前生产`factors.frozen_from_study`尚无新`kind=trusted_ir`专门分支。v1rc已增加这一路径，但不能据此宣称生产支持。超出冻结合同返回UNSUPPORTED_STUDY或后续FAILED。

**重要：`qrtk_read_study`在v1 Beta不是纯只读操作。** `quant.py:612/616`会调用`_refresh_rolling`→broker.evaluate；源版本变化时可以发布快照、计算新的滚动结果并追加报告，即使用户只是问“最新报告”。本轮因此没有调用该Tool、生产chat或broker RPC。名称“read”不能作为无副作用的证明。

这属于已启用C1滚动功能，不代表一次性独立Holdout预算重新开放。滚动通道与Codex的`test_evaluator/phase3c_v1`各自使用独立目录、密钥及账本；本轮未读取或修改一次性五日反转评价环境。

## 4. “没有Test”的真实证据

### 4.1 当前成功案例

2026-10-14 20:21:04，20日动量研究`INTERNAL_RUN_ID_REDACTED:6d18815210424ad9`生成回执`INTERNAL_RUN_ID_REDACTED`。

冻结定义为`cs_zscore(returns(close,20))`，H=1、5组。观察日186，有效评价日184，最后成熟信号10-12，入场10-13、退出10-14；10-13和10-14的标签未成熟。Test IC=-0.008690611491，RankIC=-0.029085289623。

最新HTML实际存在，manifest及关键文件哈希一致：

`/srv/jijigua-quant-agent/v1beta/research_runs/2026-10-14/20-21-04_report_revision_2/reports/report.html`

同study原`20-19-52_momentum_20d/reports/report.html`仍是revision1，其Test为PENDING。**直接浏览原成果目录不等于打开最新revision2。** 新报告的Test核心/月度结果与注册回执逐项一致。

该研究会话`INTERNAL_RUN_ID_REDACTED`的“默认”回复已明确显示2026数值及revision2路径。因此近期日常生产链路确实成功过，不能说当前所有用户入口都没有Test。

### 4.2 已确认的其它状态

| 历史研究 | 真实状态及影响 |
|---|---|
| 10-13 15:10 ILLIQ、15:12反转、18:29 GH、18:31 ILLIQ | 创建于通道开启前，只有revision1，Test=NOT_AUTHORIZED；不能以今天配置开启倒推旧报告已有Test |
| 10-13 20:14 GH | root已签发7b4aea07…回执，但研究Tool随后ContractError，未建立revision2，原报告仍PENDING；证明评价成功与报告交付是两件事 |
| 10-13 20:44 GH | revision2显示FAILED；root日志20:45记录REQUEST_FILE_CONFLICT，多个读取追问仍返回旧/失败状态 |
| 10-13 21:18 GH | 热修复后复用既有结果，回执57e72a83…、revision2完整，四次读取追问均记录成功复用 |
| MA论文会话 | 研究阶段ToolError/ContractError，随后读结果被STUDY_NOT_IN_SESSION拒绝；未完成Train/Validation就不能要求它已经有Test |

MA具体静态审核误报原因由历史Claude交付描述；本轮生产日志只能独立确认ContractError及未形成研究，不能恢复完整异常堆栈。REQUEST_FILE_CONFLICT是有明确历史证据的故障；21:19后的成功及今天动量成功说明不能直接把它当作仍然全局发生。

### 4.3 已确认的解释、缓存与定位问题

1. 最近普通对话“你好”“给我做个动量因子”“factor_research工具在哪”仍说“2026独立Test需另行审批/当前不可读”，与已启用滚动通道的状态混淆。2026原始数据不可读是对的，自动受控滚动统计不能一概说未批准。
2. 原始analysis/revision1保留初始PENDING/NOT_AUTHORIZED，最新统计在版本索引指向的revision2；`result`返回的历史研究模型摘要也可能只写Train/Validation。对“原始文件/旧任务/最新报告”必须区分证据时间。
3. v1beta/config目前只有research.json、resources.json，没有report_catalog.json。代码有共享目录机制，但配置未登记，跨会话不能任意读取其它会话已有研究。实际存在STUDY_NOT_IN_SESSION记录；不能通过放开全局读取来修复。
4. `_refresh_rolling`失败会记录ROLLING_REFRESH，但返回旧报告；非成功结果不追加状态版本，异常只保留类型，普通回答可能没有刷新失败提示。历史失败追问的日志与这一路径相符。
5. P1一条回复把Validation区间误称跨0；实际不跨0。最新动量研究内部模型摘要又说“假设被证伪”，比探索性资格更强。程序最终回复较谨慎，不能把模型文字当数值或科学认证。

**尚未验证：** 用户最近所指的是哪一个task_id、哪份HTML或哪个会话。本轮没有用户原始屏幕/路径的唯一关联，也没有主动真实复现，所以不能宣称已唯一定位其个人这次现象。

## 5. 源行情、成熟标签与质量

最新已发布滚动快照：`rolling_20261014_b317a017d62b`，截至**2026-10-14**；测试2026-01-05起共186日，2025暖机330日，合计516×5427。

manifest SHA：`1ce1a346086e7dea6450ff3ded6e27cacef14d05bb88d23998481395a8d0f6b8`。本轮对固定六原始PKL共491,809,560字节做只读SHA，不反序列化；六个SHA/大小全部与该manifest一致，读取期间稳定。

| 字段 | 当前SHA-256 |
|---|---|
| open | 68cc0ba3d9921df2f4e3acda12d758cc120ed3143d20410568b96263ee4f26e9 |
| high | 599f329d053ea6b892fed80b2db5700a52190b31ec057badf047b9da3df3e63e |
| low | 0d8570a58c6b4fd3e02ea47ae23bd31c209c91ea14e3f565c90f823217f236ff |
| close | 2df48045a6cb01f27d67c059f93a1d0cd74ed9652ecb778a8cd99472ff906741 |
| volume | 715f54b4f911ce3ba94c9a41d185601cda0fa8c91c8e4b25c3ab696427ed596c |
| amount | 174fb2938b2b99d94b6c6b2a566d018fdb8aad1932ffb9d02083a88dea3c1833 |

六文件各81,968,260字节。不能用mtime代替真实交易日期；本轮日期来自认证manifest/实际交易日索引，并以源SHA及更新完成日志关联。

末日close有效5183，前20日中位数5182，未剔除不完整尾日。旧10-13与新10-14源指纹不同，说明原文件版本变化；本轮未重做全历史逐格差异，不能宣称变化全部仅来自新增一天。复现仍需保留不可变快照。

成熟边界随H改变：既有GH H=10快照截至10-13，最后成熟信号09-18、入场09-21、退出10-13，尾11日未成熟；动量H=1截至10-14，最后成熟信号10-12，尾2日未成熟。均从真实索引复算，没有硬编码以日历天推算。

数据仍为PROFILED_EXPLORATORY_ONLY：固定证券轴、候选上市屏蔽未获PIT认证，原始未复权收益受公司行动影响，停牌/ST/涨跌停/退市估值合同仍不齐。价格存在不代表可交易，滚动Test持续曝光，不是严格未见Holdout或账户回测。

## 6. 签名、数值与OS安全核验

三张现有回执HMAC全部通过；root签名材料只在受审核验进程内使用，没有导出或交给quantagent。21条broker审计链逐条重算完整；评价账本只有2个独立评价行，第三张是同定义/快照结果重新绑定研究的复用回执。没有新评价或记录写入。

第一层：本地对签名逐日聚合独立复算IC/RankIC均值、中位数、样本标准差、非年化IR、正值比例、HAC标准误/CI/t/p、年度/月度均值、G0–G4和G0−G4，误差<1e-12。HAC采用Bartlett权重，带宽max(H−1,floor(4·(n/100)^(2/9)))；剔除结构性边缘缺口，不压缩中间缺日，样本门槛及渐近正态局限保留。

第二层：按本轮已授权历史数值审计，在root受控只读进程内校验两份既有私有NPY快照（allow_pickle=False，固定形状/浮点类型/文件SHA）；用独立NumPy/Pandas公式重新得到既有因子、日度IC/RankIC、分组及G0−G4。不导入生产评价器，不执行模型代码，不生成新定义/预测/回执或调参结果。

| 回执 | 固定对象 | 成熟日期核对 | G0–G4单元格核对 | 最大数值误差 |
|---|---|---:|---:|---:|
| 7b4aea07… | GH 52周高点H=10 | 174 | 870 | 2.50e-16 |
| 57e72a83… | 同定义/快照复用 | 174 | 870 | 2.50e-16 |
| c4a023c5… | 20日动量H=1 | 184 | 920 | 2.78e-16 |

两快照各六数组SHA通过。尾部未成熟日期没有IC/RankIC/分组值；不填0。数值核验1.83秒、峰值RSS约372.8MiB；账本、root审计文件、三张回执的核验前后哈希相同。原始矩阵/股票标签没有输出给模型或存入本地证据。

GH Test：IC -0.000529729116、RankIC -0.011757693332；G0..G4平均毛收益约−0.300840%/−0.223648%/−0.308398%/−0.444534%/−0.357288%，G0−G4=+0.056448%。动量Test：IC -0.008690611491、RankIC -0.029085289623；G0−G4=−0.033210%。这些是原始open到open、重叠H期、信号日等权组均值，不是账户收益/NAV。

当前生产回执给出IC/RankIC HAC，G0−G4给出均值/标准差；不要将候选报告模块新增的G0−G4 HAC展示能力说成当前生产已完成。

OS实际探针以UID999尝试只读打开、但不读内容：raw close.pkl、最新Test close.npy、rolling.key、ledger.sqlite、root audit均EACCES；root登记回执允许打开。没有更改用户、组或ACL。

**额外合同差距：** broker验证Validation暖机重叠时只比count/sum/sum_sq，并非每股票逐格相等。交换两个股票的值可保持这些统计不变，因此历史文档“逐值一致”描述偏强。本轮固定案例独立复算已通过，不证明所有未来算法的暖机都通过逐格检验。

## 7. 基础设施健康

| 项目 | 当前结果 |
|---|---|
| 根分区overlay | 30GiB，已用约27.35GiB，剩2.65GiB，92% |
| /tmp | 与根分区同一overlay，实际目录约45.3MiB |
| /hy-tmp | 独立XFS设备，300GiB，剩约52.49GiB，83% |
| inode | 约2%使用，当前不是inode耗尽 |
| /var/log | 约1.19GiB，主要btmp=1,273,401,600字节；两次采集大小未变 |
| /root/.cache | 约46.5MiB，不是本轮根容量主要来源 |
| v1beta代码/venv | 约332MiB；本轮没有全根目录占用归因 |
| 评价审计/账本 | broker日志8381字节、ledger172032字节，无异常膨胀证据 |
| cron | supervisor RUNNING，PID525267，已持续约1天4小时 |
| crontab | CRON_TZ=Asia/Shanghai，每日19:00调用原run_daily_pipeline.sh |
| 更新完成 | cron日志包含10-12、10-13、10-14的PIPELINE_DONE status=success；今日约19:26完成 |

不存在“当前cron未启动/行情停在10-09”的证据。日志尾部和所查任务事件未出现ENOSPC；不等于过去从未磁盘写满，因为本轮没有完整Docker宿主/系统日志。历史P1故障有ContractError及JSON预算证据，不能未经证据归因于磁盘。

已结束的测试目录未删除；/tmp总体很小，不能把所有未知临时文件视为清理候选。/hy-tmp挂载为实例本地XFS，未查到本轮范围内的独立持久备份证据，平台生命周期/清理政策尚未再次核验。不能因为XFS和可读就认为永久保存。

## 8. 版本与配置差异

生产发布清单SHA：`342a78a95041803a8c00169495dbd6b8a87ca87fe6bc7fab4a5aaa924ccb4d9d`。169个列明文件全部匹配P1热修复基线，**生产代码漂移0**。root当前入口及broker配置仍为已启用v1版本；不能拿本地热修复前清单判漂移。

| 比较 | 结果 |
|---|---|
| P1热修复基线→当前生产 | 169文件全部一致 |
| 当前生产→冻结candidate4发布清单 | 11修改、2新增；171个发布条目 |
| candidate4冻结副本 | SHA256SUMS的16个存档文件全部一致；这是补丁/操作文件子集，不冒充171文件完整源码副本 |
| candidate4→23:26采集的当前v1rc | 28修改、6新增；无扩展名部署模板存在但未纳入这轮v1rc后缀哈希，标NOT_HASHED而非缺失 |
| v1rc授权状态 | authorized=false，独立目录与配置；不能把预发布没有Test误判为生产故障 |

v1rc新增/改动包括trusted_ir、rolling_test/factors.py、quant.py、report_versions.py、workflow/runtime、Provider错误恢复、语义/机构识别、缓存invalidations、报告说明。它已超出旧candidate4的13文件质量审批计划；后续必须冻结新的完整清单，不可用旧清单直接复制当前活跃v1rc。

已有活跃root broker/Agent会话已加载模块。将来原地替换代码而不协调旧会话，会出现旧broker与新子评价器模块混用的风险。本轮没有终止这些进程。

## 9. 风险优先级与最小处理建议（均未实施）

1. **P1 根分区空间紧张。** 已验证92%/2.65GiB。升级前确认足够峰值写入空间，若要清理必须单独测量并审批具体目标；不建议直接递归删除/tmp或研究目录。
2. **P1 用户收到错误的2026权限说明。** 真实普通回复说需另行审批，而实际滚动评价已授权。下轮将原始数据权限、一次性独立测试、自动滚动统计三类状态由可信配置和结果统一表达；不得硬编码2026数值。
3. **P1 评价成功但报告未成功。** GH 7b…已有回执而原study仍revision1/PENDING，Tool随后ContractError。修复应仅恢复原签名结果的后处理及明确失败状态，不能重新评价以解决报告故障。
4. **P1 只读名称掩盖刷新副作用。** qrtk_read_study会评价/发布/写报告。下一轮验收及运维查询需明确是否仅读缓存，或批准固定版本刷新；不能用一次“查询”无意消耗新测试或生成新曝光。
5. **P2 未明确暴露刷新失败与旧状态。** 当前失败追问日志有FAILED而返回旧报告；保留既有报告，同时将最新刷新结果和数据版本显式返回，不能吞掉detail。
6. **P2 会话与报告版本可见性。** 新会话没有共享目录，直接浏览原run只能看到rev1。保持权限边界，用明确审批的单研究共享/会话恢复和准确latest路径改善定位，不开放全局历史。
7. **P1 下一轮清单已过期。** 当前v1rc比candidate4多28处修改，不得按旧13文件审批上线。冻结新基线并按实际变更评审；生产本轮没有漂移。
8. **P2 暖机验证与计算版本缓存。** 现有重叠验证是交换不敏感的聚合摘要；缓存键为定义SHA、快照、合同，未显式包括评价实现SHA。下轮不能宣称逐格相等；若可信IR语义变更，应升级合同/计算指纹并明确旧结果复用规则。
9. **P2 科学解释偏强。** 已有误述HAC区间与“假设被证伪”表述，应以真实统计和探索资格校准。不能从当前原始价格统计升级为可交易结论。

以上不是自动修复授权，也未对Claude下发任务。

## 10. 下一轮准备与尚待授权事项

详细草案见同目录`NEXT_UPGRADE_ACCEPTANCE_PLAN_CN.md`。需要用户授权才可做：单次真实CLI复现、任何研究/报告修复、生产升级/回滚、额外数据权限、清理目录、产生新的2026评价或曝光。当前P1及新动量数字均已有现成回执，不应为修复展示问题重新评价。

建议最小复现只针对现有动量会话和当前快照，单条“2026年的测试结果出来了吗？”；但当前Tool会自动刷新，必须先核对source/definition/receipt固定并批准最多一次会话查询及其账本/审计写入。若发现数据更新、缓存未命中或需新评价，则停止另行确认。此步骤本轮未执行。

不能在未得到用户当前task_id/实际HTML路径前，把某一个旧故障当成他最近这次现象的唯一原因。当前证据已足以排除整体通道关闭，并明确后续验收应覆盖报告版本、当前权限说明、会话恢复、可信IR边界及失败后处理。

## 11. 证据索引与检查限制

- `evidence/server_inventory.json`：入口、进程、账户、空间、cron、挂载及目录元数据。
- `server_sources.json`、`evidence/code/`：生产/预发布采集时源码、配置及manifest；不执行这些副本。
- `server_state.json`：既有研究/版本、任务、评价账本与日志，稳定不可变SQL读取。
- `server_receipts.json`：HMAC布尔结果、真实OS打开拒绝、已有对话。
- `server_final.json`：六源SHA、生产169文件校验、HTML/manifest关键文件及依赖。
- `independent_public_aggregate_checks.json`：聚合统计、成熟索引、HAC及完整审计链复算。
- `server_cross_sectional.json`：既有两个私有快照的独立日度IC/RankIC/分组核验，原数据不导出。
- `receipt_report_consistency.json`：两份成功revision2与正式回执核心/月度指标一致。
- `version_comparison_calibrated.json`：P1、candidate4、当前v1rc差异；首版采集器漏哈希无扩展名模板已校准，不能据初版missing判生产漂移。
- `scripts/`：仅本地审计采集及核验程序。采集器初次编译/manifest字段匹配问题均在本地修正，不改变生产断言或统计定义。

未运行真实chat/DeepSeek，没有新的2026评价，没有修复/升级/回滚。没有检查Claude正在运行的A/B实验产物、完整系统历史日志、每一种论文算法的真实成功率或平台持久性规则。未进行私有矩阵以外的其它研究、未来参数选择或真实账户回测。
