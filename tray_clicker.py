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
import os
import json
import winsound


# ============================================================
# 簡單腳本資料結構
# ============================================================

class SimpleScript:
    """簡單腳本：一個圖 + 一組動作"""

    def __init__(self, name="未命名"):
        self.name = name
        self.template_path = ""      # 模板圖片路徑
        self.click_count = 1         # 點擊次數
        self.click_interval = 0.1    # 點擊間隔（秒）
        self.after_key = ""          # 點完後按的鍵（空=不按）

    def to_dict(self):
        return {
            "name": self.name,
            "template_path": self.template_path,
            "click_count": self.click_count,
            "click_interval": self.click_interval,
            "after_key": self.after_key,
        }

    @classmethod
    def from_dict(cls, data):
        script = cls(data.get("name", "未命名"))
        script.template_path = data.get("template_path", "")
        script.click_count = data.get("click_count", 1)
        script.click_interval = data.get("click_interval", 0.1)
        script.after_key = data.get("after_key", "")
        return script

    def save(self, filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

pyautogui.FAILSAFE = True

# Windows API for click without focus change
user32 = ctypes.windll.user32

# 單一實例鎖
def check_single_instance():
    """確保只有一個實例運行"""
    mutex_name = "PyClick_SingleInstance_Mutex"
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    return True
kernel32 = ctypes.windll.kernel32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def force_focus(hwnd):
    """強制恢復視窗焦點（繞過 Windows 限制）"""
    if not hwnd:
        return

    # 取得目標視窗的執行緒 ID
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    # 取得當前執行緒 ID
    current_thread = kernel32.GetCurrentThreadId()

    # 附加到目標執行緒（這樣才能設定焦點）
    if target_thread != current_thread:
        user32.AttachThreadInput(current_thread, target_thread, True)

    # 恢復焦點
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    user32.SetActiveWindow(hwnd)

    # 解除附加
    if target_thread != current_thread:
        user32.AttachThreadInput(current_thread, target_thread, False)


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

    # 強制恢復前景視窗焦點
    force_focus(foreground_hwnd)


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
        self.continuous_click = False  # 連續點擊模式
        self.total_clicks = 0  # 總點擊計數器

        # 簡單腳本
        self.current_script = SimpleScript()
        self.scripts_dir = os.path.join(os.path.dirname(__file__), "simple_scripts")
        os.makedirs(self.scripts_dir, exist_ok=True)

        # 執行緒鎖
        self._lock = threading.Lock()

        # 音效提示
        self.sound_enabled = True

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

        # 第零排：腳本選擇
        row0 = ttk.Frame(ctrl_frame)
        row0.pack(fill="x", padx=10, pady=5)

        ttk.Label(row0, text="腳本:").pack(side="left", padx=(0, 5))
        self.script_var = tk.StringVar(value="(新腳本)")
        self.script_combo = ttk.Combobox(row0, textvariable=self.script_var, width=20, state="readonly")
        self.script_combo.pack(side="left", padx=2)
        self.script_combo.bind("<<ComboboxSelected>>", self.on_script_select)
        self._refresh_script_list()

        ttk.Button(row0, text="💾 儲存", command=self.save_script, width=8).pack(side="left", padx=2)
        ttk.Button(row0, text="📝 另存", command=self.save_script_as, width=8).pack(side="left", padx=2)
        ttk.Button(row0, text="⭐ 預設", command=self.set_default_script, width=8).pack(side="left", padx=2)
        ttk.Button(row0, text="🗑 刪除", command=self.delete_script, width=8).pack(side="left", padx=2)

        ttk.Separator(row0, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(row0, text="📜 進階編輯", command=self.open_block_editor, width=12).pack(side="left", padx=5)

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

        # 第二排：動作設定
        row2 = ttk.Frame(ctrl_frame)
        row2.pack(fill="x", padx=10, pady=5)

        ttk.Label(row2, text="動作:").pack(side="left", padx=5)

        ttk.Label(row2, text="點擊").pack(side="left", padx=(5, 2))
        self.click_count_var = tk.StringVar(value="1")
        click_count_combo = ttk.Combobox(row2, textvariable=self.click_count_var, width=4,
                                          values=["1", "2", "3", "4", "5", "10"])
        click_count_combo.pack(side="left", padx=2)
        click_count_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        click_count_combo.bind("<FocusOut>", self.on_action_change)
        ttk.Label(row2, text="次").pack(side="left", padx=(2, 10))

        ttk.Label(row2, text="間隔:").pack(side="left", padx=5)
        self.click_interval_var = tk.StringVar(value="0.1")
        interval_combo = ttk.Combobox(row2, textvariable=self.click_interval_var, width=6,
                                       values=["0.05", "0.1", "0.15", "0.2", "0.3", "0.5", "1.0"])
        interval_combo.pack(side="left", padx=2)
        interval_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        interval_combo.bind("<FocusOut>", self.on_action_change)
        ttk.Label(row2, text="秒").pack(side="left", padx=(2, 10))

        ttk.Label(row2, text="然後按:").pack(side="left", padx=5)
        self.after_key_var = tk.StringVar(value="")
        after_key_combo = ttk.Combobox(row2, textvariable=self.after_key_var, width=8,
                                        values=["", "Enter", "Tab", "Space", "Escape", "Up", "Down", "Left", "Right"])
        after_key_combo.pack(side="left", padx=2)
        after_key_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        after_key_combo.bind("<FocusOut>", self.on_action_change)

        ttk.Button(row2, text="縮小到托盤", command=self.hide_to_tray).pack(side="right", padx=10)

        # 第三排：模式控制
        row3 = ttk.Frame(ctrl_frame)
        row3.pack(fill="x", padx=10, pady=5)

        ttk.Label(row3, text="模式:").pack(side="left", padx=5)

        self.mode_var = tk.StringVar(value="off")
        ttk.Radiobutton(row3, text="停用", variable=self.mode_var, value="off",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(row3, text="熱鍵 (F6)", variable=self.mode_var, value="hotkey",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(row3, text="🔥 自動點擊", variable=self.mode_var, value="auto",
                        command=self.on_mode_change).pack(side="left", padx=5)

        ttk.Separator(row3, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Label(row3, text="掃描間隔:").pack(side="left", padx=5)
        self.interval_var = tk.StringVar(value="0.5")
        scan_interval_combo = ttk.Combobox(row3, textvariable=self.interval_var, width=8, state="readonly",
                                            values=["0.3", "0.5", "1.0", "2.0"])
        scan_interval_combo.pack(side="left", padx=5)
        scan_interval_combo.bind("<<ComboboxSelected>>", self.on_interval_change)
        ttk.Label(row3, text="秒").pack(side="left")

        ttk.Separator(row3, orient="vertical").pack(side="left", fill="y", padx=10)

        # 點擊速度選項
        self.instant_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="瞬間點擊", variable=self.instant_var,
                        command=self.on_instant_change).pack(side="left", padx=5)

        # === 預覽區 ===
        preview_frame = ttk.LabelFrame(self.root, text="預覽 (拖曳框選目標)")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 提示文字
        tip_frame = ttk.Frame(preview_frame)
        tip_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(tip_frame, text="💡 選取範圍適中即可，太小易誤判、太大會變慢",
                  foreground="gray", font=("", 9)).pack(side="left")
        ttk.Label(tip_frame, text="🖱 滾輪縮放 | Alt+拖曳移動", foreground="#666", font=("", 9)).pack(side="right")

        self.canvas = tk.Canvas(preview_frame, bg="#333", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows 滾輪
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)    # Linux 滾輪上
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)    # Linux 滾輪下

        # Alt+拖曳移動圖片
        self.canvas.bind("<Alt-ButtonPress-1>", self.on_pan_start)
        self.canvas.bind("<Alt-B1-Motion>", self.on_pan_move)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)  # 中鍵也可以
        self.canvas.bind("<B2-Motion>", self.on_pan_move)

        self.zoom_level = 1.0  # 縮放等級
        self.pan_offset = [0, 0]  # 平移偏移
        self.pan_start = None

        # === 底部狀態 ===
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        # 左側：模板狀態（純文字，不顯示圖片）
        ttk.Label(bottom_frame, text="模板:").pack(side="left")
        self.template_info = ttk.Label(bottom_frame, text="(未設定)", foreground="gray")
        self.template_info.pack(side="left", padx=5)

        # 連續點擊選項
        ttk.Separator(bottom_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        self.continuous_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom_frame, text="連續點擊", variable=self.continuous_var,
                        command=self.on_continuous_change).pack(side="left", padx=5)

        # 音效提示選項
        self.sound_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom_frame, text="提示音", variable=self.sound_var,
                        command=self.on_sound_change).pack(side="left", padx=5)

        # 右側：設定按鈕 + 計數
        self.total_clicks_var = tk.StringVar(value="0")
        count_btn = tk.Button(bottom_frame, textvariable=self.total_clicks_var, width=6,
                               bg="#222", fg="#4CAF50", font=("Consolas", 12, "bold"),
                               relief="flat", cursor="hand2", command=self.show_settings)
        count_btn.pack(side="right", padx=5)
        ttk.Label(bottom_frame, text="次 |", foreground="gray").pack(side="right")

        ttk.Button(bottom_frame, text="⚙ 設定", command=self.show_settings, width=8).pack(side="right", padx=5)

        # 狀態
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
            Item('⏸ 停用', self.set_off_mode,
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
            self.status_var.set(f"自動模式開啟 - 視窗將縮小")
            # 自動縮小避免點到自己
            self.root.after(500, self.hide_to_tray)
        elif self.mode == "hotkey":
            self.status_var.set("熱鍵模式：按 F6 找圖點擊")
        else:
            self.status_var.set("已停用")

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

    def on_continuous_change(self):
        """連續點擊改變"""
        self.continuous_click = self.continuous_var.get()
        if self.continuous_click:
            self.status_var.set("連續點擊: 開啟（找到就連點）")
        else:
            self.status_var.set("連續點擊: 關閉")

    def on_sound_change(self):
        """音效提示改變"""
        self.sound_enabled = self.sound_var.get()
        if self.sound_enabled:
            winsound.Beep(1000, 50)  # 播放示範音
            self.status_var.set("提示音: 開啟")
        else:
            self.status_var.set("提示音: 關閉")

    def on_action_change(self, event=None):
        """動作設定改變，更新當前腳本"""
        try:
            self.current_script.click_count = int(self.click_count_var.get())
        except ValueError:
            self.current_script.click_count = 1

        try:
            self.current_script.click_interval = float(self.click_interval_var.get())
        except ValueError:
            self.current_script.click_interval = 0.1

        self.current_script.after_key = self.after_key_var.get()

        action_desc = f"點{self.current_script.click_count}下"
        if self.current_script.after_key:
            action_desc += f" → {self.current_script.after_key}"

        # 提示用戶儲存
        if self.current_script.name and self.current_script.name != "未命名":
            self.status_var.set(f"動作: {action_desc}  ⚠ 記得按「儲存」")
        else:
            self.status_var.set(f"動作: {action_desc}  ⚠ 記得按「另存」")

    # ============================================================
    # 腳本管理
    # ============================================================

    def _refresh_script_list(self):
        """刷新腳本下拉列表"""
        scripts = ["(新腳本)"]
        if os.path.exists(self.scripts_dir):
            for f in os.listdir(self.scripts_dir):
                if f.endswith(".json"):
                    scripts.append(f[:-5])
        self.script_combo["values"] = scripts

    def on_script_select(self, event=None):
        """選擇腳本"""
        name = self.script_var.get()
        if name == "(新腳本)":
            self.current_script = SimpleScript()
            self.template = None
            self._update_ui_from_script()
            self.status_var.set("新腳本")
            return

        filepath = os.path.join(self.scripts_dir, f"{name}.json")
        if os.path.exists(filepath):
            self.current_script = SimpleScript.load(filepath)
            self._load_template_from_script()
            self._update_ui_from_script()
            self.status_var.set(f"已載入: {name}")
            self._show_toast(f"已載入腳本: {name}")

    def _show_toast(self, message, duration=1500):
        """顯示自動消失的通知"""
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)  # 無邊框
        toast.attributes("-topmost", True)

        # 置中於主視窗上方
        toast.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 250) // 2
        y = self.root.winfo_y() + 50
        toast.geometry(f"250x40+{x}+{y}")

        # 樣式
        frame = tk.Frame(toast, bg="#2E7D32", padx=15, pady=8)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=message, bg="#2E7D32", fg="white",
                 font=("Microsoft JhengHei", 10, "bold")).pack()

        # 自動消失
        toast.after(duration, toast.destroy)

    def _update_ui_from_script(self):
        """從腳本更新 UI"""
        self.click_count_var.set(str(self.current_script.click_count))
        self.click_interval_var.set(str(self.current_script.click_interval))
        self.after_key_var.set(self.current_script.after_key)

        # 更新模板資訊
        if self.template is not None:
            h, w = self.template.shape[:2]
            name = os.path.basename(self.current_script.template_path)
            self.template_info.config(text=f"{name} ({w}x{h})", foreground="green")
        else:
            self.template_info.config(text="(未設定)", foreground="gray")

        self.update_icon()

    def _load_template_from_script(self):
        """從腳本載入模板圖片"""
        if self.current_script.template_path and os.path.exists(self.current_script.template_path):
            self.template = cv2.imread(self.current_script.template_path)
        else:
            self.template = None

    def save_script(self):
        """儲存當前腳本"""
        if not self.current_script.name or self.current_script.name == "未命名":
            self.save_script_as()
            return

        filepath = os.path.join(self.scripts_dir, f"{self.current_script.name}.json")
        self.current_script.save(filepath)
        self._refresh_script_list()
        self.script_var.set(self.current_script.name)
        self.status_var.set(f"已儲存: {self.current_script.name}")

    def save_script_as(self):
        """另存腳本"""
        from tkinter import simpledialog
        name = simpledialog.askstring("儲存腳本", "腳本名稱:", parent=self.root)
        if not name:
            return

        self.current_script.name = name
        filepath = os.path.join(self.scripts_dir, f"{name}.json")
        self.current_script.save(filepath)
        self._refresh_script_list()
        self.script_var.set(name)
        self.status_var.set(f"已儲存: {name}")

    def delete_script(self):
        """刪除腳本"""
        from tkinter import messagebox
        name = self.script_var.get()
        if name == "(新腳本)":
            return

        if not messagebox.askyesno("確認刪除", f"確定要刪除「{name}」嗎？"):
            return

        filepath = os.path.join(self.scripts_dir, f"{name}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

        self._refresh_script_list()
        self.script_var.set("(新腳本)")
        self.current_script = SimpleScript()
        self.template = None
        self._update_ui_from_script()
        self.status_var.set(f"已刪除: {name}")

    def set_default_script(self):
        """設定當前腳本為預設（啟動時自動選中）"""
        name = self.script_var.get()
        if name == "(新腳本)":
            self.status_var.set("請先儲存腳本")
            return

        config_path = os.path.join(os.path.dirname(__file__), "config.json")

        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

        config["default_script"] = name

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        self.status_var.set(f"已設為預設腳本: {name}")
        self._show_toast(f"⭐ {name} 設為預設")

    def increment_click_count(self, count=1):
        """增加點擊計數並更新 UI"""
        self.total_clicks += count
        self.root.after(0, self._update_counter_ui)

    def _update_counter_ui(self):
        """更新計數器 UI"""
        self.total_clicks_var.set(str(self.total_clicks))

    def show_settings(self):
        """顯示設定面板"""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("PyClick 設定")
        settings_win.geometry("500x600")
        settings_win.transient(self.root)
        settings_win.grab_set()

        notebook = ttk.Notebook(settings_win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # === 頁籤1：功績統計 ===
        stats_frame = ttk.Frame(notebook, padding=20)
        notebook.add(stats_frame, text="📊 功績")

        # 大數字顯示
        tk.Label(stats_frame, text="已幫你點擊", font=("", 14), fg="#666").pack(pady=(20, 5))
        tk.Label(stats_frame, text=str(self.total_clicks), font=("Consolas", 72, "bold"), fg="#4CAF50").pack()
        tk.Label(stats_frame, text="次", font=("", 14), fg="#666").pack(pady=(5, 30))

        # 統計資訊
        info_frame = ttk.LabelFrame(stats_frame, text="統計", padding=10)
        info_frame.pack(fill="x", pady=10)
        ttk.Label(info_frame, text=f"本次啟動點擊: {self.total_clicks} 次").pack(anchor="w")
        ttk.Label(info_frame, text=f"當前模式: {self.mode}").pack(anchor="w")
        ttk.Label(info_frame, text=f"掃描間隔: {self.auto_interval} 秒").pack(anchor="w")

        # === 頁籤2：模板管理 ===
        template_frame = ttk.Frame(notebook, padding=20)
        notebook.add(template_frame, text="📁 模板")

        ttk.Label(template_frame, text="已儲存的模板", font=("", 12, "bold")).pack(anchor="w", pady=(0, 10))

        # 模板列表
        list_frame = ttk.Frame(template_frame)
        list_frame.pack(fill="both", expand=True)

        self.template_listbox = tk.Listbox(list_frame, height=10, font=("", 10))
        self.template_listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.template_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.template_listbox.config(yscrollcommand=scrollbar.set)

        # 載入已儲存的模板
        self._load_template_list()

        # 按鈕
        btn_frame = ttk.Frame(template_frame)
        btn_frame.pack(fill="x", pady=10)

        ttk.Button(btn_frame, text="💾 儲存目前模板", command=self._save_current_template).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="📂 載入選中", command=self._load_selected_template).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="⭐ 設為預設", command=self._set_default_template).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🗑 刪除選中", command=self._delete_selected_template).pack(side="left", padx=5)

        # 當前模板預覽
        if self.template is not None:
            ttk.Label(template_frame, text="當前模板預覽:", font=("", 10)).pack(anchor="w", pady=(10, 5))
            h, w = self.template.shape[:2]
            scale = min(150/w, 100/h, 1.0)
            thumb = cv2.resize(self.template, (int(w*scale), int(h*scale)))
            thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(thumb))
            preview_label = ttk.Label(template_frame, image=photo)
            preview_label.image = photo
            preview_label.pack(anchor="w")

        # === 頁籤3：設定 ===
        config_frame = ttk.Frame(notebook, padding=20)
        notebook.add(config_frame, text="⚙ 設定")

        ttk.Label(config_frame, text="個人化設定", font=("", 12, "bold")).pack(anchor="w", pady=(0, 15))

        # 相似度門檻
        threshold_frame = ttk.Frame(config_frame)
        threshold_frame.pack(fill="x", pady=5)
        ttk.Label(threshold_frame, text="相似度門檻:").pack(side="left")
        ttk.Label(threshold_frame, text="70%（預設）", foreground="gray").pack(side="left", padx=10)

        # 點擊冷卻
        cooldown_frame = ttk.Frame(config_frame)
        cooldown_frame.pack(fill="x", pady=5)
        ttk.Label(cooldown_frame, text="點擊冷卻:").pack(side="left")
        ttk.Label(cooldown_frame, text=f"{self.click_cooldown} 秒", foreground="gray").pack(side="left", padx=10)

        # 熱鍵
        hotkey_frame = ttk.Frame(config_frame)
        hotkey_frame.pack(fill="x", pady=5)
        ttk.Label(hotkey_frame, text="觸發熱鍵:").pack(side="left")
        ttk.Label(hotkey_frame, text=self.hotkey, foreground="gray").pack(side="left", padx=10)

        ttk.Separator(config_frame, orient="horizontal").pack(fill="x", pady=20)

        ttk.Label(config_frame, text="更多設定即將推出...", foreground="gray").pack()

    def _load_template_list(self):
        """載入模板列表"""
        import os
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        if not os.path.exists(template_dir):
            os.makedirs(template_dir)

        self.template_listbox.delete(0, tk.END)
        for f in os.listdir(template_dir):
            if f.endswith(".png"):
                self.template_listbox.insert(tk.END, f[:-4])

    def _save_current_template(self):
        """儲存當前模板"""
        if self.template is None:
            return

        import os
        from tkinter import simpledialog

        name = simpledialog.askstring("儲存模板", "模板名稱:", parent=self.root)
        if not name:
            return

        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        if not os.path.exists(template_dir):
            os.makedirs(template_dir)

        filepath = os.path.join(template_dir, f"{name}.png")
        cv2.imwrite(filepath, self.template)
        self._load_template_list()
        self.status_var.set(f"模板已儲存: {name}")

    def _load_selected_template(self):
        """載入選中的模板"""
        import os
        selection = self.template_listbox.curselection()
        if not selection:
            return

        name = self.template_listbox.get(selection[0])
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        filepath = os.path.join(template_dir, f"{name}.png")

        self.template = cv2.imread(filepath)
        if self.template is not None:
            self.update_icon()
            h, w = self.template.shape[:2]
            self.template_info.config(text=f"{name} ({w}x{h})", foreground="green")
            self.status_var.set(f"已載入模板: {name}")

    def _delete_selected_template(self):
        """刪除選中的模板"""
        import os
        selection = self.template_listbox.curselection()
        if not selection:
            return

        name = self.template_listbox.get(selection[0])
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        filepath = os.path.join(template_dir, f"{name}.png")

        if os.path.exists(filepath):
            os.remove(filepath)
            self._load_template_list()
            self.status_var.set(f"已刪除: {name}")

    def _set_default_template(self):
        """設定選中的模板為預設"""
        import os
        import json

        selection = self.template_listbox.curselection()
        if not selection:
            self.status_var.set("請先選擇一個模板")
            return

        name = self.template_listbox.get(selection[0])
        config_path = os.path.join(os.path.dirname(__file__), "config.json")

        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

        config["default_template"] = name

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        self.status_var.set(f"已設為預設: {name}")

    def _check_default_script(self):
        """啟動時檢查並詢問要載入哪個腳本"""
        # 取得所有腳本
        scripts = []
        if os.path.exists(self.scripts_dir):
            for f in os.listdir(self.scripts_dir):
                if f.endswith(".json"):
                    scripts.append(f[:-5])

        if not scripts:
            return  # 沒有腳本就跳過

        # 檢查有沒有預設腳本
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        default_script = None
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                default_script = config.get("default_script")

        # 顯示選擇對話框
        self._show_script_select_dialog(scripts, default_script)

    def _show_script_select_dialog(self, scripts, default_script=None):
        """顯示腳本選擇對話框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("載入腳本")
        dialog.geometry("300x350")
        dialog.transient(self.root)
        dialog.grab_set()

        # 置中
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 350) // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="選擇要載入的腳本", font=("Microsoft JhengHei", 12, "bold")).pack(pady=15)

        # 列表
        list_frame = tk.Frame(dialog)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)

        listbox = tk.Listbox(list_frame, font=("", 11), selectmode="single")
        listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scrollbar.set)

        for s in scripts:
            listbox.insert(tk.END, s)
            if s == default_script:
                listbox.selection_set(tk.END)

        # 如果有預設就選中，沒有就選第一個
        if not listbox.curselection() and scripts:
            listbox.selection_set(0)

        def on_load():
            selection = listbox.curselection()
            if selection:
                name = listbox.get(selection[0])
                dialog.destroy()
                self.script_var.set(name)
                self.on_script_select()

        def on_skip():
            dialog.destroy()

        # 按鈕
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="載入", command=on_load, width=10,
                  bg="#4CAF50", fg="white", font=("", 10)).pack(side="left", padx=10)
        tk.Button(btn_frame, text="跳過", command=on_skip, width=10).pack(side="left", padx=10)

        # 雙擊載入
        listbox.bind("<Double-Button-1>", lambda e: on_load())

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
        self.zoom_level = 1.0  # 重置縮放
        self.pan_offset = [0, 0]  # 重置平移
        self.show_preview(self.screenshot)
        self.status_var.set(f"截圖完成 {self.screenshot.shape[1]}x{self.screenshot.shape[0]} - 拖曳框選目標 (滾輪縮放)")

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
        base_scale = min(cw / w, ch / h, 1.0)
        self.scale = base_scale * self.zoom_level
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
        self.img_x = (cw - nw) // 2 + self.pan_offset[0]
        self.img_y = (ch - nh) // 2 + self.pan_offset[1]
        self.canvas.create_image(self.img_x, self.img_y, anchor="nw", image=self.photo)

    def on_mouse_wheel(self, event):
        """滾輪縮放"""
        if self.screenshot is None:
            return

        # Windows: event.delta, Linux: event.num
        if event.delta:
            delta = event.delta / 120
        elif event.num == 4:
            delta = 1
        else:
            delta = -1

        # 調整縮放等級
        old_zoom = self.zoom_level
        self.zoom_level *= 1.2 if delta > 0 else 0.8
        self.zoom_level = max(0.5, min(5.0, self.zoom_level))  # 限制 0.5x ~ 5x

        if old_zoom != self.zoom_level:
            self.show_preview(self.screenshot)
            self.status_var.set(f"縮放: {self.zoom_level:.1f}x (Alt+拖曳移動)")

    def on_pan_start(self, event):
        """開始平移"""
        self.pan_start = (event.x, event.y)
        self.canvas.config(cursor="fleur")

    def on_pan_move(self, event):
        """平移中"""
        if self.pan_start is None:
            return
        dx = event.x - self.pan_start[0]
        dy = event.y - self.pan_start[1]
        self.pan_offset[0] += dx
        self.pan_offset[1] += dy
        self.pan_start = (event.x, event.y)
        self.show_preview(self.screenshot)

    def on_drag_start(self, event):
        if self.screenshot is None:
            return
        self.canvas.config(cursor="crosshair")
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

        # 自動儲存模板圖片
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        os.makedirs(template_dir, exist_ok=True)

        # 使用時間戳命名
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        template_filename = f"template_{timestamp}.png"
        template_path = os.path.join(template_dir, template_filename)
        cv2.imwrite(template_path, self.template)

        # 更新當前腳本的模板路徑
        self.current_script.template_path = template_path

        # 更新模板資訊
        h, w = self.template.shape[:2]
        self.template_info.config(text=f"{template_filename} ({w}x{h})", foreground="green")

        self.update_icon()
        self.status_var.set("模板已儲存！可調整動作設定後儲存腳本")

    def _show_quick_action_menu(self):
        """顯示截圖後快速動作選單"""
        menu = tk.Toplevel(self.root)
        menu.title("下一步？")
        menu.geometry("320x200")
        menu.transient(self.root)
        menu.grab_set()

        # 置中
        menu.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 320) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 200) // 2
        menu.geometry(f"+{x}+{y}")

        tk.Label(menu, text="模板已儲存！接下來要？", font=("Microsoft JhengHei", 12, "bold")).pack(pady=15)

        btn_frame = tk.Frame(menu)
        btn_frame.pack(pady=10)

        def add_to_script(action):
            menu.destroy()
            self._add_block_to_editor(action)

        tk.Button(
            btn_frame, text="🖱️ 點擊它", width=12, height=2,
            bg="#4C97FF", fg="white", font=("", 10),
            command=lambda: add_to_script("click")
        ).grid(row=0, column=0, padx=5, pady=5)

        tk.Button(
            btn_frame, text="👁️ 等它出現", width=12, height=2,
            bg="#FFBF00", fg="black", font=("", 10),
            command=lambda: add_to_script("wait_image")
        ).grid(row=0, column=1, padx=5, pady=5)

        tk.Button(
            btn_frame, text="📜 編輯腳本", width=12, height=2,
            bg="#9966FF", fg="white", font=("", 10),
            command=lambda: [menu.destroy(), self.open_block_editor()]
        ).grid(row=1, column=0, padx=5, pady=5)

        tk.Button(
            btn_frame, text="❌ 只儲存", width=12, height=2,
            bg="#666", fg="white", font=("", 10),
            command=menu.destroy
        ).grid(row=1, column=1, padx=5, pady=5)

    def _add_block_to_editor(self, action_type):
        """添加積木到編輯器"""
        # 先儲存模板到檔案
        from tkinter import simpledialog
        name = simpledialog.askstring("儲存模板", "模板名稱:", parent=self.root)
        if not name:
            return

        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        os.makedirs(template_dir, exist_ok=True)
        filepath = os.path.join(template_dir, f"{name}.png")
        cv2.imwrite(filepath, self.template)

        # 開啟編輯器並添加積木
        self.open_block_editor()
        if hasattr(self, 'block_editor') and self.block_editor:
            from block_editor import Block
            block = Block(action_type, {"image": filepath})
            self.block_editor.script.blocks.append(block)
            self.block_editor.refresh_script_view()
            self.block_editor.status_var.set(f"已添加: {block.get_label()}")

    def open_block_editor(self):
        """開啟積木編輯器"""
        try:
            from block_editor import BlockEditor
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
            scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
            self.block_editor = BlockEditor(self.root, templates_dir, scripts_dir)
        except ImportError as e:
            from tkinter import messagebox
            messagebox.showerror("錯誤", f"無法載入積木編輯器: {e}")

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
            ox, oy = monitor["left"], monitor["top"]  # 多螢幕偏移

        self.root.deiconify()

        result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        th, tw = self.template.shape[:2]
        preview = screen.copy()

        if max_val >= 0.7:
            cv2.rectangle(preview, max_loc, (max_loc[0]+tw, max_loc[1]+th), (0, 255, 0), 3)
            # 螢幕座標 = 圖片座標 + 偏移
            cx, cy = max_loc[0] + tw//2 + ox, max_loc[1] + th//2 + oy
            cv2.circle(preview, (max_loc[0] + tw//2, max_loc[1] + th//2), 10, (0, 0, 255), -1)
            self.status_var.set(f"找到！螢幕座標 ({cx}, {cy}) 相似度 {max_val:.0%}")
        else:
            self.status_var.set(f"找不到 (最高相似度 {max_val:.0%})")

        self.screenshot = screen
        self.selection = None
        self.show_preview(preview)

    def start_auto_thread(self):
        """啟動自動執行緒"""
        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()

    def _execute_action_sequence(self, cx, cy):
        """執行動作序列：多次點擊 + 按鍵"""
        # 播放提示音（非同步，不阻塞）
        if self.sound_enabled:
            winsound.Beep(1000, 50)  # 1000Hz, 50ms 短促叮聲

        click_count = self.current_script.click_count
        click_interval = self.current_script.click_interval
        after_key = self.current_script.after_key

        # 儲存原本游標位置和前景視窗
        original_pos = pyautogui.position()
        original_hwnd = user32.GetForegroundWindow()

        # 移動到目標位置（只移動一次）
        user32.SetCursorPos(cx, cy)
        time.sleep(0.02)

        # 執行多次點擊（不移動游標）
        for i in range(click_count):
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            if i < click_count - 1:
                time.sleep(click_interval)

        # 執行後續按鍵（在目標視窗按）
        if after_key:
            time.sleep(0.1)
            pyautogui.press(after_key.lower())
            time.sleep(0.05)

        # 游標回原位
        user32.SetCursorPos(original_pos[0], original_pos[1])

        # 恢復原本視窗焦點
        force_focus(original_hwnd)

        # 更新計數
        self.increment_click_count(click_count)

    def _auto_loop(self):
        """自動偵測（不搶焦點）"""
        while self.running and self.mode == "auto":
            try:
                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    screen = np.array(sct.grab(monitor))
                    screen_bgr = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                    ox, oy = monitor["left"], monitor["top"]

                # Hash 比對
                small = cv2.resize(screen_bgr, (160, 90))
                screen_hash = hashlib.md5(small.tobytes()).hexdigest()

                with self._lock:
                    if screen_hash == self.last_screen_hash:
                        time.sleep(self.auto_interval)
                        continue
                    self.last_screen_hash = screen_hash

                # 模板匹配
                result = cv2.matchTemplate(screen_bgr, self.template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= 0.7:
                    # 檢查冷卻（連續模式跳過冷卻檢查）
                    with self._lock:
                        cooldown_passed = self.continuous_click or (time.time() - self.last_click_time >= self.click_cooldown)

                    if cooldown_passed:
                        th, tw = self.template.shape[:2]
                        cx = max_loc[0] + tw // 2 + ox
                        cy = max_loc[1] + th // 2 + oy

                        # 執行動作序列
                        self._execute_action_sequence(cx, cy)

                        with self._lock:
                            self.last_click_time = time.time()
                            self.last_screen_hash = None

                time.sleep(self.auto_interval)

            except Exception as e:
                # 記錄錯誤但不中斷
                print(f"[PyClick] 自動模式錯誤: {e}")
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

            # 執行動作序列
            self._execute_action_sequence(cx, cy)

        except Exception as e:
            print(f"[PyClick] 熱鍵點擊錯誤: {e}")

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

        # 檢查預設模板
        self.root.after(100, self._check_default_script)

        # 主視窗
        self.root.mainloop()


if __name__ == "__main__":
    if not check_single_instance():
        # 已有實例運行，顯示提示後退出
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox
        messagebox.showwarning("PyClick", "PyClick 已在運行中！\n請查看系統托盤。")
        root.destroy()
    else:
        app = TrayClicker()
        app.run()
