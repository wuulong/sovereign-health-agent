#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 臨床試驗與多資料庫科研檢索 URL 產生器
功能：自動讀取本地資料庫之診斷與用藥，或透過命令列參數指定，透過 PICO 邏輯拼接多個國內外資料庫的最佳化檢索 URL。
"""

import os
import sys
import sqlite3
import urllib.parse
import argparse

# 台灣為預設搜尋地理限制 (GEMINI Memory Rule)
DEFAULT_LOCATION = "Taiwan"

# 常見疾病的英文同義詞對照表 (用於 PICO 檢索語法擴充)
DISEASE_SYNONYMS = {
    "多發性骨髓瘤": ["Multiple Myeloma", "Plasma Cell Myeloma", "Kahler Disease"],
    "大腸癌": ["Colorectal Neoplasm", "Colon Cancer", "Rectal Cancer"],
    "肺腺癌": ["Lung Adenocarcinoma", "Non-Small Cell Lung Cancer", "NSCLC"],
}

def get_patient_profile(db_path):
    """
    從資料庫讀取病患核心診斷與當前用藥資訊
    """
    if not db_path or not os.path.exists(db_path):
        # 若資料庫不存在，傳回預設測試值 (阿喜伯)
        return {
            "diagnoses": ["多發性骨髓瘤"],
            "medications": ["Daratumumab", "Bortezomib"],
            "location": DEFAULT_LOCATION
        }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 讀取診斷 (從 MY_CLINICAL_JOURNEY 中尋找 Condition 或 Observation 資源)
        cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Condition'")
        conditions = cursor.fetchall()
        
        diagnoses = []
        for cond_json in conditions:
            try:
                import json
                cond_data = json.loads(cond_json[0])
                diag_text = cond_data.get("code", {}).get("text", "")
                if diag_text:
                    diagnoses.append(diag_text)
            except Exception:
                pass

        # 讀取藥物
        cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'MedicationRequest'")
        meds = cursor.fetchall()
        medications = []
        for med_json in meds:
            try:
                import json
                med_data = json.loads(med_json[0])
                med_text = med_data.get("medicationCodeableConcept", {}).get("text", "")
                if med_text:
                    medications.append(med_text)
            except Exception:
                pass

        conn.close()
        
        # 去重
        diagnoses = list(set(diagnoses)) if diagnoses else ["多發性骨髓瘤"]
        medications = list(set(medications)) if medications else ["Daratumumab"]
        
        return {
            "diagnoses": diagnoses,
            "medications": medications,
            "location": DEFAULT_LOCATION
        }
    except Exception as e:
        print(f"【警告】讀取資料庫失敗: {e}，將使用預載測試資料。", file=sys.stderr)
        return {
            "diagnoses": ["多發性骨髓瘤"],
            "medications": ["Daratumumab", "Bortezomib"],
            "location": DEFAULT_LOCATION
        }

def build_clinical_trials_url(pico_p, pico_i, location):
    """
    拼接 ClinicalTrials.gov 的檢索 URL
    """
    # 擴充疾病同義詞
    p_terms = DISEASE_SYNONYMS.get(pico_p, [pico_p])
    p_query = " OR ".join([f'"{term}"' for term in p_terms])
    
    # 組裝搜尋關鍵字
    query_parts = [f"({p_query})"]
    if pico_i:
        query_parts.append(f'"{pico_i}"')
    
    query_string = " AND ".join(query_parts)
    
    params = {
        "cond": pico_p,
        "term": query_string,
        "locn": location,
        "distance": "50"
    }
    
    encoded_params = urllib.parse.urlencode(params)
    return f"https://clinicaltrials.gov/search?{encoded_params}"

def build_pubmed_url(pico_p, pico_i):
    """
    拼接 PubMed 的檢索 URL
    """
    p_terms = DISEASE_SYNONYMS.get(pico_p, [pico_p])
    p_query = " OR ".join([f'{term}[Title/Abstract]' for term in p_terms])
    
    query_parts = [f"({p_query})"]
    if pico_i:
        query_parts.append(f'"{pico_i}"[Title/Abstract]')
    
    # 限制在最近 5 年、人類研究、英文或中文
    query_parts.append('("last 5 years"[dp] AND "humans"[Mesh])')
    
    query_string = " AND ".join(query_parts)
    encoded_query = urllib.parse.quote_plus(query_string)
    
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={encoded_query}"

def build_google_scholar_url(pico_p, pico_i):
    """
    拼接 Google Scholar 的檢索 URL
    """
    p_terms = DISEASE_SYNONYMS.get(pico_p, [pico_p])
    p_query = " OR ".join([f'"{term}"' for term in p_terms])
    
    query_parts = [f"({p_query})"]
    if pico_i:
        query_parts.append(f'"{pico_i}"')
        
    query_string = " AND ".join(query_parts)
    encoded_query = urllib.parse.quote_plus(query_string)
    
    return f"https://scholar.google.com/scholar?q={encoded_query}"

def build_cochrane_url(pico_p, pico_i):
    """
    拼接 Cochrane Library 的檢索 URL
    """
    p_terms = DISEASE_SYNONYMS.get(pico_p, [pico_p])
    p_query = " OR ".join([f'"{term}"' for term in p_terms])
    
    query_parts = [f"({p_query})"]
    if pico_i:
        query_parts.append(f'"{pico_i}"')
        
    query_string = " AND ".join(query_parts)
    encoded_query = urllib.parse.quote_plus(query_string)
    
    return f"https://www.cochranelibrary.com/search?queryString={encoded_query}"

def print_taiwan_cde_guide(pico_p, pico_i):
    """
    印出台灣臨床試驗資訊平台 (CDE) 的檢索指引
    """
    print("\n[5-1] 台灣臨床試驗資訊平台 (Taiwan Clinical Trials)")
    print("👉 官方入口: https://www.taiwanclinicaltrials.tw")
    print(f"💡 搜尋建議: 請手動複製並在搜尋框輸入：'{pico_p}' 或 '{pico_i}'。若無結果，可嘗試英文名稱。")

def print_taiwan_fda_guide(pico_p, pico_i):
    """
    印出台灣藥品臨床試驗資訊網 (TFDA) 的檢索指引
    """
    print("\n[5-2] 台灣藥品臨床試驗資訊網 (TFDA)")
    print("👉 官方入口: https://e-sub.fda.gov.tw/ClinicalTrialInfo/home")
    print(f"💡 搜尋建議: 請在「適應症」欄位輸入：'{pico_p}'，或在「試驗藥物」欄位輸入：'{pico_i}'。")

def generate_search_links(db_path=None, disease=None, drug=None, location=None, dbs=None):
    """
    核心調度函數：整合參數，輸出指定之檢索連結與指引
    """
    if dbs is None:
        dbs = ["all"]
        
    # 如果 disease 或 drug 沒有完全指定，則嘗試讀取資料庫
    if not disease or not drug:
        patient_data = get_patient_profile(db_path)
        if not disease:
            disease = patient_data["diagnoses"][0]
        if not drug:
            drug = patient_data["medications"][0] if patient_data["medications"] else ""
            
    if not location:
        location = DEFAULT_LOCATION

    # 處理 dbs 的大小寫與格式
    dbs = [db.lower() for db in dbs]
    show_all = "all" in dbs

    print("=========================================")
    print(" 🌐 Sovereign Health Agent - 科研檢索輔助")
    print("=========================================")
    print(f"【PICO 定位】")
    print(f" - P (患者診斷): {disease}")
    print(f" - I (主要介入): {drug}")
    print(f" - 地理限制  : {location}")
    print("-----------------------------------------")
    
    # 1. ClinicalTrials.gov
    if show_all or "ct" in dbs:
        ct_url = build_clinical_trials_url(disease, drug, location)
        print("\n[1] ClinicalTrials.gov (尋找最新臨床試驗)")
        print(f"👉 搜尋連結:\n{ct_url}")
        
    # 2. PubMed
    if show_all or "pm" in dbs:
        pm_url = build_pubmed_url(disease, drug)
        print("\n[2] PubMed (尋找最近五年同儕審查文獻)")
        print(f"👉 搜尋連結:\n{pm_url}")
        
    # 3. Google Scholar
    if show_all or "gs" in dbs:
        gs_url = build_google_scholar_url(disease, drug)
        print("\n[3] Google Scholar (學術文獻搜尋)")
        print(f"👉 搜尋連結:\n{gs_url}")
        
    # 4. Cochrane Library
    if show_all or "cochrane" in dbs:
        cochrane_url = build_cochrane_url(disease, drug)
        print("\n[4] Cochrane Library (系統性文獻回顧)")
        print(f"👉 搜尋連結:\n{cochrane_url}")
        
    # 5. 台灣平台指引
    if show_all or "tw" in dbs:
        print_taiwan_cde_guide(disease, drug)
        print_taiwan_fda_guide(disease, drug)
        
    print("=========================================")

if __name__ == '__main__':
    # 取得預設 db路徑
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.abspath(os.path.join(script_dir, "..", "db", "fv_patient_personal.db"))

    
    # 命令列參數解析
    parser = argparse.ArgumentParser(description="Sovereign Health Agent (SHA) - 臨床試驗與多資料庫科研檢索 URL 產生器")
    parser.add_argument("-d", "--disease", type=str, help="指定疾病名稱 (例如：多發性骨髓瘤)")
    parser.add_argument("-i", "--drug", type=str, help="指定主要治療藥物/介入 (例如：Daratumumab)")
    parser.add_argument("-l", "--location", type=str, help=f"限制地理位置 (預設為 {DEFAULT_LOCATION})")
    parser.add_argument("-b", "--dbs", type=str, nargs="+", default=["all"], 
                        help="指定要查詢的資料庫，可選: ct (ClinicalTrials), pm (PubMed), gs (Google Scholar), cochrane (Cochrane Library), tw (台灣平台指引), all (預設)")
    parser.add_argument("--db-path", type=str, default=default_db, help="手動指定 SQLite 資料庫路徑")
    
    args = parser.parse_args()
    
    # 呼叫主函數
    generate_search_links(
        db_path=args.db_path,
        disease=args.disease,
        drug=args.drug,
        location=args.location,
        dbs=args.dbs
    )
