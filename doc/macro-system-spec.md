# PyClick 巨集系統規格書

## 版本資訊
- **文件版本**: v1.0
- **目標版本**: PyClick 2.0
- **撰寫日期**: 2026-01-12

---

## 1. 功能概述

### 1.1 目標
將 PyClick 從單一圖像點擊工具擴展為完整的**視覺巨集系統**，支援：
- 多圖像辨識觸發
- 多種操作動作（不只點擊）
- 條件式流程控制
- 巨集錄製與管理

### 1.2 核心理念
基於「按鍵精靈」概念，但以**圖像辨識**作為觸發條件，而非固定座標或時間間隔。

---

## 2. 系統架構

### 2.1 資料結構

```
Macro（巨集）
├── name: 巨集名稱
├── description: 描述
├── triggers: 觸發條件[]
├── steps: 執行步驟[]
├── settings: 巨集設定
└── enabled: 是否啟用
```

```
Trigger（觸發條件）
├── type: "image" | "hotkey" | "time"
├── template: 圖像模板 (若為 image)
├── hotkey: 熱鍵組合 (若為 hotkey)
├── interval: 時間間隔 (若為 time)
└── threshold: 相似度門檻
```

```
Step（執行步驟）
├── action: 動作類型
├── target: 目標（圖像/座標）
├── params: 動作參數
├── delay: 執行前延遲
└── condition: 執行條件（可選）
```

### 2.2 檔案結構

```
pyclick/
├── tray_clicker.py      # 主程式
├── macros/              # 巨集儲存目錄
│   ├── macro_001.json   # 巨集定義檔
│   ├── macro_002.json
│   └── ...
├── templates/           # 圖像模板
│   ├── template_001.png
│   └── ...
├── doc/
│   └── macro-system-spec.md
└── config.json
```

---

## 3. 功能規格

### 3.1 觸發類型

| 類型 | 說明 | 參數 |
|------|------|------|
| `image` | 偵測到圖像時觸發 | template, threshold, region |
| `image_disappear` | 圖像消失時觸發 | template, threshold, timeout |
| `hotkey` | 按下熱鍵觸發 | key_combination |
| `time` | 定時觸發 | interval, start_time |
| `macro_complete` | 其他巨集完成時觸發 | macro_id |

### 3.2 動作類型

| 動作 | 說明 | 參數 |
|------|------|------|
| `click` | 滑鼠點擊 | target, button, count |
| `double_click` | 雙擊 | target |
| `right_click` | 右鍵點擊 | target |
| `drag` | 拖曳 | from_target, to_target |
| `scroll` | 滾輪 | direction, amount |
| `type_text` | 輸入文字 | text, speed |
| `press_key` | 按下按鍵 | key, modifiers |
| `hotkey` | 組合鍵 | keys[] |
| `wait` | 等待 | duration |
| `wait_image` | 等待圖像出現 | template, timeout |
| `wait_image_disappear` | 等待圖像消失 | template, timeout |
| `if_image` | 條件判斷 | template, then_steps, else_steps |
| `loop` | 迴圈 | count, steps |
| `run_macro` | 執行其他巨集 | macro_id |

### 3.3 目標定位方式

| 方式 | 說明 | 範例 |
|------|------|------|
| `image` | 辨識圖像位置 | `{"type": "image", "template": "button.png"}` |
| `image_offset` | 圖像位置 + 偏移 | `{"type": "image", "template": "label.png", "offset": [50, 0]}` |
| `absolute` | 絕對座標 | `{"type": "absolute", "x": 100, "y": 200}` |
| `relative` | 相對於前一動作 | `{"type": "relative", "dx": 10, "dy": 20}` |
| `center` | 螢幕中心 | `{"type": "center"}` |

---

## 4. 巨集編輯器 UI

### 4.1 主介面佈局

```
┌─────────────────────────────────────────────────────────┐
│ PyClick 巨集編輯器                              [_][□][X]│
├─────────────────────────────────────────────────────────┤
│ [巨集列表]      │  [步驟編輯區]                          │
│                │                                        │
│ ┌────────────┐ │  巨集名稱: [________________]          │
│ │ 巨集 A     │ │  描述: [________________________]      │
│ │ 巨集 B  ✓  │ │                                        │
│ │ 巨集 C     │ │  觸發條件:                             │
│ └────────────┘ │  ┌──────────────────────────────┐      │
│                │  │ [圖像] button.png (≥80%)     │ [+]  │
│ [新增] [刪除]  │  └──────────────────────────────┘      │
│                │                                        │
│                │  執行步驟:                             │
│                │  ┌──────────────────────────────┐      │
│                │  │ 1. 點擊 → button.png          │ [↑] │
│                │  │ 2. 等待 500ms                 │ [↓] │
│                │  │ 3. 輸入 "Hello"              │ [X] │
│                │  │ 4. 按鍵 Enter                │      │
│                │  └──────────────────────────────┘      │
│                │                                        │
│                │  [+ 新增步驟 ▼]                        │
├─────────────────────────────────────────────────────────┤
│ [儲存] [測試執行] [錄製巨集]        狀態: 已儲存        │
└─────────────────────────────────────────────────────────┘
```

### 4.2 步驟編輯對話框

