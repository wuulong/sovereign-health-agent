---
title: HEALTH_QUERY_TOOL
section: 1
date: 2026-09-12
header: SHA User Commands
footer: v2.4
---

# NAME
health_query_tool - 蓬萊本地主權健康查證與防幻覺工具箱 (SHVT) (CGS v2.4)

# SYNOPSIS
`health_query_tool.py` [*COMMAND*] [*OPTIONS*]...  
`health_query_tool.py` `disease` *KEYWORD*  
`health_query_tool.py` `drug` *DRUG_NAME*  
`health_query_tool.py` `doctor` *DOCTOR_NAME*  
`health_query_tool.py` `lab` *INDICATOR*  
`health_query_tool.py` `code` *CODE*  
`health_query_tool.py` `status`  
`health_query_tool.py` `-i`  

# DESCRIPTION
`health_query_tool.py` 是 Sovereign Health Verification Toolbox (SHVT) 的核心查詢工具，遵循 CGS v2.4 規範。
本工具 100% 離線運作，旨在解析本地個人健康資料庫 (SQLite PHR)，提供疾病、用藥、醫師、就醫歷程與檢驗代碼之快速查證，並剛性組裝產生指向 TFDA、健保署及 PubMed (PMID) 的實時查證連結，防範模型幻覺。
同時，具備動態開關控制與外接台灣醫療大數據庫 (`tw-med-db`) 之能力。

# COMMANDS
`disease` *KEYWORD*
: 查詢疾病衛教與臨床指引，提供 PubMed 實時查證連結。

`drug` *NAME*
: 查詢個人歷史用藥變更與藥物說明，自動融合 tw-med-db 藥證資訊。

`doctor` *NAME_OR_CODE*
: 依醫師姓名或代號追溯住院事件與原始病歷。

`lab` *INDICATOR*
: 查詢臨床指標歷史趨勢與住院就醫事件對照。

`code` *CODE*
: 翻譯並查證常用臨床代碼 (LOINC 檢驗碼或健保藥品碼)。

`status`
: 檢查並顯示個人資料庫與外部醫療大數據庫連線態勢。

`schema`
: 輸出符合 CGS v2.4 之 JSON Schema。

`version`
: 輸出工具與 CGS 規格版本。

`man`, `manual`
: 檢視本說明手冊。

# OPTIONS
`-j`, `--json`
: 啟用單行緊湊 JSON 格式輸出，便於 AI Agent 與 Unix 管道串聯。

`-q`, `--quiet`
: 極簡輸出模式。

`-i`, `--interactive`
: 啟動終端對話式互動選單。

`--stdin`, `-`
: 從標準輸入讀取查詢字串。

`--no-med-db`
: 強制停用外部醫療大數據庫（採用本地字典備援）。

`--with-med-db`
: 強制嘗試啟用外部醫療大數據庫。

`--db` *PATH*
: 指定自訂 SQLite 個人健康資料庫路徑。

# EXAMPLES
1. 管道串流翻譯檢驗碼並以 jq 解析：
   ```bash
   echo "1001-2" | python3 health_query_tool.py code - -j | jq '.title'
   ```

2. 查詢個人用藥紀錄輸出 JSON：
   ```bash
   python3 health_query_tool.py drug "得利生" --json
   ```

3. 檢查資料庫與大數據連線健康度：
   ```bash
   python3 health_query_tool.py status
   ```

# SEE ALSO
bman(1), seman(1), tw_med_bridge(1)
