#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Health Agent (SHA) - 實體紙本報告影像處理與 PDF 合成工具
功能：將使用者拍攝的紙本報告照片 (JPG/PNG) 批次合成為單一 PDF，計算 SHA-256 雜湊並自動命名。
"""

import os
import sys
import hashlib
from PIL import Image

def calculate_sha256(file_path):
    """
    計算檔案的 SHA-256 雜湊值
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def images_to_pdf(image_paths, output_pdf_path):
    """
    將多張圖片 (PNG/JPG) 合成並另存為單一多頁 PDF
    """
    if not image_paths:
        print("【錯誤】未提供任何輸入圖片！", file=sys.stderr)
        return False

    valid_images = []
    
    # 依序開啟並檢查圖片，同時轉換為 RGB 格式 (PDF 不支援 RGBA)
    for img_path in image_paths:
        if not os.path.exists(img_path):
            print(f"【警告】忽略不存在的圖片檔案：{img_path}", file=sys.stderr)
            continue
        try:
            img = Image.open(img_path)
            # 轉換為 RGB
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            valid_images.append(img)
            print(f"【處理】載入影像成功: {img_path} ({img.size})")
        except Exception as e:
            print(f"【錯誤】無法讀取圖片 {img_path}，錯誤原因: {e}", file=sys.stderr)

    if not valid_images:
        print("【錯誤】沒有成功載入任何有效影像，無法合成 PDF！", file=sys.stderr)
        return False

    try:
        # 第一張圖片作為主體，其餘圖片作為追加頁面 (append_images)
        first_img = valid_images[0]
        extra_imgs = valid_images[1:]
        
        first_img.save(
            output_pdf_path,
            save_all=True,
            append_images=extra_imgs
        )
        print(f"【成功】成功合成 PDF 檔案：{output_pdf_path}")
        return True
    except Exception as e:
        print(f"【錯誤】PDF 合成存檔失敗，原因: {e}", file=sys.stderr)
        return False

def process_inbox_images(inbox_dir, patient_id, report_desc):
    """
    掃描收件箱中符合的圖片，將其批次合成並重命名移至 raw 目錄
    """
    if not os.path.exists(inbox_dir):
        print(f"【錯誤】找不到收件箱目錄：{inbox_dir}", file=sys.stderr)
        return

    # 搜尋 JPEG/PNG 檔案 (排除隱藏檔)
    valid_extensions = ('.jpg', '.jpeg', '.png')
    files = [f for f in os.listdir(inbox_dir) if f.lower().endswith(valid_extensions)]
    # 排序確保頁面順序正確 (建議使用者在檔名加上 _page1, _page2 命名)
    files.sort()

    if not files:
        print(f"【提示】收件箱 {inbox_dir} 中無新進 JPG/PNG 圖片檔。")
        return

    image_paths = [os.path.join(inbox_dir, f) for f in files]
    temp_pdf = os.path.join(inbox_dir, "temp_combined.pdf")

    print(f"【啟動】偵測到收件箱有 {len(image_paths)} 張圖片，開始進行 PDF 合成...")
    if images_to_pdf(image_paths, temp_pdf):
        # 計算 SHA-256 雜湊
        file_hash = calculate_sha256(temp_pdf)
        hash_short = file_hash[:8]
        
        # 依照 sha- 前綴物理命名規則命名
        # 格式: [YYYYMMDD]_[病患ID]_[描述]_[SHA256].pdf
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        new_filename = f"{date_str}_{patient_id}_{report_desc}_{hash_short}.pdf"
        
        # 定位目標歸檔路徑 (預設移至 data/raw/clinical_reports/)
        target_dir = os.path.abspath(os.path.join(inbox_dir, "..", "raw", "clinical_reports"))
        os.makedirs(target_dir, exist_ok=True)
        final_pdf_path = os.path.join(target_dir, new_filename)
        
        # 移動檔案
        if os.path.exists(final_pdf_path):
            os.remove(final_pdf_path)
        os.rename(temp_pdf, final_pdf_path)
        print(f"【歸檔成功】原始圖片已合成 PDF 並移動至實體庫：{final_pdf_path}")
        print(f"【雜湊認證】SHA-256: {file_hash}")
        
        # 清除 inbox 內原先已合併的圖片檔 (防範重複處理)
        for path in image_paths:
            try:
                os.remove(path)
                print(f"【清理】刪除 inbox 已處理圖片: {path}")
            except Exception as e:
                print(f"【警告】清理圖片失敗 {path}: {e}", file=sys.stderr)
    else:
        print("【失敗】影像合成過程出錯。")

if __name__ == '__main__':
    # CLI 測試與執行範例
    # 使用說明: python3 pdf_processor.py <patient_id> <report_desc>
    if len(sys.argv) < 3:
        print("使用說明: python3 pdf_processor.py <patient_id> <report_desc>")
        print("範例: python3 pdf_processor.py PUMC_004 biopsy_report")
        sys.exit(1)
        
    p_id = sys.argv[1]
    desc = sys.argv[2]
    
    # 本地對應 inbox 路徑
    script_dir = os.path.dirname(os.path.abspath(__file__))
    inbox_path = os.path.abspath(os.path.join(script_dir, "..", "data", "inbox"))

    
    # 建立測試目錄
    os.makedirs(inbox_path, exist_ok=True)
    process_inbox_images(inbox_path, p_id, desc)
