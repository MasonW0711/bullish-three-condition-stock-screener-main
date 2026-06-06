"""Signal calculation engine for the Bullish / Bearish Three-Condition Method.

Core attack logic
-----------------
prev_close = previous K-bar close (per StockCode).

The attack DIRECTION is determined ONLY by Open vs prev_close.
The Close ONLY decides whether the attack succeeded or failed.
A failed attack NEVER converts into the opposite-side attack.

    red_attack_success   = Open > prev_close AND Close > prev_close
    red_attack_failed    = Open > prev_close AND Close < prev_close   (NOT a black attack)
    black_attack_success = Open < prev_close AND Close < prev_close
    black_attack_failed  = Open < prev_close AND Close > prev_close   (NOT a red attack)

Lines
-----
red_line   is created ONLY by Big Red Attack Success  (red_line_raw   = prev_close, then ffill).
black_line is created ONLY by Big Black Attack Success (black_line_raw = prev_close, then ffill).
Failed attacks never create or update the opposite line.

Three-Condition Methods (within the recent lookback_bars window)
----------------------------------------------------------------
Bullish — at least 2 of:
    A. Big Red Attack Success appears.
    B. Break above the latest black_line:
         previous Close <= previous black_line AND current Close > current black_line
    C. Retest red_line or black_line as support and hold:
         Low <= line_price AND Close >= line_price

Bearish — at least 2 of:
    A. Big Black Attack Success appears.
    B. Break below the latest red_line:
         previous Close >= previous red_line AND current Close < current red_line
    C. Retest red_line or black_line as resistance and fail:
         High >= line_price AND Close <= line_price

A / B / C are calculated independently (no if/elif mutual exclusion); they do not
need to appear in order, be consecutive, or appear on separate K-bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _ensure_sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy sorted by StockCode then Date — required for shift/ffill/rolling."""
    return df.sort_values(["StockCode", "Date"]).reset_index(drop=True)


def add_prev_close(df: pd.DataFrame) -> pd.DataFrame:
    """Add prev_close = previous K-bar close, computed separately per StockCode."""
    output = _ensure_sorted(df)
    output["prev_close"] = output.groupby("StockCode")["Close"].shift(1)
    return output


def add_attack_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Detect Big Red / Big Black attack signals using explicit, independent masks.

    Each of the four signals is an independent boolean mask. There is NO if/elif
    logic, so a failed attack can never be reclassified as the opposite attack.
    """
    output = df.copy()

    prev_close = output["prev_close"]
    has_prev = prev_close.notna()
    opens_above = output["Open"] > prev_close
    opens_below = output["Open"] < prev_close
    closes_above = output["Close"] > prev_close
    closes_below = output["Close"] < prev_close

    # Independent boolean masks — Open decides direction, Close decides success/failure.
    output["red_attack_success"] = has_prev & opens_above & closes_above
    output["red_attack_failed"] = has_prev & opens_above & closes_below
    output["black_attack_success"] = has_prev & opens_below & closes_below
    output["black_attack_failed"] = has_prev & opens_below & closes_above

    # attack_type / attack_direction come from Open only (the attack attempt direction).
    output["attack_type"] = np.select(
        [has_prev & opens_above, has_prev & opens_below],
        ["Big Red Attack", "Big Black Attack"],
        default="No Attack",
    )
    output["attack_direction"] = np.select(
        [has_prev & opens_above, has_prev & opens_below],
        ["Bullish", "Bearish"],
        default="None",
    )
    output["attack_result"] = np.select(
        [
            output["red_attack_success"] | output["black_attack_success"],
            output["red_attack_failed"] | output["black_attack_failed"],
        ],
        ["Success", "Failed"],
        default="None",
    )
    output["signal_summary"] = np.select(
        [
            output["red_attack_success"],
            output["red_attack_failed"],
            output["black_attack_success"],
            output["black_attack_failed"],
        ],
        [
            "Big Red Attack Success",
            "Big Red Attack Failed",
            "Big Black Attack Success",
            "Big Black Attack Failed",
        ],
        default="No Attack",
    )
    return output


def add_attack_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Create red_line and black_line, each from its own success signal only.

    red_line_raw   = prev_close where red_attack_success   else NaN, ffill per stock.
    black_line_raw = prev_close where black_attack_success else NaN, ffill per stock.

    Failed attacks never create or update the opposite line.
    """
    output = df.copy()

    output["red_line_raw"] = np.where(
        output["red_attack_success"], output["prev_close"], np.nan
    )
    output["black_line_raw"] = np.where(
        output["black_attack_success"], output["prev_close"], np.nan
    )

    output["red_line"] = output.groupby("StockCode")["red_line_raw"].transform("ffill")
    output["black_line"] = output.groupby("StockCode")["black_line_raw"].transform("ffill")
    return output


