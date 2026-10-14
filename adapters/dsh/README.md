# DSH 适配器（Iven 桌宠桥接）

[dsh](https://github.com/deepseek-ai/deepseek-harness)（DeepSeek Harness）宿主插件：
订阅 `session/event`，把工作状态归约为统一事件写入本地收件箱（默认
`~/.iven-pet/events`），由 Iven 桌宠消费。状态归约语义参考
[dsh-pet](https://github.com/PC2005-cloud/dsh-pet)（MIT）的经验：
`turn/end` 只是"本轮结束"；goal 自动续跑的轮次不算任务完成；只有
`update_goal` 显式 `complete` / `blocked` 才映射为 `task.completed` / `turn.failed`。

## 安装

方式 A（推荐，与 loci-dsh 同做法）：

```bash
# 1. 把插件符号链接进你的 profile（示例为 web）
ln -s <本仓库绝对路径>/adapters/dsh/iven-bridge \
      $DSH_HOME/profiles/web/node_modules/iven-bridge
# 2. 在该 profile 的 cordis.patch.yml 里加一行条目（参考 iven-bridge/cordis.patch.yml）：
#    - id: iven-bridge
#      name: iven-bridge
#      config: { eventsDir: "", summary: false }
```

方式 B：`dsh plugin --profile <name> add <本目录绝对路径>`。

一次性试验也可以 `dsh --profile <name> --patch <补丁文件>`：把
`iven-bridge/cordis.patch.yml` 复制到别处、`name` 改成相对补丁文件的
`./iven-bridge/` 路径（相对路径按补丁文件位置锚定）。

## 验证

```bash
node adapters/dsh/self-test.mjs     # 纯映射语义自测（无需启动 dsh）
```

然后在 dsh 里跑一个真实任务（开始 → 工具执行 → 审批等待 → 结束），
观察桌宠动作；`ls ~/.iven-pet/events` 应看到事件被陆续消费。

## 配置

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `eventsDir` | `IVEN_BRIDGE_DIR` 环境变量或 `~/.iven-pet/events` | 收件箱目录 |
| `summary` | `false` | 开启后附带 todo 提炼的任务标签（截断 80 字） |

## 卸载

从 profile 的 `cordis.patch.yml` 删除 `iven-bridge` 条目并移除符号链接；
`rm -rf ~/.iven-pet` 清掉收件箱。

## 事件映射

| DSH `session/event` | 统一事件 |
| --- | --- |
| turn/start | turn.started |
| tool/call | tool.started（`update_goal` 同时记录 closing） |
| tool/result | tool.finished |
| approval/asked | permission.required |
| todo/write | （仅更新任务标签，不发事件） |
| turn/end（closing=complete） | task.completed |
| turn/end（closing=blocked） | turn.failed |
| turn/end（其余，含 goal 续跑） | turn.ended |
