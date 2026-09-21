"""Jev Quality Decision Gate · CLI 入口。

用法：
    python tools/jev/evaluate.py <evidence.json> --mock    # 离线确定性判定（POC 主路径）
    python tools/jev/evaluate.py <evidence.json> --jev     # 真实 Jev API（未实现，恒 REVIEW）
    python tools/jev/evaluate.py --selftest                # 跑 tests/jev 三个决策用例

管线：客观测试产出事实 → evidence.json → 本工具 → PASS / REVIEW / FAIL。
Jev 只对照 schema.THRESHOLDS（源自既有验收标准）判断，不发明标准、不修改素材与运行时。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "tools"))

from decision import jev_decide, mock_decide  # noqa: E402
from schema import SCHEMA_VERSION, THRESHOLDS, validate_evidence  # noqa: E402

REPO = HERE.parents[1]


def evaluate(path: Path, mode: str = "mock") -> dict:
    ev = json.loads(path.read_text(encoding="utf-8"))
    ok, missing = validate_evidence(ev)
    if not ok:
        return {
            "decision": "REVIEW",
            "confidence": 0.5,
            "reasons": [f"evidence 结构不完整，缺少字段: {', '.join(missing)}"],
            "requires_human_review": True,
        }
    decide = mock_decide if mode == "mock" else jev_decide
    out = decide(ev)
    out["evidence"] = str(path)
    out["mode"] = mode
    out["schema_version"] = SCHEMA_VERSION
    return out


def render(out: dict) -> str:
    icon = {"PASS": "✅", "REVIEW": "⚠️", "FAIL": "❌"}[out["decision"]]
    lines = [
        "=" * 60,
        f"Jev Quality Gate   {icon} {out['decision']}   (confidence {out['confidence']})",
        f"mode={out['mode']}  schema={out.get('schema_version', '?')}  evidence={out.get('evidence', '-')}",
        "-" * 60,
    ]
    for chk in out.get("checks", []):
        mark = {"PASS": "PASS  ", "REVIEW": "REVIEW", "FAIL": "FAIL  "}[chk["status"]]
        name = chk["check"].replace("visual_quality.", "").replace("motion_quality.", "")
        name = name.replace("asset.", "").replace("runtime.", "")
        line = f"  {mark}  {name}: {chk['measurement']}"
        lines.append(line)
        if chk["status"] != "PASS":
            if chk.get("reason"):
                lines.append(f"          reason: {chk['reason']}")
            if chk.get("classification"):
                lines.append(f"          class : {chk['classification']}  ← {chk.get('standard_source', '')}")
    if not out.get("checks"):
        for r in out["reasons"]:
            lines.append(f"  · {r}")
    lines.append("-" * 60)
    lines.append(f"Overall: {out['decision']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def selftest() -> int:
    cases = sorted((REPO / "tests" / "jev").glob("*.json"))
    if not cases:
        print("no test cases found in tests/jev/")
        return 2

    def expect_of(stem: str):
        if stem.startswith("pass"):
            return "PASS"
        if stem.startswith("review"):
            return "REVIEW"
        if stem.startswith("fail"):
            return "FAIL"
        return "SKIP"

    failures = 0
    for case in cases:
        want = expect_of(case.stem)
        if want == "SKIP":
            print(f"[skip] {case.name}: 非 evidence 用例（fixture/文档类）")
            continue
        out = evaluate(case, "mock")
        got = out["decision"]
        ok = (want is None) or (got == want)
        failures += 0 if ok else 1
        mark = "ok " if ok else "MISMATCH"
        print(f"[{mark}] {case.name}: expected={want or 'n/a'} got={got}")
        for r in out["reasons"][:4]:
            print(f"       · {r}")
    print(f"{'ALL CASES PASS' if failures == 0 else f'{failures} case(s) failed'}")
    return 1 if failures else 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--selftest":
        return selftest()
    if len(args) < 2:
        print(__doc__)
        return 2
    mode = args[1].lstrip("-")
    if mode not in ("mock", "jev"):
        print(f"unknown mode: {args[1]} (use --mock or --jev)")
        return 2
    out = evaluate(Path(args[0]), mode)
    print(render(out))
    return {"PASS": 0, "REVIEW": 1, "FAIL": 2}[out["decision"]]


if __name__ == "__main__":
    sys.exit(main())
