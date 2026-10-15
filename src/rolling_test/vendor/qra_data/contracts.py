"""Versioned data contracts, field dictionaries and certification levels for Phase 3-A.

Every statement here is tied to an evidence id under survey/results/. Field status is one of:
VERIFIED (numerically checked), PARTIAL (checked for a sub-range or with a known defect), UNVERIFIED (exists, not
checked), REJECTED (checked and unfit for the stated use).
"""
from dataclasses import asdict, dataclass, field
from enum import IntEnum
import json

CONTRACT_VERSION = "qra-data-contract/1.0.0"


class Level(IntEnum):
    """Certification ladder. A level is always scoped to (resource, fields, date range, universe)."""
    NONE = 0
    DISCOVERED = 1          # file exists: path, size, sha256 recorded
    PROFILED = 2            # axes, dtypes, ranges and basic quality decoded
    RESEARCH_READY = 3      # quality + time alignment verified for the scope; usable for historical factor research
    BACKTEST_CANDIDATE = 4  # meets the candidate backtest data contract; waits for joint engine acceptance
    BACKTEST_APPROVED = 5   # data + a specific execution contract jointly accepted (never granted by this package)


LEVEL_REQUIREMENTS = {
    Level.DISCOVERED: ["file_exists", "sha256_recorded"],
    Level.PROFILED: ["axes_decoded_without_execution", "dtypes_known", "coverage_measured"],
    Level.RESEARCH_READY: ["unique_keys", "ohlc_constraints", "units_verified", "calendar_matches_exchange",
                           "adjustment_consistent", "cross_source_agreement", "delisted_codes_retained",
                           "field_time_semantics_declared", "frozen_or_filled_segments_excluded", "version_pinned"],
    Level.BACKTEST_CANDIDATE: ["exchange_suspension_status_pit", "exchange_limit_prices_pit", "st_status_pit",
                               "listing_delisting_dates_complete", "corporate_action_event_table",
                               "availability_timestamps", "complete_universe_incl_new_listings",
                               "execution_price_fields_defined"],
    Level.BACKTEST_APPROVED: ["joint_acceptance_with_backtest_engine", "execution_contract_signed_off"],
}


@dataclass(frozen=True)
class Field:
    name: str
    dtype: str
    unit: str
    basis: str            # raw | hfq | derived | status | shifted_future | shifted_past | mixed
    time: str             # when the value is known
    source: str
    status: str           # VERIFIED | PARTIAL | UNVERIFIED | REJECTED
    evidence: str
    notes: str = ""
    signal_use: bool = True   # False: must never be a factor input at T (future or unreliable)


DAILY_UPDATE_FIELDS = [
    Field("open", "float64", "CNY/share", "raw", "T open", "Tushare daily.open", "VERIFIED",
          "daily_update_checks.json#cross_csv.fields.Opnprc", "Exact match with published CSV on 65 overlap days"),
    Field("high", "float64", "CNY/share", "raw", "T close", "Tushare daily.high", "VERIFIED", "daily_update_checks.json#ohlc"),
    Field("low", "float64", "CNY/share", "raw", "T close", "Tushare daily.low", "VERIFIED", "daily_update_checks.json#ohlc"),
    Field("close", "float64", "CNY/share", "raw", "T close", "Tushare daily.close", "VERIFIED",
          "daily_update_checks.json#cross_csv; cross_source_checks.json#eod_vs_daily_close",
          "Equal to research EOD close on 8,518,112 pairs and to CSV on 337,157 pairs"),
    Field("volume", "float64", "lots (100 shares)", "raw", "T close", "Tushare daily.vol", "VERIFIED",
          "daily_update_checks.json#unit_check_lots_thousand_cny",
          "NOT shares: CSV Dnshrtrd = volume*100; EOD vol = volume*100"),
    Field("amount", "float64", "thousand CNY", "raw", "T close", "Tushare daily.amount", "VERIFIED",
          "daily_update_checks.json#unit_check_lots_thousand_cny", "NOT CNY: CSV Dnvaltrd = amount*1000"),
    Field("adj_factor", "float64", "dimensionless", "hfq", "T (ex-date)", "Tushare adj_factor", "PARTIAL",
          "daily_update_checks.json#adjustment; cross_source_checks.json#adj_factor_steps; hfq_revision_probe.json",
          "Cumulative backward factor (min 1.0). 19,465 of 47,587 steps are <1e-3 rounding noise; 3 large decreases; "
          "history was rebuilt after 2026-07-24 (snapshots differ)"),
    Field("open_adj", "float64", "CNY/share x factor", "hfq", "T open", "open*adj_factor", "VERIFIED",
          "producer source line 531", "Backward-adjusted: not a tradable price"),
    Field("high_adj", "float64", "CNY/share x factor", "hfq", "T close", "high*adj_factor", "VERIFIED", "producer source line 531"),
    Field("low_adj", "float64", "CNY/share x factor", "hfq", "T close", "low*adj_factor", "VERIFIED", "producer source line 531"),
    Field("close_adj", "float64", "CNY/share x factor", "hfq", "T close", "close*adj_factor", "VERIFIED",
          "daily_update_checks.json#adjustment.close_adj_max_rel_err=0"),
    Field("vwap_adj", "float64", "CNY/share x factor", "hfq", "T close", "amount*10/volume*adj_factor", "VERIFIED",
          "daily_update_checks.json#adjustment.vwap_adj_max_rel_err=0"),
    Field("vwap", "float64", "CNY/share", "raw", "T close", "legacy", "REJECTED", "daily_update_static_meta.json",
          "Stale: ends 20260807", signal_use=False),
    Field("pre_close", "float64", "CNY/share", "shifted_past", "T-1 close", "close.shift(1)", "VERIFIED",
          "daily_update_checks.json#pre_close.equals_prior_row_close",
          "NOT the exchange pre-close: differs from it on every ex-date"),
    Field("next_open", "float64", "CNY/share", "shifted_future", "T+1 open", "open.shift(-1)", "VERIFIED",
          "producer source line 633", "Future value: execution use only, never a factor input", signal_use=False),
    Field("pre_close_adj", "float64", "CNY/share x factor", "shifted_past", "T-1 close", "close_adj.shift(1)", "VERIFIED", "producer source line 624"),
    Field("next_open_adj", "float64", "CNY/share x factor", "shifted_future", "T+1 open", "open_adj.shift(-1)", "VERIFIED",
          "producer source line 625", "Future value", signal_use=False),
    Field("turnover", "float64", "percent", "raw", "T close", "Tushare daily_basic.turnover_rate", "UNVERIFIED", "daily_update_static_meta.json"),
    Field("total_mkt_cap", "float64", "ten-thousand CNY", "raw", "T close", "Tushare daily_basic.total_mv", "UNVERIFIED",
          "producer source line 547", "Tushare unit; CSV Dsmvtll is x10 (thousand CNY)"),
    Field("float_mkt_cap", "float64", "ten-thousand CNY", "raw", "T close", "Tushare daily_basic.circ_mv", "UNVERIFIED", "producer source line 547"),
    Field("is_valid_trading", "bool", "flag", "status", "T close", "has positive OHLCV", "PARTIAL",
          "daily_update_checks.json#status; daily_update_static_meta.json",
          "Equals 'has a close' before 2026-05-22; frozen (forward-filled) from 2026-05-22", signal_use=False),
    Field("is_valid_suspension", "bool", "flag", "status", "T", "suspend_d + 60-day cooldown rule", "REJECTED",
          "producer source lines 271-316, 638-676; daily_update_static_meta.json",
          "Eligibility rule, not suspension; frozen from 2026-05-22", signal_use=False),
    Field("is_valid_list", "bool", "flag", "status", "T", "stock_basic list/delist", "REJECTED",
          "daily_update_checks.json#status.close_but_not_listed_pre_freeze=224592", "Not a listing flag; frozen from 2026-05-22",
          signal_use=False),
    Field("is_valid_not_st", "bool", "flag", "status", "T", "stock_st", "PARTIAL", "daily_update_checks.json#status",
          "Plausible ST shares 2019-2025; frozen from 2026-05-21; history PIT not proven", signal_use=False),
    Field("sw_industry_class", "object", "code", "status", "unknown", "unknown", "UNVERIFIED", "daily_update_static_meta.json",
          "Forward-filled by design; not decoded", signal_use=False),
]

