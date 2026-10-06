"""
stock_fetcher.py - 股票資料抓取模組

台股：使用 TWSE 證交所官方即時 API（真正即時，無延遲）。
美股：使用 yfinance（延遲約 15 分鐘）。
歷史資料：全部使用 yfinance。
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

logger = logging.getLogger(__name__)

# 使用 curl_cffi 模擬 Chrome 瀏覽器，避免雲端環境被 Yahoo Finance 封鎖（美股用）
try:
    from curl_cffi import requests as curl_requests
    _SESSION = curl_requests.Session(impersonate="chrome")
except ImportError:
    _SESSION = None

# 中文名稱快取（避免重複打 API）
_NAME_CACHE: dict = {}

# ── TWSE 即時 API（台股專用）────────────────────────────────────────────

_TWSE_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _is_tw_stock(stock_code: str) -> bool:
    """判斷是否為台股代號（純數字 4~6 碼，或數字+英文字母如 00631L）"""
    return bool(re.match(r"^\d{4,6}[A-Z]?$", stock_code.strip().upper()))


def _fetch_twse_realtime(stock_code: str) -> Optional[dict]:
    """
    從 TWSE 官方即時 API 抓取台股報價（真正即時，非延遲）。

    回傳 dict 或 None（查無資料）。
    先查上市(tse)，若無資料改查上櫃(otc)。

    TWSE msgArray 欄位說明：
      z  = 最新成交價（盤中即時，收盤後為空字串）
      y  = 昨日收盤價
      o  = 今日開盤價
      h  = 今日最高價
      l  = 今日最低價
      v  = 累計成交量（張）
      n  = 公司簡稱
      d  = 日期（YYYYMMDD）
      t  = 最後成交時間（HH:MM:SS）
    """
    code = stock_code.strip().upper()
    for prefix in ["tse", "otc"]:
        try:
            ex_ch = f"{prefix}_{code}.tw"
            url = (
                f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
                f"?ex_ch={ex_ch}&json=1&delay=0"
            )
            r = req.get(url, timeout=8, headers=_TWSE_HEADERS)
            data = r.json()
            msg = data.get("msgArray", [])
            if not msg:
                continue
            item = msg[0]
            # z 欄位存在且非空字串才算有即時價
            if item.get("z") or item.get("y"):
                return item
        except Exception as e:
            logger.warning(f"TWSE API 查詢失敗 {code} ({prefix}): {e}")
    return None


def _parse_twse_item(item: dict, stock_code: str) -> dict:
    """
    將 TWSE msgArray 的單一 item 轉換為與 get_stock_info 相同的回傳格式。
    """
    def _f(val) -> Optional[float]:
        try:
            v = float(val)
            return round(v, 2) if v > 0 else None
        except (TypeError, ValueError):
            return None

    z = item.get("z", "")      # 最新成交價（盤中空字串表示未成交）
    y = item.get("y", "")      # 昨收
    o = item.get("o", "")      # 開盤
    h = item.get("h", "")      # 最高
    l = item.get("l", "")      # 最低
    v = item.get("v", "")      # 成交量(張)
    name = item.get("n", stock_code)

    price_raw = z if z and z != "-" else y   # 盤中用即時價，盤前/盤後用昨收
    price = _f(price_raw)
    prev_close = _f(y)
    is_prev_close = not (z and z != "-")     # True 表示非盤中，顯示昨收

    change = None
    change_pct = None
    if price and prev_close and not is_prev_close:
        change = round(price - prev_close, 2)
        change_pct = round(change / prev_close * 100, 2)

    try:
        volume = int(float(v) * 1000) if v and v != "-" else None  # 張→股
    except (TypeError, ValueError):
        volume = None

    # 從離線對應表補充更完整的中文名
    offline_name = get_stock_name(stock_code.upper())
    display_name = offline_name if offline_name else name

    return {
        "success": True,
        "code": stock_code,
        "name": display_name,
        "price": price,
        "change": change,
        "change_percent": change_pct,
        "volume": volume,
        "open": _f(o),
        "high": _f(h),
        "low": _f(l),
        "prev_close": prev_close,
        "market_cap": None,      # TWSE API 不提供市值
        "is_prev_close": is_prev_close,
        "source": "twse",        # 標示資料來源
    }


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

    台股（純數字代號）：使用 TWSE 官方即時 API，無延遲。
    美股（英文代號如 TSLA）：使用 yfinance，約延遲 15 分鐘。

    Args:
        stock_code: 股票代號（台股輸入純數字即可，如 "2330"；美股如 "TSLA"）

    Returns:
        dict 包含 success, code, name, price, change, change_percent,
        volume, open, high, low, prev_close, market_cap, is_prev_close
    """
    code = stock_code.strip().upper()

    # ── 台股：走 TWSE 即時 API ──────────────────────────────────────
    if _is_tw_stock(code):
        try:
            item = _fetch_twse_realtime(code)
            if item:
                return _parse_twse_item(item, code)
            # TWSE 查無資料（代號錯誤）
            return {
                "success": False,
                "code": code,
                "error": f"找不到台股代號 {code}，請確認是否正確。",
            }
        except Exception as e:
            return {
                "success": False,
                "code": code,
                "error": f"抓取台股 {code} 資料時發生錯誤：{str(e)}",
            }

    # ── 美股 / ETF：走 yfinance（延遲約 15 分鐘）──────────────────
    normalized = _normalize_stock_code(code)
    try:
        ticker, normalized = _try_get_ticker(normalized)
        info = ticker.info

        if not info or info.get("regularMarketPrice") is None:
            hist = ticker.history(period="5d")
            if hist.empty:
                return {
                    "success": False,
                    "code": normalized,
                    "error": f"找不到股票代號 {code}，請確認是否正確。",
                }

            # 過濾掉 Close 為 0 或 NaN 的列
            hist_valid = hist[hist["Close"].notna() & (hist["Close"] > 0)]
            if hist_valid.empty:
                return {
                    "success": False,
                    "code": normalized,
                    "error": f"找不到 {code} 的有效收盤資料。",
                }

            if len(hist_valid) < 2:
                last_row = hist_valid.iloc[-1]
                price = _safe_float(last_row["Close"])
                return {
                    "success": True,
                    "code": normalized,
                    "name": _get_name(info, normalized),
                    "price": price,
                    "change": None,
                    "change_percent": None,
                    "volume": int(last_row["Volume"]) if last_row["Volume"] else None,
                    "open": _safe_float(last_row["Open"]),
                    "high": _safe_float(last_row["High"]),
                    "low": _safe_float(last_row["Low"]),
                    "prev_close": None,
                    "market_cap": info.get("marketCap"),
                    "is_prev_close": True,
                    "source": "yfinance",
                }

            last_row = hist_valid.iloc[-1]
            prev_row = hist_valid.iloc[-2]
            price = _safe_float(last_row["Close"])
            prev_close = _safe_float(prev_row["Close"])
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
                "is_prev_close": True,
                "source": "yfinance",
            }

        price = _safe_float(info.get("regularMarketPrice"))
        prev_close = _safe_float(info.get("regularMarketPreviousClose"))
        change = _safe_float(info.get("regularMarketChange"))
        if change is None and price and prev_close:
            change = round(price - prev_close, 2)
        elif change is not None:
            change = round(change, 2)

        change_pct = _safe_float(info.get("regularMarketChangePercent"))
        if change_pct is None and change and prev_close:
            change_pct = round(change / prev_close * 100, 2)
        elif change_pct is not None:
            change_pct = round(change_pct, 2)

        # Fallback：若 change 還是 None，用近 5 天歷史算漲跌
        if (change is None or prev_close is None) and price is not None:
            try:
                hist_fb = ticker.history(period="5d")
                if len(hist_fb) >= 2:
                    today_close = _safe_float(hist_fb.iloc[-1]["Close"])
                    yesterday_close = _safe_float(hist_fb.iloc[-2]["Close"])
                    if today_close and yesterday_close and yesterday_close != 0:
                        change = round(today_close - yesterday_close, 2)
                        change_pct = round(change / yesterday_close * 100, 2)
                        if prev_close is None:
                            prev_close = yesterday_close
            except Exception:
                pass

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
            "is_prev_close": False,
            "source": "yfinance",
        }

    except Exception as e:
        return {
            "success": False,
            "code": normalized,
            "error": f"抓取 {code} 資料時發生錯誤：{str(e)}",
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

        volumes = [int(v) if v else 0 for v in hist["Volume"]]
        valid_volumes = [v for v in volumes if v > 0]
        # 最後一筆是今日，均量用前面的資料算（排除今日避免影響）
        avg_volume = int(sum(valid_volumes[:-1]) / len(valid_volumes[:-1])) if len(valid_volumes) > 1 else None
        today_volume = volumes[-1] if volumes else None

        return {
            "success": True,
            "code": normalized,
            "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
            "closes": closes,
            "highs": [_safe_float(v) for v in hist["High"]],
            "lows": [_safe_float(v) for v in hist["Low"]],
            "volumes": volumes,
            "avg_price": avg_price,
            "avg_volume": avg_volume,
            "today_volume": today_volume,
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


def calculate_rsi(stock_code: str, period: int = 14) -> dict:
    """
    計算股票的 RSI（相對強弱指標）。

    RSI 使用近 period+20 天的收盤價計算，回傳最新一日的 RSI 值。

    Args:
        stock_code: 股票代號
        period:     RSI 週期，預設 14 日

    Returns:
        dict 包含:
            success (bool)
            rsi (float | None): 最新 RSI 值，0~100
            signal (str): "超賣" | "偏弱" | "中性" | "偏強" | "超買"
            description (str): 長輩友善的說明文字
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        ticker, normalized = _try_get_ticker(normalized)
        hist = ticker.history(period=f"{period + 30}d")

        if hist.empty or len(hist) < period + 1:
            return {"success": False, "rsi": None,
                    "signal": "無資料", "description": "歷史資料不足，無法計算 RSI。"}

        closes = hist["Close"].dropna()
        delta = closes.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, float("inf"))
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = round(float(rsi_series.iloc[-1]), 1)

        if rsi_val < 30:
            signal = "超賣"
            description = f"RSI {rsi_val}，目前嚴重超賣，股價可能已到低點，可以留意買入機會，但仍需謹慎。"
        elif rsi_val < 45:
            signal = "偏弱"
            description = f"RSI {rsi_val}，目前偏弱，賣壓較大，建議觀望為主。"
        elif rsi_val < 55:
            signal = "中性"
            description = f"RSI {rsi_val}，目前多空均衡，沒有明顯方向。"
        elif rsi_val < 70:
            signal = "偏強"
            description = f"RSI {rsi_val}，目前偏強，股價動能不錯，但注意追高風險。"
        else:
            signal = "超買"
            description = f"RSI {rsi_val}，目前嚴重超買，股價可能偏高，不建議此時追入。"

        return {
            "success": True,
            "rsi": rsi_val,
            "signal": signal,
            "description": description,
        }

    except Exception as e:
        return {
            "success": False,
            "rsi": None,
            "signal": "錯誤",
            "description": f"RSI 計算失敗：{e}",
        }


def calculate_macd(stock_code: str,
                   fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    計算 MACD（指數平滑異同移動平均線）。

    需要至少 slow+signal+10 天的收盤價。
    回傳最新一日的 MACD 值，以及是否發生交叉訊號。

    Args:
        stock_code: 股票代號
        fast:       快線週期，預設 12
        slow:       慢線週期，預設 26
        signal:     訊號線週期，預設 9

    Returns:
        dict 包含:
            success (bool)
            macd      (float): MACD 線最新值
            signal_line (float): 訊號線最新值
            histogram (float): 柱狀值（MACD - Signal）
            cross     (str | None): "golden"（黃金交叉）| "dead"（死亡交叉）| None
            description (str): 長輩友善說明
    """
    normalized = _normalize_stock_code(stock_code)
    try:
        ticker, normalized = _try_get_ticker(normalized)
        # 需要足夠天數讓 EMA 穩定
        hist = ticker.history(period=f"{slow + signal + 30}d")

        if hist.empty or len(hist) < slow + signal:
            return {
                "success": False,
                "cross": None,
                "description": "歷史資料不足，無法計算 MACD。",
            }

        closes = hist["Close"].dropna()

        ema_fast   = closes.ewm(span=fast,   adjust=False).mean()
        ema_slow   = closes.ewm(span=slow,   adjust=False).mean()
        macd_line  = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram  = macd_line - signal_line

        macd_val   = round(float(macd_line.iloc[-1]),   4)
        signal_val = round(float(signal_line.iloc[-1]), 4)
        hist_val   = round(float(histogram.iloc[-1]),   4)

        # 交叉偵測：昨日 MACD < Signal，今日 MACD > Signal → 黃金交叉
        prev_macd   = float(macd_line.iloc[-2])
        prev_signal = float(signal_line.iloc[-2])

        cross = None
        if prev_macd < prev_signal and macd_val > signal_val:
            cross = "golden"
            description = "MACD 出現黃金交叉（多頭訊號），短期動能轉強，可以多留意！"
        elif prev_macd > prev_signal and macd_val < signal_val:
            cross = "dead"
            description = "MACD 出現死亡交叉（空頭訊號），短期動能轉弱，操作要謹慎！"
        elif macd_val > 0:
            description = f"MACD {macd_val}，目前在零軸上方，趨勢偏多。"
        else:
            description = f"MACD {macd_val}，目前在零軸下方，趨勢偏空。"

        return {
            "success": True,
            "macd": macd_val,
            "signal_line": signal_val,
            "histogram": hist_val,
            "cross": cross,
            "description": description,
        }

    except Exception as e:
        return {
            "success": False,
            "cross": None,
            "description": f"MACD 計算失敗：{e}",
        }
