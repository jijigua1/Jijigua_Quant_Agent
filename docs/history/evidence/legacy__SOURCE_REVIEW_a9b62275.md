> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-C 真实服务器资产与复用审查

## 补充验收采用的指定绘图入口

优先来源修正为 `<LOCAL_RESEARCH_ROOT>/backtest.ipynb` 最后一个 cell：`from core_backtest.api import *` → `run_final_notebook(CONFIG_FINAL)` → `load_final_data` / `run_final_backtest` / `final_factor_analysis` → **`core_backtest.plotting.plot_final_result`** → `save_final_result`。仅追踪源码，未运行 notebook 或账户引擎。最后一个 cell 没有保存输出；前四个历史 cell 的图形不作为终版来源。

已核对 `core_backtest/plotting.py` SHA-256 `d2b5a374e66d426eb33363dd5441709a25915ef884893ffdcd2a9bbddfe8dd52`：15×12三联图、高度比1.4:1:1；策略红#c84b31、基准蓝灰#475f78、相对灰#8a929a；曲线1.0—1.7、弱虚线y网格、零轴、无框图例、百分比轴、分组柱宽0.65与正负百分比标注、tight_layout(pad=2)、输出160dpi。其数据合同为 nav/drawdowns/metrics 与 factor.groups，不适用于将当前因子毛收益当作账户曲线。

Agent 的 `server_plot.annotate_group_returns` 适配原终版分组百分比标注；`research_report` 复用上述配色、零线、图例与网格规范。使用因子自己的7.2×3.3画幅、300dpi与训练/验证层次；带数值标注的分组图取消网格以避免穿过文字。Perry字体函数作为辅助字体发现，已不作为主要绘图风格来源。日期轴使用稀疏ConciseDateFormatter。

原项目已有图样 `output/research_demo_20261005_v2/output/final_backtest/20261005_154752_092445/backtest_result_final.png` 已复制为 `notebook-final-original-synthetic.png` 并实际检查；**这是已有合成演示，不是本轮真实行情回测证据**。源码/样本指纹在 `notebook-final-provenance.json`。原项目源码未改动。

2026-10-12。有界只读检查，不批量加载因子库，不修改研究人员项目。完整路径/源码SHA-256见source-inspection.json；三份样本完整静态操作码与数值缓冲区证据见factor-header-inspection.json。未知原始PKL没有动态反序列化。

## 因子格式：先检查实际消费代码

| 真实样本 | 静态观察形状 | 日期字面范围 | 数值缓冲区 |
|---|---:|---|---|
| /hy-tmp/data/factor/CommonMetrics/ACD_R5.pkl.zip | 183×5213 | 20260105—20261009 | float64，NaN 12534，inf 0 |
| /hy-tmp/data/factor/eod1/factor1.pkl.zip | 183×5214 | 同上 | float64，NaN 5378，inf 0 |
| /hy-tmp/data/factor/wq/wq_032_R5.pkl.zip | 183×4998 | 同上 | float64，NaN 62579，inf 0 |

三份单文件Zip约6—7MiB、解压不足10MiB，pickle协议4。静态DataFrame/BlockManager/ArrowStringArray操作码、日期和代码offset缓冲区、f8长度互相对应；不是执行对象认证。日期/Code字符串轴，代码含交易所后缀；股票池并不完全一致。只提取已发布daily65的50个代码映射，三份样本一致。新资源代码不能靠前缀猜后缀，未核对时拒绝导出。

生成证据：Gyc trim_407_factors_to_2026.py使用单DataFrame、协议4、.pkl.zip、临时文件+验证+替换；merge_440_moneyflow46.py使用日期交集、参考股票列序、缺失保留NaN。原程序未执行。

| 真实消费入口 | 合同与新输出 | 验证边界 |
|---|---|---|
| Gyc analyze_3030_neutral_vwap_20261005.py:norm_index | 单面板，日期去横线截8位；代码去后缀补6位；唯一且日期排序。factor.pkl/.pkl.zip；factor_plain.pkl为六位兼容输出 | 原模块有生产导入及环境副作用，只抽取未改函数在受控测试中运行 |
| Perry model/data_load_process.py:load_and_pivot_factors | dict[因子名,宽表]→date:stock×factor；factor_dict.pkl | 原函数未改，受控新文件真实调用；原有float32转换按float32预期核对，不声称保持float64精度 |
| Pyx GP/src/gp_factor_miner/data.py:load_eod_panel_dataset | 因子dict，规范字符串轴并与价格/目标交集 | 静态合同审查；其2016—2022区间、目标文件、PyArrow依赖未满足，不执行完整GP流程 |
| Gyc合并程序、Perry完整模型/回测 | 有附加数据、股票池、资格与模型依赖 | 没有执行完整消费程序或声称策略可用 |

主输出使用常规字符串Index而非ArrowStringArray：消费代码使用astype(str)/索引对齐，语义兼容，避免强制新增PyArrow。非MultiIndex；数值float64；日期升序；股票列依可信资源顺序；没有标签、测试绩效、账户记录。字典和面板是分别命名的适配文件，不混用。

读回安全：先将CSV数值构造成固定预期对象，用当前程序固定协议序列化；必须整文件字节完全一致，才读取自产PKL。只有manifest SHA相同不能授予未知pickle加载权限。符号链接/硬链接、超限文件、无限值、非法日期/代码、未知对象和覆盖旧文件均拒绝。原库含numpy._core与Arrow版本依赖，未假装已在Agent环境安全读取。

## 绘图来源与实际样例

Perry `/opt/external-research/策略回测/backtest_visualization.py` 的SHA-256为aad04db19cdaafd07b1b3b9c65535a9e6abbbb84382999db8c4a1700c5b11aa5。精确复用纯函数configure_chinese_font；函数指纹在adaptation-provenance.json。通过真实字形检查选中文字体；英文金融图采用DejaVu Sans、CJK备用，PDF嵌入字体，SVG文本保持可编辑。复用该模块克制蓝/中性色、PercentFormatter、稀疏日期定位器。新增布局由独立报告模块完成，不导入整套回测程序。

实际检查 `/opt/external-research/backtest.ipynb`（仅JSON读取、不执行）的两个既有PNG，保存perry-source-preview-1/2.png。历史样例的拥挤分组标注和累计收益解释不继承；它们只是视觉来源，绝非本轮真实市场验证。实际复用范围为用户授权研究代码的纯字体函数与风格配置，未复制未知第三方专有组件；不是认证整套既有绘图为正确。

原qrtk 0.2.0的12模块和47份来源/合同文件维持原SHA。生产IC/RankIC、成熟标签、分组、共同股票相关性继续使用qrtk；独立标量公式只在验证脚本中使用。原独立SkillRuntime没有启动，新增自产资产和报告只由主Agent调度。
