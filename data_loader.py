"""Data loading and resampling utilities for the stock screener.

Responsibilities
----------------
- parse_stock_list           : parse a text area (one symbol per line) into codes
- load_stock_list_from_upload: read a CSV upload that must contain a StockCode column
- download_stock_data        : download daily OHLCV via yfinance, robust to failures
- normalize_yfinance_data    : convert raw yfinance output into the long-format schema
- resample_ohlcv             : resample daily OHLCV into Daily / Weekly / Monthly K

Only DAILY data is downloaded. Weekly / Monthly bars are produced by resampling the
daily data per StockCode — never downloaded directly from yfinance.
"""

from __future__ import annotations

import contextlib
import logging
from io import StringIO
from typing import Callable, Iterable

import pandas as pd
import requests
import urllib3
import yfinance as yf

from config import REQUIRED_OHLCV_COLUMNS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_YFINANCE_LOGGER_NAMES = ("yfinance", "peewee")


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    """Drop duplicate symbols while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _normalize_token(token: str) -> str:
    return str(token).strip().upper()


def parse_stock_list(text: str) -> list[str]:
    """Parse text-area input (one symbol per line) into a deduplicated list.

    Commas are also treated as separators. Empty lines and blanks are ignored.
    Defensive: returns an empty list for None or empty input.
    """
    if not text:
        return []

    tokens: list[str] = []
    for line in str(text).splitlines():
        tokens.extend(part for part in line.replace(",", "\n").splitlines())

    cleaned = [_normalize_token(token) for token in tokens]
    return _dedupe_preserve_order([token for token in cleaned if token])


def load_stock_list_from_upload(uploaded_file) -> list[str]:
    """Read a CSV upload that must contain a 'StockCode' column.

    Raises ValueError if the file cannot be parsed or the column is missing.
    Returns a deduplicated list of symbols (may be empty).
    """
    if uploaded_file is None:
        return []

    try:
        upload_df = pd.read_csv(uploaded_file)
    except Exception as exc:  # malformed CSV, wrong encoding, etc.
        raise ValueError(f"Could not read the uploaded CSV: {exc}") from exc

    if "StockCode" not in upload_df.columns:
        raise ValueError("The uploaded CSV must contain a 'StockCode' column.")

    codes = [_normalize_token(value) for value in upload_df["StockCode"].dropna().tolist()]
    return _dedupe_preserve_order([code for code in codes if code])


def normalize_yfinance_data(df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """Convert a raw yfinance DataFrame into the project's long-format schema.

    Handles both flat and MultiIndex column layouts. Returns an empty frame with
    the expected columns when the input is empty or lacks OHLCV columns.
    """
    empty = pd.DataFrame(columns=REQUIRED_OHLCV_COLUMNS)
    if df is None or len(df) == 0:
        return empty

    normalized = df.copy()

    # yfinance may return MultiIndex columns (e.g. when group_by="ticker").
    if isinstance(normalized.columns, pd.MultiIndex):
        ticker_level = normalized.columns.get_level_values(0)
        price_level = normalized.columns.get_level_values(-1)
        if stock_code in set(ticker_level):
            normalized = normalized.xs(stock_code, axis=1, level=0, drop_level=True)
        elif stock_code in set(price_level):
            normalized = normalized.xs(stock_code, axis=1, level=-1, drop_level=True)
        else:
            normalized.columns = [
                "_".join(str(part) for part in column if part)
                for column in normalized.columns.to_flat_index()
            ]

    normalized = normalized.reset_index()

    if "Datetime" in normalized.columns and "Date" not in normalized.columns:
        normalized = normalized.rename(columns={"Datetime": "Date"})
    if "Date" not in normalized.columns and len(normalized.columns) > 0:
        normalized = normalized.rename(columns={normalized.columns[0]: "Date"})

    price_columns = {"Open", "High", "Low", "Close", "Volume"}
    if not price_columns.issubset(normalized.columns):
        return empty

    normalized = normalized[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    normalized["Date"] = pd.to_datetime(
        normalized["Date"], errors="coerce", utc=True
    ).dt.tz_localize(None)

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["StockCode"] = stock_code
    normalized = (
        normalized.dropna(subset=["Date"])
        .drop_duplicates(subset=["Date"])
        .dropna(subset=["Open", "High", "Low", "Close"], how="any")
    )
    if normalized.empty:
        return empty
    return normalized[REQUIRED_OHLCV_COLUMNS].sort_values("Date").reset_index(drop=True)


def _download_single(symbol: str, start_date, end_date) -> pd.DataFrame:
    """Download one symbol's daily OHLCV, silencing yfinance noise."""
    # yfinance treats `end` as exclusive; add a day so the chosen end date is included.
    end_exclusive = (pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)).date()

    loggers = [logging.getLogger(name) for name in _YFINANCE_LOGGER_NAMES]
    previous_levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(StringIO()), contextlib.redirect_stderr(StringIO()):
            return yf.download(
                symbol,
                start=pd.Timestamp(start_date).date(),
                end=end_exclusive,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
    finally:
        for logger, level in zip(loggers, previous_levels):
            logger.setLevel(level)


def download_stock_data(
    stock_codes: list[str],
    start_date,
    end_date,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Download daily OHLCV data for each symbol independently.

    Returns (combined_long_format_df, success_list, failed_list). If one symbol
    fails (exception, empty data, or insufficient data) it is added to failed_list
    and processing continues with the others.
    """
    success_list: list[str] = []
    failed_list: list[str] = []
    frames: list[pd.DataFrame] = []

    deduped = _dedupe_preserve_order(_normalize_token(code) for code in (stock_codes or []))
    total = len(deduped)
    if total == 0:
        return pd.DataFrame(columns=REQUIRED_OHLCV_COLUMNS), success_list, failed_list

    for index, symbol in enumerate(deduped, start=1):
        if progress_callback is not None:
            progress_callback((index - 1) / total, f"Downloading {symbol} ({index}/{total})...")

        try:
            raw = _download_single(symbol, start_date, end_date)
            normalized = normalize_yfinance_data(raw, stock_code=symbol)
        except Exception:
            normalized = pd.DataFrame(columns=REQUIRED_OHLCV_COLUMNS)

        # Need at least 2 bars so prev_close exists for at least one row.
        if normalized.empty or len(normalized) < 2:
            failed_list.append(symbol)
        else:
            frames.append(normalized)
            success_list.append(symbol)

    if progress_callback is not None:
        progress_callback(1.0, f"Downloaded {len(success_list)}/{total} symbols.")

    if not frames:
        return pd.DataFrame(columns=REQUIRED_OHLCV_COLUMNS), success_list, failed_list

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["StockCode", "Date"]).reset_index(drop=True)
    return combined, success_list, failed_list


def _resample_single_stock(stock_df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample one stock's daily data; Date = actual last trading day in each period."""
    stock_df = stock_df.sort_values("Date").copy()
    stock_df["TradeDate"] = stock_df["Date"]

    resampled = (
        stock_df.set_index("Date")
        .resample(rule, label="right", closed="right")
        .agg(
            {
                "TradeDate": "max",  # actual last trading day in the period
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .reset_index(drop=True)
    )

    resampled = resampled.dropna(subset=["Open", "High", "Low", "Close"], how="all")
    if resampled.empty:
        return pd.DataFrame(columns=REQUIRED_OHLCV_COLUMNS)

    resampled = resampled.rename(columns={"TradeDate": "Date"})
    resampled["StockCode"] = stock_df["StockCode"].iloc[0]
    resampled["Date"] = pd.to_datetime(resampled["Date"], errors="coerce")
    return (
        resampled.dropna(subset=["Date"])[REQUIRED_OHLCV_COLUMNS]
        .reset_index(drop=True)
    )


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Convert daily OHLCV into the selected timeframe and add a Timeframe column.

    timeframe: 'D' (Daily), 'W' (Weekly), or 'M' (Monthly).
    Each StockCode is resampled separately; stocks are never mixed.
    """
    columns_with_tf = [*REQUIRED_OHLCV_COLUMNS, "Timeframe"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns_with_tf)

    missing = set(REQUIRED_OHLCV_COLUMNS).difference(df.columns)
    if missing:
        raise ValueError(f"Input data is missing required columns: {sorted(missing)}")

    timeframe = str(timeframe).upper()
    if timeframe not in {"D", "W", "M"}:
        raise ValueError("timeframe must be one of: D, W, M")

    prepared = df[REQUIRED_OHLCV_COLUMNS].copy()
    prepared["Date"] = pd.to_datetime(prepared["Date"], errors="coerce")
    prepared = (
        prepared.dropna(subset=["Date"])
        .sort_values(["StockCode", "Date"])
        .reset_index(drop=True)
    )

    if timeframe == "D":
        daily = prepared.copy()
        daily["Timeframe"] = "D"
        return daily.reset_index(drop=True)

    resample_rule = {"W": "W-FRI", "M": "ME"}[timeframe]
    frames: list[pd.DataFrame] = []
    for _, stock_df in prepared.groupby("StockCode", sort=False):
        stock_resampled = _resample_single_stock(stock_df, resample_rule)
        if not stock_resampled.empty:
            frames.append(stock_resampled)

    if not frames:
        return pd.DataFrame(columns=columns_with_tf)

    output = pd.concat(frames, ignore_index=True)
    output["Timeframe"] = timeframe
    return output.sort_values(["StockCode", "Date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 外資 / 投信 法人買賣超資料（台股，公開資料）
# ---------------------------------------------------------------------------
_INVESTOR_COLUMNS = ["Date", "BaseCode", "foreign_net", "trust_net"]


def _to_int(value) -> int:
    """Parse a public-data integer string that may contain commas, parens, or dashes."""
    text = str(value).strip().replace(",", "").replace("+", "")
    if text in {"", "nan", "NaN", "None", "--", "-", "—"}:
        return 0
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _get_with_ssl_fallback(url: str) -> requests.Response:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        return response
    except requests.exceptions.SSLError:
        response = requests.get(url, timeout=30, headers=headers, verify=False)
        response.raise_for_status()
        return response


def _fetch_twse_investor_flow(trade_date: pd.Timestamp) -> pd.DataFrame:
    """Fetch one day of TWSE (上市) institutional net buy/sell (foreign / trust)."""
    url = (
        "https://www.twse.com.tw/rwd/zh/fund/T86"
        f"?date={trade_date.strftime('%Y%m%d')}&selectType=ALLBUT0999&response=json"
    )
    try:
        payload = _get_with_ssl_fallback(url).json()
    except Exception:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)

    if payload.get("stat") != "OK":
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)
    rows = payload.get("data") or []
    if not rows:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)

    frame = pd.DataFrame(rows)
    if frame.shape[1] < 11:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)
    code_series = frame.iloc[:, 0].astype(str).str.strip()
    if not code_series.str.fullmatch(r"\d{4}").any():
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)
    # TWSE T86: col 4 = foreign net (incl. dealer), col 10 = investment trust net.
    result = pd.DataFrame(
        {
            "Date": trade_date.normalize(),
            "BaseCode": code_series,
            "foreign_net": frame.iloc[:, 4].map(_to_int),
            "trust_net": frame.iloc[:, 10].map(_to_int),
        }
    )
    return result[result["BaseCode"].str.fullmatch(r"\d{4}", na=False)].reset_index(drop=True)


def _fetch_tpex_investor_flow(trade_date: pd.Timestamp) -> pd.DataFrame:
    """Fetch one day of TPEx (上櫃) institutional net buy/sell (foreign / trust)."""
    roc_date = f"{trade_date.year - 1911:03d}/{trade_date.month:02d}/{trade_date.day:02d}"
    url = (
        "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
        f"?l=zh-tw&d={roc_date}&o=json"
    )
    try:
        payload = _get_with_ssl_fallback(url).json()
    except Exception:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)

    tables = payload.get("tables") or []
    if not tables or not tables[0].get("data"):
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)

    frame = pd.DataFrame(tables[0]["data"])
    if frame.shape[1] < 14:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)
    code_series = frame.iloc[:, 0].astype(str).str.strip()
    if not code_series.str.fullmatch(r"\d{4}").any():
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)
    # TPEx schema: col 4 = foreign net (incl. dealer), col 13 = investment trust net.
    result = pd.DataFrame(
        {
            "Date": trade_date.normalize(),
            "BaseCode": code_series,
            "foreign_net": frame.iloc[:, 4].map(_to_int),
            "trust_net": frame.iloc[:, 13].map(_to_int),
        }
    )
    return result[result["BaseCode"].str.fullmatch(r"\d{4}", na=False)].reset_index(drop=True)


def download_investor_flow_data(
    stock_codes: list[str],
    end_date,
    lookback_days: int = 30,
    progress_callback: Callable[[float, str], None] | None = None,
) -> pd.DataFrame:
    """Download recent daily institutional net buy/sell data for Taiwan stocks.

    Returns daily rows [Date, BaseCode, foreign_net, trust_net]. Always defensive:
    on any failure it simply returns whatever (possibly empty) data it gathered, so
    the screener can continue without institutional flags.
    """
    base_codes = {
        str(code).split(".")[0].strip()
        for code in (stock_codes or [])
        if str(code).split(".")[0].strip().isdigit()
    }
    if not base_codes:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)

    end_ts = pd.Timestamp(end_date).normalize()
    start_ts = end_ts - pd.Timedelta(days=max(int(lookback_days), 5))
    trade_dates = list(pd.bdate_range(start_ts, end_ts))

    frames: list[pd.DataFrame] = []
    total = max(len(trade_dates), 1)
    for index, trade_date in enumerate(trade_dates, start=1):
        if progress_callback is not None:
            progress_callback(
                index / total,
                f"下載法人買賣超資料 {trade_date.date()} ({index}/{total})...",
            )
        twse_df = _fetch_twse_investor_flow(trade_date)
        if not twse_df.empty:
            frames.append(twse_df)
        tpex_df = _fetch_tpex_investor_flow(trade_date)
        if not tpex_df.empty:
            frames.append(tpex_df)

    if not frames:
        return pd.DataFrame(columns=_INVESTOR_COLUMNS)

    output = pd.concat(frames, ignore_index=True)
    output = output[output["BaseCode"].isin(base_codes)].copy()
    output = output.drop_duplicates(subset=["Date", "BaseCode"]).sort_values(["BaseCode", "Date"])
    return output.reset_index(drop=True)
