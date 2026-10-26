"""pet_config · 桌宠本地配置（~/.iven-pet/config.json，Tk 与 Swift 端共用同一文件）。

字段（version 1）：
    notifications     "auto" | "always" | "off"   系统通知（auto=桌宠隐藏/内嵌时才弹）
    update_check      "auto" | "off"              启动时检查 GitHub 新版本（默认 auto）
    remember_position bool                        重启后回到上次位置
    position          {"x": int, "y": int, "cs": "topleft"|"bottomleft"}
                      cs 标记坐标系：Tk 为屏幕左上原点，Swift/Cocoa 为左下原点；
                      只恢复与自身坐标系一致的记录，跨平台互不误用。

原子写、损坏回落默认、绝不抛异常（返回 bool/默认值），与 language_preferences
同级的最小本地偏好；不含凭据，不含代理内容。
"""
import json
import os
from pathlib import Path

VERSION = 1
NOTIFICATION_MODES = ("auto", "always", "off")
UPDATE_CHECK_MODES = ("auto", "off")
COORD_SYSTEMS = ("topleft", "bottomleft")

DEFAULTS = {
    "version": VERSION,
    "notifications": "auto",
    "update_check": "auto",
    "remember_position": True,
    "position": None,
}


def config_path():
    return Path(os.environ.get("IVEN_CONFIG_DIR")
                or Path.home() / ".iven-pet") / "config.json"


def _normalize(raw):
    cfg = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return cfg
    if raw.get("notifications") in NOTIFICATION_MODES:
        cfg["notifications"] = raw["notifications"]
    if raw.get("update_check") in UPDATE_CHECK_MODES:
        cfg["update_check"] = raw["update_check"]
    if isinstance(raw.get("remember_position"), bool):
        cfg["remember_position"] = raw["remember_position"]
    pos = raw.get("position")
    if (isinstance(pos, dict) and isinstance(pos.get("x"), int)
            and isinstance(pos.get("y"), int) and pos.get("cs") in COORD_SYSTEMS):
        cfg["position"] = {"x": pos["x"], "y": pos["y"], "cs": pos["cs"]}
    return cfg


def load(path=None):
    path = Path(path) if path is not None else config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raw = None
    return _normalize(raw)


def save(cfg, path=None):
    """原子写回；失败不抛异常，返回 False。只写入已知字段。"""
    path = Path(path) if path is not None else config_path()
    clean = _normalize(cfg)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def valid_position(pos, screen_w, screen_h, size, cs, margin=8):
    """把记忆位置夹回屏幕内；非法/越界过多返回 None。

    完全离屏（例如换了显示器布局）也返回 None，让调用侧走默认出生点。
    """
    if not (isinstance(pos, dict) and pos.get("cs") == cs):
        return None
    try:
        x, y = int(pos["x"]), int(pos["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if x < -size or y < -size or x > screen_w or y > screen_h:
        return None                       # 位置完全不在任何合理屏幕范围内
    x = max(-size // 2, min(x, screen_w - size // 2))
    y = max(margin, min(y, screen_h - size // 2))
    return {"x": x, "y": y, "cs": cs}
