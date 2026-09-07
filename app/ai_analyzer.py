"""
ai_analyzer.py - AI 白話文分析模組

使用 OpenAI API 將股票資料轉換成長輩友善的白話文說明。
若未設定 API Key，自動 fallback 到純格式化輸出。
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ─────────────────────────────────────────
#  格式化工具函數
# ─────────────────────────────────────────

def _format_change_arrow(change: Optional[float]) -> str:
    """將漲跌數字轉成箭頭符號。"""
    if change is None:
        return "－"
    if change > 0:
        return f"▲{change:.2f}"
    if change < 0:
        return f"▼{abs(change):.2f}"
    return f"－{change:.2f}"


def _format_change_pct(pct: Optional[float]) -> str:
    """將漲跌幅格式化，加上 +/- 符號。"""
    if pct is None:
        return ""
    sign = "+" if pct > 0 else ""
    return f"({sign}{pct:.2f}%)"


def format_simple_response(stock_info: dict, query_type: str) -> str:
    """
    不依賴 AI，直接把股票資料格式化為簡訊友善的文字。

    格式設計原則：
    - 不超過 160 字（SMS 單則限制）
    - 使用大字體符號方便老人家閱讀
    - 語氣親切

    Args:
        stock_info: get_stock_info() 回傳的 dict
        query_type: "price" 或 "buy_analysis"

    Returns:
        格式化後的字串
    """
    if not stock_info.get("success"):
        error_msg = stock_info.get("error", "查詢失敗")
        return f"😅 找不到這支股票\n{error_msg}\n\n請確認代號是否正確，例如傳「2330」查台積電。"

    name = stock_info.get("name", stock_info.get("code", "未知"))
    code = stock_info.get("code", "").replace(".TW", "")
    price = stock_info.get("price")
    change = stock_info.get("change")
    change_pct = stock_info.get("change_percent")

    price_str = f"{price:.2f}" if price is not None else "－"
    change_str = _format_change_arrow(change)
    pct_str = _format_change_pct(change_pct)

    if query_type == "price":
        lines = [
            f"📈 {name}({code})",
            f"股價：{price_str} 元",
            f"漲跌：{change_str} {pct_str}",
        ]
        high = stock_info.get("high")
        low = stock_info.get("low")
        if high and low:
            lines.append(f"今日區間：{low:.2f}～{high:.2f}")
        if change and change > 0:
            lines.append("今天有漲喔！")
        elif change and change < 0:
            lines.append("今天有跌，別擔心！")
        else:
            lines.append("今天持平。")
        return "\n".join(lines)

    elif query_type == "buy_analysis":
        open_p = stock_info.get("open")
        prev_close = stock_info.get("prev_close")

        lines = [
            f"📊 {name}({code}) 買賣參考",
            f"現價：{price_str} 元",
            f"漲跌：{change_str} {pct_str}",
        ]
        if prev_close:
            lines.append(f"昨收：{prev_close:.2f} 元")

        # 簡單建議（沒有歷史資料時的 fallback）
        if change_pct is not None:
            if change_pct > 3:
                lines.append("⚠️ 今天漲比較多，要買的話可以等回檔。")
            elif change_pct < -3:
                lines.append("💡 今天跌比較多，可能是低點，但要小心。")
            else:
                lines.append("目前股價變動不大，可依自身判斷決定。")
        lines.append("投資有風險，請謹慎評估！")
        return "\n".join(lines)

    else:
        return (
            f"📈 {name}({code})\n"
            f"股價：{price_str} 元  漲跌：{change_str} {pct_str}"
        )


# ─────────────────────────────────────────
#  AI 分析（OpenAI）
# ─────────────────────────────────────────

def generate_elder_friendly_analysis(
    stock_info: dict,
    history: Optional[dict],
    query_type: str,
) -> str:
    """
    呼叫 OpenAI API，用長輩口吻生成白話分析文字。

    若 OPENAI_API_KEY 未設定，自動 fallback 到 format_simple_response()。

    Args:
        stock_info: get_stock_info() 回傳的 dict
        history: get_stock_history() 回傳的 dict（可為 None）
        query_type: "price" 或 "buy_analysis"

    Returns:
        給使用者看的分析文字（不超過 160 字）
    """
    if not OPENAI_API_KEY:
        # 沒有 API Key，用簡單格式
        if query_type == "buy_analysis" and history and history.get("success"):
            return _format_with_history(stock_info, history)
        return format_simple_response(stock_info, query_type)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        # 準備資料摘要給 AI
        name = stock_info.get("name", "")
        code = stock_info.get("code", "").replace(".TW", "")
        price = stock_info.get("price", "N/A")
        change = stock_info.get("change", 0)
        change_pct = stock_info.get("change_percent", 0)
        high = stock_info.get("high", "N/A")
        low = stock_info.get("low", "N/A")

        avg_30d = history.get("avg_price") if history and history.get("success") else None

        if query_type == "price":
            prompt = f"""
