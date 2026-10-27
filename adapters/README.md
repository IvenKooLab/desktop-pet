# 适配器总览：能力矩阵与验收状态

全部适配器共用同一套 bridge（协议 v1、收件箱 `~/.comi-pet/events`、桌宠端
状态归约），见 [docs/BRIDGE.md](../docs/BRIDGE.md)。统一能力声明：
`read_state` / `read_summary` / `send_prompt`——未核实或不支持就如实为 ❌，
不提供会静默失效的按钮。第二阶段（`send_prompt`）统一设计，不逐家私造。

| 适配器 | 接入形态 | read_state | read_summary | send_prompt | 已验证版本 | 验收方式 |
| --- | --- | :-: | :-: | :-: | --- | --- |
| [ZCode](zcode/README.md) | 官方 Hooks（process 执行器） | ✅ | 开关后 ✅ | ❌ | 接口按官方文档 | fixture 重放（`tests/test_zcode_adapter.py`）；**真实新 session 验收待用户执行** |
| [DSH](dsh/README.md) | cordis 宿主插件（session/event） | ✅ | 开关后 ✅ | ❌（SDK 属二阶段） | 事件语义按 dsh-pet 与本地 dsh 源码 | 映射自测（`dsh/self-test.mjs`）+ Python 归约重放；真实任务待用户执行 |
| [Codex](codex/README.md) | App Server stdio JSON-RPC | ✅（仅本客户端会话） | ❌ | ❌ | **codex-cli 0.162.1 实测握手/thread-list** | mock 重放 + 实连 `--list`；**当前不支持跟随正在使用的 Codex 桌面会话**（ipc.sock 为内部 IPC） |
| [Claude Code](claude-code/README.md) | Hooks（command 形式） | ✅ | 开关后 ✅ | ❌ | 按官方文档 | fixture 重放（`tests/test_host_hooks.py`）；本机未装，实机待用户验收 |
| [Cursor](cursor/README.md) | Hooks（项目/用户 hooks.json） | ✅ | 开关后 ✅ | ❌ | 按官方文档 | fixture 重放；本机未装，实机待用户验收 |
| [OpenCode](opencode/README.md) | Server HTTP SSE 监听 | ✅ | ❌ | ❌ | 按官方文档 | mock SSE 重放（`tests/test_opencode_adapter.py`）；本机未装 |

共同约定（docs/BRIDGE.md「安全红线」）：
默认只传状态；摘要需显式开启且截断清洗；不读 transcript/消息正文冒充上下文；
Hook/监听失败静默退出不阻塞宿主；等待确认只提醒用户回宿主批准，不自动审批；
普通 Stop / turn end 一律显示"本轮结束"，只有明确结果事件才播完成。

**"旁听用户正在用的会话"与"客户端自建会话"是两回事**：目前六家都是只读
监测（Codex 明确仅本客户端会话）；任何适配器接不上时桌宠显示未连接是正确
行为，不从进程存在推断工作状态，更不会悄悄新建会话冒充旁听。
