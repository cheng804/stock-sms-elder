"""
database.py - SQLAlchemy + SQLite 資料庫操作模組

包含 User、QueryLog、Subscription 三個 model，
以及完整的 CRUD 函數。
"""

import os
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, Text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

_RAW_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stock_sms.db")

# Render 免費 PostgreSQL 提供的 URL 以 "postgres://" 開頭，
# SQLAlchemy 2.x 只接受 "postgresql://"，需要替換。
DATABASE_URL = _RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # SQLite：單執行緒保護
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL：啟用連線池，避免 Render 免費方案閒置斷線
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,      # 每次取用連線前先 ping，自動重連
        pool_recycle=300,        # 5 分鐘回收閒置連線，防止 server 端踢掉
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─────────────────────────────────────────
#  Models
# ─────────────────────────────────────────

class User(Base):
    """使用者資料表：儲存每一支曾傳過簡訊的手機號碼。"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=False)  # 需先傳「開始」才啟用
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User phone={self.phone_number}>"


class QueryLog(Base):
    """查詢紀錄資料表：每一筆簡訊查詢都會記錄。"""
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    stock_code = Column(String(20), nullable=True)
    command_type = Column(String(30), nullable=False)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<QueryLog phone={self.phone_number} code={self.stock_code} type={self.command_type}>"


class Subscription(Base):
    """訂閱資料表：記錄使用者訂閱的股票與通知時間。"""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False)
    notify_time = Column(String(5), nullable=False, default="08:30")  # HH:MM
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Subscription phone={self.phone_number} code={self.stock_code} time={self.notify_time}>"


class PriceAlert(Base):
    """價格警報資料表：記錄使用者設定的股票到價提醒。"""
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False)
    target_price = Column(String(20), nullable=False)   # 儲存為字串，避免浮點精度問題
    direction = Column(String(5), nullable=False)        # "below"（跌破）或 "above"（突破）
    is_active = Column(Boolean, default=True)
    triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (f"<PriceAlert phone={self.phone_number} code={self.stock_code} "
                f"target={self.target_price} dir={self.direction}>")


# 建立所有資料表
Base.metadata.create_all(bind=engine)


# ─────────────────────────────────────────
#  Helper: get DB session
# ─────────────────────────────────────────

def get_db() -> Session:
    """取得資料庫 session（用完記得 close）。"""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


# ─────────────────────────────────────────
#  CRUD 函數
# ─────────────────────────────────────────

def get_or_create_user(phone: str) -> User:
    """根據手機號碼取得或建立使用者。"""
    db = get_db()
    try:
        user = db.query(User).filter(User.phone_number == phone).first()
        if not user:
            user = User(phone_number=phone, is_active=False)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def activate_user(phone: str) -> User:
    """啟用使用者（傳「開始」後呼叫）。"""
    db = get_db()
    try:
        user = db.query(User).filter(User.phone_number == phone).first()
        if not user:
            user = User(phone_number=phone, is_active=True)
            db.add(user)
        else:
            user.is_active = True
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def deactivate_user(phone: str) -> bool:
    """停用使用者（傳「停止」後呼叫）。"""
    db = get_db()
    try:
        user = db.query(User).filter(User.phone_number == phone).first()
        if user:
            user.is_active = False
            db.commit()
            return True
        return False
    finally:
        db.close()


def is_user_active(phone: str) -> bool:
    """檢查使用者是否已啟用。"""
    db = get_db()
    try:
        user = db.query(User).filter(User.phone_number == phone).first()
        return user.is_active if user else False
    finally:
        db.close()


def log_query(
    phone: str,
    stock_code: Optional[str],
    command_type: str,
    response_text: Optional[str]
) -> QueryLog:
    """
    新增一筆查詢紀錄。

    Args:
        phone: 使用者手機號碼
        stock_code: 股票代號（可為 None）
        command_type: 指令類型（price/buy_analysis/subscribe/...）
        response_text: 回傳給使用者的文字

    Returns:
        QueryLog ORM 物件
    """
    db = get_db()
    try:
        log = QueryLog(
            phone_number=phone,
            stock_code=stock_code,
            command_type=command_type,
            response_text=response_text,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    finally:
        db.close()


def add_subscription(phone: str, stock_code: str, notify_time: str = "08:30") -> Subscription:
    """
    新增或重新啟用一筆訂閱。

    若已存在相同 (phone, stock_code) 的訂閱，更新 notify_time 並設為 active。

    Args:
        phone: 使用者手機號碼
        stock_code: 股票代號
        notify_time: 通知時間，格式 HH:MM

    Returns:
        Subscription ORM 物件
    """
    db = get_db()
    try:
        sub = (
            db.query(Subscription)
            .filter(
                Subscription.phone_number == phone,
                Subscription.stock_code == stock_code,
            )
            .first()
        )
        if sub:
            sub.notify_time = notify_time
            sub.is_active = True
        else:
            sub = Subscription(
                phone_number=phone,
                stock_code=stock_code,
                notify_time=notify_time,
                is_active=True,
            )
            db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub
    finally:
        db.close()


def remove_subscription(phone: str, stock_code: str) -> bool:
    """
    取消指定使用者對某支股票的訂閱（設為 inactive）。

    Args:
        phone: 使用者手機號碼
        stock_code: 股票代號

    Returns:
        True 表示成功找到並停用，False 表示找不到
    """
    db = get_db()
    try:
        sub = (
            db.query(Subscription)
            .filter(
                Subscription.phone_number == phone,
                Subscription.stock_code == stock_code,
                Subscription.is_active == True,
            )
            .first()
        )
        if sub:
            sub.is_active = False
            db.commit()
            return True
        return False
    finally:
        db.close()


def get_all_subscriptions() -> List[Subscription]:
    """
    取得所有啟用中的訂閱。

    Returns:
        Subscription 物件列表
    """
    db = get_db()
    try:
        return db.query(Subscription).filter(Subscription.is_active == True).all()
    finally:
        db.close()


def get_subscriptions_by_time(notify_time: str) -> List[Subscription]:
    """
    取得指定通知時間的所有啟用訂閱。

    Args:
        notify_time: 格式 HH:MM

    Returns:
        Subscription 物件列表
    """
    db = get_db()
    try:
        return (
            db.query(Subscription)
            .filter(
                Subscription.notify_time == notify_time,
                Subscription.is_active == True,
            )
            .all()
        )
    finally:
        db.close()


def get_top_queried_stocks(limit: int = 5) -> List[dict]:
    """
    取得今日查詢次數最多的前 N 支股票。

    Args:
        limit: 回傳筆數，預設 5

    Returns:
        [{"stock_code": str, "count": int}, ...]
    """
    db = get_db()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        results = (
            db.query(QueryLog.stock_code, func.count(QueryLog.id).label("count"))
            .filter(
                QueryLog.stock_code.isnot(None),
                QueryLog.created_at >= today_start,
            )
            .group_by(QueryLog.stock_code)
            .order_by(func.count(QueryLog.id).desc())
            .limit(limit)
            .all()
        )
        return [{"stock_code": r.stock_code, "count": r.count} for r in results]
    finally:
        db.close()


def get_command_type_distribution() -> List[dict]:
    """
    取得今日各指令類型的查詢分佈。

    Returns:
        [{"command_type": str, "count": int}, ...]
    """
    db = get_db()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        results = (
            db.query(QueryLog.command_type, func.count(QueryLog.id).label("count"))
            .filter(QueryLog.created_at >= today_start)
            .group_by(QueryLog.command_type)
            .order_by(func.count(QueryLog.id).desc())
            .all()
        )
        return [{"command_type": r.command_type, "count": r.count} for r in results]
    finally:
        db.close()


def get_total_users() -> int:
    """
    取得總使用者人數。

    Returns:
        int 使用者總數
    """
    db = get_db()
    try:
        return db.query(func.count(User.id)).scalar() or 0
    finally:
        db.close()


def get_today_query_count() -> int:
    """
    取得今日查詢總次數。

    Returns:
        int 今日查詢次數
    """
    db = get_db()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            db.query(func.count(QueryLog.id))
            .filter(QueryLog.created_at >= today_start)
            .scalar()
            or 0
        )
    finally:
        db.close()


def get_today_sms_count() -> int:
    """
    取得今日發送簡訊總次數（等同查詢次數，每次查詢回一則簡訊）。

    Returns:
        int 今日發送簡訊次數
    """
    return get_today_query_count()


def get_active_subscription_count() -> int:
    """
    取得目前活躍訂閱總數。

    Returns:
        int 訂閱數
    """
    db = get_db()
    try:
        return db.query(func.count(Subscription.id)).filter(Subscription.is_active == True).scalar() or 0
    finally:
        db.close()


def get_recent_logs(limit: int = 50) -> List[dict]:
    """
    取得最近的查詢紀錄。

    Args:
        limit: 回傳筆數，預設 50

    Returns:
        [{"id", "phone_number", "stock_code", "command_type", "response_text", "created_at"}, ...]
    """
    db = get_db()
    try:
        logs = (
            db.query(QueryLog)
            .order_by(QueryLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": log.id,
                "phone_number": log.phone_number,
                "stock_code": log.stock_code,
                "command_type": log.command_type,
                "response_text": log.response_text,
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
            }
            for log in logs
        ]
    finally:
        db.close()


# ─────────────────────────────────────────
#  個人化分析用查詢函數
# ─────────────────────────────────────────

def get_user_query_history(phone: str, limit: int = 100) -> List[dict]:
    """
    取得指定使用者的查詢歷史（最近 N 筆）。

    Args:
        phone: 使用者手機號碼
        limit: 回傳筆數，預設 100

    Returns:
        [{"stock_code", "command_type", "created_at"}, ...]
    """
    db = get_db()
    try:
        logs = (
            db.query(QueryLog)
            .filter(
                QueryLog.phone_number == phone,
                QueryLog.stock_code.isnot(None),
            )
            .order_by(QueryLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "stock_code": log.stock_code,
                "command_type": log.command_type,
                "created_at": log.created_at,
            }
            for log in logs
        ]
    finally:
        db.close()


def get_user_favorite_stocks(phone: str, top_n: int = 3) -> List[dict]:
    """
    取得使用者最常查詢的前 N 支股票。

    Args:
        phone: 使用者手機號碼
        top_n: 回傳筆數，預設 3

    Returns:
        [{"stock_code": str, "count": int, "last_queried": datetime}, ...]
        依查詢次數由多到少排列
    """
    db = get_db()
    try:
        results = (
            db.query(
                QueryLog.stock_code,
                func.count(QueryLog.id).label("count"),
                func.max(QueryLog.created_at).label("last_queried"),
            )
            .filter(
                QueryLog.phone_number == phone,
                QueryLog.stock_code.isnot(None),
            )
            .group_by(QueryLog.stock_code)
            .order_by(func.count(QueryLog.id).desc())
            .limit(top_n)
            .all()
        )
        return [
            {
                "stock_code": r.stock_code,
                "count": r.count,
                "last_queried": r.last_queried,
            }
            for r in results
        ]
    finally:
        db.close()


def get_user_query_today_count(phone: str) -> int:
    """
    取得指定使用者今日查詢次數（含所有指令類型）。

    Args:
        phone: 使用者手機號碼

    Returns:
        今日查詢次數
    """
    db = get_db()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            db.query(func.count(QueryLog.id))
            .filter(
                QueryLog.phone_number == phone,
                QueryLog.created_at >= today_start,
            )
            .scalar()
            or 0
        )
    finally:
        db.close()


def get_user_last_query(phone: str, stock_code: str) -> Optional[dict]:
    """
    取得使用者上一次查詢特定股票的紀錄。

    Args:
        phone: 使用者手機號碼
        stock_code: 股票代號（含 .TW 後綴）

    Returns:
        {"stock_code", "command_type", "created_at"} 或 None
    """
    db = get_db()
    try:
        # 比對時去掉 .TW/.TWO 後綴，讓 2330 和 2330.TW 都能找到
        clean = stock_code.replace(".TWO", "").replace(".TW", "")
        log = (
            db.query(QueryLog)
            .filter(
                QueryLog.phone_number == phone,
                QueryLog.stock_code.ilike(f"{clean}%"),
            )
            .order_by(QueryLog.created_at.desc())
            .first()
        )
        if not log:
            return None
        return {
            "stock_code": log.stock_code,
            "command_type": log.command_type,
            "created_at": log.created_at,
        }
    finally:
        db.close()


def get_user_subscriptions(phone: str) -> List[Subscription]:
    """
    取得指定使用者的所有啟用訂閱。

    Args:
        phone: 使用者手機號碼

    Returns:
        Subscription 物件列表
    """
    db = get_db()
    try:
        return (
            db.query(Subscription)
            .filter(
                Subscription.phone_number == phone,
                Subscription.is_active == True,
            )
            .all()
        )
    finally:
        db.close()


def get_all_users_with_activity() -> List[dict]:
    """
    取得所有使用者及其活動摘要（供 Dashboard 個人分析頁用）。

    Returns:
        [{"phone_number", "is_active", "created_at",
          "total_queries", "last_query_at", "favorite_stock"}, ...]
    """
    db = get_db()
    try:
        users = db.query(User).all()
        result = []
        for user in users:
            # 計算總查詢次數與最後查詢時間
            stats = (
                db.query(
                    func.count(QueryLog.id).label("total"),
                    func.max(QueryLog.created_at).label("last_at"),
                )
                .filter(QueryLog.phone_number == user.phone_number)
                .first()
            )
            # 找最常查的股票
            top = (
                db.query(QueryLog.stock_code, func.count(QueryLog.id).label("cnt"))
                .filter(
                    QueryLog.phone_number == user.phone_number,
                    QueryLog.stock_code.isnot(None),
                )
                .group_by(QueryLog.stock_code)
                .order_by(func.count(QueryLog.id).desc())
                .first()
            )
            result.append({
                "phone_number": user.phone_number,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "total_queries": stats.total if stats else 0,
                "last_query_at": stats.last_at if stats else None,
                "favorite_stock": top.stock_code if top else None,
            })
        return result
    finally:
        db.close()


# ─────────────────────────────────────────
#  價格警報 CRUD
# ─────────────────────────────────────────

def add_alert(phone: str, stock_code: str, target_price: float, direction: str) -> PriceAlert:
    """
    新增或覆蓋一筆價格警報。
    同一 (phone, stock_code) 若已有啟用中的警報，更新目標價與方向。

    Args:
        phone:        使用者手機號碼
        stock_code:   股票代號
        target_price: 目標價格
        direction:    "below"（跌破通知）或 "above"（突破通知）

    Returns:
        PriceAlert ORM 物件
    """
    db = get_db()
    try:
        alert = (
            db.query(PriceAlert)
            .filter(
                PriceAlert.phone_number == phone,
                PriceAlert.stock_code == stock_code,
                PriceAlert.is_active == True,
            )
            .first()
        )
        if alert:
            alert.target_price = str(target_price)
            alert.direction = direction
            alert.triggered_at = None
        else:
            alert = PriceAlert(
                phone_number=phone,
                stock_code=stock_code,
                target_price=str(target_price),
                direction=direction,
                is_active=True,
            )
            db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert
    finally:
        db.close()


def remove_alert(phone: str, stock_code: str) -> bool:
    """
    取消指定使用者對某支股票的價格警報（設為 inactive）。

    Returns:
        True 表示找到並停用，False 表示找不到
    """
    db = get_db()
    try:
        alert = (
            db.query(PriceAlert)
            .filter(
                PriceAlert.phone_number == phone,
                PriceAlert.stock_code == stock_code,
                PriceAlert.is_active == True,
            )
            .first()
        )
        if alert:
            alert.is_active = False
            db.commit()
            return True
        return False
    finally:
        db.close()


def get_active_alerts() -> List[PriceAlert]:
    """取得所有啟用中的價格警報。"""
    db = get_db()
    try:
        return db.query(PriceAlert).filter(PriceAlert.is_active == True).all()
    finally:
        db.close()


def trigger_alert(alert_id: int) -> bool:
    """
    標記警報為已觸發（設 triggered_at 並停用）。

    Args:
        alert_id: PriceAlert 的 id

    Returns:
        True 表示成功
    """
    db = get_db()
    try:
        alert = db.query(PriceAlert).filter(PriceAlert.id == alert_id).first()
        if alert:
            alert.triggered_at = datetime.utcnow()
            alert.is_active = False
            db.commit()
            return True
        return False
    finally:
        db.close()


def get_all_alerts_for_dashboard() -> List[dict]:
    """
    取得所有警報（含已觸發），供 Dashboard 顯示。

    Returns:
        [{"id", "phone_number", "stock_code", "target_price",
          "direction", "is_active", "triggered_at", "created_at"}, ...]
    """
    db = get_db()
    try:
        alerts = db.query(PriceAlert).order_by(PriceAlert.created_at.desc()).all()
        return [
            {
                "id": a.id,
                "phone_number": a.phone_number,
                "stock_code": a.stock_code,
                "target_price": float(a.target_price),
                "direction": a.direction,
                "is_active": a.is_active,
                "triggered_at": a.triggered_at.strftime("%Y-%m-%d %H:%M") if a.triggered_at else "—",
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "—",
            }
            for a in alerts
        ]
    finally:
        db.close()


# ─────────────────────────────────────────
#  後台統計資料（新增）
# ─────────────────────────────────────────

def get_weekly_query_trend() -> List[dict]:
    """
    取得最近 7 天的每日查詢趨勢。
    
    Returns:
        [{"date": "2024-01-01", "count": 123}, ...]
    """
    from datetime import timedelta
    db = get_db()
    try:
        result = []
        for i in range(6, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            
            count = (
                db.query(QueryLog)
                .filter(
                    QueryLog.created_at >= start,
                    QueryLog.created_at < end,
                )
                .count()
            )
            
            result.append({
                "date": start.strftime("%m/%d"),
                "count": count,
            })
        
        return result
    finally:
        db.close()


def get_popular_stocks_with_change(limit: int = 10) -> List[dict]:
    """
    取得熱門股票及其漲跌幅（需配合 stock_fetcher）。
    
    Returns:
        [{"stock_code": "2330", "count": 50, "change_pct": 1.5}, ...]
    """
    from app.stock_fetcher import get_stock_info
    
    top_stocks = get_top_queried_stocks(limit=limit)
    
    result = []
    for stock in top_stocks:
        stock_code = stock["stock_code"]
        try:
            info = get_stock_info(stock_code)
            change_pct = info.get("change_percent", 0) if info.get("success") else 0
        except Exception:
            change_pct = 0
        
        result.append({
            "stock_code": stock_code,
            "name": stock.get("name", stock_code),
            "count": stock["count"],
            "change_pct": change_pct,
        })
    
    return result


def get_user_engagement_stats() -> dict:
    """
    取得使用者參與度統計。
    
    Returns:
        {
            "active_users_today": int,      # 今天有查詢的使用者數
            "subscribers": int,              # 有訂閱的使用者數
            "alert_users": int,              # 有設定警報的使用者數
            "avg_queries_per_user": float,   # 平均每人查詢次數
        }
    """
    db = get_db()
    try:
        # 今天有查詢的使用者數
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        active_today = (
            db.query(QueryLog.phone_number)
            .filter(QueryLog.created_at >= today_start)
            .distinct()
            .count()
        )
        
        # 有訂閱的使用者數
        subscribers = (
            db.query(Subscription.phone_number)
            .filter(Subscription.is_active == True)
            .distinct()
            .count()
        )
        
        # 有設定警報的使用者數
        alert_users = (
            db.query(PriceAlert.phone_number)
            .filter(PriceAlert.is_active == True)
            .distinct()
            .count()
        )
        
        # 平均每人查詢次數（全部時間）
        total_queries = db.query(QueryLog).count()
        total_users = db.query(User).count()
        avg_queries = round(total_queries / total_users, 1) if total_users > 0 else 0
        
        return {
            "active_users_today": active_today,
            "subscribers": subscribers,
            "alert_users": alert_users,
            "avg_queries_per_user": avg_queries,
        }
    finally:
        db.close()


def get_command_type_stats_today() -> List[dict]:
    """
    取得今天各指令類型的統計（更詳細版本）。
    
    Returns:
        [{"type": "price", "count": 50, "label": "查股價"}, ...]
    """
    db = get_db()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        from sqlalchemy import func
        results = (
            db.query(
                QueryLog.query_type,
                func.count(QueryLog.id).label("count")
            )
            .filter(QueryLog.created_at >= today_start)
            .group_by(QueryLog.query_type)
            .order_by(func.count(QueryLog.id).desc())
            .all()
        )
        
        type_labels = {
            "price": "查股價",
            "buy_analysis": "買賣分析",
            "week_report": "週報告",
            "subscribe": "訂閱",
            "unsubscribe": "退訂",
            "set_alert": "設定警報",
            "remove_alert": "取消警報",
            "help": "說明",
            "safe_pick": "推薦股票",
            "unknown": "無法識別",
        }
        
        return [
            {
                "type": r.query_type,
                "label": type_labels.get(r.query_type, r.query_type),
                "count": r.count,
            }
            for r in results
        ]
    finally:
        db.close()


def get_recent_logs(limit: int = 50) -> List[dict]:
    """
    取得最近的查詢紀錄。

    Args:
        limit: 回傳筆數

    Returns:
        查詢紀錄列表
    """
    db = get_db()
    try:
        logs = (
            db.query(QueryLog)
            .order_by(QueryLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
                "phone_number": log.phone_number or "",
                "stock_code": log.stock_code or "",
                "command_type": log.command_type or "",
                "response_text": log.response_text or "",
            }
            for log in logs
        ]
    finally:
        db.close()


def get_all_users_with_activity() -> List[dict]:
    """
    取得所有使用者及其活動統計。

    Returns:
        使用者活動列表
    """
    db = get_db()
    try:
        users = db.query(User).all()
        result = []
        for user in users:
            # 計算總查詢次數
            total_queries = (
                db.query(QueryLog)
                .filter(QueryLog.phone_number == user.phone_number)
                .count()
            )
            
            # 取得最後查詢時間
            last_log = (
                db.query(QueryLog)
                .filter(QueryLog.phone_number == user.phone_number)
                .order_by(QueryLog.created_at.desc())
                .first()
            )
            
            # 取得最愛股票（查詢次數最多的）
            favorite = (
                db.query(
                    QueryLog.stock_code,
                    func.count(QueryLog.stock_code).label("count")
                )
                .filter(
                    QueryLog.phone_number == user.phone_number,
                    QueryLog.stock_code.isnot(None),
                )
                .group_by(QueryLog.stock_code)
                .order_by(func.count(QueryLog.stock_code).desc())
                .first()
            )
            
            result.append({
                "phone_number": user.phone_number,
                "is_active": user.is_active,
                "total_queries": total_queries,
                "last_query_at": last_log.created_at if last_log else None,
                "favorite_stock": favorite[0].replace(".TW", "").replace(".TWO", "") if favorite else None,
                "created_at": user.created_at,
            })
        
        return result
    finally:
        db.close()


def get_user_query_today_count(phone: str) -> int:
    """
    取得使用者今日查詢次數。

    Args:
        phone: 使用者手機號碼

    Returns:
        今日查詢次數
    """
    from datetime import datetime, time
    
    db = get_db()
    try:
        today_start = datetime.combine(datetime.today(), time.min)
        count = (
            db.query(QueryLog)
            .filter(
                QueryLog.phone_number == phone,
                QueryLog.created_at >= today_start,
            )
            .count()
        )
        return count
    finally:
        db.close()


def get_all_alerts_for_dashboard() -> List[dict]:
    """
    取得所有價格警報（供 Dashboard 使用）。

    Returns:
        警報列表
    """
    db = get_db()
    try:
        alerts = db.query(PriceAlert).order_by(PriceAlert.created_at.desc()).all()
        return [
            {
                "phone_number": alert.phone_number,
                "stock_code": alert.stock_code,
                "target_price": float(alert.target_price),
                "direction": alert.direction,
                "is_active": alert.is_active,
                "triggered_at": alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S") if alert.triggered_at else None,
                "created_at": alert.created_at.strftime("%Y-%m-%d %H:%M:%S") if alert.created_at else "",
            }
            for alert in alerts
        ]
    finally:
        db.close()
