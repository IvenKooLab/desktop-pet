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


def following_badge(bridge, zh=True):
    if bridge is not None and bridge.enabled and bridge.selected_source and not bridge.source:
        name = SOURCES.get(bridge.selected_source, bridge.selected_source)
        return (name+(" · 未收到事件" if zh else " · No events"), "#8b8792")
    if bridge is None or not bridge.enabled or not bridge.source:
        return ("独立模式" if zh else "Standalone", "#8b8792")
    name = SOURCES.get(bridge.source, bridge.source)
    colors = {"zcode":"#8b5cc6", "dsh":"#487dc5", "codex":"#398c79",
              "claude-code":"#be7657", "cursor":"#555766", "opencode":"#6578ab"}
    if bridge.mode:
        others = max(0,len(bridge.active_sources)-1)
        text = ("跟随 · " if zh else "Following · ")+name
        if others and not bridge.selected_source:
            text += "  +"+str(others)
    else:
        text = ("最近 · " if zh else "Last · ")+name
    return text, colors.get(bridge.source,"#8b8792")
