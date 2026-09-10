# 📖 本地主權健康離線查證工具箱 (SHVT) 操作手冊 (User Manual)

本手冊引導使用者（包括患者及照護家屬）如何操作完全離線運作的 **「本地主權健康查證工具箱 (Sovereign Health Verification Toolbox, SHVT)」**。本工具物理整合本地端 SQLite 個人健康資料庫與去識別化之原始病摘，旨在防範並對抗大語言模型 (LLM) 可能產生的醫療名詞、用藥資訊及住院軌跡之幻覺，落實「有所本、可查證」的主權自救理念。

> **💡 阿喜伯的實踐故事：**
> 阿喜伯的兒子為了幫阿喜伯核對他在治療期間的所有用藥變更史，並釐清白血球低點是不是在住院期間發生的，他啟動了本地離線的 SHVT 工具箱。阿喜伯看著螢幕上印出的交互式選單，點選了檢驗指標查詢。工具箱立刻秀出 WBC 數值的歷史曲線，並在低點自動標註「🏥 某某醫院住院期間對齊」，這讓阿喜伯和家人恍然大悟，消除了對數值忽高忽低的焦慮。接著，他們查詢醫師工號，立刻找出了去識別化的原始出院病摘片段。這一切完全在阿喜伯本機電腦上離線完成，隱私安全無虞，展現了高超的「可查證」章法。

---

## 📌 1. 工具基本概念

大語言模型雖具備良好的醫學常識與語意理解能力，但在面對個人就醫細節時，極易因字元錯位或時間線混亂而產生「幻覺」（例如誤記檢驗指標變化日期、虛構並未使用的藥物）。

**SHVT 工具箱** 採取 100% 本地端、離線、確定性 SQL 運算與實體原始病歷檢索，作為個人健康的「硬性防線」。在您使用 AI 進行病況整理與分析前，可隨時透過本工具進行雙向查核，保障資料準確無誤。本手冊以系統預設之去識別化範本作為功能示範，確保病患就醫隱私安全。

---

## 🎨 2. 終端互動式選單操作示範

若直接執行 `python3 utils/health_query_tool.py`，系統將引導您進入排版精緻、完全繁體中文的選單模式：

```text
=================================================================
    蓬萊本地主權健康查證與防幻覺工具箱 (SHVT)
=================================================================
  📂 【當前個人資料庫】: .../db/instances/myself/fv_patient_personal.db
  📂 【當前原始檔案庫】: .../data/instances/myself/raw
-----------------------------------------------------------------
  1. 查詢疾病衛教與臨床指引 (Disease & Guidelines)
  2. 查詢個人歷史用藥變更與藥物說明 (Medications)
  3. 查詢醫師/醫院就醫報告與原始檔案溯源 (Doctors & Reports)
  4. 查詢常用臨床指標歷史趨勢與住院對齊 (Lab Indicators)
  5. 翻譯 LOINC 或健保藥物程式碼 (Clinical Code Translator)
  6. 顯示系統免責聲明 (Disclaimer)
  Q. 離開工具箱 (Quit)
=================================================================
👉 請輸入選項 (1-6 或 Q): 
```

### 📋 簡易操作步驟：
1. 輸入 **`2`** 進入藥物查詢，接著輸入您想查證的藥物名稱（例如：`Entecavir` ），即可查閱該藥的臨床用藥歷史與對照整合健保碼。
2. 輸入 **`4`** 進入檢驗指標查詢，接著輸入指標程式碼（例如：`WBC`），即可完整瀏覽該指標的歷史軌跡及對照整合住院狀態。
3. 輸入 **`3`** 進入醫師溯源，輸入醫師程式碼或工號，便能查證其所負責之住院歷程，並取得去識別化之原始出處片段。
4. 輸入 **`Q`** 即可退出工具箱，返回主對話。

---

<details>
<summary>🛠️ 技術家屬區 (CLI 命令列參數與四大離線查證機制)</summary>

### 💻 終端命令列參數與操作

本工具位於 `utils/health_query_tool.py`，支援標準的命令列參數（Command-line arguments）。在終端機中，切換至 `events/sovereign-health-agent` 目錄下，執行以下命令：

