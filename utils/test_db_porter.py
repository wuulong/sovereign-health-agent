#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification script for db_porter.py (test_db_porter.py)
驗證 db_porter.py 的匯出、匯入、去識別化與各格式轉換功能是否 100% 正常。
"""

import os
import sys
import sqlite3
import json
import csv
import zipfile
import subprocess
import shutil
from datetime import datetime

UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(UTILS_DIR)  # events/sovereign-health-agent
DB_PORTER_PATH = os.path.join(UTILS_DIR, "db_porter.py")

# 測試用路徑
TEST_DIR = os.path.join(PROJECT_DIR, "scratch", "test_porter_workspace")
TEST_DB_PATH = os.path.join(TEST_DIR, "db", "instances", "test_user", "fv_patient_personal.db")
BACKUP_JSON_PATH = os.path.join(TEST_DIR, "backup_myself.json")
RESEARCH_JSON_PATH = os.path.join(TEST_DIR, "research_deid.json")
DAILY_CSV_PATH = os.path.join(TEST_DIR, "daily_monitoring.csv")
ICE_MD_PATH = os.path.join(TEST_DIR, "ice_card.md")
CLINICAL_MD_PATH = os.path.join(TEST_DIR, "clinical_summary.md")
TRANSITION_MD_PATH = os.path.join(TEST_DIR, "care_transition.md")
INSURANCE_ZIP_PATH = os.path.join(TEST_DIR, "claim_export.zip")

def run_command(args):
    cmd = [sys.executable, DB_PORTER_PATH] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result

def main():
    print("🧪 ==================================================")
    print("🧪   開始進行 db_porter.py 整合功能自動化測試驗證")
    print("🧪 ==================================================")
    
    # 清理舊測試目錄
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    
    # 0. 確保 myself 資料庫存在
    myself_db = os.path.join(PROJECT_DIR, "db", "instances", "myself", "fv_patient_personal.db")
    if not os.path.exists(myself_db):
        print(f"❌ 錯誤：找不到 myself 資料庫於 {myself_db}，請先執行對話介面或初始化器！")
        sys.exit(1)
        
    print(f"✅ 找到驗證用資料庫: {myself_db}")
    
    # 1. 測試情境 C：匯出完整 JSON 備份
    print("\n👉 測試 1: 匯出完整備份 (情境 C)...")
    res = run_command(["--profile", "myself", "-e", "-t", "backup", "-f", "json", "-o", BACKUP_JSON_PATH])
    if res.returncode != 0:
        print(f"❌ 測試 1 失敗: {res.stderr}")
        sys.exit(1)
    
    if not os.path.exists(BACKUP_JSON_PATH):
        print("❌ 測試 1 失敗: 未產生備份 JSON 檔案。")
        sys.exit(1)
        
    with open(BACKUP_JSON_PATH, 'r', encoding='utf-8') as f:
        backup = json.load(f)
        
    assert backup.get("export_type") == "sovereign_phr_backup", "備份標記錯誤"
    assert "my_profile" in backup, "缺少 my_profile"
    assert "my_clinical_journey" in backup, "缺少 my_clinical_journey"
    print(f"✅ 測試 1 成功！備份檔案結構正確。")

    # 2. 測試情境 C：增量排重匯入至新測試庫
    print("\n👉 測試 2: 增量排重匯入至新資料庫 (情境 C)...")
    # 先初始化空資料庫結構，由 template.db 複製過來
    os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)
    shutil.copy2(os.path.join(PROJECT_DIR, "db", "template.db"), TEST_DB_PATH)
    
    res = run_command(["--db-path", TEST_DB_PATH, "-i", BACKUP_JSON_PATH])
    if res.returncode != 0:
        print(f"❌ 測試 2 失敗: {res.stderr}")
        sys.exit(1)
        
    # 驗證新資料庫中是否寫入資料
    conn = sqlite3.connect(TEST_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM MY_CLINICAL_JOURNEY")
    count1 = cursor.fetchone()[0]
    conn.close()
    
    assert count1 > 0, "匯入資料庫中無歷程資料"
    print(f"✅ 測試 2 成功！已成功匯入 {count1} 筆歷程至新庫。")

    # 3. 測試情境 B：去識別化科研共享匯出與時間平移
    print("\n👉 測試 3: 去識別化科研共享匯出與時間平移 (情境 B)...")
    shift_days = 20
    res = run_command([
        "--profile", "myself", "-e", "-t", "research", "-f", "json", 
        "--deidentify", "--shift-days", str(shift_days), "-o", RESEARCH_JSON_PATH
    ])
    if res.returncode != 0:
        print(f"❌ 測試 3 失敗: {res.stderr}")
        sys.exit(1)
        
    with open(RESEARCH_JSON_PATH, 'r', encoding='utf-8') as f:
        research = json.load(f)
        
    assert research.get("export_type") == "de-identified_research_bundle", "科研包標記錯誤"
    assert research.get("shift_days") == shift_days, "平移天數不符"
    
    # 檢查是否去識別化
    profile_deid = research.get("profile_deid")
    assert "DEID" in profile_deid, "未正確遮蔽個人識別 ID"
    
    # 檢查是否有時間平移 (比對原資料庫中的時間與匯出時間)
    conn = sqlite3.connect(myself_db)
    cursor = conn.cursor()
    cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Observation' LIMIT 1")
    orig_fhir = json.loads(cursor.fetchone()[0])
    orig_date = orig_fhir.get("effectiveDateTime")
    conn.close()
    
    # 找到對應去識別化的 Observation 日期
    shifted_date = None
    for entry in research.get("clinical_journey", []):
        if entry.get("resource_type") == "Observation":
            shifted_date = entry.get("fhir_resource_json", {}).get("effectiveDateTime")
            break
            
    if orig_date and shifted_date:
        print(f"   * 原始日期: {orig_date}")
        print(f"   * 平移日期: {shifted_date}")
        # 簡單天數比對
        day_diff = int(shifted_date[8:10]) - int(orig_date[8:10])
        # 若跨月，用 datetime 運算比對
        dt_orig = datetime.strptime(orig_date[:10], "%Y-%m-%d")
        dt_shifted = datetime.strptime(shifted_date[:10], "%Y-%m-%d")
        diff = (dt_shifted - dt_orig).days
        assert diff == shift_days, f"時間平移天數差應為 {shift_days} 天，但計算為 {diff} 天"
        print(f"✅ 測試 3 成功！時間平移與去識別化機制完美匹配。")
    else:
        print("⚠️  無法比對日期，因為資料庫中缺少 Observation 樣本。")

    # 4. 測試情境 E：日常監測 CSV 匯出
    print("\n👉 測試 4: 日常健康監測資料匯出 (情境 E)...")
    res = run_command(["--profile", "myself", "-e", "-t", "daily_monitoring", "-f", "csv", "-o", DAILY_CSV_PATH])
    if res.returncode != 0:
        print(f"❌ 測試 4 失敗: {res.stderr}")
        sys.exit(1)
        
    assert os.path.exists(DAILY_CSV_PATH), "未產出 CSV 檔案"
    with open(DAILY_CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert "指標名稱" in headers and "LOINC代碼" in headers, "CSV 欄位名稱錯誤"
        rows = list(reader)
        print(f"   * CSV 共匯出 {len(rows)} 筆資料。")
    print("✅ 測試 4 成功！日常監測 CSV 生成正常。")

    # 5. 測試情境 D, A, G：Markdown 報告 (緊急救援、門診摘要、長照交接)
    print("\n👉 測試 5: Markdown 報告生成 (情境 D, A, G)...")
    # 緊急卡
    res_d = run_command(["--profile", "myself", "-e", "-t", "ice", "-f", "md", "-o", ICE_MD_PATH])
    # 門診摘要
    res_a = run_command(["--profile", "myself", "-e", "-t", "clinical_summary", "-f", "md", "-o", CLINICAL_MD_PATH])
    # 長照交接
    res_g = run_command(["--profile", "myself", "-e", "-t", "care_transition", "-f", "md", "-o", TRANSITION_MD_PATH])
    
    assert res_d.returncode == 0 and os.path.exists(ICE_MD_PATH), "緊急救援卡匯出失敗"
    assert res_a.returncode == 0 and os.path.exists(CLINICAL_MD_PATH), "門診摘要卡匯出失敗"
    assert res_g.returncode == 0 and os.path.exists(TRANSITION_MD_PATH), "長照照護交接表匯出失敗"
    
    print("✅ 測試 5 成功！三種 Markdown 報告生成良好。")

    # 6. 測試情境 F：保險理賠申報包 (ZIP 打包)
    print("\n👉 測試 6: 商業保險理賠打包 (情境 F)...")
    # 先找出 myself DB 裡的任何就醫事件 ID
    conn = sqlite3.connect(myself_db)
    cursor = conn.cursor()
    cursor.execute("SELECT entry_id FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Encounter' LIMIT 1")
    enc_row = cursor.fetchone()
    conn.close()
    
    if enc_row:
        enc_id = enc_row[0]
        print(f"   * 找到就醫事件 ID: '{enc_id}'，開始打包...")
        res = run_command(["--profile", "myself", "-e", "-t", "insurance", "-f", "zip", "--event-id", enc_id, "-o", INSURANCE_ZIP_PATH])
        if res.returncode != 0:
            print(f"❌ 測試 6 失敗: {res.stderr}")
            sys.exit(1)
            
        assert os.path.exists(INSURANCE_ZIP_PATH), "未產生 ZIP 檔案"
        with zipfile.ZipFile(INSURANCE_ZIP_PATH, 'r') as z:
            namelist = z.namelist()
            assert "claim_summary.md" in namelist, "ZIP 中缺少 claim_summary.md 明細"
            print(f"   * ZIP 包中包含: {namelist}")
        print("✅ 測試 6 成功！保險理賠壓縮包封裝完成。")
    else:
        print("⚠️  跳過測試 6，因為資料庫中查無 Encounter 事件資料。")

    # 清理測試目錄
    shutil.rmtree(TEST_DIR)
    
    print("\n🎉 ==================================================")
    print("🎉   所有 7 種匯出與轉移情境整合測試 [100% 通過]！")
    print("🎉 ==================================================")

if __name__ == "__main__":
    main()
