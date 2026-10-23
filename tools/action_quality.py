"""Build-time action checks. Measurements flag candidates; they never approve art."""
import math
from PIL import Image, ImageChops, ImageDraw

PARTS = ("hair", "headphones", "clothing", "prop")


def opaque_median(image, boxes):
    """Median per channel over visible pixels in explicitly annotated part regions."""
    pixels = []
    for box in boxes:
        region = image.crop(tuple(box)).convert("RGBA")
        data = region.get_flattened_data() if hasattr(region, "get_flattened_data") else region.getdata()
        pixels.extend(p[:3] for p in data if p[3] >= 192)
    if not pixels:
        raise ValueError("Annotated region has no opaque pixels")
    return tuple(sorted(p[c] for p in pixels)[len(pixels) // 2] for c in range(3))


def pixel_delta(first, second):
    """Mean premultiplied RGBA difference, including silhouettes (0..1)."""
    def premultiply(image):
        r, g, b, a = image.convert("RGBA").split()
        return Image.merge("RGBA", (ImageChops.multiply(r, a),
                                    ImageChops.multiply(g, a), ImageChops.multiply(b, a), a))
    hist = ImageChops.difference(premultiply(first), premultiply(second)).histogram()
    return sum((i % 256) * n for i, n in enumerate(hist)) / (first.width * first.height * 4 * 255)


def validate_annotations(frames, annotation):
    if annotation.get("version") != 1 or not isinstance(annotation.get("frames"), dict):
        raise ValueError("Annotations require version=1 and a frames object")
    if set(annotation["frames"]) != {p.name for p, _ in frames}:
        raise ValueError("Annotations must match every frame filename exactly")
    ref = annotation.get("reference_index", 0)
    if type(ref) is not int or not 0 <= ref < len(frames):
        raise ValueError("Invalid reference_index")
    for path, image in frames:
        item = annotation["frames"][path.name]
        for key in ("head_width", "body_height", "ground_y", "anchor_x", "foot_y"):
            value = item.get(key)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{path.name}: finite {key} required")
        if not 0 < item["body_height"] <= image.height:
            raise ValueError("Invalid body_height")
        if not 0 < item["head_width"] <= image.width:
            raise ValueError("Invalid head_width")
        if not 0 <= item["anchor_x"] <= image.width or not 0 <= item["ground_y"] <= image.height:
            raise ValueError("Anchor/ground outside source canvas")
        if not 0 <= item["foot_y"] <= image.height:
            raise ValueError("foot_y outside source canvas")
        for part in PARTS:
            boxes = item.get("regions", {}).get(part)
            if not isinstance(boxes, list) or not boxes:
                raise ValueError(f"{path.name}: annotate {part}, including visible prop pixels")
            for box in boxes:
                if (not isinstance(box, list) or len(box) != 4
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)):
                    raise ValueError("Region must be a finite x0,y0,x1,y1 box")
                if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
                    raise ValueError("Region outside source canvas")
    return ref


def inspect(frames, annotation, reference, reference_regions, reference_body_to_head=None):
    ref_index = validate_annotations(frames, annotation)
    ref_meta = annotation["frames"][frames[ref_index][0].name]
    baseline = {part: opaque_median(reference, reference_regions[part]) for part in PARTS}
    new_props = annotation.get("prop_policy", "same") == "new"
    if annotation.get("prop_policy", "same") not in ("same", "new"):
        raise ValueError("prop_policy must be same or new")
    if new_props:
        # A cyan mug is not expected to match the original dark clapperboard.
        baseline["prop"] = opaque_median(frames[ref_index][1], ref_meta["regions"]["prop"])
    findings, measures = [], []
    for path, image in frames:
        item = annotation["frames"][path.name]
        colors = {part: opaque_median(image, item["regions"][part]) for part in PARTS}
        deltas = {part: round(math.dist(colors[part], baseline[part]), 2) for part in PARTS}
        box = image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if box and (box[0] <= 1 or box[1] <= 1 or box[2] >= image.width-1 or box[3] >= image.height-1):
            findings.append(f"{path.name}: subject touches source boundary; inspect clipping/grid bleed")
        ratio = item["head_width"] / ref_meta["head_width"]
        body_ratio = item["body_height"] / ref_meta["body_height"]
        if reference_body_to_head is not None:
            proportion = (item["body_height"] / item["head_width"]) / reference_body_to_head
            if abs(proportion - 1) > .12:
                findings.append(f"{path.name}: body/head proportion differs >12% from approved reference")
        if abs(body_ratio - 1) > .08:
            findings.append(f"{path.name}: body scale drift >8%; inspect articulation")
        if abs(ratio - 1) > .06:
            findings.append(f"{path.name}: head scale drift >6%")
        for part, delta in deltas.items():
            if delta > 25:
                findings.append(f"{path.name}: {part} palette drift >25 RGB units")
        # Ground is a coordinate system, NOT the bottom of a jumping/raised-hand bbox.
        if item["ground_y"] != ref_meta["ground_y"] or item["anchor_x"] != ref_meta["anchor_x"]:
            findings.append(f"{path.name}: camera/root calibration changed")
        measures.append({"file": path.name, "head_ratio": round(ratio, 4),
                         "foot_offset": item["foot_y"] - item["ground_y"],
                         "body_ratio": round(body_ratio, 4),
                         "part_rgb_delta": deltas})
    transitions = [round(pixel_delta(a[1], b[1]), 5) for a, b in zip(frames, frames[1:])]
    seam = round(pixel_delta(frames[-1][1], frames[0][1]), 5)
    if seam > .035:
        findings.append("start/end seam differs >3.5%; inspect neutral-pose return")
    for index, delta in enumerate(transitions):
        if delta > .08:
            findings.append(f"transition {index}->{index+1}: large image delta; inspect pop/prop stability")
    for index, (a, b) in enumerate(zip(measures, measures[1:])):
        if abs(a["foot_offset"] - b["foot_offset"]) > ref_meta["head_width"] * .35:
            findings.append(f"transition {index}->{index+1}: large foot displacement; inspect jump/sliding")
    return {"version": 1, "approved": False, "status": "needs_visual_review",
            "automatic_checks_pass": not findings, "findings": findings,
            "frames": measures, "transition_deltas": transitions, "seam_delta": seam,
            "prop_reference": "candidate neutral; new prop design needs visual review" if new_props else "approved character reference",
            "limitations": "Region and landmark annotations must be verified. Image deltas cannot prove anatomy, motion or prop correctness."}


def render_review(frames, durations, out, name):
    """Unmodified artwork on two backgrounds; no recolouring, resizing or erosion."""
    w, h = frames[0][1].size
    for theme, background in (("light", "#f5f5f5"), ("dark", "#20232d")):
        rendered = []
        sheet = Image.new("RGB", (w * min(6, len(frames)), (h + 24) * math.ceil(len(frames) / 6)), background)
        draw = ImageDraw.Draw(sheet)
        for index, (path, frame) in enumerate(frames):
            canvas = Image.new("RGB", frame.size, background)
            canvas.paste(frame, (0, 0), frame.getchannel("A"))
            rendered.append(canvas)
            x, y = (index % 6) * w, (index // 6) * (h + 24)
            sheet.paste(canvas, (x, y + 24))
            draw.text((x + 4, y + 4), f"{index}: {durations[index]}ms", fill="#888888")
        sheet.save(out / f"{name}-contact-{theme}.png")
        rendered[0].save(out / f"{name}-preview-{theme}.gif", save_all=True,
                         append_images=rendered[1:], duration=[round(d / .75) for d in durations],
                         loop=0, disposal=2)
