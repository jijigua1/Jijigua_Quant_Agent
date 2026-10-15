> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · reversal / 10日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

训练与验证的因子方向一致。训练/验证均值 RankIC 为 0.0790 / 0.1172。有效日期有限，当前仅支持探索性描述，不能确认预测效力。

gpushare:daily65 · 2026-07-03—2026-09-17 · 50只 · 复权=none

### IC / RankIC 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | 0.0458 | 0.2491 | 0.1837 | 23 |
| train | rank_ic | 0.0790 | 0.2585 | 0.3057 | 23 |
| valid | ic | 0.3436 | 0.1911 | 1.7978 | 10 |
| valid | rank_ic | 0.1172 | 0.1974 | 0.5938 | 10 |

## 因子定义与经济假设

-(close[T]/close[T-10]-1)

将观察窗口由5天延长至10天，反转信号可能捕捉更充分的价格修正，预期IC/RankIC与ICIR/RankICIR在训练与验证段相对lookback=5有所变化（方向不定），分组毛收益单调性可能改善或减弱，自相关稳定性预计随窗口拉长而下降。

## 预测能力

### 方向与有效股票

| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|
| train | ic | 56.52% | 48.6522 | 23 |
| train | rank_ic | 56.52% | 48.6522 | 23 |
| valid | ic | 100.00% | 48.0000 | 10 |
| valid | rank_ic | 80.00% | 48.0000 | 10 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | -0.0008 | 0.0020 | 27 |
| valid | 1 | 0.1129 | 0.0886 | 14 |
| train | 3 | 0.0176 | 0.0341 | 25 |
| valid | 3 | 0.1862 | 0.1135 | 12 |
| train | 5 | 0.0458 | 0.0790 | 23 |
| valid | 5 | 0.3436 | 0.1172 | 10 |
| train | 10 | 0.0711 | 0.0740 | 18 |
| valid | 10 | 0.4920 | 0.1069 | 5 |

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
| train | 1 | 0.8954 | 0.8654 | 28 | 48.6786 |
| valid | 1 | 0.8946 | 0.8289 | 16 | 48.2500 |
| train | 5 | 0.4374 | 0.4066 | 24 | 48.5833 |
| valid | 5 | 0.4019 | 0.4227 | 16 | 48.0625 |
| train | 10 | -0.0892 | -0.0924 | 19 | 48.5789 |
| valid | 10 | -0.2070 | -0.0519 | 16 | 48.3125 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | -0.0648 | 0.2114 | 6 |
| train | ic | second_half | 0.0848 | 0.2553 | 17 |
| train | rank_ic | first_half | -0.0341 | 0.2106 | 6 |
| train | rank_ic | second_half | 0.1190 | 0.2675 | 17 |
| valid | ic | first_half | 0.4891 | 0.0925 | 5 |
| valid | ic | second_half | 0.1981 | 0.1438 | 5 |
| valid | rank_ic | first_half | 0.1576 | 0.1083 | 5 |
| valid | rank_ic | second_half | 0.0768 | 0.2681 | 5 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 79.49% | 完整可见矩形含暖机 |
| 缺失率 | 20.51% | NaN保留 |
| 有效因子值 | 2186 | 训练+验证有限数值 |
| 均值 / 标准差 | -0.0097 / 0.1040 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | -1.4649 / 14.2397 | 无偏估计，小样本可N/A |
| 异常值比例 | 1.33% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 55 | 观察日，含暖机 |
| P01 / P50 / P99 | -0.2968 / -0.0075 / 0.2796 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | 1.44% | 3.43% | 23 |
| train | G1 | 1.80% | 2.17% | 23 |
| train | G2 | 2.02% | 2.88% | 23 |
| train | G3 | 1.65% | 3.22% | 23 |
| train | G4 | 0.82% | 3.23% | 23 |
| valid | G0 | -1.31% | 2.43% | 10 |
| valid | G1 | -1.33% | 1.68% | 10 |
| valid | G2 | -0.64% | 1.55% | 10 |
| valid | G3 | -1.05% | 3.11% | 10 |
| valid | G4 | -3.68% | 2.43% | 10 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | 0.62% | 0.3000 | 23 |
| valid | 2.37% | 0.2000 | 10 |

