> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 首次真实 Test：一次性精确审批申请

状态：**READY_FOR_HOLDOUT_APPROVAL**。本文件尚未获批；`approval.draft.json` 的 `approved=false`。依据用户本轮第3、9节，真实发布、账户及权限设置、第一次2026表现读取必须先确认。

## 1. 已核实的来源与冻结对象

2026-10-13上海01:52的有界SSH检查确认：六文件与Phase3-A已审查版本逐字节相同；随后以quantpub静态解析close的日期/证券轴，不输出价格或标签。实际Test是 **2026-01-05—2026-10-09、183个观测日、5427固定代码轴**。不是2026全年，也不把系统日期或mtime当数据末日。

源路径均为 `/hy-tmp/data/daily_update/<field>.pkl`，各81,837,746字节：

| 字段 | SHA-256 |
|---|---|
| open | 2accab1dde39ff1822b05c6f3262db4e6fe0dac5814d3a35aaa0fc197d289d05 |
| high | b5b6f2d539786181b6a9238d21d8bcc81d1614b469f06e29d52aa03992f4d881 |
| low | 17019d88800a8c168b4443bb1bd7f08f002d99e0f57d9a934cbde0314948beab |
| close | a864dc3397af840206bc6f839b9ccf4e5ba5f70abeff2d8b031e1ddb739cd326 |
| volume | c2b87c2d94bc44822fa362299d1a796ab82fc23e11d94872b436618ed6e5ad6f |
| amount | 599cbeb7f2255fcc1f49f2865ef0f90bcc0ab485165d95b66f1caab44d2aa62b |

价格为原始未复权元/股，volume为手（100股），amount为千元。任何源SHA、大小、轴或批次在执行前变化，立即停止，不自动改用新数据。

首次只测试现有研究 `INTERNAL_RUN_ID_REDACTED:1339576f3486425d`：

- 原成果：`/srv/jijigua-quant-agent/research_runs/2026-10-13/01-33-21_reversal_5d/`。
- 原manifest SHA：`5c7141f136b26635b170e4c41c2b0b5de15262b0d4c8d8c9890e0c7250e4599b`。
- 因子 `-(close[t]/close[t-5]-1)`；raw、5组、方向+1、下一观测开盘起算、H=5；标签 `open[t+6]/open[t+1]-1`。不重新选窗口、方向或评价口径。
- 原研究代码SHA `344c5fac041946df8902527a4e2320c1cf005933e11603b8d42dd926bdf30121`。
- 执行冻结SHA `f330895906745ee174b8e6dd5e7314f955fabb92728629ae6c889f1bde7e2995`，见 `evidence/frozen_definition.json`。这是闭合执行合同的指纹；旧Tool申请 `d94777…` 指纹包含研究说明和参数对象，两者定义不同，不能混称。
- Train/Validation manifest仍分别为 `9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221` / `82246b4424f8dbd45c11d959164199a4b45efeb6803d6a6064204a6fc08bf4b4`，执行前复核，不修改。

## 2. 请求批准的全部变更

| 范围 | 精确操作 |
|---|---|
| 独立身份 | 仅创建系统组quanteval及同名无登录用户，主组quanteval；不加入quantdata/quantagent，不授sudo/SSH。UID/GID由系统分配并登记；若已有同名身份，停止审查。现有用户、组及权限不变。 |
| 受审代码/环境 | 新建 `/srv/jijigua-quant-agent/test_evaluator/phase3c_v1/`，root管理只读代码；只复制审定v0.8 wheel中的模块及独立适配代码，112文件SHA见 `evidence/source_manifest.json`。新建独立venv，离线复制现有v0.8已验收的确定性依赖（NumPy1.26.4/Pandas2.3.3/Matplotlib3.8.4等白名单），不联网安装，不改主Agentvenv。新建var仅quanteval可访问；私有随机HMAC材料、SQLite账本、缓存放这里，不交给Agent。 |
| 私有快照 | 仅新增 `/srv/jijigua-quant-agent/data_releases/test_private/test_20261009_a864dc33_v1/`。父目录/批次目录root:quanteval 0750，数值/manifest 0440。quantagent与quantpub均不能读取封存结果。只处理六字段；120个2025暖机观测日（2025-07-09—12-31）+183个2026日，共303×5427；暖机不计Test统计。 |
| 发布暂存 | 仅在现有quantpub私有staging中新建 `test_20261009_a864dc33_v1`。root固定只读打开六FD，清除其他FD/环境、降至quantpub后静态解析、质量检查和写入NPY。root验证完整哈希后原子改名并设置新文件的私有所有权；不改staging父目录或源数据。 |
| 准入规则 | 与Train/Validation相同的候选上市日前屏蔽；候选CSV SHA `f6f5d072d6502561a3ca3495f9132b84753584ddbef6d7ce459b4a0dfa10e209`。001914.SZ、302132.SZ仍整列NaN。候选Listdt不认证上市/PIT；六字段质量闸门有error就停止，不为通过而删股票或改变规则。 |
| 第一次评价 | 仅以上冻结研究，独立quanteval执行一次；全局尝试预算1，失败也计数；不给模型私有reader、FD、密钥或原始矩阵。末H+1=6日无成熟标签；本批次最后可成熟信号日为2026-09-23。 |
| 独立复算 | 在同一quanteval权限内以独立NumPy公式、平均秩和Pearson基准复算全部Test逐日IC/RankIC及年/月汇总，容差1e-12。复算失败不发布综合报告，不自动重试或调参。 |
| 报告输入与归档 | 只复制以上一个已授权Train/Validation研究的必要CSV/JSON（约145MiB，含已有因子值CSV），到私有报告工作区；不重算Train/Validation，不复制原始PKL/整个数据仓库。合法签名回执由quanteval验证并生成同一study_id的revision2。root仅核对文件、移动聚合报告并更新原研究的版本索引/manifest；旧HTML/MD/PKL/指标均保留，旧manifest及索引存于 `reports/history/`。新报告使用服务器真实上海创建时间目录 `research_runs/YYYY-MM-DD/HH-MM-SS_report_revision_2/`。 |
| 返回范围 | 只返回签名的逐日IC/RankIC/覆盖率、分区/年度/月度聚合统计、HAC/稳定性/理论毛收益诊断、版本和曝光信息；不返回原始价格、逐股票因子或收益标签。公共报告有完整签名回执，私钥和独立账本保持私有。 |

