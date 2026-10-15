> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：expression

状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。

## 研究问题与假设

在已登记资源 gpushare:daily65（日频、未复权、2026-07-03 至 2026-10-09）上构造并检验“放量滞涨”因子：假设成交量相对放大而价格涨幅偏低的股票未来短期相对表现更好。因子定义采用受控表达式，例如以 volume 相对过去 N 日均量的放大倍数与同期收益的负向组合，如 neg(returns(close,5)) 与 volume/mean(volume,5) 的乘积或比值形式，具体表达式需符合 op 白名单、历史窗口与最多 40 节点 8 层限制。参数：lookback=5，horizon=5，n_groups=5，standardization=raw。输出 IC/RankIC、分组毛收益、图表与 Markdown/HTML 报告，保留封存测试段 2026-09-18 至 2026-10-09，并给出证据充分性判定与限制说明。

假设：在已登记资源 gpushare:daily65（日频、未复权、2026-07-03 至 2026-10-09）上，成交量相对过去5日均量放大而同期价格涨幅偏低的股票，未来5个交易日相对表现更好；即“放量滞涨”因子（量比放大与负向收益的组合）与未来收益正相关，IC/RankIC 为正，分组毛收益随因子值升高呈单调上升。

## 因子定义与时间约束

```json
{
  "operator_version": "1.0.0",
  "expression": {
    "nodes": [
      {
        "op": "field",
        "field": "close"
      },
      {
        "op": "returns",
        "args": [
          0
        ],
        "window": 5
      },
      {
        "op": "neg",
        "args": [
          1
        ]
      },
      {
        "op": "field",
        "field": "volume"
      },
      {
        "op": "rolling_mean",
        "args": [
          3
        ],
        "window": 5
      },
      {
        "op": "delay",
        "args": [
          4
        ],
        "window": 1
      },
      {
        "op": "div",
        "args": [
          3,
          5
        ]
      },
      {
        "op": "mul",
        "args": [
          2,
          6
        ]
      }
    ],
    "output": 7
  },
  "expression_sha256": "e72bfc62b7a6260074861d093827f04ebea3b3f3e5e03213e2431688ceb4709c",
  "input_fields": [
    "close",
    "volume"
  ],
  "nodes": 8,
  "warmup_observations": 5,
  "formula": "mul(neg(returns(close,5)),div(volume,delay(rolling_mean(volume,5),1)))",
  "output_units": {
    "price_power": 0,
    "volume_power": 0
  },
  "available_time": "T close after all required input observations; historical publication time requires data contract",
  "zero_denominator": "NaN",
  "rolling_min_periods": "full window",
  "rank_ties": "average",
  "std_ddof": 1,
  "hypothesis": "成交量相对过去5日均量放大而同期价格涨幅偏低的股票，未来5个交易日相对表现更好：放量滞涨因子（量比放大 × 负向5日收益）与未来收益正相关，IC/RankIC 为正，分组毛收益随因子值升高呈单调上升。",
  "generation_reason": "用户提出新的放量滞涨想法，与已有五日反转因子不同，需用受控表达式新建实验。量比采用 volume / delay(rolling_mean(volume,5),1)，避免当前成交量混入历史均值；再与 neg(returns(close,5)) 相乘，使“放量且滞涨”的股票因子值更高。参数 lookback=5、horizon=5、n_groups=5、standardization=raw，保留封存测试段，并以已有 study_id 作为 parent_study_id 对照同一数据、H、分组与时间分段。"
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
| train | 28 | 0.0633967 | 0.0382677 | 0.535714 | 0.0137209 |
| valid | 10 | 0.115055 | 0.137242 | 0.7 | 0.0153817 |

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
  "parent_study_id": "INTERNAL_RUN_ID_REDACTED:b7efefaff8cb4cb8",
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
            "field": "close"
          },
          {
            "op": "returns",
            "args": [
              0
            ],
            "window": 5
          },
          {
            "op": "neg",
            "args": [
              1
            ]
          },
          {
            "op": "field",
            "field": "volume"
          },
          {
            "op": "rolling_mean",
            "args": [
              3
            ],
            "window": 5
          },
          {
            "op": "delay",
            "args": [
              4
            ],
            "window": 1
          },
          {
            "op": "div",
            "args": [
              3,
              5
            ]
          },
          {
            "op": "mul",
            "args": [
              2,
              6
            ]
          }
        ],
        "output": 7
      },
      "expression_sha256": "e72bfc62b7a6260074861d093827f04ebea3b3f3e5e03213e2431688ceb4709c",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 8,
      "warmup_observations": 5,
      "formula": "mul(neg(returns(close,5)),div(volume,delay(rolling_mean(volume,5),1)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量相对过去5日均量放大而同期价格涨幅偏低的股票，未来5个交易日相对表现更好：放量滞涨因子（量比放大 × 负向5日收益）与未来收益正相关，IC/RankIC 为正，分组毛收益随因子值升高呈单调上升。",
      "generation_reason": "用户提出新的放量滞涨想法，与已有五日反转因子不同，需用受控表达式新建实验。量比采用 volume / delay(rolling_mean(volume,5),1)，避免当前成交量混入历史均值；再与 neg(returns(close,5)) 相乘，使“放量且滞涨”的股票因子值更高。参数 lookback=5、horizon=5、n_groups=5、standardization=raw，保留封存测试段，并以已有 study_id 作为 parent_study_id 对照同一数据、H、分组与时间分段。"
    },
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:b7efefaff8cb4cb8"
  },
  "independent_test": false,
  "rank_ic_delta": {
    "train": 0.012553284598648226,
    "valid": -0.012604069220646441
  }
}
```


## 图表（由实际 CSV 生成）

!ic_rankic（原内部附件未公开）

!ic_distribution（原内部附件未公开）

!group_returns_gross（原内部附件未公开）

!factor_coverage（原内部附件未公开）

!factor_distribution（原内部附件未公开）

## 复现与成果

数据 SHA-256：`d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8`

参数指纹：`a241dd505f10718803a3a03b23f143e93ff3dcdea50926f1ecfd563b7dd7ff31`。完整代码、依赖、调用版本及文件 SHA-256 见 manifest.json。

受控复现入口：`python code/reproduce.py`（同版本依赖；只读本成果 data/input_slice.csv）。

/hy-tmp 为临时存储，请自行备份；前台 SSH 断开不保证任务继续。
