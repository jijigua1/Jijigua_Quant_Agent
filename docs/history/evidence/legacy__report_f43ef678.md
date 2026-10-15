> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：expression

状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。

## 研究问题与假设

在 gpushare:daily65（真实日频未复权，50只代码，65个观测日期，2026-07-03至2026-10-09）上，将本会话已构造的“放量滞涨”因子（表达式 sub(cs_rank(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),1)),cs_rank(returns(close,5)))，即放量程度横截面排名减5日涨幅横截面排名）的观察窗口由5日改为10日，即把 returns(close,5) 改为 returns(close,10)，其余参数保持 horizon=5、n_groups=5、standardization=raw、lag=1、执行规则 next_observed_open，时间划分 train 2026-07-03至2026-08-26、valid 2026-08-27至2026-09-17、test sealed。传入 parent_study_id=INTERNAL_RUN_ID_REDACTED:3e8a3580a8ac4dc2 以与上一实验（5日窗口）比较，输出 IC/RankIC、分组毛收益、覆盖与图表报告，并说明短样本与未复权价格限制。

假设：将“放量滞涨”因子中的价格观察窗口由5日延长至10日，可更完整地刻画放量后价格未充分上涨的状态；预期放量程度横截面排名减10日涨幅横截面排名仍为正向信号，即放量高、10日涨幅低者未来5日收益更高，方向与5日窗口版本一致。

## 因子定义与时间约束

```json
{
  "operator_version": "1.0.0",
  "expression": {
    "nodes": [
      {
        "op": "field",
        "field": "volume"
      },
      {
        "op": "field",
        "field": "volume"
      },
      {
        "op": "rolling_mean",
        "args": [
          1
        ],
        "window": 5
      },
      {
        "op": "delay",
        "args": [
          2
        ],
        "window": 1
      },
      {
        "op": "div",
        "args": [
          0,
          3
        ]
      },
      {
        "op": "constant",
        "value": 1
      },
      {
        "op": "sub",
        "args": [
          4,
          5
        ]
      },
      {
        "op": "max",
        "args": [
          6,
          5
        ]
      },
      {
        "op": "field",
        "field": "close"
      },
      {
        "op": "returns",
        "args": [
          8
        ],
        "window": 10
      },
      {
        "op": "cs_rank",
        "args": [
          7
        ]
      },
      {
        "op": "cs_rank",
        "args": [
          9
        ]
      },
      {
        "op": "sub",
        "args": [
          10,
          11
        ]
      }
    ],
    "output": 12
  },
  "expression_sha256": "e59de407b3ef3b7df12d3e31ebc44c61faadf4b5a276f005c34762ed69e653eb",
  "input_fields": [
    "close",
    "volume"
  ],
  "nodes": 13,
  "warmup_observations": 10,
  "formula": "sub(cs_rank(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),1)),cs_rank(returns(close,10)))",
  "output_units": {
    "price_power": 0,
    "volume_power": 0
  },
  "available_time": "T close after all required input observations; historical publication time requires data contract",
  "zero_denominator": "NaN",
  "rolling_min_periods": "full window",
  "rank_ties": "average",
  "std_ddof": 1,
  "hypothesis": "将“放量滞涨”因子中的价格观察窗口由5日延长至10日，可更完整地刻画放量后价格未充分上涨的状态；预期放量程度横截面排名减10日涨幅横截面排名仍为正向信号，即放量高、10日涨幅低者未来5日收益更高，方向与5日窗口版本一致。",
  "generation_reason": "仅把 returns(close,5) 改为 returns(close,10)，其余节点与参数（horizon=5、n_groups=5、standardization=raw、lag=1、next_observed_open）保持不变，并传入 parent_study_id=INTERNAL_RUN_ID_REDACTED:3e8a3580a8ac4dc2，以便在同一数据、同一预测期、同一分组与同一时间分段下与5日窗口版本对照；该比较不是独立样本外验证。"
}
```

输入截至 T 收盘。只允许历史偏移；零分母与缺失输出 NaN，不填成零收益。
标签：open[T+1+H] / open[T+1] − 1；T 表示已观察日期序号。
该数据未证明正式交易日历或历史发布时间，故不得将该标签当可执行交易收益。
方向 +1 预先固定，G0 分数最高；ICIR 未年化，重叠标签不独立。

## 数据合同与研究划分

