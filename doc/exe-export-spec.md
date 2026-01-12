# PyClick 腳本導出 EXE 功能規格

## 1. 功能概述

### 1.1 目標
讓使用者能將 PyClick 建立的自動化腳本（模板圖片 + 動作設定）打包成獨立的 EXE 執行檔，方便分享給他人使用，無需安裝 Python 環境。

### 1.2 核心價值
- **零門檻分享**：接收者雙擊即可執行，無需技術背景
- **隱私保護**：腳本邏輯內建於 EXE，不暴露原始設定
- **輕量部署**：單一 EXE 檔案，便於傳輸與管理

---

## 2. 用戶流程

### 2.1 在 PyClick 主程式建立腳本
```
1. 截圖 → 框選目標 → 儲存模板
2. 設定動作參數（點擊次數、間隔、後續按鍵）
3. 儲存腳本（或使用進階編輯器建立複雜流程）
```

### 2.2 導出 EXE
```
1. 選擇要導出的腳本
2. 點擊「導出 EXE」按鈕
3. 設定導出選項：
   - EXE 名稱
   - 圖示（可選）
   - 是否允許用戶調整參數
4. 選擇儲存位置
5. 等待打包完成（約 10-30 秒）
6. 取得獨立 EXE 檔案
```

### 2.3 接收者使用 EXE
```
1. 雙擊執行 EXE
2. 程式常駐系統托盤
3. 右鍵托盤圖示：
   - 開始/停止自動模式
   - 開啟設定面板
   - 結束程式
4. （可選）調整基本參數後執行
```

---

## 3. 導出 EXE 的結構

### 3.1 檔案內容
```
exported_script.exe
├── 精簡執行引擎（Python runtime + 必要模組）
├── 模板圖片（內嵌於 EXE 資源）
├── 腳本設定（JSON 格式，內嵌）
└── 托盤 UI 元件
```

### 3.2 內嵌資源
| 資源類型 | 說明 |
|---------|------|
| template_*.png | 模板圖片，Base64 編碼存入 |
| config.json | 腳本參數設定 |
| icon.ico | 托盤圖示 |

### 3.3 精簡執行引擎包含的模組
```python
# 核心模組（必要）
- cv2 (OpenCV)      # 圖像比對
- numpy             # 數值運算
- mss               # 螢幕截圖
- pyautogui         # 滑鼠鍵盤控制
- pystray           # 系統托盤
- PIL (Pillow)      # 圖像處理
- tkinter           # 設定介面

# 排除模組（精簡體積）
- matplotlib
- scipy
- pandas
- 其他非必要依賴
```

---

## 4. EXE 的簡易設定 GUI

### 4.1 設定面板設計
```
┌─────────────────────────────────────┐
│  [腳本名稱] 設定                    │
├─────────────────────────────────────┤
│                                     │
│  掃描間隔：[0.5] 秒  ▼              │
│                                     │
│  點擊次數：[1] 次    ▼              │
│                                     │
│  點擊間隔：[0.1] 秒  ▼              │
│                                     │
│  相似度門檻：[70] %  ────●────      │
│                                     │
│  □ 開機自動啟動                     │
│  ☑ 找到目標後連續點擊               │
│                                     │
├─────────────────────────────────────┤
│  [開始執行]              [關閉]     │
└─────────────────────────────────────┘
```

### 4.2 可調整參數
| 參數 | 預設值 | 範圍 | 說明 |
|-----|-------|------|------|
| 掃描間隔 | 0.5 秒 | 0.1-5.0 | 檢查畫面的頻率 |
| 點擊次數 | 1 次 | 1-10 | 每次找到目標的點擊次數 |
| 點擊間隔 | 0.1 秒 | 0.05-1.0 | 多次點擊間的延遲 |
| 相似度門檻 | 70% | 50-95 | 圖像匹配的嚴格程度 |
| 連續點擊 | 否 | 開/關 | 持續偵測到就持續點擊 |

### 4.3 托盤選單
```
右鍵選單：
├─ 顯示設定面板
├─ ─────────────
├─ ● 自動模式（執行中）
├─ ○ 暫停
├─ ─────────────
├─ 開機啟動 ✓
├─ ─────────────
└─ 結束程式
```

---

## 5. 技術實現方案

