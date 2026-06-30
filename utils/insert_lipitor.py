#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 補登立普妥 (Lipitor) 用藥
功能：將許先生目前服用的降膽固醇藥物立普妥 (Lipitor / Atorvastatin) 寫入本地 SQLite 資料庫，
      以維護 PHR 活性用藥清單。符合個資安全規範，不使用中國用語。
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

def insert_lipitor():
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫：{db_path}", file=sys.stderr)
        return False

    entry_id = "MED_REQ_LIPITOR_REPORTED"
    now_str = datetime.now().isoformat()
    
    fhir_resource = {
        "resourceType": "MedicationRequest",
        "id": entry_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://substances.nhia.gov.tw",
                    "code": "BC24618100",
                    "display": "Atorvastatin 10mg"
                }
            ],
            "text": "立普妥 (Lipitor)"
        },
        "subject": {
            "reference": f"Patient/{patient_id}-DEID"
        },
        "authoredOn": now_str[:10] + "T00:00:00+08:00",
        "note": [
            {
                "text": "病人口述用藥：降膽固醇藥物立普妥 (Lipitor)，目前持續服用中。長期使用類固醇 (Prednisolone) 易引發血脂異常，此藥為重要對位控制用藥。"
            }
        ]
    }
    
    meta_data = {
        "source": "PatientReportedActiveMedication",
        "category": "降膽固醇藥 / 降血脂藥",
        "description": "立普妥 (Lipitor)，用於控制膽固醇與預防心血管併發症。"
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            patient_id,
            "MedicationRequest",
            json.dumps(fhir_resource, ensure_ascii=False),
            now_str,
            json.dumps(meta_data, ensure_ascii=False)
        ))
        conn.commit()
        print("【成功】已成功將降血脂藥物『立普妥 (Lipitor)』歷史用藥寫入資料庫！")
        return True
    except Exception as e:
        conn.rollback()
        print(f"【失敗】寫入資料庫時發生異常：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    insert_lipitor()
