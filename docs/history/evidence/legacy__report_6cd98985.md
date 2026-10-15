> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · expression / 预热5观察日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

训练与验证的因子方向一致。训练/验证均值 RankIC 为 0.1021 / 0.0828。有效日期有限，当前仅支持探索性描述，不能确认预测效力。

gpushare:daily65 · 2026-07-03—2026-09-17 · 50只 · 复权=none · 创建 2026-10-12T12:53:04.307404+08:00

### IC / RankIC 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | 0.1014 | 0.1724 | 0.5883 | 28 |
| train | rank_ic | 0.1021 | 0.1665 | 0.6130 | 28 |
| valid | ic | 0.0842 | 0.3328 | 0.2529 | 10 |
| valid | rank_ic | 0.0828 | 0.1995 | 0.4152 | 10 |

PKL：/srv/jijigua-quant-agent/research_runs/2026-10-12/12-53-04_expression_d257d1db/data/factor.pkl

## 因子定义与经济假设

$$
f_{t,i}=\left(\max\left(\left(\frac{V_{t,i}}{\mathrm{Delay}_{1}\left(\mathrm{Mean}_{5}\left(V_{t,i}\right)\right)}-1\right),0\right)\cdot -\left(\left(\frac{C_{t,i}}{\mathrm{Delay}_{5}\left(C_{t,i}\right)}-1\right)\right)\right)
$$

在已批准的历史日频样本上，成交量相对放大且价格涨幅偏低（放量滞涨）的股票，未来短期收益更弱，因此该因子与未来收益呈负向关系，且分组毛收益应随因子值升高而单调下降。

C/O/H/L为收盘/开盘/最高/最低价，V为成交量，t为当前观察日，i为股票。Delay为历史偏移；Mean/Std/RankTS/CorrTS包含当日的完整历史窗口（Std: ddof=1）；RankCS为横截面百分位平均秩，ZCS为当日横截面样本标准化。固定放量滞涨的成交量均值使用前L日、不含当日。

## 预测能力

### 方向与有效股票

| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|
| train | ic | 85.71% | 48.6429 | 28 |
| train | rank_ic | 71.43% | 48.6429 | 28 |
| valid | ic | 60.00% | 48.0000 | 10 |
| valid | rank_ic | 60.00% | 48.0000 | 10 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | 0.0347 | 0.0294 | 32 |
| valid | 1 | 0.0810 | 0.1332 | 14 |
| train | 3 | 0.0907 | 0.0854 | 30 |
| valid | 3 | 0.0945 | 0.1019 | 12 |
| train | 5 | 0.1014 | 0.1021 | 28 |
| valid | 5 | 0.0842 | 0.0828 | 10 |
| train | 10 | 0.0955 | 0.0976 | 23 |
| valid | 10 | 0.2527 | 0.2510 | 5 |

### 统计推断准入

| 样本 | 指标 | 状态 | 有效日 | HAC滞后 |
|---|---|---|---|---|
| train | ic | insufficient | 33 | 4 |
| train | rank_ic | insufficient | 33 | 4 |
| valid | ic | insufficient | 10 | 4 |
| valid | rank_ic | insufficient | 10 | 4 |



## 稳定性与分布诊断

### 因子值与排序自相关

| 样本 | Lag | 值相关 | 秩相关 | 有效日 | 平均共同股票 |
|---|---|---|---|---|---|
| train | 1 | 0.4583 | 0.3573 | 33 | 48.7273 |
| valid | 1 | 0.4945 | 0.3419 | 16 | 48.0000 |
| train | 5 | -0.0277 | 0.0005 | 29 | 48.6552 |
| valid | 5 | 0.0346 | 0.0031 | 16 | 48.0000 |
| train | 10 | -0.0124 | -0.0254 | 24 | 48.5833 |
| valid | 10 | -0.0491 | 0.0472 | 16 | 48.0000 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | 0.1567 | 0.1090 | 11 |
| train | ic | second_half | 0.0656 | 0.1982 | 17 |
| train | rank_ic | first_half | 0.0847 | 0.1728 | 11 |
| train | rank_ic | second_half | 0.1133 | 0.1667 | 17 |
| valid | ic | first_half | 0.2286 | 0.3069 | 5 |
| valid | ic | second_half | -0.0603 | 0.3207 | 5 |
| valid | rank_ic | first_half | 0.1614 | 0.2122 | 5 |
| valid | rank_ic | second_half | 0.0043 | 0.1705 | 5 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 88.22% | 完整可见矩形含暖机 |
| 缺失率 | 11.78% | NaN保留 |
| 有效因子值 | 2426 | 训练+验证有限数值 |
| 均值 / 标准差 | -0.0109 / 0.0745 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | -14.3354 / 279.7179 | 无偏估计，小样本可N/A |
| 异常值比例 | 29.71% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 48 | 观察日，含暖机 |
| P01 / P50 / P99 | -0.2017 / 0.0000 / 0.0355 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | 1.26% | 4.19% | 28 |
| train | G1 | 1.58% | 3.16% | 28 |
| train | G2 | 0.23% | 3.00% | 28 |
| train | G3 | -0.00% | 3.50% | 28 |
| train | G4 | -0.58% | 3.98% | 28 |
| valid | G0 | -1.92% | 2.67% | 10 |
| valid | G1 | -0.92% | 2.33% | 10 |
| valid | G2 | -0.62% | 1.13% | 10 |
| valid | G3 | -1.58% | 2.32% | 10 |
| valid | G4 | -2.91% | 3.36% | 10 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | 1.84% | 0.9000 | 28 |
| valid | 0.99% | 0.3000 | 10 |

