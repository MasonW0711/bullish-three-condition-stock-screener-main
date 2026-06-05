# Bullish / Bearish Three-Condition Stock Screener

> **Disclaimer: This tool is for stock research and screening only. It is NOT investment advice.**

A Python + Streamlit screener that automatically downloads stock OHLCV data from the
internet (via `yfinance`) and screens both the **Bullish** and **Bearish**
**Three-Condition Method**, based on **Big Red Attack** / **Big Black Attack** lines.

---

## Installation

Requires **Python 3.11+**.

```bash
# (optional) create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Running the app

```bash
streamlit run app.py
```

The app opens in your browser. Configure the inputs in the sidebar and click
**Run Screening**.

## Deploying to Streamlit Cloud

1. Push this repository to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and create a new app.
3. Select the repository and branch, and set the main file to **`app.py`**.
4. Streamlit Cloud installs `requirements.txt` automatically and runs the app.

No local absolute paths are used, so the project runs unchanged on Streamlit Cloud.

---

## How to use

In the sidebar you can:

- Paste a **stock list** (one symbol per line), or
- Upload a **CSV** that contains a `StockCode` column (see `sample_stock_list.csv`).
- Choose a **date range** (`start_date`, `end_date`).
- Choose the **analysis timeframe**: Daily K / Weekly K / Monthly K.
- Set the **minimum volume** (default `2000`).
- Set the **lookback bars** (default `10`).
- Choose a **signal direction filter**: Both / Bullish only / Bearish only.

Default stock list:

```
2330.TW
2317.TW
2382.TW
2474.TW
6182.TWO
```

After clicking **Run Screening** you get: a download status panel, a matching-signals
table, a latest-summary table, an interactive candlestick chart, and an Excel download.

---

## Strategy definitions

`prev_close` = the **previous K-bar's close** (computed separately per stock).

The attack **direction** is determined **only** by `Open` versus `prev_close`.
The `Close` **only** decides whether the attack *succeeded* or *failed*.
**A failed attack never becomes the opposite-side attack.**

### Big Red Attack

- **Success**: `Open > prev_close` **AND** `Close > prev_close` → creates a **red_line**.
- **Failed**: `Open > prev_close` **AND** `Close < prev_close` → *only* a failed bullish
  attack. **Not** a Big Black Attack. Does **not** create or update `black_line`.

### Big Black Attack

- **Success**: `Open < prev_close` **AND** `Close < prev_close` → creates a **black_line**.
- **Failed**: `Open < prev_close` **AND** `Close > prev_close` → *only* a failed bearish
  attack. **Not** a Big Red Attack. Does **not** create or update `red_line`.

If `Open == prev_close`, the bar is **No Attack**.

### red_line

Created **only** by Big Red Attack Success:

```
red_line_raw = prev_close   (only on red_attack_success bars, else NaN)
red_line     = forward-fill of red_line_raw, separately per StockCode
```

### black_line

Created **only** by Big Black Attack Success:

```
black_line_raw = prev_close (only on black_attack_success bars, else NaN)
black_line     = forward-fill of black_line_raw, separately per StockCode
```

---

## Bullish Three-Condition Method

Within the most recent `lookback_bars` K-bars, at least **2 of 3** must be true:

- **A** — Big Red Attack Success appears.
- **B** — Break above the latest `black_line`:
  `previous Close <= previous black_line` **AND** `current Close > current black_line`.
- **C** — Retest `red_line` or `black_line` as **support** and hold:
  `Low <= line_price` **AND** `Close >= line_price`.

```
bull_score        = bull_A_window + bull_B_window + bull_C_window
bull_signal       = bull_score >= 2
final_bull_signal = bull_signal AND volume_pass
```

## Bearish Three-Condition Method

Within the most recent `lookback_bars` K-bars, at least **2 of 3** must be true:

- **A** — Big Black Attack Success appears.
- **B** — Break below the latest `red_line`:
  `previous Close >= previous red_line` **AND** `current Close < current red_line`.
- **C** — Retest `red_line` or `black_line` as **resistance** and fail:
  `High >= line_price` **AND** `Close <= line_price`.

```
bear_score        = bear_A_window + bear_B_window + bear_C_window
bear_signal       = bear_score >= 2
final_bear_signal = bear_signal AND volume_pass
```

The A / B / C conditions are calculated **independently**. They do not need to appear
in order, do not need to be consecutive, and can appear on the same K-bar.

---

## Daily K / Weekly K / Monthly K

Only **daily** data is downloaded. Weekly and Monthly bars are produced by
**resampling the daily OHLCV** per stock (never downloaded directly):

| Field  | Weekly / Monthly value                  |
|--------|------------------------------------------|
| Open   | first trading day's open in the period   |
| High   | highest high in the period               |
| Low    | lowest low in the period                 |
| Close  | last trading day's close in the period   |
| Volume | sum of volume in the period              |
| Date   | last trading day's date in the period    |

Each stock is resampled separately; stocks are never mixed. A `Timeframe` column
records `D`, `W`, or `M`.

## Volume filter

```
volume_pass = Volume >= min_volume     (default min_volume = 2000)
```

For Weekly / Monthly K, `Volume` is the resampled (summed) period volume.

## Lookback bars

For each stock, only the most recent `lookback_bars` K-bars are checked
(`lookback_rank = 1` is the most recent bar). The results include bars where
`final_bull_signal` or `final_bear_signal` is True within that window, plus a
latest-summary table with one row per stock per signal direction.

---

## Excel export

The downloadable workbook contains seven sheets: `All_Data`, `Matching_Signals`,
`Bullish_Signals`, `Bearish_Signals`, `Latest_Summary`, `Failed_Downloads`, and
`Parameter_Settings`.

## Testing the sample stock list

`sample_stock_list.csv` contains the default symbols. Upload it in the sidebar (or
just click **Run Screening** with the default text-area list) to verify the full
download → resample → signal → display → export flow end to end.

---

*This tool is for stock research and screening only. It is not investment advice.*
