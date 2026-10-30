"""Render colour-separated collection cards from a reviewed JSON plan (no printing)."""
import argparse
import math
import re
import shlex
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .common import read_json, write_json, new_output

FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
W,H=2480,3508

def font(size,bold=False):
    return ImageFont.truetype(BOLD if bold else FONT,size)

def grid(draw,x,y,e):
 s=55;gap=6
 draw.ellipse((x-72,y+88,x-18,y+142),outline='#666666',width=2)
 for rr in range(4):
  for cc in range(4):
   cell='ABCD'[3-rr]+str(cc+1);bx=x+cc*(s+gap);by=y+rr*(s+gap)
   fill='#16863a' if (cell==e['target'] and e['color']=='green') or (cell==e['distractor'] and e['color']=='red') else '#ce2727' if cell in [e['target'],e['distractor']] else 'white'
   draw.rectangle((bx,by,bx+s,by+s),outline='#777777',fill=fill,width=2)

 for cc in range(4):draw.text((x+cc*(s+gap)+17,y-30),str(cc+1),font=font(24),fill='#555555')
 draw.text((x+244,y+10),'D',font=font(23),fill='#555555');draw.text((x+244,y+193),'A',font=font(23),fill='#555555')
def signed(n):return f'+{n}' if n>0 else str(n)
checks=[]
def text(draw,xy,s,f,fill='black',limit=None):
 if limit is not None:
  assert draw.textbbox(xy,s,font=f)[2]<=limit,(s,draw.textbbox(xy,s,font=f),limit)
 draw.text(xy,s,font=f,fill=fill)
def rich(draw,x,y,segments,size,limit):
 for label,changed in segments:
  f=font(size,changed)
  text(draw,(x,y),label,f,fill='#c00000' if changed else 'black',limit=limit)
  x+=draw.textlength(label,font=f)

def card(draw,x,y,e):
 width=1135;height=284
 draw.rectangle((x,y,x+width,y+height),outline='#999999',width=2)
 color='绿' if e['color']=='green' else '红';other='红' if color=='绿' else '绿'
 changed=any(e[k]!=0 for k in ['target_dx_mm','target_dy_mm','target_yaw_deg','distractor_dx_mm','distractor_dy_mm','distractor_yaw_deg'])
 title=f"{e['id']}  抓{color}  ·  {e['variant']}"
 text(draw,(x+18,y+8),title,font(33,True),fill='#c00000' if changed else 'black',limit=x+width-355)
 grid(draw,x+width-270,y+35,e)
 for role,cn,cell,yy,prefix in [('目标',color,e['target'],57,'target'),('干扰',other,e['distractor'],102,'distractor')]:
  dx,dy,yaw=[e[prefix+k] for k in ['_dx_mm','_dy_mm','_yaw_deg']]
  parts=[(f'{role} {cn}{cell}：',False),(f'→{signed(dx)}',dx!=0),(' ',False),(f'↑{signed(dy)}',dy!=0),(' mm；',False),(f'θ{signed(yaw)}°',yaw!=0)]
  rich(draw,x+18,y+yy,parts,32,x+width-355)
 text(draw,(x+18,y+174),'录制ep____  首抓 □成 □败   入碗 □是 □否',font(31),limit=x+width-355)
 text(draw,(x+18,y+232),'□收录  □待剔除    备注：______________',font(29),limit=x+width-355)
def wrap(s,f,width):
 out=[];line=''
 for ch in s:
  if f.getlength(line+ch)>width:out.append(line);line=ch
  else:line+=ch
 if line:out.append(line)
 return out
def para(draw,x,y,title,body):
 text(draw,(x,y),title,font(38,True));y+=61
 for b in body:
  for line in wrap(b,font(34),1075):text(draw,(x,y),line,font(34));y+=52
 return y+32


def validate(plan):
    names, ids, batch_ids = set(), set(), set()
    for b in plan['batches']:
        bid = b['batch']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', bid) or bid in batch_ids:
            raise ValueError('invalid or duplicate batch name')
        batch_ids.add(bid)
        c = b['color']
        if c not in ['green','red']:
            raise ValueError('invalid color')
        if b['task'] != f'Put the {c} cube into the paper bowl':
            raise ValueError('task does not match batch color')
        name = b['dataset_name']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',name) or name in names:
            raise ValueError('invalid or duplicate dataset name')
        names.add(name)
        if not b['episodes']:
            raise ValueError('empty batch')
        for e in b['episodes']:
            if e['color'] != c:
                raise ValueError('mixed color batch')
            if not re.fullmatch(('G' if c == 'green' else 'R') + r'[0-9]+',e['id']) or e['id'] in ids:
                raise ValueError('invalid or duplicate card id')
            ids.add(e['id'])
            if isinstance(e['episode_order'], bool) or e['episode_order'] != int(e['id'][1:]):
                raise ValueError('card order and id do not match')
            for key in ['target','distractor']:
                if not re.fullmatch(r'[ABCD][1234]',e[key]):
                    raise ValueError('invalid cell')
            if e['target']==e['distractor']:
                raise ValueError('target and distractor occupy same cell')
            for p in ['target','distractor']:
                for suffix in ['_dx_mm','_dy_mm','_yaw_deg']:
                    value=e[p+suffix]
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                        raise ValueError('invalid position/angle')
    return plan


