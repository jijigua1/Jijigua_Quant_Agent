> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2-C 最终生产部署确认



**已获用户批准并执行。** v0.7.0于2026-10-12完成部署及正式入口真实SSH PTY验收。详细记录见PHASE3B2C_FINAL_REPORT.md、production_deployment.json和production_acceptance.json。以下保留原审批精确范围及回滚要求。



## 精确变更



1. 仅在 `/opt/jijigua-quant-agent/research_agent/` 内保存v0.6.8代码/config/deploy的可回滚副本（root管理）；已有0.6.8轮子原件SHA `8752477363bdf6a186a1aee045c2b443b98607a177dfe467905592096db1ecf5`，不重新打包原版。

2. 更新该项目src快照、版本/README和既有venv内wty-research-agent包至审定0.7.0轮子（`--no-index --no-deps`），不安装新依赖、不碰其他项目/服务。

3. 替换该项目 `config/resources.json`、`config/research.json` 为候选已核验清单：两个固定发布ID，Train/Validation SHA如最终报告。旧daily20/daily65元数据保留但本profile不再读取2026；这是为避免旧工具旁路的明确兼容性变化。

4. 仅更新该项目 `deploy/launcher.py` 的root降权附加组：从清空组改为保留**既已获批、已存在的quantdata GID998**。不改账号、组成员、ACL或原始数据权限。已核验`/usr/local/bin/quant-agent`由root管理（0755）并引用该脚本；该命令文件保持原样，root SSH使用习惯保持。

5. 沿用原来的官方DeepSeek配置、隐藏Key输入、`var/state` SQLite与既有研究记录。部署不迁移/覆盖这些记录，不新建Worker/cron/systemd，不发布任何2026数据，不注册正式回测Tool。

6. 替换后执行一次root启动器→UID999→真实中文全量研究的最终验收；若关键门失败，恢复旧源码/config/launcher并用原0.6.8轮子离线回装。失败的新研究产物保留独立目录，不删旧成果。



候选轮子 SHA `2f7ab6ea38d500062fa6759789f40f16b44560d5a44cbbe0d99d789273aa22fa`。逐文件变更清单见change_manifest.json。



## 回滚



恢复备份的整个src快照（新增候选文件移至此次部署备份，不覆盖旧快照），恢复两个配置、launcher和版本文件；既有venv离线安装原0.6.8轮子。保持数据库原位；如需回滚数据库结构，本次没有Schema迁移，禁止倒灌备份覆盖新的历史记录。



## 需明确知道的影响



- 正式`quant-agent chat`在批准前仍是v0.6.8，尚不能通过正式入口使用长期发布分区。

- 新profile主动封住旧daily65/daily20的2026数据读取，但历史status/result/logs继续可查。旧会话配置绑定发生变化时只能查看历史，不能假装恢复旧授权继续执行。

- 数据仅探索性，未复权/上市/PIT/交易能力等风险不变。Validation已曝光。2026此前也有旧样本曝光，不能追溯恢复独立盲测。

- 当前前台研究不是硬沙箱或后台持久任务，/hy-tmp产物须备份。



用户批准：批准上述精确部署范围。已按该范围执行；没有新增系统权限或开放2026数据。

