#!/usr/bin/env python3
"""
極簡 GUI - 先截圖預覽，再點擊藍色區域
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import mss
import pyautogui
import threading

pyautogui.FAILSAFE = True


class BlueClickerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("藍色點擊器")
        self.root.geometry("800x600")
        
        # 狀態
        self.screenshot = None
        self.regions = []
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0
        
        self.setup_ui()
    
    def setup_ui(self):
        # === 上方按鈕區 ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(btn_frame, text="📷 截圖", command=self.take_screenshot).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🔍 偵測藍色", command=self.detect_blue).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="👆 點擊最大", command=self.click_largest).pack(side="left", padx=5)
        
        # 狀態標籤
        self.status_var = tk.StringVar(value="按「截圖」開始")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side="right", padx=10)
        
        # === 預覽區域 ===
        self.canvas = tk.Canvas(self.root, bg="#333")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 點擊 canvas 直接點該位置
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        # === 結果列表 ===
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        ttk.Label(list_frame, text="找到的區域:").pack(side="left")
        self.region_list = ttk.Combobox(list_frame, state="readonly", width=50)
        self.region_list.pack(side="left", padx=5)
        ttk.Button(list_frame, text="點擊選中", command=self.click_selected).pack(side="left")
    
    def take_screenshot(self):
        """截圖"""
        self.status_var.set("截圖中...")
        self.root.update()
        
        # 先最小化視窗
        self.root.iconify()
        self.root.update()
        
        import time
        time.sleep(0.3)  # 等視窗最小化
        
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            self.screenshot = np.array(shot)
            self.screenshot = cv2.cvtColor(self.screenshot, cv2.COLOR_BGRA2BGR)
            self.offset_x = monitor["left"]
            self.offset_y = monitor["top"]
        
        # 恢復視窗
        self.root.deiconify()
        self.root.update()
        
        self.show_preview(self.screenshot)
        self.status_var.set(f"截圖完成: {self.screenshot.shape[1]}x{self.screenshot.shape[0]}")
        self.regions = []
        self.region_list["values"] = []
    
    def detect_blue(self):
        """偵測藍色區域"""
        if self.screenshot is None:
            self.status_var.set("請先截圖！")
            return
        
        # HSV 藍色範圍
        hsv = cv2.cvtColor(self.screenshot, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([100, 100, 50]), np.array([130, 255, 255]))
        
        # 去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # 找輪廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        self.regions = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 100:
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            self.regions.append({"center": (cx, cy), "area": area, "contour": c})
        
        self.regions.sort(key=lambda r: r["area"], reverse=True)
        
        # 畫出結果
        preview = self.screenshot.copy()
        for i, r in enumerate(self.regions):
            cv2.drawContours(preview, [r["contour"]], -1, (0, 255, 0), 2)
            cx, cy = r["center"]
            cv2.circle(preview, (cx, cy), 8, (0, 0, 255), -1)
            cv2.putText(preview, str(i+1), (cx+12, cy+5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        self.show_preview(preview)
        
        # 更新列表
        items = [f"#{i+1} - 位置({r['center'][0]}, {r['center'][1]}) 面積:{r['area']:.0f}" 
                 for i, r in enumerate(self.regions)]
        self.region_list["values"] = items
        if items:
            self.region_list.current(0)
        
        self.status_var.set(f"找到 {len(self.regions)} 個藍色區域")
    
    def show_preview(self, img):
        """顯示預覽圖"""
        self.root.update()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        if canvas_w < 10:
            canvas_w, canvas_h = 780, 400
        
        h, w = img.shape[:2]
        self.scale = min(canvas_w / w, canvas_h / h, 1.0)
        
        new_w = int(w * self.scale)
        new_h = int(h * self.scale)
        
        resized = cv2.resize(img, (new_w, new_h))
        resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        self.photo = ImageTk.PhotoImage(Image.fromarray(resized))
        
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w//2, canvas_h//2, image=self.photo)
    
    def click_largest(self):
        """點擊最大的藍色區域"""
        if not self.regions:
            self.status_var.set("請先偵測藍色！")
            return
        
        r = self.regions[0]
        self.do_click(r["center"])
    
    def click_selected(self):
        """點擊選中的區域"""
        if not self.regions:
            return
        
        idx = self.region_list.current()
        if idx >= 0:
            r = self.regions[idx]
            self.do_click(r["center"])
    
    def on_canvas_click(self, event):
        """點擊 canvas 上的位置"""
        if self.screenshot is None:
            return
        
        # 計算在原圖的座標
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        h, w = self.screenshot.shape[:2]
        preview_w = int(w * self.scale)
        preview_h = int(h * self.scale)
        
        # 圖片左上角在 canvas 的位置
        img_x = (canvas_w - preview_w) // 2
        img_y = (canvas_h - preview_h) // 2
        
        # 轉換到原圖座標
        local_x = int((event.x - img_x) / self.scale)
        local_y = int((event.y - img_y) / self.scale)
        
        if 0 <= local_x < w and 0 <= local_y < h:
            self.do_click((local_x, local_y))
    
    def do_click(self, local_pos):
        """執行點擊"""
        local_x, local_y = local_pos
        global_x = local_x + self.offset_x
        global_y = local_y + self.offset_y
        
        self.status_var.set(f"點擊 ({global_x}, {global_y})...")
        self.root.update()
        
        # 最小化後點擊
        self.root.iconify()
        self.root.update()
        
        import time
        time.sleep(0.2)
        
        pyautogui.click(global_x, global_y)
        
        time.sleep(0.3)
        self.root.deiconify()
        self.status_var.set(f"已點擊 ({global_x}, {global_y})")
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BlueClickerGUI()
    app.run()
