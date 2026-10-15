"""Independent reconciliation and performance metrics for a BacktestResult."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def reconcile(result, atol: float = 1e-6) -> dict:
    """Rebuild cash, shares, market value and equity from the trade list and compare.

    Uses only trades, positions (for marks) and the initial state, not the ledger's running
    variables. Returns max absolute differences and an overall ok flag."""
    daily, trades, pos = result.daily, result.trades, result.positions
    idx = daily.index
    flow = trades.groupby("date")["cash_flow"].sum().reindex(idx, fill_value=0.0)
    cash = result.initial_cash + flow.cumsum()
    q = trades.assign(q=np.where(trades["side"] == "buy", trades["shares"], -trades["shares"]))
    codes = sorted(set(q["code"]) | set(result.initial_positions) | set(pos["code"]))
    delta = (q.pivot_table(index="date", columns="code", values="q", aggfunc="sum")
             .reindex(index=idx, columns=codes).fillna(0).cumsum())
    start = pd.Series(result.initial_positions, dtype=float).reindex(codes).fillna(0)
    shares = delta + start
    ledger_shares = (pos.pivot_table(index="date", columns="code", values="shares", aggfunc="sum")
                     .reindex(index=idx, columns=codes).fillna(0))
    marks = pos.pivot_table(index="date", columns="code", values="mark_price", aggfunc="first").reindex(index=idx, columns=codes)
    mv = (shares * marks.fillna(0)).sum(axis=1)
    out = {
        "cash_diff": float((cash - daily["cash"]).abs().max()),
        "shares_diff": float((shares - ledger_shares).abs().to_numpy().max()) if len(codes) else 0.0,
        "market_value_diff": float((mv - daily["market_value"]).abs().max()),
        "equity_diff": float((cash + mv - daily["equity"]).abs().max()),
        "fees_diff": float(((trades["commission"] + trades["stamp_duty"]).groupby(trades["date"]).sum()
                            .reindex(idx, fill_value=0.0) - daily["fees"]).abs().max()),
        "min_cash": float(daily["cash"].min()),
        "min_shares": float(shares.to_numpy().min()) if len(codes) else 0.0,
    }
    out["ok"] = (max(out["cash_diff"], out["shares_diff"], out["market_value_diff"], out["equity_diff"],
                     out["fees_diff"]) <= atol and out["min_cash"] >= -atol and out["min_shares"] >= 0)
    return out


def performance_metrics(result, periods_per_year: int = 252, rf_annual: float = 0.0) -> dict:
    """Account metrics from the NAV path (initial equity prepended as NAV = 1).

    cumulative_return  NAV_end - 1
    annual_return      NAV_end ** (P / N) - 1          (geometric; N = number of daily returns)
    annual_volatility  std(r, ddof=1) * sqrt(P)
    sharpe             mean(r - rf_d) / std(r - rf_d, ddof=1) * sqrt(P), rf_d = (1+rf)^(1/P) - 1
    max_drawdown       min(NAV / running_max(NAV) - 1)
    turnover           mean over days of (buy_amount + sell_amount) / 2 / previous equity
    total_fees, fee_ratio = total_fees / initial equity
    Undefined values (fewer than 2 returns, zero volatility) are NaN, never 0. Valid only for
    the simulated account under the listed assumptions; not a live-trading result."""
    d = result.daily
    nav = pd.concat([pd.Series([1.0]), (d["equity"] / result.initial_equity).reset_index(drop=True)],
                    ignore_index=True)
    r = nav.pct_change().iloc[1:]
    n = len(r)
    rf_d = (1 + rf_annual) ** (1 / periods_per_year) - 1
    ex = r - rf_d
    vol = r.std(ddof=1) if n > 1 else np.nan
    ex_sd = ex.std(ddof=1) if n > 1 else np.nan
    prev_eq = pd.concat([pd.Series([result.initial_equity]), d["equity"].iloc[:-1].reset_index(drop=True)],
                        ignore_index=True)
    turn = ((d["buy_amount"] + d["sell_amount"]).reset_index(drop=True) / 2 / prev_eq)
    fees = float(d["fees"].sum())
    return {
        "n_days": n,
        "cumulative_return": float(nav.iloc[-1] - 1),
        "annual_return": float(nav.iloc[-1] ** (periods_per_year / n) - 1) if n else np.nan,
        "annual_volatility": float(vol * math.sqrt(periods_per_year)) if n > 1 else np.nan,
        "sharpe": float(ex.mean() / ex_sd * math.sqrt(periods_per_year)) if n > 1 and ex_sd > 0 else np.nan,
        "max_drawdown": float((nav / nav.cummax() - 1).min()),
        "turnover": float(turn.mean()) if n else np.nan,
        "total_fees": fees,
        "fee_ratio": fees / result.initial_equity,
    }
