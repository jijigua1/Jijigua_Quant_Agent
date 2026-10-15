> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究 · momentum_20d_v08_benchmark / 预热20观察日

状态：incomplete / exploratory；PKL已验证，正式回测未准入。

## 研究摘要

REJECTED · Train / Validation RankIC：-0.0391 / -0.0710。 与Train方向一致的年度：6/6。

gpushare:train2020_2023 · 2020-01-02—2025-12-31 · 5427只 · 复权=none · 创建 2026-10-13 00:59:49（上海时间）

### 统一三阶段研究

| 分区 | 年份 | 状态 | 实际数据范围 |
|---|---|---|---|
| Train | 2020—2023 | COMPLETED | 2020-01-02 — 2023-12-29 |
| Validation | 2024—2025 | COMPLETED / EXPOSED | 2024-01-02 — 2025-12-31 |
| Test | 2026 | NOT_RUN / SEALED | 未获批 — 认证截止日期未确定 |

### Train / Validation / Test · 核心指标

| 样本 | 指标 | 均值 | 标准差 | IR¹ | 有效日 |
|---|---|---|---|---|---|
| train | ic | -0.0290 | 0.1162 | -0.2494 | 944 |
| train | rank_ic | -0.0391 | 0.1290 | -0.3035 | 944 |
| valid | ic | -0.0461 | 0.1409 | -0.3273 | 479 |
| valid | rank_ic | -0.0710 | 0.1732 | -0.4099 | 479 |
| Test / NOT_RUN / SEALED | ic | N/A | N/A | N/A | N/A |
| Test / NOT_RUN / SEALED | rank_ic | N/A | N/A | N/A | N/A |

PKL：/srv/jijigua-quant-agent/research_runs/2026-10-13/00-59-49_momentum_20d_v08_benchmark/data/factor.pkl

## 因子定义与经济假设

$$
f_{t,i}=\left(\frac{C_{t,i}}{\mathrm{Delay}_{20}\left(C_{t,i}\right)}-1\right)
$$

same20d raw momentum v0.7 comparison; professional2020-2025 report

C/O/H/L为收盘/开盘/最高/最低价，V为成交量，t为当前观察日，i为股票。Delay为历史偏移；Mean/Std/RankTS/CorrTS包含当日的完整历史窗口（Std: ddof=1）；RankCS为横截面百分位平均秩，ZCS为当日横截面样本标准化。固定放量滞涨的成交量均值使用前L日、不含当日。

## 预测能力

### 中位数、方向与有效股票

| 样本 | 指标 | 中位数 | 正值比例 | 平均股票数 | 有效日 |
|---|---|---|---|---|---|
| train | ic | -0.0273 | 40.89% | 4459.6303 | 944 |
| train | rank_ic | -0.0399 | 38.98% | 4459.6303 | 944 |
| valid | ic | -0.0431 | 35.07% | 5091.4823 | 479 |
| valid | rank_ic | -0.0629 | 29.23% | 5091.4823 | 479 |

### 预测期衰减

| 样本 | H | IC均值 | RankIC均值 | 有效日 |
|---|---|---|---|---|
| train | 1 | -0.0139 | -0.0285 | 948 |
| valid | 1 | -0.0217 | -0.0422 | 483 |
| train | 3 | -0.0250 | -0.0372 | 946 |
| valid | 3 | -0.0377 | -0.0595 | 481 |
| train | 5 | -0.0290 | -0.0391 | 944 |
| valid | 5 | -0.0461 | -0.0710 | 479 |
| train | 10 | -0.0349 | -0.0450 | 939 |
| valid | 10 | -0.0568 | -0.0873 | 474 |

### 统计推断准入

| 样本 | 指标 | 状态 | 输入日 | 有效日 | HAC滞后 |
|---|---|---|---|---|---|
| train | ic | approximate | 944 | 944 | 6 |
| train | rank_ic | approximate | 944 | 944 | 6 |
| valid | ic | approximate | 479 | 479 | 5 |
| valid | rank_ic | approximate | 479 | 479 | 5 |

### HAC均值95%区间

| 样本 | 指标 | 标准误 | 下界 | 上界 |
|---|---|---|---|---|
| train | ic | 0.0071 | -0.0429 | -0.0150 |
| train | rank_ic | 0.0078 | -0.0545 | -0.0238 |
| valid | ic | 0.0113 | -0.0682 | -0.0240 |
| valid | rank_ic | 0.0137 | -0.0978 | -0.0442 |

## Annual Performance · 逐年表现

### 三阶段状态

| 分区 | 规定年份 | 评价状态 | 实际数据范围 |
|---|---|---|---|
| Train | 2020—2023 | COMPLETED | 2020-01-02 — 2023-12-29 |
| Validation | 2024—2025 | COMPLETED / EXPOSED | 2024-01-02 — 2025-12-31 |
| Test | 2026 | NOT_RUN / SEALED | 未获批 — 认证截止日期未确定 |

### 逐年预测能力

| 年份/分区 | IC均值 | RankIC均值 | RankIC IR | 正RankIC | 有效日 |
|---|---|---|---|---|---|
| 2020 / train | -0.0150 | -0.0324 | -0.2681 | 42.15% | 223 |
| 2021 / train | -0.0138 | -0.0286 | -0.2029 | 41.98% | 243 |
| 2022 / train | -0.0481 | -0.0484 | -0.3565 | 38.84% | 242 |
| 2023 / train | -0.0382 | -0.0469 | -0.4063 | 33.05% | 236 |
| 2024 / valid | -0.0571 | -0.0665 | -0.3246 | 32.64% | 242 |
| 2025 / valid | -0.0349 | -0.0756 | -0.5654 | 25.74% | 237 |
| 2026 / Test · SEALED / NOT_RUN | N/A | N/A | N/A | N/A | N/A |

