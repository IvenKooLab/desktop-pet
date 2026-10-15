#!/usr/bin/env python3
"""Hook 适配器公共运行时：stdin 一行 JSON → 宿主映射 → 收件箱，永不打扰宿主。

各宿主脚本（zcode / claude-code / cursor …）只提供 build_event(payload)；
这里的约定对全家一致（docs/BRIDGE.md）：
- stdout 保持宿主协议输出（我们什么都不写）；调试走 stderr 且默认静默；
- 默认只传状态，IVEN_BRIDGE_SUMMARY=1 才附带任务标签/有限摘要；
- Hook 文本一律当数据清洗后转发，不执行；正常返回，不阻断、不自动审批；
- 桌宠没开也照常成功（写文件即返回），绝不阻塞宿主。
"""
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from host_bridge import write_event, default_dir  # noqa: E402

SUMMARY_ENV = "IVEN_BRIDGE_SUMMARY"
DEBUG_ENV = "IVEN_BRIDGE_DEBUG"
STDIN_CAP = 65536


def summary_enabled():
    """摘要开关：环境变量，或本机标记文件 ~/.iven-pet/summary。

    GUI 应用派生的 Hook 进程继承不到 shell 环境变量，标记文件是
    Mac/Windows 上最可靠的开法：`touch ~/.iven-pet/summary` 即开。
    """
    from pathlib import Path
    import os
    if os.environ.get(SUMMARY_ENV, "") not in ("", "0", "false"):
        return True
    return (Path.home() / ".iven-pet" / "summary").is_file()


def clean(value, limit):
    """事件文本进气泡前清洗：去控制字符 + 截断（文本只作数据）。"""
    if not isinstance(value, str):
        return None
    cleaned = "".join(ch if ch >= " " and ch != "\x7f" else " "
                      for ch in value).strip()
    return cleaned[:limit] if cleaned else None


def first_key(payload, *names):
    """宽容取键：不同宿主/版本字段大小写不一致（session_id / sessionId）。"""
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return None


def run(build_event, source):
    """宿主脚本入口：读 stdin → 映射 → 写收件箱 → exit 0（任何失败静默）。"""
    try:
        raw = sys.stdin.read(STDIN_CAP)
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not an object")
        mapped = build_event(payload)
        if mapped is not None:
            kind, fields = mapped
            write_event(default_dir(), source, kind, **fields)
    except Exception as exc:                       # 任何失败都不打扰宿主
        if os.environ.get(DEBUG_ENV):
            print(f"[iven-hook:{source}] {exc}", file=sys.stderr)
    return 0
