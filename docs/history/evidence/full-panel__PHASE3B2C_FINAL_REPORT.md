> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2-C 交付与验收



状态：**FULL_DATA_NL_RESEARCH_ACCEPTED**。用户已批准精确部署范围，v0.7.0已更新至正式入口，并通过真实官方DeepSeek SSH PTY验收。该证据为实际SSH终端程序，不是Mock；用户自己在FinalShell的人工复测尚未由本次操作代替。



## 1. 实际工作区与边界



- 本地：<ARCHIVE_ROOT>/phase3b2c_work；原主项目冻结文件逐一核对未改变。

- Linux候选：/srv/jijigua-quant-agent/research_runs/2026-10-12/19-40-27_phase3b2c_candidate。

- 批准前候选通过生产 venv + 独立PYTHONPATH/state验收。批准后仅替换项目源码、包、两个配置及launcher；正式命令仍为quant-agent chat，运行quantagent UID999并保留既有quantdata GID998。原SQLite原位使用，没有Schema迁移或历史覆盖。

- v0.6.8备份：baseline_v0.6.8.zip、baseline_fingerprints.json；原0.6.8轮子SHA 8752477363bdf6a186a1aee045c2b443b98607a177dfe467905592096db1ecf5。

- 没有原始PKL解析、数据再发布、账号/ACL变更、常驻服务、2026标签/绩效读取或正式回测。



## 2. 资源与合同



复用 baseline_20261009_a864dc33、原 release.py 字节一致副本 published_release.py（SHA ea3702bba89fcef3b9c6a5420d38a52fd6b70d36b191dae7ec02f3c71bdcdb26）。模型只可用登记ID。



| 资源 | 实际日期 | 观察日 | 代码轴 | manifest SHA |

|---|---|---:|---:|---|

| gpushare:train2020_2023 | 2020-01-02—2023-12-29 | 970 | 5427 | 9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221 |

| gpushare:validation2024_2025 | 2024-01-02—2025-12-31 | 485 | 5427 | 82246b4424f8dbd45c11d959164199a4b45efeb6803d6a6064204a6fc08bf4b4 |



六字段open/high/low/close/volume/amount；volume为手、amount为千元。Train有close的代码5218，Validation5258；5427为固定轴，不代表每一天5427只有效股票。001914.SZ和302132.SZ整列缺失。



状态保持 PROFILED_EXPLORATORY_ONLY。候选上市日期屏蔽不等于上市日认证；非PIT股票池、未复权价格、公司行动、停牌/ST/涨跌停、退市估值和权威可获得时间缺口继续存在。原始价格收益不是经济总收益；价格存在不等于可成交。



## 3. 科学与访问边界



- 每次研究在Validation读取/评价前冻结参数/AST指纹，并记 RESEARCH_DEFINITION_FROZEN、VALIDATION_EXPOSURE。

- 一次合并两个已准入分区用于因子历史暖机，全横截面计算，无股票分块/时间截断；算子未来偏移禁止，截断回归保持一致。

- 信号T收盘；统计标签 raw open[T+1+H]/raw open[T+1]−1。不是实际成交承诺。每分区只保留退出日期<=本区末日的标签，H=5时末端剔除6个信号日。

- Train因子不受Validation未来输入影响；Validation头部使用Train历史，尾部不通过2026补标签。

- 当前为固定因子描述性检验、无监督拟合/多折训练，没有额外embargo间隙；lag+H成熟期purge已落实。未来模型训练必须另外提交适合该标签/执行时间的purge/embargo合同。

- 5日原始价格动量Validation此前已曝光；本轮新增曝光有独立账本事件。不声称Validation独立盲测。

- 六原始PKL、staging、daily_private、audit均有quantagent实际OS拒绝证据。2026未发布；没有新增独立Holdout评估器。

- 旧daily20/daily65包含2026。v0.7.0保留其注册元数据与既有历史，但新profile拒绝读取；原版v0.6.8完整保存在回滚副本。旧2026数据此前已曝光，因此不能追溯宣称整个2026未接触。

- paired资源均必须位于程序注入的授权集合，Skill和模型不能扩大它。源/数据/代码/参数指纹在 manifest、metadata、SQLite 中关联。



## 4. 实际DeepSeek CLI场景



