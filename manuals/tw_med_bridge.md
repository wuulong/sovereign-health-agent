---
title: TW_MED_BRIDGE
section: 1
date: 2026-09-10
header: SHA User Commands
footer: v2.4
---

# NAME
tw_med_bridge - Sovereign Health Agent (SHA) 台灣醫療大數據邊界適配器 (CGS v2.4)

# SYNOPSIS
`tw_med_bridge.py` [*COMMAND*] [*OPTIONS*]...  
`tw_med_bridge.py` `status`  
`tw_med_bridge.py` `search` *KEYWORD*  
`tw_med_bridge.py` `code` *CODE*  
`tw_med_bridge.py` `rule` *QUERY*  

# DESCRIPTION
`tw_med_bridge.py` 是符合 CLI Governance Spec (CGS) v2.4 規範之醫療大數據適配器。
它封裝對地端 `tw-med-db` 醫療資料庫之唯讀連線，支援 M01 (處方藥證)、M02 (主成分)、M06 (健保給付規定) 與 M12 (LOINC 檢驗碼) 核心檢索。
本工具支援三級開關控制（CLI 旗標 > 環境變數 > `config.json` > 預設相對路徑），並具備 100% 零崩潰平滑降級能力。

# COMMANDS
`status`
: 診斷當前資料庫連線狀態、可用性與實體路徑。

`search` *KEYWORD*
: 搜尋處方藥品與官方藥證 (M01 FTS5/LIKE)。

`code` *CODE*
: 翻譯臨床檢驗代碼 (M12 LOINC) 或藥品許可證號。

`rule` *QUERY*
: 檢索健保給付規定條文 (M06)。

`schema`
: 輸出符合 CGS v2.4 之 JSON Schema。

`version`
: 輸出工具與 CGS 規格版本。

# OPTIONS
`-j`, `--json`
: 啟用單行緊湊 JSON 格式輸出，方便 AI Agent 與 Pipeline 串接。

`-q`, `--quiet`
: 極簡輸出模式，不輸出任何裝飾文字。

`--no-med-db`
: 強制停用外部醫療大數據庫，切換為本地離線降級模式。

`--with-med-db`
: 強制嘗試連線外部醫療大數據庫。

`--db` *PATH*
: 指定自訂之 `med.db` 實體檔案路徑。

`--stdin`, `-`
: 自標準輸入讀取查詢字串。
