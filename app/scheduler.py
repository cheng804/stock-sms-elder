"""
scheduler.py - 訂閱排程模組

使用 APScheduler 每分鐘檢查一次，
到了訂閱設定的通知時間就自動發送股票資訊給使用者。
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
#  通知發送邏輯
# ─────────────────────────────────────────

def send_subscription_notifications(notify_time: str) -> None:
    """
    查詢指定通知時間的所有啟用訂閱，發送股票資訊給每位訂閱者。

    Args:
        notify_time: 格式 "HH:MM"，例如 "08:30"
    """
    # 延遲 import 避免循環依賴
    from app.database import get_subscriptions_by_time, log_query
    from app.stock_fetcher import get_stock_info, get_stock_history
    from app.ai_analyzer import generate_elder_friendly_analysis
    from app.sms_client import send_sms

    subscriptions = get_subscriptions_by_time(notify_time)

    if not subscriptions:
        logger.debug(f"[排程] {notify_time} 沒有訂閱需要通知。")
        return

    logger.info(f"[排程] {notify_time} 開始發送訂閱通知，共 {len(subscriptions)} 筆。")

    for sub in subscriptions:
        phone = sub.phone_number
        stock_code = sub.stock_code

        try:
            info = get_stock_info(stock_code)
            history = get_stock_history(stock_code, days=30)

            if not info.get("success"):
                reply = f"😅 {stock_code} 今日資料取得失敗，請稍後手動查詢。"
            else:
                reply = generate_elder_friendly_analysis(info, history, "price")

            # 加上每日訂閱提示
            reply = f"📬 每日通知 {notify_time}\n\n{reply}\n\n傳「取消 {stock_code}」可停止通知。"

            success = send_sms(phone, reply)
            log_query(phone, stock_code, "subscription_notify", reply)

            if success:
                logger.info(f"[排程] 訂閱通知發送成功：{phone} -> {stock_code}")
            else:
                logger.warning(f"[排程] 訂閱通知發送失敗：{phone} -> {stock_code}")

        except Exception as e:
            logger.error(f"[排程] 處理訂閱 {phone}/{stock_code} 時發生錯誤：{e}")


def _check_and_notify() -> None:
    """
    每分鐘執行的任務：取得台灣時間，呼叫對應的通知函數。
    """
    # 使用台灣時間（UTC+8）
    from datetime import timezone, timedelta
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    current_time = f"{now.hour:02d}:{now.minute:02d}"
    logger.debug(f"[排程] 每分鐘檢查：台灣時間 {current_time}")
    send_subscription_notifications(current_time)


# ─────────────────────────────────────────
#  排程器啟動
# ─────────────────────────────────────────

def start_scheduler() -> Optional[BackgroundScheduler]:
    """
    建立並啟動 APScheduler BackgroundScheduler。

    設定每分鐘整點執行 _check_and_notify()，
    讓系統在正確時間點發送訂閱通知。

    Returns:
        啟動中的 BackgroundScheduler，或 None（若啟動失敗）
    """
    try:
        scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,       # 若積壓多個相同任務，只執行一次
                "max_instances": 1,     # 同一個 job 只允許一個實例在跑
                "misfire_grace_time": 30,  # 允許最多 30 秒的延遲
            }
        )

        # 每分鐘的第 0 秒執行
        scheduler.add_job(
            func=_check_and_notify,
            trigger=CronTrigger(second=0),
            id="check_subscriptions",
            name="每分鐘檢查訂閱通知",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("✅ APScheduler 排程器已啟動，每分鐘檢查一次訂閱。")
        return scheduler

    except Exception as e:
        logger.error(f"❌ 排程器啟動失敗：{e}")
        return None
