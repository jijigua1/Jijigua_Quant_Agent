# Quant-Agent研发时间线

证据优先级：实际源码/指纹与可核验数值 > 具有明确环境的验收记录 > 当时方案/需求。无Git仓库意味着不能补造commit图。下列日期描述证据记录，不把文件mtime冒充首次发现日期。

## 阶段总览

| 时间 | 阶段 | 主要进展 | 当时限制 | 证据 |
|---|---|---|---|---|
| 2026-10-11（当前最早可核验交付） | Phase1-D：独立离线研究核心 | Provider、Tool Registry、Skill、独立授权与SQLite。Mock研究证明接口而非自然语言能力。早期固定步骤式原型存在于需求背景，但其完整原始源码/提交链未取得，不能重建成虚构版本。 | 真实API和服务器数据尚未连通；后续改为明确development profile及受控只读入口。 | [legacy__PHASE1_D_REPORT.md](evidence/legacy__PHASE1_D_REPORT.md) |
| 2026-10-12（报告标注） | Phase1-E/F：真实模型、只读数据与连续对话 | 真实DeepSeek协议、Skill发现、多轮指代、会话/任务分离；普通聊天与澄清可不调Tool。HTTP诊断、JSON校验与未知用量记录进入Provider层。 | 早期首次HTTP_ERROR无法追溯具体状态码，不能因后来成功而补写原因。 | [legacy__REPORT_1e9c4b54.md](evidence/legacy__REPORT_1e9c4b54.md) |
| 2026-10-12（报告标注） | Phase2-A：工具包和五个研究Skill | 复用qrtk而非另起Agent；日频计算、数据诊断、报告与回测准入分层，真实daily65仍为小样本探索。 | 正式回测数据与交易规则不足；独立工具包测试不是账户策略有效性。 | [legacy__REPORT_4f55df2b.md](evidence/legacy__REPORT_4f55df2b.md) |
| 2026-10-12（报告标注） | Phase2-B：19算子DSL与成果归档 | 受控表达式、因果窗口检查、参数变更独立实验、图表、Markdown/HTML、进度与预算。 | 阶段事件不是固定Step1–9；合作式超时不是OS硬配额。 | [legacy__REPORT_b0797616.md](evidence/legacy__REPORT_b0797616.md) |
| 2026-10-12（报告标注） | Phase2-C：默认PKL、报告、LaTeX、终端及定义门 | 计算成功后可信归档自动导出验证PKL；时间+因子目录、指标表和公式。动量请求暴露Schema误分类及未确认替代，随后增加参数指纹确认门。 | v0.6.5探索替代曾抢先执行，不能写成全通过；v0.6.8门禁结果参见独立修复材料。 | [legacy__REPORT_82afdfd4.md](evidence/legacy__REPORT_82afdfd4.md) |
| 2026-10-12（证据与报告；精确起始时刻未确认） | Phase3-A：长期行情审查与认证降级 | 静态PKL、字段字典、单位、历史修订、上市前回填、状态字段冻结及分区原型。 | SplitReader原型不是服务器物理隔离；价格可读不能认证成交或总收益。 | [data-audit__PHASE3A_FINAL_REPORT.md](evidence/data-audit__PHASE3A_FINAL_REPORT.md) |
| 2026-10-12（阶段报告） | Phase3-B1：候选账本及合成交易合同 | 审查现有core_backtest raw-price模式，独立手算/合成交易、公司行动与资金核对。 | 不是正式真实回测上线；佣金、订单生命周期、交易状态和PIT仍有缺口。 | [ledger__PHASE3B1_FINAL_REPORT.md](evidence/ledger__PHASE3B1_FINAL_REPORT.md) |
| 2026-10-12（真实发布记录） | Phase3-B2：受控历史发布与上市准入限制 | 2020–2025六原字段分区，固定源SHA与低权限静态解析；两只身份冲突证券排除，研究资格仍为PROFILED_EXPLORATORY_ONLY。 | 上市日期未全认证；不能默认为正式可交易股票池。 | [release__PHASE3B2_LISTING_RELEASE_REPORT.md](evidence/release__PHASE3B2_LISTING_RELEASE_REPORT.md) |
| 2026-10-12（阶段交付） | v0.7.0：全轴长期自然语言因子研究 | 970日Train+485日Validation、5427轴，暖机/成熟标签边界、默认全轴PKL和报告、真实官方模型CLI。 | Validation已曝光，2026不是普通资源；旧daily65旁路被限制。 | [full-panel__PHASE3B2C_FINAL_REPORT.md](evidence/full-panel__PHASE3B2C_FINAL_REPORT.md) |
| 2026-10-12—13（报告记录，逐文件查时间） | v0.8：专业评价和统一三阶段报告 | 年/月指标、数值热力图、HAC、交互报告、Research Verdict和独立Test合成评估原型。 | 未批准Test时保留栏目SEALED/NOT_RUN，不能把合成Test填进真实研究。 | [v08__V08_FINAL_REPORT.md](evidence/v08__V08_FINAL_REPORT.md) |
| 2026-10-13前后（以审批和执行报告为准） | Phase3-C：一次性真实回顾性Test与报告恢复 | 冻结五日反转，一次获批真实Test；183观察/177成熟日，空值核验故障后仅恢复核验与报告，未增加评价预算。 | H=5最后成熟边界按真实索引计算；10月N/A不是缺行情；历史曝光不再称盲测。 | [holdout__PHASE3C_FINAL_REPORT.md](evidence/holdout__PHASE3C_FINAL_REPORT.md) |
| 2026-10-13（最终修复记录） | v0.8.1/0.8.2：连续图、最新证据、共享报告与CLI | 连续累计、分区竖线、新revision、会话摘要失效、跨会话共享目录与真实中文查询。 | 仅共享审定研究；模型对样本量仍有偏强措辞风险，测试不证明无幻觉。 | [holdout__RESUME_FINAL_REPORT.md](evidence/holdout__RESUME_FINAL_REPORT.md) |
| 2026-10-13 | v1.0 Beta：论文—可信执行—滚动Test | 独立预发布、生产启动路由、root broker、quanteval、日更源版本和签名回执。 | 自动化启用与用户实际入口是两件事；首轮真实Test引发64KB及请求文件冲突事故。 | [v1beta__PRODUCTION_ENABLEMENT_CN.md](evidence/v1beta__PRODUCTION_ENABLEMENT_CN.md) |
| 2026-10-14 | candidate4及质量验收 | 经济逻辑、显著性说明、G0–G4与报告视觉改进，候选冻结。 | 发现AQR错误放行与MA自由参数/资产问题，不能以图表正确代替论文忠实。 | [v1beta__FINAL_QUALITY_ACCEPTANCE_20261014_CN.md](evidence/v1beta__FINAL_QUALITY_ACCEPTANCE_20261014_CN.md) |
| 2026-10-14晚—15 | 论文稳定性、IR语义、回执恢复与客户端加固 | 有限调查、命名参数、编号一致、JSON修复、符号语义版本、逐股票暖机投影、read/refresh分离、完整指标表和批量跨平台客户端。 | 最新阅读器真实验收一度受官方API故障阻断；后续A/B仍可能在活跃推进，本归档不代其最终验收。 | [v1beta__05_AI_PROGRAM_RECONCILE_CN.md](evidence/v1beta__05_AI_PROGRAM_RECONCILE_CN.md) |
| 2026-10-14 23时段（历史只读审计） | 生产与预发布差异核验 | 生产169文件与P1 hotfix清单一致；已有回执与数值复算、磁盘/cron/权限核查。 | 该状态有时间边界，不证明10月15之后生产从未变化。本次归档未再连接生产。 | [production-audit__QUANT_AGENT_PRODUCTION_AUDIT_CN.md](evidence/production-audit__QUANT_AGENT_PRODUCTION_AUDIT_CN.md) |