### 逐年IC完整汇总

| 年份 | IC median | IC std | IC IR | 正IC比例 | 有效日 |
|---|---|---|---|---|---|
| 2020 | -0.0247 | 0.1115 | -0.1347 | 44.39% | 223 |
| 2021 | -0.0070 | 0.1267 | -0.1091 | 47.33% | 243 |
| 2022 | -0.0356 | 0.1108 | -0.4339 | 37.19% | 242 |
| 2023 | -0.0419 | 0.1117 | -0.3423 | 34.75% | 236 |
| 2024 | -0.0495 | 0.1610 | -0.3545 | 30.58% | 242 |
| 2025 | -0.0318 | 0.1163 | -0.3006 | 39.66% | 237 |

### 逐年RankIC完整汇总

| 年份 | RankIC median | RankIC std | RankIC IR | 正RankIC比例 | 有效日 |
|---|---|---|---|---|---|
| 2020 | -0.0342 | 0.1209 | -0.2681 | 42.15% | 223 |
| 2021 | -0.0295 | 0.1408 | -0.2029 | 41.98% | 243 |
| 2022 | -0.0434 | 0.1356 | -0.3565 | 38.84% | 242 |
| 2023 | -0.0529 | 0.1155 | -0.4063 | 33.05% | 236 |
| 2024 | -0.0596 | 0.2047 | -0.3246 | 32.64% | 242 |
| 2025 | -0.0662 | 0.1337 | -0.5654 | 25.74% | 237 |

### 年度不确定性与覆盖

| 年份 | RankIC std | HAC 95%下界 | HAC 95%上界 | 覆盖率 | Lag1 |
|---|---|---|---|---|---|
| 2020 | 0.1209 | -0.0596 | -0.0052 | 65.30% | 0.9531 |
| 2021 | 0.1408 | -0.0608 | 0.0036 | 79.36% | 0.9509 |
| 2022 | 0.1356 | -0.0776 | -0.0192 | 86.54% | 0.9479 |
| 2023 | 0.1155 | -0.0719 | -0.0219 | 91.59% | 0.9444 |
| 2024 | 0.2047 | -0.1109 | -0.0220 | 93.64% | 0.9458 |
| 2025 | 0.1337 | -0.1040 | -0.0472 | 94.29% | 0.9487 |

### 年度理论分组诊断

| 年份 | G0−末组均值 | 毛收益std | 单调性 | IC正比 | 有效日 |
|---|---|---|---|---|---|
| 2020 | -0.10% | 1.99% | 0.0103 | 44.39% | 223 |
| 2021 | -0.09% | 2.51% | 0.0617 | 47.33% | 243 |
| 2022 | -0.55% | 2.06% | -0.0938 | 37.19% | 242 |
| 2023 | -0.45% | 1.66% | -0.1165 | 34.75% | 236 |
| 2024 | -0.86% | 4.24% | -0.1442 | 30.58% | 242 |
| 2025 | -0.49% | 2.06% | -0.0869 | 39.66% | 237 |

## Monthly Performance · 月度热力图

### 逐月完整评价

