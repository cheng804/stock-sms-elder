"""
stock_fetcher_finmind.py - FinMind REST API 資料抓取模組

直接呼叫 FinMind REST API，不依賴 finmind Python 套件（避免相依衝突）。

========================================
教育用途聲明 / Educational Use Declaration
========================================
本模組使用 FinMind 開源金融資料，僅供學術研究與教育展示用途。
資料來源：FinMind (https://finmind.github.io/)
使用依據：FinMind 教育用途授權
資料僅供參考，不構成投資建議。
========================================
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import pytz

from app.stock_name_map import get_stock_name
from app.config import FINMIND_TOKEN

logger = logging.getLogger(__name__)

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
FINMIND_SNAPSHOT_API = "https://api.finmindtrade.com/api/v4/taiwan_stock_tick_snapshot"


def _base_params() -> dict:
    """組合基本參數，有 Token 就帶入"""
    p = {}
    if FINMIND_TOKEN:
        p["token"] = FINMIND_TOKEN
    return p


def _is_trading_hours() -> bool:
    """判斷現在是否為台股盤中（09:00–13:30，週一~五）"""
    tw = pytz.timezone("Asia/Taipei")
    now = datetime.now(tw)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return datetime.strptime("09:00", "%H:%M").time() <= t <= datetime.strptime("13:30", "%H:%M").time()


def _get_realtime(stock_code: str) -> dict:
    """盤中即時報價（需 Token）"""
    try:
        params = {**_base_params(), "data_id": stock_code}
        resp = requests.get(FINMIND_SNAPSHOT_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200 or not data.get("data"):
            return {"success": False, "error": data.get("msg", "即時資料為空")}

        row = data["data"][0]
        price      = round(float(row.get("close") or row.get("price") or 0), 2)
        open_p     = round(float(row.get("open") or 0), 2)
        high       = round(float(row.get("high") or 0), 2)
        low        = round(float(row.get("low") or 0), 2)
        prev_close = round(float(row.get("yesterday_price") or 0), 2)
        volume     = int(row.get("total_volume") or 0)
        change     = round(price - prev_close, 2) if price and prev_close else None
        change_pct = round(change / prev_close * 100, 2) if change and prev_close else None

        if price == 0:
            return {"success": False, "error": "即時價格為 0"}

        return {
            "success": True,
            "code": stock_code,
            "name": get_stock_name(stock_code) or stock_code,
            "price": price,
            "change": change,
            "change_percent": change_pct,
            "volume": volume,
            "open": open_p,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "market_cap": None,
            "is_today": True,
            "is_realtime": True,
            "data_source": "FinMind（即時）",
            "disclaimer": "資料僅供參考，非投資建議 | 資料來源：FinMind"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_daily(stock_code: str) -> dict:
    """最近收盤價"""
    try:
        end_date   = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

        params = {
            **_base_params(),
            "dataset": "TaiwanStockPrice",
            "data_id": stock_code,
            "start_date": start_date,
            "end_date": end_date,
        }
        resp = requests.get(FINMIND_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200 or not data.get("data"):
            return {"success": False, "code": stock_code,
                    "error": f"查無股票代號 {stock_code}，請確認是否正確"}

        df = pd.DataFrame(data["data"])
        df = df.dropna(subset=["close"]).sort_values("date")

        if df.empty:
            return {"success": False, "code": stock_code, "error": f"{stock_code} 無有效收盤資料"}

        last_row   = df.iloc[-1]
        last_date  = last_row["date"][:10]
        is_today   = (last_date == datetime.now().strftime('%Y-%m-%d'))

        price      = round(float(last_row["close"]), 2)
        open_price = round(float(last_row.get("open") or 0), 2)
        high       = round(float(last_row.get("max") or 0), 2)
        low        = round(float(last_row.get("min") or 0), 2)
        volume     = int(last_row.get("Trading_Volume") or 0)

        if len(df) >= 2:
            prev_close  = round(float(df.iloc[-2]["close"]), 2)
            change      = round(price - prev_close, 2)
            change_pct  = round(change / prev_close * 100, 2) if prev_close else None
        else:
            prev_close = change = change_pct = None

        return {
            "success": True,
            "code": stock_code,
            "name": get_stock_name(stock_code) or stock_code,
            "price": price,
            "change": change,
            "change_percent": change_pct,
            "volume": volume,
            "open": open_price,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "market_cap": None,
            "last_trade_date": last_date,
            "is_today": is_today,
            "is_realtime": False,
            "data_source": "FinMind（收盤）",
            "disclaimer": "資料僅供參考，非投資建議 | 資料來源：FinMind"
        }
    except Exception as e:
        logger.error(f"[FinMind] 錯誤 {stock_code}: {e}")
        return {"success": False, "code": stock_code,
                "error": f"抓取 {stock_code} 資料時發生錯誤：{str(e)}"}


def get_stock_info(stock_code: str) -> dict:
    """取得股票資訊：盤中有 Token → 即時；其餘 → 收盤價"""
    stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()

    if FINMIND_TOKEN and _is_trading_hours():
        result = _get_realtime(stock_code)
        if result.get("success"):
            return result
        logger.warning(f"[FinMind] 即時報價失敗，改用收盤價: {result.get('error')}")

    return _get_daily(stock_code)


def get_stock_history(stock_code: str, days: int = 30) -> dict:
    """取得股票歷史資料"""
    stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
    try:
        end_date   = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')

        params = {
            **_base_params(),
            "dataset": "TaiwanStockPrice",
            "data_id": stock_code,
            "start_date": start_date,
            "end_date": end_date,
        }
        resp = requests.get(FINMIND_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200 or not data.get("data"):
            return {"success": False, "code": stock_code, "error": "無歷史資料"}

        df = pd.DataFrame(data["data"])
        df = df.dropna(subset=["close"]).sort_values("date").tail(days)

        if df.empty:
            return {"success": False, "code": stock_code, "error": "歷史資料全部無效"}

        closes  = [round(float(x), 2) for x in df["close"]]
        volumes = [int(x) if x else 0 for x in df.get("Trading_Volume", [])]

        avg_price  = round(sum(closes) / len(closes), 2) if closes else None
        valid_vols = [v for v in volumes[:-1] if v > 0]
        avg_volume = int(sum(valid_vols) / len(valid_vols)) if valid_vols else None

        return {
            "success": True,
            "code": stock_code,
            "dates":  [d[:10] for d in df["date"]],
            "closes": closes,
            "highs":  [round(float(x), 2) for x in df["max"]] if "max" in df.columns else None,
            "lows":   [round(float(x), 2) for x in df["min"]] if "min" in df.columns else None,
            "volumes": volumes,
            "avg_price": avg_price,
            "avg_volume": avg_volume,
            "today_volume": volumes[-1] if volumes else None,
            "data_source": "FinMind"
        }
    except Exception as e:
        return {"success": False, "code": stock_code, "error": f"抓取歷史資料失敗：{str(e)}"}


def calculate_fair_value(stock_code: str) -> dict:
    """簡易合理價分析"""
    stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
    info = get_stock_info(stock_code)
    if not info.get("success"):
        return {"success": False, "code": stock_code, "error": info.get("error")}

    current_price = info.get("price")
    hist_30 = get_stock_history(stock_code, days=30)
    hist_60 = get_stock_history(stock_code, days=60)
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

    return {
        "success": True,
        "code": stock_code,
        "current_price": current_price,
        "avg_30d": avg_30d,
        "avg_60d": avg_60d,
        "suggestion": suggestion,
        "pe_ratio": None,
        "data_source": "FinMind"
    }


def calculate_rsi(stock_code: str, period: int = 14) -> dict:
    """計算 RSI"""
    stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
    hist = get_stock_history(stock_code, days=period + 30)
    if not hist.get("success") or len(hist.get("closes", [])) < period + 1:
        return {"success": False, "rsi": None, "signal": "無資料", "description": "歷史資料不足，無法計算 RSI"}

    closes = pd.Series(hist["closes"])
    delta  = closes.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss.replace(0, float("inf"))
    rsi = round(float((100 - 100 / (1 + rs)).iloc[-1]), 1)

    if rsi < 30:
        signal, description = "超賣", f"RSI {rsi}，目前嚴重超賣，股價可能已到低點"
    elif rsi < 45:
        signal, description = "偏弱", f"RSI {rsi}，目前偏弱，賣壓較大，建議觀望"
    elif rsi < 55:
        signal, description = "中性", f"RSI {rsi}，目前多空均衡"
    elif rsi < 70:
        signal, description = "偏強", f"RSI {rsi}，目前偏強，股價動能不錯"
    else:
        signal, description = "超買", f"RSI {rsi}，目前嚴重超買，股價可能偏高"

    return {"success": True, "rsi": rsi, "signal": signal, "description": description, "data_source": "FinMind"}


def calculate_macd(stock_code: str, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """計算 MACD"""
    stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
    hist = get_stock_history(stock_code, days=slow + signal + 40)
    if not hist.get("success") or len(hist.get("closes", [])) < slow + signal:
        return {"success": False, "cross": None, "description": "歷史資料不足，無法計算 MACD"}

    closes      = pd.Series(hist["closes"])
    ema_fast    = closes.ewm(span=fast,   adjust=False).mean()
    ema_slow    = closes.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line

    macd_val   = round(float(macd_line.iloc[-1]),   4)
    signal_val = round(float(signal_line.iloc[-1]), 4)
    hist_val   = round(float(histogram.iloc[-1]),   4)
    prev_macd  = float(macd_line.iloc[-2])
    prev_sig   = float(signal_line.iloc[-2])

    if prev_macd < prev_sig and macd_val > signal_val:
        cross, description = "golden", "MACD 出現黃金交叉（多頭訊號），短期動能轉強"
    elif prev_macd > prev_sig and macd_val < signal_val:
        cross, description = "dead", "MACD 出現死亡交叉（空頭訊號），短期動能轉弱"
    elif macd_val > 0:
        cross, description = None, f"MACD {macd_val}，目前在零軸上方，趨勢偏多"
    else:
        cross, description = None, f"MACD {macd_val}，目前在零軸下方，趨勢偏空"

    return {
        "success": True,
        "macd": macd_val,
        "signal_line": signal_val,
        "histogram": hist_val,
        "cross": cross,
        "description": description,
        "data_source": "FinMind"
    }
