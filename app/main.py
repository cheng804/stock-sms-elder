"""
main.py - FastAPI 主程式

提供以下路由：
    POST /webhook/sms  - Twilio Webhook，接收簡訊並回應
    GET  /health       - 健康檢查
    GET  /api/stats    - Dashboard 統計資料
    GET  /api/logs     - Dashboard 查詢紀錄

簡訊處理流程：
    1. 接收 Twilio Webhook
    2. 解析手機號碼與簡訊內容
    3. 呼叫 parse_command 識別指令
    4. 根據指令取得股票資料、呼叫 AI 分析
    5. 透過 TwiML 回傳結果
    6. 記錄查詢 log
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from app.sms_handler import parse_command, get_help_message
from app.stock_fetcher import get_stock_info, get_stock_history, calculate_fair_value
from app.ai_analyzer import generate_elder_friendly_analysis, format_simple_response
from app.twilio_client import parse_incoming_webhook, verify_webhook_signature, send_sms

TEXTBEE_WEBHOOK_SECRET = os.getenv("TEXTBEE_WEBHOOK_SECRET", "")
from app.database import (
    get_or_create_user,
    activate_user,
    deactivate_user,
    is_user_active,
    log_query,
    add_subscription,
    remove_subscription,
    get_total_users,
    get_today_query_count,
    get_today_sms_count,
    get_active_subscription_count,
    get_top_queried_stocks,
    get_command_type_distribution,
    get_recent_logs,
)
from app.scheduler import start_scheduler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
#  Lifespan：啟動時順便啟動排程器
# ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理：啟動排程器。"""
    logger.info("🚀 stock-sms-elder 服務啟動中...")
    scheduler = start_scheduler()
    yield
    logger.info("👋 服務關閉，停止排程器...")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)


# ─────────────────────────────────────────
#  FastAPI App
# ─────────────────────────────────────────

