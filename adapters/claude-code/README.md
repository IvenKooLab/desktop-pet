# Claude Code 适配器（Comi 桌宠桥接）

把 Claude Code CLI 的 Hooks 转成统一事件写入本地收件箱（`~/.comi-pet/events`），
桌宠据此显示工作/等待/本轮结束/失败/完成等状态。

## 安装

把 `settings.example.json` 里的 `hooks` 合并进（三处任选，都不覆盖已有配置）：

- 用户级 `~/.claude/settings.json`（对所有项目生效）
- 项目级 `.claude/settings.json` 或 `.claude/settings.local.json`
- 插件的 `hooks/hooks.json`

替换 `__IVER_REPO__` 为本仓库绝对路径。Claude Code 的 `command` 是**单字符串**
形式（经 shell 执行），与 ZCode 的 `command + args` 数组结构不同，别互抄。

## 验证

```bash
echo '{"session_id":"t1","hook_event_name":"PreToolUse","tool_name":"Bash"}' \
  | python3 adapters/claude-code/claude_hook.py
ls ~/.comi-pet/events/
```

真实验收（自动测试替代不了）：启动真实 CLI 新会话，执行一次工具、触发一次
人工审批、正常 Stop 与失败路径各走一遍。若 Hook 没生效，桌宠显示"未连接"
是正确行为——不从普通进程存在推断工作状态。

## 卸载

从 settings 删除对应 hooks 条目；`rm -rf ~/.comi-pet`。

## 隐私与边界

- 默认**只传状态**；`COMI_BRIDGE_SUMMARY=1` 才附带任务标签（截断 80 字）与
  Stop 回复摘要（截断 160 字）。
- `transcript_path` 只是本地会话记录路径且并非模型全部请求上下文：本适配器
  **不读取**它。
- Hook 只做短时本地投递，正常返回：不阻断、不自动审批、不调用模型。
- `Notification` 事件同时覆盖"等待权限"与"输入空闲"，统一按"等你"处理；
  实际版本缺失的事件自动跳过（显式降级，不猜字段）。

## 事件映射

| Claude Code Hook | 统一事件 |
| --- | --- |
| SessionStart | session.started |
| UserPromptSubmit | turn.started（可选任务标签） |
| PreToolUse | tool.started（带 tool_use_id → tool_call_id） |
| PermissionRequest / Notification | permission.required |
| PostToolUse | tool.finished |
| PostToolUseFailure | tool.failed（is_interrupt 时为 interrupted） |
| Stop | turn.ended（可选回复摘要；**不是**任务成功） |
| SessionEnd | session.ended |

能力声明：read_state ✅ · read_summary 开关后 ✅ · send_prompt ❌（第二阶段）。
本适配器按官方 Hooks 文档实现，在本机未安装 Claude Code，验收以 fixture
重放为准，实机请按上节自行验收。
