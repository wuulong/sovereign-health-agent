#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 健保健康存摺「其他檢驗資料」複製文字匯入工具
功能：解析從健保快易通網頁複製的檢驗資料純文字檔，轉換為 FHIR Observation 資源並存入 SQLite。
      支援單行截斷格式與多行完整格式（縮小網頁字型後複製的完整版），並具備二階段明細檔整合功能。
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


def convert_roc_to_ad(roc_date_str):
    """
    將民國日期 (如 115/05/13) 轉換為西元 ISO 日期格式 (YYYY-MM-DD)
    """
    roc_date_str = roc_date_str.strip()
    match = re.match(r'(\d{2,3})[-/](\d{1,2})[-/](\d{1,2})', roc_date_str)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    return roc_date_str

def parse_detail_file(detail_path):
    """
    解析明細檔，明細格式通常為:
    項目名稱: 完整值
    或者
    項目名稱
    完整值
    """
    if not os.path.exists(detail_path):
        return {}
        
    with open(detail_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    details_map = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        # 模式一: "項目名稱: 完整值" 或 "項目名稱： 完整值"
        match = re.match(r'^([^：:]+)[：:](.+)$', line)
        if match:
            item_name = match.group(1).strip()
            item_val = match.group(2).strip()
            details_map[item_name] = item_val
        else:
            # 模式二: 第一行是項目名稱，第二行是完整值
            if i + 1 < len(lines):
                next_line = lines[i+1].strip()
                if next_line and not re.match(r'^[^：:]+[：:]', next_line):
                    details_map[line] = next_line
                    i += 1 # 額外前進一行
        i += 1
    return details_map

def merge_details(records, details_map):
    """
    利用 prefix match 將主表紀錄中被截斷的欄位，以明細檔中的完整值替換
    """
    if not details_map:
        return records
        
    for rec in records:
        item_name = rec["item_name"]
        value = rec["value"]
        
        # 1. 處理項目名稱被截斷 (如 "Beta-2 Microglo ...")
        if "..." in item_name:
            clean_prefix = item_name.replace("...", "").strip()
            # 在明細中搜尋以此 prefix 開頭的項目
            for full_name, full_val in details_map.items():
                if full_name.startswith(clean_prefix):
                    print(f"【對合成功】項目名稱對齊: '{item_name}' -> '{full_name}'")
                    rec["item_name"] = full_name
                    # 如果結果值也被截斷，同步從明細檔更新結果值
                    if "..." in value:
                        print(f"【對合成功】結果值對齊: '{value}' -> '{full_val}'")
                        rec["value"] = full_val
                    break
                    
        # 2. 處理項目名稱完整但結果值被截斷 (如 "Electrophoresis" 的 "Serum pro ...")
        elif "..." in value:
            # 在明細中尋找該項目名稱
            if item_name in details_map:
                print(f"【對合成功】結果值對齊 ({item_name}): '{value}' -> '{details_map[item_name]}'")
                rec["value"] = details_map[item_name]
            else:
                # 模糊比對項目名稱
                for full_name, full_val in details_map.items():
                    if item_name.startswith(full_name) or full_name.startswith(item_name):
                        print(f"【對合成功】模糊結果值對齊 ({item_name} ~ {full_name}): '{value}' -> '{full_val}'")
                        rec["value"] = full_val
                        break
                        
    return records

def parse_lab_data_file(file_path):
    """
    解析複製的文字格式，自動判定是「單行截斷格式」或「多行展開格式」。
    """
    if not os.path.exists(file_path):
        print(f"【錯誤】找不到檔案：{file_path}", file=sys.stderr)
        return []

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    records = []
    i = 0
    
    # 格式自動偵測：檢查第一個包含日期的行分割後有幾個部分
    is_multiline_format = False
    for line in lines:
        cleaned = line.strip()
        if re.match(r'^\d{2,3}[-/]\d{1,2}[-/]\d{1,2}', cleaned):
            parts = [p.strip() for p in re.split(r'\t|\s{2,}', cleaned) if p.strip()]
            if len(parts) == 1:
                is_multiline_format = True
            break

    if is_multiline_format:
        print("[*] 偵測為多行展開格式 (未截斷完整複製版)...")
        while i < len(lines):
            line = lines[i].strip()
            # 尋找以民國年為開頭的列，如 115/05/13
            if re.match(r'^\d{2,3}[-/]\d{1,2}[-/]\d{1,2}', line):
                # 確保後面有足夠的行 (至少13行以獲取完整記錄欄位)
                if i + 13 < len(lines):
                    date_str = line
                    code = lines[i+1].strip()
                    name_line = lines[i+3].strip()
                    val_str = lines[i+4].strip()
                    unit = lines[i+6].strip()
                    ref = lines[i+8].strip()
                    hospital = lines[i+10].strip()
                    
                    # 處理醫囑與項目名稱分割
                    name_parts = [p.strip() for p in re.split(r'\t|\s{2,}', name_line) if p.strip()]
                    item_name = name_parts[1] if len(name_parts) >= 2 else name_parts[0] if name_parts else "Unknown"
                    
                    records.append({
                        "roc_date": date_str,
                        "ad_date": convert_roc_to_ad(date_str),
                        "item_name": item_name,
                        "value": val_str,
                        "unit": unit,
                        "reference_range": ref,
                        "hospital": hospital,
                        "code": code
                    })
                    i += 14  # 穩定步進 14 行
                    continue
            i += 1
    else:
        print("[*] 偵測為單行截斷格式 (簡便複製版)...")
        while i < len(lines):
            line = lines[i].strip()
            # 尋找以民國年為開頭的列，如 115/05/13
            if re.match(r'^\d{2,3}[-/]\d{1,2}[-/]\d{1,2}', line):
                # 以 Tab 或多個空白分割
                parts = [p.strip() for p in re.split(r'\t|\s{2,}', line) if p.strip()]
                if len(parts) >= 2:
                    date_str = parts[0]
                    item_name = parts[1]
                    
                    # 尋找結果值（在下一行或隨後非空行中）
                    val_str = ""
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if next_line:
                            val_str = next_line
                            break
                        j += 1
                    
                    if val_str:
                        records.append({
                            "roc_date": date_str,
                            "ad_date": convert_roc_to_ad(date_str),
                            "item_name": item_name,
                            "value": val_str
                        })
                        i = j
            i += 1
        
    return records

def import_to_database(records, db_path, patient_id):
    """
    將解析的記錄轉換為 FHIR Observation 並存入 SQLite
    """
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫：{db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    imported_count = 0
    now_str = datetime.now().isoformat()
    
    for idx, rec in enumerate(records):
        # 建立穩定的 entry_id，結合日期與項目名稱的雜湊或縮寫，防止重複匯入
        safe_item_name = re.sub(r'[^a-zA-Z0-9_]', '_', rec['item_name'])
        entry_id = f"OBS_LAB_{rec['ad_date'].replace('-', '')}_{safe_item_name}"
        
        # 判定數值類型
        value_quantity = None
        value_string = None
        
        # 檢查是否包含 "..." (代表明細檔也未成功修補)
        is_truncated = "..." in rec['item_name'] or "..." in rec['value']
        
        try:
            # 嘗試轉換為浮點數
            val_float = float(rec['value'])
            value_quantity = {
                "value": val_float,
                "system": "http://unitsofmeasure.org"
            }
        except ValueError:
            # 非數值，存為字串
            value_string = rec['value']
            
        # 建立 FHIR Observation 資源
        fhir_resource = {
            "resourceType": "Observation",
            "id": entry_id,
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "laboratory",
                            "display": "Laboratory"
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "display": rec['item_name']
                    }
                ],
                "text": rec['item_name']
            },
            "subject": {
                "reference": f"Patient/{patient_id}-DEID"
            },
            "effectiveDateTime": f"{rec['ad_date']}T00:00:00+08:00",
            "note": [
                {
                    "text": "由健康存摺複製文字匯入。已自動進行民國年轉換。"
                }
            ]
        }
        
        # 加上額外醫令代碼欄位 (如果是多行格式)
        if "code" in rec and rec["code"]:
            fhir_resource["code"]["coding"].append({
                "system": "http://substances.nhia.gov.tw",
                "code": rec["code"],
                "display": rec["item_name"]
            })
            
        if value_quantity:
            if "unit" in rec and rec["unit"]:
                value_quantity["unit"] = rec["unit"]
            fhir_resource["valueQuantity"] = value_quantity
        else:
            fhir_resource["valueString"] = value_string
            
        if "reference_range" in rec and rec["reference_range"]:
            fhir_resource["referenceRange"] = [
                {
                    "text": rec["reference_range"]
                }
            ]
            
        meta_obj = {"source": "MyHealthBankCopiedText", "roc_date": rec['roc_date']}
        if "hospital" in rec and rec["hospital"]:
            meta_obj["hospital"] = rec["hospital"]
            
        if is_truncated:
            meta_obj["is_truncated"] = True
            fhir_resource["note"].append({"text": "注意：本檢驗資料包含被截斷的欄位，建議補全明細。"})
            
        # 存入資料庫
        cursor.execute("""
        INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry_id, 
            patient_id, 
            "Observation", 
            json.dumps(fhir_resource, ensure_ascii=False), 
            now_str, 
            json.dumps(meta_obj, ensure_ascii=False)
        ))
        imported_count += 1
        
    conn.commit()
    conn.close()
    print(f"【成功】已成功匯入 {imported_count} 筆檢驗檢查觀測指標 (FHIR Observation) 至本地庫！")
    return True

def backup_and_cleanup(file_name, inbox_dir, raw_dir, detail_file_name=None):
    """
    備份原始檔案及明細檔案到 data/raw/，並從 data/inbox/ 物理移除
    """
    os.makedirs(raw_dir, exist_ok=True)
    
    # 處理主檔案
    inbox_path = os.path.join(inbox_dir, file_name)
    raw_path = os.path.join(raw_dir, file_name)
    
    if os.path.exists(inbox_path):
        shutil.copy2(inbox_path, raw_path)
        print(f"[*] 備份原始檔案至: {raw_path}")
        os.remove(inbox_path)
        print(f"[*] 已安全移除收件夾原始檔案: {inbox_path}")
        
    # 處理明細檔案
    if detail_file_name:
        detail_inbox_path = os.path.join(inbox_dir, detail_file_name)
        detail_raw_path = os.path.join(raw_dir, detail_file_name)
        
        if os.path.exists(detail_inbox_path):
            shutil.copy2(detail_inbox_path, detail_raw_path)
            print(f"[*] 備份明細檔案至: {detail_raw_path}")
            os.remove(detail_inbox_path)
            print(f"[*] 已安全移除收件夾明細檔案: {detail_inbox_path}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="健保健康存摺「其他檢驗資料」複製文字匯入工具")
    parser.add_argument("file_name", type=str, help="收件匣 (inbox) 中的原始檔案名稱")
    parser.add_argument("--profile", type=str, default="myself", help="指定主體身分名稱 (預設: myself)")
    args = parser.parse_args()
    
    file_name = args.file_name
    profile = args.profile
    
    db_path, inbox_dir, raw_dir, patient_id = get_paths(profile)
    inbox_file_path = os.path.join(inbox_dir, file_name)
    
    if not os.path.exists(inbox_file_path):
        # 如果是絕對路徑，轉換為檔名
        if os.path.isabs(file_name):
            inbox_file_path = file_name
            file_name = os.path.basename(file_name)
            
    print(f"==================================================")
    print(f"   Sovereign Health Agent 檢驗資料複製文字匯入器")
    print(f"   👤 身分設定: {profile} (ID: {patient_id})")
    print(f"   💾 資料庫: {db_path}")
    print(f"==================================================")
    print(f"[*] 正在解析檔案: {inbox_file_path}")
    
    records = parse_lab_data_file(inbox_file_path)
    if not records:
        print("【失敗】未解析出任何檢驗記錄，請檢查檔案格式！")
        sys.exit(1)
        
    print(f"[*] 解析完成。共偵測到 {len(records)} 筆檢驗指標。")
    
    # 尋找是否有對應的明細檔，例如：主檔 IN_20260613.md -> 明細檔 IN_20260613_details.md 或 .txt
    base_name, _ = os.path.splitext(file_name)
    detail_file_name = None
    details_map = {}
    
    for ext in ['.md', '.txt']:
        potential_detail = f"{base_name}_details{ext}"
        potential_path = os.path.join(inbox_dir, potential_detail)
        if os.path.exists(potential_path):
            detail_file_name = potential_detail
            print(f"[*] 偵測到補全明細檔: {potential_path}")
            details_map = parse_detail_file(potential_path)
            break
            
    if details_map:
        print(f"[*] 開始進行二階段明細比對與欄位整合...")
        records = merge_details(records, details_map)
        
    # 統計是否仍有未修補的截斷欄位
    truncated_items = [r['item_name'] for r in records if "..." in r['item_name'] or "..." in r['value']]
    if truncated_items:
        print(f"【提醒】以下項目仍存在網頁截斷，建議點擊健康存摺網頁取得完整文字並貼至明細檔修補：")
        for t_item in truncated_items[:5]:
            print(f"  - {t_item}")
        if len(truncated_items) > 5:
            print(f"  - ... (共 {len(truncated_items)} 項被截斷)")
            
    # 進行資料庫匯入
    success = import_to_database(records, db_path, patient_id)
    
    # 進行安全備份與清理
    if success:
        backup_and_cleanup(file_name, inbox_dir, raw_dir, detail_file_name)
        print("==================================================")
        print("   🎉 檢驗資料匯入、備份與清理作業已全部圓滿完成！")
        print("==================================================")
    else:
        print("【錯誤】資料庫匯入失敗，未執行備份與清理。")

if __name__ == "__main__":
    main()
