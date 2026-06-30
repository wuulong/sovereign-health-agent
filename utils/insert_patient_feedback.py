#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 寫入病人日常口述回饋至資料庫
功能：將許先生口述之「神經病變完全改善史」與「口服 CP 類固醇脈衝反應」封裝為 FHIR R4 Patient-Reported Observation，
      寫入本地 SQLite 個人資料庫，為代理人推理提供患者端的事實基礎。
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

# 設定路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))
db_path = "/Users/wuulong/github/bmad-pa/private_data/sovereign-health/db/instances/myself/fv_patient_personal.db"
patient_id = "PUMC_001"

def create_neuro_history_fhir():
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
    obs = {
        "resourceType": "Observation",
        "id": "OBS-PAT-NEURO-HISTORY",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey"
                    }
                ],
                "text": "Patient Reported Feedback"
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "29272-2",
                    "display": "Patient-reported symptoms"
                }
            ],
            "text": "患者主觀神經病變歷史回饋"
        },
        "subject": {
            "reference": f"Patient/{patient_id}-DEID",
            "display": "許武龍"
        },
        "effectiveDateTime": "2026-06-16",
        "issued": now_str,
        "performer": [
            {
                "reference": f"Patient/{patient_id}-DEID",
                "display": "許武龍"
            }
        ],
        "valueString": "完全改善 (Fully Resolved)",
        "note": [
            {
                "text": "脫髓鞘多發性神經病變（Demyelinating polyneuropathy, DPN）在 2017 年開始治療後持續改善，約半年至一年後完全改善，之後 8 年（至 2026 年目前）無任何復發或惡化跡象，行動力完全自如。"
            }
        ]
    }
    return obs

def create_med_reaction_fhir():
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
    obs = {
        "resourceType": "Observation",
        "id": "OBS-PAT-MED-REACTION",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey"
                    }
                ],
                "text": "Patient Reported Feedback"
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "80598-6",
                    "display": "Patient-reported outcomes"
                }
            ],
            "text": "患者口服類固醇脈衝用藥生理反應回饋"
        },
        "subject": {
            "reference": f"Patient/{patient_id}-DEID",
            "display": "許武龍"
        },
        "effectiveDateTime": "2026-06-16",
        "issued": now_str,
        "performer": [
            {
                "reference": f"Patient/{patient_id}-DEID",
                "display": "許武龍"
            }
        ],
        "valueString": "脈衝期精神好、思緒清晰、無失眠",
        "note": [
            {
                "text": "長期維持口服 CP 方案藥物耐受性極佳。早期整月吃藥時半夜易醒想事情。改為每月服藥 4 天（CP 方案）後，服藥期間無失眠，僅感精神特別好、思緒清晰；停藥後身體作息完全正常。日常耐受度極佳。"
            }
        ]
    }
    return obs

def insert_feedback():
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫檔案：{db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    meta_data = {
        "patient_reported": True,
        "source": "patient_interview",
        "description": "患者於 2026-06-16 對話中主動提供之長期病程與用藥生理反應回饋"
    }

    try:
        # 1. 構造 FHIR 數據
        obs_list = [create_neuro_history_fhir(), create_med_reaction_fhir()]
        
        # 2. 寫入資料表 MY_CLINICAL_JOURNEY
        for obs in obs_list:
            cursor.execute("""
                INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (
                    entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                obs["id"],
                patient_id,
                "Observation",
                json.dumps(obs, ensure_ascii=False),
                now_str,
                json.dumps(meta_data, ensure_ascii=False)
            ))
            
        conn.commit()
        print("\n🎉 成功寫入病人口述回饋數據至資料庫！")
        print("  - 寫入 entry_id: OBS-PAT-NEURO-HISTORY (神經病變恢復歷史)")
        print("  - 寫入 entry_id: OBS-PAT-MED-REACTION (類固醇脈衝生理反應)")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"【失敗】寫入資料庫時發生異常：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    insert_feedback()
