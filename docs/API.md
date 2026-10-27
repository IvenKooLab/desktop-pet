# 本机控制接口（File Control API）

任何本机进程——其他 DSH 插件、shell 脚本、快捷指令——都可以通过一组
**本地 JSON 文件**驱动桌宠：让它说话、点播动作、入睡/唤醒、读实况。
与桥接事件、对话协议同风格：**零网络、零端口、原子写、读后即焚**，
权限即文件系统权限（仅本机用户可写 `~/.comi-pet/`）。

目录默认 `~/.comi-pet/api/`（环境变量 `COMI_API_DIR` 可覆盖）。
两端实现（Tk/`pet.py` 与 Swift/`ComiPet.swift`）语义一致。

## 请求

`~/.comi-pet/api/request-<id>.json`（原子写）：

```json
{"version": 1, "id": "cli-1234-abc", "action": "say", "text": "休息一下吧"}
```

| 字段 | 说明 |
| :--- | :--- |
| `version` | 固定 `1` |
| `id` | 调用方生成的唯一串（≤64 字符）；回复按 id 配对 |
| `action` | `say` / `play` / `sleep` / `wake` / `state` |
| `text` | `say` 的文本（控制字符清洗、截断 2000） |
| `state` | `play` 的动作名（见下） |

桌宠每 ~0.5 秒轮询一次；请求文件**处理即取走**，随后在同目录写
`reply-<id>.json`（含 `version`/`id`/`ok` 与各动作的结果字段），
调用方读取即消费。请求 15 分钟无人消费、回复滞留 5 分钟会被清理。

## 动作

| action | 参数 | 成功回复 | 说明 |
| :--- | :--- | :--- | :--- |
| `say` | `text` | `{"ok": true, "shown": bool}` | 气泡说一句话；`shown=false` 表示桌宠当前在 DSH 界面内（桌面端隐藏），只确认不显示 |
| `play` | `state` | `{"ok": true, "state": "..."}` | 点播动作。白名单 = `frames3d/animation.json` 的剪辑名（`CHEER`、`WORK`、`STRETCH`…）+ 内置 `IDLE`/`WALK`/`RUN`/`SLEEP`/`BOUNCE`/`HAPPY`/`SHY`/`SPIN`。多数动作需要站在平台上（`not-grounded`） |
| `sleep` | — | `{"ok": true}` | 手动入睡（点击可唤醒） |
| `wake` | — | `{"ok": true, "was_asleep": bool}` | 唤醒 |
| `state` | — | 快照全量字段 | 同步读取一次实况 |

失败回复统一 `{"ok": false, "reason": "bad-request" | "unsupported" | "not-grounded" | "internal-error"}`。

## 状态快照

桌宠每 ~1 秒原子写 `~/.comi-pet/state.json`（无需发请求即可直接读）：

```json
{"version": 1, "updated": "2026-10-22T19:00:00+08:00", "state": "WORK",
 "x": 812, "y": 640, "display": "desktop", "following": "dsh",
 "host_mode": "working"}
```

- `state`：当前动作（剪辑名或内置状态）
- `display`：`desktop`（独立桌面）/ `embedded`（DSH 界面内，桌面端隐藏）
- `following` / `host_mode`：桥接来源与归约后的工作状态（未接通为 `null`）
- `x`/`y`：窗口左上角坐标（注意 Tk 屏幕坐标 y 向下；Swift 端写入 Cocoa 坐标 y 向下换算前的原始值，以 `state.json` 所在端为准）

## 命令行

```sh
python tools/comi_cli.py say "休息一下吧"
python tools/comi_cli.py play CHEER
python tools/comi_cli.py state
python tools/comi_cli.py wake
```

## 边界

- 文本只作数据展示（清洗控制字符、截断），绝不当作指令执行；
- `say`/`play` 不打断拖拽、投掷、睡眠队列和宿主状态卡的既有优先级；
- 该接口不提供权限审批、任务发送等能力——与桥接协议一样，
  桌宠绝不代用户操作编码助手。
