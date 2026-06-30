# Sovereign Health Agent (主權健康代理人)

本專案旨在落實以病患為中心的「主權自決與自救」理念，建構一個 **台灣人通用、100% 本地端跑、單人單獨使用** 的個人健康代理人系統。使用者下載此工具後可在本地完全獨立運行，在物理上徹底隔離個人敏感資料，規避中心化雲端平台的個資洩露與安全管理風險。


## 🪐 三位一體架構 (Trinity Architecture)

本專案採用「書（方法論）- 資料庫（結構化）- 虛擬個人（實踐）」三位一體架構：

1. **書 (Theory)**：病患健康數據主權與邊問邊補自學指南，請參閱首頁 [book/README.md](book/README.md) 與自動目錄索引 [book/TOC.md](book/TOC.md)。
2. **資料庫 (Database)**：病患端的實體隔離自主 PHR 庫 `db/instances/{profile}/fv_patient_personal.db`，使用標準 SQLite，儲存去識別化個人健康歷程、就醫紀錄與雙軌簽署同意書。
3. **虛擬個人 (Patient Agent)**：實體運行的個人健康代理人 `patient/patient_agent.py`，協助引導患者進行「邊問邊補」症狀自述，並將其封裝為 FHIR Observation 標準格式推送給醫院端。

## 🧬 測試受體：虛擬病人 004 (阿喜伯 / PUMC_004)

阿喜伯（蓬萊 004）是本專案的測試案例。他可以使用此 Agent 在看診前於本地端記錄背痛等症狀，並透過安全信道將去識別化的 FHIR 數據傳輸至 `tdhi-agent-sandbox` 的門診分流路由器。

## 💬 對話快捷指令手冊 (Dialogue Commands Guide)

在執行 `python patient/patient_agent.py` 的對話終端中，Sovereign Health Agent 支援以 `!sha_` 為前綴的快捷指令，供您進行進階的健康管理：

*   **`!sha_hot` (熱接入快速建檔)**：用於病情嚴峻的黃金決策期，以一問一答快速建立病情、用藥、看診醫院、過敏史核心檔案，並去識別化存檔。
*   **`!sha_myedu` (個人化衛教摘要卡)**：自動讀取本機 PHR 中的疾病與用藥，動態檢索本地衛教庫，產出區分實證文獻與 AI 智慧歸納日常照護的摘要。
*   **`!sha_edu` (瀏覽本機衛教庫主題)**：列出本機所有已預載之病情與用藥衛教條目，可輸入編號查看詳細內容與 AI 照護建議。

更多指令操作細節，請參閱手冊 [book/ch08_sha_commands_guide.md](book/ch08_sha_commands_guide.md)。

## 🛡️ 大書安全防禦校驗與 TOC 生成工具

本專案在 `utils/book_publisher.py` 部署了安全校驗工具。當您或 AI 編輯了 `book/` 底下的手冊內容後，可直接執行該工具：
*   **自動防禦校驗**：自動掃描 `book/` 下的所有正式 Markdown 檔案，執行隱私個資去識別化、絕對路徑相對化修正、以及台灣在地化用語校正（防範中國用語殘留）。
*   **自動 TOC 生成**：自動讀取已發布章節的第一行標題，刷新生成最新的 [book/TOC.md](book/TOC.md) 目錄索引。

## 🚀 快速開始與冷啟動指引 (Getting Started)

當您剛下載（Clone / Download）本專案至本地端時，請依循以下步驟啟動您的個人主權健康助理：

### 步驟 1：安裝依賴套件
建議先安裝 Pillow（圖片合成 PDF 用）與 BeautifulSoup4（網頁 HTML 解析用）：
```bash
pip install Pillow beautifulsoup4
```

### 步驟 2：一鍵啟動個人健康代理人 (對話式初始化)
您**不需要手動建立資料庫或物理目錄**，直接一鍵啟動個人代理人對話：
```bash
python patient/patient_agent.py
```
*此時 Agent 會進行冷啟動偵測。若為首次使用，會自動在對話中引導您：*
1. **自動建立環境**：詢問您是否一鍵物理初始化 SQLite 資料庫與 `data/inbox/`、`data/raw/` 目錄。
2. **需求痛點探索**：詢問您目前或家人正面臨的健康關卡，並動態解鎖更新您的 **[data/health_map.md](data/health_map.md) (健康自救地圖)** 看板，只啟用您當前需要的防線，避免不必要的填表焦慮。

### 步驟 3：日常自救操作實踐

#### 💬 情境 A：日常「邊問邊補」症狀自述
在資料庫初始化後，平時直接執行：
```bash
python patient/patient_agent.py
```
*助理會引導您輸入日常的不適，自動在本地端抹除個資（PII），封裝為標準 FHIR Observation JSON 輸出並存檔。*


#### 📥 情境 B：匯入您的健保快易通網頁另存檔案
依據 [健保健康存摺取得與解析指南](book/ch02_my_health_bank_guide.md)，將您另存網頁的 HTML 檔拖入 `data/inbox/`，並執行：
```bash
python utils/nhia_html_parser.py data/inbox/[您的另存網頁檔名].html
```
*系統會自動提取表格、去除網頁按鈕雜訊、民國年轉西元年，完成結構化入庫。*

#### 📸 情境 C：拍照合成您的實體紙本報告
依據 [台灣醫療報告實體紙本匯入指引](book/ch01_hospital_report_guide.md)，將您去醫院申請的紙本病歷照片拖入 `data/inbox/`，並執行：
```bash
python utils/pdf_processor.py PUMC_004 biopsy_report
```
*系統會自動將多張照片合成為一個多頁 PDF，計算安全 SHA-256 雜湊，重命名歸檔移入實體庫中。*

---
*版權所有 © 2026 Sovereign Health Agent. 基於哈爸「病患自主與自救」心法開發。*
