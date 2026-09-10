#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[metadata]
name: tw_med_bridge.py
title: Sovereign Health Agent 台灣醫療大數據邊界適配器 (CGS v2.4)
description: 封裝對地端 tw-med-db 醫療大數據庫之唯讀訪問，支援 M01 藥證、M02 主成分、M06 給付規定與 M12 LOINC 檢驗碼查詢，提供三級開關控制與 100% 零崩潰平滑降級能力。
category: healthcare_bridge
spec: @sovereign-health-agent/specs/tw_med_bridge.spec.md
manual: @sovereign-health-agent/manuals/tw_med_bridge.md
bman: bman_sha_book:ch09
seman: seman_sha_sys_eng:02
dependencies: none
cgs_version: 2.4
"""

import os
import sys
import json
import sqlite3
import re
import argparse
from typing import Optional, Dict, Any, List, Tuple

# 顯式宣告 CGS 規格版號
__cli_spec_version__ = "2.4"

# 跨平台 (Windows Console) UTF-8 強制編碼保護
if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# 專案路徑解析
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
MANUAL_PATH = os.path.join(PROJECT_DIR, "manuals", "tw_med_bridge.md")

# 預設候選 tw-med-db 路徑 (依相對位置探索)
CANDIDATE_MED_DB_PATHS = [
    os.path.abspath(os.path.join(PROJECT_DIR, "..", "..", "events", "TDHI_haba", "med-db-in", "tw-med-db", "db", "med.db")),
    os.path.abspath(os.path.join(PROJECT_DIR, "..", "tw-med-db", "db", "med.db")),
    os.path.abspath(os.path.join(PROJECT_DIR, "med.db")),
]

def log_msg(msg: str, level: str = "INFO"):
    """標準化結構化日誌輸出至 stderr (符合 CGS v2.4 流向分離)"""
    prefix = {"INFO": "ℹ️ [INFO]", "WARN": "⚠️ [WARN]", "ERROR": "❌ [ERROR]", "DEBUG": "🔍 [DEBUG]"}.get(level, "[INFO]")
    sys.stderr.write(f"{prefix} {msg}\n")
    sys.stderr.flush()

class TwMedBridge:
    """
    台灣醫療與健保開放大數據引擎 (tw-med-db) 橋接器
    具備三級開關控制、狀態診斷與防崩潰平滑降級能力。
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
        """搜尋藥品 (M01 處方藥證與健保價 FTS5 / LIKE)"""
        if not self.available or not query or not query.strip():
            return []

        clean_query = query.strip()
        conn = self._get_ro_connection()
        if not conn:
            return []

        results = []
        try:
            cursor = conn.cursor()
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
        """依許可證號或 drug_code 查詢藥品詳情"""
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

    def get_ingredients(self, ingredient_name_or_code: str) -> List[Dict[str, Any]]:
        """查詢成分資訊與 ATC 分類 (M02)"""
        if not self.available or not ingredient_name_or_code:
            return []

        clean_str = ingredient_name_or_code.strip()
        conn = self._get_ro_connection()
        if not conn:
            return []

        results = []
        try:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='m02_tw_ingredient_map_db';
            """)
            if not cursor.fetchone():
                return []

            cursor.execute("""
            SELECT ingredient_code, ingredient_name_en, ingredient_name_tw, atc_code, atc_name_tw
            FROM m02_tw_ingredient_map_db
            WHERE ingredient_name_en LIKE ? OR ingredient_name_tw LIKE ? OR atc_code = ?
            LIMIT 10;
            """, (f"%{clean_str}%", f"%{clean_str}%", clean_str))
            for r in cursor.fetchall():
                results.append({
                    "ingredient_code": r["ingredient_code"],
                    "ingredient_name_en": r["ingredient_name_en"],
                    "ingredient_name_tw": r["ingredient_name_tw"],
                    "atc_code": r["atc_code"],
                    "atc_name_tw": r["atc_name_tw"]
                })
        except Exception:
            pass
        finally:
            conn.close()

        return results

    def get_payment_rules(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """查詢健保給付規定條文 (M06)"""
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
        """翻譯臨床代碼 (優先比對 M12 LOINC 檢驗碼與 M01 健保藥品許可證)"""
        if not self.available or not code:
            return None

        clean_code = code.strip()
        conn = self._get_ro_connection()
        if not conn:
            return None

        translation = None
        try:
            cursor = conn.cursor()
            
            # 1. 優先比對 M12 LOINC 檢驗代碼
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

            # 2. 比對 M01 藥品許可證號或 drug_code
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


# ==============================================================================
# CGS v2.4 標準 CLI 子命令路由與管道處理 (Pipeline-Native)
# ==============================================================================

def get_schema() -> Dict[str, Any]:
    """回傳符合 CGS v2.4 之自我描述 Schema"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "TwMedBridgeSchema",
        "type": "object",
        "cgs_spec_version": __cli_spec_version__,
        "subcommands": {
            "status": "取得 tw-med-db 連線狀態與路徑",
            "search": "搜尋藥品許可證與健保價",
            "code": "翻譯臨床檢驗代碼 (LOINC) 或藥品代碼",
            "rule": "查詢健保給付規定條文",
            "schema": "輸出 JSON Schema",
            "version": "輸出版本資訊"
        },
        "properties": {
            "enabled": {"type": "boolean"},
            "available": {"type": "boolean"},
            "status_message": {"type": "string"},
            "db_path": {"type": ["string", "null"]}
        }
    }

