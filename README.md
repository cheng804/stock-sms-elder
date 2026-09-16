# 📱 stock-sms-elder — 老人機傳簡訊查股票

讓長輩不需要智慧型手機或 App，  
用最普通的老人機傳一則簡訊，就能即時查到股票資訊。

---

## 🎯 專題簡介

台灣有很多長輩手邊只有老人機，  
卻對股票投資很有興趣。  
這個專題讓長輩只要傳 `2330` 這樣一則簡訊，  
系統就會自動回傳台積電的即時股價、漲跌幅，  
還能用簡單易懂的文字解釋「今天是貴還是便宜」。

---

## 🗺️ 系統架構

```
長輩老人機
    │
    │  SMS（傳 "2330"）
    ▼
 Twilio
 電話號碼
    │
    │  Webhook POST /webhook/sms
    ▼
┌─────────────────────────────────────┐
│          FastAPI Server             │
│  ┌────────────┐  ┌───────────────┐  │
│  │ sms_handler│  │ stock_fetcher │  │
│  │ 解析指令   │  │ yfinance 抓價 │  │
│  └────────────┘  └───────────────┘  │
│  ┌────────────┐  ┌───────────────┐  │
│  │response_ │  │   database    │  │
│  │formatter │  │ SQLite 記錄   │  │
│  └────────────┘  └───────────────┘  │
│  ┌────────────┐                     │
│  │ scheduler  │  APScheduler 排程   │
│  └────────────┘                     │
└─────────────────────────────────────┘
    │
    │  TwiML XML Response
    ▼
 Twilio
    │
    │  SMS 回覆
    ▼
長輩老人機
（收到股票資訊）

另外開一個 Streamlit Dashboard 供管理：
┌─────────────────────────────────────┐
│      Streamlit Dashboard            │
│  KPI 卡片 / 圖表 / 查詢紀錄         │
│  直接連 SQLite 或呼叫 FastAPI        │
└─────────────────────────────────────┘
```

---

## ✨ 功能列表

| 功能 | 說明 |
|------|------|
| 📈 即時查價 | 傳股票代號，回傳即時股價、漲跌、今日高低 |
| 📊 買賣分析 | 結合近 30 天均價，規則引擎判斷貴不貴 |
| 🔔 訂閱通知 | 每天指定時間自動發送股票資訊 |
| ❌ 退訂 | 隨時可以取消訂閱 |
| 🧠 個人化建議 | 依據查詢歷史提供訂閱提醒、關注股比較、頻率警示 |
| 🗄️ 查詢記錄 | SQLite 記錄所有查詢供後台檢視 |
| 📊 管理後台 | Streamlit Dashboard 即時統計圖表 |

---

## 🛠️ 環境需求

