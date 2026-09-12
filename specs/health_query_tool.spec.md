# 蓬萊主權健康查證工具箱規格書 (health_query_tool.spec.md)

## 1. 基本資訊
- **腳本名稱**: `health_query_tool.py`
- **所屬專案/目錄**: `events-2026Q3/sovereign-health-agent/utils/health_query_tool.py`
- **CLI 規格版號**: CGS v2.4 (AI-Native, Pipeline-Native, Structured Logging, Decoupled Sidecar)
- **模組版本**: `1.0.0`
- **追溯系統工程**: `[SPC-033, SPC-040, REQ-023, REQ-024, DSN-020]`
- **說明手冊**: `events-2026Q3/sovereign-health-agent/manuals/health_query_tool.md` 與 `book/ch09_shvt_user_manual.md`
- **依賴套件**: 標準庫 (`os`, `sys`, `sqlite3`, `json`, `argparse`, `urllib.parse`, `datetime`, `re`, `typing`)
- **外部外掛**: 可選地端 `tw-med-db` (`db/med.db`) 經由 `tw_med_bridge.py` 介接

## 2. 核心願景與設計哲學
本工具為 Sovereign Health Verification Toolbox (SHVT) 的核心查詢引擎。
旨在 100% 離線運作下，解析本地個人健康資料庫 (SQLite PHR)，提供疾病衛教、個人歷史用藥變更、醫師報告溯源、臨床指標歷史趨勢與代碼翻譯查證。

### 核心原則：
1. **Pipeline-Native 管道原生串接 (CGS v2.4)**：
   - 支援 `--stdin` / `-` 管道輸入與 clean stdout 輸出。
   - 支援 `-j / --json` 輸出單行緊湊 JSON，日誌與進度提示輸出至 `stderr`，實現零暫存檔之 AI 鏈式串接。
2. **三位一體資產治理 (Spec-Code-Manual)**：
   - 檔頭顯式宣告 `__cli_spec_version__ = "2.4"`。
   - 具備對應規格書與 UNIX Man 手冊。
3. **100% 向後向下相容 (Backward Compatibility)**：
   - 完全相容舊有的 `-d`, `-m`, `-p`, `-l`, `-c`, `-i`, `--status` 旗標與互動選單。
4. **雙軌醫療大數據融合與平滑降級**：
   - 整合 `tw_med_bridge`，在有大數據庫時提供 7.8 萬筆官方藥證與 LOINC 翻譯，無大數據庫時 100% 靜默退回本地備援字典。

## 3. CLI 命令列規格 (Subcommands & Arguments)

### 子命令架構 (現代化介面)
- `disease <keyword>`: 查詢疾病衛教與臨床指引 (對應 `-d`)。
- `drug <name>`: 查詢個人歷史用藥變更與藥物說明 (對應 `-m`)。
- `doctor <name_or_id>`: 依醫師姓名或代號追溯住院事件與原始病歷 (對應 `-p`)。
- `lab <indicator>`: 查詢臨床指標歷史趨勢與住院對齊 (對應 `-l`)。
- `code <code>`: 翻譯並查證常用臨床代碼與藥證 (對應 `-c`)。
- `status`: 檢查並顯示個人資料庫與醫療大數據連線狀態 (對應 `--status`)。
- `schema`: 輸出自我描述 JSON Schema。
- `version`: 輸出腳本與 CGS 規格版號。
- `man` / `manual`: 檢視完整說明書。

### 標準 Flag 支援
- `-j, --json`: 啟用單行緊湊 JSON 格式輸出。
- `-q, --quiet`: 極簡輸出。
- `-i, --interactive`: 啟動終端互動選單模式。
- `--no-med-db`: 強制停用外部醫療大數據庫（本地字典備援）。
- `--with-med-db`: 強制嘗試啟用外部醫療大數據庫。
- `--db <path>`: 指定自訂 SQLite 個人健康資料庫路徑。
- `--stdin`, `-`: 從標準輸入讀取查詢字串。
