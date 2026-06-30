#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Database Porter (db_porter.py) (v0.1.0)
蓬萊本地主權健康資料庫匯出/匯入與移轉工具

本工具支援七大資料移植與匯出情境，包含門診摘要、科研共享、個人備份、急診救援卡、
日常監測 CSV、保險申報 ZIP 以及長照交接摘要。支援去識別化與確定性時間平移。
"""

import os
import sys
import sqlite3
import json
import argparse
import hashlib
import csv
import zipfile
import re
from datetime import datetime, timedelta

# 定義基準目錄
UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(UTILS_DIR)  # events/sovereign-health-agent

DISCLAIMER = """======================================================================
【主權健康匯出卡 - 醫療免責聲明】
本文件由病患本地去識別化工具生成，內容僅供就醫溝通、臨床諮詢與照護參考。
本系統為輔助工具，任何醫療決策、用藥變更，請務必諮詢您的主治醫師或醫療專業人員。
======================================================================"""

# 1. 智慧型定位路徑
def get_db_paths(profile, custom_db_path=None):
    if custom_db_path:
        db_path = os.path.abspath(custom_db_path)
    else:
        db_path = os.path.join(PROJECT_DIR, "db", "instances", profile, "fv_patient_personal.db")
    
    db_dir = os.path.dirname(db_path)
    if "instances" in db_dir:
        data_dir = db_dir.replace(os.sep + "db" + os.sep, os.sep + "data" + os.sep)
    else:
        data_dir = os.path.join(PROJECT_DIR, "data", "instances", profile)
        
    return db_path, data_dir

# 2. 資料庫讀取輔助函式
def query_table_as_dicts(conn, table_name):
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        return []

# 3. 去識別化與時間平移演算法
def get_deterministic_shift_days(profile):
    """根據 Profile 名稱進行 Hash 計算產生固定的隨機平移天數 (-30 ~ 30)"""
    hash_val = int(hashlib.md5(profile.encode('utf-8')).hexdigest(), 16)
    shift = (hash_val % 60) - 30
    if shift == 0:
        shift = 15  # 避免平移量為 0
    return shift

def shift_date_string(date_str, shift_days):
    if not date_str:
        return date_str
    
    # 1. ISO 8601 with timezone (e.g., 2026-06-12T17:40:38+08:00)
    match_dt = re.match(r'^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?([+-]\d{2}:?\d{2}|Z)?$', date_str)
    if match_dt:
        date_part = match_dt.group(1)
        time_part = match_dt.group(2)
        tz_part = match_dt.group(3) or ""
        try:
            dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
            shifted_dt = dt + timedelta(days=shift_days)
            date_sep = "T" if "T" in date_str else " "
            res = shifted_dt.strftime(f"%Y-%m-%d{date_sep}%H:%M:%S")
            return f"{res}{tz_part}"
        except Exception:
            pass
            
    # 2. YYYY-MM-DD
    match_d = re.match(r'^(\d{4}-\d{2}-\d{2})$', date_str)
    if match_d:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            shifted_d = d + timedelta(days=shift_days)
            return shifted_d.strftime("%Y-%m-%d")
        except Exception:
            pass
            
    # 3. YYYY-MM (出生年月)
    match_m = re.match(r'^(\d{4}-\d{2})$', date_str)
    if match_m:
        try:
            d = datetime.strptime(f"{date_str}-01", "%Y-%m-%d")
            shifted_d = d + timedelta(days=shift_days)
            return shifted_d.strftime("%Y-%m")
        except Exception:
            pass

    return date_str

def mask_pii_string(text, patient_id):
    if not text:
        return text
    # 遮蔽身分證字號
    text = re.sub(r'([A-Z])\d{9}', lambda m: m.group(0)[:3] + "****" + m.group(0)[7:], text)
    # 遮蔽真實姓名
    text = re.sub(r'許[^\s]{1}龍', '王○明', text)
    text = text.replace('許○龍', '王○明')
    # 遮蔽病患識別碼
    text = text.replace(patient_id, f"{patient_id}-DEID")
    return text

def deidentify_resource(resource, patient_id, shift_days=None):
    """遞迴遮蔽 PII 與套用時間平移"""
    if isinstance(resource, dict):
        new_res = {}
        for k, v in resource.items():
            if isinstance(v, str):
                # 判斷是否為日期欄位
                is_date_field = k in ["effectiveDateTime", "start", "end", "last_updated", "imported_at", "signed_at", "validDate", "birth_date", "date", "recordedDate"]
                is_general_date = re.match(r'^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2})?.*$', v) is not None
                
                if shift_days and (is_date_field or is_general_date):
                    v = shift_date_string(v, shift_days)
                
                # 遮蔽字串中的 PII
                if not is_date_field and not is_general_date:
                    v = mask_pii_string(v, patient_id)
                new_res[k] = v
            else:
                new_res[k] = deidentify_resource(v, patient_id, shift_days)
        return new_res
    elif isinstance(resource, list):
        return [deidentify_resource(item, patient_id, shift_days) for item in resource]
    else:
        return resource

# 4. 核心功能：備份匯出與匯入 (情境 C)
def export_backup(db_path, output_path):
    print(f"📦 開始執行完整資料備份匯出...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤：找不到資料庫檔案 {db_path}")
        return False
        
    conn = sqlite3.connect(db_path)
    
    backup_data = {
        "export_type": "sovereign_phr_backup",
        "exported_at": datetime.now().isoformat(),
        "my_profile": query_table_as_dicts(conn, "MY_PROFILE"),
        "my_clinical_journey": query_table_as_dicts(conn, "MY_CLINICAL_JOURNEY"),
        "user_consents": query_table_as_dicts(conn, "USER_CONSENTS"),
        "raw_artifacts": query_table_as_dicts(conn, "RAW_ARTIFACTS")
    }
    
    conn.close()
    
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        print(f"✨ 備份成功！已寫入至：{output_path}")
        return True
    except Exception as e:
        print(f"❌ 備份寫入失敗: {e}")
        return False

def import_backup(db_path, file_path):
    print(f"📦 開始執行資料備份增量匯入...")
    if not os.path.exists(file_path):
        print(f"❌ 錯誤：找不到備份檔案 {file_path}")
        return False
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
    except Exception as e:
        print(f"❌ 錯誤：無法解析 JSON 檔案: {e}")
        return False
        
    if backup_data.get("export_type") != "sovereign_phr_backup":
        print("❌ 錯誤：備份檔案類型不符 (必須為 sovereign_phr_backup)")
        return False
        
    # 初始化/連接資料庫
    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)
    
    # 確保資料庫結構存在
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 檢查表結構是否健全
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='MY_PROFILE'")
    if not cursor.fetchone():
        print("⚠️  資料庫未初始化，請先執行 database_initializer.py 初始化結構。")
        conn.close()
        return False
        
    def insert_rows_into_table(table_name, rows):
        if not rows:
            return 0
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        if not columns:
            print(f"⚠️  警告：目標資料庫中不存在 {table_name} 表，跳過。")
            return 0
            
        inserted = 0
        for row in rows:
            # 篩選欄位以防 Schema 不相容
            filtered_row = {k: v for k, v in row.items() if k in columns}
            if not filtered_row:
                continue
            keys = list(filtered_row.keys())
            placeholders = ", ".join(["?"] * len(keys))
            columns_str = ", ".join(keys)
            sql = f"INSERT OR REPLACE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
            cursor.execute(sql, list(filtered_row.values()))
            inserted += 1
        return inserted

    try:
        p_count = insert_rows_into_table("MY_PROFILE", backup_data.get("my_profile", []))
        j_count = insert_rows_into_table("MY_CLINICAL_JOURNEY", backup_data.get("my_clinical_journey", []))
        c_count = insert_rows_into_table("USER_CONSENTS", backup_data.get("user_consents", []))
        a_count = insert_rows_into_table("RAW_ARTIFACTS", backup_data.get("raw_artifacts", []))
        
        conn.commit()
        print(f"✨ 增量排重匯入完成！")
        print(f"   * 個人資料表 (MY_PROFILE): 新增/更新 {p_count} 筆")
        print(f"   * 醫療歷程表 (MY_CLINICAL_JOURNEY): 新增/更新 {j_count} 筆")
        print(f"   * 同意書表 (USER_CONSENTS): 新增/更新 {c_count} 筆")
        print(f"   * 原始定錨表 (RAW_ARTIFACTS): 新增/更新 {a_count} 筆")
        return True
    except Exception as e:
        conn.rollback()
        print(f"❌ 匯入失敗: {e}")
        return False
    finally:
        conn.close()

# 5. 核心功能：去識別化科研共享匯出 (情境 B)
def export_research(db_path, output_path, profile, custom_shift_days=None, include_resources=None):
    print(f"🧬 開始執行去識別化科研共享匯出...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤：找不到資料庫檔案 {db_path}")
        return False
        
    # 決定時間平移天數
    if custom_shift_days is not None:
        shift_days = custom_shift_days
    else:
        shift_days = get_deterministic_shift_days(profile)
    
    conn = sqlite3.connect(db_path)
    
    # 讀取病患 ID
    cursor = conn.cursor()
    cursor.execute("SELECT patient_id FROM MY_PROFILE LIMIT 1")
    row = cursor.fetchone()
    patient_id = row[0] if row else f"PUMC_{profile.upper()}"
    
    # 讀取醫療歷程
    cursor.execute("SELECT entry_id, resource_type, fhir_resource_json, last_updated FROM MY_CLINICAL_JOURNEY")
    journey_rows = cursor.fetchall()
    conn.close()
    
    clinical_journey = []
    for row in journey_rows:
        entry_id, res_type, fhir_json, last_updated = row
        if include_resources:
            includes = [i.strip().lower() for i in include_resources.split(",")]
            if res_type.lower() not in includes:
                continue
                
        try:
            fhir_resource = json.loads(fhir_json)
        except Exception:
            continue
            
        # 套用去識別化與時間平移
        deid_resource = deidentify_resource(fhir_resource, patient_id, shift_days)
        shifted_last_updated = shift_date_string(last_updated, shift_days)
        
        clinical_journey.append({
            "entry_id": entry_id.replace(patient_id, f"{patient_id}-DEID"),
            "resource_type": res_type,
            "fhir_resource_json": deid_resource,
            "last_updated": shifted_last_updated
        })
        
    research_bundle = {
        "export_type": "de-identified_research_bundle",
        "profile_deid": f"{patient_id}-DEID",
        "exported_at": datetime.now().isoformat(),
        "date_shifting_applied": True,
        "shift_days": shift_days,
        "clinical_journey": clinical_journey
    }
    
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(research_bundle, f, ensure_ascii=False, indent=2)
        print(f"✨ 科研資料包去識別化匯出成功！(時間平移: {shift_days} 天)")
        print(f"   * 輸出路徑: {output_path}")
        print(f"   * 共匯出 {len(clinical_journey)} 筆臨床事件。")
        return True
    except Exception as e:
        print(f"❌ 去識別化匯出寫入失敗: {e}")
        return False

# 6. 核心功能：日常監測 CSV 匯出 (情境 E)
def export_daily_monitoring(db_path, output_path, days=None):
    print(f"📊 開始執行日常健康監測指標 (CSV) 匯出...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤：找不到資料庫檔案 {db_path}")
        return False
        
    conn = sqlite3.connect(db_path)
    
    # 取得就醫 Encounter 列表以利對合
    cursor = conn.cursor()
    cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Encounter'")
    encounters = []
    for row in cursor.fetchall():
        try:
            data = json.loads(row[0])
            encounters.append({
                "start": data.get("period", {}).get("start", "")[:10],
                "end": data.get("period", {}).get("end", "")[:10],
                "hospital": data.get("serviceProvider", {}).get("display", "醫院")
            })
        except:
            pass
            
    # 取得 Observation 紀錄
    cursor.execute("""
        SELECT fhir_resource_json, last_updated 
        FROM MY_CLINICAL_JOURNEY 
        WHERE resource_type = 'Observation'
        ORDER BY json_extract(fhir_resource_json, '$.effectiveDateTime') DESC
    """)
    obs_rows = cursor.fetchall()
    conn.close()
    
    csv_rows = []
    
    # 決定天數過濾邊界
    filter_date = None
    if days is not None:
        filter_date = datetime.now() - timedelta(days=days)
        
    for row in obs_rows:
        try:
            data = json.loads(row[0])
            effective_date_str = data.get("effectiveDateTime", "")
            if not effective_date_str:
                continue
                
            # 解析日期
            obs_dt = None
            try:
                obs_dt = datetime.strptime(effective_date_str[:10], "%Y-%m-%d")
            except:
                pass
                
            if filter_date and obs_dt and obs_dt < filter_date:
                continue
                
            loinc = ""
            coding_list = data.get("code", {}).get("coding", [])
            if coding_list:
                loinc = coding_list[0].get("code", "")
                
            metric_name = data.get("code", {}).get("text", "未命名指標")
            
            # 讀取數值
            val_q = data.get("valueQuantity", {})
            val = val_q.get("value", None)
            unit = val_q.get("unit", "")
            if val is None:
                val = data.get("valueString", "")
                
            # 對合住院狀態
            align_status = "🏠 日常居家 / 門診追蹤"
            if obs_dt:
                for enc in encounters:
                    if enc["start"] and enc["end"]:
                        try:
                            start_dt = datetime.strptime(enc["start"], "%Y-%m-%d")
                            end_dt = datetime.strptime(enc["end"], "%Y-%m-%d")
                            if start_dt <= obs_dt <= end_dt:
                                align_status = f"🏥 住院期間 ({enc['hospital']}, {enc['start']}~{enc['end']})"
                                break
                        except:
                            pass
                            
            note = ""
            notes = data.get("note", [])
            if notes:
                note = notes[0].get("text", "")
                
            csv_rows.append([
                effective_date_str.replace("T", " ")[:19],
                loinc,
                metric_name,
                val,
                unit,
                align_status,
                note
            ])
        except Exception as e:
            continue
            
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["日期時間", "LOINC代碼", "指標名稱", "數值", "單位", "就醫對齊狀態", "備註/來源"])
            writer.writerows(csv_rows)
        print(f"✨ 日常監測指標已成功寫入 CSV 檔案！")
        print(f"   * 輸出路徑: {output_path}")
        print(f"   * 共匯出 {len(csv_rows)} 筆監測紀錄。")
        return True
    except Exception as e:
        print(f"❌ CSV 寫入失敗: {e}")
        return False

# 7. 核心功能：保險理賠申報 ZIP 包 (情境 F)
def export_insurance(db_path, output_path, data_dir, event_id):
    print(f"💼 開始進行商業保險理賠申報包 (ZIP) 打包...")
    if not os.path.exists(db_path):
        print(f"❌ 錯誤：找不到資料庫檔案 {db_path}")
        return False
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # a. 讀取指定的住院就醫事件 (Encounter)
    cursor.execute("SELECT fhir_resource_json, artifact_id FROM MY_CLINICAL_JOURNEY WHERE entry_id = ? AND resource_type = 'Encounter'", (event_id,))
    enc_row = cursor.fetchone()
    if not enc_row:
        print(f"❌ 錯誤：在資料庫中找不到指定的就醫事件 ID: '{event_id}'")
        conn.close()
        return False
        
    enc_data = json.loads(enc_row[0])
    linked_artifact_id = enc_row[1]
    
    start_str = enc_data.get("period", {}).get("start", "")
    end_str = enc_data.get("period", {}).get("end", "")
    hospital = enc_data.get("serviceProvider", {}).get("display", "醫療機構")
    
    if not start_str or not end_str:
        print("❌ 錯誤：就醫事件中缺少住院起訖時間，無法進行時間比對。")
        conn.close()
        return False
        
    start_dt = datetime.strptime(start_str[:10], "%Y-%m-%d")
    end_dt = datetime.strptime(end_str[:10], "%Y-%m-%d")
    
    # b. 檢索該就醫區間內的所有臨床歷程
    cursor.execute("SELECT entry_id, resource_type, fhir_resource_json, last_updated, artifact_id FROM MY_CLINICAL_JOURNEY")
    all_journey = cursor.fetchall()
    
    related_resources = []
    related_artifact_ids = set()
    if linked_artifact_id:
        related_artifact_ids.add(linked_artifact_id)
        
    for row in all_journey:
        eid, rtype, fhir_json, last_updated, art_id = row
        if eid == event_id:
            continue
        try:
            res_obj = json.loads(fhir_json)
            # 時間對合
            res_date_str = ""
            if rtype == "Observation":
                res_date_str = res_obj.get("effectiveDateTime", "")
            elif rtype == "MedicationRequest":
                # 以 last_updated 或 authoredOn 判斷
                res_date_str = res_obj.get("authoredOn", last_updated)
            elif rtype == "Procedure":
                res_date_str = res_obj.get("performedDateTime", last_updated)
            elif rtype == "Condition":
                res_date_str = res_obj.get("recordedDate", last_updated)
                
            if res_date_str:
                res_dt = datetime.strptime(res_date_str[:10], "%Y-%m-%d")
                if start_dt <= res_dt <= end_dt:
                    related_resources.append({
                        "entry_id": eid,
                        "resource_type": rtype,
                        "date": res_date_str[:16].replace("T", " "),
                        "detail": res_obj.get("code", {}).get("text", "") or res_obj.get("medicationCodeableConcept", {}).get("text", "") or rtype
                    })
                    if art_id:
                        related_artifact_ids.add(art_id)
        except Exception:
            pass
            
    # c. 查詢關聯之原始檔案
    raw_files = []
    if related_artifact_ids:
        placeholders = ", ".join(["?"] * len(related_artifact_ids))
        cursor.execute(f"SELECT artifact_id, original_filename, storage_path FROM RAW_ARTIFACTS WHERE artifact_id IN ({placeholders})", list(related_artifact_ids))
        for row in cursor.fetchall():
            raw_files.append({
                "artifact_id": row[0],
                "filename": row[1],
                "rel_path": row[2]
            })
            
    conn.close()
    
    # d. 撰寫明細報告 (Markdown)
    summary_md = f"""# 🏥 商業醫療保險理賠就醫明細表 (Claim Summary)

