> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2-A 安全发布通道收尾（2026-10-12）

**结论：受控发布器源码与 Linux 合成权限验收完成；真实 Train/Validation 未发布。** 本文是 [`PHASE3B2A_FINAL_REPORT.md`](release__PHASE3B2A_FINAL_REPORT.md) 的后续补证，不改变已冻结的主 Agent v0.6.8。

## 已完成的最小实现

`linux_publisher.py`（原内部附件未公开） SHA-256 `589acc1c7b87e4a43d14c4c86438c833ef7f36f74777419ac34a35317cbcf939`：可信入口仅允许固定六字段和 Train/Validation；root 仅白名单只读打开，检查单链接常规文件、大小、SHA、inode、mtime、六字段更新时间差；子进程降为 `quantpub`，只继承已固定 FD，使用 Phase 3-A 静态解码器与原有质量闸门，设置 CPU/内存/文件/打开 FD/运行时间限额。输出沿用独立 `release.py`（原内部附件未公开） 的不可覆盖版本与哈希清单。它不是 Agent Tool，也没有运行真实原始 PKL。源码含真实路径白名单，合成路径仅允许固定 `/tmp/qra-b2a-synth-*` 范围。

GPUShare 上用**合成**三日期行情和临时文件测试：2020 Train、2024 Validation 可由 `quantagent` 读发布结果，2026 Holdout 未发布；`quantagent` 对原始合成 PKL、staging/daily_private、写入发布结果均被 OS 拒绝；符号链接、硬链接源被拒绝；发布文件为 `quantpub:quantdata 0640`，版本目录 `0750`；测试临时文件已清理。结构化结果见 `linux_synthetic_evidence.json`（原内部附件未公开）。服务器正式发布目录检查为 **0 个文件**，本次没有真实行情批次。

这项进程降权与 RLIMIT 是**受限开发执行**，并非完整安全沙箱：现有 Docker/cgroup 条件下未证明整个后代作业树的硬资源限制，未建立无网络命名空间、seccomp 或独立实例。发布器由可信管理员固定参数调用，不能暴露给模型。失败时原始文件不动；测试临时目录清理后无生产发布物。

## 准入状态与下一动作

| 条件 | 当前状态 |
|---|---|
| `quantpub`/`quantdata`、五个空目录 | 先前已获批且实测；不重复创建 |
| 六字段来源 SHA、最近数据日 | 只读实测与 Phase 3-A 清单同版，实际截至 2026-10-09；尚无更新批次 |
| 白名单 FD、降权解析、Linux 合成权限拒绝 | 已在隔离的临时合成样本通过，未部署长期运行发布服务 |
| 上市日期可信合同 | **BLOCKED**，见 [`LISTING_DATE_AUDIT.md`](release__LISTING_DATE_AUDIT.md) |
| 真实 Train/Validation 发布 | **未获本轮批准、未执行**，仍需单独批准具体字段/年份/批次/备份 |
| Holdout 独立评估身份及真实物理隔离 | **未建立**；只证明 `quantagent` 当前读不到原始文件 |
| Daily Inference 与最新信号 | 合同与本地原型；无实际发布视图或 Worker |
| 主 Agent 注册 / 正式回测 | **未做 / BLOCKED** |

下一次申请只需覆盖：上市日期合同的可信来源或排除方案，六字段固定源哈希与一次 2020–2025 Train/Validation 发布，发布批次的权限、质量与版本核对，以及持久备份位置。Holdout 评估身份、定时任务、主 Agent 资源注册与正式回测需分别审批；不得把本次合成验收当作真实发布授权。
