"""Iven Pet v4 · 3D 手办版桌面宠（行为状态机，运行时零第三方依赖）。

素材来自豆包生成的 3D 三视图 + 6 姿势表情Sheet，由 tools/make_frames3d.py
切片抠图产出 frames3d/。伪 3D：侧视图走路分左右、360° 转体展示。

状态机：GREET(落地打招呼) → IDLE(呼吸) → WALK(走动) → GRAB(挣扎) →
        FALL(重力下落) → LAND(压扁) → SLEEP(睡着) + CHEER(打板) / SPIN(转一圈)

平台：屏幕底部 + 所有可见窗口的顶边（Shimeji 式）——掉落时踩到就落地，
     沿窗口顶边行走，窗口关闭/移走会跟着掉下来。

    python pet.py
"""
import random
import tkinter as tk

try:                    # Windows：枚举窗口顶边当平台
    import ctypes
    from ctypes import wintypes
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
except (ImportError, AttributeError):   # 非 Windows：只有屏幕底部
    ctypes = None

MAGENTA = "#FF00FF"
SIZE = 200                   # 画布边长
GROUND_MARGIN = 6            # 距屏幕底边
WALK_SPEED = 3
GRAVITY = 3
HOP_VY = -14                 # 双击起跳速度
FOOT_INSET = 40              # 脚底支撑判定的左右内缩
PLATFORM_MIN_W = 180         # 窗口至少这么宽才配当平台
PLATFORM_MIN_TOP = 240       # 太靠上的窗口顶不站（会半截出屏）
PLAT_TOL = 8                 # 站立面吸附容差

FRAMES = ["idle_0", "idle_1", "grab_0", "grab_1", "fall_0", "land_0",
          "sleep_0", "sleep_1", "greet_0", "cheer_0", "cheer_1",
          "spin_0", "spin_1", "spin_2", "spin_3"]
for _d in ("l", "r"):
    FRAMES += [f"walk_{_d}_{i}" for i in range(4)]

LINES = [
    "token 又免费了，快薅！",
    "今天的格子，点亮了吗？",
    "Agent & RAG，学着呢。",
    "free tier 也要有梦想。",
    "README 已经是英文的了哦。",
    "三个仓库，都在双平台躺着。",
    "慢慢做，比较快。",
    "有 bug 去公众号看我调试。",
    "Action！开拍啦！",
    "我现在是 3D 手办了哦。",
    "你的窗口，都是我的路。",
]
GRAB_LINES = ["哇！", "放手！", "别提我！"]
LAND_LINES = ["着陆成功。", "一点不疼。", "再来。"]
CHEER_LINES = ["Action——！", "咔，一条过！"]
SLEEP_LINE = "Zzz……"


def enum_window_platforms(exclude=()):
    """可见窗口的顶边 → [(x0, surface_y, x1)]，用 DWM 可视边界（去掉隐形边框）。

    过滤：不可见/最小化/工具窗/幻影窗(UWP cloak)/无标题/太窄/太靠上。
    """
    if ctypes is None:
        return []
    u32 = ctypes.windll.user32
    dwm = ctypes.windll.dwmapi
    out = []

    def cb(hwnd, lparam):
        try:
            if hwnd in exclude:
                return True
            if not u32.IsWindowVisible(hwnd) or u32.IsIconic(hwnd):
                return True
            if u32.GetWindowLongW(hwnd, -20) & 0x80:        # WS_EX_TOOLWINDOW
                return True
            cloaked = wintypes.DWORD(0)
            if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked),
                                         ctypes.sizeof(cloaked)) == 0 and cloaked.value:
                return True                                  # DWMWA_CLOAKED
            rect = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect),
                                         ctypes.sizeof(rect)) != 0:   # EXTENDED_FRAME_BOUNDS
                if not u32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w < PLATFORM_MIN_W or h < 80:
                return True
            if u32.GetWindowTextLengthW(hwnd) == 0:
                return True
            if rect.top < PLATFORM_MIN_TOP:
                return True
            out.append((rect.left, rect.top, rect.right))
        except Exception:
            pass
        return True

    proc = _WNDENUMPROC(cb)
    u32.EnumWindows(proc, 0)
    return out


