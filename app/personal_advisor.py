"""
personal_advisor.py - 個人化投資建議模組

根據使用者的查詢歷史，產生個人化的附加建議文字。
不依賴 AI，純粹基於行為資料與規則引擎。

對外只有一個主函數：
    get_personal_advice(phone, stock_code, current_price) -> str

回傳空字串代表沒有建議可附加（例如新用戶、首次查詢）。
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import (
    get_user_favorite_stocks,
    get_user_query_today_count,
    get_user_last_query,
    get_user_subscriptions,
)

# 今日查詢次數超過此值才顯示「頻率警示」
_HIGH_FREQUENCY_THRESHOLD = 5

# 上次查詢距今超過幾天才顯示「追蹤提醒」
_DAYS_SINCE_LAST_QUERY_THRESHOLD = 3

# 訂閱績效：訂閱超過幾天才計算
_SUBSCRIPTION_DAYS_MIN = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_code(code: str) -> str:
    """移除 .TW / .TWO 後綴，方便比對顯示。"""
    return code.replace(".TWO", "").replace(".TW", "")


# ─────────────────────────────────────────
#  子模組：各類建議產生器
# ─────────────────────────────────────────

def _advice_frequency_warning(phone: str, stock_code: str) -> Optional[str]:
    """
    查詢頻率警示：同一天查同一支股票超過閾值次數，
    提醒長輩不要太緊張。

    Returns:
        建議文字，或 None
    """
    today_count = get_user_query_today_count(phone)
    if today_count >= _HIGH_FREQUENCY_THRESHOLD:
        clean = _clean_code(stock_code)
        return (
            f"⚠️ 您今天已查詢 {today_count} 次了，\n"
            f"股價短期波動很正常，請放鬆心情！"
        )
    return None


def _advice_last_query_tracking(phone: str, stock_code: str, current_price: Optional[float]) -> Optional[str]:
    """
    上次查價追蹤：計算距上次查詢的價格變化與時間差。

    Returns:
        建議文字，或 None
    """
    if current_price is None:
        return None

    last = get_user_last_query(phone, stock_code)
    if not last:
        return None

    last_dt: datetime = last["created_at"]
    # 確保有時區資訊以便比較
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)

    days_ago = (_utc_now() - last_dt).days

    if days_ago < _DAYS_SINCE_LAST_QUERY_THRESHOLD:
        return None  # 最近才查過，不需提示

    # 從上次回傳文字中無法取得當時股價，改用時間訊息提醒
    clean = _clean_code(stock_code)
    return f"📅 您上次查 {clean} 是 {days_ago} 天前，記得定期關注！"


def _advice_watchlist_compare(phone: str, stock_code: str, current_price: Optional[float]) -> Optional[str]:
    """
    關注股池比較：若使用者常查多支股票，
    在查某支時提示他的其他關注股今日表現。

    這裡只能提示「您也常查 XXX」，實際比較需呼叫端傳入資料，
    因此回傳的是「建議去查」的提示，不是即時比價。

    Returns:
        建議文字，或 None
    """
    favorites = get_user_favorite_stocks(phone, top_n=4)
    if len(favorites) < 2:
        return None

    clean_current = _clean_code(stock_code)

    # 找出除了當前查詢股以外的常查股（前 2 名）
    others = [
        f for f in favorites
        if _clean_code(f["stock_code"]) != clean_current
    ][:2]

    if not others:
        return None

    other_codes = "、".join(_clean_code(f["stock_code"]) for f in others)
    return f"💡 您也常查 {other_codes}，可傳代號查看最新股價。"


def _advice_subscription_reminder(phone: str, stock_code: str) -> Optional[str]:
    """
    訂閱提醒：如果使用者頻繁手動查這支股票卻沒有訂閱，
    提醒他可以訂閱每日通知。

    Returns:
        建議文字，或 None
    """
    clean = _clean_code(stock_code)

    # 取得此股票的查詢次數
    favorites = get_user_favorite_stocks(phone, top_n=10)
    this_stock = next(
        (f for f in favorites if _clean_code(f["stock_code"]) == clean),
        None,
    )
    if not this_stock or this_stock["count"] < 3:
        return None  # 查詢次數太少，不需提示

    # 檢查是否已有訂閱
    subs = get_user_subscriptions(phone)
    already_subscribed = any(
        _clean_code(s.stock_code) == clean for s in subs
    )
    if already_subscribed:
        return None

    return (
        f"🔔 您已查 {clean} 達 {this_stock['count']} 次，\n"
        f"傳「訂閱 {clean}」可每天自動收到通知！"
    )


def _advice_subscription_performance(phone: str, stock_code: str) -> Optional[str]:
    """
    訂閱績效提示：若使用者已訂閱此股票，
    顯示訂閱了多少天（象徵性地提醒持續追蹤的價值）。

    Returns:
        建議文字，或 None
    """
    clean = _clean_code(stock_code)
    subs = get_user_subscriptions(phone)

    target_sub = next(
        (s for s in subs if _clean_code(s.stock_code) == clean),
        None,
    )
    if not target_sub:
        return None

    sub_dt: datetime = target_sub.created_at
    if sub_dt is None:
        return None
    if sub_dt.tzinfo is None:
        sub_dt = sub_dt.replace(tzinfo=timezone.utc)

    days_subscribed = (_utc_now() - sub_dt).days
    if days_subscribed < _SUBSCRIPTION_DAYS_MIN:
        return None

    return f"📌 您已訂閱 {clean} 滿 {days_subscribed} 天，持續追蹤中。"


# ─────────────────────────────────────────
#  主函數
# ─────────────────────────────────────────

def get_personal_advice(
    phone: str,
    stock_code: str,
    current_price: Optional[float] = None,
) -> str:
    """
    根據使用者行為歷史，產生個人化附加建議。

    優先順序（由高到低，只取第一個有值的）：
        1. 頻率警示（今日查太多次）
        2. 訂閱提醒（常查但未訂閱）
        3. 訂閱績效（已訂閱幾天）
        4. 上次查價追蹤（N 天前查過）
        5. 關注股池提示（其他常查股）

    Args:
        phone:          使用者手機號碼
        stock_code:     本次查詢的股票代號（含或不含 .TW 都可）
        current_price:  當前股價（部分邏輯需要）

    Returns:
        附加建議文字，供 caller 附加在主回覆後面。
        若無建議則回傳空字串。
    """
    try:
        checks = [
            _advice_frequency_warning(phone, stock_code),
            _advice_subscription_reminder(phone, stock_code),
            _advice_subscription_performance(phone, stock_code),
            _advice_last_query_tracking(phone, stock_code, current_price),
            _advice_watchlist_compare(phone, stock_code, current_price),
        ]
        for advice in checks:
            if advice:
                return advice
        return ""
    except Exception:
        # 個人化建議是附加功能，任何錯誤都不能影響主流程
        return ""
