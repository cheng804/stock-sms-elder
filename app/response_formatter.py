"""
response_formatter.py - 回覆格式化模組

將股票資料依據規則引擎轉換成長輩友善的白話文簡訊。
不依賴任何外部 AI 服務，純本地邏輯。
"""

from typing import Optional


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
    return "持平"


def _format_change_pct(pct: Optional[float]) -> str:
    if pct is None or pct == 0:
        return ""
    sign = "+" if pct > 0 else ""
    return f"({sign}{pct:.2f}%)"


def format_simple_response(stock_info: dict, query_type: str, history: Optional[dict] = None) -> str:
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
        is_prev = stock_info.get("is_prev_close", False)
        prefix = "昨收" if is_prev else "股價"
        lines = [
            f"📈 {name}",
            f"代號：{code}",
            f"{prefix}：{price_str} 元",
        ]
        # 漲跌資訊（無論是否昨日收盤都顯示）
        if change is not None and change_pct is not None:
            lines.append(f"漲跌：{change_str} {pct_str}")
        
        # 今日/昨日區間
        high = stock_info.get("high")
        low = stock_info.get("low")
        if high and low:
            range_label = "昨日區間" if is_prev else "今日區間"
            lines.append(f"{range_label}：{low:.2f}～{high:.2f}")

        # 均價分析（直接放在查價結果裡）
        avg_30d = history.get("avg_price") if history and history.get("success") else None
        if avg_30d and price:
            lines.append(f"近30天均價：{avg_30d:.2f} 元")
            diff_pct = (price - avg_30d) / avg_30d * 100
            if diff_pct < -5:
                lines.append("💡 現在比均價便宜，可考慮！")
            elif diff_pct > 5:
                lines.append("⚠️ 現在比均價貴，注意風險。")
            else:
                lines.append("目前股價在合理範圍。")

        # 爆量偵測
        avg_vol = history.get("avg_volume") if history and history.get("success") else None
        today_vol = history.get("today_volume") if history and history.get("success") else None
        if avg_vol and today_vol and avg_vol > 0:
            vol_ratio = today_vol / avg_vol
            if vol_ratio >= 2.0:
                lines.append(f"🔥 今日爆量！成交量是近期均量的 {vol_ratio:.1f} 倍，有大戶在動，請多留意！")

        if is_prev:
            lines.append("（尚未開盤，以上為昨日收盤價）")
        elif change and change > 0:
            lines.append("今天有漲喔！")
        elif change and change < 0:
            lines.append("今天有跌，別擔心！")
        else:
            lines.append("今天持平。")

        # 非交易時間提示
        from datetime import datetime, timezone, timedelta
        tw_now = datetime.now(timezone(timedelta(hours=8)))
        hour = tw_now.hour
        weekday = tw_now.weekday()
        if not is_prev and (weekday >= 5 or not (9 <= hour < 14)):
            lines.append("（目前非交易時段，以上為最近收盤價）")

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


def _format_with_history(stock_info: dict, history: dict, rsi_data: Optional[dict] = None) -> str:
    """結合歷史資料的買賣分析（不使用 AI），加入 RSI 解讀。"""
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

    # RSI 解讀
    if rsi_data and rsi_data.get("success"):
        signal = rsi_data.get("signal", "")
        rsi_val = rsi_data.get("rsi")
        signal_emoji = {
            "超賣": "🟢", "偏弱": "🔵", "中性": "⚪",
            "偏強": "🟡", "超買": "🔴"
        }.get(signal, "")
        if rsi_val is not None:
            lines.append(f"{signal_emoji} RSI {rsi_val}（{signal}）")
            lines.append(rsi_data.get("description", ""))

    lines.append("投資有風險，請謹慎！")
    return "\n".join(lines)


def generate_elder_friendly_analysis(
    stock_info: dict,
    history: Optional[dict],
    query_type: str,
    rsi_data: Optional[dict] = None,
) -> str:
    """
    格式化股票資訊，直接用固定格式輸出。
    buy_analysis 時帶入 rsi_data 可顯示 RSI 解讀。
    """
    if query_type == "buy_analysis" and history and history.get("success"):
        return _format_with_history(stock_info, history, rsi_data)
    return format_simple_response(stock_info, query_type, history)
