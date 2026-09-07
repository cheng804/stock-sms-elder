"""
stock_fetcher.py - 股票資料抓取模組

使用 yfinance 取得台股和美股的即時與歷史資料，
並提供簡易合理價分析。
"""

import re
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf
import pandas as pd


# ─────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────

def _normalize_stock_code(stock_code: str) -> str:
    """
    將輸入的股票代號正規化為 yfinance 可用的格式。

    - 純數字（台股）自動加上 .TW 後綴
    - 已有後綴者直接回傳
    - 美股英文字母直接回傳

    Args:
        stock_code: 使用者輸入的股票代號，例如 "2330"、"2330.TW"、"AAPL"

    Returns:
        正規化後的代號字串
    """
    stock_code = stock_code.strip().upper()
    if re.match(r"^\d{4,6}$", stock_code):
        return f"{stock_code}.TW"
    return stock_code


def _safe_float(value) -> Optional[float]:
    """安全地將值轉為 float，失敗回傳 None。"""
    try:
        v = float(value)
        return None if pd.isna(v) else round(v, 2)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────
#  公開 API
# ─────────────────────────────────────────

def get_stock_info(stock_code: str) -> dict:
    """
    取得股票即時資訊。

    Args:
        stock_code: 股票代號（台股輸入純數字即可，如 "2330"）

    Returns:
        dict 包含以下欄位：
            - success (bool)
            - code (str): 正規化代號
            - name (str): 公司名稱
            - price (float | None): 目前股價
            - change (float | None): 今日漲跌點數
            - change_percent (float | None): 今日漲跌幅 (%)
            - volume (int | None): 成交量
            - open (float | None): 開盤價
            - high (float | None): 今日最高
            - low (float | None): 今日最低
            - prev_close (float | None): 昨日收盤
            - market_cap (int | None): 市值
            - error (str): 錯誤訊息（success=False 時才有）
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        ticker = yf.Ticker(normalized)
        info = ticker.info

        # yfinance 有時回傳空 dict
        if not info or info.get("regularMarketPrice") is None:
            # 嘗試用歷史資料抓最新收盤價
            hist = ticker.history(period="2d")
            if hist.empty:
                return {
                    "success": False,
                    "code": normalized,
                    "error": f"找不到股票代號 {stock_code}，請確認是否正確。",
                }
            last_row = hist.iloc[-1]
            prev_row = hist.iloc[-2] if len(hist) > 1 else None
            price = _safe_float(last_row["Close"])
            prev_close = _safe_float(prev_row["Close"]) if prev_row is not None else None
            change = round(price - prev_close, 2) if price and prev_close else None
            change_pct = round(change / prev_close * 100, 2) if change and prev_close else None

            return {
                "success": True,
                "code": normalized,
                "name": info.get("shortName") or info.get("longName") or normalized,
                "price": price,
                "change": change,
                "change_percent": change_pct,
                "volume": int(last_row["Volume"]) if last_row["Volume"] else None,
                "open": _safe_float(last_row["Open"]),
                "high": _safe_float(last_row["High"]),
                "low": _safe_float(last_row["Low"]),
                "prev_close": prev_close,
                "market_cap": info.get("marketCap"),
            }

        price = _safe_float(info.get("regularMarketPrice"))
        prev_close = _safe_float(info.get("regularMarketPreviousClose"))
        change = round(price - prev_close, 2) if price and prev_close else None
        change_pct = _safe_float(info.get("regularMarketChangePercent"))
        if change_pct is not None:
            change_pct = round(change_pct, 2)

        return {
            "success": True,
            "code": normalized,
            "name": info.get("shortName") or info.get("longName") or normalized,
            "price": price,
            "change": change,
            "change_percent": change_pct,
            "volume": info.get("regularMarketVolume"),
            "open": _safe_float(info.get("regularMarketOpen")),
            "high": _safe_float(info.get("regularMarketDayHigh")),
            "low": _safe_float(info.get("regularMarketDayLow")),
            "prev_close": prev_close,
            "market_cap": info.get("marketCap"),
        }

    except Exception as e:
        return {
            "success": False,
            "code": normalized,
            "error": f"抓取 {stock_code} 資料時發生錯誤：{str(e)}",
        }


def get_stock_history(stock_code: str, days: int = 30) -> dict:
    """
    取得股票近期歷史資料。

    Args:
        stock_code: 股票代號
        days: 取幾天的歷史，預設 30

    Returns:
        dict 包含：
            - success (bool)
            - code (str)
            - dates (list[str])
            - closes (list[float])
            - highs (list[float])
            - lows (list[float])
            - volumes (list[int])
            - avg_price (float | None): 期間平均收盤價
            - error (str): 失敗時才有
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        ticker = yf.Ticker(normalized)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)  # 多抓幾天以防假日
        hist = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))

        if hist.empty:
            return {"success": False, "code": normalized, "error": "無歷史資料"}

        hist = hist.tail(days)
        closes = [_safe_float(v) for v in hist["Close"]]
        valid_closes = [c for c in closes if c is not None]
        avg_price = round(sum(valid_closes) / len(valid_closes), 2) if valid_closes else None

        return {
            "success": True,
            "code": normalized,
            "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
            "closes": closes,
            "highs": [_safe_float(v) for v in hist["High"]],
            "lows": [_safe_float(v) for v in hist["Low"]],
            "volumes": [int(v) if v else 0 for v in hist["Volume"]],
            "avg_price": avg_price,
        }

    except Exception as e:
        return {
            "success": False,
            "code": normalized,
            "error": f"抓取歷史資料失敗：{str(e)}",
        }


def calculate_fair_value(stock_code: str) -> dict:
    """
    簡易合理價分析。

    計算邏輯：
    1. 取得近 30 天和近 60 天的平均收盤價
    2. 若目前股價低於 30 日均價 5% 以上 → 便宜
       若高於 30 日均價 5% 以上 → 偏貴
       否則 → 合理

    Args:
        stock_code: 股票代號

    Returns:
        dict 包含：
            - success (bool)
            - code (str)
            - current_price (float | None)
            - avg_30d (float | None)
            - avg_60d (float | None)
            - suggestion (str): "便宜" | "合理" | "偏貴" | "無法判斷"
            - pe_ratio (float | None)
            - error (str): 失敗時才有
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        # 取即時價
        info_data = get_stock_info(stock_code)
        if not info_data.get("success"):
            return {"success": False, "code": normalized, "error": info_data.get("error", "未知錯誤")}

        current_price = info_data.get("price")

        # 取 60 天歷史
        hist_60 = get_stock_history(stock_code, days=60)
        hist_30 = get_stock_history(stock_code, days=30)

        avg_30d = hist_30.get("avg_price") if hist_30.get("success") else None
        avg_60d = hist_60.get("avg_price") if hist_60.get("success") else None

        # 合理價判斷
        suggestion = "無法判斷"
        if current_price and avg_30d:
            diff_pct = (current_price - avg_30d) / avg_30d * 100
            if diff_pct < -5:
                suggestion = "便宜"
            elif diff_pct > 5:
                suggestion = "偏貴"
            else:
                suggestion = "合理"

        # PE ratio
        ticker = yf.Ticker(normalized)
        pe_ratio = _safe_float(ticker.info.get("trailingPE"))

        return {
            "success": True,
            "code": normalized,
            "current_price": current_price,
            "avg_30d": avg_30d,
            "avg_60d": avg_60d,
            "suggestion": suggestion,
            "pe_ratio": pe_ratio,
        }

    except Exception as e:
        return {
            "success": False,
            "code": normalized,
            "error": f"合理價分析失敗：{str(e)}",
        }
