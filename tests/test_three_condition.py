"""Tests for the Bullish / Bearish Three-Condition Stock Screener.

Covers the validation examples from the specification (section 20), the attack
line logic, resampling rules, and defensive behaviour.

Run with:
    python -m pytest tests/test_three_condition.py
or:
    python -m unittest tests.test_three_condition
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import parse_stock_list, resample_ohlcv  # noqa: E402
from signal_engine import (  # noqa: E402
    add_attack_lines,
    add_attack_signals,
    add_prev_close,
    attach_investor_flow_flags,
    run_signal_pipeline,
)


def _two_bar_frame(prev_close, open_, close, stock="TEST"):
    """Build a 2-bar frame whose second bar has the given prev_close/Open/Close.

    The first bar's Close == prev_close so that the second bar's prev_close matches.
    """
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "StockCode": [stock, stock],
            "Open": [prev_close, open_],
            "High": [max(prev_close, open_, close) + 1, max(open_, close) + 1],
            "Low": [min(prev_close, open_, close) - 1, min(open_, close) - 1],
            "Close": [prev_close, close],
            "Volume": [10_000, 10_000],
        }
    )


class AttackSignalTests(unittest.TestCase):
    def _signal_row(self, prev_close, open_, close):
        df = _two_bar_frame(prev_close, open_, close)
        df = add_prev_close(df)
        df = add_attack_signals(df)
        df = add_attack_lines(df)
        return df.iloc[-1]

    def test_20_1_big_red_attack_success(self):
        row = self._signal_row(prev_close=100, open_=105, close=110)
        self.assertTrue(row["red_attack_success"])
        self.assertFalse(row["red_attack_failed"])
        self.assertFalse(row["black_attack_success"])
        self.assertFalse(row["black_attack_failed"])
        self.assertEqual(row["red_line_raw"], 100)
        self.assertTrue(np.isnan(row["black_line_raw"]))
        self.assertEqual(row["signal_summary"], "Big Red Attack Success")

    def test_20_2_big_red_attack_failed_is_not_black(self):
        row = self._signal_row(prev_close=100, open_=105, close=98)
        self.assertFalse(row["red_attack_success"])
        self.assertTrue(row["red_attack_failed"])
        self.assertFalse(row["black_attack_success"])  # MUST NOT convert to black
        self.assertFalse(row["black_attack_failed"])
        self.assertTrue(np.isnan(row["red_line_raw"]))
        self.assertTrue(np.isnan(row["black_line_raw"]))
        self.assertEqual(row["attack_type"], "Big Red Attack")
        self.assertEqual(row["attack_direction"], "Bullish")
        self.assertEqual(row["signal_summary"], "Big Red Attack Failed")

    def test_20_3_big_black_attack_success(self):
        row = self._signal_row(prev_close=100, open_=95, close=90)
        self.assertFalse(row["red_attack_success"])
        self.assertFalse(row["red_attack_failed"])
        self.assertTrue(row["black_attack_success"])
        self.assertFalse(row["black_attack_failed"])
        self.assertTrue(np.isnan(row["red_line_raw"]))
        self.assertEqual(row["black_line_raw"], 100)
        self.assertEqual(row["signal_summary"], "Big Black Attack Success")

    def test_20_4_big_black_attack_failed_is_not_red(self):
        row = self._signal_row(prev_close=100, open_=95, close=103)
        self.assertFalse(row["red_attack_success"])  # MUST NOT convert to red
        self.assertFalse(row["red_attack_failed"])
        self.assertFalse(row["black_attack_success"])
        self.assertTrue(row["black_attack_failed"])
        self.assertTrue(np.isnan(row["red_line_raw"]))
        self.assertTrue(np.isnan(row["black_line_raw"]))
        self.assertEqual(row["attack_type"], "Big Black Attack")
        self.assertEqual(row["attack_direction"], "Bearish")
        self.assertEqual(row["signal_summary"], "Big Black Attack Failed")

    def test_open_equals_prev_close_is_no_attack(self):
        row = self._signal_row(prev_close=100, open_=100, close=105)
        self.assertFalse(row["red_attack_success"])
        self.assertFalse(row["black_attack_success"])
        self.assertEqual(row["attack_type"], "No Attack")
        self.assertEqual(row["attack_result"], "None")
        self.assertEqual(row["attack_direction"], "None")
        self.assertEqual(row["signal_summary"], "No Attack")


class ThreeConditionTests(unittest.TestCase):
    def test_20_5_bullish_three_condition(self):
        """A (red success) + B (break above black_line) + C (support retest) -> bull_signal."""
        # Sequence engineered so all three bullish conditions occur within lookback.
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(
                    ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
                ),
                "StockCode": ["AAA"] * 5,
                #            bar0  bar1(black succ) bar2(red succ) bar3(break+retest)  bar4
                "Open": [100, 99, 96, 99, 101],
                "High": [101, 100, 103, 103, 104],
                "Low": [99, 95, 95, 97, 100],
                "Close": [100, 96, 102, 101, 103],
                "Volume": [10_000] * 5,
            }
        )
        out = run_signal_pipeline(df, {"lookback_bars": 10, "min_volume": 2000})
        last = out.iloc[-1]
        self.assertGreaterEqual(last["bull_score"], 2)
        self.assertTrue(last["bull_signal"])
        self.assertTrue(last["final_bull_signal"])

    def test_20_6_bearish_three_condition(self):
        """A (black success) + B (break below red_line) + C (resistance retest) -> bear_signal."""
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(
                    ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
                ),
                "StockCode": ["BBB"] * 5,
                #            bar0  bar1(red succ)  bar2(black succ) bar3(break+retest) bar4
                "Open": [100, 101, 104, 101, 99],
                "High": [101, 105, 105, 103, 100],
                "Low": [99, 100, 97, 97, 96],
                "Close": [100, 104, 98, 99, 97],
                "Volume": [10_000] * 5,
            }
        )
        out = run_signal_pipeline(df, {"lookback_bars": 10, "min_volume": 2000})
        last = out.iloc[-1]
        self.assertGreaterEqual(last["bear_score"], 2)
        self.assertTrue(last["bear_signal"])
        self.assertTrue(last["final_bear_signal"])

    def test_volume_filter_blocks_final_signal(self):
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                "StockCode": ["CCC"] * 3,
                "Open": [100, 99, 96],
                "High": [101, 100, 103],
                "Low": [99, 95, 95],
                "Close": [100, 96, 102],
                "Volume": [10, 10, 10],  # below min_volume
            }
        )
        out = run_signal_pipeline(df, {"lookback_bars": 10, "min_volume": 2000})
        self.assertFalse(out["volume_pass"].any())
        self.assertFalse(out["final_bull_signal"].any())
        self.assertFalse(out["final_bear_signal"].any())


class ResampleAndDefensiveTests(unittest.TestCase):
    def test_weekly_resample_rules(self):
        daily = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),  # Mon-Wed
                "StockCode": ["X.TW"] * 3,
                "Open": [100, 102, 101],
                "High": [105, 108, 107],
                "Low": [99, 101, 100],
                "Close": [103, 107, 106],
                "Volume": [1000, 2000, 1500],
            }
        )
        weekly = resample_ohlcv(daily, "W")
        self.assertEqual(len(weekly), 1)
        row = weekly.iloc[0]
        self.assertEqual(row["Open"], 100)              # first open
        self.assertEqual(row["High"], 108)              # max high
        self.assertEqual(row["Low"], 99)                # min low
        self.assertEqual(row["Close"], 106)             # last close
        self.assertEqual(row["Volume"], 4500)           # summed volume
        self.assertEqual(row["Date"], pd.Timestamp("2026-01-07"))  # last trading day
        self.assertEqual(row["Timeframe"], "W")

    def test_resample_keeps_stocks_separate(self):
        daily = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05", "2026-01-06"] * 2),
                "StockCode": ["A.TW", "A.TW", "B.TW", "B.TW"],
                "Open": [10, 11, 50, 51],
                "High": [12, 13, 52, 53],
                "Low": [9, 10, 49, 50],
                "Close": [11, 12, 51, 52],
                "Volume": [100, 200, 300, 400],
            }
        )
        monthly = resample_ohlcv(daily, "M")
        self.assertEqual(set(monthly["StockCode"]), {"A.TW", "B.TW"})
        a = monthly[monthly["StockCode"] == "A.TW"].iloc[0]
        self.assertEqual(a["Open"], 10)
        self.assertEqual(a["Close"], 12)
        self.assertEqual(a["Volume"], 300)

    def test_parse_stock_list_handles_duplicates_and_blanks(self):
        codes = parse_stock_list("2330.TW\n\n2330.tw , 2317.TW\n   \n6182.TWO")
        self.assertEqual(codes, ["2330.TW", "2317.TW", "6182.TWO"])

    def test_parse_stock_list_empty(self):
        self.assertEqual(parse_stock_list(""), [])
        self.assertEqual(parse_stock_list(None), [])

    def test_empty_pipeline_does_not_crash(self):
        out = run_signal_pipeline(pd.DataFrame(), {"lookback_bars": 10, "min_volume": 2000})
        self.assertTrue(out.empty)

    def test_single_bar_has_no_prev_close_signal(self):
        df = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-01"]),
                "StockCode": ["Z"],
                "Open": [100],
                "High": [101],
                "Low": [99],
                "Close": [100],
                "Volume": [10_000],
            }
        )
        out = run_signal_pipeline(df, {"lookback_bars": 10, "min_volume": 2000})
        self.assertFalse(out["red_attack_success"].any())
        self.assertFalse(out["black_attack_success"].any())
        self.assertEqual(out.iloc[0]["attack_type"], "No Attack")


class InvestorFlowTests(unittest.TestCase):
    def _bars(self, dates, stock="2330.TW"):
        n = len(dates)
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(dates),
                "StockCode": [stock] * n,
                "Open": [100] * n,
                "High": [101] * n,
                "Low": [99] * n,
                "Close": [100] * n,
                "Volume": [10_000] * n,
            }
        )

    def test_foreign_and_trust_consecutive_buy_streak_meets_threshold(self):
        bars = self._bars(["2026-01-07"])  # latest bar after 3 buy days
        flow = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "BaseCode": ["2330"] * 3,
                "foreign_net": [10, 20, 30],   # 3 consecutive net-buy days
                "trust_net": [5, 5, 5],        # 3 consecutive net-buy days
            }
        )
        out = attach_investor_flow_flags(bars, flow, consecutive_days=3)
        row = out.iloc[0]
        self.assertEqual(row["foreign_buy_streak"], 3)
        self.assertEqual(row["trust_buy_streak"], 3)
        self.assertTrue(row["foreign_buy_streak_ok"])
        self.assertTrue(row["trust_buy_streak_ok"])

    def test_streak_resets_on_sell_day_and_misses_threshold(self):
        bars = self._bars(["2026-01-07"])
        flow = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "BaseCode": ["2330"] * 3,
                "foreign_net": [10, -5, 20],   # sell day resets streak -> latest streak = 1
                "trust_net": [5, 5, 5],
            }
        )
        out = attach_investor_flow_flags(bars, flow, consecutive_days=3)
        row = out.iloc[0]
        self.assertEqual(row["foreign_buy_streak"], 1)
        self.assertFalse(row["foreign_buy_streak_ok"])
        self.assertTrue(row["trust_buy_streak_ok"])

    def test_empty_flow_yields_false_flags_without_crashing(self):
        bars = self._bars(["2026-01-07", "2026-01-08"])
        out = attach_investor_flow_flags(bars, pd.DataFrame(), consecutive_days=3)
        self.assertEqual(list(out["foreign_buy_streak"]), [0, 0])
        self.assertFalse(out["foreign_buy_streak_ok"].any())
        self.assertFalse(out["trust_buy_streak_ok"].any())

    def test_non_taiwan_symbol_gets_false_flags(self):
        bars = self._bars(["2026-01-07"], stock="AAPL")
        flow = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "BaseCode": ["2330"] * 3,
                "foreign_net": [10, 20, 30],
                "trust_net": [5, 5, 5],
            }
        )
        out = attach_investor_flow_flags(bars, flow, consecutive_days=3)
        self.assertEqual(out.iloc[0]["foreign_buy_streak"], 0)
        self.assertFalse(out.iloc[0]["foreign_buy_streak_ok"])


if __name__ == "__main__":
    unittest.main()
