> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-B 最小新增目录申请

只读检查确认 `/srv/jijigua-quant-agent/integration_tests/phase2b` 不存在。
`research_runs` 已获授权且可写；本申请只新增一个测试成果目录：

```python
from pathlib import Path
import os
p = Path('/srv/jijigua-quant-agent/integration_tests/phase2b')
assert not p.exists() and not p.is_symlink()
p.mkdir(mode=0o700)
os.chown(p, 999, 999)  # 已有 quantagent UID/GID
```

不更改父目录权限、已有 Phase 2-A 成果、任何数据或其他项目。
后续 quantagent 在此目录创建独立 UUID 子目录并写入测试记录；不覆盖历史文件。
恢复方式：如尚未使用，可以删除这个空目录；已有成果时保留，不自动删除。
当前挂载 XFS，空闲约 73.8 GiB。单次研究文件总量限 20 MiB（应用校验，非磁盘硬配额）。
