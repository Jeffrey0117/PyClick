#!/usr/bin/env python3
"""
PyClick 共用工具模組
"""

import ctypes
from ctypes import wintypes
import time
import json
import base64
import zlib
import pyautogui

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# WindowFromPoint：取得指定座標的視窗 handle
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND

# GetAncestor：取得頂層視窗
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wintypes.HWND

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

# 預設常數
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_CLICK_COOLDOWN = 1.0
DEFAULT_SCAN_INTERVAL = 0.5
DEFAULT_HOTKEY = 'f6'
ROI_MARGIN = 200


def get_window_at(x, y):
    """取得指定座標的頂層視窗 handle"""
    GA_ROOT = 2
    hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if hwnd:
        root = user32.GetAncestor(hwnd, GA_ROOT)
        return root if root else hwnd
    return hwnd


def force_focus(hwnd):
    """強制恢復視窗焦點"""
    if not hwnd:
        return

    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    attached = False

    try:
        # 附加執行緒輸入
        if target_thread != current_thread:
            user32.AttachThreadInput(current_thread, target_thread, True)
            attached = True

        # 恢復焦點（即使失敗也要確保分離）
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SetActiveWindow(hwnd)
    finally:
        # 保證分離執行緒輸入（避免殘留）
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def click_no_focus(x, y, instant=True):
    """點擊但不改變焦點"""
    original_pos = pyautogui.position()
    foreground_hwnd = user32.GetForegroundWindow()
    user32.SetCursorPos(x, y)
    if instant:
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    else:
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.01)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.02)
    user32.SetCursorPos(original_pos[0], original_pos[1])
    force_focus(foreground_hwnd)


def encode_config(config_dict):
    """編碼設定"""
    json_str = json.dumps(config_dict, ensure_ascii=False)
    compressed = zlib.compress(json_str.encode())
    encoded = base64.b64encode(compressed)
    return (encoded[::-1] + b"_PYC_").decode()


def decode_config(encoded_data):
    """解碼設定"""
    try:
        if isinstance(encoded_data, str):
            encoded_data = encoded_data.encode()
        cleaned = encoded_data[:-5][::-1]
        compressed = base64.b64decode(cleaned)
        return json.loads(zlib.decompress(compressed).decode())
    except:
        return None


def encode_image(image_path):
    """編碼圖片為 Base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def check_single_instance(mutex_name="PyClick_SingleInstance_Mutex"):
    """確保只有一個實例運行"""
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return False
    return True
