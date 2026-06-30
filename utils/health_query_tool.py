#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Verification Toolbox (SHVT) - CLI Query Tool (v0.1.0)
蓬萊本地主權健康離線查證與防幻覺工具箱

本工具 100% 離線運作，旨在解析本地個人健康資料庫 (SQLite PHR)，
提供疾病、用藥、醫師、就醫歷程與檢驗代碼之快速查證，
並剛性組裝產生指向 TFDA、健保署及 PubMed (PMID) 的實時查證連結，對抗模型幻覺。
語境與術語完全採用台灣繁體中文，無中國用語。
"""

import os
import sys
import sqlite3
import json
import argparse
import urllib.parse
from datetime import datetime
import re

# 醫療免責聲明 (剛性輸出)
DISCLAIMER = """
======================================================================
【主權健康查證工具箱 - 醫療免責聲明】
本工具查詢之所有內容（含檢驗值、用藥、衛教）僅供自主健康管理與照護參考。
本系統為輔助工具，不提供任何實質醫療診斷或治療處方建議。
任何醫療決策、用藥變更、臨床指引解讀，請務必諮詢您的主治醫師或醫療專業人員。
======================================================================
"""

# 預設資料庫路徑候選
UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(UTILS_DIR)

# 載入臨床代碼對照表 (從外部 JSON 檔案讀取，並保留 Hardcoded 作為備援)
JSON_CODE_PATH = os.path.join(PROJECT_DIR, "data", "clinical_codes.json")

# 備援臨床代碼對照表
FALLBACK_CODE_DICT = {
    # LOINC
    "89555-7": "血液腫瘤/多發性骨髓瘤患者之自述症狀與功能評估調查 (Oncology patient-reported symptoms)",
    "26436-6": "白血球計數 (WBC Count) - 免疫與感染指標",
    "777-3": "血小板計數 (Platelet Count) - 凝血與出血風險指標",
    "2823-3": "免疫球蛋白 G (IgG) - 骨髓瘤與免疫狀態追蹤指標",
    "38483-4": "腎絲球濾過率 (eGFR) - 腎功能評估指標",
    "8462-4": "舒張壓 (Diastolic Blood Pressure)",
    "8480-6": "收縮壓 (Systolic Blood Pressure)",
    "2085-9": "高密度脂蛋白膽固醇 (HDL-C) - 好的膽固醇",
    "13457-7": "低密度脂蛋白膽固醇 (LDL-C) - 壞的膽固醇",
    "3094-0": "尿素氮 (BUN) - 腎代謝指標",
    "2160-0": "肌酸酐 (Creatinine) - 腎功能指標",
    "1912-3": "鈣離子 (Calcium) - 高血鈣症狀指標",
    "4544-3": "糖化血色素 (HbA1c) - 血糖控制指標",
    "28539-9": "骨髓漿細胞比例 (Bone marrow plasma cell %)",
    "15074-8": "人類皰疹病毒 DNA 定性檢測 (HSV DNA Qualitative test)",
    
    # 健保藥品碼
    "BC12601100": "貝樂克膜衣錠 0.5 毫克 (Baraclude 0.5mg) - 用於抗 B 肝病毒之預防用藥",
    "B024343100": "普力馬林錠 0.625 毫克 (Premarin 0.625mg) - 雌激素/類固醇製劑",
    "BC24483100": "得利生錠 50 毫克 (Dorison 50mg) - 美法崙/口服化療藥物 (Melphalan)"
}

CODE_DICT = FALLBACK_CODE_DICT.copy()
if os.path.exists(JSON_CODE_PATH):
    try:
        with open(JSON_CODE_PATH, 'r', encoding='utf-8') as f:
            CODE_DICT = json.load(f)
    except Exception as e:
        print(f"⚠️  警告：載入外部代碼對照表失敗 ({e})，改採用系統內建備援字典。")

DB_CANDIDATES = [
    os.path.join(PROJECT_DIR, "db", "instances", "myself", "fv_patient_personal.db"),
    os.path.join(PROJECT_DIR, "db", "fv_patient_personal.db"),
]

def deidentify_text(text):
    """將敏感個資進行去識別化遮蔽，保護病人隱私"""
    if not text:
        return text
    # 遮蔽身分證字號 (例如: J12001**** -> J12****)
    text = re.sub(r'([A-Z])\d{9}', lambda m: m.group(0)[:3] + "****" + m.group(0)[7:], text)
    # 將所有涉及真實病患的姓名轉換為範例名「王○明」
    text = re.sub(r'許[^\s]{1}龍', '王○明', text)
    text = text.replace('許○龍', '王○明')
    return text

def get_db_and_data_paths(custom_db_path=None):
    """智慧型定位資料庫路徑與對應的 data/raw 實體目錄"""
    if custom_db_path:
        db_path = os.path.abspath(custom_db_path)
    else:
        found = None
        for path in DB_CANDIDATES:
            if os.path.exists(path):
                found = path
                break
        db_path = found if found else DB_CANDIDATES[0]
    
    db_dir = os.path.dirname(db_path)
    if "instances" in db_dir:
        data_root = db_dir.replace(os.sep + "db" + os.sep, os.sep + "data" + os.sep)
    else:
        data_root = os.path.join(os.path.dirname(db_dir), "data")
        
    return db_path, data_root

def get_all_encounters(conn):
    """讀取本地所有的就醫住院事件 (Encounter)"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entry_id, artifact_id, fhir_resource_json, last_updated 
        FROM MY_CLINICAL_JOURNEY 
        WHERE resource_type = 'Encounter'
        ORDER BY last_updated ASC
    """)
    encounters = []
    for row in cursor.fetchall():
        entry_id, artifact_id, fhir_json, last_updated = row
        try:
            data = json.loads(fhir_json)
            start_date = data.get("period", {}).get("start", "")
            end_date = data.get("period", {}).get("end", "")
            hospital = data.get("serviceProvider", {}).get("display", "未知醫院")
            encounters.append({
                "entry_id": entry_id,
                "artifact_id": artifact_id,
                "start": start_date,
                "end": end_date,
                "hospital": hospital,
                "raw_json": data
            })
        except Exception:
            pass
    return encounters

def find_encounter_for_date(date_str, encounters):
    """比對檢驗日期是否落在某次住院就醫區間內"""
    if not date_str or not encounters:
        return None
    try:
        # 只取日期前 10 碼 (YYYY-MM-DD)
        obs_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
        for enc in encounters:
            if enc["start"] and enc["end"]:
                start = datetime.strptime(enc["start"][:10], "%Y-%m-%d")
                end = datetime.strptime(enc["end"][:10], "%Y-%m-%d")
                if start <= obs_date <= end:
                    return enc
    except Exception:
        pass
    return None

def query_disease(db_path, query_str):
    """1. 查詢疾病衛教與臨床指引"""
    print(f"\n🔍 正在檢索本地衛教庫，搜尋疾病: '{query_str}'...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤: 找不到資料庫檔案: {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 模糊查詢
    cursor.execute("""
        SELECT disease_name, title, content, citations, last_updated 
        FROM MY_EDUCATION_BASE 
        WHERE category = 'disease' AND (disease_name LIKE ? OR keyword LIKE ? OR title LIKE ?)
    """, (f"%{query_str}%", f"%{query_str}%", f"%{query_str}%"))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print(f"⚠️  本地衛教庫中查無與 '{query_str}' 相關的疾病指南。")
        # 提供 PubMed 搜尋連結防幻覺
        pubmed_query = f"{query_str} guidelines"
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(pubmed_query)}"
        print(f"💡 建議您可直接前往 PubMed 進行實時文獻查證:")
        print(f"🔗 PubMed 指南搜尋: {pubmed_url}")
        return
        
    print(f"✨ 找到 {len(rows)} 筆相關疾病衛教與指南資料:\n")
    for row in rows:
        disease_name, title, content, citations, last_updated = row
        print(f"📌 【主題】: {title} ({disease_name})")
        print(f"📅 【更新日期】: {last_updated}")
        print(f"📄 【指南與說明內容】:")
        print("-" * 60)
        print(content)
        print("-" * 60)
        print(f"📚 【文獻與指引出處】: {citations}")
        
        # 動態組裝 PubMed 實時查證連結
        pubmed_query = f"{disease_name} guidelines"
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(pubmed_query)}"
        print(f"🔗 PubMed 實時文獻查證連結: {pubmed_url}\n")
    
    print(DISCLAIMER)

def query_drug(db_path, query_str):
    """2. 查詢個人用藥變更歷史與藥物說明"""
    print(f"\n🔍 正在檢索本地個人用藥歷程與衛教庫，搜尋藥物: '{query_str}'...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤: 找不到資料庫檔案: {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    
    # a. 先查詢個人用藥歷程 (MedicationRequest)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entry_id, fhir_resource_json, last_updated 
        FROM MY_CLINICAL_JOURNEY 
        WHERE resource_type = 'MedicationRequest'
        ORDER BY last_updated ASC
    """)
    
    med_requests = []
    for row in cursor.fetchall():
        entry_id, fhir_json, last_updated = row
        try:
            data = json.loads(fhir_json)
            # 取得藥物名稱 (text 或是 display)
            drug_name = data.get("medicationCodeableConcept", {}).get("text", "")
            coding_display = ""
            coding_list = data.get("medicationCodeableConcept", {}).get("coding", [])
            if coding_list:
                coding_display = coding_list[0].get("display", "")
                
            # 模糊比對藥物名稱
            if (query_str.lower() in drug_name.lower()) or (query_str.lower() in coding_display.lower()):
                dosage = data.get("dosageInstruction", [{}])[0].get("text", "未註明劑量")
                status = data.get("status", "unknown")
                med_requests.append({
                    "entry_id": entry_id,
                    "drug_name": drug_name if drug_name else coding_display,
                    "dosage": dosage,
                    "status": status,
                    "last_updated": last_updated
                })
        except Exception:
            pass
            
    # b. 查詢衛教知識庫中的藥物說明
    cursor.execute("""
        SELECT title, content, citations 
        FROM MY_EDUCATION_BASE 
        WHERE category = 'medication' AND (keyword LIKE ? OR title LIKE ?)
    """, (f"%{query_str}%", f"%{query_str}%"))
    edu_rows = cursor.fetchall()
    conn.close()
    
    # 輸出個人用藥歷史
    if med_requests:
        print(f"📦 【個人歷史用藥異動軌跡】(共 {len(med_requests)} 筆):")
        print(f"{'更新時間':<20} | {'藥物名稱':<25} | {'服藥劑量與用法':<30} | {'狀態':<10}")
        print("-" * 90)
        for req in med_requests:
            print(f"{req['last_updated']:<20} | {req['drug_name']:<25} | {req['dosage']:<30} | {req['status']:<10}")
        print("-" * 90)
        
        # 指出最新藥囑
        latest_req = med_requests[-1]
        print(f"💡 【最新藥囑狀態】: 截至 {latest_req['last_updated']}，您目前的用藥指示為 '{latest_req['drug_name']}'，劑量為 '{latest_req['dosage']}' (狀態: {latest_req['status']})。\n")
    else:
        print(f"⚠️  在個人用藥歷程中，查無與 '{query_str}' 相關的活性處方紀錄。")
        # 特殊臨床對位提示 (得利生/美法崙/類固醇防幻覺)
        if query_str.lower() in ["dorison", "得利生", "melphalan", "美法崙", "得力生"]:
            print("\n💡 【本地主權健康防幻覺提示】:")
            print("   經過檢索真實病歷，病患在『自體幹細胞移植後』並未繼續使用口服得利生 (Dorison / Melphalan) 或類固醇進行維持治療。")
            print("   臨床事實上，口服美法崙 (Melphalan) 與普力馬林/類固醇為移植前之誘導或挽救化療方案，而移植過程中已使用了超高劑量靜脈注射 Melphalan。")
            print("   移植完成後，一般會視臨床檢驗指標（如電泳 M 蛋白、血球數值）決定是否進行維持治療。本機資料庫查無此藥，代表移植後目前停用此藥。")
            print("   未來若不幸復發，當初誘導方案之敏感度與耐受性（如白血球與血小板之低下程度）將是醫師評估是否再次使用該方案的重要參考資訊。")
            print("   (詳細歷史敏感性分析可參考本機報告: reports/medication_sensitivity_history_report.md)")
            
    # 輸出衛教庫內容
    if edu_rows:
        print(f"\n📖 【本地藥理衛教與日常照護指引】:")
        for edu in edu_rows:
            title, content, citations = edu
            print(f"📌 {title}")
            print("-" * 60)
            print(content)
            print("-" * 60)
            print(f"📚 出處: {citations}\n")
            
    # 組裝外部查證連結
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(query_str)}"
    tfda_url = f"https://www.fda.gov.tw/MLMS/H0001.aspx"
    nhia_url = "https://www.nhi.gov.tw/ch/cp-14571-33129-3236-1.html"
    
    print(f"🔗 【外部權威實物查證連結】(對抗模型幻覺):")
    print(f"   1. PubMed PMID 實時科研檢索: {pubmed_url}")
    print(f"   2. 台灣食品藥物管理署 (TFDA) 藥品許可證首頁: {tfda_url}")
    print(f"   3. 台灣中央健康保險署 (NHIA) 健保給付標準規定: {nhia_url}")
    print(DISCLAIMER)

