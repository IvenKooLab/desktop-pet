"""throw_physics · 甩抛物理（纯函数，Tk 端实现；Swift 端在 IvenPet.swift 镜像同一语义）。

坐标系：屏幕坐标 y 向下（Tk 约定）。Swift 为 Cocoa y 向上，调用侧自行翻转换算，
常量（重力/弹性/摩擦/落地阈值）保持一致换算，两端手感相同。

- estimate_velocity：拖拽采样 → 松手初速（px/s，窗口 120ms，限幅 MAX_SPEED）。
- step：推进一个时间步（dt 秒），处理左右/顶部边缘反弹、平台/地面落点，
  返回 "fly"（继续飞）/"bounce"（触地弹起）/"land"（落定）。

语义要点：
- 抛物线飞行；触地时垂直或水平速度仍超过 LAND_SPEED 才弹起（vy 反转
  × RESTITUTION，vx 衰减 × FRICTION），否则落定——温柔放下原地停住，
  甩出去才弹跳，能量逐次衰减最终停稳。
- 调用侧自行限制弹跳次数上限（MAX_BOUNCES），超出强制落定，防数值飘移。
"""
import math

WINDOW = 0.12          # 速度估计采样窗口（秒）
MIN_SPAN = 0.02        # 采样时间跨度下限，低于此视为无速度（防单击抖动）
MAX_SPEED = 2600.0     # 出手速度限幅（px/s）
THROW_MIN = 280.0      # 低于此速度不算甩出，走普通下落（px/s）
G = 1200.0             # 重力加速度（px/s²）
RESTITUTION = 0.55     # 触地反弹系数
FRICTION = 0.72        # 触地水平衰减
LAND_SPEED = 260.0     # 触地速度（垂直或水平）低于此值直接落定（px/s）
MAX_BOUNCES = 4        # 建议弹跳上限（调用侧执行）


def estimate_velocity(samples, now, window=WINDOW, min_span=MIN_SPAN,
                      max_speed=MAX_SPEED):
    """由拖拽采样估算松手初速。

    samples: [(t, x, y), ...]（monotonic 秒 + 指针坐标）。取窗口内首尾差分；
    样本不足、跨度太小或含非法值返回 None。返回 (vx, vy)，限幅 max_speed。
    """
    usable = [s for s in samples if len(s) == 3
              and all(isinstance(v, (int, float)) and math.isfinite(v)
                      for v in s)]
    if len(usable) < 2:
        return None
    usable.sort(key=lambda s: s[0])
    usable = [s for s in usable if now - s[0] <= window]
    if len(usable) < 2:
        return None
    first, last = usable[0], usable[-1]
    dt = last[0] - first[0]
    if dt < min_span:
        return None
    vx = (last[1] - first[1]) / dt
    vy = (last[2] - first[2]) / dt
    speed = math.hypot(vx, vy)
    if speed < 1e-6:
        return None
    if speed > max_speed:
        scale = max_speed / speed
        vx, vy = vx * scale, vy * scale
    return (vx, vy)


def step(x, y, vx, vy, dt, min_x, max_x, min_y, ground_y, size,
         platforms=(), g=G, restitution=RESTITUTION, friction=FRICTION,
         land_speed=LAND_SPEED):
    """推进一投掷步。ground_y 为可行走地面线（脚底 y），platforms 为 [(x0, py, x1)]。

    返回 (x, y, vx, vy, event)；event ∈ {"fly", "bounce", "land"}。
    非法输入（NaN/非正 dt）原样返回 "fly"，由调用侧兜底。
    """
    if not (dt > 0) or not all(math.isfinite(v) for v in (x, y, vx, vy)):
        return (x, y, vx, vy, "fly")
    prev_feet = y + size
    vy = vy + g * dt
    x = x + vx * dt
    y = y + vy * dt
    event = "fly"

    # 左右屏幕边缘：水平反弹
    if x < min_x:
        x, vx = min_x, -vx * restitution
    elif x > max_x:
        x, vx = max_x, -vx * restitution
    # 顶部边缘：垂直反弹（vy 向上为负）
    if y < min_y:
        y, vy = min_y, -vy * restitution

    # 落点：平台优先（更高者先碰到），其次地面
    feet = y + size
    span_l, span_r = x, x + size
    hits = sorted(py for (x0, py, x1) in platforms
                  if x0 <= span_r and x1 >= span_l and prev_feet <= py <= feet)
    surface = hits[0] if hits else (ground_y if feet >= ground_y else None)
    if surface is not None:
        if abs(vy) > land_speed or abs(vx) > land_speed:
            # 带能量触地：弹起（垂直反转 ×restitution，水平衰减 ×friction），
            # 反复弹跳能量递减，最终落入落定分支
            y = surface - size
            vy = -vy * restitution
            vx = vx * friction
            event = "bounce"
        else:
            # 慢速触地：温柔放下，原地停稳
            y = surface - size
            vx = vy = 0.0
            event = "land"
    return (x, y, vx, vy, event)
