# 参与 Comi Pet

谢谢你愿意帮忙。这个项目的第一原则是**诚实**：不伪造效果、不宣称没验证过的能力、不把没做完的东西说成做完了。代码和文档都遵守它。

## 最快上手

```bash
git clone https://github.com/IvenKooLab/desktop-pet
cd desktop-pet

# macOS：双击 start-mac.command 即可（首次会编译，需要 xcode-select --install）
# Windows：python pet.py（Python 3.8+，自带 tkinter）

# 跑测试（运行时零依赖；7 项构建期测试需要 Pillow 等）
python3 -m unittest discover -s tests
pip install -r requirements-dev.txt      # 装上后 7 项不再跳过
```

## 提交之前请自测

仓库的约定是「改哪里就测哪里」：

| 改动 | 必须跑 |
| :--- | :--- |
| 运行时逻辑（`pet.py`、`*.py`） | `python3 -m unittest discover -s tests` |
| macOS 原生端（`native/macos/ComiPet.swift`） | `zsh tools/build_macos.sh` + `build/ComiPet.app/Contents/MacOS/ComiPet --self-test` |
| DSH 适配器（`adapters/dsh/`） | `node adapters/dsh/self-test.mjs` + `node adapters/dsh/web-test.mjs` |
| 素材/时间轴（`frames3d/`、`tools/export_comi_v2.py`） | `python3 tools/export_comi_v2.py --manifest-only` + 上面全部 |

**不要把没跑过的测试说成跑过。** CI 会在 push 后跑完整套件，包括 macOS 通用二进制打包。

## 三条硬约束

1. **角色不改**：Comi 是已批准的 3D 绒质手办造型（紫白短发、青蓝耳机、场记板）。不要重绘、不要换 2D 母版、不要改身体比例。想加新动作，见 [素材配方](docs/ASSET_RECIPE.md)。
2. **运行时保持零依赖**：`pet.py` 只用 Python 标准库；构建期工具才可以用 Pillow/numpy。Mac 端是原生 AppKit，不是 Python。
3. **隐私**：适配器只走本机文件，不发网络请求（新版本检查除外——它只读 GitHub 的跳转地址，可在菜单关闭）。不要引入上传、遥测、账号。

## 常见改动位置

| 想做什么 | 看这里 |
| :--- | :--- |
| 改动作编排 / 加生活小动作 | `tools/export_comi_v2.py` 的 `themed_clips()`，再 `--manifest-only` 导出 |
| 加一个**全新**动作（新像素） | [docs/ASSET_RECIPE.md](docs/ASSET_RECIPE.md) + `tools/import_action.py` |
| 改右键菜单 | `pet.py` 的 `_bind()`；Swift 端 `ComiPet.swift` 的 `contextMenu()` — **两端都要改** |
| 改甩抛手感 | `throw_physics.py` 是权威常量；Swift 的 `ThrowPhysics` 必须同步，测试在 `tests/test_throw_physics.py` 与 `--self-test` |
| 接一个新的编码助手 | `adapters/<name>/`，参考 `adapters/zcode/comi_hook.py` 与 [docs/BRIDGE.md](docs/BRIDGE.md) |
| 改「DSH 界面内」 | `adapters/dsh/comi-bridge/web.js`（宿主）+ `client.js`（页面），两端都要动 |

## 提交信息

用 `type: 一句话说明` 的形式，`type` 取 `feat` / `fix` / `docs` / `test` / `refactor` / `style` / `chore`。正文说清楚**为什么**改，而不只是改了什么。

## 提 Issue

- **Bug**：请附系统与版本（`cat VERSION`、macOS/Windows 版本）、复现步骤、期望与实际。桌宠相关的问题请说明是「独立桌面」还是「DSH 界面内」。
- **功能建议**：先说清楚它解决什么场景。涉及新动作的，请确认素材来源（自绘 / AI 生成 / 复用现有帧）。
- 安全问题请**不要**开公开 issue，直接邮件联系仓库主人。

## 许可

提交即表示你的贡献以 [MIT](LICENSE) 授权。
