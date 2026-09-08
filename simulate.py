"""
simulate.py - 終端機簡訊模擬器

不需要真實手機，直接在終端機測試所有功能。
輸入模擬的簡訊內容，系統會回傳對應的結果。

使用方式：
    python simulate.py
"""
import sys
import os
sys.path.insert(0, ".")

# 模擬手機號碼
FAKE_PHONE = "+886900000000"

from app.sms_handler import parse_command, get_help_message
from app.stock_fetcher import get_stock_info, get_stock_history
from app.ai_analyzer import generate_elder_friendly_analysis, format_simple_response
from app.database import (
    get_or_create_user, activate_user, deactivate_user, is_user_active,
    log_query, add_subscription, remove_subscription
)

def handle_message(message: str) -> str:
    """處理一則模擬簡訊，回傳系統回應"""
    get_or_create_user(FAKE_PHONE)
    command = parse_command(message)
    cmd_type = command["type"]
    stock_code = command.get("stock_code")
    notify_time = command.get("time") or "08:30"

    # 開始指令
    if cmd_type == "start":
        activate_user(FAKE_PHONE)
        reply = (
            "👋 您好！股票查詢服務已開啟！\n\n"
            "📱 操作方式：\n"
            "• 傳股票代號查股價（如：2330）\n"
            "• 代號加「買」做分析（如：2330買）\n"
            "• 傳「訂閱 2330」每日自動通知\n"
            "• 傳「說明」看完整指令\n\n"
            "傳「停止」可關閉服務。"
        )
        log_query(FAKE_PHONE, None, "start", reply)
        return reply

    # 停止指令
    if cmd_type == "stop":
        deactivate_user(FAKE_PHONE)
        reply = "👋 服務已關閉。傳「開始」可以重新啟用。"
        log_query(FAKE_PHONE, None, "stop", reply)
        return reply

    # 未啟用：完全不回應
    if not is_user_active(FAKE_PHONE):
        return "（系統無回應）未啟用，請先傳「開始」"

    if cmd_type == "price":
        info = get_stock_info(stock_code)
        if not info.get("success"):
            reply = info.get("error", f"😅 查不到 {stock_code}")
        else:
            reply = generate_elder_friendly_analysis(info, None, "price")

    elif cmd_type == "buy_analysis":
        info = get_stock_info(stock_code)
        if not info.get("success"):
            reply = info.get("error", f"😅 查不到 {stock_code}")
        else:
            history = get_stock_history(stock_code, days=30)
            reply = generate_elder_friendly_analysis(info, history, "buy_analysis")

    elif cmd_type == "subscribe":
        if not stock_code:
            reply = "😅 請告訴我您要訂閱的股票代號，例如：訂閱 2330"
        else:
            add_subscription(FAKE_PHONE, stock_code, notify_time)
            reply = f"✅ 訂閱成功！\n股票：{stock_code}\n每天 {notify_time} 會傳通知給您。\n要取消請傳「取消 {stock_code}」"

    elif cmd_type == "unsubscribe":
        if not stock_code:
            reply = "😅 請告訴我您要取消的股票代號"
        else:
            success = remove_subscription(FAKE_PHONE, stock_code)
            reply = f"✅ 已取消 {stock_code} 的訂閱。" if success else f"😅 找不到 {stock_code} 的訂閱紀錄。"

    elif cmd_type == "help":
        reply = get_help_message()

    else:
        reply = "😅 看不懂您的指令。\n傳「說明」可以看完整的操作方式，\n或直接傳股票代號，例如：2330"

    log_query(FAKE_PHONE, stock_code, cmd_type, reply)
    return reply


def main():
    print("=" * 50)
    print("📱 股票簡訊服務 - 終端機模擬器")
    print("=" * 50)
    print("輸入模擬的簡訊內容，按 Enter 送出")
    print("輸入 'quit' 或按 Ctrl+C 離開")
    print("-" * 50)
    print("範例指令：")
    print("  2330        查台積電股價")
    print("  2330買      買賣分析")
    print("  訂閱 2330   每日通知")
    print("  取消 2330   退訂")
    print("  說明        操作說明")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n📤 你傳送: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                print("👋 模擬器結束")
                break

            print("⏳ 處理中...")
            reply = handle_message(user_input)
            print(f"\n📩 系統回覆:")
            print("-" * 30)
            print(reply)
            print("-" * 30)

        except KeyboardInterrupt:
            print("\n👋 模擬器結束")
            break
        except Exception as e:
            print(f"❌ 錯誤：{e}")


if __name__ == "__main__":
    main()
