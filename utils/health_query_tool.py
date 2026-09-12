#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[metadata]
name: health_query_tool.py
title: 蓬萊本地主權健康查證與防幻覺工具箱 (SHVT) (CGS v2.4)
description: 100% 離線運作，解析本地個人健康資料庫 (SQLite PHR)，提供疾病衛教、用藥異動、醫師報告、檢驗指標與代碼翻譯之快速查證，支援 Pipeline-Native 與 tw-med-db 融合。
category: healthcare_verification
spec: @sovereign-health-agent/specs/health_query_tool.spec.md
manual: @sovereign-health-agent/manuals/health_query_tool.md
bman: bman_sha_book:ch09
seman: seman_sha_sys_eng:02
dependencies: none
cgs_version: 2.4
"""

import os
import sys
import sqlite3
import json
import argparse
import urllib.parse
from datetime import datetime
import re
from typing import Optional, Dict, Any, List, Tuple

# 顯式宣告 CGS 規格版號
__cli_spec_version__ = "2.4"

# 跨平台 (Windows Console) UTF-8 強制編碼保護
if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# 匯入 tw-med-db 邊界適配器 (具備開關與平滑降級)
try:
    from utils.tw_med_bridge import get_med_bridge
except ImportError:
    try:
        from tw_med_bridge import get_med_bridge
    except ImportError:
        get_med_bridge = None

# 醫療免責聲明 (剛性輸出)
DISCLAIMER = """======================================================================
【主權健康查證工具箱 - 醫療免責聲明】
本工具查詢之所有內容（含檢驗值、用藥、衛教）僅供自主健康管理與照護參考。
本系統為輔助工具，不提供任何實質醫療診斷或治療處方建議。
任何醫療決策、用藥變更、臨床指引解讀，請務必諮詢您的主治醫師或醫療專業人員。
======================================================================"""

# 專案路徑解析
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
MANUAL_PATH = os.path.join(PROJECT_DIR, "manuals", "health_query_tool.md")
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
    except Exception:
        pass

DB_CANDIDATES = [
    os.path.join(PROJECT_DIR, "db", "instances", "myself", "fv_patient_personal.db"),
    os.path.join(PROJECT_DIR, "db", "fv_patient_personal.db"),
]

def log_msg(msg: str, level: str = "INFO"):
    """標準結構化日誌輸出至 stderr (符合 CGS v2.4 規範)"""
    prefix = {"INFO": "ℹ️ [INFO]", "WARN": "⚠️ [WARN]", "ERROR": "❌ [ERROR]", "DEBUG": "🔍 [DEBUG]"}.get(level, "[INFO]")
    sys.stderr.write(f"{prefix} {msg}\n")
    sys.stderr.flush()

def deidentify_text(text: str) -> str:
    """將敏感個資進行去識別化遮蔽，保護病人隱私"""
    if not text:
        return text
    text = re.sub(r'([A-Z])\d{9}', lambda m: m.group(0)[:3] + "****" + m.group(0)[7:], text)
    text = re.sub(r'許[^\s]{1}龍', '王○明', text)
    text = text.replace('許○龍', '王○明')
    return text

def get_db_and_data_paths(custom_db_path: Optional[str] = None) -> Tuple[str, str]:
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

def get_all_encounters(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
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

def find_encounter_for_date(date_str: str, encounters: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """比對檢驗日期是否落在某次住院就醫區間內"""
    if not date_str or not encounters:
        return None
    try:
        obs_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
        for enc in encounters:
            if enc.get("start") and enc.get("end"):
                start = datetime.strptime(enc["start"][:10], "%Y-%m-%d")
                end = datetime.strptime(enc["end"][:10], "%Y-%m-%d")
                if start <= obs_date <= end:
                    return enc
    except Exception:
        pass
    return None

# ==========================================
# 核心資料查詢函式 (純資料回傳，解耦 CLI 呈現)
# ==========================================

def get_disease_data(db_path: str, query_str: str) -> List[Dict[str, Any]]:
    """查詢疾病衛教與臨床指引數據"""
    if not query_str or not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT disease_name, title, content, citations, last_updated 
        FROM MY_EDUCATION_BASE 
        WHERE category = 'disease' AND (disease_name LIKE ? OR keyword LIKE ? OR title LIKE ?)
    """, (f"%{query_str}%", f"%{query_str}%", f"%{query_str}%"))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        disease_name, title, content, citations, last_updated = r
        pubmed_query = f"{disease_name} guidelines"
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(pubmed_query)}"
        results.append({
            "disease_name": disease_name,
            "title": title,
            "content": content,
            "citations": citations,
            "last_updated": last_updated,
            "pubmed_url": pubmed_url
        })
    return results

