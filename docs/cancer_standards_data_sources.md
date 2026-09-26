# 癌症全週期臨床標準資料來源與種子下載實務指引 (Cancer Clinical Standards Data Acquisition Guide)

本檔案完整記錄癌症全週期臨床標準（包含 NCI CTCAE、NCCN、AJCC TNM、RECIST、CAP 等）在探勘、實體 API 介接與範例種子下載時的**實測經驗、避坑紀錄（Pitfalls）、正式 REST 端點與一鍵拉取範例程式碼**。確保未來啟動資料庫建置（`tw-med-db` H56~H60）與個人端側代理程式（`SHA`）工具開發時，資料源與種子資料皆已備妥且隨手可用。

---

## 1. 核心標準架構與下載地圖

| 領域 / 標準 | 權威機構 | 核心用途 | 官方建議端點 / 來源 | 目標資料表 (`tw-med-db`) | SHA 應用工具 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CTCAE v5.0/v6.0** | 美國國家癌症研究所 (NCI) | 化放療副作用與不良反應分級 (Grade 1~5) | **NCI EVS REST API** (NCIt 概念圖譜) | `M58_ctcae_terms` (`H57`) | `utils/cancer_toxicity_screener.py` |
| **NCCN Guidelines** | 美國國家綜合癌症網路 (NCCN) | 癌症診療指引、化療處方模板 (Order Templates) | NCCN Categories of Preference / 臨床處方公開字典 | `M57_nccn_templates` (`H56`) | `utils/regimen_comparator.py` |
| **AJCC Staging (8th/9th)** | 美國癌症聯合委員會 (AJCC) | TNM 臨床與病理分期系統 | AJCC API / SEER Staging Rules | `M59_ajcc_staging` (`H58`) | `utils/tnm_stage_evaluator.py` |
| **RECIST 1.1 / iRECIST** | EORTC / NCI | 實體腫瘤療效評估標準 (CR/PR/SD/PD) | NCI NCIt Criteria Definitions | `M60_recist_criteria` (`H59`) | `utils/recist_response_tracker.py` |
| **CAP Protocols** | 美國病理學會 (CAP) | 癌症病理切片報告電子化檢核專案 | CAP Electronic Cancer Checklists (eCC) | `M61_cap_protocols` (`H60`) | `utils/pathology_parser.py` |

---

## 2. 官方端點探勘避坑經驗 (Crucial Pitfalls & Best Practices)

在探索官方來源時，實測發現以下重要經驗，後續開發請**嚴格遵守最佳路徑，避免重複踩坑**：

### ❌ 失敗與高風險端點（請勿再次嘗試）
1. **NCI FTP / Web 直接爬取** (`https://evs.nci.nih.gov/ftp1/CTCAE/` 或 `https://ctep.cancer.gov/...`):
   * **問題**：會遇到 HTTP 403 Forbidden、防爬蟲 WAF 阻擋，或被重新導向至通用登錄頁面。不適合作為 CI/CD 或自動化腳本的資料來源。
2. **非官方 GitHub 倉庫之靜態 Excel (`.xlsx`)**:
   * **問題**：常因檔案重新命名或刪除而遭遇 HTTP 404，且版本混雜（例如 4.03 與 5.0 混雜），缺乏語意唯一識別碼 (NCIt Code)。

### 🟢 唯一推薦官方架構：NCI Enterprise Vocabulary Services (EVS) REST API
* **Base URL**: `https://api-evsrest.nci.nih.gov/api/v1/`
* **認證機制**：**100% 免費、公開、無需任何 API Key**，具備極高可靠度與結構化 JSON 輸出。
* **主要查詢端點**：
  1. **全文/術語搜尋 (Search)**:
     ```http
     GET https://api-evsrest.nci.nih.gov/api/v1/concept/ncit/search?terminology=ncit&term={關鍵字}
     ```
  2. **概念詳細屬性與階層 (Concept Full Details)**:
     ```http
     GET https://api-evsrest.nci.nih.gov/api/v1/concept/ncit/{code}?include=full
     ```
  3. **CTCAE 分級子概念 (Children/Grades)**:
     * 可從主概念的 `children` 陣列直接解析出對應的 Grade 1、Grade 2、Grade 3、Grade 4 程式碼。

---

## 3. 本地種子範例資料 (Seed Data)

本地已備妥實體種子範例 JSON 檔案：
* **實體路徑**：`events-2026Q3/sovereign-health-agent/data/sample_seeds/cancer_standards_sample_seeds.json`
* **收錄內容範例**：
  * `C143752`: Peripheral Sensory Neuropathy, CTCAE（周邊感覺神經病變主概念）
  * `C144328`: Grade 1 Peripheral Sensory Neuropathy (Mild symptoms)
  * `C144912`: Grade 2 Peripheral Sensory Neuropathy (Moderate symptoms; limiting instrumental ADL)
  * `C145535`: Grade 3 Peripheral Sensory Neuropathy (Severe symptoms; limiting self-care ADL)
  * `C146043`: Grade 4 Peripheral Sensory Neuropathy (Life-threatening consequences; urgent intervention indicated)

---

## 4. 快速拉取腳本 (Python Recipe)

未來需要擴充或重新拉取其他副作用（如皮疹、腹瀉、噁心嘔吐）時，直接執行下列 Python 邏輯即可：

```python
import json
import urllib.request

def fetch_ncit_concept(code: str):
    """透過 NCI EVS REST API 取得特定 NCIt / CTCAE 概念"""
    url = f"https://api-evsrest.nci.nih.gov/api/v1/concept/ncit/{code}?include=full"
    req = urllib.request.Request(url, headers={"User-Agent": "SHA-Tool/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

# 範例：取得 Grade 2 神經病變定義
data = fetch_ncit_concept("C144912")
print(f"名稱: {data.get('name')}")
print(f"定義: {data.get('definitions', [{}])[0].get('definition')}")
```
