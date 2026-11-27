"""本機完整測試，確認所有功能正常再推上 Render"""
import sys
sys.path.insert(0, ".")

print("=== 測試 1: 指令解析 ===")
from app.sms_handler import parse_command
tests = [("2330", "price"), ("2330買", "buy_analysis"), ("2330 買", "buy_analysis"),
         ("訂閱 2330", "subscribe"), ("取消 2330", "unsubscribe"), ("說明", "help")]
all_ok = True
for msg, expected in tests:
    result = parse_command(msg)
    ok = result["type"] == expected
    status = "✅" if ok else "❌"
    print(f"  {status} {msg!r:15} -> {result['type']} (expected: {expected})")
    if not ok:
        all_ok = False

print()
print("=== 測試 2: 股票資料 + 公司名稱 ===")
from app.stock_fetcher import get_stock_info
for code in ["2330", "0050"]:
    info = get_stock_info(code)
    if info.get("success"):
        print(f"  ✅ {code} -> name={info.get('name')}, price={info.get('price')}")
    else:
        print(f"  ❌ {code} -> {info.get('error')}")

print()
print("=== 測試 3: 回傳格式 ===")
from app.response_formatter import format_simple_response
info = get_stock_info("2330")
if info.get("success"):
    msg = format_simple_response(info, "price")
    print("  查價格式:")
    print("  " + "\n  ".join(msg.split("\n")))
    print()
    msg2 = format_simple_response(info, "buy_analysis")
    print("  買賣分析格式:")
    print("  " + "\n  ".join(msg2.split("\n")))

print()
if all_ok:
    print("✅ 全部測試通過，可以推上 Render")
else:
    print("❌ 有測試失敗，請先修正")
