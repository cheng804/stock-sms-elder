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

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stock_sms.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
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
    """
    根據手機號碼取得或建立使用者。

    Args:
        phone: 手機號碼字串

    Returns:
        User ORM 物件
    """
    db = get_db()
    try:
        user = db.query(User).filter(User.phone_number == phone).first()
        if not user:
            user = User(phone_number=phone)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
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
