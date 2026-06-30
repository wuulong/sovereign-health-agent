# 臺灣核心實作指引 (TW Core IG) FHIR 驗證技術指南

本文件旨在詳細解析在進行個人醫療病歷 FHIR (Fast Healthcare Interoperability Resources) 規格驗證時，Java Validator 執行參數中加載 `-ig tw.gov.mohw.twcore` 的底層運作機制、網址規範以及實務部署對策。

---

## 1. `-ig tw.gov.mohw.twcore` 參數的基本定義

在執行 HL7 官方 Java Validator 時，`-ig` (Implementation Guide) 參數用於載入特定的實作指引套件。`tw.gov.mohw.twcore` 是中華民國衛生福利部（MOHW）於國際 FHIR Registry 註冊的官方套件識別碼，代表 **「臺灣核心實作指引 (Taiwan Core Implementation Guide)」**。

加載此參數能讓驗證器理解並驗證符合臺灣本土醫療常規（如健保申報、身分證字號、本地藥物代碼等）的 FHIR 資源。

---

## 2. 驗證器加載套件後的核心工作

當您在指令中加入 `-ig tw.gov.mohw.twcore`，Validator 會在幕後執行以下三大核心工作：

### 2.1 自動下載與本地快取 (Package Caching)
* 驗證器啟動時，會自動連線至官方的 FHIR Package Registry 下載 `tw.gov.mohw.twcore` 的規格套件壓縮包，並將其解壓縮快取於您的本地系統（macOS 路徑通常為 `~/.fhir/packages/tw.gov.mohw.twcore#[版本號]`）。

### 2.2 啟用臺灣本土化資料結構驗證 (Structure Validation)
* **檢查必填欄位 (Cardinality)**：
  在國際標準（Base FHIR）中，許多欄位是選填的；但在台灣的 TW Core 實作指引中被列為**最少填寫 1 個 (1..*) 的必填欄位**。
  * *例如*：Base FHIR 的 `Observation.category`（檢驗類別）為選填；但在台灣 `Observation-laboratoryResult-twcore` 規範中，規定必須至少填寫一個包含 `laboratory` 的代碼。加載此套件才能觸發這些本土必填規則。
* **臺灣專屬延伸欄位 (Extensions)**：
  驗證器能藉此核對臺灣特有的資料型態，例如：身分證字號、健保卡號、特定的福利身份等延伸欄位是否合乎格式。
* **資料結構切片 (Slicing)**：
  驗證器會根據套件定義，對特定陣列資料進行切片比對（例如確認 Identifier 陣列中，哪一個是身分證號，哪一個是病歷號）。

### 2.3 載入臺灣在地術語與編碼系統 (Terminology Mapping)
* 套件內建了臺灣衛福部與中央健康保險署所發佈的專門術語代碼系統（CodeSystems）與值集（ValueSets），包含：
  * **健保用藥品項代碼**
  * **ICD-10-CM 臺灣臨床修訂版診斷代碼**
  * **臺灣健保特約醫療機構代碼** 等。
* 若不加載此參數，當驗證器遇到本國特有的藥物代碼（如 Entecavir 的 `AA57786100`）時，會因國際庫查無此代碼而拋出 `Unknown code` (未知代碼) 錯誤而無法通過驗證。

---

## 3. 邏輯識別碼 (Canonical URL) 與 實體網頁網址 (Web URL) 的區分

在 FHIR 規格中，許多看似為網址的欄位，其用途與一般瀏覽器網址有本質上的不同：

### 3.1 邏輯識別碼 (Canonical URL) —— 給電腦看的 Namespace
* **定義**：在 FHIR JSON 檔案（例如 `coding.system` 欄位）中填寫的 URL，主要是作為**全域唯一的邏輯命名空間識別碼**。
* **特性**：它本質上是一個 **Key (識別字串)**。驗證器會直接拿這個字串在本地快取套件中進行檢索，**並不會真的發送 HTTP 請求去連線這個網址**。因此，這些網址在瀏覽器中直接開啟時，通常會顯示網頁不存在（404）。

### 3.2 實體網頁網址 (Web URL) —— 給人類看的說明網頁
* **定義**：HL7 Taiwan 官方提供供人類閱讀的實體規格說明與對照網頁，其網址命名格式與邏輯識別碼略有不同。

### 3.3 常用臺灣核心編碼網址對照表

| 術語系統 (CodeSystem) | 邏輯識別碼 (Canonical URL)<br>*(填寫於 JSON 資料中)* | 實體說明網頁 (Web URL)<br>*(可用瀏覽器直接開啟)* |
| :--- | :--- | :--- |
| **健保用藥品項代碼** | `https://twcore.mohw.gov.tw/ig/twcore/CodeSystem/medication-nhi-tw` | [官方網頁](https://twcore.mohw.gov.tw/ig/twcore/CodeSystem-medication-nhi-tw.html) |
| **ICD-10-CM 2021 診斷代碼** | `https://twcore.mohw.gov.tw/ig/twcore/CodeSystem/icd-10-cm-2021-tw` | [官方網頁](https://twcore.mohw.gov.tw/ig/twcore/CodeSystem-icd-10-cm-2021-tw.html) |
| **ICD-10-CM 2023 診斷代碼** | `https://twcore.mohw.gov.tw/ig/twcore/CodeSystem/icd-10-cm-2023-tw` | [官方網頁](https://twcore.mohw.gov.tw/ig/twcore/CodeSystem-icd-10-cm-2023-tw.html) |
| **LOINC 臺灣版檢驗項目碼** | `https://twcore.mohw.gov.tw/ig/twcore/CodeSystem/loinc-tw` | [官方網頁](https://twcore.mohw.gov.tw/ig/twcore/CodeSystem-loinc-tw.html) |

---

## 4. 臨床部署與完美檢驗對策

在臺灣本地醫療環境部署「主權健康代理人」時，要達成 100% 完美檢驗通過，必須採取以下**雙軌對合**步驟：

1. **資料層面綁定與轉換**：
   產出的資源 JSON 必須宣告對應的 TW Core Profile，且處方藥物不使用國際 RxNorm，而是改用健保署官方的「健保用藥品項代碼」。
2. **指定臺灣本地術語伺服器 (解決中文語系 Bug)**：
   若使用國際術語伺服器 (`tx.fhir.org`)，在 `zh_TW` 語系環境下會因為國際伺服器的中文對照資料庫受污染（例如將恩替卡韋錯誤翻譯為感冒藥），導致合規代碼被判定為 Display Name 錯誤。
   * **解決方案**：
     在執行 Java Validator 時，除了加載 `-ig tw.gov.mohw.twcore`，必須額外使用 `-tx` 參數指定臺灣本地建置的 FHIR Terminology 伺服器（例如衛福部官方伺服器），提供校正後的中文對照，即可達成 100% 完美通過驗證。
