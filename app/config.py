"""
config.py - 專題設定檔

========================================
教育用途聲明 / Educational Use Declaration
========================================
本專題為學校專題/畢業製作，使用 FinMind 教育授權
資料僅供參考，不構成投資建議
========================================
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 資料源選擇
# 'finmind' - 使用 FinMind（教育用途，推薦）
# 'yfinance' - 使用 yfinance（備用）
DATA_SOURCE = os.getenv("DATA_SOURCE", "finmind")

# FinMind Token（從 https://finmindtrade.com 取得）
# 填入後：API 額度 300→600/hr，解鎖即時報價
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")

# 教育用途標記
IS_EDUCATIONAL_PROJECT = True
PROJECT_NAME = "股票 SMS 長輩服務"
PROJECT_INSTITUTION = "學校專題/畢業製作"

# 資料授權資訊
DATA_LICENSE_INFO = {
    "source": "FinMind",
    "url": "https://finmind.github.io/",
    "license": "教育用途",
    "disclaimer": "資料僅供參考，不構成投資建議"
}

# textbee 設定
TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY", "")
TEXTBEE_WEBHOOK_SECRET = os.getenv("TEXTBEE_WEBHOOK_SECRET", "")

# OpenAI 設定（選填）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# 資料庫設定
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stock_sms.db")

# 啟動時顯示聲明
def print_startup_disclaimer():
    """啟動時顯示教育用途聲明"""
    print("\n" + "=" * 70)
    print(f"🎓 {PROJECT_NAME}")
    print(f"   {PROJECT_INSTITUTION}")
    print("=" * 70)
    print(f"\n📊 資料來源：{DATA_LICENSE_INFO['source']}")
    print(f"   授權類型：{DATA_LICENSE_INFO['license']}")
    print(f"   資料網址：{DATA_LICENSE_INFO['url']}")
    print(f"\n⚠️  免責聲明：{DATA_LICENSE_INFO['disclaimer']}")
    print(f"   使用者依本資料交易發生交易損失需自行負責")
    print(f"   本服務僅供學術研究與教育展示用途\n")
    print("=" * 70)
    print(f"🔧 目前資料源：{DATA_SOURCE.upper()}")
    print("=" * 70 + "\n")
