# 📱 stock-sms-elder — 老人機傳簡訊查股票

讓長輩不需要智慧型手機或 App，  
用最普通的老人機傳一則簡訊，就能即時查到股票資訊。

---

## 📋 教育用途聲明 / Educational Use Declaration

**本專題為學校專題/畢業製作，僅供學術研究與教育展示用途**

```
資料來源：FinMind 開源金融資料 (https://finmind.github.io/)
使用依據：FinMind 教育用途授權
專題性質：學校專題/畢業製作
用途聲明：非商業、非營利、教育展示
使用期限：專題期間

依據臺灣證券交易所『交易資訊使用管理辦法』，使用者須遵守相關規定。
本服務所提供資訊僅供參考，不構成投資建議。
使用者依本資料交易發生交易損失需自行負責。

This project uses FinMind open-source financial data for academic 
research and educational purposes only. Data is for reference only 
and does not constitute investment advice.
```

**重要提醒：**
- ✅ 本專題使用 FinMind 免費教育授權
- ✅ 僅限於專題展示與學術用途
- ⚠️ 如未來計劃商業化營運，需申請正式行情資料授權
- ⚠️ 資料僅供參考，投資風險請自行評估

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
 textbee
 Android 手機
    │
    │  Webhook POST /webhook/sms
    ▼
┌─────────────────────────────────────┐
│          FastAPI Server             │
│  ┌────────────┐  ┌───────────────┐  │
│  │ sms_handler│  │ stock_fetcher │  │
│  │ 解析指令   │  │ FinMind 資料  │  │
│  └────────────┘  └───────────────┘  │
│  ┌────────────┐  ┌───────────────┐  │
│  │ response_  │  │   database    │  │
│  │ formatter  │  │ PostgreSQL    │  │
│  └────────────┘  └───────────────┘  │
│  ┌─────────────┐ ┌───────────────┐  │
│  │  scheduler  │ │intent_parser  │  │
│  │ APScheduler │ │ GPT 語意解析  │  │
│  └─────────────┘ └───────────────┘  │
└─────────────────────────────────────┘
    │
    │  textbee API 回傳 SMS
    ▼
長輩老人機
（收到股票資訊）
```

另外開一個 Streamlit Dashboard 供管理：
```
┌─────────────────────────────────────┐
│      Streamlit Dashboard            │
│  KPI 卡片 / 圖表 / 查詢紀錄         │
└─────────────────────────────────────┘
```

---

## ✨ 功能列表

| 功能 | 說明 |
|------|------|
| 📈 即時查價 | 傳股票代號，回傳即時股價、漲跌、今日高低 |
| 📊 買賣分析 | 結合近 30 天均價，規則引擎判斷貴不貴 |
| 📉 技術指標 | RSI、MACD 計算，出現黃金/死亡交叉主動預警 |
| 🔔 訂閱通知 | 每天指定時間自動發送股票資訊 |
| 🚨 到價警報 | 股價突破或跌破目標價時發送通知 |
| 🧠 個人化建議 | 依據查詢歷史提供訂閱提醒、頻率警示 |
| 💬 模糊語意 | 支援「護國神山」「GG」等暱稱，GPT 解析自然語言 |
| 🗄️ 查詢記錄 | PostgreSQL 記錄所有查詢供後台檢視 |
| 📊 管理後台 | Streamlit Dashboard 即時統計圖表 |

---

## 🛠️ 環境需求

- Python 3.10 以上
- Android 手機一支（用於 textbee 收發簡訊）
- [textbee](https://textbee.dev) 帳號（免費）
- 可公開存取的 HTTPS 網址（供 Webhook 用）
  - 本機開發可用 [ngrok](https://ngrok.com) 暫時使用
  - 正式部署建議使用 [Render](https://render.com)

---

## 🚀 安裝步驟

### 1. 下載專案

```bash
git clone https://github.com/cheng804/stock-sms-elder.git
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
TEXTBEE_API_KEY=your_api_key_here
TEXTBEE_WEBHOOK_SECRET=your_webhook_secret_here
OPENAI_API_KEY=sk-xxxxxxxx   # 選填
DATABASE_URL=sqlite:///./stock_sms.db
```

---

## ⚙️ 設定說明

### textbee 設定

1. 前往 [https://app.textbee.dev](https://app.textbee.dev) 註冊帳號
2. 在手機上安裝 textbee App，並登入同一帳號
3. 在 Dashboard 取得 **API Key**
4. 建立 Webhook，URL 填入 `https://你的網址/webhook/sms`，取得 **Webhook Secret**
5. 將 API Key 與 Webhook Secret 填入 `.env`

### OpenAI 設定（選填）

填入後啟用兩項功能：
1. 模糊語意解析：長輩可傳「護國神山今天怎樣」等自然語言
2. 「買哪隻安全」等開放性問題由 GPT 給出友善回覆

不填則使用本地別名對應表（涵蓋數十種常見股票暱稱）。

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
4. 建立完成後，複製 **Internal Database URL**
5. 前往 Web Service → 「Environment」→ 新增：
   ```
   DATABASE_URL = （貼上 Internal Database URL）
   ```
