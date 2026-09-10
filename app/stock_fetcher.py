"""
stock_fetcher.py - 股票資料抓取模組

使用 yfinance 取得台股和美股的即時與歷史資料。
使用 curl_cffi 模擬瀏覽器，避免被 Yahoo Finance 封鎖（HTTP 401/429）。
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf
import pandas as pd
import requests as req
from app.stock_name_map import get_stock_name

# 抑制 yfinance 的 WARNING/ERROR log（404、401 等）
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# 使用 curl_cffi 模擬 Chrome 瀏覽器，避免雲端環境被 Yahoo Finance 封鎖
try:
    from curl_cffi import requests as curl_requests
    _SESSION = curl_requests.Session(impersonate="chrome")
except ImportError:
    _SESSION = None

# 中文名稱快取（避免重複打 API）
_NAME_CACHE: dict = {}


def _fetch_chinese_name(code: str) -> str:
    """
    從 TWSE 即時報價 API 取得中文公司名稱。
    分別查上市(tse)和上櫃(otc)。
    """
    if code in _NAME_CACHE:
        return _NAME_CACHE[code]

    for prefix in ["tse", "otc"]:
        try:
            ex_ch = f"{prefix}_{code}.tw"
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
            r = req.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            msg_array = data.get("msgArray", [])
            if msg_array:
                name = msg_array[0].get("n", "")
                if name:
                    _NAME_CACHE[code] = name
                    return name
        except Exception:
            pass

    return ""


def _normalize_stock_code(stock_code: str) -> str:
    """台股純數字或數字+英文字母（如00991A）自動加 .TW 後綴"""
    stock_code = stock_code.strip().upper()
    if re.match(r"^\d{4,6}[A-Z]?$", stock_code):
        return f"{stock_code}.TW"
    return stock_code


def _try_get_ticker(normalized: str):
    """
    嘗試建立 Ticker，若 .TW 查無資料自動改試 .TWO（上櫃）。
    回傳 (ticker, normalized_code)
    """
    ticker = _make_ticker(normalized)
    try:
        hist = ticker.history(period="1d")
        if not hist.empty:
            return ticker, normalized
    except Exception:
        pass

    # 若是 .TW 結尾，改試 .TWO
    if normalized.endswith(".TW") and not normalized.endswith(".TWO"):
        two_code = normalized[:-3] + ".TWO"
        ticker2 = _make_ticker(two_code)
        try:
            hist2 = ticker2.history(period="1d")
            if not hist2.empty:
                return ticker2, two_code
        except Exception:
            pass

    return ticker, normalized


def _safe_float(value) -> Optional[float]:
    """安全地將值轉為 float，失敗回傳 None。"""
    try:
        v = float(value)
        return None if pd.isna(v) else round(v, 2)
    except (TypeError, ValueError):
        return None


def _get_name(info: dict, normalized: str) -> str:
    """取公司名稱：離線對應表 → 即時爬取中文名 → yfinance 英文名 → 代號"""
    code = normalized.replace(".TWO", "").replace(".TW", "")

    # 1. 離線對應表（最快）
    chinese_name = get_stock_name(code)
    if chinese_name:
        return chinese_name

    # 2. 即時爬取中文名
    fetched_name = _fetch_chinese_name(code)
    if fetched_name:
        return fetched_name

    # 3. yfinance 英文名（太長或純英文就用代號）
    name = info.get("shortName") or info.get("longName") or ""
    if name and not (len(name) > 12 or name.replace(" ", "").replace(".", "").isascii()):
        return name

    return code

def _make_ticker(normalized: str) -> yf.Ticker:
    """建立 yf.Ticker，帶入 curl_cffi session。"""
    if _SESSION is not None:
        return yf.Ticker(normalized, session=_SESSION)
    return yf.Ticker(normalized)


def get_stock_info(stock_code: str) -> dict:
    """
    取得股票即時資訊。

    Args:
        stock_code: 股票代號（台股輸入純數字即可，如 "2330"）

    Returns:
        dict 包含 success, code, name, price, change, change_percent,
        volume, open, high, low, prev_close, market_cap
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        ticker, normalized = _try_get_ticker(normalized)
        info = ticker.info

        if not info or info.get("regularMarketPrice") is None:
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
                "name": _get_name(info, normalized),
                "price": price,
                "change": change,
                "change_percent": change_pct,
                "volume": int(last_row["Volume"]) if last_row["Volume"] else None,
                "open": _safe_float(last_row["Open"]),
                "high": _safe_float(last_row["High"]),
                "low": _safe_float(last_row["Low"]),
                "prev_close": prev_close,
                "market_cap": info.get("marketCap"),
                "is_prev_close": True,  # 標示這是前日收盤價
            }

        price = _safe_float(info.get("regularMarketPrice"))
        prev_close = _safe_float(info.get("regularMarketPreviousClose"))
        # 優先用 API 的漲跌，若沒有就自己算
        change = _safe_float(info.get("regularMarketChange"))
        if change is None and price and prev_close:
            change = round(price - prev_close, 2)
        elif change is not None:
            change = round(change, 2)
        # 漲跌幅
        change_pct = _safe_float(info.get("regularMarketChangePercent"))
        if change_pct is None and change and prev_close:
            change_pct = round(change / prev_close * 100, 2)
        elif change_pct is not None:
            change_pct = round(change_pct, 2)

        return {
            "success": True,
            "code": normalized,
            "name": _get_name(info, normalized),
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
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        ticker, normalized = _try_get_ticker(normalized)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)
        hist = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d")
        )

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
    簡易合理價分析（近30天均價比對）。
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        info_data = get_stock_info(stock_code)
        if not info_data.get("success"):
            return {"success": False, "code": normalized, "error": info_data.get("error", "未知錯誤")}

        current_price = info_data.get("price")
        hist_60 = get_stock_history(stock_code, days=60)
        hist_30 = get_stock_history(stock_code, days=30)
        avg_30d = hist_30.get("avg_price") if hist_30.get("success") else None
        avg_60d = hist_60.get("avg_price") if hist_60.get("success") else None

        suggestion = "無法判斷"
        if current_price and avg_30d:
            diff_pct = (current_price - avg_30d) / avg_30d * 100
            if diff_pct < -5:
                suggestion = "便宜"
            elif diff_pct > 5:
                suggestion = "偏貴"
            else:
                suggestion = "合理"

        ticker = _make_ticker(normalized)
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
