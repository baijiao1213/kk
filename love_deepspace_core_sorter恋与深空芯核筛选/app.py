"""
恋与深空芯核全自动筛选工具 - 一体化程序
一个窗口完成：连接手机 → 投屏(可选) → 筛选 → 关闭
"""
import sys, os, json, time, threading, queue, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core_sorter import CoreSorter


# ═══════════════════════════════════════════════
# 工具路径检测
# ═══════════════════════════════════════════════

def find_tool(name, candidates):
    # 优先从 exe 所在目录（及其 scrcpy 子目录）中查找
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        for sub in ["", "scrcpy"]:
            p = os.path.join(base, sub, name + ".exe")
            if os.path.exists(p):
                return p
    found = shutil.which(name)
    if found: return found
    for c in candidates:
        if os.path.exists(c): return c
    return None

ADB = find_tool("adb", [
    r"C:\scrcpy\scrcpy-win64-v4.0\adb.exe",
    r"C:\scrcpy\adb.exe",
])
SCRCPY = find_tool("scrcpy", [
    r"C:\scrcpy\scrcpy-win64-v4.0\scrcpy.exe",
    r"C:\scrcpy\scrcpy.exe",
])


# ═══════════════════════════════════════════════
# ADB 操作
# ═══════════════════════════════════════════════

def adb_run(*args, timeout=15):
    try:
        r = subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def adb_pair(addr, code):
    return adb_run("pair", addr, code)

def adb_connect(addr):
    return adb_run("connect", addr)

def adb_disconnect():
    adb_run("disconnect")

def adb_devices():
    code, out, _ = adb_run("devices")
    devs = []
    for line in out.split("\n")[1:]:
        if "\tdevice" in line:
            devs.append(line.split("\t")[0])
    return devs


# ═══════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════

