"""測試收盤價顯示"""
from app.stock_fetcher import get_stock_info
from app.response_formatter import format_simple_response
import json

result = get_stock_info('2330')
print("=" * 50)
print("股票資料:")
print(json.dumps(result, indent=2, ensure_ascii=False))
print("\n" + "=" * 50)
print("格式化後簡訊:")
print(format_simple_response(result, "price"))
print("=" * 50)