RESEARCH_EOD_FIELDS = [
    Field("open/high/low/close", "float64", "CNY/share", "raw", "T close", "historical build + Tushare", "PARTIAL",
          "cross_source_checks.json#eod_vs_daily_close", "Raw; equals daily_update; suspended days carry the last close"),
    Field("vol", "float64", "shares", "raw", "T close", "Tushare vol*100", "VERIFIED", "cross_source_checks.json#eod_vs_daily_vol"),
    Field("amount", "float64", "CNY", "raw", "T close", "Tushare amount*1000", "VERIFIED", "cross_source_checks.json#eod_vs_daily_amount"),
    Field("trade_status", "bool", "flag", "status", "T", "unknown producer", "PARTIAL", "cross_source_checks.json#eod_trade_status",
          "0 on 511,856 cells that still carry a (filled) close"),
    Field("limit_status", "float64", "-1/0/1", "status", "T close", "unknown producer", "UNVERIFIED", "cross_source_checks.json#eod_limit_status"),
    Field("limit_up_price/limit_down_price", "float64", "CNY/share", "derived", "T", "board-ratio heuristic", "REJECTED",
          "cross_source_checks.json#eod_limit_up.close_above_limit_up=13079", "Not exchange limit prices", signal_use=False),
    Field("ST", "bool", "flag", "status", "unknown", "current names", "REJECTED", "cross_source_checks.json#eod_ST",
          "0.1% ST in 2016 vs ~3-4% actual: not point-in-time", signal_use=False),
    Field("minute_* (100)", "float32", "various", "derived", "T close", "stk_mins aggregates", "UNVERIFIED",
          "pit_checks.json#eod_field_coverage_share_per_year"),
    Field("moneyflow (18)", "float64", "shares / CNY", "raw", "T close", "Tushare moneyflow", "UNVERIFIED",
          "pit_checks.json#eod_field_coverage_share_per_year"),
]


@dataclass
class ResourceContract:
    id: str
    path: str
    format: str
    sha256: str
    bytes: int
    dates: tuple
    codes: int
    fields: list
    certification: dict = field(default_factory=dict)   # scope name -> {"level": Level name, "failed": [...]}
    limits: list = field(default_factory=list)


def field_dictionary():
    return {"contract_version": CONTRACT_VERSION,
            "daily_update": [asdict(f) for f in DAILY_UPDATE_FIELDS],
            "research_eod": [asdict(f) for f in RESEARCH_EOD_FIELDS],
            "levels": {lvl.name: reqs for lvl, reqs in LEVEL_REQUIREMENTS.items()}}


def dumps():
    return json.dumps(field_dictionary(), ensure_ascii=False, indent=1)
