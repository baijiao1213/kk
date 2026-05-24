# 恋与深空芯核全自动筛选工具

自动遍历游戏中的芯核列表，OCR 识别每个芯核的副词条，根据内置阈值表反推强化次数，自动判定保留或弃置。

## 工作原理

```
点击芯核 → 详情区更新 → 截图等级+词条区域 → OCR识别
→ 反推强化次数 → 判定(保留/弃置) → 点击对应按钮 → 下一个芯核
每处理12个芯核自动向上滑动加载新一批，直到列表底部。
```

## 安装步骤

### 1. 安装 Python

需要 Python 3.9 或更高版本。从 https://www.python.org/downloads/ 下载安装。
安装时勾选 "Add Python to PATH"。

### 2. 安装 scrcpy / ADB

**方式一（推荐）**：下载 scrcpy（自带 ADB）
- 从 https://github.com/Genymobile/scrcpy/releases 下载 Windows 版本
- 解压到任意目录，记下路径（例如 `C:\scrcpy`）

**方式二**：单独安装 ADB（platform-tools）
- 从 https://developer.android.com/tools/releases/platform-tools 下载

### 3. 配置 ADB 环境变量

将 scrcpy 或 platform-tools 目录添加到系统 PATH：
1. 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
2. 在 Path 中添加 scrcpy 所在目录
3. 打开终端，输入 `adb version` 验证安装成功

### 4. 安装 Python 依赖

```bash
cd love_deepspace_core_sorter
pip install -r requirements.txt
```

PaddleOCR 首次运行会自动下载模型文件（约 100MB），请保持网络畅通。

### 5. 连接手机

1. 手机开启开发者模式 → USB 调试
2. 用 USB 线连接电脑
3. 手机弹出"允许 USB 调试"提示时，勾选"始终允许"并确认
4. 终端输入 `adb devices`，确认能看到设备

### 6. （可选）启动 scrcpy 投屏

在终端运行 `scrcpy`，可以在电脑上看到手机画面，方便监控运行状态。
**工具本身不需要 scrcpy**，通过 ADB 直接控制手机。

## 使用步骤

### 第一步：测量坐标（仅需一次）

```bash
python measure_coords.py
```

按屏幕提示依次点击各个位置：
1. **列表页**：3个芯核中心位置 → 翻页滑动起点和终点
2. **详情页**（展开任意芯核后）：上锁按钮、弃置按钮、等级区域框选、词条区域框选

测量完成后生成 `coordinates.json` 和 `config.json`。

### 第二步：运行筛选

```bash
python core_sorter.py
```

脚本将自动执行筛选流程。运行过程中：
- **Ctrl+C**：暂停，弹出菜单（继续 / 统计 / 退出）
- 控制台实时显示每个芯核的处理结果
- 结果自动写入 `logs/cores_YYYYMMDD_HHMMSS.csv`

## 日志说明

CSV 文件包含以下字段：

| 字段 | 说明 |
|------|------|
| 序号 | 处理序号 |
| 时间 | 处理时间 |
| 等级 | 芯核等级（0/3/6/9/12/15） |
| N0 | 反推出的初始词条数 |
| 词条1~4 | 四个副词条的名称 |
| 数值1~4 | OCR 识别到的数值 |
| 强化1~4 | 反推出的强化次数 |
| 平均1~4 | 该强化次数下的平均值 |
| 达标1~4 | 是否达标（数值 >= 平均值） |
| 判定 | 保留 / 丢弃 / 失败 |

## 判定规则

- 任一副词条的**当前数值 >= 该强化次数下的平均值** → 保留（上锁）
- 所有词条均不达标 → 丢弃（点弃置按钮）

## 常见问题

**Q: OCR 识别不准怎么办？**
A: 重新运行 `measure_coords.py`，确保词条区域框选准确（包含所有4行词条名称和数值，但不要包含无关内容）。

**Q: 脚本点击位置偏移？**
A: 游戏界面布局改变后需要重新测量坐标。手机分辨率改变也需要重新测量。

**Q: 处理到一半手机熄屏了？**
A: 脚本持续点击会保持屏幕唤醒。如有问题，将手机屏幕超时设为最大值（10分钟以上）。

**Q: 一根数据线可以边充边用吗？**
A: 可以，USB 连接同时支持充电和 ADB 控制。

**Q: 2000个芯核大概要多久？**
A: 每个约 2.5~3 秒，总计约 1.5~2 小时。

## 文件结构

```
love_deepspace_core_sorter/
├── core_sorter.py       # 主程序
├── measure_coords.py    # 坐标测量工具
├── thresholds.py        # 阈值表和别名映射
├── coordinates.json     # 坐标配置（measure_coords.py 生成）
├── config.json          # 区域和时序配置（measure_coords.py 生成）
├── requirements.txt     # Python 依赖
├── logs/                # 运行日志（自动创建）
│   └── cores_*.csv
└── README.md
```
