# 更新日志

## [2.0.2] - 2026-10-28

紧急修复：v2.0.0 改名导致老用户宿主配置指向不存在的脚本，钩子集体失效。

### 修复

- 恢复旧路径脚本作为纯委托垫片（git pull 后立即恢复工作，无需改配置）：`adapters/zcode/iven_hook.py` → `comi_hook.py`、`adapters/codex/iven_codex.py` → `comi_codex.py`、`adapters/opencode/iven_opencode.py` → `comi_opencode.py`、`tools/iven_cli.py` → `comi_cli.py`。argv/stdin/退出码原样透传，映射逻辑只有一份（新脚本），不会语义分叉。
- 新增 tests/test_legacy_shims.py：旧路径 iven_hook.py 收到真实 ZCode Hook stdin 后收件箱必须出现正确的统一事件；其余垫片做静态委托校验。
- DSH 界面内（Web 端）右键菜单按类分组（日常互动/工作状态/生活小动作），与桌面端一致；拖拽松手支持甩抛物理（与 throw_physics.py 同一套常量：抛物线、视口边缘反弹、落地 Q 弹、温柔放下原地停住）；补齐 Web 端运行时合成的 FALL/LAND 剪辑与帧服务白名单。

### 升级

- **ZCode/Codex/OpenCode 钩子用户**：`git pull` 后即恢复，配置无需改动（旧路径垫片长期保留）；也可以把配置里的 `iven_hook.py` 改成 `comi_hook.py`。
- DSH 桌面应用需重启一次并刷新浏览器页面，才能拿到新的 Web 菜单与甩抛物理。

## [2.0.1] - 2026-10-27

修复 v2.0.0 中"DSH 界面内"显示切换在 DSH 桌面应用上完全失效的问题。

### 修复

- DSH 桌面应用（0.2.1-rc.3 宿主）里，适配器的 HTTP 路由对每个请求都抛
  `cannot get property "webRuntime" without inject`——cordis 服务代理不允许读取未声明注入的服务，可选链拦不住代理 getter 的异常，宿主把异常吞成空 body 的 400，页面无法认领显示租约，桌宠总在 6 秒后回桌面。现在 `trustedHosts` 读取失败时安全回退空数组（本机 loopback 本来就放行）。
- 适配器 handler 加了异常守卫：不再被宿主吞成不可诊断的裸 400，改为返回 500 带原因，并把异常栈写入 `~/.comi-pet/../.comi-debug.log` 便于排查。

### 升级

- 直接替换程序并重新加载 DSH 即可；适配器（comi-bridge）随本版一起更新，DSH 桌面应用需重启一次。

## [2.0.0] - 2026-10-27

角色正式定名 **Comi（可米）**，并发布 v2.0.0。她最早是 comfy-agent（ComfyUI 桌面工作台）的工具图标，后来才长成一只桌宠——名字里的 "Com" 就来自那段出身。

### 变更（不含破坏性迁移）

- **角色改名**：Iven → **Comi（可米）**。窗口标题、气泡署名、右键菜单、README（中/英）、适配器文档统一更新。
- **安装包改名**：`IvenPet.app` / `IvenPet.exe` → `ComiPet.app` / `ComiPet.exe`。
- **适配器改名**：DSH 插件包 `iven-bridge` → `comi-bridge`，配套 `characters/iven-pet` → `characters/comi-pet`、素材目录 `assets/iven-v2` → `assets/comi-v2`、脚本 `export_iven_v2.py`/`iven_cli.py` → `export_comi_v2.py`/`comi_cli.py`。
- **环境变量改名**：`IVEN_BRIDGE_DIR` / `IVEN_CHAT_DIR` / `IVEN_API_DIR` / `IVEN_CONFIG_DIR` → `COMI_*`（旧名仍可读）。

### 兼容与升级

- **配置与数据自动沿用**：尚在使用旧目录 `~/.iven-pet` 的用户会被自动识别并继续读原目录，配置、对话记忆、事件历史、休眠状态都不丢。只有全新安装才会创建 `~/.comi-pet`。
- **旧环境变量仍生效**：`COMI_*` 优先，未设置时回退到 `IVEN_*`，脚本与 CI 无需立刻改。
- **升级方式**：直接替换程序即可（Mac 拖出旧 `IvenPet.app` 换成 `ComiPet.app`；Windows 替换 `IvenPet.exe`）。DSH 适配器需重新安装一次新包名（旧 `iven-bridge` 目录可删）。
- 首次启动会在 `~/.iven-pet`（老用户）或 `~/.comi-pet`（新用户）继续读写，不需要手动迁移任何文件。

### 新增