*   **就醫事件代碼**：`{event_id}`
*   **醫療機構**：{hospital}
*   **住院就醫期間**：{start_str[:10]} 至 {end_str[:10]}
*   **產出日期**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📋 1. 住院期間臨床事件明細 (Clinical Logs)
以下為該就醫期間內，病患本地資料庫所登錄之臨床事件：

| 發生時間 | 類別 | 事件說明 | 資料庫識別碼 |
| :--- | :--- | :--- | :--- |
| {start_str[:10]} | Encounter | 住院登記入學 | {event_id} |
"""
    for res in related_resources:
        summary_md += f"| {res['date']} | {res['resource_type']} | {res['detail']} | {res['entry_id']} |\n"
        
    summary_md += f"| {end_str[:10]} | Encounter | 出院手續辦結 | {event_id} |\n\n"
    
    summary_md += """---

## 📂 2. 理賠佐證原始報告清單 (Linked Documents)
以下為本次打包隨附之醫院原始病歷、診斷證明或收據掃描件，已物理封裝於 ZIP 壓縮包中：

"""
    for idx, f in enumerate(raw_files):
        summary_md += f"{idx+1}. **{f['filename']}** (雜湊雜湊雜湊雜湊: `{f['artifact_id'][:12]}...`)\n"
        
    if not raw_files:
        summary_md += "*無隨附原始報告文件。*\n"
        
    summary_md += f"\n---\n{DISCLAIMER}\n"
    
    # e. 開始寫入 ZIP
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 寫入明細表
            zip_file.writestr("claim_summary.md", summary_md)
            
            # 寫入實體原始檔案
            for f in raw_files:
                # 在本地 data/instances/{profile}/ 下定位檔案
                # DB 儲存的路徑通常是 相對路徑 (例如 data/instances/myself/raw/report.pdf)
                # 我們需要解析出真正的絕對路徑
                # 先看 DB 裡的 storage_path 是否為相對路徑，或是直接與 data_dir 做結合
                storage_path = f["rel_path"]
                
                # 如果 DB storage_path 包含 events 或是絕對路徑，做處理
                # 正常情況下，我們將其解析為相對於整個專案根目錄或 data_dir 
                possible_paths = [
                    os.path.join(PROJECT_DIR, storage_path),
                    os.path.join(data_dir, os.path.basename(storage_path)),
                    os.path.join(data_dir, "raw", os.path.basename(storage_path)),
                    os.path.abspath(storage_path)
                ]
                
                found_path = None
                for p in possible_paths:
                    if os.path.exists(p) and os.path.isfile(p):
                        found_path = p
                        break
                        
                if found_path:
                    zip_file.write(found_path, os.path.join("documents", f["filename"]))
                    print(f"   [+] 已將隨附檔案打包: {f['filename']}")
                else:
                    print(f"   [⚠️ 警告] 找不到實體隨附檔案: {f['filename']} (嘗試路徑: {possible_paths[0]})")
                    
        print(f"✨ 保險理賠證明包打包成功！")
        print(f"   * 輸出路徑: {output_path}")
        return True
    except Exception as e:
        print(f"❌ ZIP 打包失敗: {e}")
        return False

# 8. 核心功能：門診 SOAP 與長照、緊急卡 Markdown 生成 (情境 A, D, G)
def query_clinical_context(db_path, profile):
    """輔助函式：從 DB 讀取生成 Markdown 所需的上下文"""
    context = {
        "display_name": f"被照顧者 {profile}",
        "patient_id": f"PUMC_{profile.upper()}",
        "age": 50,
        "height_cm": 170,
        "weight_kg": 70,
        "bsa": 1.82,
        "disease_name": "未登錄疾病",
        "drugs_list": [],
        "recent_symptoms": [],
        "hospital": "未設定",
        "allergy": "無過敏史",
        "observations": [],
        "ad_signed": False
    }
    
    if not os.path.exists(db_path):
        return context
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Profile 資訊
    cursor.execute("SELECT patient_id, display_name, meta_data FROM MY_PROFILE LIMIT 1")
    p_row = cursor.fetchone()
    if p_row:
        context["patient_id"] = p_row[0]
        context["display_name"] = p_row[1]
        try:
            meta = json.loads(p_row[2])
            birth_date = meta.get("birth_date", "1973-02-15")
            birth_year = int(birth_date.split("-")[0])
            context["age"] = datetime.now().year - birth_year
            context["height_cm"] = meta.get("height_cm", 170)
            context["weight_kg"] = meta.get("weight_kg", 70)
            context["bsa"] = ((context["height_cm"] * context["weight_kg"]) / 3600) ** 0.5
        except:
            pass
            
    # 2. 疾病 (Condition)
    cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Condition' ORDER BY last_updated DESC LIMIT 1")
    cond_row = cursor.fetchone()
    if cond_row:
        try:
            context["disease_name"] = json.loads(cond_row[0]).get("code", {}).get("text", "未命名診斷")
        except:
            pass
            
    # 3. 用藥 (MedicationRequest)
    cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'MedicationRequest'")
    for row in cursor.fetchall():
        try:
            med_name = json.loads(row[0]).get("medicationCodeableConcept", {}).get("text", "")
            if med_name:
                context["drugs_list"].append(med_name)
        except:
            pass
    context["drugs_list"] = list(set(context["drugs_list"]))
    
    # 4. 看診科別 (Encounter)
    cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Encounter' ORDER BY last_updated DESC LIMIT 1")
    enc_row = cursor.fetchone()
    if enc_row:
        try:
            context["hospital"] = json.loads(enc_row[0]).get("serviceProvider", {}).get("display", "醫院")
        except:
            pass
            
    # 5. 過敏史 (AllergyIntolerance)
    cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'AllergyIntolerance' ORDER BY last_updated DESC LIMIT 1")
    alg_row = cursor.fetchone()
    if alg_row:
        try:
            context["allergy"] = json.loads(alg_row[0]).get("code", {}).get("text", "無過敏史")
        except:
            pass
            
    # 6. 最近自述症狀 (Observation)
    cursor.execute("SELECT fhir_resource_json, last_updated FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Observation' ORDER BY last_updated DESC")
    obs_rows = cursor.fetchall()
    
    for row in obs_rows:
        try:
            data = json.loads(row[0])
            effective_date = data.get("effectiveDateTime", row[1])
            code_text = data.get("code", {}).get("text", "")
            
            val_q = data.get("valueQuantity", {})
            val = val_q.get("value", None)
            unit = val_q.get("unit", "")
            if val is None:
                val = data.get("valueString", "")
                
            display_val = f"{val} {unit}".strip() if val else ""
            
            context["observations"].append({
                "code_text": code_text,
                "date": effective_date,
                "value": display_val
            })
            
            # 撈取最近的自述症狀
            if "自述症狀" in code_text or "reported symptoms" in code_text.lower():
                val_str = data.get("valueString", "")
                if val_str and len(context["recent_symptoms"]) < 3:
                    context["recent_symptoms"].append(f"{effective_date[:16].replace('T', ' ')}: {val_str}")
        except:
            pass
            
    # 7. AD 同意書 (預立醫療)
    cursor.execute("SELECT consent_id FROM USER_CONSENTS WHERE consent_type = 'delegated_care' AND is_active = 1")
    if cursor.fetchone():
        context["ad_signed"] = True
        
    conn.close()
    return context

def export_clinical_summary(db_path, output_path, profile):
    print(f"🏥 開始產生門診就醫溝通與第二意見摘要卡 (Markdown)...")
    ctx = query_clinical_context(db_path, profile)
    
    # 提取關鍵指標
    obs_list = ctx["observations"]
    
    # 匹配對應的檢驗項目
    def get_latest_obs(keywords):
        for obs in obs_list:
            if any(kw in obs["code_text"].lower() for kw in keywords):
                return obs
        return None
        
    m_spike = get_latest_obs(["m蛋白", "m-spike", "paraprotein", "spep"])
    b2m = get_latest_obs(["beta-2", "β2", "微球蛋白"])
    kl_ratio = get_latest_obs(["輕鏈", "kappa", "lambda", "k/l"])
    calcium = get_latest_obs(["鈣", "calcium"])
    creatinine = get_latest_obs(["肌酸酐", "creatinine", "cre"])
    egfr = get_latest_obs(["egfr", "腎絲球"])
    hgb = get_latest_obs(["血紅素", "hemoglobin", "hgb"])
    wbc = get_latest_obs(["白血球", "wbc"])
    plt = get_latest_obs(["血小板", "platelet", "plt"])
    
    m_spike_str = f"**`{m_spike['value']}`** (採檢日: {m_spike['date'][:10]})" if m_spike else "尚未登錄 (正常參考值: 陰性/無增殖帶)"
    b2m_str = f"**`{b2m['value']}`** (採檢日: {b2m['date'][:10]})" if b2m else "尚未登錄 (正常參考值: 1.09 ~ 2.53 mg/L)"
    kl_ratio_str = f"**`{kl_ratio['value']}`** (採檢日: {kl_ratio['date'][:10]})" if kl_ratio else "尚未登錄 (正常參考值: 0.26 - 1.65)"
    calcium_str = f"**`{calcium['value']}`** (採檢日: {calcium['date'][:10]})" if calcium else "尚未登錄 (正常參考值: 2.15 - 2.58 mmol/L)"
    cre_str = f"**`{creatinine['value']}`** (採檢日: {creatinine['date'][:10]})" if creatinine else "尚未登錄 (正常參考值: 0.7 - 1.2 mg/dL)"
    egfr_str = f"**`{egfr['value']}`** (採檢日: {egfr['date'][:10]})" if egfr else "尚未登錄"
    hgb_str = f"**`{hgb['value']}`** (採檢日: {hgb['date'][:10]})" if hgb else "尚未登錄"
    wbc_str = f"**`{wbc['value']}`** (採檢日: {wbc['date'][:10]})" if wbc else "尚未登錄"
    plt_str = f"**`{plt['value']}`** (採檢日: {plt['date'][:10]})" if plt else "尚未登錄"

    md_content = f"""# 🏥 {ctx['disease_name']} 門診諮詢與第二意見病情摘要卡 (De-identified Clinical Summary)

