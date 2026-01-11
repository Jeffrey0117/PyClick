#!/usr/bin/env python3
"""
超極簡版 - 三個按鈕搞定
"""

import tkinter as tk
from PIL import Image, ImageTk
import cv2
import numpy as np
import mss
import pyautogui
import time

class MiniBlueClicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("藍色點擊")
        self.root.attributes("-topmost", True)  # 置頂
        
        self.img = None
        self.target = None
        self.offset = (0, 0)
        
        # 三個按鈕
        tk.Button(self.root, text="1. 截圖", command=self.snap, 
                  width=12, height=2, bg="#4CAF50", fg="white").pack(pady=5, padx=10)
        tk.Button(self.root, text="2. 找藍色", command=self.find, 
                  width=12, height=2, bg="#2196F3", fg="white").pack(pady=5, padx=10)
        tk.Button(self.root, text="3. 點擊", command=self.click, 
                  width=12, height=2, bg="#FF5722", fg="white").pack(pady=5, padx=10)
        
        # 狀態
        self.label = tk.Label(self.root, text="按 1 開始", wraplength=150)
        self.label.pack(pady=10, padx=10)
        
        # 小預覽
        self.preview = tk.Label(self.root, bg="#333")
        self.preview.pack(pady=5, padx=10)
    
    def snap(self):
        self.root.iconify()
        time.sleep(0.3)
        
        with mss.mss() as sct:
            m = sct.monitors[0]
            self.img = np.array(sct.grab(m))
            self.img = cv2.cvtColor(self.img, cv2.COLOR_BGRA2BGR)
            self.offset = (m["left"], m["top"])
        
        self.root.deiconify()
        self.target = None
        self.show_thumb(self.img)
        self.label.config(text=f"已截圖 {self.img.shape[1]}x{self.img.shape[0]}")
    
    def find(self):
        if self.img is None:
            self.label.config(text="先截圖！")
            return
        
        hsv = cv2.cvtColor(self.img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (100, 100, 50), (130, 255, 255))
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best = None
        best_area = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area > best_area:
                best_area = area
                M = cv2.moments(c)
                if M["m00"] > 0:
                    best = (int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"]), c)
        
        if best:
            self.target = (best[0], best[1])
            
            # 畫出來
            vis = self.img.copy()
            cv2.drawContours(vis, [best[2]], -1, (0, 255, 0), 3)
            cv2.circle(vis, self.target, 15, (0, 0, 255), -1)
            self.show_thumb(vis)
            
            self.label.config(text=f"找到! ({self.target[0]}, {self.target[1]})")
        else:
            self.label.config(text="沒找到藍色")
    
    def click(self):
        if self.target is None:
            self.label.config(text="先找藍色！")
            return
        
        gx = self.target[0] + self.offset[0]
        gy = self.target[1] + self.offset[1]
        
        self.root.iconify()
        time.sleep(0.2)
        pyautogui.click(gx, gy)
        time.sleep(0.3)
        self.root.deiconify()
        
        self.label.config(text=f"已點擊 ({gx}, {gy})")
    
    def show_thumb(self, img):
        h, w = img.shape[:2]
        scale = min(150/w, 100/h)
        small = cv2.resize(img, (int(w*scale), int(h*scale)))
        small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(small))
        self.preview.config(image=self.photo)
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MiniBlueClicker().run()
