> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：reversal



状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。



## 研究问题与假设



图表最终排版检查



假设：五日反转可能有预测性



## 因子定义与时间约束



```json

{

  "factor_id": "reversal",

  "lookback": 5,

  "standardization": "raw",

  "hypothesis": "五日反转可能有预测性",

  "generation_reason": "记录实际计算，不调优测试段"

}

```



输入截至 T 收盘。只允许历史偏移；零分母与缺失输出 NaN，不填成零收益。

标签：open[T+1+H] / open[T+1] − 1；T 表示已观察日期序号。

该数据未证明正式交易日历或历史发布时间，故不得将该标签当可执行交易收益。

方向 +1 预先固定，G0 分数最高；ICIR 未年化，重叠标签不独立。



## 数据合同与研究划分



资源：synthetic:history；360 观察日、20 只股票。

来源：fixed seeded synthetic fixture。

复权：none；成交量单位：shares；日历：observed_union。

可获得时间：synthetic after close；股票池：synthetic fixed twenty codes。



```json

{

  "factor_name": "reversal",

  "direction": 1,

  "horizon": 5,

  "lag": 1,

  "n_groups": 5,

  "min_obs": 10,

  "train": [

    "2023-01-02",

    "2023-10-30"

  ],

  "valid": [

    "2023-10-31",

    "2024-03-04"

  ],

  "test": [

    "2024-03-05",

    "2024-05-17"

  ],

  "universe_name": "synthetic fixed twenty codes",

  "execution_rule": "next_observed_open",

  "min_dates_per_split": 60

}

```



每个分段剔除出场日在段外的标签。验证段用于探索，看到结果后改参数不能称独立样本外。

test=sealed 仅隐藏本工具统计输出；daily65 原始数据已有其他授权读取路径，**不是全系统盲测**。

真正独立测试应单独发布、阻断所有原始价格/标签/绩效通路并冻结假设后验收。



## 实际计算结果



| Split | Mature dates | IC mean | RankIC mean | RankIC positive share | G0−G last gross |

|---|---|---|---|---|---|

| train | 205 | 0.00655443 | 0.0049514 | 0.507317 | -0.00100566 |

| valid | 84 | 0.0206888 | 0.0239169 | 0.547619 | -1.27096e-05 |



分组为等权、未扣成本的 H 观察日毛收益；不是净值、Sharpe 或可交易收益。



## 稳健性、证据与回测准入



截断测试：True；证据等级：insufficient。

正式回测：BLOCKED_DATA_CONTRACT / BLOCKED_ENGINE_QUALIFICATION，无账户绩效和账户图表。

尚需复权与公司行动、独立买卖状态、退市、费用历史、合格引擎逐日账本与独立样本外验证。



## 研究局限



- synthetic only

- labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5

- test is sealed; no independent test claim

- IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores

- group returns are gross, equal weight, missing labels excluded; not account returns

- no industry/size neutralisation, HAC or multiple-testing adjustment

- positive observed volume is sample eligibility, not permission to buy/sell

- all parameter changes after seeing validation are exploratory; no certified out-of-sample performance



## 图表（由实际 CSV 生成）



!ic_rankic（原内部附件未公开）



!ic_distribution（原内部附件未公开）



!group_returns_gross（原内部附件未公开）



!factor_coverage（原内部附件未公开）



!factor_distribution（原内部附件未公开）



## 复现与成果



数据 SHA-256：`43af39978676e44bc4e20e6f982a307d902e42c05261935107497b56ef7a0901`



参数指纹：`7579c465a177534b3f72c343ee51297c15d0032eedb44729c8c44f13343f3c95`。完整代码、依赖、调用版本及文件 SHA-256 见 manifest.json。



受控复现入口：`python code/reproduce.py`（同版本依赖；只读本成果 data/input_slice.csv）。



/hy-tmp 为临时存储，请自行备份；前台 SSH 断开不保证任务继续。

