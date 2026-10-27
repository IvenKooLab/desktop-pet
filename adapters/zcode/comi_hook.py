#!/usr/bin/env python3
"""ZCode Hooks → Comi 桌宠桥接收件箱适配器。

用法（~/.zcode/cli/config.json 或插件的 hooks/hooks.json，process 执行器）：
    {"type": "process", "command": "python3",
     "args": ["<本仓库绝对路径>/adapters/zcode/comi_hook.py"]}

映射与边界见 adapters/zcode/README.md 与 docs/BRIDGE.md：
- stdin 一行 Hook JSON，映射为统一事件后立即退出；
- 默认只传状态，COMI_BRIDGE_SUMMARY=1 才附带任务标签/摘要；
- 不读 transcript_path；不返回 block、不改权限、不调用任何模型。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hook_common import run, summary_enabled, clean, first_key  # noqa: E402

# ZCode Hook 事件 → 统一事件 kind（interrupted 由 PostToolUseFailure 区分）
EVENT_MAP = {
    "SessionStart": "session.started",
    "UserPromptSubmit": "turn.started",
    "PreToolUse": "tool.started",
    "PermissionRequest": "permission.required",
    "PostToolUse": "tool.finished",
    "PostToolUseFailure": "tool.failed",
    "Stop": "turn.ended",
}


def build_event(payload):
    name = payload.get("hook_event_name") or ""
    kind = EVENT_MAP.get(name)
    if kind is None:
        return None
    label = summary_text = None
    if summary_enabled():
        if name == "UserPromptSubmit":
            label = clean(payload.get("prompt"), 80)
        elif name == "Stop":
            summary_text = clean(payload.get("last_assistant_message"), 160)
    if name == "PostToolUseFailure" and payload.get("is_interrupt"):
        kind = "interrupted"
    return kind, {
        "session_id": first_key(payload, "session_id", "sessionId") or "unknown",
        "task_label": label,
        "summary": summary_text,
        "tool_name": clean(first_key(payload, "tool_name", "toolName"), 48),
        "tool_call_id": clean(first_key(payload, "tool_use_id", "toolUseId",
                                        "tool_call_id"), 64),
    }


if __name__ == "__main__":
    sys.exit(run(build_event, "zcode"))
