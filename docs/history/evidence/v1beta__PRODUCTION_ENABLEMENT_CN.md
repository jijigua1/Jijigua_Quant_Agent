> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# v1.0 Beta 生产启用 · 一次性授权清单（2026-10-13）

本清单一次覆盖三件事：恢复每日行情更新、把生产入口切换到 v1.0 Beta、开启默认自动的 2026 滚动 Test。批准后由 root 执行 `deploy/enable_production_v1.sh`，回滚使用 `deploy/rollback_production_v1.sh`。下文“已核实”指 2026-10-13 18:36–18:50 在服务器上只读检查的结果。

## 1. 现状（已核实）

| 项目 | 事实 |
| --- | --- |
| 行情停更原因 | 容器 2026-10-11 16:08 重启；PID 1 为 `tini → supervisord`，supervisord 只管理 jupyterlab、sshd、tensorboard，**cron 守护进程没有被拉起**。root crontab 中 `0 19 * * * /home/real_time_product/scripts/run_daily_pipeline.sh` 仍在，未被改动。 |
| 最后一次成功 | `PIPELINE_DONE target_date=20261009 status=success`（10-09 19:26）；10-10 为非交易日，正常跳过。 |
| 漏跑 | 2026-10-12（周一）；2026-10-13 的 19:00 运行同样不会发生。 |
| 数据截止 | `/hy-tmp/data/daily_update/close.pkl` 最后日期 20261009（1882 × 5427）。源文件为 root 0600。 |
| 管线能力 | `daily_pipeline.py` 支持 `--date YYYYMMDD`、`--no-email`，自带 `flock` 防重入锁。 |
| 生产入口 | `/usr/local/bin/quant-agent`（SHA-256 `b3655e36…c009`）→ `research_agent/deploy/launcher.py`（v0.8.2）。 |
| 滚动通道 | 已部署在 v1 隔离副本：`broker.json` 中 `authorized=false`、`approval_ref=NOT_YET_APPROVED`；快照目录为空；quanteval/quantpub/quantagent 身份与目录权限已就绪。 |
| 一次性评价 | Codex 的 `/srv/jijigua-quant-agent/test_evaluator/phase3c_v1` 不在 v1 的任何读写路径中。 |

## 2. 请求批准的全部变更

| # | 变更 | 前 | 后 | 归属 |
| --- | --- | --- | --- | --- |
| A1 | 新增 `/etc/supervisor/conf.d/cron.conf`（`/usr/sbin/cron -f`，autorestart），`supervisorctl reread/update cron` | cron 未运行 | cron 由 supervisord 常驻，容器重启后自动恢复 | 系统服务配置；**不改** real_time_product 的代码、crontab、密钥 |
| A2 | 用产品自己的入口补跑：`run_daily_pipeline.sh --date 20261012 --no-email`，然后 `--date 20261013`（正常发送当日邮件） | 数据止于 10-09 | 补齐 10-12、10-13；同时按管线正常行为生成当日评分和仓位计划产物 | real_time_product 的既有行为，以 root 运行（与 cron 相同） |
| B1 | 备份 `quant-agent` 为 `/usr/local/bin/quant-agent-v082`，把 `quant-agent` 改为执行 `/opt/jijigua-quant-agent/v1beta/deploy/launcher_v1.py` | v0.8.2 | v1.0 Beta（`quant-agent-v082` 可随时回到 v0.8.2） | 生产启动器 |
| C1 | `v1beta/deploy/rolling/broker.json`：`authorized=true`、`approval_ref=<批准编号>` | 关闭 | 每次研究自动做 2026 滚动评价；读取研究时遇到新快照自动追加新修订版 | v1 部署配置（root 0600） |

**以下内容不变更：** v0.8.2 代码、状态与工作区，Codex 的 v0.8 开发，Codex 的一次性 2026 评价，原始行情，`data_releases`，`daily_update` 文件权限，用户与用户组，sudoers；也不新增其他服务。

## 3. 2026 滚动 Test 的权限模型（已实现，批准后启用）

