# PyClick 輸入保護機制分析報告

> 日期: 2026-01-13
> 狀態: 分析完成

---

## 1. 問題描述

自動點擊執行時，用戶可能同時操作鍵盤滑鼠，導致：
- 點擊位置偏移（用戶移動了滑鼠）
- 意外按鍵被送出
- 打字被中斷

---

## 2. 方案分析

### 方案 A: 暫時鎖定輸入 ⭐ 推薦

```python
import ctypes
user32 = ctypes.windll.user32

def execute_with_block(action_func):
    """執行動作時暫時鎖定輸入"""
    try:
        user32.BlockInput(True)  # 鎖定
        action_func()
    finally:
        user32.BlockInput(False)  # 解鎖（即使出錯也會執行）
```

| 項目 | 評估 |
|------|------|
| 實現難度 | ⭐ 簡單 |
| 效果 | ⭐⭐⭐ 完美防干擾 |
| 風險 | ⚠️ 需要管理員權限 |
| 用戶體驗 | 中等（短暫鎖定可接受）|

**安全機制：**
```python
# 1. 最大鎖定時間
MAX_BLOCK_TIME = 500  # ms

# 2. 異常自動解鎖
try:
    user32.BlockInput(True)
    # ... 動作 ...
finally:
    user32.BlockInput(False)  # 保證解鎖

# 3. 退出時確保解鎖
import atexit
atexit.register(lambda: user32.BlockInput(False))
```

**優點：**
- 動作執行期間 100% 不受干擾
- 實現簡單（3 行程式碼）
- 滑鼠會回到原位，用戶幾乎無感

**缺點：**
- 需要管理員權限運行
- 如果程式崩潰且沒有 finally，輸入會卡住
- 用戶可能覺得「失控」

---

### 方案 B: 監控並補按 ❌ 不推薦

```
用戶意圖 → 預測 → 補按
   ↓
  極難實現
```

| 項目 | 評估 |
|------|------|
| 實現難度 | ⭐⭐⭐⭐⭐ 極難 |
| 效果 | 不確定 |
| 風險 | 高（誤判會更糟）|

**為什麼不推薦：**
1. 無法知道用戶「想」按什麼
2. 需要追蹤所有視窗的上下文
3. 補按可能造成更大問題（重複輸入）
4. 本質上是 AI 預測問題

---

### 方案 C: 截圖記錄 📸 輔助方案

```python
def log_action_with_screenshot():
    """每次動作前截圖記錄"""
    timestamp = datetime.now().strftime("%H%M%S")
    screenshot = mss.mss().grab(monitor)

    # 儲存到日誌目錄
    cv2.imwrite(f"logs/action_{timestamp}.png", screenshot)

    # 記錄元資料
    log_entry = {
        "time": timestamp,
        "active_window": get_foreground_window_title(),
        "mouse_pos": pyautogui.position(),
        "action": "click",
    }
```

| 項目 | 評估 |
|------|------|
| 實現難度 | ⭐⭐ 中等 |
| 效果 | 事後追溯，無法預防 |
| 磁碟使用 | ~50KB/張 × 每次動作 |

**優點：**
- 用戶可以查看「發生了什麼」
- 不影響正常操作
- 有助於除錯

**缺點：**
- 無法防止問題，只是記錄
- 磁碟空間消耗（需要定期清理）
- 增加每次動作的開銷

---

### 方案 D: 打字中斷檢測 🔤

```python
def is_user_typing():
    """檢測用戶是否正在打字"""
    # 方法 1: 檢查最近按鍵時間
    last_key_time = keyboard.get_last_event_time()
    if time.time() - last_key_time < 0.5:
        return True

    # 方法 2: 檢查是否有文字輸入框焦點
    # （較複雜，需要 UI Automation）

    return False

def safe_click():
    if is_user_typing():
        # 延遲執行，等用戶打完
        time.sleep(1.0)
    do_click()
```

