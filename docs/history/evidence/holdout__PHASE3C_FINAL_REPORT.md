> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 实际交付与恢复核验

日期：2026-10-13（Asia/Shanghai）。生产主Agent仍为v0.8.0。

## 结论

**真实Test发布、一次评价、独立数值复核及同一研究revision2归档已完成。CLI验收部分通过，不能标记整项 `REAL_HOLDOUT_EVALUATOR_ACCEPTED`。**

本轮按用户“批准仅恢复核验与报告”执行，没有再次调用评价器，没有增加测试预算。普通中文首次查询仍可能复述旧会话SEALED缓存；明确要求调用已授权读取工具后，真实DeepSeek成功读取revision2，但下一轮对10月N/A的原因解释错误。记录保留，未修改生产代码消除这一问题。

## 同一研究与实际成果

- study_id：`INTERNAL_RUN_ID_REDACTED:1339576f3486425d`。
- evaluation_id：`INTERNAL_RUN_ID_REDACTED`。
- 固定定义：`-returns(close,5)`，raw，方向+1，H=5，执行延迟1，五分组。
- 定义SHA：`f330895906745ee174b8e6dd5e7314f955fabb92728629ae6c889f1bde7e2995`。
- 原研究：`/srv/jijigua-quant-agent/research_runs/2026-10-13/01-33-21_reversal_5d/`。
- 新综合报告：`/srv/jijigua-quant-agent/research_runs/2026-10-13/06-54-19_report_revision_2/reports/report.html`。
- Markdown位于同一reports目录。原PKL仍在原研究data目录，仅包含Train/Validation因子值。
- revision2 manifest SHA：`322d5e5f8d2ca8a79050119d975477a808bd2a49409244590f168aa1cc18df14`。

原89个登记文件均保留正确SHA，报告索引的旧版另存history，原manifest保存为`reports/history/manifest_revision_1.json`。生产92个源码文件SHA均与前置检查一致。会话正常新增查询记录，旧实验未修改。

## 真实统计结果

| 分区 | 范围 | IC均值 | RankIC均值 | 有效评价日 |
|---|---|---:|---:|---:|
| Train | 2020-01-02—2023-12-29 | 0.020367376934 | 0.026380421612 | 959 |
| Validation | 2024-01-02—2025-12-31 | 0.043337659475 | 0.046300839332 | 479 |
| Test | 2026-01-05—2026-10-09 | -0.000863362188 | 0.004014245450 | 177 |

Test观察日183，预置2025年暖机120日，固定证券轴5427。按实际观察索引复算：最后成熟信号2026-09-23，入场2026-09-24，退出2026-10-09。末端六个信号日未成熟：09-24、09-28、09-29、09-30、10-08、10-09。10月两个观察日均无成熟标签，因此月度IC/RankIC是N/A，不能填0，也没有补入更晚数据。这里使用经过审查的观察索引，尚未认证为权威交易所日历。

Test RankIC HAC95%区间为[-0.034185158189, 0.042213649089]，p约0.8368，包含0。IC区间也包含0。IR未年化，带宽4。Test方向与强度没有提供可靠的预测证据，结论`NEEDS_MORE_EVIDENCE`。这是已存在历史曝光的回顾性2026统计评价，不是真正未见的前瞻盲测，不是交易有效性认证。

## 独立数值与文件核验

quanteval读取同一私有快照，使用独立NumPy平均秩及相关基准复核183日，177个有效日，年度/月度及空值一致，容差1e-12。本地只接收获批的聚合证据，再用标准库均值、自协方差和Bartlett权重独立复算HAC、年度/月度；168个IC/RankIC热力图单元格与CSV一致。Train/Validation旧统计对象完全未变。

测试回执HMAC在独立环境验证。原私有回执文件SHA为`9c6ae94aa6f037e0a30060a07e49a2c2a1a376dad41d74083f12d7104a843176`；公开报告中格式化的签名JSON文件SHA为`f8d8da4d2f79fe097937a966258e2e71a973e22a999f416cff6187c4b16e89ca`。两者序列化字节不同，签名结果对象相同；未下载签名密钥。

## 权限与审计

