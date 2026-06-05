"""多頭 / 空頭 三條件選股系統（大紅攻 / 大黑攻）— Streamlit 應用程式。

執行方式：
    streamlit run app.py

本工具僅供股票研究與篩選參考，並不構成任何投資建議。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import config
from chart_engine import create_stock_chart
from data_loader import (
    download_investor_flow_data,
    download_stock_data,
    load_stock_list_from_upload,
    parse_stock_list,
    resample_ohlcv,
)
from export_engine import create_excel_bytes
from signal_engine import attach_investor_flow_flags, run_signal_pipeline

st.set_page_config(page_title=config.APP_TITLE, layout="wide")


# ---------------------------------------------------------------------------
# 顯示繁體中文化（僅用於畫面與 Excel；內部欄位維持英文）
# ---------------------------------------------------------------------------
def localize_df(df: pd.DataFrame, columns_order: list[str] | None = None) -> pd.DataFrame:
    """將資料表轉為繁體中文：翻譯欄位名稱、類別數值、布林值與日期格式。"""
    if df is None or df.empty:
        cols = columns_order or (list(df.columns) if df is not None else [])
        return pd.DataFrame(columns=[config.DISPLAY_COLUMN_LABELS.get(c, c) for c in cols])

    out = df.copy()

    # 類別字串值翻譯。
    for col, mapping in config.VALUE_LABELS.items():
        if col in out.columns:
            out[col] = out[col].map(lambda v: mapping.get(v, v))

    # 日期格式化。
    for date_col in ("Date", "LatestSignalDate"):
        if date_col in out.columns:
            out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.strftime("%Y-%m-%d")

    # 週期代碼 -> 中文標籤。
    if "Timeframe" in out.columns:
        out["Timeframe"] = out["Timeframe"].map(lambda v: config.TIMEFRAME_LABELS.get(v, v))

    # 布林值 -> 是 / 否。
    for col in out.columns:
        if out[col].dtype == bool:
            out[col] = out[col].map(
                {True: config.BOOL_TRUE_LABEL, False: config.BOOL_FALSE_LABEL}
            )

    return out.rename(columns=config.DISPLAY_COLUMN_LABELS)


# ---------------------------------------------------------------------------
# 結果表組裝
# ---------------------------------------------------------------------------
def _ordered_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [c for c in columns if c in df.columns]


def _investor_pass(df: pd.DataFrame, params: dict) -> pd.Series:
    """依「需外資/投信連買達標」設定回傳布林遮罩。"""
    mask = pd.Series(True, index=df.index)
    if params.get("require_foreign_buy") and "foreign_buy_streak_ok" in df.columns:
        mask &= df["foreign_buy_streak_ok"].fillna(False).astype(bool)
    if params.get("require_trust_buy") and "trust_buy_streak_ok" in df.columns:
        mask &= df["trust_buy_streak_ok"].fillna(False).astype(bool)
    return mask


def build_matching_table(signals: pd.DataFrame, params: dict) -> pd.DataFrame:
    """回看區間內、符合方向與法人條件的訊號 K 棒，並依規則排序。"""
    if signals is None or signals.empty:
        return pd.DataFrame(columns=config.RESULT_COLUMNS)

    direction = params["signal_direction_filter"]
    in_window = signals.get("in_lookback_window", pd.Series(True, index=signals.index))
    inv_pass = _investor_pass(signals, params)

    if direction == config.DIRECTION_BULLISH:
        direction_mask = signals["final_bull_signal"]
    elif direction == config.DIRECTION_BEARISH:
        direction_mask = signals["final_bear_signal"]
    else:
        direction_mask = signals["final_bull_signal"] | signals["final_bear_signal"]

    matched = signals[direction_mask & in_window & inv_pass].copy()
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


def build_summary_table(signals: pd.DataFrame, params: dict) -> pd.DataFrame:
    """每檔股票、每個訊號方向一列（限回看區間，且套用法人條件）。"""
    empty = pd.DataFrame(columns=config.SUMMARY_COLUMNS)
    if signals is None or signals.empty:
        return empty

    direction = params["signal_direction_filter"]
    in_window = signals.get("in_lookback_window", pd.Series(True, index=signals.index))
    windowed = signals[in_window].copy()
    if windowed.empty:
        return empty

    inv_pass = _investor_pass(windowed, params)
    windowed["_eff_bull"] = windowed["final_bull_signal"] & inv_pass
    windowed["_eff_bear"] = windowed["final_bear_signal"] & inv_pass

    allow_bull = direction in (config.DIRECTION_BOTH, config.DIRECTION_BULLISH)
    allow_bear = direction in (config.DIRECTION_BOTH, config.DIRECTION_BEARISH)

    rows: list[dict] = []
    for stock_code, group in windowed.groupby("StockCode", sort=True):
        has_bull = bool(group["_eff_bull"].any())
        has_bear = bool(group["_eff_bear"].any())
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
                "ForeignBuyStreak": int(latest.get("foreign_buy_streak", 0) or 0),
                "ForeignBuyStreakOK": bool(latest.get("foreign_buy_streak_ok", False)),
                "TrustBuyStreak": int(latest.get("trust_buy_streak", 0) or 0),
                "TrustBuyStreakOK": bool(latest.get("trust_buy_streak_ok", False)),
                "LatestSignalSummary": summary,
            }

        if has_bull and allow_bull:
            bull_rows = group[group["_eff_bull"]]
            rows.append(_row(bull_rows.loc[bull_rows["Date"].idxmax()], "Bullish"))
        if has_bear and allow_bear:
            bear_rows = group[group["_eff_bear"]]
            rows.append(_row(bear_rows.loc[bear_rows["Date"].idxmax()], "Bearish"))

    if not rows:
        return empty

    summary_df = pd.DataFrame(rows).sort_values(
        by=["LatestSignalDate", "StockCode", "SignalDirection"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    return summary_df[_ordered_columns(summary_df, config.SUMMARY_COLUMNS)]


# ---------------------------------------------------------------------------
# 篩選流程
# ---------------------------------------------------------------------------
def resolve_stock_list(text_value: str, uploaded_file) -> tuple[list[str], str | None]:
    """合併文字框與 CSV 上傳，得到去重後的股票代號清單。"""
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
    """下載、重新取樣、計算訊號、抓取法人資料並組裝所有輸出表。"""
    stock_codes = params["stock_codes"]
    timeframe_code = config.TIMEFRAME_OPTIONS[params["analysis_timeframe"]]

    progress = st.progress(0.0, text="開始下載股價資料...")

    def _cb(fraction: float, message: str) -> None:
        progress.progress(min(max(fraction, 0.0), 1.0), text=message)

    raw_data, success_list, failed_list = download_stock_data(
        stock_codes, params["start_date"], params["end_date"], progress_callback=_cb
    )

    investor_note = None
    if raw_data is None or raw_data.empty:
        progress.empty()
        return {
            "signals": pd.DataFrame(),
            "matching": pd.DataFrame(columns=config.RESULT_COLUMNS),
            "summary": pd.DataFrame(columns=config.SUMMARY_COLUMNS),
            "success_list": success_list,
            "failed_list": failed_list,
            "investor_note": investor_note,
            "params": params,
        }

    resampled = resample_ohlcv(raw_data, timeframe_code)
    signals = run_signal_pipeline(resampled, params)

    # 外資 / 投信 連續買入。
    investor_df = pd.DataFrame()
    if params.get("enable_investor_flow"):
        consecutive = int(params.get("consecutive_buy_days", 3))
        lookback_days = max(int(consecutive * 1.6) + 12, 25)
        investor_df = download_investor_flow_data(
            success_list, params["end_date"], lookback_days=lookback_days, progress_callback=_cb
        )
        if investor_df.empty:
            investor_note = (
                "未取得外資 / 投信法人資料（可能為非台股、或公開資料來源暫時無法連線），"
                "相關欄位以 0 / 否 顯示。"
            )
    signals = attach_investor_flow_flags(
        signals, investor_df, consecutive_days=int(params.get("consecutive_buy_days", 3))
    )
    progress.empty()

    matching = build_matching_table(signals, params)
    summary = build_summary_table(signals, params)

    return {
        "signals": signals,
        "matching": matching,
        "summary": summary,
        "success_list": success_list,
        "failed_list": failed_list,
        "investor_note": investor_note,
        "params": params,
    }


# ---------------------------------------------------------------------------
# 側邊欄
# ---------------------------------------------------------------------------
def render_sidebar() -> dict | None:
    """繪製側邊欄控制項。按下「開始篩選」時回傳參數 dict。"""
    st.sidebar.header("篩選設定")

    text_value = st.sidebar.text_area(
        "股票清單（每行一個代號）",
        value=config.DEFAULT_TEXT_STOCK_LIST,
        height=160,
        help="範例：2330.TW；亦可用逗號分隔。",
    )
    uploaded_file = st.sidebar.file_uploader(
        "或上傳 CSV（需包含 StockCode 欄位）", type=["csv"]
    )

    col1, col2 = st.sidebar.columns(2)
    start_date = col1.date_input("起始日期", value=config.DEFAULT_START_DATE)
    end_date = col2.date_input("結束日期", value=config.DEFAULT_END_DATE)

    timeframe_labels = list(config.TIMEFRAME_OPTIONS.keys())
    analysis_timeframe = st.sidebar.selectbox(
        "分析週期",
        options=timeframe_labels,
        index=timeframe_labels.index(config.DEFAULT_TIMEFRAME_LABEL),
    )
    min_volume = st.sidebar.number_input(
        "最低成交量", min_value=0, value=config.DEFAULT_MIN_VOLUME, step=100
    )
    lookback_bars = st.sidebar.number_input(
        "回看根數", min_value=1, value=config.DEFAULT_LOOKBACK_BARS, step=1
    )
    signal_direction_filter = st.sidebar.selectbox(
        "訊號方向篩選", options=config.DIRECTION_OPTIONS, index=0
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("外資 / 投信 連續買入")
    enable_investor_flow = st.sidebar.checkbox(
        "計算外資 / 投信連續買入",
        value=config.ENABLE_INVESTOR_FLOW_DEFAULT,
        help="需額外抓取台股（上市/上櫃）法人買賣超公開資料，較花時間。",
    )
    consecutive_buy_days = st.sidebar.number_input(
        "連續買入天數",
        min_value=1,
        max_value=20,
        value=config.DEFAULT_CONSECUTIVE_BUY_DAYS,
        step=1,
        help="外資 / 投信需連續幾個交易日皆為買超才算達標。",
        disabled=not enable_investor_flow,
    )
    require_foreign_buy = st.sidebar.checkbox(
        "篩選：需外資連買達標", value=False, disabled=not enable_investor_flow
    )
    require_trust_buy = st.sidebar.checkbox(
        "篩選：需投信連買達標", value=False, disabled=not enable_investor_flow
    )

    st.sidebar.markdown("---")
    run_clicked = st.sidebar.button("開始篩選", type="primary", use_container_width=True)

    if not run_clicked:
        return None

    if end_date < start_date:
        st.sidebar.error("結束日期必須不早於起始日期。")
        return None

    stock_codes, upload_error = resolve_stock_list(text_value, uploaded_file)
    if upload_error:
        st.sidebar.error(upload_error)
    if not stock_codes:
        st.sidebar.error("請至少輸入一個股票代號。")
        return None

    return {
        "stock_codes": stock_codes,
        "start_date": start_date,
        "end_date": end_date,
        "analysis_timeframe": analysis_timeframe,
        "min_volume": int(min_volume),
        "lookback_bars": int(lookback_bars),
        "signal_direction_filter": signal_direction_filter,
        "enable_investor_flow": bool(enable_investor_flow),
        "consecutive_buy_days": int(consecutive_buy_days),
        "require_foreign_buy": bool(require_foreign_buy),
        "require_trust_buy": bool(require_trust_buy),
    }


# ---------------------------------------------------------------------------
# 結果呈現
# ---------------------------------------------------------------------------
def render_download_status(result: dict) -> None:
    st.subheader("下載狀態")
    col1, col2 = st.columns(2)
    col1.metric("下載成功", len(result["success_list"]))
    col2.metric("下載失敗", len(result["failed_list"]))
    if result["failed_list"]:
        st.warning("下載失敗的代號：" + "、".join(result["failed_list"]))
    if result.get("investor_note"):
        st.info(result["investor_note"])


def render_chart(signals: pd.DataFrame, timeframe_label: str) -> None:
    st.subheader("個股圖表")
    available = sorted(signals["StockCode"].dropna().unique().tolist())
    if not available:
        st.info("沒有可繪製圖表的股票資料。")
        return
    selected = st.selectbox("選擇要繪製的股票", options=available)
    stock_df = signals[signals["StockCode"] == selected].copy()
    fig, message = create_stock_chart(stock_df, timeframe_label)
    if fig is None:
        st.info(message)
    else:
        st.plotly_chart(fig, use_container_width=True)


def render_results(result: dict) -> None:
    params = result["params"]
    signals = result["signals"]

    render_download_status(result)

    if signals is None or signals.empty:
        st.error("沒有可用的下載資料。請嘗試其他代號或加大日期區間。")
        return

    matching_disp = localize_df(result["matching"], config.RESULT_COLUMNS)
    summary_disp = localize_df(result["summary"], config.SUMMARY_COLUMNS)

    st.subheader("符合訊號")
    st.caption(
        f"最近 {params['lookback_bars']} 根 K 棒（{params['analysis_timeframe']}）內出現最終訊號的 K 棒。"
        f"方向篩選：{params['signal_direction_filter']}。"
    )
    if result["matching"].empty:
        st.info("目前參數下沒有符合的訊號。")
    else:
        st.dataframe(matching_disp, use_container_width=True, hide_index=True)

    st.subheader("最新摘要")
    st.caption("每檔股票、每個訊號方向各一列。")
    if result["summary"].empty:
        st.info("最新摘要中沒有符合條件的股票。")
    else:
        st.dataframe(summary_disp, use_container_width=True, hide_index=True)

    render_chart(signals, params["analysis_timeframe"])

    # --- Excel 匯出（已繁體中文化）---
    bullish_signals = signals[signals["final_bull_signal"]].copy()
    bearish_signals = signals[signals["final_bear_signal"]].copy()
    excel_bytes = create_excel_bytes(
        all_data=localize_df(signals),
        matching_signals=matching_disp,
        bullish_signals=localize_df(bullish_signals),
        bearish_signals=localize_df(bearish_signals),
        latest_summary=summary_disp,
        failed_list=result["failed_list"],
        params=params,
    )
    st.download_button(
        "下載 Excel 報表",
        data=excel_bytes,
        file_name="三條件選股結果.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------
def main() -> None:
    st.title(config.APP_TITLE)
    st.caption(config.APP_DISCLAIMER)

    with st.expander("策略說明", expanded=False):
        st.markdown(
            """
            **大紅攻成功**：`開盤 > 前一根收盤 且 收盤 > 前一根收盤` → 在 `前一根收盤` 建立一條**紅線**。

            **大黑攻成功**：`開盤 < 前一根收盤 且 收盤 < 前一根收盤` → 在 `前一根收盤` 建立一條**黑線**。

            攻擊「失敗」（例如跳空開高卻收低）只算失敗的攻擊，**不會**變成反向攻擊，也**不會**建立反向均線。

            **多頭三條件**（回看區間內至少符合 2 項）：A) 出現大紅攻成功、
            B) 突破最新黑線、C) 回測紅線或黑線作為支撐並守住。

            **空頭三條件**（回看區間內至少符合 2 項）：A) 出現大黑攻成功、
            B) 跌破最新紅線、C) 反彈回測紅線或黑線作為反壓並失敗。

            **外資 / 投信連續買入**：可設定連續買入天數（預設 3 日），系統會標示外資、投信是否達標，
            並可勾選作為額外篩選條件。
            """
        )

    params = render_sidebar()
    if params is not None:
        with st.spinner("篩選計算中..."):
            st.session_state["result"] = run_screening(params)

    if "result" in st.session_state:
        render_results(st.session_state["result"])
    else:
        st.info("請在左側設定參數，並按下 **開始篩選**。")


if __name__ == "__main__":
    main()
