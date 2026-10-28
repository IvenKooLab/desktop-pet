#!/usr/bin/env python3
"""兼容垫片：v2.0 起本脚本改名为 comi_codex.py（角色从 Iven 更名 Comi）。

旧配置仍指向 iven_codex.py；委托同目录的 comi_codex.py 执行，
argv / stdin / 退出码原样透传。新配置请直接使用 comi_codex.py。
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("comi_codex.py")),
               run_name="__main__")