def main():
    # 通用 parent parser 讓子命令前後皆可吃通用 flags
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-j", "--json", action="store_true", help="啟用單行緊湊 JSON 格式輸出")
    parent_parser.add_argument("-q", "--quiet", action="store_true", help="極簡輸出模式")
    parent_parser.add_argument("--no-med-db", action="store_true", help="強制模擬停用 tw-med-db")
    parent_parser.add_argument("--with-med-db", action="store_true", help="強制嘗試連線 tw-med-db")
    parent_parser.add_argument("--db", type=str, help="指定自訂 med.db 路徑")
    parent_parser.add_argument("--stdin", "-", dest="use_stdin", action="store_true", help="從標準輸入讀取查詢字串")

    parser = argparse.ArgumentParser(
        description="tw_med_bridge - Sovereign Health Agent 台灣醫療大數據邊界適配器 (CGS v2.4)",
        parents=[parent_parser],
        add_help=True
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令清單")

    # status 子命令
    subparsers.add_parser("status", parents=[parent_parser], help="檢驗當前 Bridge 連線與可用性狀態")

    # search 子命令
    p_search = subparsers.add_parser("search", parents=[parent_parser], help="搜尋處方藥品與官方藥證 (M01)")
    p_search.add_argument("query", nargs="?", default="", help="藥物關鍵字")
    p_search.add_argument("-l", "--limit", type=int, default=5, help="限制回傳筆數")

    # code 子命令
    p_code = subparsers.add_parser("code", parents=[parent_parser], help="翻譯臨床檢驗代碼或藥品代碼")
    p_code.add_argument("code_str", nargs="?", default="", help="代碼 (如 1001-2 或許可證號)")

    # rule 子命令
    p_rule = subparsers.add_parser("rule", parents=[parent_parser], help="查詢健保給付規定條文")
    p_rule.add_argument("rule_query", nargs="?", default="", help="條文關鍵字")
    p_rule.add_argument("-l", "--limit", type=int, default=3, help="限制回傳筆數")

    # schema & version & manual
    subparsers.add_parser("schema", parents=[parent_parser], help="輸出自我描述 JSON Schema")
    subparsers.add_parser("version", parents=[parent_parser], help="輸出版本資訊")
    subparsers.add_parser("man", parents=[parent_parser], help="檢視說明手冊")
    subparsers.add_parser("manual", parents=[parent_parser], help="檢視說明手冊")

    args = parser.parse_args()

    # 決定開關旗標
    force_flag = None
    if args.no_med_db:
        force_flag = False
    elif args.with_med_db:
        force_flag = True

    bridge = get_med_bridge(force_enabled=force_flag, custom_db_path=args.db)

    # 處理 stdin 管道輸入 (僅在顯式指定 --stdin 時讀取，防範非 TTY 背景執行卡住)
    stdin_data = ""
    if args.use_stdin:
        try:
            stdin_data = sys.stdin.read().strip()
        except Exception:
            pass

    cmd = args.command or "status"

    try:
        if cmd == "status":
            res = bridge.get_status()
            if args.json:
                sys.stdout.write(json.dumps(res, ensure_ascii=False, separators=(',', ':')) + "\n")
            elif args.quiet:
                sys.stdout.write(f"{res['available']}\n")
            else:
                sys.stdout.write("=" * 60 + "\n")
                sys.stdout.write("    TwMedBridge 診斷檢驗 (CGS v2.4)\n")
                sys.stdout.write("=" * 60 + "\n")
                sys.stdout.write(f"狀態啟用 (Enabled):   {res['enabled']}\n")
                sys.stdout.write(f"可用性 (Available):  {res['available']}\n")
                sys.stdout.write(f"狀態訊息:            {res['status_message']}\n")
                sys.stdout.write(f"資料庫路徑:          {res['db_path']}\n")
                sys.stdout.write("=" * 60 + "\n")

        elif cmd == "search":
            target = stdin_data if stdin_data else args.query
            if not target:
                log_msg("未提供搜尋關鍵字", "WARN")
                return
            res = bridge.search_drugs(target, limit=args.limit)
            if args.json:
                sys.stdout.write(json.dumps(res, ensure_ascii=False, separators=(',', ':')) + "\n")
            elif args.quiet:
                for item in res:
                    sys.stdout.write(f"{item['drug_code']}\t{item['trade_name_tw']}\n")
            else:
                sys.stdout.write(f"🔍 搜尋藥品關鍵字: '{target}' (共 {len(res)} 筆)\n")
                for item in res:
                    sys.stdout.write(f"  [{item['drug_code']}] {item['trade_name_tw']} ({item['trade_name_en']}) - NT$ {item['nhi_price']}\n")

        elif cmd == "code":
            target = stdin_data if stdin_data else args.code_str
            if not target:
                log_msg("未提供代碼", "WARN")
                return
            res = bridge.translate_clinical_code(target)
            if args.json:
                sys.stdout.write(json.dumps(res or {}, ensure_ascii=False, separators=(',', ':')) + "\n")
            elif args.quiet:
                if res:
                    sys.stdout.write(f"{res['code']}\t{res['title']}\n")
            else:
                sys.stdout.write(f"🔍 翻譯臨床代碼: '{target}'\n")
                if res:
                    sys.stdout.write(f"  類別: {res['type']}\n")
                    sys.stdout.write(f"  名稱: {res['title']}\n")
                    sys.stdout.write(f"  說明: {res['description']}\n")
                    sys.stdout.write(f"  來源: {res['source']}\n")
                else:
                    sys.stdout.write("  (未命中代碼或 tw-med-db 未啟用)\n")

        elif cmd == "rule":
            target = stdin_data if stdin_data else args.rule_query
            if not target:
                log_msg("未提供給付條文關鍵字", "WARN")
                return
            res = bridge.get_payment_rules(target, limit=args.limit)
            if args.json:
                sys.stdout.write(json.dumps(res, ensure_ascii=False, separators=(',', ':')) + "\n")
            elif args.quiet:
                for r in res:
                    sys.stdout.write(f"{r['rule_id']}\t{r['item_name']}\n")
            else:
                sys.stdout.write(f"🔍 查詢給付規定: '{target}' (共 {len(res)} 筆)\n")
                for r in res:
                    sys.stdout.write(f"  [{r['rule_id']}] {r['item_name']} ({r['section_code']})\n")
                    sys.stdout.write(f"   內容: {r['rule_content'][:80]}...\n")

        elif cmd == "schema":
            sys.stdout.write(json.dumps(get_schema(), ensure_ascii=False, indent=2) + "\n")

        elif cmd == "version":
            ver_info = {
                "script": "tw_med_bridge.py",
                "version": "1.0.0",
                "cgs_spec_version": __cli_spec_version__
            }
            if args.json:
                sys.stdout.write(json.dumps(ver_info, ensure_ascii=False) + "\n")
            else:
                sys.stdout.write(f"tw_med_bridge.py v1.0.0 (CGS v{__cli_spec_version__})\n")

        elif cmd in ["man", "manual"]:
            if os.path.exists(MANUAL_PATH):
                with open(MANUAL_PATH, "r", encoding="utf-8") as f:
                    sys.stdout.write(f.read())
            else:
                log_msg(f"說明手冊不存在: {MANUAL_PATH}", "ERROR")

    except Exception as e:
        log_msg(str(e), "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
