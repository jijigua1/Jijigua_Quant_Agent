> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 第一阶段（论文理解稳定性）状态冻结记录：2026-10-15

**状态：`IMPLEMENTED / OFFLINE_TESTED / LIVE_VALIDATION_BLOCKED_BY_PROVIDER_OUTAGE`**（不是 PASSED）

最新一批修复（阅读器 `paper_agent.understanding/5`、规划器 `planner/4-reconcile-parameters-numbered-factors`）尚未经过真实 DeepSeek 端到端验证。2026-10-15 11:10 的重跑遇上 DeepSeek 官方 API 部分中断（状态页：Web/API Partially Unavailable，涉及 V4.1 Flash API、V4 Pro API 与对话服务），所有调用都超时。在服务恢复并通过最小化健康检查之前，不再发起任何真实 API 测试。

## 1. 代码指纹

| 位置 | .py 文件数 | 聚合 SHA-256（`tools/src_fingerprint.py`，按“相对路径\0字节”排序累加） |
| --- | --- | --- |
| 本地 `agent_v1beta/src`（冻结时） | 107 | `a8ebf1afb3491bb39d3a1805f990294e0fee76d7a3bf33fbc7de93f1890dbd5c` |
| 预发布 `/opt/jijigua-quant-agent/v1rc/src` | 107 | 同上 |
| 生产 v1.0 Beta | 169 文件发布清单 | `342a78a9…`（Codex 审计确认无漂移，本轮未触碰） |

说明：

- 冻结后本地又改了两处（第二阶段开始前），新指纹以第二阶段文档为准：
  - `paper_tools.py`：服务商故障单独归类；
  - `conversation.py`：超时、网络错误、服务端错误、限流的中文提示。
- 冻结的 candidate4 仍保存在 `docs/v1beta/candidates/candidate4_20261014`，没有改动；下一候选必须重新生成完整清单。

## 2. 回归结果（离线，不代表真实验收）

| 环境 | 结果 |
| --- | --- |
| 本地 Windows | 452 通过，2 失败（既有：phase2b 表达式 handler、phase2c 导出一致性；修改前的代码同样失败）；launcher 测试仅限 Linux |
| 预发布 Linux（以 quantagent 身份，临时目录在 /hy-tmp） | 462 通过，同样 2 项既有失败 |
| 新增 `test_v1beta_reconcile.py` | 33 项 |

## 3. 真实运行记录与计数口径

| 运行 | 位置 | 计入 |
| --- | --- | --- |
| A/B 第一次（10-14 21:28 / 21:30） | `docs/v1beta/live/ab_20261014_212830/`、`ab_20261014_213009/` | 计入（当时口径不同，见 05 第 7.4 节） |
| A/B 第二次（10-14 22:31，每案例 2 次） | `ab_20261014_223100/`（含 consistency.md） | 计入（阅读器 /4） |
| J1–J6（10-14 21:45、22:50） | `J*_STAGING_*.20261014_2*.txt` | 计入 |
| A/B 与 J1–J6（10-15 11:10） | `ab_20261015_111013_deepseek_outage/`（含终端转录） | **服务商故障，不计入**：所有调用都等满 60 秒 TIMEOUT，0 次有效调用 |

**计数原则**：服务商的超时、网络错误、服务端错误和限流单独记为“服务商故障（不计入）”，不进入论文理解正确率、错误放行率或工程失败率。对比脚本的判定、Agent 的中文回复和论文工具的失败码现在都按这一口径区分（`MODEL_PROVIDER_UNAVAILABLE`）。

## 4. 尚未解决或未经真实验证的问题

1. 以下修复只有离线回放和单元测试证据，没有阅读器 /5 的真实运行证据：GMI 独立二次读取、Alpha#12 编号精确匹配、AQR 标识定位、规划模型必须调用论文工具、中文研报字节预算、资产短语提示、sign 容差、MACD 复权口径、RSI 频率证据、多因子由用户选择。
2. JSON 结构修复覆盖率：离线 46/53（87%），其余请模型带精确提示重答，真实效果未复测。
3. 重复运行一致性：阅读器 /4 为 7/26 漂移，阅读器 /5 尚未测量。
4. CMI 的浮点并列：排序翻转和分组边界的影响尚未量化（第三阶段数值复核中完成）。
5. sign 容差改变了可信执行器的数值语义，需要明确计算版本和旧研究复用规则（第二阶段 F 项）。

## 5. 恢复后的验收步骤（服务恢复后按顺序执行）

1. **最小化健康检查**：`python tools/paper_ab_remote.py --health`。只发 3 个极小 JSON 请求，每个须在 20 秒内返回合法 JSON，全部满足才输出 `PROVIDER_HEALTHY`。不能只凭状态页告警消失就判断已恢复。
2. 新旧对比：`python tools/paper_ab_remote.py dev,exposed,holdout2`（默认每案例 2 次，带运行锁、实时进度和 Ctrl+C 取消，结果记录源代码指纹与论文 SHA）。
3. 端到端：`python tools/live_v1.py J1_STAGING_params J2_STAGING_condmat_ma J3_STAGING_blocks_cn J4_STAGING_exposed J5_STAGING_holdout2 J6_STAGING_holdout2b`（会话定义见 `tools/live_v1.py`，每个会话不超过 4 篇论文）。
4. 必须逐一确认的关键案例：GMI、AQR、RSI（含 X=14）、MACD、Alpha#12（及 #101）、CMI、hans（资产短语）、华泰（中文长文）。
5. 对新产生的成功研究运行独立数值复核（`tools/numcheck_study.py`）。

**第一阶段通过之前，不申请新版 Quant-Agent 的生产部署。**
