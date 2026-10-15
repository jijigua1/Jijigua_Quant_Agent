> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：expression

状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。

## 研究问题与假设

在已登记资源 gpushare:daily65（2026-07-03 至 2026-10-09，未复权日频 OHLC）上构造并检验“放量滞涨”因子：假设为成交量相对放大但价格涨幅偏低的股票未来收益更高。用受控表达式实现，例如以 volume 相对其 N 日均值的放大倍数（volume/mean(volume,N)）与同期价格涨幅（close/close[N]-1）组合，取“放量且滞涨”方向（放量倍数高、涨幅低者为高分）。先查询该资源可用字段与口径，再提交 qrtk_expression_study，参数 horizon=5、n_groups=5、standardization=raw，并给出 hypothesis 与 reason。若需与上一实验（study_id INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e，五日反转因子）比较，传 parent_study_id。输出 IC/RankIC、分组毛收益与图表，并说明样本仅65个观测日、标签重叠、未复权等限制，测试段封存，不作策略有效性结论。

假设：成交量相对其N日均值放大（放量）且同期价格涨幅偏低（滞涨）的股票，未来5日收益更高；即高分端应为高放量倍数、低价格涨幅。

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
        "op": "field",
        "field": "close"
      },
      {
        "op": "returns",
        "args": [
          5
        ],
        "window": 5
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
  "expression_sha256": "ca7e4727b12531c76962914ad1324529e4f6f74392703910b46e96f6f1ad422b",
  "input_fields": [
    "close",
    "volume"
  ],
  "nodes": 9,
  "warmup_observations": 5,
  "formula": "add(div(volume,delay(rolling_mean(volume,5),1)),neg(returns(close,5)))",
  "output_units": {
    "price_power": 0,
    "volume_power": 0
  },
  "available_time": "T close after all required input observations; historical publication time requires data contract",
  "zero_denominator": "NaN",
  "rolling_min_periods": "full window",
  "rank_ties": "average",
  "std_ddof": 1,
  "hypothesis": "成交量相对其N日均值放大（放量）且同期价格涨幅偏低（滞涨）的股票，未来5日收益更高；即高分端应为高放量倍数、低价格涨幅。",
  "generation_reason": "上一实验（study_id INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e）为五日反转因子 reversal=-(close[T]/close[T-5]-1)，仅用价格维度。本实验引入成交量维度，构造放量滞涨因子，检验量价组合是否比纯价格反转提供不同信息；将 parent_study_id 设为该 study_id，以在同一资源、同一 horizon=5、n_groups=5、standardization=raw 及相同时间分段下对照。构造：volume/delay(rolling_mean(volume,5),1) 为放量倍数（历史均值不含当日），neg(returns(close,5)) 为滞涨方向，两者相加使高分端对应高放量、低涨幅。"
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
| train | 28 | -0.0757475 | -0.065897 | 0.392857 | -0.0112074 |
| valid | 10 | -0.0157658 | -0.0662881 | 0.4 | -0.0188797 |

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
- train: only 28 valid RankIC dates (< 60)
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
  "parent_study_id": "INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e",
  "parent_parameters": {
    "factor_id": "reversal",
    "horizon": 5,
    "lookback": 5,
    "n_groups": 5,
    "resource_id": "gpushare:daily65",
    "standardization": "raw"
  },
  "current_parameters": {
    "resource_id": "gpushare:daily65",
    "factor_id": "expression",
    "lookback": 5,
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
            "op": "field",
            "field": "close"
          },
          {
            "op": "returns",
            "args": [
              5
            ],
            "window": 5
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
      "expression_sha256": "ca7e4727b12531c76962914ad1324529e4f6f74392703910b46e96f6f1ad422b",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 9,
      "warmup_observations": 5,
      "formula": "add(div(volume,delay(rolling_mean(volume,5),1)),neg(returns(close,5)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量相对其N日均值放大（放量）且同期价格涨幅偏低（滞涨）的股票，未来5日收益更高；即高分端应为高放量倍数、低价格涨幅。",
      "generation_reason": "上一实验（study_id INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e）为五日反转因子 reversal=-(close[T]/close[T-5]-1)，仅用价格维度。本实验引入成交量维度，构造放量滞涨因子，检验量价组合是否比纯价格反转提供不同信息；将 parent_study_id 设为该 study_id，以在同一资源、同一 horizon=5、n_groups=5、standardization=raw 及相同时间分段下对照。构造：volume/delay(rolling_mean(volume,5),1) 为放量倍数（历史均值不含当日），neg(returns(close,5)) 为滞涨方向，两者相加使高分端对应高放量、低涨幅。"
    },
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:446a71952c2c4c6e"
  },
  "independent_test": false,
  "parent_statistics": {
    "train": {
      "ic": {
        "icir": 0.1752838090702972,
        "mean": 0.04977170482884974,
        "n_dates": 28,
        "positive_ratio": 0.6071428571428571,
        "std": 0.2839492426188029
      },
      "rank_ic": {
        "icir": 0.09879235227070986,
        "mean": 0.02571445113631573,
        "n_dates": 28,
        "positive_ratio": 0.5714285714285714,
        "std": 0.26028787193823705
      }
    },
    "valid": {
      "ic": {
        "icir": 0.4253674926214821,
        "mean": 0.15683501504754224,
        "n_dates": 10,
        "positive_ratio": 0.6,
        "std": 0.36870475005268816
      },
      "rank_ic": {
        "icir": 0.8825774202005592,
        "mean": 0.1498458681508709,
        "n_dates": 10,
        "positive_ratio": 0.7,
        "std": 0.169782123042327
      }
    }
  },
  "rank_ic_delta": {
    "train": -0.09161148618980633,
    "valid": -0.2161339648033143
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