资源：gpushare:daily65；65 观察日、50 只股票。
来源：GPUShare published recent_days TRD_Dalyr.csv; reviewed production Tushare field conversion, some mixed-source publication。
复权：none；成交量单位：shares；日历：observed_union。
可获得时间：after T close; historical per-row fetched_at not fully verified; trade date is not availability time；股票池：fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe。

```json
{
  "factor_name": "expression",
  "direction": 1,
  "horizon": 5,
  "lag": 1,
  "n_groups": 5,
  "min_obs": 10,
  "train": [
    "2026-07-03",
    "2026-08-26"
  ],
  "valid": [
    "2026-08-27",
    "2026-09-17"
  ],
  "test": [
    "2026-09-18",
    "2026-10-09"
  ],
  "universe_name": "fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe",
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
| train | 23 | 0.0145073 | 0.0413332 | 0.565217 | 0.00137835 |
| valid | 10 | 0.134593 | 0.130547 | 0.8 | 0.0250889 |

分组为等权、未扣成本的 H 观察日毛收益；不是净值、Sharpe 或可交易收益。

## 稳健性、证据与回测准入

截断测试：True；证据等级：insufficient。
正式回测：BLOCKED_DATA_CONTRACT / BLOCKED_ENGINE_QUALIFICATION，无账户绩效和账户图表。
尚需复权与公司行动、独立买卖状态、退市、费用历史、合格引擎逐日账本与独立样本外验证。

## 研究局限

- only 65 observed dates, each train/validation segment may have fewer than 60 mature labels
- unadjusted prices: corporate actions can distort returns; no strategy efficacy claim
- observed date union is not independently verified exchange calendar
- historical availability, suspension, limits, delisting and full universe not fully verified
- labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5
- train: only 23 valid RankIC dates (< 60)
- train: mean factor coverage 0.69 < 0.80
- valid: only 10 valid RankIC dates (< 60)
- test is sealed; no independent test claim
- IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores
- group returns are gross, equal weight, missing labels excluded; not account returns
- no industry/size neutralisation, HAC or multiple-testing adjustment
- positive observed volume is sample eligibility, not permission to buy/sell
- all parameter changes after seeing validation are exploratory; no certified out-of-sample performance

## 与父实验对照（探索性）

```json
{
  "parent_study_id": "INTERNAL_RUN_ID_REDACTED:3e8a3580a8ac4dc2",
  "parent_parameters": {
    "definition": {
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "expression": {
        "nodes": [
          {
            "field": "volume",
            "op": "field"
          },
          {
            "field": "volume",
            "op": "field"
          },
          {
            "args": [
              1
            ],
            "op": "rolling_mean",
            "window": 5
          },
          {
            "args": [
              2
            ],
            "op": "delay",
            "window": 1
          },
          {
            "args": [
              0,
              3
            ],
            "op": "div"
          },
          {
            "op": "constant",
            "value": 1
          },
          {
            "args": [
              4,
              5
            ],
            "op": "sub"
          },
          {
            "args": [
              6,
              5
            ],
            "op": "max"
          },
          {
            "field": "close",
            "op": "field"
          },
          {
            "args": [
              8
            ],
            "op": "returns",
            "window": 5
          },
          {
            "args": [
              7
            ],
            "op": "cs_rank"
          },
          {
            "args": [
              9
            ],
            "op": "cs_rank"
          },
          {
            "args": [
              10,
              11
            ],
            "op": "sub"
          }
        ],
        "output": 12
      },
      "expression_sha256": "0ab43160e43a796bd7a9c0a71cba0fdc70c03383725d78b3df5e3c02d6cbabec",
      "formula": "sub(cs_rank(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),1)),cs_rank(returns(close,5)))",
      "generation_reason": "用 volume/delay(rolling_mean(volume,5),1)-1 度量放量程度（delay 避免当前成交量混入历史均值），用 returns(close,5) 度量同期涨幅；对两者分别做横截面排名后相减（放量排名 - 涨幅排名），使放量高、涨幅低者取高值，方向与假设一致。horizon=5、n_groups=5、raw，与上一 reversal 实验同数据同分段对照。",
      "hypothesis": "成交量相对其历史均值放大、而同期价格涨幅偏低的股票，未来5日收益更高；即“放量滞涨”为正向信号，放量程度高且涨幅低者为高因子值。",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 13,
      "operator_version": "1.0.0",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "rank_ties": "average",
      "rolling_min_periods": "full window",
      "std_ddof": 1,
      "warmup_observations": 5,
      "zero_denominator": "NaN"
    },
    "factor_id": "expression",
    "horizon": 5,
    "lookback": 5,
    "n_groups": 5,
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:ca951799d1b24473",
    "resource_id": "gpushare:daily65",
    "standardization": "raw"
  },
  "current_parameters": {
    "resource_id": "gpushare:daily65",
    "factor_id": "expression",
    "lookback": 10,
    "horizon": 5,
    "n_groups": 5,
    "standardization": "raw",
    "definition": {
      "operator_version": "1.0.0",
      "expression": {
        "nodes": [
          {
            "op": "field",
            "field": "volume"
          },
          {
            "op": "field",
            "field": "volume"
          },
          {
            "op": "rolling_mean",
            "args": [
              1
            ],
            "window": 5
          },
          {
            "op": "delay",
            "args": [
              2
            ],
            "window": 1
          },
          {
            "op": "div",
            "args": [
              0,
              3
            ]
          },
          {
            "op": "constant",
            "value": 1
          },
          {
            "op": "sub",
            "args": [
              4,
              5
            ]
          },
          {
            "op": "max",
            "args": [
              6,
              5
            ]
          },
          {
            "op": "field",
            "field": "close"
          },
          {
            "op": "returns",
            "args": [
              8
            ],
            "window": 10
          },
          {
            "op": "cs_rank",
            "args": [
              7
            ]
          },
          {
            "op": "cs_rank",
            "args": [
              9
            ]
          },
          {
            "op": "sub",
            "args": [
              10,
              11
            ]
          }
        ],
        "output": 12
      },
      "expression_sha256": "e59de407b3ef3b7df12d3e31ebc44c61faadf4b5a276f005c34762ed69e653eb",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 13,
      "warmup_observations": 10,
      "formula": "sub(cs_rank(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),1)),cs_rank(returns(close,10)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "将“放量滞涨”因子中的价格观察窗口由5日延长至10日，可更完整地刻画放量后价格未充分上涨的状态；预期放量程度横截面排名减10日涨幅横截面排名仍为正向信号，即放量高、10日涨幅低者未来5日收益更高，方向与5日窗口版本一致。",
      "generation_reason": "仅把 returns(close,5) 改为 returns(close,10)，其余节点与参数（horizon=5、n_groups=5、standardization=raw、lag=1、next_observed_open）保持不变，并传入 parent_study_id=INTERNAL_RUN_ID_REDACTED:3e8a3580a8ac4dc2，以便在同一数据、同一预测期、同一分组与同一时间分段下与5日窗口版本对照；该比较不是独立样本外验证。"
    },
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:3e8a3580a8ac4dc2"
  },
  "independent_test": false,
  "parent_statistics": {
    "train": {
      "ic": {
        "icir": 0.10002199194554828,
        "mean": 0.025397687887667553,
        "n_dates": 28,
        "positive_ratio": 0.5714285714285714,
        "std": 0.2539210367005487
      },
      "rank_ic": {
        "icir": -0.021548629691160573,
        "mean": -0.005532800753746734,
        "n_dates": 28,
        "positive_ratio": 0.5357142857142857,
        "std": 0.2567588210036546
      }
    },
    "valid": {
      "ic": {
        "icir": 0.6237887203340429,
        "mean": 0.11836078412136149,
        "n_dates": 10,
        "positive_ratio": 0.6,
        "std": 0.18974498938996287
      },
      "rank_ic": {
        "icir": 0.8860201806661931,
        "mean": 0.16333375198858757,
        "n_dates": 10,
        "positive_ratio": 0.7,
        "std": 0.18434540832442206
      }
    }
  },
  "rank_ic_delta": {
    "train": 0.0468660208238683,
    "valid": -0.032787136080818624
  }
}
```


## 图表（由实际 CSV 生成）

!ic_rankic（原内部附件未公开）

!ic_distribution（原内部附件未公开）

!group_returns_gross（原内部附件未公开）

!factor_coverage（原内部附件未公开）

!factor_distribution（原内部附件未公开）

!experiment_comparison（原内部附件未公开）

## 复现与成果

数据 SHA-256：`d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8`

参数指纹：`a241dd505f10718803a3a03b23f143e93ff3dcdea50926f1ecfd563b7dd7ff31`。完整代码、依赖、调用版本及文件 SHA-256 见 manifest.json。

受控复现入口：`python code/reproduce.py`（同版本依赖；只读本成果 data/input_slice.csv）。

/hy-tmp 为临时存储，请自行备份；前台 SSH 断开不保证任务继续。
