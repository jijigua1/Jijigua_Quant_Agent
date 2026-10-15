> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-A 数据资产清单

审计日期：2026-10-12。范围仅为已有 `survey/results/` 证据、只读源码快照与已记录的小范围真实核验；本次交接没有重新扫描、复制或反序列化服务器数据。下表“可读”表示格式核验，不表示交易时点或回测准入。

| 资源 | 位置与格式 | 已核实覆盖 | 来源/关系 | 本轮结论 |
|---|---|---|---|---|
| `daily_update` 宽表 | `/hy-tmp/data/daily_update/{open,high,low,close,volume,amount,adj_factor,close_adj,...}.pkl`；单字段 date×code DataFrame | 2019-01-02—2026-10-09，1,882 个交易日、5,427 个沪深代码；每个主字段约 81.8 MB | `eod_factor_update.py` 使用 Tushare daily、adj_factor、daily_basic 等更新；文件大小及逐文件 SHA-256 固定于 `schemas/daily_update_manifest.v1.json` | 六个原始价量字段可做**版本固定、探索性**长期因子研究；上市前回填、复权版本、可交易状态等问题阻止正式回测 |
| 实际适配器核验切片 | 同上，8 个主字段 | 2020-01-02—2026-10-09，1,638 日、5,427 代码 | `real_sample_run.json` 记录静态解码、数值和拒绝结果 | 不是独立新数据源；其核验范围与上行相交，不能叠加为更多样本 |
| Perry EOD | `/hy-tmp/research_perry/eod`，约 9.99 GB、dict/134 字段 | 2016-01-04—2026-08-20，2,583 日、5,878 代码 | 与 `/srv/auxiliary-data/EOD_Columns/eod` 字节相同；与 daily_update 重叠 8,518,112 对原始 close 完全一致 | 可作交叉核查和早期覆盖候选；不是第二份独立行情证据。大文件解码内存边界未合格，**不开放 Agent 读取** |
| 近期原始 CSV | `/hy-tmp/update_data/recent_days/TRD_Dalyr.csv`、`.../tushare/TRD_Dalyr.csv` | 前者 2026-07-03—10-09、360,644 行；后者 2026-07-15—10-09、315,864 行 | `auto_update_csv.py`：Tushare daily/basic/moneyflow → CSV，部分状态/涨跌停为派生或估计 | 可交叉核验单位、近端交易数据；不是完整历史状态合同 |
| 当日 CSV | `/hy-tmp/update_data/today/TRD_Dalyr.csv` | 2026-10-09，5,559 行 | 同一生产链 | 仅当日审计样本 |
| 交易日历 | `daily_update/trading_date.pkl` | 数据区间内 SSE/SZSE 各 1,882 日，日期与宽表一致 | `calendar_check.json` 独立静态检查 | 日期轴交叉核验通过；交易所具体时段/临时停市规则尚未单独验收 |
| 历史上市清单 | `/srv/auxiliary-data/TRD_Co.csv` | 有 5,537 A 股记录；其最后上市日期为 2026-07-02 | `pit_checks.json` 与宽表对照 | 时点和完整性不足，不能单独充当历史股票池/上市退市真值 |
| 旧版复权快照 | `/hy-tmp/data/daily/close_adj.pkl` | 2019-01-02—2026-05-22，1,789 日 | 与当前文件历史值大量不一致 | 只用于版本漂移审计，不作为替代价格真值 |
| VWAP、状态、行业、分钟及 moneyflow 辅助列 | daily_update/EOD 各相应文件 | 字段存在，覆盖不一；如独立 `vwap` 提前停更于 2026-08-07 左右 | 字段枚举及部分缺失率见静态元数据/EOD skeleton | 逐字段准入；未经历史可获得时间和含义核验，不开放正式研究或回测 |

`daily_update` 是固定生产轴，非完整动态上市股票池：5,427 代码中有 234 个最后交易日早于最后一个月，但缺少北交所；与 `TRD_Co.csv` 比较至少 5 只 2026 年上市股票未进入宽表。宽表股票代码采用六位数字加 `.SH`/`.SZ`，日期为 `YYYYMMDD`；不能把该固定轴当成“当时全部可交易 A 股”。

**当前访问状态。** 上表“可作探索”指数据候选；全历史 PKL 包含最终测试期，旧适配器先读整文件。Train/Validation 独立快照尚未发布，因此本次交付的分区接口对真实资源拒绝读取。

**版本与身份。** 主文件逐项路径、字节数和 SHA-256 见保留的 `v1 原清单`（原内部附件未公开） 及新增的 `v2 降级清单`（原内部附件未公开）；EOD 两份内容一致见 `../survey/results/eod_copies_cmp.txt`（原内部附件未公开）。所有后续研究必须指向确定的哈希，不能只记录路径。v1 原有整段 `RESEARCH_READY` 声明是旧阶段清单标记；v2 已将核心字段降为 `PROFILED` 并列出失败条件，分区原型仅用 v2，并标为 `PROFILED_EXPLORATORY_ONLY`。

主要证据：`daily_update_static_meta.json`（原内部附件未公开）、`daily_update_checks.json`（原内部附件未公开）、`cross_source_checks.json`（原内部附件未公开）、`pit_checks.json`（原内部附件未公开）、`real_sample_run.json`（原内部附件未公开）、`csv_axis_profile.json`（原内部附件未公开）。证据路径及复核范围见 [`EVIDENCE_INDEX.md`](data-audit__EVIDENCE_INDEX.md)。