### 5.1 打包流程
```
PyClick 主程式
      │
      ▼
┌─────────────────────────────────┐
│ 1. 收集資源                      │
│    - 複製模板圖片                │
│    - 生成腳本設定 JSON           │
│    - 準備精簡執行引擎程式碼       │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│ 2. 生成打包腳本                  │
│    - 動態生成 .spec 檔案         │
│    - 設定內嵌資源路徑            │
│    - 設定排除模組列表            │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│ 3. 執行 PyInstaller             │
│    pyinstaller --onefile        │
│                --noconsole      │
│                --icon=icon.ico  │
│                script.spec      │
└─────────────────────────────────┘
      │
      ▼
   獨立 EXE 檔案
```

### 5.2 精簡執行引擎架構
```python
# lite_runner.py（導出 EXE 的核心程式）

class LiteRunner:
    """精簡版執行引擎"""

    def __init__(self):
        self.config = self._load_embedded_config()
        self.templates = self._load_embedded_templates()
        self.running = False

    def _load_embedded_config(self):
        """從內嵌資源載入設定"""
        # PyInstaller 打包後資源路徑處理
        pass

    def _load_embedded_templates(self):
        """從內嵌資源載入模板圖片"""
        pass

    def find_and_click(self):
        """核心找圖點擊邏輯"""
        pass

    def run(self):
        """主迴圈"""
        pass
```

### 5.3 PyInstaller 配置範例
```python
# generated_script.spec

a = Analysis(
    ['lite_runner.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates/*.png', 'templates'),
        ('config.json', '.'),
    ],
    hiddenimports=['pystray._win32'],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
    ],
    ...
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='MyAutoClicker',
    icon='icon.ico',
    console=False,  # 無命令列視窗
)
```

### 5.4 資源內嵌方式
```python
import sys
import os

def get_resource_path(relative_path):
    """取得內嵌資源的正確路徑"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包後的臨時目錄
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)
```

---

## 6. 檔案大小預估

### 6.1 組成分析
| 組件 | 預估大小 |
|-----|---------|
| Python runtime (精簡) | ~8 MB |
| OpenCV (核心功能) | ~15 MB |
| NumPy | ~5 MB |
| Pillow | ~3 MB |
| mss | ~0.5 MB |
| pyautogui | ~0.5 MB |
| pystray | ~0.3 MB |
| tkinter (內建) | ~2 MB |
| 模板圖片 (1-5 張) | ~0.1-0.5 MB |
| 腳本設定 | < 0.01 MB |
| **總計** | **約 35-40 MB** |

### 6.2 優化策略
- 使用 UPX 壓縮可減少 30-40% 體積
- 排除不必要的 DLL（如 Qt 相關）
- OpenCV 可用 opencv-python-headless 減少依賴

### 6.3 目標
- 基本版：35-40 MB
- 壓縮後：20-25 MB

---

## 7. 未來擴展可能

### 7.1 短期優化
- [ ] 支援自訂 EXE 圖示
- [ ] 打包進度顯示
- [ ] 導出前預覽功能
- [ ] 批次導出多個腳本

### 7.2 中期功能
- [ ] 加密保護腳本內容
- [ ] 設定密碼保護
- [ ] 使用期限設定
- [ ] 綁定特定電腦

### 7.3 長期願景
- [ ] 線上腳本市集
- [ ] 腳本版本更新機制
- [ ] 遠端控制 EXE 開關
- [ ] 執行日誌回報功能
- [ ] 支援 macOS / Linux 導出

### 7.4 進階腳本支援
- [ ] 積木式腳本（block_editor）完整導出
- [ ] 多模板順序執行
- [ ] 條件分支邏輯
- [ ] 變數與迴圈控制

---

## 8. 實作優先順序

### Phase 1：基礎導出（MVP）
1. 實作 `lite_runner.py` 精簡執行引擎
2. 實作單一模板 + 簡單動作的導出
3. 基本托盤 UI
4. PyInstaller 整合

### Phase 2：設定介面
1. 導出 EXE 的設定面板
2. 可調整參數功能
3. 開機啟動支援

### Phase 3：完善體驗
1. 導出選項 UI
2. 進度顯示
3. 體積優化
4. 錯誤處理

---

## 附錄：相關檔案

- `tray_clicker.py` - 主程式（參考其托盤與找圖邏輯）
- `block_editor.py` - 積木編輯器（未來支援複雜腳本導出）
- `simple_scripts/` - 簡單腳本存放目錄
- `templates/` - 模板圖片存放目錄
