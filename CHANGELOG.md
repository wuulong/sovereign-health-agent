# Changelog

All notable changes to the **Sovereign Health Agent** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-30

### Added (新增)
- **《主權個人健康管理手冊》全書 12 章正式合龍發布**：
  - **第一部分：資料建置篇 (第 1 - 4 章)**：撰寫並發布醫療報告申請 `ch01_hospital_report_guide.md`、健康存摺匯入 `ch02_my_health_bank_guide.md`、血液數值整合 `ch03_blood_test_import_guide.md`、與用藥對合 `ch04_medication_import_guide.md`，引導患者逐步建置個人去識別化 PHR 資料庫。
  - **第二部分：科研思辨篇 (第 5 - 7 章)**：撰寫並發布自主衛教 `ch05_patient_literacy_guide.md`、科研檢索 `ch06_clinical_research_guide.md`、與個人化醫囑 SOP `ch07_personalized_education_sop.md`，引入「三向引導迴路」及「AI Grounded QA 誠實問答 IDK 原則」。
  - **第三部分：工具操作篇 (第 8 - 10 章)**：撰寫並發布快捷對話指令 `ch08_sha_commands_guide.md`、SHVT 離線手冊 `ch09_shvt_user_manual.md`、與資料移轉 `ch10_db_porter_guide.md`，提供 7 大資料備份與去識別化科研共享情境。
  - **第四部分：終老尊嚴篇 (第 11 - 12 章)**：撰寫並發布台灣長照 2.0 與防跌 `ch11_ltc_beers_safety_guide.md`，以及病人自主權利法與在宅安寧 `ch12_hospice_comfort_care_guide.md`，拿回生命的自決權。
- **書籍目錄 `TOC.md` 自動生成**：於 `utils/book_publisher.py` 中實作自動目錄索引產生器，發布後自動依篇章結構刷新 `book/TOC.md`。

### Changed (修改)
- **單一真理源頭 (Single Source of Truth) 檔案管理架構**：
  - 確立 `book/` 目錄為手冊唯一編輯源頭，將 `sys_eng/book_planning/` 下已發布的重複 Guides 草稿檔案移走物理刪除，徹底消除重複維護與不慎覆蓋疑慮。
  - 將發布腳本 `book_publisher.py` 重構為「大書安全防禦校驗與 TOC 生成工具」，直接掃描 `book/` 底下正式檔案，執行個資脫敏、絕對路徑相對化修正、台灣在地化用語校正並重新寫回，扮演後台主動防禦防線。
- **書籍章節檔名雙位數前綴重構**：將所有 Guides 檔案重新命名加入 `ch01_` ~ `ch12_` 前綴，實現目錄與檔案管理器的物理順序對齊，並在發布時由腳本自動改寫全書內部交叉引用超連結。

---

## [0.1.3] - 2026-06-30


### Added (新增)
- **通用手冊脫敏與發布工具 [`utils/book_publisher.py`]**：實作大書自動化清洗發布 Python 程式。支援將開發用標記剪枝、絕對路徑校正為相對連結（如 `file:///utils/` 轉換為相對路徑 `../utils/`），並以私有對照配置進行個資脫敏。
- **YAML Frontmatter 狀態感知發布控制**：升級發布邏輯，僅發布頂端包含 `status: published` 標記的 Draft 檔案至 `book/`，並自動從正式目錄清理下架未標記或被刪除的 Draft。
- **本地私有脫敏對照表配置 [`utils/private_deid_rules.json` - Git 忽略]**：利用「邏輯與配置分離」架構，於 `.gitignore` 排除此對照檔，保證敏感個資（如使用者本機路徑、就醫日期、量測座標等）永遠留在本機，不流入 Git 儲存庫。
- **個資隱私安全與去識別化審查報告**：對 ToC 目錄與大書內容發動個資風險自審，確立時間相對化與化名化（阿喜伯）防禦對策。

### Changed (修改)
- **手冊目錄與準備檔案重構**：將 `book_toc.md`（開發大綱與寫作意圖）、`empirical_proof_matrix.md`（實證矩陣）與 `my_health_bank_menu.md`（選單結構）搬移至系統工程 `sys_eng/book_planning/`，實現「正式讀者版手冊」與「系統工程準備檔案」的優雅分離。
- **手冊封面與讀者 Toc 入口**：將 Draft `README.md` 移動至 `book_planning/` 進行狀態管理，並經由腳本自動脫敏發布至 `book/README.md`，提供乾淨、親切且無開發標記之大書封面與目錄。

---

## [0.1.2] - 2026-06-14

