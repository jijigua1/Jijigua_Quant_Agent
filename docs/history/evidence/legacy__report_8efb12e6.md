> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · volume_stall / 5日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

训练与验证的因子方向一致。训练/验证均值 RankIC 为 -0.0480 / -0.0151。有效日期有限，当前仅支持探索性描述，不能确认预测效力。

gpushare:daily65 · 2026-07-03—2026-09-17 · 50只 · 复权=none

### IC / RankIC 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | -0.0062 | 0.1738 | -0.0358 | 28 |
| train | rank_ic | -0.0480 | 0.2180 | -0.2200 | 28 |
| valid | ic | 0.0198 | 0.0875 | 0.2259 | 10 |
| valid | rank_ic | -0.0151 | 0.1851 | -0.0816 | 10 |

## 因子定义与经济假设

max(volume[T]/mean(volume[T-5:T-1])-1,0)*exp(-abs(close[T]/close[T-5]-1)/0.02)

在已批准的历史日频研究样本上，成交量相对放大而价格涨幅偏低（量增价滞）的股票，后续表现弱于量价配合或缩量上涨的股票，因此该因子具有负向选股能力。

## 预测能力

### 方向与有效股票

| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|
| train | ic | 50.00% | 48.6429 | 28 |
| train | rank_ic | 39.29% | 48.6429 | 28 |
| valid | ic | 70.00% | 48.0000 | 10 |
| valid | rank_ic | 40.00% | 48.0000 | 10 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | -0.0417 | -0.0401 | 32 |
| valid | 1 | -0.0038 | -0.0103 | 14 |
| train | 3 | -0.0165 | -0.0273 | 30 |
| valid | 3 | 0.0086 | 0.0255 | 12 |
| train | 5 | -0.0062 | -0.0480 | 28 |
| valid | 5 | 0.0198 | -0.0151 | 10 |
| train | 10 | 0.0822 | 0.0140 | 23 |
| valid | 10 | 0.0081 | -0.0490 | 5 |

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
| train | 1 | 0.1361 | 0.2848 | 33 | 48.7273 |
| valid | 1 | 0.2461 | 0.3152 | 16 | 48.0000 |
| train | 5 | -0.0360 | -0.1019 | 29 | 48.6552 |
| valid | 5 | -0.0834 | -0.1847 | 16 | 48.0000 |
| train | 10 | -0.0102 | -0.0004 | 24 | 48.5833 |
| valid | 10 | 0.0236 | -0.0053 | 16 | 48.0000 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | 0.0391 | 0.1395 | 11 |
| train | ic | second_half | -0.0356 | 0.1910 | 17 |
| train | rank_ic | first_half | 0.0450 | 0.2164 | 11 |
| train | rank_ic | second_half | -0.1081 | 0.2029 | 17 |
| valid | ic | first_half | 0.0689 | 0.0998 | 5 |
| valid | ic | second_half | -0.0294 | 0.0350 | 5 |
| valid | rank_ic | first_half | 0.0528 | 0.2375 | 5 |
| valid | rank_ic | second_half | -0.0830 | 0.0957 | 5 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 88.22% | 完整可见矩形含暖机 |
| 缺失率 | 11.78% | NaN保留 |
| 有效因子值 | 2426 | 训练+验证有限数值 |
| 均值 / 标准差 | 0.0344 / 0.1137 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | 7.1497 / 70.4699 | 无偏估计，小样本可N/A |
| 异常值比例 | 36.76% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 48 | 观察日，含暖机 |
| P01 / P50 / P99 | 0.0000 / 0.0000 / 0.5337 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | 0.56% | 2.80% | 28 |
| train | G1 | 0.56% | 4.12% | 28 |
| train | G2 | 0.58% | 3.85% | 28 |
| train | G3 | 0.98% | 2.92% | 28 |
| train | G4 | -0.16% | 3.94% | 28 |
| valid | G0 | -0.99% | 2.69% | 10 |
| valid | G1 | -2.28% | 2.95% | 10 |
| valid | G2 | -3.17% | 2.64% | 10 |
| valid | G3 | -1.18% | 1.13% | 10 |
| valid | G4 | -0.34% | 2.04% | 10 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | 0.72% | 0.1000 | 28 |
| valid | -0.64% | -0.3000 | 10 |

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
  "goal": "构建并检验“放量滞涨”因子：在已批准的历史日频研究样本上，以成交量相对放大而价格涨幅偏低（量增价滞）为核心定义，计算该因子的IC/RankIC、分组收益、自相关稳定性等指标，输出指标表、图表与研究报告，评估其选股效果。",
  "parameters": {
    "resource_id": "gpushare:daily65",
    "factor_id": "volume_stall",
    "lookback": 5,
    "horizon": 5,
    "n_groups": 5,
    "standardization": "raw"
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
    "factor_name": "volume_stall",
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
  "spec_fingerprint": "c92b5c7ab92eea17cb8296300364dfb59144a72887b1dee7c3581b474c1dce19",
  "implementation": {
    "core_version": "0.6.0",
    "tool_version": "0.3.0",
    "source_sha256": "69d81b746a3d5848a85cafe964b995dbc39e6d17a829fe936e6fad445d05c8c2",
    "report_version": "2.0.0"
  },
  "factor_export": {
    "status": "VERIFIED",
    "format_version": "server-panel-v1",
    "protocol": 4,
    "writer_version": "1.0.0",
    "core_version": "0.6.0",
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
      "factor_id": "volume_stall",
      "lookback": 5,
      "standardization": "raw",
      "hypothesis": "在已批准的历史日频研究样本上，成交量相对放大而价格涨幅偏低（量增价滞）的股票，后续表现弱于量价配合或缩量上涨的股票，因此该因子具有负向选股能力。",
      "generation_reason": "用户要求构建并检验“放量滞涨”因子。该定义与已审核固定因子 volume_stall 一致：volume_stall=max(volume[T]/mean(volume[T-L:T-1])-1,0)*exp(-abs(L日价格收益)/0.02)，属于已有固定入口，因此优先使用 qrtk_factor_study 及对应 factor_id 执行，不自行用 expression 拼装或扩充算子。参数按工具 Schema 缺省建议 lookback=5、horizon=5、n_groups=5、standardization=raw，方向为+1，lag=1，时间划分与最低有效日数由工具预先固定。",
      "formula": "max(volume[T]/mean(volume[T-5:T-1])-1,0)*exp(-abs(close[T]/close[T-5]-1)/0.02)"
    },
    "axis_mapping_sha256": "debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848",
    "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/9396fc4636cf4d86/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "6d107eaff9adb505602fff16c3b7e339ea1767341a58211b4e29545c21218c38",
        "bytes": 23834
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/9396fc4636cf4d86/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "f9376ae3214d48a569c65dd54077a9980fdc7c40929b311776540a02edae298b",
        "bytes": 9560
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/9396fc4636cf4d86/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "2e4a8decd6c2cf8b5400134f56b307f63e38f53fe8d1f4b3c66286f264660bb9",
        "bytes": 23684
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/9396fc4636cf4d86/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "286bf61de6f29d683f4df11a9639dc0ba5002d12028227d054130eda98c20b9a",
        "bytes": 23852
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