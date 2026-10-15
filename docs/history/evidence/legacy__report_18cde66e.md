> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · reversal / 5日



状态：incomplete / exploratory；PKL已验证，正式回测未准入。



## 研究摘要



训练与验证的因子方向一致。训练/验证均值 RankIC 为 0.0257 / 0.1498。有效日期有限，当前仅支持探索性描述，不能确认预测效力。



gpushare:daily65 · 2026-07-03—2026-09-17 · 50只 · 复权=none



### IC / RankIC 核心指标



| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |

|---|---|---|---|---|---|

| train | ic | 0.0498 | 0.2839 | 0.1753 | 28 |

| train | rank_ic | 0.0257 | 0.2603 | 0.0988 | 28 |

| valid | ic | 0.1568 | 0.3687 | 0.4254 | 10 |

| valid | rank_ic | 0.1498 | 0.1698 | 0.8826 | 10 |



## 因子定义与经济假设



-(close[T]/close[T-5]-1)



过去5个交易日收益的反向（reversal = -(close[T]/close[T-L]-1)，L=5）在已批准历史日频样本 gpushare:daily65 上具有短期反转效应：前期跌幅较大的股票在随后约5个交易日内相对走强，因此因子值与未来收益正相关（IC/RankIC为正），分组毛收益随因子值分组呈单调上升。



## 预测能力



### 方向与有效股票



| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |

|---|---|---|---|---|

| train | ic | 60.71% | 48.6429 | 28 |

| train | rank_ic | 57.14% | 48.6429 | 28 |

| valid | ic | 60.00% | 48.0000 | 10 |

| valid | rank_ic | 70.00% | 48.0000 | 10 |



### 预测期衰减



| 样本 | H | IC均值 | RankIC均值 | 有效日 |

|---|---|---|---|---|

| train | 1 | -0.0114 | -0.0075 | 32 |

| valid | 1 | 0.1513 | 0.1323 | 14 |

| train | 3 | 0.0370 | 0.0123 | 30 |

| valid | 3 | 0.1766 | 0.1752 | 12 |

| train | 5 | 0.0498 | 0.0257 | 28 |

| valid | 5 | 0.1568 | 0.1498 | 10 |

| train | 10 | 0.0448 | 0.0599 | 23 |

| valid | 10 | 0.4866 | 0.1900 | 5 |



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

| train | 1 | 0.8001 | 0.7604 | 33 | 48.7273 |

| valid | 1 | 0.7825 | 0.6883 | 16 | 48.0000 |

| train | 5 | -0.0561 | -0.0201 | 29 | 48.6552 |

| valid | 5 | 0.0643 | -0.0414 | 16 | 48.0625 |

| train | 10 | -0.0337 | -0.0952 | 24 | 48.5833 |

| valid | 10 | -0.2277 | -0.0040 | 16 | 48.0625 |



### 时间窗口稳定性



| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |

|---|---|---|---|---|---|

| train | ic | first_half | 0.0171 | 0.1618 | 11 |

| train | ic | second_half | 0.0709 | 0.3442 | 17 |

| train | rank_ic | first_half | -0.0546 | 0.1763 | 11 |

| train | rank_ic | second_half | 0.0777 | 0.2960 | 17 |

| valid | ic | first_half | 0.4694 | 0.1286 | 5 |

| valid | ic | second_half | -0.1557 | 0.2125 | 5 |

| valid | rank_ic | first_half | 0.2144 | 0.0882 | 5 |

| valid | rank_ic | second_half | 0.0853 | 0.2160 | 5 |



### 分布与数据质量



| 指标 | 值 | 口径 |

|---|---|---|

| 覆盖率 | 88.25% | 完整可见矩形含暖机 |

| 缺失率 | 11.75% | NaN保留 |

| 有效因子值 | 2427 | 训练+验证有限数值 |

| 均值 / 标准差 | -0.0019 / 0.0728 | 合并观测、ddof=1 |

| 偏度 / 超额峰度 | -0.8522 / 9.0884 | 无偏估计，小样本可N/A |

| 异常值比例 | 1.81% | 逐日稳健z>5，MAD=0不评估 |

| 最长连续缺失 | 48 | 观察日，含暖机 |

| P01 / P50 / P99 | -0.2256 / -0.0005 / 0.2030 | 无尾部修剪 |



## 分组表现



### 分组未来毛收益



| 样本 | 组别 | 均值 | 标准差 | 有效日 |

|---|---|---|---|---|

| train | G0 | 0.42% | 5.06% | 28 |

| train | G1 | 0.52% | 3.44% | 28 |

| train | G2 | 1.42% | 2.58% | 28 |

| train | G3 | 1.10% | 2.84% | 28 |

| train | G4 | -1.00% | 4.83% | 28 |

| valid | G0 | -0.92% | 3.17% | 10 |

| valid | G1 | -1.44% | 1.54% | 10 |

| valid | G2 | -1.16% | 2.27% | 10 |

| valid | G3 | -1.50% | 2.24% | 10 |

| valid | G4 | -3.01% | 2.87% | 10 |



### 单调性



| 样本 | G0−末组毛收益 | 单调性² | 有效日 |

|---|---|---|---|

| train | 1.42% | 0.1000 | 28 |

