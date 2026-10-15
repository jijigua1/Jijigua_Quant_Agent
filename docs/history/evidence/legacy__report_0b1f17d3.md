> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · volume_stall_10d / 10日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

训练与验证方向不一致，稳定性尚不足。训练/验证均值 RankIC 为 -0.0893 / 0.0093。有效日期有限，当前仅支持探索性描述，不能确认预测效力。

gpushare:daily65 · 2026-07-03—2026-09-17 · 50只 · 复权=none · 创建 2026-10-12 13:03:26（上海时间）

### IC / RankIC 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | 0.0418 | 0.1750 | 0.2386 | 23 |
| train | rank_ic | -0.0893 | 0.1515 | -0.5891 | 23 |
| valid | ic | 0.0347 | 0.0823 | 0.4218 | 10 |
| valid | rank_ic | 0.0093 | 0.2009 | 0.0464 | 10 |

PKL：/srv/jijigua-quant-agent/research_runs/2026-10-12/13-03-26_volume_stall_10d/data/factor.pkl

## 因子定义与经济假设

$$
f_{t,i}=\max\left(\frac{V_{t,i}}{\frac{1}{10}\sum_{k=1}^{10}V_{t-k,i}}-1,0\right)\exp\left(-\frac{\left|\left(\frac{C_{t,i}}{C_{t-10,i}}-1\right)\right|}{0.02}\right)
$$

将 volume_stall 的观察窗口由 5 天延长至 10 天，可更完整地刻画成交量相对历史均值的放大程度与价格滞涨的背离，预期 IC/RankIC 的绝对值与方向稳定性较 lookback=5 有所改善，或至少不劣化。

C/O/H/L为收盘/开盘/最高/最低价，V为成交量，t为当前观察日，i为股票。Delay为历史偏移；Mean/Std/RankTS/CorrTS包含当日的完整历史窗口（Std: ddof=1）；RankCS为横截面百分位平均秩，ZCS为当日横截面样本标准化。固定放量滞涨的成交量均值使用前L日、不含当日。

## 预测能力

### 方向与有效股票

| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|
| train | ic | 52.17% | 48.5652 | 23 |
| train | rank_ic | 30.43% | 48.5652 | 23 |
| valid | ic | 70.00% | 48.0000 | 10 |
| valid | rank_ic | 40.00% | 48.0000 | 10 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | -0.0158 | -0.0507 | 27 |
| valid | 1 | -0.0349 | -0.0078 | 14 |
| train | 3 | 0.0125 | -0.0590 | 25 |
| valid | 3 | 0.0058 | 0.0204 | 12 |
| train | 5 | 0.0418 | -0.0893 | 23 |
| valid | 5 | 0.0347 | 0.0093 | 10 |
| train | 10 | 0.1036 | 0.0079 | 18 |
| valid | 10 | -0.0098 | 0.0343 | 5 |

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
| train | 1 | 0.3199 | 0.3960 | 28 | 48.6429 |
| valid | 1 | 0.4293 | 0.4375 | 16 | 48.0000 |
| train | 5 | -0.0217 | -0.0396 | 24 | 48.5833 |
| valid | 5 | -0.0376 | -0.0471 | 16 | 48.0000 |
| train | 10 | -0.0543 | -0.1206 | 19 | 48.4737 |
| valid | 10 | -0.0494 | -0.1444 | 16 | 48.0000 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | 0.0126 | 0.0914 | 6 |
| train | ic | second_half | 0.0520 | 0.1976 | 17 |
| train | rank_ic | first_half | -0.0251 | 0.1606 | 6 |
| train | rank_ic | second_half | -0.1119 | 0.1463 | 17 |
| valid | ic | first_half | 0.0457 | 0.0956 | 5 |
| valid | ic | second_half | 0.0238 | 0.0762 | 5 |
| valid | rank_ic | first_half | 0.1223 | 0.1779 | 5 |
| valid | rank_ic | second_half | -0.1037 | 0.1652 | 5 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 79.24% | 完整可见矩形含暖机 |
| 缺失率 | 20.76% | NaN保留 |
| 有效因子值 | 2179 | 训练+验证有限数值 |
| 均值 / 标准差 | 0.0316 / 0.1179 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | 7.0985 / 68.1742 | 无偏估计，小样本可N/A |
| 异常值比例 | 41.84% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 55 | 观察日，含暖机 |
| P01 / P50 / P99 | 0.0000 / 0.0000 / 0.5241 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | 1.28% | 2.70% | 23 |
| train | G1 | 1.28% | 2.96% | 23 |
| train | G2 | 2.20% | 2.11% | 23 |
| train | G3 | 1.86% | 2.88% | 23 |
| train | G4 | 1.13% | 2.10% | 23 |
| valid | G0 | -1.28% | 3.04% | 10 |
| valid | G1 | -2.11% | 3.52% | 10 |
| valid | G2 | -2.44% | 1.96% | 10 |
| valid | G3 | -1.23% | 1.24% | 10 |
| valid | G4 | -0.87% | 2.06% | 10 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | 0.15% | 0.1000 | 23 |
| valid | -0.41% | -0.6000 | 10 |