```
┌─────────────────────────────────────┐
│ 編輯步驟                        [X] │
├─────────────────────────────────────┤
│ 動作類型: [點擊 ▼]                  │
│                                     │
│ 目標:                               │
│ ○ 圖像辨識  ● 絕對座標  ○ 相對位置  │
│                                     │
│ [選取圖像...] 或 X: [___] Y: [___]  │
│                                     │
│ 點擊按鈕: ● 左鍵 ○ 右鍵 ○ 中鍵      │
│ 點擊次數: [1 ▼]                     │
│                                     │
│ 執行前延遲: [0  ] ms                │
│                                     │
│        [確定] [取消]                │
└─────────────────────────────────────┘
```

---

## 5. 巨集範例

### 5.1 自動登入範例

```json
{
  "name": "自動登入",
  "description": "偵測到登入按鈕時自動輸入帳密並登入",
  "triggers": [
    {
      "type": "image",
      "template": "login_button.png",
      "threshold": 0.8
    }
  ],
  "steps": [
    {
      "action": "click",
      "target": {"type": "image", "template": "username_field.png"},
      "delay": 100
    },
    {
      "action": "type_text",
      "params": {"text": "myusername", "speed": 50}
    },
    {
      "action": "press_key",
      "params": {"key": "tab"}
    },
    {
      "action": "type_text",
      "params": {"text": "mypassword", "speed": 50}
    },
    {
      "action": "click",
      "target": {"type": "image", "template": "login_button.png"}
    }
  ],
  "settings": {
    "cooldown": 60,
    "run_once": true
  }
}
```

### 5.2 連續點擊不同按鈕範例

```json
{
  "name": "收穫作物",
  "description": "依序點擊所有成熟的作物",
  "triggers": [
    {
      "type": "hotkey",
      "hotkey": "ctrl+shift+h"
    }
  ],
  "steps": [
    {
      "action": "loop",
      "params": {
        "condition": {"type": "image_exists", "template": "ripe_crop.png"},
        "max_iterations": 100,
        "steps": [
          {
            "action": "click",
            "target": {"type": "image", "template": "ripe_crop.png"}
          },
          {
            "action": "wait",
            "params": {"duration": 300}
          }
        ]
      }
    }
  ]
}
```

### 5.3 條件式操作範例

```json
{
  "name": "智能回血",
  "description": "血量低時自動使用藥水",
  "triggers": [
    {
      "type": "image",
      "template": "low_hp_indicator.png",
      "threshold": 0.85
    }
  ],
  "steps": [
    {
      "action": "if_image",
      "params": {
        "template": "potion_available.png",
        "then": [
          {
            "action": "press_key",
            "params": {"key": "1"}
          }
        ],
        "else": [
          {
            "action": "click",
            "target": {"type": "image", "template": "inventory_button.png"}
          },
          {
            "action": "wait",
            "params": {"duration": 500}
          },
          {
            "action": "click",
            "target": {"type": "image", "template": "potion_in_bag.png"}
          }
        ]
      }
    }
  ],
  "settings": {
    "cooldown": 5
  }
}
```

---

## 6. 實作優先序

### 第一階段：基礎巨集系統
1. [ ] 巨集資料結構定義
2. [ ] 巨集 JSON 儲存/載入
3. [ ] 基礎動作實作（click, wait, type_text, press_key）
4. [ ] 簡易巨集編輯器 UI
5. [ ] 多圖像模板管理

### 第二階段：進階動作
6. [ ] 拖曳、滾輪動作
7. [ ] 條件判斷（if_image）
8. [ ] 迴圈控制（loop）
9. [ ] 等待圖像（wait_image）
10. [ ] 多觸發條件支援

### 第三階段：錄製功能
11. [ ] 滑鼠動作錄製
12. [ ] 鍵盤輸入錄製
13. [ ] 錄製編輯與優化
14. [ ] 錄製暫停/繼續

### 第四階段：進階功能
15. [ ] 巨集匯入/匯出
16. [ ] 巨集分享格式
17. [ ] 執行日誌與除錯
18. [ ] 錯誤處理與恢復

---

## 7. 技術考量

### 7.1 效能優化
- 多圖像辨識時使用 ROI（Region of Interest）限制搜尋範圍
- 圖像快取避免重複載入
- 非同步執行避免 UI 凍結
- Hash 比對跳過無變化畫面

### 7.2 穩定性
- 動作執行失敗時的重試機制
- 圖像找不到時的 timeout 處理
- 巨集執行中的緊急中斷（保留 FAILSAFE）
- 執行狀態的即時回報

### 7.3 使用者體驗
- 步驟拖放排序
- 即時預覽目標位置
- 執行時高亮顯示當前步驟
- 友善的錯誤提示

---

## 8. 相容性

- 保持與現有單圖像點擊功能的相容
- 現有模板可直接用於巨集
- 現有設定（熱鍵、冷卻等）繼續有效
- 漸進式升級，不影響現有使用者

---

## 9. 附錄

### 9.1 參考專案
- 按鍵精靈
- AutoHotkey
- SikuliX
- PyAutoGUI

### 9.2 名詞對照

| 中文 | 英文 | 說明 |
|------|------|------|
| 巨集 | Macro | 一系列自動化步驟的集合 |
| 觸發 | Trigger | 啟動巨集的條件 |
| 步驟 | Step | 巨集中的單一動作 |
| 動作 | Action | 具體要執行的操作 |
| 模板 | Template | 用於圖像辨識的參照圖片 |
