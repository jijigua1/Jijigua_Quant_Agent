> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · volume_change_x_short_reversal / 预热5观察日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

训练与验证的因子方向一致。训练/验证均值 RankIC 为 0.0266 / 0.0481。需结合重叠标签、诊断与独立验证判断；相关性不构成因果证据。

gpushare:train2020_2023 · 2020-01-02—2025-12-31 · 5427只 · 复权=none · 创建 2026-10-12 20:04:20（上海时间）

### IC / RankIC 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | 0.0192 | 0.0779 | 0.2470 | 959 |
| train | rank_ic | 0.0266 | 0.1213 | 0.2192 | 959 |
| valid | ic | 0.0409 | 0.0877 | 0.4668 | 479 |
| valid | rank_ic | 0.0481 | 0.1544 | 0.3117 | 479 |

PKL：/srv/jijigua-quant-agent/research_runs/2026-10-12/20-04-20_volume_change_x_short_reversal/data/factor.pkl

## 因子定义与经济假设

$$
f_{t,i}=\left(\frac{V_{t,i}}{\mathrm{Delay}_{1}\left(\mathrm{Mean}_{5}\left(V_{t,i}\right)\right)}\cdot -\left(\left(\frac{C_{t,i}}{\mathrm{Delay}_{5}\left(C_{t,i}\right)}-1\right)\right)\right)
$$

成交量放大伴随短期价格下跌（放量下跌/放量滞涨）后存在短期反转修复倾向：以成交量相对前期均值的放量程度乘以负的短期价格收益构造组合因子，因子值越高预期未来5日收益越高。

C/O/H/L为收盘/开盘/最高/最低价，V为成交量，t为当前观察日，i为股票。Delay为历史偏移；Mean/Std/RankTS/CorrTS包含当日的完整历史窗口（Std: ddof=1）；RankCS为横截面百分位平均秩，ZCS为当日横截面样本标准化。固定放量滞涨的成交量均值使用前L日、不含当日。

## 预测能力

### 方向与有效股票

| 样本 | 指标 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|
| train | ic | 60.06% | 4469.2534 | 959 |
| train | rank_ic | 58.19% | 4469.2534 | 959 |
| valid | ic | 72.86% | 5095.0585 | 479 |
| valid | rank_ic | 63.88% | 5095.0585 | 479 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | 0.0115 | 0.0288 | 963 |
| valid | 1 | 0.0218 | 0.0328 | 483 |
| train | 3 | 0.0168 | 0.0288 | 961 |
| valid | 3 | 0.0361 | 0.0457 | 481 |
| train | 5 | 0.0192 | 0.0266 | 959 |
| valid | 5 | 0.0409 | 0.0481 | 479 |
| train | 10 | 0.0218 | 0.0256 | 954 |
| valid | 10 | 0.0404 | 0.0448 | 474 |

### 统计推断准入

| 样本 | 指标 | 状态 | 输入日 | 有效日 | HAC滞后 |
|---|---|---|---|---|---|
| train | ic | insufficient | 964 | 959 | 6 |
| train | rank_ic | insufficient | 964 | 959 | 6 |
| valid | ic | approximate | 479 | 479 | 5 |
| valid | rank_ic | approximate | 479 | 479 | 5 |

### HAC均值95%区间

| 样本 | 指标 | 标准误 | 下界 | 上界 |
|---|---|---|---|---|
| valid | ic | 0.0057 | 0.0297 | 0.0521 |
| valid | rank_ic | 0.0111 | 0.0263 | 0.0699 |

## 稳定性与分布诊断

### 因子值与排序自相关