你是一個幫台灣長輩看股票的助手，請用親切白話的台灣口語說明今天的股票狀況。
注意：
1. 用長輩能懂的比喻，例如「漲了一碗麵的錢」這樣
2. 不要用太多專業術語
3. 整段回覆不超過 100 字
4. 可以加 emoji

股票資訊：
- 名稱：{name}（{code}）
- 現價：{price} 元
- 今日漲跌：{change} 元（{change_pct}%）
- 今日高低：{high}～{low}

請用一段話說明今天漲跌情況，讓長輩看得懂。
""".strip()

        else:  # buy_analysis
            prompt = f"""
你是一個幫台灣長輩看股票的助手，請用親切白話的台灣口語分析這支股票現在貴不貴、要不要買。
注意：
1. 用長輩能懂的比喻
2. 不要用太多專業術語
3. 整段回覆不超過 120 字
4. 可以加 emoji
5. 最後要提醒「投資有風險」

股票資訊：
- 名稱：{name}（{code}）
- 現價：{price} 元
- 今日漲跌：{change} 元（{change_pct}%）
- 近 30 天平均價：{avg_30d if avg_30d else '無資料'} 元

請分析這支股票目前貴不貴，給長輩一個簡單建議。
""".strip()

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一個用台灣白話文幫長輩看股票的親切助手，說話像鄰居阿伯一樣自然。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.7,
        )
        ai_text = response.choices[0].message.content.strip()

        # 保護性截斷，簡訊不能太長
        if len(ai_text) > 300:
            ai_text = ai_text[:297] + "..."

        return ai_text

    except Exception as e:
        # AI 失敗就 fallback
        if query_type == "buy_analysis" and history and history.get("success"):
            return _format_with_history(stock_info, history)
        return format_simple_response(stock_info, query_type)


def _format_with_history(stock_info: dict, history: dict) -> str:
    """
    結合歷史資料，輸出較豐富的買賣分析（不使用 AI）。

    Args:
        stock_info: 即時股票資訊
        history: 歷史資料（含 avg_price）

    Returns:
        格式化字串
    """
    name = stock_info.get("name", stock_info.get("code", ""))
    code = stock_info.get("code", "").replace(".TW", "")
    price = stock_info.get("price")
    change = stock_info.get("change")
    change_pct = stock_info.get("change_percent")
    avg_30d = history.get("avg_price")

    price_str = f"{price:.2f}" if price else "－"
    change_str = _format_change_arrow(change)
    pct_str = _format_change_pct(change_pct)

    lines = [
        f"📊 {name}({code}) 買賣參考",
        f"現價：{price_str} 元 {change_str} {pct_str}",
    ]

    if avg_30d and price:
        lines.append(f"近30天均價：{avg_30d:.2f} 元")
        diff_pct = (price - avg_30d) / avg_30d * 100
        if diff_pct < -5:
            lines.append("💡 現在比近期均價便宜，有買的機會！")
        elif diff_pct > 5:
            lines.append("⚠️ 現在比近期均價貴，要考慮清楚再買。")
        else:
            lines.append("目前股價在合理範圍內。")
    else:
        lines.append("無法取得均價資料。")

    lines.append("投資有風險，請謹慎！")
    return "\n".join(lines)
