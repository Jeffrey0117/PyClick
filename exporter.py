#!/usr/bin/env python3
"""
PyClick 腳本導出器
將腳本打包成獨立 EXE
"""

import os
import sys
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
import threading

from utils import encode_config, encode_image


def export_script(parent, script, template_path):
    """導出腳本為 EXE"""
    # 檢查 PyInstaller
    try:
        import PyInstaller
    except ImportError:
        if messagebox.askyesno(
            "缺少 PyInstaller",
            "導出需要 PyInstaller，是否自動安裝？\n\n"
            "將執行: pip install pyinstaller",
            parent=parent
        ):
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "pyinstaller"],
                capture_output=True
            )
            if result.returncode != 0:
                messagebox.showerror("安裝失敗", "無法安裝 PyInstaller", parent=parent)
                return
        else:
            return

    # 開啟導出對話框
    ExportDialog(parent, script, template_path)


class ExportDialog:
    """導出對話框"""

    def __init__(self, parent, script, template_path):
        self.parent = parent
        self.script = script
        self.template_path = template_path

        self._create_dialog()

    def _create_dialog(self):
        """建立對話框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("導出 EXE")
        self.dialog.geometry("400x300")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)
        self.dialog.configure(bg="white")

        # 置中
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 400) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 300) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # 標題
        tk.Label(
            self.dialog, text="導出獨立執行檔",
            font=("Microsoft JhengHei", 14, "bold"),
            bg="white"
        ).pack(pady=15)

        # 設定區
        frame = tk.Frame(self.dialog, bg="white", padx=20)
        frame.pack(fill="x")

        # EXE 名稱
        tk.Label(frame, text="程式名稱:", bg="white").grid(row=0, column=0, sticky="w", pady=8)
        self.name_var = tk.StringVar(value=self.script.name or "MyAutoClicker")
        tk.Entry(frame, textvariable=self.name_var, width=30).grid(row=0, column=1, pady=8)

        # 輸出位置
        tk.Label(frame, text="輸出位置:", bg="white").grid(row=1, column=0, sticky="w", pady=8)
        output_frame = tk.Frame(frame, bg="white")
        output_frame.grid(row=1, column=1, sticky="w", pady=8)
        self.output_var = tk.StringVar(value=os.path.expanduser("~/Desktop"))
        tk.Entry(output_frame, textvariable=self.output_var, width=22).pack(side="left")
        tk.Button(output_frame, text="瀏覽", command=self._browse_output).pack(side="left", padx=5)

        # 選項
        self.sound_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame, text="啟用提示音", variable=self.sound_var, bg="white").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=5)

        # 進度
        self.progress_var = tk.StringVar(value="")
        self.progress_label = tk.Label(
            self.dialog, textvariable=self.progress_var,
            fg="gray", bg="white"
        )
        self.progress_label.pack(pady=10)

        # 按鈕
        btn_frame = tk.Frame(self.dialog, bg="white")
        btn_frame.pack(pady=15)

        self.export_btn = tk.Button(
            btn_frame, text="開始導出", command=self._start_export,
            width=12, bg="#4CAF50", fg="white", font=("", 10, "bold")
        )
        self.export_btn.pack(side="left", padx=10)

        tk.Button(
            btn_frame, text="取消", command=self.dialog.destroy, width=12
        ).pack(side="left", padx=10)

    def _browse_output(self):
        """瀏覽輸出位置"""
        path = filedialog.askdirectory(parent=self.dialog)
        if path:
            self.output_var.set(path)

    def _start_export(self):
        """開始導出"""
        self.export_btn.configure(state="disabled")
        self.progress_var.set("準備中...")

        # 在新執行緒中執行
        thread = threading.Thread(target=self._do_export, daemon=True)
        thread.start()

    def _do_export(self):
        """執行導出（在執行緒中）"""
        try:
            self._update_progress("建立設定檔...")

            # 準備設定
            config = {
                "name": self.name_var.get(),
                "scan_interval": 0.5,
                "threshold": 0.7,
                "click_count": self.script.click_count,
                "click_interval": self.script.click_interval,
                "after_key": self.script.after_key,
                "sound_enabled": self.sound_var.get(),
            }

            # 編碼模板圖片
            if self.template_path and os.path.exists(self.template_path):
                config["template_data"] = encode_image(self.template_path)
            else:
                raise Exception("找不到模板圖片")

            # 加密設定
            encrypted_config = encode_config(config)

            # 建立臨時目錄
            self._update_progress("準備打包環境...")
            temp_dir = tempfile.mkdtemp(prefix="pyclick_export_")

            try:
                # 複製 lite_runner.py
                src_dir = os.path.dirname(os.path.abspath(__file__))
                runner_src = os.path.join(src_dir, "lite_runner.py")
                runner_dst = os.path.join(temp_dir, "lite_runner.py")
                shutil.copy(runner_src, runner_dst)

                # 寫入設定檔
                config_path = os.path.join(temp_dir, "config.dat")
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(encrypted_config)

                # 執行 PyInstaller
                self._update_progress("打包中（約需 1 分鐘）...")

                exe_name = self.name_var.get().replace(" ", "_")
                output_dir = self.output_var.get()

                cmd = [
                    sys.executable, "-m", "PyInstaller",
                    "--onefile",
                    "--noconsole",
                    "--name", exe_name,
                    "--distpath", output_dir,
                    "--workpath", os.path.join(temp_dir, "build"),
                    "--specpath", temp_dir,
                    "--add-data", f"{config_path};.",
                    runner_dst
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=temp_dir
                )

                if result.returncode != 0:
                    raise Exception(f"PyInstaller 失敗:\n{result.stderr[:500]}")

                # 完成
                exe_path = os.path.join(output_dir, f"{exe_name}.exe")
                self._update_progress("完成！")
                self.dialog.after(0, lambda: self._show_success(exe_path))

            finally:
                # 清理
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

        except Exception as e:
            self.dialog.after(0, lambda: self._show_error(str(e)))

    def _update_progress(self, message):
        """更新進度"""
        self.dialog.after(0, lambda: self.progress_var.set(message))

    def _show_success(self, exe_path):
        """成功"""
        self.progress_var.set("導出成功！")

        if messagebox.askyesno(
            "導出成功",
            f"EXE 已導出到:\n{exe_path}\n\n要開啟資料夾嗎？",
            parent=self.dialog
        ):
            os.startfile(os.path.dirname(exe_path))

        self.dialog.destroy()

    def _show_error(self, error):
        """失敗"""
        self.progress_var.set("導出失敗")
        self.export_btn.configure(state="normal")
        messagebox.showerror("導出失敗", error, parent=self.dialog)
