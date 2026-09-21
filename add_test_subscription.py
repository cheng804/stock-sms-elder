"""
手動新增測試訂閱到本地資料庫
"""
from app.database import get_db, Subscription, User
from datetime import datetime

def add_test_subscription():
    db = get_db()
    try:
        phone = "0982018407"
        
        # 1. 確保用戶存在
        user = db.query(User).filter(User.phone_number == phone).first()
        if not user:
            user = User(
                phone_number=phone,
                is_active=True,
                created_at=datetime.now()
            )
            db.add(user)
            db.commit()
            print(f"✅ 新增用戶: {phone}")
        else:
            print(f"✓ 用戶已存在: {phone}")
        
        # 2. 檢查訂閱是否已存在
        existing = db.query(Subscription).filter(
            Subscription.phone_number == phone,
            Subscription.stock_code == "0050.TW"
        ).first()
        
        if existing:
            # 更新為啟用
            existing.is_active = True
            existing.notify_time = "08:30"
            db.commit()
            print(f"✅ 更新訂閱: {phone} -> 0050")
        else:
            # 新增訂閱
            subscription = Subscription(
                phone_number=phone,
                stock_code="0050.TW",
                notify_time="08:30",
                is_active=True,
                created_at=datetime.now()
            )
            db.add(subscription)
            db.commit()
            print(f"✅ 新增訂閱: {phone} -> 0050 @ 08:30")
        
        # 3. 列出所有訂閱
        print("\n📋 當前所有訂閱:")
        all_subs = db.query(Subscription).filter(Subscription.is_active == True).all()
        for sub in all_subs:
            phone_display = sub.phone_number[-4:] if len(sub.phone_number) >= 4 else sub.phone_number
            stock = sub.stock_code.replace(".TW", "").replace(".TWO", "")
            print(f"  - ****{phone_display}: {stock} @ {sub.notify_time}")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_test_subscription()
