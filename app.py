"""Bullish / Bearish Three-Condition Stock Screener — Streamlit app.

Run with:
    streamlit run app.py

This tool is for stock research and screening only. It is NOT investment advice.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config
from chart_engine import create_stock_chart
from data_loader import (
    download_stock_data,
    load_stock_list_from_upload,
    parse_stock_list,
    resample_ohlcv,
)
from export_engine import create_excel_bytes
from signal_engine import run_signal_pipeline

st.set_page_config(page_title=config.APP_TITLE, layout="wide")


# ---------------------------------------------------------------------------
# Result-table assembly
# ---------------------------------------------------------------------------
def _ordered_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    """Return the subset of `columns` present in df, in order."""
    return [c for c in columns if c in df.columns]


def build_matching_table(signals: pd.DataFrame, direction: str) -> pd.DataFrame:
    """Rows with a final signal within the lookback window, filtered and sorted.

    Sort order (spec 15.2): Date desc, final_bull_signal desc, final_bear_signal desc,
    bull_score desc, bear_score desc, StockCode asc.
    """
    if signals is None or signals.empty:
        return pd.DataFrame(columns=config.RESULT_COLUMNS)

    in_window = signals.get("in_lookback_window", pd.Series(True, index=signals.index))

    if direction == config.DIRECTION_BULLISH:
        mask = signals["final_bull_signal"]
    elif direction == config.DIRECTION_BEARISH:
        mask = signals["final_bear_signal"]
    else:
        mask = signals["final_bull_signal"] | signals["final_bear_signal"]

    matched = signals[mask & in_window].copy()
    if matched.empty:
        return pd.DataFrame(columns=config.RESULT_COLUMNS)

    matched = matched.sort_values(
        by=[
            "Date",
            "final_bull_signal",
            "final_bear_signal",
            "bull_score",
            "bear_score",
            "StockCode",
        ],
        ascending=[False, False, False, False, False, True],
    ).reset_index(drop=True)

    return matched[_ordered_columns(matched, config.RESULT_COLUMNS)]


def build_summary_table(signals: pd.DataFrame, direction: str) -> pd.DataFrame:
    """One row per StockCode per signal direction, restricted to the lookback window."""
    empty = pd.DataFrame(columns=config.SUMMARY_COLUMNS)
    if signals is None or signals.empty:
        return empty

    in_window = signals.get("in_lookback_window", pd.Series(True, index=signals.index))
    windowed = signals[in_window].copy()
    if windowed.empty:
        return empty

    allow_bull = direction in (config.DIRECTION_BOTH, config.DIRECTION_BULLISH)
    allow_bear = direction in (config.DIRECTION_BOTH, config.DIRECTION_BEARISH)

    rows: list[dict] = []
    for stock_code, group in windowed.groupby("StockCode", sort=True):
        has_bull = bool(group["final_bull_signal"].any())
        has_bear = bool(group["final_bear_signal"].any())
        both = has_bull and has_bear

        def _row(latest: pd.Series, signal_direction: str) -> dict:
            if both:
                summary = "Both Bullish and Bearish Signals"
            elif signal_direction == "Bullish":
                summary = "Bullish Three-Condition Method"
            else:
                summary = "Bearish Three-Condition Method"
            return {
                "StockCode": stock_code,
                "LatestSignalDate": latest["Date"],
                "Timeframe": latest.get("Timeframe", ""),
                "SignalDirection": signal_direction,
                "BullScore": int(latest.get("bull_score", 0)),
                "BearScore": int(latest.get("bear_score", 0)),
                "LatestOpen": latest.get("Open"),
                "LatestHigh": latest.get("High"),
                "LatestLow": latest.get("Low"),
                "LatestClose": latest.get("Close"),
                "LatestVolume": latest.get("Volume"),
                "LatestSignalSummary": summary,
            }

        if has_bull and allow_bull:
            bull_rows = group[group["final_bull_signal"]]
            latest = bull_rows.loc[bull_rows["Date"].idxmax()]
            rows.append(_row(latest, "Bullish"))
        if has_bear and allow_bear:
            bear_rows = group[group["final_bear_signal"]]
            latest = bear_rows.loc[bear_rows["Date"].idxmax()]
            rows.append(_row(latest, "Bearish"))

    if not rows:
        return empty

    summary_df = pd.DataFrame(rows)
    summary_df = summary_df.sort_values(
        by=["LatestSignalDate", "StockCode", "SignalDirection"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    return summary_df[_ordered_columns(summary_df, config.SUMMARY_COLUMNS)]


# ---------------------------------------------------------------------------
# Screening orchestration
# ---------------------------------------------------------------------------
def resolve_stock_list(text_value: str, uploaded_file) -> tuple[list[str], str | None]:
    """Merge the text area and CSV upload into a deduplicated symbol list."""
    upload_error = None
    text_codes = parse_stock_list(text_value)
    upload_codes: list[str] = []
    if uploaded_file is not None:
        try:
            upload_codes = load_stock_list_from_upload(uploaded_file)
        except ValueError as exc:
            upload_error = str(exc)

    merged: list[str] = []
    seen: set[str] = set()
    for code in [*text_codes, *upload_codes]:
        if code not in seen:
            seen.add(code)
            merged.append(code)
    return merged, upload_error


def run_screening(params: dict) -> dict:
    """Download, resample, run the signal pipeline and assemble all output tables."""
    stock_codes = params["stock_codes"]
    timeframe_code = config.TIMEFRAME_OPTIONS[params["analysis_timeframe"]]

    progress = st.progress(0.0, text="Starting download...")

    def _cb(fraction: float, message: str) -> None:
        progress.progress(min(max(fraction, 0.0), 1.0), text=message)

    raw_data, success_list, failed_list = download_stock_data(
        stock_codes, params["start_date"], params["end_date"], progress_callback=_cb
    )
    progress.empty()

    if raw_data is None or raw_data.empty:
        return {
            "signals": pd.DataFrame(),
            "matching": pd.DataFrame(columns=config.RESULT_COLUMNS),
            "summary": pd.DataFrame(columns=config.SUMMARY_COLUMNS),
            "success_list": success_list,
            "failed_list": failed_list,
            "params": params,
        }

    resampled = resample_ohlcv(raw_data, timeframe_code)
    signals = run_signal_pipeline(resampled, params)

    matching = build_matching_table(signals, params["signal_direction_filter"])
    summary = build_summary_table(signals, params["signal_direction_filter"])

    return {
        "signals": signals,
        "matching": matching,
        "summary": summary,
        "success_list": success_list,
        "failed_list": failed_list,
        "params": params,
    }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> dict | None:
    """Render sidebar controls. Returns params dict when Run Screening is clicked."""
    st.sidebar.header("Screening Controls")

    text_value = st.sidebar.text_area(
        "Stock list (one symbol per line)",
        value=config.DEFAULT_TEXT_STOCK_LIST,
        height=160,
        help="Example: 2330.TW. Commas are also accepted as separators.",
    )
    uploaded_file = st.sidebar.file_uploader(
        "Or upload a CSV (must contain a StockCode column)", type=["csv"]
    )

    col1, col2 = st.sidebar.columns(2)
    start_date = col1.date_input("Start date", value=config.DEFAULT_START_DATE)
    end_date = col2.date_input("End date", value=config.DEFAULT_END_DATE)

    analysis_timeframe = st.sidebar.selectbox(
        "Analysis timeframe",
        options=list(config.TIMEFRAME_OPTIONS.keys()),
        index=list(config.TIMEFRAME_OPTIONS.keys()).index(config.DEFAULT_TIMEFRAME_LABEL),
    )
    min_volume = st.sidebar.number_input(
        "Minimum volume", min_value=0, value=config.DEFAULT_MIN_VOLUME, step=100
    )
    lookback_bars = st.sidebar.number_input(
        "Lookback bars", min_value=1, value=config.DEFAULT_LOOKBACK_BARS, step=1
    )
    signal_direction_filter = st.sidebar.selectbox(
        "Signal direction filter", options=config.DIRECTION_OPTIONS, index=0
    )

    run_clicked = st.sidebar.button("Run Screening", type="primary", use_container_width=True)

    if not run_clicked:
        return None

    if end_date < start_date:
        st.sidebar.error("End date must be on or after the start date.")
        return None

    stock_codes, upload_error = resolve_stock_list(text_value, uploaded_file)
    if upload_error:
        st.sidebar.error(upload_error)
    if not stock_codes:
        st.sidebar.error("Please provide at least one stock symbol.")
        return None

    return {
        "stock_codes": stock_codes,
        "start_date": start_date,
        "end_date": end_date,
        "analysis_timeframe": analysis_timeframe,
        "min_volume": int(min_volume),
        "lookback_bars": int(lookback_bars),
        "signal_direction_filter": signal_direction_filter,
    }


# ---------------------------------------------------------------------------
# Results rendering
# ---------------------------------------------------------------------------
def render_download_status(success_list: list[str], failed_list: list[str]) -> None:
    st.subheader("Download Status")
    col1, col2 = st.columns(2)
    col1.metric("Successful downloads", len(success_list))
    col2.metric("Failed downloads", len(failed_list))
    if failed_list:
        st.warning("Failed symbols: " + ", ".join(failed_list))


def render_chart(signals: pd.DataFrame, timeframe_label: str) -> None:
    st.subheader("Stock Chart")
    available = sorted(signals["StockCode"].dropna().unique().tolist())
    if not available:
        st.info("No stock data available to chart.")
        return
    selected = st.selectbox("Select a stock to chart", options=available)
    stock_df = signals[signals["StockCode"] == selected].copy()
    fig, message = create_stock_chart(stock_df, timeframe_label)
    if fig is None:
        st.info(message)
    else:
        st.plotly_chart(fig, use_container_width=True)


def render_results(result: dict) -> None:
    params = result["params"]
    signals = result["signals"]
    matching = result["matching"]
    summary = result["summary"]

    render_download_status(result["success_list"], result["failed_list"])

    if signals is None or signals.empty:
        st.error("No usable data was downloaded. Try different symbols or a wider date range.")
        return

    st.subheader("Matching Signals")
    st.caption(
        f"Bars with a final signal within the most recent {params['lookback_bars']} "
        f"K-bars ({params['analysis_timeframe']}). Filter: {params['signal_direction_filter']}."
    )
    if matching.empty:
        st.info("No matching signals found for the current parameters.")
    else:
        st.dataframe(matching, use_container_width=True, hide_index=True)

    st.subheader("Latest Summary")
    st.caption("One row per stock per signal direction.")
    if summary.empty:
        st.info("No qualifying stocks in the latest summary.")
    else:
        st.dataframe(summary, use_container_width=True, hide_index=True)

    render_chart(signals, params["analysis_timeframe"])

    # --- Excel export ---
    bullish_signals = signals[signals["final_bull_signal"]].copy()
    bearish_signals = signals[signals["final_bear_signal"]].copy()
    excel_bytes = create_excel_bytes(
        all_data=signals,
        matching_signals=matching,
        bullish_signals=bullish_signals,
        bearish_signals=bearish_signals,
        latest_summary=summary,
        failed_list=result["failed_list"],
        params=params,
    )
    st.download_button(
        "Download Excel report",
        data=excel_bytes,
        file_name="three_condition_screener.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.title(config.APP_TITLE)
    st.caption(config.APP_DISCLAIMER)

    with st.expander("About the strategy", expanded=False):
        st.markdown(
            """
            **Big Red Attack Success**: `Open > prev_close AND Close > prev_close` → creates a **red_line** at `prev_close`.

            **Big Black Attack Success**: `Open < prev_close AND Close < prev_close` → creates a **black_line** at `prev_close`.

            A *failed* attack (e.g. opened up but closed down) is only a failed attack — it never
            becomes the opposite attack and never creates the opposite line.

            **Bullish Three-Condition** (≥2 within the lookback window): A) Big Red Attack Success appears,
            B) break above the latest black_line, C) retest red/black line as support and hold.

            **Bearish Three-Condition** (≥2 within the lookback window): A) Big Black Attack Success appears,
            B) break below the latest red_line, C) retest red/black line as resistance and fail.
            """
        )

    params = render_sidebar()
    if params is not None:
        with st.spinner("Running screening..."):
            st.session_state["result"] = run_screening(params)

    if "result" in st.session_state:
        render_results(st.session_state["result"])
    else:
        st.info("Set your parameters in the sidebar and click **Run Screening** to begin.")


if __name__ == "__main__":
    main()
