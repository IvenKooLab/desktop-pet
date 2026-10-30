"""Build staged Halloween PNG/GIF frames from explicitly annotated transparent sheets.

Usage: python tools/build_halloween_actions.py --config candidate.json --out pet-work/built

The config is {"version": 1, "actions": [...]}. Each action has name, source,
source_sha256, scale and cells. Cells have box=[left,top,right,bottom], anchor_x,
ground_y and duration_ms. Anchors are LOCAL to their cell, never inferred from
the visible silhouette. All poses of one action use the same scale and map the
annotated origin to (100,193), preserving jumps and prop travel in that space.
This tool never approves artwork or writes the project's frames3d directory.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from PIL import Image

from action_quality import pixel_delta, render_review

ROOT = Path(__file__).resolve().parents[1]
CANVAS = (200, 200)
TARGET_ANCHOR = (100, 193)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _load(config_path):
    config_path = Path(config_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict) or payload.get("version") != 1
            or not isinstance(payload.get("actions"), list) or not payload["actions"]):
        raise ValueError("Config requires version=1 and nonempty actions")
    prepared, used = [], set()
    for action in payload["actions"]:
        if not isinstance(action, dict):
            raise ValueError("Each action must be an object")
        name = action.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in used:
            raise ValueError("Action names must be unique uppercase identifiers")
        used.add(name)
        source_name = action.get("source")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError(f"{name}: source path required")
        source = (config_path.parent / source_name).resolve()
        if source.suffix.lower() != ".png":
            raise ValueError(f"{name}: source must be a transparent PNG")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if action.get("source_sha256") != digest:
            raise ValueError(f"{name}: source_sha256 mismatch")
        with Image.open(source) as image:
            atlas = image.convert("RGBA")
        if atlas.getchannel("A").getextrema()[0] == 255:
            raise ValueError(f"{name}: source has no transparent background")
        scale = action.get("scale")
        if not _finite(scale) or scale <= 0:
            raise ValueError(f"{name}: scale must be finite and positive")
        cells = action.get("cells")
        if not isinstance(cells, list) or not cells:
            raise ValueError(f"{name}: cells must be nonempty")
        expected = action.get("expected_frames", 16)
        if type(expected) is not int or expected <= 0:
            raise ValueError(f"{name}: expected_frames must be a positive integer")
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                raise ValueError(f"{name}/{index}: cell must be an object")
            box = cell.get("box")
            if (not isinstance(box, list) or len(box) != 4
                    or any(type(v) is not int for v in box)
                    or not 0 <= box[0] < box[2] <= atlas.width
                    or not 0 <= box[1] < box[3] <= atlas.height):
                raise ValueError(f"{name}/{index}: integer box outside source canvas")
            width, height = box[2]-box[0], box[3]-box[1]
            if min(round(width*scale), round(height*scale)) < 1:
                raise ValueError(f"{name}/{index}: scale produces an empty image")
            for key, limit in (("anchor_x", width), ("ground_y", height)):
                if not _finite(cell.get(key)) or not 0 <= cell[key] <= limit:
                    raise ValueError(f"{name}/{index}: {key} must be local to cell")
            if type(cell.get("duration_ms")) is not int or cell["duration_ms"] <= 0:
                raise ValueError(f"{name}/{index}: positive integer duration_ms required")
        prepared.append((action, source, digest, atlas))
    return payload, prepared


def save_windows_gif(image, path):
    """Reserve palette entry 255 for transparency; retain the Windows magenta key."""
    rgba = image.convert("RGBA")
    result = rgba.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    palette = result.getpalette()[:765]
    palette += [0] * (765-len(palette))
    result.putpalette(palette + [255, 0, 255])
    result.paste(255, mask=rgba.getchannel("A").point(lambda a: 255 if a < 128 else 0))
    result.save(path, format="GIF", transparency=255, disposal=2, optimize=False)


def build(config_path, output):
    """Validate everything first, then emit only beneath the explicit output path."""
    output = Path(output).resolve()
    runtime = (ROOT / "frames3d").resolve()
    if output == runtime or runtime in output.parents:
        raise ValueError("Build into a staging directory, not frames3d")
    _, prepared = _load(config_path)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "canvas": list(CANVAS), "clips": {}}
    reports = {}
    for action, source, digest, atlas in prepared:
        name, scale = action["name"], action["scale"]
        slug, frames, durations, measures, findings = name.lower(), [], [], [], []
        if len(action["cells"]) != action.get("expected_frames", 16):
            findings.append("frame count differs from expected_frames")
        for index, cell in enumerate(action["cells"]):
            cell_image = atlas.crop(tuple(cell["box"]))
            bbox = cell_image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
            if bbox is None:
                findings.append(f"frame {index}: empty/missing artwork")
            elif (bbox[0] == 0 or bbox[1] == 0 or bbox[2] == cell_image.width or bbox[3] == cell_image.height):
                findings.append(f"frame {index}: artwork touches source cell boundary; inspect clipping/grid bleed")
            sprite = cell_image.resize((round(cell_image.width*scale), round(cell_image.height*scale)), Image.Resampling.LANCZOS)
            offset = (round(TARGET_ANCHOR[0]-cell["anchor_x"]*scale),
                      round(TARGET_ANCHOR[1]-cell["ground_y"]*scale))
            if bbox:
                transformed = [offset[0]+bbox[0]*scale, offset[1]+bbox[1]*scale,
                               offset[0]+bbox[2]*scale, offset[1]+bbox[3]*scale]
                if transformed[0] < 0 or transformed[1] < 0 or transformed[2] > 200 or transformed[3] > 200:
                    findings.append(f"frame {index}: artwork clips runtime canvas")
            canvas = Image.new("RGBA", CANVAS)
            canvas.alpha_composite(sprite, offset)
            runtime_bbox = canvas.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
            if runtime_bbox and (runtime_bbox[0] <= 1 or runtime_bbox[1] <= 1 or runtime_bbox[2] >= 199 or runtime_bbox[3] >= 199):
                findings.append(f"frame {index}: runtime alpha touches outer margin")
            stem = f"{slug}_{index}"
            canvas.save(output / f"{stem}.png")
            save_windows_gif(canvas, output / f"{stem}.gif")
            frames.append((Path(stem + ".png"), canvas))
            durations.append(cell["duration_ms"])
            measures.append({"frame": stem, "source_box": cell["box"], "offset": list(offset),
                             "scale": scale, "runtime_bbox": runtime_bbox})
        deltas = [round(pixel_delta(a[1], b[1]), 5) for a, b in zip(frames, frames[1:])]
        seam = round(pixel_delta(frames[-1][1], frames[0][1]), 5)
        for index, delta in enumerate(deltas):
            if delta > .08:
                findings.append(f"transition {index}->{index+1}: large pixel delta; inspect pose/prop continuity")
        if seam > .035:
            findings.append("loop seam differs >3.5%; inspect return pose")
        manifest["clips"][name] = {"frames": [p.stem for p, _ in frames], "durations": durations}
        report = {"version": 1, "approved": False, "status": "needs_visual_review",
                  "source_sha256": digest, "scale": scale, "frame_count": len(frames),
                  "expected_frames": action.get("expected_frames", 16), "frames": measures,
                  "transition_deltas": deltas, "seam_delta": seam, "findings": findings,
                  "automatic_checks_pass": not findings,
                  "limitations": "Alpha and pixel checks cannot verify character identity, material, anatomy or true continuous motion."}
        reports[name] = report
        (output / f"{slug}-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # A normalized candidate source preserves the exact reviewed 200px pixels.
        # export_comi_v2 can reproduce it with scale=1 and no extra calibration.
        sheets = output / "sheets"
        sheets.mkdir(exist_ok=True)
        normalized = Image.new("RGBA", (CANVAS[0]*len(frames), CANVAS[1]))
        for index, (_, image) in enumerate(frames):
            normalized.paste(image, (index*CANVAS[0], 0))
        normalized_path = sheets / f"{slug}-sheet.png"
        normalized.save(normalized_path)
        normalized_spec = {
            "source": normalized_path.name,
            "sha256": hashlib.sha256(normalized_path.read_bytes()).hexdigest(),
            "columns": [index*CANVAS[0] for index in range(len(frames)+1)],
            "rows": [0, CANVAS[1]],
            "centers": [index*CANVAS[0]+TARGET_ANCHOR[0] for index in range(len(frames))],
            "baselines": [TARGET_ANCHOR[1]], "scale": 1,
            "actions": [{"name": name, "durations": durations}],
            "review": {"approved": False, "report": f"{slug}-qa.json"},
        }
        (sheets / f"{slug}-sheet.json").write_text(json.dumps(normalized_spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (sheets / f"{slug}-qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        render_review(frames, durations, output, slug)
    (output / "animation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "qa.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest, reports = build(args.config, args.out)
    print(json.dumps({"out": str(args.out.resolve()), "actions": list(manifest["clips"]),
                      "approved": False, "findings": {name: report["findings"] for name, report in reports.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
