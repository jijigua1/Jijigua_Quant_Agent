> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-A 受控历史 CSV 发布申请

源文件已只读核验：`/hy-tmp/update_data/recent_days/TRD_Dalyr.csv`，360,644 行，5,656 个代码，65 个观察到的交易日期，2026-07-03—2026-10-09，736,860,569 bytes。源 SHA-256：e9d88d46f6aa8ec443f163fa021a506839b4d7ee85b98f63126b0b44051cad8a。

真实生产转换代码确认 OHLC 来自 Tushare daily，未乘复权因子；vol 手×100转股、amount千元×1000转元。已有 source_manifest 部分记录有抓取时间与来源；尚未核验每个历史字段的可获得时间。

申请范围：

1. 从**首日2026-07-03出现的代码**按代码排序固定选前50只，保留全部65个日期内这些代码的行，最多3,500行。选池规则不按末日存活或结果选择。
2. 仅发布 Stkcd、Trddt、Opnprc、Hiprc、Loprc、Clsprc、Dnshrtrd、Dnvaltrd、Trdsta 九字段。
3. 新增 `/opt/jijigua-quant-agent/research_agent/data_readonly/daily65.csv`，root:quantagent 0640；只对新文件设置权限，不改共享原始数据。
4. 在该项目 root 管理的 resources.json 中**追加** `gpushare:daily65`，保留原 gpushare:daily20 与原快照；新增 research.json 记录口径、授权引用和成果根目录。
5. 管理发布脚本只使用标准库 csv，先核对源指纹、行数和无重复键，再写入新目标；已有目标则拒绝覆盖。

能力边界：该样本只允许 **原始价格的探索性因子统计与接口验收**。65日不足以完成每段60日的训练/验证/测试；日历是样本日期并集，公司行动未处理，停牌/涨跌停/退市字段语义未完整验证。测试段封存，不能称为独立样本外表现、合格回测或有效策略。放量滞涨计算使用同口径成交量比，不声称其有效。

禁止事项不变：不加载 pickle、不读88GiB因子矩阵、不修改其他项目或生产任务。
