#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 補登病人口述移植後口服 CP 方案
功能：將許先生口述 2018 年 ASCT 後開始口服 CP 方案（癌德星+普力多寧）並持續到 2026 年之資訊寫入資料庫。
      符合個資安全規範，不使用中國用語。
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

# 設定路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))
db_path = os.path.join(agent_dir, "db", "instances", "myself", "fv_patient_personal.db")
patient_id = "PUMC_001"

def insert_cp_history():
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫：{db_path}", file=sys.stderr)
        return False

    now_str = datetime.now().isoformat()
    
    # 1. Cyclophosphamide 癌德星
    cyc_entry_id = "MED_REQ_20180507_CYCLOPHOSPHAMIDE_REPORTED"
    cyc_fhir = {
        "resourceType": "MedicationRequest",
        "id": cyc_entry_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://substances.nhia.gov.tw",
                    "code": "A004128100",
                    "display": "Cyclophosphamide 50mg"
                }
            ],
            "text": "口服癌德星 (Cyclophosphamide)"
        },
        "subject": {
            "reference": f"Patient/{patient_id}-DEID"
        },
        "authoredOn": "2018-05-07T00:00:00+08:00",
        "note": [
            {
                "text": "病人口述用藥史：2018 年自體幹細胞移植 (ASCT) 後開始服用口服 CP 方案 (Cyclophosphamide)。不確定是馬上就跟現在的用藥相同，或是隔幾個月開始和現在用藥相同，但一直持續服用至目前 2026 年。"
            }
        ]
    }
    
    cyc_meta = {
        "source": "PatientReportedHistory",
        "verification_status": "unconfirmed_onset_date",
        "category": "口服 CP 方案",
        "description": "2018年ASCT移植後，開始口服 CP 方案並持續至 2026 年目前。起始具體月份待確認 (移植後當月或隔數月)"
    }

    # 2. Prednisolone 普力多寧
    pred_entry_id = "MED_REQ_20180507_PREDNISOLONE_REPORTED"
    pred_fhir = {
        "resourceType": "MedicationRequest",
        "id": pred_entry_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://substances.nhia.gov.tw",
                    "code": "A003893100",
                    "display": "Prednisolone 5mg"
                }
            ],
            "text": "普力多寧 (Prednisolone)"
        },
        "subject": {
            "reference": f"Patient/{patient_id}-DEID"
        },
        "authoredOn": "2018-05-07T00:00:00+08:00",
        "note": [
            {
                "text": "病人口述用藥史：2018 年自體幹細胞移植 (ASCT) 後開始服用口服 CP 方案 (Prednisolone)。不確定是馬上就跟現在的用藥相同，或是隔幾個月開始和現在用藥相同，但一直持續服用至目前 2026 年。"
            }
        ]
    }
    
    pred_meta = {
        "source": "PatientReportedHistory",
        "verification_status": "unconfirmed_onset_date",
        "category": "口服 CP 方案",
        "description": "2018年ASCT移植後，開始口服 CP 方案並持續至 2026 年目前。起始具體月份待確認 (移植後當月或隔數月)"
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 寫入 Cyclophosphamide
        cursor.execute("""
        INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            cyc_entry_id,
            patient_id,
            "MedicationRequest",
            json.dumps(cyc_fhir, ensure_ascii=False),
            now_str,
            json.dumps(cyc_meta, ensure_ascii=False)
        ))
        
        # 寫入 Prednisolone
        cursor.execute("""
        INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            pred_entry_id,
            patient_id,
            "MedicationRequest",
            json.dumps(pred_fhir, ensure_ascii=False),
            now_str,
            json.dumps(pred_meta, ensure_ascii=False)
        ))
        
        conn.commit()
        print("【成功】已成功將病人口述的口服 CP 方案（癌德星+普力多寧）歷史用藥寫入資料庫！")
        return True
    except Exception as e:
        conn.rollback()
        print(f"【失敗】寫入資料庫時發生異常：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    insert_cp_history()
