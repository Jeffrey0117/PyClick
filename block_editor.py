#!/usr/bin/env python3
"""
PyClick 積木式腳本編輯器
參考 Scratch 設計的簡單積木系統
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import json
import os
import uuid
import cv2
import numpy as np
import mss
import time
import threading
import pyautogui
import ctypes

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

# ============================================================
# 積木類型定義
# ============================================================

BLOCK_COLORS = {
    "trigger": "#9966FF",   # 紫色 - 觸發
    "action": "#4C97FF",    # 藍色 - 動作
    "keyboard": "#59C059",  # 綠色 - 鍵盤
    "wait": "#FFBF00",      # 黃色 - 等待
    "control": "#FF8C1A",   # 橙色 - 控制
}

BLOCK_TYPES = {
    # === 觸發類 ===
    "trigger_hotkey": {
        "category": "trigger",
        "label": "當按下 [{key}] 時",
        "icon": "🎬",
        "params": {"key": "F7"},
        "is_trigger": True,
    },
    "trigger_image": {
        "category": "trigger",
        "label": "當找到 [{image}] 時",
        "icon": "🎬",
        "params": {"image": ""},
        "is_trigger": True,
    },

    # === 動作類 ===
    "click": {
        "category": "action",
        "label": "點擊 [{image}]",
        "icon": "🖱️",
        "params": {"image": ""},
    },
    "click_xy": {
        "category": "action",
        "label": "點擊座標 X:[{x}] Y:[{y}]",
        "icon": "🖱️",
        "params": {"x": 0, "y": 0},
    },
    "right_click": {
        "category": "action",
        "label": "右鍵 [{image}]",
        "icon": "🖱️",
        "params": {"image": ""},
    },
    "double_click": {
        "category": "action",
        "label": "雙擊 [{image}]",
        "icon": "🖱️",
        "params": {"image": ""},
    },
    "scroll": {
        "category": "action",
        "label": "滾輪 [{direction}] [{amount}] 格",
        "icon": "🖲️",
        "params": {"direction": "上", "amount": 3},
    },

    # === 鍵盤類 ===
    "press_key": {
        "category": "keyboard",
        "label": "按 [{key}]",
        "icon": "⌨️",
        "params": {"key": "Enter"},
    },
    "hotkey": {
        "category": "keyboard",
        "label": "按 [{modifier}]+[{key}]",
        "icon": "⌨️",
        "params": {"modifier": "Ctrl", "key": "C"},
    },
    "type_text": {
        "category": "keyboard",
        "label": "輸入 \"{text}\"",
        "icon": "📝",
        "params": {"text": ""},
    },

    # === 等待類 ===
    "wait": {
        "category": "wait",
        "label": "等待 [{seconds}] 秒",
        "icon": "⏱️",
        "params": {"seconds": 1.0},
    },
    "wait_image": {
        "category": "wait",
        "label": "等到 [{image}] 出現",
        "icon": "👁️",
        "params": {"image": "", "timeout": 30},
    },
    "wait_image_gone": {
        "category": "wait",
        "label": "等到 [{image}] 消失",
        "icon": "👁️",
        "params": {"image": "", "timeout": 30},
    },

    # === 控制類 ===
    "repeat": {
        "category": "control",
        "label": "重複 [{count}] 次",
        "icon": "🔁",
        "params": {"count": 3},
        "has_children": True,
    },
    "repeat_until": {
        "category": "control",
        "label": "重複直到 [{image}] 出現",
        "icon": "🔁",
        "params": {"image": "", "max_iterations": 100},
        "has_children": True,
    },
    "if_image": {
        "category": "control",
        "label": "如果 [{image}] 存在",
        "icon": "❓",
        "params": {"image": ""},
        "has_children": True,
    },
}

# 常用按鍵選項
KEY_OPTIONS = [
    "Enter", "Tab", "Escape", "Space", "Backspace", "Delete",
    "Up", "Down", "Left", "Right",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
]

MODIFIER_OPTIONS = ["Ctrl", "Alt", "Shift", "Ctrl+Shift", "Ctrl+Alt", "Alt+Shift"]


# ============================================================
# Block 資料類別
# ============================================================

class Block:
    """積木資料結構"""

    def __init__(self, block_type, params=None, children=None):
        self.id = str(uuid.uuid4())[:8]
        self.type = block_type
        self.params = params or dict(BLOCK_TYPES[block_type]["params"])
        self.children = children or []

    def to_dict(self):
        """轉換為字典"""
        return {
            "id": self.id,
            "type": self.type,
            "params": self.params,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data):
        """從字典建立"""
        block = cls(data["type"], data.get("params"))
        block.id = data.get("id", str(uuid.uuid4())[:8])
        block.children = [cls.from_dict(c) for c in data.get("children", [])]
        return block

    def get_label(self):
        """取得顯示標籤"""
        info = BLOCK_TYPES[self.type]
        label = info["label"]
        for key, value in self.params.items():
            # 圖像參數顯示檔名
            if key == "image" and value:
                display = os.path.basename(value) if value else "(未設定)"
            else:
                display = str(value)
            label = label.replace(f"[{{{key}}}]", f"[{display}]")
        return f"{info['icon']} {label}"

    def get_color(self):
        """取得積木顏色"""
        category = BLOCK_TYPES[self.type]["category"]
        return BLOCK_COLORS[category]

    def has_children(self):
        """是否可包含子積木"""
        return BLOCK_TYPES[self.type].get("has_children", False)

    def is_trigger(self):
        """是否為觸發積木"""
        return BLOCK_TYPES[self.type].get("is_trigger", False)


# ============================================================
# Script 腳本類別
# ============================================================

class Script:
    """腳本資料結構"""

    def __init__(self, name="未命名"):
        self.name = name
        self.blocks = []  # Block 列表

    def to_dict(self):
        return {
            "name": self.name,
            "blocks": [b.to_dict() for b in self.blocks],
        }

    @classmethod
    def from_dict(cls, data):
        script = cls(data.get("name", "未命名"))
        script.blocks = [Block.from_dict(b) for b in data.get("blocks", [])]
        return script

    def save(self, filepath):
        """儲存腳本"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, filepath):
        """載入腳本"""
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# ============================================================
# 積木 UI 元件
# ============================================================

