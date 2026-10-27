"""comi_home · 数据目录与环境变量解析（新旧名兼容的唯一入口）。

Comi 曾用名 Iven，因此：
- 数据根目录：`COMI_HOME` > `~/.comi-pet`（已存在）> 旧 `~/.iven-pet`（已存在）> `~/.comi-pet`
  老用户升级后直接用原目录，配置、对话记忆、事件历史都不丢。
- 环境变量：新名优先，旧名兜底（`COMI_BRIDGE_DIR` → `IVEN_BRIDGE_DIR`）。

所有读写 `~/.comi-pet` 的模块都必须经过这里，不要在别处硬编码路径。
"""
import os
from pathlib import Path

LEGACY_SUFFIX = ".iven-pet"
CURRENT_SUFFIX = ".comi-pet"


def _existing_dir(*candidates):
    for candidate in candidates:
        if candidate is not None and Path(candidate).is_dir():
            return Path(candidate)
    return None


def data_dir():
    """数据根目录（配置、events、chat、api、state 都在其下）。"""
    override = env("COMI_HOME")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    current = home / CURRENT_SUFFIX
    if current.is_dir():
        return current
    legacy = _existing_dir(home / LEGACY_SUFFIX)
    return legacy or current


def env(name):
    """读取新环境变量；未设置时回退到旧名（IVEN_*）。"""
    value = os.environ.get(name)
    if value:
        return value
    if name.startswith("COMI_"):
        return os.environ.get("IVEN_" + name[len("COMI_"):]) or None
    return None


def subdir(name):
    return data_dir() / name