| valid | 2.10% | 0.9000 | 10 |



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

  "goal": "真实样本报告视觉复核",

  "parameters": {

    "factor_id": "reversal",

    "horizon": 5,

    "lookback": 5,

    "n_groups": 5,

    "resource_id": "gpushare:daily65",

    "standardization": "raw"

  },

  "data_contract": {

    "adjustment": "none",

    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",

    "calendar": "observed_union",

    "corporate_actions": "not_modelled",

    "limits": [

      "only 65 observed dates, each train/validation segment may have fewer than 60 mature labels",

      "unadjusted prices: corporate actions can distort returns; no strategy efficacy claim",

      "observed date union is not independently verified exchange calendar",

      "historical availability, suspension, limits, delisting and full universe not fully verified"

    ],

    "research_use": "exploratory_raw_price",

    "universe": "fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe",

    "volume_unit": "shares"

  },

  "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",

  "spec": {

    "direction": 1,

    "execution_rule": "next_observed_open",

    "factor_name": "reversal",

    "horizon": 5,

    "lag": 1,

    "min_dates_per_split": 60,

    "min_obs": 10,

    "n_groups": 5,

    "test": [

      "2026-09-18",

      "2026-10-09"

    ],

    "train": [

      "2026-07-03",

      "2026-08-26"

    ],

    "universe_name": "fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe",

    "valid": [

      "2026-08-27",

      "2026-09-17"

    ]

  },

  "factor_export": {

    "available_time": "after T close; historical per-row fetched_at not fully verified; trade date is not availability time",

    "axis_mapping_sha256": "debdf8a0ba206b4876ade45936921f961d4ca434f8656e0b32543918b3dc5848",

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

    "column_type": "Index[str six-digit code + observed exchange suffix]",

    "columns_name": "Code",

    "data_sha256": "d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8",

    "date_end": "20260917",

    "date_start": "20260703",

    "definition": {

      "factor_id": "reversal",

      "formula": "-(close[T]/close[T-5]-1)",

      "generation_reason": "资源清单查询已完成，仅有一个已批准日频量价资源 gpushare:daily65（日频、含 Clsprc/Opnprc/Hiprc/Loprc/Dnshrtrd/Dnvaltrd/Trdsta 等量价字段，2026-07-03 至 2026-10-09，共65个观测日，未复权，固定50只股票探索性样本）。该资源为唯一可用日频量价样本，故选用它。用户要求构建并检验五日反转因子，该因子已有审核通过的固定入口（reversal 固定公式，L=5），因此优先使用 qrtk_factor_study 及对应 factor_id，而非自定义 expression；参数按工具Schema缺省建议 lookback=5、horizon=5、n_groups=5、standardization=raw。",

      "hypothesis": "过去5个交易日收益的反向（reversal = -(close[T]/close[T-L]-1)，L=5）在已批准历史日频样本 gpushare:daily65 上具有短期反转效应：前期跌幅较大的股票在随后约5个交易日内相对走强，因此因子值与未来收益正相关（IC/RankIC为正），分组毛收益随因子值分组呈单调上升。",

      "lookback": 5,

      "standardization": "raw"

    },

    "direction": 1,

    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",

    "dtype": "float64",

    "files": [

      {

        "bytes": 23834,

        "format": "server-panel-v1",

        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/8ce5a5cef4ee49c2/data/factor.pkl",

        "sha256": "1d3f210a837c583afc03e7412c603f79e6ab640916f354c394cf32557690ac78"

      },

      {

        "bytes": 17374,

        "format": "server-panel-zip-v1",

        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/8ce5a5cef4ee49c2/data/factor.pkl.zip",

        "sha256": "837e737ef5787591bc400c442f92231515ecd8ee9664b65feab13caed462678f"

      },

      {

        "bytes": 23684,

        "format": "plain-code-panel-v1",

        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/8ce5a5cef4ee49c2/data/factor_plain.pkl",

        "sha256": "025ef811d1687c8a4443174dd3bfd253f84cfc81ec82bb594b27ef28310dde57"

      },

      {

        "bytes": 23848,

        "format": "perry-dict-v1",

        "path": "/srv/jijigua-quant-agent/research_runs/INTERNAL_RUN_ID_REDACTED/8ce5a5cef4ee49c2/data/factor_dict.pkl",

        "sha256": "a6915223c62e9160051d955c9adab80478319879fb2c90a433344d18e519d6ff"

      }

    ],

    "format_version": "server-panel-v1",

    "index_name": "date",

    "index_type": "Index[str YYYYMMDD]",

    "inf_cells": 0,

    "multiindex": false,

    "nan_cells": 323,

    "numpy_version": "1.26.4",

    "pandas_version": "2.3.3",

    "protocol": 4,

    "scope": "train+validation factor values only; no future labels/test performance/account data",

    "shape": [

      55,

      50

    ],

    "status": "VERIFIED",

    "writer_version": "1.0.0"

  },

  "metric_definitions": {

    "autocorrelation": "cross-sectional Pearson over common finite eligible stocks at T and T-lag, then equal-date mean; minimum 10 pairs",

    "inference": "Bartlett HAC bandwidth max(H-1,floor(4*(n/100)^(2/9))); complete finite grid required, conservative n gate; no annualisation",

    "moments": "pooled finite train+valid values; sample std, pandas unbiased skew/excess kurtosis; no test values",

    "predictive_decay": "separate H=1/3/5/10 forward open labels, each split purged by label exit; not factor autocorrelation",

    "rank_autocorrelation": "same common pairs, Spearman average tied ranks; lag in observed rows",

    "rank_turnover_proxy": "1 - intersection(top group T,T-1)/size(top group T); not account turnover"

  },

  "reproduce": "python code/reproduce.py",

  "font": {

    "primary": "DejaVu Sans",

    "cjk_fallback": "MiSans"

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