## 1. Phase1-D：独立离线研究核心

**证据时间：** 2026-10-11（当前最早可核验交付）。

**能力与升级动机：** Provider、Tool Registry、Skill、独立授权与SQLite。Mock研究证明接口而非自然语言能力。早期固定步骤式原型存在于需求背景，但其完整原始源码/提交链未取得，不能重建成虚构版本。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [legacy__PHASE1_D_REPORT.md](evidence/legacy__PHASE1_D_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 真实API和服务器数据尚未连通；后续改为明确development profile及受控只读入口。


## 2. Phase1-E/F：真实模型、只读数据与连续对话

**证据时间：** 2026-10-12（报告标注）。

**能力与升级动机：** 真实DeepSeek协议、Skill发现、多轮指代、会话/任务分离；普通聊天与澄清可不调Tool。HTTP诊断、JSON校验与未知用量记录进入Provider层。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [legacy__REPORT_1e9c4b54.md](evidence/legacy__REPORT_1e9c4b54.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 早期首次HTTP_ERROR无法追溯具体状态码，不能因后来成功而补写原因。


## 3. Phase2-A：工具包和五个研究Skill

**证据时间：** 2026-10-12（报告标注）。

**能力与升级动机：** 复用qrtk而非另起Agent；日频计算、数据诊断、报告与回测准入分层，真实daily65仍为小样本探索。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [legacy__REPORT_4f55df2b.md](evidence/legacy__REPORT_4f55df2b.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 正式回测数据与交易规则不足；独立工具包测试不是账户策略有效性。


## 4. Phase2-B：19算子DSL与成果归档

**证据时间：** 2026-10-12（报告标注）。

**能力与升级动机：** 受控表达式、因果窗口检查、参数变更独立实验、图表、Markdown/HTML、进度与预算。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [legacy__REPORT_b0797616.md](evidence/legacy__REPORT_b0797616.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 阶段事件不是固定Step1–9；合作式超时不是OS硬配额。


## 5. Phase2-C：默认PKL、报告、LaTeX、终端及定义门

**证据时间：** 2026-10-12（报告标注）。

**能力与升级动机：** 计算成功后可信归档自动导出验证PKL；时间+因子目录、指标表和公式。动量请求暴露Schema误分类及未确认替代，随后增加参数指纹确认门。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [legacy__REPORT_82afdfd4.md](evidence/legacy__REPORT_82afdfd4.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** v0.6.5探索替代曾抢先执行，不能写成全通过；v0.6.8门禁结果参见独立修复材料。


## 6. Phase3-A：长期行情审查与认证降级

**证据时间：** 2026-10-12（证据与报告；精确起始时刻未确认）。

**能力与升级动机：** 静态PKL、字段字典、单位、历史修订、上市前回填、状态字段冻结及分区原型。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [data-audit__PHASE3A_FINAL_REPORT.md](evidence/data-audit__PHASE3A_FINAL_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** SplitReader原型不是服务器物理隔离；价格可读不能认证成交或总收益。


## 7. Phase3-B1：候选账本及合成交易合同

**证据时间：** 2026-10-12（阶段报告）。

**能力与升级动机：** 审查现有core_backtest raw-price模式，独立手算/合成交易、公司行动与资金核对。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [ledger__PHASE3B1_FINAL_REPORT.md](evidence/ledger__PHASE3B1_FINAL_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 不是正式真实回测上线；佣金、订单生命周期、交易状态和PIT仍有缺口。


## 8. Phase3-B2：受控历史发布与上市准入限制

**证据时间：** 2026-10-12（真实发布记录）。

**能力与升级动机：** 2020–2025六原字段分区，固定源SHA与低权限静态解析；两只身份冲突证券排除，研究资格仍为PROFILED_EXPLORATORY_ONLY。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [release__PHASE3B2_LISTING_RELEASE_REPORT.md](evidence/release__PHASE3B2_LISTING_RELEASE_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 上市日期未全认证；不能默认为正式可交易股票池。


## 9. v0.7.0：全轴长期自然语言因子研究

**证据时间：** 2026-10-12（阶段交付）。

**能力与升级动机：** 970日Train+485日Validation、5427轴，暖机/成熟标签边界、默认全轴PKL和报告、真实官方模型CLI。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [full-panel__PHASE3B2C_FINAL_REPORT.md](evidence/full-panel__PHASE3B2C_FINAL_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** Validation已曝光，2026不是普通资源；旧daily65旁路被限制。


## 10. v0.8：专业评价和统一三阶段报告

**证据时间：** 2026-10-12—13（报告记录，逐文件查时间）。

**能力与升级动机：** 年/月指标、数值热力图、HAC、交互报告、Research Verdict和独立Test合成评估原型。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [v08__V08_FINAL_REPORT.md](evidence/v08__V08_FINAL_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 未批准Test时保留栏目SEALED/NOT_RUN，不能把合成Test填进真实研究。


## 11. Phase3-C：一次性真实回顾性Test与报告恢复

**证据时间：** 2026-10-13前后（以审批和执行报告为准）。

**能力与升级动机：** 冻结五日反转，一次获批真实Test；183观察/177成熟日，空值核验故障后仅恢复核验与报告，未增加评价预算。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [holdout__PHASE3C_FINAL_REPORT.md](evidence/holdout__PHASE3C_FINAL_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** H=5最后成熟边界按真实索引计算；10月N/A不是缺行情；历史曝光不再称盲测。


## 12. v0.8.1/0.8.2：连续图、最新证据、共享报告与CLI

**证据时间：** 2026-10-13（最终修复记录）。

**能力与升级动机：** 连续累计、分区竖线、新revision、会话摘要失效、跨会话共享目录与真实中文查询。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [holdout__RESUME_FINAL_REPORT.md](evidence/holdout__RESUME_FINAL_REPORT.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 仅共享审定研究；模型对样本量仍有偏强措辞风险，测试不证明无幻觉。


## 13. v1.0 Beta：论文—可信执行—滚动Test

**证据时间：** 2026-10-13。

**能力与升级动机：** 独立预发布、生产启动路由、root broker、quanteval、日更源版本和签名回执。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [v1beta__PRODUCTION_ENABLEMENT_CN.md](evidence/v1beta__PRODUCTION_ENABLEMENT_CN.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 自动化启用与用户实际入口是两件事；首轮真实Test引发64KB及请求文件冲突事故。


## 14. candidate4及质量验收

**证据时间：** 2026-10-14。

**能力与升级动机：** 经济逻辑、显著性说明、G0–G4与报告视觉改进，候选冻结。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [v1beta__FINAL_QUALITY_ACCEPTANCE_20261014_CN.md](evidence/v1beta__FINAL_QUALITY_ACCEPTANCE_20261014_CN.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 发现AQR错误放行与MA自由参数/资产问题，不能以图表正确代替论文忠实。


## 15. 论文稳定性、IR语义、回执恢复与客户端加固

**证据时间：** 2026-10-14晚—15。

**能力与升级动机：** 有限调查、命名参数、编号一致、JSON修复、符号语义版本、逐股票暖机投影、read/refresh分离、完整指标表和批量跨平台客户端。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [v1beta__05_AI_PROGRAM_RECONCILE_CN.md](evidence/v1beta__05_AI_PROGRAM_RECONCILE_CN.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 最新阅读器真实验收一度受官方API故障阻断；后续A/B仍可能在活跃推进，本归档不代其最终验收。


## 16. 生产与预发布差异核验

**证据时间：** 2026-10-14 23时段（历史只读审计）。

**能力与升级动机：** 生产169文件与P1 hotfix清单一致；已有回执与数值复算、磁盘/cron/权限核查。

**初始实现、失败与设计演进：** 具体缺陷以对应原报告及下方事故档案为准；不能将该阶段的验收归到其他源码快照。

**验证与最终状态：** [production-audit__QUANT_AGENT_PRODUCTION_AUDIT_CN.md](evidence/production-audit__QUANT_AGENT_PRODUCTION_AUDIT_CN.md) 记录当时测试/真实调用及环境。本次运行结果另见[归档验收](../release/TEST_RESULTS.md)。

**遗留与后续影响：** 该状态有时间边界，不证明10月15之后生产从未变化。本次归档未再连接生产。

## 不能重建的部分

没有取得从项目第一天开始的完整原始需求、私有Git提交链与所有修复前源码。旧对话及日志未公开；不把其缺失补成已发生事实。候选4目录是冻结文件子集，不是完整171文件源码仓库；各份清单、打包版本与运行版本需要分别核验。当前公开代码是本次一致研发快照，历史文件只承担证据职能。
