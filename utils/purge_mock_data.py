#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 範例資料清空工具 (Mock Data Purge Tool)
功能：當真實使用者開始使用系統並建立自己的資料後，徹底刪除預設的「虛擬病人 (PUMC_004/阿喜伯)」範例資料。
      維護本地資料庫僅保留單一真實病患資料的核心設計原則。
      內建安全鎖：只有在檢測到其他活躍病人 Profile 存在時才允許清除。
"""

import os
import sys
import sqlite3

# 設定路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))

DB_PATH = os.path.join(agent_dir, "db", "fv_patient_personal.db")

MOCK_VIRTUAL_PATIENT_ID = "PUMC_004"

def purge_mock_data():
    if not os.path.exists(DB_PATH):
        print(f"【錯誤】找不到資料庫：{DB_PATH}", file=sys.stderr)
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. 安全防鎖檢驗：確認是否有其他病人 Profile 存在
        cursor.execute("SELECT patient_id, display_name FROM MY_PROFILE WHERE patient_id != ?", (MOCK_VIRTUAL_PATIENT_ID,))
        active_profiles = cursor.fetchall()
        
        if not active_profiles:
            print("==================================================")
            print("   ⚠️  安全保護鎖觸發：未偵測到其他真實病人 Profile ⚠️")
            print("==================================================")
            print("為了防止誤刪唯一展示樣本導致系統空白，請先建立或匯入真實病人資料後，再執行本工具。")
            return False
            
        print("==================================================")
        print("   Sovereign Health Agent 範例資料安全清理工具")
        print("==================================================")
        print(f"[*] 檢測到真實病人 Profile 存在：")
        for pid, name in active_profiles:
            print(f"    - ID: {pid} | 姓名: {name}")
            
        # 2. 開始執行清除
        print(f"\n[*] 正在清除虛擬病人 ({MOCK_VIRTUAL_PATIENT_ID}/阿喜伯) 的範例資料...")
        
        # 刪除就醫與用藥紀錄
        cursor.execute("DELETE FROM MY_CLINICAL_JOURNEY WHERE patient_id = ?", (MOCK_VIRTUAL_PATIENT_ID,))
        journey_deleted = cursor.rowcount
        
        # 刪除同意書紀錄
        cursor.execute("DELETE FROM USER_CONSENTS WHERE patient_id = ?", (MOCK_VIRTUAL_PATIENT_ID,))
        consents_deleted = cursor.rowcount
        
        # 刪除個人 Profile
        cursor.execute("DELETE FROM MY_PROFILE WHERE patient_id = ?", (MOCK_VIRTUAL_PATIENT_ID,))
        profile_deleted = cursor.rowcount
        
        conn.commit()
        
        # 整理資料庫空間 (需在無 transaction 狀態下執行)
        old_isolation = conn.isolation_level
        conn.isolation_level = None
        cursor.execute("VACUUM")
        conn.isolation_level = old_isolation

        
        print(f"\n【成功】已徹底清除虛擬病人所有範例資料！")
        print(f"  - 刪除 Clinical Journey 記錄: {journey_deleted} 筆")
        print(f"  - 刪除 User Consents 記錄: {consents_deleted} 筆")
        print(f"  - 刪除 Patient Profile 記錄: {profile_deleted} 筆")
        print(f"  - 資料庫空間重組 (VACUUM) 完成")
        print("==================================================")
        print("   🎉 系統目前已切換為「純淨生產模式」，僅包含真實病人用藥與健康履歷。")
        print("==================================================")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"【錯誤】清理過程中發生異常：{str(e)}", file=sys.stderr)
        return False
    finally:
        conn.close()

def main():
    purge_mock_data()

if __name__ == "__main__":
    main()
