# sovereign-health-agent (SHA 主權健康代理人) 跨專案 AI 協同接駁總覽

> **遵守規格**：PGS v3.2 (專案治理規格書) & CGS v2.4 (CLI 治理規範，Pipeline-Native)  
> **專案定位**：台灣人通用、100% 地端運作、單人單獨使用之端側個人主權健康代理人 (Edge Sovereign Health Agent)  
> **當前版本**：`v0.1.5` (支援 CGS v2.4 萬用管道、FHIR R4 去識別化結構化匯出、本地三表 PHR 隔離與 tw-med-db 雙向接駁)  
> **核心使命**：落實以病患為中心的「主權自決與自救」理念。使用者在本地完全獨立運作，在物理上徹底隔離個人敏感健康資料，杜絕中心化雲端個資外洩風險。提供「邊問邊補」症狀口述結構化、FHIR R4 去識別化交換、用藥三向引導、癌症全週期國際臨床標準（CTCAE/NCCN/RECIST）端側快篩與在地醫療巨量資料唯讀對位。

---

## 1. 協同接駁契約索引 (Minimal Viable Context)

外部 AI Agent 或跨系統（如醫院遠端門診、資料中台、院端 HIS、其他專案 Agent）調用時，**嚴禁耗費大量 Token 暴力掃描全庫原始碼**，請依據需求直接精準讀取對應接駁檔案：

* 🚀 **呼叫 CLI/API 進行個人病歷查證、症狀對位、用藥警示或跨系統管道串接** ➔ 請讀取：[prompt_for_api.md](prompt_for_api.md)
* 🗄️ **解析本地自主 PHR 資料庫 (`fv_patient_personal.db`) 或掛載唯讀查詢** ➔ 請讀取：[prompt_for_db.md](prompt_for_db.md)

---

## 2. 🏛️ 核心垂直模組與能力全覽 (Module & Capability Matrix)

本專案遵循「三位一體架構（書-理論、資料庫-結構化、虛擬個人-實踐）」，核心能力劃分為六大功能維度：

| 模組代號 | 領域名稱 | 核心工具與進入點 | 規模與型態 | 核心功能與資料源 |
| :---: | :--- | :--- | :---: | :--- |
| **`M01`** | **主權查證工具箱 (SHVT)** | `utils/health_query_tool.py` | CLI (CGS v2.4)<br>子命令模式 | 100% 離線查詢疾病、用藥、醫師住院歷程、LOINC 檢驗程式碼；自動組裝 TFDA/健保署/PubMed (PMID) 實時查證連結防幻覺 |
| **`M02`** | **醫療巨量資料橋接器** | `utils/tw_med_bridge.py` | Adapter (CGS v2.4)<br>四階開關判定 | 唯讀存取外部地端 `tw-med-db`（522MB, 182 表），涵蓋 7.8 萬筆藥證 (M01)、健保價、適應症與 LOINC 檢驗碼對照，具備 100% 零崩潰降級 |
| **`M03`** | **個人健康代理人大腦** | `patient/patient_agent.py` | 互動對話 Agent<br>狀態機 (FSM) | 引導「邊問邊補」症狀自述、病情嚴峻說服熱接入 (`!sha_hot`)、動態衛教摘要 (`!sha_myedu`)，自動遮蔽 PII 並封裝 FHIR Observation |
| **`M04`** | **異質資料解析與正規化** | `utils/nhia_html_parser.py`<br>`utils/pdf_processor.py` | Ingestion Pipeline | 健保快易通 HTML 表格抽取清洗（民國年轉西元 ISO-8601）、實體紙本就醫病歷照片合成多頁安全 PDF 並計算 SHA-256 雜湊定錨 |
| **`M05`** | **去識別化與資料出入港** | `utils/db_porter.py` | CLI / JSON Porter | 選擇性結構化 JSON 匯出/匯入；支援 `--deidentify` 抹除姓名電話明文並對臨床日期隨機時間平移，支援多病患實體遷移 |
| **`M06`** | **癌症全週期標準種子庫** | `data/sample_seeds/`<br>`docs/cancer_standards_data_sources.md` | JSON Seed & Guide<br>(Future Work) | NCI EVS REST API 介接驗證，收錄 CTCAE v5/v6 神經毒性 Grade 1~4 官方結構化種子，支援離線毒性快篩對照 |

---

## 3. 資料主權與安全邊界宣告 (Philosophy & Security Boundaries)

1. **單一實體一病人 (Single-Instance per Patient)**：
   - 拒絕多租戶邏輯混存。每位病患的資料庫（`fv_patient_personal.db`）與原始檔案（`data/raw/`）擁有獨立物理目錄，徹底根除跨病患資料污染與洩漏風險。
2. **公共資料下沉 vs 個人資料封閉 (Dual-Track Partitioning)**：
   - 公共、無隱私之醫療法規與藥證巨量資料全面下沉於 **`tw-med-db`**。
   - 病患個人病歷、就醫事件與對話歷程完全封閉於 **`SHA`** 本地端，**絕不上傳公有雲**。
3. **強制 PII 去識別化與 FHIR R4 標準 (Zero-PII Interoperability)**：
   - 跨系統傳輸時，SHA 強制抹除姓名、身分證號、電話等明文個資，主體一律改採去識別化虛擬 ID（如 `Patient/PUMC_004-DEID`）。
   - 資料封裝嚴格對齊 HL7 FHIR R4 / TW Core IG 標準格式（`Observation`、`Condition`、`MedicationRequest`、`Encounter`）。
4. **Pipeline-Native 與零中斷平滑降級 (Graceful Degradation)**：
   - 所有 CLI 工具業務輸出嚴格保持為單行 Compact JSON (stdout)，系統日誌流向 stderr，天然適配 Unix 管道與跨 Agent 呼叫。
   - 若外部 `tw-med-db` 因未掛載或離線而無法使用，自動無縫降級至本地微型快取（`clinical_codes.json` 與 `cancer_standards_sample_seeds.json`），確保外部呼叫 100% 零崩潰。
