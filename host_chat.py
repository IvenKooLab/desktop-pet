"""host_chat · "和 Iven 说话"：本地对话请求/回复文件协议（桌宠消费端）。

与 DSH 适配器（adapters/dsh/iven-bridge/chat-host.js）对齐的本机原子文件协议：

    请求 <dir>/request-<id>.json   {"version": 1, "id": "...", "text": "..."}
    回复 <dir>/reply-<id>.json     {"version": 1, "id": "...", "ok": true,
                                    "text": "...", "mood": "happy"| null,
                                    或 {"ok": false, "reason": "...", "message": ...}}

目录默认 ~/.iven-pet/chat（IVEN_CHAT_DIR 可覆盖）。适配器不在线时请求只会
安静地过期（15 分钟后由适配器/桌宠清理），桌宠按超时如实提示，绝不伪造回复。
回复文本与宿主事件一样只作数据展示：清洗控制字符、截断，绝不当作指令执行。
"""
import json
import os
import re
import time
from pathlib import Path

MAX_TEXT = 2000          # 与适配器一致的单条上限
REPLY_TTL = 300.0        # 回复停留 5 分钟，过期清理
REQUEST_TTL = 900.0      # 无人接手的请求 15 分钟后清理


def chat_dir():
    return Path(os.environ.get("IVEN_CHAT_DIR")
                or Path.home() / ".iven-pet" / "chat")


def _atomic_write(path, payload):
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def write_request(directory, text, now=None):
    """写入一条对话请求，返回请求 id。文本在桌宠端先做同样的清洗截断。"""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text).strip()
    if not cleaned:
        raise ValueError("消息为空")
    cleaned = cleaned[:MAX_TEXT]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    req_id = f"pet-{os.getpid()}-{os.urandom(4).hex()}"
    _atomic_write(directory / f"request-{req_id}.json",
                  {"version": 1, "id": req_id, "text": cleaned,
                   "ts": int((now or time.time()) * 1000)})
    return req_id


def read_reply(directory, req_id, clock=None):
    """取回并消费指定请求的回复；不存在返回 None。坏文件/串号一律丢弃。"""
    if not req_id:
        return None
    path = Path(directory) / f"reply-{req_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        path.unlink()
    except OSError:
        pass
    if (not isinstance(raw, dict) or raw.get("version") != 1
            or raw.get("id") != req_id):
        return None
    if raw.get("ok") is True:
        text = raw.get("text")
        raw["text"] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ",
                             text if isinstance(text, str) else "").strip()[:400]
        mood = raw.get("mood")
        if mood not in ("happy", "shy", "cheer", "greet", "relieved"):
            raw["mood"] = None
    return raw


def cleanup(directory, now=None):
    """清理过期的请求与回复（桌宠侧兜底；适配器侧也会清）。"""
    now = time.time() if now is None else now
    try:
        names = list(Path(directory).iterdir())
    except OSError:
        return
    for path in names:
        try:
            if path.name.startswith("request-") and path.suffix == ".json" \
                    and now - path.stat().st_mtime > REQUEST_TTL:
                path.unlink()
            elif path.name.startswith("reply-") and path.suffix == ".json" \
                    and now - path.stat().st_mtime > REPLY_TTL:
                path.unlink()
        except OSError:
            pass
