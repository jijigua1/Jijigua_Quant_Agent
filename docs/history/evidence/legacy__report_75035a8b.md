> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · expression / 9日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

训练与验证的因子方向一致。训练/验证均值 RankIC 为 0.0805 / 0.2024。有效日期有限，当前仅支持探索性描述，不能确认预测效力。

gpushare:daily65 · 2026-07-03—2026-09-17 · 50只 · 复权=none

### IC / RankIC 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | 0.0800 | 0.2955 | 0.2706 | 24 |
| train | rank_ic | 0.0805 | 0.2711 | 0.2971 | 24 |
| valid | ic | 0.2698 | 0.2420 | 1.1148 | 10 |
| valid | rank_ic | 0.2024 | 0.2115 | 0.9570 | 10 |

## 因子定义与经济假设

sub(neg(returns(close,5)),rolling_std(returns(close,5),5))

5日反转（负的5日收益）与5日波动率之差可能同时捕捉短期超跌与低波动溢价：反转项提供方向性alpha，减去波动率项偏好低波动股票，二者叠加或可提升IC与分组单调性。

## 预测能力

### 方向与有效股票

| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|
| train | ic | 62.50% | 48.5833 | 24 |
| train | rank_ic | 66.67% | 48.5833 | 24 |
| valid | ic | 90.00% | 48.0000 | 10 |
| valid | rank_ic | 80.00% | 48.0000 | 10 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | 0.0186 | 0.0281 | 28 |
| valid | 1 | 0.1683 | 0.1567 | 14 |
| train | 3 | 0.0850 | 0.0844 | 26 |
| valid | 3 | 0.2238 | 0.2025 | 12 |
| train | 5 | 0.0800 | 0.0805 | 24 |
| valid | 5 | 0.2698 | 0.2024 | 10 |
| train | 10 | 0.0718 | 0.0705 | 19 |
| valid | 10 | 0.5159 | 0.3269 | 5 |

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
| train | 1 | 0.8155 | 0.7619 | 29 | 48.6552 |
| valid | 1 | 0.7980 | 0.7094 | 16 | 48.0000 |
| train | 5 | -0.0095 | 0.0035 | 25 | 48.6000 |
| valid | 5 | 0.2531 | 0.1154 | 16 | 48.0000 |
| train | 10 | 0.0296 | -0.0123 | 20 | 48.5000 |
| valid | 10 | -0.0906 | 0.0628 | 16 | 48.0000 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | 0.1305 | 0.1821 | 7 |
| train | ic | second_half | 0.0591 | 0.3339 | 17 |
| train | rank_ic | first_half | 0.0763 | 0.1943 | 7 |
| train | rank_ic | second_half | 0.0823 | 0.3025 | 17 |
| valid | ic | first_half | 0.4506 | 0.1533 | 5 |
| valid | ic | second_half | 0.0890 | 0.1631 | 5 |
| valid | rank_ic | first_half | 0.2662 | 0.1242 | 5 |
| valid | rank_ic | second_half | 0.1385 | 0.2738 | 5 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 81.02% | 完整可见矩形含暖机 |
| 缺失率 | 18.98% | NaN保留 |
| 有效因子值 | 2228 | 训练+验证有限数值 |
| 均值 / 标准差 | -0.0399 / 0.0794 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | -2.3137 / 15.1537 | 无偏估计，小样本可N/A |
| 异常值比例 | 2.74% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 55 | 观察日，含暖机 |
| P01 / P50 / P99 | -0.3097 / -0.0275 / 0.1285 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | 2.21% | 4.12% | 24 |
| train | G1 | 1.49% | 3.01% | 24 |
| train | G2 | 1.51% | 1.97% | 24 |
| train | G3 | 1.43% | 2.84% | 24 |
| train | G4 | 0.12% | 3.25% | 24 |
| valid | G0 | -0.46% | 2.43% | 10 |
| valid | G1 | -1.39% | 1.87% | 10 |
| valid | G2 | -1.00% | 1.96% | 10 |
| valid | G3 | -2.22% | 2.33% | 10 |
| valid | G4 | -2.93% | 3.04% | 10 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | 2.09% | 0.9000 | 24 |
| valid | 2.47% | 0.9000 | 10 |

## 局限与下一步

