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
import logging
import random
import urllib.request
import webbrowser
from datetime import datetime

# 版本資訊
__version__ = "1.2.0"
GITHUB_REPO = "Jeffrey0117/PyClick"

from utils import (
    force_focus, click_no_focus, check_single_instance, get_window_at,
    user32, kernel32, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
)

# ============================================================
# 日誌設定
# ============================================================
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"pyclick_{datetime.now():%Y%m%d}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('PyClick')

# ============================================================
# 輸入保護機制
# ============================================================
import atexit

def is_admin():
    """檢查是否有管理員權限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def ensure_input_unblocked():
    """確保輸入解鎖（安全機制）"""
    try:
        user32.BlockInput(False)
    except:
        pass

# 程式退出時確保解鎖
atexit.register(ensure_input_unblocked)


# ============================================================
# 簡單腳本資料結構
# ============================================================

class SimpleScript:
    """簡單腳本：多個圖 + 一組動作（任一圖匹配即觸發）"""

    def __init__(self, name="未命名"):
        self.name = name
        self.template_paths = []     # 模板圖片路徑列表（多模板支援）
        self.click_count = 1         # 點擊次數
        self.click_interval = 0.1    # 點擊間隔（秒）
        self.after_key = ""          # 點完後按的鍵（空=不按）
        self.after_key_count = 1     # 按鍵次數
        # 確認機制：點擊後確認圖片是否還在
        self.verify_still_there = False  # 是否啟用確認機制
        self.verify_delay = 0.5          # 確認延遲（秒）
        self.verify_key = "enter"        # 如果還在的話按什麼鍵
        # Focus 模式：不點擊，focus 視窗後按鍵
        self.focus_mode = False
        # 重試直到消失
        self.retry_until_gone = False
        self.retry_max = 3
        # 新增：掃描設定
        self.auto_interval = 0.5     # 掃描間隔（秒）
        self.threshold = 0.7         # 相似度門檻
        self.sound_enabled = True    # 提示音

    @property
    def template_path(self):
        """向後相容：取得第一個模板路徑"""
        return self.template_paths[0] if self.template_paths else ""

    @template_path.setter
    def template_path(self, value):
        """向後相容：設定單一模板"""
        if value:
            if not self.template_paths:
                self.template_paths = [value]
            else:
                self.template_paths[0] = value

    def to_dict(self):
        return {
            "name": self.name,
            "template_paths": self.template_paths,
            "click_count": self.click_count,
            "click_interval": self.click_interval,
            "after_key": self.after_key,
            "after_key_count": self.after_key_count,
            # 確認機制
            "verify_still_there": self.verify_still_there,
            "verify_delay": self.verify_delay,
            "verify_key": self.verify_key,
            # Focus 模式 + 重試直到消失
            "focus_mode": self.focus_mode,
            "retry_until_gone": self.retry_until_gone,
            "retry_max": self.retry_max,
            # 新增：掃描設定
            "auto_interval": self.auto_interval,
            "threshold": self.threshold,
            "sound_enabled": self.sound_enabled,
        }

    @classmethod
    def from_dict(cls, data):
        script = cls(data.get("name", "未命名"))
        # 向後相容：支援舊格式 template_path (單一) 和新格式 template_paths (多個)
        if "template_paths" in data:
            script.template_paths = data["template_paths"]
        elif "template_path" in data and data["template_path"]:
            script.template_paths = [data["template_path"]]
        script.click_count = data.get("click_count", 1)
        script.click_interval = data.get("click_interval", 0.1)
        script.after_key = data.get("after_key", "")
        script.after_key_count = data.get("after_key_count", 1)
        # 確認機制（向後相容）
        script.verify_still_there = data.get("verify_still_there", False)
        script.verify_delay = data.get("verify_delay", 0.5)
        script.verify_key = data.get("verify_key", "enter")
        # Focus 模式 + 重試直到消失（向後相容）
        script.focus_mode = data.get("focus_mode", False)
        script.retry_until_gone = data.get("retry_until_gone", False)
        script.retry_max = data.get("retry_max", 3)
        # 新增：掃描設定（向後相容：舊腳本沒有這些欄位則用預設值）
        script.auto_interval = data.get("auto_interval", 0.5)
        script.threshold = data.get("threshold", 0.7)
        script.sound_enabled = data.get("sound_enabled", True)
        return script

    def save(self, filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

pyautogui.FAILSAFE = True


class TrayClicker:
    def __init__(self):
        self.templates = []  # 多模板支援（任一匹配即觸發）
        self.templates_gray = []  # 灰階版本（效能優化）
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
        self.total_clicks = 0  # 本次啟動點擊計數
        self.lifetime_clicks = 0  # 累計總點擊次數
        self.similarity_threshold = 0.7  # 相似度閾值（可設定）
        self.block_input_enabled = False  # 執行時鎖定輸入（需管理員權限）

        # 定時停止功能
        self.auto_stop_enabled = False   # 是否啟用定時停止
        self.auto_stop_minutes = 30      # 運行多少分鐘後停止
        self.auto_start_time = None      # 自動模式開始時間

        # 點擊偏移（防偵測）
        self.click_offset_enabled = False  # 是否啟用隨機偏移
        self.click_offset_range = 5        # 偏移範圍（像素）

        # 彩色匹配（預設開啟，關閉則用灰階匹配）
        self.use_color_match = True

        # 設定檔路徑
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")

        # 簡單腳本
        self.current_script = SimpleScript()
        self.scripts_dir = os.path.join(os.path.dirname(__file__), "simple_scripts")
        os.makedirs(self.scripts_dir, exist_ok=True)

        # 執行緒鎖
        self._lock = threading.Lock()

        # ROI 優化：記錄上次匹配位置
        self._last_match_pos = None  # (x, y) 上次找到的螢幕位置
        self._roi_margin = 200       # ROI 邊距像素
        self._roi_miss_count = 0     # ROI 連續未找到次數
        self._roi_max_miss = 3       # 超過此次數回退到全螢幕搜尋
        self._idle_streak = 0        # 連續未找到次數（用於閒置退避）
        self._suppress_pos = None    # 重試失敗後暫時忽略的位置 (x, y)
        self._suppress_until = 0     # 忽略到期時間 (timestamp)

        # 音效提示
        self.sound_enabled = True

        # GUI
        self.root = None
        self.panel_visible = True

        # 托盤
        self.icon = None

        # 載入統計資料
        self._load_stats()

        self.setup_gui()
        self.setup_tray()
        self.setup_hotkey()

    # 向後相容的 template 屬性
    @property
    def template(self):
        """向後相容：取得第一個模板"""
        return self.templates[0] if self.templates else None

    @template.setter
    def template(self, value):
        """向後相容：設定單一模板"""
        if value is None:
            self.templates = []
            self.templates_gray = []
        elif not self.templates:
            self.templates = [value]
            self.templates_gray = [cv2.cvtColor(value, cv2.COLOR_BGR2GRAY)]
        else:
            self.templates[0] = value
            self.templates_gray[0] = cv2.cvtColor(value, cv2.COLOR_BGR2GRAY)

    def _load_stats(self):
        """載入統計資料和設定"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.lifetime_clicks = config.get("lifetime_clicks", 0)
                    self.sound_enabled = config.get("sound_enabled", True)
                    self.similarity_threshold = config.get("similarity_threshold", 0.7)
                    self.click_cooldown = config.get("click_cooldown", 1.0)
                    self.block_input_enabled = config.get("block_input_enabled", False)
                    self.auto_stop_enabled = config.get("auto_stop_enabled", False)
                    self.auto_stop_minutes = config.get("auto_stop_minutes", 30)
                    self.click_offset_enabled = config.get("click_offset_enabled", False)
                    self.click_offset_range = config.get("click_offset_range", 5)
                    self.use_color_match = config.get("use_color_match", True)
            except Exception as e:
                logger.warning(f"載入設定失敗: {e}")

    def _save_stats(self):
        """儲存統計資料和設定"""
        try:
            config = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            config["lifetime_clicks"] = self.lifetime_clicks
            config["sound_enabled"] = self.sound_enabled
            config["similarity_threshold"] = self.similarity_threshold
            config["click_cooldown"] = self.click_cooldown
            config["block_input_enabled"] = self.block_input_enabled
            config["auto_stop_enabled"] = self.auto_stop_enabled
            config["auto_stop_minutes"] = self.auto_stop_minutes
            config["click_offset_enabled"] = self.click_offset_enabled
            config["click_offset_range"] = self.click_offset_range
            config["use_color_match"] = self.use_color_match
            config["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"儲存設定失敗: {e}")

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
        ttk.Button(row0, text="📦 導出 EXE", command=self.export_exe, width=12).pack(side="left", padx=5)

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
                                   width=14, height=1, bg="#FF9800", fg="white",
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

        # 按鍵次數
        self.after_key_count_var = tk.StringVar(value="1")
        after_key_count_combo = ttk.Combobox(row2, textvariable=self.after_key_count_var, width=4,
                                             values=["1", "2", "3", "4", "5", "10"])
        after_key_count_combo.pack(side="left", padx=2)
        after_key_count_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        after_key_count_combo.bind("<FocusOut>", self.on_action_change)
        ttk.Label(row2, text="次").pack(side="left", padx=(2, 10))

        ttk.Button(row2, text="縮小到托盤", command=self.hide_to_tray).pack(side="right", padx=10)

        # 第 2.5 排：確認機制
        row2b = ttk.Frame(ctrl_frame)
        row2b.pack(fill="x", padx=10, pady=2)

        self.verify_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2b, text="確認機制:", variable=self.verify_var,
                        command=self.on_action_change).pack(side="left", padx=5)

        ttk.Label(row2b, text="等").pack(side="left", padx=2)
        self.verify_delay_var = tk.StringVar(value="0.5")
        verify_delay_combo = ttk.Combobox(row2b, textvariable=self.verify_delay_var, width=5,
                                           values=["0.3", "0.5", "0.8", "1.0", "1.5", "2.0"])
        verify_delay_combo.pack(side="left", padx=2)
        verify_delay_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        verify_delay_combo.bind("<FocusOut>", self.on_action_change)
        ttk.Label(row2b, text="秒後，若圖片還在則按").pack(side="left", padx=2)

        self.verify_key_var = tk.StringVar(value="Enter")
        verify_key_combo = ttk.Combobox(row2b, textvariable=self.verify_key_var, width=8,
                                         values=["Enter", "Tab", "Space", "Escape", "Up", "Down", "Left", "Right"])
        verify_key_combo.pack(side="left", padx=2)
        verify_key_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        verify_key_combo.bind("<FocusOut>", self.on_action_change)

        # 第 2.6 排：Focus 模式 + 重試直到消失
        row2c = ttk.Frame(ctrl_frame)
        row2c.pack(fill="x", padx=10, pady=2)

        self.focus_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2c, text="Focus 模式", variable=self.focus_mode_var,
                        command=self.on_action_change).pack(side="left", padx=5)

        ttk.Separator(row2c, orient="vertical").pack(side="left", fill="y", padx=8)

        self.retry_until_gone_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2c, text="重試直到消失", variable=self.retry_until_gone_var,
                        command=self._on_retry_toggle).pack(side="left", padx=5)

        ttk.Label(row2c, text="最多").pack(side="left", padx=2)
        self.retry_max_var = tk.StringVar(value="3")
        retry_max_combo = ttk.Combobox(row2c, textvariable=self.retry_max_var, width=4,
                                        values=["1", "2", "3", "5", "10"])
        retry_max_combo.pack(side="left", padx=2)
        retry_max_combo.bind("<<ComboboxSelected>>", self.on_action_change)
        retry_max_combo.bind("<FocusOut>", self.on_action_change)
        ttk.Label(row2c, text="次").pack(side="left", padx=2)

        # 第三排：模式控制
        row3 = ttk.Frame(ctrl_frame)
        row3.pack(fill="x", padx=10, pady=5)

        # 大大的開始/停止按鈕（美化版）
        self.start_btn = tk.Button(
            row3, text="▶ 開始", width=10, height=1,
            bg="#2E7D32", fg="white", font=("Microsoft JhengHei", 12, "bold"),
            activebackground="#1B5E20", activeforeground="white",
            relief="flat", bd=0, cursor="hand2", command=self.toggle_auto_mode,
            padx=15, pady=5
        )
        self.start_btn.pack(side="left", padx=10, ipady=3)

        ttk.Separator(row3, orient="vertical").pack(side="left", fill="y", padx=5)

        ttk.Label(row3, text="模式:").pack(side="left", padx=5)

        self.mode_var = tk.StringVar(value="off")
        ttk.Radiobutton(row3, text="停用", variable=self.mode_var, value="off",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(row3, text="熱鍵 (F6)", variable=self.mode_var, value="hotkey",
                        command=self.on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(row3, text="自動", variable=self.mode_var, value="auto",
                        command=self.on_mode_change).pack(side="left", padx=5)

        ttk.Separator(row3, orient="vertical").pack(side="left", fill="y", padx=5)

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

        # 清除模板按鈕
        ttk.Button(bottom_frame, text="清除", width=4,
                   command=self._clear_templates).pack(side="left", padx=2)

        # 連續點擊選項
        ttk.Separator(bottom_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        self.continuous_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom_frame, text="連續點擊", variable=self.continuous_var,
                        command=self.on_continuous_change).pack(side="left", padx=5)

        # 音效提示選項（從設定載入）
        self.sound_var = tk.BooleanVar(value=self.sound_enabled)
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
        keyboard.add_hotkey('F7', self.on_stop_hotkey)

    def on_stop_hotkey(self):
        """F7 停止熱鍵：回到 off 模式"""
        with self._lock:
            if self.mode == "off":
                return
            self.mode = "off"
        logger.info("F7 停止熱鍵觸發")
        self.root.after(0, self._stop_from_hotkey)

    def _stop_from_hotkey(self):
        """在主執行緒更新 UI"""
        self.mode_var.set("off")
        self._update_start_button()
        self.update_icon()
        self.status_var.set("已停用（F7）")
        self._show_panel()

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
        # 恢復時刷新計數器（修復隱藏時不更新的問題）
        self._update_counter_ui()

    def hide_to_tray(self):
        """隱藏到托盤"""
        self.root.withdraw()
        self.panel_visible = False

    def toggle_auto_mode(self):
        """切換自動模式（大按鈕用）"""
        with self._lock:
            current_mode = self.mode
            has_template = self.template is not None

        if current_mode == "auto":
            # 停止
            with self._lock:
                self.mode = "off"
            self.mode_var.set("off")
            self._update_start_button()
            self.update_icon()
            self.status_var.set("已停止")
        else:
            # 開始
            if not has_template:
                self.status_var.set("請先儲存模板！")
                return
            with self._lock:
                self.mode = "auto"
                self.auto_start_time = time.time()  # 記錄開始時間
            self.mode_var.set("auto")
            self._update_start_button()
            self.update_icon()
            self.start_auto_thread()
            self.status_var.set("自動模式已開啟")
            # 自動縮小避免點到自己
            self.root.after(500, self.hide_to_tray)

    def _update_start_button(self):
        """更新開始按鈕外觀"""
        if self.mode == "auto":
            self.start_btn.config(
                text="■ 停止", bg="#C62828", activebackground="#B71C1C",
                font=("Microsoft JhengHei", 12, "bold")
            )
        else:
            self.start_btn.config(
                text="▶ 開始", bg="#2E7D32", activebackground="#1B5E20",
                font=("Microsoft JhengHei", 12, "bold")
            )

    def on_mode_change(self):
        """模式改變"""
        new_mode = self.mode_var.get()

        with self._lock:
            has_template = self.template is not None

        if new_mode in ["hotkey", "auto"] and not has_template:
            self.status_var.set("請先儲存模板！")
            self.mode_var.set("off")
            return

        with self._lock:
            self.mode = new_mode
        self._update_start_button()
        self.update_icon()

        if new_mode == "auto":
            self.start_auto_thread()
            self.status_var.set(f"自動模式開啟 - 視窗將縮小")
            # 自動縮小避免點到自己
            self.root.after(500, self.hide_to_tray)
        elif new_mode == "hotkey":
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
        self._save_stats()  # 儲存設定
        if self.sound_enabled:
            winsound.Beep(1000, 50)  # 播放示範音
            self.status_var.set("提示音: 開啟")
        else:
            self.status_var.set("提示音: 關閉")

    def _on_retry_toggle(self):
        """重試直到消失切換：與確認機制互斥"""
        if self.retry_until_gone_var.get():
            self.verify_var.set(False)
        self.on_action_change()

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

        try:
            self.current_script.after_key_count = int(self.after_key_count_var.get())
        except ValueError:
            self.current_script.after_key_count = 1

        # 確認機制設定
        self.current_script.verify_still_there = self.verify_var.get()
        try:
            self.current_script.verify_delay = float(self.verify_delay_var.get())
        except ValueError:
            self.current_script.verify_delay = 0.5
        self.current_script.verify_key = self.verify_key_var.get()

        # Focus 模式 + 重試直到消失
        self.current_script.focus_mode = self.focus_mode_var.get()
        self.current_script.retry_until_gone = self.retry_until_gone_var.get()
        try:
            val = int(self.retry_max_var.get())
            self.current_script.retry_max = max(1, min(val, 50))
        except ValueError:
            self.current_script.retry_max = 3

        if self.current_script.focus_mode:
            action_desc = f"[Focus] 按鍵{self.current_script.after_key or 'N/A'}"
            if self.current_script.after_key_count > 1:
                action_desc += f" x{self.current_script.after_key_count}"
        else:
            action_desc = f"點{self.current_script.click_count}下"
            if self.current_script.after_key:
                if self.current_script.after_key_count > 1:
                    action_desc += f" → {self.current_script.after_key} x{self.current_script.after_key_count}"
                else:
                    action_desc += f" → {self.current_script.after_key}"
        if self.current_script.verify_still_there:
            action_desc += f" → 確認({self.current_script.verify_delay}s後按{self.current_script.verify_key})"
        if self.current_script.retry_until_gone:
            action_desc += f" → 重試(最多{self.current_script.retry_max}次)"

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
            with self._lock:
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
        self.after_key_count_var.set(str(self.current_script.after_key_count))

        # 載入確認機制設定
        self.verify_var.set(self.current_script.verify_still_there)
        self.verify_delay_var.set(str(self.current_script.verify_delay))
        self.verify_key_var.set(self.current_script.verify_key or "Enter")

        # 載入 Focus 模式 + 重試直到消失
        self.focus_mode_var.set(self.current_script.focus_mode)
        self.retry_until_gone_var.set(self.current_script.retry_until_gone)
        self.retry_max_var.set(str(self.current_script.retry_max))

        # 載入掃描設定
        self.auto_interval = self.current_script.auto_interval
        self.similarity_threshold = self.current_script.threshold
        self.sound_enabled = self.current_script.sound_enabled

        # 更新 UI 控制項
        self.interval_var.set(str(self.auto_interval))
        self.sound_var.set(self.sound_enabled)

        # 更新模板資訊（多模板支援）
        count = len(self.templates)
        if count == 0:
            self.template_info.config(text="(未設定)", foreground="gray")
        elif count == 1:
            h, w = self.templates[0].shape[:2]
            name = os.path.basename(self.current_script.template_paths[0]) if self.current_script.template_paths else "模板"
            self.template_info.config(text=f"{name} ({w}x{h})", foreground="green")
        else:
            self.template_info.config(text=f"{count} 個模板", foreground="green")

        self.update_icon()

    def _load_template_from_script(self):
        """從腳本載入模板圖片（多模板支援）"""
        new_templates = []
        new_templates_gray = []
        for path in self.current_script.template_paths:
            if path and os.path.exists(path):
                img = cv2.imread(path)
                if img is not None:
                    new_templates.append(img)
                    new_templates_gray.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))

        with self._lock:
            self.templates = new_templates
            self.templates_gray = new_templates_gray

    def _sync_settings_to_script(self):
        """同步 TrayClicker 設定到腳本（儲存前呼叫）"""
        self.current_script.auto_interval = self.auto_interval
        self.current_script.threshold = self.similarity_threshold
        self.current_script.sound_enabled = self.sound_enabled

    def save_script(self):
        """儲存當前腳本"""
        if not self.current_script.name or self.current_script.name == "未命名":
            self.save_script_as()
            return

        self._sync_settings_to_script()  # 同步設定
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

        self._sync_settings_to_script()  # 同步設定
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
        with self._lock:
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
        self.lifetime_clicks += count
        self.root.after(0, self._update_counter_ui)

        # 每 10 次點擊儲存一次（避免頻繁寫入）
        if self.total_clicks % 10 == 0:
            self._save_stats()

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

        # 大數字顯示（累計總點擊）
        tk.Label(stats_frame, text="已幫你點擊", font=("", 14), fg="#666").pack(pady=(20, 5))
        tk.Label(stats_frame, text=str(self.lifetime_clicks), font=("Consolas", 72, "bold"), fg="#4CAF50").pack()
        tk.Label(stats_frame, text="次", font=("", 14), fg="#666").pack(pady=(5, 30))

        # 統計資訊
        info_frame = ttk.LabelFrame(stats_frame, text="統計", padding=10)
        info_frame.pack(fill="x", pady=10)
        ttk.Label(info_frame, text=f"累計總點擊: {self.lifetime_clicks} 次", font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(info_frame, text=f"本次啟動: {self.total_clicks} 次").pack(anchor="w")
        ttk.Label(info_frame, text=f"當前模式: {self.mode}").pack(anchor="w")
        ttk.Label(info_frame, text=f"掃描間隔: {self.auto_interval} 秒").pack(anchor="w")

        # === 頁籤2：模板管理 ===
        template_frame = ttk.Frame(notebook, padding=20)
        notebook.add(template_frame, text="📁 模板")

        ttk.Label(template_frame, text="已儲存的模板", font=("", 12, "bold")).pack(anchor="w", pady=(0, 10))

        # 模板列表和預覽
        list_container = ttk.Frame(template_frame)
        list_container.pack(fill="both", expand=True)

        # 左側：列表
        list_frame = ttk.Frame(list_container)
        list_frame.pack(side="left", fill="both", expand=True)

        self.template_listbox = tk.Listbox(list_frame, height=10, font=("", 10))
        self.template_listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.template_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.template_listbox.config(yscrollcommand=scrollbar.set)

        # 右側：預覽圖
        preview_frame = ttk.LabelFrame(list_container, text="預覽", padding=10)
        preview_frame.pack(side="right", fill="both", padx=(10, 0))

        self.template_preview_label = ttk.Label(preview_frame, text="選擇模板以預覽",
                                                foreground="gray", anchor="center")
        self.template_preview_label.pack(expand=True)

        # 綁定選擇事件
        self.template_listbox.bind("<<ListboxSelect>>", self._on_template_select)

        # 載入已儲存的模板
        self._load_template_list()

        # 按鈕
        btn_frame = ttk.Frame(template_frame)
        btn_frame.pack(fill="x", pady=10)

        ttk.Button(btn_frame, text="💾 儲存目前模板", command=self._save_current_template).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="📂 載入選中", command=self._load_selected_template).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="⭐ 設為預設", command=self._set_default_template).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🗑 刪除選中", command=self._delete_selected_template).pack(side="left", padx=5)

        # 當前已載入的模板預覽（顯示所有）
        ttk.Separator(template_frame, orient="horizontal").pack(fill="x", pady=10)
        loaded_label = ttk.Label(template_frame, text=f"當前已載入: {len(self.templates)} 個模板", font=("", 10, "bold"))
        loaded_label.pack(anchor="w", pady=(5, 5))

        if self.templates:
            # 水平排列的預覽框架
            preview_container = ttk.Frame(template_frame)
            preview_container.pack(fill="x", anchor="w")

            for i, template in enumerate(self.templates):
                # 每個模板的框架
                item_frame = ttk.Frame(preview_container)
                item_frame.pack(side="left", padx=5, pady=5)

                # 縮略圖
                h, w = template.shape[:2]
                scale = min(80/w, 60/h, 1.0)
                thumb = cv2.resize(template, (int(w*scale), int(h*scale)))
                thumb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
                photo = ImageTk.PhotoImage(Image.fromarray(thumb))
                img_label = ttk.Label(item_frame, image=photo)
                img_label.image = photo  # 保持引用
                img_label.pack()

                # 編號
                ttk.Label(item_frame, text=f"#{i+1}", font=("", 8)).pack()

            # 清除按鈕
            ttk.Button(preview_container, text="🗑 清除全部",
                       command=lambda: [self._clear_templates(), settings_win.destroy()]).pack(side="left", padx=20)
        else:
            ttk.Label(template_frame, text="(尚未載入模板)", foreground="gray").pack(anchor="w")

        # === 頁籤3：設定 ===
        config_frame = ttk.Frame(notebook, padding=20)
        notebook.add(config_frame, text="⚙ 設定")

        ttk.Label(config_frame, text="個人化設定", font=("", 12, "bold")).pack(anchor="w", pady=(0, 15))

        # 相似度閾值
        threshold_frame = ttk.Frame(config_frame)
        threshold_frame.pack(fill="x", pady=8)
        ttk.Label(threshold_frame, text="相似度閾值:", width=12).pack(side="left")
        threshold_var = tk.StringVar(value=str(int(self.similarity_threshold * 100)))
        threshold_combo = ttk.Combobox(threshold_frame, textvariable=threshold_var, width=8,
                                        values=["50", "60", "70", "80", "90"])
        threshold_combo.pack(side="left", padx=5)
        ttk.Label(threshold_frame, text="%").pack(side="left")
        ttk.Label(threshold_frame, text="(越低越容易匹配，但可能誤判)", foreground="gray", font=("", 8)).pack(side="left", padx=10)

        # 點擊冷卻
        cooldown_frame = ttk.Frame(config_frame)
        cooldown_frame.pack(fill="x", pady=8)
        ttk.Label(cooldown_frame, text="點擊冷卻:", width=12).pack(side="left")
        cooldown_var = tk.StringVar(value=str(self.click_cooldown))
        cooldown_combo = ttk.Combobox(cooldown_frame, textvariable=cooldown_var, width=8,
                                       values=["0.5", "1.0", "1.5", "2.0", "3.0", "5.0"])
        cooldown_combo.pack(side="left", padx=5)
        ttk.Label(cooldown_frame, text="秒").pack(side="left")
        ttk.Label(cooldown_frame, text="(兩次點擊之間的最小間隔)", foreground="gray", font=("", 8)).pack(side="left", padx=10)

        # 熱鍵
        hotkey_frame = ttk.Frame(config_frame)
        hotkey_frame.pack(fill="x", pady=8)
        ttk.Label(hotkey_frame, text="觸發熱鍵:", width=12).pack(side="left")
        ttk.Label(hotkey_frame, text=self.hotkey, foreground="#4CAF50", font=("", 10, "bold")).pack(side="left", padx=5)

        # 輸入保護
        block_frame = ttk.Frame(config_frame)
        block_frame.pack(fill="x", pady=8)
        block_var = tk.BooleanVar(value=self.block_input_enabled)
        block_check = ttk.Checkbutton(block_frame, text="執行時鎖定輸入", variable=block_var)
        block_check.pack(side="left")
        admin_text = "✓ 已有管理員權限" if is_admin() else "⚠ 需要管理員權限"
        admin_color = "#4CAF50" if is_admin() else "#FF9800"
        ttk.Label(block_frame, text=admin_text, foreground=admin_color, font=("", 8)).pack(side="left", padx=10)

        # 定時停止
        timer_frame = ttk.Frame(config_frame)
        timer_frame.pack(fill="x", pady=8)
        auto_stop_var = tk.BooleanVar(value=self.auto_stop_enabled)
        ttk.Checkbutton(timer_frame, text="定時停止:", variable=auto_stop_var).pack(side="left")
        timer_minutes_var = tk.StringVar(value=str(self.auto_stop_minutes))
        timer_combo = ttk.Combobox(timer_frame, textvariable=timer_minutes_var, width=6,
                                   values=["5", "10", "15", "30", "60", "120"])
        timer_combo.pack(side="left", padx=5)
        ttk.Label(timer_frame, text="分鐘後自動停止").pack(side="left")

        # 點擊偏移
        offset_frame = ttk.Frame(config_frame)
        offset_frame.pack(fill="x", pady=8)
        offset_var = tk.BooleanVar(value=self.click_offset_enabled)
        ttk.Checkbutton(offset_frame, text="隨機偏移:", variable=offset_var).pack(side="left")
        offset_range_var = tk.StringVar(value=str(self.click_offset_range))
        offset_combo = ttk.Combobox(offset_frame, textvariable=offset_range_var, width=6,
                                    values=["3", "5", "10", "15", "20"])
        offset_combo.pack(side="left", padx=5)
        ttk.Label(offset_frame, text="像素 (防偵測)").pack(side="left")

        # 彩色匹配
        color_frame = ttk.Frame(config_frame)
        color_frame.pack(fill="x", pady=8)
        color_var = tk.BooleanVar(value=self.use_color_match)
        ttk.Checkbutton(color_frame, text="彩色匹配", variable=color_var).pack(side="left")
        ttk.Label(color_frame, text="(關閉=灰階匹配，較快但可能誤判顏色)", foreground="gray", font=("", 8)).pack(side="left", padx=10)

        ttk.Separator(config_frame, orient="horizontal").pack(fill="x", pady=20)

        # 儲存按鈕
        def save_settings():
            try:
                self.similarity_threshold = int(threshold_var.get()) / 100.0
                self.click_cooldown = float(cooldown_var.get())
                self.block_input_enabled = block_var.get()
                self.auto_stop_enabled = auto_stop_var.get()
                self.auto_stop_minutes = int(timer_minutes_var.get())
                self.click_offset_enabled = offset_var.get()
                self.click_offset_range = int(offset_range_var.get())
                self.use_color_match = color_var.get()
                self._save_stats()
                timer_msg = f"，定時 {self.auto_stop_minutes}分" if self.auto_stop_enabled else ""
                offset_msg = f"，偏移 ±{self.click_offset_range}px" if self.click_offset_enabled else ""
                color_msg = "，彩色匹配" if self.use_color_match else "，灰階匹配"
                self.status_var.set(f"設定已儲存：閾值 {self.similarity_threshold:.0%}{timer_msg}{offset_msg}{color_msg}")
                settings_win.destroy()
            except ValueError:
                self.status_var.set("設定值無效")

        btn_row = ttk.Frame(config_frame)
        btn_row.pack(pady=10)
        tk.Button(btn_row, text="儲存設定", command=save_settings,
                  bg="#4CAF50", fg="white", font=("", 10, "bold"), width=12).pack(side="left", padx=5)
        tk.Button(btn_row, text="檢查更新", command=self._check_update,
                  bg="#2196F3", fg="white", font=("", 10), width=10).pack(side="left", padx=5)

        # 版本資訊
        ttk.Label(config_frame, text=f"目前版本: v{__version__}", foreground="gray").pack()

    def _check_update(self):
        """檢查 GitHub 更新"""
        def check():
            try:
                url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "PyClick"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    latest = data.get("tag_name", "").lstrip("v")
                    html_url = data.get("html_url", "")

                    if latest and latest != __version__:
                        # 有新版本
                        self.root.after(0, lambda: self._show_update_dialog(latest, html_url))
                    else:
                        self.root.after(0, lambda: self.status_var.set(f"已是最新版本 v{__version__}"))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"檢查更新失敗: {e}"))

        self.status_var.set("檢查更新中...")
        threading.Thread(target=check, daemon=True).start()

    def _show_update_dialog(self, version, url):
        """顯示更新對話框"""
        from tkinter import messagebox
        result = messagebox.askyesno(
            "發現新版本",
            f"目前版本: v{__version__}\n最新版本: v{version}\n\n是否開啟下載頁面？"
        )
        if result and url:
            webbrowser.open(url)

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

    def _on_template_select(self, event=None):
        """當選擇模板時顯示預覽圖"""
        import os
        selection = self.template_listbox.curselection()
        if not selection:
            return

        name = self.template_listbox.get(selection[0])
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        filepath = os.path.join(template_dir, f"{name}.png")

        if not os.path.exists(filepath):
            self.template_preview_label.config(image='', text="檔案不存在", foreground="red")
            return

        # 讀取圖片
        img = cv2.imread(filepath)
        if img is None:
            self.template_preview_label.config(image='', text="無法載入圖片", foreground="red")
            return

        # 轉換顏色並縮放
        h, w = img.shape[:2]
        max_size = 200
        scale = min(max_size/w, max_size/h, 1.0)
        new_w, new_h = int(w * scale), int(h * scale)
        img_resized = cv2.resize(img, (new_w, new_h))
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)

        # 轉為 PhotoImage
        photo = ImageTk.PhotoImage(Image.fromarray(img_rgb))

        # 保存引用（防止被垃圾回收）
        self.template_preview_label._photo = photo
        self.template_preview_label.config(image=photo, text="")

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
        """載入選中的模板（新增到列表，防止重複）"""
        import os
        selection = self.template_listbox.curselection()
        if not selection:
            return

        name = self.template_listbox.get(selection[0])
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        filepath = os.path.join(template_dir, f"{name}.png")

        # 檢查是否已載入（防止重複）
        if filepath in self.current_script.template_paths:
            self.status_var.set(f"模板 {name} 已存在，不重複載入")
            return

        new_template = cv2.imread(filepath)
        if new_template is not None:
            with self._lock:
                self.templates.append(new_template)
                self.templates_gray.append(cv2.cvtColor(new_template, cv2.COLOR_BGR2GRAY))

            # 更新腳本路徑列表
            self.current_script.template_paths.append(filepath)

            self.update_icon()
            count = len(self.templates)
            h, w = new_template.shape[:2]
            if count == 1:
                self.template_info.config(text=f"{name} ({w}x{h})", foreground="green")
            else:
                self.template_info.config(text=f"{count} 個模板", foreground="green")
            self.status_var.set(f"已新增模板: {name} (共 {count} 個)")

            # 警告過多模板
            if count > 5:
                self._show_toast(f"警告: {count} 個模板可能影響效能", duration=2000)

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

    def _clear_templates(self):
        """清除所有模板"""
        with self._lock:
            self.templates = []
            self.templates_gray = []
            self._last_match_pos = None
            self._roi_miss_count = 0

        self.current_script.template_paths = []
        self.template_info.config(text="(未設定)", foreground="gray")
        self.update_icon()
        self.status_var.set("已清除所有模板")

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
        with self._lock:
            if self.template is None:
                return
            self.mode = "auto"
            self.auto_start_time = time.time()  # 記錄開始時間
        self.mode_var.set("auto")
        self.update_icon()
        self.start_auto_thread()

    def set_hotkey_mode(self, icon=None, item=None):
        with self._lock:
            if self.template is None:
                return
            self.mode = "hotkey"
        self.mode_var.set("hotkey")
        self.update_icon()

    def set_off_mode(self, icon=None, item=None):
        with self._lock:
            self.mode = "off"
        self.mode_var.set("off")
        self.update_icon()

    def _auto_stop_triggered(self):
        """定時停止觸發"""
        with self._lock:
            self.mode = "off"
            self.auto_start_time = None
        # 在主執行緒更新 UI
        if self.root:
            self.root.after(0, lambda: self._on_auto_stop_complete())

    def _on_auto_stop_complete(self):
        """定時停止後更新 UI"""
        self.mode_var.set("off")
        self._update_start_button()
        self.update_icon()
        minutes = self.auto_stop_minutes
        self.status_var.set(f"已運行 {minutes} 分鐘，自動停止")
        self._show_toast(f"已運行 {minutes} 分鐘\n自動停止", duration=3000)

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
        """儲存模板（多模板支援：新增到列表）"""
        if self.selection is None:
            self.status_var.set("請先拖曳框選目標！")
            return

        x1, y1, x2, y2 = self.selection
        new_template = self.screenshot[y1:y2, x1:x2].copy()

        # 自動儲存模板圖片
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        os.makedirs(template_dir, exist_ok=True)

        # 使用時間戳命名
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        template_filename = f"template_{timestamp}.png"
        template_path = os.path.join(template_dir, template_filename)
        cv2.imwrite(template_path, new_template)

        # 新增到模板列表（多模板支援 + 灰階版本）
        with self._lock:
            self.templates.append(new_template)
            self.templates_gray.append(cv2.cvtColor(new_template, cv2.COLOR_BGR2GRAY))
            self.last_screen_hash = None

        # 更新當前腳本的模板路徑列表
        self.current_script.template_paths.append(template_path)

        # 更新模板資訊（顯示數量）
        h, w = new_template.shape[:2]
        count = len(self.templates)
        if count == 1:
            self.template_info.config(text=f"{template_filename} ({w}x{h})", foreground="green")
        else:
            self.template_info.config(text=f"{count} 個模板", foreground="green")

        # 警告過多模板
        if count > 5:
            self._show_toast(f"警告: {count} 個模板可能影響效能", duration=2000)

        self.update_icon()
        self.status_var.set(f"模板已新增！共 {count} 個模板")

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

    def export_exe(self):
        """導出為獨立 EXE"""
        from tkinter import messagebox

        # 檢查是否有腳本和模板
        if not self.current_script.template_path or not os.path.exists(self.current_script.template_path):
            messagebox.showwarning("提示", "請先儲存腳本和模板！", parent=self.root)
            return

        if not self.current_script.name or self.current_script.name == "未命名":
            messagebox.showwarning("提示", "請先儲存腳本（按「另存」）", parent=self.root)
            return

        try:
            from exporter import export_script
            export_script(self.root, self.current_script, self.current_script.template_path)
        except ImportError as e:
            messagebox.showerror("錯誤", f"無法載入導出器: {e}")
        except Exception as e:
            messagebox.showerror("錯誤", f"導出失敗: {e}")

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

        if max_val >= self.similarity_threshold:
            cv2.rectangle(preview, max_loc, (max_loc[0]+tw, max_loc[1]+th), (0, 255, 0), 3)
            # 螢幕座標 = 圖片座標 + 偏移
            cx, cy = max_loc[0] + tw//2 + ox, max_loc[1] + th//2 + oy
            cv2.circle(preview, (max_loc[0] + tw//2, max_loc[1] + th//2), 10, (0, 0, 255), -1)
            self.status_var.set(f"找到！座標 ({cx}, {cy}) 相似度 {max_val:.0%} (閾值 {self.similarity_threshold:.0%})")
        else:
            self.status_var.set(f"找不到 (相似度 {max_val:.0%} < 閾值 {self.similarity_threshold:.0%})")

        self.screenshot = screen
        self.selection = None
        self.show_preview(preview)

    def start_auto_thread(self):
        """啟動自動執行緒"""
        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()

    def _find_all_matches(self, screen_match, template, threshold, ox=0, oy=0):
        """找出螢幕上所有匹配位置（使用 NMS 避免重複）"""
        th, tw = template.shape[:2]
        result = cv2.matchTemplate(screen_match, template, cv2.TM_CCOEFF_NORMED)

        # 找出所有超過閾值的位置
        locations = np.where(result >= threshold)
        matches = []

        for pt in zip(*locations[::-1]):  # (x, y) 格式
            cx = pt[0] + tw // 2 + ox
            cy = pt[1] + th // 2 + oy
            score = result[pt[1], pt[0]]
            matches.append((cx, cy, score))

        if not matches:
            return []

        # 非極大值抑制 (NMS)：移除重疊的匹配
        # 按分數排序（高到低）
        matches.sort(key=lambda x: x[2], reverse=True)

        # 過濾重疊的匹配（距離太近的視為同一個）
        min_distance = max(tw, th) * 0.8  # 80% 的模板尺寸作為最小間距
        filtered = []

        for cx, cy, score in matches:
            is_duplicate = False
            for fx, fy, _ in filtered:
                dist = ((cx - fx) ** 2 + (cy - fy) ** 2) ** 0.5
                if dist < min_distance:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered.append((cx, cy, score))

        return [(int(cx), int(cy)) for cx, cy, _ in filtered]

    def _execute_action_sequence(self, cx, cy, skip_count=False):
        """執行動作序列：多次點擊 + 按鍵（可選輸入鎖定）"""
        # 播放提示音（非同步，不阻塞）
        if self.sound_enabled:
            threading.Thread(target=lambda: winsound.Beep(1000, 100), daemon=True).start()
            time.sleep(0.3)  # 給人反應時間

        # 隨機偏移（防偵測）
        if self.click_offset_enabled and self.click_offset_range > 0:
            offset_x = random.randint(-self.click_offset_range, self.click_offset_range)
            offset_y = random.randint(-self.click_offset_range, self.click_offset_range)
            cx += offset_x
            cy += offset_y

        click_count = self.current_script.click_count
        click_interval = self.current_script.click_interval
        after_key = self.current_script.after_key
        focus_mode = self.current_script.focus_mode

        # 儲存原本游標位置和前景視窗
        original_pos = pyautogui.position()
        original_hwnd = user32.GetForegroundWindow()

        try:
            # 鎖定輸入（如果啟用且有管理員權限）
            if self.block_input_enabled:
                user32.BlockInput(True)

            if focus_mode:
                # Focus 模式：點擊確保焦點到正確子面板，再按鍵
                user32.SetCursorPos(cx, cy)
                time.sleep(0.02)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.1)
                if after_key:
                    after_key_count = self.current_script.after_key_count
                    for i in range(after_key_count):
                        pyautogui.press(after_key.lower())
                        if i < after_key_count - 1:
                            time.sleep(0.05)
                    time.sleep(0.15)
                else:
                    logger.warning("Focus 模式啟用但未設定按鍵，僅點擊")
            else:
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
                    after_key_count = self.current_script.after_key_count
                    for i in range(after_key_count):
                        pyautogui.press(after_key.lower())
                        if i < after_key_count - 1:
                            time.sleep(0.05)

        finally:
            # 保證解鎖（即使出錯也會執行）
            if self.block_input_enabled:
                user32.BlockInput(False)

            # 游標回原位
            try:
                user32.SetCursorPos(int(original_pos[0]), int(original_pos[1]))
            except Exception:
                pass

            # 焦點恢復策略：
            # 1. Focus 模式：一定恢復（因為是臨時切換焦點）
            # 2. 手動觸發：恢復焦點
            # 3. Auto 模式 + 非 focus：不恢復（避免打斷打字）
            try:
                should_restore = focus_mode or (self.mode != "auto")
                if should_restore and original_hwnd:
                    force_focus(original_hwnd)
            except Exception:
                pass

        # 更新計數（重試時 skip_count=True 避免重複計算）
        if not skip_count:
            self.increment_click_count(click_count if not focus_mode else 0)

        # 確認機制：retry_until_gone 啟用時跳過舊的 verify_still_there
        if self.current_script.verify_still_there and not self.current_script.retry_until_gone:
            self._verify_and_press()

    def _check_roi_match(self, cx, cy):
        """ROI 區域模板匹配檢查：只掃描目標位置附近"""
        with self._lock:
            templates = self.templates
            templates_gray = self.templates_gray
            use_color = self.use_color_match
            threshold = self.similarity_threshold

        if not templates:
            return False

        try:
            margin = self._roi_margin
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                ox, oy = monitor["left"], monitor["top"]
                # 將螢幕座標轉為截圖座標
                sx = cx - ox
                sy = cy - oy
                # ROI 邊界（確保不超出螢幕）
                x1 = max(0, sx - margin)
                y1 = max(0, sy - margin)
                x2 = min(monitor["width"], sx + margin)
                y2 = min(monitor["height"], sy + margin)

                roi_region = {"left": x1 + ox, "top": y1 + oy,
                              "width": x2 - x1, "height": y2 - y1}
                roi_img = np.array(sct.grab(roi_region))

            if use_color:
                roi_match = cv2.cvtColor(roi_img, cv2.COLOR_BGRA2BGR)
                match_templates = templates
            else:
                roi_match = cv2.cvtColor(roi_img, cv2.COLOR_BGRA2GRAY)
                match_templates = templates_gray

            for template in match_templates:
                th, tw = template.shape[:2]
                if roi_match.shape[0] < th or roi_match.shape[1] < tw:
                    continue
                result = cv2.matchTemplate(roi_match, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                if max_val >= threshold:
                    return True

            return False

        except Exception as e:
            logger.error(f"ROI 檢查錯誤: {e}", exc_info=True)
            return False

    def _execute_with_retry(self, cx, cy):
        """包裝器：執行動作後，若啟用重試直到消失，則重複檢查並重試"""
        # 快照腳本參考，避免 UI 切換腳本時產生競態
        script = self.current_script
        self._execute_action_sequence(cx, cy)

        if not script.retry_until_gone:
            return

        retry_max = max(1, script.retry_max)
        verify_delay = script.verify_delay

        for attempt in range(retry_max):
            time.sleep(verify_delay)
            still_there = self._check_roi_match(cx, cy)
            if not still_there:
                logger.info("重試機制: 模板已消失")
                return
            logger.info(f"重試機制: 模板仍在，重試 {attempt + 1}/{retry_max}")
            self._execute_action_sequence(cx, cy, skip_count=True)

        logger.info(f"重試機制: 已達上限 {retry_max} 次，暫時跳過此位置 30 秒")
        with self._lock:
            self._suppress_pos = (cx, cy)
            self._suppress_until = time.time() + 30

    def _verify_and_press(self):
        """確認機制：等待後檢查圖片是否還在，若在則按鍵"""
        verify_delay = self.current_script.verify_delay
        verify_key = self.current_script.verify_key

        # 等待指定時間
        time.sleep(verify_delay)

        # 取得當前模板和設定
        with self._lock:
            templates = self.templates
            templates_gray = self.templates_gray
            use_color = self.use_color_match
            threshold = self.similarity_threshold

        if not templates:
            return

        try:
            # 截取螢幕
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screen = np.array(sct.grab(monitor))

            # 根據設定選擇匹配模式
            if use_color:
                screen_match = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                match_templates = templates
            else:
                screen_match = cv2.cvtColor(screen, cv2.COLOR_BGRA2GRAY)
                match_templates = templates_gray

            # 檢查是否還能找到任一模板
            still_there = False
            for template in match_templates:
                result = cv2.matchTemplate(screen_match, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                if max_val >= threshold:
                    still_there = True
                    break

            # 如果圖片還在，按下確認鍵
            if still_there and verify_key:
                logger.info(f"確認機制: 圖片仍在，按下 {verify_key}")
                pyautogui.press(verify_key.lower())
                # 播放不同的提示音（較低音）
                if self.sound_enabled:
                    threading.Thread(target=lambda: winsound.Beep(800, 80), daemon=True).start()
            else:
                logger.info("確認機制: 圖片已消失，不按鍵")

        except Exception as e:
            logger.error(f"確認機制錯誤: {e}")

    def _auto_loop(self):
        """自動偵測（不搶焦點）- ROI 優先掃描 + 閒置退避"""
        self._idle_streak = 0  # 每次啟動自動模式重置
        while self.running:
            # 執行緒安全：讀取共享狀態（不複製模板，只讀參考）
            with self._lock:
                current_mode = self.mode
                templates = self.templates  # 只讀，不需複製
                templates_gray = self.templates_gray  # 灰階版本
                use_color = self.use_color_match  # 彩色匹配開關
                auto_interval = self.auto_interval
                continuous_click = self.continuous_click
                last_match_pos = self._last_match_pos
                threshold = self.similarity_threshold
                roi_miss_count = self._roi_miss_count

            if current_mode != "auto":
                break

            # 定時停止檢查
            if self.auto_stop_enabled and self.auto_start_time:
                elapsed = time.time() - self.auto_start_time
                if elapsed >= self.auto_stop_minutes * 60:
                    # 時間到，停止自動模式
                    self._auto_stop_triggered()
                    break

            if not templates:
                time.sleep(auto_interval)
                continue

            try:
                # ROI 優先掃描：有上次匹配位置且未超過失敗上限時，只截 ROI 區域
                use_roi = (last_match_pos is not None
                           and roi_miss_count < self._roi_max_miss)

                found = False
                all_matches = []

                if use_roi:
                    # --- ROI 掃描（面積約全螢幕 8%，大幅降低 CPU） ---
                    roi_cx, roi_cy = last_match_pos
                    margin = self._roi_margin
                    with mss.mss() as sct:
                        monitor = sct.monitors[0]
                        ox, oy = monitor["left"], monitor["top"]
                        # 將螢幕座標轉為截圖座標
                        sx = roi_cx - ox
                        sy = roi_cy - oy
                        x1 = max(0, sx - margin)
                        y1 = max(0, sy - margin)
                        x2 = min(monitor["width"], sx + margin)
                        y2 = min(monitor["height"], sy + margin)
                        roi_region = {"left": x1 + ox, "top": y1 + oy,
                                      "width": x2 - x1, "height": y2 - y1}
                        screen = np.array(sct.grab(roi_region))

                    screen_bgr = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                    roi_ox = roi_region["left"]
                    roi_oy = roi_region["top"]

                    # ROI 很小，直接做 matchTemplate（跳過 hash 比對）
                    if use_color:
                        screen_match = screen_bgr
                        match_templates = templates
                    else:
                        screen_match = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
                        match_templates = templates_gray

                    for template in match_templates:
                        th, tw = template.shape[:2]
                        if screen_match.shape[0] < th or screen_match.shape[1] < tw:
                            continue
                        matches = self._find_all_matches(
                            screen_match, template, threshold, roi_ox, roi_oy)
                        all_matches.extend(matches)

                    # 去除重複位置
                    if len(all_matches) > 1:
                        unique_matches = []
                        min_dist = 50
                        for cx, cy in all_matches:
                            is_dup = False
                            for ux, uy in unique_matches:
                                if ((cx - ux) ** 2 + (cy - uy) ** 2) ** 0.5 < min_dist:
                                    is_dup = True
                                    break
                            if not is_dup:
                                unique_matches.append((cx, cy))
                        all_matches = unique_matches

                    found = len(all_matches) > 0
                    del screen_bgr, screen, screen_match

                else:
                    # --- 全螢幕掃描（原有邏輯，含 hash 優化） ---
                    with mss.mss() as sct:
                        monitor = sct.monitors[0]
                        screen = np.array(sct.grab(monitor))
                        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                        ox, oy = monitor["left"], monitor["top"]

                    # Hash 比對 (使用內建 hash 更快)
                    small = cv2.resize(screen_bgr, (160, 90))
                    screen_hash = hash(small.tobytes())

                    with self._lock:
                        if screen_hash == self.last_screen_hash:
                            time.sleep(auto_interval)
                            continue
                        self.last_screen_hash = screen_hash

                    # 根據設定選擇匹配模式
                    if use_color:
                        screen_match = screen_bgr
                        match_templates = templates
                    else:
                        screen_match = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
                        match_templates = templates_gray

                    # 收集所有匹配位置（多模板 + 多位置）
                    for template in match_templates:
                        matches = self._find_all_matches(screen_match, template, threshold, ox, oy)
                        all_matches.extend(matches)

                    # 去除重複位置（不同模板可能匹配到同一處）
                    if len(all_matches) > 1:
                        unique_matches = []
                        min_dist = 50
                        for cx, cy in all_matches:
                            is_dup = False
                            for ux, uy in unique_matches:
                                if ((cx - ux) ** 2 + (cy - uy) ** 2) ** 0.5 < min_dist:
                                    is_dup = True
                                    break
                            if not is_dup:
                                unique_matches.append((cx, cy))
                        all_matches = unique_matches

                    found = len(all_matches) > 0
                    del screen_bgr, screen, screen_match

                # --- 過濾被暫時跳過的位置 ---
                with self._lock:
                    sup_pos = self._suppress_pos
                    sup_until = self._suppress_until

                if sup_pos and time.time() < sup_until:
                    all_matches = [
                        (cx, cy) for cx, cy in all_matches
                        if ((cx - sup_pos[0]) ** 2 + (cy - sup_pos[1]) ** 2) ** 0.5 > 80
                    ]
                    found = len(all_matches) > 0
                elif sup_pos:
                    # 過期了，清除 suppress
                    with self._lock:
                        self._suppress_pos = None
                        self._suppress_until = 0

                # --- 處理匹配結果（ROI 和全螢幕共用） ---
                with self._lock:
                    if found:
                        self._roi_miss_count = 0
                    else:
                        self._roi_miss_count += 1

                if found:
                    self._idle_streak = 0
                    logger.info(f"找到 {len(all_matches)} 處匹配")

                    for idx, (cx, cy) in enumerate(all_matches):
                        with self._lock:
                            self._last_match_pos = (cx, cy)

                        if idx == 0:
                            with self._lock:
                                cooldown_passed = continuous_click or (time.time() - self.last_click_time >= self.click_cooldown)
                            if not cooldown_passed:
                                break

                        self._execute_with_retry(cx, cy)

                        with self._lock:
                            self.last_click_time = time.time()
                            self.last_screen_hash = None

                        if idx < len(all_matches) - 1:
                            time.sleep(0.15)
                else:
                    self._idle_streak += 1

                # 動態間隔 + 閒置退避
                if found:
                    sleep_time = auto_interval * 0.5
                else:
                    backoff = auto_interval * (1 + self._idle_streak * 0.15)
                    sleep_time = min(backoff, auto_interval * 2.5)
                time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"自動模式錯誤: {e}")
                time.sleep(auto_interval)

    def on_hotkey(self):
        """熱鍵觸發"""
        with self._lock:
            current_mode = self.mode
            has_templates = len(self.templates) > 0

        if current_mode != "hotkey" or not has_templates:
            return
        threading.Thread(target=self.find_and_click, daemon=True).start()

    def find_and_click(self):
        """手動找圖點擊 - 短路優化"""
        # 執行緒安全：取得參考（不複製）
        with self._lock:
            templates = self.templates
            templates_gray = self.templates_gray
            use_color = self.use_color_match
            threshold = self.similarity_threshold

        if not templates:
            return

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screen = np.array(sct.grab(monitor))
                ox, oy = monitor["left"], monitor["top"]

            # 根據設定選擇匹配模式
            if use_color:
                screen_match = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
                match_templates = templates
            else:
                screen_match = cv2.cvtColor(screen, cv2.COLOR_BGRA2GRAY)
                match_templates = templates_gray

            # 收集所有匹配位置
            all_matches = []
            for template in match_templates:
                matches = self._find_all_matches(screen_match, template, threshold, ox, oy)
                all_matches.extend(matches)

            # 去除重複位置
            if len(all_matches) > 1:
                unique_matches = []
                min_dist = 50
                for cx, cy in all_matches:
                    is_dup = False
                    for ux, uy in unique_matches:
                        if ((cx - ux) ** 2 + (cy - uy) ** 2) ** 0.5 < min_dist:
                            is_dup = True
                            break
                    if not is_dup:
                        unique_matches.append((cx, cy))
                all_matches = unique_matches

            if all_matches:
                logger.info(f"熱鍵: 找到 {len(all_matches)} 處匹配")
                for idx, (cx, cy) in enumerate(all_matches):
                    self._execute_with_retry(cx, cy)
                    if idx < len(all_matches) - 1:
                        time.sleep(0.15)

        except Exception as e:
            logger.error(f"熱鍵點擊錯誤: {e}")

    def quit_app(self, icon=None, item=None):
        """結束"""
        self._save_stats()  # 儲存統計資料
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
    logger.info("=" * 50)
    logger.info("PyClick 啟動")
    logger.info(f"日誌檔案: {log_file}")
    try:
        app = TrayClicker()
        app.run()
    except Exception as e:
        logger.critical(f"程式異常終止: {e}", exc_info=True)
    finally:
        logger.info("PyClick 結束")
