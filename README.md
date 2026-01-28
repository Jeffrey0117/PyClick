<div align="center">
  <img src="logo.png" width="200" alt="PyClick Logo">
  <h1>PyClick</h1>
  <p>
    <strong>Windows 智能自動點擊器</strong><br>
    看到圖 → 點過去 → 按按鍵，就這麼簡單
  </p>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white">
  <img src="https://img.shields.io/badge/License-MIT-green">
  <img src="https://img.shields.io/badge/OpenCV-4.x-5C3EE8?logo=opencv">
</p>

<p align="center">
  <a href="#features">功能</a> •
  <a href="#use-cases">使用場景</a> •
  <a href="#quick-start">快速開始</a> •
  <a href="#usage">使用說明</a> •
  <a href="#advanced">進階功能</a>
</p>

---

## 📖 About

**PyClick** 是一款基於圖像識別的自動點擊工具，專為 Windows 平台設計。

### 核心理念

- 🎯 **簡單直覺**：截圖 → 框選 → 設定 → 執行
- 🔄 **自動化重複操作**：讓程式代替你點擊重複的按鈕
- 🎮 **不干擾工作流**：後台執行，不搶奪焦點
- 💾 **腳本化管理**：儲存多組設定，隨時切換

### 適用對象

- 開發者：自動化 CLI 確認、測試流程
- 運維人員：批次處理、定時操作
- 一般用戶：網頁自動填表、重複性操作
- 遊戲玩家：自動化日常任務（僅限個人使用）

---

## ✨ Features

### 🎯 核心功能

| 功能 | 說明 |
|------|------|
| **圖像辨識** | OpenCV 模板匹配，70% 相似度即觸發 |
| **腳本系統** | 儲存多組設定，JSON 格式，易於管理 |
| **多模板支援** | 一個腳本支援多個目標圖像 |
| **Focus 模式** | 點擊切換焦點後按鍵，適合多視窗操作 |

### ⚡ 執行功能

| 功能 | 說明 |
|------|------|
| **多次點擊** | 點 1~N 下，自訂間隔時間 |
| **連續按鍵** | 點完自動按 Enter/Tab/方向鍵，支援多次 |
| **重試機制** | 失敗自動重試，直到目標消失 |
| **確認機制** | 執行後檢查是否還在，決定是否繼續 |

### 🛡️ 安全功能

| 功能 | 說明 |
|------|------|
| **不搶焦點** | 點擊後自動恢復原焦點，不打斷打字 |
| **冷卻時間** | 防止連續觸發，保護系統資源 |
| **定時停止** | 設定執行時長，自動停止 |
| **輸入鎖定** | 可選：執行時暫時鎖定鍵盤滑鼠（需管理員） |

### 🎨 介面功能

| 功能 | 說明 |
|------|------|
| **托盤常駐** | 最小化到系統托盤，隨時待命 |
| **熱鍵觸發** | F6 開始/停止，F7 緊急停止 |
| **即時統計** | 顯示點擊次數、執行狀態 |
| **聲音提示** | 可選：執行前播放提示音 |

---

## 🎯 Use Cases

<details>
<summary><strong>🛠️ 開發場景</strong></summary>

- **CLI 工具確認**：自動點擊「Yes/Continue」
- **測試流程**：自動化點擊測試步驟
- **Build 流程**：自動處理彈窗確認
- **Docker/WSL**：自動化容器操作確認

</details>

<details>
<summary><strong>💼 辦公場景</strong></summary>

- **報表生成**：自動點擊「生成報表」→「下載」
- **批次處理**：重複性的表單填寫
- **定時操作**：每 X 分鐘點擊一次「刷新」
- **網頁操作**：自動化網頁表單提交

</details>

<details>
<summary><strong>🎮 個人使用</strong></summary>

- **遊戲日常**：自動化重複任務（僅限個人使用）
- **簽到打卡**：自動點擊簽到按鈕
- **影片播放**：自動跳過廣告（如適用）
- **自動刷新**：定時刷新頁面

</details>

<details>
<summary><strong>🧪 測試場景</strong></summary>

- **UI 自動化測試**：點擊特定 UI 元素
- **壓力測試**：模擬大量點擊操作
- **回歸測試**：重複執行相同操作
- **截圖對比**：配合截圖工具驗證 UI

</details>

---

## 🚀 Quick Start

```bash
# 1. 安裝
git clone https://github.com/Jeffrey0117/PyClick.git
cd PyClick
pip install -r requirements.txt

# 2. 啟動
python tray_clicker.py
```

### 第一次使用

1. **截圖** - 點擊「開始截圖」擷取螢幕
2. **框選目標** - 拖曳選擇要點擊的按鈕/圖標
3. **設定動作** - 設定點擊次數、按鍵
4. **儲存腳本** - 另存新檔 (`simple_scripts/xxx.json`)
5. **選擇模式** - 熱鍵 (F6) 或自動模式
6. **開始執行** - 觀察系統托盤圖示狀態