| 月份/分区 | IC均值 | RankIC均值 | 有效日 | 正RankIC | 覆盖率 |
|---|---|---|---|---|---|
| 2020-01 / train | N/A | N/A | 0 | N/A | 0.00% |
| 2020-02 / train | -0.0864 | -0.1336 | 16 | 18.75% | 55.16% |
| 2020-03 / train | -0.0649 | -0.0498 | 22 | 36.36% | 69.34% |
| 2020-04 / train | -0.0262 | -0.0001 | 21 | 52.38% | 69.41% |
| 2020-05 / train | 0.0185 | -0.0059 | 18 | 44.44% | 69.57% |
| 2020-06 / train | -0.0186 | -0.0746 | 20 | 15.00% | 69.81% |
| 2020-07 / train | 0.0298 | -0.0335 | 23 | 52.17% | 70.28% |
| 2020-08 / train | -0.0563 | -0.0604 | 21 | 28.57% | 71.05% |
| 2020-09 / train | -0.0556 | -0.0926 | 22 | 18.18% | 71.98% |
| 2020-10 / train | 0.0113 | 0.0298 | 16 | 75.00% | 73.03% |
| 2020-11 / train | -0.0612 | -0.0595 | 21 | 38.10% | 74.06% |
| 2020-12 / train | 0.1250 | 0.1068 | 23 | 82.61% | 74.63% |
| 2021-01 / train | -0.0128 | -0.0088 | 20 | 60.00% | 75.20% |
| 2021-02 / train | -0.1071 | -0.0971 | 15 | 20.00% | 75.87% |
| 2021-03 / train | -0.0300 | -0.0469 | 23 | 39.13% | 76.47% |
| 2021-04 / train | 0.0018 | -0.0123 | 21 | 42.86% | 77.09% |
| 2021-05 / train | 0.0066 | -0.0421 | 18 | 33.33% | 77.88% |
| 2021-06 / train | 0.0072 | -0.0025 | 21 | 42.86% | 78.69% |
| 2021-07 / train | 0.0785 | 0.0827 | 22 | 77.27% | 79.68% |
| 2021-08 / train | -0.0104 | -0.0244 | 22 | 40.91% | 80.70% |
| 2021-09 / train | -0.0680 | -0.0407 | 20 | 40.00% | 81.53% |
| 2021-10 / train | 0.0243 | -0.0177 | 16 | 56.25% | 82.06% |
| 2021-11 / train | -0.0375 | -0.0741 | 22 | 22.73% | 82.73% |
| 2021-12 / train | -0.0353 | -0.0747 | 23 | 26.09% | 83.45% |
| 2022-01 / train | -0.0370 | -0.0100 | 19 | 47.37% | 84.07% |
| 2022-02 / train | -0.0443 | -0.0353 | 16 | 50.00% | 84.66% |
| 2022-03 / train | 0.0246 | 0.0639 | 23 | 69.57% | 85.19% |
| 2022-04 / train | -0.0529 | -0.0396 | 19 | 47.37% | 85.45% |
| 2022-05 / train | -0.0959 | -0.1055 | 19 | 10.53% | 85.23% |
| 2022-06 / train | -0.0508 | -0.0699 | 21 | 33.33% | 85.73% |
| 2022-07 / train | -0.0093 | -0.0267 | 21 | 47.62% | 86.25% |
| 2022-08 / train | -0.0905 | -0.0990 | 23 | 21.74% | 86.92% |
| 2022-09 / train | -0.0477 | -0.0264 | 21 | 38.10% | 87.65% |
| 2022-10 / train | -0.0477 | -0.0581 | 16 | 43.75% | 88.29% |
| 2022-11 / train | -0.0873 | -0.1241 | 22 | 22.73% | 88.91% |
| 2022-12 / train | -0.0426 | -0.0519 | 22 | 36.36% | 89.47% |
| 2023-01 / train | -0.0938 | -0.1006 | 16 | 12.50% | 89.81% |
| 2023-02 / train | -0.0374 | -0.0387 | 20 | 35.00% | 90.10% |
| 2023-03 / train | 0.0703 | 0.0418 | 23 | 60.87% | 90.39% |
| 2023-04 / train | 0.0268 | -0.0169 | 19 | 36.84% | 90.71% |
| 2023-05 / train | -0.1017 | -0.1341 | 20 | 5.00% | 90.67% |
| 2023-06 / train | -0.0747 | -0.0908 | 20 | 20.00% | 90.90% |
| 2023-07 / train | -0.0410 | -0.0275 | 21 | 42.86% | 91.43% |
| 2023-08 / train | -0.1055 | -0.1041 | 23 | 26.09% | 92.22% |
| 2023-09 / train | -0.0025 | -0.0363 | 20 | 30.00% | 92.76% |
| 2023-10 / train | -0.0294 | -0.0222 | 17 | 35.29% | 93.04% |
| 2023-11 / train | -0.0403 | -0.0245 | 22 | 40.91% | 93.25% |
| 2023-12 / train | -0.0434 | -0.0150 | 15 | 46.67% | 93.41% |
| 2024-01 / valid | 0.0738 | 0.1564 | 22 | 86.36% | 93.55% |
| 2024-02 / valid | -0.2076 | -0.2215 | 15 | 33.33% | 93.74% |
| 2024-03 / valid | -0.0474 | -0.0523 | 21 | 33.33% | 93.88% |
| 2024-04 / valid | -0.0996 | -0.1403 | 20 | 35.00% | 93.87% |
| 2024-05 / valid | 0.0171 | -0.0191 | 20 | 40.00% | 93.65% |
| 2024-06 / valid | -0.0685 | -0.0652 | 19 | 26.32% | 93.63% |
| 2024-07 / valid | -0.0456 | -0.0497 | 23 | 26.09% | 93.45% |
| 2024-08 / valid | -0.0709 | -0.0758 | 22 | 13.64% | 93.55% |
| 2024-09 / valid | -0.0775 | -0.0896 | 19 | 15.79% | 93.56% |
| 2024-10 / valid | -0.0136 | -0.0888 | 18 | 33.33% | 93.54% |
| 2024-11 / valid | -0.0989 | -0.1238 | 21 | 23.81% | 93.58% |
| 2024-12 / valid | -0.0894 | -0.0894 | 22 | 22.73% | 93.75% |
| 2025-01 / valid | -0.1119 | -0.1476 | 18 | 27.78% | 93.84% |
| 2025-02 / valid | 0.0136 | -0.0251 | 18 | 50.00% | 93.99% |
| 2025-03 / valid | -0.0547 | -0.0585 | 21 | 23.81% | 94.08% |
| 2025-04 / valid | -0.1280 | -0.1717 | 21 | 19.05% | 93.99% |
| 2025-05 / valid | -0.0334 | -0.0493 | 19 | 21.05% | 94.00% |
| 2025-06 / valid | -0.0528 | -0.0918 | 20 | 15.00% | 94.14% |
| 2025-07 / valid | -0.0052 | -0.0689 | 23 | 13.04% | 94.30% |
| 2025-08 / valid | -0.0089 | -0.0634 | 21 | 23.81% | 94.46% |
| 2025-09 / valid | 0.0113 | -0.0303 | 22 | 40.91% | 94.57% |
| 2025-10 / valid | -0.0400 | -0.0817 | 17 | 23.53% | 94.61% |
| 2025-11 / valid | -0.0215 | -0.0476 | 20 | 35.00% | 94.66% |
| 2025-12 / valid | 0.0108 | -0.0753 | 17 | 17.65% | 94.70% |

## Predictive Stability · 时间稳定性

分别展示IC与RankIC；滚动窗口使用连续观察日、完整窗口；累计相关按分区重置，不是账户净值。

## 稳定性与分布诊断

### 因子值与排序自相关

| 样本 | Lag | 值相关 | 秩相关 | 有效日 | 平均共同股票 |
|---|---|---|---|---|---|
| train | 1 | 0.9490 | 0.9296 | 949 | 4466.3235 |
| valid | 1 | 0.9472 | 0.9258 | 485 | 5095.8495 |
| train | 5 | 0.7272 | 0.6872 | 945 | 4457.7143 |
| valid | 5 | 0.7123 | 0.6648 | 485 | 5088.8289 |
| train | 10 | 0.4616 | 0.4266 | 940 | 4450.4734 |
| valid | 10 | 0.4441 | 0.3949 | 485 | 5083.4845 |

### 时间窗口稳定性

