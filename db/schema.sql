-- ======================================================================
-- Sovereign Health Agent (SHA) - Database Schema (v0.1.0)
-- 蓬萊本地主權健康個人 PHR 資料庫結構定義 (schema.sql)
--
-- 本檔案定義專案中 SQLite 本地自主 PHR 資料庫之核心表格結構。
-- 術語與欄位設計完全採用台灣繁體中文之系統工程與臨床醫療對合。
-- ======================================================================

-- 1. 使用者個人資料表 (MY_PROFILE)
-- 儲存去識別化之病患 Profile（例如王○明）與生理基礎特徵（身高、體重等）以利藥物劑量計算。
CREATE TABLE IF NOT EXISTS MY_PROFILE (
    patient_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    meta_data TEXT DEFAULT '{}'
);

-- 2. 病患醫療歷程 FHIR Bundle 表 (MY_CLINICAL_JOURNEY)
-- 存放結構化解譯後之 HL7 FHIR R4 標準資源（例如 Condition, MedicationRequest, Observation, Encounter）。
CREATE TABLE IF NOT EXISTS MY_CLINICAL_JOURNEY (
    entry_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    artifact_id TEXT,
    resource_type TEXT NOT NULL,
    fhir_resource_json TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    meta_data TEXT DEFAULT '{}'
);

-- 3. 使用者免責與不爭訟簽署合約表 (USER_CONSENTS)
-- 記錄使用者紙本或電子免責合約之簽署狀態與 Hash，維護法律與代理安全邊界。
CREATE TABLE IF NOT EXISTS USER_CONSENTS (
    consent_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    consent_version TEXT NOT NULL,
    fido_cert_sn TEXT,
    signature_hash TEXT,
    signed_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    contract_text_hash TEXT NOT NULL,
    consent_type TEXT DEFAULT 'online_otp', -- 'online_otp' / 'offline_paper'
    paper_artifact_hash TEXT,
    meta_data TEXT DEFAULT '{}'
);

-- 4. 我的衛教知識庫 (MY_EDUCATION_BASE)
-- 預載及動態下載（如 TFDA 許可證仿單）之臨床指引、藥理說明與照護卫教文章。
CREATE TABLE IF NOT EXISTS MY_EDUCATION_BASE (
    knowledge_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    citations TEXT,
    last_updated TEXT NOT NULL,
    meta_data TEXT DEFAULT '{}'
);

-- 5. 原始資料定錨表 (RAW_ARTIFACTS)
-- 對合 data/raw/ 中原始病歷/健康存摺檔案之 Hash 與本機儲存物理路徑，防範檔案篡改。
CREATE TABLE IF NOT EXISTS RAW_ARTIFACTS (
    artifact_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    meta_data TEXT DEFAULT '{}'
);
