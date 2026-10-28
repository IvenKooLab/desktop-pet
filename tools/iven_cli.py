#!/usr/bin/env python3
"""兼容垫片：v2.0 起本工具改名为 comi_cli.py（角色从 Iven 更名 Comi）。

旧脚本/文档仍引用 iven_cli.py；委托同目录的 comi_cli.py 执行，
argv / 退出码原样透传。新用法请直接使用 comi_cli.py。
"""
import runpy
import sys
from pathlib import Path

sys.argv[0] = "comi_cli.py"
runpy.run_path(str(Path(__file__).resolve().with_name("comi_cli.py")),
               run_name="__main__")
