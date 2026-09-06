"""临时冒烟测试驱动：固定出生点，依次触发各状态并截图（不入库）。"""
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
at(8000, lambda: (shot("sleep"), p.root.destroy()))

p.root.mainloop()
print("done")
