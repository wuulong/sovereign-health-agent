#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tw_med_bridge.py - Sovereign Health Agent (SHA) 與 tw-med-db 邊界適配器 (Adapter)
[規格追溯]: SPC-010, SPC-039, SPC-040, DSN-020, REQ-024, NFR-005

功能：
1. 支援三級開關控制 (CLI 旗標 > 環境變數 > config.json > 預設路徑)。
2. 提供唯讀 (Read-only) 連線保護，嚴格隔離病患個人隱私資料庫 (fv_patient_personal.db)。
3. 封裝 M01 (處方藥證)、M02 (主成分)、M06 (健保給付規定) 與 M12 (LOINC 檢驗碼) 核心查詢。
4. 100% 安全平滑降級：若未安裝或未啟用 tw-med-db，所有函式安全回傳 None/空串列，不造成主程式崩潰。
"""

import os
import sys
import json
import sqlite3
import re
from typing import Optional, Dict, Any, List, Tuple

# 專案路徑解析
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")

# 預設候選 tw-med-db 路徑 (依相對位置探索)
CANDIDATE_MED_DB_PATHS = [
    os.path.abspath(os.path.join(PROJECT_DIR, "..", "..", "events", "TDHI_haba", "med-db-in", "tw-med-db", "db", "med.db")),
    os.path.abspath(os.path.join(PROJECT_DIR, "..", "tw-med-db", "db", "med.db")),
    os.path.abspath(os.path.join(PROJECT_DIR, "med.db")),
]

class TwMedBridge:
    """
    台灣醫療與健保開放大數據引擎 (tw-med-db) 橋接器
    具備開關控制、狀態診斷與防崩潰平滑降級能力。
    """
    def __init__(self, force_enabled: Optional[bool] = None, custom_db_path: Optional[str] = None):
        self.config_enabled = True
        self.config_db_path = None
        self._load_config()

        # 三級覆蓋開關判定
        if force_enabled is not None:
            self.enabled = force_enabled
        elif "ENABLE_TW_MED_DB" in os.environ:
            self.enabled = os.environ.get("ENABLE_TW_MED_DB", "1").strip().lower() in ("1", "true", "yes")
        else:
            self.enabled = self.config_enabled

        # 路徑判定
        if custom_db_path:
            self.db_path = custom_db_path
        elif os.environ.get("TW_MED_DB_PATH"):
            self.db_path = os.environ.get("TW_MED_DB_PATH")
        elif self.config_db_path:
            self.db_path = self.config_db_path
        else:
            self.db_path = self._discover_db_path()

        # 狀態診斷
        self.available, self.status_message = self._verify_connection()

    def _load_config(self):
        """讀取 SHA 根目錄 config.json"""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.config_enabled = cfg.get("enable_tw_med_db", True)
                    self.config_db_path = cfg.get("tw_med_db_path", None)
            except Exception:
                self.config_enabled = True
                self.config_db_path = None

    def _discover_db_path(self) -> Optional[str]:
        """依序探索預設候選路徑"""
        for path in CANDIDATE_MED_DB_PATHS:
            if os.path.exists(path):
                return path
        return None

    def _verify_connection(self) -> Tuple[bool, str]:
        """驗證資料庫可用性與核心表結構"""
        if not self.enabled:
            return False, "DISABLED_BY_CONFIG (開關已設定為關閉)"

        if not self.db_path or not os.path.exists(self.db_path):
            return False, "NOT_FOUND (未偵測到 tw-med-db 實體資料庫檔案)"

        try:
            uri = f"file:{os.path.abspath(self.db_path)}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='m01_tw_drug_db';")
            row = cursor.fetchone()
            conn.close()

            if row:
                return True, f"ENABLED_CONNECTED ({self.db_path})"
            else:
                return False, "INVALID_SCHEMA (資料庫內缺少 m01_tw_drug_db 核心表)"
        except Exception as e:
            return False, f"ERROR_CONNECTING ({str(e)})"

    def is_available(self) -> bool:
        """回傳 tw-med-db 是否可正常調用"""
        return self.available

    def get_status(self) -> Dict[str, Any]:
        """回傳當前 Bridge 詳細狀態資訊"""
        return {
            "enabled": self.enabled,
            "available": self.available,
            "status_message": self.status_message,
            "db_path": self.db_path
        }

    def _get_ro_connection(self) -> Optional[sqlite3.Connection]:
        """取得唯讀資料庫連線"""
        if not self.available:
            return None
        try:
            uri = f"file:{os.path.abspath(self.db_path)}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=2.0)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            return None

    # ==========================================
    # 核心查詢 API (具備平滑降級)
    # ==========================================

    def search_drugs(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        搜尋藥品 (M01 處方藥證與健保價 FTS5 / LIKE)
        """
        if not self.available or not query or not query.strip():
            return []

        clean_query = query.strip()
        conn = self._get_ro_connection()
        if not conn:
            return []

        results = []
        try:
            cursor = conn.cursor()
            # 1. 嘗試 FTS5 檢索
            fts_sql = """
            SELECT d.drug_code, d.license_id, d.trade_name_tw, d.trade_name_en, 
                   d.ingredient_name, d.indications, d.nhi_price, d.form_description
            FROM m01_tw_drug_db_fts f
            JOIN m01_tw_drug_db d ON f.rowid = d.rowid
            WHERE m01_tw_drug_db_fts MATCH ?
            LIMIT ?;
            """
            try:
                cursor.execute(fts_sql, (f'"{clean_query}"', limit))
                rows = cursor.fetchall()
            except Exception:
                rows = []

            # 2. 若 FTS 未命中，嘗試 LIKE 備援
            if not rows:
                like_sql = """
                SELECT drug_code, license_id, trade_name_tw, trade_name_en, 
                       ingredient_name, indications, nhi_price, form_description
                FROM m01_tw_drug_db
                WHERE trade_name_tw LIKE ? OR trade_name_en LIKE ? OR ingredient_name LIKE ? OR drug_code LIKE ? OR license_id LIKE ?
                LIMIT ?;
                """
                pattern = f"%{clean_query}%"
                cursor.execute(like_sql, (pattern, pattern, pattern, pattern, pattern, limit))
                rows = cursor.fetchall()

            for r in rows:
                results.append({
                    "drug_code": r["drug_code"],
                    "license_id": r["license_id"],
                    "trade_name_tw": r["trade_name_tw"],
                    "trade_name_en": r["trade_name_en"],
                    "ingredient_name": r["ingredient_name"],
                    "indications": r["indications"],
                    "nhi_price": r["nhi_price"],
                    "form_description": r["form_description"]
                })
        except Exception:
            pass
        finally:
            conn.close()

        return results

    def get_drug_by_code(self, drug_or_lic_code: str) -> Optional[Dict[str, Any]]:
        """
        依許可證號或 drug_code 查詢藥品詳情
        """
        if not self.available or not drug_or_lic_code:
            return None

        clean_code = drug_or_lic_code.strip()
        conn = self._get_ro_connection()
        if not conn:
            return None

        drug_info = None
        try:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT drug_code, license_id, trade_name_tw, trade_name_en, ingredient_name, 
                   indications, nhi_price, form_description, approval_date
            FROM m01_tw_drug_db
            WHERE drug_code = ? OR license_id = ?
            LIMIT 1;
            """, (clean_code, clean_code))
            r = cursor.fetchone()
            if r:
                drug_info = {
                    "drug_code": r["drug_code"],
                    "license_id": r["license_id"],
                    "trade_name_tw": r["trade_name_tw"],
                    "trade_name_en": r["trade_name_en"],
                    "ingredient_name": r["ingredient_name"],
                    "indications": r["indications"],
                    "nhi_price": r["nhi_price"],
                    "form_description": r["form_description"],
                    "approval_date": r["approval_date"]
                }
        except Exception:
            pass
        finally:
            conn.close()

        return drug_info

    def get_payment_rules(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        查詢健保給付規定條文 (M06)
        """
        if not self.available or not query:
            return []

        clean_query = query.strip()
        conn = self._get_ro_connection()
        if not conn:
            return []

        rules = []
        try:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT rule_id, nhi_code, item_name, section_code, rule_raw_text
            FROM m06_nhi_rules
            WHERE rule_raw_text LIKE ? OR item_name LIKE ? OR section_code LIKE ?
            LIMIT ?;
            """, (f"%{clean_query}%", f"%{clean_query}%", f"%{clean_query}%", limit))
            for r in cursor.fetchall():
                rules.append({
                    "rule_id": r["rule_id"],
                    "nhi_code": r["nhi_code"],
                    "item_name": r["item_name"],
                    "section_code": r["section_code"],
                    "rule_content": r["rule_raw_text"]
                })
        except Exception:
            pass
        finally:
            conn.close()

        return rules

    def translate_clinical_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        翻譯臨床代碼 (優先比對 M12 LOINC 檢驗碼與 M01 健保藥品許可證)
        若命中則回傳結構化字典；若未命中或不可用，回傳 None (由呼叫端走 fallback)
        """
        if not self.available or not code:
            return None

        clean_code = code.strip()
        conn = self._get_ro_connection()
        if not conn:
            return None

        translation = None
        try:
            cursor = conn.cursor()
            
            # 1. 優先比對 M12 LOINC 檢驗代碼 (支援 1001-2 等)
            cursor.execute("""
            SELECT loinc_num, component_zh, unit, ref_range_min, ref_range_max, fhir_resource_type
            FROM m12_loinc_codes
            WHERE loinc_num = ?
            LIMIT 1;
            """, (clean_code,))
            r = cursor.fetchone()
            if r:
                ref_range = f"{r['ref_range_min']} ~ {r['ref_range_max']} {r['unit']}" if r['ref_range_min'] is not None else f"單位: {r['unit']}"
                translation = {
                    "code": r["loinc_num"],
                    "type": "LOINC 臨床檢驗碼",
                    "title": r["component_zh"],
                    "description": f"參考範圍: {ref_range} | 標準 FHIR Resource: {r['fhir_resource_type']}",
                    "source": "tw-med-db (M12 loinc_codes)"
                }
                return translation

            # 2. 比對 M01 藥品許可證號或 drug_code (如 DHA00202451009)
            cursor.execute("""
            SELECT drug_code, license_id, trade_name_tw, trade_name_en, ingredient_name, indications
            FROM m01_tw_drug_db
            WHERE drug_code = ? OR license_id = ?
            LIMIT 1;
            """, (clean_code, clean_code))
            r = cursor.fetchone()
            if r:
                translation = {
                    "code": r["drug_code"],
                    "type": "TFDA 藥品許可證",
                    "title": f"{r['trade_name_tw']} ({r['trade_name_en']})",
                    "description": f"許可證: {r['license_id']} | 主成分: {r['ingredient_name']} | 適應症: {r['indications'][:60]}...",
                    "source": "tw-med-db (M01 tw_drug_db)"
                }
                return translation

        except Exception:
            pass
        finally:
            conn.close()

        return translation


