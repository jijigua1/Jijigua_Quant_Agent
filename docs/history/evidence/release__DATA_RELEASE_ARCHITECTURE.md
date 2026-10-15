> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 独立数据发布原型与准入闸门

本目录的 `release.py`（原内部附件未公开） 是独立原型，不属于冻结的 v0.6.8 主 Agent，也没有部署 GPUShare。它复用 Phase 3-A `qra_data.adapter.ControlledReader` 静态解码及 `qra_data.validators`；`panel_from_reader()` 只接收可信发布者注入的读取器并固定 Train/Validation 日期，不调用 `pickle.load`。合成 PKL 已验证从静态读取到发布文件，但真实原始文件需要受限发布者与 FD broker。`capture_source()` 固定六文件名，按 FD 计算 SHA，前后核对整组 inode/长度/mtime，检查同组更新时间跨度；`inspect_source()` 再与已批准 manifest 比对。哈希一致只表示版本锁定，不能替代字段质量认证。

获批后已创建空的 `/srv/jijigua-quant-agent/data_releases/`，按身份物理分为 `train/`、`validation/` 和独立的 `daily_private/`。`mask_prelisting()` 可依据独立可信上市日期把上市前价格及量额置为缺失，不改原始数据；缺名单或未经屏蔽时 `publish()` 拒绝。`publish()` 还拒绝越界日期、未来字段及异常价格/成交单位，先写私有暂存目录，再原子改名为不可覆盖的版本目录；原型已设置最终目录 `0750`、文件 `0640`，实际 Linux 身份可读性尚未验收。基线保存六个只含该分区的 `.npy`；后续仅保存新增或修订日期的增量，manifest 链含父版本哈希。`read()` 限白名单字段、读量、日期/代码及文件 SHA；没有 Holdout 读取入口。实际研究服务必须由可信配置固定根目录，模型只传资源 ID，不能调用 `read(root=任意路径)`。

真实发布仍需一个**非 root、只运行受审发布代码**的隔离工作进程。原始文件为 `root:root 0600`，`quantagent` 无读取权。最小方案由 root 管理的小型白名单 FD broker 只读打开六文件，向隔离发布进程传 FD；进程在降权后才执行 Phase 3-A 静态解析、校验与发布。`quantpub` 身份与空目录已获批创建并通过基础权限检查；FD broker **尚未实现或部署**，真实发布仍未获批准。绝不能以 root 运行不可信 PKL 反序列化，亦不能给 `quantagent` 原始目录的通用读权限。

一次更新的准入顺序：

1. 等生产者退出且六文件连续稳定；捕获候选指纹，确认日期轴真实末日及六字段轴相同。
2. 受限进程对固定文件做静态解码，复用 Phase 3-A 质量检查；载入可信上市日期并屏蔽/拒绝上市前值。无法证明发布日期则保持 `PROFILED_EXPLORATORY_ONLY`。
3. 比对上一版的重叠历史，记录新增日、改写/删除日期及代码。异常的大范围历史重写隔离待审，不自动覆盖旧研究版本。
4. 从同一冻结源版本分别发布 Train、Validation；每个目录只包含本区间日期，检查权限、哈希、实际读取拒绝及结果预算。Holdout 不向研究目录发布。
5. 独立 Daily Inference 只给冻结策略计算某个 as-of 时刻的已可得输入，研究 Agent 仅收到最新信号及来源/曝光记录，不得到测试标签或绩效。
6. 发布批次记录原始六 SHA、日期、轴、质量结论、修订摘要、发布 ID 和备份状态。研究任务引用发布 ID 与 manifest SHA。

区分四个状态：`SOURCE_UPDATED`（文件完成）、`QUALITY_PROFILED`（字段检查）、`RESEARCH_PUBLISHED`（分区隔离且获准探索）、`BACKTEST_APPROVED`（独立交易数据/引擎验收）。本轮到第二种静态证据及本地原型；没有真实第三或第四种。当前 `check_listing_bounds` 缺完整可信上市日期时拒绝发布，不偷用可疑回填行。

原型限制：虽已有 `quantpub` 和空目录的 Linux 权限划界，仍无受限 FD broker、真实日期轴解码作业、持续调度、真实发布、持久审计库或正式日更计算。增量链限制 32 版，超过后需管理员审核压实为新基线；其状态不应被 CLI 描述为已上线服务。
