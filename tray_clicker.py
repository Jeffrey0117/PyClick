#!/usr/bin/env python3
"""
系統托盤點擊器 - 最小化運行在右下角
支援：F6 手動觸發 / 自動偵測點擊模式
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import cv2
import numpy as np
import mss
import pyautogui
import pystray
from pystray import MenuItem as Item
import threading
import keyboard
import time
import hashlib

pyautogui.FAILSAFE = True


class TrayClicker:
    def __init__(self):
        self.template = None
        self.hotkey = 'F6'
        self.running = True

        # 模式
        self.mode = "off"  # off / hotkey / auto
        self.auto_thread = None
        self.auto_interval = 0.5  # 自動掃描間隔（秒）
        self.last_screen_hash = None
        self.click_cooldown = 1.0  # 點擊後冷卻時間
        self.last_click_time = 0

        # 建立托盤
        self.icon = None
        self.setup_tray()
        self.setup_hotkey()

    def create_icon_image(self):
        """建立托盤圖示"""
        img = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(img)

        if self.mode == "auto":
            # 自動模式 - 綠色 + A
            draw.ellipse([8, 8, 56, 56], fill='#4CAF50', outline='#2E7D32', width=3)
            draw.text((23, 18), "A", fill='white')
        elif self.mode == "hotkey":
            # 熱鍵模式 - 橘色 + H
            draw.ellipse([8, 8, 56, 56], fill='#FF9800', outline='#F57C00', width=3)
            draw.text((23, 18), "H", fill='white')
        else:
            # 關閉 - 藍色
            draw.ellipse([8, 8, 56, 56], fill='#2196F3', outline='#1976D2', width=3)
            if self.template is None:
                draw.text((24, 18), "?", fill='white')
            else:
                draw.text((23, 18), "O", fill='white')

        return img

    def setup_tray(self):
        """設定系統托盤"""
        menu = pystray.Menu(
            Item('📷 截圖選取目標', self.show_selector),
            Item('─────────', None, enabled=False),
            Item('🔥 自動點擊模式', self.set_auto_mode,
                 checked=lambda item: self.mode == "auto",
                 enabled=lambda item: self.template is not None),
            Item('⌨ 熱鍵模式 (F6)', self.set_hotkey_mode,
                 checked=lambda item: self.mode == "hotkey",
                 enabled=lambda item: self.template is not None),
            Item('⏸ 關閉', self.set_off_mode,
                 checked=lambda item: self.mode == "off"),
            Item('─────────', None, enabled=False),
            Item('⚙ 掃描間隔', pystray.Menu(
                Item('0.3 秒（快）', lambda: self.set_interval(0.3),
                     checked=lambda item: self.auto_interval == 0.3),
                Item('0.5 秒（標準）', lambda: self.set_interval(0.5),
                     checked=lambda item: self.auto_interval == 0.5),
                Item('1.0 秒（省電）', lambda: self.set_interval(1.0),
                     checked=lambda item: self.auto_interval == 1.0),
                Item('2.0 秒（超省電）', lambda: self.set_interval(2.0),
                     checked=lambda item: self.auto_interval == 2.0),
            )),
            Item('🎯 測試找圖', self.test_find,
                 enabled=lambda item: self.template is not None),
            Item('─────────', None, enabled=False),
            Item('❌ 結束', self.quit_app)
        )

        self.icon = pystray.Icon(
            "PyClick",
            self.create_icon_image(),
            "PyClick - 右鍵設定",
            menu
        )

    def setup_hotkey(self):
        """設定熱鍵"""
        keyboard.add_hotkey(self.hotkey, self.on_hotkey)

    def update_icon(self):
        """更新圖示和提示"""
        self.icon.icon = self.create_icon_image()
        if self.mode == "auto":
            self.icon.title = f"PyClick - 自動模式 ({self.auto_interval}s)"
        elif self.mode == "hotkey":
            self.icon.title = "PyClick - 按 F6 點擊"
        elif self.template:
            self.icon.title = "PyClick - 已設定模板"
        else:
            self.icon.title = "PyClick - 右鍵設定"

    def set_interval(self, interval):
        """設定掃描間隔"""
        self.auto_interval = interval
        self.update_icon()

    def set_auto_mode(self, icon=None, item=None):
        """開啟自動模式"""
        if self.template is None:
            return
        self.mode = "auto"
        self.update_icon()
        self.start_auto_thread()

    def set_hotkey_mode(self, icon=None, item=None):
        """開啟熱鍵模式"""
        if self.template is None:
            return
        self.mode = "hotkey"
        self.update_icon()
        self.stop_auto_thread()

    def set_off_mode(self, icon=None, item=None):
        """關閉模式"""
        self.mode = "off"
        self.update_icon()
        self.stop_auto_thread()

    def start_auto_thread(self):
        """啟動自動偵測執行緒"""
        self.stop_auto_thread()
        self.auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self.auto_thread.start()

    def stop_auto_thread(self):
        """停止自動偵測"""
        # 執行緒會自己檢查 mode 並結束
        pass

    def _auto_loop(self):
        """自動偵測迴圈（低耗能策略）"""
        while self.running and self.mode == "auto":
            try:
                # 冷卻期間不掃描
                if time.time() - self.last_click_time < self.click_cooldown:
                    time.sleep(0.1)
                    continue

                # 截圖
                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    screen = np.array(sct.grab(monitor))
                    screen_bgr = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                    ox, oy = monitor["left"], monitor["top"]

                # 計算螢幕 hash（低耗能：只有畫面變化才深度掃描）
                small = cv2.resize(screen_bgr, (160, 90))
                screen_hash = hashlib.md5(small.tobytes()).hexdigest()

                if screen_hash == self.last_screen_hash:
                    # 畫面沒變，跳過
                    time.sleep(self.auto_interval)
                    continue

                self.last_screen_hash = screen_hash

                # 模板匹配
                result = cv2.matchTemplate(screen_bgr, self.template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= 0.7:
                    # 找到了！點擊
                    original_pos = pyautogui.position()

                    th, tw = self.template.shape[:2]
                    cx = max_loc[0] + tw // 2 + ox
                    cy = max_loc[1] + th // 2 + oy

                    pyautogui.click(cx, cy)

                    time.sleep(0.05)
                    pyautogui.moveTo(original_pos[0], original_pos[1])

                    self.last_click_time = time.time()
                    self.last_screen_hash = None  # 重置，讓下次一定會掃

                time.sleep(self.auto_interval)

            except Exception:
                time.sleep(self.auto_interval)

    def show_selector(self, icon=None, item=None):
        """顯示選取視窗"""
        # 先關閉自動模式
        was_auto = self.mode == "auto"
        self.mode = "off"
        self.update_icon()

        threading.Thread(target=lambda: self._show_selector_window(was_auto), daemon=True).start()

    def _show_selector_window(self, restore_auto=False):
        """選取視窗"""
        root = tk.Tk()
        root.title("選取目標")
        root.geometry("800x600")
        root.attributes("-topmost", True)

        screenshot = None
        selection = None
        scale = 1.0
        img_x = 0
        img_y = 0
        drag_start = None
        drag_rect = None

        def take_screenshot():
            nonlocal screenshot, scale, img_x, img_y
            root.iconify()
            root.update()
            time.sleep(0.3)

            with mss.mss() as sct:
                monitor = sct.monitors[0]
                shot = sct.grab(monitor)
                screenshot = np.array(shot)
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

            root.deiconify()
            show_preview()
            status.config(text="拖曳框選目標，或按「偵測藍色」輔助")

        def detect_blue():
            nonlocal screenshot
            if screenshot is None:
                status.config(text="請先截圖！")
                return

            hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([100, 100, 50]), np.array([130, 255, 255]))
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            preview = screenshot.copy()
            count = 0
            for c in contours:
                if cv2.contourArea(c) < 100:
                    continue
                count += 1
                cv2.drawContours(preview, [c], -1, (0, 255, 0), 2)
                x, y, w, h = cv2.boundingRect(c)
                cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 255, 255), 1)

            show_preview(preview)
            status.config(text=f"找到 {count} 個藍色區域，拖曳框選你要的")

        def show_preview(img=None):
            nonlocal scale, img_x, img_y
            if img is None:
                img = screenshot
            if img is None:
                return

            root.update()
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if cw < 10:
                cw, ch = 780, 450

            h, w = img.shape[:2]
            scale = min(cw / w, ch / h, 1.0)
            nw, nh = int(w * scale), int(h * scale)

            resized = cv2.resize(img, (nw, nh))
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

            photo = ImageTk.PhotoImage(Image.fromarray(resized))
            canvas.image = photo

            canvas.delete("all")
            img_x = (cw - nw) // 2
            img_y = (ch - nh) // 2
            canvas.create_image(img_x, img_y, anchor="nw", image=photo)

        def on_drag_start(event):
            nonlocal drag_start
            if screenshot is None:
                return
            drag_start = (event.x, event.y)

        def on_drag_move(event):
            nonlocal drag_rect
            if drag_start is None:
                return
            if drag_rect:
                canvas.delete(drag_rect)
            drag_rect = canvas.create_rectangle(
                drag_start[0], drag_start[1], event.x, event.y,
                outline="red", width=2, dash=(4, 4)
            )

        def on_drag_end(event):
            nonlocal drag_start, selection
            if drag_start is None or screenshot is None:
                return

            x1, y1 = drag_start
            x2, y2 = event.x, event.y

            ix1 = int((min(x1, x2) - img_x) / scale)
            iy1 = int((min(y1, y2) - img_y) / scale)
            ix2 = int((max(x1, x2) - img_x) / scale)
            iy2 = int((max(y1, y2) - img_y) / scale)

            h, w = screenshot.shape[:2]
            ix1, ix2 = max(0, ix1), min(w, ix2)
            iy1, iy2 = max(0, iy1), min(h, iy2)

            if ix2 - ix1 < 10 or iy2 - iy1 < 10:
                status.config(text="選取範圍太小！")
                drag_start = None
                return

            selection = (ix1, iy1, ix2, iy2)
            status.config(text=f"已選取 {ix2-ix1}x{iy2-iy1}，按「確認儲存」")
            drag_start = None

        def save_and_close():
            if selection is None:
                status.config(text="請先框選目標！")
                return

            x1, y1, x2, y2 = selection
            self.template = screenshot[y1:y2, x1:x2].copy()
            self.last_screen_hash = None
            self.update_icon()

            if restore_auto:
                self.set_auto_mode()

            root.destroy()

        # UI
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(btn_frame, text="1. 截圖", command=take_screenshot).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="2. 偵測藍色", command=detect_blue).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="✓ 確認儲存", command=save_and_close).pack(side="right", padx=5)

        canvas = tk.Canvas(root, bg="#333", cursor="crosshair")
        canvas.pack(fill="both", expand=True, padx=10, pady=5)
        canvas.bind("<ButtonPress-1>", on_drag_start)
        canvas.bind("<B1-Motion>", on_drag_move)
        canvas.bind("<ButtonRelease-1>", on_drag_end)

        status = ttk.Label(root, text="按「截圖」開始")
        status.pack(pady=10)

        root.mainloop()

    def on_hotkey(self):
        """熱鍵觸發"""
        if self.mode != "hotkey" or self.template is None:
            return
        threading.Thread(target=self.find_and_click, daemon=True).start()

    def find_and_click(self):
        """找圖並點擊（手動）"""
        try:
            original_pos = pyautogui.position()

            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screen = np.array(sct.grab(monitor))
                screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                ox, oy = monitor["left"], monitor["top"]

            result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val < 0.7:
                return

            th, tw = self.template.shape[:2]
            cx = max_loc[0] + tw // 2 + ox
            cy = max_loc[1] + th // 2 + oy

            pyautogui.click(cx, cy)

            time.sleep(0.05)
            pyautogui.moveTo(original_pos[0], original_pos[1])

        except Exception:
            pass

    def test_find(self, icon=None, item=None):
        """測試找圖"""
        if self.template is None:
            return
        threading.Thread(target=self._test_find, daemon=True).start()

    def _test_find(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            screen = np.array(sct.grab(monitor))
            screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)

        result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= 0.7:
            self.icon.notify(f"找到目標！相似度 {max_val:.0%}", "PyClick")
        else:
            self.icon.notify(f"找不到（{max_val:.0%}）", "PyClick")

    def quit_app(self, icon=None, item=None):
        """結束"""
        self.running = False
        self.mode = "off"
        keyboard.unhook_all()
        self.icon.stop()

    def run(self):
        self.icon.run()


if __name__ == "__main__":
    app = TrayClicker()
    app.run()
