"""Excel 匯出 — 多頭 / 空頭三條件選股系統（繁體中文）。

產生七張工作表（傳入的資料表已先轉為中文欄位/數值）：
  1. 全部資料     - 所有 OHLCV 與計算欄位
  2. 符合訊號     - 回看區間內 final_bull_signal 或 final_bear_signal 為真
  3. 多頭訊號     - final_bull_signal 為真
  4. 空頭訊號     - final_bear_signal 為真
  5. 最新摘要     - 每檔股票每個訊號方向一列
  6. 下載失敗清單 - 下載失敗的股票代號
  7. 參數設定     - 本次執行參數
"""

from __future__ import annotations

import io

import pandas as pd

import config


def _sheet_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    """回傳可安全寫入的副本；資料缺漏時回傳空表。"""
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
    """組成七張工作表的活頁簿並回傳 bytes。"""
    parameter_rows = [
        (config.PARAMETER_LABELS.get(key, key), value)
        for key, value in [
            ("start_date", params.get("start_date", "")),
            ("end_date", params.get("end_date", "")),
            ("analysis_timeframe", params.get("analysis_timeframe", "")),
            ("min_volume", params.get("min_volume", "")),
            ("lookback_bars", params.get("lookback_bars", "")),
            ("signal_direction_filter", params.get("signal_direction_filter", "")),
            ("enable_investor_flow", params.get("enable_investor_flow", "")),
            ("consecutive_buy_days", params.get("consecutive_buy_days", "")),
            ("require_foreign_buy", params.get("require_foreign_buy", "")),
            ("require_trust_buy", params.get("require_trust_buy", "")),
        ]
    ]
    parameter_sheet = pd.DataFrame(
        {"參數": [r[0] for r in parameter_rows], "設定值": [str(r[1]) for r in parameter_rows]}
    )

    failed_sheet = pd.DataFrame({"下載失敗股票代號": list(failed_list or [])})

    names = config.EXCEL_SHEET_NAMES
    workbook = {
        names["all_data"]: _sheet_frame(all_data),
        names["matching"]: _sheet_frame(matching_signals),
        names["bullish"]: _sheet_frame(bullish_signals),
        names["bearish"]: _sheet_frame(bearish_signals),
        names["summary"]: _sheet_frame(latest_summary),
        names["failed"]: failed_sheet,
        names["params"]: parameter_sheet,
    }

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in workbook.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()