| 样本 | 指标 | 子窗口 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|---|
| train | ic | first_half | -0.0151 | 0.1196 | 462 |
| train | ic | second_half | -0.0422 | 0.1114 | 482 |
| train | rank_ic | first_half | -0.0319 | 0.1311 | 462 |
| train | rank_ic | second_half | -0.0461 | 0.1266 | 482 |
| valid | ic | first_half | -0.0575 | 0.1619 | 239 |
| valid | ic | second_half | -0.0348 | 0.1156 | 240 |
| valid | rank_ic | first_half | -0.0668 | 0.2060 | 239 |
| valid | rank_ic | second_half | -0.0751 | 0.1330 | 240 |

### 分布与数据质量

| 指标 | 值 | 口径 |
|---|---|---|
| 覆盖率 | 85.11% | 完整可见矩形含暖机 |
| 缺失率 | 14.89% | NaN保留 |
| 有效因子值 | 6720395 | 训练+验证有限数值 |
| 均值 / 标准差 | 0.0085 / 0.1464 | 合并观测、ddof=1 |
| 偏度 / 超额峰度 | 2.6325 / 39.6322 | 无偏估计，小样本可N/A |
| 异常值比例 | 1.38% | 逐日稳健z>5，MAD=0不评估 |
| 最长连续缺失 | 1455 | 观察日，含暖机 |
| P01 / P50 / P99 | -0.2944 / -0.0055 / 0.4883 | 无尾部修剪 |

## 分组表现

### 分组未来毛收益

| 样本 | 组别 | 均值 | 标准差 | 有效日 |
|---|---|---|---|---|
| train | G0 | -0.18% | 3.05% | 944 |
| train | G1 | 0.26% | 2.74% | 944 |
| train | G2 | 0.29% | 2.78% | 944 |
| train | G3 | 0.22% | 2.93% | 944 |
| train | G4 | 0.12% | 3.31% | 944 |
| valid | G0 | -0.04% | 4.65% | 479 |
| valid | G1 | 0.48% | 4.53% | 479 |
| valid | G2 | 0.56% | 4.77% | 479 |
| valid | G3 | 0.59% | 5.12% | 479 |
| valid | G4 | 0.64% | 5.73% | 479 |

### 单调性

| 样本 | G0−末组毛收益 | 单调性² | 有效日 |
|---|---|---|---|
| train | -0.30% | -0.1000 | 944 |
| valid | -0.68% | -1.0000 | 479 |

## Robustness & Risks · 稳健性

### 分区HAC统计推断

| 样本/指标 | t统计量 | p（渐近） | 95%下界 | 95%上界 | 状态 |
|---|---|---|---|---|---|
| train / ic | -4.0749 | 4.6e-05 | -0.0429 | -0.0150 | approximate |
| train / rank_ic | -4.9993 | 5.75e-07 | -0.0545 | -0.0238 | approximate |
| valid / ic | -4.0912 | 4.29e-05 | -0.0682 | -0.0240 | approximate |
| valid / rank_ic | -5.1885 | 2.12e-07 | -0.0978 | -0.0442 | approximate |

### 极端值敏感性（预设诊断）

| 样本/指标 | 原均值 | 移除极端值后 | 变化 | 有效日 |
|---|---|---|---|---|
| train / ic | -0.0290 | -0.0186 | 0.0104 | 944 |
| valid / ic | -0.0461 | -0.0349 | 0.0112 | 479 |
| train / rank_ic | -0.0391 | -0.0339 | 0.0052 | 944 |
| valid / rank_ic | -0.0710 | -0.0649 | 0.0061 | 479 |

## Independent Test · 最终独立评价

### 三阶段状态

| 分区 | 规定年份 | 评价状态 | 实际数据范围 |
|---|---|---|---|
| Train | 2020—2023 | COMPLETED | 2020-01-02 — 2023-12-29 |
| Validation | 2024—2025 | COMPLETED / EXPOSED | 2024-01-02 — 2025-12-31 |
| Test | 2026 | NOT_RUN / SEALED | 未获批 — 认证截止日期未确定 |

Test：NOT_RUN / SEALED。未获得真实发布及首次结果解封批准；现有报告不包含2026评价数值。

## Research Verdict · 研究判断

REJECTED

- Train / Validation RankIC：-0.0391 / -0.0710。
- 与Train方向一致的年度：6/6。
- HAC区间均不跨0。
- 正RankIC月份占比：8.5%；最长非正月份连续23个月。
- Validation因子覆盖率：94.0%；高低组理论毛收益差：-0.680%；日度单调性均值：-0.116。
- 预先冻结的高分看多方向不获支持；反向定义需新实验，不能事后翻转方向冒充成功。
- 原始未复权收益、未认证历史股票池及已曝光Validation限制证据强度；不构成可交易结论。