## 实验对比

### 父子实验

| 样本 | 父RankIC | 本次RankIC | 差值 | 父有效日 | 本次有效日 |
|---|---|---|---|---|---|
| train | -0.0480 | -0.0893 | -0.0413 | 28 | 23 |
| valid | -0.0151 | 0.0093 | 0.0244 | 10 | 10 |

### 参数变化

| 参数 | 父实验 | 本次 |
|---|---|---|
| factor_id | volume_stall | volume_stall |
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
  "goal": "在资源 gpushare:daily65 上，将放量滞涨因子 volume_stall 的观察窗口（lookback）由 5 天改为 10 天，其余参数保持 horizon=5、n_groups=5、standardization=raw，生成对照实验并与上一实验（study_id INTERNAL_RUN_ID_REDACTED:f39b4cf485fc4362，lookback=5）比较 IC、RankIC 及稳定性差异。",
  "parameters": {
    "resource_id": "gpushare:daily65",
    "factor_id": "volume_stall",
    "lookback": 10,
    "horizon": 5,
    "n_groups": 5,
    "standardization": "raw",
    "parent_study_id": "INTERNAL_RUN_ID_REDACTED:f39b4cf485fc4362"
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
    "nan_cells": 571,
    "inf_cells": 0,
    "direction": 1,
    "definition": {
      "factor_id": "volume_stall",
      "lookback": 10,
      "standardization": "raw",
      "hypothesis": "将 volume_stall 的观察窗口由 5 天延长至 10 天，可更完整地刻画成交量相对历史均值的放大程度与价格滞涨的背离，预期 IC/RankIC 的绝对值与方向稳定性较 lookback=5 有所改善，或至少不劣化。",
      "generation_reason": "用户明确要求在同一资源 gpushare:daily65 上仅将 lookback 由 5 改为 10，horizon=5、n_groups=5、standardization=raw 保持不变，并以 study_id INTERNAL_RUN_ID_REDACTED:f39b4cf485fc4362 为父实验做对照。窗口变更属于新实验，需创建新 study 并传入 parent_study_id，在同一数据、同一预测期、同一分组与同一时间分段下比较 IC、RankIC 与稳定性差异。",
      "formula": "max(volume[T]/mean(volume[T-10:T-1])-1,0)*exp(-abs(close[T]/close[T-10]-1)/0.02)"
    },
    "axis_mapping_sha256": "debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848",
    "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",
    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/13-03-26_volume_stall_10d/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "19ead9e20eb8b760d727a302954cc71272387772ade90893de23988def76c92f",
        "bytes": 23834
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/13-03-26_volume_stall_10d/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "8934e8ee3e5cdb30acc86c5e2d8ce7431a7514142e1e3df07b72186616caa086",
        "bytes": 7965
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/13-03-26_volume_stall_10d/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "f0d8adc7ee3f667b35ad329ac8c8bd80a4c7045acfef67a2786fbc4f5458747b",
        "bytes": 23684
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/13-03-26_volume_stall_10d/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "ea787bdf14aeab2f839c29c3639ddfa409616eabee94367dabcbfe2dcd0ce0e3",
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
  "cjk_font_available": true,
  "formula_rendering": {
    "latex": "f_{t,i}=\\max\\left(\\frac{V_{t,i}}{\\frac{1}{10}\\sum_{k=1}^{10}V_{t-k,i}}-1,0\\right)\\exp\\left(-\\frac{\\left|\\left(\\frac{C_{t,i}}{C_{t-10,i}}-1\\right)\\right|}{0.02}\\right)",
    "definition_sha256": "38aeed8a901d0995cad320ce779a95fae79f6016411d4119bd2c4a923dbc4c45",
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

!experiment_comparison（原内部附件未公开）