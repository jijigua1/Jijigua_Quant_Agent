> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2 上市日期准入与首次真实行情发布（2026-10-12）

**结论：PUBLISHED_EXPLORATORY_VERIFIED。** 用户已明确批准 [精确范围](release__REAL_RELEASE_APPROVAL_20261012.md)；真实六字段 Train/Validation 已于 2026-10-12 发布，并由 `quantagent` 独立验收。上市日期未获权威认证，不能升级为正式回测数据。实际批次证据见 real_release_20261012.json（原内部附件未公开）。

## 上市日期来源与准入决定

- `/srv/auxiliary-data/TRD_Co.csv` 为 root:root 0644、910,235 字节；SHA-256 `f6f5d072d6502561a3ca3495f9132b84753584ddbef6d7ce459b4a0dfa10e209`。有 `Stkcd/Listdt` 等字段，共 5,980 个不重复代码、其中 5,537 条 A 股；最后候选 `Listdt` 为 2026-07-02。未找到生成脚本、原始提供方、版本历史或 `Listdt` 的正式定义。文件名及修改时间不能证明其为首次可交易日。
- 对现有 `/home/updates/daily/eod_factor_update.py` 的只读源码追踪发现它运行时调用 Tushare `stock_basic(ts_code,list_date,delist_date)`，用于当日上市状态回退；该代码**没有证明** `TRD_Co.csv` 由同一接口产生，也没有保存覆盖全历史的不可变 PIT 上市/退市事件。其他已检查项目只把 CSV 当基础股票资料；未发现可复核的候选表生产链。源码证据在 `phase3a_data/survey/server_sources/home__updates__daily__eod_factor_update.py.readonly.txt` 第 99–126、700–715 行。
- Phase 3-A 首个有限价格日期与候选上市日期比较显示 `001914.SZ` 与 `302132.SZ` 存在明显身份/日期冲突。2020–2025 原始 close 中，早于候选 `Listdt` 的有限值共 1,228 个，均落在 `302132.SZ`。`001914.SZ` 冲突发生在 2019 年，虽目标区间没有候选上市前单元，历史身份仍不明。当前记录无法解释重组、重新上市、代码沿用或上市日语义，因此两个代码在整个目标区间全部排除，不根据因子表现挑选排除对象。
- 方案 A（可信股票准入）目前**不可认证**：其余代码没有逐股独立的时点证据，不能把“与候选日期不冲突”当成上市日已认证。已批准并执行方案 B：六原始字段作为 `PROFILED_EXPLORATORY_ONLY` 发布；候选日期以前的数值一律设缺失，两只已知冲突代码整列设缺失，保留诊断计数。该屏蔽规则可能过度或不足，**不代表**上市日认证、可交易状态或正式回测资格。

## 有界真实数据预演

复用 Phase 3-A 静态 PKL 解码器和既有受限发布器。root 只打开固定六源文件只读 FD，确认大小、SHA、inode/mtime 未变；子进程降权为 quantpub 后解码，设置 2 GiB 地址空间、75 CPU 秒、120 墙钟秒、UID 进程数上限 16、1 GiB 单文件，并把数值库设为单线程。这些是本次受控作业的限制，不是正式作业树沙箱。`dry_run=True` 在六字段执行同样的上市日期屏蔽、身份排除及质量校验，**不创建发布文件**。摘要见 listing_release_dry_run_20261012.json（原内部附件未公开）。

| 分区 | 实际交易日 | 日数 | 固定代码轴 | 有 close 的代码 | 候选日期前屏蔽单元 | 冲突代码剩余屏蔽单元 | 最终有效 close 单元/占固定轴 |
|---|---|---:|---:|---:|---:|---:|---:|
| Train | 2020-01-02—2023-12-29 | 970 | 5,427 | 5,218 | 960 | 970 | 4,358,626 / 82.80% |
| Validation | 2024-01-02—2025-12-31 | 485 | 5,427 | 5,258 | 268 | 702 | 2,480,340 / 94.23% |

排除两只代码后，固定轴仍为 5,427 列，其中两列全为 NaN；潜在非排除代码 5,425 只，实际有值代码数见表。按候选表**当前**行业标签，`001914.SZ` 为房地产、`302132.SZ` 为工业；行业标签没有 PIT 认证，不能据此定量证明行业偏差为零。另有固定沪深代码轴、北交所缺失、2026 新股遗漏、退市/重新上市事件不完整等样本选择风险。收益或 IC 不能用于反向修改本准入规则。