def render(plan,output,datasets_root,batches=None):
    validate(plan)
    if Path(datasets_root).resolve() != Path('/data/work/so101-datasets'):
        raise ValueError('record.sh currently writes only to /data/work/so101-datasets')
    selected=[b for b in plan['batches'] if batches is None or b['batch'] in batches]
    if not selected or (batches and set(batches)-{b['batch'] for b in selected}):
        raise ValueError('unknown or empty batch selection')
    output=new_output(output)
    result=[]
    for batch in selected:
        entries=batch['episodes'];cn='绿' if batch['color']=='green' else '红'
        dataset=Path(datasets_root)/batch['dataset_name']
        command=shlex.join(['env','TASK='+batch['task'],'./record.sh',batch['dataset_name'],str(len(entries))])
        pages=[]
        for offset in range(0,len(entries),20):
            subset=entries[offset:offset+20]
            im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im)
            text(d,(90,43),f"批次{batch['batch']} · 只抓{cn}方块 · {cn}色ACT",font(57,True))
            text(d,(90,129),f"本批{len(entries)}条 | 本页{subset[0]['id']}—{subset[-1]['id']} | 第{offset//20+1}/{math.ceil(len(entries)/20)}页",font(34))
            # Wrap potentially long operator-supplied dataset roots, rather than clipping.
            path_label='录制文件夹：'+str(dataset)
            path_font=font(29)
            if path_font.getlength(path_label)>2300:
                raise ValueError('dataset path too long for card header; use a shorter root')
            text(d,(90,190),path_label,path_font)
            text(d,(90,239),'TASK="'+batch['task']+'"',font(32))
            text(d,(90,292),'→正数沿1→4；↑正数沿A→D；负数反向。单位mm，格心为零；θ为俯视顺时针角。红色粗体须核对。',font(29))
            for i,e in enumerate(subset):
                card(d,90+(i//10)*1170,350+(i%10)*294,e)
            if len(subset)<=10:
                x,y=1290,370
                y=para(d,x,y,'本批编号与数据归属',[
                    f"只采{cn}色，按{subset[0]['id']}—{subset[-1]['id']}依次操作。干扰块保持在卡片指定位置。",
                    f"本文件夹独立编号：计划ep1对应{entries[0]['id']}。卡片号是计划，录制ep填写实际编号。",
                    '本批数据与同色原始示范合并，训练对应ACT。保留颜色任务文本后，也可另建SmolVLA训练集。'])
                y=para(d,x,y,'摆放与统一动作',[
                    '偏移沿纸垫字母数字判断；3 mm用尺量，角度俯视纸垫粗对。θ0°为方块边与格线平行。',
                    '右侧图只标格位，精确偏移和角度以文字为准。非零变化已标红加粗。',
                    '同一折叠位开始，目标上方约20 mm对准，平顺直降；夹稳后方块底部离桌约30 mm再搬运。',
                    '夹爪用可达姿态，不强行独立调整偏航。送到碗内可达且不碰碗的位置松开，稳定入碗约1秒结束。'])
                y=para(d,x,y,'收录要求',[
                    '沿用P0相机、灯光、纸垫和碗位置；空碗、手退出画面后开始。',
                    '只收首次抓取成功的完整示范；空抓、明显推块再追或人工救援标待剔除。',
                    '保留原始失败记录，之后按实际ep筛选干净导出。数值是拟定遥操作参考，不代表已验证最优。'])
                if y>=3290:
                    raise ValueError('instruction panel overflow')
            text(d,(90,3320),f"本文件夹计划ep1对应{entries[0]['id']}；每张填写实际录制ep。左右两列分别从上往下读。",font(30))
            text(d,(90,3370),'统一：上方约20 mm对准→平顺直降→夹稳后底部离桌约30 mm→碗内松开→稳定1秒结束。',font(30))
            text(d,(90,3420),'非零条件红色加粗；红绿分批、分文件夹、分别训练ACT。仅生成采集计划，不自动录制或打印。',font(29))
            stem=f"{batch['batch']}-page{offset//20+1}"
            im.save(output/(stem+'.png'))
            preview=im.copy();preview.thumbnail((1600,1600));preview.save(output/(stem+'-preview.png'))
            pages.append(im)
        pdf=output/(batch['batch']+'-cards.pdf')
        pages[0].save(pdf,save_all=True,append_images=pages[1:],resolution=300)
        (output/(batch['batch']+'-record-command.txt')).write_text(command+'\n')
        result.append(dict(batch=batch['batch'],dataset_root=str(dataset),task=batch['task'],cards=len(entries),pages=len(pages),pdf=str(pdf),record_command=command))
    write_json(output/'render-manifest.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--datasets-root',required=True,type=Path)
    parser.add_argument('--batch',action='append',dest='batches')
    parser.add_argument('--font',default=FONT)
    parser.add_argument('--bold-font',default=BOLD)
    args=parser.parse_args()
    globals()['FONT'],globals()['BOLD']=args.font,args.bold_font
    print(render(read_json(args.plan),args.output,args.datasets_root,args.batches))


if __name__=='__main__':
    main()