## 局限与下一步

- 探索性研究 / 证据不足；正式回测 BLOCKED，无账户图表。
- test=sealed 只隐藏统计，不是全系统盲测。
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
- industry/size neutralisation
- existing-factor correlation without authorized reference
- true independent OOS
- tradable NAV, Sharpe, drawdown, costs

## 技术附录

```json
{
  "goal": "在已批准的历史日频研究样本上构建并检验放量滞涨因子：以成交量相对放大、价格涨幅偏低（滞涨）为核心逻辑，计算因子值并输出IC/RankIC、分组收益、自相关稳定性、指标表、图表与报告；若需调整回看窗口，则以对照实验方式比较。",
  "parameters": {
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
            "op": "constant",
            "value": 0
          },
          {
            "op": "max",
            "args": [
              6,
              7
            ]
          },
          {
            "op": "field",
            "field": "close"
          },
          {
            "op": "returns",
            "args": [
              9
            ],
            "window": 5
          },
          {
            "op": "neg",
            "args": [
              10
            ]
          },
          {
            "op": "mul",
            "args": [
              8,
              11
            ]
          }
        ],
        "output": 12
      },
      "expression_sha256": "d257d1db6d33587ffcfacaf856701464f1e7f40efcf7736173d5c82770a046e3",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 13,
      "warmup_observations": 5,
      "formula": "mul(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),0),neg(returns(close,5)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量相对放大且价格涨幅偏低（放量滞涨）的股票，未来短期收益更弱，因子与未来收益应呈负向关系，分组毛收益随因子值升高而单调下降。",
      "generation_reason": "按已审核固定构造：量比放大项 = max(volume/delay(rolling_mean(volume,5),1)-1, 0)，滞涨项 = -returns(close,5)，因子为两者乘积。量比用 delay 避免当前成交量混入历史均值；正部截断用 constant=0 的 max。默认 L=5、H=5、5 组、raw 标准化。"
    }
  },
  "data_contract": {
    "adjustment": "none",
    "volume_unit": "shares",
    "calendar": "observed_union",
    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",
    "corporate_actions": "not_modelled",
    "universe": "fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe",
    "limits": [
      "only 65 observed dates, each train/validation segment may have fewer than 60 mature labels",
      "unadjusted prices: corporate actions can distort returns; no strategy efficacy claim",
      "observed date union is not independently verified exchange calendar",
      "historical availability, suspension, limits, delisting and full universe not fully verified"
    ],
    "research_use": "exploratory_raw_price"
  },
  "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
  "spec": {
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
  },
  "spec_fingerprint": "a241dd505f10718803a3a03b23f143e93ff3dcdea50926f1ecfd563b7dd7ff31",
  "implementation": {
    "core_version": "0.6.1",
    "tool_version": "0.3.0",
    "source_sha256": "69d81b746a3d5848a85cafe964b995dbc39e6d17a829fe936e6fad445d05c8c2",
    "report_version": "2.1.0"
  },
  "factor_export": {
    "status": "VERIFIED",
    "format_version": "server-panel-v1",
    "protocol": 4,
    "writer_version": "1.0.0",
    "core_version": "0.6.1",
    "writer_sha256": "96439b3b2b1e8b1523c8b7eb8b198e91da0e7e77747e6e1be25b09f4c92d3edd",
    "pandas_version": "2.3.3",
    "numpy_version": "1.26.4",
    "shape": [
      55,
      50
    ],
    "index_type": "Index[str YYYYMMDD]",
    "column_type": "Index[str six-digit code + observed exchange suffix]",
    "multiindex": false,
    "index_name": "date",
    "columns_name": "Code",
    "dtype": "float64",
    "date_start": "20260703",
    "date_end": "20260917",
    "codes": [
      "000001.SZ",
      "000002.SZ",
      "000004.SZ",
      "000006.SZ",
      "000007.SZ",
      "000008.SZ",
      "000009.SZ",
      "000010.SZ",
      "000011.SZ",
      "000012.SZ",
      "000014.SZ",
      "000016.SZ",
      "000017.SZ",
      "000019.SZ",
      "000020.SZ",
      "000021.SZ",
      "000025.SZ",
      "000026.SZ",
      "000027.SZ",
      "000028.SZ",
      "000029.SZ",
      "000030.SZ",
      "000031.SZ",
      "000032.SZ",
      "000034.SZ",
      "000035.SZ",
      "000036.SZ",
      "000037.SZ",
      "000039.SZ",
      "000042.SZ",
      "000045.SZ",
      "000048.SZ",
      "000049.SZ",
      "000050.SZ",
      "000055.SZ",
      "000056.SZ",
      "000058.SZ",
      "000059.SZ",
      "000060.SZ",
      "000061.SZ",
      "000062.SZ",
      "000063.SZ",
      "000065.SZ",
      "000066.SZ",
      "000068.SZ",
      "000069.SZ",
      "000070.SZ",
      "000078.SZ",
      "000088.SZ",
      "000089.SZ"
    ],
    "nan_cells": 324,
    "inf_cells": 0,
    "direction": 1,
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
            "op": "constant",
            "value": 0
          },
          {
            "op": "max",
            "args": [
              6,
              7
            ]
          },
          {
            "op": "field",
            "field": "close"
          },
          {
            "op": "returns",
            "args": [
              9
            ],
            "window": 5
          },
          {
            "op": "neg",
            "args": [
              10
            ]
          },
          {
            "op": "mul",
            "args": [
              8,
              11
            ]
          }
        ],
        "output": 12
      },
      "expression_sha256": "d257d1db6d33587ffcfacaf856701464f1e7f40efcf7736173d5c82770a046e3",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 13,
      "warmup_observations": 5,
      "formula": "mul(max(sub(div(volume,delay(rolling_mean(volume,5),1)),1),0),neg(returns(close,5)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量相对放大且价格涨幅偏低（放量滞涨）的股票，未来短期收益更弱，因子与未来收益应呈负向关系，分组毛收益随因子值升高而单调下降。",
      "generation_reason": "按已审核固定构造：量比放大项 = max(volume/delay(rolling_mean(volume,5),1)-1, 0)，滞涨项 = -returns(close,5)，因子为两者乘积。量比用 delay 避免当前成交量混入历史均值；正部截断用 constant=0 的 max。默认 L=5、H=5、5 组、raw 标准化。"
    },
    "axis_mapping_sha256": "debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848",
    "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/12-53-04_expression_d257d1db/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "d0409211fe2d893e398512a6bc104c0cda894794f232e874ca1554ffded6b841",
        "bytes": 23834
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/12-53-04_expression_d257d1db/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "3dc8fade78111710171edd666d37d15fec910dabd0a79e502dacaeb1601d2b8e",
        "bytes": 9860
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/12-53-04_expression_d257d1db/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "162423340fda1ec8f02d3d6cf07a82c51f79ef39e72177eaed0232c0e90cb761",
        "bytes": 23684
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/12-53-04_expression_d257d1db/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "466a77e54bf9657638e7f32b3cff4d27a9ac4d8c71ae0e96d19e8e841a463c78",
        "bytes": 23850
      }
    ]
  },
  "metric_definitions": {
    "autocorrelation": "cross-sectional Pearson over common finite eligible stocks at T and T-lag, then equal-date mean; minimum 10 pairs",
    "rank_autocorrelation": "same common pairs, Spearman average tied ranks; lag in observed rows",
    "predictive_decay": "separate H=1/3/5/10 forward open labels, each split purged by label exit; not factor autocorrelation",
    "rank_turnover_proxy": "1 - intersection(top group T,T-1)/size(top group T); not account turnover",
    "moments": "pooled finite train+valid values; sample std, pandas unbiased skew/excess kurtosis; no test values",
    "inference": "Bartlett HAC bandwidth max(H-1,floor(4*(n/100)^(2/9))); complete finite grid required, conservative n gate; no annualisation"
  },
  "reproduce": "python code/reproduce.py",
  "font": {
    "primary": "DejaVu Sans",
    "cjk_fallback": "Noto Sans CJK JP"
  },
  "cjk_font_available": true,
  "formula_rendering": {
    "latex": "f_{t,i}=\\left(\\max\\left(\\left(\\frac{V_{t,i}}{\\mathrm{Delay}_{1}\\left(\\mathrm{Mean}_{5}\\left(V_{t,i}\\right)\\right)}-1\\right),0\\right)\\cdot -\\left(\\left(\\frac{C_{t,i}}{\\mathrm{Delay}_{5}\\left(C_{t,i}\\right)}-1\\right)\\right)\\right)",
    "definition_sha256": "f1ec851a70b59ef4cfb9b5c8662ac2d4286560d146328e45c9ecceefb424a1bb",
    "renderer": "Matplotlib mathtext / offline SVG",
    "renderer_version": "3.8.4",
    "formula_version": "1.0.0"
  },
  "plot_source": {
    "entry": "backtest.ipynb last cell -> core_backtest.api.run_final_notebook -> core_backtest.plotting.plot_final_result",
    "plot_sha256": "d2b5a374e66d426eb33363dd5441709a25915ef884893ffdcd2a9bbddfe8dd52",
    "reused": "palette, group percentage annotations, dashed y-grid, zero line, frameless legends, percentage formatter; independent factor layout",
    "account_engine_executed": false
  }
}
```

## 图表

!ic_rankic（原内部附件未公开）

!ic_distribution（原内部附件未公开）

!group_returns_gross（原内部附件未公开）

!factor_coverage（原内部附件未公开）

!factor_distribution（原内部附件未公开）

!ic_decay（原内部附件未公开）

!factor_autocorrelation（原内部附件未公开）