官方端点 https://api.deepseek.com/chat/completions，deepseek-flash。自然中文经真实SSH PTY输入，原Provider和隐藏Key方式保留。



A：20日动量成功调用 qrtk_expression_study，944/479有效日，完整1455×5427输出。

B：最初模型并列计算reversal和volume_stall，**不满足组合目标，验收失败**；没有删除该历史。完善固定公式/组合入口说明后，模型通过19算子DSL计算历史量比×短期反转。最终带双资源授权检查的候选再次通过，同一会话追问报告未重算。

C：2026收益调参请求直接拒绝，没有研究工具调用或2026结果。独立拒绝测试另覆盖旧资源旁路、边界越界和未授权配对。



| 因子 | 分区 | IC mean | RankIC mean | 有效日 |

|---|---|---:|---:|---:|

| 20日动量 | Train | -0.02898336 | -0.03914481 | 944 |

| 20日动量 | Validation | -0.04611826 | -0.07097932 | 479 |

| 历史量比×5日反转 | Train | 0.01923103 | 0.02658673 | 959 |

| 历史量比×5日反转 | Validation | 0.04092646 | 0.04812766 | 479 |



以上数值为原始价格探索性相关结果，不是策略效果或可交易绩效。组合分组并非严格单调；不得只据正IC升级认证。



## 5. 交付产物与独立核验



- 默认4种兼容产物：factor.pkl、factor.pkl.zip、factor_plain.pkl、factor_dict.pkl；协议4，宽表YYYYMMDD字符串日期、Code列、float64、NaN；exchange suffix来自已发布真实轴，未猜映射。

- 因子CSV/PKL保留1455×5427，无降采样，无未来标签/2026绩效；导出失败不准COMPLETED。

- Gyc norm_index及Perry load_and_pivot_factors受审提取读取函数在完整轴上成功；后者既有实现内部转float32，已按该合同核对。未运行完整下游回测。

- 20日动量全矩阵与独立NumPy相同，并独立复算两分区多个日期Pearson/Spearman；组合全矩阵与独立NumPy历史窗口均值/收益构造一致（rtol1e-10, atol1e-12）。

- 所有manifest文件SHA、索引、dtype、NaN、两只冲突证券全缺失、报告表格对CSV核对通过。真实PNG已查看，图例、轴标签和分组注释可读；IC图末端2026为日期刻度边界，实际数据止于2025-12-31。

- 单文件离线HTML、Markdown、AST/LaTeX、7类PNG/SVG/PDF、指标CSV、复现脚本和data_partitions.json均保留。



动量成果：/srv/jijigua-quant-agent/research_runs/2026-10-12/19-47-01_momentum_20d



组合成果：/srv/jijigua-quant-agent/research_runs/2026-10-12/20-04-20_volume_change_x_short_reversal



本地可直接打开 sample_report.html，图表 sample_ic_rankic.png、sample_group_returns_gross.png。



## 6. 性能与预算



| 阶段 | 实测秒 |

|---|---:|

| Train完整六字段读取 | 0.632 |

| Validation完整六字段读取 | 0.405 |

| 20日动量构造 | 0.162 |

| IC/RankIC与分组评价 | 7.466 |

| 稳定性/分布/多预测期诊断 | 23.844 |

| 默认4种PKL写入及独立读核验 | 8.285 |

| 报告生成（含7类图表） | 2.691 |

| 计算至成果交付合计 | 57.997 |



峰值RSS1880.14MiB；六输入矩阵379021680字节；完整因子7896285单元。包含独立复核的工程基准63.275秒；真实中文动量CLI约74秒、最终复合CLI约77秒（含模型交互）。小型250×200等值基准从重复2次评价改为1次，约1.61倍加速；不能把此倍率当全量总流程速度倍率。



输入不可变缓存按发布指纹/文件状态复用，一份因子缓存复用同定义以及截断检查的完整构造；原计算公式不变。rolling_rank使用已安装Pandas原生rolling.rank，替代逐窗口Python调用，已有32项算子回归通过。没有跨股票分块语义变化。



最大800万单元、40节点、8层、120历史观察、1个线程的BLAS/OMP、每任务600秒阶段检查、512MiB成果上限；memory_mib=4096为声明与规模预算。不是cgroup硬限制、CPU配额或正式沙箱；原子算子内部无法被阶段超时抢占。SSH断线不保证继续。此次实际API用量121921 tokens（含失败场景与修复重验），未知调用0；API没有提供账单金额，不推算费用。



