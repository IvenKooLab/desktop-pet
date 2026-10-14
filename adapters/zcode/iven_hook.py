#!/usr/bin/env python3
"""ZCode Hooks → Iven 桌宠桥接收件箱适配器。

用法（~/.zcode/cli/config.json 或插件的 hooks/hooks.json，process 执行器）：
    {"type": "process", "command": "python3",
     "args": ["<本仓库绝对路径>/adapters/zcode/iven_hook.py"]}

行为约定（docs/BRIDGE.md）：
- 从 stdin 读一行 Hook JSON，映射为统一事件写入收件箱后立即退出；
  桌宠没开也照常成功，绝不阻塞宿主、绝不向 stdout 输出（那是宿主协议通道）。
- 默认只传状态；设 IVEN_BRIDGE_SUMMARY=1 才附带 task_label/摘要文本。
- Hook 收到的文本一律当数据清洗后转发，不执行；不读 transcript_path；
  第一版不返回 block、不改权限、不额外调用任何模型。
"""
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from host_bridge import write_event, default_dir  # noqa: E402

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
SUMMARY_ENV = "IVEN_BRIDGE_SUMMARY"


def _clean(value, limit):
    if not isinstance(value, str):
        return None
    cleaned = "".join(ch if ch >= " " and ch != "\x7f" else " "
                      for ch in value).strip()
    return cleaned[:limit] if cleaned else None


def build_event(payload):
    """Hook JSON → (kind, fields) 或 None（不认识的事件静默跳过）。"""
    name = payload.get("hook_event_name") or ""
    kind = EVENT_MAP.get(name)
    if kind is None:
        return None
    summary_on = os.environ.get(SUMMARY_ENV, "") not in ("", "0", "false")
    label = summary_text = None
    if summary_on:
        if name == "UserPromptSubmit":
            label = _clean(payload.get("prompt"), 80)
        elif name == "Stop":
            summary_text = _clean(payload.get("last_assistant_message"), 160)
    if name == "PostToolUseFailure" and payload.get("is_interrupt"):
        kind = "interrupted"
    return kind, {
        "session_id": payload.get("session_id") or "unknown",
        "task_label": label,
        "summary": summary_text,
        "tool_name": _clean(payload.get("tool_name"), 48),
    }


def main():
    try:
        raw = sys.stdin.read(65536)                    # 单行 JSON，上限防御
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not an object")
        mapped = build_event(payload)
        if mapped is not None:
            kind, fields = mapped
            write_event(default_dir(), "zcode", kind, **fields)
    except Exception as exc:                           # 任何失败都不打扰宿主
        if os.environ.get("IVEN_BRIDGE_DEBUG"):
            print(f"[iven-hook] {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