# 全域單例便利函式
_global_bridge_instance: Optional[TwMedBridge] = None

def get_med_bridge(force_enabled: Optional[bool] = None, custom_db_path: Optional[str] = None) -> TwMedBridge:
    """取得或建立全域 TwMedBridge 實例"""
    global _global_bridge_instance
    if _global_bridge_instance is None or force_enabled is not None or custom_db_path is not None:
        _global_bridge_instance = TwMedBridge(force_enabled=force_enabled, custom_db_path=custom_db_path)
    return _global_bridge_instance


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="tw_med_bridge 狀態檢測與測試工具")
    parser.add_argument("--no-med-db", action="store_true", help="強制模擬停用 tw-med-db")
    parser.add_argument("--db", type=str, help="指定自訂 med.db 路徑")
    parser.add_argument("-s", "--search", type=str, help="測試搜尋藥品")
    parser.add_argument("-c", "--code", type=str, help="測試代碼翻譯")
    parser.add_argument("-r", "--rule", type=str, help="測試給付條文查詢")
    args = parser.parse_args()

    force_flag = False if args.no_med_db else None
    bridge = get_med_bridge(force_enabled=force_flag, custom_db_path=args.db)

    print("=" * 60)
    print("    TwMedBridge 診斷檢驗")
    print("=" * 60)
    status = bridge.get_status()
    print(f"狀態啟用 (Enabled):   {status['enabled']}")
    print(f"可用性 (Available):  {status['available']}")
    print(f"狀態訊息:            {status['status_message']}")
    print(f"資料庫路徑:          {status['db_path']}")
    print("-" * 60)

    if args.search:
        print(f"🔍 搜尋藥品關鍵字: '{args.search}'")
        res = bridge.search_drugs(args.search, limit=3)
        if res:
            for item in res:
                print(f"  [{item['drug_code']}] {item['trade_name_tw']} ({item['trade_name_en']}) | {item['ingredient_name']}")
        else:
            print("  (未查詢到結果或 tw-med-db 未啟用)")

    if args.code:
        print(f"🔍 翻譯臨床代碼: '{args.code}'")
        res = bridge.translate_clinical_code(args.code)
        if res:
            print(f"  類別: {res['type']}")
            print(f"  名稱: {res['title']}")
            print(f"  說明: {res['description']}")
            print(f"  來源: {res['source']}")
        else:
            print("  (未命中代碼或 tw-med-db 未啟用)")

    if args.rule:
        print(f"🔍 查詢給付規定: '{args.rule}'")
        res = bridge.get_payment_rules(args.rule, limit=2)
        if res:
            for r in res:
                print(f"  [{r['rule_id']}] {r['item_name']} ({r['section_code']})")
                print(f"   內容: {r['rule_content'][:80]}...")
        else:
            print("  (未查詢到條文或 tw-med-db 未啟用)")
    print("=" * 60)
