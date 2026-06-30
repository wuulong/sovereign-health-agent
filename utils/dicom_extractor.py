# -*- coding: utf-8 -*-
"""
Sovereign Health Agent - DICOM 醫療影像與報告本地萃取模組 (整合超音波分析與 OCR)
功能：提供完全本地端、離線的 DICOM (.dcm) 影像解析與轉檔，自動偵測量測游標 (Caliper) 並提取燒錄文字 (OCR) 轉譯為白話資訊。
"""

import os
import sys
import json
from datetime import datetime
import numpy as np
from PIL import Image

try:
    import pydicom
    from pydicom.pixel_data_handlers.util import convert_color_space
except ImportError:
    pydicom = None

# 嘗試導入超音波量測與 OCR 模組
try:
    from utils.ultrasound_ocr_extractor import UltrasoundOcrExtractor
except ImportError:
    # 支援相對路徑與包結構
    try:
        from ultrasound_ocr_extractor import UltrasoundOcrExtractor
    except ImportError:
        UltrasoundOcrExtractor = None


class DicomExtractor:
    def __init__(self):
        if pydicom is None:
            raise ImportError("未安裝 pydicom 函式庫，請執行 'pip install pydicom' 進行安裝。")
        
        # 初始化超音波 OCR 與游標檢測服務
        self.ocr_extractor = None
        if UltrasoundOcrExtractor is not None:
            try:
                self.ocr_extractor = UltrasoundOcrExtractor()
            except Exception as e:
                print(f"Warning: Failed to load UltrasoundOcrExtractor: {e}")
        else:
            print("Warning: UltrasoundOcrExtractor module not found. Advanced analysis will be disabled.")

    def extract_metadata(self, filepath):
        """
        讀取單一 DICOM 檔案的核心中介資料 (Metadata)
        """
        try:
            ds = pydicom.dcmread(filepath)
            
            def get_tag_val(tag_name, default=""):
                val = getattr(ds, tag_name, default)
                if val is None:
                    return default
                return str(val).strip()
                
            study_date = get_tag_val("StudyDate", "")
            if len(study_date) == 8:
                study_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}"
                
            study_time = get_tag_val("StudyTime", "")
            if len(study_time) >= 6:
                study_time = f"{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}"

            return {
                "patient_name": get_tag_val("PatientName", "去識別化病患"),
                "patient_id": get_tag_val("PatientID", "未設定"),
                "study_date": study_date,
                "study_time": study_time,
                "modality": get_tag_val("Modality", ""),
                "manufacturer": get_tag_val("Manufacturer", ""),
                "model_name": get_tag_val("ManufacturerModelName", ""),
                "institution": get_tag_val("InstitutionName", ""),
                "study_description": get_tag_val("StudyDescription", ""),
                "series_description": get_tag_val("SeriesDescription", ""),
                "physician": get_tag_val("PerformingPhysicianName", ""),
                "image_comment": get_tag_val("ImageComments", "")
            }
        except Exception as e:
            raise RuntimeError(f"讀取 DICOM 失敗: {e}")

    def export_png(self, filepath, output_png_path):
        """
        將 DICOM 檔案的像素資料 (Pixel Array) 轉換並匯出為 PNG 影像
        """
        try:
            ds = pydicom.dcmread(filepath)
            arr = ds.pixel_array
            
            if len(arr.shape) == 2:
                # 灰階影像歸一化
                arr_min = arr.min()
                arr_max = arr.max()
                if arr_max > arr_min:
                    arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)
                else:
                    arr = arr.astype(np.uint8)
                img = Image.fromarray(arr)
            elif len(arr.shape) == 3:
                # 彩色影像處理
                photometric = getattr(ds, "PhotometricInterpretation", "")
                if photometric in ["YBR_FULL", "YBR_FULL_422", "YBR_RCT", "YBR_ICT"]:
                    try:
                        arr = convert_color_space(arr, photometric, "RGB")
                    except Exception:
                        pass
                img = Image.fromarray(arr.astype(np.uint8))
            else:
                raise ValueError(f"不支援的影像維度: {arr.shape}")
                
            img.save(output_png_path)
            return True
        except Exception as e:
            raise RuntimeError(f"轉檔 PNG 失敗: {e}")

    def generate_patient_friendly_explanation(self, calipers, ocr_texts):
        """根據 Caliper 座標及 OCR 提取到的文字，動態組裝產生病患友善的白話解釋說明"""
        explanations = []
        
        # 尋找是否有量測數據 (優先找帶有 cm 或 mm 單位的數值，如 0.9 cm)
        measurement = None
        for item in ocr_texts:
            if item["is_measurement"] and any(unit in item["text"].lower() for unit in ["cm", "mm"]):
                measurement = item["text"]
                break
        if not measurement:
            for item in ocr_texts:
                if item["is_measurement"]:
                    measurement = item["text"]
                    break
                
        # 尋找是否有器官或部位標記
        medical_tag = None
        for item in ocr_texts:
            if item["is_medical"]:
                medical_tag = item["text"].upper()
                break

        # 針對量測點 (Caliper) 解釋
        if calipers:
            explanations.append(f"1. **量測位置**: 偵測到黃色十字量測點 (Caliper) 位於成像區之座標 `{calipers[0][:2]}`。這代表醫生在檢查過程中，在此切面特別針對該處結構進行了測量。")
            
        # 針對 OCR 數據與臨床意義解釋
        if measurement:
            explanations.append(f"2. **自動提取數據**: 經由影像資訊列之逆向工程識別，本切面的量測數值為 **`{measurement}`**。")
            
            # 給予白話臨床對位說明
            if "cm" in measurement.lower():
                try:
                    num_val = float(measurement.lower().replace("cm", "").strip())
                except ValueError:
                    num_val = 0.0
            else:
                num_val = 0.0

            if medical_tag:
                explanations.append(f"3. **標籤與臨床意義**: 影像上方標註為 `{medical_tag}`，代表醫生針對該部位的 **{measurement}** 病灶或切面進行記錄。")
            else:
                # 模糊提示
                explanations.append(f"3. **臨床白話對照**: 在腹部超音波追蹤中，測量大於 0.3 公分通常是針對**膽結石、膽囊息肉、或者是肝臟/腎臟內的水泡 (囊腫) 或血管瘤**進行監控。此照片可做為您比對日後追蹤（看病灶是否有長大或消失）的基準照片。")
        else:
            if calipers:
                explanations.append("2. **臨床說明**: 此處點下了單一量測標記，通常是醫師用以指出疑似病灶或解剖邊界之起點，本影像上未顯示最終計算之文字結果，建議與紙本報告進行核對。")

        return "\n  ".join(explanations)

    def process_directory(self, source_dir, output_dir):
        """
        批量處理目錄下所有 DICOM 檔案，匯出影像、執行 OCR 分析並產生整合 Markdown 報告
        """
        if not os.path.exists(source_dir):
            raise FileNotFoundError(f"找不到來源目錄: {source_dir}")
            
        os.makedirs(output_dir, exist_ok=True)
        
        dcm_files = [f for f in os.listdir(source_dir) if f.lower().endswith(".dcm")]
        dcm_files.sort()
        
        if not dcm_files:
            return 0, []
            
        study_info = {}
        image_list = []
        
        for idx, filename in enumerate(dcm_files):
            filepath = os.path.join(source_dir, filename)
            png_filename = f"image_{idx+1:02d}.png"
            png_filepath = os.path.join(output_dir, png_filename)
            
            try:
                # 1. 萃取中介資料
                meta = self.extract_metadata(filepath)
                if not study_info:
                    study_info = meta
                
                # 2. 匯出圖片
                self.export_png(filepath, png_filepath)
                img_success = True
                img_err = ""
                
                # 3. 執行超音波 OCR 與游標檢測
                analysis_result = {"calipers": [], "ocr_texts": []}
                if self.ocr_extractor:
                    try:
                        # analyze_image 會自動在 output_dir 產生 image_XX_annotated.png
                        analysis_result = self.ocr_extractor.analyze_image(png_filepath, output_dir)
                    except Exception as ocr_ex:
                        print(f"OCR analysis skipped for {filename} due to: {ocr_ex}")
                
            except Exception as e:
                img_success = False
                img_err = str(e)
                meta = {}
                analysis_result = {"calipers": [], "ocr_texts": []}
                
            image_list.append({
                "dcm_file": filename,
                "png_file": png_filename if img_success else None,
                "series_description": meta.get("series_description", ""),
                "image_comment": meta.get("image_comment", ""),
                "img_success": img_success,
                "img_err_msg": img_err,
                "calipers": analysis_result.get("calipers", []),
                "ocr_texts": analysis_result.get("ocr_texts", [])
            })
            
        # 產生彙整 Markdown 報告
        report_path = os.path.join(output_dir, "report_summary.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 🏥 腹部超音波影像與檢查報告萃取書 (MHB)\n\n")
            f.write(f"> [!IMPORTANT]\n")
            f.write(f"> **本檔案由主權個人健康代理人自動解讀本機 DICOM 檔案並進行 OCR 影像分析產出。**\n")
            f.write(f"> **資料來源目錄**：{source_dir}\n")
            f.write(f"> **解碼產出時間**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## 📌 一、 檢查基本資訊\n\n")
            if study_info:
                f.write(f"* **病患姓名**：{study_info['patient_name']} (ID: {study_info['patient_id']})\n")
                f.write(f"* **檢查醫院**：{study_info['institution'] if study_info['institution'] else '未於 DICOM 載明'}\n")
                f.write(f"* **檢查日期**：{study_info['study_date']} (時間: {study_info['study_time']})\n")
                f.write(f"* **檢查儀器**：{study_info['modality']} ({study_info['manufacturer']} - {study_info['model_name']})\n")
                f.write(f"* **檢查項目**：{study_info['study_description']}\n")
                f.write(f"* **執行醫師**：{study_info['physician'] if study_info['physician'] else '未於 DICOM 載明'}\n")
            else:
                f.write("* 查無有效檢查基本資訊。\n")
                
            f.write("\n---\n\n")
            f.write("## 🖼️ 二、 影像列表與註記\n\n")
            f.write("本段落呈現所有超音波切面影像的註記與註解說明，部分檔案可能包含檢查當下儀器上登錄的量測數據。\n\n")
            
            for idx, img in enumerate(image_list):
                f.write(f"### 📷 影像 {idx+1:02d} ({img['dcm_file']})\n")
                f.write(f"* **系列說明 (Series Description)**：{img['series_description'] if img['series_description'] else '無'}\n")
                f.write(f"* **影像註記 (Image Comments)**：{img['image_comment'] if img['image_comment'] else '無'}\n")
                
                if img['img_success']:
                    # 判斷是否偵測到游標或文字
                    has_calipers = len(img["calipers"]) > 0
                    has_measurements = any(item["is_measurement"] for item in img["ocr_texts"])
                    
                    if has_calipers or has_measurements:
                        annotated_filename = f"image_{idx+1:02d}_annotated.png"
                        f.write(f"* **已匯出圖片**：[{img['png_file']}]({img['png_file']}) | [標註分析圖]({annotated_filename})\n")
                        
                        # 生成並寫入白話翻譯
                        explanation_text = self.generate_patient_friendly_explanation(img["calipers"], img["ocr_texts"])
                        f.write(f"* **💡 代理人自動分析結果 & 臨床白話解釋**:\n  {explanation_text}\n\n")
                        
                        f.write(f"![影像 {idx+1:02d}]({img['png_file']})\n")
                        f.write(f"![影像 {idx+1:02d} 標註]({annotated_filename})\n")
                    else:
                        f.write(f"* **已匯出圖片**：[{img['png_file']}]({img['png_file']})\n")
                        f.write(f"\n![影像 {idx+1:02d}]({img['png_file']})\n")
                else:
                    f.write(f"* **❌ 影像轉檔失敗**：{img['img_err_msg']}\n")
                f.write("\n---\n\n")
                
        return len(dcm_files), image_list


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用說明: python dicom_extractor.py <DICOM資料夾路徑> [輸出資料夾路徑]")
        sys.exit(1)
        
    src = sys.argv[1]
    dest = sys.argv[2] if len(sys.argv) > 2 else os.path.join(src, "extracted_report")
    
    try:
        extractor = DicomExtractor()
        count, results = extractor.process_directory(src, dest)
        print(f"處理成功！共解析 {count} 個檔案，報告已輸出至 {dest}/report_summary.md")
    except Exception as ex:
        print(f"執行出錯: {ex}")
        sys.exit(1)