- 右键菜单按类分组（参考 dsh-pet）：顶层精简为「说话/和 Comi 说话 · 动作 ▸ · 陪伴 ▸ · 语言 ▸ · 关于与更新 ▸ · 退出」。「动作」再分日常互动 / 工作状态 / 生活小动作三级；「陪伴」收纳显示模式、跟踪 Harness、固定位置、自动轮播、宿主桥接、系统通知；「关于与更新」收纳版本号、检查更新与 GitHub 入口。空分类不挂出。新增 test_menu_structure.py 防止菜单再退化成长列表。
- 新版本检查：启动约 4 秒后静默探测 GitHub Release——只请求 `releases/latest` 的跳转地址并读取 tag，不调用 API、不上传任何本机内容；发现新版本时气泡提示（桌宠隐藏时改用系统通知），右键菜单出现"下载新版本 vX…"，另有"检查更新…"手动项与"启动时检查更新"开关（`~/.comi-pet/config.json` 的 `update_check`，默认 auto）。网络不可用时静默失败，绝不打扰。
- 甩抛物理：拖拽时记录指针速度，松手甩出即抛物线飞行——屏幕左右/顶部边缘反弹、落地按剩余能量弹跳（每次衰减），温柔放下则原地落定；Mac 端落地与弹跳瞬间有 CALayer Q 弹挤压动画，Windows 端复用弹跳帧。物理语义两端一致（`throw_physics.py` 纯函数 + Swift 镜像 + 双端测试）。
- 系统通知：任务完成、出问题、等待确认这三类一次性事件可弹原生系统通知（macOS `osascript` / Windows `Shell_NotifyIcon` 气泡）。默认"自动"——仅桌宠隐藏（DSH 界面内模式）时才弹，另有"总是/关闭"；同类通知 8 秒限流，正文只含状态与任务标签。
- 配置持久化（`~/.comi-pet/config.json`）：重启后回到上次离开的位置（坐标系标记隔离 Tk/Cocoa 两端）；通知模式持久化。右键菜单可切换系统通知模式。
- 本机文件控制接口（`~/.comi-pet/api`，[docs/API.md](docs/API.md)）：其他插件或脚本可让 Comi 说话（`say`）、点播动作（`play`）、入睡/唤醒、读实况（每秒原子写 `~/.comi-pet/state.json`）。零网络零端口；配套命令行 `python tools/comi_cli.py`。
- 四个生活小动作（全部复用已验收帧，无新像素）：困倦眨眼（YAWN）、委屈表情（STOMP）、挥手庆祝（CELEBRATE）、左右观察（SEARCH），加入自动轮播与右键菜单。
- 新动作素材生产线（[docs/ASSET_RECIPE.md](docs/ASSET_RECIPE.md)）：提示词配方（角色一致性约束 + 绿幕视频/图像两条生成路线）+ `tools/import_action.py` 一键打包 + 分部位配色/比例/首尾检查与离线逐帧验收。

## [1.0.1] - 2026-10-21

修复"DSH 界面内"显示切换在 DSH 未运行时桌宠失联的问题。

### 修复

- DSH 界面内模式改为两段式显示租约：桌宠只在 DSH 网页确认接手（认领显示权并写入 client_id）后才隐藏；约 6 秒无人接手自动回到桌面并弹出提示，不再出现选择内嵌后消失几十秒的情况。
- 内嵌请求改用 6 秒确认窗口租约（原为一次性 30 秒租约即隐藏）。已接手后页面断开仍按租期（最长 30 秒）恢复桌面显示，行为不变。
- 菜单提示文案同步更新（中/英）："内嵌需 DSH 网页接手；约 6 秒未接手自动回桌面"。

### 文档

- README（中文/英文）新增桥接工作状态实拍截图：跟随 ZCode 时的状态气泡、任务标签与来源徽章。

### 兼容性

- DSH 适配器无需更新：认领/心跳协议向后兼容，旧插件可直接配合新版桌宠。
- 其余范围与限制同 v1.0.0（Mac 包临时签名未公证；不支持跟随正在使用的 Codex 桌面会话）。

## [1.0.0] - 2026-10-18

首个公开打包版本：Comi 独立 3D 绒质桌宠，支持 macOS 与 Windows。

### 新增

- macOS 原生透明窗口，支持拖拽、重力下落、固定位置和约 60fps 渲染。
- Windows 桌面漫游、窗口顶边平台、鼠标互动、开场演出和随机台词。
- 长段动作轮播，保留 75% 播放速度；伸懒腰、打瞌睡、玩魔方等生活动作约持续 11–21 秒。
- 苦思冥想、等待不耐烦、额度不足、松口气四组主题时间线，复用已确认的原版帧；额度不足仅为手动表演。
- DSH、ZCode 本地状态桥接、持续工作气泡、权限等待提醒和来源选择菜单。
- DSH 界面内 / 独立桌面显示切换；页面失联后通过短期租约恢复独立桌宠。
- 跟随系统 / 简体中文 / English 菜单语言切换，保存选择；菜单可打开 GitHub 仓库。
- Windows x64、macOS 通用包与 SHA-256 校验文件；自动构建与发布工作流。

### 修复

- Mac 透明窗口残影、向上拖拽坐标和气泡位置。
- 多来源会话混淆、状态提醒过早消失，以及等待确认后不能恢复工作动画的问题。
- 自主工作 / 等待动作被空闲桥接取消、动画提前截断和短时间频繁换动作的问题。
- 补充动作的尺寸和配色统一；本次新增主题编排没有修改原版 PNG/GIF。

### 范围与限制

- DSH 界面内模式需安装适配器并重新加载 DSH；独立程序需保持运行，才能在页面关闭后恢复桌面显示。真实宿主仍需用户环境验收，已完成隔离界面验收。
- 当前无法跟随正在使用的 Codex 桌面会话。Claude Code、Cursor、OpenCode 适配器仍需实际客户端验收。
- Windows 程序经 CI 构建和测试，桌面透明与窗口交互仍需 Windows 实机验收。
- macOS 13+；通用包覆盖 Apple Silicon 与 Intel，采用临时签名，未做 Apple 公证。
- 不包含桌宠制作器；Linux 暂不支持。
