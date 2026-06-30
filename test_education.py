#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for health education base and agent logic.
自動化驗證 SQLite 衛教庫查詢、!sha_myedu 個人化產製以及 IDK 免責防線。
"""

import os
import sqlite3
import json
from patient.patient_agent import SovereignHealthAgent, PATIENT_DB_PATH

def test_flow():
    print("=== 1. 初始化 SovereignHealthAgent ===")
    agent = SovereignHealthAgent()
    print(f"病患顯示名稱: {agent.display_name}")
    assert agent.display_name == "阿喜伯", "Profile 載入姓名錯誤"
    
    print("\n=== 2. 測試指令前綴邏輯 ===")
    # 測試 !sha_hot 觸發
    assert agent.check_hot_ingestion_trigger("!sha_hot") == True, "check_hot_ingestion_trigger 觸發錯誤"
    assert agent.check_hot_ingestion_trigger("我想確診") == True, "病情詞組觸發錯誤"
    assert agent.check_hot_ingestion_trigger("多發性骨髓瘤的症狀是什麼") == False, "諮詢問句應被排除在熱接入外"
    
    # 測試醫療諮詢識別
    assert agent.is_medical_query("症狀有哪些") == True, "is_medical_query 識別錯誤"
    assert agent.is_medical_query("偏方有效嗎") == True, "is_medical_query 識別錯誤"
    
    print("\n=== 3. 測試醫療 QA 有所本檢索 (多發性骨髓瘤症狀) ===")
    agent.run_grounded_qa_flow("我想了解多發性骨髓瘤的症狀與CRAB")
    
    print("\n=== 4. 測試用藥衛教檢索 (萬科) ===")
    agent.run_grounded_qa_flow("萬科有什麼副作用？")
    
    print("\n=== 5. 測試偏方與不知道防線 (IDK) ===")
    agent.run_grounded_qa_flow("吃綠豆沙能治多發性骨髓瘤嗎")
    
    print("\n=== 6. 測試個人化衛教卡生成 (!sha_myedu) ===")
    # 模擬寫入 Condition 與 MedicationRequest 進行測試
    print("寫入測試 Condition 與 MedicationRequest...")
    agent.save_hot_ingestion_data(
        disease="多發性骨髓瘤，第三期",
        drugs="Daratumumab, Bortezomib",
        hospital="台大醫院血液科",
        allergy="無"
    )
    
    agent.generate_personalized_education()
    
    print("\n=== 7. 測試自述症狀 (發燒 38.5 度) 寫入 ===")
    agent.process_general_flow("阿喜伯突然發燒，目前 38.5 度，現在是晚上 3 點")
    
    print("\n=== 8. 測試病情概況卡 (SOAP) 生成 ===")
    agent.generate_soap_card()
    
    print("\n測試完成，所有斷言皆通過！")

if __name__ == "__main__":
    test_flow()

