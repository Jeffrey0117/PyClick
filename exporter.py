#!/usr/bin/env python3
"""
PyClick 腳本導出器
將腳本打包成獨立 EXE
"""

import os
import sys
import json
import base64
import zlib
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading


def encode_config(config_dict):
    """加密設定"""
    json_str = json.dumps(config_dict, ensure_ascii=False)
    compressed = zlib.compress(json_str.encode())
    encoded = base64.b64encode(compressed)
    return (encoded[::-1] + b"_PYC_").decode()


def encode_image(image_path):
    """編碼圖片為 Base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


class ExportDialog:
    """導出對話框"""

    def __init__(self, parent, script, template_path):
        self.parent = parent
        self.script = script
        self.template_path = template_path
        self.result = None

        self._create_dialog()

    def _create_dialog(self):
        """建立對話框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("導出 EXE")
        self.dialog.geometry("450x350")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)

        # 置中
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 450) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 350) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # 標題
        tk.Label(
            self.dialog, text="導出獨立執行檔",
            font=("Microsoft JhengHei", 14, "bold")
        ).pack(pady=15)

        # 設定區
        settings_frame = ttk.LabelFrame(self.dialog, text="導出設定", padding=15)
        settings_frame.pack(fill="x", padx=20, pady=10)

        # EXE 名稱
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=5)
        ttk.Label(row1, text="程式名稱:").pack(side="left")
        self.name_var = tk.StringVar(value=self.script.name or "MyAutoClicker")
        ttk.Entry(row1, textvariable=self.name_var, width=25).pack(side="right")

        # 輸出位置
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=5)
        ttk.Label(row2, text="輸出位置:").pack(side="left")
        self.output_var = tk.StringVar(value=os.path.expanduser("~/Desktop"))
        ttk.Entry(row2, textvariable=self.output_var, width=20).pack(side="left", padx=5)
        ttk.Button(row2, text="瀏覽", command=self._browse_output, width=6).pack(side="left")

        # 選項
        options_frame = ttk.LabelFrame(self.dialog, text="選項", padding=15)
        options_frame.pack(fill="x", padx=20, pady=10)

        self.sound_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="啟用提示音",
                        variable=self.sound_var).pack(anchor="w")

        self.console_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="顯示命令列視窗（除錯用）",
                        variable=self.console_var).pack(anchor="w")

        # 進度
        self.progress_var = tk.StringVar(value="")
        self.progress_label = tk.Label(
            self.dialog, textvariable=self.progress_var,
            fg="gray", font=("", 9)
        )
        self.progress_label.pack(pady=5)

        self.progress_bar = ttk.Progressbar(self.dialog, mode="indeterminate", length=300)
        self.progress_bar.pack(pady=5)

        # 按鈕
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(pady=15)

        self.export_btn = ttk.Button(
            btn_frame, text="開始導出", command=self._start_export, width=12
        )
        self.export_btn.pack(side="left", padx=10)

        ttk.Button(
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
        self.progress_bar.start()
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
                "scan_interval": self.script.click_interval if hasattr(self.script, 'click_interval') else 0.5,
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
                self._update_progress("打包中（這可能需要一分鐘）...")

                exe_name = self.name_var.get().replace(" ", "_")
                output_dir = self.output_var.get()

                cmd = [
                    sys.executable, "-m", "PyInstaller",
                    "--onefile",
                    "--name", exe_name,
                    "--distpath", output_dir,
                    "--workpath", os.path.join(temp_dir, "build"),
                    "--specpath", temp_dir,
                    "--add-data", f"{config_path};.",
                ]

                if not self.console_var.get():
                    cmd.append("--noconsole")

                cmd.append(runner_dst)

                # 執行
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=temp_dir
                )

                if result.returncode != 0:
                    raise Exception(f"PyInstaller 失敗:\n{result.stderr}")

                # 完成
                exe_path = os.path.join(output_dir, f"{exe_name}.exe")
                self._update_progress(f"完成！")
                self.dialog.after(0, lambda: self._show_success(exe_path))

            finally:
                # 清理臨時目錄
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

        except Exception as e:
            self.dialog.after(0, lambda: self._show_error(str(e)))

    def _update_progress(self, message):
        """更新進度訊息"""
        self.dialog.after(0, lambda: self.progress_var.set(message))

    def _show_success(self, exe_path):
        """顯示成功"""
        self.progress_bar.stop()
        self.progress_var.set("導出成功！")

        if messagebox.askyesno(
            "導出成功",
            f"EXE 已導出到:\n{exe_path}\n\n要開啟所在資料夾嗎？",
            parent=self.dialog
        ):
            os.startfile(os.path.dirname(exe_path))

        self.dialog.destroy()

    def _show_error(self, error):
        """顯示錯誤"""
        self.progress_bar.stop()
        self.progress_var.set("導出失敗")
        self.export_btn.configure(state="normal")
        messagebox.showerror("導出失敗", error, parent=self.dialog)


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
    dialog = ExportDialog(parent, script, template_path)
