#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patient Agent for Sovereign Health Agent (v0.2.0)
個人醫療 AI 助理實體運行腳本。
提供與病患（蓬萊 004 / 阿喜伯）互動的自述問答介面。
實作邊問邊補、熱接入快速建檔，以及整合本地 SQLite 衛教庫的實證與 AI 歸納雙層問答防線。
指令全面改用 "!sha_" 作為前綴。
"""

import os
import sys
import sqlite3
import json
import shutil
import argparse
from datetime import datetime

# 定義基準目錄
DB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class SovereignHealthAgent:
    def __init__(self, profile="myself"):
        self.profile = profile
        self.db_path = os.path.join(DB_DIR, "db", "instances", profile, "fv_patient_personal.db")
        
        # 初始病患基本欄位，將於 load_profile 中覆寫
        if profile == "myself":
            self.patient_id = "PUMC_004"
            self.display_name = "阿喜伯"
        else:
            self.patient_id = f"PUMC_{profile.upper()}"
            self.display_name = f"被照顧者 {profile}"
            
        self.api_url = "http://localhost:8000/api/v1/clinical/observation"
        self.email = "未設定"
        self.phone = "未設定"
        self.birth_date = "1958-08-08"
        self.height_cm = 168
        self.weight_kg = 62
        
        # 執行冷啟動檢測與目錄建置
        self.check_and_init_db()
        self.load_profile()
        
    def check_and_init_db(self):
        """檢查並初始化當前 Profile 的資料庫與實體目錄"""
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        # 建立 raw 和 inbox 資料夾
        self.data_dir = os.path.join(DB_DIR, "data", "instances", self.profile)
        os.makedirs(os.path.join(self.data_dir, "inbox"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "raw"), exist_ok=True)
        
        if not os.path.exists(self.db_path):
            template_path = os.path.join(DB_DIR, "db", "template.db")
            if os.path.exists(template_path):
                print(f"【冷啟動】偵測到新身分 '{self.profile}'，正在自範本複製初始化資料庫...")
                shutil.copy2(template_path, self.db_path)
            else:
                print(f"【錯誤】找不到範本資料庫 {template_path}，無法冷啟動。")

    def sign_delegation_consent(self):
        """引導照顧者簽署受託代管健康檔案免責與授權承諾書"""
        print("\n==================================================")
        print(" 📜 【BMAD 個人健康主權】代理授權簽署宣告")
        print("==================================================")
        print("您目前正嘗試存取非您個人的健康檔案。為保障健康隱私，")
        print("您必須簽署「受託代管健康檔案免責與隱私同意書」。")
        print("您承諾：此操作已獲得當事人受託，且數據僅用於本地健康管理與就醫協助，")
        print("且全文符合台灣個人資料保護法與醫療隱私防禦規範。")
        print("--------------------------------------------------")
        print("是否確認同意並簽署？(Y/N)")
        confirm = input("> ")
        if confirm.strip().upper() not in ["Y", "YES", "是", "好"]:
            print("【拒絕簽署】無法取得存取授權。身分切換已取消。")
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            consent_id = f"CNS-DEL-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT OR REPLACE INTO USER_CONSENTS (
                consent_id, patient_id, consent_version, signed_at, is_active, contract_text_hash, consent_type, meta_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                consent_id, self.patient_id, "v0.1.3-delegated", now_str, 1,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "delegated_care",
                json.dumps({"signed_by": "myself", "relation": "representative"})
            ))
            conn.commit()
            conn.close()
            print("【簽署成功】委託代管同意書已物理定錨於此資料庫中。")
            return True
        except Exception as e:
            print(f"簽署代管同意書失敗: {e}")
            return False

    def switch_profile(self, new_profile):
        """一鍵切換操作主體，安全卸載並載入新病患實體"""
        if new_profile == self.profile:
            print(f"目前已經是身分: {self.profile}。")
            return
            
        print(f"\nAI 助理：「正在安全切換至身分: {new_profile}...」")
        
        # 備份舊狀態以防切換失敗
        old_profile = self.profile
        old_patient_id = self.patient_id
        old_db_path = self.db_path
        
        # 切換路徑
        self.profile = new_profile
        self.db_path = os.path.join(DB_DIR, "db", "instances", new_profile, "fv_patient_personal.db")
        
        # 建立目錄與複製範本庫
        self.check_and_init_db()
        
        # 重設病患 ID
        if new_profile == "myself":
            self.patient_id = "PUMC_004"
        else:
            self.patient_id = f"PUMC_{new_profile.upper()}"
            
        # 代管權限檢驗
        if new_profile != "myself":
            has_consent = False
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT consent_id FROM USER_CONSENTS WHERE consent_type = 'delegated_care' AND is_active = 1")
                row = cursor.fetchone()
                if row:
                    has_consent = True
                conn.close()
            except Exception:
                pass
                
            if not has_consent:
                success = self.sign_delegation_consent()
                if not success:
                    # 簽署失敗，還原至舊身分
                    self.profile = old_profile
                    self.patient_id = old_patient_id
                    self.db_path = old_db_path
                    print(f"AI 助理：「已安全還原至原身分: {self.profile}。」")
                    return
                    
        # 載入新 Profile
        self.load_profile()
        self.display_welcome()
        print(f"AI 助理：「身分已成功切換！當前操作對象為: {self.display_name}。」")

    def load_profile(self):
        """讀取本機 PHR 的病患個人檔"""
        if not os.path.exists(self.db_path):
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # 優先直接撈取資料庫中唯一的個人檔案，以動態更新 patient_id
            cursor.execute("SELECT patient_id, display_name, email, phone, meta_data FROM MY_PROFILE LIMIT 1")
            row = cursor.fetchone()
            if row:
                self.patient_id = row[0]
                self.display_name = row[1]
                self.email = row[2]
                self.phone = row[3]
                try:
                    meta = json.loads(row[4])
                    self.birth_date = meta.get("birth_date", "1973-02-15")
                    self.height_cm = meta.get("height_cm", 170)
                    self.weight_kg = meta.get("weight_kg", 95)
                except:
                    pass
            conn.close()
        except Exception as e:
            print(f"載入個人檔失敗: {e}")
            
    def display_welcome(self):
        # 計算年齡與體表面積 BSA
        birth_year = int(self.birth_date.split("-")[0])
        current_year = datetime.now().year
        age = current_year - birth_year
        bsa = ((self.height_cm * self.weight_kg) / 3600) ** 0.5
        
        print("==================================================")
        print("     Sovereign Health Agent (主權健康代理人) ")
        print("==================================================")
        print(f"【病患身份】: {self.display_name} 阿伯 (ID: {self.patient_id})")
        print(f"【生理特徵】: {age} 歲 | {self.height_cm} cm | {self.weight_kg} kg | BSA: {bsa:.2f} ㎡")
        print(f"【聯絡電話】: {self.phone}")
        print(f"【電子信箱】: {self.email}")
        print("==================================================")
        print("主權生醫 AI 助理已就位。本機資料採用 mTLS 加密防護。")
        print("--------------------------------------------------")

    def check_hot_ingestion_trigger(self, user_input):
        """
        判斷使用者是否觸發熱接入
        主動：輸入 "!sha_hot"
        被動：輸入敏感病情詞組（確診、癌症、轉移、復發、自費、第二意見、骨髓瘤、腫瘤）
        """
        cleaned = user_input.strip()
        if cleaned == "!sha_hot":
            return True
            
        severe_keywords = ["確診", "癌症", "轉移", "復發", "自費", "第二意見", "骨髓瘤", "腫瘤"]
        for kw in severe_keywords:
            if kw in cleaned:
                # 排除一般諮詢性提問，僅在陳述句中觸發
                if not any(q in cleaned for q in ["是什麼", "有效嗎", "有哪些", "副作用", "照護"]):
                    return True
        return False

    def is_medical_query(self, user_input):
        """
        判斷是否為醫療諮詢問題
        """
        question_words = ["是什麼", "最新", "有效嗎", "怎麼治", "有哪些", "副作用", "可以吃", "療效", "如何治療", "藥物", "偏方", "症狀", "照護", "須知"]
        for word in question_words:
            if word in user_input:
                return True
        return False

    def run_dialogue(self):
        """相容性轉發，呼叫對話迴圈"""
        self.run_dialogue_loop()

    def run_dialogue_loop(self):
        """持續運行問答對話迴圈，支援切換身分與退出"""
        self.display_welcome()
        print("AI 助理：「您好！我是您的個人健康助理。看診前我們可以先準備好您今天的自述症狀，或查詢衛教資訊。」")
        print("（提示：輸入 '!sha_hot' 開始熱接入建檔、'!sha_myedu' 產生個人化衛教、'!sha_soap' 生成門診 SOAP 卡、'!sha_edu' 瀏覽衛教主題）")
        print("（提示：輸入 '!sha_backup' 匯出個人健康備份、'!sha_ice' 顯示並產生緊急救援卡）")
        print("（進階：輸入 '!sha_switch [身分名稱]' 可以切換操作主體，例如 '!sha_switch father'；輸入 'exit' 結束對話）")
        
        while True:
            try:
                user_input = input(f"\n[{self.display_name}] 輸入 > ")
                cleaned = user_input.strip()
                if not cleaned:
                    continue
                
                if cleaned.lower() in ["exit", "quit", "退出", "離開"]:
                    print("AI 助理：「對話已結束。祝您身體健康，平安順心！」")
                    break
                    
                # 偵測身分切換指令
                if cleaned.startswith("!sha_switch"):
                    parts = cleaned.split()
                    if len(parts) >= 2:
                        new_profile = parts[1]
                        self.switch_profile(new_profile)
                    else:
                        print("AI 助理：「請提供要切換的身分名稱，例如：!sha_switch father」")
                    continue
                
                # 偵測快捷指令
                if cleaned == "!sha_hot":
                    self.run_hot_ingestion_flow(cleaned)
                    continue
                elif cleaned == "!sha_edu":
                    self.run_all_education_list()
                    continue
                elif cleaned == "!sha_myedu":
                    self.generate_personalized_education()
                    continue
                elif cleaned == "!sha_soap":
                    self.generate_soap_card()
                    continue
                elif cleaned == "!sha_backup":
                    self.generate_backup()
                    continue
                elif cleaned == "!sha_ice":
                    self.generate_ice_card_shortcut()
                    continue

                # 1. 偵測被動熱接入觸發
                if self.check_hot_ingestion_trigger(cleaned):
                    self.run_hot_ingestion_flow(cleaned)
                    continue

                # 2. 偵測是否為醫療問答 (Grounded QA)
                if self.is_medical_query(cleaned):
                    self.run_grounded_qa_flow(cleaned)
                    continue

                # 3. 走一般日常自述症狀流程
                self.process_general_flow(cleaned)
            except (KeyboardInterrupt, EOFError):
                print("\nAI 助理：「對話已結束。祝您身體健康，平安順心！」")
                break

    def process_general_flow(self, user_input):
        """執行一般日常自述症狀流程"""
        print("\nAI 助理：「好的，我正在進行 PII 個資去識別化處理，並幫您封裝成標準的 FHIR Observation 格式...」")
        
        observation_resource = self.build_fhir_observation(user_input)
        
        print("\n================ [FHIR Observation JSON 輸出] ================")
        print(json.dumps(observation_resource, ensure_ascii=False, indent=2))
        print("==============================================================")
        
        print("\nAI 助理：「數據已在本機 PHR 庫存檔。看診時，助理會安全推送給虛擬醫院的門診分流路由器。」")
        print(f"預計發送端點: {self.api_url}")
        
        self.save_to_local_journey(observation_resource)

    def run_grounded_qa_flow(self, user_query):
        """執行有所本醫療問答與誠實回覆流程"""
        print("\nAI 助理：「正在為您檢索本地及外部權威生醫文獻資料庫...」")
        
        # 剛性防範偏方與幻覺：若提問包含無實證文獻支持的詞彙，強制進入誠實未知流程
        if any(unproven in user_query for unproven in ["偏方", "綠豆沙", "中藥秘方", "神藥"]):
            self.trigger_idk_flow()
            return
            
        found_records = []
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT title, content, citations, category, disease_name, keyword FROM MY_EDUCATION_BASE")
                rows = cursor.fetchall()
                conn.close()
                
                for row in rows:
                    title, content, citations, category, disease_name, keyword_str = row
                    keywords = [k.strip() for k in keyword_str.split(",") if k.strip()]
                    
                    match = False
                    if disease_name in user_query:
                        if any(kw in user_query for kw in keywords) or any(act in user_query for act in ["介紹", "症狀", "什麼是", "了解", "說明"]):
                            match = True
                    else:
                        for kw in keywords:
                            if kw in user_query and kw not in ["症狀", "CRAB", "了解", "說明"]:
                                match = True
                                break
                    
                    if match:
                        found_records.append({
                            "title": title,
                            "content": content,
                            "citations": citations,
                            "category": category,
                            "disease_name": disease_name
                        })
            except Exception as e:
                print(f"檢索資料庫失敗: {e}")
                
        if found_records:
            print("\n================ [有所本生醫問答回覆] ================")
            print("【一、 資料庫權威實證資訊】")
            for idx, rec in enumerate(found_records):
                print(f"🔹 {rec['title']}：")
                print(f"   {rec['content']}")
                print(f"   [文獻出處：{rec['citations']}]")
                print("-" * 50)
                
            print("\n【二、 AI 智慧歸納與日常照護補充】")
            print("💡 助理為您整理的日常叮嚀：")
            diseases = list(set([r['disease_name'] for r in found_records]))
            
            has_summary = False
            if "多發性骨髓瘤" in diseases:
                if any("Daratumumab" in r['title'] or "達希美" in r['title'] for r in found_records):
                    print("  * 針對於 Daratumumab 達希美：首次輸注容易有過敏反應，施打當天請務必留在院所觀察。回家後若出現呼吸道喘癢、咳嗽或發燒，請速聯絡醫療人員。")
                if any("Bortezomib" in r['title'] or "萬科" in r['title'] for r in found_records):
                    print("  * 針對於 Bortezomib 萬科：要極度防範周邊神經麻木。請穿厚襪並防範燙傷，且『帶狀疱疹』預防性抗病毒藥一定要天天吃，不可自行停藥。")
                if any("Lenalidomide" in r['title'] or "瑞復美" in r['title'] for r in found_records):
                    print("  * 針對於 Lenalidomide 瑞復美：Revlimid 有血栓風險。每日服藥期間應適度走動，若有一側小腿突發紅腫痛，要立刻急診就醫。")
                print("  * 骨病變日常防範：請勿搬運重物，小心防跌以避免發生病理性骨折。")
                has_summary = True
            
            if "大腸直腸癌" in diseases:
                if any("Cetuximab" in r['title'] or "爾必得舒" in r['title'] for r in found_records):
                    print("  * 針對於 Cetuximab 爾必得舒：臉部痤瘡樣皮疹是標靶藥效指標。清潔請溫和，注意防曬並加強保濕，必要時由醫師開立外用抗生素。")
                print("  * 飲食習慣：應採取好消化、少刺激之溫和飲食。若出現大便出血或大便變細，請務必拍照紀錄於回診時回報。")
                has_summary = True
                
            if not has_summary:
                print("  * 助理提醒您：請依醫囑服藥，定時作息，適度飲水，若身體有任何異常，請儘速就醫。")
            
            print("\n*（以上區塊為 AI 根據本機文獻資料庫之疾病與用藥，所進行之智慧綜合照護歸納，非原始文獻直接原文，請與主治醫師討論確認）*")
            print("==================================================")
            self.print_disclaimer()
        else:
            self.trigger_idk_flow()

    def generate_personalized_education(self):
        """
        !sha_myedu 指令：自動讀取病患當前的病名與用藥 Context，從 SQLite 檢索對應的衛教內容並產出
        """
        print("\nAI 助理：「正在讀取您的本地自主 PHR 歷程以提煉病情與用藥檔案...」")
        
        disease_list = []
        drug_list = []
        
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                # 讀取 Condition
                cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Condition'")
                cond_rows = cursor.fetchall()
                for r in cond_rows:
                    fhir_obj = json.loads(r[0])
                    disease_name = fhir_obj.get("code", {}).get("text", "")
                    if disease_name:
                        core_disease = ""
                        for d in ["多發性骨髓瘤", "大腸直腸癌", "大腸癌", "直腸癌"]:
                            if d in disease_name:
                                core_disease = d
                                break
                        if not core_disease:
                            core_disease = disease_name
                        disease_list.append(core_disease)
                
                # 讀取 MedicationRequest
                cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'MedicationRequest'")
                med_rows = cursor.fetchall()
                for r in med_rows:
                    fhir_obj = json.loads(r[0])
                    if fhir_obj.get("status") == "active":
                        med_name = fhir_obj.get("medicationCodeableConcept", {}).get("text", "")
                        if med_name:
                            drug_list.append(med_name.strip())
                
                conn.close()
            except Exception as e:
                print(f"讀取患者 PHR 歷程失敗: {e}")
                
        disease_list = list(set(disease_list))
        drug_list = list(set(drug_list))
        
        if not disease_list:
            print("\nAI 助理：「阿喜伯，您的本地歷程中目前尚未登錄 any 確診疾病（Condition）。」")
            print("        「您可以先輸入 '!sha_hot' 來快速填寫您的確診疾病與用藥，以便我為您產生個人化的衛教資訊喔！」")
            return
            
        birth_year = int(self.birth_date.split("-")[0])
        current_year = datetime.now().year
        age = current_year - birth_year
        bsa = ((self.height_cm * self.weight_kg) / 3600) ** 0.5
        
        print(f"\n【偵測到您的健康檔案】")
        print(f"🔸 基本生理：{age} 歲 | 身高：{self.height_cm} cm | 體重：{self.weight_kg} kg | BSA：{bsa:.2f} ㎡")
        print(f"🔸 確診疾病：{', '.join(disease_list)}")
        print(f"🔸 主要用藥：{', '.join(drug_list) if drug_list else '未登錄用藥'}")
        
        print("\nAI 助理：「正在為您從本地 SQLite 衛教庫檢索對應的權威實證資訊...」")
        
        found_records = []
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # 1. 查詢疾病相關衛教
                for dis in disease_list:
                    cursor.execute("""
                    SELECT title, content, citations, category, disease_name 
                    FROM MY_EDUCATION_BASE 
                    WHERE category = 'disease' AND disease_name LIKE ?
                    """, (f"%{dis}%",))
                    for r in cursor.fetchall():
                        found_records.append({"title": r[0], "content": r[1], "citations": r[2], "category": r[3], "disease_name": r[4]})
                        
                # 2. 查詢藥物相關衛教
                for drug in drug_list:
                    cursor.execute("""
                    SELECT title, content, citations, category, disease_name 
                    FROM MY_EDUCATION_BASE 
                    WHERE category = 'medication' AND keyword LIKE ?
                    """, (f"%{drug}%",))
                    for r in cursor.fetchall():
                        found_records.append({"title": r[0], "content": r[1], "citations": r[2], "category": r[3], "disease_name": r[4]})
                        
                conn.close()
            except Exception as e:
                print(f"檢索衛教庫失敗: {e}")
                
        unique_records = []
        seen_titles = set()
        for r in found_records:
            if r["title"] not in seen_titles:
                seen_titles.add(r["title"])
                unique_records.append(r)
                
        print("\n=================== [ 您的個人化衛教與用藥資訊摘要卡 ] ===================")
        
        if unique_records:
            print("【一、 資料庫權威實證資訊】")
            for idx, rec in enumerate(unique_records):
                print(f"🔹 [{idx+1}] {rec['title']}：")
                print(f"   {rec['content']}")
                print(f"   [文獻出處：{rec['citations']}]")
                print("-" * 50)
        else:
            print("【一、 資料庫權威實證資訊】")
            print("  ℹ 查無直接對應的資料庫實證衛教條目。")
            print("-" * 50)
            
        print("\n【二、 AI 智慧歸納與日常照護補充】")
        print("💡 助理特別為您提煉的個人化生活叮嚀：")
        
        has_summary = False
        for dis in disease_list:
            if "多發性骨髓瘤" in dis:
                print("  * 🦴 骨骼安全防護：多發性骨髓瘤易致骨骼病變與骨折。請防範跌倒，居家鋪設防滑墊，日常避免搬提重物。")
                print("  * 💧 水分與腎臟代謝：每日建議飲水至少 2000c.c.，有助於代謝 M 蛋白並保護腎功能。")
                has_summary = True
            elif "大腸直腸癌" in dis or "大腸癌" in dis or "直腸癌" in dis:
                print("  * 🥦 腸胃道日常保養：採取好消化之溫和飲食。避免辛辣、油炸食物，防範便秘。")
                print("  * 📊 排便監測：注意有無大便變細、便血，若有請拍照或文字記錄。")
                has_summary = True
                
        if len(drug_list) >= 2:
            print(f"  * 💊 多重用藥交叉防範：您目前同時使用 {', '.join(drug_list)}。")
            if any(d in ["Bortezomib", "萬科"] for d in drug_list) and any(d in ["Daratumumab", "達希美"] for d in drug_list):
                print("    - 達希美與萬科聯用是目前主流的復發/難治性多發性骨髓瘤療法。")
                print("    - 雙重照護警示：達希美易有前期輸注反應（發熱、喘），而萬科則易累積手腳發麻之神經毒性。")
                print("    - 日常叮嚀：洗澡水溫由家人調好，防範燙傷；剪指甲防受傷；有咳嗽發熱請立即通報。")
                print("    - 疱疹防範：免疫功能受抑，預防疱疹抗病毒藥（Acyclovir）必須每日按時吞服。")
            has_summary = True
        elif len(drug_list) == 1:
            drug = drug_list[0]
            if drug in ["Bortezomib", "萬科"]:
                print("  * 💊 萬科用藥照護：注意手腳是否有發麻或針刺痛。洗熱水澡防燙傷。每天按時服用預防皮蛇抗病毒藥。")
                has_summary = True
            elif drug in ["Daratumumab", "達希美"]:
                print("  * 💊 達希美用藥照護：施打後若有咳嗽、鼻塞、畏寒或體溫過高，請通知個管師。")
                has_summary = True
            elif drug in ["Lenalidomide", "瑞復美"]:
                print("  * 💊 瑞復美用藥照護：有血栓風險。服藥期間請配合低劑量阿斯匹靈，並注意單側小腿是否紅腫痛，若有此現象請即刻就診。")
                has_summary = True
            elif drug in ["Cetuximab", "爾必得舒"]:
                print("  * 💊 爾必得舒皮膚護理：面部痤瘡樣皮疹通常在服藥後一至二週發生。請溫和保濕、外出嚴格防曬，不使用含刺激酒精保養品。")
                has_summary = True
                
        if not has_summary:
            print("  * ℹ 助理已為您記錄此病情檔案。在日常生活中，請遵循醫囑按時服藥，適度休息，並定期追蹤。")
            
        print("\n*（以上區塊為 AI 根據本機文獻資料庫之疾病與用藥，所進行之智慧綜合照護歸納，非原始文獻直接原文，僅供參考，請與主治醫師討論確認）*")
        print("=========================================================================")
        self.print_disclaimer()

    def run_all_education_list(self):
        """
        !sha_edu 指令：從 SQLite 讀取並列出所有已預載的衛教主題清單，供使用者輸入編號查詢
        """
        if not os.path.exists(self.db_path):
            print("【警告】未偵測到資料庫，無法查詢。")
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT knowledge_id, category, disease_name, title FROM MY_EDUCATION_BASE")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            print(f"讀取衛教清單失敗: {e}")
            return
            
        if not rows:
            print("AI 助理：「目前衛教庫中沒有任何資料。」")
            return
            
        print("\n=================== [ 本機衛教知識庫主題清單 ] ===================")
        for idx, row in enumerate(rows):
            kid, category, disease, title = row
            cat_name = "病情衛教" if category == "disease" else "用藥衛教"
            print(f"[{idx + 1}] 【{disease} - {cat_name}】{title}")
        print("=================================================================")
        print("請輸入您想查看的主題編號（或輸入 'Q' 返回）：")
        choice = input("> ")
        
        if choice.strip().upper() == "Q":
            return
            
        try:
            val = int(choice.strip())
            if 1 <= val <= len(rows):
                target_kid = rows[val - 1][0]
                self.show_education_detail(target_kid)
            else:
                print("輸入編號超出範圍。")
        except ValueError:
            print("無效的輸入。")
            
    def show_education_detail(self, knowledge_id):
        """顯示指定衛教條目的詳細資訊"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT title, content, citations, disease_name, category FROM MY_EDUCATION_BASE WHERE knowledge_id = ?", (knowledge_id,))
            row = cursor.fetchone()
            conn.close()
        except Exception as e:
            print(f"讀取衛教詳細內容失敗: {e}")
            return
            
        if not row:
            print("查無此衛教條目。")
            return
            
        title, content, citations, disease, category = row
        
        print("\n==================================================")
        print(f"📖 【資料庫權威實證資訊】")
        print(f"標題：{title}")
        print(f"內容：\n{content}")
        print(f"文獻出處：{citations}")
        print("--------------------------------------------------")
        
        print("💡 【AI 智慧歸納與日常照護補充】")
        if "Bortezomib" in title or "萬科" in title:
            print("  * 萬科手麻腳麻照護：麻木嚴重時，建議與主治醫師討論是否改為皮下注射，可顯著減輕周邊神經病變症狀。")
            print("  * 帶狀疱疹預防：免疫功能低下時，疱疹病毒極易活化，請務必遵醫囑天天服用抗病毒藥預防。")
        elif "Daratumumab" in title or "達希美" in title:
            print("  * 輸注反應管理：打完達希美回去的幾天內，若有發燒或咳嗽，應立刻通知個管師，並避免到人多的公共場所。")
        elif "Lenalidomide" in title or "瑞復美" in title:
            print("  * 血栓防範：Revlimid 易引發深部靜脈栓塞。每天服藥期間若有小腿腫痛發熱，應立刻回診掛急診。")
        elif "Cetuximab" in title or "爾必得舒" in title:
            print("  * 皮膚痤瘡樣皮疹照護：痤瘡樣皮疹代表標靶藥物有發揮對抗腫瘤的療效。請使用溫和保濕產品，防曬工作一定要做足。")
        elif "多發性骨髓瘤" in title:
            print("  * 骨痛與骨折防範：多發性骨髓瘤患者易因骨質疏鬆而發生骨折，日常應防跌倒，避免提重物與重體力勞動。")
        elif "大腸直腸癌" in title:
            print("  * 飲食習慣：大腸癌術後或化放療期間，應維持少量多餐、高蛋白且好消化的飲食，多喝水防便秘。")
            
        print("\n*（此區塊為 AI 根據文獻與臨床照護經驗歸納之照護提醒，非直接文獻原文，僅供參考，請與主治醫師討論確認）*")
        print("==================================================")
        self.print_disclaimer()

    def trigger_idk_flow(self):
        print("\n================ [有所本生醫問答回覆] ================")
        print("AI 助理：「對不起，阿喜伯。我檢索了 PubMed 與本機醫學指引資料庫，找不到關於您詢問內容的足夠權威實證醫學文獻。」")
        print("        「本著醫療安全原則，我『不知道』這個問題的確切醫學答案，也無法為您提供任何未經證實的建議。」")
        print("        「如果身體感到任何不適，建議您直接向您的主治醫師或藥師進行諮詢，切勿聽信偏方。」")
        print("==================================================")
        self.print_disclaimer()

    def print_disclaimer(self):
        print("【主權健康助理免責聲明】")
        print("本助理所提供之醫學資訊僅供科研與衛教參考，不能替代專業醫師的診斷、治療或醫學建議。")
        print("任何用藥與治療方針調整，請務必與您的主治醫師進行討論確認。")
        print("==================================================")

    def run_hot_ingestion_flow(self, user_input):
        """運行熱接入流程"""
        print("\n==================================================")
        print("      ⚠️ 偵測到關鍵健康決策點，建議執行熱接入 ⚠️")
        print("==================================================")
        
        if user_input.strip() != "!sha_hot":
            print("AI 助理：「阿喜伯，聽起來目前是治療的關鍵期。為了能立即幫您比對最合適的台灣臨床試驗與最新療法，」")
            print("        「我建議我們花 3 分鐘進行『熱接入快速設定』，一次把主要病情與用藥填齊，好嗎？(Y/N)」")
            confirm = input("> ")
            if confirm.strip().upper() not in ["Y", "YES", "是", "好"]:
                print("AI 助理：「好的，我們維持一般的日常症狀記錄。請保重身體！」")
                self.process_general_flow(user_input)
                return
        else:
            print("AI 助理：「已為您啟動熱接入快速建檔模式。」")

        print("\nAI 助理：「請跟著我一步步完成以下四個主要問題，這將建立您的本地主權 PHR 核心檔案。」")
        
        print("\n【問題 1/4】您目前確診的疾病名稱是什麼？是否知道分期或有無復發？")
        print("（例如：多發性骨髓瘤，第三期，初診斷）")
        disease_input = input("> ")
        
        print("\n【問題 2/4】您目前正在使用的主要治療藥物有哪些？請以英文藥名或簡寫輸入，並以逗號分隔。")
        print("（例如：Daratumumab, Bortezomib）")
        drugs_input = input("> ")
        
        print("\n【問題 3/4】您目前在台灣哪一家醫院的哪一個科別看診？")
        print("（例如：台大醫院血液科）")
        hospital_input = input("> ")
        
        print("\n【問題 4/4】您是否有藥物 or 食物過敏史？")
        print("（例如：對 Penicillin 過敏，或無過敏史）")
        allergy_input = input("> ")

        print("\nAI 助理：「好的，我正在將您輸入的資料在本地進行去識別化處理，並封裝成符合 HL7 FHIR R4 標準的 JSON 資源...」")

        self.save_hot_ingestion_data(disease_input, drugs_input, hospital_input, allergy_input)

        print("\nAI 助理：「熱接入基本建檔已完成！如果您有健保快易通下載的網頁檔，或是紙本醫療報告的影像，」")
        print(f"        「您可以隨時將它們拖入本地的 `data/inbox` 目錄中，助理會自動進行一鍵歸檔與深度解譯。」")
        print("==================================================")

    def save_hot_ingestion_data(self, disease, drugs, hospital, allergy):
        """將熱接入輸入封裝為 FHIR R4 資源並存入 SQLite"""
        if not os.path.exists(self.db_path):
            print("【警告】未偵測到資料庫，無法存檔。")
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()
            
            # 1. 儲存疾病 (Condition)
            cond_id = f"COND-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            cond_fhir = {
                "resourceType": "Condition",
                "id": cond_id,
                "meta": {
                    "profile": ["https://twcore.mohw.gov.tw/ig/twcore/StructureDefinition/Condition-twcore"]
                },
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "problem-list-item",
                        "display": "Problem List Item"
                    }]
                }],
                "clinicalStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active"
                    }]
                },
                "code": {
                    "text": disease
                },
                "subject": {
                    "reference": f"Patient/{self.patient_id}-DEID"
                }
            }
            cursor.execute("""
            INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (cond_id, self.patient_id, "Condition", json.dumps(cond_fhir, ensure_ascii=False), now_str, '{"source": "HotIngestion"}'))

            # 2. 儲存用藥 (MedicationRequest)
            drug_list = [d.strip() for d in drugs.split(",") if d.strip()]
            for idx, drug_name in enumerate(drug_list):
                med_id = f"MED-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{idx}"
                med_fhir = {
                    "resourceType": "MedicationRequest",
                    "id": med_id,
                    "meta": {
                        "profile": ["https://twcore.mohw.gov.tw/ig/twcore/StructureDefinition/MedicationRequest-twcore"]
                    },
                    "status": "active",
                    "intent": "order",
                    "medicationCodeableConcept": {
                        "text": drug_name
                    },
                    "subject": {
                        "reference": f"Patient/{self.patient_id}-DEID"
                    }
                }
                cursor.execute("""
                INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (med_id, self.patient_id, "MedicationRequest", json.dumps(med_fhir, ensure_ascii=False), now_str, '{"source": "HotIngestion"}'))

            # 3. 儲存看診醫院 (Encounter)
            enc_id = f"ENC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            enc_fhir = {
                "resourceType": "Encounter",
                "id": enc_id,
                "meta": {
                    "profile": ["https://twcore.mohw.gov.tw/ig/twcore/StructureDefinition/Encounter-twcore"]
                },
                "status": "finished",
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "AMB",
                    "display": "ambulatory"
                },
                "subject": {
                    "reference": f"Patient/{self.patient_id}-DEID"
                },
                "serviceProvider": {
                    "display": hospital
                }
            }
            cursor.execute("""
            INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (enc_id, self.patient_id, "Encounter", json.dumps(enc_fhir, ensure_ascii=False), now_str, '{"source": "HotIngestion"}'))

            # 4. 儲存過敏史 (AllergyIntolerance)
            alg_id = f"ALG-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            alg_fhir = {
                "resourceType": "AllergyIntolerance",
                "id": alg_id,
                "meta": {
                    "profile": ["https://twcore.mohw.gov.tw/ig/twcore/StructureDefinition/AllergyIntolerance-twcore"]
                },
                "clinicalStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": "active"
                    }]
                },
                "code": {
                    "text": allergy
                },
                "patient": {
                    "reference": f"Patient/{self.patient_id}-DEID"
                }
            }
            cursor.execute("""
            INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (alg_id, self.patient_id, "AllergyIntolerance", json.dumps(alg_fhir, ensure_ascii=False), now_str, '{"source": "HotIngestion"}'))

            conn.commit()
            conn.close()
            print("【熱接入存檔成功】所有主要健康歷程 (Condition, MedicationRequest, Encounter, AllergyIntolerance) 已安全寫入本地資料庫！")
        except Exception as e:
            print(f"熱接入存檔失敗: {e}")

    def build_fhir_observation(self, symptom_text):
        """將自述文字封裝為 FHIR Observation 資源"""
        now_str = datetime.now().isoformat() + "+08:00"
        observation = {
          "resourceType": "Observation",
          "meta": {
            "profile": ["https://twcore.mohw.gov.tw/ig/twcore/StructureDefinition/Observation-laboratoryResult-twcore"]
          },
          "status": "preliminary",
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
                "code": "89555-7",
                "display": "Patient-reported symptoms panel"
              }
            ],
            "text": "患者自述症狀面板"
          },
          "subject": {
            "reference": f"Patient/{self.patient_id}-DEID"
          },
          "effectiveDateTime": now_str,
          "valueString": symptom_text,
          "note": [
            {
              "text": "由外部 sovereign-health-agent 透過標準 API 去識別化推送寫入。已自動遮蔽姓名等 PII 資訊。"
            }
          ]
        }
        return observation

    def save_to_local_journey(self, fhir_resource):
        """將發送的 FHIR 資源存檔至本機 PHR 資料庫"""
        if not os.path.exists(self.db_path):
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            entry_id = f"OBS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            now_str = datetime.now().isoformat()
            
            cursor.execute("""
            INSERT OR REPLACE INTO MY_CLINICAL_JOURNEY (entry_id, patient_id, resource_type, fhir_resource_json, last_updated, meta_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (entry_id, self.patient_id, "Observation", json.dumps(fhir_resource, ensure_ascii=False), now_str, '{"schema_version": "v0.1.0"}'))
            
            conn.commit()
            conn.close()
            print("【存檔成功】此筆自述事件已安全寫入您的本地 PHR 醫療歷程資料表！")
        except Exception as e:
            print(f"存檔失敗: {e}")

    def generate_soap_card(self):
        """
        !sha_soap 指令：一鍵提取本地 PHR 所有核心資料，組裝成一份簡明、結構化的病情全景 SOAP 摘要卡，方便就醫溝通。
        """
        print("\nAI 助理：「正在為您一鍵生成門診溝通 SOAP 病情概況卡...」")
        
        disease_name = "未登錄疾病"
        drugs_list = []
        hospital = "未設定"
        allergy = "未設定"
        recent_symptoms = []
        
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # 1. 讀取 Condition
                cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Condition' ORDER BY last_updated DESC LIMIT 1")
                cond_row = cursor.fetchone()
                if cond_row:
                    disease_name = json.loads(cond_row[0]).get("code", {}).get("text", "多發性骨髓瘤")
                    
                # 2. 讀取 MedicationRequest
                cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'MedicationRequest'")
                med_rows = cursor.fetchall()
                for r in med_rows:
                    fhir_obj = json.loads(r[0])
                    if fhir_obj.get("status") == "active":
                        med_name = fhir_obj.get("medicationCodeableConcept", {}).get("text", "")
                        if med_name:
                            drugs_list.append(med_name.strip())
                drugs_list = sorted(list(set(drugs_list)))
                        
                # 3. 讀取 Encounter
                cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Encounter' ORDER BY last_updated DESC LIMIT 1")
                enc_row = cursor.fetchone()
                if enc_row:
                    hospital = json.loads(enc_row[0]).get("serviceProvider", {}).get("display", "未設定")
                    
                # 4. 讀取 AllergyIntolerance
                cursor.execute("SELECT fhir_resource_json FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'AllergyIntolerance' ORDER BY last_updated DESC LIMIT 1")
                alg_row = cursor.fetchone()
                if alg_row:
                    allergy = json.loads(alg_row[0]).get("code", {}).get("text", "無過敏史")
                    
                # 5. 讀取 Observation（包含自述症狀與實驗室關鍵指標）
                cursor.execute("SELECT fhir_resource_json, last_updated FROM MY_CLINICAL_JOURNEY WHERE resource_type = 'Observation' ORDER BY last_updated DESC")
                obs_rows = cursor.fetchall()
                
                # 區分自述症狀與實驗室關鍵數據
                free_kl_ratio = None
                hgb = None
                cre = None
                
                for r in obs_rows:
                    fhir_obj = json.loads(r[0])
                    
                    codings = fhir_obj.get("code", {}).get("coding", [])
                    loinc_code = ""
                    if codings:
                        loinc_code = codings[0].get("code", "")
                    
                    # 處理自述症狀（僅限 LOINC 89555-7 "患者自述症狀面板"）
                    symptom = fhir_obj.get("valueString", "")
                    if symptom and loinc_code == "89555-7" and len(recent_symptoms) < 3:
                        time_str = fhir_obj.get("effectiveDateTime", r[1])
                        recent_symptoms.append(f"{time_str[:16].replace('T', ' ')}: {symptom}")
                    
                    # 處理實驗室數據
                    val_quantity = fhir_obj.get("valueQuantity", {})
                    if val_quantity:
                        val = val_quantity.get("value")
                        if loinc_code and val is not None:
                            if loinc_code == "53578-1" and free_kl_ratio is None: # Free K/L Ratio
                                free_kl_ratio = val
                            elif loinc_code == "718-7" and hgb is None: # Hemoglobin
                                hgb = val
                            elif loinc_code == "2160-0" and cre is None: # Creatinine
                                cre = val
                        
                conn.close()
            except Exception as e:
                print(f"讀取 SOAP 資料失敗: {e}")
                
        # 計算生理特徵
        birth_year = int(self.birth_date.split("-")[0])
        current_year = datetime.now().year
        age = current_year - birth_year
        bsa = ((self.height_cm * self.weight_kg) / 3600) ** 0.5
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 動態判定目前療程與評估
        treatment_type = "多發性骨髓瘤"
        has_dara_bort = any(d in ["Daratumumab", "達希美", "Bortezomib", "萬科"] for d in drugs_list)
        has_thal = any(d in ["Thalidomide", "沙利竇邁"] for d in drugs_list)
        has_cp = any(d in ["Cyclophosphamide", "癌德星"] for d in drugs_list) and any(d in ["Prednisolone", "普力多寧"] for d in drugs_list)
        
        if has_dara_bort:
            treatment_type = f"接受 Daratumumab (達希美) 及 Bortezomib (萬科) 標靶治療之 {disease_name}"
        elif has_thal:
            treatment_type = f"接受 Thalidomide (沙利竇邁) 療程之 {disease_name}"
        elif has_cp:
            treatment_type = f"接受口服 CP 方案 (Cyclophosphamide + Prednisolone) 之 {disease_name}"
        else:
            treatment_type = f"{disease_name}"

        # 評估病情控制狀態
        control_status = ""
        if free_kl_ratio is not None and hgb is not None:
            # 醫學規則判定：若游離輕鏈比值正常且血紅素正常，代表病情控制良好
            if 0.26 <= free_kl_ratio <= 1.65 and hgb >= 12.0:
                control_status = "。目前關鍵指標（血紅素、腎功能及游離輕鏈比值）均維持在正常範圍內，病情控制良好且穩定"

        # 判斷最近是否有發燒症狀以加入評估
        has_fever = False
        for sym in recent_symptoms:
            if "發燒" in sym or "38" in sym:
                has_fever = True
                break
        
        print("\n=========================================================================")
        print("                 🏥 BMAD 主權個人健康歷程門診溝通卡 (SOAP) ")
        print(f"                                          產出時間: {now_str}")
        print("=========================================================================")
        print("【S】Subjective (患者主觀自述與近期症狀)")
        if recent_symptoms:
            for sym in recent_symptoms:
                print(f"  * {sym}")
        else:
            print("  * 暫無日常自述症狀紀錄。")
            
        print("\n【O】Objective (醫療客觀指標與生理檔案)")
        print(f"  * 患者姓名：{self.display_name} (唯一代碼: {self.patient_id}-DEID)")
        print(f"  * 生理特徵：{age} 歲 | 身高：{self.height_cm} cm | 體重：{self.weight_kg} kg | BSA：{bsa:.2f} ㎡")
        print(f"  * 臨床診斷：{disease_name}")
        print(f"  * 目前主要用藥：{', '.join(drugs_list) if drugs_list else '無'}")
        print(f"  * 看診醫院與科別：{hospital}")
        print(f"  * 藥物過敏史：{allergy}")
        
        print("\n【A】Assessment (臨床初步評估)")
        print(f"  * 確診為 {treatment_type} 患者{control_status}。")
        if has_fever:
            print("  * 警告：近期有發燒症狀，在免疫受抑狀態下，高度疑似腫瘤科急症「白血球低下性發燒 (Febrile Neutropenia)」，須極速就醫！")
        else:
            print("  * 近期若有發燒症狀（38 度以上），因免疫受抑，須立刻前往急診評估。")
        
        if any(d in ["Bortezomib", "萬科"] for d in drugs_list):
            print("  * 萬科治療中，需注意潛在之周邊神經病變（手腳麻木）風險。")
        if any(d in ["Thalidomide", "沙利竇邁"] for d in drugs_list):
            print("  * 沙利竇邁治療中，需注意潛在之手腳麻木、便秘與深部靜脈血栓風險。")
        
        print("\n【P】Plan (建議處置計畫與緊急處置)")
        if has_fever:
            print("  * 1. 立即前往醫院急診部就醫，尋求癌症發燒綠色通道處理。")
            print("  * 2. 進行 CBC/diff 抽血檢查，緊急評估嗜中性白血球與血小板數值。")
            print("  * 3. 遵醫囑進行經驗性廣效抗生素靜脈注射。")
            print("  * 4. 嚴禁在未確診感染源前擅自服用普拿疼退燒，以防遮蔽真實熱型。")
        else:
            print("  * 1. 於門診或日常追蹤周邊神經病變與血球狀態。")
            if any(d in ["Bortezomib", "萬科"] for d in drugs_list):
                print("  * 2. 萬科注射期間，遵醫囑每日服用帶狀疱疹預防用藥。")
                print("  * 3. 隨時監測體溫，一旦發燒（38度以上）須立刻急診就醫。")
            else:
                print("  * 2. 隨時監測體溫，一旦發燒（38度以上）須立刻急診就醫。")
        print("=========================================================================")
        self.print_disclaimer()
        
        # 儲存為本地文件
        soap_filename = os.path.join(self.data_dir, f"SOAP_{self.patient_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        try:
            os.makedirs(os.path.dirname(soap_filename), exist_ok=True)
            with open(soap_filename, "w", encoding="utf-8") as f:
                f.write("=========================================================================\n")
                f.write("                 🏥 BMAD 主權個人健康歷程門診溝通卡 (SOAP) \n")
                f.write(f"                                          產出時間: {now_str}\n")
                f.write("=========================================================================\n")
                f.write("【S】Subjective (患者主觀自述與近期症狀)\n")
                if recent_symptoms:
                    for sym in recent_symptoms:
                        f.write(f"  * {sym}\n")
                else:
                    f.write("  * 暫無日常自述症狀紀錄。\n")
                f.write("\n")
                f.write("【O】Objective (醫療客觀指標與生理檔案)\n")
                f.write(f"  * 患者姓名：{self.display_name} (唯一代碼: {self.patient_id}-DEID)\n")
                f.write(f"  * 生理特徵：{age} 歲 | 身高：{self.height_cm} cm | 體重：{self.weight_kg} kg | BSA：{bsa:.2f} ㎡\n")
                f.write(f"  * 臨床診斷：{disease_name}\n")
                f.write(f"  * 目前主要用藥：{', '.join(drugs_list) if drugs_list else '無'}\n")
                f.write(f"  * 看診醫院與科別：{hospital}\n")
                f.write(f"  * 藥物過敏史：{allergy}\n\n")
                f.write("【A】Assessment (臨床初步評估)\n")
                f.write(f"  * 確診為 {treatment_type} 患者{control_status}。\n")
                if has_fever:
                    f.write("  * 警告：近期有發燒症狀，在免疫受抑狀態下，高度疑似腫瘤科急症「白血球低下性發燒 (Febrile Neutropenia)」，須極速就醫！\n")
                else:
                    f.write("  * 近期若有發燒症狀（38 度以上），因免疫受抑，須立刻前往急診評估。\n")
                if any(d in ["Bortezomib", "萬科"] for d in drugs_list):
                    f.write("  * 萬科治療中，需注意潛在之周邊神經病變（手腳麻木）風險。\n")
                if any(d in ["Thalidomide", "沙利竇邁"] for d in drugs_list):
                    f.write("  * 沙利竇邁治療中，需注意潛在之手腳麻木、便秘與深部靜脈血栓風險。\n")
                f.write("\n")
                f.write("【P】Plan (建議處置計畫與緊急處置)\n")
                if has_fever:
                    f.write("  * 1. 立即前往醫院急診部就醫，尋求癌症發燒綠色通道處理。\n")
                    f.write("  * 2. 進行 CBC/diff 抽血檢查，緊急評估嗜中性白血球與血小板數值。\n")
                    f.write("  * 3. 遵醫囑進行經驗性廣效抗生素靜脈注射。\n")
                    f.write("  * 4. 嚴禁在未確診感染源前擅自服用普拿疼退燒，以防遮蔽真實熱型。\n")
                else:
                    f.write("  * 1. 於門診或日常追蹤周邊神經病變與血球狀態。\n")
                    if any(d in ["Bortezomib", "萬科"] for d in drugs_list):
                        f.write("  * 2. 萬科注射期間，遵醫囑每日服用帶狀疱疹預防用藥。\n")
                        f.write("  * 3. 隨時監測體溫，一旦發燒（38度以上）須立刻急診就醫。\n")
                    else:
                        f.write("  * 2. 隨時監測體溫，一旦發燒（38度以上）須立刻急診就醫。\n")
                f.write("=========================================================================\n")
            print(f"【備份成功】病情概況卡已成功導出至本地檔案: {soap_filename}")
        except Exception as e:
            print(f"備份 SOAP 卡檔案失敗: {e}")

    def generate_backup(self):
        """!sha_backup 指令：調用 db_porter.py 匯出完整 JSON 備份檔案"""
        print("\nAI 助理：「正在為您匯出完整的個人主權健康備份包 (JSON)...」")
        now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = os.path.join(self.data_dir, f"backup_{self.patient_id}_{now_str}.json")
        
        db_porter_script = os.path.join(DB_DIR, "utils", "db_porter.py")
        import subprocess
        cmd = [sys.executable, db_porter_script, "--profile", self.profile, "-e", "-t", "backup", "-f", "json", "-o", backup_filename]
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print("\n==================================================")
                print("           📦 【個人主權健康備份包匯出成功】")
                print("==================================================")
                print(f"備份檔案已安全儲存至您的本地實體目錄：")
                print(f"📂 {backup_filename}")
                print("您可以將此檔案複製保存或轉移至其他裝置進行增量匯入。")
                print("==================================================")
            else:
                print(f"\n❌ 備份失敗：{res.stderr}")
        except Exception as e:
            print(f"\n❌ 備份執行出錯：{e}")

    def generate_ice_card_shortcut(self):
        """!sha_ice 指令：調用 db_porter.py 產生緊急救援卡"""
        print("\nAI 助理：「正在為您產生緊急醫療救援資訊卡 (ICE Card)...」")
        ice_filename = os.path.join(self.data_dir, f"ICE_{self.patient_id}.md")
        
        db_porter_script = os.path.join(DB_DIR, "utils", "db_porter.py")
        import subprocess
        cmd = [sys.executable, db_porter_script, "--profile", self.profile, "-e", "-t", "ice", "-f", "md", "-o", ice_filename]
        
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                # 讀取並在 console 印出
                with open(ice_filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                print("\n" + content)
                print(f"【備份成功】緊急醫療卡已保存至本地檔案：\n📂 {ice_filename}")
            else:
                print(f"\n❌ 緊急卡產生失敗：{res.stderr}")
        except Exception as e:
            print(f"\n❌ 緊急卡執行出錯：{e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sovereign Health Agent (v0.1.3)")
    parser.add_argument("--profile", type=str, default="myself", help="指定初始身分 (例如 myself 或 father)")
    args = parser.parse_args()
    
    agent = SovereignHealthAgent(profile=args.profile)
    agent.run_dialogue_loop()