def get_drug_data(db_path: str, query_str: str) -> Dict[str, Any]:
    """查詢個人用藥歷程、衛教說明與 tw-med-db 官方藥證融合"""
    if not query_str or not os.path.exists(db_path):
        return {"med_requests": [], "education": [], "tw_med_db": [], "links": {}}

    conn = sqlite3.connect(db_path)
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
            drug_name = data.get("medicationCodeableConcept", {}).get("text", "")
            coding_display = ""
            coding_list = data.get("medicationCodeableConcept", {}).get("coding", [])
            if coding_list:
                coding_display = coding_list[0].get("display", "")
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

    cursor.execute("""
        SELECT title, content, citations 
        FROM MY_EDUCATION_BASE 
        WHERE category = 'medication' AND (keyword LIKE ? OR title LIKE ?)
    """, (f"%{query_str}%", f"%{query_str}%"))
    edu_rows = []
    for r in cursor.fetchall():
        edu_rows.append({"title": r[0], "content": r[1], "citations": r[2]})
    conn.close()

    tw_med_results = []
    if get_med_bridge:
        bridge = get_med_bridge()
        if bridge.is_available():
            tw_med_results = bridge.search_drugs(query_str, limit=5)

    links = {
        "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(query_str)}",
        "tfda": "https://www.fda.gov.tw/MLMS/H0001.aspx",
        "nhi": "https://www.nhi.gov.tw/ch/cp-14571-33129-3236-1.html"
    }

    return {
        "query": query_str,
        "med_requests": med_requests,
        "education": edu_rows,
        "tw_med_db": tw_med_results,
        "links": links
    }

def get_doctor_data(db_path: str, data_root: str, query_str: str) -> List[Dict[str, Any]]:
    """查詢醫師與原始病歷溯源數據"""
    if not query_str or not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT artifact_id, original_filename, storage_path, imported_at 
        FROM RAW_ARTIFACTS
    """)
    artifacts = cursor.fetchall()
    results = []

    for art in artifacts:
        art_id, orig_filename, storage_path, imported_at = art
        full_path = os.path.join(data_root, storage_path)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if query_str.lower() in content.lower():
                        snippet = ""
                        lines = content.split("\n")
                        for idx, line in enumerate(lines):
                            if query_str.lower() in line.lower():
                                start_idx = max(0, idx - 1)
                                end_idx = min(len(lines), idx + 2)
                                snippet = "\n".join(lines[start_idx:end_idx])
                                break
                        
                        # 查關聯就醫事件
                        cursor.execute("""
                            SELECT entry_id, fhir_resource_json, last_updated 
                            FROM MY_CLINICAL_JOURNEY 
                            WHERE artifact_id = ? AND resource_type = 'Encounter'
                        """, (art_id,))
                        enc_row = cursor.fetchone()
                        enc_info = None
                        if enc_row:
                            try:
                                enc_data = json.loads(enc_row[1])
                                enc_info = {
                                    "entry_id": enc_row[0],
                                    "start": enc_data.get("period", {}).get("start", ""),
                                    "end": enc_data.get("period", {}).get("end", ""),
                                    "hospital": enc_data.get("serviceProvider", {}).get("display", "未知醫院")
                                }
                            except Exception:
                                pass

                        results.append({
                            "artifact_id": art_id,
                            "original_filename": orig_filename,
                            "storage_path": storage_path,
                            "snippet": snippet,
                            "encounter": enc_info
                        })
            except Exception:
                pass
    conn.close()
    return results

def get_lab_data(db_path: str, query_str: str) -> List[Dict[str, Any]]:
    """查詢常用臨床指標歷史趨勢與住院對齊數據"""
    if not query_str or not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    encounters = get_all_encounters(conn)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entry_id, fhir_resource_json, last_updated 
        FROM MY_CLINICAL_JOURNEY 
        WHERE resource_type = 'Observation'
        ORDER BY json_extract(fhir_resource_json, '$.effectiveDateTime') ASC
    """)
    results = []
    for row in cursor.fetchall():
        entry_id, fhir_json, last_updated = row
        try:
            data = json.loads(fhir_json)
            code_text = data.get("code", {}).get("text", "")
            if query_str.lower() in code_text.lower():
                date_str = data.get("effectiveDateTime", "")
                val_quantity = data.get("valueQuantity", {})
                val = val_quantity.get("value", None)
                unit = val_quantity.get("unit", "")
                val_str = data.get("valueString", "")
                display_val = f"{val} {unit}" if val is not None else val_str

                matched_enc = find_encounter_for_date(date_str, encounters)
                enc_summary = f"{matched_enc['hospital']} ({matched_enc['start']}~{matched_enc['end']})" if matched_enc else "日常門診/居家"

                results.append({
                    "entry_id": entry_id,
                    "code_text": code_text,
                    "date": date_str,
                    "value": display_val,
                    "aligned_encounter": enc_summary
                })
        except Exception:
            pass
    conn.close()
    return results