def _rolling_any(df: pd.DataFrame, column: str, lookback_bars: int) -> pd.Series:
    """True if `column` was True in ANY of the last lookback_bars rows, per StockCode."""
    return df.groupby("StockCode")[column].transform(
        lambda x: x.astype(float).rolling(lookback_bars, min_periods=1).max() > 0
    )


def add_bullish_three_conditions(df: pd.DataFrame, lookback_bars: int) -> pd.DataFrame:
    """Compute Bullish Three-Condition columns A / B / C, their windows and score."""
    output = df.copy()
    grouped = output.groupby("StockCode")

    prev_close = grouped["Close"].shift(1)
    prev_black_line = grouped["black_line"].shift(1)

    red_line = output["red_line"]
    black_line = output["black_line"]

    # A: Big Red Attack Success appears.
    output["bull_A_daily"] = output["red_attack_success"].astype(bool)

    # B: break above the latest black_line. NaN black_line -> False.
    output["bull_B_break_black_daily"] = (
        prev_black_line.notna()
        & black_line.notna()
        & (prev_close <= prev_black_line)
        & (output["Close"] > black_line)
    ).fillna(False)

    # C: retest red_line / black_line as support and hold. NaN line -> False.
    output["bull_C_retest_red_line_daily"] = (
        red_line.notna() & (output["Low"] <= red_line) & (output["Close"] >= red_line)
    ).fillna(False)
    output["bull_C_retest_black_line_daily"] = (
        black_line.notna() & (output["Low"] <= black_line) & (output["Close"] >= black_line)
    ).fillna(False)
    output["bull_C_retest_support_daily"] = (
        output["bull_C_retest_red_line_daily"] | output["bull_C_retest_black_line_daily"]
    )

    # Rolling windows: did the daily condition appear in the last lookback_bars bars?
    output["bull_A_window"] = _rolling_any(output, "bull_A_daily", lookback_bars)
    output["bull_B_window"] = _rolling_any(output, "bull_B_break_black_daily", lookback_bars)
    output["bull_C_window"] = _rolling_any(output, "bull_C_retest_support_daily", lookback_bars)

    output["bull_score"] = (
        output["bull_A_window"].astype(int)
        + output["bull_B_window"].astype(int)
        + output["bull_C_window"].astype(int)
    )
    output["bull_signal"] = output["bull_score"] >= 2
    return output


