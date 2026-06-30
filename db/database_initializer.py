#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Initializer for Sovereign Health Agent (v0.1.0)
一鍵物理建立並初始化病患自主 PHR 資料庫，並預載虛擬病人 004 (阿喜伯) 之個人健康歷程與同意書數據。
本腳本完全採用台灣繁體中文語境之系統工程術語與註解。
"""

import os
import sqlite3
import json
from datetime import datetime

# 取得目前檔案所在目錄，確保相對路徑正常運行
DB_DIR = os.path.dirname(os.path.abspath(__file__))

# 定義範本資料庫物理路徑，作為系統冷啟動的種子來源
TEMPLATE_DB_PATH = os.path.join(DB_DIR, "template.db")

def init_patient_db():
    print(f"正在初始化病患自主 PHR 範本資料庫: {TEMPLATE_DB_PATH}")
    conn = sqlite3.connect(TEMPLATE_DB_PATH)
    cursor = conn.cursor()
    
    # 1. 使用者個人資料表 (MY_PROFILE)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS MY_PROFILE (
        patient_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        meta_data TEXT DEFAULT '{}'
    );
    """)
    
    # 2. 病患醫療歷程 FHIR Bundle 表 (MY_CLINICAL_JOURNEY)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS MY_CLINICAL_JOURNEY (
        entry_id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        artifact_id TEXT,
        resource_type TEXT NOT NULL,
        fhir_resource_json TEXT NOT NULL,
        last_updated TEXT NOT NULL,
        meta_data TEXT DEFAULT '{}'
    );
    """)
    
    # 3. 使用者免責與不爭訟簽署合約表 (USER_CONSENTS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS USER_CONSENTS (
        consent_id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        consent_version TEXT NOT NULL,
        fido_cert_sn TEXT,
        signature_hash TEXT,
        signed_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        contract_text_hash TEXT NOT NULL,
        consent_type TEXT DEFAULT 'online_otp', -- 'online_otp' / 'offline_paper'
        paper_artifact_hash TEXT,
        meta_data TEXT DEFAULT '{}'
    );
    """)

    # 4. 我的衛教知識庫 (MY_EDUCATION_BASE)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS MY_EDUCATION_BASE (
        knowledge_id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        disease_name TEXT NOT NULL,
        keyword TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        citations TEXT,
        last_updated TEXT NOT NULL,
        meta_data TEXT DEFAULT '{}'
    );
    """)

    # 5. 原始資料定錨表 (RAW_ARTIFACTS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS RAW_ARTIFACTS (
        artifact_id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        meta_data TEXT DEFAULT '{}'
    );
    """)
    
    # 預載個人設定（包含出生日期、身高與體重，以利臨床用藥劑量計算）
    cursor.execute("""
    INSERT OR REPLACE INTO MY_PROFILE (patient_id, display_name, email, phone, meta_data)
    VALUES ('PUMC_004', '阿喜伯', 'wang004@taiwan.tw', '0912-345-678', 
    '{"schema_version": "v0.1.0", "phr_sync_status": "synced", "birth_date": "1958-08-08", "height_cm": 170, "weight_kg": 85}');
    """)
    
    # 預載病患的免責同意書
    cursor.execute("""
    INSERT OR REPLACE INTO USER_CONSENTS (
        consent_id, patient_id, consent_version, fido_cert_sn, signature_hash, signed_at, is_active, contract_text_hash, consent_type, paper_artifact_hash, meta_data
    )
    VALUES (
        'CNS-20260520-004', 'PUMC_004', 'v0.2.1', NULL, NULL, '2026-05-20 14:30:00', 1,
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        'offline_paper',
        '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88d5dbbab21824a',
        '{"schema_version": "v0.1.0", "consent_medium": "paper_scan"}'
    );
    """)

    # 預載衛教數據
    education_data = [
        (
            "EDU_MM_DISEASE",
            "disease",
            "多發性骨髓瘤",
            "多發性骨髓瘤,症狀,CRAB",
            "多發性骨髓瘤疾病成因與 CRAB 症狀說明",
            "多發性骨髓瘤是漿細胞（一種白血球）惡性增生所導致的癌症。癌化的漿細胞會大量浸潤骨髓，並產生異常的單株免疫球蛋白（M 蛋白），造成以下四大核心症狀（簡稱 CRAB）：\n"
            "1. 高血鈣 (C - Calcium elevation)：癌細胞破壞骨骼使鈣質釋出，會引起口渴、多尿、便秘、噁心、甚至意識模糊。\n"
            "2. 腎功能不全 (R - Renal insufficiency)：M 蛋白沈積於腎小管，導致蛋白尿與慢性腎衰竭，症狀包括水腫、尿量減少、疲倦。\n"
            "3. 貧血 (A - Anemia)：惡性漿細胞排擠正常造血細胞，引發貧血，使人常感到頭暈、易喘、無力。\n"
            "4. 骨骼病變與骨痛 (B - Bone lesions)：骨髓瘤細胞分泌細胞激素活化噬骨細胞，導致嚴重的骨質疏鬆、骨折與劇烈骨痛，常見於脊椎骨、肋骨與骨盆。",
            "[NCCN 癌症治療指引 2026, 台灣血液病學會多發性骨髓瘤診治指引 2025]",
            "2026-06-12",
            "{}"
        ),
        (
            "EDU_MM_DRUG_DARA",
            "medication",
            "多發性骨髓瘤",
            "Daratumumab,達希美,Darzalex",
            "標靶藥物 Daratumumab (達希美) 用藥須知",
            "Daratumumab 是一種抗 CD38 單株抗體，專門結合多發性骨髓瘤細胞表面的 CD38 抗原，進而啟動患者自身的免疫系統來攻擊並消滅癌細胞。\n"
            "【注意事項與副作用照護】：\n"
            "1. 輸注反應：首次注射時極易發生發燒、發冷、鼻塞、呼吸急促或喉嚨癢等症狀。護理人員會在輸注前給予抗組織胺與類固醇藥物以預防反應。\n"
            "2. 呼吸道感染：本藥會降低患者免疫力，增加感冒或肺炎風險，若出現發燒、咳嗽，請務必立即回診。\n"
            "3. 疲倦與體力減退：服藥期間應避免過度勞累，維持充足休息。",
            "[PubMed PMID: 27557302, NCCN 癌症治療指引 2026]",
            "2026-06-12",
            "{}"
        ),
        (
            "EDU_MM_DRUG_BOR",
            "medication",
            "多發性骨髓瘤",
            "Bortezomib,萬科,Velcade",
            "標靶藥物 Bortezomib (萬科) 用藥須知",
            "Bortezomib 屬於蛋白酶體抑制劑，藉由阻斷癌細胞內的蛋白質垃圾清理機制（蛋白酶體），使異常蛋白質在癌細胞內堆積，進而引發癌細胞凋亡。\n"
            "【注意事項與副作用照護】：\n"
            "1. 周邊神經病變：為萬科最常見的副作用，表現為手套或襪子區域的雙手、雙腳針刺感、麻木或燒灼性疼痛。若症狀嚴重，請主動告知醫師，通常可透過改為皮下注射（Subcutaneous）或調整劑量來改善。\n"
            "2. 帶狀疱疹復發（皮蛇）：因免疫受抑，帶狀疱疹復發風險很高。臨床上強烈建議遵醫囑每日預防性口服抗病毒藥物（如 Acyclovir）以防止皮蛇復發。\n"
            "3. 血小板低下：服藥後血小板可能在用藥週期第 11 天降至最低，請注意皮膚是否有不明瘀青、流鼻血或牙齦出血。",
            "[PubMed PMID: 18711175, 衛福部健保藥物說明書]",
            "2026-06-12",
            "{}"
        ),
        (
            "EDU_MM_DRUG_LEN",
            "medication",
            "多發性骨髓瘤",
            "Lenalidomide,瑞復美,Revlimid",
            "免疫調節劑 Lenalidomide (瑞復美) 用藥須知",
            "Lenalidomide 具有三合一作用：調節免疫反應（增強 T 細胞與自然殺手細胞活性）、防範血管新生（切斷腫瘤養分），並能直接誘導骨髓瘤細胞凋亡。\n"
            "【注意事項與副作用照護】：\n"
            "1. 深部靜脈栓塞 (DVT)：這是最嚴重的潛在副作用，表現為單側下肢突發性紅腫、發熱或疼痛。請遵醫囑服用預防性抗凝血藥物（如低劑量阿斯匹靈），若出現下肢不適應立刻就醫。\n"
            "2. 嗜中性白血球低下：容易引起白血球數量下降而發生嚴重感染，每次看診前需定期抽血追蹤血球計數。\n"
            "3. 胚胎胎兒毒性：有致畸胎風險，育齡男女服藥期間應嚴格採取有效避孕措施。",
            "[PubMed PMID: 27557302, 衛福部健保藥物說明書]",
            "2026-06-12",
            "{}"
        ),
        (
            "EDU_CRC_DISEASE",
            "disease",
            "大腸直腸癌",
            "大腸直腸癌,大腸癌,直腸癌,症狀",
            "大腸直腸癌成因與常見症狀說明",
            "大腸直腸癌是由大腸或直腸黏膜細胞在基因突變後，先形成腺瘤性瘜肉，再經多年惡化演變成的癌症。\n"
            "【常見臨床症狀】：\n"
            "1. 排便習慣改變：不明原因持續性腹瀉、便秘或大便變細。\n"
            "2. 血便或黏液便：糞便帶暗紅色血液或帶有黏液，常被誤認為痔瘡出血，導致延誤診斷。\n"
            "3. 體重減輕與貧血：腫瘤長期慢性微量出血導致貧血，進而出現疲倦、臉色蒼白，並常伴隨無預警體重下降。\n"
            "4. 腹痛與腹部腫塊：部分患者會出現下腹部間歇性絞痛或在腹部摸到硬塊。",
            "[NCCN 大腸直腸癌治療指引 2026, 台灣癌症登記報告 2024]",
            "2026-06-12",
            "{}"
        ),
        (
            "EDU_CRC_DRUG_CET",
            "medication",
            "大腸直腸癌",
            "Cetuximab,爾必得舒,Erbitux",
            "標靶藥物 Cetuximab (爾必得舒) 用藥須知",
            "Cetuximab 是一種針對表皮生長因子受體 (EGFR) 的單株抗體標靶藥物。它專門結合於癌細胞表面的 EGFR，阻斷傳導路徑，藉此抑制癌細胞生長。本藥僅適用於 RAS 基因野生型 (Wild-type) 的轉移性大腸直腸癌患者。\n"
            "【注意事項與副作用照護】：\n"
            "1. 痤瘡樣皮疹：通常於服藥一至二週內，在臉部、胸部、上背部出現類似青春痘的皮疹。這是藥物有效的指標之一。請使用溫水洗臉，塗抹無刺激性保濕霜，避免擠壓皮疹，並於出門時加強防曬 (SPF30+)，必要時請醫師開立口服或外用抗生素。\n"
            "2. 甲溝炎：長期使用可能使指甲周圍紅腫、疼痛甚至化膿。修剪指甲時切勿剪得太深，並保持手腳乾燥乾淨。\n"
            "3. 低鎂血症：本藥會干擾腎臟對鎂的吸收，導致疲倦、肌肉痙攣，看診時需定期抽血監測電解質，必要時口服補充鎂離子。",
            "[PubMed PMID: 19622903, NCCN 大腸直腸癌指引 2026]",
            "2026-06-12",
            "{}"
        ),
        (
            "EDU_LTC_GUIDE",
            "disease",
            "長照與老化",
            "長照,長照2.0,1966,喘息服務,輔具",
            "台灣長照 2.0 申請與資源導航",
            "台灣長照 2.0 提供『照顧及專業服務』、『交通接送』、『輔具及居家無障礙環境改善』、『喘息服務』四大面向補助（俗稱長照四包錢）。\n【申請與評估流程】：\n1. 撥打 1966 專線或向醫院出院準備服務組申請。\n2. 照顧管理專員（照專）到府評估失能等級 (CMS 第 2 至 8 級)。\n3. 個案管理員與家屬擬定照顧計畫並媒合服務。\n【補助額度與負擔】：政府依據失能等級給予每月補助額度。一般戶自付額通常為 16%，中低收入戶為 5%，低收入戶全額免費。喘息服務可提供每年 14 至 21 天短期照顧補助，減輕主要照顧者負擔。",
            "[中華民國衛生福利部長期照顧服務指南 2026]",
            "2026-06-14",
            "{}"
        ),
        (
            "EDU_LTC_BARTHEL",
            "disease",
            "長照與老化",
            "巴氏量表,Barthel,失能等級",
            "巴氏量表 (Barthel Index) 自評與失能評估指引",
            "巴氏量表是台灣用來評估日常自理能力與申請外籍看護、長照補助的核心工具，總分 100 分，共包含十個項目：\n1. 進食、移位、個人盥洗、上廁所、洗澡、平地走動、上下樓梯、穿脫衣服、大便控制、小便控制。\n【評估標準與分級】：\n- 0 - 20 分：極重度失能（符合外籍看護工申請標準）。\n- 21 - 60 分：重度失能。\n- 61 - 90 分：中度失能。\n- 91 - 99 分：輕度失能。\n【自主健康管理提示】：家屬可利用巴氏量表定期自評（每月一次），記錄各分項分數的變化，這可作為物理/職能治療介入之療效指標，亦是長照複評的重要實證。",
            "[巴氏量表標準評估手冊, 衛生福利部公告 2025]",
            "2026-06-14",
            "{}"
        ),
        (
            "EDU_GER_BEERS",
            "medication",
            "長照與老化",
            "Beers,高齡用藥,跌倒,副作用,立普妥,Statin",
            "高齡多重用藥 Beers Criteria 與日常防跌指引",
            "高齡長輩常因共病面臨多重用藥（Polypharmacy），大幅增加藥物交互作用與跌倒風險。美國老年醫學會（AGS）Beers Criteria 定義了高齡者潛在不適當藥物（PIM）：\n1. 易致跌倒藥物：如強效安眠藥、肌肉鬆弛劑、抗組織胺及某些抗憂鬱/降血壓藥物，易引發頭暈、姿勢性低血壓。\n2. Statin 類藥物（如立普妥 Lipitor）：雖能有效降血脂，但少數高齡者易出現肌肉痠痛或無力。若長輩抱怨無力，可就醫檢測 CPK（肌酸激酶）以排除藥物肌肉毒性。\n【居家防跌三部曲】：\n- 醒後躺 30 秒、坐起 30 秒、站立 30 秒再邁步。\n- 浴室與走廊保持明亮，鋪設防滑墊，加裝扶手。高跌倒風險藥物建議於睡前服用，服藥後立即就寢。",
            "[AGS Beers Criteria 2023, 台灣老年醫學會高齡合理用藥指引 2025]",
            "2026-06-14",
            "{}"
        ),
        (
            "EDU_EOL_AD",
            "disease",
            "臨終安寧",
            "安寧,安寧緩和,病人自主權利法,預立決定,AD",
            "病人自主權利法與預立醫療決定 (AD) 簽署指引",
            "台灣《病人自主權利法》保障民眾在特定臨床狀態下，有拒絕或接受維持生命治療與人工營養的權利：\n1. 適用五大臨床條件：末期病人、處於不可逆轉之昏迷狀態、永久植物人、極重度失智、其他經政府公告之難以承受疾病。\n【預立醫療決定 (AD) 簽署流程】：\n- 步驟 1 (ACP 諮商)：病患、至少一位二親等內親屬，至指定醫院進行『預立醫療照護諮商』。\n- 步驟 2 (簽署意願)：填寫預立醫療決定書 (AD)，需兩位見證人簽名或公證。\n- 步驟 3 (健保卡註記)：由醫院上傳並註記於健保卡，即具備法定約束效力，保障尊嚴終老決定權。",
            "[台灣病人自主權利法 2019, 衛生福利部安寧緩和醫療宣導手冊 2025]",
            "2026-06-14",
            "{}"
        ),
        (
            "EDU_EOL_CARE",
            "disease",
            "臨終安寧",
            "臨終,安寧居家,喉音,護理,呼吸困難",
            "居家安寧舒適護理與臨終關懷指引",
            "臨終在宅安寧照護著重於提升病患的舒適度（Comfort Care），而非無益的侵入性搶救：\n1. 瀕死喉音（Death Rattle）：因無力吞嚥唾液，呼吸時喉部發出痰音。家屬請保持冷靜（病患此時並無痛苦），可協助翻身側臥，或以棉棒清潔口腔，『不建議進行抽痰』以免加劇疼痛。\n2. 呼吸困難：可微開窗戶、使用小風扇溫和吹拂病患臉部，並協助採取半坐臥姿以擴張肺部呼吸空間。\n3. 飲食拒絕：臨終階段器官衰竭，拒食為自然生理表現，切勿強行灌食以免造成吸入性肺炎。可用濕棉棒經常濕潤嘴唇以防乾燥。",
            "[台灣安寧照顧協會居家緩和護理指引 2025, 臨床安寧安詳照護手冊 2026]",
            "2026-06-14",
            "{}"
        )
    ]

    for item in education_data:
        cursor.execute("""
        INSERT OR REPLACE INTO MY_EDUCATION_BASE (
            knowledge_id, category, disease_name, keyword, title, content, citations, last_updated, meta_data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, item)
        
    conn.commit()
    conn.close()
    print("病患自主 PHR 範本資料庫初始化完成！")

def main():
    print("==================================================")
    print("   Sovereign Health Agent PHR 範本資料庫初始化啟動")
    print("==================================================")
    
    # 物理刪除舊的資料庫檔案以利重新乾淨建置
    if os.path.exists(TEMPLATE_DB_PATH):
        os.remove(TEMPLATE_DB_PATH)
        print(f"已物理清除舊範本庫: {os.path.basename(TEMPLATE_DB_PATH)}")
        
    init_patient_db()
    
    print("==================================================")
    print("    恭喜！病患個人 PHR 範本資料庫已成功初始化完成！")
    print("==================================================")

if __name__ == "__main__":
    main()