| 角色 | 能做什么 | 不能做什么 |
| --- | --- | --- |
| quantagent（普通 Agent） | 运行研究；通过继承的 socket 只能发出 `status` / `evaluate(study_id, 研究目录)` 两种请求；读取 root 登记的回执（root:quantagent 0440） | 读快照、密钥、评价账本；读 `daily_update`；伪造回执（只接受登记表中、且不属于自己的回执） |
| root 代理（launcher fork 出的父进程，仅随会话存在） | 校验请求和研究目录（lstat 逐级检查，O_NOFOLLOW）；需要时发布快照；以 `runuser -u quanteval` 调起评价器；校验 HMAC 回执并登记；写哈希链审计日志 | 执行模型代码（新算法一律由可信 IR 重算） |
| quantpub | 在 root 预先打开的文件描述符上读取源数据，写入暂存区 | 自行打开 `daily_update`（文件仍为 root 0600） |
| quanteval（997） | 读私有快照与密钥（root:quanteval 0750/0440），写评价账本与回执草稿 | 写已登记的回执；访问 Agent 工作区 |

快照按“六个源文件指纹 + 认证截止日”寻址；数据不变则复用，有新交易日则发布新版本。末日覆盖率低于前 20 日中位数 90% 时剔除该日，不作填补。与 Validation 重叠的 60 个交易日必须逐值一致，否则判为 HISTORY_MISMATCH，不出 Test 数值。同一（定义 SHA、快照、合同）只评价一次并复用结果。报告一律标记 **ROLLING_EXPOSED_TEST（持续曝光，不是盲测）**，未成熟标签显示为 NaN 并注明原因。程序不提供依据 Test 结果选择参数的路径。

## 4. 部署前由我完成、无需另行授权的代码项

1. **静态图覆盖 Test**：滚动修订版目前只重画交互图族（时间序列、热力图、覆盖率，均已含 Test，并导出 PNG/SVG/PDF）；`ic_distribution`、`group_returns_gross` 等静态图仍复制 rev1，只覆盖 Train/Validation。部署前改为：能从回执得到的 Test 数据进入同一张图；得不到的（Test 期因子值不对 Agent 开放、Test 衰减未计算）在图注中写明原因。
2. 生成 `docs/release_v1_sha256.txt`（src/deploy 全部文件的 SHA-256）；启用脚本第 0 步逐一校验，代码与清单不符即停止。
3. 在服务器上以 quantagent 身份重跑 v1 定向回归（上一轮 105/105 通过）。

## 5. 批准后的执行顺序

```bash
bash /opt/jijigua-quant-agent/v1beta/deploy/enable_production_v1.sh KEVIN-20261013-V1-PROD 20261012:no-email 20261013
```

1. 第 0 步：前置校验（代码 SHA、v0.8.2 入口原样、身份与目录权限、一次性评价目录存在）。
2. 第 1–2 步：恢复 cron、补跑 10-12 与 10-13，打印 `daily_update` 新的截止日。
3. 第 3–4 步：切换生产入口，开启滚动通道。
4. **首轮真实评价**：在 `quant-agent chat` 中输入“研究George和Hwang那篇52周高点论文。”。这个冻结定义（`P/ts_max_252(P)`，代码 `f0d6c9475302` 已批准）从未做过任何 2026 评价，且已有确认记录，不会重复解析或审批。预期结果：快照 `rolling_<截止日>_<指纹>` 发布 → quanteval 评价 → 回执登记 → 报告修订版 2，Train/Validation/Test 都有真实数值。
5. 我的独立核验：以 root 从私有快照重算 Test 日度 IC/RankIC 并与回执比对；核对审计链、账本唯一性、尾部未成熟标签为 NaN、一致性检查 PASSED，以及 HTML、PNG/SVG/PDF 的 Test 段。核验只用于验收，不用于调参。
6. 新交易日到来后：19:00 管线更新数据；下次研究或读取研究时自动发布新快照，并追加新修订版，旧修订版不变。

## 6. 回滚

```bash
bash /opt/jijigua-quant-agent/v1beta/deploy/rollback_production_v1.sh            # 入口回到 v0.8.2、关闭滚动通道、移除 cron 程序
bash /opt/jijigua-quant-agent/v1beta/deploy/rollback_production_v1.sh --keep-cron  # 只回滚 Agent，保留每日行情更新
```

回滚保留所有研究成果、快照、回执、账本与审计日志作为证据；不触及 real_time_product 与原始数据。

## 7. 仍需注意

- 补跑 10-12、10-13 会按管线既有行为生成这两天的评分与仓位计划产物；10-12 不发邮件，10-13 正常发送。若你希望 10-13 也不发邮件，把命令中的 `20261013` 改为 `20261013:no-email`。
- 滚动 Test 是持续曝光的样本外观察。2026 的结果会随新交易日变化，不能作为严格未见盲测。
- 论文第三轮验收（MA 论文、暂停/恢复、模糊回答闸门）在部署后继续进行。
