> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 生产最终修复与验收

交付状态：**PRODUCTION_FINAL_ACCEPTED**。生产 Research Agent 已更新为 **v0.8.2**，现有五日反转研究最新综合报告为 **revision4**。用户批准的5模块、wheel、只读报告目录配置及报告指针范围已执行。核心功能和自然语言验收通过；本报告保留非关键模型措辞及采集器问题，不宣称每一句生成文字均无瑕疵。

## 1. 实际部署

生产代码：`/opt/jijigua-quant-agent/research_agent/`。

使用方式仍为 root SSH 登录后执行 `quant-agent chat`，启动器内部保持 quantagent 非root运行。Provider为deepseek，实际模型deepseek-flash，接口`https://api.deepseek.com/chat/completions`；原API配置、密钥读取、启动器及数据权限未修改。

只修改 __init__.py、conversation.py、evidence.py、interactive_report.py、quant.py及获批wheel/项目文档；具体修改前后SHA见candidate/evidence/v082_patch_source_sha256.json。新config/report_catalog.json为root:quantagent、0640，只登记本轮已有公开五日反转研究，不是2026行情Resource，也不导入其他SSH会话聊天记录。

wheel SHA-256：`aad21f2d2b538635cd6413b378ff1b25e8af5f7d42fdec13c4b85912f5c32715`。

报告目录配置SHA-256：`39448e8e5df166ad2450c659eb3f2ab1fa9eb5412aeed625290a4832f269d0c3`。

## 2. 最新真实报告

同一study_id：`INTERNAL_RUN_ID_REDACTED:1339576f3486425d`。

HTML：`/srv/jijigua-quant-agent/research_runs/2026-10-13/12-07-19_report_revision_4/reports/report.html`。

Markdown位于同目录的report.md。manifest SHA-256：`ab469a42d196727b294c97b8ce45ca0c082c62fc2e0126689b4fdc96c298ede5`。

revision4仅重渲染已批准公开统计，与原签名评价evaluation_id相同。年度、月度、IC/RankIC、标签成熟、分区参数均未改动。原因子PKL仍位于`/srv/jijigua-quant-agent/research_runs/2026-10-13/01-33-21_reversal_5d/data/factor.pkl`，未重写。

## 3. 连续图表

所有日期轴图使用统一真实时间范围及两条Train/Validation、Validation/Test分界线；IC、RankIC、滚动、覆盖率和累计曲线遵循同一规则。累计值跨分区继续累计，真实NaN保留缺口；HTML connectgaps=false，PNG/SVG/PDF由同一数值绘制。不存在的数据不插值，不零填充，不连接跨越缺口。

没有获批Test逐日分组收益，因此分组曲线止于Validation；Test区域不虚构线段。非日期轴图保留原含义。累计相关不是账户NAV，理论毛收益不是可执行净值。

实际桌面、390px窄屏、PNG及独立栅格化PDF均已查看。窄屏只在图表容器内滚动，页面无整体横向溢出。截图及PDF检查位于candidate/evidence/screenshots/。SVG/PDF/PNG同figure导出且指纹通过；SVG没有另做浏览器截图。

## 4. 正式自然语言验收

在真实GPUShare PTY中运行正式`/usr/local/bin/quant-agent chat`，官方DeepSeek实际调用；没有向模型输入标准答案。12条主矩阵及1条恢复新会话重复查询通过：

- 恢复原历史会话，首次询问五日反转现状。
- 新会话执行用户指定的8条中文问题，不输入study_id或工具参数。
- 旧SEALED状态提醒仍自动刷新revision4。
- 2026原始价格/收益标签调参请求被拒绝。
- 其他用户未共享私有研究被拒绝。
- 恢复同一新会话重复询问10月N/A，仍读取revision4。

10条主矩阵合法查询及1条重复查询各只执行一次qrtk_read_study。两条越权请求没有工具调用。原/tasks中的历史实验名称仅是已有记录展示，不是本轮新增评价。

完整原转录：candidate/evidence/production_final_cli.txt、production_repeat_cli.txt。原结构记录及真实工具参数：production_final_results.json、production_repeat_results.json。正式数据库原回答和284条审计事件：v082_production_integrity.json；逐条人工语义审核与数值校验：production_final_semantic_review.json；便于阅读的用例表：candidate/docs/NATURAL_CLI_TEST_MATRIX.md。

恢复/失败范围：真实历史会话与新会话恢复均通过；模型失败、Ctrl+C、EOF、未知用量、预算停止以已有定向回归验证。没有在正式API请求中故意制造中途SSH断线；仍不能保证运行中的前台任务断线后继续，不把这一点描述为后台持久运行。

## 5. 数值与科学语义

| 分区 | IC Mean | RankIC Mean | 有效评价日 |
|---|---:|---:|---:|
| Train | 0.020367376934 | 0.026380421612 | 959 |
| Validation | 0.043337659475 | 0.046300839332 | 479 |
| Test | -0.000863362188 | 0.004014245450 | 177 |

