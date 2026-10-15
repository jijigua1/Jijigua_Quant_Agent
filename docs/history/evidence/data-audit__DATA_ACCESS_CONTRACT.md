> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-A 独立数据适配器与访问合同

本目录的 `qra_data` 是独立审计原型，**未**部署或注册至主 Agent v0.6.8。项目只读输入；代码只允许自己的测试临时目录及本目录文档/Schema 写入。真实原始数据、其他研究者项目均未修改。

## 固定输入与方法

`ControlledReader(manifest, allowed_roots, budget, opener)` 仅从可信清单按资源 ID、字段名、日期、股票代码读取。分区原型使用 `schemas/daily_update_manifest.v2.json`，它保留 v1 每文件的绝对根、相对文件名、字节长度和 SHA-256，同时把原先过高的 `RESEARCH_READY` 降为 `PROFILED`；读取前检查规范路径、允许根、非符号链接、普通文件、单硬链接、大小、哈希。默认最大 4,000 万输出单元、单文件 256 MiB、结果估算 1 GiB；没有 CPU/OS 内存硬限制，实际每字段先完整读入内存再切片。特殊 8 字段全样本核验使用过单独的 8,000 万单元预算，**不能当作日常 Agent 配置**。

静态 PKL 解码器 `qra_data/static_pickle.py` 使用 `pickletools.genops` 建符号树，`GLOBAL/REDUCE/BUILD` 不 import、不实例化、不调用 Python 对象；拒绝未知 global、危险 opcode、类型与形状。合成恶意 `__reduce__` 测试确认未执行。该结论仅针对已支持的受限格式和预算，不意味着任意 pickle 安全。`Blob` 大块带 offset/SHA，按需 `_pread` 可验证文件未变；但 `genops` **先把大字节 opcode 参数物化**，然后才转 `Blob`，所以 9.99 GB EOD skeleton **没有可靠峰值内存界**。本轮将 EOD 动态读取列为 `BLOCKED`，不可在主 Agent 或 root 进程调用。需要真正有界的流式 opcode 解析或预先经隔离审核、转换为受控列式快照。

`survey/real_sample_run.py` 提供由管理员只读打开文件、将 FD 映射交给低权限解析进程的代码入口；打开器只接收白名单路径、复制已有 FD。已有 JSON 证明实际读和拒绝结果，但**未记录运行 UID/GID、进程命令及 OS 资源限制**；脚本还直接打开过交易日历及近期 CSV。因此“root 只打开、nobody 解析”的全链路隔离还不能认证。不得把 venv、FD 传递或静态解析等同完整沙箱；不得用 root 解析未知 pickle。

## 研究侧分区原型

`schemas/data_split_contract.v1.json` 独立声明 Train、Validation、Holdout，版本号 `qra-split/1.0.0`，并固定 v2 源清单的规范化内容 SHA-256。**交付状态三个分区均未发布独立快照**：Train/Validation 请求在底层 I/O 前以 `SPLIT_RESOURCE_NOT_PUBLISHED` 拒绝，Holdout 一律 `HOLDOUT_NOT_PUBLISHED`。`SplitReader` 构造时核对分区边界、源指纹和六字段硬白名单，由可信主程序注入 `research_agent` 身份和审计回调；模型不能传任意路径、用途、认证等级或放宽预算。未来发布后每个分区必须有不同资源 ID、仅含其日期范围的经审核文件，不能拿完整历史原文件仅改清单日期来冒充。已发布的分区接口调用底层 `ControlledReader` 的 `profile` 用途，输出仍只标 `PROFILED_EXPLORATORY_ONLY`。历史 v1 的 `RESEARCH_READY` 不作为本次认证；拒绝/允许的审计记录都不含数值。

示意调用（仅合成或未来经过批准并独立发布的分区快照；用本次交付的真实源清单会拒绝）：

```python
gate = SplitReader(pinned_reader, split_contract, role="research_agent", audit=audit_event)
train = gate.read("train", ["close", "volume"], "20200102", "20200131", codes=["000001.SZ"])
```

**上线前必须增加的外层控制**：研究进程看不到 2026 原始文件/FD，训练验证以独立只读快照或行级服务发布；账号与挂载/ACL 划界；模型无法构造 `ControlledReader` 绕过包装；工具白名单、会话上下文、缓存、日志、指标导出不得透露 Holdout 标签或表现。未来评估器以独立身份读取 Holdout，授权事件、次数上限、实验冻结、使用记录和受限汇总输出须持久化。当前 `SplitReader` 是合同验证而非系统级隔离，不能以此宣称 Holdout 已封存。

## 验收与失败模式

合成测试覆盖合法训练读取、标记降级、Holdout 及跨界拒绝、未来/状态字段拒绝、标签成熟、版本/角色错误；现有测试覆盖恶意 pickle 拒绝、路径、哈希、预算、文件形状与真实样本中的五类拒绝。缺少可信数据发布时间、真实上市/退市、交易所状态和公司行动时，返回“探索性/未认证”，不能转为正式回测。所有读取均记录文件哈希与版本；哈希漂移必须失败并重审，而不是静默改用新文件。
