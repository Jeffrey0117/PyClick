# Bug 修復記錄：numpy int64 類型轉換錯誤

## 日期
2026-01-27

## 問題描述
PyClick 在自動模式下找到模板匹配後，執行點擊時會失敗，日誌顯示：
```
[INFO] 找到 1 處匹配
[ERROR] 自動模式錯誤: argument 1: TypeError: Don't know how to convert parameter 1
```

每次找到匹配都會觸發此錯誤，導致點擊完全無法執行。

## 根本原因
`_find_all_matches` 函式中，座標計算使用了 numpy 陣列的值：

```python
locations = np.where(result >= threshold)
for pt in zip(*locations[::-1]):
    cx = pt[0] + tw // 2 + ox  # pt[0] 是 np.int64
    cy = pt[1] + th // 2 + oy  # pt[1] 是 np.int64
```

`np.where()` 返回的是 numpy 陣列，其中的元素是 `np.int64` 類型。當這些座標傳遞給 `ctypes` 的 `user32.SetCursorPos(cx, cy)` 時，ctypes 不知道如何將 `np.int64` 轉換為 C 的 `int` 類型。

## 修復方式
在 `_find_all_matches` 返回座標時，明確轉換為 Python 原生 `int`：

```python
# 修復前
return [(cx, cy) for cx, cy, _ in filtered]

# 修復後
return [(int(cx), int(cy)) for cx, cy, _ in filtered]
```

## 影響範圍
- `tray_clicker.py` 第 1866 行
- 影響所有使用模板匹配後點擊的功能（自動模式、熱鍵模式）

## 提交
- Commit: `c46c506`
- Message: `fix: convert numpy int64 to Python int for ctypes SetCursorPos`

## 教訓
當使用 numpy 進行計算後，如果結果要傳給 ctypes 等需要原生 Python 類型的 API，記得做類型轉換。
