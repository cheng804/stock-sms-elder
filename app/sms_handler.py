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

    Args:
        text: 輸入文字

    Returns:
        股票代號字串，或 None
    """
    # 先找數字型（台股）
    match = re.search(r"\b(\d{4,6})\b", text)
    if match:
        return match.group(1)
    # 再找英文型（美股，排除常見中文拼音）
    match = re.search(r"\b([A-Z]{1,5})\b", text.upper())
    if match:
        candidate = match.group(1)
        # 排除指令關鍵字本身
        if candidate not in {"HELP", "SUB", "UNSUB"}:
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
        "說明" / "help" / "HELP"     -> help
        其他                         -> unknown

    Args:
        message: 使用者傳來的簡訊原文

    Returns:
        dict:
            - type (str): "price" | "buy_analysis" | "subscribe" |
                          "unsubscribe" | "help" | "unknown"
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
    unsubscribe_keywords = ["取消", "退訂", "退订", "unsubscribe", "停止"]
    for kw in unsubscribe_keywords:
        if kw in msg.lower() or kw in msg_no_space.lower():
            stock_code = _extract_stock_code(msg)
            return {
                "type": "unsubscribe",
                "stock_code": stock_code,
                "time": None,
                "raw": msg,
            }

    # ── 買賣分析 ─────────────────────────
    buy_keywords = ["買", "分析", "要不要", "值不值", "貴不貴", "buy"]
    for kw in buy_keywords:
        if kw in msg.lower() or kw in msg_no_space.lower():
            stock_code = _extract_stock_code(msg)
            if stock_code:
                return {
                    "type": "buy_analysis",
                    "stock_code": stock_code,
                    "time": None,
                    "raw": msg,
                }

    # ── 單純查價：訊息幾乎只有股票代號 ───
    # 允許代號後面有少量空白或標點
    clean = re.sub(r"[\s\.,，。！!？?]+", "", msg)
    if re.match(r"^(\d{4,6}|[A-Za-z]{1,5})$", clean):
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
        "【買賣分析】\n"
        "  代號後加「買」\n"
        "  例：2330買\n"
        "\n"
        "【訂閱每日通知】\n"
        "  訂閱 代號 時間\n"
        "  例：訂閱 2330 08:30\n"
        "\n"
        "【取消訂閱】\n"
        "  取消 代號\n"
        "  例：取消 2330\n"
        "\n"
        "再傳「說明」可再看這則訊息。"
    )