六个原始 PKL 当前均为 81,837,746 字节，源 SHA、批次信息、更新时间及只读权限证据见 server_readonly_20261012.json（原内部附件未公开）。六文件字节与 Phase 3-A 已解码快照一致，内容截至交易日 2026-10-09；服务器 mtime 不是截止日证据。本轮并未证明以后每日自动更新一定成功。Train/Validation 预演已触及真实六字段，但**未读取 2026 收益/IC/策略表现**，未修改原始文件。

## 工程与未解决边界

实际独立发布批次：

| 分区 | 服务器成果目录 | 发布时间（上海） | 目录字节数 | manifest SHA-256 |
|---|---|---|---:|---|
| Train | `/srv/jijigua-quant-agent/data_releases/train/baseline_20261009_a864dc33/` | 2026-10-12 19:02:53 | 252,759,895 | `9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221` |
| Validation | `/srv/jijigua-quant-agent/data_releases/validation/baseline_20261009_a864dc33/` | 2026-10-12 19:03:30 | 126,414,005 | `82246b4424f8dbd45c11d959164199a4b45efeb6803d6a6064204a6fc08bf4b4` |

两份 manifest 均标记 `PROFILED_EXPLORATORY_ONLY`、`listing_certified=false`、`formal_backtest_eligible=false`。`quantagent` 独立重算了 12 个 `.npy` 哈希并读取完整 close 核对 4,358,626 / 2,480,340 个有效单元，两只冲突代码全缺失；又读取各分区末日六字段。两份质量检查无错误。Linux 权限检查确认 `quantagent` 可读两份发布、不能读原始 PKL、私有/暂存/审计目录或写入发布，Holdout 发布目录不存在。没有遗留 `.pending-` 目录。实际审计摘要见 发布证据（原内部附件未公开）。

两份实际 manifest 已按字节转存到本地 Train manifest（原内部附件未公开） 与 Validation manifest（原内部附件未公开），SHA 与服务器一致。**数值文件尚无持久备份**；如果 `/hy-tmp` 被清理，单凭这两份 manifest 无法恢复数据。

工程层面另以 `quantagent` 在内存中对**完整 Train 股票横截面**计算 5 日原始收盘价变动，维度 965×5,427、有限值 4,327,783 个；结果未保存为研究因子、未用于绩效评价。此计算只证明长期分区可用于有界数值研究，不认证复权收益或预测能力。

按预先固定的同一 5 日原始价格动量定义，在**独立 Validation 文件**上调用已审 `qrtk.factor_eval` 计算探索性相关性：信号在 T 收盘后可见，标签为 T+1 收盘至 T+2 收盘原始价格变化；首 5 日只用于分区内暖机、末 2 日标签未成熟不计。有效日期 478 个，IC Mean `-0.018671`、RankIC Mean `-0.033345`，最后有效信号日 2025-12-29。结果及函数指纹见 Validation 曝光记录（原内部附件未公开）。这次已经观察到该因子的 Validation 结果，不可再把它称为未触及的独立测试；原始价格跨公司行动未调整，T+1 收盘只是统计标签而非可执行成交价，不能推断正式回测或策略收益。

- 独立 `release.py` 增加冲突身份整列屏蔽；`linux_publisher.py` 固定候选 CSV SHA、禁止真实发布时传入调用者上市日期、记录来源与代码指纹、支持不落盘 dry-run。原本六字段白名单、固定源 FD、分区读者、质量闸门与权限结构保留。新增只读审计 `listing_readonly_audit.py`。没有修改 `<ARCHIVE_ROOT>\src`、主 Agent v0.6.8、服务器部署或 GeorgeResearch。
- Windows：Phase 3-A 与独立发布模块联合测试 **69 passed, 1 skipped**（Windows 无符号链接权限）。最终代码哈希与传输包哈希已在 Linux 对上，随后 Linux 合成发布、链接拒绝、身份权限和真实六字段 Train/Validation dry-run 再次通过；真实发布及独立读取验证也已完成。
- 六字段为原始行情；未认证复权/公司行动、PIT 发布时间、历史停牌/ST/涨跌停、退市估值与真实交易能力。因此仅能做带限制的探索性因子计算；跨公司行动 raw close 收益不是真实总收益。Train 可用于开发，Validation 使用要记录曝光；2026 Holdout 不发布。本轮也**未**实现 Holdout 的独立评估身份。
- 主 Agent v0.6.8 尚未注册新资源。其现有因子表达式和 PKL 导出还有 `100000` 单元上限、仅已验证股票映射，无法直接处理这份全股票长期分区。已验收独立只读分区、全股票 Train 内存因子计算及受控 Validation 探索性 IC/RankIC；标准全轴因子 PKL、Agent 自然语言调用需另案受控适配，不能把发布成功写成 Agent 已可用。
- 已批准的 Train/Validation 目录所有者 `quantpub:quantdata`、模式 2750；private/staging/audit 为 0700。当前 `quantagent` 不能读原始 PKL/私有目录。正式发布前后再次核查。`/hy-tmp` 为可清理临时存储，当前约 79.1 GB 可用；**未完成持久备份**，不可把版本指纹误当作可恢复的数据副本。