## 7. 自动化证据



- Windows完整：300 passed、1 symlink权限skip；之后最终模块回归106 passed/1 skip、交付门70 passed。XML保留。

- Linux完整：300 passed、1可选PyArrow缺失skip；最终受影响模块110 passed，符号链接测试在Linux通过。发布NPY不依赖PyArrow，未额外安装依赖。

- 初次Linux测试包漏deploy/launcher.py导致2个文件缺失错误；补齐测试包后完整回归通过，未改变测试断言来绕过失败。

- 证据：live_cli.txt、live_composite_cli.txt、live_final_cli.txt、live_tasks.json、benchmark.json、verification.json、各测试XML、change_manifest.json、local_release_proof.json。

- 最终Wheel SHA：2f7ab6ea38d500062fa6759789f40f16b44560d5a44cbbe0d99d789273aa22fa（见本次最终local_release_proof.json）。



## 8. 尚未开放与下一步



正式入口替换及生产PTY验收已通过；保持正式回测BLOCKED，无账户NAV/Sharpe/成本结果；最终Holdout评估器、Daily Inference资源、每日Worker、本地未知代码执行、论文/自主算法模块都未开发。



本次固定批次接口按manifest SHA固定版本，新获批批次可用同接口注册并留旧版本；增量parent链与Daily Inference必须另行审核准入，候选reader当前仅准入无parent的已审基线，未宣称日更入口已上线。



重要报告/因子须人工备份，/hy-tmp不是永久存储，未向外部平台自动上传。



## 9. 已批准的生产部署与最终验收



- 生产路径：/opt/jijigua-quant-agent/research_agent/；版本0.7.0。

- /usr/local/bin/quant-agent文件及其SHA保持不变，root Shell执行该命令后由项目launcher降权至quantagent；没有新增用户、组成员或共享数据权限。

- 回滚目录：/opt/jijigua-quant-agent/research_agent/release_backups/v0.6.8_phase3b2c_20261012_203516。包含原代码、配置、launcher和原0.6.8 wheel；数据库没有迁移，禁止用旧数据库倒灌覆盖新记录。

- production_entry.json为部署前证据；production_deployment.json为部署后逐文件源码指纹，production_acceptance.json为正式入口独立验收。Windows原<ARCHIVE_ROOT>基线未覆盖；本轮完整新源码位于phase3b2c_work。

- 正式root SSH PTY依次输入20日动量全量需求、报告追问、2026收益调参请求。研究task_id=INTERNAL_RUN_ID_REDACTED，真实会话138da64272b84969aa12e338cf2dad50。一次因子计算、后续报告追问无重算、2026请求无研究调用。

- 成果：/srv/jijigua-quant-agent/research_runs/2026-10-12/20-36-39_momentum_20d/，完整1455×5427，默认PKL/HTML/图表交付。PKL SHA b2cc14d81ea3cc83444644be758ff7e52895b131892a92ca1b40f08f029a0084，manifest SHA 008e2dbbcaa5588908481742104d23835b6f68daca51e8646f93a7666403ed61。

- 生产成果再次通过全矩阵独立NumPy20日收益计算、Gyc/Perry受审消费函数、所有manifest文件哈希及核心表/CSV一致性验证。定义冻结事件sequence4155，Validation曝光事件4162；两个分区各purge6个尾端信号日。

- 本次生产计算/交付57.609秒，含模型研究首轮约73秒；生产验收3轮共37024 tokens、未知调用0。连同候选验收累计158945 tokens；不据此推算账单。

- 原数据库中258条此前任务仍可读取。部署未执行删表、Schema迁移或旧记录覆盖；不能将这一计数夸大为对所有历史业务结果重新验收。

- 受控单字段读取、报告路径查询与status/result/logs保留；当前数据仍是PROFILED_EXPLORATORY_ONLY，Validation不是独立盲测。



启动：root SSH登录后直接执行 `quant-agent chat`，按原方式隐藏输入官方DeepSeek Key。建议用上述20日动量中文请求自行复测；已开着的旧chat请退出后重新启动，以加载新版本。

