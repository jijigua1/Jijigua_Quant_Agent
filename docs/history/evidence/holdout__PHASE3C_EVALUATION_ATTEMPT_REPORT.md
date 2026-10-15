> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 真实发布及一次评价执行报告

状态：**BLOCKED_INDEPENDENT_VERIFICATION**。真实私有发布及一次评价已发生；独立复算中断，尚未达到REAL_HOLDOUT_EVALUATOR_ACCEPTED。遵守一次预算，不重跑IndependentEvaluator.evaluate。

## 1. 已完成的真实操作

- 只修复已获准的runuser绝对定位；旧控制器和两个批准配置保存于root审计目录，历史失败记录未删除。
- 沿用已创建quanteval（UID997/GID996/nologin、无补充组），不重复创建身份或venv。
- 独立UID实际确认NumPy1.26.4、Pandas2.3.3、Matplotlib3.8.4、jsonschema4.19.2；低权限临时合成协议通过。
- 固定六源SHA不变，首次发布六字段303×5427的私有快照：120个2025暖机日、183个2026观测日（2026-01-05—10-09）。
- 新快照路径：`/srv/jijigua-quant-agent/data_releases/test_private/test_20261009_a864dc33_v1/`。
- manifest SHA：`c786c5a2f752e8138e59d1b05fb72cdb23c203661e02a91acca4087f776ad3d7`；六NPY逐文件哈希全部核验。
- quantagent实际OS拒绝全部六Test文件、Test manifest、原始六PKL、独立密钥/缓存/账本/审计、staging和daily_private。quanteval拒绝原始六PKL、Train/Validation直接路径、staging/daily_private及root审计。quantpub无法读取已封存Test及评估私有目录。权限未放宽。

## 2. 一次评价及曝光

| 项目 | 实际状态 |
|---|---|
| study_id | INTERNAL_RUN_ID_REDACTED:1339576f3486425d |
| 因子 | 冻结五日反转，raw、H=5、下一观测开盘、5组、方向+1 |
| 定义SHA | f330895906745ee174b8e6dd5e7314f955fabb92728629ae6c889f1bde7e2995 |
| evaluation_id | INTERNAL_RUN_ID_REDACTED |
| 尝试数 / 剩余预算 | 1 / 0 |
| 评价器计算状态 | COMPLETED |
| 独立复算状态 | FAILED：空月份统计的None处理错误 |
| 整体交付状态 | BLOCKED_INDEPENDENT_VERIFICATION |
| Test结果曝光事件 | 1：独立评价器私有结果已产生；未送给DeepSeek或发布综合报告 |
| 评价类型 | retrospective_2026；不声称整个2026是未经接触的盲测 |

签名回执仍在quanteval私有目录，其SHA为 `9c6ae94aa6f037e0a30060a07e49a2c2a1a376dad41d74083f12d7104a843176`。未导出原始Test价格、逐股票因子或标签。尚未通过独立核验，未对模型开放研究统计值。

root审计记录了ATTEMPT_STARTED、PRIVATE_RESULT_EXPOSED、ATTEMPT_FAILED、EVALUATE_FAILED及两份封存账本副本。评价账本有且仅有一行COMPLETED；控制器交付失败与评价结果曝光分别保留，不能清空后伪装未测试。

## 3. 成熟边界及准确故障原因

真实发布日期轴及实际评价结果确认：183个观测日中177个具有成熟标签；首次信号2026-01-05，最后有效信号2026-09-23。最后有效入场09-24，退出10-09。末6个信号日期09-24、09-28、09-29、09-30、10-08、10-09不成熟。

2026-10仅有10-08、10-09两个观测日，IC/RankIC有效日数均0。因此该月均值和样本标准差必须为null/N/A，不能填0。评价器正确保存null；复算器在年度/月度核验阶段直接用浮点数减None，触发TypeError。

代码执行顺序表明此前183日的IC/RankIC对照循环已完成，未触发差异拒绝；但复算器没有写出完整PASSED证明，因此**不能把它当作完成的独立验收**，也不发布相关统计结论。

## 4. 性能（实际已执行部分）

| 模块 | 秒 |
|---|---:|
| 私有数据读取 | 0.2685 |
| 固定因子计算 | 0.0724 |
| IC/RankIC及分组计算 | 1.7905 |
| 年度/月度统计 | 0.0166 |
| 总评价 | 2.1836 |

峰值RSS298188KiB（约291.2MiB）。没有缩短183日观察范围或5427代码轴。复算完整耗时、报告生成、真实CLI以及视觉验收尚未完成，不能给出整链路成功耗时。

## 5. 原系统与历史兼容

- 生产v0.8全部92源码文件指纹未变，官方API及密钥未改。
- 原研究manifest SHA仍为 `5c7141f136b26635b170e4c41c2b0b5de15262b0d4c8d8c9890e0c7250e4599b`。
- 原manifest登记的全部成果逐个哈希未变。原PKL SHA `6d9cc855d43d1af80f068697060a0bd44a8ce113cff4b51a25bc4714ac892a540`。
- 原报告索引仍只有revision1；没有生成或伪造revision2。
- 本轮没有真实DeepSeek请求，不将未核验的Test性能发送给模型。

## 6. 已完成的本地修复及证据

复算器已在本地修正：n=0时均值为None，n<2时样本标准差为None；缺失不能伪装为0；有效数值仍按1e-12容差核对。没有修改评价公式、冻结因子、源数据或结果。

- 新增手算空月份/单点/两点和伪造零值测试4通过。
- 本地独立模块全套29通过（2.40秒）；已有Linux合成25通过，修复尚未在服务器应用或复算。
- `evidence/runuser_repair_actual.json`：已批准定位修复。
- `evidence/pinned_runtime_actual.json` / `pinned_synthetic_actual.json`：独立UID环境与协议验收。
- `evidence/publish_actual.json` / `private_publication_security.json`：真实发布、六文件哈希及OS拒绝。
- `evidence/evaluation_preflight_final.json`：评价前固定SHA、原研究和生产源码核对。
- `evidence/evaluate_actual.json`：不可视为成功的失败输出。
- `evidence/failed_evaluation_evidence.json`：一行评价、一次曝光、零剩余预算及原成果未变证明。
- `evidence/controller_audit_after_attempt.jsonl`：root审计副本；原文件SHA `2e33c0291ffc08d5c9eabc1fab88ef5f3b5f37d3b2ddb21d85451e46036f7be6`。
- `evidence/period_fix_local.xml` / `windows_post_null_fix.xml` / `null_fix_proposal.json`：只在本地的修复及指纹。

后续只恢复已有回执的数值核验和报告合并的申请见 `VERIFICATION_RECOVERY_APPROVAL.md`。不会重跑评价、重发数据或追加测试预算。

数据仍PROFILED_EXPLORATORY_ONLY，上市/PIT、公司行动、交易状态及账户回测资格均未升级。`/hy-tmp`清理风险仍存在；当前只在本地备份非秘密工程与聚合审计证据，私有数据和账本仍在服务器。
