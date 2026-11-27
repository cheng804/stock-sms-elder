"""
stock_fetcher_finmind.py - FinMind 資料抓取模組

========================================
教育用途聲明 / Educational Use Declaration
========================================

本模組使用 FinMind 開源金融資料，僅供學術研究與教育展示用途。

資料來源：FinMind (https://finmind.github.io/)
使用依據：FinMind 教育用途授權
專題性質：學校專題/畢業製作
用途聲明：非商業、非營利、教育展示

依據臺灣證券交易所『交易資訊使用管理辦法』，使用者須遵守相關規定。
本服務所提供資訊僅供參考，不構成投資建議。

This module uses FinMind open-source financial data for academic research
and educational purposes only. Data is for reference only and does not
constitute investment advice.

========================================
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd

try:
    from finmind.data import DataLoader
    FINMIND_AVAILABLE = True
except ImportError:
    FINMIND_AVAILABLE = False
    logging.warning("FinMind 未安裝，請執行: pip install finmind")

from app.stock_name_map import get_stock_name
from app.config import FINMIND_TOKEN

# 設定 logging
logger = logging.getLogger(__name__)


class FinMindStockFetcher:
    """FinMind 股票資料抓取器"""
    
    def __init__(self):
        if not FINMIND_AVAILABLE:
            raise ImportError("FinMind 未安裝")
        self.dl = DataLoader()
        # 有 Token 就登入，提升額度並解鎖即時報價
        if FINMIND_TOKEN:
            try:
                self.dl.login_by_token(api_token=FINMIND_TOKEN)
                logger.info("✅ FinMind Token 已載入，使用即時報價模式")
            except Exception as e:
                logger.warning(f"⚠️ FinMind Token 無效，降級為收盤價模式: {e}")
        else:
            logger.info("ℹ️  未設定 FINMIND_TOKEN，使用收盤價模式（設定後可取得即時報價）")
        self._name_cache = {}

    def _is_trading_hours(self) -> bool:
        """判斷現在是否為台股盤中（09:00–13:30，週一~五）"""
        import pytz
        tw = pytz.timezone("Asia/Taipei")
        now = datetime.now(tw)
        if now.weekday() >= 5:
            return False
        t = now.time()
        return datetime.strptime("09:00", "%H:%M").time() <= t <= datetime.strptime("13:30", "%H:%M").time()

    def get_stock_info(self, stock_code: str) -> dict:
        """
        取得股票資訊。
        盤中有 Token → 即時報價；其餘情況 → 最近收盤價。
        """
        stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
        
        # 盤中且有 Token → 嘗試即時報價
        if FINMIND_TOKEN and self._is_trading_hours():
            result = self._get_realtime(stock_code)
            if result.get("success"):
                return result
            logger.warning(f"[FinMind] 即時報價失敗，改用收盤價: {result.get('error')}")
        
        # 其餘情況用收盤價
        return self._get_daily(stock_code)
        
    def _get_realtime(self, stock_code: str) -> dict:
        """取得盤中即時報價（需 Token）"""
        try:
            df = self.dl.taiwan_stock_tick_snapshot(data_id=stock_code)
            if df is None or df.empty:
                return {"success": False, "error": "即時資料為空"}
            
            row = df.iloc[0]
            price     = round(float(row.get("close", 0) or row.get("price", 0)), 2)
            open_p    = round(float(row.get("open", 0)), 2)
            high      = round(float(row.get("high", 0)), 2)
            low       = round(float(row.get("low", 0)), 2)
            prev_close = round(float(row.get("yesterday_price", 0)), 2)
            volume    = int(row.get("total_volume", 0) or 0)
            change    = round(price - prev_close, 2) if price and prev_close else None
            change_pct = round(change / prev_close * 100, 2) if change and prev_close else None
            
            if price == 0:
                return {"success": False, "error": "即時價格為 0"}
            
            return {
                "success": True,
                "code": stock_code,
                "name": self._get_stock_name(stock_code),
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

    def _get_daily(self, stock_code: str) -> dict:
        """取得最近收盤價"""
        try:
            end_date   = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
            
            logger.info(f"[FinMind] 收盤價查詢 {stock_code}: {start_date} ~ {end_date}")
            
            df = self.dl.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty:
                return {"success": False, "code": stock_code,
                        "error": f"查無股票代號 {stock_code}，請確認是否正確"}
            
            df = df.dropna(subset=['close']).sort_values('date')
            if df.empty:
                return {"success": False, "code": stock_code,
                        "error": f"{stock_code} 無有效收盤資料"}
            
            last_row   = df.iloc[-1]
            last_date  = pd.to_datetime(last_row['date']).strftime('%Y-%m-%d')
            is_today   = (last_date == datetime.now().strftime('%Y-%m-%d'))
            
            price      = round(float(last_row['close']), 2)
            open_price = round(float(last_row['open']), 2) if 'open' in last_row else None
            high       = round(float(last_row['max']), 2)  if 'max'  in last_row else None
            low        = round(float(last_row['min']), 2)  if 'min'  in last_row else None
            volume     = int(last_row['Trading_Volume'])   if 'Trading_Volume' in last_row else None
            
            if len(df) >= 2:
                prev_close  = round(float(df.iloc[-2]['close']), 2)
                change      = round(price - prev_close, 2)
                change_pct  = round(change / prev_close * 100, 2) if prev_close else None
            else:
                prev_close = change = change_pct = None
            
            return {
                "success": True,
                "code": stock_code,
                "name": self._get_stock_name(stock_code),
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
    
    def get_stock_history(self, stock_code: str, days: int = 30) -> dict:
        """
        取得股票歷史資料
        
        Args:
            stock_code: 股票代號
            days: 取幾天的歷史，預設 30
        """
        stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
        
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')
            
            df = self.dl.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty:
                return {"success": False, "code": stock_code, "error": "無歷史資料"}
            
            # 過濾並排序
            df = df.dropna(subset=['close'])
            df = df.sort_values('date')
            df = df.tail(days)
            
            if df.empty:
                return {"success": False, "code": stock_code, "error": "歷史資料全部無效"}
            
            # 計算統計數據
            closes = [round(float(x), 2) for x in df['close']]
            volumes = [int(x) if x else 0 for x in df['Trading_Volume']]
            
            avg_price = round(sum(closes) / len(closes), 2) if closes else None
            
            # 均量排除今日
            valid_volumes = [v for v in volumes[:-1] if v > 0]
            avg_volume = int(sum(valid_volumes) / len(valid_volumes)) if valid_volumes else None
            today_volume = volumes[-1] if volumes else None
            
            return {
                "success": True,
                "code": stock_code,
                "dates": [pd.to_datetime(d).strftime('%Y-%m-%d') for d in df['date']],
                "closes": closes,
                "highs": [round(float(x), 2) for x in df['max']] if 'max' in df.columns else None,
                "lows": [round(float(x), 2) for x in df['min']] if 'min' in df.columns else None,
                "volumes": volumes,
                "avg_price": avg_price,
                "avg_volume": avg_volume,
                "today_volume": today_volume,
                "data_source": "FinMind"
            }
            
        except Exception as e:
            logger.error(f"[FinMind] 歷史資料錯誤 {stock_code}: {e}")
            return {
                "success": False,
                "code": stock_code,
                "error": f"抓取歷史資料失敗：{str(e)}"
            }
    
    def calculate_fair_value(self, stock_code: str) -> dict:
        """
        簡易合理價分析（近30天均價比對）
        """
        stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
        
        try:
            info_data = self.get_stock_info(stock_code)
            if not info_data.get("success"):
                return {"success": False, "code": stock_code, "error": info_data.get("error")}
            
            current_price = info_data.get("price")
            hist_30 = self.get_stock_history(stock_code, days=30)
            hist_60 = self.get_stock_history(stock_code, days=60)
            
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
                "pe_ratio": None,  # FinMind 不直接提供 P/E
                "data_source": "FinMind"
            }
            
        except Exception as e:
            logger.error(f"[FinMind] 合理價分析錯誤 {stock_code}: {e}")
            return {
                "success": False,
                "code": stock_code,
                "error": f"合理價分析失敗：{str(e)}"
            }
    
    def calculate_rsi(self, stock_code: str, period: int = 14) -> dict:
        """
        計算 RSI（相對強弱指標）
        """
        stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
        
        try:
            # 需要更多天數來計算 RSI
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=period + 30)).strftime('%Y-%m-%d')
            
            df = self.dl.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty or len(df) < period + 1:
                return {
                    "success": False,
                    "rsi": None,
                    "signal": "無資料",
                    "description": "歷史資料不足，無法計算 RSI"
                }
            
            # 計算 RSI
            df = df.sort_values('date')
            closes = df['close'].astype(float)
            delta = closes.diff()
            
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            
            avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
            avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
            
            rs = avg_gain / avg_loss.replace(0, float("inf"))
            rsi_series = 100 - (100 / (1 + rs))
            rsi_val = round(float(rsi_series.iloc[-1]), 1)
            
            # 判斷訊號
            if rsi_val < 30:
                signal = "超賣"
                description = f"RSI {rsi_val}，目前嚴重超賣，股價可能已到低點，可以留意買入機會"
            elif rsi_val < 45:
                signal = "偏弱"
                description = f"RSI {rsi_val}，目前偏弱，賣壓較大，建議觀望"
            elif rsi_val < 55:
                signal = "中性"
                description = f"RSI {rsi_val}，目前多空均衡"
            elif rsi_val < 70:
                signal = "偏強"
                description = f"RSI {rsi_val}，目前偏強，股價動能不錯"
            else:
                signal = "超買"
                description = f"RSI {rsi_val}，目前嚴重超買，股價可能偏高"
            
            return {
                "success": True,
                "rsi": rsi_val,
                "signal": signal,
                "description": description,
                "data_source": "FinMind"
            }
            
        except Exception as e:
            logger.error(f"[FinMind] RSI 計算錯誤 {stock_code}: {e}")
            return {
                "success": False,
                "rsi": None,
                "signal": "錯誤",
                "description": f"RSI 計算失敗：{e}"
            }
    
    def calculate_macd(self, stock_code: str,
                       fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        """
        計算 MACD（指數平滑異同移動平均線）
        """
        stock_code = stock_code.replace('.TW', '').replace('.TWO', '').strip()
        
        try:
            # 需要足夠天數
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=slow + signal + 40)).strftime('%Y-%m-%d')
            
            df = self.dl.taiwan_stock_daily(
                stock_id=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty or len(df) < slow + signal:
                return {
                    "success": False,
                    "cross": None,
                    "description": "歷史資料不足，無法計算 MACD"
                }
            
            # 計算 MACD
            df = df.sort_values('date')
            closes = df['close'].astype(float)
            
            ema_fast = closes.ewm(span=fast, adjust=False).mean()
            ema_slow = closes.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()
            histogram = macd_line - signal_line
            
            macd_val = round(float(macd_line.iloc[-1]), 4)
            signal_val = round(float(signal_line.iloc[-1]), 4)
            hist_val = round(float(histogram.iloc[-1]), 4)
            
            # 交叉偵測
            prev_macd = float(macd_line.iloc[-2])
            prev_signal = float(signal_line.iloc[-2])
            
            cross = None
            if prev_macd < prev_signal and macd_val > signal_val:
                cross = "golden"
                description = "MACD 出現黃金交叉（多頭訊號），短期動能轉強"
            elif prev_macd > prev_signal and macd_val < signal_val:
                cross = "dead"
                description = "MACD 出現死亡交叉（空頭訊號），短期動能轉弱"
            elif macd_val > 0:
                description = f"MACD {macd_val}，目前在零軸上方，趨勢偏多"
            else:
                description = f"MACD {macd_val}，目前在零軸下方，趨勢偏空"
            
            return {
                "success": True,
                "macd": macd_val,
                "signal_line": signal_val,
                "histogram": hist_val,
                "cross": cross,
                "description": description,
                "data_source": "FinMind"
            }
            
        except Exception as e:
            logger.error(f"[FinMind] MACD 計算錯誤 {stock_code}: {e}")
            return {
                "success": False,
                "cross": None,
                "description": f"MACD 計算失敗：{e}"
            }
    
    def _get_stock_name(self, stock_code: str) -> str:
        """取得股票名稱"""
        if stock_code in self._name_cache:
            return self._name_cache[stock_code]
        
        # 優先使用離線對應表
        name = get_stock_name(stock_code)
        if name:
            self._name_cache[stock_code] = name
            return name
        
        # 嘗試從 FinMind 取得
        try:
            df = self.dl.taiwan_stock_info()
            if df is not None and not df.empty:
                match = df[df['stock_id'] == stock_code]
                if not match.empty:
                    name = match.iloc[0]['stock_name']
                    self._name_cache[stock_code] = name
                    return name
        except Exception:
            pass
        
        return stock_code


# 建立全域實例（教育用途）
try:
    _finmind_fetcher = FinMindStockFetcher()
except ImportError:
    _finmind_fetcher = None
    logger.warning("FinMind 未安裝，部分功能將無法使用")


# 便利函數（相容於原 stock_fetcher API）
def get_stock_info(stock_code: str) -> dict:
    """取得股票即時資訊（使用 FinMind）"""
    if _finmind_fetcher is None:
        return {"success": False, "error": "FinMind 未安裝"}
    return _finmind_fetcher.get_stock_info(stock_code)


def get_stock_history(stock_code: str, days: int = 30) -> dict:
    """取得股票歷史資料（使用 FinMind）"""
    if _finmind_fetcher is None:
        return {"success": False, "error": "FinMind 未安裝"}
    return _finmind_fetcher.get_stock_history(stock_code, days)


def calculate_fair_value(stock_code: str) -> dict:
    """計算合理價（使用 FinMind）"""
    if _finmind_fetcher is None:
        return {"success": False, "error": "FinMind 未安裝"}
    return _finmind_fetcher.calculate_fair_value(stock_code)


def calculate_rsi(stock_code: str, period: int = 14) -> dict:
    """計算 RSI（使用 FinMind）"""
    if _finmind_fetcher is None:
        return {"success": False, "error": "FinMind 未安裝"}
    return _finmind_fetcher.calculate_rsi(stock_code, period)


def calculate_macd(stock_code: str, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """計算 MACD（使用 FinMind）"""
    if _finmind_fetcher is None:
        return {"success": False, "error": "FinMind 未安裝"}
    return _finmind_fetcher.calculate_macd(stock_code, fast, slow, signal)
