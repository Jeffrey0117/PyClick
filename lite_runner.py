#!/usr/bin/env python3
"""
PyClick Lite Runner - 精簡執行引擎
用於導出的獨立 EXE 執行腳本
"""

import sys
import os
import json
import base64
import zlib
import time
import threading
import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
import mss
import pyautogui
import pystray
from pystray import MenuItem as Item
from PIL import Image, ImageDraw
import ctypes
import winsound

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


# ============================================================
# 加密/解密工具
# ============================================================

def decode_config(encoded_data):
    """解密設定"""
    try:
        if isinstance(encoded_data, str):
            encoded_data = encoded_data.encode()
        # 移除鹽值並反轉
        cleaned = encoded_data[:-5][::-1]
        compressed = base64.b64decode(cleaned)
        json_str = zlib.decompress(compressed).decode()
        return json.loads(json_str)
    except Exception as e:
        print(f"解密失敗: {e}")
        return None


def encode_config(config_dict):
    """加密設定（導出時使用）"""
    json_str = json.dumps(config_dict, ensure_ascii=False)
    compressed = zlib.compress(json_str.encode())
    encoded = base64.b64encode(compressed)
    # 簡單混淆：反轉 + 加鹽
    return (encoded[::-1] + b"_PYC_").decode()


def decode_image(encoded_data):
    """解碼圖片（Base64 → numpy array）"""
    try:
        if isinstance(encoded_data, str):
            encoded_data = encoded_data.encode()
        img_data = base64.b64decode(encoded_data)
        nparr = np.frombuffer(img_data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"圖片解碼失敗: {e}")
        return None


def encode_image(image_path):
    """編碼圖片（導出時使用）"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ============================================================
# 資源路徑處理
# ============================================================

def get_resource_path(relative_path):
    """取得資源路徑（支援 PyInstaller 打包）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)


# ============================================================
# 焦點控制
# ============================================================

def force_focus(hwnd):
    """強制恢復視窗焦點"""
    if not hwnd:
        return
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    if target_thread != current_thread:
        user32.AttachThreadInput(current_thread, target_thread, True)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    user32.SetActiveWindow(hwnd)
    if target_thread != current_thread:
        user32.AttachThreadInput(current_thread, target_thread, False)


# ============================================================
# 精簡執行引擎
# ============================================================