```bash
python3 utils/health_query_tool.py [選項]
```

| 參數選項 | 英文完整參數 | 用途與說明 | 範例命令 |
| :--- | :--- | :--- | :--- |
| **`-i`** | `--interactive` | 啟動互動式終端對話選單（無任何參數時的預設模式）。 | `python3 utils/health_query_tool.py -i` |
| **`-d`** | `--disease` | 模糊查詢本機預載之疾病衛教說明與臨床指引。 | `python3 utils/health_query_tool.py -d 多發性骨髓瘤` |
| **`-m`** | `--drug` | 查詢個人歷史處方，並動態融合 `tw-med-db` 全台藥證與健保價。 | `python3 utils/health_query_tool.py -m 萬科` |
| **`-p`** | `--doctor` | 依醫師代號或關鍵字追溯所有關聯之就醫住院事件。 | `python3 utils/health_query_tool.py -p H01180` |
| **`-l`** | `--lab` | 查詢個人臨床檢驗指標歷史趨勢，自動與住院事件對齊。 | `python3 utils/health_query_tool.py -l WBC` |
| **`-c`** | `--code` | 翻譯臨床程式碼（優先查詢 `tw-med-db` LOINC/健保碼，平滑降級至本地字典）。 | `python3 utils/health_query_tool.py -c 1001-2` |
| **`--no-med-db`** | | 強制停用外部醫療大資料庫，切換為純本地離線字典模式。 | `python3 utils/health_query_tool.py --no-med-db -c 89555-7` |
| **`--with-med-db`**| | 強制嘗試啟用外部醫療大資料庫。 | `python3 utils/health_query_tool.py --with-med-db` |
| **`--db`** | | 指定要讀取的自訂 SQLite 資料庫物理路徑。 | `python3 utils/health_query_tool.py --db db/template.db` |

---

### 🧬 四大核心離線查證機制說明 (含 tw-med-db 醫療大資料融合)

1. **疾病與指南查詢（-d / --disease）**：直接模糊檢索本機 SQLite 中的 `MY_EDUCATION_BASE`（衛教庫）並印出。結尾自動拼裝產生該疾病在 PubMed 上的 Guidelines 搜尋連結，引導病患直接查閱最新文獻，避免被模型舊記憶誤導。
2. **個人用藥歷史差分與大資料藥證對照（-m / --drug）**：通用地遍歷個人歷程表中所有的 `MedicationRequest` 資源，依時間排序展現「劑量演變與目前狀態」。若環境中配置並啟用了 `tw-med-db`，系統將自動秒級檢索全台 6.6 萬筆官方藥品許可證，同步補充呈現健保程式碼、最新付款價格、有效主成分與核定適應症；若未啟用則平滑回退至純個人歷程模式。
3. **醫師與原始病歷檔案溯源（-p / --doctor）**：在去識別化原始病歷（`data/raw/`）中進行全文關鍵字檢索。一旦發現匹配，系統會透過 SQL Join `artifact_id`，找出對應之就醫事件 `Encounter`，印出醫師所屬住院區間與去識別化的原始檔案名稱、路徑與前後文字片段。
4. **檢驗指標歷史與就醫住院時間軸對齊（-l / --lab）**：查詢數值時，系統除列出時間趨勢外，會自動將每一筆檢驗日期與所有的住院區間進行交集比對（`Encounter.period.start <= Obs.date <= Encounter.period.end`），並在右方自動標註 `🏥 住院期間` 提醒。
5. **臨床程式碼雙軌翻譯（-c / --code）**：優先查詢 `tw-med-db` 醫療大資料庫（涵蓋完整 LOINC 檢驗碼與 TFDA 藥證清單）；若未安裝或未啟用該庫，系統將自動且 100% 靜默平滑降級至本地精簡字典（`clinical_codes.json` 與內建備援），保證查詢體驗不中斷。

---

### 🌉 醫療大資料橋接器 (tw_med_bridge.py) 開發與調用指引

