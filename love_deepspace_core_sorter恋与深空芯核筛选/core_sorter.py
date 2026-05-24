#!/usr/bin/env python3
"""
恋与深空芯核全自动筛选工具
通过 ADB 控制手机，OCR 识别芯核词条，自动判定保留/丢弃。
"""

import subprocess
import sys
import json
import os
import csv
import time
import random
import re
import gc
import shutil
from datetime import datetime
from itertools import product


def _find_adb():
    # 优先从 exe 所在目录查找（PyInstaller 打包后）
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        for sub in ["", "scrcpy"]:
            p = os.path.join(base, sub, "adb.exe")
            if os.path.exists(p):
                return p
    adb = shutil.which("adb")
    if adb:
        return adb
    candidates = [
        r"C:\scrcpy\scrcpy-win64-v4.0\adb.exe",
        r"C:\scrcpy\adb.exe",
        r"C:\platform-tools\adb.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "adb"

ADB = _find_adb()
NO_WIN = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


def _get_device():
    r = subprocess.run([ADB, "devices"], capture_output=True,
                       text=True, timeout=10, creationflags=NO_WIN)
    for line in r.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            return line.split("\t")[0]
    return None

import cv2
import numpy as np
from paddleocr import PaddleOCR

from thresholds import (
    normalize_stat_name,
    get_candidate_times,
    get_threshold,
    VALID_LEVELS,
)


# ══════════════════════════════════════════════════════════════════════
# ADB 底层操作
# ══════════════════════════════════════════════════════════════════════

def _adb_cmd(*args):
    """构建 ADB 命令，自动添加 -s 设备序号"""
    dev = _get_device()
    if dev:
        return [ADB, "-s", dev] + list(args)
    return [ADB] + list(args)


def adb_tap(x, y):
    subprocess.run(_adb_cmd("shell", "input", "tap", str(x), str(y)),
                   capture_output=True, timeout=10, creationflags=NO_WIN)


def adb_swipe(x1, y1, x2, y2, duration=300):
    subprocess.run(_adb_cmd("shell", "input", "swipe",
                    str(x1), str(y1), str(x2), str(y2), str(duration)),
                   capture_output=True, timeout=10, creationflags=NO_WIN)


def adb_screenshot():
    """ADB 截图，返回 OpenCV BGR 图像"""
    r = subprocess.run(
        _adb_cmd("exec-out", "screencap", "-p"),
        capture_output=True, timeout=15, creationflags=NO_WIN
    )
    if r.returncode != 0:
        raise RuntimeError(f"ADB 截图失败: {r.stderr.decode()}")
    arr = np.frombuffer(r.stdout, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("无法解码截图数据")
    return img


def check_adb():
    try:
        dev = _get_device()
        if not dev:
            print("[错误] 未检测到已连接的设备")
            return False
        print(f"[设备] {dev}")
        return True
    except FileNotFoundError:
        print("[错误] 未找到 adb 命令")
        return False


# ══════════════════════════════════════════════════════════════════════
# OCR 解析
# ══════════════════════════════════════════════════════════════════════

def parse_number(raw):
    """从 OCR 文本中提取数值。'8.5%'→8.5, '+925'→925, '1,200'→1200"""
    text = raw.strip().lstrip("+").rstrip("%").replace(",", "").replace("，", "")
    m = re.search(r'[\d.]+', text)
    return float(m.group()) if m else None


def parse_stats(ocr_results):
    """
    将 PaddleOCR 结果解析为 {标准词条名: 数值}。
    通过 Y 坐标聚类分行，每行左侧是名称、右侧是数值。
    """
    if not ocr_results:
        return {}

    items = []
    for det in ocr_results:
        if det is None or len(det) < 2:
            continue
        bbox = det[0]
        text_info = det[1]

        if isinstance(text_info, (tuple, list)) and len(text_info) >= 2:
            text = str(text_info[0])
            conf = float(text_info[1])
        else:
            text = str(text_info)
            conf = 1.0

        pts = np.array(bbox)
        cx = pts[:, 0].mean()
        cy = pts[:, 1].mean()
        items.append({"text": text, "cx": cx, "cy": cy, "conf": conf})

    if len(items) < 2:
        return {}

    # 按 Y 排序，然后聚类成行
    items.sort(key=lambda x: x["cy"])
    rows = []
    current = [items[0]]
    for item in items[1:]:
        if item["cy"] - current[-1]["cy"] < 50:
            current.append(item)
        else:
            rows.append(current)
            current = [item]
    rows.append(current)

    # 每行：最左=名称，最右=数值
    # 用 OCR 原始展示名作为 key，避免「生命加成」和「攻击加成」
    # 因归一化后同为"加成"而互相覆盖
    stats = {}
    for row in rows:
        if len(row) < 1:
            continue
        row.sort(key=lambda x: x["cx"])

        name_text = row[0]["text"].strip()
        display_name = name_text
        if normalize_stat_name(display_name) is None:
            # 第一个 item 不是有效名称，尝试第二个
            if len(row) >= 2:
                display_name = row[1]["text"].strip()
            if normalize_stat_name(display_name) is None:
                continue  # 无法识别的名称，跳过该行

        value = None
        for item in reversed(row):
            v = parse_number(item["text"])
            if v is not None:
                value = v
                break

        if value is not None and display_name not in stats:
            stats[display_name] = value

    return stats


def parse_level(ocr_results):
    """从 OCR 结果中提取等级 (0/3/6/9/12/15)"""
    if not ocr_results:
        return None
    for det in ocr_results:
        if det is None or len(det) < 2:
            continue
        text_info = det[1]
        text = str(text_info[0] if isinstance(text_info, (tuple, list))
                   else text_info).strip()
        # 优先匹配有效等级
        m = re.search(r'\b(0|3|6|9|12|15)\b', text)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)', text)
        if m:
            v = int(m.group(1))
            if v in VALID_LEVELS:
                return v
    return None


# ══════════════════════════════════════════════════════════════════════
# 强化次数反推与判定
# ══════════════════════════════════════════════════════════════════════

def determine_times(level, stats):
    """
    根据等级和词条数值反推每个词条的强化次数。
    枚举 N0 ∈ {2,3,4} 和所有组合，选偏离平均值最小的解。
    Returns: (times_dict, n0) 或 (None, None)
    """
    if len(stats) < 2:
        return None, None

    # 收集每个词条的候选强化次数
    candidates = {}
    for name, val in stats.items():
        cand = get_candidate_times(name, val)
        if not cand:
            return None, None
        candidates[name] = cand

    T_base = level // 3
    names = list(candidates.keys())
    best_result = None
    best_score = float("inf")

    for n0 in [2, 3, 4]:
        target = T_base + (4 - n0)
        cand_lists = [candidates[n] for n in names]
        for combo in product(*cand_lists):
            if sum(combo) != target:
                continue
            score = 0.0
            for name, t in zip(names, combo):
                avg = get_threshold(name, t)["avg"]
                val = stats[name]
                score += abs(val - avg) / max(avg, 0.01)
            if score < best_score:
                best_score = score
                best_result = (dict(zip(names, combo)), n0)

    return best_result


def evaluate(stats, times):
    """
    判定：所有词条 当前值 >= 该强化次数平均值 → 保留。
    任一条不达标 → 丢弃。
    Returns: (keep, details_dict)
    """
    if not times:
        return False, {}
    details = {}
    all_pass = True
    for name, t in times.items():
        avg = get_threshold(name, t)["avg"]
        val = stats.get(name, 0)
        ok = val >= avg
        details[name] = {"value": val, "times": t, "avg": avg, "ok": ok}
        if not ok:
            all_pass = False
    return all_pass, details


# ══════════════════════════════════════════════════════════════════════
# 主程序
# ══════════════════════════════════════════════════════════════════════

class CoreSorter:
    def __init__(self):
        base = os.path.dirname(os.path.abspath(__file__))

        with open(os.path.join(base, "coordinates.json"), "r", encoding="utf-8") as f:
            self.coords = json.load(f)
        with open(os.path.join(base, "config.json"), "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        # 验证必要坐标
        for k in ["first_core", "lock_btn", "discard_btn", "swipe_start", "swipe_end"]:
            if self.coords.get(k) is None:
                raise ValueError(f"coordinates.json 缺少字段: {k}")

        # UI 回调（控制面板会覆盖）
        self._ui_log = print
        self._ui_paused = lambda: False
        self._ui_running = lambda: True

        self.t = self.cfg.get("timings", {})
        self.stats_region = self.cfg.get("stats_region")
        self.level_region = self.cfg.get("level_region")

        # OCR
        print("[OCR] 正在初始化 PaddleOCR...")
        self.ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        dummy = np.zeros((50, 200, 3), dtype=np.uint8)
        self.ocr.ocr(dummy, cls=True)
        print("[OCR] 初始化完成")

        # 统计
        self.total = 0
        self.kept = 0
        self.discarded = 0
        self.failed = 0
        self.start_time = None
        self.paused = False

        # 日志
        log_dir = os.path.join(base, "logs")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = os.path.join(log_dir, f"cores_{ts}.csv")
        self.csv_file = open(self.csv_path, "w", encoding="utf-8-sig", newline="")
        self.w = csv.writer(self.csv_file)
        self.w.writerow([
            "序号", "时间", "等级", "N0",
            "词条1", "数值1", "强化1", "平均1", "达标1",
            "词条2", "数值2", "强化2", "平均2", "达标2",
            "词条3", "数值3", "强化3", "平均3", "达标3",
            "词条4", "数值4", "强化4", "平均4", "达标4",
            "判定",
        ])
        self.csv_file.flush()

    def _log(self, msg):
        self._ui_log(msg)

    # ── 底层操作 ────────────────────────────────────────────────

    def tap(self, x, y):
        time.sleep(self.t.get("tap_delay", 0.2)
                   + random.uniform(self.t.get("random_min", 0.1),
                                    self.t.get("random_max", 0.3)))
        adb_tap(x, y)

    def swipe(self, x1, y1, x2, y2):
        adb_swipe(x1, y1, x2, y2)

    def screenshot(self):
        return adb_screenshot()

    def core_pos(self, row, col):
        """计算网格中第 row 行 col 列芯核的点击坐标"""
        b = self.coords["first_core"]
        return (b[0] + col * self.coords["step_x"],
                b[1] + row * self.coords["step_y"])

    # ── OCR ─────────────────────────────────────────────────────

    def ocr_region(self, img, region):
        """截取并 OCR 指定区域，返回 PaddleOCR 原始结果列表"""
        if region is None:
            return []
        x, y, w, h = region
        # 边界保护
        ih, iw = img.shape[:2]
        x = max(0, x)
        y = max(0, y)
        w = min(w, iw - x)
        h = min(h, ih - y)
        if w <= 0 or h <= 0:
            return []
        crop = img[y:y + h, x:x + w]
        results = self.ocr.ocr(crop, cls=True)
        if not results or results[0] is None:
            return []
        return results[0]

    # ── 网格区域对比（判断列表到底） ──────────────────────────

    def grid_roi(self, img):
        """提取网格区域的 ROI"""
        c = self.coords["first_core"]
        sx = self.coords["step_x"]
        sy = self.coords["step_y"]
        m = 30
        x = max(0, c[0] - m)
        y = max(0, c[1] - m)
        w = min(img.shape[1] - x, 4 * sx + 2 * m)
        h = min(img.shape[0] - y, 3 * sy + 2 * m)
        if w <= 0 or h <= 0:
            return None
        return img[y:y + h, x:x + w]

    def is_scroll_dead(self):
        """执行滑动翻页。禁用自动到底检测，由用户手动停止。"""
        ss = self.coords["swipe_start"]
        sy = self.coords["step_y"]
        total = int(sy * 2.78)
        adb_swipe(ss[0], ss[1], ss[0], ss[1] - total, duration=5000)
        time.sleep(self.t.get("page_turn_wait", 1.5))
        return False  # 永不自动停止

    # ── 单个芯核处理 ───────────────────────────────────────────

    def process_one(self, row, col, batch):
        """处理网格中 (row, col) 位置的芯核"""
        self.total += 1

        # 1. 点击芯核
        x, y = self.core_pos(row, col)
        self.tap(x, y)
        time.sleep(self.t.get("detail_wait", 0.5))

        # 2. 截图
        img = self.screenshot()

        # 3. OCR 等级（最多重试3次）
        level = None
        for _ in range(3):
            lr = self.ocr_region(img, self.level_region)
            level = parse_level(lr)
            if level is not None:
                break
            time.sleep(0.3)
            img = self.screenshot()

        if level is None:
            self._fail(row, col, "等级识别失败")
            return

        # 4. OCR 词条（最多重试3次）
        stats = {}
        for _ in range(3):
            sr = self.ocr_region(img, self.stats_region)
            stats = parse_stats(sr)
            if len(stats) >= 2:
                break
            time.sleep(0.3)
            img = self.screenshot()

        if len(stats) < 2:
            self._fail(row, col, f"词条识别不足(仅{len(stats)}个)")
            return

        # 5. 反推强化次数
        times, n0 = determine_times(level, stats)
        if times is None:
            self._fail(row, col, "无法确定强化次数组合")
            return

        # 6. 判定
        keep, details = evaluate(stats, times)

        # 7. 执行操作
        btn = self.coords["lock_btn"] if keep else self.coords["discard_btn"]
        self.tap(btn[0], btn[1])
        if keep:
            self.kept += 1
        else:
            self.discarded += 1
        time.sleep(self.t.get("action_wait", 0.3))

        # 8. 日志
        self._log_result(level, n0, stats, times, details, keep)

        # 9. 控制台输出
        self._print_result(batch, row, col, level, keep, details)

    def _fail(self, row, col, reason):
        """记录失败"""
        self.failed += 1
        ts = datetime.now().strftime("%H:%M:%S")
        self._log(f"[{ts}] [失败] ({row},{col}) {reason}")
        self.w.writerow([
            self.total, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "", "", "", "", "", "", "", "", "", "", "",
            "", "", "", "", "", f"失败:{reason}",
        ])
        self.csv_file.flush()
        gc.collect()

    def _log_result(self, level, n0, stats, times, details, keep):
        """写入 CSV"""
        row = [self.total, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               level, n0]
        entries = list(stats.items())
        for i in range(4):
            if i < len(entries):
                name, val = entries[i]
                t = times.get(name, "?")
                d = details.get(name, {})
                avg = d.get("avg", "?")
                ok = "是" if d.get("ok") else "否"
                row.extend([name, val, t, avg, ok])
            else:
                row.extend(["", "", "", "", ""])
        row.append("保留" if keep else "丢弃")
        self.w.writerow(row)
        self.csv_file.flush()
        # 每50个强制 gc
        if self.total % 50 == 0:
            gc.collect()

    def _print_result(self, batch, row, col, level, keep, details):
        """控制台实时输出"""
        ts = datetime.now().strftime("%H:%M:%S")
        status = "保留" if keep else "丢弃"
        icon = "+" if keep else "-"
        parts = []
        for name, d in details.items():
            parts.append(f"{name}={d['value']}/{d['avg']}({d['times']}次{'Y' if d['ok'] else 'N'})")
        info = " | ".join(parts)
        elapsed = time.time() - self.start_time
        rpm = self.total / (elapsed / 60) if elapsed > 0 else 0
        self._log(f"[{ts}] B{batch}({row},{col}) Lv{level} {icon}{status}")
        for name, d in details.items():
            mark = "Y" if d['ok'] else "N"
            self._log(f"  {name}({d['times']}) {d['value']}/{d['avg']} {mark}")
        self._log(f"  总计:{self.total} 保留:{self.kept} 丢弃:{self.discarded} "
                  f"失败:{self.failed} | {rpm:.1f}个/分钟")

    # ── 暂停处理 ────────────────────────────────────────────────

    def _pause(self):
        elapsed = time.time() - self.start_time
        print(f"\n{'='*45}")
        print(f"[暂停中]")
        print(f"   已处理: {self.total} | 保留: {self.kept} | "
              f"丢弃: {self.discarded} | 失败: {self.failed}")
        print(f"   已耗时: {elapsed/60:.1f} 分钟")
        print(f"   [C] 继续   [S] 详细统计   [Q] 退出")
        print(f"{'='*45}")

        while True:
            try:
                c = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                c = "q"

            if c == "c":
                print("继续运行...\n")
                return
            elif c == "s":
                self._stats()
            elif c == "q":
                self._shutdown()
                sys.exit(0)
            else:
                print("  无效输入，请输入 C/S/Q")

    def _stats(self):
        elapsed = time.time() - self.start_time
        rpm = self.total / (elapsed / 60) if elapsed > 0 else 0
        n = max(self.total, 1)
        print(f"\n  [运行统计]")
        print(f"  总处理: {self.total}")
        print(f"  保留:   {self.kept} ({self.kept/n*100:.1f}%)")
        print(f"  丢弃:   {self.discarded} ({self.discarded/n*100:.1f}%)")
        print(f"  失败:   {self.failed} ({self.failed/n*100:.1f}%)")
        print(f"  耗时:   {elapsed/60:.1f} 分钟")
        print(f"  速度:   {rpm:.1f} 个/分钟")
        eta = (2000 - self.total) / rpm if rpm > 0 else 0
        print(f"  剩余估算:{eta:.0f} 分钟 (假设2000个)")
        print(f"  日志:   {self.csv_path}\n")

    def _shutdown(self):
        if self.csv_file and not self.csv_file.closed:
            self.csv_file.close()
        print(f"\n日志已保存: {self.csv_path}")
        self._stats()

    # ── 主循环 ──────────────────────────────────────────────────

    def _check_ui(self):
        """等待暂停/停止状态解除"""
        while self._ui_running() and self._ui_paused():
            time.sleep(0.3)

    def run_loop(self):
        """供控制面板调用的入口，会检查 UI 回调"""
        self.start_time = time.time()
        self._log("[OCR] 正在初始化 PaddleOCR...")
        # OCR 已在 __init__ 中初始化
        self._log("[OCR] 初始化完成")
        self._log("=== 开始筛选 ===")
        self._main_loop_ui()

    def _main_loop_ui(self):
        """带 UI 回调检查的主循环"""
        batch = 0
        r = 0
        c = 0

        while self._ui_running():
            self._check_ui()
            if not self._ui_running():
                break

            if r == 0 and c == 0:
                batch += 1
                self._log(f"-- 第 {batch} 批 ({(batch-1)*12+1}~{batch*12}) --")

            while r < 3 and self._ui_running():
                self._check_ui()
                while c < 4 and self._ui_running():
                    self._check_ui()
                    if not self._ui_running():
                        break
                    try:
                        self.process_one(r, c, batch)
                    except Exception as e:
                        self._fail(r, c, f"异常: {e}")
                    c += 1
                c = 0
                r += 1

            if not self._ui_running():
                break

            r = 0
            c = 0
            self._log("滑动加载下一批...")
            at_end = self.is_scroll_dead()
            if at_end:
                self._log("[完成] 已到列表底部，全部处理完成！")
                break
            time.sleep(0.5)

        self._shutdown()

    def run(self):
        """命令行入口（保留 Ctrl+C 暂停）"""
        if not check_adb():
            return

        print("\n" + "=" * 50)
        print("  恋与深空 - 芯核全自动筛选工具")
        print("=" * 50)
        print("  Ctrl+C = 暂停")
        print("=" * 50 + "\n")

        if self.start_time is None:
            self.start_time = time.time()
        self._main_loop_ui()


if __name__ == "__main__":
    CoreSorter().run()
