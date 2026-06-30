#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 健保健康存摺隱私去識別化工具 (Privacy Scrubber)
功能：將健康存摺 HTML/TXT/JSON 檔案中的敏感個資 (姓名、身分證字號、卡號、生日、醫院、醫護人員姓名) 
      進行本地端去識別化與時間平移，產出可用於開發與測試的安全樣本檔案。
"""

import os
import sys
import re
import random
from datetime import datetime, timedelta

# 預設去識別化對應值
MOCK_PATIENT_NAME = "王小明"
MOCK_PATIENT_ID = "A123456789"
MOCK_CARD_NUMBER = "000012345678"
MOCK_BIRTHDAY = "0800101" # 民國 80 年 1 月 1 日

# 常用正規表達式
ROC_ID_PATTERN = re.compile(r'\b[A-Za-z][12]\d{8}\b')
NHI_CARD_PATTERN = re.compile(r'\b\d{12}\b')
TAIWAN_MOBILE_PATTERN = re.compile(r'\b09\d{8}\b|\b09\d{2}-\d{6}\b|\b09\d{2}-\d{3}-\d{3}\b')
TAIWAN_PHONE_PATTERN = re.compile(r'\b0\d{1,2}-\d{6,8}\b')

# 醫療院所後置詞，用來辨識院所名稱
CLINIC_SUFFIX_PATTERN = re.compile(r'([^\s<>"\']*?(?:醫院|診所|衛生所|醫學中心|分院|聯合診所|牙醫|中醫|藥局))')

# 醫療機構名稱穩定映射快取，確保相同醫院在同一次執行中替換為同一個假名，不同醫院替換為不同假名
_HOSPITAL_CACHE = {}

def get_mock_hospital_name(hosp_name):
    if hosp_name in _HOSPITAL_CACHE:
        return _HOSPITAL_CACHE[hosp_name]
    
    hosp_type = "醫療機構"
    if "藥局" in hosp_name:
        hosp_type = "社區藥局"
    elif "診所" in hosp_name:
        hosp_type = "健保診所"
    elif "醫院" in hosp_name:
        hosp_type = "區域醫院"
        
    next_letter = chr(65 + (len(_HOSPITAL_CACHE) % 26))
    fake_name = f"{hosp_type}{next_letter}"
    _HOSPITAL_CACHE[hosp_name] = fake_name
    return fake_name

def shift_roc_date(date_str, days_shift):
    """
    平移民國格式日期 (如 115/05/20, 115-05-20, 1150520)
    """
    if days_shift == 0:
        return date_str

    # 尋找符號分隔
    match_sep = re.match(r'^(\d{2,3})([-/])(\d{1,2})([-/])(\d{1,2})$', date_str.strip())
    if match_sep:
        roc_year = int(match_sep.group(1))
        sep = match_sep.group(2)
        month = int(match_sep.group(3))
        day = int(match_sep.group(5))
        
        ad_year = roc_year + 1911
        try:
            dt = datetime(ad_year, month, day)
            shifted_dt = dt + timedelta(days=days_shift)
            new_roc_year = shifted_dt.year - 1911
            return f"{new_roc_year}{sep}{shifted_dt.month:02d}{sep}{shifted_dt.day:02d}"
        except ValueError:
            return date_str

    # 尋找無分隔字串 (如 1150520)
    match_no_sep = re.match(r'^(\d{3})(\d{2})(\d{2})$', date_str.strip())
    if match_no_sep:
        roc_year = int(match_no_sep.group(1))
        month = int(match_no_sep.group(2))
        day = int(match_no_sep.group(3))
        
        ad_year = roc_year + 1911
        try:
            dt = datetime(ad_year, month, day)
            shifted_dt = dt + timedelta(days=days_shift)
            new_roc_year = shifted_dt.year - 1911
            return f"{new_roc_year:03d}{shifted_dt.month:02d}{shifted_dt.day:02d}"
        except ValueError:
            return date_str
            
    return date_str

def shift_ad_date(date_str, days_shift):
    """
    平移西元格式日期 (如 2026/05/20, 2026-05-20)
    """
    if days_shift == 0:
        return date_str
        
    match = re.match(r'^(\d{4})([-/])(\d{1,2})([-/])(\d{1,2})$', date_str.strip())
    if match:
        year = int(match.group(1))
        sep = match.group(2)
        month = int(match.group(3))
        day = int(match.group(5))
        try:
            dt = datetime(year, month, day)
            shifted_dt = dt + timedelta(days=days_shift)
            return f"{shifted_dt.year:04d}{sep}{shifted_dt.month:02d}{sep}{shifted_dt.day:02d}"
        except ValueError:
            return date_str
    return date_str

def scrub_text_content(text, days_shift=0, mask_hospitals=True):
    """
    以字串為主的正規表達式去識別化
    """
    # 1. 身分證字號與卡號
    text = ROC_ID_PATTERN.sub(MOCK_PATIENT_ID, text)
    text = NHI_CARD_PATTERN.sub(MOCK_CARD_NUMBER, text)
    
    # 2. 聯絡方式
    text = TAIWAN_MOBILE_PATTERN.sub("0912-345-678", text)
    text = TAIWAN_PHONE_PATTERN.sub("02-2345-6789", text)
    
    # 3. 姓名標籤置換 (姓名：XXX 或 保險對象姓名：XXX 等)
    text = re.sub(r'(姓名[：:\s]*)([^\s<]+)', rf'\g<1>{MOCK_PATIENT_NAME}', text)
    text = re.sub(r'(保險對象[：:\s]*)([^\s<]+)', rf'\g<1>{MOCK_PATIENT_NAME}', text)
    text = re.sub(r'(身分證號碼|身分證統一編號|身分證[：:\s]*)([A-Za-z]\d{8})', rf'\g<1>{MOCK_PATIENT_ID}', text)
    text = re.sub(r'(生日|出生日期|出生年月日[：:\s]*)(\d{2,3}[-/]\d{1,2}[-/]\d{1,2}|\d{7})', rf'\g<1>{MOCK_BIRTHDAY}', text)

    # 4. 醫療機構模糊化 (如果啟用)
    if mask_hospitals:
        unique_hospitals = list(set(CLINIC_SUFFIX_PATTERN.findall(text)))
        # 排除包含「健保」、「署」等非院所字眼
        unique_hospitals = [h for h in unique_hospitals if "中央健康保險" not in h and "健保署" not in h and "衛生福利部" not in h]
        # 排序長度由長至短，避免短名稱先被取代導致長名稱錯位
        unique_hospitals.sort(key=len, reverse=True)
        
        for hosp in unique_hospitals:
            fake_name = get_mock_hospital_name(hosp)
            text = text.replace(hosp, fake_name)

    # 5. 時間平移 (Date Shifting)
    if days_shift != 0:
        # 民國日期 pattern
        def replace_roc_date(match):
            return shift_roc_date(match.group(0), days_shift)
        
        # 匹配 115/05/20 或 115-05-20
        text = re.sub(r'\b\d{2,3}[-/]\d{1,2}[-/]\d{1,2}\b', replace_roc_date, text)
        # 匹配無分隔 1150520 (排除與健保卡號或ID等干擾，長度為7的純數字)
        text = re.sub(r'\b\d{7}\b', replace_roc_date, text)

        # 西元日期 pattern
        def replace_ad_date(match):
            return shift_ad_date(match.group(0), days_shift)
        
        text = re.sub(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', replace_ad_date, text)

    return text

def scrub_html_with_bs4(html_content, days_shift=0, mask_hospitals=True):
    """
    使用 BeautifulSoup 針對特定 HTML 結構做更精準的節點去識別化
    """
    from bs4 import BeautifulSoup, Comment
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. 尋找所有表格進行行與列的過濾，先標註醫護人員欄位
    tables = soup.find_all('table')
    for table in tables:
        headers = []
        th_tags = table.find_all('th')
        if th_tags:
            headers = [th.get_text().strip() for th in th_tags]
            
        tr_tags = table.find_all('tr')
        for tr in tr_tags:
            td_tags = tr.find_all('td')
            if not td_tags:
                continue
                
            for idx, td in enumerate(td_tags):
                # 取得當前欄位對應的表頭名稱
                header_name = headers[idx] if idx < len(headers) else ""
                
                # 若欄位名稱為醫師、藥師、調劑人員等，直接將其名字改為假名 (加寬長度判定至 8 個字元以容納「李博文醫師」等)
                if any(kw in header_name for kw in ["醫師", "藥師", "醫事人員", "調劑人員", "人員"]):
                    orig_text = td.get_text().strip()
                    if orig_text and len(orig_text) <= 8:
                        td.string = "醫療人員"

    # 2. 遍歷 DOM 中所有的文字節點進行去識別化與日期平移，確保不重複處理
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, Comment):
            continue
        if text_node.parent.name in ['script', 'style']:
            continue
            
        orig_text = str(text_node)
        if not orig_text.strip():
            continue
            
        # 避免重複處理已置換為「醫療人員」的欄位
        if orig_text.strip() == "醫療人員":
            continue
            
        # 進行常規去識別化與時間平移
        scrubbed = scrub_text_content(orig_text, days_shift, mask_hospitals)
        text_node.replace_with(scrubbed)

    return str(soup)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="健保健康存摺隱私去識別化工具 (Local Privacy Scrubber)")
    parser.add_argument("input_file", help="輸入之原始健康存摺 HTML/TXT/JSON 檔案路徑")
    parser.add_argument("-o", "--output", help="輸出之去識別化後檔案路徑 (預設為 input_file 目錄下的 *_scrubbed 檔案)")
    parser.add_argument("-s", "--shift-days", type=int, default=None, help="就醫日期平移天數 (未指定時，將自動依病患 ID 產生穩定加密的隨機天數)")
    parser.add_argument("-p", "--patient-id", default="PUMC_001", help="病患代號，用於產生穩定加密的隨機平移天數 (預設為 PUMC_001)")
    parser.add_argument("--no-mask-hospitals", action="store_true", help="不模糊化醫療院所名稱")
    
    args = parser.parse_args()
    
    input_path = args.input_file
    if not os.path.exists(input_path):
        print(f"【錯誤】找不到輸入檔案：{input_path}", file=sys.stderr)
        sys.exit(1)
        
    # 自動決定輸出路徑
    if args.output:
        output_path = args.output
    else:
        dir_name, file_name = os.path.split(input_path)
        base_name, ext = os.path.splitext(file_name)
        output_path = os.path.join(dir_name, f"{base_name}_scrubbed{ext}")
        
    print(f"[*] 讀取原始檔案: {input_path}")
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    mask_hosp = not args.no_mask_hospitals
    
    # 計算平移天數
    shift_days = args.shift_days
    if shift_days is None:
        import hashlib
        salt = "BMAD_SALT_2026"
        h = hashlib.sha256((args.patient_id + salt).encode('utf-8')).hexdigest()
        val = int(h[:8], 16)
        shift_days = -(7 + (val % 24)) # 產生 -7 到 -30 天的加密隨機偏置 (1至4週)

        print(f"[*] 未指定平移天數。系統已依病患 ID '{args.patient_id}' 自動產生加密隨機平移偏置: {shift_days} 天")
    else:
        print(f"[*] 使用指定平移天數: {shift_days} 天")
    
    # 嘗試使用 bs4 進行結構化去識別化
    use_bs4 = False
    try:
        from bs4 import BeautifulSoup
        use_bs4 = True
    except ImportError:
        print("[!] 系統未安裝 BeautifulSoup4。將直接使用字串正規表達式進行去識別化...")
        
    if use_bs4 and input_path.lower().endswith(('.html', '.htm')):
        print(f"[*] 偵測為 HTML 檔案，使用 BeautifulSoup 解析去識別化...")
        scrubbed_content = scrub_html_with_bs4(content, days_shift=shift_days, mask_hospitals=mask_hosp)
    else:
        print(f"[*] 使用字串正規表達式進行去識別化...")
        scrubbed_content = scrub_text_content(content, days_shift=shift_days, mask_hospitals=mask_hosp)
        
    # 寫入輸出檔案
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(scrubbed_content)
        
    print(f"【成功】去識別化完成！")
    print(f"[*] 已產出安全樣本檔案: {output_path}")
    print(f"[*] 安全規則檢驗：")
    print(f"    - 日期已平移: {shift_days} 天")
    print(f"    - 身分證字號置換: {MOCK_PATIENT_ID}")
    print(f"    - 健保卡號置換: {MOCK_CARD_NUMBER}")
    print(f"    - 姓名置換: {MOCK_PATIENT_NAME}")
    print(f"    - 醫療院所模糊化: {'啟用' if mask_hosp else '停用'}")


if __name__ == '__main__':
    main()
