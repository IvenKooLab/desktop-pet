# Codex 适配器（Comi 桌宠桥接）

OpenAI Codex 的 App Server（stdio JSON-RPC）→ 统一事件 → 本地收件箱。

**已验证版本：codex-cli 0.162.1**（本机实测）：
- spawn `codex app-server` → `initialize` / `initialized` / `thread/list`
  握手与通知推送正常（行分隔 JSON，通知带 `emittedAtMs`）；
- `thread/list` 能读到本机共享线程历史（`~/.codex` 下的存储）。

**能力边界（如实）**：
- 本适配器监听的是**它自己驱动的 app-server 实例**上的会话事件——
  "仅支持本客户端会话"。桌面 App 正在使用的会话不会自动出现在这里：
  桌面实例的 `~/.codex/ipc/ipc.sock` 对 app-server 握手无响应（内部 IPC），
  已实测确认**不读它**、不冒充实时集成。等官方提供受支持的共享事件入口再扩展。
- `turn/start`（发送任务）属第二阶段，此处不实现；`--list` 只读。
- Codex 桌面自带的 Pets 与 App Server 是不同功能，互不通用。

## 用法

```bash
python3 adapters/codex/comi_codex.py --list    # 诊断：握手 + 线程列表后退出
python3 adapters/codex/comi_codex.py           # 常驻：转发 turn/approval 事件
```

`--server-cmd "codex app-server"` 可换自定义命令（测试替身用）；
`--debug` 走 stderr。卸载：Ctrl-C 退出 + `rm -rf ~/.comi-pet`。

## 事件映射

| App Server | 统一事件 |
| --- | --- |
| turn/started | turn.started |
| turn/completed（completed） | turn.ended（**本轮结束≠任务成功**） |
| turn/completed（interrupted / failed） | interrupted / turn.failed |
| approval/*（asked/requested/pending，方法名宽容匹配） | permission.required |

能力声明：read_state ✅（本客户端会话）· read_summary ❌（事件不含文本，
第一版不读线程内容）· send_prompt ❌（第二阶段）。
app-server 进程退出时适配器正常退出（exit 0），桌宠按断线回退到普通轮播。
