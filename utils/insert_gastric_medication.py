#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 手動補登自費或漏登用藥工具 (Weimok Famotidine)
功能：將藥袋上讀取出的胃莫潰膜衣錠 (Weimok) 寫入本地 SQLite 資料庫，與同批癌症藥物定錨於相同日期，
      並將原始照片從 data/inbox/ 移到 data/raw/ 備份並刪除原檔。
"""

import os
import sys
import json
import shutil
import sqlite3
from datetime import datetime

# 設定路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))

FILE_DATE = "2026-06-13" # 與同批癌症用藥平移定錨日期一致
IMAGE_NAME = "IN_20260613-3.jpg"

def get_paths(profile):
    db_path = os.path.join(agent_dir, "db", "instances", profile, "fv_patient_personal.db")
    data_dir = os.path.join(agent_dir, "data", "instances", profile)
    inbox_dir = os.path.join(data_dir, "inbox")
    raw_dir = os.path.join(data_dir, "raw")
    
    if profile == "myself":
        patient_id = "PUMC_001"
    else:
        patient_id = f"PUMC_{profile.upper()}"
        
    return db_path, inbox_dir, raw_dir, patient_id

def insert_weimok_to_db(db_path, patient_id):
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫：{db_path}", file=sys.stderr)
        return False

    entry_id = f"MED_REQ_{FILE_DATE.replace('-', '')}_AC409861G0"
    
    # 建立符合專案格式的 FHIR MedicationRequest
    fhir_resource = {
        "resourceType": "MedicationRequest",
        "id": entry_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://substances.nhia.gov.tw",
                    "code": "AC409861G0",
                    "display": "胃莫潰膜衣錠20公絲"
                }
            ],
            "text": "胃莫潰膜衣錠20公絲 (Weimok F.C. 20 mg/tab)"
        },
        "subject": {
            "reference": f"Patient/{patient_id}-DEID"
        },
        "authoredOn": f"{FILE_DATE}T00:00:00+08:00",
        "dispenseRequest": {
            "expectedSupplyDuration": {
                "value": 12,
                "unit": "days",
                "system": "http://unitsofmeasure.org",
                "code": "d"
            },
            "quantity": {
                "value": 24.0,
                "system": "http://unitsofmeasure.org"
            }
        },
        "note": [
            {
                "text": "藥品分類：組織胺H2受體拮抗劑 / 胃腸藥 (胃壁保護防禦用藥)"
            },
            {
                "text": "服藥排程：每月服用 4 天 (配合癌德星與普力多寧服藥日)，早晚各 1 錠，連續服用 3 個月 (共 12 天，24 錠)"
            }
        ],
        "dosageInstruction": [
            {
                "text": "每月服用 4 天 (配合癌症治療日)，每日二次 (早晚各一次)，每次 1 錠，共 3 個月 (總給藥 24 錠，天數 12 天)",
                "timing": {
                    "repeat": {
                        "boundsDuration": {
                            "value": 3,
                            "unit": "months",
                            "system": "http://unitsofmeasure.org",
                            "code": "mo"
                        },
                        "duration": 4,
                        "durationUnit": "d",
                        "frequency": 2,
                        "period": 1,
                        "periodUnit": "mo"
                    }
                },
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": 1,
                            "unit": "錠",
                            "system": "http://unitsofmeasure.org"
                        }
                    }
                ]
            }
        ]
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now_str = datetime.now().isoformat()
    meta_data = {
        "source": "ManualImportFromPrescriptionBag",
        "category": "胃腸藥",
        "original_prescription_date": "2026-05-26",
        "hospital": "台大醫院新竹分院"
    }

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
        print(f"【成功】已成功將胃藥『胃莫潰膜衣錠20公絲 (AC409861G0)』寫入資料庫！")
        return True
    except Exception as e:
        print(f"【失敗】寫入資料庫時發生異常：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

def backup_and_cleanup_image(inbox_dir, raw_dir):
    os.makedirs(raw_dir, exist_ok=True)
    inbox_path = os.path.join(inbox_dir, IMAGE_NAME)
    raw_path = os.path.join(raw_dir, IMAGE_NAME)
    
    if os.path.exists(inbox_path):
        shutil.copy2(inbox_path, raw_path)
        print(f"[*] 已備份原始藥袋圖片至: {raw_path}")
        os.remove(inbox_path)
        print(f"[*] 已從收件夾 (inbox) 安全移除原始圖片: {inbox_path}")
    else:
        print(f"【警訊】收件夾中找不到原始圖片：{inbox_path}，可能已被處理過。")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="胃藥手動補登與個資隔離工具")
    parser.add_argument("--profile", type=str, default="myself", help="指定主體身分名稱 (預設: myself)")
    args = parser.parse_args()
    
    profile = args.profile
    db_path, inbox_dir, raw_dir, patient_id = get_paths(profile)

    print("==================================================")
    print("   Sovereign Health Agent 胃藥手動補登與個資隔離工具")
    print(f"   👤 身分設定: {profile} (ID: {patient_id})")
    print(f"   💾 資料庫: {db_path}")
    print("==================================================")
    
    # 執行資料庫補登
    if insert_weimok_to_db(db_path, patient_id):
        # 執行個資檔案移動與清理
        backup_and_cleanup_image(inbox_dir, raw_dir)
        print("==================================================")
        print("   🎉 補登與資料安全防禦隔離工作已全部圓滿完成！")
        print("==================================================")

if __name__ == "__main__":
    main()
