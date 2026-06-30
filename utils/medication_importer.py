#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 健保健康存摺「藥品醫囑資料」複製文字匯入工具
功能：解析從健保快易通網頁複製的用藥明細純文字檔，轉換為 FHIR MedicationRequest 資源並存入 SQLite。
      處理完成後，依據安全規範備份原始檔案至 data/raw/，並移除 data/inbox/ 的原始檔。
"""

import os
import sys
import re
import json
import shutil
import sqlite3
from datetime import datetime

# 設定路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))

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


def parse_medication_file(file_path):
    """
    解析用藥紀錄純文字檔，提取多個藥品醫囑資料
    """
    if not os.path.exists(file_path):
        print(f"【錯誤】找不到檔案：{file_path}", file=sys.stderr)
        return []

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    medications = []
    i = 0
    current_med = {}
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line == "藥品醫囑資料":
            i += 1
            continue
            
        if line == "醫囑代碼" and i + 1 < len(lines):
            # 偵測到新的藥物代碼。若先前已有累積一個完整藥物資料，則先將其存檔
            if current_med and "code" in current_med:
                medications.append(current_med)
            current_med = {"code": lines[i+1].strip()}
            i += 2
            continue
        elif line == "醫囑名稱" and i + 1 < len(lines):
            current_med["name"] = lines[i+1].strip()
            i += 2
            continue
        elif line == "藥品藥理分類" and i + 1 < len(lines):
            current_med["category"] = lines[i+1].strip()
            i += 2
            continue
        elif line == "藥品用量" and i + 1 < len(lines):
            try:
                current_med["quantity"] = float(lines[i+1].strip())
            except ValueError:
                current_med["quantity"] = lines[i+1].strip()
            i += 2
            continue
        elif line == "給藥日數" and i + 1 < len(lines):
            try:
                current_med["days"] = int(lines[i+1].strip())
            except ValueError:
                current_med["days"] = lines[i+1].strip()
            i += 2
            continue
            
        i += 1
        
    # 加入最後一個未完成的藥物
    if current_med and "code" in current_med:
        medications.append(current_med)
        
    return medications

def import_to_database(medications, file_date, db_path, patient_id):
    """
    將用藥資料轉換為 FHIR MedicationRequest 並寫入 SQLite
    """
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫：{db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    imported_count = 0
    now_str = datetime.now().isoformat()
    
    for rec in medications:
        # 建立穩定的 entry_id，結合日期與健保代碼，防範重複匯入
        entry_id = f"MED_REQ_{file_date.replace('-', '')}_{rec['code']}"
        
        # 建立 FHIR MedicationRequest 資源
        fhir_resource = {
            "resourceType": "MedicationRequest",
            "id": entry_id,
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://substances.nhia.gov.tw",
                        "code": rec["code"],
                        "display": rec["name"]
                    }
                ],
                "text": rec["name"]
            },
            "subject": {
                "reference": f"Patient/{patient_id}-DEID"
            },
            "authoredOn": f"{file_date}T00:00:00+08:00",
            "dispenseRequest": {
                "expectedSupplyDuration": {
                    "value": rec.get("days", 1),
                    "unit": "days",
                    "system": "http://unitsofmeasure.org",
                    "code": "d"
                },
                "quantity": {
                    "value": rec.get("quantity", 0),
                    "system": "http://unitsofmeasure.org"
                }
            },
            "note": [
                {
                    "text": f"藥品分類：{rec.get('category', '一般藥物')}"
                }
            ]
        }
        
        # 存入資料庫
        cursor.execute("""
        INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry_id, 
            patient_id, 
            "MedicationRequest", 
            json.dumps(fhir_resource, ensure_ascii=False), 
            now_str, 
            json.dumps({"source": "MyHealthBankCopiedMedication", "category": rec.get('category')}, ensure_ascii=False)
        ))
        imported_count += 1
        
    conn.commit()
    conn.close()
    print(f"【成功】已成功匯入 {imported_count} 筆藥品醫囑 (FHIR MedicationRequest) 至本地庫！")
    return True

def backup_and_cleanup(file_name, inbox_dir, raw_dir):
    """
    備份原始檔案到 data/raw/，並從 data/inbox/ 物理移除
    """
    os.makedirs(raw_dir, exist_ok=True)
    
    inbox_path = os.path.join(inbox_dir, file_name)
    raw_path = os.path.join(raw_dir, file_name)
    
    if os.path.exists(inbox_path):
        shutil.copy2(inbox_path, raw_path)
        print(f"[*] 備份原始檔案至: {raw_path}")
        os.remove(inbox_path)
        print(f"[*] 已安全移除收件夾原始檔案: {inbox_path}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="健保健康存摺「藥品醫囑資料」複製文字匯入工具")
    parser.add_argument("file_name", type=str, help="收件匣 (inbox) 中的原始檔案名稱")
    parser.add_argument("--profile", type=str, default="myself", help="指定主體身分名稱 (預設: myself)")
    args = parser.parse_args()
    
    file_name = args.file_name
    profile = args.profile
    
    db_path, inbox_dir, raw_dir, patient_id = get_paths(profile)
    inbox_file_path = os.path.join(inbox_dir, file_name)
    
    if not os.path.exists(inbox_file_path):
        if os.path.isabs(file_name):
            inbox_file_path = file_name
            file_name = os.path.basename(file_name)
            
    print(f"==================================================")
    print(f"   Sovereign Health Agent 藥品醫囑複製文字匯入器")
    print(f"   👤 身分設定: {profile} (ID: {patient_id})")
    print(f"   💾 資料庫: {db_path}")
    print(f"==================================================")
    print(f"[*] 正在解析檔案: {inbox_file_path}")
    
    # 從檔名解析日期，預設為今日
    file_date = datetime.now().strftime("%Y-%m-%d")
    match = re.search(r'(\d{4})(\d{2})(\d{2})', file_name)
    if match:
        file_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        
    medications = parse_medication_file(inbox_file_path)
    if not medications:
        print("【失敗】未解析出任何藥物紀錄，請檢查檔案格式！")
        sys.exit(1)
        
    print(f"[*] 解析完成。共偵測到 {len(medications)} 筆用藥指令。日期定錨於: {file_date}")
    for idx, med in enumerate(medications):
        print(f"  - [{idx+1}] 代碼: {med['code']} | 名稱: {med['name']} | 用量: {med['quantity']} | 日數: {med['days']}")
        
    # 進行資料庫匯入
    success = import_to_database(medications, file_date, db_path, patient_id)
    
    # 進行安全備份與清理
    if success:
        backup_and_cleanup(file_name, inbox_dir, raw_dir)
        print("==================================================")
        print("   🎉 藥品資料匯入、備份與清理作業已全部圓滿完成！")
        print("==================================================")
    else:
        print("【錯誤】資料庫匯入失敗，未執行備份與清理。")

if __name__ == "__main__":
    main()
