> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# v1.0 Beta 质量更新：集中生产审批申请

日期：2026-10-14　申请人：Claude（与 Codex 共用工作区）　状态：**待 Kevin 批准，尚未部署**

本次申请把已在隔离预发布环境 `v1rc` 完成验证的修改，一次性部署到生产 `v1beta`。生产代码在提交本申请时与其 169 文件清单完全一致（`sha256sum -c` 通过），没有任何改动。

## 1. 部署范围（13 个文件，仅限 `src/` 与 `deploy/`）

| 文件 | 生产 SHA → 候选 SHA（前 12 位） | 实际改动行 | 作用 |
| --- | --- | --- | --- |
| `src/paper_research/candidate.py` | `959073a5b44b → 987cac66973c` | +96 −12 | **安全闸门**：静态审核误报的最小修正（详见第 3 节） |
| `src/research_agent/conversation.py` | `dec39b09850e → 117c088adda2` | +39 −5 | 暂停/待确认提示、Ctrl+C 中断文案、显著性一致性检查、论文路由 |
| `src/research_agent/economic_rationale.py` | `a9986fb4a77a → a33e77eb13af` | +21 −1 | 段落编号 `P0010 p2` 严格解析（页码必须与段落真实页一致），版本号 /4 |
| `src/research_agent/significance.py`（新增） | — → `baee9b3990dc` | 68 行 | 按 RankIC HAC 95% 区间程序判定显著性，检出摘要与数字矛盾 |
| `src/research_agent/evidence.py` | `ac2b2a057cf9 → 93ab3801082f` | +9 −1 | 论文阻断原因、论文列表进入证据白名单；去掉会诱发“SEALED”措辞的 `access` |
| `src/research_agent/paper_library.py` | `3ab510656989 → d4ac3c3a52dc` | +10 −4 | 标题去模板占位；按作者/机构/关键词加权解析；“继续刚才”指向最近研究 |
| `src/research_agent/paper_tools.py` | `b200b5f692af → 2058a739491c` | +69 −1 | 阻断原因中文说明、候选论文列表；丢失审核请求时按原 SHA 重建（不运行代码）；JSON 故障注入只在测试主机生效 |
| `src/research_agent/report_explain.py`（新增） | — → `59760a2378c8` | 321 行 | G0–G4 分组源码逻辑说明、HAC、单调性、解读；方法说明；局限中文映射 |
| `src/research_agent/research_report.py` | `5143fe032001 → 4ce90f3c3b7b` | +72 −35 | 经济逻辑章节拼接修正、分组章节、方法说明、静态图中文与 CJK 字体 |
| `src/research_agent/interactive_report.py` | `e481fb8c77dd → bfc75739d64f` | +64 −49 | 交互图中文标题/图例/坐标、热力图 CJK 字体、`2026.0000` 修复、未评价 Test 标题 |
| `src/research_agent/report_test_figures.py` | `676ae3a7b8a7 → cde1e1c3897b` | +31 −39 | 滚动修订静态图中文化、CJK 字体、持续性图由已存统计重绘 |
| `deploy/configure_v1.py` | `44909e858653 → 6f9b9192854b` | +19 −7 | `--name v1rc` 与 `--test-fault-injection`（对 v1beta 拒绝） |
| `deploy/launcher_v1.py` | `05b5e7c97b95 → 5f857f69519b` | +6 −3 | 仅当 root 所有的 host.json 声明测试标志且根目录不是 v1beta 时注入一次 JSON 故障；生产 host.json 无此标志 |

完整候选清单：`docs/release_v1_sha256_candidate4.txt`（171 行 = 原 169 + 2 个新文件），SHA-256 `f3b8205954e99fb27458d5d8bf8510ad2d70d7c49e25385c998d98744046ca8b`。生产现行清单快照：`docs/release_v1_sha256_production_20261013_hotfix.txt`（`342a78a9…`，已含 broker/evaluator 热修复）。本地旧的 `docs/release_v1_sha256.txt` 是热修复前版本，不作依据。

**不在范围内**：cron、supervisord、`quant-agent` 入口与 `quant-agent-v082`、`broker.json`（保持 authorized=true）、用户与用户组、私有 2026 行情与快照、回执与账本、`/srv/jijigua-quant-agent/test_evaluator/phase3c_v1`、Codex 目录、历史研究目录与转录。`tools/` 下的 quant-paper 与验收脚本是客户端/操作员工具，不部署到生产。

## 2. 部署与回滚方式

- 部署：`deploy/apply_quality_update_v1.sh <批准编号>`（root）。
  1. 先核对生产清单 SHA，以及候选清单与预发布 13 个文件逐一对应审定 SHA。任何一项不一致即停止。
  2. 备份被替换的 11 个文件和原清单（带校验表）。
  3. 原子替换文件（root:root 0644），换上新清单，旧清单另存为 `.deploy3.txt`。
  4. 全量 171 文件校验。
  5. 以 quantagent 身份做导入冒烟，再运行合成数据 OS 级滚动自检 `selftest_rolling.py`。
