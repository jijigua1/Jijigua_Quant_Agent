> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-C 交付报告 — Research Agent v0.6.0

2026-10-12。已在既有主Agent上完成默认PKL资产、丰富指标、专业报告和真实DeepSeek验收。核心部署仍为`/opt/jijigua-quant-agent/research_agent/`，运行身份quantagent（999:999）。**PKL结构兼容已验证；当前数据仍只支持探索性因子研究，正式账户回测继续BLOCKED。**

## 使用方法与实际成果

沿用root SSH登录，执行`quant-agent chat`，启动器内部切换身份，隐藏输入Key。输入“帮我做一个放量滞涨因子，研究一下效果。”即可触发计算、PKL、指标表、图表和HTML/Markdown交付；不需要额外要求导出。末尾自动显示PKL、HTML、图表和成果目录。status/result/logs原入口保留，旧SQLite原位、原历史任务仍存在。

真实五日反转样本：

`/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/aa51b304229a4d3d/`

其中`data/factor.pkl`、`data/factor.pkl.zip`、`data/factor_plain.pkl`、`data/factor_dict.pkl`、`factor_metadata.json`、指标CSV、7组PNG/SVG/PDF、`reports/report.html`/`report.md`、代码、阶段日志和manifest均存在，逐文件SHA已核对。10日子实验为`INTERNAL_RUN_ID_REDACTED:7402c86c3c3240d8`，独立PKL、对照表/CSV及第8张对照图，不覆盖父实验。

其余成功研究及最终包单句复验路径见acceptance-summary.json和default-live-session.json；每个实际计算均由原生Tool Calling触发，mode=real_data、execution_mode=live_api。最终部署wheel与源码备份路径见deployment.json；最终包另以单句放量滞涨复验新增源码指纹和默认交付，不重跑七轮对话消耗Token。

## 1. 服务器真实格式与消费兼容

三份约6—7MiB因子Zip样本完整静态检查，183日、4998—5214股票、float64数值缓冲区、协议4、Arrow字符串日期/交易所后缀代码；没有反序列化原始未知PKL，没有复制88GiB矩阵。生成及消费代码反向验证、日期/代码差异、原库版本依赖详见SOURCE_REVIEW.md。

| 新文件 | 固定合同 | 验收 |
|---|---|---|
| factor.pkl | YYYYMMDD字符串日期×经过核对的后缀股票代码，float64、date/Code轴名、NaN保留 | Gyc原norm_index函数及受控独立数值读取 |
| factor.pkl.zip | 同一面板，确定性Zip成员factor.pkl、协议4 | Pandas实际压缩读取和精确数值核对 |
| factor_plain.pkl | 六位代码面板 | 与因子CSV精确一致 |
| factor_dict.pkl | dict[factor_id,后缀宽表] | Perry原load_and_pivot_factors函数；原float32转换按float32预期一致 |

真实输出矩形55×50，20260703—20260917，仅训练/验证因子值。原5日、10日、放量滞涨、自定义表达式的NaN位置分别与各自计算CSV一致（详见linux-consumer-check.json）。未运行完整Gyc生产合并、Perry训练/交易回测或Pyx GP；它们还要求额外数据/时期/依赖。**读取入口兼容不等于可以不经审查投入已有生产回测。**

程序固定写入、原子保存、同进程固定序列化字节比对后读取、数值验证、SHA、源码与依赖版本、日期/代码/缺失、定义及可获得时间进元数据与manifest。只凭外部哈希不能授权pickle加载。未知pickle、路径/链接、无限值、额外参数、伪造工具、跨会话、覆盖旧文件均有拒绝测试。导出失败为EXPORT_FAILED，计算结果保留；修复生成新run，旧文件不变。已验证再导出只复核、复用文件。

## 2. 指标与研究报告

沿用qrtk正确的IC、RankIC、成熟标签、分组、共同股票相关等数值实现，未改其原模块。新增Lag1/5/10原值与秩自相关、有效共同股票数、分段半窗稳定性、H=1/3/5/10预测衰减、方向符号一致性、分布/无偏偏度/超额峰度/分位数、覆盖/连续缺失/MAD异常率、Top组排序换手代理、父子参数及样本数对照。具体输入、公式、样本、NaN/零方差与统计限制见METRICS_CONTRACT.md。

HAC为有条件的近似95%均值区间，带宽覆盖标签重叠，完整有限序列及保守n门槛；当前daily65为insufficient，不输出显著性星号。IR不年化，分组是未扣费毛收益；排序换手代理不是实际账户换手。未知方向、零方差矩和缺少数值的图表明确N/A/无法判断，不填0、不生成空预测图。

真实五日反转（L=5，H=5，方向+1固定）：

| 分段 | IC均值 | RankIC均值 | 有效日期 | G0−G4毛收益 |
|---|---:|---:|---:|---:|
| train | 0.0497717 | 0.0257145 | 28 | 1.4202% |
| valid | 0.1568353 | 0.1498460 | 10 | 2.0978% |

样本少、未复权、重叠标签；这些数值不能确认预测效力或可交易策略收益。独立标量因子/IC/分组最大误差在10⁻¹⁴以内；偏度、峰度、MAD、分位数、共同股票相关与每个预测期成熟边界也独立交叉核验，详细误差见real-numerical-baselines.json、independent-metrics.json。

报告首页为标题→一句结论→样本→核心指标小表→重点IC图。每个主题配3—6列表格，数值右对齐、统一小数/百分比/N/A；预测、稳定性、质量、分组、参数比较与可展开技术附录分区。HTML内嵌真实PNG、无外部CDN/脚本；Markdown与全部图表使用同一计算结果，原始表值在report_tables.json。源码版本/实现指纹、数据与参数指纹、PKL元数据与复现入口均可追溯。