## 指纹与后续最小验收

本次独立代码 SHA-256：`release.py` `EA3702BBA89FCEF3B9C6A5420D38A52FD6B70D36B191DAE7EC02F3C71BDCDB26`；`linux_publisher.py` `A74AAF203BFB9F2E3B554172B73E74575FF847D725E0FF63D39B3CF19A018790`；`listing_readonly_audit.py` `C5C9E7E9B9674CF9A6CD1BFDE6918A5B7171FEA8AC0DD5CC7119534355BCC3B0`；静态解码器 `3A442A548B952338758DC1C1780E18BE1C7077A39D5596FDDF10CE117CF23EFF`；源清单 `F3CAFC2B4D0B3D40F7C01563DA941307B22DC559C2975BBF826FC776832508B0`。真实六源 SHA 在只读证据文件中，不在此重复。

已完成的最小验收：精确哈希重核六源与代码 → 独立 Train、Validation 发布 → manifest/12 个数值文件哈希复核 → quantagent 只读完整 close 及末日六字段 → 原始、private、staging、写入及 Holdout 拒绝/不存在检查 → Train 全股票 5 日原始价格变化的内存数值计算 → 独立 Validation 文件上的成熟标签 IC/RankIC。尚未执行标准全轴因子 PKL；需先解决冻结主 Agent 的 100,000 单元及映射限制，并建立显式的研究实验账本。任何账户回测与正式绩效仍为 BLOCKED。

以下是可复查的**只读**分区命令（先将 `APPROVED_CODE_ROOT` 设置为哈希核对过的代码包，其中含 `release.py` 与 `qra_data/`；本轮运行已通过）：

```bash
runuser -u quantagent -- env PYTHONPATH="$APPROVED_CODE_ROOT" python3 -c 'from release import read; from pathlib import Path; import numpy as np; root=Path("/srv/jijigua-quant-agent/data_releases"); rid="baseline_20261009_a864dc33"; p=read(root,"train",rid,fields=("close",),max_cells=6000000); assert p.dates[0]=="20200102" and p.dates[-1]=="20231229" and len(p.codes)==5427 and np.isfinite(p.fields["close"]).sum()==4358626; print("TRAIN_READ_VERIFIED",len(p.dates),len(p.codes))'
runuser -u quantagent -- env PYTHONPATH="$APPROVED_CODE_ROOT" python3 -c 'from release import read; from pathlib import Path; import numpy as np; root=Path("/srv/jijigua-quant-agent/data_releases"); rid="baseline_20261009_a864dc33"; p=read(root,"validation",rid,fields=("close",),max_cells=3000000); assert p.dates[0]=="20240102" and p.dates[-1]=="20251231" and len(p.codes)==5427 and np.isfinite(p.fields["close"]).sum()==2480340; print("VALIDATION_READ_VERIFIED",len(p.dates),len(p.codes))'
```

批次之前若源发生变化，上述固定计数和 release ID 必须重算并重新审批，不允许为了让断言通过而修改市场数据。新因子 PKL 的全轴导出需扩展 v0.6.8 的 `100000` 单元上限并核实全代码后缀映射；这属于下一步 Agent 集成，当前不得在冻结主 Agent 中暗改。为避免错误宣称，本阶段没有提供伪装成现成可用的全量 `quant-agent chat` 命令。
