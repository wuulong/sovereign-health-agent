# sovereign-health-agent: API / CLI 調用協同契約 Prompt (AI Agent Cheat Sheet)

> **調用主體**：Antigravity、Cursor、Claude Code、跨專案 Agent、院端門診分流路由器、資料中台、Shell 管道。  
> **遵守規格**：CGS v2.4 (Pipeline-Native, Token-Saving, Clean JSON, Subprocess-Friendly)。  
> **專案定位**：`sovereign-health-agent` (SHA 端側主權健康代理人)。

---

## 1. 核心 CLI 工具進入點

```bash
# 專案基準路徑: events-2026Q3/sovereign-health-agent/

# 進入點 A：蓬萊主權健康查證與防幻覺工具箱 (SHVT)
python utils/health_query_tool.py <subcommand> [flags]

# 進入點 B：台灣醫療大數據邊界適配器 (Bridge to tw-med-db)
python utils/tw_med_bridge.py <subcommand> [flags]

# 進入點 C：個人醫療資料去識別化導出入工具
python utils/db_porter.py [options]

# 進入點 D：個人健康代理人交談主程式
python patient/patient_agent.py [--profile <profile_name>]
```

---

## 2. 常用子命令速查表

### 2.1 主權健康查證工具箱 (`health_query_tool.py`)

1. **`status`**：檢測個人健康庫與外部醫療巨量資料庫連線態勢與實體路徑。
   ```bash
   python utils/health_query_tool.py status -j
   ```
2. **`disease <keyword>`**：查詢個人疾病診斷歷史、文獻查證出處（PMID）與臨床指引。
   ```bash
   python utils/health_query_tool.py disease "多發性骨髓瘤" -j
   ```
3. **`drug <drug_name>`**：查詢個人用藥歷程，自動融合 `tw-med-db` 官方藥證、健保核定價與適應症。
   ```bash
   python utils/health_query_tool.py drug "萬科" -j
   ```
4. **`doctor <doctor_name>`**：依醫師姓名或代號追溯住院事件、就醫科別與原始病歷。
   ```bash
   python utils/health_query_tool.py doctor "王醫師" -j
   ```
5. **`lab <indicator>`**：查詢臨床檢驗指標（如血糖、肌酸酐、球蛋白）之歷史數值與變化。
   ```bash
   python utils/health_query_tool.py lab "1001-2" -j
   ```
6. **`code <code>`**：翻譯並查證臨床檢驗程式碼 (LOINC) 或健保藥品碼。
   ```bash
   python utils/health_query_tool.py code "89555-7" -j
   ```

### 2.2 醫療巨量資料邊界適配器 (`tw_med_bridge.py`)

1. **`status`**：診斷外部 `tw-med-db` 可用性、表結構筆數與連線模式。
   ```bash
   python utils/tw_med_bridge.py status -j
   ```
2. **`search <keyword>`**：全文/模糊檢索 7.8 萬筆台灣官方處方藥證 (M01)。
   ```bash
   python utils/tw_med_bridge.py search "Bortezomib" -j
   ```
3. **`code <code>`**：精準查詢健保程式碼或國際檢驗程式碼 (M12 LOINC)。
   ```bash
   python utils/tw_med_bridge.py code "B024345100" -j
   ```
4. **`rule <keyword>`**：檢索抗癌藥物與標靶之健保事前審查給付規定條文 (M06)。
   ```bash
   python utils/tw_med_bridge.py rule "骨髓瘤" -j
   ```

### 2.3 資料去識別化導出入 (`db_porter.py`)

* **去識別化安全匯出**：
  ```bash
  # 匯出特定病患資料，抹除姓名電話明文並對臨床日期進行平移
  python utils/db_porter.py --export --profile myself --deidentify --output exported_clean.json
  ```
* **排重增量匯入**：
  ```bash
  python utils/db_porter.py --import --profile myself --input new_records.json
  ```

---

## 3. 標準輸出調用規範 (`--json / -j`)

* **機器/Agent 消費 (強制推薦)**：傳入 `--json`（或 `-j`），保證 stdout 輸出純淨單行或緊湊 JSON，無 ANSI 控制碼或排版框線。
* **日誌分流保證**：所有除錯、診斷、連線重試提示一律自動分流至 `stderr`，絕對不干擾 Unix Pipe。

---

## 4. Pipeline 管道串聯實戰範例 (Unix Pipe Cookbook)

### 場景 A：外部系統傳入藥品名稱 ➔ SHA 查詢官方藥證與核定價 (零暫存檔)
```bash
echo "Velcade" | python utils/tw_med_bridge.py search --stdin -j | jq .
```

### 場景 B：就醫用藥歷程查詢 ➔ 過濾特定處方狀態
```bash
python utils/health_query_tool.py drug "萬科" -j | jq '.results[] | {name: .drug_name, status: .status, price: .nhi_price}'
```

### 場景 C：離線強制降級查詢 (在無 tw-med-db 環境下保證零崩潰)
```bash
python utils/health_query_tool.py code "89555-7" --no-med-db -j
```
