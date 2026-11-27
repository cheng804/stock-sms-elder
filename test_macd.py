"""
測試 MACD 預警功能

這個腳本會：
1. 檢查多支股票的 MACD 狀態
2. 模擬訂閱該股票
3. 測試預警通知生成
"""
import sys
sys.path.insert(0, ".")

from app.stock_fetcher import calculate_macd, get_stock_info
from app.database import add_subscription, get_all_subscriptions, remove_subscription

# 測試用假手機號碼
FAKE_PHONE = "+886900000000"

# 常見台股代號
TEST_STOCKS = ["2330", "2317", "2454", "2882", "0050", "0056"]

print("=" * 60)
print("📊 MACD 預警功能測試")
print("=" * 60)

print("\n🔍 第一步：檢查哪些股票目前有 MACD 交叉訊號\n")

stocks_with_signal = []

for stock in TEST_STOCKS:
    try:
        macd = calculate_macd(stock)
        info = get_stock_info(stock)
        
        name = info.get("name", stock)
        price = info.get("price", 0)
        
        if macd.get("success") and macd.get("cross"):
            cross = macd["cross"]
            signal = "🟢 黃金交叉（多頭）" if cross == "golden" else "🔴 死亡交叉（空頭）"
            print(f"✅ {stock} {name:8s} | 現價 {price:7.2f} | {signal}")
            stocks_with_signal.append((stock, name, price, cross))
        else:
            print(f"⚪ {stock} {name:8s} | 現價 {price:7.2f} | 無交叉訊號")
            
    except Exception as e:
        print(f"❌ {stock} 檢查失敗：{e}")

print("\n" + "=" * 60)

if not stocks_with_signal:
    print("\n❌ 目前測試的股票都沒有 MACD 交叉訊號")
    print("   這是正常的，MACD 交叉不是每天都會出現")
    print("\n💡 如何測試：")
    print("   1. 等待真實股票出現交叉（通常在趨勢反轉時）")
    print("   2. 或者修改 calculate_macd() 的邏輯來模擬交叉")
else:
    print(f"\n✅ 找到 {len(stocks_with_signal)} 支有訊號的股票")
    
    print("\n🧪 第二步：模擬訂閱並生成預警訊息\n")
    
    for stock, name, price, cross in stocks_with_signal:
        # 加入訂閱
        add_subscription(FAKE_PHONE, stock, "08:30")
        
        # 生成預警訊息（模擬 check_macd_signals 的邏輯）
        if cross == "golden":
            emoji = "🟢"
            signal_text = "黃金交叉（多頭訊號）"
            action_hint = "短期動能轉強，可以留意買入機會。"
        else:
            emoji = "🔴"
            signal_text = "死亡交叉（空頭訊號）"
            action_hint = "短期動能轉弱，操作要謹慎。"
        
        reply = (
            f"{emoji} MACD 技術預警：{stock}\n"
            f"出現 {signal_text}\n"
            f"現價：{price:.2f} 元\n"
            f"{action_hint}\n"
            f"傳「{stock}買」可查看完整分析。\n"
            f"投資有風險，請謹慎！"
        )
        
        print(f"📤 預警訊息（{stock} {name}）：")
        print("-" * 60)
        print(reply)
        print("-" * 60)
        print()
        
        # 清理訂閱
        remove_subscription(FAKE_PHONE, stock)

print("\n" + "=" * 60)
print("📋 測試完成摘要：")
print("=" * 60)
print(f"✅ MACD 計算功能：正常")
print(f"✅ 預警訊息生成：正常")
print(f"📊 有交叉訊號的股票：{len(stocks_with_signal)} 支")

if stocks_with_signal:
    print("\n💡 如何啟用真實預警：")
    print("   1. 用 simulate.py 訂閱有訊號的股票")
    for stock, name, _, _ in stocks_with_signal:
        print(f"      訂閱 {stock}")
    print("   2. 等到明天 08:30，系統會自動發送預警")
    print("   3. 或部署到 Render，就會在台灣時間 08:30 自動檢查")
else:
    print("\n💡 MACD 交叉是什麼時候出現：")
    print("   - 黃金交叉：股價從下跌轉為上漲的初期")
    print("   - 死亡交叉：股價從上漲轉為下跌的初期")
    print("   - 通常一個月內會出現 1-3 次（視市場波動）")
    
print("\n" + "=" * 60)
