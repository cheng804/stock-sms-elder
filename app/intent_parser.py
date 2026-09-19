"""
intent_parser.py - 模糊語意解析模組

允許長輩輸入自然語言（如「幫我看護國神山今天狀況」、「買哪隻比較安全」），
解析成結構化意圖後交給主流程處理。

解析流程：
    1. 先用別名對應表（本地，免費）比對股票名稱與常用暱稱
    2. 若本地比對有結果，直接回傳
    3. 若本地比對無結果且有 OPENAI_API_KEY，呼叫 GPT 解析
    4. GPT 也無結果，回傳 unknown

對外只有一個主函數：
    parse_intent(message) -> dict
        {
            "type":       str,            # price / buy_analysis / subscribe / help / unknown / safe_pick
            "stock_code": str | None,     # 解析出的股票代號
            "message":    str | None,     # 若是 safe_pick 或 unknown，GPT 的建議文字
            "source":     str,            # "alias" | "gpt" | "fallback"
        }
"""

import os
import re
import logging
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ─────────────────────────────────────────
#  別名對應表
#  key: 使用者可能輸入的文字（小寫）
#  value: 股票代號
# ─────────────────────────────────────────

_ALIAS_MAP: dict[str, str] = {
    # 台積電
    "台積電": "2330", "台積": "2330", "tsmc": "2330",
    "護國神山": "2330", "護國": "2330", "神山": "2330",
    "台積電股票": "2330", "2330": "2330",
    "gg": "2330", "GG": "2330",
    # 常見錯字
    "台基電": "2330", "台機電": "2330", "台績電": "2330",
    
    # 鴻海
    "鴻海": "2317", "foxconn": "2317", "郭台銘": "2317",
    "鴻海精密": "2317", "海爸": "2317",
    # 常見錯字
    "洪海": "2317", "紅海": "2317",
    
    # 聯發科
    "聯發科": "2454", "mediatek": "2454", "發哥": "2454",
    "聯發": "2454", "mtk": "2454",
    # 常見錯字
    "連發科": "2454", "聯發課": "2454",
    
    # 金融股
    "富邦金": "2881", "國泰金": "2882", "兆豐金": "2886",
    "中信金": "2891", "玉山金": "2884", "元大金": "2885",
    "第一金": "2892", "合庫金": "5880", "台新金": "2887",
    "開發金": "2883", "永豐金": "2890", "日盛金": "5820",
    # 常見錯字
    "國太金": "2882", "富幫金": "2881", "富棒金": "2881",
    
    # 電信
    "中華電": "2412", "中華電信": "2412", "中華": "2412",
    "台灣大": "3045", "台灣大哥大": "3045",
    "遠傳": "4904", "遠傳電信": "4904",
    
    # 航運三雄
    "長榮": "2603", "長榮海運": "2603", "長榮海": "2603",
    "陽明": "2609", "陽明海運": "2609", "陽明海": "2609",
    "萬海": "2615", "萬海航運": "2615",
    
    # 半導體
    "聯電": "2303", "umc": "2303", "聯華電子": "2303",
    "日月光": "3711", "日月光投控": "3711",
    "大立光": "3008",
    "緯穎": "6669", "緯穎科技": "6669",
    "矽力": "6415", "矽力*ky": "6415", "矽力ky": "6415",
    "世芯": "3661", "世芯*ky": "3661", "世芯ky": "3661",
    "力積電": "6770", "力積": "6770",
    "南亞科": "2408", "南亞科技": "2408",
    "華邦電": "2344", "華邦": "2344",
    "群聯": "8299", "群聯電子": "8299",
    "瑞昱": "2379", "realtek": "2379",
    "祥碩": "5269",
    "創意": "3443", "創意電子": "3443",
    "智原": "3035", "智原科技": "3035",
    
    # 科技股
    "廣達": "2382", "廣達電腦": "2382",
    "台達電": "2308", "台達": "2308",
    "華碩": "2357", "asus": "2357", "華碩電腦": "2357",
    "宏碁": "2353", "acer": "2353",
    "研華": "2395", "研華科技": "2395",
    "緯創": "3231", "緯創資通": "3231",
    "仁寶": "2324", "仁寶電腦": "2324",
    "光寶科": "2301", "光寶": "2301",
    "和碩": "4938", "和碩聯合": "4938",
    "英業達": "2356",
    "微星": "2377", "msi": "2377",
    "技嘉": "2376", "gigabyte": "2376",
    
    # 面板雙虎
    "友達": "2409", "友達光電": "2409", "auo": "2409",
    "群創": "3481", "群創光電": "3481",
    
    # 塑化
    "台塑": "1301", "南亞": "1303", "台化": "1326",
    "台塑化": "6505",
    
    # 鋼鐵
    "中鋼": "2002", "中國鋼鐵": "2002",
    "中鴻": "2014",
    
    # 食品
    "統一": "1216", "統一企業": "1216",
    "味全": "1201",
    "大統益": "1232",
    
    # 傳產
    "台泥": "1101", "台灣水泥": "1101",
    "亞泥": "1102", "亞洲水泥": "1102",
    "遠東新": "1402",
    "正新": "2105", "正新輪胎": "2105",
    
    # 汽車
    "裕隆": "2201", "裕隆汽車": "2201",
    "和泰車": "2207", "和泰汽車": "2207",
    
    # 生技
    "台康": "6589", "台康生技": "6589",
    "合一": "4743", "合一生技": "4743",
    "浩鼎": "4174", "浩鼎生技": "4174",
    
    # ETF
    "台灣50": "0050", "元大台灣50": "0050", "0050": "0050", "五十": "0050",
    "高股息": "0056", "元大高股息": "0056", "0056": "0056", "五六": "0056",
    "國泰高股息": "00878", "00878": "00878",
    "富邦台50": "006208", "006208": "006208",
    "元大電子": "0053", "0053": "0053",
    "富邦金融": "0055", "0055": "0055",
    "元大msci台灣": "006203", "006203": "006203",
    
    # 美股（常見）
    "蘋果": "AAPL", "apple": "AAPL", "蘋果電腦": "AAPL",
    "微軟": "MSFT", "microsoft": "MSFT",
    "谷歌": "GOOGL", "google": "GOOGL", "alphabet": "GOOGL", "字母": "GOOGL",
    "特斯拉": "TSLA", "tesla": "TSLA", "電動車王": "TSLA",
    "輝達": "NVDA", "nvidia": "NVDA", "nvdia": "NVDA", "顯卡王": "NVDA",
    "亞馬遜": "AMZN", "amazon": "AMZN",
    "meta": "META", "臉書": "META", "facebook": "META", "fb": "META",
    "台積電adr": "TSM", "tsm": "TSM",
}

