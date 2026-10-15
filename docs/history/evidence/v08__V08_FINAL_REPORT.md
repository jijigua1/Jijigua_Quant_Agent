> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Research Agent v0.8.0 最终工程交付



状态：**V08_FULL_DATA_NL_RESEARCH_ACCEPTED**。用户已批准精确部署范围，v0.8.0已安装；真实2026评估：**READY_FOR_HOLDOUT_APPROVAL**，未发布/未解封。配置、官方API、入口和数据库未替换；生产最终验收结果另见production_acceptance.json。



## 1. 实际实现与工作区



本地独立副本 `<ARCHIVE_ROOT>/v08_work/`；Linux候选 `/srv/jijigua-quant-agent/research_runs/2026-10-12/23-43-16_v08_candidate/`，UID999（quantagent），沿用已批准quantdata组。Windows/Linux均直接执行实际源码；没有新数据仓库、研究引擎、Worker或运行时安装。



| 模块 | 已交付能力 |

|---|---|

| factor_evaluation.py / research_metrics.py | 复用qrtk逐日IC/RankIC/分组；新增均值/中位数/Std/非年化IR、HAC/t/p/CI、极端日期、6年/72月、20/60滚动/累计、敏感性、覆盖、年度方向及月度低效诊断 |

| interactive_report.py / research_report.py | 离线嵌入式Plotly2.32.0（MIT、固定SHA），8交互图；RankIC/IC数字热力图、分开的时序、悬浮/时间范围/图例、15类PNG/SVG/PDF；紧凑表、AST数学SVG、Markdown、证据Verdict |

| factor_report.schema.json | factor-report/2：每份报告从创建时含Train/Validation/Test、study_id及报告版本；无Test数值时N/A，不填0 |

| independent_evaluator.py | 独立冻结描述、主机批准合同、操作者permit、私有SQLite次数/曝光/失败、并发单次、白名单聚合结果及签名回执；合成验证，未部署真实私有读通道 |

| report_versions.py | 操作者校验签名/同研究ID/数据/代码/表达式；合法结果生成同study_id的新三阶段版本，保留原HTML/Markdown/PKL及manifest；模型没有合并Tool或密钥 |

| conversation.py / evidence.py | 保留已有年度证据，单摘要2500字节、总5000字节；后续追问复用证据，授权不来自历史模型内容 |

| Tool/Skill | 继续当前唯一调度系统；factor_research更新方法及已批准指纹；qrtk_independent_test_request只登记待审批申请，不读取2026 |



Claude qrtk / qrtk_skills源码与v0.7逐字节相同；GeorgeResearch原项目、原始行情、不可变分区均未改。19算子、定义确认门、默认兼容PKL、授权/预算/SQLite/人类可读目录保留。



## 2. 统一三阶段产品合同



- Train：2020—2023，实际2020-01-02—2023-12-29、970日。

- Validation：2024—2025，实际2024-01-02—2025-12-31、485日；已曝光，不能称独立盲测。

- Test：2026，真实认证截止日尚未批准；首页、核心指标、年度表、月度IC/RankIC热力图、稳定性和Verdict均保留 `NOT_RUN / SEALED`。



合成验收已证明：冻结因子经过独立账本评价并签署回执后，同一study_id产生report_revision=2；合法Test年度/月度/聚合日结果进入同一综合报告，而不是一份独立Test研究。原报告字节未改变。`reports/report_versions.json`维护版本映射与SHA，最新读取通过索引/manifest核验；篡改、重复、不同冻结参数或合成Test并入真实报告均拒绝。



真实Test身份、私有快照、独立密钥/接收入口及首次结果曝光仍待审批。HMAC密钥不能交给quantagent；合成跨UID文件拒绝不是正式2026隔离部署，更不是硬沙箱。未生成或读取2026真实因子/标签/表现。



## 3. 真实行情和科学口径



只用baseline_20261009_a864dc33现成发布，六原始字段、5427固定代码轴（两只身份冲突代码整列NaN），完整输出1455×5427。Train manifest SHA `9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221`；Validation `82246b4424f8dbd45c11d959164199a4b45efeb6803d6a6064204a6fc08bf4b4`。各字段SHA在benchmark.json与研究manifest，未重新解析/复制原始PKL。