6. 重新 Deploy，系統啟動時會自動建立所有資料表

> **注意：** Render 免費 PostgreSQL 會在 **90 天無活動後自動刪除**。

---

## ▶️ 啟動方式

### 啟動 FastAPI 服務

```bash
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

ngrok 會提供一個類似 `https://abc123.ngrok.io` 的網址，複製後填入 textbee Webhook 設定。

---

## 📡 textbee Webhook 設定

1. 登入 [textbee Dashboard](https://app.textbee.dev)
2. 前往「Webhooks」→「New Webhook」
3. URL 填入：
   ```
   https://你的網址/webhook/sms
   ```
4. 事件選擇 `MESSAGE_RECEIVED`
5. 儲存後複製 Webhook Secret，填入 `.env` 的 `TEXTBEE_WEBHOOK_SECRET`

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
| `警報 股票代號 目標價` | 設定到價警報 | `警報 2330 750` |
| `警報 股票代號 目標價 突破` | 設定突破警報 | `警報 2330 800 突破` |
| `取消警報 股票代號` | 取消警報 | `取消警報 2330` |
| `開始` | 啟用服務 | `開始` |
| `停止` | 停用服務 | `停止` |
| `說明` | 查看操作說明 | `說明` |

> **支援台股與美股：**  
> 台股輸入純數字（如 `2330`、`0050`），系統自動加 `.TW` 後綴。  
> 美股輸入英文代號（如 `AAPL`、`TSLA`）。  
> 也支援股票暱稱，如「護國神山」、「GG」、「海爸」等。

---

## 📁 專案結構

```
stock-sms-elder/
├── app/
│   ├── __init__.py           # Package 初始化
│   ├── main.py               # FastAPI 主程式 + Webhook 入口
│   ├── sms_handler.py        # 解析簡訊指令（規則引擎）
│   ├── intent_parser.py      # 模糊語意解析（別名表 + GPT）
│   ├── stock_fetcher.py      # 抓取股票資料（yfinance，備用）
│   ├── stock_fetcher_finmind.py  # FinMind 資料抓取（主要）
│   ├── response_formatter.py # 格式化長輩友善回覆文字
│   ├── personal_advisor.py   # 個人化建議（規則引擎）
│   ├── sms_client.py         # textbee 發送簡訊
│   ├── database.py           # 資料庫操作（SQLAlchemy）
│   ├── scheduler.py          # 訂閱排程（APScheduler）
│   └── stock_name_map.py     # 離線股票名稱對應表
├── dashboard/
│   └── streamlit_app.py      # Streamlit 管理後台
├── .env.example              # 環境變數範例
├── requirements.txt          # Python 套件清單
└── README.md                 # 本文件
```

---

## 🔍 常見問題

**Q: 收不到回覆簡訊？**  
A: 確認 textbee App 在手機上保持背景執行，且 Webhook URL 填寫正確。用 `/health` 端點確認服務是否運作。

**Q: 股票代號查不到？**  
A: 台股輸入 4~5 位數字。部分冷門股 yfinance 可能沒資料，可先到 Yahoo Finance 查確認代號。

**Q: 長輩傳「護國神山」沒反應？**  
A: 確認 `.env` 有填入 `OPENAI_API_KEY`，或確認該暱稱在本地別名表中（`intent_parser.py` 的 `_ALIAS_MAP`）。

**Q: 訂閱通知沒有發送？**  
A: 確認 textbee App 在指定時間有網路連線，且 FastAPI 服務持續在運行中。

**Q: 資料來源是什麼？可以商業使用嗎？**  
A: 本專題使用 FinMind 開源資料，僅供教育用途。如需商業化營運，需申請正式行情資料授權（Fugle MarketData 或證交所授權）。詳見下方「資料授權說明」。

---

## 📜 資料授權說明

### 本專題使用的資料來源

**主要資料源：FinMind**
- 網站：https://finmind.github.io/
- 授權：教育用途免費使用
- 限制：僅限非商業、教育、學術研究
- 聲明：本專案所有內容均用於教育、非商業用途

### 使用規範

✅ **允許使用情境：**
- 學校專題、畢業製作
- 學術研究、論文
- 技術展示、概念驗證
- 非營利教育推廣

❌ **禁止使用情境：**
- 商業營運（無論是否收費）
- 對外提供付費服務
- 任何營利行為

### 免責聲明

本服務所提供資訊僅供參考，不構成投資建議。  
使用者依本資料交易發生交易損失需自行負責。  
所有資訊以臺灣證券交易所公告資料為準。

### 商業化路徑

如未來計劃商業化營運，需申請正式行情資料授權：

1. **Fugle MarketData**
   - Developer 方案：NT$1,499/月
   - 官網：https://developer.fugle.tw/
   
2. **證交所資訊廠商授權**
   - 需申請資訊廠商資格
   - 年費約 NT$5-20萬起

3. **TW Market Data**
   - 聯繫取得企業授權
   - 官網：https://twmarketdata.com/

---

## 📄 授權

MIT License — 自由使用於個人或學術專題。
