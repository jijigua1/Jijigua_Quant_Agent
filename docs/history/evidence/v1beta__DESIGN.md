> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Autonomous Quant Research Agent v1.0 Beta — 集成设计

基线：GPUShare 生产 v0.8.2（`/opt/jijigua-quant-agent/research_agent`，2026-10-13 12:29 发布）。
本设计只在其上做最小兼容改造，所有研究计算、评价、报告与审计复用 v0.8.2 已有实现。
基线文件指纹见 `baseline_v082_sha256.txt`。

## 0. 核查结论（2026-10-13，只读）

| 项目 | 实际状态 |
|---|---|
| 生产版本 | 0.8.2；源码 `src/{research_agent,qrtk,qrtk_skills}`；入口 `/usr/local/bin/quant-agent` → `deploy/launcher.py`（root → quantagent） |
| 2026 一次性独立评价 | `test_evaluator/phase3c_v1`：quanteval（uid 997），私有快照 `data_releases/test_private/test_20261009_a864dc33_v1`（含 120 个 2025 暖机日 + 183 个 2026 观察日），HMAC 签名回执；五日反转 revision2–4 |
| 每日行情 | `/hy-tmp/data/daily_update/*.pkl`，root 0600；由 `real_time_product` 项目 cron（19:00）更新 |
| 最新观测日 | **2026-10-09**（close.pkl 实际索引，非 mtime）；5180/5427 只股票有收盘价 |
| 更新机制现状 | 容器 2026-10-11 16:08 重启后只有 supervisord，**cron 守护进程未运行**；10-12 未更新 |

## 1. 总体结构

```
quant-agent chat (root 启动器)
 ├─ 父进程（root，仅在会话期间存在）= 滚动评价代理 broker
 │     socketpair ⇄ 子进程；不读终端；只执行固定操作
 │     ├─ 快照检查/发布：pinned FD 读 daily_update → 降权 quantpub 静态解析 → 私有快照（root:quanteval）
 │     ├─ 评价：runuser quanteval → rolling evaluator（私有快照 → 聚合统计 + HMAC 回执）
 │     └─ 回执登记：root 拥有、quantagent 只读的 receipts 目录 + 哈希链审计
 └─ 子进程（quantagent，附加组 quantdata）= 原 Agent
       Conversation → Workflow → Skill → Tools（QuantBackend）
       ├─ factor_research（原有）：DSL/固定因子研究，研究完成后默认请求滚动 Test
       └─ paper_research（新增）：论文库 + qrtk_paper_research 管线
```

普通 Agent 进程不持有 2026 文件、FD、路径、密钥；只能发送“请评价这个已完成研究”的请求，代理从研究目录自行读取冻结定义。

## 2. ROLLING_EXPOSED_TEST

- **快照**：`rolling_<认证末日>_<六源文件SHA前12位>`；内容为基线 5427 股票轴、六字段、2026 全部观察日 + 之前 300 个观察日暖机（来自 2024–2025，已曝光的 Validation 区间）。末日完整性：最后一日收盘价覆盖数低于前 20 日中位数 90% 时，该日视为不完整并截去。同源指纹复用已有快照，不重复发布。
- **评价**：quanteval 进程按冻结定义计算全快照因子（DSL→生产 `factor_expression`；固定因子→`quant_factors`；论文新算法→可信 IR 求值器，不执行模型代码），只对 2026 信号日统计；标签按快照观察日序列成熟，未成熟为 NaN。
- **输出合同（白名单聚合）**：逐日 IC、RankIC、覆盖率、有效配对数、各组等权平均前向毛收益、G0−末组；分区/年度/月度统计（复用 `factor_evaluation._period`）；成熟信息（观察日数、最后成熟信号日、未成熟日期）；暖机重叠校验摘要。不含逐股票价格、因子或标签。
- **账本**：quanteval 自有 SQLite；`(definition_sha256, snapshot_version, contract_version)` 唯一，命中直接复用。与 phase3c 一次性账本、密钥、预算完全分离，不读不写。
- **历史一致性**：代理用研究目录 `factor_values.csv` 的最后 60 个 Validation 日与评价器在同日计算的值做摘要比对；不一致记录为 `HISTORY_MISMATCH`，结果不合并。
- **报告**：Agent 进程验证回执与 root 登记副本逐字节一致后，生成同一 study 的新 report revision；旧 revision 永不覆盖。

## 3. Test 状态分类（报告与对话统一）

| 状态 | 含义 |
|---|---|
| `RETROSPECTIVE_ONE_TIME` | 原 phase3c 一次性回顾性评价（五日反转） |
| `ROLLING_EXPOSED_TEST` | 新滚动暴露评价；持续曝光，不是盲测 |
| `NOT_EVALUATED` + 原因 | `NOT_AUTHORIZED`（生产未授权）、`EVALUATOR_UNAVAILABLE`、`NO_TEST_DATA`、`NO_MATURE_LABELS`、`HISTORY_MISMATCH`、`FAILED` |

## 4. 论文

- **上传**：Windows `quant-paper upload` → scp 到 root 0700 staging（随机名）→ `ssh quant-agent paper-import <id> <b64名>`：启动器 root 段只做“定长字节复制到 quantagent 收件目录”，随即降权；quantagent 段校验 PDF（魔数、大小、加密、页数，子进程资源限制）、SHA 去重、原子入库、登记。
- **论文库**：`<workspace>/papers/{files/<sha>.pdf, registry.json}`；单用户受控工作区，不宣称多租户。
- **研究**：`paper_research` Skill：`paper_list`（只读）、`qrtk_paper_research(paper, factor)`（确定性管线，内部模型调用计入任务预算）、`qrtk_read_study`。理解/计划/候选按论文 SHA 缓存，复读不再调用模型。

## 5. 审批

- **口径替代**：沿用 v0.8 确认门（程序保存提案、用户原话与模型判断同时为同意才执行、参数指纹绑定）。
- **新代码**：新增 `AWAITING_CODE_APPROVAL`。会话中同一时刻最多一个待批代码对象；用户自然语言“同意/批准”且模型判断一致时，程序以完整 SHA、冻结定义 SHA、合同 SHA、数据范围和 30 分钟有效期绑定批准；随后已知真值测试，通过才注册；代码任一字节变化即失效。不再要求输入 `APPROVE <hash>`。

## 6. 不在本设计中

正式账户回测（仍 BLOCKED）、多租户隔离、操作系统级沙箱、cron 恢复（属于 real_time_product 项目运维，需单独授权）。
