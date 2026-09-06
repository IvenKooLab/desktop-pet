"""临时冒烟测试驱动：固定出生点，依次触发各状态并截图（不入库）。

末尾附带平台测试：落到窗口顶边 / 沿窗口边行走掉落。
"""
import random
import sys

random.seed(7)
sys.path.insert(0, ".")
import pet as m
from PIL import ImageGrab

p = m.Pet()
p.x, p.y = 400, 40
p.root.geometry(f"+{p.x}+{p.y}")

def shot(tag):
    img = ImageGrab.grab()
    img.crop((250, max(0, p.y - 140), 250 + 700, min(img.height, p.y + m.SIZE + 120))
             ).save(f"assets/cut/verify_{tag}.png")
    print("shot", tag, "pet@", p.x, int(p.y), "state", p.state)

def at(ms, fn):
    p.root.after(ms, fn)

at(2600, lambda: (shot("greet"), p._to_walk()))
at(4200, lambda: (shot("walk"), p._set_state("IDLE", 20)))
at(4500, lambda: p._to_spin())
at(5600, lambda: (shot("spin"), p._to_cheer()))
at(6800, lambda: (shot("cheer"), p._to_sleep()))
at(8000, lambda: shot("sleep"))

def plat_test():
    # 强制刷新平台，选一个够宽的窗口顶
    p.plats = m.enum_window_platforms((p.hwnd,))
    cands = [t for t in p.plats if t[2] - t[0] > 500 and t[1] < p.sh - 500]
    print("platforms:", len(p.plats), "testable:", len(cands))
    if not cands:
        print("no testable platform, skip")
        p.root.destroy()
        return
    x0, sy, x1 = max(cands, key=lambda t: t[2] - t[0])
    print("target plat", x0, sy, x1)

    # (a) 从窗口上方 300px 落下，应精确踩在窗口顶
    p.x = (x0 + x1) // 2 - m.SIZE // 2
    p.y = sy - m.SIZE - 300
    p._to_fall()

    def chk_land():
        ok = abs(p.y + m.SIZE - sy) <= m.PLAT_TOL + 2
        print("land-on-window:", "OK" if ok else "FAIL",
              "y=", int(p.y), "surf=", sy, "state=", p.state)
        shot("onwin")
        # (b) 站到左边缘附近向左走，几步内应掉下去
        p.x = x0 + 100
        p.y = sy - m.SIZE
        p.dir = -1
        m.random.random = lambda: 0.99     # 固定随机：边缘永不掉头，必走落
        p._set_state("WALK", 600)

        def poll(tries=[0]):
            tries[0] += 1
            if p.state == "FALL":
                def after_land():
                    s2 = p._support()
                    print("walked-off-edge:", "OK" if s2 else "STILL-FALLING",
                          "support=", s2, "y=", int(p.y))
                    shot("offedge")
                    p.root.destroy()
                p.root.after(1500, after_land)
            elif tries[0] > 100:                      # 10s 兜底
                print("walk-off-edge TIMEOUT, state=", p.state, "x=", p.x)
                shot("offedge")
                p.root.destroy()
            else:
                p.root.after(100, poll)
        poll()

    p.root.after(1800, chk_land)

at(8300, plat_test)
p.root.mainloop()
print("done")
