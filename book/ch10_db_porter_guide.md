# 🔄 蓬萊本地主權健康資料移轉工具使用手冊 (db_porter.py Operations Manual)

本手冊提供 `utils/db_porter.py` 工具的完整指令指引與實務操作範例。此工具專為病患與照護者設計，能物理遷移、備份、或去識別化共享您的個人健康歷程資料 (SQLite PHR)。

> **💡 阿喜伯的實踐故事：**
> 阿喜伯的兒子想要為阿喜伯的醫療資料建立一個定期備份，或者在阿喜伯需要入住長照護理之家時，將急性住院病歷、長照巴氏量表評估和目前用藥（CP方案、貝樂克）的照護建議無縫交接給長照機構。他使用本指南的 `db_porter` 工具，一鍵產生了「轉診與長照照護交接摘要」與「備份 JSON 包」。更重要的是，在把資料提供給研究機構進行多發性骨髓瘤分析時，他啟動了去識別化與確定性時間平移，在完全隔離個人隱私的前提下完成了資料共享。這讓阿喜伯體驗到了個人主權資料「能進能出、完全自決」的自由度。

---

## 🎯 1. 工具核心特性 (Core Features)

1.  **多主體實體隔離 (Profile Isolation)**：支援指定不同的 `--profile`（如 `myself`、`father`），程式會自動定位至對應隔離的個人資料庫與資料目錄。
2.  **去識別化防禦 (PII Masking)**：開啟 `--deidentify` 時，會自動遮蔽真實姓名、身分證字號與病患唯一代碼，保護隱私。
3.  **確定性隨機時間平移 (Deterministic Date Shifting)**：科研共享時，系統會依據 Profile 名稱的雜湊值 (Hash) 計算一組固定隨機天數，統一平移所有就醫與檢驗時間，既維持時間相對順序，又無法反向交叉比對破譯就診紀錄。
4.  **增量排重匯入 (Incremental Import)**：匯入備份檔時採用 `INSERT OR REPLACE` 機制，自動根據資料庫主鍵排除重複紀錄，無痛增量升級。
5.  **動態 Schema 對合 (Dynamic Schema Mapping)**：利用 `PRAGMA table_info` 動態讀取欄位，防止因資料庫版本微調導致結構毀損或衝突。

---

## 🚀 2. 七大情境操作範例 (The 7 Scenario Examples)

### 情境 A：產出門診 SOAP 溝通卡 (Markdown)
*   **用途**：提供給新醫師的去識別化病情摘要與關鍵檢驗指標明細。
*   **指令**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t clinical_summary -f md -o reports/clinical_summary.md
    ```

### 情境 B：科研去識別化與時間平移共享包 (JSON)
*   **用途**：去識別化並平移日期，提供給研究或臨床試驗機構。
*   **指令 (自動確定性平移)**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t research -f json --deidentify -o data/research_share.json
    ```

### 情境 C：完整主權健康檔案備份與移轉 (JSON)
*   **備份完整資料庫**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t backup -f json -o data/backup_myself.json
    ```
*   **增量排重載入至新資料庫 (跨裝置移植)**：
    ```bash
    python3 utils/db_porter.py --profile myself -i data/backup_myself.json
    ```

### 情境 D：緊急醫療救援卡 (ICE Card Markdown)
*   **用途**：產生救命用的血型、嚴敏藥物過敏史與緊急聯絡人極簡卡。
*   **指令**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t ice -f md -o reports/ice_card.md
    ```

### 情境 E：日常監測資料與日誌 (CSV)
*   **用途**：以 CSV 表格格式匯出，方便用 Excel 軟體開啟與列印（可篩選最近天數）。
*   **指令 (匯出最近 30 天日常監測資料)**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t daily_monitoring -f csv --days 30 -o data/vitals_30days.csv
    ```

### 情境 F：商業保險理賠申報包 (ZIP)
*   **用途**：自動打包某一就醫住院區間內的所有明細、處方，與關聯的原始病理 PDF 報告或收據圖片。
*   **指令 (需先取得該就醫 Encounter 的 entry_id，如 `ENC_202X_XX_XX_HG99999`)**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t insurance -f zip --event-id ENC_202X_XX_XX_HG99999 -o reports/claim_ENC_202X_XX_XX.zip
    ```

### 情境 G：轉診與長照照護交接摘要 (Markdown)
*   **用途**：整合急性出院摘要、巴氏量表分數、Beers 用藥警告與預立醫療 AD 狀態移交長照機構。
*   **指令**：
    ```bash
    python3 utils/db_porter.py --profile myself -e -t care_transition -f md -o reports/care_transition_summary.md
    ```

---

## 💬 3. 對話代理快捷整合 (Dialogue Integration)

本功能已原生嵌入 `patient_agent.py` 的對話迴圈中，病患在 Console 視窗直接輸入以下便捷指令：

*   **`!sha_backup`**：系統會在背景調用 `db_porter` 引擎，將您的 PHR 完整 JSON 備份產出至對應實例資料夾下（如 `data/instances/myself/backup_AFU_004_YYYYMMDD_HHMMSS.json`）。
*   **`!sha_ice`**：系統會動態彙整血型、過敏、緊急聯絡人，在 Console 視窗直接顯示「緊急救援卡」內容，並於背景輸出為 `data/instances/myself/ICE_AFU_004.md`。

---

<details>
<summary>🛠️ 技術家屬區 (CLI 完整參數列表與自動化測試指令)</summary>

### ⚙️ 命令列參數說明 (CLI Arguments Reference)

執行指令：`python3 utils/db_porter.py [選項]`

| 參數 | 類型 | 說明 |
| :--- | :--- | :--- |
| `--profile` | 字串 | 指定操作主體，例如 `myself` (預設) 或 `father`。 |
| `--db-path` | 路徑 | 手動指定目標資料庫 SQLite 檔案路徑。 |
| `-e, --export` | 開關 | 執行資料匯出動作。 |
| `-i, --import-file` | 路徑 | 執行資料匯入動作，並指定備份 JSON 檔案路徑。 |
| `-t, --type` | 字串 | 匯出的報告類型：`clinical_summary` / `research` / `backup` / `ice` / `daily_monitoring` / `insurance` / `care_transition` |
| `-f, --format` | 類別 | 匯出檔案格式：`md` / `json` / `csv` / `zip` (與匯出類型相符)。 |
| `-o, --output` | 路徑 | 輸出檔案的實體儲存路徑。 |
| `--deidentify` | 開關 | 啟用去識別化處理（抹除 PII 資訊）。 |
| `--shift-days` | 整數 | 手動指定平移天數。未指定時將採 deterministic hash 自動計算。 |
| `--include` | 字串 | 選擇性匯出：指定欲包含的 FHIR 資源類型（逗號分隔，如 `Observation,Condition`）。 |
| `--days` | 整數 | 日常監測 CSV 專用：指定匯出最近 N 天的監測觀測值。 |
| `--event-id` | 字串 | 保險理賠 ZIP 專用：指定住院 Encounter 事件的唯一的 `entry_id`。 |

---

### 🧪 自動化測試驗證 (Verification Tests)

開發團隊可執行以下自動化指令，在本地 `scratch/` 工作區模擬生成所有 7 種匯出情境的檔案，並盲檢資料庫讀寫：
```bash
python3 events/sovereign-health-agent/utils/test_db_porter.py
```
*若終端機輸出「所有 7 種匯出與轉移情境整合測試 [100% 通過]！」即代表系統功能健全。*

</details>
