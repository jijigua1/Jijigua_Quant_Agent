> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 已批准范围执行记录

状态：**BLOCKED_ENVIRONMENT_PRECHECK**。本轮按“前置检查失败立即停止、不得自动重试”的用户要求停止；不是 REAL_HOLDOUT_EVALUATOR_ACCEPTED。

## 已执行

- 六个原始源文件、上市候选文件、Train/Validation发布manifest、冻结研究及生产92份源码再次核对，均与审批指纹一致。
- 创建quanteval：UID997、GID996、`/usr/sbin/nologin`，无补充组、不加入quantdata。
- 受审112份代码进入 `/srv/jijigua-quant-agent/test_evaluator/phase3c_v1/`；离线依赖复制到独立venv。生产venv及API配置未改变。
- 创建空私有父目录 `/srv/jijigua-quant-agent/data_releases/test_private/`，root:quanteval 0750；尚无2026批次目录。
- 创建root管理的审计目录及哈希链，记录PREPARE_STARTED、PREPARE_COMPLETED和ENVIRONMENT_PRECHECK_FAILED。quantagent/quanteval实际OS读取均拒绝；这些低权限身份不能修改或删除审计目录内的记录。root仍属于可信管理员，不宣称具有平台WORM能力。

## 失败原因及停止点

独立venv版本验收的启动程序使用相对命令`runuser`，同时把PATH收紧为 `/usr/local/bin:/usr/bin:/bin`。服务器实际程序在 `/usr/sbin/runuser`，因此Popen在启动前抛出FileNotFoundError。

这是操作者验收脚本的定位错误，不是数据哈希、身份或因子定义错误。独立运行环境尚未验收，不据此宣称可用。**没有运行publish/evaluate，也没有以工程错误为理由重跑独立测试。**

| 项目 | 实际状态 |
|---|---|
| 私有2026真实数据发布 | NOT_RUN |
| 独立评价次数 | 0；预算仍1 |
| 真实测试结果曝光 | 0 |
| evaluator.sqlite / receipt.json | 尚未创建 |
| 统计独立复算 | NOT_RUN |
| revision2综合报告 | NOT_GENERATED |
| 原研究manifest / HTML / PKL | 没有更新 |
| 生产v0.8源码 | 92文件指纹完全不变 |

逐文件SFTP传输曾由操作者在代码传输阶段主动暂停，改用同一受审文件集合的单个SHA校验包；当时尚无评估身份、数据发布或测试尝试。该传输记录另存，不混为一次统计测试。

## H=5成熟边界

由已核实源日期轴重新按`i+lag+H < n`计算，H=5、lag=1、183个2026观测日：

- 最后有成熟标签的信号：2026-09-23。
- 对应入场观测开盘：2026-09-24。
- 对应退出观测开盘：2026-10-09。
- 未成熟信号：09-24、09-28、09-29、09-30、10-08、10-09。

依据是原文件实际**观测日期轴**及固定源SHA，未按自然日推断，也未计算任何真实收益标签。该轴不等于另行认证的权威交易所日历；真实私有快照尚未发布，发布后仍须再次核对轴。

## 测试与权限证据

- Windows定向25通过；Linux quantpub合成25通过。仅软件工程证据，不是真实2026评价证据。
- 本地启动定位修复后的审计/成熟边界测试2通过；未将修复上传服务器。
- quantagent实际拒绝原始close.pkl、独立密钥和root审计；quanteval实际拒绝原始close.pkl、Train manifest和root审计。
- 完整原始六文件在执行前均已由quantagent身份验证OS拒绝。尚未生成Test文件，因此不能宣称已完成真实Test文件访问拒绝验收。

## 证据索引

- `evidence/execution_preflight.json`：第一次只读核对。
- `evidence/transport_change.json`：传输暂停，测试次数0。
- `evidence/execution_preflight_batch.json`：执行前再次只读核对。
- `evidence/code_upload_actual.json`：112受审文件SHA校验。
- `evidence/prepare_actual.json`：真实身份及环境创建。
- `evidence/stopped_precheck.json`：失败、现有权限及生产/原研究未变证明。
- `evidence/admin_audit_stopped.jsonl`：服务器root审计副本，SHA `82d16cb6f473c03a6f47ae42472348f04e646948d6f5b32a622c02561d1a59fe`。
- `evidence/maturity_index_check.json`：H=5按实际轴复算，无标签计算。
- `evidence/windows_approved.xml` / `linux_synthetic.xml`：25项定向回归。
- `evidence/admin_fix_local.xml` / `proposed_repair.json`：仅本地修复及指纹。

后续精确修复与继续申请见 `PRECHECK_REPAIR_APPROVAL.md`。已创建身份、环境和审计保留，不删除、不反复创建。不自动执行回滚、不清除失败记录。

尚未检查真实Test指标、报告视觉或真实CLI结果，因为真实发布和评价均未执行。正式回测仍BLOCKED；数据资格仍PROFILED_EXPLORATORY_ONLY。`/hy-tmp`存在实例清理风险，当前只备份本地审批和非秘密聚合工程证据。
