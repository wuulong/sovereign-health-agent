# 🏥 台美官方藥物與給付即時查詢工具使用手冊
`Sovereign Health Agent (SHA) - Official Drug Query Utility Manual`

本工具是由主權健康代理人（Sovereign Health Agent, SHA）所開發的官方聯網查詢工具，旨在協助研究人員與臨床分析人員直接連線台灣與美國官方的開放資料庫（Open Data），進行無 Mock、防幻覺的藥物品項、健保給付藥價、藥物許可證與官方適應症之即時比對。

---

## 📌 核心特色

1. **三方官方直連 (No-Mock Trinity Query)**：
   * **美國 FDA (OpenFDA API)**：即時連線美國食品藥物管理局 label API，查詢原廠藥名、學名、活性成分及英文適應症。
   * **台灣食藥署 (TFDA)**：下載並解析最新「未註銷藥品許可證資料集」，提供完整中文適應症與藥證狀態。
   * **台灣健保署 (NHI)**：下載並解析最新「健保用藥品項查詢項目檔」，提供給付價格、生效日期與健保代碼。
2. **健壯的動態解析 (Robust Parser)**：
   * **動態標頭索引映射 (Header Mapping)**：自動分析健保 CSV 的第一行標頭，動態對齊藥品代碼與支付價欄位，防堵政府平台更新結構導致腳本失效。
   * **內建自動解壓縮 (Auto-ZIP Extraction)**：自動偵測 TFDA 網址下載的壓縮檔，並使用 Python 內建 `zipfile` 模組動態解壓為 JSON 讀取，免去手動操作。
   * **空值防禦 (NoneType Protection)**：全面防護 API 欄位 Null 值，防止查詢時產生程式崩潰。
3. **無外部依賴 (Zero Dependency)**：
   * 100% 使用 Python 3 內建標準庫（`urllib`, `json`, `csv`, `zipfile`, `argparse`），不需安裝額外第三方套件，隨開隨用。

---

## 💻 系統需求

* **作業系統**：Windows / macOS / Linux
* **Python 版本**：Python 3.6 或以上版本
* **網路連線**：需具備外網連線能力以進行首次下載與即時 API 查詢

---

## 🛠️ 安裝與設定

本工具為單一 Python 腳本，無需特別安裝程序。請確保腳本具備執行權限：

```bash
chmod +x events/sovereign-health-agent/utils/query_official_drug_db.py
```

---

## 📖 使用說明與指令範例

本工具提供三種查詢模式（`--nhi`, `--tfda`, `--fda`）與一個強制更新參數（`--update`）。

### 1. 查詢台灣健保署給付價格 (`--nhi`)
此模式會連線至健保署官方端點下載最新藥價檔，並依關鍵字進行模糊比對。

* **指令範例**：
  ```bash
  python3 events/sovereign-health-agent/utils/query_official_drug_db.py --nhi Entecavir
  ```
* **查詢範圍**：健保代碼、中文品名、英文品名。
* **輸出欄位**：健保代碼、中文品名、英文品名、支付價格、生效日期。

### 2. 查詢台灣食藥署許可證與適應症 (`--tfda`)
此模式會下載最新「未註銷藥品許可證資料集」並解壓，進行本地模糊比對。因檔案大小約 30MB，首次下載需要數十秒。

* **指令範例**：
  ```bash
  python3 events/sovereign-health-agent/utils/query_official_drug_db.py --tfda Elranatamab
  ```
* **查詢範圍**：許可證字號、中文品名、英文品名、主成分略述。
* **輸出欄位**：許可證號、中文品名、英文品名、主成成分、官方適應症。

### 3. 查詢美國 FDA 官方登記資訊 (`--fda`)
此模式直接發送網路請求至美國 OpenFDA API，檢索最新註冊的藥物標籤資訊。

* **指令範例**：
  ```bash
  python3 events/sovereign-health-agent/utils/query_official_drug_db.py --fda Elranatamab
  ```
* **查詢範圍**：學名 (Generic Name)、商品名 (Brand Name)。
* **輸出欄位**：商品名稱、學名、活性成分、英文官方適應症 (擷取前 200 字)。

### 4. 強制更新本機快取資料 (`--update`)
為避免重複下載，腳本預設會使用本機暫存資料。若需獲取最新資料，請加上 `--update`。

* **指令範例**：
  ```bash
  python3 events/sovereign-health-agent/utils/query_official_drug_db.py --nhi Entecavir --update
  ```

---

## 📁 快取機制與檔案說明

本工具下載的官方開放資料檔案將會暫存於以下路徑：
* **快取根目錄**：`events/sovereign-health-agent/data/open-data/medication/`

### 快取檔案對照表：
| 來源單位 | 暫存檔案名稱 | 官方直連下載點 (URL) |
| :--- | :--- | :--- |
| **健保署** | `nhi_drugs_latest.csv` | `https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-E41001-001` |
| **食藥署** | `tfda_drugs_latest.json` | `https://data.fda.gov.tw/data/opendata/export/37/json` |

> 💡 **注意事項**：食藥署下載的原始檔案為 ZIP，解壓後會將 JSON 覆寫存回 `tfda_drugs_latest.json`，以節省本地儲存空間。

---

## ⚖️ 免責聲明

1. 本工具僅提供政府公開資料之即時比對與檢索，僅供學術研究與個案分析參考。
2. 藥品實際給付條件（如給付規定章節、事前審查規定等）與適應症詳情，請以衛福部健保署及食藥署之官方公告單張為準。
3. 臨床用藥決策請務必遵循醫囑與合格醫療人員指引，切勿擅自更動用藥。
