"""Short local display lease prevents showing both native and embedded pets."""
import json
import math
import os
import tempfile
import time
from pathlib import Path


def read_display_mode(events_directory, now_ms=None):
    """An absent, expired, malformed or implausibly long lease restores the desktop pet."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    try:
        with (Path(events_directory).parent / "display.json").open(encoding="utf-8") as stream:
            raw = stream.read(2049)
        if len(raw) > 2048:
            return "desktop"
        data = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        return "desktop"
    if not isinstance(data, dict) or data.get("version") != 1:
        return "desktop"
    until = data.get("lease_until")
    if (data.get("mode") == "embedded" and data.get("owner") == "dsh"
            and type(until) in (int, float) and math.isfinite(until)
            and now_ms < until <= now_ms + 90000):
        return "embedded"
    return "desktop"


def display_claimed(events_directory, now_ms=None):
    """True only when a live embedded client has claimed the lease (client_id set).

    桌宠端据此决定是否真的隐藏：请求租约（确认窗口内）还没有 client_id，
    说明没有任何 DSH 网页接手——不能藏。
    """
    if read_display_mode(events_directory, now_ms) != "embedded":
        return False
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    try:
        with (Path(events_directory).parent / "display.json").open(encoding="utf-8") as stream:
            data = json.loads(stream.read(2049))
    except (OSError, ValueError, UnicodeError):
        return False
    client = data.get("client_id") if isinstance(data, dict) else None
    return isinstance(client, str) and 0 < len(client) <= 128


def write_display_mode(events_directory, mode, now_ms=None, lease_ms=60000):
    """Request DSH takeover. 默认 30 秒；桌宠端请求时用短确认窗口（约 6 秒），
    只有网页客户端 claim 并心跳续租（写 client_id + 完整租期）后桌宠才隐藏。"""
    if mode not in ("desktop", "embedded"):
        raise ValueError("Unknown pet display mode")
    if not isinstance(lease_ms, int) or not 0 < lease_ms <= 90000:
        lease_ms = 60000
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    parent = Path(events_directory).parent
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=parent, prefix="display-", suffix=".tmp",
                                         encoding="utf-8", delete=False) as stream:
            temporary = stream.name
            json.dump({"version": 1, "mode": mode, "owner": "dsh",
                       "lease_until": int(now_ms + lease_ms) if mode == "embedded" else 0}, stream)
        os.replace(temporary, parent / "display.json")
        return True
    except OSError:
        return False
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
