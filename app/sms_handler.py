"""
sms_handler.py - 簡訊指令解析模組

負責把使用者傳來的短訊文字解析成結構化指令，
並提供說明訊息。
"""

import re
from typing import Optional


# 股票代號的正規表達式：4~6 位數字，或英文字母（美股）
_STOCK_CODE_PATTERN = re.compile(r"\b([A-Za-z]{1,5}|\d{4,6})\b")

# 時間格式 HH:MM
_TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2})\b")


def _extract_stock_code(text: str) -> Optional[str]:
    """
    從文字中擷取第一個股票代號。
    支援：純數字台股（2330）、數字+英文ETF（00991A）、純英文美股（AAPL）
    """
    # 優先找數字開頭（台股/ETF），包含後綴英文字母如 00991A
    match = re.search(r"(?<!\d)(\d{4,6}[A-Za-z]?)(?!\d)", text)
    if match:
        return match.group(1).upper()
    # 再找純英文（美股），但排除太短的（1-2字元交給 intent_parser 處理）
    match = re.search(r"(?<![A-Za-z])([A-Z]{3,5})(?![A-Za-z])", text.upper())
    if match:
        candidate = match.group(1)
        if candidate not in {"HELP", "SUB", "UNSUB", "BUY", "START", "STOP"}:
            return candidate
    return None


def _extract_time(text: str) -> Optional[str]:
    """
    從文字中擷取時間字串（HH:MM）。

    Args:
        text: 輸入文字

    Returns:
        時間字串（如 "08:30"），或 None
    """
    match = _TIME_PATTERN.search(text)
    if match:
        time_str = match.group(1)
        # 補零：8:30 -> 08:30
        parts = time_str.split(":")
        return f"{int(parts[0]):02d}:{parts[1]}"
    return None


