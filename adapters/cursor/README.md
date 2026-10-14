# Cursor 适配器（Iven 桌宠桥接）

把 Cursor 的本地 Agent Chat Hooks 转成统一事件写入本地收件箱
（`~/.iven-pet/events`），桌宠据此显示工作/等待/本轮结束等状态。

## 安装

把 `hooks.example.json` 的内容合并进项目 `.cursor/hooks.json` 或用户
`~/.cursor/hooks.json`（保留已有配置）。**两处脚本的执行工作目录不同**：
用户级以用户主目录、项目级以项目根为 cwd——command 里的相对路径按来源处理，
示例统一用绝对路径最稳妥。替换 `__IVER_REPO__` 为本仓库绝对路径。

## 验证

```bash
echo '{"sessionId":"t1","hookEventName":"preToolUse","toolName":"terminal"}' \
  | python3 adapters/cursor/cursor_hook.py
ls ~/.iven-pet/events/
```

真实验收：在真实本地 Agent Chat 里触发一次工具调用与最终回复；错误或停止
不能误报成功；用户级/项目级两种配置路径分别确认脚本能找到。测试插件失灵
不应影响正常编码（Hook 失败静默退出）。

## 卸载

从 hooks.json 删除对应条目；`rm -rf ~/.iven-pet`。

## 隐私与边界

- 默认**只传状态**；`IVEN_BRIDGE_SUMMARY=1` 才附带任务标签与最终回复摘要
  （afterAgentResponse，截断 160 字）。**不接 afterAgentThought**——内部
  推理不当作用户摘要。
- `stop.status`：completed → 本轮结束（不是任务成功）、aborted → 中断、
  error → 失败。
- `followup_message` 可影响后续执行但不是任意时刻发消息接口，本适配器不用。
- 云端 Hook 即使触发也不会自动连到本地 bridge；云端接入留作后续独立方案。
- 只承诺 Hooks 状态能力：本轮未核验通用既有 IDE 会话控制 API。

## 事件映射

| Cursor Hook | 统一事件 |
| --- | --- |
| sessionStart / sessionEnd | session.started / session.ended |
| beforeSubmitPrompt | turn.started（可选任务标签） |
| preToolUse / postToolUse | tool.started / tool.finished（带调用 ID） |
| postToolUseFailure | tool.failed |
| afterAgentResponse | turn.ended（可选最终回复摘要） |
| stop（completed / aborted / error） | turn.ended / interrupted / turn.failed |

能力声明：read_state ✅ · read_summary 开关后 ✅ · send_prompt ❌（第二阶段）。
本机未安装 Cursor，验收以 fixture 重放为准；实际版本的 payload 字段名请按
当期官方文档核验（本适配器对 session_id/sessionId 等常见差异做了宽容提取）。