# 意圖關鍵字
_BUY_INTENT   = ["買", "買進", "買入", "值不值", "要不要買", "可以買", "划算", "合理"]
_PRICE_INTENT = ["看", "查", "狀況", "怎樣", "如何", "現在", "今天", "多少", "幾點"]
_SAFE_INTENT  = ["安全", "穩定", "保守", "推薦", "哪隻好", "買哪", "哪支", "建議"]
_HELP_INTENT  = ["說明", "怎麼用", "操作", "指令", "幫助", "help"]


def _match_alias(text: str) -> Optional[str]:
    """
    從文字中比對別名對應表，回傳股票代號。
    先做完整詞比對，再做包含比對。
    """
    text_lower = text.lower()
    # 完整詞比對（較長的別名優先）
    for alias, code in sorted(_ALIAS_MAP.items(), key=lambda x: -len(x[0])):
        if alias.lower() in text_lower:
            return code
    return None


def _detect_intent_local(text: str, stock_code: Optional[str]) -> str:
    """
    本地規則判斷意圖類型。
    """
    if any(kw in text for kw in _HELP_INTENT):
        return "help"
    if any(kw in text for kw in _SAFE_INTENT) and not stock_code:
        return "safe_pick"
    if any(kw in text for kw in _BUY_INTENT) and stock_code:
        return "buy_analysis"
    if stock_code:
        return "price"
    return "unknown"


