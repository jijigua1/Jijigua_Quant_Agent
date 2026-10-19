## 论文研究（v1.0 Beta）

用户说“研究我刚上传的论文”“读取Amihud那篇论文”“提取里面的因子并做完整研究”时，调用一次 `qrtk_paper_research`：
paper 填用户对论文的原话描述（如“刚上传的”“Amihud”；没有描述时填空字符串），factor 填用户点名的因子名（未点名填空字符串）。
不要编造或填写 SHA、任务ID、文件路径、Resource、DSL 或公式；程序在后台完成论文定位、证据核对、研究定义与路线选择。

用户只想看已上传论文列表时调用 `paper_list`。查看已有研究结果时用 `qrtk_read_study` 和会话中已有 study_id，不重新计算。

工具返回 `paper_status=AMBIGUOUS/NOT_FOUND/NO_PAPERS` 时，不再调用其他工具，action=complete，summary 用自然中文列出候选论文名称请用户选择，或说明需要先用 quant-paper upload 上传。
工具返回 `paper_status=BLOCKED` 时，如实说明阻断原因（hard_stops），不得改用替代定义或自行编造公式。

需要用户确认的口径替代与新代码审核由程序暂停并向用户展示，不是模型决定；模型不能批准任何东西，也不能声称已经批准。

研究完成后的结论只依据工具返回：Train/Validation 指标、Test（ROLLING_EXPOSED_TEST 为持续曝光的滚动评价，不是盲测；NOT_EVALUATED 时说明原因）、研究判断 verdict 与局限。
不得把探索性替代说成论文复现，不得把理论分组毛收益说成账户收益。终端摘要约400字，路径由程序另行显示。
只有获得本 Skill 合法工具结果后才能 action=complete。授权拒绝时停止；参数格式错误由程序在预算内纠正，禁止改变用户定义。
