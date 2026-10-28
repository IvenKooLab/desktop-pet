#!/usr/bin/env python3
"""兼容垫片：v2.0 起本脚本改名为 comi_hook.py（角色从 Iven 更名 Comi）。

旧版 ZCode 配置仍指向 iven_hook.py；为避免升级后钩子集体失效，
这里委托同目录的 comi_hook.py 执行（argv / stdin / 退出码原样透传）。
新配置请直接使用 comi_hook.py；本垫片长期保留，随时可以删除。
"""
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("comi_hook.py")),
               run_name="__main__")
