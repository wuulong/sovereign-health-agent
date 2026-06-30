#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import sqlite3
import argparse
from datetime import datetime

# Import Playwright dynamically to show installation instruction if missing
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("【錯誤】未偵測到 playwright 套件。請在 terminal 執行以下指令進行安裝：")
    print("       pip install playwright")
    print("       playwright install chromium")
    sys.exit(1)

# Default Database Path (Dynamically resolved based on profile in main)

def convert_lic_name_to_id(lic_name):
    """
    將許可證字號中文名稱（如 內衛藥製字第000711號）轉換為食藥署的 licId（如 12000711）
    """
    pattern = r"(衛署藥製|衛署藥輸|內衛藥製|衛部藥製|衛部藥輸|衛署罕藥輸)字第(\d+)號"
    match = re.search(pattern, lic_name)
    if not match:
        return None
        
    type_str = match.group(1)
    code_str = match.group(2)
    
    # 類別代碼映射
    type_map = {
        "衛署藥製": "01",
        "衛署藥輸": "02",
        "衛署罕藥輸": "10",
        "內衛藥製": "12",
        "衛部藥製": "51",
        "衛部藥輸": "52"
    }
    
    type_code = type_map.get(type_str)
    if not type_code:
        return None
        
    # 證號補足 6 位數
    code_padded = code_str.zfill(6)
    return f"{type_code}{code_padded}"

def fetch_drug_data(nhi_code=None, lic_id=None, verbose=False):
    """
    透過 Playwright 在無頭瀏覽器中查詢食藥署許可證並攔截 API 資料
    """
    search_url = "https://lmspiq.fda.gov.tw/web/DRPIQ/DRPIQLicSearch"
    result_base_url = "https://lmspiq.fda.gov.tw/web/DRPIQ/DRPIQ1000Result"
    
    detail_data = None
    search_api_response = None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 建立一個有設定常用 user-agent 的 context
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        # 攔截並擷取 API 網路回應
        def handle_response(response):
            nonlocal detail_data, search_api_response
            url = response.url
            if verbose:
                print(f"[Network] Response: {url} | Status: {response.status}")
                
            if "/sh/piq/1000/licSearch" in url:
                if response.status in [200, 304]:
                    try:
                        detail_data = response.json()
                        if verbose:
                            print("[*] 成功攔截詳細資料 API 回應！")
                            print("[Raw JSON Response]:")
                            print(json.dumps(detail_data, indent=2, ensure_ascii=False))
                    except Exception as e:
                        if verbose:
                            print(f"[!] 解析詳細資料 JSON 失敗: {e}")
            elif "/sh/piq/1000/search" in url:
                if response.status in [200, 304]:
                    try:
                        search_api_response = response.json()
                        if verbose:
                            print("[*] 成功攔截搜尋結果 API 回應！")
                    except Exception as e:
                        if verbose:
                            print(f"[!] 解析搜尋結果 JSON 失敗: {e}")

        # 剛性防禦：一律先訪問 SPA 基礎路徑以載入 React 應用，避免直接進入子路由時遭遇 404 崩潰
        base_url = "https://lmspiq.fda.gov.tw/web/"
        print(f"[*] 初始化 SPA 基礎頁面: {base_url}")
        page.goto(base_url)
        page.wait_for_timeout(3000) # 等待 SPA 載入
        
        page.on("response", handle_response)
        
        if lic_id:
            # 場景 1: 直接使用 licId 前往詳細資料頁面 (此時免驗證碼)
            target_url = f"{result_base_url}?licId={lic_id}"
            print(f"[*] 導向詳細資料頁面: {target_url}")
            
            try:
                # 使用 Playwright 官方推薦的 expect_response 同步等待 API 回應
                with page.expect_response("**/sh/piq/1000/licSearch", timeout=15000) as response_info:
                    page.goto(target_url)
                
                resp = response_info.value
                if resp.status in [200, 304]:
                    detail_data = resp.json()
                    if verbose:
                        print("[*] 成功透過 expect_response 獲取 JSON 資料！")
            except Exception as e:
                print(f"[!] 等待詳細資料 API 逾時或失敗: {e}")
        
        elif nhi_code:
            # 場景 2: 健保代碼查詢引導說明
            # 由於食藥署查詢表單並不提供健保代碼查詢欄位，且該表單設有圖形驗證碼，
            # 在本地 CLI 端不適合直接執行此搜尋。引導使用者透過對照或對話進行。
            print("==================================================")
            print("【說明】食藥署許可證系統不支援直接以健保代碼進行搜尋。")
            print("請採用以下任一方式查詢：")
            print("  1. 在個人健康助理對話中輸入：!sha_drug [健保碼]")
            print("     (AI 助理將自動在背景利用 search_web 幫您對照出許可證字號並入庫。)")
            print("  2. 手動上網搜尋該健保碼對應的許可證字號（例如 衛署藥輸字第012601號），")
            print("     並在本地執行：")
            print(f"     python utils/medication_query.py -l [許可證字號] -s")
            print("==================================================")
            browser.close()
            sys.exit(0)
            
        browser.close()
        
    return detail_data