class LiteRunner:
    """精簡版執行引擎"""

    def __init__(self):
        self.config = None
        self.template = None
        self.running = True
        self.mode = "off"  # off / auto
        self.auto_interval = 0.5
        self.threshold = 0.7
        self.sound_enabled = True

        # 腳本參數
        self.click_count = 1
        self.click_interval = 0.1
        self.after_key = ""
        self.script_name = "PyClick Script"

        # 狀態
        self.last_click_time = 0
        self.click_cooldown = 1.0
        self.total_clicks = 0

        # UI
        self.root = None
        self.icon = None

        # 載入資源
        self._load_embedded_resources()

    def _load_embedded_resources(self):
        """載入內嵌資源"""
        # 嘗試從內嵌資料載入
        config_path = get_resource_path("config.dat")

        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                encrypted = f.read()
                self.config = decode_config(encrypted)

        if self.config:
            self.script_name = self.config.get("name", "PyClick Script")
            self.auto_interval = self.config.get("scan_interval", 0.5)
            self.threshold = self.config.get("threshold", 0.7)
            self.click_count = self.config.get("click_count", 1)
            self.click_interval = self.config.get("click_interval", 0.1)
            self.after_key = self.config.get("after_key", "")
            self.sound_enabled = self.config.get("sound_enabled", True)

            # 載入模板圖片
            template_data = self.config.get("template_data")
            if template_data:
                self.template = decode_image(template_data)

    def create_icon_image(self):
        """建立托盤圖示"""
        img = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(img)

        if self.mode == "auto":
            draw.ellipse([8, 8, 56, 56], fill='#4CAF50', outline='#2E7D32', width=3)
            draw.text((23, 18), "A", fill='white')
        else:
            draw.ellipse([8, 8, 56, 56], fill='#2196F3', outline='#1976D2', width=3)
            draw.text((23, 18), "S", fill='white')

        return img

    def setup_tray(self):
        """設定系統托盤"""
        menu = pystray.Menu(
            Item('開啟設定', self.show_settings),
            Item('─────────', None, enabled=False),
            Item('自動模式', self.toggle_auto,
                 checked=lambda item: self.mode == "auto"),
            Item('停用', self.set_off,
                 checked=lambda item: self.mode == "off"),
            Item('─────────', None, enabled=False),
            Item('結束程式', self.quit_app)
        )

        self.icon = pystray.Icon(
            self.script_name,
            self.create_icon_image(),
            f"{self.script_name} - 右鍵開啟選單",
            menu
        )

    def update_icon(self):
        """更新托盤圖示"""
        if self.icon:
            self.icon.icon = self.create_icon_image()
            status = "執行中" if self.mode == "auto" else "已停用"
            self.icon.title = f"{self.script_name} - {status}"

    def toggle_auto(self, icon=None, item=None):
        """切換自動模式"""
        if self.template is None:
            return

        if self.mode == "auto":
            self.mode = "off"
        else:
            self.mode = "auto"
            self.start_auto_thread()

        self.update_icon()

    def set_off(self, icon=None, item=None):
        """停用"""
        self.mode = "off"
        self.update_icon()

    def show_settings(self, icon=None, item=None):
        """顯示設定視窗"""
        if self.root and self.root.winfo_exists():
            self.root.lift()
            return

        self.root = tk.Tk()
        self.root.title(f"{self.script_name} 設定")
        self.root.geometry("350x400")
        self.root.resizable(False, False)

        # 標題
        tk.Label(
            self.root, text=self.script_name,
            font=("Microsoft JhengHei", 14, "bold")
        ).pack(pady=15)

        # 設定區
        settings_frame = ttk.LabelFrame(self.root, text="參數設定", padding=15)
        settings_frame.pack(fill="x", padx=20, pady=10)

        # 掃描間隔
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=5)
        ttk.Label(row1, text="掃描間隔:").pack(side="left")
        self.interval_var = tk.StringVar(value=str(self.auto_interval))
        ttk.Combobox(row1, textvariable=self.interval_var, width=8,
                     values=["0.3", "0.5", "1.0", "2.0"]).pack(side="right")
        ttk.Label(row1, text="秒").pack(side="right", padx=5)

        # 點擊次數
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=5)
        ttk.Label(row2, text="點擊次數:").pack(side="left")
        self.clicks_var = tk.StringVar(value=str(self.click_count))
        ttk.Combobox(row2, textvariable=self.clicks_var, width=8,
                     values=["1", "2", "3", "5", "10"]).pack(side="right")
        ttk.Label(row2, text="次").pack(side="right", padx=5)

        # 相似度
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill="x", pady=5)
        ttk.Label(row3, text="相似度門檻:").pack(side="left")
        self.threshold_var = tk.StringVar(value=str(int(self.threshold * 100)))
        ttk.Combobox(row3, textvariable=self.threshold_var, width=8,
                     values=["60", "70", "80", "90"]).pack(side="right")
        ttk.Label(row3, text="%").pack(side="right", padx=5)

        # 提示音
        row4 = ttk.Frame(settings_frame)
        row4.pack(fill="x", pady=5)
        self.sound_var = tk.BooleanVar(value=self.sound_enabled)
        ttk.Checkbutton(row4, text="執行前播放提示音",
                        variable=self.sound_var).pack(side="left")

        # 控制區
        control_frame = ttk.LabelFrame(self.root, text="控制", padding=15)
        control_frame.pack(fill="x", padx=20, pady=10)

        # 狀態顯示
        status_row = ttk.Frame(control_frame)
        status_row.pack(fill="x", pady=5)
        ttk.Label(status_row, text="狀態:").pack(side="left")
        self.status_label = tk.Label(
            status_row,
            text="已停止" if self.mode == "off" else "執行中",
            fg="#D32F2F" if self.mode == "off" else "#388E3C",
            font=("Microsoft JhengHei", 10, "bold")
        )
        self.status_label.pack(side="right")

        # 開始/停止按鈕
        control_btn_frame = ttk.Frame(control_frame)
        control_btn_frame.pack(fill="x", pady=10)

        self.start_btn = tk.Button(
            control_btn_frame, text="▶ 開始",
            command=self._start_from_ui, width=10,
            bg="#4CAF50", fg="white", activebackground="#388E3C",
            font=("Microsoft JhengHei", 9, "bold"), relief="flat"
        )
        self.start_btn.pack(side="left", padx=5, expand=True)

        self.stop_btn = tk.Button(
            control_btn_frame, text="■ 停止",
            command=self._stop_from_ui, width=10,
            bg="#F44336", fg="white", activebackground="#D32F2F",
            font=("Microsoft JhengHei", 9, "bold"), relief="flat"
        )
        self.stop_btn.pack(side="left", padx=5, expand=True)

        self._update_control_buttons()

        # 統計
        stats_frame = ttk.LabelFrame(self.root, text="統計", padding=15)
        stats_frame.pack(fill="x", padx=20, pady=10)

        self.stats_label = tk.Label(
            stats_frame, text=f"已點擊: {self.total_clicks} 次",
            font=("", 12)
        )
        self.stats_label.pack()

        # 按鈕
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="套用設定", command=self._apply_settings,
                   width=10).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="關閉", command=self.root.destroy,
                   width=10).pack(side="left", padx=10)

        self.root.mainloop()

    def _apply_settings(self):
        """套用設定"""
        try:
            self.auto_interval = float(self.interval_var.get())
            self.click_count = int(self.clicks_var.get())
            self.threshold = int(self.threshold_var.get()) / 100
            self.sound_enabled = self.sound_var.get()
        except ValueError:
            pass

    def _update_control_buttons(self):
        """更新控制按鈕狀態"""
        if self.mode == "auto":
            self.start_btn.config(state="disabled", bg="#A5D6A7")
            self.stop_btn.config(state="normal", bg="#F44336")
            self.status_label.config(text="執行中", fg="#388E3C")
        else:
            self.start_btn.config(state="normal", bg="#4CAF50")
            self.stop_btn.config(state="disabled", bg="#EF9A9A")
            self.status_label.config(text="已停止", fg="#D32F2F")

    def _start_from_ui(self):
        """從 UI 啟動自動模式"""
        if self.template is None:
            return
        self.mode = "auto"
        self.start_auto_thread()
        self.update_icon()
        self._update_control_buttons()
        self._start_stats_update()

    def _stop_from_ui(self):
        """從 UI 停止自動模式"""
        self.mode = "off"
        self.update_icon()
        self._update_control_buttons()

    def _start_stats_update(self):
        """啟動統計更新"""
        def update():
            if self.root and self.root.winfo_exists():
                if hasattr(self, 'stats_label'):
                    self.stats_label.config(text=f"已點擊: {self.total_clicks} 次")
                if self.mode == "auto":
                    self.root.after(1000, update)
        update()

    def start_auto_thread(self):
        """啟動自動執行緒"""
        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()

    def _execute_action(self, cx, cy):
        """執行點擊動作"""
        # 播放提示音（非同步）
        if self.sound_enabled:
            threading.Thread(target=lambda: winsound.Beep(1000, 100), daemon=True).start()

        # 保存狀態
        original_pos = pyautogui.position()
        original_hwnd = user32.GetForegroundWindow()

        # 移動並點擊
        user32.SetCursorPos(cx, cy)
        time.sleep(0.02)

        for i in range(self.click_count):
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            if i < self.click_count - 1:
                time.sleep(self.click_interval)

        # 按鍵
        if self.after_key:
            time.sleep(0.1)
            pyautogui.press(self.after_key.lower())

        # 恢復
        user32.SetCursorPos(original_pos[0], original_pos[1])
        force_focus(original_hwnd)

        self.total_clicks += self.click_count

    def _auto_loop(self):
        """自動偵測迴圈"""
        while self.running and self.mode == "auto":
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    screen = np.array(sct.grab(monitor))
                    screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                    ox, oy = monitor["left"], monitor["top"]

                # 模板匹配
                result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= self.threshold:
                    # 冷卻檢查
                    if time.time() - self.last_click_time >= self.click_cooldown:
                        th, tw = self.template.shape[:2]
                        cx = max_loc[0] + tw // 2 + ox
                        cy = max_loc[1] + th // 2 + oy

                        self._execute_action(cx, cy)
                        self.last_click_time = time.time()

                time.sleep(self.auto_interval)

            except Exception as e:
                print(f"錯誤: {e}")
                time.sleep(self.auto_interval)

    def quit_app(self, icon=None, item=None):
        """結束程式"""
        self.running = False
        self.mode = "off"
        if self.icon:
            self.icon.stop()
        if self.root:
            try:
                self.root.quit()
            except:
                pass

    def run(self):
        """啟動"""
        if self.template is None:
            print("錯誤：找不到模板圖片")
            return

        self.setup_tray()
        self.icon.run()


# ============================================================
# 主程式
# ============================================================

if __name__ == "__main__":
    runner = LiteRunner()
    runner.run()
