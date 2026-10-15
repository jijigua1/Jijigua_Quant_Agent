> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 最终验收盲测集（2026-10-14 冻结）

规则：

- 以下文件在开发期间**不打开、不读取内容、不放入开发调试**，只登记路径与 SHA-256 前 16 位。
- 最终验收时上传到预发布论文库，由真实 DeepSeek 端到端处理。
- 结果按“真实成功 / 正确阻断 / 工程失败”分类，不得删除失败案例。
- 选取依据只有文件名与来源目录，未查看摘要或正文。

| 编号 | 文件（只读来源） | SHA-256 前16位 | 来源说明 |
| --- | --- | --- | --- |
| H01 | `<LOCAL_RESEARCH_ROOT>\策略创建流程化\test_materials\papers\local\greatwall_technical_overlap_20160824.pdf` | 338cad2737e1fb2b | 中文券商研报（长城证券） |
| H02 | `…\xiangcai_etf_trend_20220929.pdf` | 7a317d95a0140f02 | 中文券商研报（湘财，文件名提示 ETF） |
| H03 | `…\hans_optimal_timing_2025.pdf` | 20310b6ecf96b974 | 英文论文 |
| H04 | `D:\Quanttrade\option_research\02_文献研究\核心文献库\Papers\china_CN03.pdf` | 53d5253a4d8207f8 | 中文论文（期权文献库） |
| H05 | `…\china_CN12.pdf` | b3ea1bfa67eaaf66 | 中文论文（期权文献库） |
| H06 | `…\core_CORE04.pdf` | fef477d11de1a059 | 英文论文（期权文献库） |
| H07 | `…\core_CORE09.pdf` | bd62f6bf90a5c15d | 英文论文（期权文献库） |
| H08 | `…\core_CORE17.pdf` | c1137c805bd18c64 | 英文论文（期权文献库） |
| H09 | `…\ml_ML03.pdf` | 5edb8ed67b41ff1c | 英文论文（期权文献库） |
| H10 | `…\ROOT08.pdf` | 3a9baee8f1776b88 | 英文论文（期权文献库） |

开发与回归集（允许读取和调试）：预发布库已有的 9 篇，即 GH、Amihud、MA（与 1907.00212 为同一文件）、1110.3383、MACD 2206.12282、cond-mat 0212641、华泰月报、AQR、Heston。

说明：Quanttrade 目录属于 Codex 项目，只读取、不修改；文件将复制到预发布论文库后使用。
