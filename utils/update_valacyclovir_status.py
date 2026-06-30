#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 停用/修正 Valacyclovir 用藥狀態
功能：根據病患目前實際用藥回饋，將 2018 年移植後開立的 Valacyclovir 抗病毒藥物狀態從 active 修改為 stopped，
      以維護個人主權資料庫中活性用藥清單 (Active Medication Registry) 的精確度。
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
entry_id = "MED_VAL_20180521"

def stop_valacyclovir():
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到資料庫：{db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. 先讀取原有的 FHIR JSON
        cursor.execute("SELECT fhir_resource_json, meta_data FROM MY_CLINICAL_JOURNEY WHERE entry_id = ?", (entry_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"【警訊】在資料庫中找不到 ID 為 {entry_id} 的藥物紀錄。")
            conn.close()
            return False
            
        fhir_resource = json.loads(row[0])
        meta_data = json.loads(row[1]) if row[1] else {}
        
        # 2. 修改狀態為 stopped
        old_status = fhir_resource.get("status", "unknown")
        fhir_resource["status"] = "stopped"
        
        # 在 note 中加入停止說明的歷史註記
        if "note" not in fhir_resource:
            fhir_resource["note"] = []
        fhir_resource["note"].append({
            "text": f"停藥記錄：2026-06-15 根據病患回饋，此藥物已於移植後預防期滿停用，目前非活性服用藥物。"
        })
        
        # 修改 meta_data
        meta_data["status_updated_at"] = datetime.now().isoformat()
        meta_data["update_reason"] = "Patient reported not taking this drug currently"
        
        now_str = datetime.now().isoformat()
        
        # 3. 寫回資料庫
        cursor.execute("""
        UPDATE MY_CLINICAL_JOURNEY 
        SET fhir_resource_json = ?, last_updated = ?, meta_data = ? 
        WHERE entry_id = ?
        """, (
            json.dumps(fhir_resource, ensure_ascii=False),
            now_str,
            json.dumps(meta_data, ensure_ascii=False),
            entry_id
        ))
        
        conn.commit()
        print(f"【成功】已成功將 Valacyclovir (Valtrex) 藥物狀態從 '{old_status}' 修正為 'stopped'！")
        return True
    except Exception as e:
        conn.rollback()
        print(f"【失敗】更新資料庫時發生異常：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    stop_valacyclovir()
