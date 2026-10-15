> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# v0.8.0 生产部署审批与回滚清单



经用户最终批准，正式入口已更新为 v0.8.0；实际安装证据见production_deployment.json，正式入口验收结果见production_acceptance.json。候选在 `/srv/jijigua-quant-agent/research_runs/2026-10-12/23-43-16_v08_candidate/` 以 quantagent 独立验收。本文请求的部署范围不包含任何真实2026数据发布或解封。



## 精确修改范围



1. 仅在 `/opt/jijigua-quant-agent/research_agent/` 中新增 root 管理的 `release_backups/v070_before_v080_<服务器时间>/`。保存当前 src、pyproject.toml、README、CHANGELOG、config、deploy、已存在 v0.7.0 wheel 及逐文件SHA。备份不包含密钥，不覆盖/迁移 SQLite；如备份运行中数据库，只用 SQLite 在线 backup，回滚不倒灌历史记录。

2. 将审定 v0.8.0 wheel 与 src 快照、版本/README/CHANGELOG、v08交付文档同步到本项目；仅既有 venv 执行 `pip install --no-index --no-deps --force-reinstall <审定wheel>`，不联网安装依赖。新Python模块、factor-report/2 Schema、factor_research声明、已批准Skill指纹和离线Plotly资源清单见 `source_manifest.json`。

3. **不修改** `/usr/local/bin/quant-agent`、项目 launcher、两个生产资源配置、官方DeepSeek配置/隐藏Key方式、quantdata组、系统用户/ACL、原始行情、不可变Train/Validation、数据库Schema或旧研究产物。

4. 继续由root Shell的 `quant-agent chat` 可信启动器降权为quantagent。候选不新增常驻进程/cron/systemd、不注册真实Test数据读取Tool、不开放正式Backtest。

5. 生产更新后只做一次正式入口验收：普通对话→完整五日反转报告→Test申请保持SEALED→拒绝2026调参。保存任务/会话和产物SHA；不因验收开放新资源。



审定 wheel：`wty_research_agent-0.8.0-py3-none-any.whl`。



SHA-256：`dfd3508fd3004d476df48268b9d3be459ad24356bad96c948542c46613600978`。



## 回滚步骤



停止此次前台候选验收后，恢复备份的 v0.7.0 src 与版本文件；v0.8新增源码移到此次备份内，不删除历史研究记录。既有venv使用已保存原v0.7.0 wheel离线回装（SHA `2f7ab6ea38d500062fa6759789f40f16b44560d5a44cbbe0d99d789273aa22fa`）。配置和launcher原本不变，逐SHA核对；数据库不迁移也不回灌。新增报告仍保留独立目录，旧status/result/logs可查。



## 用户会感受到的变化与限制



- 每份新报告从创建时就含Train/Validation/Test；真实Test未批准时为NOT_RUN / SEALED、2026热力图N/A。

- 合成验收通过的签名结果合并入口不开放为模型Tool；真实Test身份、快照、传输和首次曝光另行审批。

- 代码版本绑定改变，旧会话可查看但不能以旧授权直接继续执行；新建chat不影响既有账本。

- 完整研究通常约一分钟级确定性计算，新增静态/交互图表和统计有真实开销；性能证据见PERFORMANCE.md。无新增Linux依赖。

- 原始未复权、历史上市/PIT/交易状态不足，仍为探索性数据，正式账户回测BLOCKED。前台SSH断线不保证继续；`/hy-tmp`产物需用户备份。



用户已明确回复“批准这份精确部署清单”。正在按以下范围执行；实际结果以production_deployment.json、production_acceptance.json为准。详细最终测试及真实报告证据见 `V08_FINAL_REPORT.md`、`TEST_RESULTS.md`、`live_acceptance.json`。





实际v0.7.0回滚备份：`/opt/jijigua-quant-agent/research_agent/release_backups/v070_before_v080_20261013_013133`。配置、启动器、数据库inode保持不变；未修改系统身份或数据ACL。

