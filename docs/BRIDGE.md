# 桌宠桥接（宿主事件 → 桌宠动作）维护文档

让 Iven 桌宠感知本地编码助手（ZCode、DSH 等）的工作状态。**事件感知是单向、
本地的**：宿主适配器 → 本地收件箱 → 桌宠。桌宠不能驱动宿主会话、不能自动
批准工具；那是第二阶段的独立能力，不在本设计内。

## 架构

```
宿主 Hooks / 插件事件
        ↓ 适配器（adapters/…）：提取事件、状态与有限摘要
本地收件箱（默认 ~/.iven-pet/events，仅本机文件）
        ↓
Iven 桌宠（Mac 原生 Swift / Windows Tk）轮询消费 → 状态动作 + 提醒 + 离线回退
```

选择本地原子文件收件箱而非 HTTP：无监听端口、无令牌管理、宿主 Hook 写一个
文件即刻退出（绝不阻塞宿主）。写入 = 临时文件 + `rename` 原子落盘；文件名
`<纳秒时间戳>-<event_id>.json` 按字典序即时间序。

## 统一事件协议 v1

```json
{
  "version": 1,
  "event_id": "producer-generated-id",
  "source": "zcode",
  "session_id": "session-123",
  "turn_id": null,
  "timestamp": "2026-10-14T12:00:00.000Z",
  "kind": "permission.required",
  "task_label": "运行测试",
  "summary": "需要确认后继续",
  "tool_name": "Bash",
  "severity": "info"
}
```

- `kind` 全集：`session.started` / `turn.started` / `tool.started` /
  `permission.required` / `tool.finished` / `tool.failed` / `turn.ended` /
  `turn.failed` / `task.completed` / `interrupted` / `session.ended`。
- **默认只传状态**：适配器不填 `task_label`/`summary`，用户显式开启
  （ZCode：`IVEN_BRIDGE_SUMMARY=1`；DSH：插件配置 `summary: true`）才附带，
  且各自截断（80/160 字）并清洗控制字符。
- 消费端约束：事件文本**只作数据展示，绝不当作指令执行**（提示注入防线）；
  未知字段忽略；`version`≠1 或 `kind` 不认识 → 丢弃。

## 归约语义（三处实现必须一致）

同一套语义有三个实现：`host_bridge.py`（Tk 端 + 测试）、
`native/macos/IvenPet.swift` 的 `HostBridge`（Mac 原生端）、
`adapters/dsh/iven-bridge/index.js` 的 `mapEvent`（DSH 侧半段）。改语义时
三处同步改，并同步三份测试：

- Python：`tests/test_host_bridge.py`、`tests/test_zcode_adapter.py`
- Swift：`--self-test`（`zsh tools/build_macos.sh` 后运行二进制 `--self-test`）
- Node：`node adapters/dsh/self-test.mjs`

核心规则：

| 事件 | 桌宠行为 |
| --- | --- |
| session.started | 注册会话，无可见变化 |
| turn.started / tool.started | WORK（可选任务标签气泡，每 turn 一次） |
| permission.required | WAITING + 重要提醒（等待用户回宿主批准） |
| tool.finished | 仍 working（只更新计数，不宣布完成） |
| tool.failed | 短暂 FAILED 闪现，宿主可自行恢复 |
| turn.ended | 本轮结束 → 回普通轮播；显示"本轮回复结束"，**不显示成功** |
| turn.failed | FAILED + 重要提醒 |
| task.completed | 明确完成 → CHEER/HAPPY |
| interrupted / session.ended | 清会话；全空后回普通轮播 |

**Stop / turn.end 只是"准备结束当前轮"**，可能被宿主其他 Hook 阻断，不是任务
成功证据。DSH 侧只有 `update_goal` 显式 `complete` 才发 `task.completed`；
goal 自动续跑轮次（`user/message` 的 `source.kind === 'goal'`）只算本轮结束。

并发与韧性：按 `session_id` 分组（多会话并行时，任一 waiting 优先于 working，
全部结束才算闲）；`event_id` 去重（有界 LRU）；单轮最多消费 64 条、积压上限
500、事件过期 180s；**断线回退**：最新事件静默超过 120s → 清空全部会话，
桌宠无声恢复普通轮播。

## 桌宠侧优先级

```
用户拖拽 / 手动睡觉 / 手动点播 > 等待确认 > 宿主工作状态 > 普通自动轮播
```

- 拖拽/下落/着陆期间宿主不抢；手动点播有抑制窗口（片段时长 + ~1.5s）；
  手动睡眠**绝不自动唤醒**——重要提醒（等待确认/失败/完成）入队（≤3 条），
  唤醒后补播最近一条。
- 桥接是可选能力：`PET_BRIDGE=0` 环境变量可整体关闭；右键菜单
  "宿主桥接"即时开关；收件箱目录不存在时轮询静默空转，桌宠完全独立。
- Mac 原生版不因桥接引入 Python/Node 依赖（`HostBridge` 纯 Foundation）。

## 适配器

### ZCode（`adapters/zcode/`）

- 入口：官方 Hooks（`SessionStart`/`UserPromptSubmit`/`PreToolUse`/
  `PermissionRequest`/`PostToolUse`/`PostToolUseFailure`/`Stop`），
  `process` 执行器 `command + args`，stdin 一行 JSON。
- 安装：用户级 `~/.zcode/cli/config.json`（`hooks.enabled: true`，见
  `user-config.example.json`）或插件 `hooks/hooks.json`。**项目级
  `.zcode/config.json` 当前被忽略**；配置在 session 启动时快照，改完要开
  新 session 验证。
- 不读 `transcript_path`（临时 JSONL，Hook 后即清理）；不返回 block、
  不改权限、不调用模型；stdout 保持宿主协议输出，调试走 stderr
  （`IVEN_BRIDGE_DEBUG=1`）。

### DSH（`adapters/dsh/`）

- 入口：宿主插件 `ctx.on('session/event', …)`（cordis 插件，ESM，零依赖）。
- 安装：符号链接进 profile 的 `node_modules` + `cordis.patch.yml` 条目
  （与 loci-dsh 同做法），或 `dsh plugin --profile <name> add <路径>`。
- `apply()` 里所有订阅包在 `ctx.effect(() => … return dispose)` 内。

### 第二批（Qwen Code / Kimi Code / Qoder / CodeBuddy / TRAE CN）

均按各自官方 Hooks 接"状态/摘要接入"，映射到同一协议；各自的安装形态、
字段口径与"仅监测 vs 可驱动"的边界在接入前按当期文档重新核验，不在本仓
预置配置。双向会话控制（`send_prompt`）是第二阶段独立提案，默认不做。

## 安全红线

- 不上传/不落盘全量对话、工具结果、源码或凭据；默认只传状态。
- 事件文本是数据：清洗（去控制字符、截断）后仅用于气泡展示，不执行。
- 不通过 Hook 自动批准工具、不绕过宿主权限审批、不代宿主发消息。
- 收件箱仅本机；如未来换 HTTP，必须 loopback + 本地令牌 + 长度限制。

## 变更检查单

改桥接任何一侧后：

```bash
python -m unittest discover -s tests        # 含 bridge/zcode 重放
zsh tools/build_macos.sh && ./build/IvenPet.app/Contents/MacOS/IvenPet --self-test
node adapters/dsh/self-test.mjs             # 有 node 环境时
```

真实验收（自动测试替代不了）：新 session 跑真实任务走一遍
开始 → 工具执行 → 等待确认 → 继续 → 本轮结束；再验工具失败、手动中断、
并行会话、桌宠关闭重开。Windows 透明窗口/拖拽/气泡需实机补验。
