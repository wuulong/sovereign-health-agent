#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 資料庫患者資料分離工具 (DB Patient Splitter)
功能：在本地 SQLite 資料庫中區分「虛擬病人 (PUMC_004)」與「目前真實病人 (PUMC_001)」。
      將真實用藥 (MED_REQ_*) 與檢驗 (OBS_LAB_*) 的歸屬 patient_id 與 FHIR Reference 更新為 PUMC_001。
      虛擬病人發燒事件 (Daratumumab, Bortezomib 等) 則保持為 PUMC_004。
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

# 設定路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))

DB_PATH = os.path.join(agent_dir, "db", "fv_patient_personal.db")

MOCK_REAL_PATIENT_ID = "PUMC_001"
MOCK_VIRTUAL_PATIENT_ID = "PUMC_004"

def split_patients():
    if not os.path.exists(DB_PATH):
        print(f"【錯誤】找不到資料庫：{DB_PATH}", file=sys.stderr)
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. 建立真實病人的 Profile (許武龍先生去識別化為王小明，生日平移 -14 天)
        cursor.execute("""
        INSERT OR REPLACE INTO MY_PROFILE (patient_id, display_name, email, phone, meta_data)
        VALUES (?, ?, ?, ?, ?)
        """, (
            MOCK_REAL_PATIENT_ID,
            "王小明",
            "wang001@taiwan.tw",
            "0912-345-678",
            json.dumps({
                "schema_version": "v0.1.0",
                "phr_sync_status": "synced",
                "birth_date": "1973-02-18", # 1973-03-04 平移 -14 天
                "height_cm": 170,
                "weight_kg": 85
            }, ensure_ascii=False)
        ))
        print(f"[*] 已在資料庫建立真實病人的 Profile (ID: {MOCK_REAL_PATIENT_ID})")

        # 2. 獲取所有屬於真實病人的資料行
        cursor.execute("""
        SELECT entry_id, resource_type, fhir_resource_json 
        FROM MY_CLINICAL_JOURNEY 
        WHERE entry_id LIKE 'OBS_LAB_%' OR entry_id LIKE 'MED_REQ_%'
        """)
        rows = cursor.fetchall()
        
        relocated_count = 0
        for entry_id, res_type, fhir_json_str in rows:
            fhir_resource = json.loads(fhir_json_str)
            
            # 更新 fhir 中的 reference
            updated = False
            if "subject" in fhir_resource and fhir_resource["subject"].get("reference") == f"Patient/{MOCK_VIRTUAL_PATIENT_ID}-DEID":
                fhir_resource["subject"]["reference"] = f"Patient/{MOCK_REAL_PATIENT_ID}-DEID"
                updated = True
                
            # 更新 patient_id 欄位與 JSON
            cursor.execute("""
            UPDATE MY_CLINICAL_JOURNEY 
            SET patient_id = ?, fhir_resource_json = ? 
            WHERE entry_id = ?
            """, (
                MOCK_REAL_PATIENT_ID, 
                json.dumps(fhir_resource, ensure_ascii=False), 
                entry_id
            ))
            relocated_count += 1
            
        conn.commit()
        print(f"【成功】已遷移 {relocated_count} 筆資源 (Observation 與 MedicationRequest) 至真實病人 ({MOCK_REAL_PATIENT_ID})！")
        return True
    except Exception as e:
        conn.rollback()
        print(f"【錯誤】資料移轉失敗：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

def print_statistics():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n==================================================")
    print("   🏥 資料庫患者資料庫分裂統計結果")
    print("==================================================")
    
    # 1. 各患者的資源統計
    cursor.execute("""
    SELECT patient_id, resource_type, count(*) 
    FROM MY_CLINICAL_JOURNEY 
    GROUP BY patient_id, resource_type
    """)
    print("[*] 臨床旅程資料分布：")
    for pid, restype, count in cursor.fetchall():
        patient_name = "真實病人 (王小明)" if pid == MOCK_REAL_PATIENT_ID else "虛擬病人 (阿喜伯)"
        print(f"  - {patient_name} [{pid}] | 資源類型: {restype:18} | 數量: {count}")
        
    # 2. 印出真實病人的用藥
    cursor.execute("""
    SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY 
    WHERE patient_id = ? AND resource_type = 'MedicationRequest'
    """, (MOCK_REAL_PATIENT_ID,))
    print(f"\n[*] 真實病人 ({MOCK_REAL_PATIENT_ID}) 的真實用藥項目：")
    for row in cursor.fetchall():
        med = json.loads(row[0])
        print(f"  - {med['medicationCodeableConcept']['text']}")
        
    # 3. 印出虛擬病人的用藥
    cursor.execute("""
    SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY 
    WHERE patient_id = ? AND resource_type = 'MedicationRequest'
    """, (MOCK_VIRTUAL_PATIENT_ID,))
    print(f"\n[*] 虛擬病人 ({MOCK_VIRTUAL_PATIENT_ID}) 的範例用藥項目：")
    for row in cursor.fetchall():
        med = json.loads(row[0])
        print(f"  - {med['medicationCodeableConcept']['text']}")
        
    print("==================================================")
    conn.close()

def main():
    if split_patients():
        print_statistics()

if __name__ == "__main__":
    main()
