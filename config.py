"""大紅攻 / 大黑攻 多空三條件選股系統 — 中央設定檔。

策略以「大紅攻（Big Red Attack）/ 大黑攻（Big Black Attack）」均線為基礎。

本工具僅供股票研究與篩選參考，並不構成任何投資建議。
"""

from __future__ import annotations

from datetime import date, timedelta

APP_TITLE = "多頭 / 空頭 三條件選股系統（大紅攻 / 大黑攻）"
APP_DISCLAIMER = "本工具僅供股票研究與篩選參考，並不構成任何投資建議。"

# 預設股票清單（使用者未輸入時採用）。
DEFAULT_STOCK_LIST = [
    "2330.TW",
    "2317.TW",
    "2382.TW",
    "2474.TW",
    "6182.TWO",
]
DEFAULT_TEXT_STOCK_LIST = "\n".join(DEFAULT_STOCK_LIST)

# 策略預設值（刻意保持精簡）。
DEFAULT_MIN_VOLUME = 2000
DEFAULT_LOOKBACK_BARS = 10

# 外資 / 投信 連續買入預設值。
DEFAULT_CONSECUTIVE_BUY_DAYS = 3
ENABLE_INVESTOR_FLOW_DEFAULT = True

# UI 顯示標籤 -> 內部週期代碼。Timeframe 欄位使用 D / W / M。
TIMEFRAME_OPTIONS = {
    "日K": "D",
    "週K": "W",
    "月K": "M",
}
TIMEFRAME_LABELS = {code: label for label, code in TIMEFRAME_OPTIONS.items()}
DEFAULT_TIMEFRAME_LABEL = "日K"

# 訊號方向篩選選項。
DIRECTION_BOTH = "全部"
DIRECTION_BULLISH = "只看多頭"
DIRECTION_BEARISH = "只看空頭"
DIRECTION_OPTIONS = [DIRECTION_BOTH, DIRECTION_BULLISH, DIRECTION_BEARISH]

# 預設日期區間：近一年。
DEFAULT_START_DATE = date.today() - timedelta(days=365)
DEFAULT_END_DATE = date.today()

DEFAULT_PARAMETERS = {
    "start_date": DEFAULT_START_DATE,
    "end_date": DEFAULT_END_DATE,
    "analysis_timeframe": DEFAULT_TIMEFRAME_LABEL,
    "min_volume": DEFAULT_MIN_VOLUME,
    "lookback_bars": DEFAULT_LOOKBACK_BARS,
    "signal_direction_filter": DIRECTION_BOTH,
    "enable_investor_flow": ENABLE_INVESTOR_FLOW_DEFAULT,
    "consecutive_buy_days": DEFAULT_CONSECUTIVE_BUY_DAYS,
    "require_foreign_buy": False,
    "require_trust_buy": False,
}

# 正規化後的長格式 OHLCV 欄位。
REQUIRED_OHLCV_COLUMNS = [
    "Date",
    "StockCode",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]

# 符合訊號結果表的欄位順序。
RESULT_COLUMNS = [
    # 基本欄位
    "Date",
    "Timeframe",
    "StockCode",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "prev_close",
    # 攻擊欄位
    "red_attack_success",
    "red_attack_failed",
    "black_attack_success",
    "black_attack_failed",
    "attack_type",
    "attack_result",
    "attack_direction",
    "signal_summary",
    # 均線欄位
    "red_line",
    "black_line",
    # 多頭欄位
    "bull_A_window",
    "bull_B_window",
    "bull_C_window",
    "bull_score",
    "bull_signal",
    "final_bull_signal",
    # 空頭欄位
    "bear_A_window",
    "bear_B_window",
    "bear_C_window",
    "bear_score",
    "bear_signal",
    "final_bear_signal",
    # 法人連買欄位
    "foreign_buy_streak",
    "foreign_buy_streak_ok",
    "trust_buy_streak",
    "trust_buy_streak_ok",
    # 篩選欄位
    "volume_pass",
    "lookback_rank",
]

# 最新摘要表欄位順序。
SUMMARY_COLUMNS = [
    "StockCode",
    "LatestSignalDate",
    "Timeframe",
    "SignalDirection",
    "BullScore",
    "BearScore",
    "LatestOpen",
    "LatestHigh",
    "LatestLow",
    "LatestClose",
    "LatestVolume",
    "ForeignBuyStreak",
    "ForeignBuyStreakOK",
    "TrustBuyStreak",
    "TrustBuyStreakOK",
    "LatestSignalSummary",
]

