#!/usr/bin/env python3
"""测试替身：模拟 codex app-server 的行分隔 JSON-RPC（握手 + turn 推送）。"""
import json
import sys
import time


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    if msg.get("method") == "initialize":
        send({"id": msg["id"], "result": {"userAgent": "mock-codex/1.0",
                                          "codexHome": "/tmp"}})
    elif msg.get("method") == "thread/list":
        send({"id": msg["id"], "result": {"data": [
            {"id": "thread-mock-1", "preview": "mock thread"}]}})
        time.sleep(0.2)
        send({"method": "turn/started",
              "params": {"threadId": "thread-mock-1"}, "emittedAtMs":
              int(time.time() * 1000)})
        time.sleep(0.2)
        send({"method": "turn/completed",
              "params": {"threadId": "thread-mock-1", "status": "completed"},
              "emittedAtMs": int(time.time() * 1000)})
        time.sleep(0.2)
        send({"method": "turn/completed",
              "params": {"threadId": "thread-mock-2", "status": "failed"},
              "emittedAtMs": int(time.time() * 1000)})
        time.sleep(0.2)
        send({"method": "approval/requested",
              "params": {"threadId": "thread-mock-1"}, "emittedAtMs":
              int(time.time() * 1000)})
        time.sleep(30)   # 保活，等适配器侧 kill
        break
    elif msg.get("method") == "initialized":
        pass
