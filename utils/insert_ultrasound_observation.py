# -*- coding: utf-8 -*-
"""
Sovereign Health Agent - 寫入超音波個人觀察數據至 SQLite 資料庫
功能：將影像 03 與影像 04 的 OpenCV + EasyOCR 逆向分析結果，封裝為 FHIR R4 Patient-Reported Observation 格式，寫入本地 db。
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = '/Users/username/github/bmad-pa/private_data/sovereign-health/db/instances/myself/fv_patient_personal.db'
SAMPLE_DIR = '/Users/username/Downloads/MHB_115XXXX_115XXXX_1'

def create_observation_fhir(obs_id, val_num, img_num, caliper_pos, note_text):
    """構造符合 HL7 FHIR R4 規範的 Patient-Reported Observation 資源"""
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
    
    obs = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey"
                    },
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "US",
                        "display": "Ultrasound"
                    }
                ],
                "text": "Patient Reported Ultrasound Measurement"
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "11524-6",
                    "display": "Abdomen Ultrasound Study"
                }
            ],
            "text": "腹部超音波量測個人觀察"
        },
        "subject": {
            "reference": "Patient/PUMC_001",
            "display": "阿喜伯"
        },
        "effectiveDateTime": "202X-XX-XX",
        "issued": now_str,
        "performer": [
            {
                "reference": "Patient/PUMC_001",
                "display": "阿喜伯"
            }
        ],
        "valueQuantity": {
            "value": val_num,
            "unit": "cm",
            "system": "http://unitsofmeasure.org",
            "code": "cm"
        },
        "bodySite": {
            "text": "腹部 (Abdomen)"
        },
        "method": {
            "text": "本地 AI 影像逆向工程 (OpenCV Caliper 偵測 + EasyOCR 數據提取)"
        },
        "device": {
            "display": "Sovereign Health Agent Local AI Parser"
        },
        "note": [
            {
                "text": f"[Patient Observation] {note_text} (偵測切面為 image_{img_num}.png，游標座標：{caliper_pos})"
            }
        ],
        "derivedFrom": [
            {
                "reference": "DocumentReference/art-us-202X_XX_XX",
                "display": "原始健康存摺超音波 DICOM 影像包"
            }
        ]
    }
    return obs

def seed_ultrasound_observations():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    artifact_id = "art-us-202X_XX_XX"

    try:
        # 1. 寫入原始資料定錨表 (RAW_ARTIFACTS)
        print("1. Seeding RAW_ARTIFACTS table...")
        cursor.execute("""
            INSERT OR REPLACE INTO RAW_ARTIFACTS (
                artifact_id, patient_id, original_filename, storage_path, mime_type, imported_at, meta_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            artifact_id,
            "PUMC_001",
            "MHB_115XXXX_115XXXX_1.zip",
            SAMPLE_DIR,
            "application/zip",
            now_str,
            json.dumps({"description": "某醫院 202X-XX-XX 腹部超音波 DICOM 原始影像包"})
        ))

        # 2. 構造 Observation FHIR 數據
        print("2. Constructing FHIR Observations...")
        obs_03 = create_observation_fhir(
            obs_id="OBS-US-MEASURE-202X_XX_XX-03",
            val_num=0.9,
            img_num="03",
            caliper_pos="(718, 294)",
            note_text="量測值為 0.9 cm。此量測點位於成像區右上方，通常為針對微小膽結石、膽囊息肉或肝臟內的水泡 (囊腫) 進行長度記錄。"
        )

        obs_04 = create_observation_fhir(
            obs_id="OBS-US-MEASURE-202X_XX_XX-04",
            val_num=0.8,
            img_num="04",
            caliper_pos="(125, 349)",
            note_text="量測值為 0.8 cm。量測點位於左側量測面板區，右上方偵測到燒錄標籤 (X=351, Y=239)，代表醫師特別量測並追蹤 0.8 公分的結節或組織大小。"
        )

        # 3. 寫入病患醫療歷程表 (MY_CLINICAL_JOURNEY)
        print("3. Seeding MY_CLINICAL_JOURNEY table...")
        for obs in [obs_03, obs_04]:
            cursor.execute("""
                INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (
                    entry_id, patient_id, artifact_id, resource_type, fhir_resource_json, last_updated, meta_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                obs["id"],
                "PUMC_001",
                artifact_id,
                "Observation",
                json.dumps(obs, ensure_ascii=False),
                now_str,
                json.dumps({"patient_reported": True, "source": "local_ai_parser"})
            ))

        conn.commit()
        print("\n🎉 Seeding successfully completed!")
        print(f"  - Anchored RAW_ARTIFACTS entry_id: {artifact_id}")
        print(f"  - Seeded MY_CLINICAL_JOURNEY entry_id: OBS-US-MEASURE-202X_XX_XX-03 (0.9 cm)")
        print(f"  - Seeded MY_CLINICAL_JOURNEY entry_id: OBS-US-MEASURE-202X_XX_XX-04 (0.8 cm)")
        
    except Exception as e:
        print(f"Seeding failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    seed_ultrasound_observations()
