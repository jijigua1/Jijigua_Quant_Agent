> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：expression

状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。

## 研究问题与假设

在资源 gpushare:daily65（2026-07-03 至 2026-10-09，65个观测日，50只代码，未复权）上，将上一实验的放量滞涨因子观察窗口从5日改为10日并做对照。因子表达式：add(div(volume,delay(rolling_mean(volume,10),1)),neg(returns(close,10)))，即放量倍数用10日均量（历史均值不含当日）、滞涨方向用10日价格涨幅取负。参数：horizon=5、n_groups=5、standardization=raw、lag=1、执行规则 next_observed_open、方向+1预先固定，并做 lookahead 检查。将 parent_study_id 设为上一实验 INTERNAL_RUN_ID_REDACTED:eb7c1d4f20d84872，以在同一资源、同一 horizon、同一分组与标准化、相同时间分段下比较10日窗口与5日窗口的 IC/RankIC、分组毛收益与多空毛收益差异；测试段保持封存，不输出独立测试结论。

假设：将放量滞涨因子的观察窗口由5日延长至10日后，放量倍数（volume/delay(rolling_mean(volume,10),1)）与滞涨方向（neg(returns(close,10))）的组合在5日预测期上仍应体现量价信息；若10日窗口更稳定，则其 IC/RankIC 与多空毛收益应优于5日窗口版本，且高分端（高放量、低10日涨幅）对应更高未来5日收益。

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
        "window": 10
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
        "op": "field",
        "field": "close"
      },
      {
        "op": "returns",
        "args": [
          5
        ],
        "window": 10
      },
      {
        "op": "neg",
        "args": [
          6
        ]
      },
      {
        "op": "add",
        "args": [
          4,
          7
        ]
      }
    ],
    "output": 8
  },
  "expression_sha256": "dff691062b47f102662aa7e12e2810ea42bc6929f851107a52514c9296da7bc9",
  "input_fields": [
    "close",
    "volume"
  ],
  "nodes": 9,
  "warmup_observations": 10,
  "formula": "add(div(volume,delay(rolling_mean(volume,10),1)),neg(returns(close,10)))",
  "output_units": {
    "price_power": 0,
    "volume_power": 0
  },
  "available_time": "T close after all required input observations; historical publication time requires data contract",
  "zero_denominator": "NaN",
  "rolling_min_periods": "full window",
  "rank_ties": "average",
  "std_ddof": 1,
  "hypothesis": "将放量滞涨因子的观察窗口由5日延长至10日后，放量倍数（volume/delay(rolling_mean(volume,10),1)）与滞涨方向（neg(returns(close,10))）的组合在5日预测期上仍应体现量价信息；若10日窗口更稳定，则其 IC/RankIC 与多空毛收益应优于5日窗口版本，且高分端（高放量、低10日涨幅）对应更高未来5日收益。",
  "generation_reason": "上一实验（study_id INTERNAL_RUN_ID_REDACTED:eb7c1d4f20d84872）使用5日窗口构造放量滞涨因子，训练段 RankIC 为 -0.0659、验证段 RankIC 为 -0.0663，符号与假设相反且弱于父实验五日反转因子。本次仅将观察窗口由5日改为10日（rolling_mean 与 returns 的 window 均由5改为10），其余构造逻辑、horizon=5、n_groups=5、standardization=raw、lag=1、执行规则 next_observed_open、方向+1及时间分段全部保持不变，并将 parent_study_id 设为该5日窗口实验，以在同一资源与同一评价口径下对照窗口长度的影响。测试段保持封存，不输出独立测试结论。"
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
IC时序、分布和分组CSV使用同一套按分段剔除的成熟标签；图中空白不插值，分布样本数等于训练及验证有效日期之和。
test=sealed 仅隐藏本工具统计输出；daily65 原始数据已有其他授权读取路径，**不是全系统盲测**。
真正独立测试应单独发布、阻断所有原始价格/标签/绩效通路并冻结假设后验收。

## 实际计算结果

