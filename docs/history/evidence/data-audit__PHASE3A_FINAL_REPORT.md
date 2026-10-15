> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-A 最终认证报告

**交付状态：Phase 3-A 独立数据调查与合同收尾完成；主 Agent v0.6.8 未修改/部署。正式回测数据准入：BLOCKED。最终 Holdout 系统级隔离：尚未实现。** 审计截至 2026-10-12，版本 `qra-data-contract/1.0.0`、`qra-data-adapter/1.0.0`、新增分区原型 `qra-split/1.0.0`。这是对 Claude 工作区证据的接手复核与最小补齐，不是重新开展全量服务器调查。

## 1. 已接收范围与认证结论

实际工作区 `<ARCHIVE_ROOT>\phase3a_data` 含 `qra_data/` 静态 PKL 解码、数据合同、适配器、验证器及合成数据，`schemas/` 旧 manifest/机器字段字典，`tests/` 旧测试，`survey/` 调查脚本、只读生产者快照及 `results/` 的 12 份证据。接手时 `docs/` 为空，缺最终字段解释、分区合同、访问约束与报告；本次补齐七份要求的报告/合同、一份证据索引、一份测试记录、v2 降级清单及独立分区原型。

**长期因子研究的数据候选是**：`daily_update` 2020–2025 区间内、按文件 SHA 固定的 `open/high/low/close/volume/amount` 六个原始日频字段，限沪深固定 5,427 代码轴。只有独立发布 Train/Validation 快照后，才能通过新分区接口作为**探索性**量价特征输入；T 日完整行情只在 T 收盘后使用，需排除已识别上市前数据并明确样本缺口。时间覆盖足够，但“长期”不代表历史时点和交易可执行性已认证；跨除权日的原始价格收益不能直接当作经济收益。复权 `adj_factor/close_adj` 可作为有版本限定的敏感性分析候选，不能替代 PIT 公司行动合同。EOD 更早（2016 起）却止于 2026-08-20，当前仅作静态交叉核验，不作为 Agent 公开工具或独立来源。

**存在高风险的字段/机制**：`is_valid_list/is_valid_suspension/is_valid_trading/is_valid_not_st` 有错误语义或尾部冻结；EOD `trade_status` 带填价、`limit_up_price` 出现价格越界；历史 ST/行业/市值时点未证明；`next_open` 是未来字段；独立 VWAP 停更；复权快照历史重写；上市前回填和固定股票轴缺漏。数值通过与可交易时点可信是不同等级。数据口径、风险计数和证据见 [`DATA_QUALITY_REPORT.md`](data-audit__DATA_QUALITY_REPORT.md) 与 [`FIELD_DICTIONARY.md`](data-audit__FIELD_DICTIONARY.md)。

## 2. 数据链与安全复核

主行情宽表 1,882 交易日、5,427 代码；实际 8 字段核验覆盖 2020-01-02—2026-10-09 共 1,638 日。原始 OHLCV 在核验单元内通过轴/范围/单位/日历检查；**上市边界失败 1,228 单元、复权因子实质下降 5 单元、尾部状态冻结约 93/94 日、旧新复权历史改变百万单元**。Perry EOD 134 字段、2,583 日、5,878 代码；两份 9.99 GB 文件字节一致，与宽表原始 close 重叠 8,518,112 对相等，不能作为第二独立价格源。生产者链审查支持 Tushare daily/basic/adj_factor 和派生字段的解释，但缺逐日历史发布时间证明。

静态解析器不调用 pickle 中的任意函数，合成恶意对象测试拒绝；主宽表适配器验证路径、大小、SHA、资源/字段/用途、预算和安全语义。**尚未通过安全认证的是**：大型 EOD 在 `pickletools.genops` 中大块先物化，不能保证峰值内存有界；调查结果没有进程 UID/GID 证据，不能证明所有真实解析都由 nobody 执行；部分辅助 CSV 由核验脚本直接打开。EOD 动态读取保持 `BLOCKED`，不能用 root 解析未知 pickle。安全边界详情见 [`DATA_ACCESS_CONTRACT.md`](data-audit__DATA_ACCESS_CONTRACT.md)。

## 3. Train / Validation / Holdout

Train：2020–2023（970 个观测日）；Validation：2024–2025（485 日）；Final Holdout：2026-01-01—2026-10-09（183 日）。新增分区版本化 Schema、`SplitReader` 合成原型。**三分区均未发布独立快照，因此交付的真实源清单不允许任何研究侧分区读取。** 合成测试证明：将来发布独立 Train/Validation 资源后，接口可只读六个原始字段；Holdout、跨分区、未来和状态字段在底层读取前拒绝，标签成熟函数阻止持有期/embargo 跨界。旧适配器会先把整份含 2026 数据的 PKL 读进内存，不能只靠日期切片实现严格隔离。主 Agent v0.6.8 未注册新资源，现有整体环境仍可能绕过原型读取 2026 文件，故“Train/Validation/Test 是否实现实际访问隔离”的答案为 **否**。发布分区快照、独立评估身份和旁路验收前，2026 Holdout 不应开放给模型，也不应用它调试 IC、目标收益或策略表现。详见 [`DATA_SPLIT_CONTRACT.md`](data-audit__DATA_SPLIT_CONTRACT.md)。

## 4. 测试、失败项与下一阶段边界

本地合成测试验证静态 pickle 拒绝、适配器权限/预算/哈希、上市/停牌/复权/时点验证器，以及新增的分区、审计、标签成熟和 Holdout 拒绝。历史真实证据中适配器拒绝 backtest、未来字段、状态字段、范围与超预算；真实数据自身的上市、复权、状态检查不通过，**不得把测试代码通过混同数据质量通过**。完整执行结果见 [`TEST_RESULTS.md`](data-audit__TEST_RESULTS.md)。本次没有重新运行服务器真实数据读取、没有接入 DeepSeek、没有执行真实回测。

Phase 3-B 现在可做合成交易账本验收、探索性因子数据适配、独立发布/准入设计；不能上线合格交易回测、声称真实账户收益或打开最终 Holdout。欠缺的时点数据、真实交易状态、公司行动、完整股票池、权限边界和回测引擎联合验收列于 [`PHASE3B_PREREQUISITES.md`](data-audit__PHASE3B_PREREQUISITES.md)。Phase 3-B **本轮未启动**。

项目资产总表见 [`DATA_INVENTORY.md`](data-audit__DATA_INVENTORY.md)，源文件指纹与可追溯索引见 [`EVIDENCE_INDEX.md`](data-audit__EVIDENCE_INDEX.md)。旧 `daily_update_manifest.v1.json` 保留原貌；新增 `v2` 已将核心数据降为 `PROFILED` 并列明失败条件。新合同不授予正式研究或回测认证。