def _ask_gpt(message: str) -> dict:
    """
    呼叫 OpenAI GPT 解析意圖。
    回傳 {type, stock_code, message} 或 fallback dict。
    """
    if not OPENAI_API_KEY:
        return {"type": "unknown", "stock_code": None, "message": None, "source": "fallback"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        system_prompt = (
            "你是一個台灣股票查詢助理，專門服務不熟悉科技的長輩。\n"
            "使用者會用自然語言或有錯字的訊息，你需要分析意圖並回傳 JSON。\n\n"
            "回傳格式（只回 JSON，不要其他文字）：\n"
            "{\n"
            '  "type": "price" | "buy_analysis" | "safe_pick" | "help" | "unknown",\n'
            '  "stock_code": "股票代號或null",\n'
            '  "reply": "若 type 是 safe_pick 或 unknown，用繁體中文給一句簡短友善回覆（40字內）"\n'
            "}\n\n"
            "type 說明：\n"
            "- price: 查詢某支股票的股價或狀況\n"
            "- buy_analysis: 詢問某支股票能不能買\n"
            "- safe_pick: 問哪支股票比較安全、推薦哪支（不指定股票）\n"
            "- help: 詢問怎麼使用服務\n"
            "- unknown: 完全無關股票的問題\n\n"
            "股票代號規則：\n"
            "- 台股用數字代號（如 2330）\n"
            "- 美股用英文代號（如 AAPL）\n"
            "- 若訊息中有公司名稱，轉換成代號\n"
            "- 若找不到或不確定，stock_code 填 null\n\n"
            "【重要】錯字處理：\n"
            "- 長輩可能有同音錯字或注音輸入錯誤\n"
            "- 「台基電」→ 台積電 2330\n"
            "- 「洪海」→ 鴻海 2317\n"
            "- 「連發科」→ 聯發科 2454\n"
            "- 「國太金」→ 國泰金 2882\n"
            "- 用語意推斷正確的公司名稱，不要生搬硬套\n\n"
            "常見台股代號參考：\n"
            "台積電(2330)、鴻海(2317)、聯發科(2454)、\n"
            "國泰金(2882)、富邦金(2881)、中華電(2412)、\n"
            "台達電(2308)、聯電(2303)、日月光(3711)、\n"
            "長榮(2603)、陽明(2609)、0050、0056"
        )

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0,
            max_tokens=150,
        )

        import json
        raw = resp.choices[0].message.content.strip()
        # 移除可能的 markdown code block
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)

        return {
            "type":       data.get("type", "unknown"),
            "stock_code": data.get("stock_code") or None,
            "message":    data.get("reply") or None,
            "source":     "gpt",
        }

    except Exception as e:
        logger.warning(f"[IntentParser] GPT 解析失敗：{e}")
        return {"type": "unknown", "stock_code": None, "message": None, "source": "fallback"}


# ─────────────────────────────────────────
#  主函數
# ─────────────────────────────────────────

def parse_intent(message: str) -> dict:
    """
    解析使用者自然語言訊息的意圖。

    Args:
        message: 使用者傳來的原始訊息

    Returns:
        {
            "type":       str,        # price/buy_analysis/safe_pick/help/unknown
            "stock_code": str | None, # 股票代號
            "message":    str | None, # safe_pick/unknown 時的回覆文字
            "source":     str,        # alias / gpt / fallback
        }
    """
    text = message.strip()

    # 1. 本地別名比對
    stock_code = _match_alias(text)
    intent_type = _detect_intent_local(text, stock_code)

    if stock_code or intent_type in ("help", "safe_pick"):
        # 本地就能處理
        result = {
            "type":       intent_type,
            "stock_code": stock_code,
            "message":    None,
            "source":     "alias",
        }
        # safe_pick 給一個固定回覆（沒有 GPT 的情況）
        if intent_type == "safe_pick" and not OPENAI_API_KEY:
            result["message"] = (
                "穩健型可考慮：0050（台灣50）或 0056（高股息）ETF，\n"
                "分散風險、長期持有，適合穩健投資。\n"
                "傳代號查看最新股價，例如：0050"
            )
        return result

    # 2. 有 OpenAI Key 才呼叫 GPT
    if OPENAI_API_KEY:
        return _ask_gpt(text)

    # 3. 完全 fallback
    return {"type": "unknown", "stock_code": None, "message": None, "source": "fallback"}