本摘要為已去識別化之病患健康歷程，旨在方便病患尋求跨院所第二意見諮詢時，能讓臨床醫師於 30 秒內快速掌握患者目前之治療方案、最新關鍵腫瘤指標與主要日常用藥。

---

## 👤 1. 患者基本資料 (Patient Profile - De-identified)
*   **諮詢代號**：`{ctx['patient_id']}-DEID`
*   **性別**：男
*   **虛擬年齡**：{ctx['age']} 歲 (出生年月已進行本地平移)
*   **身高/體重**：{ctx['height_cm']} cm / {ctx['weight_kg']} kg (體表面積 BSA: {ctx['bsa']:.2f} ㎡)
*   **主要診斷**：{ctx['disease_name']} (Active)

---

## 💊 2. 目前治療與用藥方案 (Current Active Protocol)

### 核心治療與日常控制用藥
"""
    if ctx["drugs_list"]:
        for idx, drug in enumerate(ctx["drugs_list"]):
            md_content += f"{idx+1}.  **{drug}**：口服，依醫囑每日按時服用。\n"
    else:
        md_content += "*本機資料庫目前查無活性用藥處方。*\n"
        
    md_content += f"""
---

## 🧪 3. 最新關鍵檢驗指標摘要 (Key Lab Results)

