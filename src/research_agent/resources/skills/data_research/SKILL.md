# 主 Agent 适配边界（Phase 2-C）

下文原始专业方法保留作参考；可执行能力以主 Agent 工具合同为准，不调用 qrtk_skills.SkillRuntime。
只使用资源 ID 和本会话 study_id，不接受 data: 任意注册、动态函数、文件路径、Shell 或 Python。
模型不得填写发布时间或授权。样本、60/25/15时间划分、方向+1、lag=1、最低有效日数60由工具预先固定。
测试统计输出 sealed，但原始数据有其他读取通路，所以不是全系统盲测。真实回测本阶段禁用；原始价格的小样本仅用于探索性统计。
固定构造：reversal=-(close[T]/close[T-L]-1)；volume_stall=max(volume[T]/mean(volume[T-L:T-1])-1,0)*exp(-abs(L日价格收益)/0.02)。
这两个已审核固定公式用qrtk_factor_study及factor_id执行。exp仅是固定volume_stall内部实现，不属于19个表达式算子；不得把它或嵌套节点塞进expression。用户只要求已有固定因子时优先固定入口；新定义缺少算子时解释边界，不擅自扩充或替代。
参数由工具Schema限定。缺省研究建议 lookback=5,horizon=5,n_groups=5,standardization=raw；不是强制用户任务。
训练/验证日数不足60必须说明证据不足；分组收益是毛收益、缺失标签排除，不能称账户收益。
查 IC/分组/报告/诊断时先使用会话 evidence 中已有 study_id 读取，不重新跑实验。
qrtk_factor_study 自动复用受审 qrtk handlers 生成评价与报告；qrtk_read_study 返回完整指标。
新想法用 qrtk_expression_study，不把新因子强行替换成已有固定公式。expression含nodes数组与output（最终节点下标）。节点只含 op、args、field/value/window（按算子需要填写）。
field叶：{"op":"field","field":"close"}；constant叶：{"op":"constant","value":1}。
单输入：neg、abs、cs_rank、cs_zscore；历史窗口单输入：delay、diff、returns、rolling_mean/std/rank；双输入：add、sub、mul、div、min、max；rolling_corr双输入+window。
min/max是逐元素比较，不是滚动极值。max(x,c)的实际下界就是c；正部截断必须使用constant=0。构造前核对常量和窗口，摘要逐字引用工具公式，不把max(x,1)解释成截断于0；任何设计修改须作为新实验说明理由。
args是已存在的前序节点下标数组（不是子对象），只允许引用更早节点；output必须是最后节点且所有节点都被使用。window为1至60正整数，std/corr至少2；最多40节点8层累计历史120。禁止未来偏移、路径、代码、额外键。
五日反转示例expression={"nodes":[{"op":"field","field":"close"},{"op":"returns","args":[0],"window":5},{"op":"neg","args":[1]}],"output":2}。
五日反转可写 neg(returns(close,5))；量比建议 volume / delay(rolling_mean(volume,L),1)，避免当前成交量混进历史均值。
经济假设与生成理由单独传hypothesis/reason。公式不覆盖用户想法时先说明缺少算子，不假装已计算。
修改窗口要创建新实验；把本会话已有study_id放入parent_study_id，对照同一数据、H、分组及时间分段。比较结果不是独立样本外。
固定qrtk_factor_study与表达式qrtk_expression_study都接受parent_study_id；用户要求比较并更新报告时必须传入真实父ID，报告的对照表与图由程序生成。
每次新因子计算必需自动生成通过验证的factor.pkl、factor_dict.pkl和元数据，以及实际统计表、图表与Markdown/HTML；不依赖模型另选导出Tool。PKL失败不能宣称完整交付。
新研究工具返回的已验证指标及文件路径已满足交付；无需在同一任务再次读取或导出才完成。后续用户要求查看/复核时再选择对应工具。
后续导出问询用qrtk_export_factor复核/返回本会话已验证PKL；旧实验或失败导出会在新任务目录补救，不覆盖旧文件。查询IC、稳定性、Lag1/5/10自相关或报告用qrtk_read_study/qrtk_diagnose_study/qrtk_export_report，不重新计算。
自相关是共同股票横截面值/秩相关的日期均值；预测衰减是不同持有期成熟收益标签。换手代理不是实际交易换手。HAC小样本为insufficient，不输出显著性星号。指标表由可信程序生成，不自行填写。
完成摘要必须根据实际工具结果，不以模型判断替代缺失计算；说明日期、预测期与限制，不能声称独立样本外有效。
终端摘要控制在约600中文字，重点为结论、关键指标和成果路径；详细表格在自包含HTML中，不重复罗列全部指标/指纹。
只有获得本 Skill 合法工具结果后才能 action=complete。工具失败或授权拒绝时停止。

## 专业方法

先查清单，再核验字段/日期/单位/复权/发布时间/缺失/股票池。来源未知保持未知；禁止推断停牌或真实可交易资格。本 Skill 只负责数据发现与质量核验；只可调用本 Skill 注册的工具。核验后总结可用边界和阻塞并完成当前任务，不构造因子、不调用 factor_research 的工具；如需因子计算，等待下一轮用户请求由主 Agent 路由。

## 已发布多年行情
当资源为gpushare:train2020_2023时，工具固定配对gpushare:validation2024_2025：Train2020-2023，Validation2024-2025，完整5427代码轴；2026不读。选择Train ID调用现有因子Tool，程序自动生成PKL和两分区评价及报告。Validation暖机可用Train尾部，未来标签跨分区剔除。方向+1冻结；Validation是曝光验证，不是独立盲测。两个分区仅PROFILED_EXPLORATORY_ONLY，未复权，公司行动、上市日期、股票池PIT与可交易状态未认证。此处优先于旧小样本60/25/15说明；旧小样本接口与历史实验保留，但新profile拒绝读取含2026的daily65。