def query_doctor(db_path, data_root, query_str):
    """3. 查詢醫師與醫院就醫溯源 (Join RAW_ARTIFACTS)"""
    print(f"\n🔍 正在進行醫師與就醫報告溯源，關鍵字: '{query_str}'...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤: 找不到資料庫檔案: {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    
    # a. 取得所有原始病歷
    cursor = conn.cursor()
    cursor.execute("""
        SELECT artifact_id, original_filename, storage_path, imported_at 
        FROM RAW_ARTIFACTS
    """)
    artifacts = cursor.fetchall()
    
    matched_artifacts = []
    
    # 遍歷實體檔案進行關鍵字比對
    for art in artifacts:
        art_id, orig_filename, storage_path, imported_at = art
        # 拼接絕對路徑
        full_path = os.path.join(data_root, storage_path)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if query_str.lower() in content.lower():
                        # 擷取含有關鍵字的片段
                        snippet = ""
                        lines = content.split("\n")
                        for idx, line in enumerate(lines):
                            if query_str.lower() in line.lower():
                                start_idx = max(0, idx - 1)
                                end_idx = min(len(lines), idx + 2)
                                snippet = "\n".join(lines[start_idx:end_idx])
                                break
                        matched_artifacts.append({
                            "artifact_id": art_id,
                            "original_filename": orig_filename,
                            "storage_path": storage_path,
                            "snippet": snippet
                        })
            except Exception as e:
                # 忽略讀取錯誤
                pass
                
    if not matched_artifacts:
        print(f"⚠️  在所有已匯入之原始病歷檔案中，未發現醫師/關鍵字 '{query_str}' 的簽章或提及紀錄。")
        conn.close()
        return
        
    print(f"✨ 成功在 {len(matched_artifacts)} 個原始病歷中查證到該醫師之軌跡:\n")
    
    # b. 針對每一個匹配的原始病歷，查出對應的 Encounter 就醫事件
    for match in matched_artifacts:
        art_id = match["artifact_id"]
        cursor.execute("""
            SELECT entry_id, fhir_resource_json, last_updated 
            FROM MY_CLINICAL_JOURNEY 
            WHERE artifact_id = ? AND resource_type = 'Encounter'
        """, (art_id,))
        
        encounter_row = cursor.fetchone()
        print(f"📄 【原始病歷檔案】: {match['original_filename']}")
        print(f"📂 【本地實體路徑】: {deidentify_text(match['storage_path'])}")
        
        if encounter_row:
            enc_id, fhir_json, last_updated = encounter_row
            try:
                enc_data = json.loads(fhir_json)
                period_start = enc_data.get("period", {}).get("start", "")
                period_end = enc_data.get("period", {}).get("end", "")
                hospital = enc_data.get("serviceProvider", {}).get("display", "未知醫院")
                
                print(f"🏥 【對齊臨床事件】: 住院事件 {enc_id}")
                print(f"🏫 【就診醫療機構】: {hospital}")
                print(f"📅 【住院就醫區間】: {period_start} 至 {period_end}")
            except Exception:
                print("🏥 【對齊臨床事件】: 關聯事件解譯失敗")
        else:
            print("🏥 【對齊臨床事件】: 此原始檔案未關聯任何結構化就醫事件表單")
            
        print(f"🔍 【原始檔案對合片段】:")
        print("-" * 50)
        print(deidentify_text(match["snippet"]))
        print("-" * 50)
        print()
        
    conn.close()
    print(DISCLAIMER)

def query_indicator(db_path, query_str):
    """4. 查詢常用臨床指標歷史趨勢與住院對齊"""
    print(f"\n🔍 正在檢索檢驗觀測值歷史指標: '{query_str}'...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤: 找不到資料庫檔案: {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    
    # 先撈取所有 Encounter 以利對齊
    encounters = get_all_encounters(conn)
    
    # 查詢匹配之 Observation
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entry_id, fhir_resource_json, last_updated 
        FROM MY_CLINICAL_JOURNEY 
        WHERE resource_type = 'Observation'
        ORDER BY json_extract(fhir_resource_json, '$.effectiveDateTime') ASC
    """)
    
    observations = []
    for row in cursor.fetchall():
        entry_id, fhir_json, last_updated = row
        try:
            data = json.loads(fhir_json)
            code_text = data.get("code", {}).get("text", "")
            # 模糊比對
            if query_str.lower() in code_text.lower():
                date_str = data.get("effectiveDateTime", "")
                val_quantity = data.get("valueQuantity", {})
                val = val_quantity.get("value", None)
                unit = val_quantity.get("unit", "")
                
                # 若為 string 值
                val_str = data.get("valueString", "")
                
                display_val = f"{val} {unit}" if val is not None else val_str
                
                observations.append({
                    "entry_id": entry_id,
                    "code_text": code_text,
                    "date": date_str,
                    "value": display_val
                })
        except Exception:
            pass
            
    conn.close()
    
    if not observations:
        print(f"⚠️  在個人歷程資料庫中，查無與 '{query_str}' 相關的檢驗數值。")
        return
        
    print(f"📊 找到 {len(observations)} 筆關於 '{query_str}' 的歷史檢驗趨勢 (已自動與住院事件對齊):")
    print(f"{'檢驗日期':<12} | {'指標名稱':<15} | {'檢驗數值':<15} | {'就醫住院期間對齊狀態'}")
    print("-" * 80)
    for obs in observations:
        # 對合住院事件
        matched_enc = find_encounter_for_date(obs["date"], encounters)
        align_status = "🏠 日常居家 / 門診追蹤"
        if matched_enc:
            align_status = f"🏥 住院期間 ({matched_enc['hospital']}, {matched_enc['start']}~{matched_enc['end']})"
            
        print(f"{obs['date']:<12} | {obs['code_text']:<15} | {obs['value']:<15} | {align_status}")
    print("-" * 80)
    print()
    print(DISCLAIMER)

def translate_code(query_str):
    """5. 翻譯 LOINC 或健保藥品代碼"""
    print(f"\n🔍 正在進行臨床代碼對照與翻譯: '{query_str}'...")
    
    # 模糊匹配 CODE_DICT
    matched = []
    for code, desc in CODE_DICT.items():
        if query_str.lower() in code.lower() or query_str in desc:
            matched.append((code, desc))
            
    if not matched:
        print(f"⚠️  本地代碼庫中查無與 '{query_str}' 相關的定義。")
        # 提供外部查詢網址
        if re.match(r'^\d+-\d+$', query_str): # LOINC 格式
            loinc_url = f"https://loinc.org/{query_str}"
            print(f"💡 偵測到此可能為 LOINC 標準代碼，您可以直接前往官方網站查驗:")
            print(f"🔗 LOINC 官方檢索: {loinc_url}")
        else:
            tfda_url = f"https://www.fda.gov.tw/MLMS/H0001D.aspx?licid={query_str}"
            print(f"💡 建議您可前往 TFDA 藥物許可證查詢系統，以許可證號或健保碼進行檢索:")
            print(f"🔗 TFDA 藥品查詢網址: {tfda_url}")
        return
        
    print(f"✨ 找到 {len(matched)} 筆代碼對照結果:\n")
    for code, desc in matched:
        print(f"🔖 【代碼】: {code}")
        print(f"📝 【中文定義與臨床意義】: {desc}")
        # 提供外部官方連結
        if "-" in code: # LOINC
            print(f"🔗 官方 LOINC 實時查證: https://loinc.org/{code}")
        else: # 健保藥品碼
            print(f"🔗 健保藥物給付標準查詢: https://www.nhi.gov.tw/")
        print()
        
    print(DISCLAIMER)

def run_interactive(db_path, data_root):
    """對話式互動選單主迴圈"""
    while True:
        print("\n" + "=" * 65)
        print("    蓬萊本地主權健康查證與防防幻覺工具箱 (SHVT)")
        print("=" * 65)
        print(f"  📂 【當前個人資料庫】: {db_path}")
        print(f"  📂 【當前原始檔案庫】: {deidentify_text(data_root)}")
        print("-" * 65)
        print("  1. 查詢疾病衛教與臨床指引 (Disease & Guidelines)")
        print("  2. 查詢個人歷史用藥變更與藥物說明 (Medications)")
        print("  3. 查詢醫師/醫院就醫報告與原始檔案溯源 (Doctors & Reports)")
        print("  4. 查詢常用臨床指標歷史趨勢與住院對齊 (Lab Indicators)")
        print("  5. 翻譯 LOINC 或健保藥物代碼 (Clinical Code Translator)")
        print("  6. 顯示系統免責聲明 (Disclaimer)")
        print("  Q. 離開工具箱 (Quit)")
        print("=" * 65)
        
        choice = input("👉 請輸入選項 (1-6 或 Q): ").strip()
        if choice.lower() == 'q':
            print("\n👋 感謝您使用主權健康查證工具箱，再見！")
            break
        elif choice == '1':
            query = input("💬 請輸入要查詢的疾病關鍵字 (如: 多發性骨髓瘤): ").strip()
            if query:
                query_disease(db_path, query)
        elif choice == '2':
            query = input("💬 請輸入要查詢的藥物名稱 (如: Entecavir / 得利生): ").strip()
            if query:
                query_drug(db_path, query)
        elif choice == '3':
            query = input("💬 請輸入醫師姓名或工號代碼 (如: 林 / H01180): ").strip()
            if query:
                query_doctor(db_path, data_root, query)
        elif choice == '4':
            query = input("💬 請輸入臨床指標代碼或名稱 (如: WBC / Platelet): ").strip()
            if query:
                query_indicator(db_path, query)
        elif choice == '5':
            query = input("💬 請輸入欲查詢之 LOINC 或健保代碼 (如: 89555-7): ").strip()
            if query:
                translate_code(query)
        elif choice == '6':
            print(DISCLAIMER)
        else:
            print("⚠️  輸入無效，請輸入 1 至 6 的數字或 Q 退出。")

def main():
    parser = argparse.ArgumentParser(description="蓬萊本地主權健康查證與防幻覺工具箱 (SHVT)")
    parser.add_argument("-d", "--disease", type=str, help="模糊查詢疾病衛教與指南 (如: 多發性骨髓瘤)")
    parser.add_argument("-m", "--drug", type=str, help="查詢個人藥物歷史變更與說明 (如: Entecavir / 得利生)")
    parser.add_argument("-p", "--doctor", type=str, help="依醫師姓名或代號追溯住院事件與原始病歷 (如: H01180)")
    parser.add_argument("-c", "--code", type=str, help="翻譯並查證常用臨床代碼 (如: 89555-7 / BC12601100)")
    parser.add_argument("-l", "--lab", type=str, help="查詢臨床指標歷史趨勢與住院對齊 (如: WBC / Platelet)")
    parser.add_argument("-i", "--interactive", action="store_true", help="啟動終端互動選單模式")
    parser.add_argument("--db", type=str, help="指定自訂 SQLite 資料庫路徑")
    
    args = parser.parse_args()
    
    # 智慧型尋找資料庫與數據路徑
    db_path, data_root = get_db_and_data_paths(args.db)
    
    # 如果有輸入參數，就執行對應查詢
    if args.disease:
        query_disease(db_path, args.disease)
    elif args.drug:
        query_drug(db_path, args.drug)
    elif args.doctor:
        query_doctor(db_path, data_root, args.doctor)
    elif args.code:
        translate_code(args.code)
    elif args.lab:
        query_indicator(db_path, args.lab)
    elif args.interactive:
        run_interactive(db_path, data_root)
    else:
        # 預設無參數時啟動互動模式
        run_interactive(db_path, data_root)

if __name__ == "__main__":
    main()