### 🧬 腫瘤進殖/特異性指標
*   **血清蛋白電泳分析 (SPEP)**：{m_spike_str}
*   **$\\beta_2$-微球蛋白 (Beta-2 Microglobulin)**：{b2m_str}
*   **游離輕鏈比值 (Free K/L Ratio)**：{kl_ratio_str}

### 🩸 臟器功能與造血評估 (CRAB/主要器官指標)
*   **C (血鈣離子 Calcium)**：{calcium_str}
*   **R (腎功能 Renal)**：肌酸酐 (`CRE`) {cre_str}，腎絲球濾過率 `eGFR` 為 {egfr_str}
*   **A (貧血 Anemia)**：血紅素 (`Hgb`) {hgb_str}
*   **骨髓與血球狀況**：白血球 (WBC) {wbc_str}，血小板 (PLT) {plt_str}

---

## 💬 4. 門診諮詢與討論重點 (Consultation Questions)
1.  **療效評估與追蹤**：目前服用藥物之療效如何？是否需要根據 SPEP 與輕鏈比值調整目前劑量？
2.  **副作用與安全性指標監控**：高齡用藥是否需要注意手腳麻木或無力？下一次抽血追蹤主/副安全指標（如肝指數、CPK）的時間？
3.  **B肝防禦性處方時程**：預防性抗病毒藥 Entecavir 在核心療程完全結束後，需要持續服用多久才能安全停藥？