- Python 3.10 以上
- Twilio 帳號（需信用卡驗證，有免費試用）
- 可公開存取的 HTTPS 網址（供 Webhook 用）
  - 開發時可用 [ngrok](https://ngrok.com) 暫時使用

---

## 🚀 安裝步驟

### 1. 下載專案

```bash
git clone https://github.com/yourname/stock-sms-elder.git
cd stock-sms-elder
```

### 2. 建立虛擬環境

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. 安裝套件

```bash
pip install -r requirements.txt
```

### 4. 設定環境變數

```bash
cp .env.example .env
```

用文字編輯器開啟 `.env`，填入以下設定：

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
```

---

## ⚙️ 設定說明

### Twilio 設定

1. 前往 [https://console.twilio.com](https://console.twilio.com) 註冊帳號
2. 在「Phone Numbers」購買一個支援 SMS 的號碼
3. 複製 Account SID、Auth Token、Phone Number 填入 `.env`

### OpenAI 設定（不需要）

本系統使用規則引擎產生回覆，不依賴外部 AI 服務，無需設定 OpenAI API Key。

---

### 資料庫設定

#### 本機開發（預設）

預設使用 SQLite，不需額外設定，啟動後自動產生 `stock_sms.db`。

#### 正式部署（Render）— 建議使用 PostgreSQL

Render 的免費方案檔案系統是暫時性的，每次 redeploy 都會重置，SQLite 資料會消失。
建議建立 Render 免費 PostgreSQL 資料庫來持久化所有查詢紀錄與訂閱。

**建立步驟：**

1. 登入 [Render Dashboard](https://dashboard.render.com)
2. 點擊「New +」→「PostgreSQL」
3. 填入名稱（如 `stock-sms-db`），Region 選 **Oregon (US West)**，Plan 選 **Free**
4. 點擊「Create Database」，等待約 1 分鐘
5. 建立完成後，進入資料庫頁面，找到 **「Internal Database URL」**（僅供同一 Render 帳號下的服務使用，速度較快）
6. 複製該 URL，格式類似：
   ```
   postgresql://stock_sms_user:xxxx@dpg-xxxx.oregon-postgres.render.com/stock_sms
   ```
7. 前往你的 **Web Service** → 「Environment」→ 新增環境變數：
   ```
   DATABASE_URL = （貼上上方複製的 Internal Database URL）
   ```
8. 重新 Deploy，系統啟動時會自動建立所有資料表。

> **注意：** Render 免費 PostgreSQL 會在 **90 天無活動後自動刪除**。  
> 只要服務有持續使用（收發簡訊），就不會觸發刪除。

---

## ▶️ 啟動方式

### 啟動 FastAPI 服務

```bash
# 方式一：直接執行
python -m app.main

# 方式二：用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

服務啟動後可前往 [http://localhost:8000/docs](http://localhost:8000/docs) 查看 API 文件。

### 啟動 Streamlit 管理後台

```bash
streamlit run dashboard/streamlit_app.py
```

後台預設開在 [http://localhost:8501](http://localhost:8501)

### 使用 ngrok 開放外部存取（開發用）

```bash
ngrok http 8000
```

ngrok 會提供一個類似 `https://abc123.ngrok.io` 的網址，  
複製後用於設定 Twilio Webhook。

---

## 📡 Twilio Webhook 設定

1. 登入 [Twilio Console](https://console.twilio.com)
2. 前往「Phone Numbers」→「Manage」→「Active Numbers」
3. 點擊你的號碼
4. 在「Messaging」區塊，找到「A MESSAGE COMES IN」
5. 選「Webhook」，填入：
   ```
   https://你的網址/webhook/sms
   ```
   方法選「HTTP POST」
6. 按「Save」

之後長輩傳簡訊到這個號碼，Twilio 就會自動呼叫你的 Webhook。

---

## 📲 支援的簡訊指令

| 傳送內容 | 功能 | 範例 |
|----------|------|------|
| `股票代號` | 查即時股價 | `2330` |
| `股票代號 買` | 買賣分析 | `2330買` 或 `2330 買` |
| `訂閱 股票代號` | 訂閱每日通知（預設 08:30）| `訂閱 2330` |
| `訂閱 股票代號 時間` | 訂閱指定時間通知 | `訂閱 2330 09:00` |
| `取消 股票代號` | 取消訂閱 | `取消 2330` |
| `退訂 股票代號` | 取消訂閱（同上）| `退訂 2330` |
| `說明` | 查看操作說明 | `說明` |
| `help` | 查看操作說明（英文）| `help` |

> **支援台股與美股：**  
> 台股輸入純數字（如 `2330`、`0050`），系統自動加 `.TW` 後綴。  
> 美股輸入英文代號（如 `AAPL`、`TSLA`）。

---

## 🔔 訂閱功能說明

訂閱後，系統會在你指定的時間（每天）自動發送該股票的最新行情。  
每位使用者可訂閱多支股票、設定不同時間。

- **建立訂閱：** `訂閱 2330 08:30`
- **取消訂閱：** `取消 2330`
- 訂閱資料儲存在 SQLite，重開服務後依然有效。
- 排程器（APScheduler）在 FastAPI 啟動時自動啟動，每分鐘檢查一次。

---

## 📁 專案結構

```
stock-sms-elder/
├── app/
│   ├── __init__.py          # Package 初始化
│   ├── main.py              # FastAPI 主程式 + Webhook 入口
│   ├── sms_handler.py       # 解析簡訊指令
│   ├── stock_fetcher.py     # 抓取股票資料 (yfinance)
│   ├── response_formatter.py # 規則引擎：格式化股票回覆文字
│   ├── twilio_client.py     # Twilio 發送/接收簡訊
│   ├── database.py          # SQLite 資料庫操作 (SQLAlchemy)
│   └── scheduler.py         # 訂閱排程 (APScheduler)
├── dashboard/
│   └── streamlit_app.py     # Streamlit 管理後台
├── .env.example             # 環境變數範例
├── requirements.txt         # Python 套件清單
└── README.md                # 本文件
```

---

## 🔍 常見問題

**Q: 收不到回覆簡訊？**  
A: 確認 Twilio Webhook URL 是否填對，且使用 HTTPS。用 `/health` 端點確認服務是否運作。

**Q: 股票代號查不到？**  
A: 台股輸入 4~5 位數字。部分冷門股 yfinance 可能沒資料，可先到 Yahoo Finance 查確認代號。

**Q: 回覆內容不夠生動？**  
A: 系統使用規則引擎產生固定格式回覆，可自行在 `response_formatter.py` 調整文字內容。

**Q: 排程通知沒有發送？**  
A: 確認 Twilio 設定正確，且 FastAPI 服務持續在運行中。

---

## 📄 授權

MIT License — 自由使用於個人或學術專題。