import tkinter as tk
from tkinter import messagebox


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("恋与深空 - 芯核筛选工具")
        self.root.geometry("720x780")
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.device_addr = None   # 当前连接的设备
        self.scrcpy_proc = None   # scrcpy 子进程
        self.sorter = None        # CoreSorter 实例
        self.sorter_thread = None
        self.running = False
        self.paused = False
        self.log_queue = queue.Queue()

        self._build_ui()
        self.poll_log()
        self.root.after(500, self._check_env)

    # ── UI 构建 ─────────────────────────────

    BG  = "#e0e7ff"
    CARD = "white"
    PRIMARY = "#6366f1"
    PRIMARY_TXT = "#f8fafc"
    SECONDARY = "#818cf8"
    SECONDARY_TXT = "#f8fafc"
    SUCCESS = "#6366f1"
    SUCCESS_TXT = "#f8fafc"
    WARNING = "#818cf8"
    WARNING_TXT = "#f8fafc"
    DANGER = "#818cf8"
    DANGER_TXT = "#f8fafc"
    INFO = "#818cf8"
    INFO_TXT = "#f8fafc"
    DARK = "#1e293b"
    DARK_TXT = "#f8fafc"
    TEXT = "#1e293b"
    MUTED = "#64748b"
    INPUT_BG = "white"
    BTN_FONT = ("Microsoft YaHei", 10)
    HDR_FONT = ("Microsoft YaHei", 11, "bold")

    def _section(self, parent, num, title):
        """创建带左侧色条的区块"""
        outer = tk.Frame(parent, bg=self.BG)
        bar = tk.Frame(outer, bg=self.PRIMARY, width=4)
        bar.pack(side=tk.LEFT, fill=tk.Y)
        card = tk.Frame(outer, bg=self.CARD, padx=14, pady=10)
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hdr = tk.Label(card, text=f"  {num}. {title}", font=self.HDR_FONT,
                       fg=self.TEXT, bg=self.CARD, anchor=tk.W)
        hdr.pack(fill=tk.X, pady=(0, 6))
        return outer, card

    def _btn(self, parent, text, command, bg, state=tk.NORMAL, bold=False, fg="#f8fafc"):
        f = ("Microsoft YaHei", 10, "bold") if bold else ("Microsoft YaHei", 9)
        return tk.Button(parent, text=text, command=command, font=f,
                         bg=bg, fg=fg, activebackground=bg,
                         activeforeground=fg, bd=0, padx=14, pady=5,
                         cursor="hand2", state=state)

    def _entry(self, parent, var, width, hint=""):
        e = tk.Entry(parent, textvariable=var, width=width,
                     font=("Consolas", 11), bg=self.INPUT_BG, fg=self.DARK,
                     insertbackground=self.DARK, bd=1, relief=tk.SOLID)
        e.pack(side=tk.LEFT, padx=(4, 2))
        if hint:
            tk.Label(parent, text=hint, font=("Microsoft YaHei", 7),
                     fg=self.MUTED, bg=self.CARD).pack(side=tk.LEFT, padx=(0, 10))
        return e

    def _stat_card(self, parent, label, key):
        f = tk.Frame(parent, bg="#f5f5f5", padx=8, pady=4,
                     highlightbackground="#e0e0e0", highlightthickness=1)
        f.pack(side=tk.LEFT, padx=3)
        tk.Label(f, text=label, font=("Microsoft YaHei", 7),
                 fg=self.MUTED, bg="#f5f5f5").pack()
        val = tk.Label(f, text="-", font=("Microsoft YaHei", 12, "bold"),
                       fg="#333", bg="#f5f5f5")
        val.pack()
        return val

    def _build_ui(self):
        # 顶部标题栏
        top = tk.Frame(self.root, bg="white", height=48, highlightbackground="#ddd", highlightthickness=1)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="恋与深空  芯核全自动筛选", font=("Microsoft YaHei", 13, "bold"),
                 fg=self.PRIMARY, bg="white").pack(side=tk.LEFT, padx=16, pady=10)
        tk.Label(top, text="v1.0.0", font=("Microsoft YaHei", 8),
                 fg=self.MUTED, bg="white").pack(side=tk.RIGHT, padx=16, pady=10)

        # 主内容区
        main = tk.Frame(self.root, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 0))

        # ── Step 1: 连接 ──
        s1_outer, s1 = self._section(main, 1, "连接手机")
        s1_outer.pack(fill=tk.X, pady=(0, 4))

        r1 = tk.Frame(s1, bg=self.CARD)
        r1.pack(fill=tk.X)
        tk.Label(r1, text="配对码", font=("Microsoft YaHei", 9),
                 fg=self.MUTED, bg=self.CARD).pack(side=tk.LEFT)
        self.pair_code_var = tk.StringVar()
        self._entry(r1, self.pair_code_var, 8, "6位数字")
        tk.Label(r1, text="配对端口", font=("Microsoft YaHei", 9),
                 fg=self.MUTED, bg=self.CARD).pack(side=tk.LEFT, padx=(6, 0))
        self.pair_addr_var = tk.StringVar()
        self._entry(r1, self.pair_addr_var, 18, "如 192.168.1.3:40571")
        tk.Label(r1, text="连接端口", font=("Microsoft YaHei", 9),
                 fg=self.MUTED, bg=self.CARD).pack(side=tk.LEFT, padx=(6, 0))
        self.connect_port_var = tk.StringVar()
        self._entry(r1, self.connect_port_var, 7, "如 38977")

        r1b = tk.Frame(s1, bg=self.CARD)
        r1b.pack(fill=tk.X, pady=(6, 0))
        self.connect_btn = self._btn(r1b, "连接", self.do_connect_all, self.PRIMARY, bold=True)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.repair_btn = self._btn(r1b, "重配", self.reset_pair, self.SECONDARY, fg=self.SECONDARY_TXT)
        self.repair_btn.pack(side=tk.LEFT, padx=4)

        self.conn_status = tk.Label(s1, font=("Microsoft YaHei", 8),
                                    fg=self.MUTED, bg=self.CARD, anchor=tk.W)
        self.conn_status.pack(fill=tk.X, pady=(4, 0))
        self.conn_status.config(text="未连接 | 输入配对码、配对端口、连接端口，点连接")

        # ── Step 2: 坐标 ──
        s2_outer, s2 = self._section(main, 2, "坐标测量（首次使用 / 换手机时）")
        s2_outer.pack(fill=tk.X, pady=4)
        r2 = tk.Frame(s2, bg=self.CARD)
        r2.pack(fill=tk.X)
        self.measure_btn = self._btn(r2, "打开坐标测量工具", self.open_measure_tool, self.SECONDARY, fg=self.SECONDARY_TXT)
        self.measure_btn.pack(side=tk.LEFT)
        self.coord_status = tk.Label(r2, font=("Microsoft YaHei", 9),
                                     fg=self.MUTED, bg=self.CARD)
        self.coord_status.pack(side=tk.LEFT, padx=10)
        self._check_coords_file()

        # ── Step 3: 投屏 ──
        s3_outer, s3 = self._section(main, 3, "投屏（可选）")
        s3_outer.pack(fill=tk.X, pady=4)
        r3 = tk.Frame(s3, bg=self.CARD)
        r3.pack(fill=tk.X)
        self.mirror_on_btn = self._btn(r3, "打开投屏", self.start_mirror, self.PRIMARY, fg=self.PRIMARY_TXT)
        self.mirror_on_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.mirror_off_btn = self._btn(r3, "关闭投屏", self.stop_mirror, self.SECONDARY, fg=self.SECONDARY_TXT)
        self.mirror_off_btn.pack(side=tk.LEFT)
        self.mirror_status = tk.Label(r3, font=("Microsoft YaHei", 9),
                                      fg=self.MUTED, bg=self.CARD)
        self.mirror_status.pack(side=tk.LEFT, padx=10)
        self.mirror_status.config(text="投屏未启动")

        # ── Step 4: 筛选 ──
        s4_outer, s4 = self._section(main, 4, "筛选控制")
        s4_outer.pack(fill=tk.X, pady=4)
        r4 = tk.Frame(s4, bg=self.CARD)
        r4.pack(fill=tk.X)
        self.start_btn = self._btn(r4, "开始筛选", self.start_screening, self.SECONDARY, bold=True, fg=self.SECONDARY_TXT)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.pause_btn = self._btn(r4, "暂停", self.toggle_pause, self.BG, bold=True, fg=self.DARK)
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.stop_btn = self._btn(r4, "停止", self.stop_screening, self.PRIMARY, bold=True, fg=self.PRIMARY_TXT)
        self.stop_btn.pack(side=tk.LEFT)

        stats_f = tk.Frame(s4, bg=self.CARD)
        stats_f.pack(fill=tk.X, pady=(8, 0))
        self.stat_labels = {}
        for key, label in [("total","已处理"), ("kept","保留"), ("discarded","丢弃"),
                           ("failed","失败"), ("batch","批次"), ("speed","速度")]:
            self.stat_labels[key] = self._stat_card(stats_f, label, key)

        # ── 日志区 ──
        log_outer, log_card = self._section(main, "", "运行日志")
        log_outer.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        clear_row = tk.Frame(log_card, bg=self.CARD)
        clear_row.pack(fill=tk.X, pady=(0, 4))
        tk.Button(clear_row, text="清除历史日志", command=self.clear_logs,
                  font=("Microsoft YaHei", 7), bg="#444", fg="white",
                  bd=0, padx=8, pady=2, cursor="hand2").pack(side=tk.RIGHT)

        self.log_text = tk.Text(log_card, height=16, bg="#fafafa", fg="#333",
                                font=("Consolas", 9), insertbackground="#333",
                                state=tk.DISABLED, bd=1, relief=tk.SOLID,
                                padx=6, pady=4)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(self.log_text)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=sb.set)
        sb.config(command=self.log_text.yview)

    # ── 日志 ────────────────────────────────

    def log(self, msg):
        self.log_queue.put(msg)

    def poll_log(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        if self.running:
            self._update_stats()
        self.root.after(300, self.poll_log)

    def _update_stats(self):
        if not self.sorter: return
        s = self.sorter
        self.stat_labels["total"].config(text=str(s.total))
        self.stat_labels["kept"].config(text=str(s.kept))
        self.stat_labels["discarded"].config(text=str(s.discarded))
        self.stat_labels["failed"].config(text=str(s.failed))
        elapsed = time.time() - s.start_time if s.start_time else 0
        rpm = s.total / (elapsed / 60) if elapsed > 0 else 0
        self.stat_labels["speed"].config(text=f"{rpm:.1f}/min")

    # ── 环境检查 ────────────────────────────

    def _check_env(self):
        msgs = []
        if not ADB:
            msgs.append("ADB 未找到，请检查 C:\\scrcpy 目录")
        if not SCRCPY:
            msgs.append("scrcpy 未找到（投屏不可用）")
        if msgs:
            for m in msgs:
                self.log(f"[警告] {m}")
        else:
            self.log("[就绪] ADB + scrcpy 已找到")

    # ── 连接 ───────────────────────────────

    def do_connect_all(self):
        """一键配对+连接（配对后立刻连接，防止端口过期）"""
        code = self.pair_code_var.get().strip()
        pair_addr = self.pair_addr_var.get().strip()
        connect_port = self.connect_port_var.get().strip()

        if not code or not pair_addr or not connect_port:
            messagebox.showwarning("提示", "请填写配对码、配对端口、连接端口")
            return
        if ":" not in pair_addr:
            messagebox.showwarning("提示", "配对端口格式: 192.168.1.3:40571")
            return
        if ":" in connect_port:
            connect_port = connect_port.split(":")[-1]

        self.connect_btn.config(state=tk.DISABLED, text="连接中...")
        self.conn_status.config(text="正在配对+连接...", fg=self.WARNING)
        self.log(f"[连接] 配对 {pair_addr}, 连接端口 {connect_port} ...")
        self.root.update()

        # 1. 配对
        ret, out, err = adb_pair(pair_addr, code)
        if ret != 0:
            self.log(f"[失败] 配对失败: {err}")
            self.conn_status.config(text=f"配对失败: {err}", fg=self.DANGER)
            self.connect_btn.config(state=tk.NORMAL, text="连接")
            return

        # 2. 马上连接（不延迟，端口可能很快过期）
        ip = pair_addr.split(":")[0]
        full_addr = f"{ip}:{connect_port}"
        self.log(f"[连接] 配对成功，立即连接 {full_addr} ...")
        ret, out, err = adb_connect(full_addr)
        if ret == 0 and "connected" in out.lower():
            self.device_addr = full_addr
            self.log(f"[成功] 已连接 {full_addr}")
            self.conn_status.config(text=f"已连接 {full_addr}", fg=self.SUCCESS)
            self.connect_btn.config(text="已连接", state=tk.DISABLED, bg=self.SUCCESS)
            self.repair_btn.config(state=tk.NORMAL)
            self._on_connected()
        else:
            self.log(f"[失败] 连接失败: {out} {err}")
            self.conn_status.config(text="连接失败，端口可能过期，点重配再试", fg=self.DANGER)
            self.connect_btn.config(state=tk.NORMAL, text="重试连接")

    def reset_pair(self):
        """重新配对：清除连接状态，重启ADB"""
        adb_disconnect()
        adb_run("kill-server")
        time.sleep(0.5)
        adb_run("start-server")
        self.device_addr = None
        self.connect_btn.config(state=tk.NORMAL, text="连接")
        self.repair_btn.config(state=tk.DISABLED)
        self.conn_status.config(text="未连接 | 填入三项后点连接", fg=self.MUTED)
        self.log("[重置] 已清除连接状态")
        self.measure_btn.config(state=tk.DISABLED)
        self.mirror_on_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self._set_ctrl_state("stopped")

    def _on_connected(self):
        self.measure_btn.config(state=tk.NORMAL)
        self._check_coords_file()
        self.mirror_on_btn.config(state=tk.NORMAL)
        self.start_btn.config(state=tk.NORMAL)

    def _check_coords_file(self):
        base = os.path.dirname(os.path.abspath(__file__))
        coords_path = os.path.join(base, "coordinates.json")
        has_coords = os.path.exists(coords_path)
        if has_coords:
            self.coord_status.config(text="坐标文件已就绪", fg="#4CAF50")
        else:
            self.coord_status.config(text="未测量坐标，请先打开坐标测量工具", fg=self.WARNING)
        # 更新筛选按钮状态（如果按钮已创建）
        if hasattr(self, 'start_btn'):
            if has_coords and self.device_addr:
                self.start_btn.config(state=tk.NORMAL)
            else:
                self.start_btn.config(state=tk.DISABLED)

    def open_measure_tool(self):
        base = os.path.dirname(os.path.abspath(__file__))
        tool_path = os.path.join(base, "measure_coords_tk.py")
        self.log("[测量] 正在打开坐标测量工具...")
        try:
            subprocess.Popen([sys.executable, tool_path],
                           creationflags=subprocess.CREATE_NO_WINDOW)
            # 监听坐标文件是否生成
            self.root.after(2000, self._watch_coords_file)
        except Exception as e:
            self.log(f"[测量] 打开失败: {e}")

    def _watch_coords_file(self):
        self._check_coords_file()
        if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "coordinates.json")):
            self.root.after(2000, self._watch_coords_file)

    # ── 投屏 ────────────────────────────────

    def start_mirror(self):
        if not self.device_addr or not SCRCPY:
            return
        self.stop_mirror()
        try:
            self.scrcpy_proc = subprocess.Popen(
                [SCRCPY, "-s", self.device_addr, "--no-audio", "--max-size", "800"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.mirror_status.config(text="投屏运行中", fg="#4CAF50")
            self.mirror_on_btn.config(state=tk.DISABLED)
            self.mirror_off_btn.config(state=tk.NORMAL)
            self.log("[投屏] 已启动")
        except Exception as e:
            self.log(f"[投屏] 启动失败: {e}")

    def stop_mirror(self):
        if self.scrcpy_proc:
            try:
                self.scrcpy_proc.kill()
                self.scrcpy_proc.wait(timeout=1)
            except:
                pass
            self.scrcpy_proc = None
        self.mirror_status.config(text="投屏已关闭", fg="#888")
        self.mirror_on_btn.config(state=tk.NORMAL if self.device_addr else tk.DISABLED)
        self.mirror_off_btn.config(state=tk.DISABLED)
        self.log("[投屏] 已关闭")

    # ── 筛选 ────────────────────────────────

    def start_screening(self):
        if not self.device_addr:
            self.log("[错误] 请先连接手机")
            return

        try:
            self.sorter = CoreSorter()
        except Exception as e:
            self.log(f"[错误] 初始化失败: {e}")
            return

        self.sorter._ui_log = self.log
        self.sorter._ui_paused = lambda: self.paused
        self.sorter._ui_running = lambda: self.running

        self.running = True
        self.paused = False
        self._set_ctrl_state("running")
        self.log("=== 开始筛选 ===")

        self.sorter_thread = threading.Thread(target=self._run_sorter, daemon=True)
        self.sorter_thread.start()

    def _run_sorter(self):
        try:
            self.sorter.start_time = time.time()
            self.sorter.run_loop()
        except Exception as e:
            self.log(f"[异常] {e}")
        finally:
            self.running = False
            self.root.after(0, self._on_screening_end)

    def _on_screening_end(self):
        self._set_ctrl_state("stopped")
        self._update_stats()
        self.log("=== 筛选结束 ===")

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self._set_ctrl_state("paused")
            self.log("--- 已暂停 ---")
        else:
            self._set_ctrl_state("running")
            self.log("--- 继续运行 ---")

    def stop_screening(self):
        self.log("--- 正在停止... ---")
        self.running = False
        self.paused = False

    def _set_ctrl_state(self, state):
        if state == "stopped":
            self.start_btn.config(state=tk.NORMAL if self.device_addr else tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED, text="暂停")
            self.stop_btn.config(state=tk.DISABLED)
        elif state == "running":
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL, text="暂停")
            self.stop_btn.config(state=tk.NORMAL)
        elif state == "paused":
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL, text="继续")
            self.stop_btn.config(state=tk.NORMAL)

    def clear_logs(self):
        base = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base, "logs")
        if not os.path.exists(log_dir):
            return
        files = [f for f in os.listdir(log_dir) if f.endswith(".csv")]
        if not files:
            self.log("[日志] 没有可清除的日志")
            return
        ok = messagebox.askyesno("确认", f"将删除 {len(files)} 个日志文件，不可恢复。确认？")
        if not ok:
            return
        for f in files:
            os.remove(os.path.join(log_dir, f))
        self.log(f"[日志] 已清除 {len(files)} 个日志文件")

    # ── 关闭 ────────────────────────────────

    def on_close(self):
        self.running = False
        self.paused = False

        if self.sorter:
            try:
                self.sorter._shutdown()
            except:
                pass

        self.stop_mirror()
        adb_disconnect()
        self.root.destroy()


if __name__ == "__main__":
    App().root.mainloop()