## 实验对比

### 父子实验

| 样本 | 父RankIC | 本次RankIC | 差值 | 父有效日 | 本次有效日 |
|---|---|---|---|---|---|
| train | 0.0257 | 0.0790 | 0.0533 | 28 | 23 |
| valid | 0.1498 | 0.1172 | -0.0326 | 10 | 10 |

### 参数变化

| 参数 | 父实验 | 本次 |
|---|---|---|
| factor_id | reversal | reversal |
| lookback | 5 | 10 |
| horizon | 5 | 5 |
| n_groups | 5 | 5 |
| standardization | raw | raw |

## 局限与下一步

- 探索性研究 / 证据不足；正式回测 BLOCKED，无账户图表。
- test=sealed 只隐藏统计，不是全系统盲测。
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
- industry/size neutralisation
- existing-factor correlation without authorized reference
- true independent OOS
- tradable NAV, Sharpe, drawdown, costs

## 技术附录

```json
{
  "goal": "在已登记资源 gpushare:daily65（2026-07-03至2026-10-09，未复权日频）上，将本会话已完成的五日反转因子（study_id=INTERNAL_RUN_ID_REDACTED:aa51b304229a4d3d，factor_id=reversal，lookback=5，horizon=5，n_groups=5，standardization=raw）的观察窗口由5天改为10天，用 qrtk_factor_study 以 parent_study_id=INTERNAL_RUN_ID_REDACTED:aa51b304229a4d3d 生成对照研究，比较 lookback=5 与 lookback=10 两个因子的 IC/RankIC、ICIR/RankICIR、分组毛收益、自相关稳定性等指标，并复核更新既有报告与图表路径。",
  "parameters": {
    "resource_id": "gpushare:daily65",
    "factor_id": "reversal",
    "lookback": 10,
    "horizon": 5,
    "n_groups": 5,
    "standardization": "raw",
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:aa51b304229a4d3d"
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
    "factor_name": "reversal",
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
    "nan_cells": 564,
    "inf_cells": 0,
    "direction": 1,
    "definition": {
      "factor_id": "reversal",
      "lookback": 10,
      "standardization": "raw",
      "hypothesis": "将观察窗口由5天延长至10天，反转信号可能捕捉更充分的价格修正，预期IC/RankIC与ICIR/RankICIR在训练与验证段相对lookback=5有所变化（方向不定），分组毛收益单调性可能改善或减弱，自相关稳定性预计随窗口拉长而下降。",
      "generation_reason": "用户明确要求把已完成的五日反转因子观察窗口由5天改为10天，并以 parent_study_id=INTERNAL_RUN_ID_REDACTED:aa51b304229a4d3d 生成对照研究，比较 lookback=5 与 lookback=10 的 IC/RankIC、ICIR/RankICIR、分组毛收益与自相关稳定性，并复核更新既有报告与图表路径。窗口变更属于新实验，须创建新研究而非覆盖旧结果。",
      "formula": "-(close[T]/close[T-10]-1)"
    },
    "axis_mapping_sha256": "debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848",
    "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7402c86c3c3240d8/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "2213b2fa5954ece65add82414f129722dbba9893246e102fb01a8cf5d9cb7e7d",
        "bytes": 23834
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7402c86c3c3240d8/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "7fa1a994d2f39c458cf64d0f6ea3e25080fb00ecd86035671bce742c35ac4690",
        "bytes": 16171
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7402c86c3c3240d8/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "994f1ce0e35e9ab6e768a3025d71300f39421d3f298daf532d948ab722f0afec",
        "bytes": 23684
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/7402c86c3c3240d8/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "446a4f5b9097f39809d3c9eaa3f3b842da52247e34447f999886abf8e3a3221c",
        "bytes": 23848
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

!experiment_comparison（原内部附件未公开）