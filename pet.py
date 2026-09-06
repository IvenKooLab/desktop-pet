"""Iven Pet v2 · GitHub 头像桌面宠（行为状态机版，运行时零第三方依赖）。

状态机：IDLE(待机呼吸) → WALK(屏幕底部走动) → GRAB(被抓住挣扎) →
        FALL(重力下落+落地压扁) → SLEEP(长时间不动睡着)

    python pet.py
"""
import random
import tkinter as tk

MAGENTA = "#FF00FF"
GROUND_MARGIN = 8            # 距屏幕底边
WALK_SPEED = 3
GRAVITY = 3
IDLE_FRAMES = ["idle_0", "idle_1", "idle_0", "idle_1"]
WALK_FRAMES = ["walk_0", "walk_1", "walk_2", "walk_3"]
GRAB_FRAMES = ["grab_0", "grab_1"]

LINES = [
    "token 又免费了，快薅！",
    "今天的格子，点亮了吗？",
    "Agent & RAG，学着呢。",
    "free tier 也要有梦想。",
    "README 已经是英文的了哦。",
    "我的场记板呢……",
    "三个仓库，都在双平台躺着。",
    "慢慢做，比较快。",
    "有 bug 去公众号看我调试。",
]
GRAB_LINES = ["哇！", "放手！", "别提我！"]
LAND_LINES = ["着陆成功。", "一点不疼。", "再来。"]
SLEEP_LINE = "Zzz……"


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
        self.ground = self.root.winfo_screenheight() - GROUND_MARGIN - 160

        self.canvas = tk.Canvas(self.root, width=160, height=160,
                                bg=MAGENTA, highlightthickness=0)
        self.canvas.pack()
        self.frames = {name: tk.PhotoImage(file=f"frames/{name}.gif")
                       for name in IDLE_FRAMES + WALK_FRAMES + GRAB_FRAMES
                       + ["fall_0", "land_0"]}
        self.sprite = self.canvas.create_image(0, 0, image=self.frames["idle_0"],
                                               anchor="nw")

        # 状态
        self.state = "FALL"          # 开场从天上掉下来
        self.x, self.y = random.randint(100, self.sw - 260), 40
        self.vy = 0
        self.dir = random.choice((-1, 1))
        self.tick_n = 0
        self.frame_i = 0
        self.state_left = 0
        self.last_input = 0
        self.drag_off = None
        self.press_pos = None
        self.bubble = None
        self.bubble_job = None

        self.root.geometry(f"+{self.x}+{self.y}")
        self._bind()
        self.root.after(50, self._tick)

    # ---------- 输入 ----------
    def _bind(self):
        c = self.canvas
        c.bind("<Button-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="说句话", command=lambda: self.say(random.choice(LINES)))
        menu.add_command(label="睡一觉", command=lambda: self._to_sleep())
        menu.add_command(label="跑两步", command=lambda: self._to_walk())
        menu.add_separator()
        menu.add_command(label="退出", command=self.root.destroy)
        c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _press(self, e):
        self.drag_off = (e.x, e.y)
        self.press_pos = (e.x_root, e.y_root)
        self._set_state("GRAB")
        if random.random() < 0.4:
            self.say(random.choice(GRAB_LINES), 900)

    def _drag(self, e):
        self.x = e.x_root - self.drag_off[0]
        self.y = e.y_root - self.drag_off[1]
        self.root.geometry(f"+{self.x}+{self.y}")

    def _release(self, e):
        moved = abs(e.x_root - self.press_pos[0]) + abs(e.y_root - self.press_pos[1])
        if moved < 6:                                   # 点击（非拖拽）
            if self.state == "SLEEP":
                self.say("……吵醒我了。", 1500)
            else:
                self.say(random.choice(LINES))
            self._to_fall() if self.y < self.ground else self._set_state("IDLE")
        elif self.y < self.ground:
            self._to_fall()                             # 松手 → 重力接管
        self.drag_off = None

    # ---------- 状态切换 ----------
    def _set_state(self, s, duration=0):
        self.state, self.state_left = s, duration
        self.frame_i = 0

    def _to_walk(self):
        self.dir = random.choice((-1, 1))
        self._set_state("WALK", random.randint(100, 260))

    def _to_fall(self):
        self.vy = 0
        self._set_state("FALL")

    def _to_sleep(self):
        self._set_state("SLEEP")
        self.say(SLEEP_LINE, 2000)

    # ---------- 主循环 ----------
    def _tick(self):
        self.tick_n += 1
        if self.state != "GRAB":
            self.state_left -= 1

        if self.state == "IDLE":
            self._anim(IDLE_FRAMES, 14)
            if self.state_left <= 0:
                self._to_walk() if random.random() < 0.6 else \
                    self._set_state("IDLE", random.randint(60, 200))
            if self.tick_n - self.last_input > 1200:    # 60 秒无交互
                self._to_sleep()

        elif self.state == "WALK":
            self._anim(WALK_FRAMES, 6)
            self.x += self.dir * WALK_SPEED
            if self.x < 0 or self.x > self.sw - 180:
                self.dir *= -1
            if self.state_left <= 0:
                self._set_state("IDLE", random.randint(60, 200))
            if random.random() < 0.004:
                self.say(random.choice(LINES))

        elif self.state == "GRAB":
            self._anim(GRAB_FRAMES, 4)

        elif self.state == "FALL":
            self.vy += GRAVITY
            self.y = min(self.y + self.vy, self.ground)
            self._show("fall_0")
            if self.y >= self.ground:
                self._set_state("IDLE", random.randint(60, 200))
                self._anim(["land_0"], 8)
                if random.random() < 0.5:
                    self.say(random.choice(LAND_LINES), 1200)

        elif self.state == "SLEEP":
            self._anim(["land_0"], 40)
            if random.random() < 0.002:
                self.say(SLEEP_LINE, 1500)

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
        b.geometry(f"+{max(10, self.x - 40)}+{max(10, self.y - 60)}")
        tk.Label(b, text=text, font=("Microsoft YaHei UI", 10),
                 bg="#FFF9C4", fg="#333", padx=10, pady=6,
                 highlightthickness=1, highlightbackground="#E0C94B").pack()
        self.bubble = b
        self.bubble_job = self.root.after(ms, b.destroy)

    def run(self):
        self.last_input = self.tick_n
        self.say("我上线啦！", 1800)
        self.root.mainloop()


if __name__ == "__main__":
    Pet().run()
