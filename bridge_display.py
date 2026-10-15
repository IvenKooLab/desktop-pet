"""Persistent host status card text; never executes or fetches event content."""
SOURCES = {"zcode": "ZCode", "dsh": "DSH", "claude-code": "Claude Code",
           "codex": "Codex", "cursor": "Cursor", "opencode": "OpenCode"}


def activity_label(tool):
    parts = tool.split(" · ", 1)
    names = {"Read":"读取文件", "read_file":"读取文件", "Bash":"运行命令",
             "shell":"运行命令", "run_shell_command":"运行命令", "Edit":"修改文件",
             "Write":"写入文件", "Grep":"搜索代码", "Glob":"查找文件", "Task":"处理子任务"}
    return names.get(parts[0],parts[0]) + (" · "+parts[1] if len(parts)>1 else "")


def status_card(bridge, zh=True):
    if bridge.mode not in ("working", "waiting"):
        return None
    source = SOURCES.get(bridge.source, bridge.source or ("编码助手" if zh else "Coding agent"))
    state = ("等你确认" if bridge.mode == "waiting" else "工作中") if zh else (
        "Needs approval" if bridge.mode == "waiting" else "Working")
    title = source + " · " + state
    lines = []
    if bridge.label:
        lines.append(bridge.label)
    if bridge.detail:
        lines.append(("当前步骤 · " + activity_label(bridge.detail)) if zh else ("Current tool · " + bridge.detail))
    if not lines:
        lines.append(("请在原应用中确认后继续" if bridge.mode == "waiting" else "正在处理你的任务…") if zh else (
            "Continue in your coding app" if bridge.mode == "waiting" else "Processing your task…"))
    return title, "\n".join(lines), bridge.mode
