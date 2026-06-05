"""Chart rendering — Plotly candlestick with attack lines and signal markers.

The chart shows, for a single stock:
  - Candlestick
  - Volume
  - red_line and black_line
  - Big Red Attack Success markers
  - Big Black Attack Success markers
  - Bullish Three-Condition Signal markers
  - Bearish Three-Condition Signal markers
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Reference lines drawn as step lines across the chart.
_LINE_STYLES = [
    ("red_line", "#dc2626", "red_line"),
    ("black_line", "#111827", "black_line"),
]

# Signal markers: column -> (label, color, symbol, y-source column, offset direction).
_MARKERS = [
    ("red_attack_success", "Big Red Attack Success", "#dc2626", "triangle-up", "High", +1),
    ("black_attack_success", "Big Black Attack Success", "#111827", "triangle-down", "Low", -1),
    ("final_bull_signal", "Bullish Three-Condition Signal", "#16a34a", "star", "Low", -1),
    ("final_bear_signal", "Bearish Three-Condition Signal", "#7c3aed", "star", "High", +1),
]


def create_stock_chart(stock_df: pd.DataFrame, timeframe_label: str):
    """Build an interactive candlestick chart for one stock.

    Returns (figure, None) on success or (None, message) when there is not enough
    data to draw a reliable chart.
    """
    if stock_df is None or stock_df.empty:
        return None, "No data available to display."

    required = {"Date", "StockCode", "Open", "High", "Low", "Close", "Volume"}
    missing = required.difference(stock_df.columns)
    if missing:
        return None, f"Chart data is missing required columns: {sorted(missing)}"

    chart_df = stock_df.sort_values("Date").copy()
    if chart_df[["Open", "High", "Low", "Close"]].dropna(how="any").shape[0] < 2:
        return None, "Not enough historical data to draw a reliable chart."

    stock_code = str(chart_df["StockCode"].iloc[-1])

    volume_colors = [
        "#16a34a" if close >= open_price else "#dc2626"
        for open_price, close in zip(chart_df["Open"], chart_df["Close"])
    ]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
    )

    # --- Candlestick ---
    fig.add_trace(
        go.Candlestick(
            x=chart_df["Date"],
            open=chart_df["Open"],
            high=chart_df["High"],
            low=chart_df["Low"],
            close=chart_df["Close"],
            name="Candlestick",
            increasing_line_color="#dc2626",
            decreasing_line_color="#16a34a",
        ),
        row=1,
        col=1,
    )

    # --- red_line / black_line as dashed step lines ---
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

    # --- Signal markers ---
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
                + "<br>Close: %{customdata:.2f}<extra></extra>",
                customdata=rows["Close"].values,
            ),
            row=1,
            col=1,
        )

    # --- Volume ---
    fig.add_trace(
        go.Bar(
            x=chart_df["Date"],
            y=chart_df["Volume"],
            name="Volume",
            marker={"color": volume_colors},
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"{stock_code} — Big Red / Big Black Attack ({timeframe_label})",
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 20, "r": 20, "t": 70, "b": 20},
        height=720,
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig, None
