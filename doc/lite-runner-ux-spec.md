# Lite Runner UX 優化規格

> 日期: 2026-01-13
> 狀態: ✅ 已完成

---

## 1. 問題清單

### 1.1 按鈕醜 ✅ 已修復
- **現象**: tk.Button 在 Windows 上即使設 `relief="flat"` 仍有奇怪的漸層效果
- **原因**: Windows 原生渲染問題，tk.Button 不支援真正的扁平按鈕
- **方案**: 改用 ttk.Button + 自定義 Style
- **修復**: 新增 `_setup_button_styles()` 方法，使用 `Green.TButton` 和 `Red.TButton` 樣式

### 1.2 開啟就縮托盤 ✅ 已修復
- **現象**: EXE 啟動後自動縮到托盤，用戶不知道怎麼用
- **原因**: 程式設計時預設行為
- **方案**: 首次啟動顯示面板 + 簡單使用說明
- **修復**: `run()` 方法改為先顯示設定面板，托盤在背景執行；新增使用提示

### 1.3 面板無法縮小 ✅ 已修復
- **現象**: 視窗無法最小化
- **原因**: `resizable(False, False)` 限制
- **方案**: 確保視窗可以正常最小化
- **修復**: 改為 `resizable(True, True)` 並設定 `minsize(300, 380)`

---

## 2. 解決方案

### 2.1 按鈕改用 ttk.Style

```python
# 建立自定義樣式
style = ttk.Style()

# 綠色開始按鈕
style.configure("Green.TButton",
    background="#2E7D32",
    foreground="white",
    font=("Microsoft JhengHei", 11, "bold"),
    padding=(20, 10)
)
style.map("Green.TButton",
    background=[("active", "#1B5E20"), ("disabled", "#A5D6A7")]
)

# 紅色停止按鈕
style.configure("Red.TButton",
    background="#C62828",
    foreground="white",
    font=("Microsoft JhengHei", 11, "bold"),
    padding=(20, 10)
)
style.map("Red.TButton",
    background=[("active", "#B71C1C"), ("disabled", "#FFCDD2")]
)
```

### 2.2 首次啟動顯示面板

```python
def __init__(self):
    # ... 初始化 ...

    # 首次啟動：顯示面板而非縮到托盤
    self.root.deiconify()

    # 顯示簡單使用說明
    self._show_welcome_tip()
```

### 2.3 確保視窗可最小化

```python
# 不要用 overrideredirect
# self.root.overrideredirect(True)  # 移除這行

# 確保有標準視窗按鈕
self.root.resizable(True, True)
```

---

## 3. 實作步驟

- [x] 3.1 檢查 lite_runner.py 視窗設定
- [x] 3.2 改用 ttk.Button + Style 美化按鈕
- [x] 3.3 移除自動縮到托盤的行為
- [x] 3.4 確保視窗可最小化
- [ ] 3.5 測試 EXE 導出後的行為

---

## 4. 變更清單

| 檔案 | 變更內容 |
|------|----------|
| `lite_runner.py` | 按鈕樣式、視窗行為、啟動流程 |

---

## 5. 詳細變更記錄

### 5.1 新增方法
- `_setup_button_styles(root)`: 設定 ttk.Button 自定義樣式（Green.TButton, Red.TButton）
- `_hide_to_tray()`: 縮小視窗到托盤

### 5.2 修改方法
- `show_settings()`:
  - 視窗可調整大小（350x430, minsize 300x380）
  - 關閉按鈕改為縮到托盤（WM_DELETE_WINDOW → _hide_to_tray）
  - 按鈕改用 ttk.Button + 自定義樣式
  - 新增使用提示標籤
  - 「關閉」按鈕改為「縮到托盤」

- `run()`:
  - 托盤在背景執行緒啟動
  - 首次啟動自動顯示設定面板

- `_update_control_buttons()`:
  - 移除 bg 參數（ttk.Button 不支援）