| 項目 | 評估 |
|------|------|
| 實現難度 | ⭐⭐⭐ 中等 |
| 效果 | 部分有效 |
| 風險 | 可能延遲太多 |

---

## 3. 推薦方案：A + C 混合

```
┌─────────────────────────────────────────────────────────┐
│  最佳實踐：短暫鎖定 + 日誌記錄                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  執行動作前:                                             │
│    1. 記錄當前狀態（時間、滑鼠位置、焦點視窗）            │
│    2. BlockInput(True) 鎖定輸入                         │
│                                                         │
│  執行動作:                                               │
│    3. 移動滑鼠、點擊、按鍵                               │
│    4. 最大鎖定 300ms                                    │
│                                                         │
│  執行後:                                                 │
│    5. BlockInput(False) 解鎖                            │
│    6. 滑鼠回原位                                         │
│    7. 記錄完成狀態                                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**實現程式碼：**

```python
import ctypes
import atexit

user32 = ctypes.windll.user32

# 確保程式退出時解鎖
atexit.register(lambda: user32.BlockInput(False))

def _execute_action_sequence_safe(self, cx, cy):
    """安全執行動作序列（帶輸入鎖定）"""
    original_pos = pyautogui.position()
    original_hwnd = user32.GetForegroundWindow()

    try:
        # 鎖定輸入
        user32.BlockInput(True)

        # 執行動作（最多 300ms）
        user32.SetCursorPos(cx, cy)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        # 按鍵（如果有）
        if self.current_script.after_key:
            time.sleep(0.05)
            pyautogui.press(self.current_script.after_key)

    finally:
        # 保證解鎖
        user32.BlockInput(False)

        # 滑鼠回原位
        user32.SetCursorPos(original_pos[0], original_pos[1])

        # 恢復焦點
        force_focus(original_hwnd)
```

---

## 4. 實現建議

### 4.1 新增設定選項

```json
{
  "block_input_during_action": true,  // 是否鎖定輸入
  "action_log_enabled": false,        // 是否記錄動作日誌
  "max_block_time_ms": 300           // 最大鎖定時間
}
```

### 4.2 UI 選項

```
☑ 執行時鎖定輸入 (需要管理員權限)
☐ 記錄動作日誌 (每次動作截圖)
```

### 4.3 管理員權限處理

```python
def is_admin():
    """檢查是否有管理員權限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def request_admin():
    """請求管理員權限重新啟動"""
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()
```

---

## 5. 風險評估

| 風險 | 機率 | 影響 | 緩解措施 |
|------|------|------|----------|
| 程式崩潰導致輸入卡住 | 低 | 高 | finally + atexit 雙保險 |
| 用戶無法緊急中斷 | 中 | 中 | Ctrl+Alt+Del 仍可使用 |
| 鎖定時間過長 | 低 | 中 | 最大 300ms 限制 |
| 缺少管理員權限 | 中 | 低 | 降級為不鎖定模式 |

---

## 6. 結論

| 方案 | 推薦度 | 說明 |
|------|--------|------|
| A. 暫時鎖定 | ⭐⭐⭐⭐⭐ | 最有效，實現簡單 |
| B. 監控補按 | ⭐ | 不實際，放棄 |
| C. 截圖記錄 | ⭐⭐⭐ | 作為輔助功能 |
| D. 打字檢測 | ⭐⭐ | 延遲過多，不推薦 |

**最終建議：** 實作方案 A（輸入鎖定），作為可選功能，預設關閉。

---

## 7. 下一步

如果要實作，建議作為 **Phase 8: 輸入保護機制**：

1. 新增 `block_input_during_action` 設定
2. 修改 `_execute_action_sequence` 加入 BlockInput
3. 新增管理員權限檢查
4. UI 新增選項開關
5. 測試安全機制（崩潰恢復）

預估：約 50 行程式碼變更
