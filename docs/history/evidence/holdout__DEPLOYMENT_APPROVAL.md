> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 最终修复：生产更新一次性批准清单



状态：READY_FOR_DEPLOYMENT_APPROVAL。生产仍是v0.8.0，最新登记报告仍为revision2。



本申请依据本轮指令第六节：正式替换生产生成器、会话逻辑及最新报告指针之前，需要最终确认。候选开发、真实官方DeepSeek SSH验收和公开聚合报告重渲染已经完成。



## 1. 精确代码范围



生产根目录：`/opt/jijigua-quant-agent/research_agent/`。



只更新以下7个Python文件及对应已构建的v0.8.1 wheel；保留其他85个源码/资源文件：



- `src/research_agent/conversation.py`：模型选择只读查询流程、刷新最新报告、旧缓存降为历史来源、仅相同配置的已审定v0.8.0会话绑定升级、科学解释约束。

- `src/research_agent/evidence.py`：压缩最新报告证据，保留Test置信区间和月度标签成熟原因，不发送逐日数组或原始数据。

- `src/research_agent/quant.py`：仅补齐读取结果的明确输出Schema；输入Schema、工具白名单、资源和权限不扩大。

- `src/research_agent/report_versions.py`：指纹验证后的最新版本读取、从已公开回执提取月度成熟状态、仅使用公开聚合文件的报告重渲染。

- `src/research_agent/interactive_report.py`：5类日期轴图连续显示、累计值跨分区延续、两条竖线、实际分区悬浮、静态导出及窄屏独立滚动。

- `src/research_agent/research_report.py`：复用已核验的统计图和聚合数据重渲染；澄清已完成独立Test与普通Test资源封存的区别。

- `src/research_agent/__init__.py`：版本0.8.1。



同步`pyproject.toml`、`README.md`、`CHANGELOG.md`及新增`docs/phase3c_final_fix/`验收文件。文件精确SHA见候选`evidence/final_patch_source_sha256.json`。



wheel：`wty_research_agent-0.8.1-py3-none-any.whl`。



SHA-256：`c59a27d89338a14d783c8656bba8cf55f8fe75700b56d699aac5577132b256ff`。



安装只执行现有虚拟环境的离线`pip install --no-index --no-deps --force-reinstall`，由现有quantagent身份执行。无依赖安装、用户/组/ACL变更或常驻服务。



## 2. 精确报告范围



同一study_id：`INTERNAL_RUN_ID_REDACTED:1339576f3486425d`。



沿用同一evaluation_id：`INTERNAL_RUN_ID_REDACTED`。新增评价次数为0。



拟登记revision3：



`/srv/jijigua-quant-agent/research_runs/2026-10-13/08-48-48_report_revision_3/`



manifest SHA：`5d7ef4309e542a3373e4671a4bdfef62b21b6a7b72c3110353032ef9db48c88a`。



源revision2 manifest SHA：`322d5e5f8d2ca8a79050119d975477a808bd2a49409244590f168aa1cc18df14`。



只在原研究的`reports/report_versions.json`追加已核验revision3条目，并更新其**运行版本索引对应的manifest登记**。在修改前，将两份原始字节分别保存为：



- `reports/report_versions_before_revision3.json`

- `reports/manifest_before_revision3.json`



同时在受保护的部署备份中保留相同字节及SHA。原revision1 HTML/Markdown、PKL、数据、参数及代码不改；revision2目录及manifest完全不改。旧报告和原manifest历史字节永久保留于版本快照，不覆盖其归档文件。



revision3已由公开聚合CSV/签名回执重渲染。原年度/月度/逐日统计CSV未改变；不是新的2026评价。没有Test逐日分组数据的曲线止于Validation。



## 3. 前置检查与操作顺序



1. 核对生产版本、92份源码/资源SHA、官方Provider配置、启动器SHA、原索引及manifest SHA，确认没有正在运行的生产会话；有偏差即停止。

2. 在现有`release_backups/`建立一次性`v080_before_v081_<服务器时间>`备份，保存7份旧代码、旧wheel、项目元数据、索引/manifest、原会话绑定及SQLite一致性备份。数据库备份只用于恢复证据，不覆盖运行数据库。

3. 核验候选wheel和7份新代码SHA，保留既有代码所有者/权限，在现有环境离线安装wheel并原子替换7份对应源码。

4. 核验生产导入版本0.8.1、其他85份源码/资源和全部配置不变，再登记revision3索引。报告文件不重新计算。

5. 通过真正的`quant-agent chat --resume`恢复原会话，以本轮5条短中文进行最终生产验收。每条仅允许`qrtk_read_study`，不得调用计算、导出或独立测试工具。

6. 保存正式入口转录、Token/延迟、工具与授权记录、最新revision3读取证据、历史指纹和部署记录。



## 4. 测试依据



- 完整Windows：324通过、1跳过（Windows符号链接权限）；完整Linux：324通过、1跳过（可选pyarrow缺失）。

- 最后输出Schema修复：Windows7项通过、Linux39项通过；非法输出字段仍被拒绝。最终渲染另有聚合数据、累计曲线、热力图及历史不变自检。

- 官方DeepSeek真实SSH候选：5条自然中文全部自动调用一次只读工具；追加研究判断验收避免将区间跨零解释为已证明失效。

- 首轮5条因输出Schema缺少版本字段而失败的原始转录、参数与账本已保留，不计为通过。

- 所有候选CLI均使用现有quantagent身份、现有Linux环境及真实官方API；仍不是已更新的生产入口。



## 5. 回滚



任一步失败即停止后续步骤。恢复备份7份源码、旧0.8.0 wheel及项目元数据；恢复原最新索引与其运行manifest。revision3及全部失败/验收文件保留，不删除报告。



不恢复整库覆盖当前SQLite；保留新增查询任务、消息与Token记录。仅将这次升级过的、配置仍一致且未处于运行中的会话绑定恢复到备份的旧绑定，追加回滚记录，不复用旧执行授权。新版本创建的会话如需继续使用，须按相同Provider/配置核对后处理，不能任意改绑定绕过配置校验。



代码和索引备份均有SHA，回滚后再次核验旧版本导入、原报告可读及原配置不变。



## 6. 明确不包含



不读取或发布2026私有行情/标签/逐股票数据；不重算因子、IC/RankIC或独立Test；不改变评估账本、签名材料、曝光次数及剩余预算；不改数据源、发布版本、ACL、官方API/Key、启动器、Claude项目或正式Backtest的BLOCKED状态。



`/hy-tmp`仍是临时存储。保留本地候选源码、wheel、公开报告和验证证据；不自动向外部备份平台上传。

