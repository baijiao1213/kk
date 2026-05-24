# 恋与深空-芯核全自动筛选工具 v1.0

一个 Windows 工具，通过 ADB 无线控制手机，OCR 自动识别游戏芯核副词条，智能判定保留/丢弃。

## 快速开始

1. 手机开启开发者模式 → USB调试/无线调试
2. 双击 `app.py` 或使用打包好的 exe 启动
3. 输入配对码和端口连接
4. 开始筛选

## 功能

- 无线 ADB 连接（无需 USB 线）
- 自动 OCR 识别副词条名称和数值
- 强化次数反推算法
- 一键保留/弃置
- 带测试验证的坐标测量工具
- 实时统计和 CSV 日志

## 技术栈

Python + Tkinter + PaddleOCR + OpenCV + ADB

## 文件结构

```
love_deepspace_core_sorter/
├── app.py                # 主程序 GUI
├── core_sorter.py        # 筛选引擎
├── measure_coords_tk.py  # 坐标测量工具
├── thresholds.py         # 阈值表
├── requirements.txt      # Python 依赖
├── logs/                 # 运行日志
└── ...
```