def get_code_data(query_str: str) -> Dict[str, Any]:
    """翻譯臨床代碼 (優先 tw-med-db，降級至本地字典)"""
    if not query_str:
        return {}
    
    # 優先嘗試 tw-med-db
    if get_med_bridge:
        bridge = get_med_bridge()
        if bridge.is_available():
            trans = bridge.translate_clinical_code(query_str)
            if trans:
                return trans

    # 降級至本地字典
    matched = []
    for code, desc in CODE_DICT.items():
        if query_str.lower() in code.lower() or query_str in desc:
            matched.append({"code": code, "definition": desc})
    
    if matched:
        return {
            "code": query_str,
            "type": "本地離線字典備援",
            "matches": matched,
            "source": "clinical_codes.json / fallback"
        }
    
    return {
        "code": query_str,
        "type": "未命中",
        "matches": [],
        "source": "none"
    }

# ==========================================
# 終端人類展示呈現 (相容原有格式)
# ==========================================

def display_disease(db_path: str, query_str: str):
    log_msg(f"正在檢索本地衛教庫，搜尋疾病: '{query_str}'...", "INFO")
    rows = get_disease_data(db_path, query_str)
    if not rows:
        sys.stdout.write(f"⚠️  本地衛教庫中查無與 '{query_str}' 相關的疾病指南。\n")
        pubmed_query = f"{query_str} guidelines"
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(pubmed_query)}"
        sys.stdout.write(f"💡 建議您可直接前往 PubMed 進行實時文獻查證:\n")
        sys.stdout.write(f"🔗 PubMed 指南搜尋: {pubmed_url}\n")
        return
    sys.stdout.write(f"✨ 找到 {len(rows)} 筆相關疾病衛教與指南資料:\n\n")
    for r in rows:
        sys.stdout.write(f"📌 【主題】: {r['title']} ({r['disease_name']})\n")
        sys.stdout.write(f"📅 【更新日期】: {r['last_updated']}\n")
        sys.stdout.write("📄 【指南與說明內容】:\n" + "-" * 60 + "\n")
        sys.stdout.write(f"{r['content']}\n" + "-" * 60 + "\n")
        sys.stdout.write(f"📚 【文獻與指引出處】: {r['citations']}\n")
        sys.stdout.write(f"🔗 PubMed 實時文獻查證連結: {r['pubmed_url']}\n\n")
    sys.stdout.write(DISCLAIMER + "\n")

