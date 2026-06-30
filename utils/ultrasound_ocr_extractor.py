# -*- coding: utf-8 -*-
"""
Sovereign Health Agent - 超音波影像游標與燒錄文字 OCR 萃取模組
功能：利用 OpenCV 及 EasyOCR，自動定位超音波影像中的 Caliper 游標，並自動提取燒錄之量測數值與器官標籤。
"""

import os
import re
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import easyocr
except ImportError:
    easyocr = None


class UltrasoundOcrExtractor:
    def __init__(self):
        self.opencv_available = cv2 is not None
        self.easyocr_available = easyocr is not None
        self.reader = None

        if not self.opencv_available:
            print("Warning: OpenCV (cv2) is not installed. Caliper detection will be disabled.")
            
        if self.easyocr_available:
            try:
                # 在本地 CPU 上初始化 EasyOCR 英文 Reader
                self.reader = easyocr.Reader(['en'], gpu=False)
            except Exception as e:
                print(f"Warning: Failed to initialize EasyOCR reader: {e}")
                self.easyocr_available = False
        else:
            print("Warning: EasyOCR is not installed. Text extraction will be disabled.")

    def detect_calipers(self, img):
        """偵測超音波影像中的黃色或亮白色量測游標"""
        if not self.opencv_available:
            return []

        calipers_found = []
        
        # 1. 偵測黃色/綠色等亮色 Caliper (HSV 色彩過濾)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_yellow = np.array([15, 50, 100])
        upper_yellow = np.array([35, 255, 255])
        yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

        contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for con in contours:
            area = cv2.contourArea(con)
            if 2 <= area <= 400:
                x, y, box_w, box_h = cv2.boundingRect(con)
                aspect_ratio = float(box_w) / box_h
                if 0.5 <= aspect_ratio <= 2.0:
                    cx = x + box_w // 2
                    cy = y + box_h // 2
                    calipers_found.append((cx, cy, "Yellow Caliper", int(area)))

        # 2. 如果沒有黃色游標，偵測亮白色十字 Caliper (影像形態學與特徵過濾)
        if not calipers_found:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, bright_mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            cross_kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (5, 5))
            morph_cross = cv2.morphologyEx(bright_mask, cv2.MORPH_OPEN, cross_kernel)

            contours_white, _ = cv2.findContours(morph_cross, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for con in contours_white:
                area = cv2.contourArea(con)
                if 4 <= area <= 250:
                    x, y, box_w, box_h = cv2.boundingRect(con)
                    aspect_ratio = float(box_w) / box_h
                    if 0.6 <= aspect_ratio <= 1.7 and box_w < 25 and box_h < 25:
                        cx = x + box_w // 2
                        cy = y + box_h // 2
                        if not any(np.hypot(cx - fx, cy - fy) < 10 for fx, fy, _, _ in calipers_found):
                            calipers_found.append((cx, cy, "White Caliper", int(area)))
                            
        return calipers_found

    def extract_text(self, img):
        """使用 EasyOCR 提取影像中所有燒錄的文字並過濾出關鍵字與量測數據"""
        if not self.easyocr_available or self.reader is None:
            return []

        ocr_results = self.reader.readtext(img)
        parsed_texts = []
        
        # 用於檢測文字中是否含有量測數據（需包含數字與 cm 或 mm 單位以排除單純的刻度數字）
        measure_pattern = re.compile(r'\d+\s*(\.\s*\d+)?\s*(cm|mm)', re.IGNORECASE)
        # 用於退回匹配純數字 (例如無單位但只有純數字的數值)
        backup_pattern = re.compile(r'^\d+(\.\d+)?$', re.IGNORECASE)
        
        # 常用超音波器官與病理標記英文字彙
        medical_words = {'liver', 'gb', 'gallbladder', 'kidney', 'spleen', 'pancreas', 'ao', 'ivc', 'pv', 'mass', 'cyst', 'stone', 'node'}

        for bbox, text, prob in ocr_results:
            text_clean = text.strip()
            if not text_clean or prob < 0.25:
                continue
                
            # 優先搜尋包含單位的片段
            measure_match = measure_pattern.search(text_clean)
            is_measurement = False
            if measure_match:
                is_measurement = True
                # 將辨識出的文字更換為精準的「數值+單位」片段 (例如 0. 9cm -> 0.9cm)
                text_clean = measure_match.group(0).replace(" ", "")
            elif backup_pattern.match(text_clean):
                is_measurement = True

            # 計算邊框中心點與大小
            pts = np.array(bbox, dtype=np.int32)
            x_min = int(np.min(pts[:, 0]))
            y_min = int(np.min(pts[:, 1]))
            x_max = int(np.max(pts[:, 0]))
            y_max = int(np.max(pts[:, 1]))
            cx = (x_min + x_max) // 2
            cy = (y_min + y_max) // 2
            
            is_medical = text_clean.lower() in medical_words or any(w in text_clean.lower() for w in medical_words)
            
            parsed_texts.append({
                "text": text_clean,
                "confidence": float(prob),
                "bbox": [x_min, y_min, x_max, y_max],
                "center": (cx, cy),
                "is_measurement": is_measurement,
                "is_medical": is_medical
            })
            
        return parsed_texts

    def analyze_image(self, img_path, output_dir=None):
        """
        分析單一超音波影像，定位量測點並提取燒錄數據
        若有輸出目錄，自動產生 annotated 影像
        """
        if not self.opencv_available:
            return {"calipers": [], "ocr_texts": []}

        img = cv2.imread(img_path)
        if img is None:
            return {"calipers": [], "ocr_texts": []}

        calipers = self.detect_calipers(img)
        ocr_texts = self.extract_text(img)

        # 如果需要產生 annotated 影像
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            annotated_img = img.copy()

            # 標註 Caliper (紅色圈 + 綠色標記)
            for i, (cx, cy, label_type, _) in enumerate(calipers):
                cv2.circle(annotated_img, (cx, cy), 12, (0, 0, 255), 2)
                cv2.drawMarker(annotated_img, (cx, cy), (0, 255, 0), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2)
                cv2.putText(annotated_img, f"Caliper #{i+1}", (cx + 15, cy - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)
            
            # 標註 OCR 文字 (綠色或黃色外框)
            for item in ocr_texts:
                x_min, y_min, x_max, y_max = item["bbox"]
                text = item["text"]
                box_color = (0, 255, 255) if item["is_measurement"] else (0, 255, 0)
                
                cv2.rectangle(annotated_img, (x_min, y_min), (x_max, y_max), box_color, 1)
                cv2.putText(annotated_img, text, (x_min, y_min - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, box_color, 1, cv2.LINE_AA)

            base_name = os.path.splitext(os.path.basename(img_path))[0]
            annotated_path = os.path.join(output_dir, f"{base_name}_annotated.png")
            cv2.imwrite(annotated_path, annotated_img)

        return {
            "calipers": calipers,
            "ocr_texts": ocr_texts
        }
