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
        stock_code: 股票代號(台股輸入純數字即可,如 "2330")

    Returns:
        dict 包含 success, code, name, price, change, change_percent,
        volume, open, high, low, prev_close, market_cap
    """
    normalized = _normalize_stock_code(stock_code)
    
    try:
        ticker, normalized = _try_get_ticker(normalized)
        info = ticker.info
        
        import logging
        logger = logging.getLogger(__name__)
        
        # 判斷是否為台股
        is_tw_stock = normalized.endswith(('.TW', '.TWO'))
        
        # 先檢查 info 是否有即時資料
        has_live_price = info and info.get("regularMarketPrice") is not None
        
        logger.info(f"[DEBUG] 股票: {normalized}, has_live_price: {has_live_price}")
        if has_live_price:
            logger.info(f"[DEBUG] regularMarketPrice: {info.get('regularMarketPrice')}")
        
        # 如果有即時資料,優先使用
        if has_live_price:
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

            logger.info(f"[DEBUG] 使用 ticker.info 即時資料: price={price}, change={change}")

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
                "is_prev_close": False,  # 即時資料
                "is_today": True,
            }
        
        # 沒有即時資料,使用歷史資料 fallback
        logger.info(f"[DEBUG] ticker.info 無即時資料,使用歷史資料 fallback")
        
        from datetime import datetime, timedelta
        import pytz
        
        tw_tz = pytz.timezone('Asia/Taipei')
        now_tw = datetime.now(tw_tz)
        
        end = datetime.now()
        start = end - timedelta(days=10)
        
        logger.info(f"[DEBUG] 查詢歷史資料: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
        logger.info(f"[DEBUG] 當前台灣時間: {now_tw.strftime('%Y-%m-%d %H:%M:%S %A')}")
        
        hist = ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
        )
        
        if hist.empty:
            from datetime import timedelta
            import logging
            logger = logging.getLogger(__name__)
            
            end = datetime.now()
            start = end - timedelta(days=10)  # 多抓幾天避免遇到連假
            
            logger.info(f"[DEBUG] 台股已收盤，查詢歷史資料: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
            
            hist = ticker.history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            
            logger.info(f"[DEBUG] 歷史資料筆數: {len(hist)}")
            if not hist.empty:
                logger.info(f"[DEBUG] 最後5筆日期: {hist.index[-5:].tolist()}")
            
            # 過濾無效資料
            hist_valid = hist[hist["Close"].notna() & (hist["Close"] > 0)]
            
            logger.info(f"[DEBUG] 有效資料筆數: {len(hist_valid)}")
            
            if not hist_valid.empty:
                # 取最新一筆（最近交易日收盤）
                last_row = hist_valid.iloc[-1]
                last_date = hist_valid.index[-1]
                price = _safe_float(last_row["Close"])
                
                logger.info(f"[DEBUG] 最後交易日: {last_date.strftime('%Y-%m-%d')}, 收盤價: {price}")
                
                # 判斷是不是今天的資料
                last_date_str = last_date.strftime("%Y-%m-%d")
                today_str = now_tw.strftime("%Y-%m-%d")
                is_today = (last_date_str == today_str)
                
                logger.info(f"[DEBUG] 今天日期: {today_str}, 是否為今天: {is_today}")
                
                # 如果有前一日資料，計算漲跌
                if len(hist_valid) >= 2:
                    prev_row = hist_valid.iloc[-2]
                    prev_close = _safe_float(prev_row["Close"])
                    change = round(price - prev_close, 2) if price and prev_close else None
                    change_pct = round(change / prev_close * 100, 2) if change and prev_close else None
                else:
                    prev_close = None
                    change = None
                    change_pct = None
                
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
                    "is_prev_close": False,
                    "last_trade_date": last_date_str,  # 新增：最後交易日
                    "is_today": is_today,  # 新增：是否為今天
                }

        # 以下是原本的即時價格邏輯（盤中或非台股）
        if not info or info.get("regularMarketPrice") is None:
            from datetime import datetime, timedelta
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[DEBUG] ticker.info 無 regularMarketPrice,使用歷史資料 fallback (is_tw_stock={is_tw_stock}, is_today_trading_day={is_today_trading_day}, is_trading_hours={is_trading_hours})")
            logger.info(f"[DEBUG] 當前台灣時間: {now_tw.strftime('%Y-%m-%d %H:%M:%S %A')}")
            
            # 強制指定日期範圍，避免 yfinance 回傳舊快取
            # 如果是台股當日交易日收盤後,需要抓到今天的資料
            end = datetime.now()
            if is_tw_stock and is_today_trading_day:
                # 當日交易日,多抓一點確保包含今天
                start = end - timedelta(days=3)
            else:
                start = end - timedelta(days=10)
                
            logger.info(f"[DEBUG] 查詢歷史資料: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
            
            hist = ticker.history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            if hist.empty:
                return {
                    "success": False,
                    "code": normalized,
                    "error": f"找不到股票代號 {stock_code}，請確認是否正確。",
                }

            # 過濾掉 Close 為 0 或 NaN 的列（盤前未開盤的今日資料）
            hist_valid = hist[hist["Close"].notna() & (hist["Close"] > 0)]
            
            logger.info(f"[DEBUG] fallback 有效資料筆數: {len(hist_valid)}")
            if not hist_valid.empty:
                logger.info(f"[DEBUG] fallback 最後日期: {hist_valid.index[-1]}")
            
            if hist_valid.empty:
                return {
                    "success": False,
                    "code": normalized,
                    "error": f"找不到 {stock_code} 的有效收盤資料。",
                }

            # 判斷最後資料是否為今天
            last_date = hist_valid.index[-1]
            last_date_str = last_date.strftime("%Y-%m-%d")
            today_str = now_tw.strftime("%Y-%m-%d")
            is_today_data = (last_date_str == today_str)
            
            logger.info(f"[DEBUG] fallback 是否為今天: {is_today_data} (last={last_date_str}, today={today_str})")

            # 取最近兩筆有效資料
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
                    "is_today": is_today_data,
                    "last_trade_date": last_date_str,
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
                "is_today": is_today_data,  # 新增
                "last_trade_date": last_date_str,  # 新增
            }

        price = _safe_float(info.get("regularMarketPrice"))
        prev_close = _safe_float(info.get("regularMarketPreviousClose"))
        change = _safe_float(info.get("regularMarketChange"))
        
        # Debug: 記錄 info 中的時間戳
        import logging
        logger = logging.getLogger(__name__)
        market_time = info.get("regularMarketTime")
        is_tw_after_close = is_tw_stock and is_today_trading_day and not is_trading_hours
        logger.info(f"[DEBUG] ticker.info: price={price}, prev_close={prev_close}, market_time={market_time}, is_tw_after_close={is_tw_after_close}")
        
        if change is None and price and prev_close:
            change = round(price - prev_close, 2)
        elif change is not None:
            change = round(change, 2)

        change_pct = _safe_float(info.get("regularMarketChangePercent"))
        if change_pct is None and change and prev_close:
            change_pct = round(change / prev_close * 100, 2)
        elif change_pct is not None:
            change_pct = round(change_pct, 2)

        # 用歷史資料補齊 prev_close / change（當 info 欄位缺失時）
        if (change is None or prev_close is None) and price is not None:
            try:
                from datetime import datetime, timedelta
                end = datetime.now()
                start = end - timedelta(days=7)
                hist_fb = ticker.history(
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                )
                # 過濾無效列
                hist_fb = hist_fb[hist_fb["Close"].notna() & (hist_fb["Close"] > 0)]
                if len(hist_fb) >= 2:
                    yesterday_close = _safe_float(hist_fb.iloc[-2]["Close"])
                    if yesterday_close:
                        change = round(price - yesterday_close, 2)
                        change_pct = round(change / yesterday_close * 100, 2)
                        if prev_close is None:
                            prev_close = yesterday_close
            except Exception:
                pass

        # 判斷是否為台股收盤後(當日)
        is_tw_after_close = is_tw_stock and is_today_trading_day and not is_trading_hours
        
        logger.info(f"[DEBUG] 返回前檢查: is_tw_stock={is_tw_stock}, is_today_trading_day={is_today_trading_day}, is_trading_hours={is_trading_hours}, is_tw_after_close={is_tw_after_close}")
        
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
            "is_prev_close": is_tw_after_close,  # 收盤後標示為今日收盤
            "is_today": is_tw_after_close,  # 是今日資料
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

        # 過濾掉 Close 為 0 或 NaN 的列（盤前/異常資料）
        hist = hist[hist["Close"].notna() & (hist["Close"] > 0)]
        if hist.empty:
            return {"success": False, "code": normalized, "error": "歷史資料全部無效"}

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
