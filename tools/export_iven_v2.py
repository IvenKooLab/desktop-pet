"""Export the approved Pets atlas to both Windows runtime character locations.

Only fits/encodes existing validated pixels. Never redraws or scales poses alone.
Run with Pillow at build time; the pet runtime remains standard-library only.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets/iven-v2/spritesheet.png"
STATES = [("idle",6,[280,110,110,140,140,320]),
          ("right",8,[120]*7+[220]), ("left",8,[120]*7+[220]),
          ("wave",4,[140]*3+[280]), ("jump",5,[140]*4+[280]),
          ("failed",8,[140]*7+[240]), ("waiting",6,[150]*5+[260]),
          ("work",6,[120]*5+[220]), ("review",6,[150]*5+[280])]

def export(source, destinations):
    atlas = Image.open(source).convert("RGBA")
    if atlas.size != (1536,2288):
        raise ValueError("Expected the validated v2 1536x2288 atlas")
    images, rows, durations = {}, {}, {}
    for row,(state,count,times) in enumerate(STATES):
        rows[state],durations[state] = [],times
        for column in range(count):
            name = f"{state}_{column}"
            images[name] = atlas.crop((column*192,row*208,(column+1)*192,(row+1)*208))
            rows[state].append(name)
    for index in range(16):
        row,column = 9+index//8,index%8
        images[f"look_{index}"] = atlas.crop((column*192,row*208,(column+1)*192,(row+1)*208))
    aliases = {"fall_0":"jump_2", "land_0":"jump_4", "sleep_0":"idle_3",
               "sleep_1":"idle_3", "greet_0":"wave_1", "shy_0":"waiting_2",
               "grab_0":"waiting_1", "grab_1":"waiting_3",
               "bounce_0":"jump_0", "bounce_1":"jump_2",
               "happy_0":"wave_1", "happy_1":"wave_2",
               "cheer_0":"work_0", "cheer_1":"work_3",
               "spin_0":"look_0", "spin_1":"look_4", "spin_2":"look_8", "spin_3":"look_12"}
    for direction,state in (("r","right"),("l","left")):
        for index in range(8):
            aliases[f"av_walk_{direction}_{index:02d}"] = f"{state}_{index}"
        for index in range(2):
            aliases[f"fast_{direction}_{index}"] = f"{state}_{index}"
    images.update({alias:images[name] for alias,name in aliases.items()})
    mapping = {"IDLE":"idle", "WALK_r":"right", "WALK_l":"left",
               "RUN_r":"right", "RUN_l":"left", "GREET":"wave",
               "BOUNCE":"jump", "HAPPY":"wave", "SHY":"waiting",
               "CHEER":"work", "GRAB":"waiting",
               "WAITING":"waiting", "WORK":"work", "REVIEW":"review", "FAILED":"failed"}
    clips = {state:{"frames":rows[row],"durations":durations[row]}
             for state,row in mapping.items()}
    for state in ("RUN_r","RUN_l"):
        clips[state]["durations"] = [max(50,round(d*.65)) for d in clips[state]["durations"]]
    clips["SLEEP"] = {"frames":["sleep_0"],"durations":[2000]}
    clips["SPIN"] = {"frames":[f"look_{i}" for i in range(16)],"durations":[100]*16}
    manifest = {"version":1,"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
                "canvas":[200,200],"scale":200/208,"foot_baseline":193,
                "style":"original-3d-plush","motion":"directional hopping",
                "clips":clips}
    encoded, transparent = {}, {}
    for name,image in images.items():
        # One shared affine fit for every pose: 192x208 -> 185x200, centered.
        sprite = image.resize((185,200),Image.Resampling.LANCZOS)
        alpha_canvas = Image.new("RGBA", (200,200), (0,0,0,0))
        alpha_canvas.alpha_composite(sprite, (7,0))
        transparent[name] = alpha_canvas
        mask = sprite.getchannel("A").point(lambda a:255 if a>=128 else 0)
        canvas = Image.new("RGB",(200,200),(255,0,255))
        canvas.paste(sprite.convert("RGB"),(7,0),mask)
        encoded[name] = canvas
    # Additional actions share one scale and baseline; no per-pose resizing.
    extra_dir = ROOT / "assets/iven-v2/actions"
    spec = json.loads((extra_dir / "little-breaks.json").read_text())
    extra_source = extra_dir / spec["source"]
    if hashlib.sha256(extra_source.read_bytes()).hexdigest() != spec["sha256"]:
        raise ValueError("Additional action source does not match its checked manifest")
    extra = Image.open(extra_source).convert("RGBA")
    factor = spec["scale"]
    for row, action in enumerate(spec["actions"]):
        names = []
        for column in range(6):
            name = action["name"].lower() + "_" + str(column)
            names.append(name)
            x0,x1 = spec["columns"][column:column+2]
            y0,y1 = spec["rows"][row:row+2]
            cell = extra.crop((x0,y0,x1,y1))
            sprite = cell.resize((round(cell.width*factor),round(cell.height*factor)),Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA",(200,200),(0,0,0,0))
            center = spec["centers"][column]-x0
            canvas.alpha_composite(sprite,(round(100-center*factor),round(193-spec["baselines"][row]*factor)))
            transparent[name] = canvas
            gif = Image.new("RGB",(200,200),(255,0,255))
            gif.paste(canvas.convert("RGB"),(0,0),canvas.getchannel("A").point(lambda a:255 if a>=128 else 0))
            encoded[name] = gif
        if action["name"] in ("STRETCH","DOZE"):
            # The established idle pose brackets the new performance.
            names = ["idle_0"] + names[1:-1] + ["idle_0"]
        manifest["clips"][action["name"]] = {"frames":names,"durations":action["durations"]}
    manifest["additional_source_sha256"] = spec["sha256"]
    for destination in destinations:
        destination.mkdir(parents=True,exist_ok=True)
        for name,image in encoded.items():
            image.save(destination/(name+".gif"))
            transparent[name].save(destination/(name+".png"))
        (destination/"animation.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=SOURCE)
    args = parser.parse_args()
    validation = json.loads((args.source.parent/"validation.json").read_text(encoding="utf-8"))
    actual_sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if validation.get("ok") is not True or validation.get("sha256") != actual_sha:
        raise ValueError("Source atlas must match its successful validation.json report")
    targets = [ROOT/"frames3d"]
    for target in targets:
        archive = ROOT/"assets/legacy-pre-iven-v2/builtin"
        if not (target/"animation.json").exists():
            archive.mkdir(parents=True,exist_ok=True)
            for image in target.glob("*.gif"):
                shutil.move(str(image),str(archive/image.name))
    result = export(args.source,targets)
    print(json.dumps({"ok":True,"destinations":[str(p) for p in targets],
                      "clips":len(result["clips"]),"source_sha256":result["source_sha256"]},indent=2))

if __name__=="__main__":
    main()