def display_drug(db_path: str, query_str: str):
    log_msg(f"正在檢索本地個人用藥歷程與衛教庫，搜尋藥物: '{query_str}'...", "INFO")
    data = get_drug_data(db_path, query_str)
    med_requests = data["med_requests"]
    edu_rows = data["education"]
    db_drugs = data["tw_med_db"]

    if med_requests:
        sys.stdout.write(f"📦 【個人歷史用藥異動軌跡】(共 {len(med_requests)} 筆):\n")
        sys.stdout.write(f"{'更新時間':<20} | {'藥物名稱':<25} | {'服藥劑量與用法':<30} | {'狀態':<10}\n")
        sys.stdout.write("-" * 90 + "\n")
        for req in med_requests:
            sys.stdout.write(f"{req['last_updated']:<20} | {req['drug_name']:<25} | {req['dosage']:<30} | {req['status']:<10}\n")
        sys.stdout.write("-" * 90 + "\n")
        latest_req = med_requests[-1]
        sys.stdout.write(f"💡 【最新藥囑狀態】: 截至 {latest_req['last_updated']}，您目前的用藥指示為 '{latest_req['drug_name']}'，劑量為 '{latest_req['dosage']}' (狀態: {latest_req['status']})。\n\n")
    else:
        sys.stdout.write(f"⚠️  在個人用藥歷程中，查無與 '{query_str}' 相關的活性處方紀錄。\n")

    if edu_rows:
        sys.stdout.write(f"\n📚 【衛教庫收錄之藥物說明】(共 {len(edu_rows)} 筆):\n")
        for r in edu_rows:
            sys.stdout.write(f"📌 【藥物衛教】: {r['title']}\n")
            sys.stdout.write(f"📄 【說明內容】: {r['content']}\n")
            sys.stdout.write(f"📚 【文獻依據】: {r['citations']}\n")
            sys.stdout.write("-" * 50 + "\n")

    if db_drugs:
        sys.stdout.write(f"\n🇹🇼 【台灣醫療大數據庫 (tw-med-db) 官方藥證與健保核定】(共 {len(db_drugs)} 筆):\n")
        sys.stdout.write(f"{'健保代碼/許可證':<16} | {'中文藥名':<20} | {'英文藥名':<25} | {'健保價':<10}\n")
        sys.stdout.write("-" * 80 + "\n")
        for d in db_drugs:
            price_str = f"NT$ {d['nhi_price']}" if d.get('nhi_price') is not None else "自費/未核定"
            code_id = d.get('drug_code') or d.get('license_id') or "N/A"
            sys.stdout.write(f"{code_id:<16} | {d['trade_name_tw'][:18]:<20} | {d['trade_name_en'][:23]:<25} | {price_str:<10}\n")
            if d.get("ingredient_name"):
                sys.stdout.write(f"   🧬 主成分: {d['ingredient_name']}\n")
            if d.get("indications"):
                sys.stdout.write(f"   📋 適應症: {d['indications'][:80]}...\n")
            sys.stdout.write("-" * 80 + "\n")

    if not med_requests and not edu_rows and not db_drugs:
        sys.stdout.write(f"⚠️  查無任何與 '{query_str}' 相關的用藥記錄或官方資料。\n")
        return

    sys.stdout.write(f"🔗 【外部權威實物查證連結】(對抗模型幻覺):\n")
    sys.stdout.write(f"   1. PubMed PMID 實時科研檢索: {data['links']['pubmed']}\n")
    sys.stdout.write(f"   2. 台灣食品藥物管理署 (TFDA) 藥品許可證首頁: {data['links']['tfda']}\n")
    sys.stdout.write(f"   3. 台灣中央健康保險署 (NHIA) 健保給付標準規定: {data['links']['nhi']}\n")
    sys.stdout.write(DISCLAIMER + "\n")