- 回滚：`deploy/rollback_quality_update_v1.sh <备份目录>`。先校验备份，再恢复 11 个文件和原清单，删除 2 个新增文件，最后验证 169 文件清单。已生成的报告修订作为记录保留，不删除。
- **演练证据**（在 `/root/qa_deploy` 生产副本上执行，结束后已删除）：apply 后 171 文件全部一致；rollback 后副本与生产逐字节相同（`diff -rq` 无差异）；全程生产清单校验通过（`PRODUCTION_UNTOUCHED`）。演练中发现并已修复两个脚本缺陷：`python -I` 会忽略 PYTHONPATH，导致导入冒烟失败；备份校验表曾包含自身，导致回滚拒绝执行（这一点正是安全阀生效）。

## 3. 安全闸门变更（静态审核）：补丁、边界与证据

问题：R3 中的真实 MA 候选代码（a29fff68）被误判。具体有两处：

- `for k in range(5, 265): shift(k)` 的回看范围无法推出；
- 已用 `.replace(0, nan)` 保护的分母被当作“不确定分母”。

修正只在 AST 层做**可证明**的放宽：

- 只有当循环变量唯一绑定到字面量 `range(a, b[, s])`（或唯一绑定到 `range(...)` 的名字）、且 `range` 未被重新绑定时，才推出 `shift` 的最小/最大值；其最大值计入 `max_lag`。
- 推出的最小值 < 0 → 仍判 `NEGATIVE_SHIFT`（未来数据）；推不出且为一元负号 → 仍判 `NEGATIVE_SHIFT`。
- 分母只在三种情况下视为安全：调用了 `.replace/.where/.mask`；非零数字字面量；只赋值一次、且值为上述两者之一的名字。字面量 0 现在会被标记。
- 未改变：非法导入、文件访问、`eval/exec`、网络、未知属性等全部拒绝规则；用户批准、独立真值测试和可信 IR 交叉核对都保留；未增加任何执行权限。

测试（`tests/test_v1beta_static_review.py`，6 项）：

- 正例：真实 R3 候选按声明的回看范围通过；等价向量化写法也通过。
- 反例：循环中读取未来数据被拒绝；无法证明或错误的窗口仍然失败关闭；只有可证明安全的分母被接受；其他拒绝规则不变。

真实运行（v1rc，Q5）：

- 含糊答复“这段代码看起来还行吧”被拒绝，代码没有运行。
- “同意”后，系统按原 SHA 重建审核请求，独立真值测试通过，再与可信 IR 交叉核对，然后才运行。

风险：放宽仅限“字面量 range 循环”和“显式保护的分母”两类模式。其他写法仍会被拒绝，可能导致新论文代码继续被阻断。这属于可接受的误拒，不会造成漏放。

## 4. 测试证据

- 本地 Windows：`tests/test_v1beta_*.py` 73 通过、2 跳过（`grp` 和符号链接在 Windows 下不可用）。
- 预发布 Linux（quantagent 身份、隔离 HOME、最终字节）：132 通过、0 失败（650 s）。
- 真实 DeepSeek 预发布稳定性矩阵 Q1–Q6：交付报告第 2 节。
- 真实浏览器验收：GH 52 周高点三阶段报告（生产真实回执 7b4aea07 的 QA 副本）和 MA 预发布报告，修复前后截图都在 `docs/v1beta/live/qa_html/screens/`。独立数值核对 17 项全部通过。

## 5. 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 报告渲染改动引入新的显示问题 | 新报告或修订的可读性 | 已在两份真实报告上逐章截图核对；一致性校验 PASSED；可一键回滚 |
| 静态审核放宽 | 理论上可能放过错误代码 | 只放宽可证明安全的两类模式；正反例测试；人工“同意”、真值测试、IR 交叉核对三道关保留 |
| 部署中途失败 | 生产代码处于半更新状态 | 每步 `set -e`；先备份；回滚脚本已演练 |
| 已冻结研究的经济逻辑为旧版本（v3） | GH 报告中“锚定”机制仍标“作者归属未经原文核对” | 这是正确的保守标注；新研究使用 v4 生成 |

## 6. 请求批准的事项

1. 用 `deploy/apply_quality_update_v1.sh` 把上述 13 个文件部署到生产（批准编号由 Kevin 指定，例如 `KEVIN-20261014-V1-QUALITY`），失败时按回滚脚本恢复。
2. 部署后，由 Kevin 在生产 CLI 中对 Amihud 研究说一句“给我看Train、Validation、Test结果”。这会走已授权的 C1 滚动通道，签发 Amihud 的第一张 2026 回执（属于正常使用，不是新增权限），之后完成 Amihud 报告的浏览器截图验收。

未经批准，以上两项都不会执行。