T日收盘因子仅用截至T的信息；Validation暖机来自允许的Train，标签为raw open[T+H+1]/open[T+1]−1，各分区末H+1日剔除，不用2026补尾。年度/月度按信号日聚合，分组是重叠标签的理论毛收益、不是账户NAV。HAC方法、最小样本、内部缺失与零方差规则见EVALUATION_CONTRACT.md；短月不打印显著性星号，多重试验/选参偏差未校正。



价格未复权，公司行动、上市时点、历史证券池/PIT和交易状态未认证。所有数值保持PROFILED_EXPLORATORY_ONLY；无正式账户收益、Sharpe、交易回撤或可交易结论。行业/市值中性、可信参考因子和参数扰动敏感性没有足够输入/批准设计，未伪造计算。



## 4. 真实官方DeepSeek / SSH PTY



Provider deepseek，实际模型deepseek-flash，端点 https://api.deepseek.com/chat/completions。官方Key仅隐藏输入，未改变Provider设置，未请求第三方API。



最后会话 `INTERNAL_RUN_ID_REDACTED`：普通中文五日反转→测试申请→逐年RankIC追问→2026调参拒绝→报告路径→tasks。实验仅 `qrtk_factor_study, qrtk_independent_test_request`，因子计算1次；后续年度/报告查询不重算。Test申请submitted=false/test_data_read=false/test_results_returned=false，所有会话任务COMPLETED。



真实五日反转：lookback5、horizon1、zscore、5组。Train RankIC +0.02852，Validation +0.03009，963/483有效日。证据Verdict `NEEDS_MORE_EVIDENCE`：年度方向全部为正，但验证分组单调性不足，数据资格受限，不宣称策略有效。



| 年份 | 分区 | RankIC mean | 有效日 |

|---|---|---:|---:|

| 2020 | Train | +0.021975 | 238 |

| 2021 | Train | +0.037304 | 243 |

| 2022 | Train | +0.033614 | 242 |

| 2023 | Train | +0.020965 | 240 |

| 2024 | Validation | +0.015340 | 242 |

| 2025 | Validation | +0.044906 | 241 |

| 2026 | Test SEALED / NOT_RUN | N/A | N/A |



PKL/CSV全矩阵与独立NumPy（含实际zscore）一致；7个日期Pearson/平均秩Spearman独立核验；标签边界剔除通过；89个产物SHA核验。真实CLI原文、工具参数/授权/SQLite记录见live_recovery_cli.txt、live_acceptance.json及候选state/live/research.sqlite3。



真实成果：`/srv/jijigua-quant-agent/research_runs/2026-10-13/01-09-21_reversal_5d`。其中 `data/factor.pkl`、`reports/report.html`、`reports/report.md`为已存在文件。实际代码/数据/参数/评价指纹与同一study_id关联。



最后通过会话使用 52,105 tokens（输入47,968、输出4,137）；本轮所有真实尝试累计204,812，unknown_calls=0。包括已保留的合同失败和年度摘要被挤掉后的修复重验，不把失败消耗抹去。API未提供实际账单费用，不推算金额；最终已停止进一步真实调用。



## 5. 工程/性能/视觉验收



Windows/Linux完整套件各319通过、1跳过。之后仅有会话证据限额修复，受影响33项Windows/Linux定向测试再通过，未重复运行全部套件。Windows跳过符号链接权限；Linux跳过未安装的可选pyarrow。完整代码/wheel、环境和XML见source_manifest.json、TEST_RESULTS.md。



同定义20日动量H5真实基准：67.303秒、2061.63MiB；新增专业评价4.108秒；6年72月及144数值格独立复算。较v0.7历史基准总时间+16.0%、RSS+9.7%，没有通过降采样宣称加速。最后真实五日反转确定性计算67.434秒、峰值2055.20MiB，含模型首轮自然对话约78秒；完整会话约96秒。阶段包含关系及限制见PERFORMANCE.md。



实际HTML、截图、深浅色、窄屏、悬浮、1y/All、SVG下载、PDF渲染检查见VISUAL_QA.md。8交互图控制台0错误、0外部资产；HTML为离线自包含设计。浏览器策略禁止file://，未绕过，文件直开UI和整页系统打印预览未实测；窄屏有7像素DOM宽度差的轻微待改进项。不能把截图存在或单元测试成功当完美视觉认证。



## 6. 生产、回滚与仍待批准事项



