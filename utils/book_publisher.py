#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
[metadata]
name: book_publisher
description: 大書安全防禦校驗與 TOC 生成工具。直接以 book/ 目錄為單一真理源頭 (Single Source of Truth)，執行個資去識別化校驗、路徑相對化修正、台灣用語防禦性本土化，並自動生成 TOC.md 索引，避免維護兩份檔案的重複疑慮。
"""

import os
import re
import json

# 定義路徑
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # events/sovereign-health-agent
BOOK_DIR = os.path.join(BASE_DIR, 'book')

# 私有脫敏規則搜尋路徑
RULES_FILE_PATHS = [
    os.path.join(BASE_DIR, 'utils', 'private_deid_rules.json'),
    os.path.join(os.path.dirname(BASE_DIR), 'TDHI_haba', 'private_deid_rules.json'),
    os.path.join(os.path.dirname(BASE_DIR), 'TDHI_haba', 'workmgr', 'private_deid_rules.json'),
]

def load_deid_rules():
    """載入私有脫敏規則 (支援多路徑 fallback)"""
    rules_file = None
    for path in RULES_FILE_PATHS:
        if os.path.exists(path):
            rules_file = path
            break
            
    if not rules_file:
        print(f"⚠️  未找到任何私有脫敏規則檔，將僅進行通用路徑與用語校正。")
        return {}
    
    try:
        with open(rules_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"🔒 成功載入脫敏對照規則: {os.path.basename(rules_file)}")
            return data.get('replacements', {})
    except Exception as e:
        print(f"❌ 讀取脫敏規則檔失敗: {e}")
        return {}

def audit_and_correct_content(content, replacements):
    """執行內容防禦性修正：個資替換、路徑相對化與台灣在地化用語轉換"""
    original_content = content
    
    # 1. 執行私有敏感詞與個資替換 (防禦性替換)
    for target, replacement in replacements.items():
        content = content.replace(target, replacement)
    
    # 2. 絕對路徑校正防禦：將 file:///Users/xxx/github/bmad-pa/ 轉換為相對路徑
    # 規則 A: 替換 book 目錄本身的絕對連結為相對 `./`
    content = re.sub(
        r'file:///Users/[^/]+/github/bmad-pa/events/sovereign-health-agent/book/',
        './',
        content
    )
    # 規則 B: 替換 sovereign-health-agent 目錄的絕對連結為相對 `../`
    content = re.sub(
        r'file:///Users/[^/]+/github/bmad-pa/events/sovereign-health-agent/',
        '../',
        content
    )
    # 規則 C: 替換整個 bmad-pa 專案根目錄的絕對連結為相對 `../../../`
    content = re.sub(
        r'file:///Users/[^/]+/github/bmad-pa/',
        '../../../',
        content
    )
    
    # 規則 D: 替換簡寫絕對路徑為相對路徑
    content = content.replace('file:///utils/', '../utils/')
    content = content.replace('file:///book/', './')
    content = content.replace('file:///sys_eng/', '../sys_eng/')
    content = content.replace('file:///data/', '../data/')
    
    # 3. 中國用語自動防禦轉換（台灣在地化）
    terms_map = {
        '信息': '資訊',
        '軟體': '軟體',
        '軟件': '軟體',
        '數據': '資料',
        '優化': '最佳化',
        '支持': '支援',
    }
    for cn_term, tw_term in terms_map.items():
        content = content.replace(cn_term, tw_term)
        
    is_changed = (content != original_content)
    return content, is_changed

def generate_toc(published_files):
    """依據現有章節自動生成 TOC.md"""
    toc_path = os.path.join(BOOK_DIR, 'TOC.md')
    toc_content = [
        "# 📖 主權個人健康管理手冊 目錄 (Table of Contents)",
        "",
        "本手冊所有已發布章節索引如下（自動生成）：",
        "",
        "* [📖 大書首頁與導覽](README.md)"
    ]
    
    # 區分部分
    parts = {
        "第一部分：資料建置篇": [],
        "第二部分：科研思辨篇": [],
        "第三部分：工具操作篇": [],
        "第四部分：終老尊嚴篇": []
    }
    
    for filepath in sorted(published_files):
        filename = os.path.basename(filepath)
        if filename == 'README.md' or filename == 'TOC.md':
            continue
            
        try:
            # 讀取第一行作為標題
            with open(filepath, 'r', encoding='utf-8') as f:
                title_line = f.readline().strip()
                title = re.sub(r'^#\s*', '', title_line)
        except Exception:
            title = filename
            
        item_str = f"  * [{title}]({filename})"
        if 'ch01' in filename or 'ch02' in filename or 'ch03' in filename or 'ch04' in filename:
            parts["第一部分：資料建置篇"].append(item_str)
        elif 'ch05' in filename or 'ch06' in filename or 'ch07' in filename:
            parts["第二部分：科研思辨篇"].append(item_str)
        elif 'ch08' in filename or 'ch09' in filename or 'ch10' in filename:
            parts["第三部分：工具操作篇"].append(item_str)
        elif 'ch11' in filename or 'ch12' in filename:
            parts["第四部分：終老尊嚴篇"].append(item_str)
            
    for part_name, items in parts.items():
        if items:
            toc_content.append(f"* **{part_name}**")
            toc_content.extend(items)
            
    with open(toc_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(toc_content) + '\n')
        
    print(f"📖 成功自動生成目錄索引: {toc_path}")

def audit_book():
    """執行大書安全防禦校驗與 TOC 生成"""
    replacements = load_deid_rules()
    
    if not os.path.exists(BOOK_DIR):
        print(f"❌ 錯誤: book/ 目錄不存在，無法進行校驗！")
        return
        
    files = [f for f in os.listdir(BOOK_DIR) if f.endswith('.md')]
    
    corrected_count = 0
    checked_count = 0
    published_files = []
    
    for filename in sorted(files):
        if filename == 'TOC.md':
            continue
            
        filepath = os.path.join(BOOK_DIR, filename)
        checked_count += 1
        published_files.append(filepath)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            corrected_content, is_changed = audit_and_correct_content(content, replacements)
            
            if is_changed:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(corrected_content)
                print(f"🛡️  已自動修正防禦偏差並存回: {filename}")
                corrected_count += 1
                
        except Exception as e:
            print(f"❌ 處理 {filename} 時出錯: {e}")
            
    # 自動生成目錄
    if len(published_files) > 0:
        generate_toc(published_files)
        
    print(f"\n🎉 大書安全校驗完成！")
    print(f"   - 共計掃描校驗章節數: {checked_count}")
    print(f"   - 自動修正防禦偏差數: {corrected_count}")

if __name__ == '__main__':
    audit_book()
