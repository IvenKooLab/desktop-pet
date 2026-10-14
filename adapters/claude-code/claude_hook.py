#!/usr/bin/env python3
"""Claude Code Hooks → Iven 桌宠桥接收件箱适配器。

用法（三处任选，合并已有配置别覆盖其他 Hook）：
- 用户级 ~/.claude/settings.json
- 项目级 .claude/settings.json / .claude/settings.local.json
- 插件 hooks/hooks.json
command 形式（与 ZCode 的 process+args 结构不同，别互抄）：
    ["python3", "<本仓库绝对路径>/adapters/claude-code/claude_hook.py"]

事件映射与边界见 adapters/claude-code/README.md：Notification 同时覆盖
"等权限"和"输入空闲"，统一按等待用户处理；实际安装版本缺失的事件静默跳过
（未知事件名不映射即自动降级）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hook_common import run, summary_enabled, clean, first_key  # noqa: E402

# Claude Code Hook 事件 → 统一事件 kind
EVENT_MAP = {
    "SessionStart": "session.started",
    "UserPromptSubmit": "turn.started",
    "PreToolUse": "tool.started",
    "PermissionRequest": "permission.required",
    "Notification": "permission.required",   # 等权限或输入空闲：都是"等你"
    "PostToolUse": "tool.finished",
    "PostToolUseFailure": "tool.failed",
    "Stop": "turn.ended",
    "SessionEnd": "session.ended",
}


def build_event(payload):
    name = payload.get("hook_event_name") or payload.get("event") or ""
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
        "tool_call_id": clean(first_key(payload, "tool_use_id", "toolUseId"), 64),
    }


if __name__ == "__main__":
    sys.exit(run(build_event, "claude-code"))
