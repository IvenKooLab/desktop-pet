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
            and now_ms < until <= now_ms + 35000):
        return "embedded"
    return "desktop"


def write_display_mode(events_directory, mode, now_ms=None):
    """Request DSH takeover for 30 seconds; only a live embedded client may renew it."""
    if mode not in ("desktop", "embedded"):
        raise ValueError("Unknown pet display mode")
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    parent = Path(events_directory).parent
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=parent, prefix="display-", suffix=".tmp",
                                         encoding="utf-8", delete=False) as stream:
            temporary = stream.name
            json.dump({"version": 1, "mode": mode, "owner": "dsh",
                       "lease_until": int(now_ms + 30000) if mode == "embedded" else 0}, stream)
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