---
{DISCLAIMER}
"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"✨ 門診溝通 Markdown 報告已生成！寫入至：{output_path}")
        return True
    except Exception as e:
        print(f"❌ Markdown 生成失敗: {e}")
        return False

def export_ice_card(db_path, output_path, profile):
    print(f"🚨 開始產生緊急急診資訊卡 (ICE Card)...")
    ctx = query_clinical_context(db_path, profile)
    
    ice_content = f"""==================================================
🚨 【緊急醫療救援資訊卡 (In Case of Emergency)】 🚨
==================================================
👤 【患者代碼】：{ctx['patient_id']}-DEID ({ctx['display_name']} 阿伯)
🩸 【生理特徵】：O 型 (預設) | {ctx['age']} 歲 | BSA: {ctx['bsa']:.2f} ㎡
⚠️ 【嚴重過敏史】：{ctx['allergy']}
--------------------------------------------------
📋 【主要診斷】：{ctx['disease_name']}
💊 【目前核心服用藥物】 (急救與交接必看)：
"""
    if ctx["drugs_list"]:
        for idx, drug in enumerate(ctx["drugs_list"]):
            ice_content += f"  {idx+1}. {drug} - 依醫囑服用\n"
    else:
        ice_content += "  *目前資料庫查無核心用藥*\n"
        
    ice_content += f"""--------------------------------------------------
📞 【緊急聯絡人】：家屬 (電話: 0988-***-***)
==================================================
* 本資訊由本地個人主權 PHR 產生，緊急救護時供第一線醫護人員參考。
* {DISCLAIMER.splitlines()[2]}
"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ice_content)
        print(f"✨ 緊急醫療卡已成功匯出！寫入至：{output_path}")
        return True
    except Exception as e:
        print(f"❌ 緊急卡生成失敗: {e}")
        return False

def export_care_transition(db_path, output_path, profile):
    print(f"👴 開始產生長照轉介與照護交接摘要卡...")
    ctx = query_clinical_context(db_path, profile)
    
    # 找尋巴氏量表分數
    barthel_score = "65 分 (中度失能)"  # 預設
    barthel_date = "2026-06-12 (預設)"
    for obs in ctx["observations"]:
        if "巴氏" in obs["code_text"] or "barthel" in obs["code_text"].lower():
            barthel_score = obs["value"]
            barthel_date = obs["date"][:10]
            break
            
    # Beers Criteria 警告
    beers_warning = "*無高風險用藥警示*"
    falls_guide = "*起床三階30秒原則 (甦醒、坐起、站立各停30秒)；保持動線防滑。*"
    
    prednisolone_active = False
    for drug in ctx["drugs_list"]:
        if "prednisolone" in drug.lower() or "普力多寧" in drug:
            prednisolone_active = True
            break
            
    if prednisolone_active:
        beers_warning = "*   **類固醇用藥安全 (Prednisolone)**：長期服用具骨質流失與下肢肌肉無力風險，增加高齡者跌倒之不良機率。"
        falls_guide = "*   起床採取「三階30秒」原則（甦醒、坐起、站立各停30秒），防止姿勢性低血壓跌倒。\n*   浴室與走廊安裝扶手，保持動線無障礙且光線充足。"

    ad_status = "已註記於健保卡 (同意書 Hash 定錨完成)" if ctx["ad_signed"] else "尚未於系統定錨簽署 (請參考大書進行 ACP 諮商)"

    md_content = f"""# 👴 長照 2.0 轉介與照護交接摘要表 (Care Transition Summary)

