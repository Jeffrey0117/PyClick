<h1 align="center">PyClick</h1>

<p align="center">
  <strong>Windows 智能自動點擊器</strong><br>
  看到圖 → 點過去 → 按按鍵，就這麼簡單
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white">
  <img src="https://img.shields.io/badge/License-MIT-green">
</p>

---

## What is PyClick?

PyClick 是一款輕量級的自動點擊工具。你只需要：

1. **截圖** — 擷取螢幕畫面
2. **框選** — 選擇要點擊的目標
3. **設定動作** — 點幾下？按什麼鍵？
4. **開啟自動** — 剩下的交給 PyClick

適合自動化重複操作，例如 CLI 確認、網頁按鈕、遊戲輔助等。

---

## Features

| 功能 | 說明 |
|------|------|
| **圖像辨識** | OpenCV 模板匹配，70% 相似度即觸發 |
| **腳本系統** | 儲存多組設定，一鍵切換 |
| **多次點擊** | 點 1~N 下，自訂間隔 |
| **連續按鍵** | 點完自動按 Enter/Tab/方向鍵 |
| **不搶焦點** | 點擊不打斷你正在打的字 |
| **托盤常駐** | 最小化到系統托盤，隨時待命 |

---

## Quick Start

```bash
# 安裝
git clone https://github.com/Jeffrey0117/PyClick.git
cd PyClick
pip install -r requirements.txt

# 啟動
python tray_clicker.py
```

---

## Usage

### 建立腳本

```
截圖 → 框選目標 → 設定動作 → 另存腳本
```

### 動作設定

```
點擊 [2] 次    間隔 [0.1] 秒    然後按 [Enter]
```

### 模式

| 模式 | 說明 |
|------|------|
| 停用 | 暫停腳本 |
| 熱鍵 | 按 F6 手動觸發 |
| 自動 | 持續掃描，找到就點 |

---

## File Structure

```
PyClick/
├── tray_clicker.py      # 主程式
├── templates/           # 模板圖片
├── simple_scripts/      # 腳本設定
└── config.json          # 全域設定
```

---

## Requirements

- Windows 10/11
- Python 3.8+
- 相依套件：`mss` `opencv-python` `numpy` `pyautogui` `Pillow` `keyboard` `pystray`

---

## License

MIT

---

<p align="center">
  <sub>Built with Claude Code</sub>
</p>
