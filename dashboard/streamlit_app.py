"""
streamlit_app.py - 股票簡訊服務管理後台

使用 Streamlit 建立視覺化管理介面，顯示：
- KPI 卡片（總使用者、今日查詢、今日簡訊、活躍訂閱）
- 今日 Top 5 查詢股票（橫向長條圖）
- 查詢指令類型分佈（圓餅圖）
- 即時查詢紀錄表格
- 訂閱管理列表

執行方式：
    cd stock-sms-elder
    streamlit run dashboard/streamlit_app.py
"""

import sys
import os
import time
from datetime import datetime
from pathlib import Path

# 確保能 import app 模組（從 dashboard/ 執行時需要往上一層）
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import requests

# ─────────────────────────────────────────
#  頁面設定
# ─────────────────────────────────────────

st.set_page_config(
    page_title="股票簡訊服務 - 管理後台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
#  常數設定
# ─────────────────────────────────────────

API_BASE_URL = os.getenv("API_BASE_URL", "https://stock-sms-elder.onrender.com")
REFRESH_INTERVAL = 30  # 秒

# 指令類型中文對照
COMMAND_TYPE_LABELS = {
    "price": "查股價",
    "buy_analysis": "買賣分析",
    "subscribe": "訂閱",
    "unsubscribe": "退訂",
    "help": "說明",
    "unknown": "無法識別",
    "subscription_notify": "訂閱通知",
}


# ─────────────────────────────────────────
#  資料載入函數
# ─────────────────────────────────────────

@st.cache_data(ttl=10)
def load_stats() -> dict:
    """
    從 FastAPI 取得統計資料，失敗時嘗試直接讀 DB。

    Returns:
        統計資料 dict
    """
    try:
        resp = requests.get(f"{API_BASE_URL}/api/stats", timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # Fallback：直接讀資料庫
    try:
        from app.database import (
            get_total_users, get_today_query_count, get_today_sms_count,
            get_active_subscription_count, get_top_queried_stocks,
            get_command_type_distribution,
        )
        return {
            "total_users": get_total_users(),
            "today_queries": get_today_query_count(),
            "today_sms_sent": get_today_sms_count(),
            "active_subscriptions": get_active_subscription_count(),
            "top_stocks": get_top_queried_stocks(limit=5),
            "command_distribution": get_command_type_distribution(),
        }
    except Exception as e:
        st.error(f"無法載入統計資料：{e}")
        return {}


@st.cache_data(ttl=10)
def load_logs(limit: int = 50) -> list:
    """
    從 FastAPI 或直接從 DB 取得查詢紀錄。

    Args:
        limit: 回傳筆數

    Returns:
        log 列表
    """
    try:
        resp = requests.get(f"{API_BASE_URL}/api/logs?limit={limit}", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("logs", [])
    except Exception:
        pass

    # Fallback
    try:
        from app.database import get_recent_logs
        return get_recent_logs(limit=limit)
    except Exception as e:
        st.error(f"無法載入查詢紀錄：{e}")
        return []


@st.cache_data(ttl=30)
def load_user_activity() -> list:
    """
    載入所有使用者活動摘要（個人分析頁用）。

    Returns:
        使用者活動摘要列表
    """
    try:
        from app.database import get_all_users_with_activity
        rows = get_all_users_with_activity()
        result = []
        for r in rows:
            last_at = r.get("last_query_at")
            created = r.get("created_at")
            result.append({
                "手機後4碼": f"****{r['phone_number'][-4:]}" if r["phone_number"] and len(r["phone_number"]) >= 4 else r["phone_number"],
                "狀態": "✅ 啟用" if r["is_active"] else "⛔ 停用",
                "最愛股票": r.get("favorite_stock") or "—",
                "總查詢次數": r.get("total_queries", 0),
                "最後查詢": last_at.strftime("%Y-%m-%d %H:%M") if last_at else "—",
                "加入日期": created.strftime("%Y-%m-%d") if created else "—",
                "_phone": r["phone_number"],
            })
        return result
    except Exception as e:
        st.error(f"無法載入使用者活動：{e}")
        return []


@st.cache_data(ttl=30)
def load_user_favorites(phone: str) -> list:
    """
    載入特定使用者的關注股池。

    Args:
        phone: 手機號碼

    Returns:
        [{"stock_code", "count", "last_queried"}, ...]
    """
    try:
        from app.database import get_user_favorite_stocks
        return get_user_favorite_stocks(phone, top_n=10)
    except Exception:
        return []


@st.cache_data(ttl=30)
def load_user_recent_logs(phone: str) -> list:
    """
    載入特定使用者最近 20 筆查詢紀錄。

    Args:
        phone: 手機號碼

    Returns:
        查詢紀錄列表
    """
    try:
        from app.database import get_user_query_history
        return get_user_query_history(phone, limit=20)
    except Exception:
        return []


@st.cache_data(ttl=10)
def load_subscriptions() -> list:
    """
    直接從資料庫讀取所有啟用訂閱。

    Returns:
        Subscription 資料列表
    """
    try:
        from app.database import get_all_subscriptions
        subs = get_all_subscriptions()
        return [
            {
                "手機後4碼": sub.phone_number[-4:] if len(sub.phone_number) >= 4 else sub.phone_number,
                "完整號碼": sub.phone_number,
                "股票代號": sub.stock_code,
                "通知時間": sub.notify_time,
                "建立時間": sub.created_at.strftime("%Y-%m-%d %H:%M") if sub.created_at else "",
            }
            for sub in subs
        ]
    except Exception as e:
        st.error(f"無法載入訂閱資料：{e}")
        return []


def check_api_status() -> bool:
    """
    檢查 FastAPI 服務是否在線。

    Returns:
        True 表示服務中
    """
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ 系統控制台")
    st.divider()

    # 服務狀態
    api_online = check_api_status()
    if api_online:
        st.success("🟢 服務中")
    else:
        st.error("🔴 離線（API 無法連線）")

    st.caption(f"API: {API_BASE_URL}")
    st.divider()

    # 最後更新時間
    st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
    st.caption(f"每 {REFRESH_INTERVAL} 秒自動重新整理")

    if st.button("🔄 立即重新整理"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**操作說明**")
    st.markdown(
        "- 傳 `2330` 查台積電\n"
        "- 傳 `2330買` 做買賣分析\n"
        "- 傳 `訂閱 2330 08:30` 訂閱\n"
        "- 傳 `取消 2330` 退訂\n"
        "- 傳 `說明` 看完整指令"
    )


# ─────────────────────────────────────────
#  主標題
# ─────────────────────────────────────────

st.title("📊 股票簡訊服務 - 管理後台")
st.caption("老人機傳簡訊查股票 · 即時統計與管理介面")
st.divider()

# 載入資料
stats = load_stats()

# ─────────────────────────────────────────
#  KPI 卡片
# ─────────────────────────────────────────

st.subheader("📈 今日總覽")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric(
        label="👴 總服務人數",
        value=stats.get("total_users", 0),
    )

with kpi2:
    st.metric(
        label="🔍 今日查詢次數",
        value=stats.get("today_queries", 0),
    )

with kpi3:
    st.metric(
        label="📨 今日發送簡訊",
        value=stats.get("today_sms_sent", 0),
    )

with kpi4:
    st.metric(
        label="🔔 活躍訂閱數",
        value=stats.get("active_subscriptions", 0),
    )

st.divider()

# ─────────────────────────────────────────
#  圖表區
# ─────────────────────────────────────────

st.subheader("📊 分析圖表")
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**今日 Top 5 查詢股票**")
    top_stocks = stats.get("top_stocks", [])

    if top_stocks:
        df_stocks = pd.DataFrame(top_stocks)
        df_stocks.columns = ["股票代號", "查詢次數"]
        df_stocks = df_stocks.sort_values("查詢次數", ascending=True)

        fig_bar = px.bar(
            df_stocks,
            x="查詢次數",
            y="股票代號",
            orientation="h",
            color="查詢次數",
            color_continuous_scale="Blues",
            text="查詢次數",
            height=300,
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=10, r=20, t=10, b=10),
            xaxis_title="查詢次數",
            yaxis_title="",
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("今日尚無查詢紀錄")

with chart_col2:
    st.markdown("**查詢指令類型分佈**")
    cmd_dist = stats.get("command_distribution", [])

    if cmd_dist:
        df_cmd = pd.DataFrame(cmd_dist)
        df_cmd.columns = ["指令類型", "次數"]
        # 轉換成中文標籤
        df_cmd["指令類型"] = df_cmd["指令類型"].map(
            lambda x: COMMAND_TYPE_LABELS.get(x, x)
        )

        fig_pie = px.pie(
            df_cmd,
            values="次數",
            names="指令類型",
            color_discrete_sequence=px.colors.qualitative.Set3,
            height=300,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("今日尚無查詢紀錄")

st.divider()

# ─────────────────────────────────────────
#  即時查詢紀錄
# ─────────────────────────────────────────

st.subheader("📋 即時查詢紀錄（最近 50 筆）")

logs = load_logs(limit=50)

if logs:
    # 資料處理
    df_logs = pd.DataFrame(logs)

    # 手機號碼遮蔽：只顯示後 4 碼
    if "phone_number" in df_logs.columns:
        df_logs["手機（後4碼）"] = df_logs["phone_number"].apply(
            lambda x: f"****{x[-4:]}" if x and len(x) >= 4 else x
        )

    # 指令類型中文化
    if "command_type" in df_logs.columns:
        df_logs["指令類型"] = df_logs["command_type"].map(
            lambda x: COMMAND_TYPE_LABELS.get(x, x)
        )

    # 回傳內容摘要（最多 50 字）
    if "response_text" in df_logs.columns:
        df_logs["回傳內容摘要"] = df_logs["response_text"].apply(
            lambda x: (x[:50] + "…") if x and len(x) > 50 else (x or "")
        )

    # 選取顯示欄位
    display_cols = {
        "created_at": "時間",
        "手機（後4碼）": "手機（後4碼）",
        "stock_code": "股票代號",
        "指令類型": "指令類型",
        "回傳內容摘要": "回傳內容摘要",
    }

    show_cols = [c for c in display_cols.keys() if c in df_logs.columns]
    df_display = df_logs[show_cols].rename(columns=display_cols)

    st.dataframe(
        df_display,
        use_container_width=True,
        height=400,
        hide_index=True,
    )
    st.caption(f"共 {len(logs)} 筆紀錄")
else:
    st.info("目前尚無查詢紀錄")

st.divider()

# ─────────────────────────────────────────
#  訂閱管理
# ─────────────────────────────────────────

st.subheader("🔔 訂閱管理")

subs = load_subscriptions()

if subs:
    df_subs = pd.DataFrame(subs)
    # 不顯示完整號碼欄
    display_subs = df_subs.drop(columns=["完整號碼"], errors="ignore")
    st.dataframe(display_subs, use_container_width=True, hide_index=True)
    st.caption(f"共 {len(subs)} 筆啟用訂閱")
else:
    st.info("目前沒有啟用中的訂閱")

st.divider()

# ─────────────────────────────────────────
#  個人化分析
# ─────────────────────────────────────────

st.subheader("👤 使用者個人分析")

user_activity = load_user_activity()

if not user_activity:
    st.info("目前尚無使用者資料")
else:
    # ── 總覽表格 ──────────────────────────
    df_users = pd.DataFrame(user_activity)
    display_cols = ["手機後4碼", "狀態", "最愛股票", "總查詢次數", "最後查詢", "加入日期"]
    st.dataframe(
        df_users[display_cols],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # ── 個別使用者深入分析 ────────────────
    st.markdown("**🔍 個別使用者深入分析**")

    # 下拉選單：只顯示後4碼，但存完整號碼
    phone_options = {
        row["手機後4碼"]: row["_phone"]
        for row in user_activity
    }
    selected_label = st.selectbox(
        "選擇使用者",
        options=list(phone_options.keys()),
        index=0,
    )
    selected_phone = phone_options[selected_label]

    col_left, col_right = st.columns(2)

    # ── 左欄：關注股池長條圖 ──────────────
    with col_left:
        st.markdown("**關注股池（查詢次數）**")
        favorites = load_user_favorites(selected_phone)

        if favorites:
            df_fav = pd.DataFrame(favorites)
            # 移除 .TW/.TWO 後綴讓圖表更簡潔
            df_fav["stock_code"] = df_fav["stock_code"].str.replace(
                r"\.(TW|TWO)$", "", regex=True
            )
            df_fav = df_fav.rename(columns={"stock_code": "股票代號", "count": "查詢次數"})
            df_fav = df_fav.sort_values("查詢次數", ascending=True)

            fig_fav = px.bar(
                df_fav,
                x="查詢次數",
                y="股票代號",
                orientation="h",
                color="查詢次數",
                color_continuous_scale="Teal",
                text="查詢次數",
                height=max(200, len(df_fav) * 45),
            )
            fig_fav.update_traces(textposition="outside")
            fig_fav.update_layout(
                showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=10, r=20, t=10, b=10),
                xaxis_title="查詢次數",
                yaxis_title="",
            )
            st.plotly_chart(fig_fav, use_container_width=True)
        else:
            st.info("此使用者尚無股票查詢紀錄")

    # ── 右欄：最近查詢時間軸 ──────────────
    with col_right:
        st.markdown("**最近查詢紀錄**")
        recent = load_user_recent_logs(selected_phone)

        if recent:
            cmd_labels = {
                "price": "查股價",
                "buy_analysis": "買賣分析",
                "subscribe": "訂閱",
                "unsubscribe": "退訂",
                "help": "說明",
                "unknown": "未知",
            }
            df_recent = pd.DataFrame(recent)
            df_recent["股票代號"] = df_recent["stock_code"].str.replace(
                r"\.(TW|TWO)$", "", regex=True
            )
            df_recent["指令"] = df_recent["command_type"].map(
                lambda x: cmd_labels.get(x, x)
            )
            df_recent["時間"] = pd.to_datetime(df_recent["created_at"]).dt.strftime(
                "%m/%d %H:%M"
            )
            st.dataframe(
                df_recent[["時間", "股票代號", "指令"]],
                use_container_width=True,
                hide_index=True,
                height=300,
            )
        else:
            st.info("此使用者尚無查詢紀錄")

    # ── 行為指標卡片 ──────────────────────
    st.markdown("**行為指標**")
    selected_row = next(r for r in user_activity if r["_phone"] == selected_phone)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("總查詢次數", selected_row["總查詢次數"])
    with m2:
        st.metric("最愛股票", selected_row["最愛股票"])
    with m3:
        fav_count = len(favorites) if favorites else 0
        st.metric("關注股票數", fav_count)
    with m4:
        # 計算今日查詢次數
        try:
            from app.database import get_user_query_today_count
            today_cnt = get_user_query_today_count(selected_phone)
        except Exception:
            today_cnt = "—"
        st.metric("今日查詢次數", today_cnt)

st.divider()

# ─────────────────────────────────────────
#  價格警報管理
# ─────────────────────────────────────────

st.subheader("🔔 價格警報管理")

@st.cache_data(ttl=15)
def load_alerts() -> list:
    try:
        from app.database import get_all_alerts_for_dashboard
        return get_all_alerts_for_dashboard()
    except Exception as e:
        st.error(f"無法載入警報資料：{e}")
        return []

alerts = load_alerts()

if alerts:
    df_alerts = pd.DataFrame(alerts)
    df_alerts["手機後4碼"] = df_alerts["phone_number"].apply(
        lambda x: f"****{x[-4:]}" if x and len(x) >= 4 else x
    )
    df_alerts["股票代號"] = df_alerts["stock_code"].str.replace(
        r"\.(TW|TWO)$", "", regex=True
    )
    df_alerts["目標價"] = df_alerts["target_price"].apply(lambda x: f"{x:.0f} 元")
    df_alerts["方向"] = df_alerts["direction"].map(
        {"below": "📉 跌破", "above": "📈 突破"}
    )
    df_alerts["狀態"] = df_alerts["is_active"].map(
        {True: "⏳ 監控中", False: "✅ 已觸發"}
    )

    display_cols = ["手機後4碼", "股票代號", "目標價", "方向", "狀態", "triggered_at", "created_at"]
    df_show = df_alerts[display_cols].rename(columns={
        "triggered_at": "觸發時間",
        "created_at": "設定時間",
    })
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    active_count = sum(1 for a in alerts if a["is_active"])
    triggered_count = len(alerts) - active_count
    c1, c2 = st.columns(2)
    with c1:
        st.metric("⏳ 監控中", active_count)
    with c2:
        st.metric("✅ 已觸發", triggered_count)
else:
    st.info("目前沒有設定任何價格警報")

# ─────────────────────────────────────────
#  自動重新整理
# ─────────────────────────────────────────

st.divider()
st.caption(f"⏱ 頁面將在 {REFRESH_INTERVAL} 秒後自動重新整理...")

time.sleep(REFRESH_INTERVAL)
st.cache_data.clear()
st.rerun()