## 3. 现有绘图复用与视觉核验

受审Perry backtest_visualization.py的configure_chinese_font原函数、蓝/中性色、百分比轴及稀疏日期定位器已适配；整套账户净值算法没有移植。实际查看Perry原notebook内嵌历史PNG，指出拥挤标注而不照抄，源码与样例指纹有记录。英文金融图使用DejaVu Sans、CJK备用；PDF嵌入字体、SVG文本可编辑，PNG 2160×990/300dpi。没有新依赖。

实际打开旧版及新版真实HTML，1280×900桌面和390×900窄屏截图已保存。首页数字可直接阅读；双栏预测图、稳定性与小表已肉眼检查；窄屏整页宽375px，表格343px内独立滚动470px内容，所有图片加载成功。旧/新desktop/narrow及专题截图、browser JSON、图表文字/重叠审计见本目录。代表性PNG逐项查看，最终受控研究样本29张PDF均通过文本与碰撞检查（figure-quality.json）。不把自动测试代替实际视觉检查。

## 4. 真实自然语言验收与失败修复

| 真人式输入 | 实际执行/结果 |
|---|---|
| 帮我做一个五日反转因子，生成因子文件和完整报告。 | 查询资源→固定因子计算→自动PKL/指标/7组图表/报告 |
| 把刚刚那个因子导出成服务器现有PKL格式。 | qrtk_export_factor复核原PKL，无重算、无覆盖 |
| 给我看它的IC、RankIC、稳定性和自相关。 | 使用真实既有实验结果，中文解释及限制 |
| 把它的核心指标整理成一张小表。 | 复用会话证据和程序报告表，不重算 |
| 我想看更漂亮的因子分析图。 | 返回已经生成的真实图表路径，不虚构新图 |
| 把观察窗口改成10天，比较两个因子，并更新报告。 | qrtk_factor_study带真实parent_study_id→新独立研究与程序比较表/图 |
| 这个PKL能直接用于服务器已有的回测程序吗？ | 说明读取格式与回测准入差别、当前BLOCKED |

七条均COMPLETED，完整同会话记录在live-session.json/live-ssh-console.txt。单独“帮我做一个放量滞涨因子，研究一下效果。”通过，未请求导出、未选导出Tool，可信程序自动完成PKL。另一次自然语言组合想法触发qrtk_expression_study并自动交付PKL；实际公式`sub(neg(returns(close,5)),rolling_std(returns(close,5),5))`，预热9观察日。波动率在此为五日收益的滚动标准差，并非单日收益的五日波动率；实际定义已记录，不能把模糊自然语言解释当成唯一标准口径。

真实验收曾暴露并修复：聚合实验超过旧64KiB账本边界、固定因子入口没有父实验参数、PDF字体/标题图例重叠。账本单独1MiB，模型/Tool JSON仍64KiB；测试覆盖聚合读写与超限拒绝，不扩大模型权限。固定与表达式入口统一父实验合同。Skill说明区分固定公式的exp与19个表达式白名单，非法算子仍拒绝。一次零方差测试错误使用纯常数，按已有“必须依赖观测数据”门禁被拒绝；改用close/close核验真正零方差指标，原失败XML保留。

主验收后额外追加的放量滞涨任务自行扩展窗口对照，触发BUDGET_EXHAUSTED，**不算成功**；保留计算文件与日志，未提高预算绕过。另开新会话单句任务通过。失败attempt1/attempt2与额外预算停止原记录全部保留；早期账本失败遗留RUNNING任务不自动接管或重放。

模型用量包括修复后的重复验收，较高；逐次实际Token、unknown_calls和总量见acceptance-summary.json。API未返回金额费用，不能按Token数声称实际账单。报告/图表/PKL均由程序一次生成；追问复用成果，不另为每项调用模型。

## 5. 测试、部署及保留边界

Windows Python3.12.4、Linux3.11.10；NumPy1.26.4、Pandas2.3.3、Matplotlib3.8.4，锁定依赖未新增。最终Agent回归Windows/Linux各248通过+1跳过：Windows因OS1314跳过符号链接，Linux该项通过，仅跳过无PyArrow的可选Parquet；CSV链路完整。原Claude工具包两端135通过，47份来源文件SHA保持不变。精确测试、时间与失败/跳过见JUnit及test-summary.json。LinuxJunit取自当前phase2c目录，不使用旧phase2b结果。

实际下游函数、独立因子复现、manifest/数值/PKL与原命令补验在linux-consumer-check.json、linux-reproduction.json、cli-verification.json。实验进度来自真实阶段事件，图表分母取实际可生成集合。原data_query、Mock、五Skills、Provider接口、权限系统、SQLite均保留，未启动第二套Agent或修改Claude原项目。

本轮仅批准新建integration_tests/phase2c（999:999，0700），其他共享数据/项目/权限和生产任务未改。quantagent不可写可信配置和发布CSV；测试证据与研究目录可写，/hy-tmp为XFS，空闲约73GiB，状态在deployment-verification.json。

能力边界：工程资产/统计/图表交付完成；正式账户回测、独立盲测、行业/市值与参考因子相关、完整生产消费运行尚未完成。下一步优先发布口径合格的长历史及交易状态、核验真实消费环境/成熟引擎，而非再造Agent。生产沙箱、进程树硬配额、后台Worker仍未上线；当前预算/超时是程序边界，SSH断线不保证继续。

`/hy-tmp`关机超过24小时或迁移存在删除风险，见[平台存储文档](https://gpushare.com/docs/data/storage/)。重要PKL、报告及证据请另行备份；本轮不自动上传外部平台。