class BlockWidget(tk.Frame):
    """積木視覺元件"""

    def __init__(self, parent, block, editor, depth=0):
        super().__init__(parent, bg=parent["bg"])
        self.block = block
        self.editor = editor
        self.depth = depth
        self.child_widgets = []

        self._create_ui()

    def _create_ui(self):
        """建立 UI"""
        color = self.block.get_color()
        darker = self._darken_color(color)

        # 主積木框
        self.frame = tk.Frame(self, bg=color, padx=2, pady=2)
        self.frame.pack(fill="x", padx=(self.depth * 20, 0), pady=2)

        # 內容區
        content = tk.Frame(self.frame, bg=color)
        content.pack(fill="x", padx=5, pady=5)

        # 標籤
        label = tk.Label(
            content,
            text=self.block.get_label(),
            bg=color,
            fg="white",
            font=("Microsoft JhengHei", 11),
            cursor="hand2",
        )
        label.pack(side="left", padx=5)

        # 綁定事件
        for widget in [self.frame, content, label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Double-Button-1>", self._on_double_click)
            widget.bind("<Button-3>", self._on_right_click)
            # 拖曳事件
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)

        # 刪除按鈕
        del_btn = tk.Label(
            content, text="✕", bg=color, fg="white",
            font=("", 10), cursor="hand2"
        )
        del_btn.pack(side="right", padx=5)
        del_btn.bind("<Button-1>", self._on_delete)

        # 子積木區（如果是控制積木）
        if self.block.has_children():
            child_frame = tk.Frame(self.frame, bg=darker)
            child_frame.pack(fill="x", padx=15, pady=5)

            # 內部放置區
            self.child_container = tk.Frame(child_frame, bg=darker)
            self.child_container.pack(fill="x", padx=5, pady=5)

            # 顯示子積木
            for child_block in self.block.children:
                child_widget = BlockWidget(
                    self.child_container, child_block, self.editor, self.depth + 1
                )
                child_widget.pack(fill="x")
                self.child_widgets.append(child_widget)

            # 放置提示
            if not self.block.children:
                hint = tk.Label(
                    self.child_container,
                    text="拖曳積木到這裡",
                    bg=darker, fg="#AAA",
                    font=("", 9),
                )
                hint.pack(pady=10)

    def _darken_color(self, hex_color):
        """加深顏色"""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        factor = 0.7
        r, g, b = int(r * factor), int(g * factor), int(b * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_click(self, event):
        """選擇積木"""
        self.editor.select_block(self.block)

    def _on_double_click(self, event):
        """編輯積木參數"""
        self.editor.edit_block(self.block)

    def _on_right_click(self, event):
        """右鍵選單"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📝 編輯參數", command=lambda: self.editor.edit_block(self.block))
        menu.add_separator()
        menu.add_command(label="📋 複製", command=lambda: self.editor.copy_block(self.block))
        menu.add_separator()
        menu.add_command(label="⬆️ 上移", command=lambda: self.editor.move_block_up(self.block))
        menu.add_command(label="⬇️ 下移", command=lambda: self.editor.move_block_down(self.block))
        menu.add_separator()
        menu.add_command(label="🗑️ 刪除", command=lambda: self.editor.delete_block(self.block))
        menu.tk_popup(event.x_root, event.y_root)

    def _on_delete(self, event):
        """刪除積木"""
        self.editor.delete_block(self.block)

    def set_executing(self, executing=True):
        """設定執行狀態樣式"""
        if executing:
            self.frame.configure(highlightbackground="#4CAF50", highlightthickness=3)
        else:
            self.frame.configure(highlightthickness=0)

    def set_executed(self):
        """設定已執行樣式（變灰）"""
        self.frame.configure(highlightthickness=0)
        # 可以加淡化效果，但暫時保持簡單

    def _on_drag_start(self, event):
        """開始拖曳"""
        self.drag_start_y = event.y_root
        self.dragging = False

    def _on_drag_motion(self, event):
        """拖曳中"""
        if not hasattr(self, 'drag_start_y'):
            return

        # 移動超過 10 像素才算拖曳
        if abs(event.y_root - self.drag_start_y) > 10:
            self.dragging = True
            self.editor.on_block_drag(self.block, event.y_root)

    def _on_drag_end(self, event):
        """拖曳結束"""
        if hasattr(self, 'dragging') and self.dragging:
            self.editor.on_block_drop(self.block, event.y_root)
        self.dragging = False


# ============================================================
# 積木編輯器主視窗
# ============================================================

class BlockEditor:
    """積木編輯器"""

    def __init__(self, parent=None, templates_dir="templates", scripts_dir="scripts"):
        self.parent = parent
        self.templates_dir = templates_dir
        self.scripts_dir = scripts_dir

        self.script = Script()
        self.selected_block = None
        self.running = False
        self.stop_flag = False

        # 拖曳狀態
        self.drag_block = None
        self.drag_indicator = None
        self.block_widgets = []

        # 確保目錄存在
        os.makedirs(self.scripts_dir, exist_ok=True)

        self._create_window()

    def _create_window(self):
        """建立編輯器視窗"""
        if self.parent:
            self.window = tk.Toplevel(self.parent)
        else:
            self.window = tk.Tk()

        self.window.title("PyClick 腳本編輯器")
        self.window.geometry("900x700")
        self.window.configure(bg="#2D2D2D")

        # === 工具列 ===
        toolbar = tk.Frame(self.window, bg="#3D3D3D", height=40)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        tk.Button(
            toolbar, text="▶ 執行", command=self.run_script,
            bg="#4CAF50", fg="white", font=("", 10, "bold"),
            relief="flat", padx=15
        ).pack(side="left", padx=5, pady=5)

        tk.Button(
            toolbar, text="⏹ 停止", command=self.stop_script,
            bg="#F44336", fg="white", font=("", 10),
            relief="flat", padx=15
        ).pack(side="left", padx=5, pady=5)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10, pady=5)

        tk.Button(
            toolbar, text="💾 儲存", command=self.save_script,
            bg="#555", fg="white", relief="flat", padx=10
        ).pack(side="left", padx=5, pady=5)

        tk.Button(
            toolbar, text="📂 載入", command=self.load_script,
            bg="#555", fg="white", relief="flat", padx=10
        ).pack(side="left", padx=5, pady=5)

        tk.Button(
            toolbar, text="🗑 清空", command=self.clear_script,
            bg="#555", fg="white", relief="flat", padx=10
        ).pack(side="left", padx=5, pady=5)

        # 腳本名稱
        tk.Label(toolbar, text="腳本:", bg="#3D3D3D", fg="white").pack(side="right", padx=(10, 5), pady=5)
        self.name_var = tk.StringVar(value=self.script.name)
        self.name_entry = tk.Entry(toolbar, textvariable=self.name_var, width=20, font=("", 10))
        self.name_entry.pack(side="right", padx=5, pady=5)

        # === 主區域 ===
        main_frame = tk.Frame(self.window, bg="#2D2D2D")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 左側：積木庫
        self._create_block_palette(main_frame)

        # 右側：腳本區
        self._create_script_area(main_frame)

        # === 狀態列 ===
        status_frame = tk.Frame(self.window, bg="#3D3D3D", height=30)
        status_frame.pack(fill="x")
        status_frame.pack_propagate(False)

        self.status_var = tk.StringVar(value="就緒 - 從左側拖曳積木到右側")
        tk.Label(
            status_frame, textvariable=self.status_var,
            bg="#3D3D3D", fg="#AAA", font=("", 9)
        ).pack(side="left", padx=10, pady=5)

        # === 快捷鍵 ===
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """設定快捷鍵"""
        self.window.bind("<Control-s>", lambda e: self.save_script())
        self.window.bind("<Control-S>", lambda e: self.save_script())
        self.window.bind("<F5>", lambda e: self.run_script())
        self.window.bind("<Escape>", lambda e: self.stop_script())
        self.window.bind("<Delete>", lambda e: self._delete_selected())

    def _delete_selected(self):
        """刪除選中的積木"""
        if self.selected_block:
            self.delete_block(self.selected_block)

    def _create_block_palette(self, parent):
        """建立積木庫"""
        palette_frame = tk.Frame(parent, bg="#3D3D3D", width=200)
        palette_frame.pack(side="left", fill="y", padx=(0, 10))
        palette_frame.pack_propagate(False)

        tk.Label(
            palette_frame, text="📦 積木庫",
            bg="#3D3D3D", fg="white", font=("Microsoft JhengHei", 12, "bold")
        ).pack(pady=10)

        # 滾動區域
        canvas = tk.Canvas(palette_frame, bg="#3D3D3D", highlightthickness=0)
        scrollbar = ttk.Scrollbar(palette_frame, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg="#3D3D3D")

        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 滑鼠滾輪
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # 按類別分組
        categories = [
            ("觸發", "trigger", ["trigger_hotkey", "trigger_image"]),
            ("動作", "action", ["click", "click_xy", "right_click", "double_click", "scroll"]),
            ("鍵盤", "keyboard", ["press_key", "hotkey", "type_text"]),
            ("等待", "wait", ["wait", "wait_image", "wait_image_gone"]),
            ("控制", "control", ["repeat", "repeat_until", "if_image"]),
        ]

        for cat_name, cat_key, block_types in categories:
            color = BLOCK_COLORS[cat_key]

            # 類別標題
            tk.Label(
                scrollable, text=f"── {cat_name} ──",
                bg="#3D3D3D", fg=color, font=("", 9)
            ).pack(pady=(15, 5))

            # 積木按鈕
            for bt in block_types:
                info = BLOCK_TYPES[bt]
                btn = tk.Label(
                    scrollable,
                    text=f"{info['icon']} {info['label'].split('[')[0].strip()}",
                    bg=color, fg="white",
                    font=("Microsoft JhengHei", 10),
                    padx=10, pady=5,
                    cursor="hand2",
                    relief="raised",
                )
                btn.pack(fill="x", padx=10, pady=2)
                btn.bind("<Button-1>", lambda e, t=bt: self.add_block_from_palette(t))

    def _create_script_area(self, parent):
        """建立腳本區"""
        script_frame = tk.Frame(parent, bg="#252525")
        script_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            script_frame, text="📜 腳本",
            bg="#252525", fg="white", font=("Microsoft JhengHei", 12, "bold")
        ).pack(pady=10)

        # 滾動區域
        canvas_frame = tk.Frame(script_frame, bg="#252525")
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.script_canvas = tk.Canvas(canvas_frame, bg="#1E1E1E", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.script_canvas.yview)

        self.script_container = tk.Frame(self.script_canvas, bg="#1E1E1E")
        self.script_container.bind(
            "<Configure>",
            lambda e: self.script_canvas.configure(scrollregion=self.script_canvas.bbox("all"))
        )

        self.script_canvas.create_window((0, 0), window=self.script_container, anchor="nw", width=650)
        self.script_canvas.configure(yscrollcommand=scrollbar.set)

        self.script_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 初始提示
        self._show_empty_hint()

    def _show_empty_hint(self):
        """顯示空白提示"""
        for widget in self.script_container.winfo_children():
            widget.destroy()

        if not self.script.blocks:
            hint = tk.Label(
                self.script_container,
                text="點擊左側積木添加到腳本\n\n建議先添加「觸發」積木",
                bg="#1E1E1E", fg="#666",
                font=("Microsoft JhengHei", 12),
                justify="center",
            )
            hint.pack(pady=50)

    def refresh_script_view(self):
        """重新整理腳本顯示"""
        for widget in self.script_container.winfo_children():
            widget.destroy()

        self.block_widgets = []

        if not self.script.blocks:
            self._show_empty_hint()
            return

        for block in self.script.blocks:
            widget = BlockWidget(self.script_container, block, self)
            widget.pack(fill="x", pady=2)
            self.block_widgets.append(widget)

    def add_block_from_palette(self, block_type):
        """從積木庫添加積木"""
        block = Block(block_type)

        # 如果是觸發積木，插入最前面
        if block.is_trigger():
            # 檢查是否已有觸發積木
            if self.script.blocks and self.script.blocks[0].is_trigger():
                if not messagebox.askyesno("替換觸發", "已有觸發積木，是否替換？"):
                    return
                self.script.blocks[0] = block
            else:
                self.script.blocks.insert(0, block)
        else:
            # 如果選中了控制積木，添加為子積木
            if self.selected_block and self.selected_block.has_children():
                self.selected_block.children.append(block)
            else:
                self.script.blocks.append(block)

        self.refresh_script_view()
        self.status_var.set(f"已添加: {block.get_label()}")

        # 如果需要設定圖像，自動開啟編輯
        if "image" in block.params and not block.params.get("image"):
            self.edit_block(block)

    def select_block(self, block):
        """選擇積木"""
        self.selected_block = block
        self.status_var.set(f"已選擇: {block.get_label()}")

    def edit_block(self, block):
        """編輯積木參數"""
        dialog = BlockParamDialog(self.window, block, self.templates_dir)
        if dialog.result:
            block.params = dialog.result
            self.refresh_script_view()
            self.status_var.set(f"已更新: {block.get_label()}")

    def copy_block(self, block):
        """複製積木"""
        new_block = Block(block.type, dict(block.params))
        idx = self._find_block_index(block)
        if idx is not None:
            self.script.blocks.insert(idx + 1, new_block)
            self.refresh_script_view()
            self.status_var.set("已複製積木")

    def delete_block(self, block, confirm=True):
        """刪除積木"""
        # 如果積木有子積木，要確認
        if confirm and block.has_children() and block.children:
            if not messagebox.askyesno("確認刪除", f"此積木包含 {len(block.children)} 個子積木，確定要刪除嗎？"):
                return

        if self._remove_block(self.script.blocks, block):
            if self.selected_block == block:
                self.selected_block = None
            self.refresh_script_view()
            self.status_var.set("已刪除積木")

    def move_block_up(self, block):
        """上移積木"""
        idx = self._find_block_index(block)
        if idx is not None and idx > 0:
            # 不能移到觸發積木前面
            if idx == 1 and self.script.blocks[0].is_trigger():
                self.status_var.set("不能移到觸發積木前面")
                return
            self.script.blocks[idx], self.script.blocks[idx - 1] = \
                self.script.blocks[idx - 1], self.script.blocks[idx]
            self.refresh_script_view()
            self.status_var.set("已上移")

    def move_block_down(self, block):
        """下移積木"""
        idx = self._find_block_index(block)
        if idx is not None and idx < len(self.script.blocks) - 1:
            # 觸發積木不能下移
            if block.is_trigger():
                self.status_var.set("觸發積木必須在最前面")
                return
            self.script.blocks[idx], self.script.blocks[idx + 1] = \
                self.script.blocks[idx + 1], self.script.blocks[idx]
            self.refresh_script_view()
            self.status_var.set("已下移")

    def on_block_drag(self, block, y_pos):
        """積木拖曳中"""
        self.drag_block = block

        # 計算目標位置
        target_idx = self._get_drop_index(y_pos)

        # 顯示插入指示線
        self._show_drop_indicator(target_idx)
        self.status_var.set(f"拖曳中... 放開以移動到位置 {target_idx + 1}")

    def on_block_drop(self, block, y_pos):
        """積木放下"""
        if not self.drag_block:
            return

        target_idx = self._get_drop_index(y_pos)
        current_idx = self._find_block_index(block)

        # 隱藏指示線
        self._hide_drop_indicator()

        if current_idx is None or target_idx == current_idx:
            self.drag_block = None
            return

        # 不能移到觸發積木前面
        if target_idx == 0 and self.script.blocks and self.script.blocks[0].is_trigger() and not block.is_trigger():
            self.status_var.set("不能移到觸發積木前面")
            self.drag_block = None
            return

        # 觸發積木只能在最前面
        if block.is_trigger() and target_idx > 0:
            self.status_var.set("觸發積木必須在最前面")
            self.drag_block = None
            return

        # 移動積木
        self.script.blocks.pop(current_idx)
        if target_idx > current_idx:
            target_idx -= 1
        self.script.blocks.insert(target_idx, block)

        self.drag_block = None
        self.refresh_script_view()
        self.status_var.set("已移動積木")

    def _get_drop_index(self, y_pos):
        """根據 Y 座標計算放置索引"""
        if not self.block_widgets:
            return 0

        for i, widget in enumerate(self.block_widgets):
            try:
                widget_y = widget.winfo_rooty()
                widget_h = widget.winfo_height()
                if y_pos < widget_y + widget_h // 2:
                    return i
            except:
                pass

        return len(self.script.blocks)

    def _show_drop_indicator(self, index):
        """顯示放置指示線"""
        self._hide_drop_indicator()

        if not self.block_widgets:
            return

        # 在目標位置顯示藍線
        try:
            if index < len(self.block_widgets):
                target_widget = self.block_widgets[index]
                self.drag_indicator = tk.Frame(
                    self.script_container, bg="#2196F3", height=3
                )
                self.drag_indicator.place(
                    x=0, y=target_widget.winfo_y(), relwidth=1
                )
            elif self.block_widgets:
                # 放在最後
                last_widget = self.block_widgets[-1]
                self.drag_indicator = tk.Frame(
                    self.script_container, bg="#2196F3", height=3
                )
                self.drag_indicator.place(
                    x=0, y=last_widget.winfo_y() + last_widget.winfo_height(),
                    relwidth=1
                )
        except:
            pass

    def _hide_drop_indicator(self):
        """隱藏放置指示線"""
        if self.drag_indicator:
            self.drag_indicator.destroy()
            self.drag_indicator = None

    def highlight_executing_block(self, block):
        """高亮正在執行的積木"""
        def _update():
            for widget in self.block_widgets:
                if widget.block == block:
                    widget.set_executing(True)
                else:
                    widget.set_executing(False)
        self.window.after(0, _update)

    def clear_highlight(self):
        """清除所有高亮"""
        def _update():
            for widget in self.block_widgets:
                widget.set_executing(False)
        self.window.after(0, _update)

    def _find_block_index(self, block, blocks=None):
        """尋找積木索引"""
        if blocks is None:
            blocks = self.script.blocks
        for i, b in enumerate(blocks):
            if b.id == block.id:
                return i
        return None

    def _remove_block(self, blocks, target):
        """遞迴刪除積木"""
        for i, b in enumerate(blocks):
            if b.id == target.id:
                blocks.pop(i)
                return True
            if b.children and self._remove_block(b.children, target):
                return True
        return False

    def clear_script(self):
        """清空腳本"""
        if self.script.blocks:
            if messagebox.askyesno("確認", "確定要清空腳本嗎？"):
                self.script.blocks.clear()
                self.selected_block = None
                self.refresh_script_view()
                self.status_var.set("腳本已清空")

    def save_script(self):
        """儲存腳本"""
        self.script.name = self.name_var.get() or "未命名"
        filepath = os.path.join(self.scripts_dir, f"{self.script.name}.json")
        self.script.save(filepath)
        self.status_var.set(f"已儲存: {filepath}")

    def load_script(self):
        """載入腳本"""
        # 列出所有腳本
        files = [f[:-5] for f in os.listdir(self.scripts_dir) if f.endswith(".json")]
        if not files:
            messagebox.showinfo("提示", "沒有已儲存的腳本")
            return

        # 選擇腳本
        dialog = ScriptSelectDialog(self.window, files)
        if dialog.result:
            filepath = os.path.join(self.scripts_dir, f"{dialog.result}.json")
            self.script = Script.load(filepath)
            self.name_var.set(self.script.name)
            self.refresh_script_view()
            self.status_var.set(f"已載入: {dialog.result}")

    def run_script(self):
        """執行腳本"""
        if not self.script.blocks:
            messagebox.showwarning("提示", "腳本是空的！")
            return

        if self.running:
            return

        self.running = True
        self.stop_flag = False
        self.status_var.set("執行中...")

        # 在新執行緒執行
        thread = threading.Thread(target=self._execute_script, daemon=True)
        thread.start()

    def stop_script(self):
        """停止執行"""
        self.stop_flag = True
        self.status_var.set("正在停止...")

    def _execute_script(self):
        """執行腳本（在執行緒中）"""
        try:
            runner = ScriptRunner(self)
            runner.run(self.script.blocks)
        except Exception as e:
            self.window.after(0, lambda: self.status_var.set(f"錯誤: {e}"))
        finally:
            self.running = False
            self.clear_highlight()
            if not self.stop_flag:
                self.window.after(0, lambda: self.status_var.set("執行完成"))
            else:
                self.window.after(0, lambda: self.status_var.set("已停止"))

    def run(self):
        """啟動編輯器"""
        if self.parent is None:
            self.window.mainloop()


# ============================================================
# 參數編輯對話框
# ============================================================

class BlockParamDialog:
    """積木參數編輯對話框"""

    def __init__(self, parent, block, templates_dir):
        self.result = None
        self.block = block
        self.templates_dir = templates_dir
        self.params = dict(block.params)

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("編輯積木參數")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._create_ui()
        self.dialog.wait_window()

    def _create_ui(self):
        """建立 UI"""
        # 標題
        tk.Label(
            self.dialog,
            text=self.block.get_label(),
            font=("Microsoft JhengHei", 12, "bold")
        ).pack(pady=10)

        # 參數區
        params_frame = tk.Frame(self.dialog)
        params_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.widgets = {}

        for key, value in self.params.items():
            row = tk.Frame(params_frame)
            row.pack(fill="x", pady=5)

            label_text = self._get_param_label(key)
            tk.Label(row, text=f"{label_text}:", width=12, anchor="e").pack(side="left")

            if key == "image":
                # 圖像選擇
                self._create_image_selector(row, key, value)
            elif key == "key":
                # 按鍵選擇
                var = tk.StringVar(value=value)
                combo = ttk.Combobox(row, textvariable=var, values=KEY_OPTIONS, width=15)
                combo.pack(side="left", padx=5)
                self.widgets[key] = var
            elif key == "modifier":
                # 修飾鍵選擇
                var = tk.StringVar(value=value)
                combo = ttk.Combobox(row, textvariable=var, values=MODIFIER_OPTIONS, width=15)
                combo.pack(side="left", padx=5)
                self.widgets[key] = var
            elif key == "direction":
                # 方向選擇
                var = tk.StringVar(value=value)
                combo = ttk.Combobox(row, textvariable=var, values=["上", "下"], width=10)
                combo.pack(side="left", padx=5)
                self.widgets[key] = var
            elif isinstance(value, (int, float)):
                # 數字輸入
                var = tk.StringVar(value=str(value))
                entry = tk.Entry(row, textvariable=var, width=10)
                entry.pack(side="left", padx=5)
                self.widgets[key] = var
            else:
                # 文字輸入
                var = tk.StringVar(value=str(value))
                entry = tk.Entry(row, textvariable=var, width=25)
                entry.pack(side="left", padx=5)
                self.widgets[key] = var

        # 按鈕
        btn_frame = tk.Frame(self.dialog)
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="確定", command=self._on_ok, width=10).pack(side="left", padx=10)
        tk.Button(btn_frame, text="取消", command=self.dialog.destroy, width=10).pack(side="left", padx=10)

    def _get_param_label(self, key):
        """取得參數中文標籤"""
        labels = {
            "image": "圖像模板",
            "key": "按鍵",
            "modifier": "修飾鍵",
            "text": "文字",
            "seconds": "秒數",
            "count": "次數",
            "x": "X 座標",
            "y": "Y 座標",
            "direction": "方向",
            "amount": "格數",
            "timeout": "逾時(秒)",
            "max_iterations": "最大次數",
        }
        return labels.get(key, key)

    def _create_image_selector(self, parent, key, value):
        """建立圖像選擇器"""
        frame = tk.Frame(parent)
        frame.pack(side="left", padx=5)

        var = tk.StringVar(value=value)
        self.widgets[key] = var

        # 顯示當前選擇
        display = os.path.basename(value) if value else "(未選擇)"
        label = tk.Label(frame, text=display, width=15, anchor="w", fg="blue")
        label.pack(side="left")

        def select_image():
            templates = [f for f in os.listdir(self.templates_dir) if f.endswith(".png")]
            if not templates:
                messagebox.showinfo("提示", "沒有已儲存的模板，請先在主程式截圖儲存")
                return

            dialog = ImageSelectDialog(self.dialog, self.templates_dir, templates)
            if dialog.result:
                filepath = os.path.join(self.templates_dir, dialog.result)
                var.set(filepath)
                label.config(text=dialog.result)

        tk.Button(frame, text="選擇...", command=select_image).pack(side="left", padx=5)

    def _on_ok(self):
        """確定"""
        for key, widget in self.widgets.items():
            value = widget.get()

            # 轉換數字類型
            original = self.params[key]
            if isinstance(original, int):
                try:
                    value = int(value)
                except ValueError:
                    value = original
            elif isinstance(original, float):
                try:
                    value = float(value)
                except ValueError:
                    value = original

            self.params[key] = value

        self.result = self.params
        self.dialog.destroy()


# ============================================================
# 圖像選擇對話框
# ============================================================

class ImageSelectDialog:
    """圖像選擇對話框"""

    def __init__(self, parent, templates_dir, templates):
        self.result = None
        self.templates_dir = templates_dir

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("選擇圖像模板")
        self.dialog.geometry("400x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        tk.Label(self.dialog, text="選擇圖像模板", font=("", 12, "bold")).pack(pady=10)

        # 列表
        list_frame = tk.Frame(self.dialog)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.listbox = tk.Listbox(list_frame, font=("", 11))
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        for t in templates:
            self.listbox.insert(tk.END, t)

        self.listbox.bind("<Double-Button-1>", lambda e: self._on_ok())

        # 預覽
        self.preview_label = tk.Label(self.dialog, text="(選擇後預覽)", fg="gray")
        self.preview_label.pack(pady=10)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # 按鈕
        btn_frame = tk.Frame(self.dialog)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="確定", command=self._on_ok, width=10).pack(side="left", padx=10)
        tk.Button(btn_frame, text="取消", command=self.dialog.destroy, width=10).pack(side="left", padx=10)

        self.dialog.wait_window()

    def _on_select(self, event):
        """選擇變更時預覽"""
        selection = self.listbox.curselection()
        if not selection:
            return

        name = self.listbox.get(selection[0])
        filepath = os.path.join(self.templates_dir, name)

        try:
            img = cv2.imread(filepath)
            if img is not None:
                h, w = img.shape[:2]
                scale = min(100 / w, 80 / h, 1.0)
                img = cv2.resize(img, (int(w * scale), int(h * scale)))
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                photo = ImageTk.PhotoImage(Image.fromarray(img))
                self.preview_label.config(image=photo, text="")
                self.preview_label.image = photo
        except Exception:
            pass

    def _on_ok(self):
        """確定"""
        selection = self.listbox.curselection()
        if selection:
            self.result = self.listbox.get(selection[0])
        self.dialog.destroy()


# ============================================================
# 腳本選擇對話框
# ============================================================

class ScriptSelectDialog:
    """腳本選擇對話框"""

    def __init__(self, parent, scripts):
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("選擇腳本")
        self.dialog.geometry("300x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        tk.Label(self.dialog, text="選擇腳本", font=("", 12, "bold")).pack(pady=10)

        # 列表
        list_frame = tk.Frame(self.dialog)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.listbox = tk.Listbox(list_frame, font=("", 11))
        self.listbox.pack(side="left", fill="both", expand=True)

        for s in scripts:
            self.listbox.insert(tk.END, s)

        self.listbox.bind("<Double-Button-1>", lambda e: self._on_ok())

        # 按鈕
        btn_frame = tk.Frame(self.dialog)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="載入", command=self._on_ok, width=10).pack(side="left", padx=10)
        tk.Button(btn_frame, text="取消", command=self.dialog.destroy, width=10).pack(side="left", padx=10)

        self.dialog.wait_window()

    def _on_ok(self):
        selection = self.listbox.curselection()
        if selection:
            self.result = self.listbox.get(selection[0])
        self.dialog.destroy()


# ============================================================
# 腳本執行引擎
# ============================================================

class ScriptRunner:
    """腳本執行引擎"""

    def __init__(self, editor):
        self.editor = editor
        self.threshold = 0.7

    def run(self, blocks):
        """執行積木列表"""
        for block in blocks:
            if self.editor.stop_flag:
                break
            self._execute_block(block)

    def _execute_block(self, block):
        """執行單個積木"""
        if self.editor.stop_flag:
            return

        action = block.type
        params = block.params

        # 高亮當前積木
        self.editor.highlight_executing_block(block)

        # 更新狀態
        self.editor.window.after(0, lambda: self.editor.status_var.set(f"執行: {block.get_label()}"))

        # 根據類型執行
        if action == "trigger_hotkey" or action == "trigger_image":
            # 觸發積木只是標記，實際觸發邏輯在外部
            pass

        elif action == "click":
            self._click_image(params["image"])

        elif action == "click_xy":
            self._click_xy(params["x"], params["y"])

        elif action == "right_click":
            self._right_click_image(params["image"])

        elif action == "double_click":
            self._double_click_image(params["image"])

        elif action == "scroll":
            self._scroll(params["direction"], params["amount"])

        elif action == "press_key":
            self._press_key(params["key"])

        elif action == "hotkey":
            self._hotkey(params["modifier"], params["key"])

        elif action == "type_text":
            self._type_text(params["text"])

        elif action == "wait":
            time.sleep(params["seconds"])

        elif action == "wait_image":
            self._wait_image(params["image"], params.get("timeout", 30))

        elif action == "wait_image_gone":
            self._wait_image_gone(params["image"], params.get("timeout", 30))

        elif action == "repeat":
            for i in range(params["count"]):
                if self.editor.stop_flag:
                    break
                self.run(block.children)

        elif action == "repeat_until":
            max_iter = params.get("max_iterations", 100)
            for i in range(max_iter):
                if self.editor.stop_flag:
                    break
                if self._find_image(params["image"]):
                    break
                self.run(block.children)

        elif action == "if_image":
            if self._find_image(params["image"]):
                self.run(block.children)

    def _find_image(self, template_path):
        """尋找圖像，回傳位置或 None"""
        if not template_path or not os.path.exists(template_path):
            return None

        template = cv2.imread(template_path)
        if template is None:
            return None

        with mss.mss() as sct:
            screen = np.array(sct.grab(sct.monitors[0]))
            screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= self.threshold:
            h, w = template.shape[:2]
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            return (cx, cy)
        return None

    def _click_image(self, template_path):
        """點擊圖像"""
        pos = self._find_image(template_path)
        if pos:
            self._click_xy(pos[0], pos[1])

    def _click_xy(self, x, y):
        """點擊座標"""
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.05)

    def _right_click_image(self, template_path):
        """右鍵點擊圖像"""
        pos = self._find_image(template_path)
        if pos:
            user32.SetCursorPos(int(pos[0]), int(pos[1]))
            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            time.sleep(0.05)

    def _double_click_image(self, template_path):
        """雙擊圖像"""
        pos = self._find_image(template_path)
        if pos:
            self._click_xy(pos[0], pos[1])
            time.sleep(0.05)
            self._click_xy(pos[0], pos[1])

    def _scroll(self, direction, amount):
        """滾輪"""
        scroll_amount = amount if direction == "上" else -amount
        pyautogui.scroll(scroll_amount)

    def _press_key(self, key):
        """按鍵"""
        pyautogui.press(key.lower())

    def _hotkey(self, modifier, key):
        """組合鍵"""
        keys = modifier.lower().split("+") + [key.lower()]
        pyautogui.hotkey(*keys)

    def _type_text(self, text):
        """輸入文字"""
        pyautogui.typewrite(text, interval=0.05)

    def _wait_image(self, template_path, timeout):
        """等待圖像出現"""
        start = time.time()
        while time.time() - start < timeout:
            if self.editor.stop_flag:
                break
            if self._find_image(template_path):
                return True
            time.sleep(0.5)
        return False

    def _wait_image_gone(self, template_path, timeout):
        """等待圖像消失"""
        start = time.time()
        while time.time() - start < timeout:
            if self.editor.stop_flag:
                break
            if not self._find_image(template_path):
                return True
            time.sleep(0.5)
        return False


# ============================================================
# 主程式入口
# ============================================================

if __name__ == "__main__":
    editor = BlockEditor()
    editor.run()
