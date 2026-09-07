"""
twilio_client.py → textbee_client.py（保留原檔名以減少其他檔案改動）

使用 textbee 作為 SMS Gateway：
  - 接收簡訊：textbee 將收到的簡訊 POST 到你的 Webhook（JSON 格式）
  - 發送簡訊：呼叫 textbee REST API 發送回覆

textbee API:
  POST https://api.textbee.dev/api/v1/gateway/send-sms
  Header: x-api-key: YOUR_API_KEY
  Body:   {"recipients": ["+886912345678"], "message": "文字"}

Webhook payload (textbee POST 過來):
  {
    "smsId": "...",
    "message": "2330",
    "sender": "+886912345678",
    "receivedAt": "2026-01-01T00:00:00.000Z",
    "webhookEvent": "MESSAGE_RECEIVED",
    "idempotencyKey": "...",
    "deviceId": "..."
  }
"""

import hashlib
import hmac
import json
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY", "")
TEXTBEE_WEBHOOK_SECRET = os.getenv("TEXTBEE_WEBHOOK_SECRET", "")
TEXTBEE_API_URL = "https://api.textbee.dev/api/v1/gateway/send-sms"


# ─────────────────────────────────────────
#  發送簡訊
# ─────────────────────────────────────────

def send_sms(to_phone: str, message: str) -> bool:
    """
    透過 textbee API 發送簡訊。

    Args:
        to_phone: 收件人手機號碼（需含國碼，如 +886912345678）
        message:  簡訊內容

    Returns:
        True 表示發送成功，False 表示失敗
    """
    if not TEXTBEE_API_KEY:
        logger.warning("TEXTBEE_API_KEY 未設定，跳過發送簡訊")
        return False

    try:
        response = requests.post(
            TEXTBEE_API_URL,
            headers={
                "x-api-key": TEXTBEE_API_KEY,
                "Content-Type": "application/json",
            },
            json={"recipients": [to_phone], "message": message},
            timeout=15,
        )
        response.raise_for_status()
        logger.info(f"簡訊發送成功 to={to_phone}")
        return True
    except requests.RequestException as e:
        logger.error(f"簡訊發送失敗 to={to_phone}：{e}")
        return False


# ─────────────────────────────────────────
#  解析 Webhook
# ─────────────────────────────────────────

def parse_incoming_webhook(body: dict) -> dict:
    """
    解析 textbee Webhook POST 的 JSON body。

    Args:
        body: FastAPI 解析後的 JSON dict

    Returns:
        {"from_phone": str, "message": str}
    """
    return {
        "from_phone": body.get("sender", ""),
        "message": body.get("message", "").strip(),
    }


def verify_webhook_signature(payload: dict, signature: str) -> bool:
    """
    驗證 textbee Webhook 的 HMAC-SHA256 簽章。

    若 TEXTBEE_WEBHOOK_SECRET 未設定，跳過驗證（方便開發測試）。

    Args:
        payload:   Webhook JSON body（dict）
        signature: 請求 Header X-Signature 的值

    Returns:
        True 表示簽章合法或未設定 secret（開發模式）
    """
    if not TEXTBEE_WEBHOOK_SECRET:
        logger.warning("TEXTBEE_WEBHOOK_SECRET 未設定，跳過簽章驗證（僅限開發）")
        return True

    expected = hmac.new(
        TEXTBEE_WEBHOOK_SECRET.encode(),
        json.dumps(payload, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature or "", expected)


# ─────────────────────────────────────────
#  相容舊介面：build_twiml_response
#  textbee 不需要 TwiML，直接回 200 即可
#  保留此函數避免 main.py 改動
# ─────────────────────────────────────────

def build_twiml_response(message: str) -> str:
    """
    textbee 不使用 TwiML，此函數僅為相容介面保留。
    實際回覆透過 send_sms() 主動發送。

    Args:
        message: 回覆內容（這裡不使用）

    Returns:
        空字串
    """
    return ""
