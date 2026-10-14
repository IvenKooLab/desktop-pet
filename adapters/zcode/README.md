# ZCode 适配器（Iven 桌宠桥接）

把 ZCode Agent 的工作状态发给 Iven 桌宠：工作中 → 打字/工作动作，等待确认 →
等待提醒，本轮结束/失败/完成 → 相应动作。宿主离线或桌宠没开都不影响 ZCode 本身。

## 安装（二选一）

### A. 用户级 Hooks（推荐，最直接）

1. 打开 `~/.zcode/cli/config.json`，把 `user-config.example.json` 里的
   `hooks` 内容合并进去（保留已有其他 hooks，别整文件覆盖）；
2. 把两处 `__IVER_REPO__` 替换成本仓库的绝对路径；
3. 新开一个 ZCode session（配置在 session 启动时快照，老窗口不保证热更新）。

### B. 插件形式

把 `zcode-plugin/` 作为插件安装（hooks/hooks.json 会被标准目录自动发现，
不要同时在 plugin.json 里重复声明），同样替换 `__IVER_REPO__` 后新开 session。

## 验证

新 session 里跑一个真实任务：开始 → 工具执行 → 等待确认 → 继续 → 本轮结束，
观察桌宠动作。也可以手动重放（不依赖宿主）：

```bash
echo '{"session_id":"t1","hook_event_name":"PreToolUse","tool_name":"Bash"}' \
  | python3 adapters/zcode/iven_hook.py
ls ~/.iven-pet/events/   # 应出现一个统一事件 JSON，桌宠会消费并进入工作状态
```

## 卸载

从 `config.json` 删除对应 hooks 条目（或移除插件），`rm -rf ~/.iven-pet`。

## 隐私与边界

- 默认**只传状态**：不含提示词、回复、工具内容。设 `IVEN_BRIDGE_SUMMARY=1`
  才附带任务标签（UserPromptSubmit 截断 80 字）与 Stop 回复摘要（截断 160 字）。
- 不读 `transcript_path`（临时文件，Hook 后即清理）；不返回 block、不改权限、
  不调用任何模型。Hook 文本一律当数据清洗后转发，绝不执行。
- 收件箱在本地（默认 `~/.iven-pet/events`，可用 `IVEN_BRIDGE_DIR` 改），无网络。

## 支持的事件

| ZCode Hook | 统一事件 |
| --- | --- |
| SessionStart | session.started |
| UserPromptSubmit | turn.started（可选任务标签） |
| PreToolUse | tool.started |
| PermissionRequest | permission.required |
| PostToolUse | tool.finished |
| PostToolUseFailure | tool.failed（is_interrupt 时为 interrupted） |
| Stop | turn.ended（可选回复摘要；**不是**任务成功） |
