> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-A 测试与认证记录

## 本次本地执行

环境：Windows，`<ARCHIVE_ROOT>\.venv\Scripts\python.exe`，Python 3.12.4，NumPy 1.26.4，Pandas 2.3.3，pytest 7.4.4。工作目录 `<ARCHIVE_ROOT>\phase3a_data`，命令：

```powershell
<ARCHIVE_ROOT>\.venv\Scripts\python.exe -m pytest -q
```

最终结果：**58 passed，1 skipped，0 failed**（约 0.95 秒）。唯一跳过：`tests/test_adapter.py:108`，当前 Windows 身份不能创建符号链接；其它路径越界、哈希漂移、恶意 pickle、预算、数据验证器及分区合同测试执行通过。没有用真实 GPUShare 文件跑 pytest。

| 测试组 | 证明范围 | 不证明什么 |
|---|---|---|
| `test_static_pickle.py` | 合成支持格式静态解码、未知/危险结构拒绝、offset/hash 与字节/opcode 预算；恶意 `__reduce__` 不执行 | 9.99 GB EOD 峰值内存、任意 pickle 安全 |
| `test_adapter.py` | 合成固定 manifest 读取、真实源哈希/路径语义、字段/用途/范围/预算拒绝、冻结段遮罩 | GPUShare 当前 ACL、运行身份、所有真实字段质量 |
| `test_validators.py` | 手工合成公司行动、上市/退市、停牌填价、单位、时间信息、历史重写等异常可被发现 | 真实异常已经修复或正式回测通过 |
| `test_splits.py` | 分区版本/边界、v2 清单指纹和认证降级、机器字段字典一致、未来/状态/非法日期与跨界拒绝、无交易日拒绝、交付合同 Train/Validation/Holdout 均不触发底层读、仅合成独立快照可读、完整历史文件冒充分区时拒绝、审计事件、标签成熟/embargo | Linux 文件权限和主 Agent 全路径 Holdout 物理隔离 |

## 已接收的真实数据检查（未重复运行）

`survey/results/real_sample_run.json` 保存过一次 GPUShare 只读实跑：2020-01-02—2026-10-09，1,638 日、5,427 代码、8 字段，文件哈希/范围/预算按当时 manifest 验证；`backtest_purpose → CERTIFICATION_TOO_LOW`，`future_field → FIELD_NOT_CERTIFIED`，`status_field_for_research → CERTIFICATION_TOO_LOW`，`outside_scope → OUTSIDE_CERTIFIED_SCOPE`，`default_budget → BUDGET`。这证明旧适配器拒绝案例，但其 v1 `RESEARCH_READY` 标记已被本次 v2 清单降级。

该真实检查中，轴、OHLC、量额单位、交易日历、覆盖率通过；`listing_bounds`（1,228 上市前单元）、`adjustment`（5 次实质下降及舍入噪声）、近端公司行动交叉检查、四个状态字段冻结尾段、复权版本历史重写 **不通过**。这些是数据认证失败，不应被“53 个软件测试通过”覆盖。源文件在 2026-10-12 之后是否仍与清单哈希相同，本次未现场复核；部署前必须重比对。

## 尚未通过/尚未执行的验收

- Linux 符号链接拒绝测试及完整 Linux 回归本次未重跑；Windows 唯一跳过项需要在未来隔离研发环境补测。
- `root` 只预开只读 FD、解析进程实际为 nobody、CPU/内存限制及所有输入路径的 OS 层审计，缺真实命令/UID/GID/资源记录；不能称已通过。
- 大型 EOD 静态 skeleton 的真正硬内存上限没有证明；动态适配器保持 BLOCKED。
- 训练/验证/最终 Holdout 的服务器级 ACL/挂载隔离未部署、未验收；主 Agent v0.6.8 未注册新资源或新工具。
- 发布时点、上市退市、交易状态、公司行动及正式回测数据合同未过；未运行 Phase 3-B 回测。