数值来自已保存的公开逐日聚合CSV独立复算，容差1e-12；168个IC/RankIC热力图格与月度CSV一致。没有读取私有Test矩阵或重新计算因子/标签/IC。证据：r4_independent_public_statistics.json。

Test有183个观察日，但177个有效评价日；2026年10月2个观察日均缺少成熟H=5标签，月度IC/RankIC为N/A，不是缺行情，也不是0。Test RankIC HAC区间[-0.034185158189,0.042213649089]包含0，当前证据不足以证明可靠预测能力，也不足以断言能力消失。

Agent能正确说明Validation均值高于Train、Test较弱且不确定，不杜撰市场原因。结果为已曝光的回顾性探索性统计，不是严格盲测、因果证明或真实账户回测。正式回测继续BLOCKED。

## 6. 回归与历史保护

复用此前Windows/Linux完整回归各324通过、1跳过证据；这不是本次5模块变更后重新运行的完整套件。受影响的样本数、只读报告共享、会话、版本与统一报告定向回归：Windows40通过、Linux40通过。最终真实缺口/报告回归：Windows8通过；Linux真实公开报告重渲染及统计、热力图、累计语义、历史SHA自检通过。

最终生产完整性核验：291条部署前任务payload不变，数据库inode和Schema不变；92份原研究产物不变；安装wheel的92份文件逐项SHA通过；原resources.json、research.json、Provider、launcher及其他源码不变。新共享配置所有者/权限正确。revision2/3/4各74份产物全哈希通过，revision1路径及原HTML哈希通过。

原revision1/2/3、所有旧manifest、签名回执保留。登记前index及运行manifest原字节分别保存到原研究reports/report_versions_before_revision4.json、manifest_before_revision4.json，并在受保护部署备份保留。

## 7. 性能和用量

公开聚合重渲染：5.90秒，最大RSS约276.4MiB。

正式主矩阵两会话合计90.36秒；恢复新会话重复查询8.08秒，CLI峰值RSS83.1MiB。主矩阵42次调用的审计延迟中位数2.13秒、范围0.92—3.34秒，包含账本开销，不称为纯HTTP延迟。

最终正式13问：46次模型调用，178909输入+10926输出=189835 tokens，未知用量0。API未返回实际费用。包括先前候选、失败排查和首次生产验收在内，本次连续收尾证据记录总计560202 tokens；不隐藏失败消耗。没有为图表、表格、报告或PKL另行调用模型。

## 8. 失败及非关键问题

第一次v0.8.2安装发现venv残留0.8.0/0.8.1/0.8.2三份distribution metadata，导致代码版本与metadata.version不一致；自动回退的wheel位于root-only备份，低权限pip无法读取。生产源码/指针当时已回退，未触发Test。诊断保留v082_failed_deployment_diagnosis.json。

随后在同一批准范围内保留残留metadata至受保护备份，使用原项目中可读且SHA固定的wheel修复安装，最终代码/metadata均为0.8.2。没有降低备份权限。最初报告完整性检查程序误假定revision1与后续revision格式相同；按既有research_report.py的真实legacy合同补全验证后通过，没有降低历史文件哈希断言。

原SSH采集器逐块UTF-8解码产生个别替换字符。正式SQLite中12条原回答均无替换字符；保留原始转录，采集器改为增量解码，重复验收通过。不是生产终端编码修改。

一条模型回答把“超过60日”称为“样本量充足”。这一措辞偏强，只可理解为满足统计计算最低门槛，不代表统计功效充分；该回答的数值、置信区间包含零及证据不足结论正确。作为非关键语言问题保留，没有为措辞再次改生产代码或消耗API。

## 9. 回滚

受保护备份：`/opt/jijigua-quant-agent/research_agent/release_backups/v081_before_v082_20261013_122907/`。

按备份恢复5个源码文件、项目元数据、旧report_versions.json与运行manifest；quantagent使用原项目dist/中经SHA核验的v0.8.1 wheel离线安装，不能直接从0700 root备份路径安装。新catalog移入备份隔离；revision4与失败证据保留，不删除，不覆盖整库或删除新查询记录。回滚会话必须不busy、配置仍一致，并追加绑定回滚记录。

源码、wheel、索引、manifest和数据库快照已保存。故障时曾实际回退源码及指针，但第一次低权限wheel回退失败，原因与修复见第8节；没有在最终稳定生产上再做整套回滚演习，不能宣称最终完整生产回滚已实操通过。

## 10. 最终边界

本轮生产连续图表、最新合法报告读取、历史缓存刷新、10月解释、无需内部ID的官方DeepSeek查询、历史归档与数值保护均已验收。没有待批准的生产代码变更；仅未来扩展共享其他研究或修改能力需要另行授权。

2026新增评价次数0；不读取私有行情/标签/逐股票因子，不修改独立评估账本、签名密钥、ACL或测试预算。`PROFILED_EXPLORATORY_ONLY`及正式Backtest BLOCKED不变。重要报告位于临时/hy-tmp，仍需用户安排持久备份；未擅自外部上传。
