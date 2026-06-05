"""Excel export for the Bullish / Bearish Three-Condition Stock Screener.

Produces an in-memory workbook with seven sheets:
  1. All_Data           - all OHLCV data with every calculated column
  2. Matching_Signals   - final_bull_signal OR final_bear_signal within lookback_bars
  3. Bullish_Signals    - rows where final_bull_signal is True
  4. Bearish_Signals    - rows where final_bear_signal is True
  5. Latest_Summary     - one row per StockCode per signal direction
  6. Failed_Downloads   - failed stock symbols
  7. Parameter_Settings - the run parameters
"""

from __future__ import annotations

import io

import pandas as pd


def _sheet_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    """Return a safe copy for writing; empty frame when input is missing/empty."""
    if df is None or df.empty:
        return pd.DataFrame()
    return df.copy()


def create_excel_bytes(
    all_data: pd.DataFrame,
    matching_signals: pd.DataFrame,
    bullish_signals: pd.DataFrame,
    bearish_signals: pd.DataFrame,
    latest_summary: pd.DataFrame,
    failed_list: list[str],
    params: dict,
) -> bytes:
    """Build the seven-sheet workbook and return it as bytes."""
    parameter_sheet = pd.DataFrame(
        {
            "Parameter": [
                "start_date",
                "end_date",
                "analysis_timeframe",
                "min_volume",
                "lookback_bars",
                "signal_direction_filter",
            ],
            "Value": [
                str(params.get("start_date", "")),
                str(params.get("end_date", "")),
                str(params.get("analysis_timeframe", "")),
                params.get("min_volume", ""),
                params.get("lookback_bars", ""),
                str(params.get("signal_direction_filter", "")),
            ],
        }
    )

    failed_sheet = pd.DataFrame({"FailedStockCode": list(failed_list or [])})

    workbook = {
        "All_Data": _sheet_frame(all_data),
        "Matching_Signals": _sheet_frame(matching_signals),
        "Bullish_Signals": _sheet_frame(bullish_signals),
        "Bearish_Signals": _sheet_frame(bearish_signals),
        "Latest_Summary": _sheet_frame(latest_summary),
        "Failed_Downloads": failed_sheet,
        "Parameter_Settings": parameter_sheet,
    }

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in workbook.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()
