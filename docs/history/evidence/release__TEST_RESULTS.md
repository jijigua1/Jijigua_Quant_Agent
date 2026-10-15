> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2-A 测试与未完成项

## Phase 3-B2 实际发布补充（覆盖下文旧阶段状态）

2026-10-12 用户批准后，以固定 SHA 的最终代码包在 GPUShare 重跑 Linux 合成发布/权限测试、真实六字段 Train/Validation dry-run，并完成一次实际发布。`quantagent` 对 12 个发布 `.npy` 独立重算 SHA，读取两份完整 close 核对有效单元及两只整列排除代码，读取各分区末日六字段；原始文件、private/staging/audit 和写入拒绝通过，Holdout 发布目录不存在。Train 全股票 5 日原始价格变化只在内存计算。具体路径、manifest SHA、文件体积及指纹见 real_release_20261012.json（原内部附件未公开）。

本地 Phase 3-A + 独立发布模块最新合并测试为 **69 passed、1 skipped**（Windows 无软链接权限）。下文的 67/1、未真实发布等语句保留 Phase 3-B2-A 的历史验收记录，不代表本次最终状态。Validation 已用预定五日原始价格动量做 478 日探索性 IC/RankIC，曝光记录见 validation_exposure_20261012.json（原内部附件未公开）。正式回测、主 Agent 全量研究接入和全轴标准因子 PKL 仍未验收。

**收尾复测**：2026-10-12 再运行 Phase 3-A + 本目录测试，仍为 **67 passed、1 skipped（Windows symlink 权限）**；新增脚本均通过 `py_compile`。GPUShare Linux Python 3.11.10 / NumPy 2.1.2 / Pandas 3.0.3 上的临时**合成**权限验收通过，结构化证据为 `linux_synthetic_evidence.json`（原内部附件未公开）：Train/Validation 的 `quantagent` 读、原始文件/私有目录/写入拒绝、无 Holdout 发布、符号链接/硬链接拒绝和临时产物清理。新 API 实测与 Mock Agent 首轮失败分别见 `api_compat_adapter_evidence.json`（原内部附件未公开）、`api_compat_agent_evidence.json`（原内部附件未公开）。没有真实市场发布或正式账户回测。

环境：Windows / Python 3.12.4 / NumPy 1.26.4 / pytest 7.4.4。2026-10-12 在独立 `phase3b_data_release` 目录执行；服务器仅实施单独获批的身份及空目录变更，没有真实数据发布或市场回测。

```powershell
$env:PYTHONPATH='<ARCHIVE_ROOT>\phase3a_data;<ARCHIVE_ROOT>\phase3b_data_release'
python -m pytest -q <ARCHIVE_ROOT>\phase3a_data\tests <ARCHIVE_ROOT>\phase3b_data_release\tests
```

最终原始输出保存在 `evidence/local_tests_20261012.txt`（原内部附件未公开）：**67 passed，1 skipped，1.33 秒**。Phase 3-A 原测试与本目录新增测试合并运行。覆盖静态 pickle 恶意全局拒绝、原始适配器预算/哈希、分区和标签成熟；新增合成测试覆盖静态解码到固定 Train/Validation 发布、基线、增量、历史修订、旧版可重读、不可覆盖、日期越界、Holdout 无入口、非法路径、单位错配、上市前回填、未来字段、输出预算、发布文件篡改、父版本篡改、源部分更新/并发修改及 Daily 冻结模型条件。发布后权限模式 `0750/0640` 的断言仅在 POSIX 环境实际执行，Windows 不作 Linux 权限验收。

初次从 `<ARCHIVE_ROOT>` 直接运行 Phase 3-A 测试时，四个模块因缺 `PYTHONPATH` 在收集阶段失败；按上面的实际包根配置重跑已解决，并未修改 Phase 3-A。Windows 无创建符号链接权限，原 Phase 3-A 的一项软链接测试会跳过；本目录的源/发布路径检查在代码中存在，但真实 Linux 符号链接验收须待获批部署环境。

**测试分类**：上述均属软件工程与合成数据证据；真实服务器另有 `server_readonly_20261012.json`（原内部附件未公开） 的 stat/hash 和 `server_permissions_20261012.json`（原内部附件未公开） 的用户/空目录权限实测。未执行真实新日增量发布、Train/Validation **数据文件**权限拒绝、独立 Holdout 评估、日更最新信号或真实策略绩效。缺失项不得折算为通过。