- 探索性研究 / 证据不足；正式回测 BLOCKED，无账户图表。
- test=sealed 只隐藏统计，不是全系统盲测。
- only 65 observed dates, each train/validation segment may have fewer than 60 mature labels
- unadjusted prices: corporate actions can distort returns; no strategy efficacy claim
- observed date union is not independently verified exchange calendar
- historical availability, suspension, limits, delisting and full universe not fully verified
- labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5
- train: only 24 valid RankIC dates (< 60)
- train: mean factor coverage 0.72 < 0.80
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
  "goal": "构建并检验新因子：5日反转减去5日波动率（即5日收益率反转信号与5日波动率之差），在已批准的历史日频研究样本上计算该因子的IC/RankIC、分组收益、自相关稳定性等指标，并输出指标表、图表与报告，评估其效果。",
  "parameters": {
    "resource_id": "gpushare:daily65",
    "factor_id": "expression",
    "lookback": 9,
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
            "op": "rolling_std",
            "args": [
              1
            ],
            "window": 5
          },
          {
            "op": "sub",
            "args": [
              2,
              3
            ]
          }
        ],
        "output": 4
      },
      "expression_sha256": "9d6ae74d68725c90e99a0d503106c9ac7d7bfc2f83d4c09c46c4f5b8cb41d995",
      "input_fields": [
        "close"
      ],
      "nodes": 5,
      "warmup_observations": 9,
      "formula": "sub(neg(returns(close,5)),rolling_std(returns(close,5),5))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "5日反转（负的5日收益）与5日波动率之差可能同时捕捉短期超跌与低波动溢价：反转项提供方向性alpha，减去波动率项偏好低波动股票，二者叠加或可提升IC与分组单调性。",
      "generation_reason": "用户要求构建新因子，现有固定入口（reversal、volume_stall）不覆盖“5日反转减5日波动率”这一组合定义，因此用表达式算子构造：neg(returns(close,5)) 减去 rolling_std(returns(close,5),5)。所有算子（neg、returns、rolling_std、sub）均在允许白名单内，不引入exp或自定义嵌套节点。参数采用缺省建议 lookback=5、horizon=5、n_groups=5、standardization=raw，与用户指定的5日窗口一致。"
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
  "factor_export": {
    "status": "VERIFIED",
    "format_version": "server-panel-v1",
    "protocol": 4,
    "writer_version": "1.0.0",
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
    "nan_cells": 522,
    "inf_cells": 0,
    "direction": 1,
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
            "op": "rolling_std",
            "args": [
              1
            ],
            "window": 5
          },
          {
            "op": "sub",
            "args": [
              2,
              3
            ]
          }
        ],
        "output": 4
      },
      "expression_sha256": "9d6ae74d68725c90e99a0d503106c9ac7d7bfc2f83d4c09c46c4f5b8cb41d995",
      "input_fields": [
        "close"
      ],
      "nodes": 5,
      "warmup_observations": 9,
      "formula": "sub(neg(returns(close,5)),rolling_std(returns(close,5),5))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "5日反转（负的5日收益）与5日波动率之差可能同时捕捉短期超跌与低波动溢价：反转项提供方向性alpha，减去波动率项偏好低波动股票，二者叠加或可提升IC与分组单调性。",
      "generation_reason": "用户要求构建新因子，现有固定入口（reversal、volume_stall）不覆盖“5日反转减5日波动率”这一组合定义，因此用表达式算子构造：neg(returns(close,5)) 减去 rolling_std(returns(close,5),5)。所有算子（neg、returns、rolling_std、sub）均在允许白名单内，不引入exp或自定义嵌套节点。参数采用缺省建议 lookback=5、horizon=5、n_groups=5、standardization=raw，与用户指定的5日窗口一致。"
    },
    "axis_mapping_sha256": "debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848",
    "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7bdd6b55ec734fcb/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "c3b191ed5262610c397d6571a10dd2c043b66d513fdd14a1715d40416f37f5b1",
        "bytes": 23834
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7bdd6b55ec734fcb/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "50a95b55cd34ff4fc3139ffbe626827599e31cbfd0ba25691ea912599949d06e",
        "bytes": 18218
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7bdd6b55ec734fcb/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "f6a3d2e147cfafb08e60e28116e6fd556371408f130718e3d6d79f91945d392d",
        "bytes": 23684
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7bdd6b55ec734fcb/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "ecc5907321cdec5424716fb8d50fcad7aa65f2590667f266ed2ad96fed966c1f",
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
  "cjk_font_available": true
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