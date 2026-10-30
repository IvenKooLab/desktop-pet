"""Create an offline, native-size timeline review page from staged sheet specs."""
import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def data_url(image):
    out = BytesIO(); image.save(out, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode('ascii')


def create_page(spec_paths, output):
    cards = []
    for path in spec_paths:
        spec = json.loads(path.read_text())
        sheet = Image.open(path.parent / spec['source']).convert('RGBA')
        qa_path = path.parent / spec.get('review', {}).get('report', '')
        qa = json.loads(qa_path.read_text()) if qa_path.is_file() else {}
        for row, action in enumerate(spec['actions']):
            frames = []
            for index, _ in enumerate(action['durations']):
                x0, x1 = spec['columns'][index:index+2]
                y0, y1 = spec['rows'][row:row+2]
                cell = sheet.crop((x0,y0,x1,y1))
                f = spec['scale']
                # Identical transform to export_comi_v2, one shared scale for all frames.
                native = Image.new('RGBA',(200,200))
                sprite = cell.resize((round(cell.width*f),round(cell.height*f)),Image.Resampling.LANCZOS)
                native.alpha_composite(sprite,(round(100-(spec['centers'][index]-x0)*f),
                                               round(193-(spec['baselines'][row]-y0)*f)))
                frames.append(data_url(native))
            labels = {'TRICK_OR_TREAT':'不给糖就捣蛋', 'GHOST_SHEET':'白布幽灵', 'VAMPIRE_CAPE':'吸血鬼披风', 'WITCH_SPELL':'小女巫施法', 'BLACK_CAT':'黑猫', 'PILOT_YAWN':'哈欠样片', 'PILOT_STOMP':'跺脚样片', 'PILOT_THINK':'持板思考样片', 'PILOT_THINK_SCENE':'桌前思考样片'}
            cards.append({'name':action['name'],'label':labels.get(action['name'], action['name']),'frames':frames,'durations':action['durations'],
                          'findings':qa.get('findings',[]),'approved':spec.get('review',{}).get('approved',False)})
    payload = json.dumps(cards,ensure_ascii=False).replace('</','<\\/')
    reference = data_url(Image.open(ROOT/'frames3d/idle_0.png').convert('RGBA'))
    html = '''<!doctype html><meta charset="utf-8"><title>Comi 动作样片验收</title>
<style>
body{font:16px system-ui;background:#f3f3f6;color:#272334;margin:18px}button{font:inherit;padding:8px 14px;margin:5px;border:1px solid #999;border-radius:8px;cursor:pointer}
main{display:flex;gap:20px;flex-wrap:wrap}.card{background:white;padding:18px;border-radius:14px;width:290px;box-sizing:border-box}h2{font-size:20px;overflow-wrap:anywhere}.stage{background:var(--stage,#fafafa);border:1px solid #aaa;width:200px;height:200px;position:relative}canvas,.reference{width:200px;height:200px}.ground{position:absolute;top:193px;width:200px;border-top:1px dashed #888;pointer-events:none}.warn{color:#a33838}details{max-height:220px;overflow:auto;font-size:13px}input{width:260px}p{max-width:1000px;line-height:1.6}
</style><h1>Comi 新动作：候选验收</h1><p>同一 200px 画幅、固定标定与 75% 播放速度。按输入姿势帧与真实时间轴播放；这不是视频插帧。检查衣服/材质、首尾、脚底线、裁切和道具数量。脚底线是固定地面，跳跃不强行贴地。</p>
<button id="bg">切换深浅背景</button><button id="all">播放/暂停全部</button><main><section class="card"><h2>批准的原版参考</h2><div class="stage"><img class="reference" src="REFERENCE"><div class="ground"></div></div></section></main>
<script>
const cards=PAYLOAD;let dark=false;document.querySelector('#bg').onclick=()=>{dark=!dark;document.body.style.setProperty('--stage',dark?'#20232d':'#fafafa')};
const controllers=[];for(const card of cards){const box=document.createElement('section');box.className='card';const title=document.createElement('h2');title.textContent=card.label;box.append(title);const status=document.createElement('p');status.className='warn';status.textContent=card.approved?'已记录验收':'候选 · 未批准进入默认库';box.append(status);const stage=document.createElement('div');stage.className='stage';const canvas=document.createElement('canvas');canvas.width=canvas.height=200;stage.append(canvas);const line=document.createElement('div');line.className='ground';stage.append(line);box.append(stage);const range=document.createElement('input');range.type='range';range.min=0;range.max=card.frames.length-1;range.step=1;range.value=0;box.append(range);const label=document.createElement('p');box.append(label);const button=document.createElement('button');button.textContent='播放/暂停';box.append(button);const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='检查提示 '+card.findings.length+' 项';details.append(summary);for(const finding of card.findings){const p=document.createElement('p');p.textContent=finding;details.append(p)}box.append(details);document.querySelector('main').append(box);
const images=card.frames.map(src=>{const image=new Image();image.src=src;return image});let playing=false,start=0,offset=0;const total=card.durations.reduce((a,b)=>a+b,0);function draw(index){const ctx=canvas.getContext('2d');ctx.clearRect(0,0,200,200);if(images[index].complete)ctx.drawImage(images[index],0,0);range.value=index;label.textContent=`帧 ${index+1}/${images.length} · ${card.durations[index]}ms素材时间 · 全段 ${(total/750).toFixed(2)}s实际时间`}
function toggle(){if(playing){offset=(performance.now()-start)*.75;playing=false}else{start=performance.now()-offset/.75;playing=true}}button.onclick=toggle;controllers.push(toggle);range.oninput=()=>{playing=false;offset=card.durations.slice(0,+range.value).reduce((a,b)=>a+b,0);draw(+range.value)};images[0].onload=()=>draw(0);draw(0);function tick(now){if(playing){let phase=((now-start)*.75)%total,index=0;while(index<card.durations.length-1&&phase>=card.durations[index])phase-=card.durations[index++];draw(index)}requestAnimationFrame(tick)}requestAnimationFrame(tick)}document.querySelector('#all').onclick=()=>controllers.forEach(toggle);
</script>'''.replace('REFERENCE',reference).replace('PAYLOAD',payload)
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(html)
    print(output.resolve())


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('specs',nargs='+',type=Path);p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();create_page(args.specs,args.out)
