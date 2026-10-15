> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-B 源码及引擎验收范围

Claude qrtk 0.2.0 的12个计算/报告模块保持原字节；47个上游源码/合同文件按已有审查指纹核对。没有修改 GeorgeResearch 原项目，也没有新增第二套 Agent Runtime。

新主代码：factor_expression.py（白名单DAG/量纲/时间/预算）、research_report.py（由qRTK数值/CSV生成报告与图表）、evidence.py（验证后结果的模型摘要）。修改 quant/workflow/conversation/terminal/data/runtime 及对应测试、五个Skill方法/内容封印、构建和部署脚本。
因子数学评价继续使用原qRTK，不重复实现生产评价公式；标准库独立标量计算只用于数值核验。

## Pyx / Perry

本輪重新哈希：
- Pyx score_backtest.py：ad000f1dfcfdf557436457f6c7b09482cf2de50e2822ace0061e744b2751a4c3
- Pyx position_planner.py：bd27bf8e9c051950fa3887756cbee83c4e747888f57645fd4c3f72f2dab27e21
- Perry run_position_backtest.py：4d81d3419368fd01cf87ae9d227d731ee43b52be91deebee8ba70108fbb76fd0

与Phase2-A审查源码一致。测试中的独立Pyx副本只保留受审的成交、绩效及轴规范化三个函数，不导入CVXPY规划器，不读写pickle，不作为Agent Tool。
合成案例覆盖下一会话日、买卖费用、卖出优先、现金不足/非法价格/交易拒绝、保留持仓、轴排序、未知NAV拒绝，以及标准库Decimal和qRTK参考账本的交叉核对。2000起始现金，100股×10、买费0.1%，后以11卖出、卖费0.2%，最终现金2096.8；不是市场收益证据。

**未认证整个引擎**：没有运行CVXPY规划器或Perry外部依赖，未执行完整生产研究脚本。
Pyx仍缺独立可买/可卖、明确的VWAP可获得性/执行口径、复权与公司行动、历史板块/退市约束和费用日程。
Perry仍需外部planner/artifacts、缺失状态默认值、日期排序、成交价估值分离、首日费用及实际成交持仓的修正/验收。
正式回测Tool不注册；qrtk_backtest_readiness明确BLOCKED_DATA_CONTRACT/BLOCKED_ENGINE_QUALIFICATION，无真实NAV/Sharpe/回撤。

## 图表复用

继续调用Claude report_render保存原Markdown/PNG/CSV兼容输出；新主报告适配器使用相同已验收数值增加统一PNG/SVG/PDF及自包含HTML。
日期使用稀疏自动刻度，图例放在曲线外；所有图表为单轴，面板对齐检查不适用。
IC/RankIC与毛分组的样本、成熟标签、缺失排除和重叠标签明确展示；比较图不称独立样本外，暖机改变的样本数保存在CSV。
无合格账户结果时不生成净值、回撤或交易成本图。

## 本轮发现并修复的问题

- 原兼容报告的全序列会包含跨训练/验证边界的标签，而分段统计已清除这些标签。新适配器使用 qrtk.label_exit_dates 分段筛选，图表/CSV与训练及验证指标一致；边界空白不连线。没有修改上游数学模块。
- 第二次真实对话把 max(x,1) 解释成 max(x,0)。保留原始记录并更正 Skill 的算子说明，CLI 直接展示可信计算登记的实际公式；最终六轮记录中的九节点表达式与独立标量复核一致。语言总结仍应以登记公式为准。
- 报告窄视口下长公式/指标表导致整页溢出。最终包增加公式换行和表格内部滚动，保留数值精度；独立真实单任务补验该报告改动。

attempt1/attempt2 是较早安装包的验收历史，不作为最终图表口径的证明；主 live-session.json 对应完整六轮最终计算功能，report-patch-live-session.json 对应最终 CSS 修复后的单任务验收。安装包指纹在 deployment.json。
