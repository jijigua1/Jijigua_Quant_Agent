> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-A 证据索引与复核范围

本次交接只读复核了本工作区已有材料，**未重新登录 GPUShare 执行全量审计**。下列服务器结论是 Claude 留存的只读调查文件与源码快照所支持；对运行 UID、服务器现时文件是否变化及原始文件哈希的再次现场比对均未独立复核。证据来源与推断层级见各报告正文。

| 证据（相对此文件） | 对应事实/检查 | 本次复核 |
|---|---|---|
| `../survey/results/daily_update_static_meta.json`（原内部附件未公开） | 宽表 1,882 日、5,427 代码、字段文件大小/哈希/类型/覆盖 | 解析结构、close 年计数、字段列表；未重新读取原始 PKL |
| `../survey/results/daily_update_checks.json`（原内部附件未公开） | OHLC、价量、单位、复权、状态与股票池统计 | 核对统计键及关键数值 |
| `../survey/results/calendar_check.json`（原内部附件未公开） | 宽表与 SSE/SZSE 日历在样本区间各 1,882 日一致 | 与较早脚本的 Int64Index 失败区分 |
| `../survey/results/eod_skeleton_research_perry.json`（原内部附件未公开） | EOD 顶层 dict、134 字段 | 只核对静态结果；不再次解析 9.99 GB 源文件 |
| `../survey/results/eod_copies_cmp.txt`（原内部附件未公开） | 两处 EOD 文件字节比较为 IDENTICAL | 不把两份路径当独立数据源 |
| `../survey/results/cross_source_checks.json`（原内部附件未公开） | EOD 2,583 日、5,878 代码；原始 close、单位、状态/涨停、股票池对照 | 核对主要计数；同源交叉核对不能证明独立准确性 |
| `../survey/results/pit_checks.json`（原内部附件未公开） | 复权历史修订、上市前日期、字段逐年覆盖 | 核对计数和异常样本 |
| `../survey/results/hfq_revision_probe.json`（原内部附件未公开）、`../survey/results/backfill_log_excerpt.txt`（原内部附件未公开） | 历史复权不只是常数比例重基；2026-08 前后有重建日志 | 只能说“与重建日志相符”，不能证明全部变化原因 |
| `../survey/results/real_sample_run.json`（原内部附件未公开） | 2020+ 8 字段真实静态读、五类拒绝、上市/复权/状态失败 | 核对审计结果与 `survey/real_sample_run.py`；未得到独立 UID/GID 记录 |
| `../survey/results/csv_axis_profile.json`（原内部附件未公开） | 三份近期 CSV 覆盖、列与行数 | 只作为近端格式/单位证据 |
| `../survey/results/source_and_asset_search.txt`（原内部附件未公开） | 有界、按名字的其它数据候选定位 | 不认证名单上的第三方/其他研究者数据 |

只读生产者快照：`survey/server_sources/home__updates__daily__eod_factor_update.py.readonly.txt`（主宽表、复权、VWAP、未来 shift 和状态更新）；`survey/server_sources/home__real_time_product__update_data__auto_update_csv.py.readonly.txt`（Tushare CSV、单位与 ST/涨跌停估计）；`survey/server_sources/home__real_time_product__update_data__publish_tushare.py.readonly.txt`（发布规则）。这些是检查用快照，**不是本次运行的生产代码**；不能因源码含“修复”逻辑就覆盖真实文件的冻结异常。

代码复核：`qra_data/static_pickle.py`、`adapter.py`、`contracts.py`、`validators.py`、`synthetic.py`、`survey/real_sample_run.py`；已有 `tests/test_static_pickle.py`、`test_adapter.py`、`test_validators.py`。新增 `qra_data/splits.py`、`schemas/daily_update_manifest.v2.json`、`schemas/data_split_contract.v1.json`、`tests/test_splits.py`，仅在 `phase3a_data` 内。本次没有改动 `<ARCHIVE_ROOT>\src`、主 Agent v0.6.8、生产数据或服务器账户。

关键文件内容哈希（SHA-256，**本地证据文件**）：

```text
schemas/daily_update_manifest.v1.json  05071ed6fbffb3423eab97cb5f7ad2075bedade9ac5351781ba640dae6e62c5e
schemas/daily_update_manifest.v2.json  f3cafc2b4d0b3d40f7c01563da941307b22dc559c2975bbf826fc776832508b0
schemas/field_dictionary.v1.json       d210c03fe66d31cad3cba94f1ac4d5e6020a0741b5d6e4b8a2c13a554d6e0c53
schemas/data_split_contract.v1.json    4898aaeb246dcd19362a2d1d5b85810f47e991889fc05ee8a1d1beb908be7b31
survey/results/daily_update_checks.json b9440bf48c4e5dda6deed8569b5a18ac2c4f6659e0589adbb82cb775cb7ed942
survey/results/cross_source_checks.json fc877563853e0ec7a1c6e723674bdf86e087d24b717e83b0ab8c94df3f9559bc
survey/results/pit_checks.json          c84bf311b5ab13799af36469d72d7f37a640e6bfd5f446a930a357a1734be94a
survey/results/real_sample_run.json     32452fa0f344844e97f4ffdba11ad217e55878bdcc8e720c31920fac198e00db
```

服务器**原始**各行情文件 SHA-256、字节数见保留的 v1 与只调整认证等级的 v2 清单；本地证据文件哈希不是原始行情指纹。EOD 两份大小及 IDENTICAL 比对见证据文本，本次未计算新的 EOD SHA。关于 Phase 3-A 的测试命令、通过/跳过见 [`TEST_RESULTS.md`](data-audit__TEST_RESULTS.md)。
