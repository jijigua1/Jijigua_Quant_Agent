> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-A 最小成果目录变更申请

只读检查确认 `/srv/jijigua-quant-agent` 已存在，root:root 0755，已有 data/logs/output/tmp 四个空目录。quantagent 为 uid/gid 999、nologin；目前不能在父目录创建成果。/hy-tmp 为 XFS，容量300 GiB，检查时空闲约73.8 GiB。

申请由管理连接仅新增以下目录，若已存在则先拒绝并核对，不覆盖：

- `/srv/jijigua-quant-agent/integration_tests`（root:quantagent 0750）
- `/srv/jijigua-quant-agent/integration_tests/phase2a`（quantagent:quantagent 0700）
- `/srv/jijigua-quant-agent/research_runs`（quantagent:quantagent 0700）
- `/srv/jijigua-quant-agent/shared_reports`（quantagent:quantagent 0700）

使用 Python Path.mkdir + os.chown + chmod 对上述准确路径逐一操作，先检查所有祖先无符号链接且 resolve 在 `/srv/jijigua-quant-agent` 内。不修改父目录、其原有 data/logs/output/tmp，也不递归修改 /hy-tmp 或其他研究员目录。

运行预算：单任务成果最多20 MiB、最多100文件，初期1个前台计算任务；每个 task_id 独立目录。该预算由固定工具执行校验，不是 cgroup 或磁盘配额。

核心代码、root 管理的配置和发布快照仍在原部署目录；SQLite不迁移。新增成果路径只由可信操作者配置，模型不能提供文件路径。

该存储是平台临时盘，不保证永久：官方规则称停机超过24小时可能删除，迁移不自动复制。暂不设置自动上传、清理或备份任务。

新历史数据发布范围将在实际字段与日期核对后另列精确申请；本申请不授予读取未知 pickle 或其他研究员私有资源的权限。
