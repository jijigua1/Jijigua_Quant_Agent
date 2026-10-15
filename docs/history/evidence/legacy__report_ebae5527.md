> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：expression

状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。

## 研究问题与假设

在已登记资源 gpushare:daily65（真实日频未复权，50只代码，2026-07-03至2026-10-09）上构造并检验“放量滞涨”因子：假设为成交量相对放大而价格涨幅偏低的股票未来收益更高。用受控表达式实现，例如以成交量相对其历史均值的放大程度（volume/mean(volume, N)）与同期价格涨幅（close/ref(close, N)-1）组合，取“放量且滞涨”方向（放量程度高、涨幅低者为高因子值）。先做因子计算与IC/RankIC、分组毛收益检验，horizon=5、n_groups=5、standardization=raw，并生成图表与Markdown/HTML报告。若需与上一实验（reversal, lookback=5）比较，传 parent_study_id=INTERNAL_RUN_ID_REDACTED:ca951799d1b24473。注意样本仅65个观测日期、未复权价格、标签重叠h=5，结论仅作探索性证据。

假设：成交量相对其历史均值放大、而同期价格涨幅偏低的股票，未来5日收益更高；即“放量滞涨”为正向信号。构造上取放量程度高、涨幅低者为高因子值。

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
        "window": 5
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
  "expression_sha256": "0ab43160e43a796bd7a9c0a71cba0fdc70c03383725d78b3df5e3c02d6cbabec",
  "input_fields": [
    "close",
    "volume"
  ],
  "nodes": 13,
  "warmup_observations": 5,
  "formula": "sub(cs_rank(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),1)),cs_rank(returns(close,5)))",
  "output_units": {
    "price_power": 0,
    "volume_power": 0
  },
  "available_time": "T close after all required input observations; historical publication time requires data contract",
  "zero_denominator": "NaN",
  "rolling_min_periods": "full window",
  "rank_ties": "average",
  "std_ddof": 1,
  "hypothesis": "成交量相对其历史均值放大、而同期价格涨幅偏低的股票，未来5日收益更高；即“放量滞涨”为正向信号，放量程度高且涨幅低者为高因子值。",
  "generation_reason": "用 volume/delay(rolling_mean(volume,5),1)-1 度量放量程度（delay 避免当前成交量混入历史均值），用 returns(close,5) 度量同期涨幅；对两者分别做横截面排名后相减（放量排名 - 涨幅排名），使放量高、涨幅低者取高值，方向与假设一致。horizon=5、n_groups=5、raw，与上一 reversal 实验同数据同分段对照。"
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
| train | 28 | 0.0253977 | -0.0055328 | 0.535714 | 0.010254 |
| valid | 10 | 0.118361 | 0.163334 | 0.7 | 0.0190213 |

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
  "parent_study_id": "INTERNAL_RUN_ID_REDACTED:ca951799d1b24473",
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
            "window": 5
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
      "expression_sha256": "0ab43160e43a796bd7a9c0a71cba0fdc70c03383725d78b3df5e3c02d6cbabec",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 13,
      "warmup_observations": 5,
      "formula": "sub(cs_rank(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),1)),cs_rank(returns(close,5)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量相对其历史均值放大、而同期价格涨幅偏低的股票，未来5日收益更高；即“放量滞涨”为正向信号，放量程度高且涨幅低者为高因子值。",
      "generation_reason": "用 volume/delay(rolling_mean(volume,5),1)-1 度量放量程度（delay 避免当前成交量混入历史均值），用 returns(close,5) 度量同期涨幅；对两者分别做横截面排名后相减（放量排名 - 涨幅排名），使放量高、涨幅低者取高值，方向与假设一致。horizon=5、n_groups=5、raw，与上一 reversal 实验同数据同分段对照。"
    },
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:ca951799d1b24473"
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
    "train": -0.031247251890062465,
    "valid": 0.01348788383771668
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
