#!/usr/bin/env python3
"""
智能點擊器 - 模板匹配 + 藍色偵測
1. 截圖 → 偵測藍色輔助定位
2. 拖曳框選目標
3. 儲存模板
4. 熱鍵模式：按 F6 自動找圖點擊
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import mss
import pyautogui
import threading
import keyboard
import time
import os

pyautogui.FAILSAFE = True


class SmartClicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("智能點擊器")
        self.root.geometry("900x700")

        # 狀態
        self.screenshot = None
        self.template = None
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0

        # 拖曳選取
        self.drag_start = None
        self.drag_rect = None
        self.selection = None  # (x1, y1, x2, y2) 原圖座標

        # 點擊模式
        self.click_mode = False
        self.hotkey = 'F6'

        self.setup_ui()
        self.setup_hotkey()

    def setup_ui(self):
        # === 上方按鈕區 ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(btn_frame, text="1. 截圖", command=self.take_screenshot).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="2. 偵測藍色", command=self.detect_blue).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="3. 儲存選取", command=self.save_template).pack(side="left", padx=5)

        # 分隔
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=10)

        # 點擊模式
        self.mode_var = tk.StringVar(value="關閉")
        self.mode_btn = ttk.Button(btn_frame, text="點擊模式: 關閉", command=self.toggle_click_mode)
        self.mode_btn.pack(side="left", padx=5)

        ttk.Label(btn_frame, text=f"熱鍵: {self.hotkey}").pack(side="left", padx=5)

        # 狀態標籤
        self.status_var = tk.StringVar(value="按「截圖」開始")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side="right", padx=10)

        # === 預覽區域 ===
        preview_frame = ttk.LabelFrame(self.root, text="預覽 (拖曳框選目標)")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(preview_frame, bg="#333", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # 綁定滑鼠事件
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        # === 下方：模板預覽 ===
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(bottom_frame, text="已儲存模板:").pack(side="left")
        self.template_label = ttk.Label(bottom_frame, text="(無)", foreground="gray")
        self.template_label.pack(side="left", padx=5)

        self.template_preview = ttk.Label(bottom_frame, background="#333")
        self.template_preview.pack(side="left", padx=10)

        # 測試按鈕
        ttk.Button(bottom_frame, text="測試找圖", command=self.test_find).pack(side="right", padx=5)

    def setup_hotkey(self):
        """設定熱鍵監聽"""
        def hotkey_listener():
            keyboard.add_hotkey(self.hotkey, self.on_hotkey)
            keyboard.wait()

        t = threading.Thread(target=hotkey_listener, daemon=True)
        t.start()

    def take_screenshot(self):
        """截圖"""
        self.status_var.set("截圖中...")
        self.root.update()

        self.root.iconify()
        self.root.update()
        time.sleep(0.3)

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            self.screenshot = np.array(shot)
            self.screenshot = cv2.cvtColor(self.screenshot, cv2.COLOR_BGRA2BGR)
            self.offset_x = monitor["left"]
            self.offset_y = monitor["top"]

        self.root.deiconify()
        self.root.update()

        self.selection = None
        self.show_preview(self.screenshot)
        self.status_var.set(f"截圖完成 {self.screenshot.shape[1]}x{self.screenshot.shape[0]} - 可拖曳框選目標")

    def detect_blue(self):
        """偵測藍色區域"""
        if self.screenshot is None:
            self.status_var.set("請先截圖！")
            return

        hsv = cv2.cvtColor(self.screenshot, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([100, 100, 50]), np.array([130, 255, 255]))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        preview = self.screenshot.copy()
        count = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area < 100:
                continue
            count += 1
            cv2.drawContours(preview, [c], -1, (0, 255, 0), 2)
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 255, 255), 1)

        self.show_preview(preview)
        self.status_var.set(f"找到 {count} 個藍色區域 - 拖曳框選你要的目標")

    def show_preview(self, img, draw_selection=True):
        """顯示預覽圖"""
        self.root.update()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w < 10:
            canvas_w, canvas_h = 880, 450

        h, w = img.shape[:2]
        self.scale = min(canvas_w / w, canvas_h / h, 1.0)

        new_w = int(w * self.scale)
        new_h = int(h * self.scale)

        resized = cv2.resize(img, (new_w, new_h))

        # 畫選取框
        if draw_selection and self.selection:
            x1, y1, x2, y2 = self.selection
            sx1 = int(x1 * self.scale)
            sy1 = int(y1 * self.scale)
            sx2 = int(x2 * self.scale)
            sy2 = int(y2 * self.scale)
            cv2.rectangle(resized, (sx1, sy1), (sx2, sy2), (0, 0, 255), 2)

        resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        self.photo = ImageTk.PhotoImage(Image.fromarray(resized))

        self.canvas.delete("all")
        self.img_x = (canvas_w - new_w) // 2
        self.img_y = (canvas_h - new_h) // 2
        self.canvas.create_image(self.img_x, self.img_y, anchor="nw", image=self.photo)

    def canvas_to_img(self, cx, cy):
        """Canvas 座標轉原圖座標"""
        ix = int((cx - self.img_x) / self.scale)
        iy = int((cy - self.img_y) / self.scale)
        return ix, iy

    def on_drag_start(self, event):
        """開始拖曳"""
        if self.screenshot is None:
            return
        self.drag_start = (event.x, event.y)
        self.drag_rect = None

    def on_drag_move(self, event):
        """拖曳中"""
        if self.drag_start is None:
            return

        if self.drag_rect:
            self.canvas.delete(self.drag_rect)

        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y
        self.drag_rect = self.canvas.create_rectangle(x1, y1, x2, y2,
                                                       outline="red", width=2, dash=(4, 4))

    def on_drag_end(self, event):
        """拖曳結束"""
        if self.drag_start is None or self.screenshot is None:
            return

        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        # 轉換成原圖座標
        ix1, iy1 = self.canvas_to_img(x1, y1)
        ix2, iy2 = self.canvas_to_img(x2, y2)

        # 確保座標正確
        ix1, ix2 = min(ix1, ix2), max(ix1, ix2)
        iy1, iy2 = min(iy1, iy2), max(iy1, iy2)

        # 檢查範圍
        h, w = self.screenshot.shape[:2]
        ix1 = max(0, min(ix1, w))
        ix2 = max(0, min(ix2, w))
        iy1 = max(0, min(iy1, h))
        iy2 = max(0, min(iy2, h))

        if ix2 - ix1 < 10 or iy2 - iy1 < 10:
            self.status_var.set("選取範圍太小！")
            self.drag_start = None
            return

        self.selection = (ix1, iy1, ix2, iy2)
        self.show_preview(self.screenshot)

        self.status_var.set(f"已選取 ({ix1},{iy1}) - ({ix2},{iy2})，按「儲存選取」確認")
        self.drag_start = None

    def save_template(self):
        """儲存選取區域為模板"""
        if self.selection is None:
            self.status_var.set("請先拖曳框選目標！")
            return

        x1, y1, x2, y2 = self.selection
        self.template = self.screenshot[y1:y2, x1:x2].copy()

        # 顯示模板預覽
        h, w = self.template.shape[:2]
        scale = min(80/w, 50/h, 1.0)
        thumb = cv2.resize(self.template, (int(w*scale), int(h*scale)))
        thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
        self.template_photo = ImageTk.PhotoImage(Image.fromarray(thumb))
        self.template_preview.config(image=self.template_photo)
        self.template_label.config(text=f"{w}x{h} px", foreground="green")

        self.status_var.set(f"模板已儲存！開啟「點擊模式」後按 {self.hotkey} 自動找圖點擊")

    def toggle_click_mode(self):
        """切換點擊模式"""
        if self.template is None:
            self.status_var.set("請先儲存模板！")
            return

        self.click_mode = not self.click_mode
        if self.click_mode:
            self.mode_btn.config(text="點擊模式: 開啟")
            self.status_var.set(f"點擊模式開啟！按 {self.hotkey} 找圖並點擊")
        else:
            self.mode_btn.config(text="點擊模式: 關閉")
            self.status_var.set("點擊模式已關閉")

    def on_hotkey(self):
        """熱鍵觸發"""
        if not self.click_mode or self.template is None:
            return

        # 在新執行緒中執行避免阻塞
        threading.Thread(target=self.find_and_click, daemon=True).start()

    def find_and_click(self):
        """找圖並點擊"""
        try:
            # 記住原始游標位置
            original_pos = pyautogui.position()

            # 截取當前螢幕
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screen = np.array(sct.grab(monitor))
                screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                ox, oy = monitor["left"], monitor["top"]

            # 模板匹配
            result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val < 0.7:
                self.root.after(0, lambda: self.status_var.set(f"找不到目標 (相似度 {max_val:.1%})"))
                return

            # 計算點擊位置（模板中心）
            th, tw = self.template.shape[:2]
            cx = max_loc[0] + tw // 2 + ox
            cy = max_loc[1] + th // 2 + oy

            # 點擊
            pyautogui.click(cx, cy)

            # 游標回到原位置
            time.sleep(0.05)
            pyautogui.moveTo(original_pos[0], original_pos[1])

            self.root.after(0, lambda: self.status_var.set(f"已點擊 ({cx}, {cy}) 相似度 {max_val:.1%}"))

        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"錯誤: {e}"))

    def test_find(self):
        """測試找圖（不點擊）"""
        if self.template is None:
            self.status_var.set("請先儲存模板！")
            return

        self.status_var.set("測試找圖中...")
        self.root.update()

        # 最小化後截圖
        self.root.iconify()
        self.root.update()
        time.sleep(0.3)

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            screen = np.array(sct.grab(monitor))
            screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)

        self.root.deiconify()

        # 模板匹配
        result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # 畫出結果
        th, tw = self.template.shape[:2]
        preview = screen.copy()

        if max_val >= 0.7:
            cv2.rectangle(preview, max_loc, (max_loc[0]+tw, max_loc[1]+th), (0, 255, 0), 3)
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            cv2.circle(preview, (cx, cy), 10, (0, 0, 255), -1)
            self.status_var.set(f"找到！位置 ({cx}, {cy}) 相似度 {max_val:.1%}")
        else:
            self.status_var.set(f"找不到目標 (最高相似度 {max_val:.1%})")

        self.screenshot = screen
        self.show_preview(preview, draw_selection=False)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = SmartClicker()
    app.run()