def format_drug_markdown(data):
    """
    將食藥署回傳的 JSON 格式化為精美的 Markdown 文件
    """
    if not data or "data" not in data:
        return "無此藥品之詳細資料。"
        
    info = data["data"]
    
    # 提取基本欄位
    lic_id = info.get("licid", "--")
    prod_name_c = info.get("prodNameC", "--")
    prod_name_e = info.get("prodNameE", "--")
    
    # 適應症
    indications_list = info.get("indicationsName", [])
    if isinstance(indications_list, list) and indications_list:
        indications = ", ".join(indications_list)
    else:
        indications = info.get("indications", "未登記或無適應症說明。")
        
    dosage_form = info.get("does", "--") # 劑型代碼
    
    # 有效日期格式化
    valid_date = info.get("validDate", "--")
    if valid_date and valid_date != "--":
        valid_date = valid_date.split()[0] # 擷取 "YYYY-MM-DD"
        
    # 包裝規格
    pkg_list = info.get("packageUnit", [])
    if pkg_list:
        package = ", ".join([f"{p.get('packageSpec', '--')} (單位代碼: {p.get('packageUnit', '--')})" for p in pkg_list])
    else:
        package = info.get("pkgDes", "--")
        
    applicant = info.get("applicantName", "--")
    
    # 格式化有效日期 (西元)
    # （此處已使用 split()[0] 直接格式化）
            
    # 提取成分明細 (處方)
    ingredients_str = ""
    ingredients_list = info.get("ingredientsDtoList", [])
    if ingredients_list:
        ingredients_str = "\n| 成分名稱 | 含量 | 單位 | 角色 |\n| :--- | :--- | :--- | :--- |\n"
        for ing in ingredients_list:
            name = ing.get("ingredientsName", "--")
            qty = ing.get("concent", "--")
            unit = ing.get("concentUnit", "--")
            role = "主成分" if ing.get("ingredientsKind") == "1" else "賦形劑"
            ingredients_str += f"| {name} | {qty} | {unit} | {role} |\n"
    else:
        ingredients_str = "*無處方成分登錄資料。*"
        
    # 提取製造廠明細
    factory_str = ""
    factory_list = info.get("factoryDtoList", [])
    if factory_list:
        for fac in factory_list:
            fac_name = fac.get("factoryName", "--")
            fac_addr = fac.get("factoryAddr", "--")
            fac_role = fac.get("factoryRole", "--")
            # 角色中文對應
            role_map = {"1": "製造廠", "2": "包裝廠", "3": "分裝廠"}
            role_desc = role_map.get(fac_role, "製造廠")
            factory_str += f"* **{role_desc}**：{fac_name} (地址：{fac_addr})\n"
    else:
        factory_str = "*無製造廠登錄資料。*"

    # 模擬副作用與照護提醒（TFDA 許可證無單獨副作用欄位，但可從仿單或本機知識庫推導，此處生成基本照護注意）
    precautions = ""
    if "cyclophosphamide" in prod_name_e.lower() or "癌德星" in prod_name_c:
        precautions = """* **常見副作用**：骨髓抑制（白血球降低，易受感染）、噁心、嘔吐、落髮、出血性膀胱炎（血尿）。
* **重要照護叮嚀**：
  1. 務必**補充足夠水分**（建議每天喝水 2000-3000cc），並頻繁排尿，以降低出血性膀胱炎風險。
  2. 服藥期間注意體溫，若有發燒（大於 38°C）或發冷，請立即急診就醫。
  3. 避免與生食或未洗淨水果接觸，預防感染。"""
    elif "prednisolone" in prod_name_e.lower() or "普力多寧" in prod_name_c:
        precautions = """* **常見副作用**：腸胃道不適（胃痛、胃潰瘍風險）、血糖升高、水腫、睡眠障礙、長期使用易致免疫力下降。
* **重要照護叮嚀**：
  1. 建議**隨餐或飯後服用**，以減少腸胃道刺激；如有需要，請配合醫師開立之胃藥（如胃莫潰）服用。
  2. 絕對**不可擅自驟然停藥**，必須遵循醫囑逐漸減量，否則會引起急性副腎皮質功能不全。
  3. 注意水分攝取與血壓，控制鹽分攝取防止水腫。"""
    else:
        precautions = "* **一般叮嚀**：請遵循醫師或藥師指示服用。若有過敏反應（如紅疹、呼吸困難）或嚴重不適，請立即停藥並就醫諮詢。"

    md = f"""# 💊 藥品許可證與衛教指引：{prod_name_c}

*   **中文品名**：{prod_name_c}
*   **英文品名**：{prod_name_e}
*   **許可證字號**：{lic_id}
*   **藥品類別**：{info.get("licOptsDrName", "處方藥")}
*   **劑型**：{dosage_form}
*   **有效日期**：{valid_date}
*   **包裝規格**：{package}
*   **申請商 (藥商)**：{applicant}

---

## 🩺 臨床適應症 (Indications)
> {indications}

---

## 🧪 處方成分明細 (Ingredients)
{ingredients_str}

---

## 🏭 製造與包裝廠資訊 (Manufacturers)
{factory_str}

---

## ⚠️ 常見副作用與居家照護叮嚀 (Precautions & Side Effects)
{precautions}

---
> 資料來源：衛生福利部食品藥物管理署 (TFDA) 藥證查詢系統。
> 本指引僅供自主照護參考，任何用藥調整必須經由您的主治醫師決定。
"""
    return md

