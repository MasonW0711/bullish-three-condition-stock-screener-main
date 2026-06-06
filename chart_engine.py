"""圖表繪製 — Plotly K 線圖，含紅線 / 黑線與訊號標記。

單一股票圖表內容：
  - K 線（蠟燭圖）
  - 成交量
  - 紅線（red_line）與黑線（black_line）
  - 大紅攻成功標記
  - 大黑攻成功標記
  - 多頭三條件訊號標記
  - 空頭三條件訊號標記
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 參考均線：以階梯線繪製。
_LINE_STYLES = [
    ("red_line", "#dc2626", "紅線"),
    ("black_line", "#111827", "黑線"),
]

# 訊號標記：欄位 -> (標籤, 顏色, 形狀, Y 來源欄位, 偏移方向)。
_MARKERS = [
    ("red_attack_success", "大紅攻成功", "#dc2626", "triangle-up", "High", +1),
    ("black_attack_success", "大黑攻成功", "#111827", "triangle-down", "Low", -1),
    ("final_bull_signal", "多頭三條件訊號", "#16a34a", "star", "Low", -1),
    ("final_bear_signal", "空頭三條件訊號", "#7c3aed", "star", "High", +1),
]


def create_stock_chart(stock_df: pd.DataFrame, timeframe_label: str):
    """為單一股票建立 K 線互動圖。

    成功時回傳 (figure, None)；資料不足以繪圖時回傳 (None, 訊息)。
    """
    if stock_df is None or stock_df.empty:
        return None, "目前沒有可供顯示的資料。"

    required = {"Date", "StockCode", "Open", "High", "Low", "Close", "Volume"}
    missing = required.difference(stock_df.columns)
    if missing:
        return None, f"圖表資料缺少必要欄位：{sorted(missing)}"

    chart_df = stock_df.sort_values("Date").copy()
    if chart_df[["Open", "High", "Low", "Close"]].dropna(how="any").shape[0] < 2:
        return None, "歷史資料不足，無法為所選股票繪製可靠圖表。"

    stock_code = str(chart_df["StockCode"].iloc[-1])

    # 成交量顏色：收紅（收 >= 開）用紅色，收黑用綠色（符合台股慣例）。
    volume_colors = [
        "#dc2626" if close >= open_price else "#16a34a"
        for open_price, close in zip(chart_df["Open"], chart_df["Close"])
    ]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
    )

    # --- K 線 ---
    fig.add_trace(
        go.Candlestick(
            x=chart_df["Date"],
            open=chart_df["Open"],
            high=chart_df["High"],
            low=chart_df["Low"],
            close=chart_df["Close"],
            name="K 線",
            increasing_line_color="#dc2626",  # 上漲紅
            decreasing_line_color="#16a34a",  # 下跌綠
        ),
        row=1,
        col=1,
    )

    # --- 紅線 / 黑線（虛線階梯）---
    for col_name, color, label in _LINE_STYLES:
        if col_name not in chart_df.columns or chart_df[col_name].isna().all():
            continue
        fig.add_trace(
            go.Scatter(
                x=chart_df["Date"],
                y=chart_df[col_name],
                mode="lines",
                line={"color": color, "width": 1.5, "dash": "dash", "shape": "hv"},
                name=label,
                connectgaps=False,
            ),
            row=1,
            col=1,
        )

    # --- 訊號標記 ---
    price_range = chart_df["High"].max() - chart_df["Low"].min()
    y_offset = price_range * 0.02 if price_range and price_range > 0 else 0

    for col_name, label, color, symbol, y_col, sign in _MARKERS:
        if col_name not in chart_df.columns:
            continue
        rows = chart_df[chart_df[col_name].fillna(False).astype(bool)]
        if rows.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=rows["Date"],
                y=rows[y_col] + sign * y_offset,
                mode="markers",
                name=label,
                marker={"color": color, "size": 11, "symbol": symbol,
                        "line": {"color": "#ffffff", "width": 1}},
                hovertemplate="%{x|%Y-%m-%d}<br>" + label
                + "<br>收盤：%{customdata:.2f}<extra></extra>",
                customdata=rows["Close"].values,
            ),
            row=1,
            col=1,
        )

    # --- 成交量 ---
    fig.add_trace(
        go.Bar(
            x=chart_df["Date"],
            y=chart_df["Volume"],
            name="成交量",
            marker={"color": volume_colors},
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"{stock_code} 大紅攻 / 大黑攻 訊號圖（{timeframe_label}）",
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
        height=720,
    )
    fig.update_yaxes(title_text="價格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    return fig, None
