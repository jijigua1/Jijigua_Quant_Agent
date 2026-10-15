"""Representative factor documents with known ground truth (synthetic test documents).

Each document restates a widely known factor methodology in our own words for testing; every number in them is
invented for the test and is NOT a result of the cited literature. EXPECTED records what a correct extraction
should find, so acceptance can be scored against it.
"""
from __future__ import annotations

from pathlib import Path

WEEK52 = r"""# Nearness to the 52-Week High (synthetic test document)

*This is a synthetic test document. It paraphrases a well-known methodology; every number below is invented for
testing and is not taken from any published paper.*

## Abstract

We examine whether stocks trading close to their 52-week high earn higher subsequent returns. The intuition is that
investors anchor on the 52-week high and underreact to good news, so prices near the high adjust slowly.

## Data

We use daily closing prices of all A-share common stocks listed on the Shanghai and Shenzhen exchanges. Prices are
backward-adjusted for splits and dividends. We exclude ST stocks and stocks listed for fewer than 252 trading days.

## Factor construction

The 52-week-high ratio (PTH) is defined as the current price divided by the highest price over the past 252 trading days.

$$PTH_{i,t} = \frac{P_{i,t}}{\max_{0 \le k \le 251} P_{i,t-k}} \tag{1}$$

where $P_{i,t}$ is the backward-adjusted closing price of stock i on day t.

The signal is computed at the close of day t and positions are opened at the next day's open.
We predict the cumulative return over the next 20 trading days.

## Preprocessing

Each day the factor is winsorized at the 1st and 99th percentiles, standardized to z-scores, and neutralized
with respect to industry and size.

## Evaluation

The training period is 2010-2016, the validation period is 2017-2018 and the out-of-sample test period is 2019-2021.
We report the information coefficient (IC), rank IC and the Sharpe ratio of a long-short quintile portfolio.

## Results

The average rank IC is 0.041 with a t-statistic of 3.85 in the test period.
The annualized long-short return is 7.2% in the test period.

## Limitations

A limitation is that we do not model transaction costs or price limits.
"""

WEEK52_EXPECTED = {
    "factor": "PTH", "formula_status": "extracted", "dsl_status": "requires_new_implementation", "dsl_reason": "UNSUPPORTED_OPERATOR",
    "fields": {"research_objective", "economic_intuition", "frequency", "lookback", "universe", "signal_timing",
               "holding_horizon", "preprocessing", "evaluation_design", "evaluation_metrics", "reported_results", "limitations",
               "sample_selection", "factor_definition"},
    "lookback": {"n": 252, "unit": "trading_day"}, "horizon": {"n": 20, "unit": "trading_day"},
    "preprocessing": {"winsorize", "standardize_zscore", "neutralize_industry", "neutralize_size"},
    "splits": {("in_sample", 2010, 2016), ("validation", 2017, 2018), ("out_of_sample", 2019, 2021)},
    "results": {"0.041", "3.85", "7.2%"}, "warmup": 252,
}

AMIHUD = r"""<!doctype html><html><head><title>Illiquidity and Returns (synthetic test document)</title>
<meta name="citation_title" content="Illiquidity and Returns (synthetic test document)"></head><body>
<h1>Illiquidity and Returns (synthetic test document)</h1>
<p><em>Synthetic test document paraphrasing a well-known illiquidity measure; numbers are invented for testing.</em></p>
<h2>1 Measure</h2>
<p>We investigate whether illiquid stocks earn a return premium as compensation for trading costs.</p>
<p>The illiquidity measure (ILLIQ) is defined as the average ratio of the absolute daily return to the daily
dollar trading volume over the past 21 trading days.</p>
<p>\[ ILLIQ_{i,t} = \frac{1}{21} \sum_{k=0}^{20} \frac{|R_{i,t-k}|}{DVOL_{i,t-k}} \]</p>
<p>where R_{i,t} is the daily return of stock i and DVOL_{i,t} is the dollar trading volume of stock i on day t.</p>
<h2>2 Data</h2>
<p>We use daily data for all listed stocks. We evaluate next month returns of decile portfolios.</p>
</body></html>
"""

AMIHUD_EXPECTED = {
    "factor": "ILLIQ", "dsl_status": "requires_new_implementation", "dsl_reason": "FIELD_NOT_IN_DSL",
    "missing": {"sample_periods", "signal_timing"}, "warmup": 21,
}

REVERSAL_ZH = r"""# 五日反转因子研究（合成测试文档）

> 本文档为合成测试文档，复述常见的短期反转因子方法；文中数字均为测试编造，不来自任何已发表研究。

## 研究目标

本文研究A股短期反转效应，检验过去一周涨幅较大的股票在随后是否回落。逻辑在于投资者对短期信息过度反应。

## 数据

样本为沪深A股，使用日频后复权收盘价。剔除ST股票和上市不足60个交易日的股票。

## 因子定义

五日反转因子（REV5）定义为过去5个交易日收益率的相反数。

$$REV5_{i,t} = -\left(\frac{P_{i,t}}{P_{i,t-5}} - 1\right)$$

其中 P 表示后复权收盘价。

信号在每个交易日收盘后计算，预测未来5个交易日的收益。

## 样本划分

训练集为2015-2018年，验证集为2019-2020年，样本外测试为2021-2022年。

## 结果

样本外 RankIC 均值为 0.032。
"""

REVERSAL_EXPECTED = {"factor": "REV5", "dsl_status": "expressible", "warmup": 6,
                     "splits": {("in_sample", 2015, 2018), ("validation", 2019, 2020), ("out_of_sample", 2021, 2022)}}


def week52_markdown(path) -> Path:
    Path(path).write_text(WEEK52, encoding="utf-8")
    return Path(path)


def amihud_html(path) -> Path:
    Path(path).write_text(AMIHUD, encoding="utf-8")
    return Path(path)


def reversal_markdown_zh(path) -> Path:
    Path(path).write_text(REVERSAL_ZH, encoding="utf-8")
    return Path(path)