def save_to_sqlite(db_path, nhi_code, title, content, lic_id):
    """
    將查詢到的藥品衛教資訊儲存至 SQLite 資料庫的 MY_EDUCATION_BASE 中
    """
    if not os.path.exists(db_path):
        print(f"【錯誤】找不到 SQLite 資料庫檔案於: {db_path}")
        return False
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    knowledge_id = f"DRUG_{nhi_code}" if nhi_code else f"DRUG_{lic_id}"
    category = "Medication"
    keyword = nhi_code if nhi_code else lic_id
    last_updated = datetime.now().strftime("%Y-%m-%d")
    meta_json = json.dumps({"licId": lic_id, "fetched_at": last_updated}, ensure_ascii=False)
    
    # 檢查是否已存在
    cursor.execute("SELECT 1 FROM MY_EDUCATION_BASE WHERE knowledge_id = ?", (knowledge_id,))
    exists = cursor.fetchone()
    
    try:
        if exists:
            # 更新
            sql = """
            UPDATE MY_EDUCATION_BASE 
            SET title = ?, content = ?, citations = ?, last_updated = ?, meta_data = ?
            WHERE knowledge_id = ?
            """
            cursor.execute(sql, (title, content, f"TFDA 許可證 {lic_id}", last_updated, meta_json, knowledge_id))
            print(f"[*] 已成功更新本機資料庫中的藥品衛教卡: {knowledge_id}")
        else:
            # 新增
            sql = """
            INSERT INTO MY_EDUCATION_BASE 
            (knowledge_id, category, disease_name, keyword, title, content, citations, last_updated, meta_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(sql, (
                knowledge_id, category, "", keyword, title, content, 
                f"TFDA 許可證 {lic_id}", last_updated, meta_json
            ))
            print(f"[*] 已成功將全新藥品衛教卡寫入本機資料庫: {knowledge_id}")
            
        conn.commit()
        return True
    except Exception as e:
        print(f"【錯誤】寫入資料庫失敗: {e}")
        return False
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="台灣藥品許可證與衛教資訊本地端查詢工具 (Playwright SPA 版)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-n", "--nhi-code", help="依健保用藥代碼查詢 (例如 BC12601100)")
    group.add_argument("-l", "--lic-id", help="依許可證 ID 查詢 (如 12000711 或是中文 內衛藥製字第000711號)")
    
    parser.add_argument("-s", "--save", action="store_true", help="將查詢結果儲存/寫入本地 SQLite 個人資料庫")
    parser.add_argument("-d", "--db-path", help="指定 SQLite 個人資料庫路徑")
    parser.add_argument("--profile", type=str, default="myself", help="指定主體身分名稱 (預設: myself)")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示詳細的 Playwright 網路瀏覽調試資訊")
    
    args = parser.parse_args()
    
    # 解析中文許可證為 licId
    lic_param = args.lic_id
    if lic_param and not lic_param.isdigit():
        converted = convert_lic_name_to_id(lic_param)
        if converted:
            print(f"[*] 許可證字號 '{lic_param}' 自動轉譯為代碼: {converted}")
            lic_param = converted
        else:
            print(f"【錯誤】無法辨識的許可證字號格式: {lic_param}。請使用類似 '內衛藥製字第000711號' 的格式。")
            sys.exit(1)
            
    profile = args.profile
    db_path = args.db_path if args.db_path else os.path.join(os.path.dirname(os.path.abspath(__file__)), "../db/instances", profile, "fv_patient_personal.db")
    db_path = os.path.abspath(db_path)

    print("==================================================")
    print("   Sovereign Health Agent 藥品許可證衛教查詢系統")
    print(f"   👤 身分設定: {profile}")
    print(f"   💾 資料庫: {db_path}")
    print("==================================================")
    
    # 執行 Playwright 查詢
    try:
        raw_data = fetch_drug_data(nhi_code=args.nhi_code, lic_id=lic_param, verbose=args.verbose)
    except Exception as e:
        print(f"【查詢失敗】發生錯誤: {e}")
        sys.exit(1)
        
    if not raw_data:
        print("【查無資料】未取得任何藥品許可證回應。")
        sys.exit(1)
        
    # 格式化輸出
    md_content = format_drug_markdown(raw_data)
    print("\n--- 藥品詳細資訊與照護指引 ---")
    print(md_content)
    
    # 寫入 SQLite
    if args.save:
        nhi_code_key = args.nhi_code if args.nhi_code else raw_data["data"].get("licid")
        title = f"{raw_data['data'].get('prodNameC')} 用藥指引"
        lic_id_val = raw_data["data"].get("licid")
        
        print("\n[*] 正在寫入資料庫...")
        save_to_sqlite(db_path, nhi_code_key, title, md_content, lic_id_val)
        
    print("==================================================")
    print("   🎉 查詢作業圓滿結束！")
    print("==================================================")

if __name__ == "__main__":
    main()