class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", MAGENTA)
        except tk.TclError:
            print("[warn] 环境不支持透明色")

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self.ground = self.sh - GROUND_MARGIN - SIZE

        self.canvas = tk.Canvas(self.root, width=SIZE, height=SIZE,
                                bg=MAGENTA, highlightthickness=0)
        self.canvas.pack()
        self.frames = {name: tk.PhotoImage(file=f"frames3d/{name}.gif")
                       for name in FRAMES}
        self.sprite = self.canvas.create_image(0, 0, image=self.frames["fall_0"],
                                               anchor="nw")

        # 自身窗口句柄（平台枚举时排除自己）
        self.hwnd = self.root.winfo_id()
        if ctypes is not None:
            self.hwnd = ctypes.windll.user32.GetParent(self.hwnd) or self.hwnd
        self.plats = []
        self._plat_cd = 0

        # 状态
        self.state = "FALL"          # 开场从天上掉下来，落地后打招呼
        self.x, self.y = random.randint(100, self.sw - SIZE - 100), 40
        self.vy = 0
        self.dir = random.choice((-1, 1))
        self.tick_n = 0
        self.state_left = 0
        self.first_land = True
        self.last_input = 0
        self.drag_off = None
        self.press_pos = None
        self.bubble = None
        self.bubble_job = None

        self.root.geometry(f"+{self.x}+{self.y}")
        self._bind()
        self.root.after(50, self._tick)

    # ---------- 平台 ----------
    def _all_platforms(self):
        return self.plats + [(0, self.ground + SIZE, self.sw)]

    def _support(self):
        """脚底下踩着的平台，没有则 None。"""
        span_l, span_r = self.x + FOOT_INSET, self.x + SIZE - FOOT_INSET
        sy = self.y + SIZE
        for (x0, py, x1) in self._all_platforms():
            if x0 <= span_r and x1 >= span_l and abs(py - sy) <= PLAT_TOL:
                return (x0, py, x1)
        return None

    # ---------- 输入 ----------
    def _bind(self):
        c = self.canvas
        c.bind("<Button-1>", self._press)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="说句话", command=lambda: self.say(random.choice(LINES)))
        menu.add_command(label="打个板 🎬", command=self._to_cheer)
        menu.add_command(label="转一圈 🔄", command=self._to_spin)
        menu.add_command(label="跑两步", command=self._to_walk)
        menu.add_command(label="睡一觉", command=self._to_sleep)
        menu.add_separator()
        menu.add_command(label="退出", command=self.root.destroy)
        c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _touch(self):
        self.last_input = self.tick_n

    def _press(self, e):
        self._touch()
        self.drag_off = (e.x, e.y)
        self.press_pos = (e.x_root, e.y_root)
        if self.state not in ("GRAB",):
            self._set_state("GRAB")
            if random.random() < 0.4:
                self.say(random.choice(GRAB_LINES), 900)

    def _double(self, e):
        self._touch()
        if self._support() is not None:               # 双击起跳
            self.vy = HOP_VY
            self._set_state("FALL")

    def _drag(self, e):
        self._touch()
        self.x = e.x_root - self.drag_off[0]
        self.y = e.y_root - self.drag_off[1]
        self.root.geometry(f"+{self.x}+{self.y}")

    def _release(self, e):
        moved = abs(e.x_root - self.press_pos[0]) + abs(e.y_root - self.press_pos[1])
        if moved < 6:                                   # 点击（非拖拽）
            if self.state == "SLEEP":
                self.say("……吵醒我了。", 1500)
                self._set_state("IDLE", random.randint(60, 200))
            elif self.state not in ("CHEER", "SPIN"):
                self.say(random.choice(LINES))
                if self.state == "GRAB":
                    self._to_fall()
        elif self.state == "GRAB":
            self._to_fall()                             # 松手 → 重力接管
        self.drag_off = None

    # ---------- 状态切换 ----------
    def _set_state(self, s, duration=0):
        self.state, self.state_left = s, duration

    def _to_walk(self):
        self._touch()
        self.dir = random.choice((-1, 1))
        self._set_state("WALK", random.randint(100, 260))

    def _to_fall(self):
        self.vy = 0
        self._set_state("FALL")

    def _to_sleep(self):
        self._set_state("SLEEP")
        self.say(SLEEP_LINE, 2000)

    def _to_cheer(self):
        self._touch()
        if self._support() is None:
            return
        self._set_state("CHEER", 26)
        self.say(random.choice(CHEER_LINES), 1800)

    def _to_spin(self):
        self._touch()
        if self._support() is None:
            return
        self._set_state("SPIN", 32)                   # 4 帧 × 2 圈
        self.say("转起来～", 1500)

    # ---------- 主循环 ----------
    def _tick(self):
        self.tick_n += 1
        if self.state != "GRAB":
            self.state_left -= 1

        # 平台清单每 0.5s 刷新一次
        self._plat_cd -= 1
        if self._plat_cd <= 0:
            self.plats = enum_window_platforms((self.hwnd,))
            self._plat_cd = 10

        # 站立类状态：吸附/跟随脚下的平台；平台消失 → 掉落
        if self.state not in ("FALL", "GRAB"):
            s = self._support()
            if s is None:
                self._to_fall()
            else:
                self.y = s[1] - SIZE

        if self.state == "IDLE":
            self._anim(["idle_0", "idle_1", "idle_0", "idle_1"], 14)
            if self.state_left <= 0:
                self._to_walk() if random.random() < 0.6 else \
                    self._set_state("IDLE", random.randint(60, 200))
            if self.tick_n - self.last_input > 1200:    # 60 秒无交互
                self._to_sleep()

        elif self.state == "WALK":
            s = self._support()
            if s is None:
                self._to_fall()
            else:
                d = "l" if self.dir < 0 else "r"
                self._anim([f"walk_{d}_0", f"walk_{d}_1", f"walk_{d}_2", f"walk_{d}_3"], 6)
                nx = self.x + self.dir * WALK_SPEED
                if nx + FOOT_INSET < s[0] or nx + SIZE - FOOT_INSET > s[2]:
                    if random.random() < 0.6:           # 到窗口边缘：多半掉头
                        self.dir *= -1
                        nx = self.x
                    # 否则径直走下去 → 下个 tick 失去支撑自然掉落
                if nx < -20 or nx > self.sw - SIZE + 20:
                    self.dir *= -1
                    nx = self.x
                self.x = nx
                if self.state_left <= 0:
                    self._set_state("IDLE", random.randint(60, 200))
                if random.random() < 0.004:
                    self.say(random.choice(LINES))

        elif self.state == "GRAB":
            self._anim(["grab_0", "grab_1"], 4)

        elif self.state == "FALL":
            prev_feet = self.y + SIZE
            self.vy += GRAVITY
            self.y += self.vy
            feet = self.y + SIZE
            span_l, span_r = self.x + FOOT_INSET, self.x + SIZE - FOOT_INSET
            hits = sorted(py for (x0, py, x1) in self._all_platforms()
                          if x0 <= span_r and x1 >= span_l and prev_feet <= py <= feet)
            if hits:                                    # 最先碰到的面
                self.y = hits[0] - SIZE
                self._set_state("LAND", 10)
            elif self.y >= self.ground:
                self.y = self.ground
                self._set_state("LAND", 10)
            else:
                self._show("fall_0")

        elif self.state == "LAND":
            self._show("land_0")
            if self.state_left <= 0:
                if self.first_land:
                    self.first_land = False
                    self._set_state("GREET", 30)
                    self.say("我上线啦！", 1800)
                else:
                    self._set_state("IDLE", random.randint(60, 200))
                    if random.random() < 0.5:
                        self.say(random.choice(LAND_LINES), 1200)

        elif self.state == "GREET":
            self._show("greet_0")
            if self.state_left <= 0:
                self._set_state("IDLE", random.randint(60, 200))

        elif self.state == "SLEEP":
            self._anim(["sleep_0", "sleep_1"], 40)
            if random.random() < 0.002:
                self.say(SLEEP_LINE, 1500)

        elif self.state == "CHEER":
            self._anim(["cheer_0", "cheer_1"], 7)
            if self.state_left <= 0:
                self._set_state("IDLE", random.randint(60, 200))

        elif self.state == "SPIN":
            i = (32 - max(self.state_left, 0)) // 8    # 每 8 tick 换一面
            self._show(["spin_0", "spin_1", "spin_2", "spin_3"][i % 4])
            if self.state_left <= 0:
                self._set_state("IDLE", random.randint(60, 200))

        self.root.geometry(f"+{self.x}+{int(self.y)}")
        self.root.after(50, self._tick)

    def _anim(self, names, speed):
        self._show(names[(self.tick_n // speed) % len(names)])

    def _show(self, name):
        self.canvas.itemconfig(self.sprite, image=self.frames[name])

    # ---------- 台词气泡 ----------
    def say(self, text, ms=2600):
        if self.bubble_job:
            self.root.after_cancel(self.bubble_job)
        if self.bubble:
            self.bubble.destroy()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.geometry(f"+{max(10, self.x - 40)}+{max(10, self.y - 56)}")
        tk.Label(b, text=text, font=("Microsoft YaHei UI", 10),
                 bg="#FFF9C4", fg="#333", padx=10, pady=6,
                 highlightthickness=1, highlightbackground="#E0C94B").pack()
        self.bubble = b
        self.bubble_job = self.root.after(ms, b.destroy)

    def run(self):
        self.last_input = self.tick_n
        self.root.mainloop()


if __name__ == "__main__":
    Pet().run()
