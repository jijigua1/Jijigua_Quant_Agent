"""qrtk: independent quantitative research toolkit.

Daily research mainline (factor_eval, diagnostics, backtest) plus minute-data support
(contract, minute, execution). Synthetic-data verified only; not validated on real market data.
"""
from .factor_eval import (assign_groups, choose_direction, coverage, cross_sectional_corr,
                          cumulative_returns, evaluate_factor, forward_returns, group_returns,
                          group_turnover, ic_summary, label_exit_dates, rank_autocorr, valid_mask)
from .backtest import (REJECTION_CATEGORY, BacktestResult, CostModel, MarketRules, run_backtest,
                       run_backtest_with_execution)
from .metrics import performance_metrics, reconcile
from .contract import (ContractError, DailyBarContract, MinuteBarContract, SessionConfig,
                       normalize_daily_bars, normalize_minute_bars, to_panel)
from .minute import aggregate_daily, window_bars, window_stats
from .execution import (FIRST_VALID_MINUTE, NEXT_OPEN, VWAP_5, VWAP_15, VWAP_30, ExecutionPrices,
                        ExecutionRule, build_execution_prices, window_vwap_rule)
from .diagnostics import (ResearchSpec, coverage_stability, evaluate_splits, factor_distribution,
                          monotonicity, multi_horizon, period_summary)

__version__ = "0.2.0"