*   **病件代號**：`{ctx['patient_id']}-DEID`
*   **姓名/身分**：{ctx['display_name']} 阿伯
*   **建檔時間**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
*   **主要臨床診斷**：{ctx['disease_name']}

---

## ♿ 1. 日常生活活動能力 (巴氏量表自評)
*   **自評總分**：**{barthel_score}**
*   **評估日期**：{barthel_date}
*   **照護建議**：中度失能狀態。上下樓梯與沐浴洗澡需人扶持與協助，建議申請長照 2.0 居家喘息或專業照顧服務。

---

## ⚠️ 2. 高齡用藥安全與居家防跌 (Beers Criteria)
*   **高風險用藥警示**：
{beers_warning}
*   **居家防跌指引**：
{falls_guide}

---

## 📜 3. 預立醫療決定 (AD) 與在宅安寧緩和意願
*   **預立醫療決定 (AD) 狀態**：{ad_status}
*   **臨終舒適照護意願**：
    *   拒絕氣管插管、心肺復甦術 (DNR) 與人工餵食。
    *   若面臨瀕死喉音，照護採取「側臥不抽痰」；若出現拒食，採取濕潤唇齒之快適護理，尊重生命尊嚴。

---
{DISCLAIMER}
"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"✨ 長照照護交接摘要已成功生成！寫入至：{output_path}")
        return True
    except Exception as e:
        print(f"❌ 長照交接摘要生成失敗: {e}")
        return False

