#!/usr/bin/env python3
"""comi_cli · 桌宠本机控制命令行（协议见 docs/API.md，纯标准库）。

用法：
    python tools/comi_cli.py say "休息一下吧"
    python tools/comi_cli.py play CHEER        # 动作名见 frames3d/animation.json
    python tools/comi_cli.py sleep | wake
    python tools/comi_cli.py state             # 读状态快照（无需桌宠应答）

桌宠独立应用需在运行（Mac：ComiPet.app；Windows：python pet.py）。
请求 15 分钟无人消费会自动清理；回复默认等待 10 秒。
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import control_api  # noqa: E402


def main():
    parser = argparse.ArgumentParser(prog="comi_cli",
                                     description="Comi Pet 本机控制命令行")
    parser.add_argument("action", choices=["say", "play", "sleep", "wake", "state"],
                        help="say TEXT | play STATE | sleep | wake | state")
    parser.add_argument("value", nargs="?", default=None,
                        help="say 的文本或 play 的动作名")
    parser.add_argument("--wait", type=float, default=10.0,
                        help="等待回复的秒数（默认 10）")
    args = parser.parse_args()

    if args.action == "state":
        snap = control_api.read_state(control_api.state_path())
        print(json.dumps(snap, ensure_ascii=False, indent=2) if snap
              else "（还没有状态快照：桌宠独立应用是否在运行？）")
        return 0 if snap else 1

    directory = control_api.api_dir()
    try:
        if args.action == "say":
            if not args.value:
                parser.error("say 需要一段文本")
            request_id = control_api.write_request(directory, "say", text=args.value)
        elif args.action == "play":
            if not args.value:
                parser.error("play 需要一个动作名（如 CHEER、SLEEP、RUN）")
            request_id = control_api.write_request(directory, "play", state=args.value)
        else:
            request_id = control_api.write_request(directory, args.action)
    except OSError as exc:
        print(f"请求写入失败：{exc}", file=sys.stderr)
        return 1

    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        reply = control_api.read_reply(directory, request_id)
        if reply is not None:
            print(json.dumps(reply, ensure_ascii=False, indent=2))
            return 0 if reply.get("ok") else 1
        time.sleep(0.2)
    print("没有等到桌宠回复：独立应用是否在运行？（请求已留下，启动后会被消费）",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