| 样本 | Lag | 值相关 | 秩相关 | 有效日 | 平均共同股票 |
|---|---|---|---|---|---|
| train | 1 | 0.4585 | 0.7126 | 964 | 4477.8579 |
| valid | 1 | 0.4954 | 0.7112 | 485 | 5101.3093 |
| train | 5 | 0.0207 | -0.0130 | 960 | 4467.5333 |
| valid | 5 | -0.0010 | -0.0350 | 485 | 5092.9443 |
| train | 10 | 0.0037 | -0.0071 | 955 | 4458.9120 |
| valid | 10 | 0.0019 | -0.0124 | 485 | 5086.4619 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | 0.0068 | 0.0762 | 477 |
| train | ic | second_half | 0.0315 | 0.0776 | 482 |
| train | rank_ic | first_half | 0.0249 | 0.1169 | 477 |
| train | rank_ic | second_half | 0.0283 | 0.1256 | 482 |
| valid | ic | first_half | 0.0502 | 0.0987 | 239 |
| valid | ic | second_half | 0.0317 | 0.0742 | 240 |
| valid | rank_ic | first_half | 0.0459 | 0.1861 | 239 |
| valid | rank_ic | second_half | 0.0504 | 0.1148 | 240 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 86.10% | 完整可见矩形含暖机 |
| 缺失率 | 13.90% | NaN保留 |
| 有效因子值 | 6798789 | 训练+验证有限数值 |
| 均值 / 标准差 | -0.0164 / 0.4636 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | -23.1532 / 521822.9315 | 无偏估计，小样本可N/A |
| 异常值比例 | 4.80% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 1455 | 观察日，含暖机 |
| P01 / P50 / P99 | -0.4945 / 0.0018 / 0.2033 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | 0.10% | 3.43% | 959 |
| train | G1 | 0.22% | 3.18% | 959 |
| train | G2 | 0.23% | 3.03% | 959 |
| train | G3 | 0.18% | 2.95% | 959 |
| train | G4 | -0.15% | 3.03% | 959 |
| valid | G0 | 0.56% | 5.69% | 479 |
| valid | G1 | 0.56% | 5.16% | 479 |
| valid | G2 | 0.56% | 4.76% | 479 |
| valid | G3 | 0.50% | 4.49% | 479 |
| valid | G4 | 0.04% | 4.56% | 479 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | 0.25% | 0.3000 | 959 |
| valid | 0.51% | 0.7000 | 479 |

## 局限与下一步

- 探索性研究 / 证据不足；正式回测 BLOCKED，无账户图表。
- Train/Validation为独立发布分区；2026未发布，本配置拒绝旧2026资源；Validation已曝光，不是独立盲测。
- PROFILED_EXPLORATORY_ONLY; not backtest approved
- raw prices may distort returns across corporate actions
- listing dates and historical universe PIT unverified
- observed calendar, trade status and delisting valuations uncertified
- labels overlap (h=5); ICIR not annualised
- IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores
- group returns are gross, equal weight, missing labels excluded; not account returns
- no industry/size neutralisation, HAC or multiple-testing adjustment
- positive observed volume is sample eligibility, not permission to buy/sell
- all parameter changes after seeing validation are exploratory; no certified out-of-sample performance
- Train2020-2023 and Validation2024-2025 are separate hash-checked published partitions; 2026 unavailable
- Validation warm-up uses permitted Train history; Train labels crossing boundary purged, Validation tail not filled from 2026
- listing dates are unverified; published candidate prelisting mask does not certify a historical PIT stock universe
- no embargo gap requested: chronological factor diagnostics only, no supervised train-label fit; lag+H boundary purge applied
- volume is lots (100 shares), amount thousand CNY; price-relative label is not corporate-action-adjusted total return
- industry/size neutralisation
- existing-factor correlation without authorized reference
- true independent OOS
- tradable NAV, Sharpe, drawdown, costs

## 技术附录

