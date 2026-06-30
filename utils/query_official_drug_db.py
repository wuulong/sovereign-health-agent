#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 台灣官方藥物與健保資料庫實時查詢/同步工具
功能：直接連接台灣健保署及食藥署 (TFDA) 的官方開放資料庫 (Open Data) 直鏈，
      實時下載並過濾查詢特定藥物之健保支付價、生效日期、藥物許可證與適應症。
      完全採用 Python 內建庫實作，不含任何 Mock 假資料，確保資料真實性。
"""

import os
import sys
import csv
import json
import urllib.request
import argparse
import zipfile

# 官方數據庫 Open Data 直鏈端點
NHI_DRUG_CSV_URL = "https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-E41001-001"
TFDA_DRUG_JSON_URL = "https://data.fda.gov.tw/data/opendata/export/37/json"

# 本地暫存路徑
script_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.abspath(os.path.join(script_dir, ".."))
CACHE_DIR = os.path.join(agent_dir, "data", "open-data", "medication")

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)

def query_nhi_official(query_str, force_download=False):
    """
    實時查詢健保署官方「健保用藥品項與支付價格」資料庫。
    """
    ensure_cache_dir()
    local_csv_path = os.path.join(CACHE_DIR, "nhi_drugs_latest.csv")
    
    # 若本地無暫存或強制更新，則進行下載
    if force_download or not os.path.exists(local_csv_path):
        print(f"[*] 正在從健保署官方開放平台下載最新藥價檔...")
        print(f"🔗 URL: {NHI_DRUG_CSV_URL}")
        try:
            urllib.request.urlretrieve(NHI_DRUG_CSV_URL, local_csv_path)
            print(f"🟢 官方資料下載完成！已暫存至: {local_csv_path}")
        except Exception as e:
            print(f"❌ 錯誤：無法連接健保署官方伺服器下載資料 ({e})", file=sys.stderr)
            return False

    print(f"🔍 正在篩選健保署官方資料庫，關鍵字：'{query_str}'...")
    print("-" * 85)
    print(f"{'健保代碼':<12} | {'中文品名':<25} | {'英文品名':<25} | {'支付價格':<10} | {'生效日期'}")
    print("-" * 85)
    
    matched_count = 0
    try:
        with open(local_csv_path, mode='r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.reader(f)
            # 讀取標頭
            header = next(reader, None)
            
            # 預設索引 (根據 2026 年最新結構)
            nhi_code_idx, eng_name_idx, chi_name_idx, price_idx, start_date_idx, component_idx = 1, 2, 3, 8, 9, 4
            
            if header:
                # 嘗試動態映射標頭欄位
                try:
                    nhi_code_idx = header.index("藥品代號")
                except ValueError: pass
                try:
                    chi_name_idx = header.index("藥品中文名稱")
                except ValueError: pass
                try:
                    eng_name_idx = header.index("藥品英文名稱")
                except ValueError: pass
                try:
                    price_idx = header.index("支付價")
                except ValueError: pass
                try:
                    start_date_idx = header.index("有效起日")
                except ValueError: pass
                try:
                    component_idx = header.index("成分")
                except ValueError: pass
            
            for row in reader:
                if len(row) <= max(nhi_code_idx, chi_name_idx, eng_name_idx, price_idx, start_date_idx, component_idx):
                    continue
                nhi_code = row[nhi_code_idx]
                chi_name = row[chi_name_idx]
                eng_name = row[eng_name_idx]
                price = row[price_idx]
                start_date = row[start_date_idx]
                component = row[component_idx]
                
                # 模糊比對中文名、英文名、成分學名、或健保代碼
                if (query_str.lower() in nhi_code.lower() or 
                    query_str.lower() in chi_name.lower() or 
                    query_str.lower() in eng_name.lower() or
                    query_str.lower() in component.lower()):
                    
                    print(f"{nhi_code:<12} | {chi_name[:22]:<25} | {eng_name[:22]:<25} | {price:<10} | {start_date}")
                    matched_count += 1
                    if matched_count >= 50:
                        print(f"\n[⚠️ 提示] 已篩選出前 50 筆符合之結果，其餘項目已自動隱藏。")
                        break
    except Exception as e:
        print(f"❌ 錯誤：解析健保署資料檔失敗 ({e})", file=sys.stderr)
        return False
        
    print("-" * 85)
    print(f"✨ 共計尋獲 {matched_count} 筆符合健保給付規定之藥物品項。")
    return True

def query_tfda_official(query_str, force_download=False):
    """
    實時查詢食藥署 (TFDA) 官方「全部藥品許可證」資料庫。
    """
    ensure_cache_dir()
    local_json_path = os.path.join(CACHE_DIR, "tfda_drugs_latest.json")
    
    if force_download or not os.path.exists(local_json_path):
        print(f"[*] 正在從食藥署 (TFDA) 官方開放平台下載全部藥品許可證資料集...")
        print(f"🔗 URL: {TFDA_DRUG_JSON_URL}")
        try:
            req = urllib.request.Request(
                TFDA_DRUG_JSON_URL, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                with open(local_json_path, 'wb') as out_file:
                    out_file.write(response.read())
            print(f"🟢 官方資料下載完成！已暫存至: {local_json_path}")
        except Exception as e:
            print(f"❌ 錯誤：無法連接食藥署官方伺服器下載資料 ({e})", file=sys.stderr)
            return False

    # 檢查是否為 zip 檔案並自動解壓縮
    if os.path.exists(local_json_path) and zipfile.is_zipfile(local_json_path):
        print(f"📦 偵測到下載檔案為 ZIP 壓縮格式，正在解壓縮...")
        try:
            with zipfile.ZipFile(local_json_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                json_files = [f for f in file_list if f.endswith('.json')]
                if json_files:
                    target_file = json_files[0]
                    json_data = zip_ref.read(target_file)
                    with open(local_json_path, 'wb') as out_file:
                        out_file.write(json_data)
                    print(f"🟢 解壓縮完成！已還原為 JSON 格式。")
                else:
                    print(f"❌ 錯誤：ZIP 檔中找不到 JSON 檔案", file=sys.stderr)
                    return False
        except Exception as e:
            print(f"❌ 錯誤：解壓縮 ZIP 檔失敗 ({e})", file=sys.stderr)
            return False

    print(f"🔍 正在篩選食藥署 (TFDA) 官方許可證資料庫，關鍵字：'{query_str}'...")
    print("-" * 85)
    
    matched_count = 0
    try:
        with open(local_json_path, 'r', encoding='utf-8', errors='ignore') as f:
            records = json.load(f)
            
            for item in records:
                lic_no = item.get("許可證字號") or item.get("licenceNo") or ""
                c_name = item.get("中文品名") or item.get("chineseName") or ""
                e_name = item.get("英文品名") or item.get("englishName") or ""
                indication = item.get("適應症") or item.get("indications") or "無標示適應症"
                components = item.get("主成分略述") or item.get("componentsDesc") or ""
                
                if (query_str.lower() in lic_no.lower() or
                    query_str.lower() in c_name.lower() or
                    query_str.lower() in e_name.lower() or
                    query_str.lower() in components.lower()):
                    
                    print(f"🔖 許可證號：{lic_no}")
                    print(f"🇨🇳 中文品名：{c_name}")
                    print(f"🇺🇸 英文品名：{e_name}")
                    print(f"🧬 主成成分：{components}")
                    print(f"📄 官方適應症：{indication}")
                    print("-" * 60)
                    matched_count += 1
                    
                    if matched_count >= 10:
                        print(f"\n[⚠️ 提示] 已篩選出前 10 筆符合之結果，其餘項目已自動隱藏。")
                        break
                        
    except Exception as e:
        print(f"❌ 錯誤：解析食藥署藥證資料檔失敗 ({e})", file=sys.stderr)
        return False
        
    print(f"✨ 共計尋獲 {matched_count} 筆符合 TFDA 核准之藥品許可證項目。")
    return True

def query_fda_official(query_str):
    """
    實時查詢美國 FDA 官方 OpenFDA API。
    """
    import urllib.parse
    encoded_query = urllib.parse.quote(f'openfda.generic_name:"{query_str}" OR openfda.brand_name:"{query_str}"')
    fda_url = f"https://api.fda.gov/drug/label.json?search={encoded_query}&limit=5"
    
    print(f"[*] 正在從美國 FDA 官方 OpenFDA API 查詢...")
    print(f"🔗 URL: {fda_url}")
    
    try:
        req = urllib.request.Request(
            fda_url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get("results", [])
            
            print(f"🔍 正在篩選美國 FDA 官方資料庫，關鍵字：'{query_str}'...")
            print("-" * 85)
            
            matched_count = 0
            for item in results:
                openfda = item.get("openfda", {})
                brand_names = openfda.get("brand_name", ["無標示商品名"])
                generic_names = openfda.get("generic_name", ["無標示學名"])
                active_ingredients = openfda.get("active_ingredient", ["無標示活性成分"])
                indications = item.get("indications_and_usage", ["無標示適應症"])
                
                print(f"🔖 商品名稱：{', '.join(brand_names)}")
                print(f"🧬 學名 (Generic Name)：{', '.join(generic_names)}")
                print(f"🧪 活性成分：{', '.join(active_ingredients)}")
                
                ind_text = indications[0] if isinstance(indications, list) else str(indications)
                print(f"📄 官方適應症 (Indications)：{ind_text[:200]}...")
                print("-" * 60)
                matched_count += 1
                
            print(f"✨ 共計尋獲 {matched_count} 筆符合 FDA 核准之藥品項目。")
            return True
            
    except Exception as e:
        if hasattr(e, 'code') and e.code == 404:
            print(f"🔍 正在篩選美國 FDA 官方資料庫，關鍵字：'{query_str}'...")
            print("-" * 85)
            print(f"✨ 共計尋獲 0 筆符合 FDA 核准之藥品項目 (OpenFDA 未查得此關鍵字)。")
            return True
        else:
            print(f"❌ 錯誤：無法連接美國 FDA 官方 API ({e})", file=sys.stderr)
            return False

def main():
    parser = argparse.ArgumentParser(description="台灣與美國官方藥物資料庫實時查詢與同步工具")
    parser.add_argument("--nhi", type=str, help="查詢健保署官方給付與支付價格 (如: Entecavir / 貝樂克)")
    parser.add_argument("--tfda", type=str, help="查詢食藥署 (TFDA) 官方許可證與適應症 (如: 癌適求 / Elranatamab)")
    parser.add_argument("--fda", type=str, help="查詢美國 FDA 官方 OpenFDA API (如: Elranatamab / Elrexfio)")
    parser.add_argument("--update", action="store_true", help="強制重新從政府開放平台下載同步最新藥物主檔")
    
    args = parser.parse_args()
    
    if not args.nhi and not args.tfda and not args.fda:
        print("\n[使用說明]")
        print("  1. 查詢健保署官方藥價與給付：")
        print("     python3 query_official_drug_db.py --nhi [藥名/學名/健保碼]")
        print("  2. 查詢食藥署 (TFDA) 官方藥物許可證與適應症：")
        print("     python3 query_official_drug_db.py --tfda [藥名/學名/許可證號]")
        print("  3. 查詢美國 FDA 官方 OpenFDA API：")
        print("     python3 query_official_drug_db.py --fda [藥名/學名]")
        print("  4. 強制同步最新數據庫：")
        print("     python3 query_official_drug_db.py --nhi [藥名] --update\n")
        sys.exit(0)
        
    print("======================================================================")
    print("   🏥 台灣及美國官方開放資料庫 (Open Data) 即時對位查詢系統")
    print("======================================================================")
    
    if args.nhi:
        query_nhi_official(args.nhi, force_download=args.update)
    elif args.tfda:
        query_tfda_official(args.tfda, force_download=args.update)
    elif args.fda:
        query_fda_official(args.fda)
        
    print("\n======================================================================")
    print("【聲明】本工具僅提供政府開放資料之即時檢索對位，實際臨床決策請務必遵循醫囑。")
    print("======================================================================")

if __name__ == "__main__":
    main()
