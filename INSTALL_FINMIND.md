# FinMind 整合安裝指南

## 📋 變更說明

本專題已從 yfinance 升級為 **FinMind**，以符合教育用途授權規範。

### 為什麼要換？
- ✅ **合法合規**：FinMind 明確允許教育用途
- ✅ **完全免費**：無請求限制
- ✅ **資料完整**：專為台股設計，資料齊全
- ✅ **穩定可靠**：社群活躍，長期維護

### 主要變更
1. 新增 `finmind` 套件到 requirements.txt
2. 新增 `app/stock_fetcher_finmind.py` 模組
3. 新增 `app/config.py` 設定檔
4. 更新 `README.md` 加入教育授權聲明
5. 更新 `app/response_formatter.py` 加入免責聲明
6. 更新 `app/main.py` 整合新資料源

---

## 🚀 安裝步驟

### 1. 安裝 FinMind

```bash
# 啟動虛擬環境（如果還沒啟動）
# Windows:
venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate

# 安裝新套件
pip install finmind
```

或者重新安裝所有套件：

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數（可選）

在 `.env` 檔案中可以設定資料源：

```env
# 資料源選擇：finmind 或 yfinance
DATA_SOURCE=finmind

# 其他設定保持不變
TEXTBEE_API_KEY=your_api_key_here
TEXTBEE_WEBHOOK_SECRET=your_webhook_secret_here
OPENAI_API_KEY=sk-xxxxxxxx  # 選填
DATABASE_URL=sqlite:///./stock_sms.db
```

**說明：**
- `DATA_SOURCE=finmind` - 使用 FinMind（預設，推薦）
- `DATA_SOURCE=yfinance` - 使用 yfinance（備用）

### 3. 啟動服務

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**應該會看到教育聲明：**

```
======================================================================
�� 股票 SMS 長輩服務
   學校專題/畢業製作
======================================================================

📊 資料來源：FinMind
   授權類型：教育用途
   資料網址：https://finmind.github.io/

⚠️  免責聲明：資料僅供參考，不構成投資建議
   使用者依本資料交易發生交易損失需自行負責
   本服務僅供學術研究與教育展示用途

======================================================================
🔧 目前資料源：FINMIND
======================================================================
```

---

## 📊 功能差異

### FinMind 支援
- ✅ 台股即時資訊（收盤價）
- ✅ 歷史資料（日K）
- ✅ 技術指標（RSI、MACD）
- ✅ 合理價分析
- ✅ 財報、三大法人等（進階功能）
- ❌ 美股資料（僅支援台股）
- ❌ 盤中即時報價（僅收盤後）

### yfinance 支援（備用）
- ✅ 台股資訊
- ✅ 美股資訊
- ✅ 技術指標
- ⚠️ 可能被封鎖
- ⚠️ 授權不明確

---

## 🧪 測試

### 測試 FinMind 是否正常運作

建立測試檔案 `test_finmind.py`：

```python
from app.stock_fetcher_finmind import get_stock_info

# 測試台積電
result = get_stock_info("2330")
print(result)

if result["success"]:
    print(f"✅ FinMind 測試成功！")
    print(f"   股票：{result['name']}")
    print(f"   價格：{result['price']}")
else:
    print(f"❌ 測試失敗：{result.get('error')}")
```

執行：
```bash
python test_finmind.py
```

### 測試簡訊回覆

傳送簡訊 `2330` 給您的 textbee 號碼，應該會收到：

```
📈 台積電
代號：2330
股價：1050.00 元
漲跌：▲5.00 (+0.48%)
今日區間：1045.00～1055.00
近30天均價：1040.00 元
目前股價在合理範圍。

[資料僅供參考｜FinMind]
```

---

## ⚠️ 常見問題

**Q: 安裝 finmind 失敗？**
```bash
# 確保 pip 是最新版本
python -m pip install --upgrade pip

# 重新安裝
pip install finmind
```

**Q: 啟動時沒看到教育聲明？**
- 檢查 `app/config.py` 是否存在
- 檢查 `app/main.py` 是否有 `from app.config import print_startup_disclaimer`

**Q: 查詢美股怎麼辦？**
- FinMind 只支援台股
- 如需美股，可在 `.env` 設定 `DATA_SOURCE=yfinance`
- 或者實作混合架構（台股用 FinMind，美股用 yfinance）

**Q: FinMind 資料不是即時的？**
- 是的，FinMind 提供的是收盤資料（T+0 或 T+1）
- 適合專題展示和教育用途
- 如需盤中即時報價，需使用 Fugle MarketData 付費方案

**Q: 商業化怎麼辦？**
- 如未來計劃商業化營運，需申請正式授權
- 建議：Fugle MarketData Developer 方案（NT$1,499/月）
- 或直接向證交所申請資訊廠商授權

---

## 📄 授權資訊

### FinMind 使用規範

**允許：**
- ✅ 學校專題、畢業製作
- ✅ 學術研究、論文
- ✅ 教育展示、概念驗證

**禁止：**
- ❌ 商業營運
- ❌ 對外提供付費服務
- ❌ 任何營利行為

詳見：https://github.com/FinMind/FinMind

### 本專題聲明

本專題使用 FinMind 開源資料，僅供學術研究與教育展示用途。
資料僅供參考，不構成投資建議。
使用者依本資料交易發生交易損失需自行負責。

---

## 🎓 專題報告建議

在專題報告中建議加入以下章節：

### 資料來源與授權
```markdown
本專題使用 FinMind 開源金融資料作為股票資訊來源。

**資料來源：** FinMind (https://finmind.github.io/)  
**授權依據：** 教育用途免費使用  
**資料範圍：** 台股日線、財報、三大法人等  
**更新頻率：** 每日收盤後更新  

**免責聲明：**
本服務所提供資訊僅供參考，不構成投資建議。
使用者依本資料交易發生交易損失需自行負責。
依據臺灣證券交易所『交易資訊使用管理辦法』，使用者須遵守相關規定。

**未來規劃：**
如本專題未來計劃商業化營運，將申請正式行情資料授權（Fugle MarketData 或證交所授權）。
```

---

## 📞 技術支援

如有任何問題，請參考：
- FinMind 官方文件：https://finmind.github.io/
- FinMind GitHub：https://github.com/FinMind/FinMind
- 本專題 README：README.md

---

**🎉 整合完成！祝專題順利！**
