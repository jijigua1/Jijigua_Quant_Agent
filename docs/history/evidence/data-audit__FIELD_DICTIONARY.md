> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-A 字段字典与使用边界

日期键为交易日 `YYYYMMDD`，股票键为六位代码加 `.SH`/`.SZ`；宽表单字段 `float64` 或布尔，行是日期、列是股票。下文“数值验证”只证明文件内/源间关系，不证明当时实时可获得。原始行情通常在 T 日收盘后才形成完整 OHLCV；要产生 T 日信号，执行时点不得早于 T 收盘，且须单独核验数据发布时间。缺失值保留为缺失，不填零、不视为停牌。

| 字段 | 含义、类型、单位及生成链 | 已核实内容 | 研究用途与限制 |
|---|---|---|---|
| `open` | 原始开盘，float64，元/股；Tushare daily→`eod_factor_update.py` | 近期 CSV 重叠价一致；T 开盘才可得 | 探索性特征可用；T 开盘信号不得使用当日后续字段 |
| `high`、`low`、`close` | 原始最高、最低、收盘，float64，元/股；Tushare daily | 8,675,338 个有效收盘单元 OHLC 边界检查通过；close 与 EOD 重叠 8,518,112 对一致 | T 收盘后的探索性因子输入；价格不是已验证的成交价格，上市前回填单元须排除 |
| `volume` | 成交量，float64，**手（100 股）**；Tushare `vol` | 近期 CSV/ EOD 对应股数约为 `volume×100` | T 收盘后的量价研究；不得把手当股 |
| `amount` | 成交额，float64，**千元**；Tushare `amount` | CSV/EOD 元单位约为 `amount×1000`；`amount×10/volume` 落在日 OHLC 内（有效单元 8,675,338） | T 收盘后的量价研究；不得把千元当元 |
| `adj_factor` | 后复权累计因子，float64、无量纲；Tushare adj_factor | 与 `close_adj=close×adj_factor` 精确相符；但旧/新历史快照变动巨大，存在异常下降及舍入跳变 | 仅做版本固定的探索性调整/敏感性检查；历史时点可信度不足，**不得直接用于正式回测** |
| `open_adj`、`high_adj`、`low_adj`、`close_adj` | 对应原始价×当日因子，float64、复权元/股；生产代码第 532 行 | 代数关系确认，`close_adj` 旧/新快照 8,192,856 对中 7,812,105 对变化 | 可供有版本说明的研究敏感性分析；不是原始成交价或可靠 PIT 快照 |
| `vwap_adj` | `amount×10/volume×adj_factor`，复权元/股；生产代码第 586–604 行 | 当前宽表公式一致 | 非原始可交易 VWAP；使用前核验当日量额/因子时点 |
| `vwap` | 独立历史辅助字段，float64、元/股 | 静态元数据显示约 2026-08-07 后未持续更新 | 拒绝作为全区间因子或执行基准 |
| `pre_close`、`pre_close_adj` | `close.shift(1)` / `close_adj.shift(1)` | 与上一宽表行一致 | `pre_close` **不是**除权日交易所昨收；不能用于涨跌停价或公司行动推断 |
| `next_open`、`next_open_adj` | `open.shift(-1)` / `open_adj.shift(-1)`，T+1 值 | 生产代码第 625/633 行 | 只可在隔离的成熟标签/执行核验中使用；**禁止因子输入** |
| `turnover` | daily_basic 换手率，float64、百分数 | 字段存在，历史覆盖/时点未独立认证 | 待认证，不进入当前探索性白名单 |
| `total_mkt_cap`、`float_mkt_cap` | daily_basic 总/流通市值，float64、万元 | 生产字段映射可见；近期 CSV 市值单位另有换算 | 历史发布时间、股本事件未验，不能做已认证中性化或交易资格判断 |
| `is_valid_trading` | 生产方布尔状态 | 冻结前基本等于“有收盘价”；尾部约 93 日冻结 | 不是可靠的可成交状态；正式回测拒绝 |
| `is_valid_suspension` | 60 日冷却等规则参与的资格布尔量 | 冻结前有 293,798 个 `false` 但仍有收盘价；尾部冻结 | 不能等同于交易所真实停牌；正式回测拒绝 |
| `is_valid_list` | 上市资格布尔量 | 冻结前有 224,592 个有收盘而标记未上市；尾部冻结 | 不能用来修复历史股票池；正式回测拒绝 |
| `is_valid_not_st` | 非 ST 布尔量 | 历史 PIT 未证明、尾部约 94 日冻结 | 不能作为正式历史 ST 过滤器 |
| `sw_industry_class` | 申万行业标签，object | 生产方可能前向填充，历史时点未认证 | 不能据此声称历史行业中性化可靠 |

**Perry EOD 差异。** `open/high/low/close` 为原始元/股，重叠 close 与宽表一致；`vol` 为**股**、`amount` 为**元**。`trade_status=false` 同时仍带 close 的单元 511,856 个，说明填价与交易状态不能混淆；`limit_up_price` 计算值低于实际 close 的单元 13,079 个，拒绝用作交易所涨停约束。`ST`、`limit_status`、`minute_*`、18 项 moneyflow 的历史语义/到达时间均未完整认证。EOD 文件本身当前不开放给 Agent，详见访问合同。

**来源与等级。** 机器可读字段记录在 `../schemas/field_dictionary.v1.json`（原内部附件未公开），含 dtype、单位、生成链、时间、证据及标记。其 `VERIFIED` 仅指对应**数值关系**已核实，不能自动提升为整段 `RESEARCH_READY` 或 `BACKTEST_APPROVED`。当前整体认证：原始六字段属于 `PROFILED_EXPLORATORY_ONLY` 数据候选，但独立 Train/Validation 快照尚未发布；复权与状态字段为 `PARTIAL/REJECTED`；正式回测准入为 **BLOCKED**。证据来自 `daily_update_checks.json`、`cross_source_checks.json`、`pit_checks.json`、`real_sample_run.json` 与只读生产者快照。
