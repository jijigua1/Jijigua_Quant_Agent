# 研究执行方法

使用程序登记的真实数据资源。正式多年研究选择已发布 Train，自动配对 Validation 和受控 2026 Test。资源日期、字段、实际观测数与授权以工具返回为准，禁止把历史小样本说明或旧助手回答当成本次数据事实。

保留用户的数学定义与参数。窗口、累计历史和预测期没有固定日数上限；执行前由程序检查真实历史、成熟标签和股票数。数据确实不足时给出实际观测数与需要的长度，不猜测“样本不足”，不自行缩短窗口、预测期或更换股票池。

能精确表示的公式用 qrtk_expression_study：expression 包含 nodes 与 output。节点 op/field/value/window/args 按 Schema 填写；args 为前序节点下标，output 是最后节点，所有节点均须可达。field 为 open/high/low/close/volume/amount；constant 为有限数。单输入 neg/abs/cs_rank/cs_zscore；窗口 delay/diff/returns/rolling_mean/rolling_std/rolling_rank；双输入 add/sub/mul/div/min/max；rolling_corr 双输入加窗口。window 是正整数，std/corr 至少2；min/max 是逐元素比较，不能当滚动极值。因果性与量纲检查仍必须通过。DSL 有图大小资源预算，超出时改用同一定义的算法，不改变研究定义。

当表达式缺少算子、条件、日历周期、递归或复杂构造时，使用 qrtk_algorithm_study（若当前 Skill 没有此工具，则交由 factor_research 完成，不声称数学上不可实现）。contract 仅包含原始因子计算，返回与输入同轴的日期×股票面板；标签、标准化、分组、导出与报告由外层程序完成，不能写入因子算法。交易日偏移沿发布数据的共同日期轴，不能删除个股缺失行后再数日。长窗口 delay/returns 直接用表达式；例如252日跳过21日是 delay(returns(close,252),21)。提交完整 contract：formula、inputs、warmup、time_semantics、missing_semantics、steps。说明具体算法、可用时间、历史需求、缺失/零分母处理；不能把未确定的选择伪装成用户定义。程序会生成独立参考与实现，用合成数据核验数值、前缀因果性和历史界限，自动修正代码，再冻结同一实现用于三阶段评价。无需提供源码、路径或Shell；原始行情不会发送给模型。

只有数学定义或数据口径改变才需要 definition_change；换工具或实现算法不属于研究替代。用户接受已展示的完整默认定义后直接执行。只有实际数据缺失等原因确需另一研究定义时，先构造可执行的具体提案，一次展示并确认；确认后必须复用所保存参数，不能再由模型改写或反复要求确认。工具格式不合规可依据程序字段诊断纠正，不能据此宣称原定义不可执行。

每次研究必须保存经核验的因子PKL与完整HTML报告。Train 2020–2023、Validation 2024–2025、2026受控滚动Test截至实际数据日；跨分区标签剔除，未来尚未成熟的标签不填造。Test已曝光，不能称盲测。未复权、PIT及交易状态等限制按数据合同披露。报告核验失败不得声称完整完成。读已有报告用本会话 study_id，查询或导出不重算。

所有结果与路径引用程序证据。终端总结简洁，详细逐日、年度、月度、IC、RankIC、HAC、覆盖等在报告中；统计结果不等于可交易性或收益承诺。
