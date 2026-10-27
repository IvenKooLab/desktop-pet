#!/usr/bin/env python3
"""OpenCode Server → Comi 桌宠桥接适配器（HTTP SSE 监听，纯标准库）。

连接【用户指定】的 OpenCode 服务（默认 http://127.0.0.1:4096，可用
--base 或 OPENCODE_BASE_URL 覆盖；token 用 OPENCODE_TOKEN）订阅
`GET /event`，把状态事件归约为统一事件写入本地收件箱。监测转发所有会话
（桌宠按 session 分组）；第二阶段发送任务时才需要用户显式选择 session，
绝不固定使用列表第一条。

映射（字段按目标版本 /doc OpenAPI 核验，此处宽容提取）：
    session.status(busy/idle) → turn.started / turn.ended
    session.idle / session.error → turn.ended / turn.failed
    permission.asked → permission.required（replied 不映射，等状态流）
    tool.execute.before / after → tool.started / tool.finished（带调用 ID）
断线退避重连；重连后按事件 id/组合键去重，不重复提醒。
用法：python3 adapters/opencode/comi_opencode.py [--base URL] [--max-events N]
"""
import json
import os
import shlex
import signal
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from host_bridge import write_event, default_dir  # noqa: E402

BACKOFF = (1, 2, 5, 10, 15)


def _sid(data):
    for key in ("sessionID", "sessionId", "session_id"):
        if data.get(key):
            return str(data[key])[:64]
    return "unknown"


def map_event(data):
    """OpenCode 事件 → (kind, fields)；不认识或不需要的返回 None。"""
    etype = data.get("type") or data.get("event") or ""
    sid = _sid(data)
    call_id = None
    for key in ("toolCallID", "toolCallId", "callID", "callId"):
        if data.get(key):
            call_id = str(data[key])[:64]
            break
    tool = data.get("tool") or data.get("toolName")
    if etype == "session.status":
        status = str(data.get("status", "")).lower()
        if status in ("busy", "running", "active"):
            return "turn.started", {"session_id": sid}
        if status in ("idle", "complete"):
            return "turn.ended", {"session_id": sid}
        return None
    if etype == "session.idle":
        return "turn.ended", {"session_id": sid}
    if etype == "session.error":
        return "turn.failed", {"session_id": sid}
    if etype == "permission.asked":
        return "permission.required", {"session_id": sid}
    if etype == "tool.execute.before":
        return "tool.started", {"session_id": sid, "tool_name": tool,
                                "tool_call_id": call_id}
    if etype == "tool.execute.after":
        return "tool.finished", {"session_id": sid, "tool_name": tool,
                                 "tool_call_id": call_id}
    return None     # permission.replied 等不映射：等后续状态流


def stream_once(base, token, on_data, max_events):
    """一次 SSE 连接；返回 (收到的事件数, 正常结束?)。"""
    req = urllib.request.Request(base.rstrip("/") + "/event",
                                 headers={"Accept": "text/event-stream"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    count = 0
    with urllib.request.urlopen(req, timeout=30) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if not line.startswith("data:"):
                continue
            text = line[5:].strip()
            if not text or text == "[DONE]":
                continue
            try:
                data = json.loads(text)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            if on_data(data):
                count += 1
                if max_events and count >= max_events:
                    return count, True
    return count, True


def main():
    args = sys.argv[1:]
    base = os.environ.get("OPENCODE_BASE_URL", "http://127.0.0.1:4096")
    max_events = 0
    debug = False
    for i, a in enumerate(args):
        if a == "--base" and i + 1 < len(args):
            base = args[i + 1]
        elif a == "--max-events" and i + 1 < len(args):
            max_events = int(args[i + 1])
        elif a == "--debug":
            debug = True
    token = os.environ.get("OPENCODE_TOKEN") or None
    inbox = default_dir()
    seen_keys = {}          # 组合键有界去重（重连不重播）
    total = 0
    running = True

    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    def on_data(data):
        key = (str(data.get("id") or "") or
               f"{data.get('type')}|{_sid(data)}|"
               f"{data.get('toolCallID') or data.get('toolCallId') or ''}|"
               f"{data.get('status') or ''}")
        if key in seen_keys:
            return False
        seen_keys[key] = time.time()
        if len(seen_keys) > 2048:
            horizon = sorted(seen_keys.values())[-1024:]
            floor = horizon[0]
            for k in [k for k, v in seen_keys.items() if v < floor]:
                del seen_keys[k]
        mapped = map_event(data)
        if not mapped:
            return False
        kind, fields = mapped
        write_event(inbox, "opencode", kind, **fields)
        if debug:
            print("[comi-opencode] →", kind, fields.get("session_id"),
                  file=sys.stderr)
        return True

    attempt = 0
    while running:
        try:
            count, _ = stream_once(base, token, on_data, max_events)
            total += count
            attempt = 0
            if max_events and total >= max_events:
                return 0
            if debug:
                print("[comi-opencode] stream ended, reconnecting",
                      file=sys.stderr)
            time.sleep(1)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            if debug:
                print(f"[comi-opencode] down ({exc}), retrying",
                      file=sys.stderr)
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
            attempt += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