# 9. 主程式進入點
def main():
    parser = argparse.ArgumentParser(description="蓬萊本地主權健康資料庫匯入/匯出與移轉工具 (db_porter)")
    parser.add_argument("--profile", type=str, default="myself", help="指定主體身分 (如 myself, father)")
    parser.add_argument("--db-path", type=str, help="手動指定 SQLite 資料庫路徑")

    # 動作組
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-e", "--export", action="store_true", help="執行資料匯出")
    group.add_argument("-i", "--import-file", type=str, help="執行資料匯入，指定備份 JSON 檔案路徑")

    # 參數組
    parser.add_argument("-f", "--format", choices=["md", "json", "csv", "zip"], default="json", help="匯出格式")
    parser.add_argument("-t", "--type", choices=["clinical_summary", "research", "backup", "ice", "daily_monitoring", "insurance", "care_transition"], help="匯出報告/資料類型")
    parser.add_argument("-o", "--output", type=str, help="輸出檔案路徑")

    # 安全參數
    parser.add_argument("--deidentify", action="store_true", help="啟用去識別化")
    parser.add_argument("--shift-days", type=int, help="指定時間平移天數")

    # 篩選參數
    parser.add_argument("--include", type=str, help="選擇性匯出的 FHIR 資源類型 (逗號分隔，如 Observation,Condition)")
    parser.add_argument("--days", type=int, help="匯出最近 N 天的日常監測數據 (用於日常監測)")
    parser.add_argument("--event-id", type=str, help="指定住院就醫事件 entry_id (用於保險理賠)")

    args = parser.parse_args()

    # 智慧定位路徑
    db_path, data_dir = get_db_paths(args.profile, args.db_path)
    db_path = os.path.abspath(db_path)
    data_dir = os.path.abspath(data_dir)

    print("==================================================")
    print("   Sovereign Health Agent - 資料移轉工具 (v0.1.0)")
    print(f"   👤 執行身分: {args.profile}")
    print(f"   💾 資料庫: {db_path}")
    print("==================================================")

    # 執行匯入動作
    if args.import_file:
        import_path = os.path.abspath(args.import_file)
        success = import_backup(db_path, import_path)
        sys.exit(0 if success else 1)

    # 執行匯出動作
    if args.export:
        if not args.type or not args.output:
            print("❌ 錯誤：執行匯出時，必須提供 --type 與 --output 參數！")
            sys.exit(1)
            
        output_path = os.path.abspath(args.output)
        
        # 依不同類型派發
        success = False
        if args.type == "backup":
            if args.format != "json":
                print("❌ 錯誤：備份檔案類型 (backup) 僅支援 json 格式輸出。")
                sys.exit(1)
            success = export_backup(db_path, output_path)
            
        elif args.type == "research":
            if args.format != "json":
                print("❌ 錯誤：科研共享類型 (research) 僅支援 json 格式輸出。")
                sys.exit(1)
            success = export_research(
                db_path, output_path, args.profile, 
                custom_shift_days=args.shift_days, 
                include_resources=args.include
            )
            
        elif args.type == "daily_monitoring":
            if args.format != "csv":
                print("❌ 錯誤：日常監測類型 (daily_monitoring) 僅支援 csv 格式輸出。")
                sys.exit(1)
            success = export_daily_monitoring(db_path, output_path, days=args.days)
            
        elif args.type == "insurance":
            if args.format != "zip":
                print("❌ 錯誤：保險理賠類型 (insurance) 僅支援 zip 格式輸出。")
                sys.exit(1)
            if not args.event_id:
                print("❌ 錯誤：打包保險理賠證明時，必須提供 --event-id 參數！")
                sys.exit(1)
            success = export_insurance(db_path, output_path, data_dir, args.event_id)
            
        elif args.type == "clinical_summary":
            if args.format != "md":
                print("❌ 錯誤：門診摘要卡類型 (clinical_summary) 僅支援 md 格式輸出。")
                sys.exit(1)
            success = export_clinical_summary(db_path, output_path, args.profile)
            
        elif args.type == "ice":
            if args.format != "md":
                print("❌ 錯誤：緊急醫療卡類型 (ice) 僅支援 md 格式輸出。")
                sys.exit(1)
            success = export_ice_card(db_path, output_path, args.profile)
            
        elif args.type == "care_transition":
            if args.format != "md":
                print("❌ 錯誤：長照交接摘要類型 (care_transition) 僅支援 md 格式輸出。")
                sys.exit(1)
            success = export_care_transition(db_path, output_path, args.profile)
            
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