# ---------------------------------------------------------------------------
# 顯示用繁體中文標籤（僅用於畫面與 Excel；內部欄位名稱維持英文以確保運算穩定）
# ---------------------------------------------------------------------------
DISPLAY_COLUMN_LABELS = {
    # 基本
    "Date": "日期",
    "Timeframe": "週期",
    "StockCode": "股票代號",
    "Open": "開盤",
    "High": "最高",
    "Low": "最低",
    "Close": "收盤",
    "Volume": "成交量",
    "prev_close": "前一根收盤",
    # 攻擊
    "red_attack_success": "大紅攻成功",
    "red_attack_failed": "大紅攻失敗",
    "black_attack_success": "大黑攻成功",
    "black_attack_failed": "大黑攻失敗",
    "attack_type": "攻擊類型",
    "attack_result": "攻擊結果",
    "attack_direction": "攻擊方向",
    "signal_summary": "訊號摘要",
    # 均線
    "red_line": "紅線",
    "black_line": "黑線",
    "red_line_raw": "紅線原始值",
    "black_line_raw": "黑線原始值",
    # 多頭
    "bull_A_daily": "多頭A當根(大紅攻)",
    "bull_B_break_black_daily": "多頭B當根(突破黑線)",
    "bull_C_retest_red_line_daily": "多頭C當根(回測紅線)",
    "bull_C_retest_black_line_daily": "多頭C當根(回測黑線)",
    "bull_C_retest_support_daily": "多頭C當根(回測支撐)",
    "bull_A_window": "多頭A(大紅攻出現)",
    "bull_B_window": "多頭B(突破黑線)",
    "bull_C_window": "多頭C(回測支撐守住)",
    "bull_score": "多頭分數",
    "bull_signal": "多頭訊號",
    "final_bull_signal": "最終多頭訊號",
    # 空頭
    "bear_A_daily": "空頭A當根(大黑攻)",
    "bear_B_break_red_daily": "空頭B當根(跌破紅線)",
    "bear_C_retest_red_line_daily": "空頭C當根(回測紅線)",
    "bear_C_retest_black_line_daily": "空頭C當根(回測黑線)",
    "bear_C_retest_resistance_daily": "空頭C當根(回測反壓)",
    "bear_A_window": "空頭A(大黑攻出現)",
    "bear_B_window": "空頭B(跌破紅線)",
    "bear_C_window": "空頭C(反壓回測失敗)",
    "bear_score": "空頭分數",
    "bear_signal": "空頭訊號",
    "final_bear_signal": "最終空頭訊號",
    # 法人連買
    "foreign_buy_streak": "外資連買天數",
    "foreign_buy_streak_ok": "外資連買達標",
    "trust_buy_streak": "投信連買天數",
    "trust_buy_streak_ok": "投信連買達標",
    # 篩選
    "volume_pass": "量能達標",
    "lookback_rank": "回看排名",
    "in_lookback_window": "在回看區間內",
    # 摘要表
    "LatestSignalDate": "最新訊號日期",
    "SignalDirection": "訊號方向",
    "BullScore": "多頭分數",
    "BearScore": "空頭分數",
    "LatestOpen": "最新開盤",
    "LatestHigh": "最新最高",
    "LatestLow": "最新最低",
    "LatestClose": "最新收盤",
    "LatestVolume": "最新成交量",
    "ForeignBuyStreak": "外資連買天數",
    "ForeignBuyStreakOK": "外資連買達標",
    "TrustBuyStreak": "投信連買天數",
    "TrustBuyStreakOK": "投信連買達標",
    "LatestSignalSummary": "最新訊號說明",
}

# 字串型欄位的值翻譯（畫面與 Excel 顯示用）。
VALUE_LABELS = {
    "attack_type": {
        "Big Red Attack": "大紅攻",
        "Big Black Attack": "大黑攻",
        "No Attack": "無攻擊",
    },
    "attack_result": {"Success": "成功", "Failed": "失敗", "None": "無"},
    "attack_direction": {"Bullish": "偏多", "Bearish": "偏空", "None": "無"},
    "signal_summary": {
        "Big Red Attack Success": "大紅攻成功",
        "Big Red Attack Failed": "大紅攻失敗",
        "Big Black Attack Success": "大黑攻成功",
        "Big Black Attack Failed": "大黑攻失敗",
        "No Attack": "無攻擊",
    },
    "SignalDirection": {"Bullish": "多頭", "Bearish": "空頭"},
    "LatestSignalSummary": {
        "Bullish Three-Condition Method": "多頭三條件法",
        "Bearish Three-Condition Method": "空頭三條件法",
        "Both Bullish and Bearish Signals": "多空訊號同時出現",
    },
}

# 布林值顯示文字。
BOOL_TRUE_LABEL = "是"
BOOL_FALSE_LABEL = "否"

# Excel 工作表名稱（繁體中文）。
EXCEL_SHEET_NAMES = {
    "all_data": "全部資料",
    "matching": "符合訊號",
    "bullish": "多頭訊號",
    "bearish": "空頭訊號",
    "summary": "最新摘要",
    "failed": "下載失敗清單",
    "params": "參數設定",
}

# Excel 參數設定表的中文參數名稱。
PARAMETER_LABELS = {
    "start_date": "起始日期",
    "end_date": "結束日期",
    "analysis_timeframe": "分析週期",
    "min_volume": "最低成交量",
    "lookback_bars": "回看根數",
    "signal_direction_filter": "訊號方向篩選",
    "enable_investor_flow": "啟用外資/投信連買",
    "consecutive_buy_days": "連續買入天數",
    "require_foreign_buy": "需外資連買達標",
    "require_trust_buy": "需投信連買達標",
}