audit.json对production_before.json核对84个源文件、两个配置和启动器全部相同，以上为部署前证据；部署后版本0.8.0，数据库原位、配置与入口SHA不变。quantagent实际读原始PKL/staging/daily_private/audit均PermissionError，旧daily20/daily65的2026读取拒绝。数据库无Schema迁移，旧会话/任务/PKL/报告保留。



审定wheel SHA `dfd3508fd3004d476df48268b9d3be459ad24356bad96c948542c46613600978`；精确生产范围/备份/回滚见DEPLOYMENT_APPROVAL.md，**用户已明确批准并执行**，正式quant-agent chat入口已通过实际SSH PTY与独立数值账本核验。真实2026发布/权限/解封另见HOLDOUT_EVALUATOR_APPROVAL.md，不能随本次生产升级自动批准。



尚未完成：真实Test发布/独立身份/传输接收/实际Test评价；正式回测、PIT行业市值、公司行动和交易状态认证；后台持久任务及生产硬沙箱。不因本轮指标或六字段发布解除BLOCKED。



`/hy-tmp`有清理风险，重要数据版本、PKL、报告、manifest和账本需要用户持久备份；本轮未上传外部平台或创建备份服务。





实际回滚备份：`/opt/jijigua-quant-agent/research_agent/release_backups/v070_before_v080_20261013_013133`。安装证据：production_deployment.json；没有注册/发布任何真实2026资源。





## 7. 获批后的正式入口验收（最终状态）



用户明确批准这份精确部署清单后，更新既有项目源码/wheel/文档，不变更配置、launcher、账号/ACL或研究数据库。正式入口仍为root Shell执行 `quant-agent chat`，随后进程由可信launcher降为quantagent UID999，官方DeepSeek/deepseek-flash。



最终会话 `INTERNAL_RUN_ID_REDACTED`，研究 `INTERNAL_RUN_ID_REDACTED:1339576f3486425d`：你好→五日反转研究→登记测试申请→逐年RankIC追问→2026调参拒绝→报告路径。问候、年度和报告查询未调用无关计算；因子计算仅一次。



本次自然语言默认选择5日反转、预测期H=5、raw、5组；与前述候选H=1/zscore是不同已记录实验，不能混用统计值。正式成果：`/srv/jijigua-quant-agent/research_runs/2026-10-13/01-33-21_reversal_5d`。完整1455×5427 PKL与独立NumPy、7日Pearson/Spearman、各分区H+1尾部成熟规则及89个manifest文件SHA均通过。



| 年份 | 分区 | IC mean | RankIC mean | 有效日 |

|---|---|---:|---:|---:|

| 2020 | Train | -0.002699 | +0.022798 | 238 |

| 2021 | Train | +0.016003 | +0.028995 | 243 |

| 2022 | Train | +0.041417 | +0.033595 | 242 |

| 2023 | Train | +0.026539 | +0.019903 | 236 |

| 2024 | Validation | +0.049835 | +0.042576 | 242 |

| 2025 | Validation | +0.036704 | +0.050104 | 237 |

| 2026 | Test SEALED / NOT_RUN | N/A | N/A | N/A |



正式研究Verdict：PROMISING_EXPLORATORY，tradable=false。这只是当前固定方向的探索性证据，数据资格与已曝光Validation的限制不变。Test申请仍submitted=false/test_data_read=false/test_results_returned=false；未产生实际2026统计。



确定性计算与交付68.303秒、峰值2059.05MiB。研究问题到首轮回答实际约80秒，完整验收会话约97秒，包含模型交互；没有用确定性阶段时间冒充CLI时长。正式验收58,056 tokens、unknown_calls=0；候选全部尝试204,812，本轮合计262,868（含失败与修复重验）。production_acceptance.json里的usage_all_attempts是整个旧生产账本历史累计，含15次历史未知调用，不是本轮成本；不能抹去该记录。



旧任务264条逐payload SHA保留，数据库Schema SHA `92dc8e9a03a7283a6bf6029f2d7695d00fbf6b9f6401bf788e3f1b212037efaa`不变、inode不变。原始PKL/私有目录和旧daily65/daily20仍拒绝；回滚备份 `/opt/jijigua-quant-agent/research_agent/release_backups/v070_before_v080_20261013_013133`。



最终证据：production_deployment.json、production_acceptance.json、production_live_cli.txt、production-live_console.txt和audit.json。生产源码与审定wheel保持一致；真实Test解封未获授权，本轮不继续。