app = FastAPI(
    title="股票簡訊服務 API",
    description="讓長輩用老人機傳簡訊查股票，自動回傳股票資訊。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
#  Helper：處理各種指令
# ─────────────────────────────────────────

def _handle_price(stock_code: str, phone: str) -> str:
    """
    處理查價指令：抓股票資料 -> AI 分析 -> 回傳文字。

    Args:
        stock_code: 股票代號
        phone: 使用者手機號碼

    Returns:
        要回傳的簡訊內容
    """
    info = get_stock_info(stock_code)
    if not info.get("success"):
        return info.get("error", f"😅 查不到 {stock_code}，請確認代號是否正確。")
    response = generate_elder_friendly_analysis(info, None, "price")
    return response


def _handle_buy_analysis(stock_code: str, phone: str) -> str:
    """
    處理買賣分析指令：抓股票資料 + 歷史 -> AI 分析 -> 回傳文字。

    Args:
        stock_code: 股票代號
        phone: 使用者手機號碼

    Returns:
        要回傳的簡訊內容
    """
    info = get_stock_info(stock_code)
    if not info.get("success"):
        return info.get("error", f"😅 查不到 {stock_code}，請確認代號是否正確。")
    history = get_stock_history(stock_code, days=30)
    response = generate_elder_friendly_analysis(info, history, "buy_analysis")
    return response


def _handle_subscribe(phone: str, stock_code: Optional[str], notify_time: str) -> str:
    """
    處理訂閱指令：寫入資料庫 -> 回傳確認訊息。

    Args:
        phone: 使用者手機號碼
        stock_code: 股票代號
        notify_time: 通知時間

    Returns:
        確認訊息
    """
    if not stock_code:
        return "😅 請告訴我您要訂閱的股票代號，例如：訂閱 2330"
    sub = add_subscription(phone, stock_code, notify_time)
    return (
        f"✅ 訂閱成功！\n"
        f"股票：{stock_code}\n"
        f"每天 {notify_time} 會傳通知給您。\n"
        f"要取消請傳「取消 {stock_code}」"
    )


def _handle_unsubscribe(phone: str, stock_code: Optional[str]) -> str:
    """
    處理退訂指令：更新資料庫 -> 回傳確認訊息。

    Args:
        phone: 使用者手機號碼
        stock_code: 股票代號

    Returns:
        確認訊息
    """
    if not stock_code:
        return "😅 請告訴我您要取消的股票代號，例如：取消 2330"
    success = remove_subscription(phone, stock_code)
    if success:
        return f"✅ 已取消 {stock_code} 的訂閱，不再傳通知給您。"
    else:
        return f"😅 找不到您訂閱 {stock_code} 的紀錄，可能已經取消了。"


# ─────────────────────────────────────────
#  路由
# ─────────────────────────────────────────

@app.post("/webhook/sms")
async def webhook_sms(request: Request):
    """
    textbee Webhook 入口：接收使用者簡訊並主動回覆。

    textbee 以 application/json 格式 POST 簡訊內容，
    本路由解析後根據指令類型呼叫 send_sms() 主動發送回覆。
    須盡快回傳 200，實際處理在背景執行。
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    # 驗證簽章（未設定 secret 時跳過）
    signature = request.headers.get("X-Signature", "")
    if TEXTBEE_WEBHOOK_SECRET and not verify_webhook_signature(body, signature):
        logger.warning("Webhook 簽章驗證失敗，拒絕請求")
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    # 只處理收到簡訊的事件
    if body.get("webhookEvent") != "MESSAGE_RECEIVED":
        return JSONResponse({"ok": True})

    try:
        parsed = parse_incoming_webhook(body)
        from_phone = parsed["from_phone"]
        message_text = parsed["message"]

        logger.info(f"收到簡訊 from={from_phone}：{message_text!r}")

        # 確保使用者存在
        get_or_create_user(from_phone)

        # 解析指令
        command = parse_command(message_text)
        cmd_type = command["type"]
        stock_code = command.get("stock_code")
        notify_time = command.get("time") or "08:30"

        # 開始指令：任何人都可以用，啟用服務
        if cmd_type == "start":
            activate_user(from_phone)
            reply = (
                "👋 您好！股票查詢服務已開啟！\n\n"
                "📱 操作方式：\n"
                "• 傳股票代號查股價（如：2330）\n"
                "• 代號加「買」做分析（如：2330買）\n"
                "• 傳「訂閱 2330」每日自動通知\n"
                "• 傳「說明」看完整指令\n\n"
                "傳「停止」可關閉服務。"
            )
            log_query(from_phone, None, "start", reply)
            send_sms(from_phone, reply)
            return JSONResponse({"ok": True})

        # 停止指令
        if cmd_type == "stop":
            deactivate_user(from_phone)
            reply = "👋 服務已關閉。傳「開始」可以重新啟用。"
            log_query(from_phone, None, "stop", reply)
            send_sms(from_phone, reply)
            return JSONResponse({"ok": True})

        # 未啟用：完全不回應（避免廣告簡訊浪費額度）
        if not is_user_active(from_phone):
            logger.info(f"未啟用用戶 {from_phone} 傳訊息，忽略不回應")
            return JSONResponse({"ok": True})

        # 根據指令處理
        if cmd_type == "price":
            reply = _handle_price(stock_code, from_phone)
        elif cmd_type == "buy_analysis":
            reply = _handle_buy_analysis(stock_code, from_phone)
        elif cmd_type == "subscribe":
            reply = _handle_subscribe(from_phone, stock_code, notify_time)
        elif cmd_type == "unsubscribe":
            reply = _handle_unsubscribe(from_phone, stock_code)
        elif cmd_type == "help":
            reply = get_help_message()
        else:
            reply = (
                "😅 看不懂您的指令。\n"
                "傳「說明」可以看完整的操作方式，\n"
                "或直接傳股票代號，例如：2330"
            )

        # 記錄 log
        log_query(from_phone, stock_code, cmd_type, reply)

        # 主動發送回覆簡訊（textbee 不用 TwiML，直接呼叫 API）
        send_sms(from_phone, reply)

    except Exception as e:
        logger.exception(f"處理 Webhook 時發生未預期錯誤：{e}")

    # 永遠回傳 200，避免 textbee 重試
    return JSONResponse({"ok": True})


@app.get("/health")
async def health_check():
    """
    服務健康檢查端點。

    Returns:
        JSON 包含服務狀態
    """
    return JSONResponse({"status": "ok", "service": "stock-sms-elder"})


@app.get("/api/stats")
async def get_stats():
    """
    取得 Dashboard 用的統計資料。

    Returns:
        JSON 包含：
            - total_users: 總使用者數
            - today_queries: 今日查詢次數
            - today_sms_sent: 今日發送簡訊次數
            - active_subscriptions: 活躍訂閱數
            - top_stocks: 今日查詢前 5 名股票
            - command_distribution: 指令類型分佈
    """
    try:
        return JSONResponse({
            "total_users": get_total_users(),
            "today_queries": get_today_query_count(),
            "today_sms_sent": get_today_sms_count(),
            "active_subscriptions": get_active_subscription_count(),
            "top_stocks": get_top_queried_stocks(limit=5),
            "command_distribution": get_command_type_distribution(),
        })
    except Exception as e:
        logger.error(f"取得統計資料失敗：{e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/logs")
async def get_logs(limit: int = 50):
    """
    取得最近的查詢紀錄（Dashboard 用）。

    Args:
        limit: 回傳筆數，預設 50，最大 200

    Returns:
        JSON 包含 logs 列表
    """
    try:
        limit = min(limit, 200)
        logs = get_recent_logs(limit=limit)
        return JSONResponse({"logs": logs, "count": len(logs)})
    except Exception as e:
        logger.error(f"取得查詢紀錄失敗：{e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────
#  Dev 直接執行
# ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