### Added (新增)
- **多維度病程與服藥遵從性交叉分析報告**：整合就醫各項生理與生化指標，交叉比對患者服藥異動引發之生理指標波動因果關係。
- **藥物用藥療效與安全性評估報告**：記錄患者服用藥物後膽固醇及低密度脂蛋白之改善療效，並比對肝功能指標證實長期藥物耐受安全性。
- **健康存摺「客製化希望清單與增量狀態維護法」[[my_health_bank_guide.md](file:///book/my_health_bank_guide.md#L136)]**：於手冊與目錄中建立增量狀態維護方法論，引導病患以最小心力（Minimal Effort）維持核心活性藥物與關鍵檢驗軌跡。
- **用藥變更之「三向引導迴路」機制 [[personalized_education_sop.md](file:///book/personalized_education_sop.md#L105)]**：於 SOP 中標準化用藥異動時的「起因追溯、後續監控、日常行為指引」閉環引導，並加入規律有氧運動與飲食藥物交互作用提醒。

### Changed (修改)
- **手動用藥與檢驗資料導入**：成功導入健康存摺歷史資料，手動補註合併用藥紀錄，建立完整病程資料庫。

---

## [0.1.1] - 2026-06-13

### Added (新增)
- **門診 SOAP 病情概況卡產製 (`!sha_soap`)**：一鍵整合患者 PHR（基礎生理特徵、診斷、主要用藥與近期自述症狀），生成結構化門診溝通 SOAP 檔並備份至本地 TXT 檔案中。
- **臨床急症評估與計畫輸出**：針對使用特定標靶藥物之免疫受抑患者，於 SOAP 中自動偵測發燒症狀，警告高度疑似腫瘤科急症，並剛性引導立即急診就醫、嚴禁服用退藥以防掩蓋熱型。
- **病患自救教育文件 [[patient_literacy_guide.md](file:///book/patient_literacy_guide.md)]（病患自主衛教與思辨指南）**：系統性指引病患防範與校驗 AI 幻覺，識讀 PubMed PMID，並利用台灣官方食藥署仿單系統與健保署系統查詢用藥與給付規定，養成自主查證與理性思辨之健康素養，並掛載至大書目錄中。
- **PMID 自動校驗工具 [`scratch/validate_pmids.py`]**：物理建立審計工具，能連線 NCBI PubMed API 校驗資料庫文獻真實性，防止錯位幻覺。
- **系統工程雙向追溯鏈對合**：於 `req_vision.md` 中新增 `REQ-012` 與 `REQ-013`、`spec_functional.md` 新增 `SPC-022` 與 `SPC-023`、`test_plan.md` 新增 `TCV-012` 與 `TCV-013`，並於 `verification_log.md` 標記為 `[PASS]`，維持 SE-6D 零警告狀態。

### Changed (修改)
- **資料庫預載文獻修復**：修正 [database_initializer.py](file:///db/database_initializer.py) 中標靶藥物與相關文獻之 PMID 錯位，重置資料庫並重新核對通過。
- **自動化測試擴充**：修改 [test_education.py](file:///test_education.py)，追加模擬發燒 Observation 寫入以及 `generate_soap_card()` 的測試。

---

## [0.1.0] - 2026-06-12

### Added (新增)
- **專案初始化**：物理建置 `sovereign-health-agent` 本地個人端代理人專案，並完成大專案之 Git Submodule 掛載。
- **本地 PHR 資料庫初始化**：實作 `database_initializer.py` 一鍵拉起 `MY_PROFILE`、`MY_CLINICAL_JOURNEY` 與 `USER_CONSENTS` 等表，並預載阿喜伯基本生理設定與紙本同意書。
- **「邊問邊補」與去識別化 FHIR Observation 輸出**：實作 `patient_agent.py`，支援病患日常對話自述、個資遮蔽及 HL7 FHIR Observation JSON 輸出。
- **「熱接入」說服與快速建檔 (`!sha_hot`)**：實作被動病情詞組監控與主動對話，快速問齊病情、用藥、醫院與過敏史並寫入 SQLite。
- **有所本生醫問答與誠實認錯機制**：模糊查詢本地 `MY_EDUCATION_BASE` 衛教資料庫，分流呈現「資料庫權威實證資訊」與「AI 智慧歸納日常照護」，並在偏方未知時觸發誠實未知話術（IDK）防線，剛性印出免責聲明。
- **系統工程治理 (SE-6D) 展開**：物理拉起六大範疇文檔，修復 10 項警告，達成 `se_manager.py audit` 零警告。
