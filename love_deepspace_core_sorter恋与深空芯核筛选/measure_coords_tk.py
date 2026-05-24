"""坐标测量工具 - Tkinter 版本（带点击验证）"""
import subprocess, sys, json, os, shutil, io, time
import tkinter as tk
from tkinter import messagebox
import numpy as np
from PIL import Image, ImageTk

def _find_adb():
    # 优先从 exe 所在目录查找（PyInstaller 打包后）
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        for sub in ["", "scrcpy"]:
            p = os.path.join(base, sub, "adb.exe")
            if os.path.exists(p): return p
    adb = shutil.which("adb")
    if adb: return adb
    for c in [r"C:\scrcpy\scrcpy-win64-v4.0\adb.exe", r"C:\scrcpy\adb.exe"]:
        if os.path.exists(c): return c
    return "adb"
ADB = _find_adb()
NO_WIN = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

def _get_device():
    r = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=10, creationflags=NO_WIN)
    for line in r.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            return line.split("\t")[0]
    return None

def adb_screenshot():
    dev = _get_device()
    if not dev: raise RuntimeError("未检测到设备")
    r = subprocess.run([ADB, "-s", dev, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=15, creationflags=NO_WIN)
    if r.returncode != 0:
        raise RuntimeError(f"ADB截图失败: {r.stderr.decode()}")
    return Image.open(io.BytesIO(r.stdout))

def adb_tap(x, y):
    dev = _get_device()
    subprocess.run([ADB, "-s", dev, "shell", "input", "tap", str(x), str(y)],
                   capture_output=True, timeout=10, creationflags=NO_WIN)

def adb_swipe(x1, y1, x2, y2, dur=500):
    dev = _get_device()
    subprocess.run([ADB, "-s", dev, "shell", "input", "swipe",
                    str(x1), str(y1), str(x2), str(y2), str(dur)],
                   capture_output=True, timeout=15, creationflags=NO_WIN)

# ====== 测量阶段 ======
# 分为：标记阶段(0-5) → 测试阶段(6) → 翻页标记(7-8) → 翻页测试(9)

STEPS = [
    # Phase 1: 截屏 + 标记
    ("截屏", "先点击任意芯核展开详情，然后点截屏", None),
    ("点第1行第1列芯核中心", "grid_c1", None),
    ("点第1行第2列芯核中心", "grid_c2", None),
    ("点第2行第1列芯核中心", "grid_c3", None),
    ("点上锁按钮", "lock_btn", None),
    ("点弃置按钮", "discard_btn", None),
    ("点等级数字左上角", "level_tl", None),
    ("点等级数字右下角", "level_br", None),
    ("点词条区域左上角", "stats_tl", None),
    ("点词条区域右下角", "stats_br", None),
    # Phase 2: 测试点击
    ("_test_click", "正在测试锁/弃置按钮...", None),
    # Phase 3: 翻页标记
    ("点滑动起点(网格底部)", "swipe_start", None),
    ("点滑动终点(网格顶部)", "swipe_end", None),
    # Phase 4: 测试翻页
    ("_test_swipe", "正在测试翻页...", None),
    ("完成", None, None),
]

class MeasureApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("芯核筛选 - 坐标测量")
        self.step = 0
        self.clicks = {}
        self.phone_img = None
        self.tk_img = None
        self.canvas_img_id = None
        self.scale = 1.0
        self.display_w = 480
        self._test_failed = False  # 翻页测试是否失败

        # 顶部状态
        self.label = tk.Label(self.root, text="", font=("Microsoft YaHei", 12),
                              fg="white", bg="#333", pady=8)
        self.label.pack(fill=tk.X)

        # 画布
        self.canvas = tk.Canvas(self.root, width=480, height=680, bg="#222")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_move)

        # 按钮区
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=6)
        self.main_btn = tk.Button(btn_frame, text="截屏",
                                  command=self.do_main_action,
                                  font=("Microsoft YaHei", 11), padx=20, pady=6)
        self.main_btn.pack(side=tk.LEFT, padx=4)
        self.undo_btn = tk.Button(btn_frame, text="撤销",
                                  command=self.undo,
                                  font=("Microsoft YaHei", 11), padx=14, pady=6)
        self.undo_btn.pack(side=tk.LEFT, padx=4)
        self.skip_btn = tk.Button(btn_frame, text="重测翻页",
                                  command=self.retry_swipe,
                                  font=("Microsoft YaHei", 11), padx=14, pady=6,
                                  state=tk.DISABLED)
        self.skip_btn.pack(side=tk.LEFT, padx=4)

        # 状态栏
        self.status_label = tk.Label(self.root, text="", font=("Microsoft YaHei", 10),
                                     fg="#aaa", bg="#222")
        self.status_label.pack(fill=tk.X, ipady=4)

        # 键盘
        self.root.bind("<space>", lambda e: self.do_main_action())
        self.root.bind("u", lambda e: self.undo())
        self.root.bind("U", lambda e: self.undo())
        self.root.bind("q", lambda e: self.root.quit())
        self.root.bind("Q", lambda e: self.root.quit())

        self.update_step()

    # ====== UI 更新 ======

    def update_step(self):
        if self.step >= len(STEPS):
            self.finish(); return
        title, key, extra = STEPS[self.step]
        self.label.config(text=f"[{self.step+1}/{len(STEPS)}] {title}")

        if title == "_test_click":
            self._run_click_test()
        elif title == "_test_swipe":
            self._run_swipe_test()
        elif title == "完成":
            self.finish()
        else:
            is_screenshot = (key is None and title == "截屏")
            is_click_step = (key is not None and not key.startswith("swipe"))
            is_swipe_step = (key is not None and key.startswith("swipe"))

            self.main_btn.config(text="截屏" if is_screenshot else "",
                                 state=tk.NORMAL if is_screenshot else tk.DISABLED)
            self.skip_btn.config(state=tk.NORMAL if is_swipe_step else tk.DISABLED,
                                 text="重测翻页")

    # ====== 截图 ======

    def take_screenshot(self):
        try:
            self.status_label.config(text="正在截屏..."); self.root.update()
            self.phone_img = adb_screenshot()
            w, h = self.phone_img.size
            self.scale = self.display_w / w
            new_h = int(h * self.scale)
            resized = self.phone_img.resize((self.display_w, new_h), Image.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(resized)
            self.canvas.config(width=self.display_w, height=new_h)
            if self.canvas_img_id: self.canvas.delete(self.canvas_img_id)
            self.canvas_img_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
            self._redraw_clicks()
            self.status_label.config(text=f"截图完成 | 分辨率 {w}x{h}")
            self.advance()
        except Exception as e:
            self.status_label.config(text=f"截图失败: {e}")

    # ====== 点击 ======

    def on_click(self, event):
        if self.step >= len(STEPS): return
        title, key, _ = STEPS[self.step]
        if key is None: return  # 截屏或测试步骤，不记录
        px = int(event.x / self.scale)
        py = int(event.y / self.scale)
        self.clicks[key] = (px, py)
        self._draw_point(event.x, event.y, key)
        self.status_label.config(text=f"已记录 {key}: ({px}, {py})")
        self.advance()

    def on_move(self, event):
        if self.phone_img:
            px, py = int(event.x / self.scale), int(event.y / self.scale)
            self.status_label.config(text=f"手机坐标 ({px}, {py})")

    # ====== 步进 ======

    def advance(self):
        self.step += 1
        if self.step >= len(STEPS):
            self.finish(); return
        title, key, _ = STEPS[self.step]

        # 跳过测试步骤的标题更新，测试方法会自己处理
        if title.startswith("_"):
            self.update_step()
            return

        self.update_step()
        self.status_label.config(text=f"[{self.step+1}/{len(STEPS)}] {title}")

    # ====== 按钮 ======

    def do_main_action(self):
        title, key, _ = STEPS[self.step]
        if key is None and title == "截屏":
            self.take_screenshot()

    def retry_swipe(self):
        """回到翻页标记的第一步，重新测翻页"""
        # 找到第一个 swipe 步骤
        for i, (title, key, _) in enumerate(STEPS):
            if key and key.startswith("swipe"):
                # 清除旧的翻页记录
                for k in list(self.clicks.keys()):
                    if k.startswith("swipe"):
                        del self.clicks[k]
                self.step = i
                self._test_failed = False
                self.update_step()
                self._redraw_clicks()
                self.status_label.config(text="请重新标记翻页起终点")
                return

    # ====== 绘制 ======

    def _draw_point(self, dx, dy, label):
        r = 4
        self.canvas.create_oval(dx-r, dy-r, dx+r, dy+r, fill="lime", outline="")
        self.canvas.create_text(dx+10, dy-10, text=label, fill="lime",
                                font=("Microsoft YaHei", 8), anchor=tk.W)

    def _redraw_clicks(self):
        if not self.tk_img or not self.canvas_img_id: return
        self.canvas.delete("all")
        self.canvas_img_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        for k, (px, py) in self.clicks.items():
            if k.startswith("_"): continue
            dx, dy = px * self.scale, py * self.scale
            self._draw_point(dx, dy, k)
        # 画矩形
        for tl_k, br_k in [("level_tl", "level_br"), ("stats_tl", "stats_br")]:
            if tl_k in self.clicks and br_k in self.clicks:
                tlx = self.clicks[tl_k][0] * self.scale
                tly = self.clicks[tl_k][1] * self.scale
                brx = self.clicks[br_k][0] * self.scale
                bry = self.clicks[br_k][1] * self.scale
                self.canvas.create_rectangle(tlx, tly, brx, bry, outline="yellow")

    # ====== 测试阶段 ======

    def _run_click_test(self):
        self.label.config(text="[测试] 正在验证按钮位置...")
        self.status_label.config(text="依次点击锁定按钮、弃置按钮、第1个芯核，请在手机上观察...")
        self.main_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        self.root.update()

        # 依次点击：lock → discard → first_core
        for key, desc in [("lock_btn", "锁定"), ("discard_btn", "弃置"), ("grid_c1", "芯核(1,1)")]:
            if key not in self.clicks:
                self.status_label.config(text=f"缺少坐标: {key}")
                return
            x, y = self.clicks[key]
            self.status_label.config(text=f"点击 {desc} ({x},{y})，请观察手机...")
            self.root.update()
            adb_tap(x, y)
            time.sleep(0.8)

        # 询问用户
        ok = messagebox.askyesno("验证点击",
                                 "请在手机上确认：\n\n"
                                 "1. 锁定按钮被点到了吗？\n"
                                 "2. 弃置按钮被点到了吗？\n"
                                 "3. 芯核详情显示出来了吗？\n\n"
                                 "位置都对 → 点「是」继续\n"
                                 "有偏差 → 点「否」重新测量")
        if ok:
            self.status_label.config(text="点击测试通过!")
            self.advance()
        else:
            self.status_label.config(text="点击测试未通过，请按U回退重新标记")
            messagebox.showinfo("重测提示",
                                "请按 U 键回退到之前的步骤重新标记。\n"
                                "建议：调整标记位置后再次运行测试。")

    def _run_swipe_test(self):
        self.label.config(text="[测试] 正在验证翻页距离...")
        self.status_label.config(text="执行滑动，请在手机上观察翻页效果...")
        self.main_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.NORMAL)
        self.root.update()

        if "swipe_start" not in self.clicks or "swipe_end" not in self.clicks:
            self.status_label.config(text="缺少翻页坐标")
            return

        ss = self.clicks["swipe_start"]
        se = self.clicks["swipe_end"]

        # 先截一张图
        before = adb_screenshot()
        self.status_label.config(text="滑动中...")
        self.root.update()
        adb_swipe(ss[0], ss[1], se[0], se[1], dur=5000)
        time.sleep(1.5)
        after = adb_screenshot()

        # 保存对比图
        before.save("swipe_test_before.png")
        after.save("swipe_test_after.png")

        self.status_label.config(text="已保存对比图: swipe_test_before/after.png")

        ok = messagebox.askyesno("验证翻页",
                                 "请对比手机上的翻页效果：\n\n"
                                 "翻页距离刚好（12个新芯核）→ 点「是」保存\n"
                                 "翻过头或没翻够 → 点「否」调整\n\n"
                                 "(也可对比 swipe_test_before/after.png)")
        if ok:
            self.status_label.config(text="翻页测试通过! 正在保存...")
            self.advance()
        else:
            self.status_label.config(text="翻页测试未通过，请点击「重测翻页」按钮重新标记")
            self._test_failed = True
            self.skip_btn.config(state=tk.NORMAL)
            # 不自动前进，等待用户点「重测翻页」

    # ====== 撤销 ======

    def undo(self):
        # 回退到上一个可标记的步骤
        for i in range(self.step - 1, -1, -1):
            title, key, _ = STEPS[i]
            if key and not title.startswith("_"):
                if key in self.clicks:
                    del self.clicks[key]
                self.step = i
                self.update_step()
                self._redraw_clicks()
                self.status_label.config(text=f"已撤销，当前: {title}")
                return
            if title == "截屏":
                self.step = i
                self.update_step()
                self.status_label.config(text=f"已回退到截屏步骤")
                return
        self.step = 0
        self.update_step()
        self.status_label.config(text="已回到第一步")

    # ====== 完成 ======

    def finish(self):
        c1 = self.clicks.get("grid_c1")
        c2 = self.clicks.get("grid_c2")
        c3 = self.clicks.get("grid_c3")
        step_x = c2[0] - c1[0] if (c1 and c2) else 0
        step_y = c3[1] - c1[1] if (c1 and c3) else 0

        coords = {
            "first_core": c1, "step_x": step_x, "step_y": step_y,
            "lock_btn": self.clicks.get("lock_btn"),
            "discard_btn": self.clicks.get("discard_btn"),
            "swipe_start": self.clicks.get("swipe_start"),
            "swipe_end": self.clicks.get("swipe_end"),
        }
        config = {
            "level_region": self._rect("level_tl", "level_br"),
            "stats_region": self._rect("stats_tl", "stats_br"),
            "timings": {
                "tap_delay": 0.2, "detail_wait": 0.5,
                "ocr_wait": 0.2, "action_wait": 0.3,
                "page_turn_wait": 1.5,
                "random_min": 0.1, "random_max": 0.3,
            },
        }

        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, "coordinates.json"), "w", encoding="utf-8") as f:
            json.dump(coords, f, indent=2, ensure_ascii=False)
        with open(os.path.join(base, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        self.label.config(text="全部完成! 坐标已保存", bg="#060")
        self.status_label.config(text=f"step_x={step_x}, step_y={step_y}")
        self.main_btn.config(state=tk.DISABLED)
        self.skip_btn.config(state=tk.DISABLED)
        messagebox.showinfo("完成", f"坐标已保存!\n\n网格间距: {step_x}x{step_y}\n\n"
                            f"可以关闭此窗口, 回到主程序开始筛选。")

    def _rect(self, k1, k2):
        a, b = self.clicks.get(k1), self.clicks.get(k2)
        if a and b:
            return [min(a[0], b[0]), min(a[1], b[1]), abs(b[0]-a[0]), abs(b[1]-a[1])]
        return None

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MeasureApp().run()
