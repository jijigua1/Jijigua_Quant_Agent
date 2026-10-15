> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 已有一次Test回执：独立核验与报告后处理恢复申请

当前一次真实评价已产生回执，预算1已经用完。按用户禁止工程故障自动重试要求，已停止；本申请**不要求第二次评价**。

## 精确修复

仅更新独立环境 `phase3c_v1/verify_once.py` 的年度/月度空值对照逻辑，并同步该文件在root批准配置内的SHA；旧文件和旧配置保存到root审计目录：

- 服务器当前SHA：`369a0e55799ecf3e3618c3982ce2dbfdd356098aeaf8fa7be767d30136bdfc34`。
- 本地修复SHA：`92e01b216de3a3d5de3f9b70133bc37c02f68efbdb09f8c2710245f864e26993`。

规则为n=0均值N/A、n<2样本标准差N/A；验证N/A不能填0，数值容差仍1e-12。新增手算测试4通过，本地全套29通过。评价器、因子、数据、HAC和方向不改。

## 获批后仅做以下后处理

1. 在quanteval身份下，重新读取**同一**已封存私有快照，进行固定五日反转的独立数值基准核验。不改变因子、不选择参数、不创建新许可。
2. 使用**同一**evaluation_id `INTERNAL_RUN_ID_REDACTED` 和回执SHA `9c6ae94aa6f037e0a30060a07e49a2c2a1a376dad41d74083f12d7104a843176`。
3. **不调用IndependentEvaluator.evaluate、不再次运行admin evaluate、不重发数据、不重建身份/环境、不清空账本、不增加预算。** 尝试数和评价曝光数仍1，旧失败审计不可删除。
4. 成功核验后，通过现有merge_private和固定commit_revision流程完成同一study_id的revision2；Train/Validation旧值和历史报告保留。
5. 记录VERIFICATION_RECOVERY_STARTED/PASSED、REPORT_COMMITTED及模型读取结果曝光事件；后处理失败仍停，不自动重试。
6. 原范围的三阶段HTML/热力图、独立文件哈希、真实官方DeepSeek CLI读取及视觉验收；不修改生产v0.8代码、API或权限。

内存/CPU/时限/返回范围、数据资格和正式回测BLOCKED沿用原已批准清单。批准后才部署此修复并进行真实后处理。

状态：**WAITING_USER_CONFIRMATION**。

审批与执行补记（保留上述原申请）：用户已明确回复“批准仅恢复核验与报告”。2026-10-13完成同一回执独立复核及revision2提交，未再次评价，预算仍1次已用完。当前实际结果与CLI部分未通过项见`PHASE3C_FINAL_REPORT.md`及`TEST_RESULTS.md`。
