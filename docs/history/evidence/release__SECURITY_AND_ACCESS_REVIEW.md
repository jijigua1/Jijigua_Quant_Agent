> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 权限与旁路审查

**当前已验证**：六个原始 PKL 为 `root:root 0600`；Linux 上 `runuser -u quantagent -- test -r .../close.pkl` 返回不可读。经用户单独批准已创建 `quantpub`/`quantdata` 与五个空目录；`quantagent` 可读但不可写 Train 目录、不可读 `daily_private`，`quantpub` 可写 Train 且不可进入主 Agent 目录。实测身份及 mode 见 `server_permissions_20261012.json`（原内部附件未公开）。冻结 Agent v0.6.8 未注册长期行情资源。本地 `release.py` 对发布 ID/分区/字段/预算、符号链接文件、SHA、父版本和源文件变化做拒绝；未知 `next_open`/状态字段不能混入发布面板。以上不是正式沙箱或已发布数据的证明。

**尚无的边界**：发布者的受限 FD broker/作业程序、独立评估者和 Daily Worker 身份；Train/Validation 真实文件及最终 ACL；独立 Holdout FD/进程访问；持久审计存储；模型/工具全路径旁路枚举；root 人员操作隔离。不能把 Phase 3-A `SplitReader` 的软件拒绝说成物理封存。研究进程应只读已发布数据目录并仅写自己的任务结果；发布进程可读白名单原始文件但不能被模型调用；Holdout 评估身份只由审批入口使用。root SSH 人员仍有管理能力，须单独审计和约定盲测纪律。

需要实际验证的攻击路径：直接完整 PKL、symlink/路径穿越、硬链接、原始 FD 继承、导出缓存、预计算 2026 标签、报告/日志/模型上下文泄漏、反复查询最终评分、Daily Worker 暖机结果泄露、发布版本替换或父链篡改。Tool 参数只能是已注册资源 ID、日期、字段、预算，不得让模型传任意绝对路径、任意 Python/Shell 或发布状态。秘密与模型凭据不进入数据发布进程或日志。

原始 PKL 的静态解析沿用 Phase 3-A `qra_data.static_pickle` 的受限格式，并且**在降权、资源受控进程中**进行；本项目源码没有任何 `pickle.load/read_pickle`。该静态解码器对 9.99GB EOD 的大字节 opcode 内存边界未认证，所以 EOD 不在发布范围。发布后 `.npy` 读取使用 `allow_pickle=False`、尺寸与哈希检查。未知 pickle、上市时点和交易状态全部 fail closed。
