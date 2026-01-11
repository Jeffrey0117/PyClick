#!/usr/bin/env python3
"""
系統托盤點擊器 - 完整面板 + 托盤圖示
支援：F6 手動觸發 / 自動偵測點擊模式
修復：點擊時不搶焦點
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
import ctypes

pyautogui.FAILSAFE = True

# Windows API for click without focus change
user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def click_no_focus(x, y, instant=True):
    """點擊但不改變焦點和前景視窗"""
    # 儲存原本游標位置
    original_pos = pyautogui.position()

    # 儲存當前前景視窗（正在使用的視窗）
    foreground_hwnd = user32.GetForegroundWindow()

    # 移動游標
    user32.SetCursorPos(x, y)

    if instant:
        # 瞬間模式：無延遲
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    else:
        # 穩定模式：有延遲確保點擊被偵測
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.02)

    # 游標回原位
    user32.SetCursorPos(original_pos[0], original_pos[1])

    # 恢復前景視窗焦點
    if foreground_hwnd:
        user32.SetForegroundWindow(foreground_hwnd)


class TrayClicker:
    def __init__(self):
        self.template = None
        self.hotkey = 'F6'
        self.running = True

        # 模式
        self.mode = "off"  # off / hotkey / auto
        self.auto_interval = 0.5
        self.last_screen_hash = None
        self.click_cooldown = 1.0
        self.last_click_time = 0
        self.instant_click = True  # 瞬間點擊模式

        # GUI
        self.root = None
        self.panel_visible = True

        # 托盤
        self.icon = None

        self.setup_gui()
        self.setup_tray()
        self.setup_hotkey()

    def setup_gui(self):
        """建立主面板"""
        self.root = tk.Tk()
        self.root.title("PyClick 智能點擊器")
        self.root.geometry("850x650")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # === 上方控制區 ===
        ctrl_frame = ttk.LabelFrame(self.root, text="控制")
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        # 第一排：操作流程
        row1 = ttk.Frame(ctrl_frame)
        row1.pack(fill="x", padx=10, pady=5)

        # 左側：準備步驟
        ttk.Label(row1, text="步驟:").pack(side="left", padx=(0, 5))
        ttk.Button(row1, text="1. 截圖", command=self.take_screenshot, width=10).pack(side="left", padx=2)
        ttk.Button(row1, text="2. 偵測藍色", command=self.detect_blue, width=12).pack(side="left", padx=2)
        ttk.Label(row1, text="→ 拖曳框選 →").pack(side="left", padx=5)

        # 重點：儲存按鈕（用醒目的 tk.Button）
        self.save_btn = tk.Button(row1, text="★ 3. 儲存選取 ★", command=self.save_template,
                                   width=14, height=1, bg="#4CAF50", fg="white",
                                   font=("", 10, "bold"), relief="raised", cursor="hand2")
        self.save_btn.pack(side="left", padx=10)

        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(row1, text="🎯 測試找圖", command=self.test_find, width=12).pack(side="left", padx=5)

        # 第二排：模式控制
        row2 = ttk.Frame(ctrl_frame)
        row2.pack(fill="x", padx=10, pady=5)

        ttk.Label(row2, text="模式:").pack(side="left", padx=5)

        self.mode_var = tk.StringVar(value="off")
        ttk.Radiobutton(row2, text="關閉", variable=self.mode_var, value="off",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(row2, text="熱鍵 (F6)", variable=self.mode_var, value="hotkey",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(row2, text="🔥 自動點擊", variable=self.mode_var, value="auto",
                        command=self.on_mode_change).pack(side="left", padx=5)

        ttk.Separator(row2, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Label(row2, text="掃描間隔:").pack(side="left", padx=5)
        self.interval_var = tk.StringVar(value="0.5")
        interval_combo = ttk.Combobox(row2, textvariable=self.interval_var, width=8, state="readonly",
                                       values=["0.3", "0.5", "1.0", "2.0"])
        interval_combo.pack(side="left", padx=5)
        interval_combo.bind("<<ComboboxSelected>>", self.on_interval_change)
        ttk.Label(row2, text="秒").pack(side="left")

        ttk.Separator(row2, orient="vertical").pack(side="left", fill="y", padx=10)

        # 點擊速度選項
        self.instant_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="瞬間點擊", variable=self.instant_var,
                        command=self.on_instant_change).pack(side="left", padx=5)

        ttk.Button(row2, text="縮小到托盤", command=self.hide_to_tray).pack(side="right", padx=10)

        # === 預覽區 ===
        preview_frame = ttk.LabelFrame(self.root, text="預覽 (拖曳框選目標)")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(preview_frame, bg="#333", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        # === 底部狀態 ===
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(bottom_frame, text="模板:").pack(side="left")
        self.template_info = ttk.Label(bottom_frame, text="(未設定)", foreground="gray")
        self.template_info.pack(side="left", padx=5)

        self.template_preview = ttk.Label(bottom_frame, background="#333")
        self.template_preview.pack(side="left", padx=10)

        self.status_var = tk.StringVar(value="按「截圖」開始")
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(side="right", padx=10)

        # 狀態
        self.screenshot = None
        self.selection = None
        self.scale = 1.0
        self.img_x = 0
        self.img_y = 0
        self.drag_start = None
        self.drag_rect = None

    def create_icon_image(self):
        """建立托盤圖示"""
        img = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(img)

        if self.mode == "auto":
            draw.ellipse([8, 8, 56, 56], fill='#4CAF50', outline='#2E7D32', width=3)
            draw.text((23, 18), "A", fill='white')
        elif self.mode == "hotkey":
            draw.ellipse([8, 8, 56, 56], fill='#FF9800', outline='#F57C00', width=3)
            draw.text((23, 18), "H", fill='white')
        else:
            draw.ellipse([8, 8, 56, 56], fill='#2196F3', outline='#1976D2', width=3)
            if self.template is None:
                draw.text((24, 18), "?", fill='white')
            else:
                draw.text((23, 18), "O", fill='white')

        return img

    def setup_tray(self):
        """設定系統托盤"""
        menu = pystray.Menu(
            Item('顯示面板', self.show_panel),
            Item('─────────', None, enabled=False),
            Item('🔥 自動模式', self.set_auto_mode,
                 checked=lambda item: self.mode == "auto",
                 enabled=lambda item: self.template is not None),
            Item('⌨ 熱鍵模式', self.set_hotkey_mode,
                 checked=lambda item: self.mode == "hotkey",
                 enabled=lambda item: self.template is not None),
            Item('⏸ 關閉', self.set_off_mode,
                 checked=lambda item: self.mode == "off"),
            Item('─────────', None, enabled=False),
            Item('❌ 結束程式', self.quit_app)
        )

        self.icon = pystray.Icon(
            "PyClick",
            self.create_icon_image(),
            "PyClick - 雙擊顯示面板",
            menu
        )

    def setup_hotkey(self):
        """設定熱鍵"""
        keyboard.add_hotkey(self.hotkey, self.on_hotkey)

    def update_icon(self):
        """更新托盤圖示"""
        if self.icon:
            self.icon.icon = self.create_icon_image()
            if self.mode == "auto":
                self.icon.title = f"PyClick - 自動模式 ({self.auto_interval}s)"
            elif self.mode == "hotkey":
                self.icon.title = "PyClick - 按 F6 點擊"
            elif self.template is not None:
                self.icon.title = "PyClick - 已設定模板"
            else:
                self.icon.title = "PyClick - 雙擊顯示面板"

    def show_panel(self, icon=None, item=None):
        """顯示主面板"""
        self.root.after(0, self._show_panel)

    def _show_panel(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.panel_visible = True

    def hide_to_tray(self):
        """隱藏到托盤"""
        self.root.withdraw()
        self.panel_visible = False

    def on_mode_change(self):
        """模式改變"""
        new_mode = self.mode_var.get()
        if new_mode in ["hotkey", "auto"] and self.template is None:
            self.status_var.set("請先儲存模板！")
            self.mode_var.set("off")
            return

        self.mode = new_mode
        self.update_icon()

        if self.mode == "auto":
            self.start_auto_thread()
            self.status_var.set(f"自動模式開啟 (每 {self.auto_interval} 秒掃描)")
        elif self.mode == "hotkey":
            self.status_var.set("熱鍵模式：按 F6 找圖點擊")
        else:
            self.status_var.set("已關閉")

    def on_interval_change(self, event=None):
        """間隔改變"""
        self.auto_interval = float(self.interval_var.get())
        self.update_icon()
        if self.mode == "auto":
            self.status_var.set(f"自動模式 (每 {self.auto_interval} 秒掃描)")

    def on_instant_change(self):
        """點擊速度改變"""
        self.instant_click = self.instant_var.get()
        mode_text = "瞬間" if self.instant_click else "穩定"
        self.status_var.set(f"點擊模式: {mode_text}")

    def set_auto_mode(self, icon=None, item=None):
        if self.template is None:
            return
        self.mode = "auto"
        self.mode_var.set("auto")
        self.update_icon()
        self.start_auto_thread()

    def set_hotkey_mode(self, icon=None, item=None):
        if self.template is None:
            return
        self.mode = "hotkey"
        self.mode_var.set("hotkey")
        self.update_icon()

    def set_off_mode(self, icon=None, item=None):
        self.mode = "off"
        self.mode_var.set("off")
        self.update_icon()

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
        self.status_var.set(f"截圖完成 {self.screenshot.shape[1]}x{self.screenshot.shape[0]} - 拖曳框選目標")

    def detect_blue(self):
        """偵測藍色"""
        if self.screenshot is None:
            self.status_var.set("請先截圖！")
            return

        hsv = cv2.cvtColor(self.screenshot, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([100, 100, 50]), np.array([130, 255, 255]))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        preview = self.screenshot.copy()
        count = 0
        for c in contours:
            if cv2.contourArea(c) < 100:
                continue
            count += 1
            cv2.drawContours(preview, [c], -1, (0, 255, 0), 2)
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 255, 255), 1)

        self.show_preview(preview)
        self.status_var.set(f"找到 {count} 個藍色區域 - 拖曳框選目標")

    def show_preview(self, img):
        """顯示預覽"""
        self.root.update()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10:
            cw, ch = 830, 400

        h, w = img.shape[:2]
        self.scale = min(cw / w, ch / h, 1.0)
        nw, nh = int(w * self.scale), int(h * self.scale)

        resized = cv2.resize(img, (nw, nh))

        # 畫選取框
        if self.selection:
            x1, y1, x2, y2 = self.selection
            sx1, sy1 = int(x1 * self.scale), int(y1 * self.scale)
            sx2, sy2 = int(x2 * self.scale), int(y2 * self.scale)
            cv2.rectangle(resized, (sx1, sy1), (sx2, sy2), (0, 0, 255), 2)

        resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(resized))

        self.canvas.delete("all")
        self.img_x = (cw - nw) // 2
        self.img_y = (ch - nh) // 2
        self.canvas.create_image(self.img_x, self.img_y, anchor="nw", image=self.photo)

    def on_drag_start(self, event):
        if self.screenshot is None:
            return
        self.drag_start = (event.x, event.y)

    def on_drag_move(self, event):
        if self.drag_start is None:
            return
        if self.drag_rect:
            self.canvas.delete(self.drag_rect)
        self.drag_rect = self.canvas.create_rectangle(
            self.drag_start[0], self.drag_start[1], event.x, event.y,
            outline="red", width=2, dash=(4, 4)
        )

    def on_drag_end(self, event):
        if self.drag_start is None or self.screenshot is None:
            return

        x1, y1 = self.drag_start
        x2, y2 = event.x, event.y

        ix1 = int((min(x1, x2) - self.img_x) / self.scale)
        iy1 = int((min(y1, y2) - self.img_y) / self.scale)
        ix2 = int((max(x1, x2) - self.img_x) / self.scale)
        iy2 = int((max(y1, y2) - self.img_y) / self.scale)

        h, w = self.screenshot.shape[:2]
        ix1, ix2 = max(0, ix1), min(w, ix2)
        iy1, iy2 = max(0, iy1), min(h, iy2)

        if ix2 - ix1 < 10 or iy2 - iy1 < 10:
            self.status_var.set("選取範圍太小！")
            self.drag_start = None
            return

        self.selection = (ix1, iy1, ix2, iy2)
        self.show_preview(self.screenshot)
        self.status_var.set(f"已選取 {ix2-ix1}x{iy2-iy1}，按「儲存選取」確認")
        self.drag_start = None

    def save_template(self):
        """儲存模板"""
        if self.selection is None:
            self.status_var.set("請先拖曳框選目標！")
            return

        x1, y1, x2, y2 = self.selection
        self.template = self.screenshot[y1:y2, x1:x2].copy()
        self.last_screen_hash = None

        # 顯示模板縮圖
        h, w = self.template.shape[:2]
        scale = min(60/w, 40/h, 1.0)
        thumb = cv2.resize(self.template, (int(w*scale), int(h*scale)))
        thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
        self.template_photo = ImageTk.PhotoImage(Image.fromarray(thumb))
        self.template_preview.config(image=self.template_photo)
        self.template_info.config(text=f"{w}x{h} px", foreground="green")

        self.update_icon()
        self.status_var.set("模板已儲存！選擇模式開始使用")

    def test_find(self):
        """測試找圖"""
        if self.template is None:
            self.status_var.set("請先儲存模板！")
            return

        self.status_var.set("測試找圖中...")
        self.root.update()

        self.root.iconify()
        self.root.update()
        time.sleep(0.3)

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            screen = np.array(sct.grab(monitor))
            screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)

        self.root.deiconify()

        result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        th, tw = self.template.shape[:2]
        preview = screen.copy()

        if max_val >= 0.7:
            cv2.rectangle(preview, max_loc, (max_loc[0]+tw, max_loc[1]+th), (0, 255, 0), 3)
            cx, cy = max_loc[0] + tw//2, max_loc[1] + th//2
            cv2.circle(preview, (cx, cy), 10, (0, 0, 255), -1)
            self.status_var.set(f"找到！位置 ({cx}, {cy}) 相似度 {max_val:.0%}")
        else:
            self.status_var.set(f"找不到 (最高相似度 {max_val:.0%})")

        self.screenshot = screen
        self.selection = None
        self.show_preview(preview)

    def start_auto_thread(self):
        """啟動自動執行緒"""
        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()

    def _auto_loop(self):
        """自動偵測（不搶焦點）"""
        while self.running and self.mode == "auto":
            try:
                if time.time() - self.last_click_time < self.click_cooldown:
                    time.sleep(0.1)
                    continue

                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    screen = np.array(sct.grab(monitor))
                    screen_bgr = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                    ox, oy = monitor["left"], monitor["top"]

                # Hash 比對
                small = cv2.resize(screen_bgr, (160, 90))
                screen_hash = hashlib.md5(small.tobytes()).hexdigest()

                if screen_hash == self.last_screen_hash:
                    time.sleep(self.auto_interval)
                    continue

                self.last_screen_hash = screen_hash

                # 模板匹配
                result = cv2.matchTemplate(screen_bgr, self.template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= 0.7:
                    th, tw = self.template.shape[:2]
                    cx = max_loc[0] + tw // 2 + ox
                    cy = max_loc[1] + th // 2 + oy

                    # 使用不搶焦點的點擊
                    click_no_focus(cx, cy, self.instant_click)

                    self.last_click_time = time.time()
                    self.last_screen_hash = None

                time.sleep(self.auto_interval)

            except Exception:
                time.sleep(self.auto_interval)

    def on_hotkey(self):
        """熱鍵觸發"""
        if self.mode != "hotkey" or self.template is None:
            return
        threading.Thread(target=self.find_and_click, daemon=True).start()

    def find_and_click(self):
        """手動找圖點擊"""
        try:
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

            click_no_focus(cx, cy, self.instant_click)

        except Exception:
            pass

    def quit_app(self, icon=None, item=None):
        """結束"""
        self.running = False
        self.mode = "off"
        keyboard.unhook_all()
        if self.icon:
            self.icon.stop()
        self.root.quit()

    def run(self):
        """啟動"""
        # 托盤在背景執行
        tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        tray_thread.start()

        # 主視窗
        self.root.mainloop()


if __name__ == "__main__":
    app = TrayClicker()
    app.run()
