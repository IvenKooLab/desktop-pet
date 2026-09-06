"""素材预处理 v2：从 460×460 头像生成桌宠全套动作帧（Shimeji 式）。

用法：
    python tools/make_frames.py assets/avatar_raw.png

产出（frames/ 下，160×160 画布，品红 #FF00FF 衬底供运行时透明）：
    idle_0/1   待机呼吸（原样 / 轻微压扁）
    walk_0..3  走路摇摆（rotate ±8° 交替 + 上下颠簸）
    grab_0/1   被抓挣扎（放大 + 反向倾斜交替）
    fall_0     下落（纵向拉长）
    land_0     落地 / 睡觉（横向压扁 squash）
构建期依赖 Pillow；运行时（pet.py）零第三方依赖。
"""
import sys
from pathlib import Path

from PIL import Image

SIZE = 160          # 画布尺寸
ACTOR = 118         # 角色基准尺寸


def remove_bg(img: Image.Image, tol: int = 32) -> Image.Image:
    """贴纸图专用抠背景：从图像边缘 BFS 连通扩散，只抠与边缘连通的背景色。

    白描边是闭合轮廓，天然挡住扩散——角色内部的浅色不会误伤。
    """
    import numpy as np
    from collections import deque

    rgb = np.asarray(img.convert("RGB")).astype(int)
    h, w, _ = rgb.shape
    bg = rgb[2, 2].copy()
    diff = np.abs(rgb - bg).sum(axis=2)
    candidate = diff < tol * 3

    visited = np.zeros((h, w), dtype=bool)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if candidate[y, x] and not visited[y, x]:
                visited[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if candidate[y, x] and not visited[y, x]:
                visited[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                dq.append((ny, nx))

    alpha = np.where(visited, 0, 255).astype("uint8")
    # 1px 腐蚀：吃掉贴纸白边外侧的抗锯齿蓝晕
    eroded = alpha.copy()
    eroded[1:, :] = np.minimum(eroded[1:, :], alpha[:-1, :])
    eroded[:-1, :] = np.minimum(eroded[:-1, :], alpha[1:, :])
    eroded[:, 1:] = np.minimum(eroded[:, 1:], alpha[:, :-1])
    eroded[:, :-1] = np.minimum(eroded[:, :-1], alpha[:, 1:])

    out = np.dstack([np.asarray(img.convert("RGB")), eroded])
    return Image.fromarray(out, "RGBA")


def variant(base: Image.Image, sw: float = 1.0, sh: float = 1.0,
            rot: float = 0.0, dy: int = 0) -> Image.Image:
    """角色变换后贴到品红画布（透明区域保持品红，供 transparentcolor 抠像）。"""
    w, h = int(ACTOR * sw), int(ACTOR * sh)
    img = base.resize((w, h), Image.LANCZOS)
    if rot:
        img = img.rotate(rot, expand=True, resample=Image.BICUBIC)
    canvas = Image.new("RGB", (SIZE, SIZE), (255, 0, 255))
    mask = img.split()[3]
    canvas.paste(img.convert("RGB"),
                 ((SIZE - img.width) // 2, (SIZE - img.height) // 2 + dy),
                 mask)
    return canvas


def main(src: str) -> None:
    out_dir = Path(__file__).resolve().parents[1] / "frames"
    out_dir.mkdir(exist_ok=True)

    img = Image.open(src).convert("RGB")
    cut = remove_bg(img)
    cut = cut.crop(cut.getbbox()).resize((ACTOR, ACTOR), Image.LANCZOS)

    frames = {
        "idle_0": variant(cut),
        "idle_1": variant(cut, sw=0.96, sh=1.04),
        "walk_0": variant(cut, rot=8, dy=2),
        "walk_1": variant(cut),
        "walk_2": variant(cut, rot=-8, dy=0),
        "walk_3": variant(cut, dy=3),
        "grab_0": variant(cut, sw=1.06, sh=1.06, rot=-10),
        "grab_1": variant(cut, sw=1.06, sh=1.06, rot=10),
        "fall_0": variant(cut, sw=0.92, sh=1.10),
        "land_0": variant(cut, sw=1.12, sh=0.86, dy=6),
    }
    for name, im in frames.items():
        im.save(out_dir / f"{name}.gif", format="GIF")
    print(f"{len(frames)} frames -> {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assets/avatar_raw.png")