def add_bearish_three_conditions(df: pd.DataFrame, lookback_bars: int) -> pd.DataFrame:
    """Compute Bearish Three-Condition columns A / B / C, their windows and score."""
    output = df.copy()
    grouped = output.groupby("StockCode")

    prev_close = grouped["Close"].shift(1)
    prev_red_line = grouped["red_line"].shift(1)

    red_line = output["red_line"]
    black_line = output["black_line"]

    # A: Big Black Attack Success appears.
    output["bear_A_daily"] = output["black_attack_success"].astype(bool)

    # B: break below the latest red_line. NaN red_line -> False.
    output["bear_B_break_red_daily"] = (
        prev_red_line.notna()
        & red_line.notna()
        & (prev_close >= prev_red_line)
        & (output["Close"] < red_line)
    ).fillna(False)

    # C: retest red_line / black_line as resistance and fail. NaN line -> False.
    output["bear_C_retest_red_line_daily"] = (
        red_line.notna() & (output["High"] >= red_line) & (output["Close"] <= red_line)
    ).fillna(False)
    output["bear_C_retest_black_line_daily"] = (
        black_line.notna() & (output["High"] >= black_line) & (output["Close"] <= black_line)
    ).fillna(False)
    output["bear_C_retest_resistance_daily"] = (
        output["bear_C_retest_red_line_daily"] | output["bear_C_retest_black_line_daily"]
    )

    output["bear_A_window"] = _rolling_any(output, "bear_A_daily", lookback_bars)
    output["bear_B_window"] = _rolling_any(output, "bear_B_break_red_daily", lookback_bars)
    output["bear_C_window"] = _rolling_any(output, "bear_C_retest_resistance_daily", lookback_bars)

    output["bear_score"] = (
        output["bear_A_window"].astype(int)
        + output["bear_B_window"].astype(int)
        + output["bear_C_window"].astype(int)
    )
    output["bear_signal"] = output["bear_score"] >= 2
    return output


def add_volume_filter(df: pd.DataFrame, min_volume: float) -> pd.DataFrame:
    """Apply the simple volume filter and derive the final bull/bear signals."""
    output = df.copy()
    volume = pd.to_numeric(output["Volume"], errors="coerce").fillna(0)
    output["volume_pass"] = volume >= min_volume
    output["final_bull_signal"] = output["bull_signal"] & output["volume_pass"]
    output["final_bear_signal"] = output["bear_signal"] & output["volume_pass"]
    return output


def add_lookback_rank(df: pd.DataFrame, lookback_bars: int) -> pd.DataFrame:
    """Rank bars from most recent (1) to oldest, per StockCode.

    in_lookback_window is True when lookback_rank <= lookback_bars, i.e. the bar is
    among the most recent lookback_bars K-bars for that stock.
    """
    output = _ensure_sorted(df)
    output["lookback_rank"] = output.groupby("StockCode").cumcount(ascending=False) + 1
    output["in_lookback_window"] = output["lookback_rank"] <= int(lookback_bars)
    return output