為了達成「外部醫療大資料庫 (tw-med-db) 與本地個人資料庫 (PHR) 徹底物理隔離，且環境無此資料庫時零崩潰降級」的系統工程目標，系統將所有與 `tw-med-db` 相關的讀取封裝於獨立模組 `utils/tw_med_bridge.py` 中。

#### 1. 三級開關設定優先權
系統依下列順序判定是否啟用 `tw-med-db`：
1. **CLI 命令列旗標**：`--no-med-db`（強制關閉）或 `--with-med-db`（強制開啟）。
2. **環境變數**：`ENABLE_TW_MED_DB=0`（關閉）或 `ENABLE_TW_MED_DB=1`（開啟），亦可指定路徑 `TW_MED_DB_PATH="/path/to/med.db"`。
3. **專案設定檔 (`config.json`)**：
   ```json
   {
     "enable_tw_med_db": true,
     "tw_med_db_path": null
   }
   ```
4. **預設自動尋找**：若路徑為 `null`，自動探測專案外部之相對路徑（如 `../../events/TDHI_haba/med-db-in/tw-med-db/db/med.db`）。

#### 2. CGS v2.4 標準命令列子命令與管道操作 (CLI & Pipeline)
`tw_med_bridge.py` 完全支援 CGS v2.4 Pipeline-Native 標準，具備結構化子命令、單行緊湊 JSON (`-j/--json`) 與管道串流 (`--stdin`) 支援：
```bash
# 1. 檢查目前連線狀態 (支援 -j 輸出緊湊 JSON)
python3 utils/tw_med_bridge.py status
python3 utils/tw_med_bridge.py status -j

# 2. 搜尋官方藥證與健保價 (M01 FTS5 / LIKE)
python3 utils/tw_med_bridge.py search "萬科"
python3 utils/tw_med_bridge.py search "萬科" -j

# 3. 翻譯臨床檢驗程式碼 (M12 LOINC) 或藥品程式碼
python3 utils/tw_med_bridge.py code "1001-2"

# 4. 查詢健保給付規定條文 (M06)
python3 utils/tw_med_bridge.py rule "抗高血糖" -j

# 5. Pipeline 原生管道串接 (Unix-style stdin ➔ stdout)
echo "1001-2" | python3 utils/tw_med_bridge.py code --stdin -j

# 6. 模擬無 tw-med-db 環境下的安全降級驗證
python3 utils/tw_med_bridge.py --no-med-db status -j

# 7. 檢視自我描述 Schema 與說明手冊
python3 utils/tw_med_bridge.py schema
python3 utils/tw_med_bridge.py man
```

#### 3. Python 程式碼直接調用 (API)
在自訂腳本或擴充代理人功能時，可直接 import 使用：
```python
from utils.tw_med_bridge import get_med_bridge

# 取得單例 Bridge 實例
bridge = get_med_bridge()

if bridge.is_available():
    # 1. 搜尋藥物
    drugs = bridge.search_drugs("Velcade", limit=3)
    
    # 2. 依健保碼或許可證字號精確查詢
    drug_detail = bridge.get_drug_by_code("DHA00202451009")
    
    # 3. 翻譯臨床檢驗程式碼 (LOINC)
    loinc_info = bridge.translate_clinical_code("1001-2")
    
    # 4. 查詢健保給付規定條文
    rules = bridge.get_payment_rules("抗高血糖")
else:
    # 平滑降級邏輯 (Fallback)
    print("tw-med-db 未啟用或未安裝，自動採用本地備援機制")
```

</details>

---

## 🔒 3. 隱私防護與免責防線

1. **去識別化防禦**：本工具箱在終端印出任何敏感資料（如病歷原始內容、就醫紀錄）時，會自動調用遮蔽正則，將身分證字號、姓名等遮蔽（例如：`王○明`），避免旁人窺視。手冊檔案與範本亦遵循此原則，不透露任何真實病患細節。
2. **免責硬性聲明**：每一次執行查詢時，系統尾部均會強制印出台灣繁體中文的「醫療免責聲明」，提醒使用者任何用藥變更與臨床決策應向專業主治醫師諮詢，守護醫病溝通的安全邊界。
