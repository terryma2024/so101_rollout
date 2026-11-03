"""Prepare 72 color-instructed SmolVLA collection cards; never record or print."""
import csv,json,shlex,argparse
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw
from .render_collection import font,grid,rich,text,signed,W,H,validate
from .common import write_json

ROOT=Path('/data/work/so101-datasets')
OUT=Path('/data/work/so101-evidence/real-robot/smolvla-wide-collection-20261102')

def prepare(output=OUT):
 output.mkdir(parents=True,exist_ok=True)
 batches=[]; counts={'green':0,'red':0}
 for session,split,shift in [('B01','train',3),('B02','train',-3),('B03','val',2)]:
  layouts=[(a,b) for a,b in [('B1','B2'),('C2','C3'),('D3','D4')] for a,b in [(a,b),(b,a)]]
  if session=='B02':layouts=list(reversed(layouts))
  if session=='B03':layouts=layouts[2:]+layouts[:2]
  for color in ['green','red']:
   name=f'real-cube-bowl-smolvla-v2-wide-{session.lower()}-{color}-20261102'
   entries=[]
   for green,red in layouts:
    for dx in [0,shift]:
     counts[color]+=1
     entries.append(dict(id=('G' if color=='green' else 'R')+f'{counts[color]:02}',episode_order=counts[color],planned_episode=len(entries),session=session,split=split,color=color,green=green,red=red,target=green if color=='green' else red,distractor=red if color=='green' else green,variant='格心0' if dx==0 else f'共同列偏移{signed(dx)}mm',target_dx_mm=dx,target_dy_mm=0,target_yaw_deg=0,distractor_dx_mm=dx,distractor_dy_mm=0,distractor_yaw_deg=0,dataset_name=name))
   batches.append(dict(batch=session+'-'+color,session=session,split=split,color=color,dataset_name=name,task=f'Put the {color} cube into the paper bowl',episodes=entries))
 plan=dict(model='SmolVLA',same_model_color_instructions=True,datasets_root=str(ROOT),total=72,new_train=48,new_val=24,preserve_existing=dict(train=214,val=52),notes=['Offsets apply equally to both cubes along increasing paper column numbers.','Rows and yaw remain zero. Bowl, camera and initial robot pose unchanged.','B01 +3mm and B02 -3mm training; B03 +2mm validation. All include zero.','Validation perturbation is independent; sample count does not guarantee sufficient validation.'],batches=batches)
 validate(plan);write_json(Path('tools/plans/smolvla-wide-20261102.json'),plan);write_json(output/'plan.json',plan)
 entries=[e for b in batches for e in b['episodes']]
 fields=list(entries[0])
 for filename,extra in [('placements.csv',[]),('results.csv',['actual_episode','first_grasp_success','in_bowl','keep','notes'])]:
  with (output/filename).open('w') as f:
   writer=csv.DictWriter(f,fieldnames=fields+extra);writer.writeheader();writer.writerows(entries)
 ordered_batches=sorted(batches,key=lambda b: [('B01','green'),('B02','green'),('B03','green'),('B01','red'),('B02','red'),('B03','red')].index((b['session'],b['color'])))
 commands=[shlex.join(['env','TASK='+b['task'],'./record.sh',b['dataset_name'],'12']) for b in ordered_batches]
 (output/'record-commands.sh').write_text('# Run each folder as a separate recording session, from the repository root.\n'+'\n'.join(commands)+'\n')
 (output/'README.md').write_text('# SmolVLA 72条采集计划\n\n同一模型按英文指令选色。新增 train 48 / val 24；保留原 train 214 / val 52。每个录制文件夹独立 planned episode 0..11，填写实际 episode 后核对。实际顺序与PDF一致：B01绿12→B02绿12→B03绿12→B01红12→B02红12→B03红12。按卡号G01–G36、R01–R36顺序采集。B01/B02各颜色训练12条，B03各颜色验证12条。\n\n格心0及两块共同列偏移：B01 +3mm、B02 -3mm、B03 +2mm。行偏移与角度均0，碗、相机与初始姿态沿用原设置。验证微扰独立，样本量不保证充分。网格仅指示格位，偏移按卡片文字。\n\n左右两列各自从上往下读。按卡片B01/B02/B03切换文件夹，不将不同颜色或session混录。\n\n```sh\n'+'\n'.join(commands)+'\n```\n')
 allpages=[]
 for color in ['green','red']:
  cn='绿' if color=='green' else '红';bs=[b for b in batches if b['color']==color];es=[e for b in bs for e in b['episodes']];pages=[]
  for p,offset in enumerate([0,20]):
   subset=es[offset:offset+20];im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im)
   text(d,(90,22),f'SmolVLA 同一模型 · 抓{cn} · {subset[0]["id"]}-{subset[-1]["id"]}',font(54,True))
   text(d,(90,100),'录制根目录：'+str(ROOT)+' /',font(29))
   for i,b in enumerate(bs):text(d,(90,145+i*43),f'{b["session"]} {b["split"]} → {b["dataset_name"]}',font(29,True))
   text(d,(90,284),'TASK="'+bs[0]['task']+'"',font(32,True))
   text(d,(90,334),'→正数沿纸面1→4；↑正数沿A→D；单位mm，格心为0。θ为俯视顺时针角。',font(29))
   text(d,(90,377),'各folder独立计划ep 0..11；填实际ep。非零偏移红色粗体；图示格位，精确偏移看文字。',font(29))
   for i,e in enumerate(subset):
    x=90+(i//10)*1170;y=435+(i%10)*282;width=1135
    d.rectangle((x,y,x+width,y+272),outline='#999999',width=2)
    text(d,(x+16,y+5),f'{e["id"]}  {e["session"]} {e["split"]}  计划ep {e["planned_episode"]:02}',font(33,True),limit=x+width-300)
    grid(d,x+width-270,y+25,e)
    for prefix,label,yy in [('target','目标'+cn,54),('distractor','干扰'+('红' if color=='green' else '绿'),100)]:
     dx=e[prefix+'_dx_mm'];rich(d,x+16,y+yy,[(label+e[prefix]+'：',False),('→'+signed(dx),dx!=0),(' ↑0 mm；θ0°',False)],31,x+width-300)
    text(d,(x+16,y+157),'实际ep____ 首抓 □成 □败  入碗 □是 □否',font(29),limit=x+width-300)
    text(d,(x+16,y+213),'□收录 □待剔除 备注：________________',font(28),limit=x+width-300)
   text(d,(90,3315),'碗、相机、初始姿态沿用原设置；两块共同列偏移，行偏移0、角度0。',font(30))
   text(d,(90,3370),'录制顺序：B01绿12→红12；B02红12→绿12；B03绿12→红12。同批双色完成再换批。',font(29))
   text(d,(90,3420),f'本色36条 · 第{p+1}/2页 · 新增合计72条（train48 / val24）· 保留原214/52条',font(29))
   stem=f'{color}-page{p+1}';im.save(output/(stem+'.png'));preview=im.copy();preview.thumbnail((1600,1600));preview.save(output/(stem+'-preview.png'));pages.append(im)
  pages[0].save(output/(color+'-cards.pdf'),save_all=True,append_images=pages[1:],resolution=300);allpages.extend(pages)
 allpages[0].save(output/'print-all.pdf',save_all=True,append_images=allpages[1:],resolution=300)
 assert Counter(e['color'] for e in entries)=={'green':36,'red':36}
 assert Counter(e['split'] for e in entries)=={'train':48,'val':24}
 assert all(len(b['episodes'])==12 and [e['planned_episode'] for e in b['episodes']]==list(range(12)) for b in batches)
 # For each session/physical layout, both target-color tasks use identical perturbations.
 for session in ['B01','B02','B03']:
  groups=[[ (e['green'],e['red'],e['target_dx_mm']) for e in b['episodes']] for b in batches if b['session']==session]
  assert groups[0]==groups[1]
 verification=dict(total=len(entries),colors=dict(Counter(e['color'] for e in entries)),splits=dict(Counter(e['split'] for e in entries)),folder_counts={b['dataset_name']:len(b['episodes']) for b in batches},pdf_pages=4,previews={p.name:Image.open(p).size for p in output.glob('*-preview.png')},original_dimensions=[W,H],same_layout_variations_across_colors=True,record_commands=commands,visual_review='pending')
 write_json(output/'verification.json',verification)
 return output
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args();print(prepare(args.output))
