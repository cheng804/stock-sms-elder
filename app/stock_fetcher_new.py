"""
簡化版的 get_stock_info - 移除所有複雜判斷
邏輯:
1. 優先使用 ticker.info 的即時資料
2. 若無即時資料,使用歷史資料 fallback
3. 判斷歷史資料是否為今天,決定顯示方式
"""

def get_stock_info_simplified(stock_code: str) -> dict:
    """取得股票即時資訊(簡化版)"""
    import logging
    from datetime import datetime, timedelta
    import pytz
    
    logger = logging.getLogger(__name__)
    normalized = _normalize_stock_code(stock_code)
    
    try:
        ticker, normalized = _try_get_ticker(normalized)
        info = ticker.info
        
        is_tw_stock = normalized.endswith(('.TW', '.TWO'))
        has_live_price = info and info.get("regularMarketPrice") is not None
        
        logger.info(f"[SIMPLE] 股票: {normalized}, 有即時資料: {has_live_price}")
        
        # ══════════════════════════════════════
        # 優先使用即時資料
        # ══════════════════════════════════════
        if has_live_price:
            price = _safe_float(info.get("regularMarketPrice"))
            prev_close = _safe_float(info.get("regularMarketPreviousClose"))
            change = _safe_float(info.get("regularMarketChange"))
            
            if change is None and price and prev_close:
                change = round(price - prev_close, 2)
            elif change:
                change = round(change, 2)

            change_pct = _safe_float(info.get("regularMarketChangePercent"))
            if change_pct is None and change and prev_close:
                change_pct = round(change / prev_close * 100, 2)
            elif change_pct:
                change_pct = round(change_pct, 2)

            logger.info(f"[SIMPLE] 使用即時資料: price={price}, change={change}")

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
                "is_today": True,
            }
        
        # ══════════════════════════════════════
        # 無即時資料,使用歷史資料 fallback
        # ══════════════════════════════════════
        logger.info(f"[SIMPLE] 無即時資料,使用歷史資料 fallback")
        
        tw_tz = pytz.timezone('Asia/Taipei')
        now_tw = datetime.now(tw_tz)
        
        end = datetime.now()
        start = end - timedelta(days=10)
        
        logger.info(f"[SIMPLE] 查詢歷史: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        logger.info(f"[SIMPLE] 當前時間: {now_tw.strftime('%Y-%m-%d %H:%M:%S %A')}")
        
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        
        if hist.empty:
            return {"success": False, "code": normalized, "error": f"找不到股票代號 {stock_code}"}

        # 過濾無效資料
        hist_valid = hist[hist["Close"].notna() & (hist["Close"] > 0)]
        
        logger.info(f"[SIMPLE] 歷史筆數: {len(hist)}, 有效筆數: {len(hist_valid)}")
        if not hist_valid.empty:
            logger.info(f"[SIMPLE] 最後5筆: {[d.strftime('%Y-%m-%d') for d in hist_valid.index[-5:]]}")
        
        if hist_valid.empty:
            return {"success": False, "code": normalized, "error": f"找不到 {stock_code} 的有效資料"}

        # 取最後交易日資料
        last_row = hist_valid.iloc[-1]
        last_date = hist_valid.index[-1]
        last_date_str = last_date.strftime("%Y-%m-%d")
        today_str = now_tw.strftime("%Y-%m-%d")
        is_today_data = (last_date_str == today_str)
        
        logger.info(f"[SIMPLE] 最後交易日: {last_date_str}, 今天: {today_str}, 是否今天: {is_today_data}")

        price = _safe_float(last_row["Close"])
        
        # 計算漲跌
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
            "is_prev_close": True,
            "is_today": is_today_data,
            "last_trade_date": last_date_str,
        }

    except Exception as e:
        logger.exception(f"[SIMPLE] 錯誤: {e}")
        return {"success": False, "code": normalized, "error": f"抓取 {stock_code} 時發生錯誤：{str(e)}"}