Test：NOT_RUN / SEALED。未获得真实发布及首次结果解封批准；现有报告不包含2026评价数值。

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
- no industry/size neutralisation or multiple-testing adjustment; HAC inference has explicit sample admission
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
  "goal": "same20d raw momentum v0.7 comparison; professional2020-2025 report",
  "parameters": {
    "resource_id": "gpushare:train2020_2023",
    "factor_id": "expression",
    "lookback": 20,
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
            "window": 20
          }
        ],
        "output": 1
      },
      "expression_sha256": "61dfba22689ae377a8b78a5680aff53434c65f134b82395e39214040cd8c8713",
      "input_fields": [
        "close"
      ],
      "nodes": 2,
      "warmup_observations": 20,
      "formula": "returns(close,20)",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "Prespecified20d raw momentum test; exploratory only",
      "generation_reason": "same definition as v0.7 engineering baseline, no parameter search",
      "name": "momentum_20d_v08_benchmark"
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
    "core_version": "0.8.0",
    "tool_version": "0.4.0",
    "source_sha256": "69d81b746a3d5848a85cafe964b995dbc39e6d17a829fe936e6fad445d05c8c2",
    "report_version": "3.0.0"
  },
  "factor_export": {
    "status": "VERIFIED",
    "format_version": "server-panel-v1",
    "protocol": 4,
    "writer_version": "1.0.0",
    "core_version": "0.8.0",
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
    "nan_cells": 1175890,
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
            "window": 20
          }
        ],
        "output": 1
      },
      "expression_sha256": "61dfba22689ae377a8b78a5680aff53434c65f134b82395e39214040cd8c8713",
      "input_fields": [
        "close"
      ],
      "nodes": 2,
      "warmup_observations": 20,
      "formula": "returns(close,20)",
      "output_units": {
        "price_power": 0,
        "volume_power": 0
      },
      "available_time": "T close after all required input observations; historical publication time requires data contract",
      "zero_denominator": "NaN",
      "rolling_min_periods": "full window",
      "rank_ties": "average",
      "std_ddof": 1,
      "hypothesis": "Prespecified20d raw momentum test; exploratory only",
      "generation_reason": "same definition as v0.7 engineering baseline, no parameter search",
      "name": "momentum_20d_v08_benchmark"
    },
    "axis_mapping_sha256": "a3550b5985b2780951a3e1aad5f169218d1af091d8651f5e951a4d94b109dc73",
    "data_sha256": "9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221",
    "available_time": "historical availability unverified; T-close research assumption",
    "scope": "train+validation factor values only; no future labels/test performance/account data",
    "downstream": "single-panel Gyc norm_index and Perry score reader; dictionary Perry load_and_pivot_factors; structure only, no account qualification",
    "files": [
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-13/00-59-49_momentum_20d_v08_benchmark/data/factor.pkl",
        "format": "server-panel-v1",
        "sha256": "b2cc14d81ea3cc83444644be758ff7e52895b131892a92ca1b40f08f029a0084",
        "bytes": 63252076
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-13/00-59-49_momentum_20d_v08_benchmark/data/factor.pkl.zip",
        "format": "server-panel-zip-v1",
        "sha256": "e216515c979706d9c06553658f43f2b641d235678ff184d55e6e5f5c3a70d3e5",
        "bytes": 47216837
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-13/00-59-49_momentum_20d_v08_benchmark/data/factor_plain.pkl",
        "format": "plain-code-panel-v1",
        "sha256": "ba9e55d955764254a49677c1138e2d3bdeff30d33b0217041391dfab10ed2ed8",
        "bytes": 63235786
      },
      {
        "path": "/srv/jijigua-quant-agent/research_runs/2026-10-13/00-59-49_momentum_20d_v08_benchmark/data/factor_dict.pkl",
        "format": "perry-dict-v1",
        "sha256": "772c718d3f25cb82d8759ea6bc1bcf4933b87084715246608d1d3ba85246ee6e",
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
    "latex": "f_{t,i}=\\left(\\frac{C_{t,i}}{\\mathrm{Delay}_{20}\\left(C_{t,i}\\right)}-1\\right)",
    "definition_sha256": "17936a0a2954e420752f6a75c7702be5656ee840ed073a705e0e16faf5baf0bd",
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
  },
  "professional_evaluation": {
    "schema_version": "factor-report/2",
    "evaluation_version": "factor-evaluation/1.0.0",
    "study_id": "INTERNAL_RUN_ID_REDACTED:1de92a8707724ebf",
    "report_revision": 1,
    "definition_sha256": "60d7190497b52fb664e0cf51fc66a4231b11af842278f2b84c04a23f76194d66",
    "data_fingerprint": "9d64e6c73962702ad5ce5cdca4ff736ef39dc36f97e26066e79b1bdb9a453221",
    "partitions": {
      "train": {
        "period": "train",
        "split": "train",
        "observed_dates": 970,
        "mean_coverage": 0.8067936377676338,
        "mean_stocks": 4459.630296610169,
        "long_short_mean_gross": -0.0030264041632956573,
        "long_short_std_gross": 0.02090137311387276,
        "group_monotonicity": -0.03485169491525423,
        "factor_lag1": 0.9489727473185272,
        "rank_lag1": 0.929571541029194,
        "ic_mean": -0.028983357028120688,
        "ic_median": -0.0272828261448505,
        "ic_std": 0.11622340316297351,
        "ic_ir": -0.2493762550342719,
        "ic_positive_ratio": 0.4088983050847458,
        "ic_n_dates": 944,
        "ic_status": "approximate",
        "ic_n_valid": 944,
        "ic_lags": 6,
        "ic_se": 0.0071126460919275205,
        "ic_ci_low": -0.04292388720307781,
        "ic_ci_high": -0.015042826853163565,
        "ic_t_stat": -4.074904986628714,
        "ic_p_value": 4.60331377680513e-05,
        "rank_ic_mean": -0.03914481081742341,
        "rank_ic_median": -0.0398637013898636,
        "rank_ic_std": 0.12897588224571446,
        "rank_ic_ir": -0.30350488894387145,
        "rank_ic_positive_ratio": 0.3898305084745763,
        "rank_ic_n_dates": 944,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 944,
        "rank_ic_lags": 6,
        "rank_ic_se": 0.007830099968694462,
        "rank_ic_ci_low": -0.054491524751412335,
        "rank_ic_ci_high": -0.023798096883434483,
        "rank_ic_t_stat": -4.999273441453922,
        "rank_ic_p_value": 5.754674499639419e-07,
        "effect_status": "descriptive_exploratory"
      },
      "valid": {
        "period": "valid",
        "split": "valid",
        "observed_dates": 485,
        "mean_coverage": 0.9396621322558646,
        "mean_stocks": 5091.482254697286,
        "long_short_mean_gross": -0.00680189437749114,
        "long_short_std_gross": 0.0334145231658889,
        "group_monotonicity": -0.11586638830897703,
        "factor_lag1": 0.9472279200275968,
        "rank_lag1": 0.925805840560685,
        "ic_mean": -0.046118259626367376,
        "ic_median": -0.043126965508628,
        "ic_std": 0.14092538993071643,
        "ic_ir": -0.32725302125501043,
        "ic_positive_ratio": 0.35073068893528186,
        "ic_n_dates": 479,
        "ic_status": "approximate",
        "ic_n_valid": 479,
        "ic_lags": 5,
        "ic_se": 0.011272446825335292,
        "ic_ci_low": -0.0682118494216668,
        "ic_ci_high": -0.024024669831067942,
        "ic_t_stat": -4.091237718036041,
        "ic_p_value": 4.290770291313251e-05,
        "rank_ic_mean": -0.07097932285838279,
        "rank_ic_median": -0.0628968074778407,
        "rank_ic_std": 0.17315398959147166,
        "rank_ic_ir": -0.40992022780327975,
        "rank_ic_positive_ratio": 0.29227557411273486,
        "rank_ic_n_dates": 479,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 479,
        "rank_ic_lags": 5,
        "rank_ic_se": 0.013680140423334361,
        "rank_ic_ci_low": -0.09779190539156793,
        "rank_ic_ci_high": -0.044166740325197656,
        "rank_ic_t_stat": -5.18849373339126,
        "rank_ic_p_value": 2.1200189475958713e-07,
        "effect_status": "descriptive_exploratory"
      }
    },
    "test": {
      "status": "NOT_RUN",
      "access": "SEALED",
      "evaluation_type": null,
      "exposure": null
    },
    "annual": [
      {
        "period": 2020,
        "split": "train",
        "observed_dates": 243,
        "mean_coverage": 0.6529651695796281,
        "mean_stocks": 3852.4484304932735,
        "long_short_mean_gross": -0.0010497703648576439,
        "long_short_std_gross": 0.019939162706041,
        "group_monotonicity": 0.01031390134529149,
        "factor_lag1": 0.9530774228089727,
        "rank_lag1": 0.9317323987298508,
        "ic_mean": -0.01500858680054626,
        "ic_median": -0.0247104657152512,
        "ic_std": 0.11145152101514517,
        "ic_ir": -0.13466471039463643,
        "ic_positive_ratio": 0.4439461883408072,
        "ic_n_dates": 223,
        "ic_status": "approximate",
        "ic_n_valid": 223,
        "ic_lags": 4,
        "ic_se": 0.013017370506498063,
        "ic_ci_low": -0.040522164166695684,
        "ic_ci_high": 0.010504990565603162,
        "ic_t_stat": -1.1529660919656712,
        "ic_p_value": 0.24892430240057378,
        "rank_ic_mean": -0.032417998911878125,
        "rank_ic_median": -0.03422641786299,
        "rank_ic_std": 0.12089971794471763,
        "rank_ic_ir": -0.2681395743760256,
        "rank_ic_positive_ratio": 0.42152466367713004,
        "rank_ic_n_dates": 223,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 223,
        "rank_ic_lags": 4,
        "rank_ic_se": 0.01387143602353091,
        "rank_ic_ci_low": -0.059605513931849465,
        "rank_ic_ci_high": -0.005230483891906786,
        "rank_ic_t_stat": -2.337032651622054,
        "rank_ic_p_value": 0.019437486371122185,
        "effect_status": "descriptive_exploratory"
      },
      {
        "period": 2021,
        "split": "train",
        "observed_dates": 243,
        "mean_coverage": 0.7936373611291205,
        "mean_stocks": 4299.399176954733,
        "long_short_mean_gross": -0.0009407584624509365,
        "long_short_std_gross": 0.025137119196925642,
        "group_monotonicity": 0.06172839506172837,
        "factor_lag1": 0.9508564359119831,
        "rank_lag1": 0.9326920694654891,
        "ic_mean": -0.013815836943008952,
        "ic_median": -0.0069706654481253,
        "ic_std": 0.12665719400132572,
        "ic_ir": -0.10908055442049618,
        "ic_positive_ratio": 0.4732510288065844,
        "ic_n_dates": 243,
        "ic_status": "approximate",
        "ic_n_valid": 243,
        "ic_lags": 4,
        "ic_se": 0.014861192270280231,
        "ic_ci_low": -0.04294323856008244,
        "ic_ci_high": 0.015311564674064538,
        "ic_t_stat": -0.9296587172644415,
        "ic_p_value": 0.35254781545452485,
        "rank_ic_mean": -0.02857304093144349,
        "rank_ic_median": -0.0295132958094567,
        "rank_ic_std": 0.14081970940916538,
        "rank_ic_ir": -0.20290512635856772,
        "rank_ic_positive_ratio": 0.41975308641975306,
        "rank_ic_n_dates": 243,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 243,
        "rank_ic_lags": 4,
        "rank_ic_se": 0.016428105855977003,
        "rank_ic_ci_low": -0.06077153674336909,
        "rank_ic_ci_high": 0.0036254548804821075,
        "rank_ic_t_stat": -1.7392778681814873,
        "rank_ic_p_value": 0.08198589831533319,
        "effect_status": "descriptive_exploratory"
      },
      {
        "period": 2022,
        "split": "train",
        "observed_dates": 242,
        "mean_coverage": 0.8653998145178609,
        "mean_stocks": 4689.338842975207,
        "long_short_mean_gross": -0.0055463885122899155,
        "long_short_std_gross": 0.020595689255914845,
        "group_monotonicity": -0.09380165289256197,
        "factor_lag1": 0.9478585737404768,
        "rank_lag1": 0.9312381065934267,
        "ic_mean": -0.04807325891562718,
        "ic_median": -0.0356042092068811,
        "ic_std": 0.11079373492960103,
        "ic_ir": -0.43389871228886007,
        "ic_positive_ratio": 0.371900826446281,
        "ic_n_dates": 242,
        "ic_status": "approximate",
        "ic_n_valid": 242,
        "ic_lags": 4,
        "ic_se": 0.011676060639699289,
        "ic_ci_low": -0.07095791725074285,
        "ic_ci_high": -0.0251886005805115,
        "ic_t_stat": -4.117249849848783,
        "ic_p_value": 3.834203369246591e-05,
        "rank_ic_mean": -0.048365149758750205,
        "rank_ic_median": -0.043376818213521004,
        "rank_ic_std": 0.13564906896283802,
        "rank_ic_ir": -0.3565461239693445,
        "rank_ic_positive_ratio": 0.3884297520661157,
        "rank_ic_n_dates": 242,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 242,
        "rank_ic_lags": 4,
        "rank_ic_se": 0.01489335763690243,
        "rank_ic_ci_low": -0.07755559433595273,
        "rank_ic_ci_high": -0.01917470518154768,
        "rank_ic_t_stat": -3.2474308975775963,
        "rank_ic_p_value": 0.0011645193841659867,
        "effect_status": "descriptive_exploratory"
      },
      {
        "period": 2023,
        "split": "train",
        "observed_dates": 242,
        "mean_coverage": 0.915862225450647,
        "mean_stocks": 4962.800847457627,
        "long_short_mean_gross": -0.00445761191711063,
        "long_short_std_gross": 0.016581868658155998,
        "group_monotonicity": -0.11652542372881354,
        "factor_lag1": 0.9444300023548887,
        "rank_lag1": 0.9227892778634509,
        "ic_mean": -0.03823049636987779,
        "ic_median": -0.041903614110545856,
        "ic_std": 0.11169935313083895,
        "ic_ir": -0.3422624688353972,
        "ic_positive_ratio": 0.3474576271186441,
        "ic_n_dates": 236,
        "ic_status": "approximate",
        "ic_n_valid": 236,
        "ic_lags": 4,
        "ic_se": 0.012798721922259315,
        "ic_ci_low": -0.0633155303856486,
        "ic_ci_high": -0.013145462354106976,
        "ic_t_stat": -2.9870557858896816,
        "ic_p_value": 0.002816783176308443,
        "rank_ic_mean": -0.04693166299296845,
        "rank_ic_median": -0.0529471728538467,
        "rank_ic_std": 0.1155206380484814,
        "rank_ic_ir": -0.40626215181803527,
        "rank_ic_positive_ratio": 0.3305084745762712,
        "rank_ic_n_dates": 236,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 236,
        "rank_ic_lags": 4,
        "rank_ic_se": 0.012753856697684748,
        "rank_ic_ci_low": -0.07192876278441482,
        "rank_ic_ci_high": -0.021934563201522084,
        "rank_ic_t_stat": -3.6798016557209805,
        "rank_ic_p_value": 0.00023341543140659388,
        "effect_status": "descriptive_exploratory"
      },
      {
        "period": 2024,
        "split": "valid",
        "observed_dates": 242,
        "mean_coverage": 0.9364312505425123,
        "mean_stocks": 5076.202479338843,
        "long_short_mean_gross": -0.008647822578783585,
        "long_short_std_gross": 0.04235008481302004,
        "group_monotonicity": -0.14421487603305783,
        "factor_lag1": 0.9457948817821057,
        "rank_lag1": 0.9267393420794768,
        "ic_mean": -0.057059500573634375,
        "ic_median": -0.04947475533430955,
        "ic_std": 0.16096258564036145,
        "ic_ir": -0.35448921466211014,
        "ic_positive_ratio": 0.30578512396694213,
        "ic_n_dates": 242,
        "ic_status": "approximate",
        "ic_n_valid": 242,
        "ic_lags": 4,
        "ic_se": 0.017945551919242585,
        "ic_ci_low": -0.09223213601804252,
        "ic_ci_high": -0.021886865129226232,
        "ic_t_stat": -3.1795901753487357,
        "ic_p_value": 0.0014748347327183731,
        "rank_ic_mean": -0.06645323744461597,
        "rank_ic_median": -0.05955054785957825,
        "rank_ic_std": 0.2047418205933117,
        "rank_ic_ir": -0.324570902280952,
        "rank_ic_positive_ratio": 0.32644628099173556,
        "rank_ic_n_dates": 242,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 242,
        "rank_ic_lags": 4,
        "rank_ic_se": 0.022673411506898243,
        "rank_ic_ci_low": -0.11089230740479133,
        "rank_ic_ci_high": -0.0220141674844406,
        "rank_ic_t_stat": -2.9308883413683904,
        "rank_ic_p_value": 0.00337994244306029,
        "effect_status": "descriptive_exploratory"
      },
      {
        "period": 2025,
        "split": "valid",
        "observed_dates": 243,
        "mean_coverage": 0.9428797181596968,
        "mean_stocks": 5107.0843881856545,
        "long_short_mean_gross": -0.004917022543260036,
        "long_short_std_gross": 0.02056348732777388,
        "group_monotonicity": -0.08691983122362867,
        "factor_lag1": 0.9486550609963577,
        "rank_lag1": 0.9248761806119296,
        "ic_mean": -0.03494619081101457,
        "ic_median": -0.0317866672512386,
        "ic_std": 0.11627069576268087,
        "ic_ir": -0.3005588861560005,
        "ic_positive_ratio": 0.39662447257383965,
        "ic_n_dates": 237,
        "ic_status": "approximate",
        "ic_n_valid": 237,
        "ic_lags": 4,
        "ic_se": 0.012810393848115368,
        "ic_ci_low": -0.060054101381093475,
        "ic_ci_high": -0.009838280240935669,
        "ic_t_stat": -2.7279560039565656,
        "ic_p_value": 0.00637281071352614,
        "rank_ic_mean": -0.0756008953061953,
        "rank_ic_median": -0.0662499789201644,
        "rank_ic_std": 0.13370520733626895,
        "rank_ic_ir": -0.5654297002513811,
        "rank_ic_positive_ratio": 0.25738396624472576,
        "rank_ic_n_dates": 237,
        "rank_ic_status": "approximate",
        "rank_ic_n_valid": 237,
        "rank_ic_lags": 4,
        "rank_ic_se": 0.014478113517383331,
        "rank_ic_ci_low": -0.10397747636434837,
        "rank_ic_ci_high": -0.047224314248042236,
        "rank_ic_t_stat": -5.221736603696616,
        "rank_ic_p_value": 1.7725296827196923e-07,
        "effect_status": "descriptive_exploratory"
      }
    ],
    "monthly_rows": 72,
    "quality": {
      "data_status": "PROFILED_EXPLORATORY_ONLY",
      "invalid_cross_sections": 32,
      "n_observed_dates": 1455,
      "mean_coverage": 0.8510831359303773,
      "monthly_positive_share": 0.08450704225352113,
      "worst_month": "2024-02",
      "longest_nonpositive_month_streak": 23,
      "constant_or_unavailable_days": 0
    },
    "verdict": {
      "status": "REJECTED",
      "evidence": [
        "Train / Validation RankIC：-0.0391 / -0.0710。",
        "与Train方向一致的年度：6/6。",
        "HAC区间均不跨0。",
        "正RankIC月份占比：8.5%；最长非正月份连续23个月。",
        "Validation因子覆盖率：94.0%；高低组理论毛收益差：-0.680%；日度单调性均值：-0.116。",
        "预先冻结的高分看多方向不获支持；反向定义需新实验，不能事后翻转方向冒充成功。",
        "原始未复权收益、未认证历史股票池及已曝光Validation限制证据强度；不构成可交易结论。"
      ],
      "tradable": false,
      "policy_version": "evidence-verdict/1",
      "data_status": "PROFILED_EXPLORATORY_ONLY",
      "selection_bias": "validation exposed; no multiple-experiment selection correction",
      "threshold_disclosure": "n>=60; annual directional support>=60%; coverage>=50%; HAC CI excludes0; no IC size cutoff"
    },
    "files": {
      "evaluation_daily.csv": {
        "path": "data/evaluation_daily.csv",
        "sha256": "7b6d6ea6cdcae8cb02a1a9ee1712c87773cee080e73957bbc56b9e7fce5030c2"
      },
      "evaluation_annual.csv": {
        "path": "data/evaluation_annual.csv",
        "sha256": "15879c276214126b7fe74d531e717b19189cb1e2fe0f03acb18024accde34f69"
      },
      "evaluation_monthly.csv": {
        "path": "data/evaluation_monthly.csv",
        "sha256": "958beb65de33d3cfff6b07c7f0a41411675e7a35c45204e0d5d6719352a27274"
      },
      "evaluation_partitions.csv": {
        "path": "data/evaluation_partitions.csv",
        "sha256": "359d900ffa8284f5480e842d3977873ae34cde86b2acc44d9165f1468e5931dd"
      },
      "evaluation_extreme_dates.csv": {
        "path": "data/evaluation_extreme_dates.csv",
        "sha256": "cf4ac31c310eb38f7a7af584dfdd72cc46a4db211ed5f14e4720a52dc41b13b2"
      },
      "evaluation_sensitivity.csv": {
        "path": "data/evaluation_sensitivity.csv",
        "sha256": "d878652588b56ec623eff4d687749a2e5a6e8fe502ee2e8c278a9b8206ab5202"
      },
      "evaluation_coverage_buckets.csv": {
        "path": "data/evaluation_coverage_buckets.csv",
        "sha256": "7fd92264898bc85d674ce59d4a2b2cb9320ac237cef33f70c85caab491757074"
      }
    },
    "definitions": {
      "ir": "mean/sample std, nonannualized",
      "inference": "Bartlett HAC, B=max(H-1,floor(4*(n/100)^(2/9))); min60 and10*(B+1); trim edge missing only; interior gaps rejected; asymptotic normal two-sided p/95% CI; no multiple-testing adjustment",
      "month_status": "<60 valid dates => insufficient; no monthly significance assertion",
      "annual_and_monthly": "group each signal-date daily result; labels can cross year/month within same authorized partition; partition boundary purged",
      "sensitivity": "fixed robust z>5 removal; undefined MAD=0 left unchanged; descriptive only, no factor selection",
      "cumulative_ic": "arithmetic sum of correlations, not investment NAV",
      "long_short": "G0 minus last group, overlapping future raw-open gross labels, not tradable returns",
      "calendar": "consecutive observed sessions assumed equally spaced; exchange/PIT calendar not certified"
    },
    "elapsed_seconds": 4.108,
    "evaluation_fingerprint": "2595d2da3517c287c137f18dc342df8aaa2a205901ab17813ff9522538c5d5e1"
  },
  "interactive_report": {
    "version": "interactive-report/1.0.0",
    "plotly_sha256": "0a17719a72751704861215da0e5c5cdb3f9a8d50eff5cb84cb6f8b80786682b0"
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

!rank_ic_monthly_heatmap（原内部附件未公开）

!ic_monthly_heatmap（原内部附件未公开）

!interactive_ic_timeline（原内部附件未公开）

!interactive_rank_ic_timeline（原内部附件未公开）

!interactive_cumulative_correlation（原内部附件未公开）

!interactive_interactive_decay（原内部附件未公开）

!interactive_coverage_timeline（原内部附件未公开）

!interactive_theoretical_groups（原内部附件未公开）