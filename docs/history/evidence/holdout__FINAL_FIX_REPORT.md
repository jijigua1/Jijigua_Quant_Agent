> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-C 最终修复候选交付

状态：READY_FOR_DEPLOYMENT_APPROVAL。候选v0.8.1；生产v0.8.0未被修改，版本索引仍指向原revision2。

## 已完成

1. IC、RankIC、20/60观察日趋势、累计IC/RankIC、覆盖率及理论分组累计毛收益采用统一连续日期轴和两条分区竖线。累计值跨分区延续；悬浮显示实际日期、数值、分区。静态PNG/SVG/PDF与HTML共用聚合CSV。
2. 缺失/未成熟标签不补0、不产生新的日期值。Test缺少逐日分组收益，分组曲线止于Validation；预测期、滞后和分组类别等非日期轴图仍保持各自正确比较口径。
3. 新报告查询通过模型自主选择的只读路由执行，独立授权仅允许qrtk_read_study，取消研究写权限。不存在重新计算或提交Test的后门。
4. 最新版本读取核验索引、manifest、analysis和公开回执指纹；旧摘要不作为当前结果，旧待审批请求不能覆盖已完成Test。
5. 已公开回执的日期及尾部成熟状态用于解释月度N/A：2026 Test有183观察日、177有效日；10月有2行情观察日、0成熟标签评价日。不是缺失行情。
6. 同一研究、同一评价回执的revision3已在授权成果区生成；尚未登记为生产最新版本。原Train/Validation、revision1、revision2和独立评价未修改。

## 真实数值

| 分区 | IC Mean | RankIC Mean | 有效评价日 |
|---|---:|---:|---:|
| Train | 0.0203673769 | 0.0263804216 | 959 |
| Validation | 0.0433376595 | 0.0463008393 | 479 |
| Test | -0.0008633622 | 0.0040142455 | 177 |

Test RankIC HAC 95%区间：[-0.0341851582, 0.0422136491]。区间含0，当前样本不能证明预测能力，也不能据此证明因子必然失效。研究判断NEEDS_MORE_EVIDENCE。2026是有既有曝光的回顾性测试，不是纯净盲测；原始未复权、股票池/PIT及交易状态问题仍使正式账户回测BLOCKED。

## 验收记录

完整Windows/Linux各324通过、1跳过；Windows跳过符号链接创建，Linux跳过可选pyarrow。Linux实际符号链接拒绝测试通过。最后Schema补丁Windows7通过、Linux39通过；最后渲染另有Windows三阶段历史兼容回归及服务器自检。

真实SSH候选使用原会话，输入均为简短自然中文：最新五日反转报告、2026结果、10月N/A、三阶段完整报告及研究价值。5次均自主选择既有只读工具；无因子研究和Test重算。追加研究价值查询验证了更谨慎的统计解释。用户未提供study_id或工具名作为自然语言输入。

首轮真实查询暴露注册Tool输出Schema遗漏revision和月度标签状态，产生ContractError/TOOL_ERROR；失败转录、模型参数和账本保留。修复声明了准确输出类型，没有跳过校验或改变输入权限。

## 性能与费用

聚合报告初次重渲染5.83秒，峰值RSS265256KiB（约259MiB），无需因子矩阵或私有Test读取。最终渲染的实际时间/RSS见evidence/rendered_revision.json。

5条成功查询实际聊天处理约63秒；追加研究价值查询约10秒。SSH元数据总时长另含连接、隐藏Key输入等待，不能当成纯Agent推理耗时。

成功6次查询24次模型调用、147791 tokens；失败排查15次模型调用、73470 tokens；本轮合计221261 tokens。未知用量0，API未提供实际费用。详细逐任务用量见api_usage_all.json及候选SQLite记录。既有Skill路由上下文较大，这是后续可优化项，本轮未扩展重构。

## 可审查成果

- 源码及wheel：候选src/、dist/；7个改动及全部92份文件SHA见final_patch_source_sha256.json。
- CLI：candidate_ssh_cli.txt、candidate_ssh_cli_verdict.txt；初次失败candidate_ssh_cli_failed.txt及failed_reader_diagnosis.json。
- 测试：windows_tests.xml、linux_tests.xml、windows_output_contract.xml、linux_output_contract.xml。
- 公开报告：evidence/rendered_report/reports/report.html，包含离线Plotly、LaTeX和原始统计表。
- 视觉：screenshots/continuous_cumulative.jpg、continuous_groups.jpg、narrow_report_final.jpg、pdf_cumulative_poppler.png；最终图表继续检查实际桌面及窄屏。
- 服务器revision3路径及manifest见rendered_revision.json；latest_pointer_updated=false、new_evaluation=false。

## 待批准后完成

按DEPLOYMENT_APPROVAL.md更新生产代码与最新报告指针，再通过真正的quant-agent chat正式入口完成5条中文验收。候选CLI通过不能代替生产上线验收。无需重新执行2026评价。

历史报告和原manifest字节须保存；配置、原数据和独立测试审计不变。所有结果仍属探索性统计研究，重要/hy-tmp成果须备份。
