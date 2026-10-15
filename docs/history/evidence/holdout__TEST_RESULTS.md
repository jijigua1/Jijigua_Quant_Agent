> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 验收记录

| 检查 | 状态 | 证据 |
|---|---|---|
| Windows独立模块 | 29通过，0跳过，2.49s | evidence/recovery_tests.xml |
| 已有Linux合成模块 | 25通过，0.86s；复用此前证据 | evidence/linux_synthetic.json |
| 批准后Linux空值修复 | 4个确定性案例通过；quanteval，未读真实快照 | evidence/final_acceptance_actual.json |
| 源SHA、私有发布/身份 | 通过；与批准固定源一致 | evidence/publish_actual.json、private_publication_security.json |
| H=5成熟边界 | 实际观察索引复算，183观察日、177成熟日、末端6日剔除 | evidence/maturity_index_check.json |
| 独立真实相关基准 | 183日IC/RankIC一致，年度/月度一致，1e-12 | evidence/accepted_report/verification/independent_verification.json |
| 独立HAC与CSV/热力图 | 通过；7年度、82月份、168单元格；Train/Validation不变 | evidence/aggregate_crosscheck_actual.json |
| 历史文件/生产源码 | 原89个产物保留；92个生产源码文件SHA不变 | evidence/revision2_integrity_actual.json、final_acceptance_actual.json |
| 默认低权限隔离 | 实际OS打开原始PKL/私有数据/账本/密钥/审计均拒绝 | evidence/private_publication_security.json、final_acceptance_actual.json |
| 尝试/曝光/失败审计 | 仅1次真实评价，剩余0，旧失败保留 | root audit/events.jsonl、evidence/revision2_integrity_actual.json |
| 官方API真实CLI读取 | 指定读取工具后成功取最新三阶段统计与revision2 | evidence/real_production_cli_read_tool.txt、final_acceptance_actual.json |
| 普通语言自动刷新 | 未通过，旧会话缓存SEALED仍被复述 | evidence/real_production_cli.txt、real_production_cli_refresh.txt |
| 下一轮N/A解释 | 未通过，模型错误称没有月度粒度 | evidence/real_production_cli_read_tool.txt |
| 未批准原始Test调参请求 | 首次真实CLI拒绝，未调用读取原始数据工具 | evidence/real_production_cli.txt |
| 桌面/窄屏报告 | 表格及2026热力图可见，窄屏初次加载无页面溢出 | evidence/screenshots/revision2_desktop_full.jpg、revision2_monthly_visible.jpg、revision2_narrow.jpg |
| 连续图本地预览 | 日期图不重置累计值，两条分区竖线，静态导出同步；不改变统计 | evidence/continuous_report_preview/v2/preview_manifest.json、evidence/screenshots/continuous_correlation_preview.jpg、continuous_groups_preview.jpg |

## 测试范围说明

- 没有重新跑冻结主Agent的无关完整回归，也没有重新运行真实评价。沿用v0.8的未冻结/参数变更/伪造回执/次数控制等合成证据，不把合成拒绝当成新真实Test评价。
- 新增聚合核验和预览脚本有断言检查；没有调用IndependentEvaluator.evaluate、任意模型代码或新API。
- 独立年度/月度测试从逐日数据复算，HAC用标准库独立实现，而非两次调用同一评价函数。
- 新预览的累计图是统计累计和，跨边界连接缺失区间只改变画线方式，保存的缺失位置不填0。分区训练、验证、测试的统计与权限仍各自独立。
- 交互缩放、日期分区、热力图N/A已有v0.8合成/视觉证据；本轮检查真实桌面及窄屏。切换大/小视口时Plotly偶有需要重新加载的布局现象，未据此声称全部响应式场景通过。
- 已批准真实Test回执没有逐日组收益/n_pairs完整公共字段，相关公共CSV保留N/A；平均有效股票数已与独立基准对照。不伪造缺失Test诊断。
- 生产代码保持冻结，本轮没有修复对话缓存、压缩摘要丢失月度信息或旧报告的历史范围措辞，因此整体CLI语义验收仍为PARTIAL。
