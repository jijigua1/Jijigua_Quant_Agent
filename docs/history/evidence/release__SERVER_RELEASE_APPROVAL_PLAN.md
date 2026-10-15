> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 真实服务器发布的分步审批与执行状态

2026-10-12 更新：上市日期候选表仍不能认证，但用户已批准并完成一次六字段隔离探索性发布，精确范围见 [REAL_RELEASE_APPROVAL_20261012.md](release__REAL_RELEASE_APPROVAL_20261012.md)、实际结果见 real_release_20261012.json（原内部附件未公开）。本文件下文保留 Phase 3-B2-A 的历史审批状态，不应用于判断当前批次是否已经发布。

第 1–2 项中的身份、组、目录已由用户于 2026-10-12 明确批准并执行，Linux 实测见 `server_permissions_20261012.json`（原内部附件未公开）。FD broker、真实 Train/Validation 发布和主 Agent 集成仍未执行；第 3–5 项需要另行确认。

后续补充：受控 FD 发布器的**独立源码**已完成并仅在临时合成 Linux 样本上验收，见 [`PHASE3B2A_SECURITY_CLOSEOUT.md`](release__PHASE3B2A_SECURITY_CLOSEOUT.md)。上述“FD broker 未执行”是指**未对真实生产 PKL 执行或部署常驻发布入口**，并非未写原型。上市日期来源仍未认证，真实第 3 项不具备执行条件。

1. **已执行**：在 `/srv/jijigua-quant-agent/` 仅新增 `data_releases/{train,validation,daily_private,staging,audit}`。`data_releases` 为 `root:root 0755`；`train/validation` 为 `quantpub:quantdata 2750`；`daily_private/staging/audit` 为 `quantpub:quantpub 0700`。无其他目录权限变更。本地原型已设置最终版本目录 `0750`、文件 `0640`；真实发布前仍须在独立 Linux 验收实际组继承与 `quantagent` 读取，不能原样声称数据文件已可读取。
2. **身份/组已执行，broker 未执行**：新增不能 SSH 登录、不能 sudo、无 home 的 `quantpub`（UID 998）及 `quantdata`（GID 998），仅让 `quantpub` 与现有 `quantagent` 加入该组。后续白名单 FD broker 需由 root 管理，**只读**打开固定六个 `0600` 源文件，然后在解析前降权到 `quantpub`；运行经固定哈希的静态解码器，并设单进程内存/CPU/文件大小/时间限额。现有 Docker/cgroup 环境不能把这些单进程限制冒充作业树硬沙箱。不得给 `quantagent` 原始目录通用读取权。若平台不允许安全传 FD，仅可在重新审批后对六源文件授 `quantpub` 读取 ACL；本次未执行此备选方案。
3. 待发布程序与权限在合成 Linux 环境验收后，才批准**一次**有界真实发布：六原始字段，Train 2020–2023、Validation 2024–2025，固定当前来源哈希、沪深代码轴；只生成分区 `.npy` 与 manifest，不复制完整原始 PKL，不发布 2026。候选上市日期 `/srv/auxiliary-data/TRD_Co.csv` 实测为 2026-07-14 版本，仅 910,235 字节；须先核对来源、覆盖和错误日期，不能默认作为完整可信名单。缺可信名单时当前发布程序会拒绝。质量失败不交付。
4. 管理员验收 Linux 身份：`quantagent` 只能读 Train/Validation、不能读原始 PKL/Holdout/staging/daily_private；发布者不能登录主 Agent；研究工具只接固定发布目录资源 ID。失败后移除新建发布批次，不碰原始数据。
5. 后续**另案审批**独立 Holdout 评估身份与只读输入、每日受控 Worker、定时任务、主 Agent 资源注册和外部持久备份。当前不创建这些，也不解锁正式回测。

预计单次六字段基线数值约 379MB 加暂存、检查和元数据；`/hy-tmp` 当前余 74GB，但该目录可清理，正式可复现版本必须有用户指定的持久备份目的地。用户目前仅批准并完成身份/空目录；真实批次发布仍待 FD broker、上市日期准入及第 3 项审批。下一次真实更新还需验证日期末端、历史修订、完成标记与多文件一致性。
