"""Central configuration for the Bullish / Bearish Three-Condition Stock Screener.

The strategy is based on Big Red Attack / Big Black Attack lines.

This tool is for stock research and screening only. It is NOT investment advice.
"""

from __future__ import annotations

from datetime import date, timedelta

APP_TITLE = "Bullish / Bearish Three-Condition Stock Screener"
APP_DISCLAIMER = (
    "This tool is for stock research and screening only. It is NOT investment advice."
)

# Default stock universe used when the user provides no input.
DEFAULT_STOCK_LIST = [
    "2330.TW",
    "2317.TW",
    "2382.TW",
    "2474.TW",
    "6182.TWO",
]
DEFAULT_TEXT_STOCK_LIST = "\n".join(DEFAULT_STOCK_LIST)

# Strategy defaults (kept intentionally minimal — no extra strategy parameters).
DEFAULT_MIN_VOLUME = 2000
DEFAULT_LOOKBACK_BARS = 10

# UI label -> internal timeframe code. Timeframe column uses the codes D / W / M.
TIMEFRAME_OPTIONS = {
    "Daily K": "D",
    "Weekly K": "W",
    "Monthly K": "M",
}
TIMEFRAME_LABELS = {code: label for label, code in TIMEFRAME_OPTIONS.items()}
DEFAULT_TIMEFRAME_LABEL = "Daily K"

# Signal direction filter options.
DIRECTION_BOTH = "Both"
DIRECTION_BULLISH = "Bullish only"
DIRECTION_BEARISH = "Bearish only"
DIRECTION_OPTIONS = [DIRECTION_BOTH, DIRECTION_BULLISH, DIRECTION_BEARISH]

# Default date range: a ~1-year window ending today.
DEFAULT_START_DATE = date.today() - timedelta(days=365)
DEFAULT_END_DATE = date.today()

DEFAULT_PARAMETERS = {
    "start_date": DEFAULT_START_DATE,
    "end_date": DEFAULT_END_DATE,
    "analysis_timeframe": DEFAULT_TIMEFRAME_LABEL,
    "min_volume": DEFAULT_MIN_VOLUME,
    "lookback_bars": DEFAULT_LOOKBACK_BARS,
    "signal_direction_filter": DIRECTION_BOTH,
}

# Long-format OHLCV schema produced after normalization.
REQUIRED_OHLCV_COLUMNS = [
    "Date",
    "StockCode",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]

# Column order for the matching-signals result table (spec section 15.2).
RESULT_COLUMNS = [
    # Basic columns
    "Date",
    "Timeframe",
    "StockCode",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "prev_close",
    # Attack columns
    "red_attack_success",
    "red_attack_failed",
    "black_attack_success",
    "black_attack_failed",
    "attack_type",
    "attack_result",
    "attack_direction",
    "signal_summary",
    # Line columns
    "red_line",
    "black_line",
    # Bullish columns
    "bull_A_window",
    "bull_B_window",
    "bull_C_window",
    "bull_score",
    "bull_signal",
    "final_bull_signal",
    # Bearish columns
    "bear_A_window",
    "bear_B_window",
    "bear_C_window",
    "bear_score",
    "bear_signal",
    "final_bear_signal",
    # Filter columns
    "volume_pass",
    "lookback_rank",
]

# Column order for the latest summary table (spec section 15.3).
SUMMARY_COLUMNS = [
    "StockCode",
    "LatestSignalDate",
    "Timeframe",
    "SignalDirection",
    "BullScore",
    "BearScore",
    "LatestOpen",
    "LatestHigh",
    "LatestLow",
    "LatestClose",
    "LatestVolume",
    "LatestSignalSummary",
]