def display_doctor(db_path: str, data_root: str, query_str: str):
    log_msg(f"正在進行醫師與就醫報告溯源，關鍵字: '{query_str}'...", "INFO")
    results = get_doctor_data(db_path, data_root, query_str)
    if not results:
        sys.stdout.write(f"⚠️  在所有已匯入之原始病歷檔案中，未發現醫師/關鍵字 '{query_str}' 的簽章或提及紀錄。\n")
        return
    sys.stdout.write(f"✨ 成功在 {len(results)} 個原始病歷中查證到該醫師之軌跡:\n\n")
    for m in results:
        sys.stdout.write(f"📄 【原始病歷檔案】: {m['original_filename']}\n")
        sys.stdout.write(f"📂 【本地實體路徑】: {deidentify_text(m['storage_path'])}\n")
        enc = m.get("encounter")
        if enc:
            sys.stdout.write(f"🏥 【對齊臨床事件】: 住院事件 {enc['entry_id']}\n")
            sys.stdout.write(f"🏫 【就診醫療機構】: {enc['hospital']}\n")
            sys.stdout.write(f"📅 【住院就醫區間】: {enc['start']} 至 {enc['end']}\n")
        else:
            sys.stdout.write("🏥 【對齊臨床事件】: 此原始檔案未關聯任何結構化就醫事件表單\n")
        sys.stdout.write("🔍 【原始檔案對合片段】:\n" + "-" * 50 + "\n")
        sys.stdout.write(deidentify_text(m["snippet"]) + "\n" + "-" * 50 + "\n\n")
    sys.stdout.write(DISCLAIMER + "\n")

def display_lab(db_path: str, query_str: str):
    log_msg(f"正在檢索檢驗觀測值歷史指標: '{query_str}'...", "INFO")
    observations = get_lab_data(db_path, query_str)
    if not observations:
        sys.stdout.write(f"⚠️  在個人歷程資料庫中，查無與 '{query_str}' 相關的檢驗數值。\n")
        return
    sys.stdout.write(f"📊 找到 {len(observations)} 筆關於 '{query_str}' 的歷史檢驗趨勢 (已自動與住院事件對齊):\n")
    sys.stdout.write(f"{'檢驗日期':<12} | {'指標名稱':<15} | {'檢驗數值':<15} | {'就醫住院期間對齊狀態'}\n")
    sys.stdout.write("-" * 80 + "\n")
    for obs in observations:
        sys.stdout.write(f"{obs['date']:<12} | {obs['code_text']:<15} | {obs['value']:<15} | {obs['aligned_encounter']}\n")
    sys.stdout.write("-" * 80 + "\n\n")
    sys.stdout.write(DISCLAIMER + "\n")

def display_code(query_str: str):
    log_msg(f"正在進行臨床代碼對照與翻譯: '{query_str}'...", "INFO")
    data = get_code_data(query_str)
    if not data or data.get("type") == "未命中":
        sys.stdout.write(f"⚠️  本地代碼庫中查無與 '{query_str}' 相關的定義。\n")
        if re.match(r'^\d+-\d+$', query_str):
            sys.stdout.write(f"💡 偵測到此可能為 LOINC 標準代碼，您可以直接前往官方網站查驗:\n🔗 LOINC 官方檢索: https://loinc.org/{query_str}\n")
        else:
            sys.stdout.write(f"💡 建議您可前往 TFDA 藥物許可證查詢系統進行檢索:\n🔗 TFDA 藥品查詢網址: https://www.fda.gov.tw/MLMS/H0001D.aspx?licid={query_str}\n")
        return
    
    if data.get("source", "").startswith("tw-med-db"):
        sys.stdout.write(f"✨ 成功從【{data['source']}】精確對照代碼:\n\n")
        sys.stdout.write(f"🔖 【代碼】: {data['code']}\n")
        sys.stdout.write(f"🏷  【類別】: {data['type']}\n")
        sys.stdout.write(f"📝 【標準名稱】: {data['title']}\n")
        sys.stdout.write(f"📋 【詳細說明】: {data['description']}\n")
    else:
        sys.stdout.write(f"✨ 找到 {len(data['matches'])} 筆代碼對照結果 (來源: 本地離線字典備援):\n\n")
        for m in data["matches"]:
            sys.stdout.write(f"🔖 【代碼】: {m['code']}\n")
            sys.stdout.write(f"📝 【中文定義與臨床意義】: {m['definition']}\n")
    sys.stdout.write("\n" + DISCLAIMER + "\n")