def run_signal_pipeline(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Run the full signal pipeline in the correct order.

    1. prev_close
    2. Attack signals (independent masks — no opposite-side conversion)
    3. Attack lines (red_line, black_line via forward-fill)
    4. Bullish three conditions
    5. Bearish three conditions
    6. Volume filter -> final signals
    7. Lookback rank / window flag
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    lookback_bars = max(int(params.get("lookback_bars", 10)), 1)
    min_volume = float(params.get("min_volume", 2000))

    output = add_prev_close(df)
    output = add_attack_signals(output)
    output = add_attack_lines(output)
    output = add_bullish_three_conditions(output, lookback_bars)
    output = add_bearish_three_conditions(output, lookback_bars)
    output = add_volume_filter(output, min_volume)
    output = add_lookback_rank(output, lookback_bars)
    return output.sort_values(["StockCode", "Date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 外資 / 投信 連續買入
# ---------------------------------------------------------------------------
_INVESTOR_COUNT_COLUMNS = ["foreign_buy_streak", "trust_buy_streak"]
_INVESTOR_FLAG_COLUMNS = ["foreign_buy_streak_ok", "trust_buy_streak_ok"]


def _consecutive_true_streak(mask: pd.Series) -> pd.Series:
    """Running count of consecutive True values, resetting to 0 on each False."""
    mask = mask.astype(bool)
    run_id = (~mask).cumsum()
    return mask.groupby(run_id).cumsum().astype(int)


def attach_investor_flow_flags(
    df: pd.DataFrame,
    investor_flow_df: pd.DataFrame,
    consecutive_days: int = 3,
) -> pd.DataFrame:
    """Attach 外資 / 投信 consecutive net-buy streaks and "達標" flags to each bar.

    Institutional net buy/sell is daily public data. The consecutive-buy streak is
    computed on the daily series per stock, then mapped to each K-bar using the
    latest daily record on or before that bar's Date (merge_asof, backward).

    foreign_buy_streak / trust_buy_streak : consecutive net-buy day count as of the bar.
    foreign_buy_streak_ok / trust_buy_streak_ok : streak >= consecutive_days.

    Always defensive: missing/empty flow data -> streak 0 and flag False, never crashes.
    """
    output = df.copy()
    consecutive_days = max(int(consecutive_days), 1)
    # Drop any pre-existing institutional columns so re-attaching is idempotent.
    output = output.drop(
        columns=[c for c in (_INVESTOR_COUNT_COLUMNS + _INVESTOR_FLAG_COLUMNS) if c in output.columns]
    )

    if output.empty:
        for col in _INVESTOR_COUNT_COLUMNS:
            output[col] = pd.Series(dtype=int)
        for col in _INVESTOR_FLAG_COLUMNS:
            output[col] = pd.Series(dtype=bool)
        return output

    output["Date"] = pd.to_datetime(output["Date"], errors="coerce")
    output["_BaseCode"] = output["StockCode"].astype(str).str.split(".").str[0]

    def _empty_result(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        for col in _INVESTOR_COUNT_COLUMNS:
            frame[col] = 0
        for col in _INVESTOR_FLAG_COLUMNS:
            frame[col] = False
        return frame.drop(columns=["_BaseCode"])

    if investor_flow_df is None or investor_flow_df.empty:
        return _empty_result(output)

    investor = investor_flow_df.copy()
    investor["Date"] = pd.to_datetime(investor["Date"], errors="coerce")
    investor["BaseCode"] = investor["BaseCode"].astype(str).str.strip()
    investor["foreign_net"] = pd.to_numeric(investor["foreign_net"], errors="coerce").fillna(0)
    investor["trust_net"] = pd.to_numeric(investor["trust_net"], errors="coerce").fillna(0)
    investor = (
        investor.dropna(subset=["Date"]).sort_values(["BaseCode", "Date"]).reset_index(drop=True)
    )
    if investor.empty:
        return _empty_result(output)

    investor["foreign_buy_streak"] = investor.groupby("BaseCode")["foreign_net"].transform(
        lambda s: _consecutive_true_streak(s > 0)
    )
    investor["trust_buy_streak"] = investor.groupby("BaseCode")["trust_net"].transform(
        lambda s: _consecutive_true_streak(s > 0)
    )

    merged_groups: list[pd.DataFrame] = []
    for base_code, stock_df in output.sort_values(["_BaseCode", "Date"]).groupby(
        "_BaseCode", sort=False
    ):
        flow = (
            investor[investor["BaseCode"] == str(base_code).strip()][
                ["Date", "foreign_buy_streak", "trust_buy_streak"]
            ]
            .drop_duplicates(subset=["Date"], keep="last")
            .sort_values("Date")
            .reset_index(drop=True)
        )
        stock_sorted = stock_df.sort_values("Date").reset_index(drop=True)
        if flow.empty:
            for col in _INVESTOR_COUNT_COLUMNS:
                stock_sorted[col] = 0
        else:
            last_flow_date = flow["Date"].max()
            stock_sorted = pd.merge_asof(stock_sorted, flow, on="Date", direction="backward")
            future_mask = stock_sorted["Date"] > last_flow_date
            for col in _INVESTOR_COUNT_COLUMNS:
                stock_sorted[col] = (
                    pd.to_numeric(stock_sorted[col], errors="coerce").fillna(0).astype(int)
                )
                if future_mask.any():
                    stock_sorted.loc[future_mask, col] = 0
        merged_groups.append(stock_sorted)

    merged = pd.concat(merged_groups, ignore_index=True)
    for col in _INVESTOR_COUNT_COLUMNS:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
    merged["foreign_buy_streak_ok"] = merged["foreign_buy_streak"] >= consecutive_days
    merged["trust_buy_streak_ok"] = merged["trust_buy_streak"] >= consecutive_days
    return (
        merged.drop(columns=["_BaseCode"])
        .sort_values(["StockCode", "Date"])
        .reset_index(drop=True)
    )
