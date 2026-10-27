"""control_api · 本机文件控制接口（~/.comi-pet/api，与桥接/对话同风格，零网络）。

让其他插件、脚本或快捷指令驱动桌宠：说话、点播动作、入睡/唤醒、读状态。
协议与 host_chat 一致（原子 JSON、读后即焚、TTL 清理）：

    请求 <dir>/request-<id>.json
        {"version": 1, "id": "...", "action": "say|play|sleep|wake|state",
         "text": "…"(say), "state": "CHEER"(play)}
    回复 <dir>/reply-<id>.json
        {"version": 1, "id": "...", "ok": true, …} / {"ok": false, "reason": "…"}
    快照 <dir>/../state.json    桌宠每秒原子写出的实况（GET state 的等价物）

边界：
- 文本只作数据展示（清洗控制字符、截断），绝不当作指令执行；
- play 的动作名必须在请求解析时对照调用侧给出的白名单（可用素材集）；
- 仅本机用户可写该目录；请求 15 分钟无人消费即清理。
"""
import json
import os
import re
import time
from pathlib import Path
import comi_home

MAX_TEXT = 2000
REPLY_TTL = 300.0
REQUEST_TTL = 900.0
ACTIONS = ("say", "play", "sleep", "wake", "state")
# play 除素材剪辑外允许的内置动作（两端各自实现）
BUILTIN_PLAY = ("IDLE", "WALK", "RUN", "SLEEP", "BOUNCE", "HAPPY", "SHY", "SPIN")


def api_dir():
    return Path(comi_home.env("COMI_API_DIR") or comi_home.subdir("api"))


def state_path():
    return api_dir().parent / "state.json"


def clean_text(text, limit=MAX_TEXT):
    """与 host_chat 相同的清洗：去控制字符、截断。"""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(text)).strip()
    return cleaned[:limit]


def parse_request(obj, allowed_states=()):
    """校验请求对象，返回规范化 dict；非法返回 None。

    allowed_states：调用侧当前实际可用的动作剪辑名（play 白名单）。
    """
    if not isinstance(obj, dict) or obj.get("version") != 1:
        return None
    req_id = obj.get("id")
    action = obj.get("action")
    if not (isinstance(req_id, str) and 0 < len(req_id) <= 64):
        return None
    if action not in ACTIONS:
        return None
    spec = {"id": req_id, "action": action, "ts": time.time()}
    if action == "say":
        text = clean_text(obj.get("text") or "")
        if not text:
            return None
        spec["text"] = text
    elif action == "play":
        state = obj.get("state")
        if not (isinstance(state, str) and state
                and (state in BUILTIN_PLAY or state in allowed_states)):
            return None
        spec["state"] = state
    return spec


def write_request(directory, action, text=None, state=None, now=None,
                  request_id=None):
    """写入一条控制请求，返回请求 id。"""
    directory = Path(directory)
    now = time.time() if now is None else now
    req_id = request_id or f"cli-{os.getpid()}-{int(now*1000):x}"
    payload = {"version": 1, "id": req_id, "action": action,
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + "Z"}
    if action == "say":
        payload["text"] = clean_text(text or "")
    elif action == "play":
        payload["state"] = state
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f"request-{req_id}.tmp-{os.getpid()}"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, directory / f"request-{req_id}.json")
    return req_id


def read_reply(directory, request_id, consume=True):
    """读取回复（默认读后即删）；不存在/损坏/过期返回 None。"""
    path = Path(directory) / f"reply-{request_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if consume:
        try:
            path.unlink()
        except OSError:
            pass
    if not (isinstance(raw, dict) and raw.get("id") == request_id):
        return None
    return raw


def write_reply(directory, request_id, payload):
    directory = Path(directory)
    body = dict(payload)
    body.update({"version": 1, "id": request_id})
    tmp = directory / f"reply-{request_id}.tmp-{os.getpid()}"
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, directory / f"reply-{request_id}.json")


def poll_requests(directory, limit=32):
    """取出待处理请求（按文件名排序），文件即请求本身（处理后由调用侧删除）。"""
    directory = Path(directory)
    try:
        names = sorted(n for n in os.listdir(directory)
                       if n.startswith("request-") and n.endswith(".json"))
    except OSError:
        return []
    out = []
    for name in names[:limit]:
        path = directory / name
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            obj = None
        out.append((path, obj))
    return out


def write_state(path, snapshot):
    """原子写状态快照；失败静默。"""
    path = Path(path)
    body = dict(snapshot)
    body["version"] = 1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def read_state(path):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) and raw.get("version") == 1 else None
    except (OSError, UnicodeError, ValueError):
        return None


def cleanup(directory, now=None, request_ttl=REQUEST_TTL, reply_ttl=REPLY_TTL):
    """清理过期请求与陈旧回复；返回删除数。"""
    directory = Path(directory)
    now = time.time() if now is None else now
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        path = directory / name
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        stale = (name.startswith("request-") and age > request_ttl) \
            or (name.startswith("reply-") and age > reply_ttl) \
            or (".tmp-" in name and age > 60)     # 残留临时文件尽快清
        if not stale:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
