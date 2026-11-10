from PIL import Image,ImageDraw
import json,numpy as np,subprocess
from pathlib import Path
p=Path(__file__).parent;out=[]
for t in range(1,13):
 for c in ['wrist','side']:
  a=np.array(Image.open(p/f'trial-{t:02d}-{c}-frame000.png'));im=Image.fromarray(a);d=ImageDraw.Draw(im)
  if c=='wrist':boxes={'red':[515,327,527,339],'green':[545,248,553,256]} if t<=6 else {'red':[530,220,542,232],'green':[516,315,524,323]}
  else:boxes={'red':[311,226,317,232],'green':[318,254,324,260]} if t<=6 else {'red':[318,254,324,260],'green':[310,227,316,233]}
  for k,(x0,y0,x1,y1) in boxes.items():
   v=a[y0:y1,x0:x1].reshape(-1,3);out.append({'trial':t,'camera':c,'color':k,'box':[x0,y0,x1,y1],'pixels':len(v),'rgb_median':np.median(v,axis=0).tolist(),'zero_fraction_per_rgb':(v==0).mean(axis=0).tolist(),'fraction_max_channel_below32':float((v.max(axis=1)<32).mean())});d.rectangle((x0,y0,x1,y1),outline='yellow',width=1)
  if t in [1,7,12]:im.save(p/f'trial-{t:02d}-{c}-fixed-patches.png')
json.dump(out,open(p/'fixed-patch-statistics.json','w'),indent=2)
for t in [1,7,12]:
 for r in out:
  if r['trial']==t:print(r)
plan=json.load(open('/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package/plan.json'));meta=[]
for t in plan['trials']:
 for c in ['wrist','side']:
  f=next((Path(t['dataset_path'])/'videos'/f'observation.images.{c}').rglob('*.mp4'))
  r=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,pix_fmt,color_range,color_space,color_transfer,color_primaries,r_frame_rate','-of','json',str(f)]));meta.append({'trial':t['id'],'camera':c,'path':str(f),**r})
json.dump(meta,open(p/'video-metadata.json','w'),indent=2);print(meta[:2])