```json
{
  "goal": "使用2020-01-02至2023-12-29的Train数据（gpushare:train2020_2023），研究一个结合成交量变化与短期价格反转的组合因子：以成交量变化（如成交量相对前期均值的放量程度）与短期价格反转（如近若干日收益的反转）组合构建DSL表达式，在Train上冻结定义并计算全轴，随后在自动配对的Validation数据（gpushare:validation2024_2025，2024-01-02至2025-12-31）上评价IC、RankIC及分组稳定性，生成完整报告与PKL成果。",
  "parameters": {
    "resource_id": "gpushare:train2020_2023",
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
            "op": "mul",
            "args": [
              4,
              7
            ]
          }
        ],
        "output": 8
      },
      "expression_sha256": "5907b2ce09999afb716d67dfba787fc8f512308587142632ae2ffba3404b0e60",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 9,
      "warmup_observations": 5,
      "formula": "mul(div(volume,delay(rolling_mean(volume,5),1)),neg(returns(close,5)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量放大伴随短期价格下跌（放量下跌/放量滞涨）后存在短期反转修复倾向：以成交量相对前期均值的放量程度乘以负的短期价格收益构造组合因子，因子值越高预期未来5日收益越高。",
      "generation_reason": "用户要求组合成交量变化与短期价格反转，属新定义，必须用表达式入口而非固定 volume_stall（后者用绝对价格收益、无反转方向）。表达式：vol_ratio=volume/delay(rolling_mean(volume,5),1)（历史均量不含当日），rev=neg(returns(close,5))，组合=mul(vol_ratio,rev)。参数取默认 lookback=5、horizon=5、n_groups=5、standardization=raw，在 Train 冻结定义并计算全轴，由工具自动在配对 Validation 评价 IC、RankIC 与分组稳定性并生成报告与 PKL。",
      "name": "volume_change_x_short_reversal"
    }
  },
  "data_contract": {
    "adjustment": "none",
    "volume_unit": "lots",
    "calendar": "observed_union",
    "available_time": "historical availability unverified; T-close research assumption",
    "corporate_actions": "not_modelled",
    "universe": "published fixed 5427 code axis; candidate listing mask unverified, two ambiguous identities all NaN",
    "limits": [
      "PROFILED_EXPLORATORY_ONLY; not backtest approved",
      "raw prices may distort returns across corporate actions",
      "listing dates and historical universe PIT unverified",
      "observed calendar, trade status and delisting valuations uncertified"
    ],
    "research_use": "exploratory_raw_price"
  },
  "data_sha256": "9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221",
  "spec": {
    "factor_name": "expression",
    "direction": 1,
    "horizon": 5,
    "lag": 1,
    "n_groups": 5,
    "min_obs": 10,
    "train": [
      "2020-01-02",
      "2023-12-29"
    ],
    "valid": [
      "2024-01-02",
      "2025-12-31"
    ],
    "test": [
      "2026-01-01",
      "2026-12-31"
    ],
    "universe_name": "published fixed 5427 code axis; candidate listing mask unverified, two ambiguous identities all NaN",
    "execution_rule": "next_observed_open",
    "min_dates_per_split": 60
  },
  "spec_fingerprint": "d84563ec9527626ff60b9662af204374a90846b7c5287c4d71a146313f3ef55d",
  "implementation": {
    "core_version": "0.7.0",
    "tool_version": "0.4.0",
    "source_sha256": "69d81b746a3d5848a85cafe964b995dbc39e6d17a829fe936e6fad445d05c8c2",
    "report_version": "2.1.0"
  },
  "factor_export": {
    "status": "VERIFIED",
    "format_version": "server-panel-v1",
    "protocol": 4,
    "writer_version": "1.0.0",
    "core_version": "0.7.0",
    "writer_sha256": "02a952e6eb63942b05040897736cdda60731923b876840f5576c29a214f9817d",
    "pandas_version": "2.3.3",
    "numpy_version": "1.26.4",
    "shape": [
      1455,
      5427
    ],
    "index_type": "Index[str YYYYMMDD]",
    "column_type": "Index[str six-digit code + observed exchange suffix]",
    "multiindex": false,
    "index_name": "date",
    "columns_name": "Code",
    "dtype": "float64",
    "date_start": "20200102",
    "date_end": "20251231",
    "nan_cells": 1097496,
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
            "op": "mul",
            "args": [
              4,
              7
            ]
          }
        ],
        "output": 8
      },
      "expression_sha256": "5907b2ce09999afb716d67dfba787fc8f512308587142632ae2ffba3404b0e60",
      "input_fields": [
        "close",
        "volume"
      ],
      "nodes": 9,
      "warmup_observations": 5,
      "formula": "mul(div(volume,delay(rolling_mean(volume,5),1)),neg(returns(close,5)))",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "成交量放大伴随短期价格下跌（放量下跌/放量滞涨）后存在短期反转修复倾向：以成交量相对前期均值的放量程度乘以负的短期价格收益构造组合因子，因子值越高预期未来5日收益越高。",
      "generation_reason": "用户要求组合成交量变化与短期价格反转，属新定义，必须用表达式入口而非固定 volume_stall（后者用绝对价格收益、无反转方向）。表达式：vol_ratio=volume/delay(rolling_mean(volume,5),1)（历史均量不含当日），rev=neg(returns(close,5))，组合=mul(vol_ratio,rev)。参数取默认 lookback=5、horizon=5、n_groups=5、standardization=raw，在 Train 冻结定义并计算全轴，由工具自动在配对 Validation 评价 IC、RankIC 与分组稳定性并生成报告与 PKL。",
      "name": "volume_change_x_short_reversal"
    },
    "axis_mapping_sha256": "a3550b5985b2780951a3e1aad5f169218d1af091d8651f5e951a4d94b109dc73",
    "data_sha256": "9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221",
    "available_time": "historical availability unverified; T-close research assumption",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/20-04-20_volume_change_x_short_reversal/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "db6b10df59bb0217e41349bc3d0204e08d978d8bb2223d274aefb40ae1d7af65",
        "bytes": 63252076
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/20-04-20_volume_change_x_short_reversal/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "1d3d660c1bad4e78ff6a0826da8f1d7193928fb71be4806f6dfd9ebb09da46e4",
        "bytes": 52514649
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/20-04-20_volume_change_x_short_reversal/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "b560dd5bc0122e152d1d6818910250663a10ef8aa84e078831caed8dd3b3b8f7",
        "bytes": 63235786
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-12/20-04-20_volume_change_x_short_reversal/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "6277662695646c8813df5d0ce529dbd6a210f71483049897af3570c0075ecda4",
        "bytes": 63252092
      }
    ],
    "data_partitions": {
      "train": {
        "resource_id": "gpushare:train2020_2023",
        "release_id": "baseline_20261009_a864dc33",
        "manifest_sha256": "9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221",
        "field_sha256": {
          "amount.npy": "ff420dff97ed9bd2a92a9efd223113ac33e926e6eb496db5deaba05b8c141772",
          "close.npy": "bfa83291f46bc612928cbbb56c9ab95a6d739748352575572d06ef7220ddcc03",
          "high.npy": "f65f84467a1d9fa2d996af0f7ece8c6a60c6482611ee0656313cacf51234804d",
          "low.npy": "54052a557a7c9a1efc75f3e151fb91fb58f68c411aca813a26ae6ef7525f8f3a",
          "open.npy": "55e6e69b057bd5db824ef46caf849f46ad52c61157d082e87dd560b2cc860176",
          "volume.npy": "a537e7b42e66e1311c86b88335aefeb8d387bfe632943519557080537dbf46d2"
        },
        "start": "2020-01-02",
        "end": "2023-12-29",
        "n_dates": 970,
        "n_codes": 5427,
        "status": "PROFILED_EXPLORATORY_ONLY"
      },
      "validation": {
        "resource_id": "gpushare:validation2024_2025",
        "release_id": "baseline_20261009_a864dc33",
        "manifest_sha256": "82246b4424f8dbd45c11d959164199a4b45efeb6803d6a6064204a6fc08bf4b4",
        "field_sha256": {
          "amount.npy": "39ea7b7bddebd77433035dac23c1842561baed93a1a6dc7f2286e01c3c9b03b5",
          "close.npy": "442b38218ac8d36f47a9d3b27a48a3254bca6c20a0238b70ced3a5a26f5901de",
          "high.npy": "50c45a4d2eaa169abf487289600342c2f82cc9d20642953340e366aeda58972d",
          "low.npy": "b9f9990d22a4616f5bb8a36557f60ebf203a81917a0cbca699177d6003113bbd",
          "open.npy": "8af62df69fc6b1897c6fee6a3ee7b19c7a15800de316629287a19d5adeb225fc",
          "volume.npy": "b1431c8ddeab9cad9542eaec44ee77e3cdda7eb05c132b8a93922d2928ac4a5c"
        },
        "start": "2024-01-02",
        "end": "2025-12-31",
        "n_dates": 485,
        "n_codes": 5427,
        "status": "PROFILED_EXPLORATORY_ONLY"
      }
    },
    "code_count": 5427
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
    "latex": "f_{t,i}=\\left(\\frac{V_{t,i}}{\\mathrm{Delay}_{1}\\left(\\mathrm{Mean}_{5}\\left(V_{t,i}\\right)\\right)}\\cdot -\\left(\\left(\\frac{C_{t,i}}{\\mathrm{Delay}_{5}\\left(C_{t,i}\\right)}-1\\right)\\right)\\right)",
    "definition_sha256": "37571b811d34b4a603f73bb303c9c3b8f1e9b157572d40c32d21c6bd2fb28372",
    "renderer": "Matplotlib mathtext / offline SVG",
    "renderer_version": "3.8.4",
    "formula_version": "1.0.0"
  },
  "data_partitions": {
    "train": {
      "resource_id": "gpushare:train2020_2023",
      "release_id": "baseline_20261009_a864dc33",
      "manifest_sha256": "9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221",
      "field_sha256": {
        "amount.npy": "ff420dff97ed9bd2a92a9efd223113ac33e926e6eb496db5deaba05b8c141772",
        "close.npy": "bfa83291f46bc612928cbbb56c9ab95a6d739748352575572d06ef7220ddcc03",
        "high.npy": "f65f84467a1d9fa2d996af0f7ece8c6a60c6482611ee0656313cacf51234804d",
        "low.npy": "54052a557a7c9a1efc75f3e151fb91fb58f68c411aca813a26ae6ef7525f8f3a",
        "open.npy": "55e6e69b057bd5db824ef46caf849f46ad52c61157d082e87dd560b2cc860176",
        "volume.npy": "a537e7b42e66e1311c86b88335aefeb8d387bfe632943519557080537dbf46d2"
      },
      "start": "2020-01-02",
      "end": "2023-12-29",
      "n_dates": 970,
      "n_codes": 5427,
      "status": "PROFILED_EXPLORATORY_ONLY"
    },
    "validation": {
      "resource_id": "gpushare:validation2024_2025",
      "release_id": "baseline_20261009_a864dc33",
      "manifest_sha256": "82246b4424f8dbd45c11d959164199a4b45efeb6803d6a6064204a6fc08bf4b4",
      "field_sha256": {
        "amount.npy": "39ea7b7bddebd77433035dac23c1842561baed93a1a6dc7f2286e01c3c9b03b5",
        "close.npy": "442b38218ac8d36f47a9d3b27a48a3254bca6c20a0238b70ced3a5a26f5901de",
        "high.npy": "50c45a4d2eaa169abf487289600342c2f82cc9d20642953340e366aeda58972d",
        "low.npy": "b9f9990d22a4616f5bb8a36557f60ebf203a81917a0cbca699177d6003113bbd",
        "open.npy": "8af62df69fc6b1897c6fee6a3ee7b19c7a15800de316629287a19d5adeb225fc",
        "volume.npy": "b1431c8ddeab9cad9542eaec44ee77e3cdda7eb05c132b8a93922d2928ac4a5c"
      },
      "start": "2024-01-02",
      "end": "2025-12-31",
      "n_dates": 485,
      "n_codes": 5427,
      "status": "PROFILED_EXPLORATORY_ONLY"
    }
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