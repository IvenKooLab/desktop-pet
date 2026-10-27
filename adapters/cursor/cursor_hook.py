#!/usr/bin/env python3
"""Cursor Hooks → Comi 桌宠桥接收件箱适配器。

配置在项目 `.cursor/hooks.json` 或用户 `~/.cursor/hooks.json`（两处脚本
工作目录不同：相对路径按配置来源处理，示例统一建议绝对路径）。
Cursor 事件命名是自己的驼峰式（sessionStart / beforeSubmitPrompt /
postToolUse / afterAgentResponse / stop …），不能直接贴 Claude 的
SessionStart / Stop 配置。

边界：afterAgentResponse 是最终回复文本，摘要开关开启后可显示；
afterAgentThought（内部推理）不接。stop 的 status=completed/aborted/error
分别映射本轮结束/中断/失败——completed 仍只是"本轮结束"，不是任务成功。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hook_common import run, summary_enabled, clean, first_key  # noqa: E402

# Cursor Hook 事件（驼峰）→ 统一事件 kind
EVENT_MAP = {
    "sessionStart": "session.started",
    "sessionEnd": "session.ended",
    "beforeSubmitPrompt": "turn.started",
    "preToolUse": "tool.started",
    "postToolUse": "tool.finished",
    "postToolUseFailure": "tool.failed",
    "afterAgentResponse": "turn.ended",
    "stop": "turn.ended",
}


def build_event(payload):
    name = (first_key(payload, "hook_event_name", "hookEventName",
                      "event", "type") or "")
    kind = EVENT_MAP.get(name)
    if kind is None:
        return None
    label = summary_text = None
    if summary_enabled():
        if name == "beforeSubmitPrompt":
            label = clean(first_key(payload, "prompt", "userPrompt"), 80)
        elif name == "afterAgentResponse":
            summary_text = clean(first_key(payload, "text", "response",
                                           "agentResponse"), 160)
    if name == "stop":
        status = (first_key(payload, "status", "stopStatus") or "").lower()
        if status in ("aborted", "cancelled", "canceled"):
            kind = "interrupted"
        elif status in ("error", "failed"):
            kind = "turn.failed"
    return kind, {
        "session_id": first_key(payload, "session_id", "sessionId",
                                "conversationId") or "unknown",
        "task_label": label,
        "summary": summary_text,
        "tool_name": clean(first_key(payload, "tool_name", "toolName"), 48),
        "tool_call_id": clean(first_key(payload, "tool_use_id", "toolUseId",
                                        "toolCallId", "callId"), 64),
    }


if __name__ == "__main__":
    sys.exit(run(build_event, "cursor"))