def display_status(db_path: str, data_root: str, as_json: bool = False, quiet: bool = False):
    """輸出當前連線狀態"""
    med_status = {"available": False, "status_message": "適配器未安裝", "db_path": None}
    if get_med_bridge:
        bridge = get_med_bridge()
        st = bridge.get_status()
        med_status = {
            "enabled": st.get("enabled", True),
            "available": bridge.is_available(),
            "status_message": st.get("status_message", ""),
            "db_path": bridge.db_path
        }

    status_obj = {
        "phr_db_path": db_path,
        "phr_db_exists": os.path.exists(db_path),
        "data_root": data_root,
        "tw_med_db": med_status
    }

    if as_json:
        sys.stdout.write(json.dumps(status_obj, ensure_ascii=False, separators=(',', ':')) + "\n")
        return
    if quiet:
        sys.stdout.write(f"{med_status['available']}\n")
        return

    sys.stdout.write("\n" + "=" * 65 + "\n")
    sys.stdout.write("    蓬萊本地主權健康查證與防幻覺工具箱 (SHVT) - 狀態診斷\n")
    sys.stdout.write("=" * 65 + "\n")
    sys.stdout.write(f"  📂 【個人資料庫】: {db_path} ({'存在' if os.path.exists(db_path) else '未找到'})\n")
    sys.stdout.write(f"  📂 【原始檔案庫】: {deidentify_text(data_root)}\n")
    if med_status["available"]:
        sys.stdout.write(f"  🇹🇼 【醫療大數據庫】: 🟢 已連線 (tw-med-db)\n")
        sys.stdout.write(f"      實體路徑: {med_status['db_path']}\n")
    else:
        sys.stdout.write(f"  🇹🇼 【醫療大數據庫】: ⚪ 未啟用/未連線 ({med_status['status_message']})\n")
    sys.stdout.write("=" * 65 + "\n\n")

def run_interactive(db_path: str, data_root: str):
    """對話式互動選單主迴圈"""
    while True:
        display_status(db_path, data_root)
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
            if query: display_disease(db_path, query)
        elif choice == '2':
            query = input("💬 請輸入要查詢的藥物名稱 (如: Entecavir / 得利生 / 萬科): ").strip()
            if query: display_drug(db_path, query)
        elif choice == '3':
            query = input("💬 請輸入醫師姓名或工號代碼 (如: 林 / H01180): ").strip()
            if query: display_doctor(db_path, data_root, query)
        elif choice == '4':
            query = input("💬 請輸入臨床指標代碼或名稱 (如: WBC / Platelet): ").strip()
            if query: display_lab(db_path, query)
        elif choice == '5':
            query = input("💬 請輸入欲查詢之 LOINC 或健保代碼 (如: 1001-2 / 89555-7 / BC12601100): ").strip()
            if query: display_code(query)
        elif choice == '6':
            print(DISCLAIMER)

