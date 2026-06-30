#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 健保健康存摺網頁 HTML 解析工具
功能：讀取網頁另存新檔之 HTML，提取就醫與用藥表格資料，並清洗轉換為結構化 TSV/JSON。
"""

import os
import sys
import re
import json

def convert_roc_to_ad(roc_date_str):
    """
    將民國日期 (如 115/05/20 或 1150520) 轉換為西元 ISO 日期格式 (YYYY-MM-DD)
    """
    roc_date_str = roc_date_str.strip()
    # 格式 1: 115/05/20 或 115-05-20
    match = re.match(r'(\d{2,3})[-/](\d{1,2})[-/](\d{1,2})', roc_date_str)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    
    # 格式 2: 1150520
    match = re.match(r'(\d{3})(\d{2})(\d{2})', roc_date_str)
    if match:
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
        
    return roc_date_str  # 無法解析則傳回原字串

def parse_nhia_html(html_path):
    """
    解析健康存摺 HTML 中的表格。
    優先使用 BeautifulSoup，若無則 fallback 至標準庫 html.parser 以確保相容性。
    """
    if not os.path.exists(html_path):
        print(f"【錯誤】找不到輸入的 HTML 檔案：{html_path}", file=sys.stderr)
        return None

    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        html_content = f.read()

    # 嘗試載入 BeautifulSoup
    try:
        from bs4 import BeautifulSoup
        return _parse_with_bs4(html_content)
    except ImportError:
        print("【警告】未安裝 bs4 (BeautifulSoup4)，將使用 Python 內建 HTMLParser 進行解析...", file=sys.stderr)
        return _parse_with_builtin(html_content)

def _parse_with_bs4(html_content):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    tables_data = []
    
    # 搜尋網頁中所有的 table 標籤
    tables = soup.find_all('table')
    for table_idx, table in enumerate(tables):
        rows_data = []
        headers = []
        
        # 尋找表頭
        th_tags = table.find_all('th')
        if th_tags:
            headers = [th.get_text().strip() for th in th_tags]
            
        tr_tags = table.find_all('tr')
        for tr in tr_tags:
            # 排除表頭行
            if tr.find('th'):
                continue
                
            td_tags = tr.find_all('td')
            if not td_tags:
                continue
                
            cells = [td.get_text().strip() for td in td_tags]
            # 清洗儲存格內的贅字與多餘換行
            cells = [re.sub(r'\s+', ' ', cell) for cell in cells]
            
            # 若無表頭，則在第一行嘗試推導表頭，或使用欄位索引
            if cells:
                rows_data.append(cells)
                
        if rows_data:
            # 如果解析時沒有抓到 <th>，但第一行看起來像表頭，則作轉換
            if not headers and len(rows_data) > 1:
                # 簡單判定：如果第一行全為文字且包含常見表頭字眼
                if any(k in "".join(rows_data[0]) for k in ["日期", "科別", "藥品", "院所"]):
                    headers = rows_data.pop(0)
            
            tables_data.append({
                "table_index": table_idx,
                "headers": headers if headers else [f"欄位_{i}" for i in range(len(rows_data[0]))],
                "rows": rows_data
            })
            
    return tables_data

class BuiltinNHIAParser(object):
    """
    Python 標準庫 HTMLParser 實現，確保在無外部相依套件時仍可順暢運作
    """
    def __init__(self):
        from html.parser import HTMLParser
        self.parser_class = HTMLParser
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_cell = []
        self.in_table = False
        self.in_tr = False
        self.in_td = False
        self.in_th = False
        
    def get_parser(self):
        outer = self
        class SubParser(self.parser_class):
            def handle_starttag(self, tag, attrs):
                if tag == 'table':
                    outer.current_table = {"headers": [], "rows": []}
                    outer.in_table = True
                elif tag == 'tr' and outer.in_table:
                    outer.current_row = []
                    outer.in_tr = True
                elif tag == 'td' and outer.in_tr:
                    outer.in_td = True
                    outer.current_cell = []
                elif tag == 'th' and outer.in_tr:
                    outer.in_th = True
                    outer.current_cell = []
                    
            def handle_endtag(self, tag):
                if tag == 'table' and outer.in_table:
                    if outer.current_table["rows"]:
                        outer.tables.append(outer.current_table)
                    outer.current_table = None
                    outer.in_table = False
                elif tag == 'tr' and outer.in_tr:
                    if outer.current_row:
                        outer.current_table["rows"].append(outer.current_row)
                    outer.current_row = None
                    outer.in_tr = False
                elif tag == 'td' and outer.in_td:
                    cell_text = "".join(outer.current_cell).strip()
                    cell_text = re.sub(r'\s+', ' ', cell_text)
                    outer.current_row.append(cell_text)
                    outer.in_td = False
                elif tag == 'th' and outer.in_th:
                    cell_text = "".join(outer.current_cell).strip()
                    cell_text = re.sub(r'\s+', ' ', cell_text)
                    outer.current_table["headers"].append(cell_text)
                    outer.in_th = False
                    
            def handle_data(self, data):
                if outer.in_td or outer.in_th:
                    outer.current_cell.append(data)
                    
        return SubParser()

def _parse_with_builtin(html_content):
    builtin_helper = BuiltinNHIAParser()
    parser = builtin_helper.get_parser()
    parser.feed(html_content)
    
    tables_data = []
    for idx, table in enumerate(builtin_helper.tables):
        tables_data.append({
            "table_index": idx,
            "headers": table["headers"] if table["headers"] else [f"欄位_{i}" for i in range(len(table["rows"][0]))] if table["rows"] else [],
            "rows": table["rows"]
        })
    return tables_data

def format_as_tsv(parsed_tables):
    """
    將解析後的表格資料格式化為 TSV 字串，便於 AI 助理閱讀或進行正規表達式二次提取
    """
    if not parsed_tables:
        return ""
        
    output = []
    for table in parsed_tables:
        output.append(f"=== Table #{table['table_index']} ===")
        output.append("\t".join(table['headers']))
        for row in table['rows']:
            # 對齊欄位數量
            if len(row) < len(table['headers']):
                row = row + [""] * (len(table['headers']) - len(row))
            elif len(row) > len(table['headers']):
                row = row[:len(table['headers'])]
            output.append("\t".join(row))
        output.append("\n")
    return "\n".join(output)

if __name__ == '__main__':
    # 提供 CLI 除錯與執行功能
    if len(sys.argv) < 2:
        print("使用說明: python3 nhia_html_parser.py <path_to_html>")
        sys.exit(1)
        
    target_path = sys.argv[1]
    tables = parse_nhia_html(target_path)
    
    if tables:
        print(f"【成功】解析出 {len(tables)} 個表格。\n")
        tsv_result = format_as_tsv(tables)
        print(tsv_result)
        
        # 測試日期轉換示範
        print("--- 日期轉換測試 (民國轉西元) ---")
        for t in tables:
            for row in t['rows'][:3]:  # 只印前三筆
                for cell in row:
                    if re.match(r'^\d{3}[-/]\d{2}[-/]\d{2}$', cell):
                        print(f"原始民國日期: {cell} -> 西元日期: {convert_roc_to_ad(cell)}")
    else:
        print("【失敗】未解析出任何有效表格資料。")
