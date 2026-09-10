# 台灣醫療大數據適配器規格書 (tw_med_bridge.spec.md)

## 1. 基本資訊
- **腳本名稱**: `tw_med_bridge.py`
- **所屬專案/目錄**: `events-2026Q3/sovereign-health-agent/utils/tw_med_bridge.py`
- **CLI 規格版號**: CGS v2.4 (Pipeline-Native, Structured Logging, Decoupled Sidecar)
- **模組版本**: `1.0.0`
- **追溯系統工程**: `[SPC-010, SPC-039, SPC-040, DSN-020, REQ-024, NFR-005]`
- **說明手冊**: `book/ch09_shvt_user_manual.md` 與 `events-2026Q3/sovereign-health-agent/manuals/tw_med_bridge.md`
- **依賴套件**: 標準庫 (`os`, `sys`, `json`, `sqlite3`, `argparse`, `typing`)
- **外部資源**: 可選地端 `tw-med-db` (`db/med.db`)

## 2. 核心願景與設計哲學
本適配器作為 Sovereign Health Agent (SHA) 跨出端側自治邊界、唯讀存取台灣醫療與健保大數據引擎 (`tw-med-db`) 的唯一橋樑。

### 核心原則：
1. **零依賴與環境解耦 (Decoupling & Graceful Degradation)**：
   - 外部醫療大數據庫（tw-med-db）為可選外掛 (Optional Extension/Sidecar)。
   - 在未安裝或關閉狀態下，100% 靜默平滑降級，絕不引發未捕捉異常中斷上層業務。
2. **絕對物理隱私邊界 (Privacy Boundary Protection)**：
   - 個人健康資料庫 (`fv_patient_personal.db`) 維持本地隔離。
   - `med.db` 僅以唯讀 (`file:...mode=ro`) 方式連接，杜絕任何跨庫寫入。
3. **Pipeline-Native 與結構化輸出 (CGS v2.4)**：
   - 支援 `--stdin` / `-` 管道輸入。
   - 透過 `-j/--json` 輸出單行緊湊 JSON，日誌全面輸出至 `stderr`，實現鏈式 AI 管道呼叫。

## 3. CLI 命令列規格 (Subcommands & Arguments)

### 共通子命令
- `status`: 檢驗當前 Bridge 連線、可用性狀態與 DB 路徑。
- `search <keyword>`: 檢索藥品許可證與健保價 (M01 FTS5/LIKE)。
- `code <code>`: 翻譯臨床代碼 (M12 LOINC 檢驗碼 或 M01 藥證)。
- `rule <query>`: 檢索健保給付規定條文 (M06)。
- `schema`: 輸出 CGS v2.4 結構化 JSON Schema。
- `version`: 輸出版本資訊與 CGS 版號。

### 標準 Flag 支援
- `-j, --json`: 輸出單行緊湊 JSON 格式。
- `-q, --quiet`: 極簡輸出（純 ID 或必要文字）。
- `--no-med-db`: 強制模擬停用外部資料庫（驗證降級）。
- `--with-med-db`: 強制嘗試連線外部資料庫。
- `--db <path>`: 指定自訂 `med.db` 路徑。
- `--stdin`, `-`: 從標準輸入讀取關鍵字或代碼串流。