def parse_command(message: str) -> dict:
    """
    解析使用者傳來的簡訊，轉成結構化指令。

    支援指令格式：
        "2330"                      -> price
        "2330 買" / "2330買"         -> buy_analysis
        "訂閱 2330" / "訂閱2330"     -> subscribe（預設 08:30）
        "訂閱 2330 09:00"            -> subscribe 指定時間
        "取消 2330" / "退訂 2330"    -> unsubscribe
        "警報 2330 750"              -> set_alert（跌破 750 通知）
        "警報 2330 800 突破"          -> set_alert（突破 800 通知）
        "取消警報 2330"              -> remove_alert
        "說明" / "help" / "HELP"     -> help
        其他                         -> unknown

    Args:
        message: 使用者傳來的簡訊原文

    Returns:
        dict:
            - type (str): "price" | "buy_analysis" | "subscribe" |
                          "unsubscribe" | "set_alert" | "remove_alert" |
                          "help" | "unknown"
            - stock_code (str | None): 股票代號（純數字或英文）
            - time (str | None): 訂閱時間（HH:MM），僅 subscribe 指令有值
            - raw (str): 原始訊息
    """
    msg = message.strip()
    msg_upper = msg.upper()
    msg_no_space = msg.replace(" ", "").replace("　", "")  # 移除全形空白

    # ── 說明 ──────────────────────────────
    if msg_upper in {"說明", "HELP", "？", "?", "菜單", "指令"}:
        return {"type": "help", "stock_code": None, "time": None, "raw": msg}
    
    # ── 我的訂閱 ──────────────────────────
    my_sub_keywords = ["我的訂閱", "訂閱清單", "訂閱列表", "查看訂閱", "有訂閱什麼"]
    if any(kw in msg for kw in my_sub_keywords):
        return {"type": "list_subscriptions", "stock_code": None, "time": None, "raw": msg}
    
    # ── 我的警報 ──────────────────────────
    my_alert_keywords = ["我的警報", "警報清單", "警報列表", "查看警報", "有什麼警報"]
    if any(kw in msg for kw in my_alert_keywords):
        return {"type": "list_alerts", "stock_code": None, "time": None, "raw": msg}

    # ── 開始/啟動 ─────────────────────────
    if msg_upper in {"開始", "START", "你好", "HI", "HELLO", "啟動", "開啟"}:
        return {"type": "start", "stock_code": None, "time": None, "raw": msg}

    # ── 停止 ─────────────────────────────
    if msg_upper in {"停止", "STOP", "關閉", "暫停"}:
        return {"type": "stop", "stock_code": None, "time": None, "raw": msg}

    # ── 訂閱 ──────────────────────────────
    subscribe_keywords = ["訂閱", "訂购", "subscribe"]
    for kw in subscribe_keywords:
        if kw in msg.lower() or kw in msg_no_space.lower():
            stock_code = _extract_stock_code(msg)
            notify_time = _extract_time(msg) or "08:30"
            return {
                "type": "subscribe",
                "stock_code": stock_code,
                "time": notify_time,
                "raw": msg,
            }

    # ── 退訂 ──────────────────────────────
    unsubscribe_keywords = ["退訂", "退订", "unsubscribe"]
    for kw in unsubscribe_keywords:
        if kw in msg.lower() or kw in msg_no_space.lower():
            stock_code = _extract_stock_code(msg)
            return {
                "type": "unsubscribe",
                "stock_code": stock_code,
                "time": None,
                "raw": msg,
            }
    # 「取消」單獨出現（不含「警報」）才視為退訂
    if "取消" in msg and not any(w in msg for w in ["警報", "提醒", "到價"]):
        stock_code = _extract_stock_code(msg)
        return {
            "type": "unsubscribe",
            "stock_code": stock_code,
            "time": None,
            "raw": msg,
        }

    # ── 取消警報 ──────────────────────────
    remove_alert_keywords = ["取消警報", "刪除警報", "移除警報"]
    for kw in remove_alert_keywords:
        if kw in msg or kw in msg_no_space:
            stock_code = _extract_stock_code(msg)
            return {
                "type": "remove_alert",
                "stock_code": stock_code,
                "time": None,
                "raw": msg,
            }

    # ── 設定警報 ──────────────────────────
    # 格式：警報 2330 750  或  警報 2330 800 突破
    alert_keywords = ["警報", "提醒", "到價"]
    for kw in alert_keywords:
        if kw in msg or kw in msg_no_space:
            stock_code = _extract_stock_code(msg)
            # 擷取目標價：在股票代號之後的第一個數字（排除代號本身）
            # 先移除關鍵字和股票代號，再找剩餘的數字
            remaining = msg
            remaining = re.sub(r"[警報提醒到價]", "", remaining)
            if stock_code:
                remaining = re.sub(re.escape(stock_code), "", remaining, count=1)
            price_match = re.search(r"(\d+(?:\.\d+)?)", remaining)
            target_price = float(price_match.group(1)) if price_match else None
            # 判斷方向：預設跌破，若有「突破」「漲到」「up」改為 above
            direction = "above" if any(w in msg for w in ["突破", "漲到", "up", "UP"]) else "below"
            return {
                "type": "set_alert",
                "stock_code": stock_code,
                "target_price": target_price,
                "direction": direction,
                "time": None,
                "raw": msg,
            }

    # ── 買賣分析 ─────────────────────────
    buy_keywords = ["買", "分析", "要不要", "值不值", "貴不貴", "buy"]
    has_buy_keyword = any(kw in msg or kw.lower() in msg.lower() for kw in buy_keywords)
    if has_buy_keyword:
        stock_code = _extract_stock_code(msg)
        if stock_code:
            return {
                "type": "buy_analysis",
                "stock_code": stock_code,
                "time": None,
                "raw": msg,
            }
    
    # ── 週報告（一週漲跌）────────────────────
    week_keywords = ["週報", "周報", "一週", "一周", "7天", "這週", "這周", "本週", "本周"]
    has_week_keyword = any(kw in msg for kw in week_keywords)
    if has_week_keyword:
        stock_code = _extract_stock_code(msg)
        if stock_code:
            return {
                "type": "week_report",
                "stock_code": stock_code,
                "time": None,
                "raw": msg,
            }

    # ── 單純查價：訊息幾乎只有股票代號 ───
    # 移除空白和標點後，若只剩股票代號則視為查價
    # 但英文代號必須 3 字元以上（1-2 字元交給 intent_parser）
    clean = re.sub(r"[\s\.,，。！!？?]+", "", msg)
    if re.match(r"^(\d{4,6}|[A-Za-z]{3,5})$", clean):
        return {
            "type": "price",
            "stock_code": clean.upper() if clean.isalpha() else clean,
            "time": None,
            "raw": msg,
        }

    # 訊息中有股票代號但不符合其他模式，視為查價
    stock_code = _extract_stock_code(msg)
    if stock_code:
        return {"type": "price", "stock_code": stock_code, "time": None, "raw": msg}

    # ── 無法識別 ─────────────────────────
    return {"type": "unknown", "stock_code": None, "time": None, "raw": msg}


def get_help_message() -> str:
    """
    回傳操作說明的簡訊文字。

    Returns:
        說明字串（盡量控制在 SMS 限制內）
    """
    return (
        "📱 股票查詢服務 操作說明\n"
        "\n"
        "【查股價】\n"
        "  直接傳股票代號\n"
        "  例：2330\n"
        "\n"
        "【買賣分析（含RSI）】\n"
        "  代號 買\n"
        "  例：2330買\n"
        "\n"
        "【一週漲跌】\n"
        "  代號 週報 或 一週\n"
        "  例：2330週報\n"
        "\n"
        "【訂閱每日通知】\n"
        "  訂閱 代號 時間\n"
        "  例：訂閱 2330 08:30\n"
        "\n"
        "【取消訂閱】\n"
        "  取消 代號\n"
        "  例：取消 2330\n"
        "\n"
        "【設定到價警報】\n"
        "  警報 代號 目標價\n"
        "  例：警報 2330 750\n"
        "  加「突破」改為向上警報\n"
        "  例：警報 2330 800 突破\n"
        "\n"
        "【取消警報】\n"
        "  取消警報 代號\n"
        "  例：取消警報 2330\n"
        "\n"
        "💡 支援公司名稱，例如：\n"
        "台積電、鴻海、GG 都可以！"
    )
