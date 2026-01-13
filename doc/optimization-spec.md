# PyClick 優化規格文檔

> 版本: 1.0.0
> 建立日期: 2026-01-13
> 狀態: 進行中

---

## 目錄

1. [概述](#1-概述)
2. [Phase 1: 執行緒安全](#2-phase-1-執行緒安全)
3. [Phase 2: 效能優化](#3-phase-2-效能優化)
4. [Phase 3: 程式碼整理](#4-phase-3-程式碼整理)
5. [Phase 4: UX 改善](#5-phase-4-ux-改善)
6. [Phase 5: 錯誤處理](#6-phase-5-錯誤處理)
7. [變更紀錄](#7-變更紀錄)

---

## 1. 概述

### 1.1 目標

將 PyClick 從 MVP 階段提升至生產品質，涵蓋：

- **效能**: 降低 CPU 使用率 30-40%，減少記憶體占用
- **穩定性**: 消除執行緒競爭條件，防止罕見當機
- **可維護性**: 消除重複程式碼，建立共用模組
- **使用者體驗**: 即時回饋、可設定參數、更好的錯誤提示

### 1.2 影響範圍

| 檔案 | 變更類型 | 預期影響 |
|------|----------|----------|
| `tray_clicker.py` | 重構 | 高 |
| `block_editor.py` | 小幅修改 | 中 |
| `lite_runner.py` | 小幅修改 | 低 |
| `utils.py` | 新建 | - |
| `config.json` | 擴展 | 低 |

### 1.3 開發原則

1. **規格先行**: 每個 Phase 開始前更新此文檔
2. **階段性提交**: 每個 Phase 完成後 commit + push
3. **向後相容**: 現有設定檔和腳本必須繼續運作
4. **最小變更**: 只改必要的部分，不做不必要的重構

---

## 2. Phase 1: 執行緒安全

### 2.1 問題描述

目前多個執行緒共享以下變數，但缺乏適當的鎖保護：

```python
# tray_clicker.py 中的共享狀態
self.mode          # UI 執行緒寫入，auto_loop 執行緒讀取
self.template      # UI 執行緒寫入，auto_loop 執行緒讀取
self.screenshot    # UI 執行緒寫入，可能同時被讀取
```

### 2.2 解決方案

擴展現有 `self._lock` 的使用範圍：

```python
# 新增保護的操作
with self._lock:
    mode = self.mode
    template = self.template.copy() if self.template is not None else None
```

### 2.3 變更清單

| 檔案 | 行號 | 變更內容 |
|------|------|----------|
| `tray_clicker.py` | ~1430 | `_auto_loop` 讀取 mode/template 時加鎖 |
| `tray_clicker.py` | ~800 | `set_mode` 寫入時加鎖 |
| `tray_clicker.py` | ~600 | `apply_selection` 設定 template 時加鎖 |

### 2.4 測試驗證

- [x] 快速切換模式 (off → auto → hotkey → off) 不當機
- [ ] 自動模式運行時修改設定不當機
- [ ] 長時間運行 (1小時+) 穩定

### 2.5 狀態

- [x] 規格完成
- [x] 實作完成
- [ ] 測試通過
- [x] 已提交

---

## 3. Phase 2: 效能優化

### 3.1 問題描述

1. **螢幕雜湊**: 使用 MD5 計算雜湊，效能不佳
2. **模板匹配**: 每次都全螢幕搜尋，4K 螢幕耗時
3. **記憶體**: 持續保留完整截圖

### 3.2 解決方案

#### 3.2.1 改用更快的雜湊演算法

```python
# 現況
import hashlib
screen_hash = hashlib.md5(small.tobytes()).hexdigest()

# 改善：使用內建 hash (快 5-10 倍)
screen_hash = hash(small.tobytes())
```

#### 3.2.2 ROI (感興趣區域) 模板匹配

```python
# 新增屬性
self._last_match_pos = None  # (x, y) 上次找到的位置
self._roi_margin = 200       # ROI 邊距像素

# 匹配邏輯
if self._last_match_pos:
    # 先在上次位置附近搜尋
    roi = extract_roi(screen, self._last_match_pos, margin=200)
    result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    if max_val >= threshold:
        # 找到了，更新位置
        ...
    else:
        # ROI 沒找到，回退到全螢幕
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
```

#### 3.2.3 記憶體優化

- 匹配完成後不保留截圖
- 使用 `del` 明確釋放大型陣列

### 3.3 變更清單

| 檔案 | 變更內容 |
|------|----------|
| `tray_clicker.py` | 雜湊演算法改用 `hash()` |
| `tray_clicker.py` | 新增 `_last_match_pos` 追蹤 |
| `tray_clicker.py` | 新增 `_extract_roi()` 方法 |
| `tray_clicker.py` | `_auto_loop` 加入 ROI 邏輯 |

### 3.4 效能指標

| 指標 | 優化前 | 目標 |
|------|--------|------|
| CPU 使用率 (自動模式) | ~15-20% | <10% |
| 單次匹配時間 (4K) | ~50ms | ~20ms |
| 記憶體占用 | ~150MB | ~80MB |

### 3.5 狀態

- [x] 規格完成
- [x] 實作完成
- [ ] 效能驗證
- [x] 已提交

---

## 4. Phase 3: 程式碼整理

### 4.1 問題描述

1. 重複程式碼散落多個檔案
2. 魔術數字未統一管理
3. 無共用工具模組

### 4.2 解決方案

#### 4.2.1 建立 `utils.py` 共用模組

```python
# utils.py - 共用工具函數

import ctypes
from ctypes import wintypes

# ===== 滑鼠操作 =====
def click_no_focus(x: int, y: int) -> None:
    """在指定座標點擊，不搶奪焦點"""
    ...

def get_foreground_window() -> int:
    """取得目前前景視窗 handle"""
    ...

def force_focus(hwnd: int) -> None:
    """強制將焦點還給指定視窗"""
    ...

# ===== 設定編碼 =====
def encode_config(data: dict) -> str:
    """編碼設定為字串 (zlib + base64 + 混淆)"""
    ...

def decode_config(encoded: str) -> dict:
    """解碼設定字串"""
    ...

# ===== 常數 =====
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_CLICK_COOLDOWN = 1.0
DEFAULT_SCAN_INTERVAL = 0.5
DEFAULT_HOTKEY = 'f6'
ROI_MARGIN = 200
```

#### 4.2.2 重構影響的檔案

| 檔案 | 移除的重複程式碼 | 改為引用 |
|------|------------------|----------|
| `tray_clicker.py` | `click_no_focus()` 等 | `from utils import ...` |
| `block_editor.py` | 點擊相關函數 | `from utils import ...` |
| `lite_runner.py` | `decode_config()` | `from utils import ...` |
| `exporter.py` | `encode_config()` | `from utils import ...` |

### 4.3 變更清單

| 檔案 | 變更內容 |
|------|----------|
| `utils.py` | 新建，包含共用函數和常數 |
| `tray_clicker.py` | 移除重複函數，改為引用 |
| `block_editor.py` | 移除重複函數，改為引用 |
| `lite_runner.py` | 移除 decode_config，改為引用 |
| `exporter.py` | 移除 encode_config，改為引用 |

### 4.4 狀態

- [x] 規格完成
- [x] 實作完成
- [ ] 測試通過
- [x] 已提交

---

## 5. Phase 4: UX 改善

### 5.1 問題描述

1. 自動模式缺乏即時回饋
2. 關鍵參數無法設定
3. 截圖操作缺少復原功能

### 5.2 解決方案

#### 5.2.1 新增可設定參數

擴展設定面板，新增以下選項：

| 參數 | 預設值 | 範圍 | 說明 |
|------|--------|------|------|
| 相似度閾值 | 0.7 | 0.5-1.0 | 模板匹配最低相似度 |
| 點擊冷卻 | 1.0s | 0.1-10s | 連續點擊最小間隔 |
| 熱鍵 | F6 | 任意鍵 | 觸發熱鍵 |

#### 5.2.2 即時狀態回饋

在主視窗新增狀態區域：

```
┌─────────────────────────────────┐
│ 狀態: 搜尋中...                  │
│ 相似度: 0.85 ✓                  │
│ 上次匹配: 2秒前                  │
│ FPS: 2.0                        │
└─────────────────────────────────┘
```

#### 5.2.3 截圖操作改善

- 新增「重置縮放」按鈕
- Ctrl+Z 復原上一步選取
- 顯示選取區域尺寸

### 5.3 config.json 擴展

```json
{
  "total_clicks": 12345,
  "similarity_threshold": 0.7,
  "click_cooldown": 1.0,
  "hotkey": "f6",
  "show_status_panel": true
}
```

### 5.4 變更清單

| 檔案 | 變更內容 |
|------|----------|
| `tray_clicker.py` | 新增設定選項 UI |
| `tray_clicker.py` | 新增狀態面板 |
| `tray_clicker.py` | 截圖介面改善 |
| `config.json` | 新增設定項目 |

### 5.5 狀態

- [x] 規格完成
- [x] 實作完成
- [ ] 測試通過
- [x] 已提交

---

## 6. Phase 5: 錯誤處理

### 6.1 問題描述

1. 錯誤只印到 console，使用者看不到
2. 無錯誤日誌檔案
3. 失敗時沒有重試機制

### 6.2 解決方案

#### 6.2.1 錯誤日誌系統

```python
import logging
from datetime import datetime

# 設定日誌
log_file = f"pyclick_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('PyClick')
```

#### 6.2.2 UI 錯誤提示

使用 Tkinter 的 `messagebox` 或自訂 Toast：

```python
def show_error_toast(message: str, duration: int = 3000):
    """顯示錯誤 Toast 通知"""
    toast = tk.Toplevel(self.root)
    toast.overrideredirect(True)
    toast.attributes('-topmost', True)
    # ... 樣式和動畫
    toast.after(duration, toast.destroy)
```

#### 6.2.3 自動重試機制

```python
def _auto_loop(self):
    retry_count = 0
    max_retries = 3

    while self.running:
        try:
            # ... 主要邏輯
            retry_count = 0  # 成功後重置
        except Exception as e:
            retry_count += 1
            logger.error(f"自動模式錯誤 ({retry_count}/{max_retries}): {e}")
            if retry_count >= max_retries:
                self.show_error_toast("自動模式連續失敗，已暫停")
                self.set_mode('off')
                break
            time.sleep(1)
```

### 6.3 變更清單

| 檔案 | 變更內容 |
|------|----------|
| `tray_clicker.py` | 新增 logging 設定 |
| `tray_clicker.py` | 新增 `show_error_toast()` |
| `tray_clicker.py` | `_auto_loop` 加入重試機制 |
| `block_editor.py` | 加入錯誤日誌 |

### 6.4 狀態

- [x] 規格完成
- [x] 實作完成
- [ ] 測試通過
- [x] 已提交

---

## 7. 變更紀錄

| 日期 | 版本 | 變更內容 |
|------|------|----------|
| 2026-01-13 | 1.0.0 | 初版規格建立 |
| 2026-01-13 | 1.1.0 | Phase 1 完成：執行緒安全修復 |
| 2026-01-13 | 1.2.0 | Phase 2 完成：ROI 優化 + 記憶體釋放 |
| 2026-01-13 | 1.3.0 | Phase 3 完成：utils.py 共用模組 |
| 2026-01-13 | 1.4.0 | Phase 4 完成：可設定參數 + 設定 UI |
| 2026-01-13 | 1.5.0 | Phase 5 完成：Logging 系統 |

---

## 附錄 A: 檔案結構 (優化後)

```
PyClick/
├── tray_clicker.py      # 主程式 (重構後)
├── block_editor.py      # 區塊編輯器
├── lite_runner.py       # 輕量執行器
├── exporter.py          # EXE 匯出工具
├── utils.py             # [新] 共用工具模組
│
├── config.json          # 設定檔 (擴展)
├── simple_scripts/      # 簡易腳本
├── scripts/             # 區塊腳本
├── templates/           # 模板圖片
├── logs/                # [新] 日誌目錄
│
└── doc/
    ├── optimization-spec.md  # [本文件]
    └── ...
```

## 附錄 B: 向後相容性

### 設定檔遷移

新版本首次啟動時，自動為舊設定檔添加預設值：

```python
def migrate_config(config: dict) -> dict:
    """遷移舊版設定檔"""
    defaults = {
        'similarity_threshold': 0.7,
        'click_cooldown': 1.0,
        'hotkey': 'f6',
        'show_status_panel': True
    }
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
    return config
```