| Split | Mature dates | IC mean | RankIC mean | RankIC positive share | G0−G last gross |
|---|---|---|---|---|---|
| train | 23 | -0.0649219 | -0.0763939 | 0.391304 | -0.0045635 |
| valid | 10 | -0.00596773 | -0.0401746 | 0.4 | -0.0125935 |

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
  "parent_study_id": "INTERNAL_RUN_ID_REDACTED:eb7c1d4f20d84872",
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
            "field": "close",
            "op": "field"
          },
          {
            "args": [
              5
            ],
            "op": "returns",
            "window": 5
          },
          {
            "args": [
              6
            ],
            "op": "neg"
          },
          {
            "args": [
              4,
              7
            ],
            "op": "add"
          }
        ],
        "output": 8
      },
      "expression_sha256": "ca7e4727b12531c76962914ad1324529e4f6f74392703910b46e96f6f1ad422b",
      "formula": "add(div(volume,delay(rolling_mean(volume,5),1)),neg(returns(close,5)))",
      "generation_reason": "上一实验（study_id INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e）为五日反转因子 reversal=-(close[T]/close[T-5]-1)，仅用价格维度。本实验引入成交量维度，构造放量滞涨因子，检验量价组合是否比纯价格反转提供不同信息；将 parent_study_id 设为该 study_id，以在同一资源、同一 horizon=5、n_groups=5、standardization=raw 及相同时间分段下对照。构造：volume/delay(rolling_mean(volume,5),1) 为放量倍数（历史均值不含当日），neg(returns(close,5)) 为滞涨方向，两者相加使高分端对应高放量、低涨幅。",
      "hypothesis": "成交量相对其N日均值放大（放量）且同期价格涨幅偏低（滞涨）的股票，未来5日收益更高；即高分端应为高放量倍数、低价格涨幅。",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 9,
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
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e",
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
            "window": 10
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
            "op": "field",
            "field": "close"
          },
          {
            "op": "returns",
            "args": [
              5
            ],
            "window": 10
          },
          {
            "op": "neg",
            "args": [
              6
            ]
          },
          {
            "op": "add",
            "args": [
              4,
              7
            ]
          }
        ],
        "output": 8
      },
      "expression_sha256": "dff691062b47f102662aa7e12e2810ea42bc6929f851107a52514c9296da7bc9",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 9,
      "warmup_observations": 10,
      "formula": "add(div(volume,delay(rolling_mean(volume,10),1)),neg(returns(close,10)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "将放量滞涨因子的观察窗口由5日延长至10日后，放量倍数（volume/delay(rolling_mean(volume,10),1)）与滞涨方向（neg(returns(close,10))）的组合在5日预测期上仍应体现量价信息；若10日窗口更稳定，则其 IC/RankIC 与多空毛收益应优于5日窗口版本，且高分端（高放量、低10日涨幅）对应更高未来5日收益。",
      "generation_reason": "上一实验（study_id INTERNAL_RUN_ID_REDACTED:eb7c1d4f20d84872）使用5日窗口构造放量滞涨因子，训练段 RankIC 为 -0.0659、验证段 RankIC 为 -0.0663，符号与假设相反且弱于父实验五日反转因子。本次仅将观察窗口由5日改为10日（rolling_mean 与 returns 的 window 均由5改为10），其余构造逻辑、horizon=5、n_groups=5、standardization=raw、lag=1、执行规则 next_observed_open、方向+1及时间分段全部保持不变，并将 parent_study_id 设为该5日窗口实验，以在同一资源与同一评价口径下对照窗口长度的影响。测试段保持封存，不输出独立测试结论。"
    },
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:eb7c1d4f20d84872"
  },
  "independent_test": false,
  "parent_statistics": {
    "train": {
      "ic": {
        "icir": -0.4505565750510749,
        "mean": -0.07574749032640783,
        "n_dates": 28,
        "positive_ratio": 0.2857142857142857,
        "std": 0.16811982006437512
      },
      "rank_ic": {
        "icir": -0.32988667017497014,
        "mean": -0.06589703505349061,
        "n_dates": 28,
        "positive_ratio": 0.39285714285714285,
        "std": 0.19975658615893502
      }
    },
    "valid": {
      "ic": {
        "icir": -0.06535950385723982,
        "mean": -0.01576584894251825,
        "n_dates": 10,
        "positive_ratio": 0.4,
        "std": 0.24121739015881283
      },
      "rank_ic": {
        "icir": -0.324805104450993,
        "mean": -0.0662880966524434,
        "n_dates": 10,
        "positive_ratio": 0.4,
        "std": 0.20408576018067176
      }
    }
  },
  "rank_ic_delta": {
    "train": -0.01049687971988697,
    "valid": 0.0261134779831805
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
