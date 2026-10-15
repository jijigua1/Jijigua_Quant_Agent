> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2-A 交付报告

2026-10-12 后续收尾证据：[`PHASE3B2A_SECURITY_CLOSEOUT.md`](release__PHASE3B2A_SECURITY_CLOSEOUT.md)、[`LISTING_DATE_AUDIT.md`](release__LISTING_DATE_AUDIT.md)；第三方模型网关独立验收见 [`NEW_API_COMPATIBILITY_REPORT.md`](release__NEW_API_COMPATIBILITY_REPORT.md)。后续完成的是**合成** Linux 发布验收，不改变下述“真实快照未发布”结论。

**结论：真实 daily_update 六文件版本已在 GPUShare 做有界只读核验；独立发布与读取原型、合成拒绝/修订测试完成。获批的 `quantpub` 身份与空发布目录已创建并做权限验收。Train/Validation 真实快照、Daily Worker、最终测试评估器和主 Agent 集成均未部署。正式真实账户回测继续 `BLOCKED`。** 冻结的 Research Agent v0.6.8 和 GeorgeResearch 未修改。

## 交付与证据

- 源码：`release.py`（原内部附件未公开），版本 `qra-release/0.1.1`，SHA-256 `e2811a1c54804c7e37ca5cb43176a197119c8f0508d7c9c8ee809b4372956777`。固定六字段读取指纹，通过 Phase 3-A 静态读取器接收固定 Train/Validation 分区，复用质量验证器，发布不可覆盖的基线/增量与 SHA 核验读取；合成 PKL 已验证从静态读取到分区发布的完整接口。本地原型把最终版本目录设为 `0750`、文件设为 `0640`，Linux 实际发布权限仍待验收。Holdout 没有研究读取入口。Daily Inference 仅有冻结模型/日期/窗口输入原型。
- 真实服务器证据：`server_readonly_20261012.json`（原内部附件未公开） 与 `server_permissions_20261012.json`（原内部附件未公开）。六个各 81,837,746 字节的源文件 SHA 与 Phase 3-A 清单完全一致，故已有静态解码的真实内容末日仍为 **2026-10-09**；截至服务器 10-12 17:40 没有新发布交易日。`quantagent` 无法读原始 PKL。现有生产者源码与此前快照 SHA 亦一致。没有读取 Holdout 研究表现。
- 方法、质量与分区详见本目录其余八份合同/报告；Phase 3-A 原始证据索引为 [`EVIDENCE_INDEX.md`](data-audit__EVIDENCE_INDEX.md)。本轮不做昂贵全量扫描或复制。
- 测试：[`TEST_RESULTS.md`](release__TEST_RESULTS.md)。合成基线/增量、历史版本、坏哈希、半更新、日期越界、未来字段、上市前、单位、预算及 Daily 窗口均经本地程序验证；不把测试通过当真实市场发布成功。

## 能力状态

| 能力 | 状态 |
|---|---|
| 六源文件真实指纹与最近**已核验**交易日 | **已核验**，当前与 Phase 3-A 同版至 2026-10-09 |
| 六字段静态质量/单位、重大缺陷 | **已有真实审计证据**；本轮沿同一 SHA 复用，上市/状态/PIT 缺陷未解除 |
| 源变更/混版识别、分区/增量发布、只读版本读取 | **本地独立原型，合成测试通过** |
| Train/Validation 实物快照与 Agent 查询 | 空目录已建；**真实快照未批准、未发布、未注册** |
| Holdout 文件系统/进程级隔离与独立评估入口 | **未完成**；`quantagent` 原始文件读取被 OS 拒绝是局部证据 |
| 最新日因子信号、自动日更 | **未实现真实通道**；2026-10-12 行情未在此次核验中出现 |
| 正式真实账户回测 | **BLOCKED**：交易状态、公司行动、PIT、股票池、分区与引擎合同仍不足 |

## 下一步准入

[`SERVER_RELEASE_APPROVAL_PLAN.md`](release__SERVER_RELEASE_APPROVAL_PLAN.md) 的身份/目录第 1–2 项已获批执行；下一步实现受限非 root 源解析与上市日期合同，另行审批真实数据发布范围；发布真实 Train/Validation 后方可考虑让主 Agent 注册新资源。每日 Worker 和最终评估器需独立验收。原始更新程序不改、不重抓数据，研究旧记录不迁移。`/hy-tmp` 临时盘上的重要版本须另存持久备份。
