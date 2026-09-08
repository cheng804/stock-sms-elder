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


def _clean_code(code: str) -> str:
    """移除 .TW / .TWO 後綴"""
    return code.replace(".TWO", "").replace(".TW", "")


def _format_change_arrow(change: Optional[float]) -> str:
    if change is None:
        return "－"
    if change > 0:
        return f"▲{change:.2f}"
    if change < 0:
        return f"▼{abs(change):.2f}"
    return f"－{change:.2f}"


def _format_change_pct(pct: Optional[float]) -> str:
    if pct is None:
        return ""
    sign = "+" if pct > 0 else ""
    return f"({sign}{pct:.2f}%)"


def format_simple_response(stock_info: dict, query_type: str) -> str:
    """不依賴 AI，直接格式化成簡訊文字。"""
    if not stock_info.get("success"):
        error_msg = stock_info.get("error", "查詢失敗")
        return f"😅 找不到這支股票\n{error_msg}\n\n請確認代號是否正確，例如傳「2330」查台積電。"

    name = stock_info.get("name", stock_info.get("code", "未知"))
    code = _clean_code(stock_info.get("code", ""))
    price = stock_info.get("price")
    change = stock_info.get("change")
    change_pct = stock_info.get("change_percent")

    price_str = f"{price:.2f}" if price is not None else "－"
    change_str = _format_change_arrow(change)
    pct_str = _format_change_pct(change_pct)

    if query_type == "price":
        lines = [
            f"📈 {name}",
            f"代號：{code}",
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
        prev_close = stock_info.get("prev_close")
        lines = [
            f"📊 {name}（{code}）買賣參考",
            f"現價：{price_str} 元",
            f"漲跌：{change_str} {pct_str}",
        ]
        if prev_close:
            lines.append(f"昨收：{prev_close:.2f} 元")
        if change_pct is not None:
            if change_pct > 3:
                lines.append("⚠️ 今天漲較多，可等回檔再買。")
            elif change_pct < -3:
                lines.append("💡 今天跌較多，留意低點機會。")
            else:
                lines.append("目前股價變動不大。")
        lines.append("投資有風險，請謹慎！")
        return "\n".join(lines)

    else:
        return f"📈 {name}（{code}）\n股價：{price_str} 元  漲跌：{change_str} {pct_str}"


def _format_with_history(stock_info: dict, history: dict) -> str:
    """結合歷史資料的買賣分析（不使用 AI）。"""
    name = stock_info.get("name", stock_info.get("code", ""))
    code = _clean_code(stock_info.get("code", ""))
    price = stock_info.get("price")
    change = stock_info.get("change")
    change_pct = stock_info.get("change_percent")
    avg_30d = history.get("avg_price")

    price_str = f"{price:.2f}" if price else "－"
    change_str = _format_change_arrow(change)
    pct_str = _format_change_pct(change_pct)

    lines = [
        f"📊 {name}（{code}）買賣參考",
        f"現價：{price_str} 元 {change_str} {pct_str}",
    ]

    if avg_30d and price:
        lines.append(f"近30天均價：{avg_30d:.2f} 元")
        diff_pct = (price - avg_30d) / avg_30d * 100
        if diff_pct < -5:
            lines.append("💡 現在比均價便宜，可考慮！")
        elif diff_pct > 5:
            lines.append("⚠️ 現在比均價貴，要考慮清楚。")
        else:
            lines.append("目前股價在合理範圍內。")
    else:
        lines.append("無法取得均價資料。")

    lines.append("投資有風險，請謹慎！")
    return "\n".join(lines)


def generate_elder_friendly_analysis(
    stock_info: dict,
    history: Optional[dict],
    query_type: str,
) -> str:
    """
    呼叫 OpenAI API，用長輩口吻生成簡短白話分析。
    若 OPENAI_API_KEY 未設定，自動 fallback。
    """
    if not OPENAI_API_KEY:
        if query_type == "buy_analysis" and history and history.get("success"):
            return _format_with_history(stock_info, history)
        return format_simple_response(stock_info, query_type)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        name = stock_info.get("name", "")
        code = _clean_code(stock_info.get("code", ""))
        price = stock_info.get("price", "N/A")
        change = stock_info.get("change", 0)
        change_pct = stock_info.get("change_percent", 0)
        high = stock_info.get("high", "N/A")
        low = stock_info.get("low", "N/A")
        avg_30d = history.get("avg_price") if history and history.get("success") else None

        if query_type == "price":
            prompt = (
                f"用一句台灣白話說明股票狀況，不超過40字，可加emoji：\n"
                f"{name}({code}) 現價{price}元，漲跌{change}元({change_pct}%)，"
                f"今日{low}～{high}"
            )
        else:
            prompt = (
                f"用兩句台灣白話分析股票貴不貴，不超過60字，最後加「投資有風險」：\n"
                f"{name}({code}) 現價{price}元，漲跌{change}元({change_pct}%)，"
                f"近30天均價{avg_30d if avg_30d else '無資料'}元"
            )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是幫台灣長輩看股票的助手，說話簡短親切。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.7,
        )
        ai_text = response.choices[0].message.content.strip()

        # 組合固定資訊 + AI 說明
        code_clean = _clean_code(stock_info.get("code", ""))
        price_str = f"{price:.2f}" if isinstance(price, float) else str(price)
        change_str = _format_change_arrow(stock_info.get("change"))
        pct_str = _format_change_pct(stock_info.get("change_percent"))

        header = f"📈 {name}（{code_clean}）\n股價：{price_str} 元  {change_str} {pct_str}\n"
        return header + ai_text

    except Exception:
        if query_type == "buy_analysis" and history and history.get("success"):
            return _format_with_history(stock_info, history)
        return format_simple_response(stock_info, query_type)
