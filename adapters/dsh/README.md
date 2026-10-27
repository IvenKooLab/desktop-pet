# DSH 适配器：状态联动与界面内桌宠

[dsh](https://github.com/deepseek-ai/deepseek-harness)（DeepSeek Harness）宿主插件：
订阅 `session/event`，把工作状态归约为统一事件写入本地收件箱（默认
`~/.comi-pet/events`），由 Comi 桌宠消费。另通过 DSH 官方 `shell.overlay`
插槽在当前 Harness 界面内显示同一个 Comi，支持与独立桌面模式切换。
两种显示方式共用仓库内已批准的透明 PNG、动作时间轴与动作编排配置，
没有复制或重新设计角色素材。状态归约语义参考
[dsh-pet](https://github.com/PC2005-cloud/dsh-pet)（MIT）的经验：
`turn/end` 只是"本轮结束"；goal 自动续跑的轮次不算任务完成；只有
`update_goal` 显式 `complete` / `blocked` 才映射为 `task.completed` / `turn.failed`。

## 安装

方式 A（推荐，与 loci-dsh 同做法）：

```bash
# 1. 把插件符号链接进你的 profile（示例为 web）
ln -s <本仓库绝对路径>/adapters/dsh/comi-bridge \
      $DSH_HOME/profiles/web/node_modules/comi-bridge
# 2. 在该 profile 的 cordis.patch.yml 里加一行条目（参考 comi-bridge/cordis.patch.yml）：
#    - id: comi-bridge
#      name: comi-bridge
#      config: { eventsDir: "", summary: false }
```

方式 B：`dsh plugin --profile <name> add <本目录绝对路径>`。

一次性试验也可以 `dsh --profile <name> --patch <补丁文件>`：把
`comi-bridge/cordis.patch.yml` 复制到别处、`name` 改成相对补丁文件的
`./comi-bridge/` 路径（相对路径按补丁文件位置锚定）。

## 验证

```bash
node adapters/dsh/self-test.mjs     # 纯映射语义自测（无需启动 dsh）
node adapters/dsh/web-test.mjs      # 路由、同源防护、显示租约与 overlay 注册
```

然后在 dsh 里跑一个真实任务（开始 → 工具执行 → 审批等待 → 结束），
观察桌宠动作；`ls ~/.comi-pet/events` 应看到事件被陆续消费。

首次安装或更新本适配器后，重启 DSH 再刷新页面，使宿主和浏览器入口同时更新。
界面右上角会出现 **Comi · 移入界面**：点击后，宠物只在当前 DSH 页面内活动；
可拖动位置，右键点播动作。工作中或等待确认时，角色上方持续显示 DSH 状态，
开启摘要后还会显示任务标签。再次点击入口或宠物右键菜单中的 **移到独立桌面**
可切回独立模式。

独立应用须先运行（Mac：`start-mac.command`；Windows：`python pet.py`）。
适配器切换显示位置，不另行启动或终止应用。独立应用菜单也可请求进入 DSH 界面；
DSH 页面收到请求后认领显示权（写入 client_id 并续满租期），桌宠确认被接手后才隐藏——插件尚未加载或页面没开时，请求租约只有约 6 秒确认窗口，超时自动回桌面并提示，不会再白藏 30 秒；已接手后页面断开则租约到期（最长 30 秒）恢复桌宠。

这是 **DSH 专用的界面内模式**。其他 Harness 的状态适配器不因此拥有界面注入能力。
浏览器刷新后，界面入口仍可用；多开 DSH 页面时，仅最后显式选中的页面显示宠物。

## 配置

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `eventsDir` | `COMI_BRIDGE_DIR` 环境变量或 `~/.comi-pet/events` | 收件箱目录 |
| `summary` | `false` | 开启后附带 todo 提炼的任务标签（截断 80 字） |

## 卸载

从 profile 的 `cordis.patch.yml` 删除 `comi-bridge` 条目并移除符号链接；
删除前可先切回独立桌面；即使直接关闭页面，有效期结束后独立应用也会恢复。
`~/.comi-pet` 同时包含其他适配器的设置与事件，卸载 DSH 插件无需删除整个目录。

## 显示协议与资源接口

显示意图位于收件箱的上级目录 `display.json`（默认 `~/.comi-pet/display.json`）：

```json
{"version":1,"owner":"dsh","mode":"embedded","lease_until":1800000030000,"client_id":"web_example123"}
```

`mode` 可为 `embedded` 或 `desktop`；界面每 5 秒续约一次，租约最长 30 秒。
无效、损坏、过期或远超有效期的文件一律按独立桌面处理。页面转入后台不再续约，
避免宠物长时间隐藏在不可见标签页。原生菜单写入的无 `client_id` 请求由第一个可见页面认领；
其他页面的心跳不能覆盖现有认领。显式点击界面入口可转移显示权。

插件在 DSH 的同源 Web 服务挂载以下路由，不新开端口：

| 路由 | 用途 |
| --- | --- |
| `GET /comi-pet/api/state` | DSH 当前工作状态、显示模式与租约 |
| `GET /comi-pet/api/manifest` | 已批准帧的时间轴 |
| `GET /comi-pet/api/behaviors` | 与独立应用共用的动作编排 |
| `GET /comi-pet/frames/<name>.png` | 只允许时间轴列出的透明 PNG |
| `POST /comi-pet/api/display` | 显式选择显示模式和当前页面 |
| `POST /comi-pet/api/heartbeat` | 当前页面续约，不允许后台抢占 |

控制路由采用与 loci-dsh / DSH API 网关同类的 Host / Origin / Fetch Metadata 校验，
拒绝跨站浏览器请求；这属于浏览器请求边界，不是用户鉴权。
素材直接从本仓库的 `frames3d/` 读取，因此请按上述本地目录方式安装，
保留仓库目录结构。无 Web 服务的 DSH profile 仍可只用事件收件箱桥接。

## 和 Comi 说话（对话功能）

装好本插件后（需含 `llm` 服务的 profile，web 默认满足），桌宠右键菜单会出现
**"和 Comi 说话…"**：输入一句话，Comi 会用你 DSH 里配置的模型生成回复，
以气泡显示，还可能搭配一个表情动作（happy/shy/cheer/greet/relieved）。

- 对话记忆在 `~/.comi-pet/chat/memory.json`，默认保留最近 8 轮；清空即删该文件。
- DSH 没开、没配置模型或生成失败时，桌宠会如实提示，不会假装聊天成功。
- 配置（profile 的 comi-bridge 条目 `config:`，均可省略）：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `chat` | `true` | 关闭后菜单输入会得到如实的"没有等到回复" |
| `chatDir` | `~/.comi-pet/chat` | 请求/回复/记忆目录 |
| `chatMemoryRounds` | `8` | 记忆保留轮数 |
| `chatTimeoutMs` | `60000` | 单次生成超时 |
| `chatProvider` / `chatModel` | 跟随会话 | 固定对话模型（覆盖默认跟随） |

自测：`node adapters/dsh/chat-test.mjs`（假 llm 全流程，无需启动 dsh）。

## 事件映射

| DSH `session/event` | 统一事件 |
| --- | --- |
| turn/start | turn.started |
| tool/call | tool.started（`update_goal` 同时记录 closing） |
| tool/result | tool.finished |
| approval/asked | permission.required |
| todo/write | task.updated（开启摘要后带任务标签） |
| turn/end（closing=complete） | task.completed |
| turn/end（closing=blocked） | turn.failed |
| turn/end（其余，含 goal 续跑） | turn.ended |
