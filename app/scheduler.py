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

def check_macd_signals() -> None:
    """
    對每位使用者訂閱的股票計算 MACD，
    出現黃金交叉或死亡交叉時主動發送預警簡訊。
    每天 08:30 由排程器呼叫一次（與訂閱通知同一時間點）。
    """
    from app.database import get_all_subscriptions, log_query
    from app.stock_fetcher import get_stock_info, calculate_macd
    from app.sms_client import send_sms

    subscriptions = get_all_subscriptions()
    if not subscriptions:
        return

    # 同一股票只計算一次 MACD，避免重複打 API
    macd_cache: dict = {}

    logger.info(f"[MACD] 開始檢查 {len(subscriptions)} 筆訂閱的 MACD 訊號。")

    for sub in subscriptions:
        phone = sub.phone_number
        stock_code = sub.stock_code
        clean = stock_code.replace(".TWO", "").replace(".TW", "")

        try:
            if stock_code not in macd_cache:
                macd_cache[stock_code] = calculate_macd(stock_code)
            macd = macd_cache[stock_code]

            if not macd.get("success") or not macd.get("cross"):
                continue  # 無交叉訊號，跳過

            info = get_stock_info(stock_code)
            price_str = f"{info['price']:.2f}" if info.get("success") and info.get("price") else "—"

            cross = macd["cross"]
            if cross == "golden":
                emoji = "🟢"
                signal_text = "黃金交叉（多頭訊號）"
                action_hint = "短期動能轉強，可以留意買入機會。"
            else:
                emoji = "🔴"
                signal_text = "死亡交叉（空頭訊號）"
                action_hint = "短期動能轉弱，操作要謹慎。"

            reply = (
                f"{emoji} MACD 技術預警：{clean}\n"
                f"出現 {signal_text}\n"
                f"現價：{price_str} 元\n"
                f"{action_hint}\n"
                f"傳「{clean}買」可查看完整分析。\n"
                f"投資有風險，請謹慎！"
            )

            send_sms(phone, reply)
            log_query(phone, stock_code, "macd_alert", reply)
            logger.info(f"[MACD] 預警發送：{phone} -> {clean} {signal_text}")

        except Exception as e:
            logger.error(f"[MACD] 處理 {phone}/{stock_code} 時發生錯誤：{e}")


def check_price_alerts() -> None:
    """
    檢查所有啟用中的價格警報，股價觸及目標價時發送簡訊通知。
    每天 08:30 由排程器呼叫一次。
    """
    from app.database import get_active_alerts, trigger_alert, log_query
    from app.stock_fetcher import get_stock_info
    from app.sms_client import send_sms

    alerts = get_active_alerts()
    if not alerts:
        logger.debug("[警報] 目前沒有啟用中的警報。")
        return

    logger.info(f"[警報] 開始檢查 {len(alerts)} 筆警報。")

    for alert in alerts:
        phone = alert.phone_number
        stock_code = alert.stock_code
        target = float(alert.target_price)
        direction = alert.direction
        clean = stock_code.replace(".TWO", "").replace(".TW", "")

        try:
            info = get_stock_info(stock_code)
            if not info.get("success"):
                continue

            price = info.get("price")
            if price is None:
                continue

            triggered = (
                (direction == "below" and price <= target) or
                (direction == "above" and price >= target)
            )

            if triggered:
                dir_text = f"跌破 {target:.0f}" if direction == "below" else f"突破 {target:.0f}"
                reply = (
                    f"🔔 到價警報！\n"
                    f"{clean} 現價 {price:.2f} 元，已{dir_text} 元！\n"
                    f"傳「{clean}買」可查看完整分析。"
                )
                send_sms(phone, reply)
                trigger_alert(alert.id)
                log_query(phone, stock_code, "alert_triggered", reply)
                logger.info(f"[警報] 觸發：{phone} -> {clean} {dir_text}")

        except Exception as e:
            logger.error(f"[警報] 處理警報 {phone}/{stock_code} 時發生錯誤：{e}")


def send_subscription_notifications(notify_time: str) -> None:
    """
    查詢指定通知時間的所有啟用訂閱，發送股票資訊給每位訂閱者。

    Args:
        notify_time: 格式 "HH:MM"，例如 "08:30"
    """
    # 延遲 import 避免循環依賴
    from app.database import get_subscriptions_by_time, log_query
    from app.stock_fetcher import get_stock_info, get_stock_history
    from app.response_formatter import generate_elder_friendly_analysis
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
    週末（六、日）不發送訂閱通知和警報。
    """
    from datetime import timezone, timedelta
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    current_time = f"{now.hour:02d}:{now.minute:02d}"
    weekday = now.weekday()  # 0=週一, 6=週日
    
    # 週末（5=週六, 6=週日）不發送通知
    if weekday >= 5:
        logger.debug(f"[排程] 今天是週末（weekday={weekday}），跳過通知。")
        return
    
    logger.debug(f"[排程] 每分鐘檢查：台灣時間 {current_time}")
    send_subscription_notifications(current_time)
    
    # 每天 08:30 執行警報檢查與 MACD 預警（僅平日）
    if current_time == "08:30":
        check_price_alerts()
        check_macd_signals()


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