**不替换生产v0.8代码/wheel/launcher/API/研究SQLite，不新增常驻服务、定时任务或普通2026 Resource，不开放正式Backtest。** 当前模型Tool仍只登记测试申请；这次获批后由有限时长的独立操作者命令执行，现有 `qrtk_read_study` 可读同一研究的新报告。自动后台评估调度不在本轮建设。

## 3. 固定命令与验收顺序

审定代码上传至上表新代码目录、root核对全部SHA并在用户批准后写入root所有的批准配置。随后只运行以下三个固定动作（不是提供给模型的Shell Tool）：

```sh
python3 /srv/jijigua-quant-agent/test_evaluator/phase3c_v1/phase3c_admin.py prepare
python3 /srv/jijigua-quant-agent/test_evaluator/phase3c_v1/phase3c_admin.py publish
python3 /srv/jijigua-quant-agent/test_evaluator/phase3c_v1/phase3c_admin.py evaluate
```

prepare之后先检查独立venv版本/合成回归；publish之后、evaluate之前，以quantagent真实OS身份验证Test、私钥、缓存、独立账本、原始PKL与staging全部PermissionError。同时验证quanteval无原始PKL/quantdata研究分区权限。任一失败即停止首次评价。

evaluate采用现有IndependentEvaluator一次性许可和私有事务账本；具体子进程为`runuser -u quanteval -- <独立venv>/bin/python -I -B`，只加载固定已审源码/config。签回执、独立复算、合并报告。再用原v0.8真实SSH CLI/官方DeepSeek读取该原会话研究的新版报告，验证Test指标与热力图，不把私有数值矩阵传给模型。原申请、旧task/session记录不删改。

资源：快照数值约75.3MiB；代码/独立依赖/私有报告输入和结果总新增上限1GiB（不含明确批准的最终报告副本，另限32MiB）。发布子进程2GiB地址空间/75 CPU秒/120墙钟秒、单文件128MiB；评价和报告进程4GiB/120CPU秒/180墙钟秒、单文件512MiB、数值库单线程。没有GPU、网络模型调用或未知代码执行。不称这些rlimit为生产沙箱。

## 4. 曝光、失败和回滚

- 采用 **retrospective_2026**。已有旧2026价格及daily20/daily65研究曝光；生产账本本次有界检索发现77条旧资源工具实验/访问记录，不等于77个不同因子或77次独立测试，也不覆盖其他研究者。这个冻结研究在独立评估器中的首次获批评价不赋予整个2026“盲测”属性。
- 不因Test结果再优化同一因子；修改定义需要新版本及新的明确审批，当前全局预算1默认拒绝第二份候选。
- 任何SHA/轴/依赖版本/OS权限/质量/签名/数值核验失败都停止。仅清理本次程序自身创建且未提交的`.pending-test-*`；已提交私有版本、失败计次和曝光证据保留，不递归清理父目录或其他项目。
- 报告更新前保存旧manifest/索引实物。回滚只恢复原报告索引和manifest指针；新报告及已发生的测试曝光仍保留，不倒灌SQLite或伪装“没测试过”。新账户/私有文件若需删除，另行提交准确清理清单，本次不自动删账户。
- `/hy-tmp`有实例清理风险。此次只把审批、manifest、源码/指纹和聚合测试证据保存本地项目；不把原始2026数值复制到研究Agent可读路径或外部平台。约75MiB测试快照及私有账本需要用户提供可信持久备份位置，否则仅能承诺当前实例内复现。

本次仍是 **PROFILED_EXPLORATORY_ONLY 历史统计测试**。公司行动、未复权跨事件收益、股票池/PIT、交易状态和退市估值仍未认证；不出正式账户NAV/Sharpe，不解除正式回测BLOCKED。
