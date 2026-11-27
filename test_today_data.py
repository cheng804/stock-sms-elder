"""測試今天資料是否存在"""
import yfinance as yf
from datetime import datetime, timedelta

ticker = yf.Ticker("2330.TW")

# 檢查 info
print("=" * 50)
print("ticker.info 的 regularMarketPrice:")
info = ticker.info
print(f"regularMarketPrice: {info.get('regularMarketPrice')}")
print(f"regularMarketTime: {info.get('regularMarketTime')}")

# 檢查歷史資料
print("\n" + "=" * 50)
print("歷史資料(最近 5 天):")
end = datetime.now()
start = end - timedelta(days=5)
hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
print(hist.tail())

print("\n" + "=" * 50)
print("過濾後的有效資料:")
hist_valid = hist[hist["Close"].notna() & (hist["Close"] > 0)]
print(hist_valid.tail())

if not hist_valid.empty:
    last_date = hist_valid.index[-1]
    print(f"\n最後交易日: {last_date.strftime('%Y-%m-%d %A')}")
    print(f"今天日期: {datetime.now().strftime('%Y-%m-%d %A')}")
    print(f"是否為今天: {last_date.strftime('%Y-%m-%d') == datetime.now().strftime('%Y-%m-%d')}")
