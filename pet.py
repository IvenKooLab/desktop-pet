"""Iven Pet · GitHub 头像桌面宠（运行时零第三方依赖，纯 tkinter）。

用法：
    python pet.py            # 出现在屏幕右下角
功能：
    悬浮呼吸浮动 / 左键拖拽 / 单击冒台词气泡 / 双击跳跃 / 右键菜单
"""
import math
import random
import tkinter as tk

MAGENTA = "#FF00FF"          # 透明色：帧图的衬底
FRAME = "frames/pet.gif"

LINES = [
    "token 又免费了，快薅！",
    "今天的格子，点亮了吗？",
    "Agent & RAG，学着呢。",
    "free tier 也要有梦想。",
    "拖我可以，摔了不赔。",
    "README 已经是英文的了哦。",
    "别卷了，跑两步?",
    "我的场记板呢……",
    "三个仓库，都在双平台躺着。",
    "慢慢做，比较快。",
    "点我是不会掉落奖励的（暂时）",
    "有事去公众号，我在这看家。",
]


class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", MAGENTA)
        except tk.TclError:
            print("[warn] 当前环境不支持透明色，桌宠会带品红底")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.base_x, self.base_y = sw - 220, sh - 280
        self.root.geometry(f"+{self.base_x}+{self.base_y}")

        self.canvas = tk.Canvas(self.root, bg=MAGENTA, highlightthickness=0)
        self.canvas.pack()
        self.img = tk.PhotoImage(file=FRAME)
        self.canvas.create_image(4, 4, image=self.img, anchor="nw")

        # 状态
        self.t = 0.0
        self.drag_off = None
        self.press_pos = None
        self.bubble = None
        self.bubble_job = None

        self._bind()
        self._float()

    # ---- 绑定 ----
    def _bind(self):
        c = self.canvas
        c.bind("<Button-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Double-Button-1>", lambda e: self.jump())
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="说句话", command=lambda: self.say(random.choice(LINES)))
        menu.add_command(label="跳一下", command=self.jump)
        self.pinned = True
        menu.add_command(label="取消置顶", command=self._toggle_pin)
        menu.add_separator()
        menu.add_command(label="退出", command=self.root.destroy)
        c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _toggle_pin(self):
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)

    # ---- 呼吸浮动 ----
    def _float(self):
        self.t += 0.08
        if self.drag_off is None:
            dy = int(math.sin(self.t) * 5)
            self.root.geometry(f"+{self.base_x}+{self.base_y + dy}")
        self.root.after(50, self._float)

    # ---- 拖拽 / 点击 ----
    def _press(self, e):
        self.drag_off = (e.x, e.y)
        self.press_pos = (e.x_root, e.y_root)

    def _drag(self, e):
        dx, dy = self.drag_off
        self.base_x = e.x_root - dx
        self.base_y = e.y_root - dy
        self.root.geometry(f"+{self.base_x}+{self.base_y}")

    def _release(self, e):
        moved = abs(e.x_root - self.press_pos[0]) + abs(e.y_root - self.press_pos[1])
        self.drag_off = None
        if moved < 6:  # 视为点击（非拖拽）
            self.say(random.choice(LINES))

    # ---- 台词气泡 ----
    def say(self, text: str, ms: int = 2600):
        if self.bubble_job:
            self.root.after_cancel(self.bubble_job)
        if self.bubble:
            self.bubble.destroy()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        bx = max(10, self.base_x - 60)
        by = max(10, self.base_y - 70)
        b.geometry(f"+{bx}+{by}")
        tk.Label(b, text=text, font=("Microsoft YaHei UI", 10),
                 bg="#FFF9C4", fg="#333", padx=10, pady=6,
                 highlightthickness=1, highlightbackground="#E0C94B").pack()
        self.bubble = b
        self.bubble_job = self.root.after(ms, b.destroy)

    # ---- 跳跃动画 ----
    def jump(self):
        frames = [0, -30, -55, -30, 0, 8, 0]
        for i, dy in enumerate(frames):
            self.root.after(i * 55,
                            lambda dy=dy: self.root.geometry(
                                f"+{self.base_x}+{self.base_y + dy}"))
        self.say("jump!", 800)

    def run(self):
        self.root.after(1500, lambda: self.say("我上线啦！拖我，点我。"))
        self.root.mainloop()


if __name__ == "__main__":
    Pet().run()