---

## 📖 Usage

### 基本操作

<details>
<summary><strong>建立腳本</strong></summary>

```
1. 開始截圖 → 2. 框選目標 → 3. 設定動作 → 4. 另存腳本
```

**動作設定範例：**
```
點擊 [2] 次    間隔 [0.1] 秒    然後按 [Enter] x 2
```

**儲存位置：**
```
simple_scripts/my_script.json
```

</details>

<details>
<summary><strong>執行模式</strong></summary>

| 模式 | 觸發方式 | 說明 |
|------|----------|------|
| **停用** | - | 暫停腳本，不執行任何動作 |
| **熱鍵** | 按 F6 | 手動觸發，每按一次執行一次 |
| **自動** | 自動偵測 | 持續掃描螢幕，找到目標自動點擊 |

**快捷鍵：**
- `F6` - 開始/停止執行
- `F7` - 緊急停止（回到停用模式）

</details>

<details>
<summary><strong>托盤圖示狀態</strong></summary>

- 🟢 **綠色圓點** - 自動模式執行中
- 🟠 **橙色圓點** - 熱鍵模式待命中
- ⚪ **灰色圓點** - 已停用

**右鍵托盤圖示** → 快速切換模式 / 開啟面板

</details>

---

## ⚙️ Advanced

### 進階功能

<details>
<summary><strong>多模板支援</strong></summary>

一個腳本可以偵測多個目標圖像，任一匹配即觸發：

```json
{
  "template_paths": [
    "templates/button1.png",
    "templates/button2.png",
    "templates/button3.png"
  ]
}
```

**適用場景：**
- 按鈕有多種狀態（normal/hover/pressed）
- 不同語言界面的相同按鈕
- 隨機出現的多個目標

</details>

<details>
<summary><strong>Focus 模式</strong></summary>

點擊後切換焦點到目標視窗，再按鍵：

```json
{
  "focus_mode": true,
  "after_key": "Enter"
}
```

**適用場景：**
- 多視窗操作（點擊 A 視窗，在 A 視窗按鍵）
- 需要確保焦點在正確視窗
- 避免按鍵送到錯誤視窗

</details>

<details>
<summary><strong>重試機制</strong></summary>

失敗時自動重試，直到目標消失：

```json
{
  "retry_until_gone": true,
  "retry_max": 3
}
```

**適用場景：**
- 需要多次點擊才會消失的彈窗
- 網路延遲導致的重試
- 確保操作成功執行

</details>

<details>
<summary><strong>定時停止</strong></summary>

設定執行時長，時間到自動停止：

```
設定 → 定時停止 → 30 分鐘
```

**適用場景：**
- 防止過度執行
- 睡前設定自動停止
- 限制執行時間

</details>

---

## 📁 File Structure

```
PyClick/
├── tray_clicker.py         # 主程式
├── lite_runner.py          # 輕量執行器（用於打包）
├── block_editor.py         # 區塊腳本編輯器（進階）
├── utils.py                # 共用工具模組
├── logo.png                # 官方 Logo
│
├── simple_scripts/         # 簡易腳本（JSON）
│   └── my_script.json
│
├── scripts/                # 區塊腳本（進階）
│   └── advanced.json
│
├── templates/              # 模板圖片
│   ├── button.png
│   └── target.png
│
├── config.json             # 全域設定
├── requirements.txt        # Python 依賴
└── README.md
```

---

## 🔧 Requirements

### 系統需求

- **作業系統**: Windows 10/11
- **Python**: 3.8+
- **記憶體**: 最低 256MB
- **磁碟空間**: 最低 100MB

### Python 套件

```bash
pip install -r requirements.txt
```

**核心依賴：**
- `opencv-python` - 圖像識別
- `mss` - 螢幕截圖
- `pyautogui` - 滑鼠/鍵盤控制
- `Pillow` - 圖像處理
- `keyboard` - 熱鍵監聽
- `pystray` - 系統托盤
- `numpy` - 數值計算

---

## 🤝 Contributing

歡迎貢獻！請遵循以下步驟：

1. Fork 本專案
2. 建立功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交變更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

---

## 📄 License

本專案採用 **MIT License** 授權 - 詳見 [LICENSE](LICENSE) 文件

---

## 🙏 Acknowledgments

- 圖像識別：[OpenCV](https://opencv.org/)
- 系統托盤：[pystray](https://github.com/moses-palmer/pystray)
- 開發工具：[Claude Code](https://claude.ai/)

---

## 📮 Contact

- **作者**: Jeffrey0117
- **專案**: [https://github.com/Jeffrey0117/PyClick](https://github.com/Jeffrey0117/PyClick)
- **問題回報**: [Issues](https://github.com/Jeffrey0117/PyClick/issues)

---

<p align="center">
  <sub>Built with ❤️ and Claude Code</sub>
</p>