- quanteval：uid997/gid996，nologin，无附加组。只读取本次获准私有快照与暖机。
- 私有快照：`/srv/jijigua-quant-agent/data_releases/test_private/test_20261009_a864dc33_v1/`，目录root:quanteval 0750，文件0440。
- 独立环境：`/srv/jijigua-quant-agent/test_evaluator/phase3c_v1/`，NumPy1.26.4、Pandas2.3.3、Matplotlib3.8.4、jsonschema4.19.2。
- 实际OS探测：quantagent不能打开六个原始PKL、六个私有矩阵、私有账本/回执/签名材料及root审计文件。没有注册普通2026资源。
- root只受控打开固定源FD，数据静态解码降权quantpub；计算/复核/报告在quanteval执行。有限管理员控制器负责批准校验与归档，没有root常驻Agent。
- 内存4GiB、CPU120秒、文件512MiB、核心转储禁止、固定任务范围及超时保持原合同。不是宿主级生产沙箱认证。
- 评价尝试1，剩余0；失败、私有结果曝光、核验恢复、报告提交和模型聚合读取分别记录。root审计hash-chain最终SHA：`92b755c8dcc5826809136fde0b4f7328f531a3e86247f9e4dcc93b4ff978856c9`。
- 审计文件对低权限身份不可改删；root仍是可信管理员。未声称平台级WORM或永不丢失存储。

## 本次修复与真实性能

只更改独立`verify_once.py`空值比较：n=0均值N/A，n<2样本标准差N/A。旧文件/配置保留root审计备份，批准SHA从`369a0e55799ecf3e3618c3982ce2dbfdd356098aeaf8fa7be767d30136bdfc34`更新为`92e01b216de3a3d5de3f9b70133bc37c02f68efbdb09f8c2710245f864e26993`。

| 步骤 | 实测秒数 |
|---|---:|
| 原一次Test读取 | 0.2685 |
| 因子计算 | 0.0724 |
| IC/RankIC等计算 | 1.7905 |
| 年度/月度 | 0.0166 |
| 批准后的独立复核 | 0.7142 |
| 报告生成 | 12.9011 |
| 核验与报告后处理总计 | 14.4345 |

评价峰值RSS约291MiB；报告约487MiB。上述步骤分两次批准执行，不应相加伪称单条CLI完整耗时。没有重新计算Train/Validation矩阵。

## 真实官方DeepSeek CLI与未完成项

官方Provider、Key输入方式和root启动器未改。实际SSH PTY恢复原会话：

`quant-agent chat --resume INTERNAL_RUN_ID_REDACTED`

查询“调用已授权的读取研究结果工具，刷新本会话五日反转的最新指标。仅查询，不重新计算、不提交新测试。”实际执行1次`qrtk_read_study`，读取成功，三阶段数字和revision2路径正确；该工具任务报告24888 tokens、unknown_calls=0。此前两组自然查询未调用工具，仍复述旧SEALED，失败记录保留。

后续“10月为什么没有有效IC”错误声称缺月度数据，并混用旧测试申请READY状态。这项解释验收不通过，不能以任务状态COMPLETED代替语义通过。需要后续另行批准主Agent的缓存刷新及证据摘要修复；本次未改冻结生产代码，也不再追加API重试。

报告主要表格、2026年/月与热力图正确。仍存在历史Train/Validation范围说明“2026未发布”与独立Test段落并列的旧措辞；主研究资源确实没有2026权限，但应在后续报告版本明确限定该句范围。部分分布/衰减诊断只有Train/Validation；本次Test仅批准固定H=5，不能补做其它预测期。

## 用户新增的连续图展示要求

本地预览：`evidence/continuous_report_preview/v2/report.html`。

所有已存在日期轴图（IC、RankIC、累计相关、分组累计和、覆盖率）统一两条竖线，跨分区延续累计值；PNG/SVG/PDF打印版本同步。缺失数值仍N/A，连接线仅用于连续展示，未修改分区统计或标签。非日期轴图继续按其分组/预测期/数值坐标展示，不能把日期分隔线放到不同含义的横轴上。

当前签名回执未返回Test逐日五组收益，故分组累计图只能显示至Validation，不能凭年度均值生成Test曲线。预览未写入服务器、未覆盖revision2、未修改主Agent；新图表规范若用于未来生产报告，需要单独批准生成器变更。

## 证据入口与后续边界

详见`TEST_RESULTS.md`。原失败报告、旧截图、回执和hash均保留。已有发布源与Train/Validation不变；官方API、其他研究员代码、生产任务未改。正式账户回测继续BLOCKED；没有额外因子测试许可、自动参数搜索或Holdout普通读接口。

`/hy-tmp`为临时存储，需备份重要成果。本地保存获准聚合报告和核验证据，不含私有2026行情矩阵、收益标签、Test因子矩阵或签名密钥；不自动上传外部平台。