def get_schema() -> Dict[str, Any]:
    """回傳自我描述 JSON Schema"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "HealthQueryToolSchema",
        "type": "object",
        "cgs_spec_version": __cli_spec_version__,
        "subcommands": {
            "disease": "查詢疾病衛教與臨床指引",
            "drug": "查詢個人歷史用藥變更與官方藥證",
            "doctor": "依醫師或代號追溯住院原始病歷",
            "lab": "查詢檢驗指標歷史趨勢與住院對齊",
            "code": "翻譯 LOINC 或健保臨床代碼",
            "status": "取得健康庫與醫療大數據連線態勢",
            "schema": "輸出 JSON Schema",
            "version": "輸出版本資訊"
        }
    }

def main():
    # 通用 parent parser 支援前置或後置 flags
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-j", "--json", action="store_true", help="啟用單行緊湊 JSON 格式輸出")
    parent_parser.add_argument("-q", "--quiet", action="store_true", help="極簡輸出模式")
    parent_parser.add_argument("--no-med-db", action="store_true", help="強制停用 tw-med-db (切換本地備援)")
    parent_parser.add_argument("--with-med-db", action="store_true", help="強制嘗試啟用 tw-med-db")
    parent_parser.add_argument("--db", type=str, help="指定自訂 SQLite 個人健康資料庫路徑")
    parent_parser.add_argument("--stdin", "-", dest="use_stdin", action="store_true", help="從標準輸入讀取查詢字串")

    # 舊有相容性旗標整合至頂層 parser
    parser = argparse.ArgumentParser(
        description="health_query_tool.py - 蓬萊本地主權健康查證工具箱 (SHVT) (CGS v2.4)",
        parents=[parent_parser],
        add_help=True
    )

    # 向後相容旗標 (Backward Compatible Flags)
    parser.add_argument("-d", "--disease-flag", type=str, help="模糊查詢疾病衛教與指南 (如: 多發性骨髓瘤)")
    parser.add_argument("-m", "--drug-flag", type=str, help="查詢個人藥物歷史變更與說明 (如: Entecavir)")
    parser.add_argument("-p", "--doctor-flag", type=str, help="依醫師姓名或代號追溯住院事件與病歷")
    parser.add_argument("-c", "--code-flag", type=str, help="翻譯並查證常用臨床代碼 (如: 89555-7)")
    parser.add_argument("-l", "--lab-flag", type=str, help="查詢臨床指標歷史趨勢 (如: WBC)")
    parser.add_argument("-i", "--interactive", action="store_true", help="啟動終端互動選單模式")
    parser.add_argument("--status", dest="status_flag", action="store_true", help="檢查並顯示資料庫診斷狀態")

    subparsers = parser.add_subparsers(dest="command", help="子命令清單")

    # 子命令宣告
    p_dis = subparsers.add_parser("disease", parents=[parent_parser], help="查詢疾病衛教與臨床指引")
    p_dis.add_argument("query", nargs="?", default="", help="疾病名稱或關鍵字")

    p_drug = subparsers.add_parser("drug", parents=[parent_parser], help="查詢個人用藥歷程與官方藥證")
    p_drug.add_argument("query", nargs="?", default="", help="藥物名稱")

    p_doc = subparsers.add_parser("doctor", parents=[parent_parser], help="醫師與住院報告溯源")
    p_doc.add_argument("query", nargs="?", default="", help="醫師姓名或工號")

    p_lab = subparsers.add_parser("lab", parents=[parent_parser], help="臨床指標歷史趨勢與就醫對齊")
    p_lab.add_argument("query", nargs="?", default="", help="指標代碼或名稱 (如 WBC)")

    p_code = subparsers.add_parser("code", parents=[parent_parser], help="翻譯臨床代碼 (LOINC 或健保碼)")
    p_code.add_argument("query", nargs="?", default="", help="代碼字串 (如 1001-2)")

    subparsers.add_parser("status", parents=[parent_parser], help="連線診斷狀態")
    subparsers.add_parser("schema", parents=[parent_parser], help="輸出 JSON Schema")
    subparsers.add_parser("version", parents=[parent_parser], help="輸出版本資訊")
    subparsers.add_parser("man", parents=[parent_parser], help="檢視說明手冊")
    subparsers.add_parser("manual", parents=[parent_parser], help="檢視說明手冊")

    args = parser.parse_args()

    # 處理 tw-med-db 旗標開關覆蓋
    if get_med_bridge:
        if args.no_med_db:
            get_med_bridge(force_enabled=False)
        elif args.with_med_db:
            get_med_bridge(force_enabled=True)

    db_path, data_root = get_db_and_data_paths(args.db)

    # 處理管道輸入
    stdin_data = ""
    if args.use_stdin or "-" in sys.argv:
        try:
            if not sys.stdin.isatty():
                stdin_data = sys.stdin.read().strip()
        except Exception:
            pass

    # 命令派發與向後向下相容映射
    cmd = args.command
    query_val = getattr(args, "query", "") or stdin_data

    # 向後相容旗標優先映射
    if args.status_flag:
        cmd = "status"
    elif args.disease_flag is not None:
        cmd = "disease"
        query_val = args.disease_flag if args.disease_flag != "-" else stdin_data
    elif args.drug_flag is not None:
        cmd = "drug"
        query_val = args.drug_flag if args.drug_flag != "-" else stdin_data
    elif args.doctor_flag is not None:
        cmd = "doctor"
        query_val = args.doctor_flag if args.doctor_flag != "-" else stdin_data
    elif args.code_flag is not None:
        cmd = "code"
        query_val = args.code_flag if args.code_flag != "-" else stdin_data
    elif args.lab_flag is not None:
        cmd = "lab"
        query_val = args.lab_flag if args.lab_flag != "-" else stdin_data
    elif args.interactive:
        run_interactive(db_path, data_root)
        return

    # 若無指定子命令且無特定旗標，預設行為
    if not cmd:
        if stdin_data:
            # 若有 pipe 輸入且未指定指令，預設以 code 翻譯
            cmd = "code"
            query_val = stdin_data
        else:
            run_interactive(db_path, data_root)
            return

    # 執行各項子命令
    if cmd == "status":
        display_status(db_path, data_root, as_json=args.json, quiet=args.quiet)

    elif cmd == "disease":
        if not query_val:
            log_msg("未提供疾病搜尋關鍵字", "WARN")
            return
        if args.json:
            data = get_disease_data(db_path, query_val)
            sys.stdout.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + "\n")
        elif args.quiet:
            for r in get_disease_data(db_path, query_val):
                sys.stdout.write(f"{r['disease_name']}\t{r['title']}\n")
        else:
            display_disease(db_path, query_val)

    elif cmd == "drug":
        if not query_val:
            log_msg("未提供藥物名稱", "WARN")
            return
        if args.json:
            data = get_drug_data(db_path, query_val)
            sys.stdout.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + "\n")
        elif args.quiet:
            data = get_drug_data(db_path, query_val)
            for req in data.get("med_requests", []):
                sys.stdout.write(f"{req['last_updated']}\t{req['drug_name']}\t{req['dosage']}\n")
        else:
            display_drug(db_path, query_val)

    elif cmd == "doctor":
        if not query_val:
            log_msg("未提供醫師姓名或代號", "WARN")
            return
        if args.json:
            data = get_doctor_data(db_path, data_root, query_val)
            sys.stdout.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + "\n")
        elif args.quiet:
            for m in get_doctor_data(db_path, data_root, query_val):
                sys.stdout.write(f"{m['artifact_id']}\t{m['original_filename']}\n")
        else:
            display_doctor(db_path, data_root, query_val)

    elif cmd == "lab":
        if not query_val:
            log_msg("未提供檢驗指標關鍵字", "WARN")
            return
        if args.json:
            data = get_lab_data(db_path, query_val)
            sys.stdout.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + "\n")
        elif args.quiet:
            for obs in get_lab_data(db_path, query_val):
                sys.stdout.write(f"{obs['date']}\t{obs['code_text']}\t{obs['value']}\n")
        else:
            display_lab(db_path, query_val)

    elif cmd == "code":
        if not query_val:
            log_msg("未提供代碼字串", "WARN")
            return
        if args.json:
            data = get_code_data(query_val)
            sys.stdout.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + "\n")
        elif args.quiet:
            data = get_code_data(query_val)
            title = data.get("title") or (data.get("matches", [{}])[0].get("definition", "") if data.get("matches") else "")
            sys.stdout.write(f"{data.get('code')}\t{title}\n")
        else:
            display_code(query_val)

    elif cmd == "schema":
        sys.stdout.write(json.dumps(get_schema(), ensure_ascii=False, indent=2) + "\n")

    elif cmd == "version":
        ver = {
            "script": "health_query_tool.py",
            "version": "1.0.0",
            "cgs_spec_version": __cli_spec_version__
        }
        if args.json:
            sys.stdout.write(json.dumps(ver, ensure_ascii=False) + "\n")
        else:
            sys.stdout.write(f"health_query_tool.py v1.0.0 (CGS v{__cli_spec_version__})\n")

    elif cmd in ["man", "manual"]:
        if os.path.exists(MANUAL_PATH):
            with open(MANUAL_PATH, "r", encoding="utf-8") as f:
                sys.stdout.write(f.read())
        else:
            log_msg(f"說明手冊不存在: {MANUAL_PATH}", "ERROR")

if __name__ == "__main__":
    main()
